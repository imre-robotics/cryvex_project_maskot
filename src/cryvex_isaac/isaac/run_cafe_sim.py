"""
Cryvex kafe simulasyonu - NVIDIA Isaac Sim 6.1 (fizik + sensorler) -> ROS 2.

Gazebo sim'in (cryvex_gazebo/gazebo.launch.py) Isaac karsiligi. ROS tarafina
Gazebo ile AYNI topic/frame'leri verir, boylece patrol.py, tablet_server.py,
Nav2, harita ve masa kurulumu HIC DEGISMEDEN calisir:

  yayinlar  /clock                       sim saati (use_sim_time:=true)
            /odom, TF odom->base_footprint teker odometrisi (spawn = odom orijini)
            /joint_states                teker acilari -> robot_state_publisher
            /points  (PointCloud2)       3D LiDAR, frame lidar_link -> navigation.launch.py
                                         icindeki pointcloud_to_laserscan -> /scan
            /ultrasonic/{fl,fr,rl,rr}    4x HC-SR04 (sensor_msgs/Range)
  dinler    /cmd_vel                     diferansiyel surus (teker yaricapi 0.0825, iz 0.56)

Calistirma (Isaac Sim 6.1 konteyneri icinde - bkz. docker/compose.yaml):
    /isaac-sim/python.sh run_cafe_sim.py --headless              # ekransiz
    /isaac-sim/python.sh run_cafe_sim.py --livestream            # WebRTC ile izle
    /isaac-sim/python.sh run_cafe_sim.py                         # masaustu penceresi

API'ler Isaac Sim 6.1.0 kaynagina (github.com/isaac-sim/IsaacSim, v6.1.0) gore
yazildi: isaacsim.core.experimental.*, isaacsim.core.simulation_manager,
isaacsim.sensors.experimental.rtx, isaacsim.asset.importer.urdf (URDFImporter).
6.x'te eski isaacsim.core.api (World, Robot...) KALDIRILDI - kullanmayin.
"""
import argparse
import hashlib
import math
import os
import sys
import time
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

parser = argparse.ArgumentParser(description='Cryvex kafe simulasyonu (Isaac Sim 6.1)')
parser.add_argument('--headless', action='store_true', help='Pencere acmadan calis')
parser.add_argument('--livestream', action='store_true',
                    help='Ekransiz calis + WebRTC yayini ac (Isaac Sim WebRTC Streaming Client ile baglan)')
parser.add_argument('--urdf', default=os.path.join(HERE, 'assets', 'cryvex.urdf'))
parser.add_argument('--world', default=os.environ.get(
    'CRYVEX_WORLD',
    os.path.join(HERE, '..', '..', 'cryvex_gazebo', 'worlds', 'cafe.world')))
parser.add_argument('--usd-cache', default=os.environ.get(
    'CRYVEX_USD_CACHE', os.path.join(HERE, 'assets', '_usd_cache')),
    help='URDF->USD cevriminin onbellegi (URDF degisince otomatik yenilenir)')
# gazebo.launch.py spawn + patrol.py HOME_POSITION/BARISTA_POS + AMCL baslangic pozu
parser.add_argument('--spawn', nargs=3, type=float, default=[-3.43, 4.05, 0.40],
                    metavar=('X', 'Y', 'YAW'))
parser.add_argument('--physics-hz', type=float, default=60.0)
parser.add_argument('--no-realtime', action='store_true',
                    help='Gercek zamana kilitleme (varsayilan: Gazebo gibi gercek zaman katsayisi 1)')
args, _unknown = parser.parse_known_args()

from isaacsim import SimulationApp  # noqa: E402

if args.livestream:
    # isaacsim.simulation_app/livestream.py ornegindeki ayarlar
    simulation_app = SimulationApp({
        'width': 1280, 'height': 720, 'window_width': 1920, 'window_height': 1080,
        'headless': True, 'hide_ui': False,
    })
