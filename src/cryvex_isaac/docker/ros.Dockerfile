# Cryvex - Isaac Sim yaninda calisan ROS 2 Jazzy tarafi
# (Nav2 + slam_toolbox + patrol.py + tablet_server + foxglove_bridge).
#
# Neden Jazzy: Isaac Sim 6.1 konteyneri Ubuntu 24.04 tabanli ve icinde ROS 2
# Jazzy kutuphaneleriyle geliyor (NVIDIA'nin onerdigi dagitim). Gercek robot
# (cryvex_hw_ws) da Jazzy - boylece sim ile gercek robot ayni ROS surumunde.
#
# Kaynak kod imaja GOMULMEZ: compose.yaml cryvex_ws/src'yi /ws/src'ye baglar ve
# konteyner her acilista colcon build yapar (ament_cmake + python betikleri,
# derleme birkac saniye). Boylece patrol.py'nin yazdigi waypoints.json /
# haritalar dogrudan senin src klasorune kaydedilir, konteyner silinse de kalir.
FROM ros:jazzy-ros-base

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    ros-jazzy-navigation2 \
    ros-jazzy-nav2-bringup \
    ros-jazzy-slam-toolbox \
    ros-jazzy-pointcloud-to-laserscan \
    ros-jazzy-robot-state-publisher \
    ros-jazzy-xacro \
    ros-jazzy-foxglove-bridge \
    ros-jazzy-rmw-fastrtps-cpp \
    python3-colcon-common-extensions \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# tablet_server.py'nin sesi: edge-tts (cevrimici) + piper (cevrimdisi yedek).
RUN pip3 install --break-system-packages edge-tts piper-tts

# Isaac Sim'in dahili ROS kutuphaneleri Fast DDS kullanir; ayni RMW = sorunsuz kesif.
ENV RMW_IMPLEMENTATION=rmw_fastrtps_cpp

COPY ros_entrypoint.sh /cryvex_entrypoint.sh
RUN chmod +x /cryvex_entrypoint.sh

# Konteyner senin kullanici kimliginle calisir (compose: user), boylece src'ye
# yazilan harita/masa dosyalari root'a ait olmaz. Derleme ciktilari icin bos,
# herkese yazilabilir klasorler (compose bunlari named volume olarak baglar).
RUN mkdir -p /ws/build /ws/install /ws/log && chmod 777 /ws/build /ws/install /ws/log
ENV HOME=/tmp

WORKDIR /ws
ENTRYPOINT ["/cryvex_entrypoint.sh"]
CMD ["ros2", "launch", "cryvex_isaac", "isaac_bringup.launch.py"]
