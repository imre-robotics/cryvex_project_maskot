"""
Cryvex gercek donanim - CANLI HARITALAMA modu ("Ortami Haritala").

navigation.launch.py'nin YERINE gecer (ikisi ayni anda calismaz - ikisi de
/map + map->odom TF yayinlar, catisir). hardware_bringup.launch.py'nin
(stm32_bridge + ydlidar + ekf + robot_state_publisher) YANINDA calisir.

~/cryvex_ws/src/cryvex_gazebo/launch/mapping.launch.py'nin gercek-donanim
kopyasi - TEK FARKI: pointcloud_to_laserscan YOK. YDLIDAR T-mini Plus zaten
native 2D lidar, dogrudan /scan yayinliyor (sim'deki Unitree L1 3D lidar gibi
pointcloud'dan cevirmeye gerek yok).

ONEMLI: async_slam_toolbox_node bir LIFECYCLE node - baslar baslamaz hicbir
sey yapmaz (subscribe/publish etmez), disaridan "configure" + "activate"
gecisleri cagrilana kadar rclcpp::spin() icinde bos bos bekler (sim'deki
mapping.launch.py'da da bu eksik, orada da fark edilmemis). Asagida node
baslar baslamaz bu iki gecisi otomatik tetikliyoruz (ros2 lifecycle set CLI'i
ile) - elle "ros2 lifecycle set /slam_toolbox configure/activate" cagirmaya
GEREK YOK.

GECICI: STM32/motor henuz baglanmadigi icin ekf_filter_node hicbir girdi
(wheel/odom, imu/data_raw) alamiyor ve "odom" TF cercevesini HIC yayinlamiyor
- slam_toolbox bu cerceve olmadan calisamaz (map/odom/base_footprint zincirini
kuramaz, /map asla yayinlanmaz). Bu yuzden burada odom->base_footprint icin
SABIT (0,0,0) bir static_transform_publisher ekliyoruz - gercek odometri
DEGIL, sadece boru hattini acmak icin. Sonuc: slam_toolbox konum tahminini
SADECE lidar tarama-eslestirmesinden (scan matching) cikarir, tekerlek geri
bildirimi yok. STM32/motor baglanip ekf_filter_node gercek "odom" TF'ini
yayinlamaya baslayinca BU NODE'U KALDIRIN (asagidaki static_odom_tf).

GECICI (devami): slam_toolbox varsayilan olarak "odom" girdisine gore en az
0.5m/0.5rad hareket algilamadan yeni bir tarama ISLEMEZ (minimum_travel_*).
Bizim odom SABIT oldugu icin bu esik ASLA asilmiyor - ilk taramadan sonra
harita tamamen DONUYOR (elinizi lidarin onune koysanız bile hicbir sey
degismez). Asagida bu esikleri 0'a cekiyoruz ki slam_toolbox her yeni
taramayi (map_update_interval'e - 5sn - gore) islesin. STM32/motor
baglanip gercek odom gelince bu override'lari KALDIRIP varsayilan (0.5/0.5)
degerlere donmek daha dogru (yoksa gercek odometriyle de gereksiz sik
islem yapar).
"""
import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, RegisterEventHandler, TimerAction
from launch.event_handlers import OnProcessExit, OnProcessStart
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    slam_pkg_dir = get_package_share_directory('slam_toolbox')

    use_sim_time = LaunchConfiguration('use_sim_time')
    slam_params_file = LaunchConfiguration('slam_params_file')

    declare_use_sim_time = DeclareLaunchArgument('use_sim_time', default_value='false')
    declare_slam_params = DeclareLaunchArgument(
        'slam_params_file',
        default_value=os.path.join(slam_pkg_dir, 'config', 'mapper_params_online_async.yaml'))

    slam_toolbox_node = Node(
        package='slam_toolbox',
        executable='async_slam_toolbox_node',
        name='slam_toolbox',
        output='screen',
        parameters=[slam_params_file, {
            'use_sim_time': use_sim_time,
            # GECICI - bkz. yukaridaki docstring (sabit/gercek olmayan odom).
            'minimum_travel_distance': 0.0,
            'minimum_travel_heading': 0.0,
        }],
    )

    # GECICI - bkz. yukaridaki modul docstring'i. STM32/motor baglaninca kaldirin.
    static_odom_tf = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='cryvex_temp_odom_tf',
        output='screen',
        arguments=['--x', '0', '--y', '0', '--z', '0',
                   '--yaw', '0', '--pitch', '0', '--roll', '0',
                   '--frame-id', 'odom', '--child-frame-id', 'base_footprint'],
    )

    configure_slam = ExecuteProcess(
        cmd=['ros2', 'lifecycle', 'set', '/slam_toolbox', 'configure'],
        output='screen',
    )
    activate_slam = ExecuteProcess(
        cmd=['ros2', 'lifecycle', 'set', '/slam_toolbox', 'activate'],
        output='screen',
    )
    # slam_toolbox process baslar baslamaz DDS/servis kesfi icin birkac
    # saniye gerekiyor - hemen "configure" cagirmak "service not available"
    # ile basarisiz olur, bu yuzden kisa bir gecikme koyuyoruz.
    trigger_configure = RegisterEventHandler(
        OnProcessStart(target_action=slam_toolbox_node,
                        on_start=[TimerAction(period=3.0, actions=[configure_slam])]))
    trigger_activate = RegisterEventHandler(
        OnProcessExit(target_action=configure_slam, on_exit=[activate_slam]))

    return LaunchDescription([
        declare_use_sim_time,
        declare_slam_params,
        static_odom_tf,
        slam_toolbox_node,
        trigger_configure,
        trigger_activate,
    ])