else:
    simulation_app = SimulationApp({'headless': args.headless})

import carb  # noqa: E402
import isaacsim.core.experimental.utils.app as app_utils  # noqa: E402
import isaacsim.core.experimental.utils.stage as stage_utils  # noqa: E402
import numpy as np  # noqa: E402
import omni.graph.core as og  # noqa: E402
import usdrt.Sdf  # noqa: E402
from isaacsim.core.simulation_manager import SimulationManager  # noqa: E402
from pxr import Gf, Usd, UsdGeom, UsdPhysics, UsdShade  # noqa: E402

if args.livestream:
    simulation_app.set_setting('/app/window/drawMouse', True)
    app_utils.enable_extension('omni.kit.livestream.app')

# ROS 2 koprusu: konteynerde (Ubuntu 24.04) dahili Jazzy kutuphaneleri otomatik yuklenir.
app_utils.enable_extension('isaacsim.ros2.bridge')
simulation_app.update()

from cafe_world import build_cafe  # noqa: E402


def log(msg):
    carb.log_warn(f'[cryvex] {msg}')   # warn: varsayilan log seviyesinde de gorunsun
    print(f'[cryvex] {msg}', flush=True)


# ---------------------------------------------------------------------------
# URDF'den okunan robot geometrisi (Gazebo diff_drive eklentisiyle ayni degerler)
# ---------------------------------------------------------------------------
WHEEL_RADIUS = 0.0825          # cryvex.urdf.xacro: wheel_diameter 0.165
WHEEL_SEPARATION = 0.56        # cryvex.urdf.xacro: wheel_separation
WHEEL_JOINTS = ['left_wheel_joint', 'right_wheel_joint']
MAX_WHEEL_TORQUE = 20.0        # Gazebo: max_wheel_torque
SONARS = ['fl', 'fr', 'rl', 'rr']
SONAR_MIN, SONAR_MAX = 0.02, 0.60     # xacro sonar makrosu <range>
SONAR_HALF_FOV_H, SONAR_HALF_FOV_V = 0.35, 0.06
SONAR_RATE_HZ = 15.0
ROBOT_PATH = '/World/cryvex'
GRAPH_PATH = '/World/ROS2Graph'

# URDF/import ayarlari degisirse onbellegi gecersiz kilmak icin surum etiketi
IMPORT_SETTINGS_VERSION = 'v1-velocity-drive'


def urdf_link_offsets(urdf_path, base='base_link'):
    """URDF'deki sabit joint zincirinden her linkin `base`'e gore pozu (Gf.Matrix4d).
    Isaac'in iceri aktardigi prim hiyerarsisine bagimli kalmamak icin sensor
    konumlarini dogrudan URDF'den hesapliyoruz."""
    root = ET.parse(urdf_path).getroot()
    parent_of = {}
    for j in root.findall('joint'):
        o = j.find('origin')
        xyz = [float(v) for v in (o.get('xyz', '0 0 0') if o is not None else '0 0 0').split()]
        rpy = [float(v) for v in (o.get('rpy', '0 0 0') if o is not None else '0 0 0').split()]
        rot = (Gf.Rotation(Gf.Vec3d(1, 0, 0), math.degrees(rpy[0]))
               * Gf.Rotation(Gf.Vec3d(0, 1, 0), math.degrees(rpy[1]))
               * Gf.Rotation(Gf.Vec3d(0, 0, 1), math.degrees(rpy[2])))
        m = Gf.Matrix4d(1.0)
        m.SetRotateOnly(rot)
        m.SetTranslateOnly(Gf.Vec3d(*xyz))
        parent_of[j.find('child').get('link')] = (j.find('parent').get('link'), m)

    def to_base(link):
        m = Gf.Matrix4d(1.0)
        while link != base:
            if link not in parent_of:
                raise KeyError(f'{link} -> {base} zinciri URDF\'de yok')
            parent, jm = parent_of[link]
            m = m * jm          # satir-vektor: cocuk * ebeveyn
            link = parent
        return m

    return {name: to_base(name) for name in list(parent_of) + [base]
            if name != 'base_footprint'}


