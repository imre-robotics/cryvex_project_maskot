#include "sonar.h"
#include "main.h" /* CubeMX'in urettigi pin makrolari: FL_TRIG_Pin, FL_TRIG_GPIO_Port, ... */
#include <stdbool.h>

typedef struct {
    GPIO_TypeDef *trig_port;
    uint16_t trig_pin;
    GPIO_TypeDef *echo_port;
    uint16_t echo_pin;
} SonarPins;

/* CubeMX'te User Label'lari TAM OLARAK FL_TRIG/FL_ECHO/FR_TRIG/... verirseniz
 * bu tablo degisiklik gerektirmeden derlenir. */
/* 2026-10-23: ek iki sensor (Nucleo uzerinde Arduino adi yazan pinler secildi):
 *   FC (on orta):   TRIG D7 = PA8,  ECHO D4 = PB5  (EXTI5  -> EXTI9_5_IRQn)
 *   RC (arka orta): TRIG A3 = PB0,  ECHO D6 = PB10 (EXTI10 -> EXTI15_10_IRQn)
 * ECHO hat numaralari (5, 10) mevcut PC0-PC3 (EXTI0-3) ile cakismaz. */
#define FC_TRIG_GPIO_Port GPIOA
#define FC_TRIG_Pin       GPIO_PIN_8
#define FC_ECHO_GPIO_Port GPIOB
#define FC_ECHO_Pin       GPIO_PIN_5
#define RC_TRIG_GPIO_Port GPIOB
#define RC_TRIG_Pin       GPIO_PIN_0
#define RC_ECHO_GPIO_Port GPIOB
#define RC_ECHO_Pin       GPIO_PIN_10

static const SonarPins s_pins[SONAR_COUNT] = {
    [SONAR_FL] = { FL_TRIG_GPIO_Port, FL_TRIG_Pin, FL_ECHO_GPIO_Port, FL_ECHO_Pin },
    [SONAR_FR] = { FR_TRIG_GPIO_Port, FR_TRIG_Pin, FR_ECHO_GPIO_Port, FR_ECHO_Pin },
    [SONAR_RL] = { RL_TRIG_GPIO_Port, RL_TRIG_Pin, RL_ECHO_GPIO_Port, RL_ECHO_Pin },
    [SONAR_RR] = { RR_TRIG_GPIO_Port, RR_TRIG_Pin, RR_ECHO_GPIO_Port, RR_ECHO_Pin },
    [SONAR_FC] = { FC_TRIG_GPIO_Port, FC_TRIG_Pin, FC_ECHO_GPIO_Port, FC_ECHO_Pin },
    [SONAR_RC] = { RC_TRIG_GPIO_Port, RC_TRIG_Pin, RC_ECHO_GPIO_Port, RC_ECHO_Pin },
};

/* Tetikleme sirasi: on/arka donusumlu - ard arda iki komsu sensor birbirinin
 * kalinti yankisini duymasin. */
static const SonarIndex s_sira[SONAR_COUNT] = { SONAR_FL, SONAR_RR, SONAR_FC, SONAR_RL, SONAR_FR, SONAR_RC };
static int s_sira_i = 0;

static TIM_HandleTypeDef *s_htim; /* 1 MHz serbest sayac */
static SonarIndex s_active = SONAR_FL;
static volatile uint32_t s_echo_start_us;
static volatile bool s_echo_captured;
static volatile bool s_waiting_echo;
static uint32_t s_trigger_tick_us;
static uint32_t s_last_step_tick_ms;
static int32_t s_last_mm[SONAR_COUNT] = { 9999, 9999, 9999, 9999, 9999, 9999 };

/* Ardisik tetiklemeler arasi minimum bosluk - onceki sensorun kalinti
 * yankisi (oda ici cok yakin yuzeylerden) bir sonrakini yanlis tetiklemesin
 * diye (HC-SR04 pratigi: ayni sensor icin >=60ms, farkli sensorler icin
 * daha az yeterli - 4 sensor / 60ms donguye bolununce ~15ms). */
#define SONAR_STEP_GAP_MS (SONAR_TRIGGER_PERIOD_MS / SONAR_COUNT)

static inline uint32_t now_us(void) { return __HAL_TIM_GET_COUNTER(s_htim); }

