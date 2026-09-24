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
} WheelState;

static WheelState s_left;
static WheelState s_right;
static uint32_t s_last_tick_ms;

static void wheel_apply(WheelState *w)
{
    /* Yon: isaret DIR pinine, buyukluk STEP frekansina (degisken PWM) gider.
     * DIR isaret kurali (pozitif = ileri) SAHADA teker donus yonuyle
     * dogrulanmali - yanlissa bu tek satiri (GPIO_PIN_SET/RESET) degistirin. */
    HAL_GPIO_WritePin(w->dir_port, w->dir_pin,
                       (w->actual_mm_s >= 0) ? GPIO_PIN_SET : GPIO_PIN_RESET);

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

    s_right.htim = htim_right;
    s_right.channel = TIM_CHANNEL_1;
    s_right.dir_port = RIGHT_DIR_GPIO_Port;
    s_right.dir_pin = RIGHT_DIR_Pin;

    battery_init(hadc_batt);

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
    s_last_tick_ms = now;
    if (dt_ms == 0) dt_ms = 1; /* ayni ms icinde iki cagri - bolme/ilerleme sifir olmasin */
    if (dt_ms > 200) dt_ms = 200; /* uzun bir ara verildiyse (debug/durak) rampayi patlatma */

    /* Motor surucu ekibinin analizi: step motor ani ivmede adim kaybeder -
     * KAYNAK (Nav2/telefon) FARK ETMEKSIZIN burada sinirlanir. */
    int32_t max_delta = (MAX_ACCEL_MM_S2 * (int32_t)dt_ms) / 1000;
    if (max_delta < 1) max_delta = 1;

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
