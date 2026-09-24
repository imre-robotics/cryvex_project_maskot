/* 4x HC-SR04 - SIRAYLA tetiklenir (dokumanin "sensorler sirayla tetiklenir"
 * notuyla ayni), TIM2'nin serbest calisan 1 MHz sayaciyla darbe genisligi
 * olculur (EXTI rising/falling kesmeleri). */
#ifndef SONAR_H
#define SONAR_H

#include "app_config.h"

void sonar_init(TIM_HandleTypeDef *htim_us_clock);

/* Ana dongude surekli cagrilir: sirayla bir sonraki sensoru tetikler,
 * zaman asimini kontrol eder. Kesmeler (HAL_GPIO_EXTI_Callback icinden
 * sonar_exti_isr ile) darbe genisligini olcer. */
void sonar_poll(void);

/* En son olculen mesafeler, mm. Menzil disi/timeout -> 9999. */
void sonar_get_all_mm(int32_t out_mm[SONAR_COUNT]);

/* main.c'nin HAL_GPIO_EXTI_Callback'inden cagrilmali (bkz. main_entegrasyon.md). */
void sonar_exti_isr(uint16_t gpio_pin);

#endif /* SONAR_H */
