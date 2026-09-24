# STM32CubeIDE / CubeMX Kurulum Rehberi (NUCLEO-F446RE)

**Bu proje ZATEN OLUŞTURULDU** (`stm32_firmware/cryvex_stm32.ioc` +
tam CubeIDE proje dosyaları) ve gerçekten derlenip test edildi — bkz.
`stm32_firmware/main_entegrasyon.md`. Aşağıdaki bölümler CubeMX'in
kullandığı ayarları belgeliyor (ör. periferik başka bir F4 kartına
taşırken referans olsun diye); **sıfırdan proje oluşturmanıza gerek yok**,
sadece `stm32_firmware/`'i STM32CubeIDE'de açın.

## 1) Kullanılan ayarlar

Aşağıdaki tüm periferikler `cryvex_stm32.ioc` içinde zaten tanımlı.

## 2) Saat ayarı (Clock Configuration)

**HSI tabanlı** (harici osilatör/kart kablolaması gerektirmez), 180 MHz:
PLLM=8, PLLN=180, PLLP=DIV2 → 16 MHz/8×180/2 = 180 MHz. AHB=180 MHz,
APB1=45 MHz (DIV4), APB2=90 MHz (DIV2), Flash Latency=5 WS.

## 3) Peripheral'lar (Pinout & Configuration sekmesi)

Nucleo-64 kartları (F411RE, F446RE dahil) aynı fiziksel pin yerleşimini
paylaşır, bu yüzden aşağıdaki pinler F446RE için de geçerli.

