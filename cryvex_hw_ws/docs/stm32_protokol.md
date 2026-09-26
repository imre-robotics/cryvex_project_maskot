# Pi 5 ↔ STM32 Seri Protokolü (Rev 1)

Pi 5, `/dev/ttyACM0` (USB CDC) üzerinden STM32'ye bağlanır. Protokol **satır
tabanlı, ASCII, `\n` ile biten** basit bir metin protokolüdür — hem debug
etmesi kolay (bir terminalden elle test edilebilir), hem de Pi 5 tarafında
ekstra kütüphane gerektirmez (`pyserial` yeterli).

Baud rate: **115200**, 8N1.

> **2026-09-18: motor sürücü DM556 (step/dir) oldu.** Bu dosyadaki Pi↔STM32
> protokolü (V/PING/STOP, S satırı) DEĞİŞMEDİ - değişen STM32'nin motor
> sürücüsüyle KENDİ ARASINDAKİ arayüz (eskiden hoverboard-hack UART çerçevesi,
> şimdi STEP/DIR darbe). Detay için `stm32_cubemx_ayarlari.md` bölüm 4 ve
> `Core/Src/motor_driver.c`'ye bakın.

## Neden bu kadar basit tutuldu

STM32'nin işi kritik ve azdır: motor komutunu uygula, watchdog'u takip et,
sensörleri oku, e-stop/tampon'u izle. Karmaşık bir binary protokol / CRC
şeması bu ölçekte gereksiz risk katar. Metin tabanlı protokol yanlış
anlaşılırsa (bozuk satır) basitçe atlanır, sistemi kilitlemez.

## Yön 1: Pi 5 → STM32 (komutlar)

| Komut | Anlamı |
|---|---|
| `V <lx_mm_s> <az_mrad_s>\n` | Hız komutu. `lx_mm_s` = ileri hız (mm/s, işaretli), `az_mrad_s` = dönüş hızı (mrad/s, işaretli). Tam sayı kullanılır (ondalık nokta derdi olmasın). Örnek: `V 250 -300\n` = 0.25 m/s ileri, -0.3 rad/s dönüş. |
| `PING\n` | Keepalive - watchdog'u besler, hız değiştirmez. Nav2/joystick'ten hız gelmiyorsa (robot duruyor ama bağlı kalmalı) Pi 5 bunu ~200ms'de bir gönderir. |
| `STOP\n` | Anında dur (yazılımsal). |
| `INFO\n` | **2026-09-26 eklendi.** Kart `READY ...` satırını tekrar gönderir (sürüm / açılış nedeni / IMU). `stm32_bridge` bağlanınca cevap gelene kadar sorar (başına `\n` koyarak - kartta yarım kalmış satırı temizlemek için). Watchdog'u **beslemez**. |

**Watchdog kuralı**: STM32, `V` veya `PING` komutlarından **200ms** boyunca
hiçbirini almazsa motorları **kendiliğinden** durdurur (Pi 5 donsa/Wi-Fi
kopsa/USB kablosu çıksa bile robot durur - bu dokümanın "STM32 watchdog"
maddesiyle birebir eşleşir). Bu, yazılımın en kritik güvenlik kuralıdır.
(2026-09-26: ilk gerçek kartta bu kuralın hiç çalışmadığı bulundu - SysTick
`HAL_IncTick` çağırmıyordu; düzeltildi ve 190 ms'de durduğu ölçüldü.)

**Donanım bekçisi (IWDG, 2026-09-26)**: kartın KENDİ yazılımı takılırsa
(ana döngü ~0.5 sn dönmezse) kart kendiliğinden yeniden başlar. Şart, çünkü
STEP darbelerini zamanlayıcı donanımı üretir - işlemci takılsa bile motorlar
son hızla dönmeye devam ederdi. Yeniden başlayınca `READY ... reset=iwdg`
gelir, `stm32_bridge` bunu hata olarak loglar. Test edildi: kasıtlı kilitlemede
0.7 sn'de toparlandı.

**Durum ışığı (Nucleo LD2, yeşil)**: sürekli yanık = acil stop/tampon
basılı (ya da kablosu kopuk/bağlı değil) · hızlı yanıp sönme = Pi'den komut
yok · çift yanıp sönme = batarya düşük · saniyede bir kısa = her şey yolunda.

## Yön 2: STM32 → Pi 5 (durum, ~20 Hz)

```
S <front_l> <front_r> <back_l> <back_r> <imu_wz> <estop> <bumper> <left_mm> <right_mm> <batt_mv>\n
```

| Alan | Anlamı |
|---|---|
| `front_l`, `front_r`, `back_l`, `back_r` | 4× HC-SR04 mesafesi, **mm** cinsinden tam sayı (menzil dışı/okunamadı = `9999`) |
| `imu_wz` | MPU6050'nin Z ekseni açısal hızı, **mrad/s** (robotun dönüşü - `robot_localization` EKF'sine gidecek) |
| `estop` | `0` = normal, `1` = acil stop butonuna basılmış (yazılım bunu bilir ama zaten donanımsal olarak motor gücü de kesilmiştir - bu sadece arayüzde göstermek için) |
| `bumper` | `0` = temiz, `1` = herhangi bir tampon switch'e basılmış |
| `left_mm`, `right_mm` | **2026-09-18 eklendi.** Sol/sağ tekerin **AÇIK ÇEVRİM** (open-loop) kümülatif ilerlediği mesafe, işaretli, mm. STM32'nin KENDİ komutladığı step sayısından türetilir - DM556'nın geri besleme hattı yok, bu yüzden bu GERÇEK pozisyon değil TAHMİN'dir (adım kaybı sessizce sapmaya yol açar). `stm32_bridge.py` bunu `/wheel/odom` (`nav_msgs/Odometry`) yayınlamak için kullanır; `robot_localization` (EKF) LiDAR/AMCL ile sürekli düzeltir. |
| `batt_mv` | **2026-09-18 eklendi.** Batarya voltajı, mV (ADC1/PA4, direnç bölücü üzerinden - SAHADA kalibre edilmeli). Sadece bir eşik uyarısı için (`BATT_LOW_MV`, bkz. `app_config.h`) - batarya yüzdesi/SoC takibi veya otomatik şarja dönüş DEĞİL, o kapsam dışı bırakıldı (bkz. `malzeme_listesi_rev5.pdf`). ADC okunamazsa `-1`. |

