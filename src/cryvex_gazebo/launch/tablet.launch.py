import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    gazebo_pkg_dir = get_package_share_directory('cryvex_gazebo')

    # Tablet Web Sunucusu
    tablet_server = Node(
        package='cryvex_gazebo',
        executable='tablet_server.py',
        name='tablet_server',
        output='screen',
        parameters=[{'use_sim_time': True}]
    )

    # Devriye Node (komut bekler modda başlar)
    patrol_node = Node(
        package='cryvex_gazebo',
        executable='patrol.py',
        name='patrol_node',
        output='screen',
        parameters=[{'use_sim_time': True}]
    )

    return LaunchDescription([
        tablet_server,
        patrol_node,
    ])