# ---------------------------------------------------------------------------
# 1) URDF -> USD (onbellekli). DIKKAT: URDFImporter kendi stage'ini acar, bu
#    yuzden sahneyi kurmadan ONCE yapilmali.
# ---------------------------------------------------------------------------
def import_robot_usd(urdf_path, cache_root):
    with open(urdf_path, 'rb') as f:
        digest = hashlib.sha1(f.read() + IMPORT_SETTINGS_VERSION.encode()).hexdigest()[:12]
    out_dir = os.path.join(cache_root, digest)
    marker = os.path.join(out_dir, 'IMPORTED_USD_PATH')
    if os.path.isfile(marker):
        usd = open(marker).read().strip()
        if os.path.isfile(usd):
            log(f'Robot USD onbellekten: {usd}')
            return usd

    log(f'URDF -> USD ceviriliyor ({urdf_path}) ...')
    for ext in ('omni.scene.optimizer.core', 'isaacsim.robot.schema', 'isaacsim.asset.importer.urdf'):
        app_utils.enable_extension(ext)
    simulation_app.update()
    from isaacsim.asset.importer.urdf.impl import URDFImporter, URDFImporterConfig

    os.makedirs(out_dir, exist_ok=True)
    wheel_pattern = r'(left|right)_wheel_joint'
    cfg = URDFImporterConfig(
        urdf_path=urdf_path,
        usd_path=out_dir,
        fix_base=False,                  # tekerli robot: zemine sabitlenmez
        merge_fixed_joints=False,        # lidar_link / sonar_* primleri kalsin
        allow_self_collision=False,
        joint_drive_type={wheel_pattern: 'force'},
        joint_target_type={wheel_pattern: 'velocity'},
        override_joint_stiffness={wheel_pattern: 0.0},
        override_joint_damping={wheel_pattern: 1000.0},
    )
    usd = URDFImporter(cfg).import_urdf()
    if not usd or not os.path.isfile(usd):
        raise RuntimeError(f'URDF ice aktarma basarisiz: {usd!r}')
    with open(marker, 'w') as f:
        f.write(usd)
    log(f'Robot USD yazildi: {usd}')
    return usd


# ---------------------------------------------------------------------------
# 2) Sahne: kafe + robot
# ---------------------------------------------------------------------------
def find_named(stage, root_path, name):
    for prim in Usd.PrimRange(stage.GetPrimAtPath(root_path)):
        if prim.GetName() == name:
            return prim
    return None


def find_articulation_root(stage, root_path):
    for prim in Usd.PrimRange(stage.GetPrimAtPath(root_path)):
        if prim.HasAPI(UsdPhysics.ArticulationRootAPI):
            return prim
    return None


def physics_material(stage, path, static_f, dynamic_f):
    mat = UsdShade.Material.Define(stage, path)
    api = UsdPhysics.MaterialAPI.Apply(mat.GetPrim())
    api.CreateStaticFrictionAttr(static_f)
    api.CreateDynamicFrictionAttr(dynamic_f)
    api.CreateRestitutionAttr(0.0)
    return mat


def bind_physics_material(prim, mat):
    # Link primine baglanir, alttaki (instanced olabilen) collision primleri miras alir.
    UsdShade.MaterialBindingAPI.Apply(prim).Bind(
        mat, UsdShade.Tokens.strongerThanDescendants, 'physics')


