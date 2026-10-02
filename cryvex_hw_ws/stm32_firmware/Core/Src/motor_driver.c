#include "motor_driver.h"
#include "battery.h"
#include "main.h" /* CubeMX pin makrolari: LEFT_DIR_Pin, MOTOR_EN_Pin, ... */
#include <stdlib.h>
#include <stdbool.h>

/* DM556 basit bir STEP/DIR surucu - tekerlek karisimini kendisi YAPMAZ
 * (hoverboard-hack surucusunun aksine). Bu yuzden diferansiyel suruş
 * kinematigi BURADA: linear+angular -> sol/sag teker hedef hizi (mm/s). */
#define MOTOR_PI 3.14159265f

typedef struct {
    TIM_HandleTypeDef *htim;
    uint32_t channel;
    GPIO_TypeDef *dir_port;
    uint16_t dir_pin;
    int32_t target_mm_s;
    int32_t actual_mm_s;   /* ivme rampasindan gecmis, GERCEKTEN cikisa uygulanan hiz */
    int64_t accum_um;      /* acik-cevrim odometri, mikrometre (tasmaya karsi int64) */
    bool dir_invert;       /* montaj yonu (app_config.h *_WHEEL_DIR_INVERT) - odometriyi etkilemez */
} WheelState;

static WheelState s_left;
static WheelState s_right;
static uint32_t s_last_tick_ms;
static int32_t s_ramp_budget; /* rampa izni, 0.001 mm/s biriminde (1 ms'lik 0.3 mm/s kaybolmasin) */

static void wheel_apply(WheelState *w)
{
    /* Yon: isaret DIR pinine, buyukluk STEP frekansina (degisken PWM) gider.
     * DIR isaret kurali (pozitif = ileri) SAHADA teker donus yonuyle
     * dogrulanmali - yanlissa bu tek satiri (GPIO_PIN_SET/RESET) degistirin. */
    bool forward = (w->actual_mm_s >= 0) != w->dir_invert;
    HAL_GPIO_WritePin(w->dir_port, w->dir_pin, forward ? GPIO_PIN_SET : GPIO_PIN_RESET);

    uint32_t speed_mm_s = (uint32_t)abs(w->actual_mm_s);
    if (speed_mm_s == 0) {
        __HAL_TIM_SET_COMPARE(w->htim, w->channel, 0); /* %0 duty = darbe yok */
        return;
    }
    /* teker hizi (mm/s) -> step frekansi (Hz): cevre = pi*cap, adim/tur sabit. */
    float steps_per_sec = ((float)speed_mm_s * (float)STEPS_PER_REV)
                          / (MOTOR_PI * (float)WHEEL_DIAMETER_MM);
    if (steps_per_sec < 1.0f) {
        __HAL_TIM_SET_COMPARE(w->htim, w->channel, 0);
        return;
    }
    uint32_t arr = (uint32_t)((float)MOTOR_STEP_TIMER_HZ / steps_per_sec);
    if (arr < 4) arr = 4;             /* asiri yuksek frekansta tasma/gecersizlik onlemi */
    if (arr > 0xFFFF) arr = 0xFFFF;   /* TIM3/TIM4 16-bit sayaç */
    __HAL_TIM_SET_AUTORELOAD(w->htim, arr - 1);
    __HAL_TIM_SET_COMPARE(w->htim, w->channel, arr / 2); /* ~%50 duty */
}

/* DM860H opto-izoleli girisleri 5 V ister (kilavuz: PUL/DIR/ENA 4.5-5 V,
 * 7-16 mA, icte 270 ohm). Baglanti ORTAK ANOT: PUL+/DIR+/ENA+ -> Nucleo 5V,
 * PUL-/DIR-/ENA- -> asagidaki STM32 pinleri. Pin LOW = opto LED'i yanar.
 * CubeMX bu pinleri push-pull uretir: 3.3 V'luk HIGH, 5 V'a bagli LED'den
 * hala ~2 mA kacirir (opto yari acik -> rastgele adim). Bu yuzden OPEN-DRAIN:
 * HIGH = pin birakilir, LED tamamen soner. PA6/PA9/PA10/PB6/PB7 5 V
 * toleransli (FT). Burada (kullanici kodunda) yapiliyor ki CubeMX yeniden
 * uretiminde kaybolmasin. */
static void motor_pins_open_drain(void)
{
    GPIO_InitTypeDef g = {0};
    g.Pull = GPIO_NOPULL;

    g.Mode = GPIO_MODE_OUTPUT_OD;
    g.Speed = GPIO_SPEED_FREQ_LOW;
    g.Pin = LEFT_DIR_Pin;
    HAL_GPIO_Init(LEFT_DIR_GPIO_Port, &g);
    g.Pin = RIGHT_DIR_Pin;
    HAL_GPIO_Init(RIGHT_DIR_GPIO_Port, &g);
    g.Pin = MOTOR_EN_Pin;
    HAL_GPIO_Init(MOTOR_EN_GPIO_Port, &g);

    g.Mode = GPIO_MODE_AF_OD;
    g.Speed = GPIO_SPEED_FREQ_HIGH;
    g.Pin = LEFT_STEP_Pin;
    g.Alternate = GPIO_AF2_TIM3;
    HAL_GPIO_Init(LEFT_STEP_GPIO_Port, &g);
    g.Pin = RIGHT_STEP_Pin;
    g.Alternate = GPIO_AF2_TIM4;
    HAL_GPIO_Init(RIGHT_STEP_GPIO_Port, &g);
}

