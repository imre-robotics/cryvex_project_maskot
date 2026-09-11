import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import ExecuteProcess
from launch_ros.actions import Node
import xacro

def generate_launch_description():
    desc_pkg_path = get_package_share_directory('cryvex_description')
    gazebo_pkg_path = get_package_share_directory('cryvex_gazebo')
    
    # Kafe dünyasının dosya yolu tanımlandı
    world_file = os.path.join(gazebo_pkg_path, 'worlds', 'cafe.world')
    
    xacro_file = os.path.join(desc_pkg_path, 'urdf', 'cryvex.urdf.xacro')
    robot_description_config = xacro.process_file(xacro_file)
    robot_description = {'robot_description': robot_description_config.toxml()}

    # RViz konfigürasyon dosyasının yolu
    rviz_config_file = os.path.join(gazebo_pkg_path, 'rviz', 'cryvex.rviz')

    node_robot_state_publisher = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        output='screen',
        parameters=[robot_description, {'use_sim_time': True}]
    )

    # Gazebo, world_file argümanı ile başlatılacak şekilde güncellendi
    gazebo = ExecuteProcess(
        cmd=['gazebo', '--verbose', '-s', 'libgazebo_ros_factory.so', world_file],
        output='screen'
    )

    # Robot, garson/barmen "Us" noktasinda dogar.
    # (patrol.py HOME_POSITION / BARISTA_POS ve AMCL baslangic pozu ile ayni:
    #  x=-3.43  y=4.05  yaw=0.40)
    spawn_entity = Node(
        package='gazebo_ros',
        executable='spawn_entity.py',
        arguments=[
            '-topic', 'robot_description', '-entity', 'cryvex',
            '-x', '-3.43', '-y', '4.05', '-Y', '0.40',
        ],
        output='screen'
    )

    # RViz2 Düğümü
    rviz2 = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        output='screen',
        arguments=['-d', rviz_config_file],
        parameters=[{'use_sim_time': True}]
    )

    return LaunchDescription([
        node_robot_state_publisher,
        gazebo,
        spawn_entity,
        rviz2
    ])