Örnek: `S 850 920 9999 9999 -120 0 0 1523 1519 27400\n` (ön sensörler 85/92 cm,
arka menzil dışı, hafif sağa dönüyor, e-stop/tampon temiz, teker ~1.52 m
ilerledi, batarya 27.4 V).

## Ek: tek seferlik/nadir mesajlar

| Mesaj | Yön | Anlamı |
|---|---|---|
| `READY fw=<sürüm> reset=<neden> imu=<0\|1>\n` | STM32→Pi5 | Açılışta bir kez ve `INFO`'ya cevap. `reset`: `power` (güç verildi), `pin` (reset düğmesi), `sw` (yazılım/yükleyici), `iwdg` (**takıldı, donanım bekçisi kurtardı**), `wwdg`, `bor` (besleme düştü), `?`. `imu=0` ise `stm32_bridge` `/imu/data_raw` yayınlamaz (takılı olmayan IMU'nun "0" değeri EKF'ye "robot dönmüyor" dedirtmesin). Eski yazılım sadece `READY` gönderir. |
| `ERR <kod>\n` | STM32→Pi5 | Beklenmeyen durum (örn. `ERR OVERCURRENT`) - loglanır, ekranda gösterilebilir. |

## Pi 5 tarafı (ROS 2 node, planı)

Küçük bir `stm32_bridge` node'u (Python, `rclpy`):
- `/cmd_vel` (`geometry_msgs/Twist`) dinler → `V ...` satırına çevirip yazar,
  komut gelmese bile 100ms'de bir en son hızı (veya `PING`) tekrar gönderir
  (watchdog'u beslemeye devam eder - Nav2 sürekli `/cmd_vel` yayınlamayabilir).
- Gelen `S ...` satırlarını parse edip:
  - 4× HC-SR04 → `sensor_msgs/Range` (`/ultrasonic/{fl,fr,rl,rr}`, **AYNI
    topic isimleri Gazebo simülasyonundaki gibi** - `patrol.py`'nin
    `SonarReader`/`ultra_blocked()` mantığı DEĞİŞMEDEN gerçek donanımda da
    çalışsın diye bilerek böyle seçildi).
  - `imu_wz` → `sensor_msgs/Imu` (`/imu/data_raw`, `robot_localization`'a).
  - `estop`/`bumper` → `/patrol_command`'a `emergency_stop`/`bumper_hit` gibi
    yeni bir komut (patrol.py'ye eklenecek, henüz yok - Aşama 3 sonunda).
  - `left_mm`/`right_mm` (2026-09-18) → ardışık iki `S` satırı arasındaki
    farktan diferansiyel sürüş odometrisi (x,y,yaw) hesaplanıp `/wheel/odom`
    (`nav_msgs/Odometry`) olarak yayınlanır - `ekf.yaml`'ın `odom0` girdisi
    (önceden "henüz yayınlanmıyor" diye işaretliydi, artık gerçek).
  - `batt_mv` (2026-09-18) → `BATT_LOW_MV` eşiğinin altına inerse **zaten
    var olan** `'stop'` komutu `/patrol_command`'a gönderilir (estop/bumper
    ile AYNI, test edilmiş yeniden kullanım deseni) + bir log uyarısı.

Bu tasarımın en önemli faydası: **Gazebo'daki sonar/patrol mantığının
neredeyse hiç değişmeden gerçek donanıma taşınması** - topic isimleri ve
mesaj tipleri aynı tutuldu ki `patrol.py`'nin zaten test edilmiş kurtulma/
yaklaşma-durdurma mantığı sıfırdan yazılmasın.
