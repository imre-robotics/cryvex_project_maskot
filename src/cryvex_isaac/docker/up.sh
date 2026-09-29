#!/bin/bash
# Cryvex Isaac Sim + ROS 2 Jazzy yiginini baslatir (GPU'lu makinede).
#   ./up.sh                          ekransiz
#   ISAAC_MODE=--livestream ./up.sh  WebRTC yayini ile
#   ./up.sh down                     durdur
set -euo pipefail
cd "$(dirname "$0")"

# ROS konteyneri senin kimliginle calissin (src'ye yazilan dosyalar sana ait olsun)
export HOST_UID="$(id -u)" HOST_GID="$(id -g)"

if [ "${1:-}" = "down" ]; then
    exec docker compose down
fi

if ! docker info 2>/dev/null | grep -qi 'nvidia'; then
    echo "UYARI: Docker'da NVIDIA runtime gorunmuyor. NVIDIA Container Toolkit kurulu mu?" >&2
    echo "       https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html" >&2
fi

# URDF'yi xacro'dan tazele (ROS kurulu degilse ros imajinin icinde calistir)
if command -v xacro >/dev/null 2>&1; then
    python3 ../tools/export_urdf.py
else
    docker compose build ros
    docker compose run --rm --no-deps --entrypoint bash ros -c \
        "source /opt/ros/jazzy/setup.bash && python3 /ws/src/cryvex_isaac/tools/export_urdf.py"
fi

docker compose up --build "$@"
