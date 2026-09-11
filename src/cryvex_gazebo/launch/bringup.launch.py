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

Tek tek calistirmak istersen eski launch'lar da duruyor:
  gazebo.launch.py -> navigation.launch.py -> tablet.launch.py
  (mapping.launch.py = navigation.launch.py'nin canli-haritalama karsiligi)
"""
import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, TimerAction
from launch.launch_description_sources import PythonLaunchDescriptionSource


def generate_launch_description():
    pkg = get_package_share_directory('cryvex_gazebo')

    def inc(fname):
        return IncludeLaunchDescription(
            PythonLaunchDescriptionSource(os.path.join(pkg, 'launch', fname)))

    return LaunchDescription([
        inc('gazebo.launch.py'),
        TimerAction(period=24.0, actions=[inc('tablet.launch.py')]),
    ])
