/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.h
  * @brief          : Header for main.c file.
  *                   This file contains the common defines of the application.
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2026 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */
/* USER CODE END Header */

/* Define to prevent recursive inclusion -------------------------------------*/
#ifndef __MAIN_H
#define __MAIN_H

#ifdef __cplusplus
extern "C" {
#endif

/* Includes ------------------------------------------------------------------*/
#include "stm32f4xx_hal.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */

/* USER CODE END Includes */

/* Exported types ------------------------------------------------------------*/
/* USER CODE BEGIN ET */

/* USER CODE END ET */

/* Exported constants --------------------------------------------------------*/
/* USER CODE BEGIN EC */

/* USER CODE END EC */

/* Exported macro ------------------------------------------------------------*/
/* USER CODE BEGIN EM */

/* USER CODE END EM */

void HAL_TIM_MspPostInit(TIM_HandleTypeDef *htim);

/* Exported functions prototypes ---------------------------------------------*/
void Error_Handler(void);

/* USER CODE BEGIN EFP */

/* USER CODE END EFP */

/* Private defines -----------------------------------------------------------*/
#define FL_ECHO_Pin GPIO_PIN_0
#define FL_ECHO_GPIO_Port GPIOC
#define FR_ECHO_Pin GPIO_PIN_1
#define FR_ECHO_GPIO_Port GPIOC
#define RL_ECHO_Pin GPIO_PIN_2
#define RL_ECHO_GPIO_Port GPIOC
#define RR_ECHO_Pin GPIO_PIN_3
#define RR_ECHO_GPIO_Port GPIOC
#define BUMPER_Pin GPIO_PIN_0
#define BUMPER_GPIO_Port GPIOA
#define ESTOP_SENSE_Pin GPIO_PIN_1
#define ESTOP_SENSE_GPIO_Port GPIOA
#define BATT_VSENSE_Pin GPIO_PIN_4
#define BATT_VSENSE_GPIO_Port GPIOA
#define LEFT_STEP_Pin GPIO_PIN_6
#define LEFT_STEP_GPIO_Port GPIOA
#define FL_TRIG_Pin GPIO_PIN_4
#define FL_TRIG_GPIO_Port GPIOC
#define FR_TRIG_Pin GPIO_PIN_5
#define FR_TRIG_GPIO_Port GPIOC
#define RL_TRIG_Pin GPIO_PIN_6
#define RL_TRIG_GPIO_Port GPIOC
#define RR_TRIG_Pin GPIO_PIN_7
#define RR_TRIG_GPIO_Port GPIOC
#define LEFT_DIR_Pin GPIO_PIN_9
#define LEFT_DIR_GPIO_Port GPIOA
#define RIGHT_DIR_Pin GPIO_PIN_10
#define RIGHT_DIR_GPIO_Port GPIOA
#define RIGHT_STEP_Pin GPIO_PIN_6
#define RIGHT_STEP_GPIO_Port GPIOB
#define MOTOR_EN_Pin GPIO_PIN_7
#define MOTOR_EN_GPIO_Port GPIOB

/* USER CODE BEGIN Private defines */

/* USER CODE END Private defines */

#ifdef __cplusplus
}
#endif

#endif /* __MAIN_H */
