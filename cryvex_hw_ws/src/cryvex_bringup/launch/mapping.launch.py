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
mapping.launch.py'da da bu eksik, orada da fark edilmemis). Asagida bu iki
gecis launch olaylariyla tetikleniyor: launch_ros node'un servisi hazir olana
kadar KENDISI bekler (sabit gecikme yok - acilista DDS kesfi yavas olsa da
calisir), configure bitince (inactive) activate gelir.

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
from launch.actions import DeclareLaunchArgument, EmitEvent, RegisterEventHandler
from launch.events import matches_action
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import LifecycleNode, Node
from launch_ros.event_handlers import OnStateTransition
from launch_ros.events.lifecycle import ChangeState
from lifecycle_msgs.msg import Transition


def generate_launch_description():
    slam_pkg_dir = get_package_share_directory('slam_toolbox')

    use_sim_time = LaunchConfiguration('use_sim_time')
    slam_params_file = LaunchConfiguration('slam_params_file')

    declare_use_sim_time = DeclareLaunchArgument('use_sim_time', default_value='false')
    declare_slam_params = DeclareLaunchArgument(
        'slam_params_file',
        default_value=os.path.join(slam_pkg_dir, 'config', 'mapper_params_online_async.yaml'))

    slam_toolbox_node = LifecycleNode(
        package='slam_toolbox',
        executable='async_slam_toolbox_node',
        name='slam_toolbox',
        namespace='',
        output='screen',
        parameters=[slam_params_file, {
            'use_sim_time': use_sim_time,
            # GECICI - bkz. yukaridaki docstring (sabit/gercek olmayan odom).
            'minimum_travel_distance': 0.0,
            'minimum_travel_heading': 0.0,
            # GECICI: odom yokken hareketi SADECE tarama eslestirmesi bulur ve
            # tahminin yalnizca ±25cm/±20° cevresine bakar. Varsayilan 0.5sn'de bir
            # tarama islenince yuruyus hizinda (~50cm) konum kaybediliyor; her
            # tarama (7 Hz, ~14cm) islenince alan icinde kalir. Odom gelince kaldirin.
            'minimum_time_interval': 0.1,
            # Canli harita (telefon/ekran) 5sn yerine 1sn'de bir guncellensin.
            'map_update_interval': 1.0,
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

    configure_slam = EmitEvent(event=ChangeState(
        lifecycle_node_matcher=matches_action(slam_toolbox_node),
        transition_id=Transition.TRANSITION_CONFIGURE))
    activate_when_configured = RegisterEventHandler(OnStateTransition(
        target_lifecycle_node=slam_toolbox_node, goal_state='inactive',
        entities=[EmitEvent(event=ChangeState(
            lifecycle_node_matcher=matches_action(slam_toolbox_node),
            transition_id=Transition.TRANSITION_ACTIVATE))]))

    return LaunchDescription([
        declare_use_sim_time,
        declare_slam_params,
        static_odom_tf,
        slam_toolbox_node,
        configure_slam,
        activate_when_configured,
    ])
