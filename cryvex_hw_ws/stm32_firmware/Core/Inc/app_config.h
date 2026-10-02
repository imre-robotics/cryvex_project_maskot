/* Cryvex STM32 firmware - genel sabitler ve pin tanımları.
 * CubeMX'te bölüm 3'teki (stm32_cubemx_ayarlari.md) pin atamalarıyla
 * BİREBİR eşleşir - CubeMX'te pin isimlerini değiştirirseniz burayı da
 * güncelleyin.
 */
#ifndef APP_CONFIG_H
#define APP_CONFIG_H

#include "stm32f4xx_hal.h"

/* Yazilim surumu: acilista (ve "INFO" komutuna) READY satirinda gonderilir -
 * Pi tarafi karttaki yazilimi loglardan gorur. Her yuklemede artirin. */
#define FW_VERSION "1.3.4"

/* ---- Pi5 <-> STM32 haberlesme hatti (2026-10-01) ----
 * 1: USART3 - PC10 (TX) -> Pi GPIO15/RXD (pin 10), PC11 (RX) <- Pi GPIO14/TXD
 *    (pin 8), GND ortak. Pi tarafinda /dev/ttyAMA0 (udev: /dev/cryvex_stm32).
 *    Sebep: bu Nucleo'nun ST-LINK seri koprusu (USART2 -> USB) 2026-10-01'deki
 *    5V kisa devresinde bozuldu - STM32 gonderiyor ama Pi'ye hic ulasmiyor
 *    (STM32 TX pini ve saatler SWD ile dogrulandi, saglam).
 * 0: eski yol - USART2 (PA2/PA3) -> ST-LINK sanal seri port (USB, /dev/ttyACM0).
 *    Yeni/saglam bir Nucleo takilirsa 0 yapin. */
#define PI_LINK_USART3 1

/* ---- Guvenlik zamanlamalari ---- */
#define WATCHDOG_TIMEOUT_MS      200U   /* Pi5'ten bu suredir komut gelmezse DUR */
/* DONANIM bekcisi (IWDG): ana dongu bu surede donmezse kart KENDINI yeniden
 * baslatir. Sart cunku STEP darbelerini zamanlayici donanimi uretir: islemci
 * takilsa bile motorlar son hizla donmeye devam ederdi (2026-09-26'da kart
 * I2C beklemesinde takildi - bu bekci olsaydi 0.5 sn'de kurtulurdu).
 * LSI ~32 kHz / 64 = 500 Hz -> 250 sayim = ~0.5 sn (LSI toleransiyla 0.3-0.9 sn). */
#define IWDG_PRESCALER_DIV64     4U
#define IWDG_RELOAD_COUNT        250U
#define SONAR_TRIGGER_PERIOD_MS  60U    /* 4 sensor sirayla ~15ms'de bir, toplam ~60ms donguyle */
#define SONAR_ECHO_TIMEOUT_US    30000U /* ~5m karsiligi - bu sureden uzun surerse "menzil disi" say */
#define STATUS_REPORT_PERIOD_MS  50U    /* Pi5'e "S ..." satiri gonderme sikligi (~20 Hz) */

/* ---- Hiz limitleri (Pi5'ten gelen komutun sinirlari - guvenlik) ---- */
#define MAX_LINEAR_MM_S   400   /* 0.4 m/s - dokumandaki kafe hizi (max_vel_x) ile ayni */
#define MAX_ANGULAR_MRAD_S 1200 /* 1.2 rad/s */

/* ---- Motor: DM556 step/dir surucu (2026-09-18, motor surucu ekibinin
 * DMA860H/DM556 analizi sonrasi hoverboard-UART tasarimindan degistirildi -
 * bkz. motor_driver.c). asagidaki 3 sabit FIZIKSEL OLCUM gerektirir, govde
 * kurulunca guncelle - yapı degismez, sadece sayilar. ---- */
#define WHEEL_DIAMETER_MM   150U  /* 2026-10-02 olculdu: 15 cm (LiDAR testi 148 mm buldu - uyumlu) */
#define WHEEL_BASE_MM       540U  /* 2026-10-02 olculdu: teker ortalari arasi 54 cm (400 yer tutucuydu -
                                    * donuslerde odometri %40 fazla donus sayiyordu, harita bozuluyordu) */