static void motor_en(bool enable)
{
    bool pin_high = MOTOR_EN_ACTIVE_LOW ? !enable : enable;
    HAL_GPIO_WritePin(MOTOR_EN_GPIO_Port, MOTOR_EN_Pin,
                       pin_high ? GPIO_PIN_SET : GPIO_PIN_RESET);
}

void motor_driver_init(TIM_HandleTypeDef *htim_left, TIM_HandleTypeDef *htim_right,
                        ADC_HandleTypeDef *hadc_batt)
{
    s_left.htim = htim_left;
    s_left.channel = TIM_CHANNEL_1;
    s_left.dir_port = LEFT_DIR_GPIO_Port;
    s_left.dir_pin = LEFT_DIR_Pin;
    s_left.dir_invert = LEFT_WHEEL_DIR_INVERT;

    s_right.htim = htim_right;
    s_right.channel = TIM_CHANNEL_1;
    s_right.dir_port = RIGHT_DIR_GPIO_Port;
    s_right.dir_pin = RIGHT_DIR_Pin;
    s_right.dir_invert = RIGHT_WHEEL_DIR_INVERT;

    battery_init(hadc_batt);

    motor_pins_open_drain();
    /* STEP cikis kutbu ters: CCR=0 (dur) iken cikis HIGH = birakilmis -> opto
     * sonuk, durakken surekli akim cekmez. Darbe sirasinda ~%50 doluluk ayni;
     * DM860H kenar ile adim attigi icin kutup adim sayisini degistirmez. */
    s_left.htim->Instance->CCER |= TIM_CCER_CC1P;
    s_right.htim->Instance->CCER |= TIM_CCER_CC1P;

    HAL_TIM_PWM_Start(s_left.htim, s_left.channel);
    HAL_TIM_PWM_Start(s_right.htim, s_right.channel);

    motor_en(true);
    s_last_tick_ms = HAL_GetTick();
    motor_driver_stop();
}

void motor_driver_send(int32_t linear_mm_s, int32_t angular_mrad_s)
{
    /* Diferansiyel suruş: v_sol = v - w*(iz/2), v_sag = v + w*(iz/2)
     * (REP-103: +angular_z = sola donus = sag teker hizlanir). */
    int32_t half_track_term = (angular_mrad_s * (int32_t)(WHEEL_BASE_MM / 2)) / 1000;
    s_left.target_mm_s = linear_mm_s - half_track_term;
    s_right.target_mm_s = linear_mm_s + half_track_term;
}

static int32_t ramp_toward(int32_t actual, int32_t target, int32_t max_delta)
{
    if (actual < target) {
        actual += max_delta;
        if (actual > target) actual = target;
    } else if (actual > target) {
        actual -= max_delta;
        if (actual < target) actual = target;
    }
    return actual;
}

void motor_driver_tick(void)
{
    uint32_t now = HAL_GetTick();
    uint32_t dt_ms = now - s_last_tick_ms;
    /* Ana dongu ms'de yuzlerce kez doner: ayni ms icinde zaman gecmedi, yapacak
     * is yok. (2026-09-26 duzeltmesi: burada dt_ms=1 zorlaniyordu - her cagri
     * 1 ms sayildi, odometri ~130 kat fazla sayiyor ve 0.3 m/s^2 ivme siniri
     * fiilen devre disi kaliyordu: robot hedef hiza ANINDA cikiyordu.) */
    if (dt_ms == 0) return;
    s_last_tick_ms = now;
    if (dt_ms > 200) dt_ms = 200; /* uzun bir ara verildiyse (debug/durak) rampayi patlatma */

    /* Motor surucu ekibinin analizi: step motor ani ivmede adim kaybeder -
     * KAYNAK (Nav2/telefon) FARK ETMEKSIZIN burada sinirlanir. 1 ms'de izin
     * verilen artis 0.3 mm/s (tam sayiya sigmaz) - kusurat biriktirilir. */
    s_ramp_budget += MAX_ACCEL_MM_S2 * (int32_t)dt_ms;
    int32_t max_delta = s_ramp_budget / 1000;
    s_ramp_budget -= max_delta * 1000;

    s_left.actual_mm_s = ramp_toward(s_left.actual_mm_s, s_left.target_mm_s, max_delta);
    s_right.actual_mm_s = ramp_toward(s_right.actual_mm_s, s_right.target_mm_s, max_delta);

    /* acik-cevrim odometri: v[mm/s] * dt[ms] = mesafe[um]. */
    s_left.accum_um += (int64_t)s_left.actual_mm_s * dt_ms;
    s_right.accum_um += (int64_t)s_right.actual_mm_s * dt_ms;

    wheel_apply(&s_left);
    wheel_apply(&s_right);
}

void motor_driver_stop(void)
{
    s_left.target_mm_s = 0;
    s_right.target_mm_s = 0;
    s_left.actual_mm_s = 0;
    s_right.actual_mm_s = 0;
    __HAL_TIM_SET_COMPARE(s_left.htim, s_left.channel, 0);
    __HAL_TIM_SET_COMPARE(s_right.htim, s_right.channel, 0);
}

void motor_driver_get_odom(int32_t *left_mm, int32_t *right_mm)
{
    *left_mm = (int32_t)(s_left.accum_um / 1000);
    *right_mm = (int32_t)(s_right.accum_um / 1000);
}
