#include "imu.h"

#define MPU6050_ADDR      (0x68 << 1) /* AD0 pini GND'ye bagliysa - HAL 8-bit adres bekler */
#define REG_PWR_MGMT_1    0x6B
#define REG_GYRO_CONFIG   0x1B
#define REG_GYRO_ZOUT_H   0x47

/* FS_SEL=0 (+-250 deg/s) -> hassasiyet 131 LSB/(deg/s).
 * mrad/s = raw/131 (deg/s) * (pi/180) * 1000 */
#define GYRO_SENS_TO_MRAD_S (1000.0f * 3.14159265f / 180.0f / 131.0f)

static I2C_HandleTypeDef *s_hi2c;
static bool s_ok;

bool imu_init(I2C_HandleTypeDef *hi2c)
{
    s_hi2c = hi2c;
    s_ok = false;

    uint8_t wake = 0x00;
    if (HAL_I2C_Mem_Write(s_hi2c, MPU6050_ADDR, REG_PWR_MGMT_1, 1, &wake, 1, 100) != HAL_OK) {
        return false;
    }
    HAL_Delay(10);
    uint8_t fs_sel = 0x00;
    if (HAL_I2C_Mem_Write(s_hi2c, MPU6050_ADDR, REG_GYRO_CONFIG, 1, &fs_sel, 1, 100) != HAL_OK) {
        return false;
    }
    s_ok = true;
    return true;
}

int32_t imu_read_wz_mrad_s(void)
{
    if (!s_ok) {
        return 0;
    }
    uint8_t buf[2];
    if (HAL_I2C_Mem_Read(s_hi2c, MPU6050_ADDR, REG_GYRO_ZOUT_H, 1, buf, 2, 50) != HAL_OK) {
        return 0; /* gecici I2C hatasi - bir sonraki turda tekrar denenir */
    }
    int16_t raw = (int16_t)((buf[0] << 8) | buf[1]);
    return (int32_t)(raw * GYRO_SENS_TO_MRAD_S);
}