def build_scene(robot_usd):
    stage = stage_utils.create_new_stage()
    stage_utils.set_stage_up_axis('Z')
    stage_utils.set_stage_units(meters_per_unit=1.0)
    stage_utils.define_prim('/World', 'Xform')

    stats = build_cafe(stage, os.path.abspath(args.world), '/World/Cafe')
    log(f'Kafe kuruldu ({os.path.abspath(args.world)}): {stats}')

    robot = stage_utils.add_reference_to_stage(robot_usd, ROBOT_PATH)
    x, y, yaw = args.spawn
    xf = UsdGeom.Xformable(robot)
    xf.ClearXformOpOrder()
    # base_footprint zeminden 5 cm yukarida doger, teker/sarhos tekerler (alt uc
    # base_footprint'in 3.25 cm altinda) kafe zeminine (ust yuz z=0.01) oturur.
    xf.AddTranslateOp(UsdGeom.XformOp.PrecisionDouble).Set(Gf.Vec3d(x, y, 0.05))
    xf.AddOrientOp(UsdGeom.XformOp.PrecisionDouble).Set(
        Gf.Quatd(math.cos(yaw / 2.0), 0.0, 0.0, math.sin(yaw / 2.0)))

    art_root = find_articulation_root(stage, ROBOT_PATH)
    if art_root is None:
        raise RuntimeError('Robotta ArticulationRootAPI bulunamadi - URDF ice aktarimini kontrol et')
    base_link = find_named(stage, ROBOT_PATH, 'base_link')
    if base_link is None:
        raise RuntimeError('base_link primi bulunamadi')

    # Tekerlek motorlari: Gazebo'daki max_wheel_torque ile ayni tork siniri
    for jname in WHEEL_JOINTS:
        joint = find_named(stage, ROBOT_PATH, jname)
        if joint is None:
            raise RuntimeError(f'{jname} bulunamadi')
        drive = UsdPhysics.DriveAPI.Apply(joint, 'angular')
        drive.CreateMaxForceAttr(MAX_WHEEL_TORQUE)

    # Surtunme: Gazebo'da sarhos tekerler mu=0, tekerler varsayilan (~1).
    caster_mat = physics_material(stage, '/World/PhysicsMaterials/caster', 0.0, 0.0)
    wheel_mat = physics_material(stage, '/World/PhysicsMaterials/wheel', 1.0, 1.0)
    for name, mat in (('front_caster', caster_mat), ('rear_caster', caster_mat),
                      ('left_wheel', wheel_mat), ('right_wheel', wheel_mat)):
        prim = find_named(stage, ROBOT_PATH, name)
        if prim is not None:
            bind_physics_material(prim, mat)
        else:
            log(f'UYARI: {name} primi yok, surtunme malzemesi baglanamadi')

    log(f'Robot: {robot_usd} -> {ROBOT_PATH} (articulation root: {art_root.GetPath()})')
    return stage, art_root.GetPath().pathString, base_link.GetPath().pathString


