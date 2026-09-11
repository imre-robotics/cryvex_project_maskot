import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    gazebo_pkg_dir = get_package_share_directory('cryvex_gazebo')
    nav2_bringup_dir = get_package_share_directory('nav2_bringup')

    # Varsayilanlar (gercek robotta:  use_sim_time:=false  map:=<yeni harita>)
    use_sim_time = LaunchConfiguration('use_sim_time')
    map_yaml_file = LaunchConfiguration('map')
    params_file = LaunchConfiguration('params_file')

    declare_use_sim_time = DeclareLaunchArgument('use_sim_time', default_value='true')
    declare_map = DeclareLaunchArgument(
        'map', default_value=os.path.join(gazebo_pkg_dir, 'maps', 'cafe_map.yaml'))
    declare_params = DeclareLaunchArgument(
        'params_file',
        default_value=os.path.join(gazebo_pkg_dir, 'config', 'nav2_params.yaml'),
        description='Kafeye ozel Nav2 parametreleri (dinamik engel costmap ayarli).')

    # Unitree L1 3D nokta bulutunu 2D /scan'e cevirir.
    pc_to_laser = Node(
        package='pointcloud_to_laserscan',
        executable='pointcloud_to_laserscan_node',
        name='pointcloud_to_laserscan',
        output='screen',
        parameters=[{
            'target_frame': 'lidar_link',
            'use_sim_time': use_sim_time,
            'transform_tolerance': 0.05,
            'min_height': 0.05,        # zemin yansimalarini ele
            'max_height': 1.60,        # tavan/lambalari ele
            'angle_min': -3.14159,
            'angle_max': 3.14159,
            'angle_increment': 0.0087,  # ~0.5 derece
            'scan_time': 0.1,
            'range_min': 0.20,
            'range_max': 12.0,
            'use_inf': True,
        }],
        remappings=[('/cloud_in', '/points'), ('/scan', '/scan')],
    )

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
        pc_to_laser,
        nav2_launch,
    ])
