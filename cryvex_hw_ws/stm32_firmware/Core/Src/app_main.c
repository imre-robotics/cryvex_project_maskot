#include "app_main.h"
#include "protocol.h"
#include "motor_driver.h"
#include "battery.h"
#include "sonar.h"
#include "imu.h"
#include "safety.h"

static uint32_t s_last_status_tick;

/* CubeMX'in .ioc NVIC scriptlemesi (yorumlanmasi belgelenmemis bir alan
 * formati) EXTI0-3'u guvenilir sekilde etkinlestirmedi - burada ACIKCA,
 * kodla enable ediyoruz. Bu, CubeMX GUI'de "NVIC" sekmesinden EXTI0-3'u
 * elle isaretlemenin YAPTIGI ISI birebir yapar; ileride CubeMX'te bunu
 * dogru sekilde isaretlerseniz bu blok ZARARSIZ sekilde tekrar eder
 * (HAL_NVIC_EnableIRQ ayni IRQ'yu iki kez enable etmekten sikayet etmez). */
static void enable_sonar_exti_irqs(void)
{
    HAL_NVIC_SetPriority(EXTI0_IRQn, 1, 0);
    HAL_NVIC_EnableIRQ(EXTI0_IRQn);
    HAL_NVIC_SetPriority(EXTI1_IRQn, 1, 0);
    HAL_NVIC_EnableIRQ(EXTI1_IRQn);
    HAL_NVIC_SetPriority(EXTI2_IRQn, 1, 0);
    HAL_NVIC_EnableIRQ(EXTI2_IRQn);
    HAL_NVIC_SetPriority(EXTI3_IRQn, 1, 0);
    HAL_NVIC_EnableIRQ(EXTI3_IRQn);
}

void app_init(UART_HandleTypeDef *huart_pi5, TIM_HandleTypeDef *htim_left_step,
              TIM_HandleTypeDef *htim_right_step, ADC_HandleTypeDef *hadc_batt,
              I2C_HandleTypeDef *hi2c_imu, TIM_HandleTypeDef *htim_us_clock)
{
    protocol_init(huart_pi5);
    motor_driver_init(htim_left_step, htim_right_step, hadc_batt);
    sonar_init(htim_us_clock);
    enable_sonar_exti_irqs();
    imu_init(hi2c_imu); /* basarisiz olsa da devam eder - imu_wz=0 gonderilir */
    safety_poll();
    s_last_status_tick = HAL_GetTick();
    protocol_send_ready();
}

void app_loop(void)
{
    protocol_poll();
    sonar_poll();
    safety_poll();

    /* KATMANLI DURMA (dokumanin guvenlik bolumu): watchdog VEYA e-stop VEYA
     * tampon - herhangi biri tetiklenirse motor gucu KOMUTLA da kesilir
     * (donanimsal role zaten e-stop icin ayrica kesiyor, bu YAZILIMSAL ek
     * bir katman). */
    bool stop_needed = protocol_watchdog_expired() || safety_estop_hit() || safety_bumper_hit();

    if (stop_needed) {
        motor_driver_stop();
    } else {
        int32_t lin_mm_s, ang_mrad_s;
        protocol_get_target(&lin_mm_s, &ang_mrad_s);
        motor_driver_send(lin_mm_s, ang_mrad_s);
    }
    /* Rampalama/STEP-DIR cikisi HER TURDA guncellenir - stop_needed olsa
     * bile (motor_driver_stop() zaten hedefi/gercek hizi sifirlar, tick()
     * ekstra zarar vermez, sadece hizli sekilde 0'da kalir). */
    motor_driver_tick();

    uint32_t now = HAL_GetTick();
    if ((now - s_last_status_tick) >= STATUS_REPORT_PERIOD_MS) {
        s_last_status_tick = now;
        int32_t mm[SONAR_COUNT];
        sonar_get_all_mm(mm);
        int32_t wz = imu_read_wz_mrad_s();
        int32_t left_mm, right_mm;
        motor_driver_get_odom(&left_mm, &right_mm);
        int32_t batt_mv = battery_read_mv();
        protocol_send_status(mm[SONAR_FL], mm[SONAR_FR], mm[SONAR_RL], mm[SONAR_RR],
                              wz, safety_estop_hit(), safety_bumper_hit(),
                              left_mm, right_mm, batt_mv);
    }
}
