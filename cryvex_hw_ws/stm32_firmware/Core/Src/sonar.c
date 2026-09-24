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
static const SonarPins s_pins[SONAR_COUNT] = {
    [SONAR_FL] = { FL_TRIG_GPIO_Port, FL_TRIG_Pin, FL_ECHO_GPIO_Port, FL_ECHO_Pin },
    [SONAR_FR] = { FR_TRIG_GPIO_Port, FR_TRIG_Pin, FR_ECHO_GPIO_Port, FR_ECHO_Pin },
    [SONAR_RL] = { RL_TRIG_GPIO_Port, RL_TRIG_Pin, RL_ECHO_GPIO_Port, RL_ECHO_Pin },
    [SONAR_RR] = { RR_TRIG_GPIO_Port, RR_TRIG_Pin, RR_ECHO_GPIO_Port, RR_ECHO_Pin },
};

static TIM_HandleTypeDef *s_htim; /* 1 MHz serbest sayac */
static SonarIndex s_active = SONAR_FL;
static volatile uint32_t s_echo_start_us;
static volatile bool s_echo_captured;
static volatile bool s_waiting_echo;
static uint32_t s_trigger_tick_us;
static uint32_t s_last_step_tick_ms;
static int32_t s_last_mm[SONAR_COUNT] = { 9999, 9999, 9999, 9999 };

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
    for (int i = 0; i < SONAR_COUNT; i++) {
        HAL_GPIO_WritePin(s_pins[i].trig_port, s_pins[i].trig_pin, GPIO_PIN_RESET);
    }
    s_active = SONAR_FL;
    s_waiting_echo = false;
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
        s_active = (SonarIndex)((s_active + 1) % SONAR_COUNT);
        return;
    }
    /* Zaman asimi - echo hic gelmedi (menzil disi/sensor bagli degil) */
    if ((uint32_t)(now_us() - s_trigger_tick_us) > SONAR_ECHO_TIMEOUT_US) {
        s_last_mm[s_active] = 9999;
        s_waiting_echo = false;
        s_active = (SonarIndex)((s_active + 1) % SONAR_COUNT);
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