#define STEPS_PER_REV       3200U /* DM556 DIP anahtari mikroadim ayarina gore
                                    * (varsayilan: 16 mikroadim x 200 tam adim/tur) -
                                    * gercek DIP anahtar konumuna gore guncelle */
#define MOTOR_STEP_TIMER_HZ 1000000U /* TIM3/TIM4 Prescaler=89 -> 90MHz/90 = 1 MHz tik */
/* Motor surucu ekibinin analizi: "step motor ani ivmede adim kaybeder" -
 * bu limit KAYNAGI NE OLURSA OLSUN (Nav2 otonom VEYA telefon manuel) TUM
 * hiz komutlarina motor_driver.c icinde uygulanir - protokolun/Nav2'nin
 * kendi ivme sinirlarindan BAGIMSIZ, son ve evrensel guvenlik katmani. */
#define MAX_ACCEL_MM_S2     300   /* 0.3 m/s^2 */
/* EN polaritesi - 2026-10-01: DM860H + ORTAK ANOT open-drain baglanti
 * (bkz. motor_driver.c motor_pins_open_drain). DM860H kilavuzu: ENA opto LED'i
 * YANARSA surucu DEVRE DISI, sonukse (ya da hic bagli degilse) ETKIN. Pin
 * LOW = LED yanar = devre disi -> etkinlestirmek icin pin HIGH (birakilir):
 * aktif-YUKSEK. (Eski 1 degeriyle DM860H motorlari hic surmezdi.) */
#define MOTOR_EN_ACTIVE_LOW 0

/* Teker yonu - 2026-10-01 tezgah testi: ayni "ileri" komutunda iki motor da
 * (mil ucundan bakinca) AYNI yone dondu. Robotta motorlar karsilikli monte
 * edildigi icin ileri giderken biri saat yonunde, digeri tersine donmeli ->
 * sag teker ters cevrildi. Motorlar govdeye takilinca robot ileri komutunda
 * geri gidiyorsa IKISINI de degistirin; donuyorsa sadece birini.
 * 2026-10-02: motorlar tabana takilinca bu tersleme YANLIS cikti - "ileri"
 * komutunda robot yerinde donuyor, "don" komutunda duz gidiyordu (LiDAR ile
 * olculdu: 52 derece donus komutunda gercek donus ~2 derece). Sag teker
 * terslemesi kaldirildi. */
#define LEFT_WHEEL_DIR_INVERT  0
#define RIGHT_WHEEL_DIR_INVERT 0

/* ---- Batarya voltaj olcumu (ADC1_IN4 / PA4, direnc bolucu uzerinden) ----
 * Motor surucu ekibinin analizi: "batarya 20V'a inerse DM556 alt sinirina
 * dayanir, 22V altina inince şarja don kurali koy" - bu sadece bir ESIK
 * UYARISIDIR (batarya yuzdesi/SoC takibi veya otomatik sarj-istasyonuna-
 * donus DEGIL, o kapsam disi birakildi - bkz. malzeme_listesi_rev5.pdf). */
#define ADC_VREF_MV         3300U
#define BATT_DIVIDER_RATIO  10U    /* 1:10 direnc bolucu varsayimi (ör. 90k/10k) - SAHADA dogrula */
#define BATT_LOW_MV         23500  /* bu esigin altinda stm32_bridge.py uyarir/dur komutu verir.
                                    * 2026-10-02: 22000'den yukseltildi - DM860H en az 24 V ister;
                                    * LiFePO4 8S'te 23.5 V ~%5-8 kalan sarj (kayip ~%3-5 kapasite). */

/* ---- HC-SR04 TRIG/ECHO pinleri (bkz. stm32_cubemx_ayarlari.md bolum 3) ---- */
#define SONAR_COUNT 4
typedef enum { SONAR_FL = 0, SONAR_FR = 1, SONAR_RL = 2, SONAR_RR = 3 } SonarIndex;

/* Bu makrolar CubeMX'in urettigi GPIO tanimlarina (main.h) karsilik gelir -
 * CubeMX'te pinlere TAM OLARAK bu isimleri (User Label) verirseniz asagidaki
 * kod DEGISIKLIKSIZ derlenir: FL_TRIG, FL_ECHO, FR_TRIG, FR_ECHO, RL_TRIG,
 * RL_ECHO, RR_TRIG, RR_ECHO (CubeMX Pinout view'da pine sag tik -> "Enter
 * User Label"). */

#endif /* APP_CONFIG_H */
