"""
Cryvex - Isaac Sim ile tam sistem, ROS tarafi (gazebo'lu bringup.launch.py'nin karsiligi).

ONCE Isaac Sim'i baslat (docker compose up isaac), konsolda
"Cryvex Isaac sim HAZIR" yazisini gorunce:

    ros2 launch cryvex_isaac isaac_bringup.launch.py

Baslattiklari:
  - robot_state_publisher  (URDF + Isaac'in /joint_states'inden teker TF'leri)
  - foxglove_bridge        (ws://<ip>:8765 - RViz yerine Foxglove)
  - patrol.py + tablet_server.py (cryvex_gazebo/tablet.launch.py; tablet_server
    Nav2/AMCL'i kendisi baslatir - Gazebo'dakiyle ayni akis)

Gazebo YOK, RViz YOK: fizik/sensorler Isaac'te, gorsellestirme Foxglove'da.
"""
import os

import xacro
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, TimerAction
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    desc_dir = get_package_share_directory('cryvex_description')
    gazebo_dir = get_package_share_directory('cryvex_gazebo')
    isaac_dir = get_package_share_directory('cryvex_isaac')

    robot_description = xacro.process_file(
        os.path.join(desc_dir, 'urdf', 'cryvex.urdf.xacro')).toxml()

    foxglove = LaunchConfiguration('foxglove')
    start_delay = LaunchConfiguration('start_delay')

    robot_state_publisher = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        output='screen',
        parameters=[{'robot_description': robot_description, 'use_sim_time': True}],
    )

    foxglove_bridge = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(isaac_dir, 'launch', 'foxglove.launch.py')),
        launch_arguments={'use_sim_time': 'true'}.items(),
        condition=IfCondition(foxglove),
    )

    # patrol.py + tablet_server.py (tablet_server -> Nav2). /clock ve TF'nin
    # akmaya baslamasi icin kisa bir bekleme; tablet_server kendi icinde de bekler.
    tablet = TimerAction(period=start_delay, actions=[IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(gazebo_dir, 'launch', 'tablet.launch.py')))])

    return LaunchDescription([
        DeclareLaunchArgument('foxglove', default_value='true',
                              description='foxglove_bridge da baslatilsin mi'),
        DeclareLaunchArgument('start_delay', default_value='3.0',
                              description='patrol/tablet_server baslamadan once bekleme (sn)'),
        robot_state_publisher,
        foxglove_bridge,
        tablet,
    ])
