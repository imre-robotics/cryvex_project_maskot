# Entegrasyon durumu: TAMAMLANDI ✅

Bu dosya artık bir "yapılacaklar" listesi değil — aşağıdaki her şey zaten
yapıldı ve **gerçekten STM32CubeIDE'nin kendi ARM GCC araç zinciriyle
(14.3.1) derlenip test edildi** (headless build, 0 hata 0 uyarı, **33.1 KB
flash / 2.7 KB RAM** kullanıyor — 512 KB/128 KB bütçede bolca yer var).

**2026-09-18 güncellemesi**: motor sürücü UART (hoverboard-hack) yerine
**DM556 STEP/DIR** oldu (motor sürücü ekibinin gerçek malzeme analizi
sonrası - bkz. `docs/stm32_cubemx_ayarlari.md` bölüm 4). Bu, `motor_driver.c`
`.h`'nin TAMAMEN yeniden yazılmasını, yeni bir `battery.c/.h` modülünü
(voltaj eşik uyarısı), `protocol.c`'nin `S` satırına 3 yeni alan
(`left_mm`/`right_mm`/`batt_mv`) eklenmesini ve `.ioc`'a 3 yeni peripheral
(ADC1, TIM3, TIM4) eklenmesini gerektirdi - hepsi headless CubeMX/CubeIDE
ile YENİDEN üretilip derlenerek doğrulandı (aşağıdaki adımlar aynen tekrar
uygulandı, yeni sürücüye özel notlar için `docs/stm32_cubemx_ayarlari.md`
bölüm 4'e bakın).

## Neler yapıldı

1. **CubeMX projesi** (`cryvex_stm32.ioc`) NUCLEO-F446RE için oluşturuldu,
   `stm32_cubemx_ayarlari.md`'deki tüm peripheral'lar (USART2, I2C1, TIM2,
   TIM3, TIM4, ADC1, 4× sonar TRIG/ECHO, BUMPER, ESTOP_SENSE, motor
   DIR/EN, batarya ADC) tanımlı.
2. **Saat ayarı**: HSI tabanlı, 180 MHz (PLLM=8, PLLN=180, PLLP=2) — harici
   osilatör/kart-özel kablolama gerektirmiyor, her F446RE'de sorunsuz çalışır.
3. **TIM2 prescaler düzeltildi**: 89 (TIM2'nin gerçek saat kaynağı APB1
   timer saati = 90 MHz'dir, 180 MHz değil — ilk denemede bu hata vardı,
   düzeltildi, sonar mikrosaniye ölçümü artık doğru). TIM3/TIM4 (motor STEP
   darbeleri) de aynı 90 MHz APB1 hattında, aynı Prescaler=89 ile 1 MHz
   tik veriyor.
4. **`Core/Src/main.c`**'ye entegrasyon kodu eklendi (USER CODE
   bölümlerinde, CubeMX yeniden kod üretse bile KORUNUR):
   - `app_init(&huart2, &htim3, &htim4, &hadc1, &hi2c1, &htim2)` —
     `MX_..._Init()` çağrılarından hemen sonra
   - `app_loop()` — `while(1)` içinde
   - `HAL_UART_RxCpltCallback` / `HAL_GPIO_EXTI_Callback` geri çağrıları
5. **EXTI0-3 kesmesi düzeltildi**: CubeMX'in `.ioc` NVIC scriptlemesi bu
   dört kesmeyi güvenilir şekilde etkinleştiremedi (nedeni tam
   belgelenmemiş bir alan formatı sorunu) — bunun yerine `stm32f4xx_it.c`'ye
   elle `EXTI0_IRQHandler`...`EXTI3_IRQHandler` eklendi ve
   `app_main.c::app_init()` içinde `HAL_NVIC_EnableIRQ` ile açıkça
   etkinleştirildi. Bu, sonar'ın gerçekten çalışması için KRİTİKTİ.
6. **`sonar.c`**'ye eksik `#include <stdbool.h>` eklendi (ilk derlemede
   gerçek bir hata olarak yakalandı) — aynı hata sınıfı yeni
   `motor_driver.c`'de de tekrarladı (bu sefer `bool motor_en(bool)`
   parametresi icin), ayni sekilde `#include <stdbool.h>` ile duzeltildi.
7. **ADC1'in `.ioc` anahtar formatı ilk denemede yanlış tahmin edildi**:
   `PA4.Signal=ADC1_IN4` doğrudan yazmak CubeMX tarafından sessizce
   YOK SAYILDI (pin sade GPIO_Output'a düştü, ADC1 hiç üretilmedi) - doğru
   format, TIM'lerdeki gibi bir "paylaşılan sinyal" (`SH.`) dolaylamasıdır:
   `PA4.Signal=ADCx_IN4` + `SH.ADCx_IN4.0=ADC1_IN4,IN4`. Bu makinedeki
   gerçek bir kullanıcı projesinde (`~/MY_PROJECTS_STM/Servo_Eksen_1`,
   aynı MCU) doğru örnek bulunup doğrulandı.

## Sırada ne var (sizin yapmanız gereken)

1. `stm32_firmware/` klasörünü STM32CubeIDE'de **File → Open Projects from
   File System** ile açın (zaten tam bir proje, yeniden CubeMX'e gerek yok).
2. Kartı (NUCLEO-F446RE) USB ile bağlayın, **Debug** (▶'nin yanındaki böcek
   ikonu) ile flaşlayıp çalıştırın.
3. Motor sürücü fiziksel olarak bağlı değilken önce sadece USART2 üzerinden
   (Pi5 tarafı - `docs/stm32_protokol.md`) `PING`/`V 0 0` gönderip `READY`
   ve `S ...` satırlarının geldiğini bir seri terminal (ör. `screen
   /dev/ttyACM0 115200`) ile doğrulayın — motor/sensörler takılı olmasa
   bile bu iletişim katmanı çalışmalı.
4. Sonra sırayla: IMU, sonarlar, en son motor sürücü — her birini tek tek
   bağlayıp `S ...` satırındaki ilgili alanın makul değer verdiğini
   kontrol edin.

## Bilinmeyen/doğrulanamayan noktalar (gerçek donanım gerektirir)

Hiçbiri compiler/derleme testiyle önceden doğrulanamaz:

- **DIR pini işaret kuralı** (`motor_driver.c::wheel_apply`): "pozitif hız =
  GPIO_PIN_SET" varsayımı - tekerin gerçekte hangi yöne döndüğü SAHADA
  gözlenip yanlışsa tek satır değiştirilir.
- **MOTOR_EN polaritesi** (`app_config.h::MOTOR_EN_ACTIVE_LOW`) - aktif-düşük
  varsayıldı, DM556'nın gerçek EN+/EN- kablolamasına göre doğrulanmalı.
- **`WHEEL_DIAMETER_MM`/`WHEEL_BASE_MM`/`STEPS_PER_REV`** (`app_config.h`) -
  üçü de yer tutucu; gövde kurulunca ve DM556'nın DIP anahtarı ayarlanınca
  gerçek değerlerle güncellenmeli (yapı değişmez, sadece 3 sayı).
- **`BATT_DIVIDER_RATIO`** (`battery.c`) - 1:10 varsayıldı, gerçek direnç
  değerleriyle (ör. multimetre ile bilinen bir voltajda ADC okuması alıp
  geriye doğru hesaplayarak) kalibre edilmeli.
