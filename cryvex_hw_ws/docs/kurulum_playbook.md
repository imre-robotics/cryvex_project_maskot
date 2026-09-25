# Cryvex - Donanım Kurulum Günü Playbook'u

Bu dosya, fiziksel parçalar elimize geçtiğinde ("hersey hazır olunca sadece
yükleme yapmak kalsın" hedefi) sırayla izlenecek adımları listeler. Yazılım
tarafı (Aşama 1-4) `cryvex-jazzy-dev` Docker imajı içinde baştan sona
doğrulandı — burada anlatılanlar o doğrulanmış adımların **Docker'sız,
gerçek Raspberry Pi 5 üzerinde native** karşılığı.

## 0) Ön koşul - donanım kontrol listesi
- Raspberry Pi 5 (8GB) + resmi güç adaptörü/PoE HAT (BOM'a göre)
- microSD (32GB+) VEYA NVMe/USB SSD (Pi 5 her ikisinden de boot edebilir)
- STM32 Nucleo-F446RE (USB kablosuyla Pi 5'e bağlanacak - hem ST-Link
  programlama hem USART2 VCP aynı kablodan gider)
- YDLIDAR T-mini Plus + USB-seri adaptörü
- Geliştirme bilgisayarı (bu makine) - STM32'yi ilk kez flaşlamak için

## 1) Raspberry Pi OS imajı (Ubuntu Server 24.04 64-bit)

ROS 2 Jazzy resmi olarak **Ubuntu 24.04 Noble** ister - Raspberry Pi OS
(Debian tabanlı) değil, doğrudan **Ubuntu Server 24.04.x LTS (64-bit,
arm64)** kullanılacak.

1. Bu makineye `rpi-imager` kur (`sudo snap install rpi-imager` veya
   `sudo apt install rpi-imager`).
2. rpi-imager'da: **Device → Raspberry Pi 5**, **OS → Other general-purpose
   OS → Ubuntu → Ubuntu Server 24.04.x LTS (64-bit)**.
3. **Dişli/ayarlar ikonuna bas (headless kurulum için ÖNEMLİ)**:
   - Hostname: `cryvex-robot`
   - SSH'i etkinleştir, şifre veya kendi SSH anahtarınla giriş
   - WiFi SSID/şifre (kafenin ağı) + ülke kodu
   - Locale/saat dilimi: `Europe/Istanbul`
4. SD karta/SSD'ye yaz, Pi 5'e tak, aç. 1-2 dk sonra `ssh <user>@cryvex-robot.local`
   ile bağlan (aynı ağdaysa mDNS ile bulunur; olmazsa router'dan IP'yi bul).

## 2) ROS 2 Jazzy native kurulumu

Bu adımlar `Dockerfile`'daki `FROM ros:jazzy-ros-base` + `apt-get install`
satırlarının **Docker'sız** birebir karşılığı - imaj zaten bu paket listesiyle
uçtan uca derlendiği için doğrulanmış bir liste:

```bash
# ROS 2 apt deposunu ekle (resmi yöntem)
sudo apt update && sudo apt install -y curl gnupg lsb-release
sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
  -o /usr/share/keyrings/ros-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] \
  http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" \
  | sudo tee /etc/apt/sources.list.d/ros2.list

sudo apt update
sudo apt install -y \
  ros-jazzy-ros-base \
  ros-jazzy-navigation2 \
  ros-jazzy-nav2-bringup \
  ros-jazzy-nav2-collision-monitor \
  ros-jazzy-slam-toolbox \
  ros-jazzy-robot-localization \
  ros-jazzy-twist-mux \
  ros-jazzy-tf2-ros \
  ros-jazzy-tf-transformations \
  ros-jazzy-xacro \
  ros-jazzy-robot-state-publisher \
  python3-colcon-common-extensions \
  python3-pip \
  python3-serial \
  git build-essential cmake

echo "source /opt/ros/jazzy/setup.bash" >> ~/.bashrc
source ~/.bashrc
```

YDLidar-SDK (apt paketi yok, kaynaktan):
```bash
mkdir -p ~/opt && cd ~/opt
git clone --depth 1 https://github.com/YDLIDAR/YDLidar-SDK.git
cd YDLidar-SDK && mkdir build && cd build
cmake .. && make -j"$(nproc)" && sudo make install && sudo ldconfig
```

TTS:
```bash
pip3 install --break-system-packages edge-tts piper-tts
```
(Piper'ın Türkçe ses modeli - `tr_TR-dfki-medium`, ~63 MB - `tablet_server.py`
gerçek donanıma portlanınca `python3 -m piper.download_voices tr_TR-dfki-medium`
ile indirilecek. Şimdilik bu Pi'de bir tüketicisi olmadığı için indirilmedi -
mevcut haliyle sadece Gazebo simülasyonundaki `tablet_server.py` kullanıyor.)

## 3) udev kuralları (USB port isimlerini sabitleme)

```bash
sudo apt-get install -y iw
sudo cp ~/cryvex_hw_ws/udev_rules/99-cryvex-serial.rules /etc/udev/rules.d/
sudo cp ~/cryvex_hw_ws/udev_rules/70-cryvex-wifi-powersave.rules /etc/udev/rules.d/
sudo udevadm control --reload
sudo udevadm trigger
```
`70-cryvex-wifi-powersave.rules` WiFi güç tasarrufunu kapatır: açıkken Pi'nin
WiFi yongası bağlantıyı kendi koparıp (`wpa_supplicant`: `locally_generated=1`,
ardından `ASSOC-REJECT`) dakikalarca geri bağlanamıyordu (2026-09-25, sahada).
Doğrulama: `iw dev wlan0 get power_save` → `off`.

STM32 kuralı (`0483:374b`) hazır ve doğrulanmış. **YDLIDAR kuralı doğrulanmadı**
- cihazı takınca önce kontrol et:
```bash
lsusb                                              # hangi cip? (CP210x/CH340/...)
udevadm info -a -n /dev/ttyUSB0 | grep -E "idVendor|idProduct"
```
Değer dosyadaki `10c4:ea60` (CP2102 varsayımı) ile uyuşmuyorsa
`99-cryvex-serial.rules` içindeki YDLIDAR satırını güncelle, `udevadm
control --reload` + cihazı çıkar-tak.

Doğrulama: `ls -l /dev/cryvex_stm32 /dev/cryvex_lidar` ikisi de gerçek
`ttyACM*`/`ttyUSB*` cihazına sembolik link göstermeli.

## 4) STM32 firmware'ini flaşlama

Firmware zaten yazılmış, headless CubeIDE ile **derlenmiş ve doğrulanmış**
durumda (`~/cryvex_hw_ws/stm32_firmware/`, bkz. `main_entegrasyon.md`).
Flaşlama bu geliştirme makinesinden (STM32CubeIDE kurulu), Nucleo'yu USB ile
buraya takarak yapılır (Pi 5'e değil - ST-Link programlama arayüzü ayrı):

**GUI ile (en basit)**: STM32CubeIDE'de `File → Open Projects from File
System` ile `stm32_firmware/` klasörünü aç, Nucleo'yu USB ile tak,
`Run → Debug` (veya sadece flaşla: `Run → Run`). CubeIDE ST-Link'i otomatik
tanır.

**Headless (script'lenebilir)**:
```bash
stm32cubeide -nosplash -application org.eclipse.cdt.managedbuilder.core.headlessbuild \
  -data /tmp/cryvex_cubeide_ws -import ~/cryvex_hw_ws/stm32_firmware \
  -build cryvex_stm32/Debug
# .elf'i ST-Link ile yaz (STM32CubeProgrammer CLI, CubeIDE ile birlikte kurulur):
STM32_Programmer_CLI -c port=SWD -w ~/cryvex_hw_ws/stm32_firmware/Debug/cryvex_stm32.elf -v -rst
```
Flaşladıktan sonra Nucleo'yu Pi 5'e tak, `/dev/cryvex_stm32` üzerinden
`115200` baud'da `READY` satırı gelip gelmediğini kontrol et:
```bash
sudo apt install -y minicom   # veya screen
minicom -D /dev/cryvex_stm32 -b 115200
```

## 5) Workspace'i Pi 5'e taşıma ve derleme

Dosyalar size nasıl ulaştıysa (`cryvex_hw_ws.tar.gz` gibi bir arşiv, USB
bellek, e-posta, git) onunla Pi'ye taşıyın. Birkaç seçenek:

```bash
# A) Elinizde .tar.gz varsa (Pi'ye herhangi bir yolla - scp, USB, tarayıcıdan
# indirme - kopyaladıktan sonra Pi ÜZERİNDE):
tar -xzf cryvex_hw_ws.tar.gz -C ~/

# B) Bu geliştirme makinesi Pi ile aynı ağdaysa doğrudan:
rsync -avz --exclude 'build' --exclude 'install' --exclude 'log' \
  ~/cryvex_hw_ws/ cryvex-robot.local:~/cryvex_hw_ws/
```

```bash
# Pi 5 üzerinde:
cd ~/cryvex_hw_ws
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install
echo "source ~/cryvex_hw_ws/install/setup.bash" >> ~/.bashrc
source ~/.bashrc
```

## 6) İlk gerçek test sırası (parçalar taktıktan sonra)

Bu sıra, Docker konteynerinde donanımsız yapılan dry-run testinin gerçek
donanımla tamamlanmış hali - kod tarafı zaten "çökmüyor" diye doğrulandı,
burada gerçek sensör/motor davranışı doğrulanacak:

1. **Sadece sensör köprüsü**: `ros2 launch cryvex_bringup
   hardware_bringup.launch.py` - ayrı terminalde `ros2 topic echo
   /ultrasonic/fl`, `/imu/data_raw`, `/scan` ile gerçek veri geldiğini
   doğrula. `ros2 run tf2_ros tf2_echo base_footprint lidar_link` ile TF
   ağacının ayakta olduğunu doğrula (Docker'da zaten doğrulandı, gerçek
   donanımda tekrar bak).
2. **Manuel sürüş** (henüz Nav2 yok): `/cmd_vel`'e elle `ros2 topic pub`
   ile küçük bir hız gönderip motorların GERÇEKTEN döndüğünü, yönün REP-103
   ile uyuştuğunu (ileri = +x, sola dönüş = +z) doğrula. **İlk denemede
   robotu tekerlekleri yerden kesecek şekilde (masaya/sehpaya) kaldırarak
   test et** - yanlış yön/aşırı hız ihtimaline karşı.
3. **Haritalama**: `ros2 launch cryvex_bringup mapping.launch.py` (veya
   `cafe_ui_server`/app üzerinden "Ortamı Haritala"), joystick ile kafeyi
   gezip harita çıkar, `ros2 run nav2_map_server
   map_saver_cli -f ~/cryvex_hw_ws/src/cryvex_bringup/maps/cafe_map`.

   **2026-09-24'te sahada bulunan iki gizli engel (ikisi de `mapping.launch.py`
   içinde artık otomatik çözülüyor, elle bir şey yapmaya gerek yok)**:
   - `async_slam_toolbox_node` bir **lifecycle node** - başlar başlamaz hiçbir
     şey yapmaz (subscribe/publish etmez), dışarıdan `configure`+`activate`
     çağrılana kadar sessizce bekler (`/map` asla yayınlanmaz, `live_map.png`
     hep 503 döner). `mapping.launch.py` artık bunu node başlar başlamaz
     otomatik tetikliyor (`ros2 lifecycle set /slam_toolbox configure/activate`
     - bkz. dosyanın içindeki `trigger_configure`/`trigger_activate`). **Aynı
     eksiklik simülasyon tarafındaki `cryvex_gazebo/launch/mapping.launch.py`'da
     da var, orası henüz düzeltilmedi.**
   - STM32/motor bağlı değilken `ekf_filter_node` hiçbir girdi
     (`/wheel/odom`, `/imu/data_raw`) alamadığı için `odom` TF çerçevesini hiç
     yayınlamıyor - slam_toolbox bu çerçeve olmadan çalışamaz. Bu yüzden
     `mapping.launch.py` geçici olarak sabit (0,0,0) bir
     `odom->base_footprint` static transform yayınlıyor (`static_odom_tf`) -
     gerçek odometri DEĞİL, sadece boru hattını açmak için (slam_toolbox konumu
     saf lidar tarama-eşleştirmesinden çıkarır). **STM32/motor bağlanınca bu
     node'u `mapping.launch.py`'dan kaldırın.**
   - Ayrıca YDLIDAR sürücüsü `/scan`'i eskiden `SensorDataQoS` (BEST_EFFORT)
     ile yayınlıyordu - slam_toolbox'un varsayılan RELIABLE aboneliğiyle asla
     eşleşmiyordu (sessizce sıfır mesaj). `ydlidar_ros2_driver_node.cpp`'de
     `rclcpp::QoS(10)` (RELIABLE) yapıldı - hem eski BestEffort bekleyen
     araçlarla hem RELIABLE bekleyenlerle uyumlu.
4. **Otonom sürüş**: `ros2 launch cryvex_bringup navigation.launch.py
   map:=~/cryvex_hw_ws/src/cryvex_bringup/maps/cafe_map.yaml`, RViz'de
   (`ros2 run rviz2 rviz2`, bu makineden `ROS_DOMAIN_ID` aynıysa uzaktan da
   bağlanılabilir) 2D Pose Estimate ver, Nav2 Goal ile hedef gönder.

## 7) Kalıcı otomatik başlatma (systemd + kiosk ekranı)

**2026-09-20: yazıldı ve hazır** — `system/` klasöründeki unit dosyaları
`systemd-analyze verify` ile sözdizimi doğrulandı (gerçek Pi/ekran olmadığı
için görsel kiosk davranışı henüz test EDİLEMEDİ, bkz. aşağıdaki uyarı).

**Önce sensörlerin/motorun tek başına, systemd OLMADAN sorunsuz çalıştığını
doğrulayın (bölüm 6) — otomatik başlatmayı en son ekleyin**, yoksa bir hata
çıktığında systemd log'ları arkasında aramak zorunda kalırsınız.

**Kullanıcı adı notu**: `.service` dosyalarındaki `User=main` ve
`/home/main/...` yolları bu betiklerin hazırlandığı geliştirme makinesinin
kullanıcı adını varsayıyor. Pi'de (rpi-imager'ın headless ayarlarında)
farklı bir kullanıcı adı seçtiyseniz, kopyalamadan önce dosyalardaki
`main` geçen yerleri gerçek kullanıcı adınızla değiştirin.

### 7.1) `cryvex-bringup.service` (sensör/motor köprüsü + café arayüz sunucusu)

```bash
sudo cp ~/cryvex_hw_ws/system/cryvex-bringup.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now cryvex-bringup
journalctl -u cryvex-bringup -f     # canlı log takibi
```
`hardware_bringup.launch.py`'yi (sensörler+motor+EKF+`cafe_ui_server.py`'nin
sunduğu `http://localhost:8080` - gerçek `index.html`, göz animasyonları,
joystick, haritalama) açılışta başlatır.

**Dikkat**: bu servisi etkinleştirmeden önce elle başlattığınız `ros2 launch`
sürecini mutlaka durdurun (`pkill -9 -f "ros2 launch cryvex_bringup"` YETMEZ,
alttaki node'ları yetim bırakabilir - bkz. 7.3'teki temizlik komutu), yoksa
iki ayrı LiDAR/node seti aynı seri portu paylaşıp checksum hatalarına yol
açar (sahada tam olarak bu yaşandı ve teşhis edildi).

### 7.2) Kiosk ekranı (Chromium tam ekran, gerçek café arayüzü)

**2026-09-24: sahada gerçek Pi5 + Waveshare HDMI ekranla doğrulandı.**
İlk denemede iki sorun çıktı, ikisi de kalıcı çözüldü:

1. `cryvex-kiosk.service` gibi bir systemd unit'in doğrudan `xinit`
   çalıştırması **çalışmaz**: `/etc/X11/Xwrapper.config`'in varsayılan
   `allowed_users=console` ayarı "Only console users are allowed to run
   the X server" hatasıyla reddeder. Bunu `allowed_users=anybody` yaparak
   "çözmek" güvenliği zayıflatır (herhangi bir process X'i kapabilir) -
   YAPMAYIN. Doğrusu: `tty1`'e gerçek bir konsol login'i (autologin) açıp,
   o login shell'in `.profile`'ından `startx` çalıştırmak (aşağıda).
2. Raspberry Pi 5'te `/dev/dri/card0` (v3d, GPU render-only, ekran çıkışı
   YOK) ve `/dev/dri/card1` (gerçek HDMI KMS çıkışı) diye iki ayrı DRM
   node'u var. Xorg'un otomatik algılaması bu ikisi arasında kafası
   karışıp "Cannot run in framebuffer mode, please specify busIDs" hatasıyla
   çöküyor. Çözüm: `system/10-cryvex-display.conf` ile doğru cihazı sabitlemek.

Kurulum adımları:
```bash
# 1) Minimal X11 + Chromium (Ubuntu 24.04'te chromium bir snap sarmalayicidir)
sudo apt-get install -y xinit xserver-xorg x11-xserver-utils openbox unclutter chromium-browser

# 2) Pi5'in dogru DRM cihazini once dogrulayin (baska bir Pi'de card
#    numarasi farkli olabilir - "connected" yazan satiri bulun):
for f in /sys/class/drm/card*-*/status; do echo "$f: $(cat $f)"; done
sudo mkdir -p /etc/X11/xorg.conf.d
sudo cp ~/cryvex_hw_ws/system/10-cryvex-display.conf /etc/X11/xorg.conf.d/
# (gerekirse dosya icindeki /dev/dri/cardN'i kendi "connected" ciktiniza gore duzenleyin)

# 3) tty1'e otomatik login (kullanici adini kendi Pi'nize gore degistirin)
sudo mkdir -p /etc/systemd/system/getty@tty1.service.d
sudo tee /etc/systemd/system/getty@tty1.service.d/autologin.conf > /dev/null << 'EOF'
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin main --noclear %I $TERM
EOF
sudo systemctl daemon-reload

# 4) tty1'e login olununca otomatik kiosk baslasin (~/.profile sonuna ekleyin)
cat >> ~/.profile << 'EOF'

if [ -z "${DISPLAY:-}" ] && [ "$(tty)" = "/dev/tty1" ]; then
    exec startx /home/main/cryvex_hw_ws/system/kiosk_session.sh -- :0 -nocursor
fi
EOF

sudo systemctl restart getty@tty1.service   # hemen test etmek icin
```
`kiosk_session.sh` `xinit`'in tek istemcisi olarak ayrı bir X oturumu açar
(masaüstü ortamı yok, sadece Chromium tam ekran) - café arayüzü ayağa
kalkana kadar (en fazla 30 sn) bekleyip öyle açılır, fare imleci gizlenir.
Bu ayar kalıcıdır: yeniden başlatmada `tty1` otomatik login olur ve kiosk
kendiliğinden açılır. SSH oturumlarını etkilemez (onlar `/dev/pts/*`
üzerinden gelir, `tty1` üzerinden değil).

### 7.3) Servisleri durdurma/devre dışı bırakma (hata ayıklarken işe yarar)

```bash
sudo systemctl stop cryvex-bringup
sudo systemctl disable cryvex-bringup

# Kiosk'u gecici kapatmak icin: Ctrl+Alt+F2 ile baska bir tty'e gecip
# `sudo pkill Xorg` (getty@tty1 otomatik olarak .profile'i tekrar
# calistirip kiosk'u yeniden acar - kalici kapatmak icin .profile'daki
# kiosk blogunu veya autologin.conf'u kaldirin).

# hardware_bringup.launch.py'nin YETIM node birakmadan tam temizligi
# (sahada yasanan "iki LiDAR node'u ayni portu okuyor" sorununun cozumu):
sudo pkill -9 -f stm32_bridge; sudo pkill -9 -f ydlidar_ros2_driver_node
sudo pkill -9 -f cafe_ui_server; sudo pkill -9 -f robot_state_publisher
sudo pkill -9 -f ekf_node; sudo pkill -9 -f "ros2 launch cryvex_bringup"
```

## Özet - hangi dosya ne işe yarıyor

| Dosya | Ne zaman kullanılır |
|---|---|
| `udev_rules/99-cryvex-serial.rules` | Adım 3, bir kere |
| `stm32_firmware/` | Adım 4, bir kere (güncelleme gerekirse tekrar) |
| `src/cryvex_bringup/launch/hardware_bringup.launch.py` | Her açılışta - sensör/motor köprüsü |
| `src/cryvex_bringup/launch/mapping.launch.py` | Yeni harita çıkarırken |
| `src/cryvex_bringup/launch/navigation.launch.py` | Otonom sürüş sırasında |
| `src/cryvex_bringup/config/nav2_params.yaml` | navigation.launch.py'nin okuduğu ayarlar |
| `src/cryvex_bringup/urdf/cryvex_real.urdf.xacro` | robot_state_publisher'ın okuduğu TF iskeleti - **gövde kurulunca `base_height`/`lidar_height`/`footprint_radius` gerçek ölçüyle güncellenmeli** |
| `system/cryvex-bringup.service` | Adım 7.1, bir kere kur (`systemctl enable`) |
| `system/kiosk_session.sh` + `system/10-cryvex-display.conf` | Adım 7.2, bir kere kur (autologin+`.profile` ile, systemd unit DEĞİL) |
