#include "protocol.h"
#include <string.h>
#include <stdio.h>

static UART_HandleTypeDef *s_huart;
static UART_HandleTypeDef s_huart3;   /* PI_LINK_USART3: Pi hatti (bkz. app_config.h) */
static ProtocolState s_state;

#define LINE_MAX 64
static volatile uint8_t s_rx_byte;
static char s_rx_line[LINE_MAX];
static volatile uint16_t s_rx_len;
static char s_pending_line[LINE_MAX];
static volatile bool s_line_ready;

/* READY satirindaki bilgiler (app_init doldurur, "INFO" ile tekrar sorulabilir). */
static const char *s_reset_cause = "?";
static bool s_imu_ok;

static void clamp_targets(void)
{
    if (s_state.linear_mm_s > MAX_LINEAR_MM_S)  s_state.linear_mm_s = MAX_LINEAR_MM_S;
    if (s_state.linear_mm_s < -MAX_LINEAR_MM_S) s_state.linear_mm_s = -MAX_LINEAR_MM_S;
    if (s_state.angular_mrad_s > MAX_ANGULAR_MRAD_S)  s_state.angular_mrad_s = MAX_ANGULAR_MRAD_S;
    if (s_state.angular_mrad_s < -MAX_ANGULAR_MRAD_S) s_state.angular_mrad_s = -MAX_ANGULAR_MRAD_S;
}

void protocol_init(UART_HandleTypeDef *huart)
{
    s_huart = huart;
    memset(&s_state, 0, sizeof(s_state));
    s_rx_len = 0;
    s_line_ready = false;
    HAL_UART_Receive_IT(s_huart, (uint8_t *)&s_rx_byte, 1);
}

/* USART3 (PC10 TX / PC11 RX, AF7) - CubeMX'te tanimli DEGIL, burada (kullanici
 * kodunda) kurulur ki .ioc yeniden uretiminde kaybolmasin. */
UART_HandleTypeDef *protocol_pi_uart3_init(void)
{
    GPIO_InitTypeDef g = {0};
    __HAL_RCC_GPIOC_CLK_ENABLE();
    __HAL_RCC_USART3_CLK_ENABLE();
    g.Pin = GPIO_PIN_10 | GPIO_PIN_11;
    g.Mode = GPIO_MODE_AF_PP;
    g.Pull = GPIO_PULLUP;            /* kablo cikarsa RX bosta HIGH kalsin (sahte bayt yok) */
    g.Speed = GPIO_SPEED_FREQ_VERY_HIGH;
    g.Alternate = GPIO_AF7_USART3;
    HAL_GPIO_Init(GPIOC, &g);

    s_huart3.Instance = USART3;
    s_huart3.Init.BaudRate = 115200;
    s_huart3.Init.WordLength = UART_WORDLENGTH_8B;
    s_huart3.Init.StopBits = UART_STOPBITS_1;
    s_huart3.Init.Parity = UART_PARITY_NONE;
    s_huart3.Init.Mode = UART_MODE_TX_RX;
    s_huart3.Init.HwFlowCtl = UART_HWCONTROL_NONE;
    s_huart3.Init.OverSampling = UART_OVERSAMPLING_16;
    HAL_UART_Init(&s_huart3);

    HAL_NVIC_SetPriority(USART3_IRQn, 0, 0);   /* USART2 ile ayni oncelik */
    HAL_NVIC_EnableIRQ(USART3_IRQn);
    return &s_huart3;
}

void USART3_IRQHandler(void)
{
    HAL_UART_IRQHandler(&s_huart3);
}

/* UART hatasi (overrun/gurultu/cerceve): HAL alimi IPTAL eder ve kendisi yeniden
 * BASLATMAZ. 2026-10-01'e kadar bu callback yoktu - kablolama sirasindaki tek
 * bir elektriksel parazit STM32'yi kalici olarak "sagir" birakabiliyordu
 * (komut gelmez -> bekci motorlari durdurur, robot yeniden baslatilana kadar
 * surulemez). Hatayi temizle ve alimi yeniden kur. */
void HAL_UART_ErrorCallback(UART_HandleTypeDef *huart)
{
    if (s_huart == NULL || huart->Instance != s_huart->Instance) {
        return;
    }
    __HAL_UART_CLEAR_OREFLAG(huart);
    s_rx_len = 0;
    HAL_UART_Receive_IT(s_huart, (uint8_t *)&s_rx_byte, 1);
}

