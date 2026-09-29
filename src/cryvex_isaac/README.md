# cryvex_isaac — Isaac Sim + ROS 2 → Foxglove

Cryvex kafe robotu simülasyonunun yeni yapısı:

```
┌────────────────────────── GPU'lu makine (docker compose) ──────────────────────────┐
│                                                                                    │
│  isaac  (nvcr.io/nvidia/isaac-sim:6.1.0)        ros  (ROS 2 Jazzy)                 │
│  ─ fizik (PhysX), kafe sahnesi                  ─ Nav2 + AMCL / slam_toolbox       │
│  ─ RTX LiDAR  → /points                         ─ pointcloud_to_laserscan → /scan  │
│  ─ 4× sonar   → /ultrasonic/*        DDS        ─ patrol.py (devriye beyni)        │
│  ─ tekerler   ← /cmd_vel          ◄───────►     ─ tablet_server.py  :8080          │
│  ─ /odom, TF, /joint_states, /clock  (UDP)      ─ robot_state_publisher            │
│                                                 ─ foxglove_bridge   :8765          │
└──────────────────────────────────────────────────────────────┬─────────────────────┘
                                                               │ WebSocket
                                                  Foxglove (masaüstü / app.foxglove.dev)
```

Isaac Sim, Gazebo ile **aynı topic ve frame'leri** yayınlar. Bu sayede patrol.py,
tablet_server.py, kayıtlı harita, masa kurulumu (`waypoints.json`) ve
keepout/speed maskeleri hiç değişmeden çalışır.

## Sürümler (Eylül 2026)

| Bileşen | Sürüm | Not |
|---|---|---|
| Isaac Sim | **6.1.0** | `isaacsim.core.experimental` API'si. Eski `isaacsim.core.api` (World, Robot) 6.x'te kaldırıldı. |
| ROS 2 | **Jazzy** | Isaac 6.1'in önerdiği dağıtım. Gerçek robot (`cryvex_hw_ws`) da Jazzy. |
| Nav2 | 1.3.x (Jazzy) | `config/nav2_params_jazzy.yaml` otomatik seçilir. |
| foxglove_bridge | 3.5 | `foxglove.sdk.v1` WebSocket protokolü. |

Bu makinedeki Humble + Gazebo akışı olduğu gibi duruyor. Tek fark:
`bringup.launch.py` artık Foxglove köprüsünü de başlatıyor.

## Donanım

Isaac Sim 6.1'in en düşük gereksinimleri: **RTX 4080 (16 GB VRAM), 32 GB RAM,
50 GB SSD, NVIDIA sürücüsü ≥ 595.58**, Ubuntu 22.04 veya 24.04. Geliştirme
dizüstü bilgisayarı (RTX 3050 Mobile 4 GB, 8 GB RAM) bu gereksinimi
karşılamıyor. Isaac, bulut GPU'da (ör. L40S) veya güçlü bir masaüstünde
çalıştırılmalı.

## GPU makinesinde kurulum (bir kez)

