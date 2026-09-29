#!/bin/bash
# /ws/src baglanmis kaynaktan calisma alanini derler, sonra verilen komutu calistirir.
set -e
source /opt/ros/jazzy/setup.bash

cd /ws
# Sadece bu uc paket: cryvex_ws/src'de baska (Humble'a ozel) paket olursa takilmasin.
colcon build --symlink-install \
    --packages-select cryvex_description cryvex_gazebo cryvex_isaac \
    --event-handlers console_direct- >/tmp/colcon_build.log 2>&1 \
    || { cat /tmp/colcon_build.log; exit 1; }
source /ws/install/setup.bash

exec "$@"
