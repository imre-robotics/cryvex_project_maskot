#!/bin/bash
# Cryvex - ROS 2 kalinti temizligi. cryvex-bringup.service bunu baslamadan ONCE
# (ExecStartPre) ve durduktan SONRA (ExecStopPost) calistirir.
#
# Neden (2026-10-01'de yasandi): servis yeniden baslatilirken durdurma 90 sn
# zaman asimina ugradi, systemd surecleri SIGKILL ile oldurmeye calisti ama
# bazilari geride kaldi ("remains running after unit stopped"). Oldurulen bir
# surec Fast DDS'in /dev/shm'deki paylasimli kesif portunu yarim yaratmisti
# (fastrtps_port7000, 0 bayt). Sonraki her baslatmada TUM dugumler o bozuk
# portu acmaya calisip sonsuza kadar bekledi: robot yazilimi hic acilmadi.
# Pi'nin yeniden baslatilmasi /dev/shm'yi bosalttigi icin acilis etkilenmez;
# risk "servisi yeniden baslat" anidir. Bu betik o durumu kendiliginden onarir.
#
# Guvenli: yalnizca bu servisin baslattigi turden surecleri (main kullanicisinin
# cryvex_hw_ws / ROS dugumleri) ve HICBIR surecin acik tutmadigi Fast DDS
# dosyalarini siler. Kiosk ekranina (Chromium) dokunmaz.
set -u

# 1) Onceki calismadan geride kalmis dugumler (systemd'nin kill'i kacirdiklari).
#    Servis durumdayken cagrilmaz: ExecStartPre'de servis henuz baslamamis,
#    ExecStopPost'ta ise durmus olur.
pkill -9 -u main -f 'ros2 launch cryvex_bringup' 2>/dev/null
pkill -9 -u main -f '/home/main/cryvex_hw_ws/install/' 2>/dev/null
pkill -9 -u main -f '^/opt/ros/jazzy/lib/' 2>/dev/null
sleep 0.5

# 2) Hicbir surecin acik tutmadigi Fast DDS paylasimli bellek dosyalari
#    (olu port kilitleri, yarim yaratilmis bozuk portlar dahil).
removed=0
for f in /dev/shm/fastrtps_* /dev/shm/sem.fastrtps_*; do
    [ -e "$f" ] || continue
    if ! fuser -s "$f" 2>/dev/null; then
        rm -f "$f" && removed=$((removed + 1))
    fi
done
echo "cryvex_ros_cleanup: $removed sahipsiz Fast DDS dosyasi silindi"
exit 0
