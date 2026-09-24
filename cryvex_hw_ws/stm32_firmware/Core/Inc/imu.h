/* MPU6050 (GY-521) - sadece Z ekseni acisal hizi okunuyor (robotun donusu,
 * robot_localization EKF'sine gidecek - bkz. docs/stm32_protokol.md). */
#ifndef IMU_H
#define IMU_H

#include "app_config.h"
#include <stdbool.h>

/* I2C1 uzerinden MPU6050'yi uyandirir (PWR_MGMT_1) ve gyro FS_SEL=0
 * (+-250 deg/s) ayarlar. Basarisizsa false doner (sensor bagli degil/ariza -
 * cagiran taraf imu_wz=0 gonderip devam edebilir, kritik degil). */
bool imu_init(I2C_HandleTypeDef *hi2c);

/* Z ekseni acisal hizini mrad/s cinsinden okur. imu_init basarisizsa 0 doner. */
int32_t imu_read_wz_mrad_s(void);

#endif /* IMU_H */
