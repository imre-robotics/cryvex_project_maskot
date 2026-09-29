"""
Cryvex — tek komutla tam sistem.

    ros2 launch cryvex_gazebo bringup.launch.py

Sirayi ve zamanlamayi kendi halleder:
  0 sn  : Gazebo + robot + RViz
  24 sn : patrol beyni + tablet arayuzu

NOT (2026-09-11): Nav2/AMCL artik burada SABIT zamanlanmis degil - tablet_server.py
kendi baslarken (LaunchManager) baslatiyor, cunku operator ekranindan "Ortami
Haritala" ile CANLI HARITALAMA moduna (slam_toolbox) gecince Nav2'nin durdurulup
sonra yeni haritayla yeniden baslatilmasi gerekiyor; ikisi ayni yerden yonetilmezse
cakisir/duplicate olur. Gazebo'nun ayaga kalkmasi icin tablet_server zaten
24 sn bekliyor (eskiden Nav2 12 sn'de baslardi, simdi daha da guvenli).

2026-09-29: Foxglove koprusu de baslar (ws://<ip>:8765, duzen:
src/cryvex_isaac/foxglove/cryvex_layout.json). Istemezsen: foxglove:=false

Tek tek calistirmak istersen eski launch'lar da duruyor:
  gazebo.launch.py -> navigation.launch.py -> tablet.launch.py
  (mapping.launch.py = navigation.launch.py'nin canli-haritalama karsiligi)
"""
import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, TimerAction
from launch.conditions import IfCondition
from launch.launch_description_sources import (AnyLaunchDescriptionSource,
                                               PythonLaunchDescriptionSource)
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    pkg = get_package_share_directory('cryvex_gazebo')

    def inc(fname):
        return IncludeLaunchDescription(
            PythonLaunchDescriptionSource(os.path.join(pkg, 'launch', fname)))

    foxglove = IncludeLaunchDescription(
        AnyLaunchDescriptionSource(os.path.join(
            get_package_share_directory('foxglove_bridge'), 'launch', 'foxglove_bridge_launch.xml')),
        launch_arguments={'use_sim_time': 'true'}.items(),
        condition=IfCondition(LaunchConfiguration('foxglove')),
    )

    return LaunchDescription([
        DeclareLaunchArgument('foxglove', default_value='true'),
        inc('gazebo.launch.py'),
        foxglove,
        TimerAction(period=24.0, actions=[inc('tablet.launch.py')]),
    ])