void protocol_uart_rx_isr(UART_HandleTypeDef *huart)
{
    if (huart->Instance != s_huart->Instance) {
        return; /* baska bir USART'in kesmesiyse (motor surucu hatti) yok say */
    }
    char c = (char)s_rx_byte;
    if (c == '\n' || c == '\r') {
        if (s_rx_len > 0 && !s_line_ready) {
            memcpy(s_pending_line, s_rx_line, s_rx_len);
            s_pending_line[s_rx_len] = '\0';
            s_line_ready = true;
        }
        s_rx_len = 0;
    } else if (s_rx_len < (LINE_MAX - 1)) {
        s_rx_line[s_rx_len++] = c;
    } else {
        s_rx_len = 0; /* satir cok uzun/bozuk - at, yeniden basla */
    }
    HAL_UART_Receive_IT(s_huart, (uint8_t *)&s_rx_byte, 1);
}

void protocol_poll(void)
{
    if (!s_line_ready) {
        return;
    }
    /* Kopyala ve HEMEN bayragi indir - yeni bir ISR satiri tampona yazmaya
     * baslayabilir biz asagida is_pending_line'i okurken. */
    char line[LINE_MAX];
    __disable_irq();
    strncpy(line, s_pending_line, LINE_MAX);
    s_line_ready = false;
    __enable_irq();

    if (strncmp(line, "V ", 2) == 0) {
        long lx = 0, az = 0;
        if (sscanf(line + 2, "%ld %ld", &lx, &az) == 2) {
            s_state.linear_mm_s = (int32_t)lx;
            s_state.angular_mrad_s = (int32_t)az;
            clamp_targets();
            s_state.last_cmd_tick = HAL_GetTick();
        }
    } else if (strncmp(line, "PING", 4) == 0) {
        s_state.last_cmd_tick = HAL_GetTick();
    } else if (strncmp(line, "STOP", 4) == 0) {
        s_state.linear_mm_s = 0;
        s_state.angular_mrad_s = 0;
        s_state.last_cmd_tick = HAL_GetTick();
    } else if (strncmp(line, "INFO", 4) == 0) {
        /* Pi baglandiginda sorar: kart acilistaki READY'yi Pi dinlemiyorken
         * gondermis olabilir. Watchdog'u BESLEMEZ (hareket komutu degil). */
        protocol_send_ready();
    }
    /* Bilinmeyen/bozuk satir: sessizce yok say (watchdog zaten koruyor). */
}

bool protocol_watchdog_expired(void)
{
    if (s_state.last_cmd_tick == 0) {
        return true; /* henuz hic komut gelmedi -> guvenli tarafta kal, DUR */
    }
    return (HAL_GetTick() - s_state.last_cmd_tick) > WATCHDOG_TIMEOUT_MS;
}

void protocol_get_target(int32_t *linear_mm_s, int32_t *angular_mrad_s)
{
    *linear_mm_s = s_state.linear_mm_s;
    *angular_mrad_s = s_state.angular_mrad_s;
}

void protocol_send_status(int32_t fl_mm, int32_t fr_mm, int32_t rl_mm, int32_t rr_mm,
                           int32_t imu_wz_mrad_s, bool estop, bool bumper,
                           int32_t left_mm, int32_t right_mm, int32_t batt_mv)
{
    char buf[112];
    int n = snprintf(buf, sizeof(buf), "S %ld %ld %ld %ld %ld %d %d %ld %ld %ld\n",
                      (long)fl_mm, (long)fr_mm, (long)rl_mm, (long)rr_mm,
                      (long)imu_wz_mrad_s, estop ? 1 : 0, bumper ? 1 : 0,
                      (long)left_mm, (long)right_mm, (long)batt_mv);
    if (n > 0) {
        HAL_UART_Transmit(s_huart, (uint8_t *)buf, (uint16_t)n, 20);
    }
}

void protocol_set_info(const char *reset_cause, bool imu_ok)
{
    s_reset_cause = reset_cause;
    s_imu_ok = imu_ok;
}

void protocol_send_ready(void)
{
    /* "READY fw=1.1.0 reset=power imu=0" - reset: power|pin|sw|iwdg|wwdg|bor|?
     * (iwdg = kart takilmis, DONANIM bekcisi yeniden baslatti). */
    char buf[64];
    int n = snprintf(buf, sizeof(buf), "READY fw=%s reset=%s imu=%d\n",
                     FW_VERSION, s_reset_cause, s_imu_ok ? 1 : 0);
    if (n > 0) {
        HAL_UART_Transmit(s_huart, (uint8_t *)buf, (uint16_t)n, 20);
    }
}