# ---------------------------------------------------------------------------
# 3) ROS 2 OmniGraph: saat, cmd_vel -> tekerler, odom + TF, joint_states
# ---------------------------------------------------------------------------
def build_ros_graph(art_root_path):
    keys = og.Controller.Keys
    og.Controller.edit(
        {'graph_path': GRAPH_PATH, 'evaluator_name': 'execution'},
        {
            keys.CREATE_NODES: [
                ('OnPlaybackTick', 'omni.graph.action.OnPlaybackTick'),
                ('Context', 'isaacsim.ros2.bridge.ROS2Context'),
                ('ReadSimTime', 'isaacsim.core.nodes.IsaacReadSimulationTime'),
                ('PublishClock', 'isaacsim.ros2.bridge.ROS2PublishClock'),
                ('SubscribeTwist', 'isaacsim.ros2.bridge.ROS2SubscribeTwist'),
                ('BreakLinVel', 'omni.graph.nodes.BreakVector3'),
                ('BreakAngVel', 'omni.graph.nodes.BreakVector3'),
                ('DiffController', 'isaacsim.robot.wheeled_robots.DifferentialController'),
                ('ArtController', 'isaacsim.core.nodes.IsaacArticulationController'),
                ('ComputeOdom', 'isaacsim.core.nodes.IsaacComputeOdometry'),
                ('PublishOdom', 'isaacsim.ros2.bridge.ROS2PublishOdometry'),
                ('PublishOdomTF', 'isaacsim.ros2.bridge.ROS2PublishRawTransformTree'),
                ('PublishJointState', 'isaacsim.ros2.bridge.ROS2PublishJointState'),
            ],
            keys.CONNECT: [
                ('Context.outputs:context', 'PublishClock.inputs:context'),
                ('Context.outputs:context', 'SubscribeTwist.inputs:context'),
                ('Context.outputs:context', 'PublishOdom.inputs:context'),
                ('Context.outputs:context', 'PublishOdomTF.inputs:context'),
                ('Context.outputs:context', 'PublishJointState.inputs:context'),
                # saat
                ('OnPlaybackTick.outputs:tick', 'PublishClock.inputs:execIn'),
                ('ReadSimTime.outputs:simulationTime', 'PublishClock.inputs:timeStamp'),
                # /cmd_vel -> diferansiyel kontrolcu -> teker hizlari
                ('OnPlaybackTick.outputs:tick', 'SubscribeTwist.inputs:execIn'),
                ('OnPlaybackTick.outputs:tick', 'ArtController.inputs:execIn'),
                ('SubscribeTwist.outputs:execOut', 'DiffController.inputs:execIn'),
                ('SubscribeTwist.outputs:linearVelocity', 'BreakLinVel.inputs:tuple'),
                ('SubscribeTwist.outputs:angularVelocity', 'BreakAngVel.inputs:tuple'),
                ('BreakLinVel.outputs:x', 'DiffController.inputs:linearVelocity'),
                ('BreakAngVel.outputs:z', 'DiffController.inputs:angularVelocity'),
                ('DiffController.outputs:velocityCommand', 'ArtController.inputs:velocityCommand'),
                # odometri + odom->base_footprint TF
                ('OnPlaybackTick.outputs:tick', 'ComputeOdom.inputs:execIn'),
                ('ComputeOdom.outputs:execOut', 'PublishOdom.inputs:execIn'),
                ('ComputeOdom.outputs:execOut', 'PublishOdomTF.inputs:execIn'),
                ('ReadSimTime.outputs:simulationTime', 'PublishOdom.inputs:timeStamp'),
                ('ReadSimTime.outputs:simulationTime', 'PublishOdomTF.inputs:timeStamp'),
                ('ComputeOdom.outputs:position', 'PublishOdom.inputs:position'),
                ('ComputeOdom.outputs:orientation', 'PublishOdom.inputs:orientation'),
                ('ComputeOdom.outputs:linearVelocity', 'PublishOdom.inputs:linearVelocity'),
                ('ComputeOdom.outputs:angularVelocity', 'PublishOdom.inputs:angularVelocity'),
                ('ComputeOdom.outputs:position', 'PublishOdomTF.inputs:translation'),
                ('ComputeOdom.outputs:orientation', 'PublishOdomTF.inputs:rotation'),
                # teker acilari (robot_state_publisher teker TF'lerini buradan uretir)
                ('OnPlaybackTick.outputs:tick', 'PublishJointState.inputs:execIn'),
                ('ReadSimTime.outputs:simulationTime', 'PublishJointState.inputs:timeStamp'),
            ],
            keys.SET_VALUES: [
                ('SubscribeTwist.inputs:topicName', 'cmd_vel'),
                ('DiffController.inputs:wheelRadius', WHEEL_RADIUS),
                ('DiffController.inputs:wheelDistance', WHEEL_SEPARATION),
                ('ArtController.inputs:jointNames', WHEEL_JOINTS),
                ('ArtController.inputs:targetPrim', [usdrt.Sdf.Path(art_root_path)]),
                ('ComputeOdom.inputs:chassisPrim', [usdrt.Sdf.Path(art_root_path)]),
                ('PublishOdom.inputs:odomFrameId', 'odom'),
                ('PublishOdom.inputs:chassisFrameId', 'base_footprint'),
                ('PublishOdom.inputs:topicName', 'odom'),
                ('PublishOdomTF.inputs:parentFrameId', 'odom'),
                ('PublishOdomTF.inputs:childFrameId', 'base_footprint'),
                ('PublishOdomTF.inputs:topicName', 'tf'),
                ('PublishJointState.inputs:targetPrim', [usdrt.Sdf.Path(art_root_path)]),
                ('PublishJointState.inputs:topicName', 'joint_states'),
            ],
        },
    )
    log(f'ROS 2 grafigi kuruldu: {GRAPH_PATH}')


