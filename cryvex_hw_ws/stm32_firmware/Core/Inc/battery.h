/* Batarya voltaj olcumu - ADC1_IN4 (PA4), direnc bolucu uzerinden.
 * Sadece bir ESIK OKUMASI saglar - SoC/yuzde takibi veya otomatik sarja
 * donus YAPMAZ (o kapsam disi, bkz. app_config.h BATT_LOW_MV yorumu). */
#ifndef BATTERY_H
#define BATTERY_H

#include "app_config.h"

void battery_init(ADC_HandleTypeDef *hadc);

/* Guncel pil voltajini mV cinsinden dondurur. ADC okunamazsa -1 doner
 * (cagiran taraf bunu "bilinmiyor" olarak ele almali, "0V" degil). */
int32_t battery_read_mv(void);

#endif /* BATTERY_H */
