"""
Foxglove koprusu (foxglove_bridge) - RViz'in yerini alan gorsellestirme.

    ros2 launch cryvex_isaac foxglove.launch.py                  # sim (Isaac/Gazebo)
    ros2 launch cryvex_isaac foxglove.launch.py use_sim_time:=false   # gercek robot

Foxglove uygulamasinda: Open connection -> Foxglove WebSocket -> ws://<makine-ip>:8765
Hazir duzen: src/cryvex_isaac/foxglove/cryvex_layout.json (Layouts -> Import from file).
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    port = LaunchConfiguration('port')
    use_sim_time = LaunchConfiguration('use_sim_time')

    return LaunchDescription([
        DeclareLaunchArgument('port', default_value='8765'),
        DeclareLaunchArgument('use_sim_time', default_value='true'),
        Node(
            package='foxglove_bridge',
            executable='foxglove_bridge',
            name='foxglove_bridge',
            output='screen',
            parameters=[{
                'port': ParameterValue(port, value_type=int),
                'address': '0.0.0.0',
                'use_sim_time': ParameterValue(use_sim_time, value_type=bool),
                # /points (3D LiDAR) buyuk; yavas baglantida eski mesajlari at, kuyrugu sisirme
                'send_buffer_limit': 10000000,
                'max_qos_depth': 10,
            }],
        ),
    ])
