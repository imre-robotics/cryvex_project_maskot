#include "battery.h"

static ADC_HandleTypeDef *s_hadc;

void battery_init(ADC_HandleTypeDef *hadc)
{
    s_hadc = hadc;
}

int32_t battery_read_mv(void)
{
    if (HAL_ADC_Start(s_hadc) != HAL_OK) {
        return -1;
    }
    if (HAL_ADC_PollForConversion(s_hadc, 10) != HAL_OK) {
        HAL_ADC_Stop(s_hadc);
        return -1;
    }
    uint32_t raw = HAL_ADC_GetValue(s_hadc);
    HAL_ADC_Stop(s_hadc);

    uint32_t adc_mv = (raw * ADC_VREF_MV) / 4095U;
    return (int32_t)(adc_mv * BATT_DIVIDER_RATIO);
}