# ---------------------------------------------------------------------------
# 4) Sensorler
# ---------------------------------------------------------------------------
def create_lidar(base_link_path, offsets):
    """3D RTX LiDAR -> /points (frame lidar_link). navigation.launch.py'deki
    pointcloud_to_laserscan bunu Gazebo'daki gibi /scan'e cevirir."""
    from isaacsim.sensors.experimental.rtx import Lidar
    t = offsets['lidar_link'].ExtractTranslation()
    lidar = Lidar.create(
        path=f'{base_link_path}/cryvex_lidar',
        config='Example_Rotary',     # 360 derece donen 3D; tarama 10 Hz
        tick_rate=10.0,              # tarama hiziyla ayni olmali (Isaac kurali)
        translations=[[t[0], t[1], t[2]]],
    )
    log(f'RTX LiDAR: {lidar.paths[0]} (base_link + {tuple(round(v, 3) for v in t)})')
    return lidar


def attach_lidar_ros(lidar):
    from isaacsim.sensors.experimental.rtx import LidarSensor
    sensor = LidarSensor(lidar, annotators=[])
    sensor.attach_writer('RtxLidarROS2PublishPointCloud', topicName='points', frameId='lidar_link')
    return sensor


class Sonars:
    """4x HC-SR04: Isaac'te hazir ultrasonik sensor yok, Gazebo'daki ray sensorunu
    PhysX isin sorgulariyla taklit ediyoruz (ayni FOV / menzil / hiz). Robotun
    kendi carpisma sekillerine carpan isinlar yok sayilir."""

    def __init__(self, base_link_path, offsets):
        import rclpy
        from rclpy.qos import qos_profile_sensor_data
        from sensor_msgs.msg import Range
        from omni.physx import get_physx_scene_query_interface

        self._Range = Range
        self._sq = get_physx_scene_query_interface()
        self._base_link_path = base_link_path
        self._rigid = None
        if not rclpy.ok():
            rclpy.init()
        self.node = rclpy.create_node('cryvex_isaac_sonars')
        self.pubs = {k: self.node.create_publisher(Range, f'/ultrasonic/{k}', qos_profile_sensor_data)
                     for k in SONARS}
        # Her sonar icin (konum, isin yonleri) base_link cercevesinde
        self.mounts = {}
        for k in SONARS:
            m = offsets[f'sonar_{k}_link']
            origin = np.array(m.ExtractTranslation())
            rot = np.array(Gf.Matrix3d(m.ExtractRotationMatrix()))   # satir-vektor
            dirs = []
            for h in np.linspace(-SONAR_HALF_FOV_H, SONAR_HALF_FOV_H, 7):
                for v in (-SONAR_HALF_FOV_V, 0.0, SONAR_HALF_FOV_V):
                    d = np.array([math.cos(v) * math.cos(h), math.cos(v) * math.sin(h), math.sin(v)])
                    dirs.append(d @ rot)
            self.mounts[k] = (origin, np.array(dirs))
        self._last_pub = -1.0

    def _base_pose(self):
        if self._rigid is None:
            from isaacsim.core.experimental.prims import RigidPrim
            self._rigid = RigidPrim(self._base_link_path)
        pos, quat = self._rigid.get_world_poses()
        p = pos.numpy()[0].astype(float)
        w, x, y, z = quat.numpy()[0].astype(float)
        r = np.array([
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ])   # sutun-vektor: world = r @ local + p
        return p, r

    def _cast(self, origin, direction):
        best = [math.inf]

        def report(hit):
            if not hit.collision.startswith(ROBOT_PATH) and hit.distance < best[0]:
                best[0] = hit.distance
            return True      # tum isabetleri gez

        self._sq.raycast_all(carb.Float3(*origin), carb.Float3(*direction), SONAR_MAX, report)
        return best[0]

    def step(self):
        t = SimulationManager.get_simulation_time()
        if t - self._last_pub < 1.0 / SONAR_RATE_HZ:
            return
        self._last_pub = t
        p, r = self._base_pose()
        sec = int(t)
        nsec = int((t - sec) * 1e9)
        for k, (origin_l, dirs_l) in self.mounts.items():
            origin = r @ origin_l + p
            dist = min(self._cast(origin, r @ d) for d in dirs_l)
            msg = self._Range()
            msg.header.stamp.sec = sec
            msg.header.stamp.nanosec = nsec
            msg.header.frame_id = f'sonar_{k}_link'
            msg.radiation_type = self._Range.ULTRASOUND
            msg.field_of_view = 2 * SONAR_HALF_FOV_H
            msg.min_range = SONAR_MIN
            msg.max_range = SONAR_MAX
            # REP 117: menzilde bir sey yoksa +inf (Gazebo ray sensoru da boyle)
            msg.range = max(dist, SONAR_MIN) if dist <= SONAR_MAX else math.inf
            self.pubs[k].publish(msg)


