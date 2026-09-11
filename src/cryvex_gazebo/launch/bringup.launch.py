"""
Cryvex — tek komutla tam sistem.

    ros2 launch cryvex_gazebo bringup.launch.py

Sirayi ve zamanlamayi kendi halleder:
  0 sn : Gazebo + robot + RViz
 12 sn : Nav2 + amcl + pointcloud_to_laserscan
 24 sn : patrol beyni + tablet arayuzu

Tek tek calistirmak istersen eski launch'lar da duruyor:
  gazebo.launch.py -> navigation.launch.py -> tablet.launch.py
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
        TimerAction(period=12.0, actions=[inc('navigation.launch.py')]),
        TimerAction(period=24.0, actions=[inc('tablet.launch.py')]),
    ])
