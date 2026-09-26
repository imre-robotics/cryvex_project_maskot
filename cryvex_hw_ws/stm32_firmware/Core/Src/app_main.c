#include "app_main.h"
#include "protocol.h"
#include "motor_driver.h"
#include "battery.h"
#include "sonar.h"
#include "imu.h"
#include "safety.h"

static uint32_t s_last_status_tick;
static int32_t s_last_batt_mv = BATT_LOW_MV;   /* LED icin - durum satiriyla (20 Hz) guncellenir */

/* Kart neden (yeniden) basladi? RCC_CSR bayraklari reset'ten sonra kalir;
 * okuyup temizleriz ki bir sonraki acilis dogru nedeni gostersin. */
static const char *read_reset_cause(void)
{
    uint32_t csr = RCC->CSR;
    const char *cause = "?";
    if (csr & RCC_CSR_IWDGRSTF)      cause = "iwdg";   /* takildi, donanim bekcisi kurtardi */
    else if (csr & RCC_CSR_WWDGRSTF) cause = "wwdg";
    else if (csr & RCC_CSR_SFTRSTF)  cause = "sw";     /* yazilim / yukleyici (-rst) */
    /* Guc verilince donanim PORRSTF ile BIRLIKTE BORRSTF'yi de kaldirir -
     * once POR'a bakilmali, yoksa her acilis "bor" gorunur (2026-09-26). */
    else if (csr & RCC_CSR_PORRSTF)  cause = "power";  /* guc verildi */
    else if (csr & RCC_CSR_BORRSTF)  cause = "bor";    /* calisirken besleme dustu (brown-out) */
    else if (csr & RCC_CSR_PINRSTF)  cause = "pin";    /* reset dugmesi */
    RCC->CSR |= RCC_CSR_RMVF;
    return cause;
}

/* Donanim bekcisi (IWDG) - bkz. app_config.h. Bir kez baslayinca yazilimla
 * DURDURULAMAZ; app_loop her turda besler. Hata ayiklayici CPU'yu durdurunca
 * bekci de dursun (yoksa her "halt" reset'e yol acar). */
static void iwdg_start(void)
{
    DBGMCU->APB1FZ |= DBGMCU_APB1_FZ_DBG_IWDG_STOP;
    IWDG->KR = 0xCCCCU;                 /* baslat (LSI otomatik acilir) */
    IWDG->KR = 0x5555U;                 /* PR/RLR yazma izni */
    IWDG->PR = IWDG_PRESCALER_DIV64;
    IWDG->RLR = IWDG_RELOAD_COUNT;
    while (IWDG->SR != 0U) { }          /* degerler bekcinin saat alanina gecsin */
    IWDG->KR = 0xAAAAU;                 /* sayaci yeniden yukle */
}

/* Nucleo'daki yesil LED (LD2, PA5) - bilgisayarsiz teshis:
 *   surekli yanik      : acil stop / tampon basili (ya da kablosu kopuk)
 *   hizli yanip sonme  : Pi'den komut gelmiyor (200 ms watchdog)
 *   cift yanip sonme   : batarya dusuk
 *   saniyede bir kisa  : her sey yolunda (kalp atisi) */
static void led_init(void)
{
    GPIO_InitTypeDef g = {0};
    __HAL_RCC_GPIOA_CLK_ENABLE();
    g.Pin = GPIO_PIN_5;
    g.Mode = GPIO_MODE_OUTPUT_PP;
    g.Pull = GPIO_NOPULL;
    g.Speed = GPIO_SPEED_FREQ_LOW;
    HAL_GPIO_Init(GPIOA, &g);
}

static void led_update(void)
{
    uint32_t t = HAL_GetTick() % 1000U;
    bool on;
    if (safety_estop_hit() || safety_bumper_hit()) {
        on = true;
    } else if (protocol_watchdog_expired()) {
        on = (t % 250U) < 125U;
    } else if (s_last_batt_mv < BATT_LOW_MV) {
        on = t < 100U || (t >= 200U && t < 300U);
    } else {
        on = t < 80U;
    }
    HAL_GPIO_WritePin(GPIOA, GPIO_PIN_5, on ? GPIO_PIN_SET : GPIO_PIN_RESET);
}

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
    const char *reset_cause = read_reset_cause();
    led_init();
    protocol_init(huart_pi5);
    motor_driver_init(htim_left_step, htim_right_step, hadc_batt);
    sonar_init(htim_us_clock);
    enable_sonar_exti_irqs();
    /* basarisiz olsa da devam eder - imu_wz=0 gonderilir, READY'de imu=0 */
    bool imu_ok = imu_init(hi2c_imu);
    safety_poll();
    s_last_status_tick = HAL_GetTick();
    protocol_set_info(reset_cause, imu_ok);
    protocol_send_ready();
    iwdg_start();   /* EN SON: yavas baslangic adimlari bekciye takilmasin */
}

void app_loop(void)
{
    IWDG->KR = 0xAAAAU;   /* donanim bekcisini besle - dongu takilirsa ~0.5 sn'de reset */
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
        s_last_batt_mv = batt_mv;
        protocol_send_status(mm[SONAR_FL], mm[SONAR_FR], mm[SONAR_RL], mm[SONAR_RR],
                              wz, safety_estop_hit(), safety_bumper_hit(),
                              left_mm, right_mm, batt_mv);
    }
    led_update();
}