1. NVIDIA sürücüsü (≥ 595.58) + [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
2. Docker + `docker compose` eklentisi
3. Bu depoyu klonla (`cryvex_ws/src` yeterli)

## Çalıştırma

```bash
cd cryvex_ws/src/cryvex_isaac/docker
./up.sh                              # ekransız
ISAAC_MODE=--livestream ./up.sh      # Isaac görüntüsünü WebRTC ile izlemek için
./up.sh down                         # durdur
```

`up.sh` şunları yapar: URDF'yi xacro'dan tazeler, ROS imajını derler, Isaac'i
başlatır. ROS tarafı, Isaac "HAZIR" diyene kadar bekler (sağlık kontrolü).
İlk açılışta shader derlemesi **10 dakikayı aşabilir**; sonraki açılışlar hızlıdır.

Kendi bilgisayarından bağlanmak için:

- **Foxglove:** *Open connection → Foxglove WebSocket →* `ws://<gpu-ip>:8765`
  Sonra *Layouts → Import from file →* `foxglove/cryvex_layout.json`
- **Tablet arayüzü:** `http://<gpu-ip>:8080`
- Bulut makinesinde port açmak yerine SSH tüneli kullanabilirsin:
  `ssh -L 8765:localhost:8765 -L 8080:localhost:8080 <sunucu>`, ardından
  `ws://localhost:8765` ve `http://localhost:8080` adreslerine bağlan.

### Foxglove düzeni

| Panel | İçerik |
|---|---|
| 3D | harita, `/scan`, global plan (yeşil), yerel plan (mavi), yerel costmap, robot modeli (`/robot_description`), 1 m ızgara. Araç çubuğundaki *2D pose estimate* → `/initialpose` (RViz'deki gibi konum düzeltme). |
| Devriye durumu | `/patrol_status` JSON'u |
| Butonlar | Devriye Başlat / Üsse Dön / **DURDUR** → `/patrol_command` |
| Grafik | `/cmd_vel` ve `/odom` hızları |
| Log | `/rosout` |

Robotu Foxglove'dan elle sürmek için Teleop paneli bilerek **eklenmedi**:
`/cmd_vel`'e doğrudan yazan bir panel patrol.py ile çakışır. Elle sürüş,
eskisi gibi tablet arayüzündeki joystick'ten yapılır (patrol üzerinden).

## Bu dizüstünde (GPU yok) Foxglove

```bash
ros2 launch cryvex_gazebo bringup.launch.py        # Gazebo + Foxglove köprüsü
ros2 launch cryvex_isaac foxglove.launch.py        # yalnızca köprü (ör. gerçek robot: use_sim_time:=false)
```

## Dosyalar

| Dosya | Görev |
|---|---|
| `isaac/run_cafe_sim.py` | Isaac Sim uygulaması: URDF→USD (önbellekli), kafe sahnesi, ROS 2 OmniGraph (saat, `/cmd_vel`→tekerler, odometri, TF, eklem durumları), RTX LiDAR, sonarlar, gerçek zaman kilidi |
| `isaac/cafe_world.py` | `cryvex_gazebo/worlds/cafe.world` (SDF) → USD. Koordinatlar Gazebo ile birebir aynı. `cafe.world` değişirse bir sonraki açılışta kendiliğinden gelir. |
| `isaac/assets/cryvex.urdf` | xacro'dan üretilir (`tools/export_urdf.py`). **Elle düzenleme**, xacro'yu değiştir. |
| `launch/isaac_bringup.launch.py` | ROS tarafı: robot_state_publisher + foxglove + patrol/tablet (→ Nav2) |
| `launch/foxglove.launch.py` | Yalnızca Foxglove köprüsü |
| `foxglove/cryvex_layout.json` | Hazır Foxglove düzeni |
| `docker/` | `compose.yaml`, `up.sh`, ROS Jazzy imajı, Fast DDS UDP profili |

### Gazebo → Isaac karşılıkları

| Gazebo eklentisi | Isaac Sim 6.1 |
|---|---|
| `libgazebo_ros_diff_drive` | OmniGraph: `ROS2SubscribeTwist → DifferentialController → IsaacArticulationController`, `IsaacComputeOdometry → ROS2PublishOdometry + ROS2PublishRawTransformTree` |
| `libgazebo_ros_ray_sensor` (3D LiDAR, `/points`) | RTX LiDAR `Example_Rotary` (360°, 10 Hz) + `RtxLidarROS2PublishPointCloud` |
| `libgazebo_ros_ray_sensor` (HC-SR04, `sensor_msgs/Range`) | PhysX ışın sorgusu (aynı FOV/menzil, 15 Hz), rclpy ile yayın |
| teker TF'leri | `ROS2PublishJointState` → robot_state_publisher |
| `/clock` | `ROS2PublishClock` |
| kamera (`tablet_camera`) | **Yok.** Hiçbir düğüm kullanmıyordu, gerçek robotta da kamera yok. |

## Doğrulama durumu

- **ROS 2 Jazzy tarafı uçtan uca test edildi.** Test, Isaac'in topic'lerini
  taklit eden sahte bir simülatörle yapıldı. Nav2 (collision_monitor,
  route_server, docking_server dahil) *active* oldu, patrol "HAZIR" dedi,
  devriye başladı ve robot Masa 1'e doğru ilerledi. AMCL konumu doğru çıktı,
  tablet arayüzü açıldı, Foxglove köprüsü tüm düzen topic'lerini yayınladı.
- **Kafe USD dönüştürücüsü test edildi.** 151 görsel ve 152 çarpışma
  primi üretildi; duvar, kolon ve masa sınırları Gazebo ile aynı çıktı.
- **Isaac Sim tarafı henüz GPU'da çalıştırılmadı.** Kod, 6.1.0 kaynağındaki
  API'lere (düğüm tipleri, öznitelik adları, `URDFImporter`,
  `Lidar.create`) göre yazıldı. İlk çalıştırmada şunları kontrol et:
  1. Konsolda `Cryvex Isaac sim HAZIR` yazısı çıkıyor mu?
  2. `ros2 topic hz /points /odom /clock` → yaklaşık 10 / 60 / 60 Hz geliyor mu?
  3. Foxglove'da robot modeli haritada Üs noktasında mı, `/scan` duvarlarla çakışıyor mu?
  4. Devriye Başlat → robot ileri gidiyor mu? Geri gidiyorsa teker eksen yönü ters demektir; `run_cafe_sim.py` içindeki `WHEEL_JOINTS` sırasını kontrol et.
  5. Sonarlar: robotu bir masaya yaklaştır → `ros2 topic echo /ultrasonic/fl` değeri 0.6 m'nin altına düşüyor mu?

## Sürüm yükseltirken

- `compose.yaml` → `nvcr.io/nvidia/isaac-sim:<sürüm>`
- Isaac API'leri sık değişiyor (5.x → 6.x'te `isaacsim.core.api` kaldırıldı).
  Yeni sürümde önce `isaacsim.ros2.bridge` ve `isaacsim.sensors.experimental.rtx`
  standalone örneklerini karşılaştır.
- Robot içe aktarma ayarlarını değiştirirsen, `run_cafe_sim.py` içindeki
  `IMPORT_SETTINGS_VERSION` değerini artır (USD önbelleği yenilenir).