# ---------------------------------------------------------------------------
def main():
    urdf = os.path.abspath(args.urdf)
    robot_usd = import_robot_usd(urdf, os.path.abspath(args.usd_cache))

    _stage, art_root_path, base_link_path = build_scene(robot_usd)
    offsets = urdf_link_offsets(urdf)
    build_ros_graph(art_root_path)
    lidar = create_lidar(base_link_path, offsets)

    SimulationManager.setup_simulation(dt=1.0 / args.physics_hz, device='cpu')
    simulation_app.update()
    lidar_sensor = attach_lidar_ros(lidar)  # noqa: F841 - yazici bu nesneye bagli, canli kalmali
    simulation_app.update()

    app_utils.play()
    for _ in range(5):          # fizik gorunumleri olussun
        simulation_app.update()
    sonars = Sonars(base_link_path, offsets)
    log('Cryvex Isaac sim HAZIR - ROS tarafini baslatabilirsin '
        '(ros2 launch cryvex_isaac isaac_bringup.launch.py)')
    # docker compose saglik kontrolu bu dosyayi bekler (ros servisi ondan sonra kalkar)
    ready_file = os.environ.get('CRYVEX_READY_FILE')
    if ready_file:
        with open(ready_file, 'w') as f:
            f.write('ready\n')

    # Gercek zaman kilidi: patrol.py/tablet_server'in bazi sayaclari (masada
    # bekleme, teleop bekcisi) duvar saatiyle calisir; sim ondan hizli kosmasin.
    wall0, sim0 = time.monotonic(), SimulationManager.get_simulation_time()
    while simulation_app.is_running():
        simulation_app.update()
        if not app_utils.is_playing():
            wall0, sim0 = time.monotonic(), SimulationManager.get_simulation_time()
            continue
        if not args.no_realtime:
            ahead = (SimulationManager.get_simulation_time() - sim0) - (time.monotonic() - wall0)
            if ahead > 0.0:
                time.sleep(min(ahead, 0.1))
        try:
            sonars.step()
        except Exception as exc:  # noqa: BLE001 - sonar hatasi simi durdurmasin
            carb.log_error(f'[cryvex] sonar: {exc!r}')

    if ready_file and os.path.exists(ready_file):
        os.remove(ready_file)
    app_utils.stop()
    sonars.node.destroy_node()
    simulation_app.close()


if __name__ == '__main__':
    main()
