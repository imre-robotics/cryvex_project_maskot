# Cryvex gercek donanim (Raspberry Pi 5 + YDLIDAR T-mini Plus + STM32) icin
# ROS 2 Jazzy gelistirme/derleme ortami. Bu makine Ubuntu 22.04/ROS Humble
# oldugundan Jazzy (Ubuntu 24.04 Noble ister) NATIVE kurulamiyor - bu imaj
# icinde gelistirip test ediyoruz. Gercek Pi 5'te (Ubuntu Server 24.04) bu
# Dockerfile'daki apt paketleri DOGRUDAN (Docker'siz) kurulacak - bkz. Asama 5.
FROM ros:jazzy-ros-base

ENV DEBIAN_FRONTEND=noninteractive

# --- Nav2 yigini + gerekli ROS paketleri (dokumanla birebir eslesir) ---
RUN apt-get update && apt-get install -y --no-install-recommends \
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
    git \
    build-essential \
    cmake \
    && rm -rf /var/lib/apt/lists/*

# --- YDLIDAR-SDK + ydlidar_ros2_driver: apt paketi YOK, kaynaktan derleniyor ---
# (bkz. https://github.com/YDLIDAR/YDLidar-SDK ve
#       https://github.com/YDLIDAR/ydlidar_ros2_driver)
RUN mkdir -p /opt/ydlidar_sdk_src && cd /opt/ydlidar_sdk_src \
    && git clone --depth 1 https://github.com/YDLIDAR/YDLidar-SDK.git \
    && cd YDLidar-SDK && mkdir build && cd build \
    && cmake .. && make -j"$(nproc)" && make install && ldconfig

# --- edge-tts (bulut, kaliteli) + Piper (tamamen offline yedek) ---
RUN pip3 install --break-system-packages edge-tts piper-tts

WORKDIR /workspace
# src/ host'tan bind-mount edilecek (bkz. run_jazzy_dev.sh) - imaj icine
# kopyalanmiyor ki duzenlemeler ANINDA gorunsun, yeniden build gerekmesin.

CMD ["/bin/bash"]