void sonar_init(TIM_HandleTypeDef *htim_us_clock)
{
    s_htim = htim_us_clock;
    HAL_TIM_Base_Start(s_htim);

    __HAL_RCC_GPIOA_CLK_ENABLE();
    __HAL_RCC_GPIOB_CLK_ENABLE();
    __HAL_RCC_GPIOC_CLK_ENABLE();
    GPIO_InitTypeDef g = {0};
    /* Ek TRIG cikislari */
    g.Mode = GPIO_MODE_OUTPUT_PP; g.Pull = GPIO_NOPULL; g.Speed = GPIO_SPEED_FREQ_LOW;
    g.Pin = FC_TRIG_Pin; HAL_GPIO_Init(FC_TRIG_GPIO_Port, &g);
    g.Pin = RC_TRIG_Pin; HAL_GPIO_Init(RC_TRIG_GPIO_Port, &g);
    /* BUTUN ECHO girisleri IKI kenarda kesme: yukselen = olcum basladi,
     * dusen = bitti (sonar_exti_isr). CubeMX ayari (.ioc) PC0-3'u sadece
     * YUKSELEN kenarla kuruyordu -> dusen kenar hic gelmez, her olcum zaman
     * asimi (9999) olurdu. Burada CubeMX'ten sonra yeniden kuruluyor.
     * Pull-down: sensor takili degilken hat yuzmesin. */
    g.Mode = GPIO_MODE_IT_RISING_FALLING; g.Pull = GPIO_PULLDOWN;
    g.Pin = FL_ECHO_Pin | FR_ECHO_Pin | RL_ECHO_Pin | RR_ECHO_Pin; HAL_GPIO_Init(GPIOC, &g);
    g.Pin = FC_ECHO_Pin | RC_ECHO_Pin; HAL_GPIO_Init(GPIOB, &g);
    HAL_NVIC_SetPriority(EXTI9_5_IRQn, 1, 0);
    HAL_NVIC_EnableIRQ(EXTI9_5_IRQn);
    HAL_NVIC_SetPriority(EXTI15_10_IRQn, 1, 0);
    HAL_NVIC_EnableIRQ(EXTI15_10_IRQn);

    for (int i = 0; i < SONAR_COUNT; i++) {
        HAL_GPIO_WritePin(s_pins[i].trig_port, s_pins[i].trig_pin, GPIO_PIN_RESET);
    }
    s_sira_i = 0;
    s_active = s_sira[0];
    s_waiting_echo = false;
}

static void sonraki(void)
{
    s_sira_i = (s_sira_i + 1) % SONAR_COUNT;
    s_active = s_sira[s_sira_i];
}

/* Ek sensorlerin kesme hatlari (CubeMX'in stm32f4xx_it.c'sinde yok). */
void EXTI9_5_IRQHandler(void)
{
    HAL_GPIO_EXTI_IRQHandler(FC_ECHO_Pin);
}

void EXTI15_10_IRQHandler(void)
{
    HAL_GPIO_EXTI_IRQHandler(RC_ECHO_Pin);
}

static void trigger_current(void)
{
    const SonarPins *p = &s_pins[s_active];
    HAL_GPIO_WritePin(p->trig_port, p->trig_pin, GPIO_PIN_SET);
    uint32_t t0 = now_us();
    while ((uint32_t)(now_us() - t0) < 10U) { /* 10us TRIG darbesi - HC-SR04 datasheet'i */ }
    HAL_GPIO_WritePin(p->trig_port, p->trig_pin, GPIO_PIN_RESET);
    s_echo_captured = false;
    s_waiting_echo = true;
    s_trigger_tick_us = now_us();
}

void sonar_poll(void)
{
    if (!s_waiting_echo) {
        if ((HAL_GetTick() - s_last_step_tick_ms) < SONAR_STEP_GAP_MS) {
            return; /* onceki sensorun kalinti yankisinin sonmesini bekle */
        }
        s_last_step_tick_ms = HAL_GetTick();
        trigger_current();
        return;
    }
    if (s_echo_captured) {
        s_waiting_echo = false;
        sonraki();
        return;
    }
    /* Zaman asimi - echo hic gelmedi (menzil disi/sensor bagli degil) */
    if ((uint32_t)(now_us() - s_trigger_tick_us) > SONAR_ECHO_TIMEOUT_US) {
        s_last_mm[s_active] = 9999;
        s_waiting_echo = false;
        sonraki();
    }
}

void sonar_exti_isr(uint16_t gpio_pin)
{
    if (!s_waiting_echo) {
        return;
    }
    if (gpio_pin != s_pins[s_active].echo_pin) {
        return; /* baska bir sensorden gecikmis/gurultu kesmesi - yok say */
    }
    GPIO_PinState level = HAL_GPIO_ReadPin(s_pins[s_active].echo_port, gpio_pin);
    if (level == GPIO_PIN_SET) {
        /* yukselen kenar: echo basladi */
        s_echo_start_us = now_us();
    } else {
        /* dusen kenar: echo bitti - darbe genisligini mesafeye cevir */
        uint32_t pulse_us = now_us() - s_echo_start_us;
        /* mesafe(mm) = pulse_us * ses_hizi(0.343 mm/us) / 2 gidis-donus */
        s_last_mm[s_active] = (int32_t)((pulse_us * 343U) / 2000U);
        s_echo_captured = true;
    }
}

void sonar_get_all_mm(int32_t out_mm[SONAR_COUNT])
{
    for (int i = 0; i < SONAR_COUNT; i++) {
        out_mm[i] = s_last_mm[i];
    }
}