| Peripheral | Mod | Pin | Ne için |
|---|---|---|---|
| **USART2** | Asynchronous, 115200-8N1 | PA2 (TX), PA3 (RX) | Pi 5 haberleşmesi - Nucleo'da **zaten ST-Link'in USB'sine bağlı**, ekstra kablo gerekmez. Pi 5'e tek USB kablosuyla bağlanır, `/dev/ttyACM0` olur. |
| **TIM3** | PWM Generation CH1, Prescaler=89 (1 MHz tik), Period çalışma zamanında değişir | PA6 (LEFT_STEP) | Sol teker DM556 STEP darbesi (bkz. bölüm 4) |
| **TIM4** | PWM Generation CH1, Prescaler=89 (1 MHz tik), Period çalışma zamanında değişir | PB6 (RIGHT_STEP) | Sağ teker DM556 STEP darbesi |
| GPIO\_Output | Push-Pull | PA9 (LEFT_DIR), PA10 (RIGHT_DIR) | DM556 yön (DIR) girişleri |
| GPIO\_Output | Push-Pull | PB7 (MOTOR_EN) | DM556 etkinleştirme (her iki sürücüye ortak) - polarite (aktif-düşük varsayıldı) SAHADA doğrulanmalı, bkz. `app_config.h MOTOR_EN_ACTIVE_LOW` |
| **ADC1** | IN4, 12-bit, tek dönüşüm, yazılımla tetikleme | PA4 (BATT_VSENSE) | Batarya voltajı (direnç bölücü üzerinden, bkz. bölüm 4) |
| **I2C1** | I2C | PB8 (SCL), PB9 (SDA) | MPU6050 IMU |
| **TIM2** | Internal Clock, 1 MHz sayaç — **Prescaler = 89** (TIM2 APB1 üzerinde, APB1 prescaler ≠1 olduğu için timer saati APB1Freq'in 2 katı = 90 MHz'dir, 180 MHz DEĞİL — CubeMX'in "Clock Configuration" sekmesindeki "APB1 Timer clocks" değerine bakıp `Prescaler = (o_deger/1MHz)-1` formülünü kullanın), Period = 0xFFFFFFFF (32-bit free-running) | — | HC-SR04 echo süresi ölçümü için ortak "mikrosaniye saati" |
| GPIO\_EXTI | External Interrupt (Rising+Falling) | PC0=FL_ECHO, PC1=FR_ECHO, PC2=RL_ECHO, PC3=RR_ECHO (lojik dönüştürücüden 3.3V) | 4× HC-SR04 echo darbe genişliği ölçümü |
| GPIO\_Output | Push-Pull | PC4=FL_TRIG, PC5=FR_TRIG, PC6=RL_TRIG, PC7=RR_TRIG | 4× HC-SR04 tetikleme |
| GPIO\_Input | Pull-up | PA0 | Tampon switch'leri (seri/NC hat - herhangi biri açılırsa veya kablo koparsa hat LOW olur). Her turda okunur (kesme gerekmez, hız kritik değil). |
| GPIO\_Input | Pull-up | PA1 | Acil stop butonunun 2. kontağı (yazılımsal bilgi - motor gücü zaten röle ile donanımsal kesiliyor). Her turda okunur. |

**2026-09-18 değişikliği**: eskiden burada USART1 (PA9/PA10) motor sürücüye
UART çerçevesi göndermek için kullanılıyordu. Motor sürücü ekibinin DM556
kararıyla bu artık gerekmiyor (DM556 basit bir STEP/DIR girişi alır) -
USART1 kaldırıldı, PA9/PA10 DIR pinlerine YENİDEN KULLANILDI (aynı fiziksel
pinler, farklı işlev).

## 4) Motor sürücü arayüzü: **DM556 STEP/DIR (2026-09-18 karar değişikliği)**

**Önceki karar (UART, hoverboard-firmware-hack çerçevesi) motor sürücü
ekibinin gerçek malzeme analizinden SONRA değiştirildi.** Ekibin bulgusu:
elde zaten bulunan DMA860H step sürücü 24V'ta çalışma aralığının (26-113 VDC)
altında kalıyor; 48V'a geçmek batarya+3 regülatör+şarj cihazı+röle bobinini
baştan gerektirirdi. Bunun yerine **DM556** (20-50V DC, 5.6A'e kadar, 86
gövde NEMA step motorla uyumlu) yeni alınacak - 24V LiFePO4 paketin tüm
şarj aralığında (dolu 29.2V, boş 20V) sorunsuz çalışır.

**DM556 basit bir STEP/DIR sürücüdür - hoverboard sürücüsünün aksine
tekerlek karışımı/kinematik YAPMAZ.** Bu yüzden:
- Diferansiyel sürüş dönüşümü (linear+angular → sol/sağ teker hızı) artık
  **STM32 tarafında** (`motor_driver.c`).
- Her teker kendi STEP darbe treni alır (TIM3/TIM4, değişken frekans =
  değişken hız, ~%50 duty) + bir DIR pini (yön) + ortak bir EN pini.
- DM556'nın geri besleme hattı YOK - firmware kendi komutladığı step
  sayısından **açık çevrim** (open-loop) teker odometrisi türetir
  (`motor_driver_get_odom()`) - gerçek pozisyon değil tahmin, adım kaybı
  olursa sessizce sapar. `robot_localization` (EKF) LiDAR/AMCL ile bunu
  sürekli düzeltir (motor sürücü ekibinin notu, bkz. `malzeme_listesi_rev5.pdf`).
- **İvme sınırı firmware'de zorunlu**: step motorlar ani hızlanmada adım
  kaybeder. `motor_driver.c` `MAX_ACCEL_MM_S2` (0.3 m/s²) ile hem Nav2 hem
  telefon komutlarını KAYNAK FARK ETMEKSİZİN rampalar - bu Nav2'nin kendi
  ivme limitinden BAĞIMSIZ, son ve evrensel güvenlik katmanıdır.
- **Batarya alt sınırı**: DM556 20V altında güvenilirliğini yitirir. PA4/ADC1
  üzerinden okunan voltaj `BATT_LOW_MV` (22V) altına inerse `stm32_bridge.py`
  zaten var olan `'stop'` komutunu tetikler (SoC/yüzde takibi veya otomatik
  şarja dönüş DEĞİL - o kapsam dışı, sadece bir eşik uyarısı).

**Fiziksel yer tutucular (gövde kurulunca SAHADA ölçüp güncelle - yapı
değişmez, sadece `app_config.h`'daki 3 sayı)**: `WHEEL_DIAMETER_MM` (150,
varsayım), `WHEEL_BASE_MM` (400, varsayım), `STEPS_PER_REV` (3200 = DM556
varsayılan 16 mikroadım × 200 adım/tur DIP ayarı - gerçek DIP anahtar
konumuna göre güncelle).

Motor sürücü ekibi yine de farklı bir sürücü getirirse, sadece
`motor_driver.c` değişir - protokol/watchdog/sensörler etkilenmez (aynı
tasarım ilkesi UART sürümünde de geçerliydi).

## 5) Projeyi açmak

`stm32_firmware/` zaten tam bir CubeIDE projesi (`.project`/`.cproject`
dahil) — STM32CubeIDE'de **File → Open Projects from File System** ile
doğrudan açın. Detaylar ve doğrulama sonuçları için
`stm32_firmware/main_entegrasyon.md`'ye bakın.
