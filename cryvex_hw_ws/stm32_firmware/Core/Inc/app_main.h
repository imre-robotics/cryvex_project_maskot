/* Tum firmware mantiginin giris noktasi - main.c bu ikisini cagirir. */
#ifndef APP_MAIN_H
#define APP_MAIN_H

#include "app_config.h"

void app_init(UART_HandleTypeDef *huart_pi5, TIM_HandleTypeDef *htim_left_step,
              TIM_HandleTypeDef *htim_right_step, ADC_HandleTypeDef *hadc_batt,
              I2C_HandleTypeDef *hi2c_imu, TIM_HandleTypeDef *htim_us_clock);

void app_loop(void); /* main.c'nin while(1) icinden her turda cagrilir */

#endif /* APP_MAIN_H */
