"""
Cryvex gercek donanim - OTONOM SURUS modu (Nav2).

hardware_bringup.launch.py'nin (stm32_bridge + ydlidar + ekf +
robot_state_publisher) YANINDA calisir; mapping.launch.py ile AYNI ANDA
calismaz (ikisi de /map + map->odom TF yayinlar, catisir).

~/cryvex_ws/src/cryvex_gazebo/launch/navigation.launch.py'nin gercek-donanim
kopyasi - TEK FARKI: pointcloud_to_laserscan YOK (YDLIDAR native 2D /scan
yayinliyor, sim'deki 3D->2D koprusune gerek yok). Kullanim:

    ros2 launch cryvex_bringup navigation.launch.py map:=/path/to/harita.yaml
"""
import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    bringup_pkg_dir = get_package_share_directory('cryvex_bringup')
    nav2_bringup_dir = get_package_share_directory('nav2_bringup')

    use_sim_time = LaunchConfiguration('use_sim_time')
    map_yaml_file = LaunchConfiguration('map')
    params_file = LaunchConfiguration('params_file')

    declare_use_sim_time = DeclareLaunchArgument('use_sim_time', default_value='false')
    declare_map = DeclareLaunchArgument(
        'map', default_value=os.path.join(bringup_pkg_dir, 'maps', 'cafe_map.yaml'),
        description='"Ortami Haritala" ile uretilip map_saver_cli ile kaydedilen harita.')
    declare_params = DeclareLaunchArgument(
        'params_file',
        default_value=os.path.join(bringup_pkg_dir, 'config', 'nav2_params.yaml'),
        description='Gercek robota uyarlanmis (sim testinden turetilmis) Nav2 parametreleri.')

    nav2_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(nav2_bringup_dir, 'launch', 'bringup_launch.py')),
        launch_arguments={
            'map': map_yaml_file,
            'use_sim_time': use_sim_time,
            'params_file': params_file,
        }.items(),
    )

    return LaunchDescription([
        declare_use_sim_time,
        declare_map,
        declare_params,
        nav2_launch,
    ])
