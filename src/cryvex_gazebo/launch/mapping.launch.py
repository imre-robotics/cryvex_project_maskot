"""
Cryvex - CANLI HARITALAMA modu.

navigation.launch.py'nin YERINE gecer (ikisi AYNI ANDA calismaz - ikisi de
/map + map->odom TF yayinlar, catisir). tablet_server.py bunu operator ekraninin
"Ortami Haritala" adiminda subprocess olarak baslatir, "Haritalamayi Bitir"
adiminda oldurup navigation.launch.py'a geri doner (bkz. LaunchManager).

Ayni 3D LiDAR -> 2D /scan koprusunu (pointcloud_to_laserscan) kullanir, sonra
slam_toolbox online_async node'u /scan'i okuyup canli /map uretir. Operator
ekrani bu /map'i /api/live_map.png ile canli izler; joystick ile surus yapilir
(patrol.py STATE_TELEOP, drive_raw uzerinden - Nav2'ye ihtiyac yoktur).
"""
import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    gazebo_pkg_dir = get_package_share_directory('cryvex_gazebo')
    slam_pkg_dir = get_package_share_directory('slam_toolbox')

    use_sim_time = LaunchConfiguration('use_sim_time')
    slam_params_file = LaunchConfiguration('slam_params_file')

    declare_use_sim_time = DeclareLaunchArgument('use_sim_time', default_value='true')
    declare_slam_params = DeclareLaunchArgument(
        'slam_params_file',
        default_value=os.path.join(slam_pkg_dir, 'config', 'mapper_params_online_async.yaml'))

    # navigation.launch.py ile AYNI koprus - lidar_link 3D nokta bulutunu 2D'ye cevirir.
    pc_to_laser = Node(
        package='pointcloud_to_laserscan',
        executable='pointcloud_to_laserscan_node',
        name='pointcloud_to_laserscan',
        output='screen',
        parameters=[{
            'target_frame': 'lidar_link',
            'use_sim_time': use_sim_time,
            'transform_tolerance': 0.05,
            'min_height': 0.05,
            'max_height': 1.60,
            'angle_min': -3.14159,
            'angle_max': 3.14159,
            'angle_increment': 0.0087,
            'scan_time': 0.1,
            'range_min': 0.20,
            'range_max': 12.0,
            'use_inf': True,
        }],
        remappings=[('/cloud_in', '/points'), ('/scan', '/scan')],
    )

    slam_toolbox_node = Node(
        package='slam_toolbox',
        executable='async_slam_toolbox_node',
        name='slam_toolbox',
        output='screen',
        parameters=[slam_params_file, {'use_sim_time': use_sim_time}],
    )

    return LaunchDescription([
        declare_use_sim_time,
        declare_slam_params,
        pc_to_laser,
        slam_toolbox_node,
    ])
