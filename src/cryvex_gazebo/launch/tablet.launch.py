import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import TimerAction
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
        # patrol.py ONCE baslar: main()'in ilk isi config/waypoints.json'u
        # yoksa TOHUMLAMAK (bkz. load_or_seed_waypoints_cfg). tablet_server.py
        # baslarken bu dosyanin varligina bakip Nav2'yi otomatik baslatip
        # baslatmayacagina karar veriyor (is_configured()) - bu kucuk gecikme
        # ikisinin AYNI ANDA baslayip tablet_server'in dosyayi henuz yazilmadan
        # once BOS gormesini (yanlislikla 'kurulum eksik' sanmasini) engeller.
        patrol_node,
        TimerAction(period=2.0, actions=[tablet_server]),
    ])
