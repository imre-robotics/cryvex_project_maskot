/* Pi 5 <-> STM32 seri protokolu (satir tabanli ASCII, bkz. docs/stm32_protokol.md).
 * USART2 uzerinden calisir (Nucleo ST-Link VCP - Pi5'e ekstra kablo gerekmez). */
#ifndef PROTOCOL_H
#define PROTOCOL_H

#include "app_config.h"
#include <stdbool.h>

typedef struct {
    int32_t linear_mm_s;   /* Pi5'ten gelen son hiz komutu */
    int32_t angular_mrad_s;
    uint32_t last_cmd_tick; /* HAL_GetTick() - watchdog bunu kontrol eder */
} ProtocolState;

/* USART2 kesmeli (interrupt) alimini baslatir - CubeMX-uretimi huart2'yi kullanir. */
void protocol_init(UART_HandleTypeDef *huart);

/* Ana donguden her turda cagrilir: gelen byte'lari satir tampolar, tam bir
 * satir gelince parse eder (V/PING/STOP), ProtocolState'i gunceller. */
void protocol_poll(void);

/* Watchdog: son komuttan bu yana WATCHDOG_TIMEOUT_MS gectiyse true doner -
 * cagiran taraf (main dongu) motorlari DURDURMALI. */
bool protocol_watchdog_expired(void);

/* Su anki hedef hizlari okur (watchdog suresi dolmus mu BAKMAZ - onu ayrica kontrol edin). */
void protocol_get_target(int32_t *linear_mm_s, int32_t *angular_mrad_s);

/* STM32 -> Pi5 durum satirini gonderir:
 * "S fl fr rl rr imu_wz estop bumper left_mm right_mm batt_mv\n"
 * (left_mm/right_mm/batt_mv 2026-09-18'de eklendi - bkz. stm32_protokol.md). */
void protocol_send_status(int32_t fl_mm, int32_t fr_mm, int32_t rl_mm, int32_t rr_mm,
                           int32_t imu_wz_mrad_s, bool estop, bool bumper,
                           int32_t left_mm, int32_t right_mm, int32_t batt_mv);

/* READY satirinin bilgileri (app_init'te bir kez). reset_cause sabit bir
 * dizge olmali (isaretcisi saklanir). */
void protocol_set_info(const char *reset_cause, bool imu_ok);

/* Acilista bir kez ve "INFO" komutuna: "READY fw=<surum> reset=<neden> imu=<0|1>\n" */
void protocol_send_ready(void);

/* HAL_UART_RxCpltCallback icinden cagrilmali (main.c'ye tek satir eklenir -
 * bkz. main_entegrasyon.md). */
void protocol_uart_rx_isr(UART_HandleTypeDef *huart);

#endif /* PROTOCOL_H */
