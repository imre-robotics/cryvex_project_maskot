/* Motor surucu arayuzu: DM556 STEP/DIR (2026-09-18 karari - bkz.
 * stm32_cubemx_ayarlari.md bolum 4, motor surucu ekibinin DMA860H/DM556
 * karsilastirmasi). Onceki hoverboard-UART tasarimi ATLANDI: DM556 basit
 * bir step/dir surucu, kendi icinde tekerlek karisimi/kinematik YAPMAZ -
 * bu yuzden diferansiyel suruş donusumu ARTIK burada (STM32 tarafinda).
 *
 * Motor surucu ekibi FARKLI bir surucu getirirse SADECE bu dosyayi
 * degistirin - protokol/watchdog/sensorler etkilenmez (ayni tasarim ilkesi
 * onceki UART surumunde de gecerliydi). */
#ifndef MOTOR_DRIVER_H
#define MOTOR_DRIVER_H

#include "app_config.h"

void motor_driver_init(TIM_HandleTypeDef *htim_left, TIM_HandleTypeDef *htim_right,
                        ADC_HandleTypeDef *hadc_batt);

/* linear_mm_s / angular_mrad_s -> HEDEF hiz olarak kaydedilir. Gercek cikis
 * hizina ANINDA SICRAMAZ - motor_driver_tick() ivme limitiyle (bkz.
 * app_config.h MAX_ACCEL_MM_S2) hedefe dogru RAMPALAR. Bu, komutun kaynagi
 * Nav2 (otonom) veya telefon (manuel) olsun FARK ETMEKSIZIN uygulanan SON
 * guvenlik katmanidir - step motor ani hizlanmada adim kaybeder. */
void motor_driver_send(int32_t linear_mm_s, int32_t angular_mrad_s);

/* Ana dongudan HER TURDA (protocol_poll ile ayni siklikta) cagrilmali -
 * rampalanmis hizi hesaplar, STEP (degisken frekansli PWM) + DIR + acik-
 * cevrim odometri sayaclarini gunceller. */
void motor_driver_tick(void);

/* Aninda dur (yazilimsal komut / watchdog / e-stop / tampon tetiklendiginde).
 * Rampayi ATLAR - motor_driver_tick() cagrilmasa bile hemen durur. */
void motor_driver_stop(void);

/* Acik-cevrim teker odometrisi (komutlanan step sayisindan turetilir - DM556
 * geri besleme HATTI YOK, bu yuzden GERCEK pozisyon degil TAHMIN'dir; adim
 * kaybi olursa sessizce sapar. AMCL/EKF (robot_localization) bunu LiDAR ile
 * surekli duzeltir - motor surucu ekibinin notu). Kumulatif, isaretli, mm. */
void motor_driver_get_odom(int32_t *left_mm, int32_t *right_mm);

#endif /* MOTOR_DRIVER_H */
