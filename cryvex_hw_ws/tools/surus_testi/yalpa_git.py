"""Bosluk kontrolu + Nav2 ile 2 m ileri ve geri."""
import math, sys, time, json, numpy as np, rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from rclpy.time import Time
from sensor_msgs.msg import LaserScan
from geometry_msgs.msg import PoseStamped
from nav2_simple_commander.robot_navigator import BasicNavigator, TaskResult
from tf2_ros import Buffer, TransformListener
MESAFE = 2.0
def yaw(q): return math.atan2(2*(q.w*q.z+q.x*q.y), 1-2*(q.y*q.y+q.z*q.z))
rclpy.init(); n = Node('yalpa_kontrol'); tf = Buffer(); TransformListener(tf, n); last = {}
n.create_subscription(LaserScan, '/scan', lambda m: last.__setitem__('s', m), qos_profile_sensor_data)
t0 = time.time(); p0 = None
while time.time() - t0 < 10 and (p0 is None or 's' not in last):
    rclpy.spin_once(n, timeout_sec=0.1)
    try:
        t = tf.lookup_transform('map', 'base_footprint', Time()); p0 = (t.transform.translation.x, t.transform.translation.y, yaw(t.transform.rotation))
    except Exception: pass
s = last['s']; t = tf.lookup_transform('base_footprint', s.header.frame_id, Time())
r = np.array(s.ranges); a = s.angle_min + s.angle_increment*np.arange(len(r)); ok = np.isfinite(r) & (r > 0.03)
ly = yaw(t.transform.rotation); x = t.transform.translation.x + r[ok]*np.cos(a[ok]+ly); y = t.transform.translation.y + r[ok]*np.sin(a[ok]+ly)
govde_disi = np.hypot(x, y) > 0.33
serit = govde_disi & (x > 0) & (x < MESAFE + 0.7) & (np.abs(y) < 0.40)
uc = govde_disi & (np.hypot(x - MESAFE, y) < 0.60)
bas = govde_disi & (np.hypot(x, y) < 0.60)
print(f'baslangic ({p0[0]:.2f}, {p0[1]:.2f}, {math.degrees(p0[2]):.0f} der); onde seritte {serit.sum()} nokta, hedefte {uc.sum()}, baslangicta {bas.sum()}')
if serit.sum() > 3 or uc.sum() > 3 or bas.sum() > 3:
    ileri = x[govde_disi & (x > 0) & (np.abs(y) < 0.40)]
    print('YOL BOS DEGIL - iptal. Ondeki en yakin engel:', round(float(ileri.min()), 2) if len(ileri) else '-', 'm'); sys.exit(2)
nav = BasicNavigator(node_name='yalpa_nav')
def poz(px, py, pyaw):
    ps = PoseStamped(); ps.header.frame_id = 'map'; ps.header.stamp = nav.get_clock().now().to_msg()
    ps.pose.position.x, ps.pose.position.y = px, py; ps.pose.orientation.z = math.sin(pyaw/2); ps.pose.orientation.w = math.cos(pyaw/2); return ps
B = (p0[0] + MESAFE*math.cos(p0[2]), p0[1] + MESAFE*math.sin(p0[2]), p0[2])
zaman = {}
for ad, hedef in (('gidis', B), ('donus', p0)):
    zaman[ad + '_bas'] = time.time()
    nav.goToPose(poz(*hedef))
    while not nav.isTaskComplete(): time.sleep(0.1)
    zaman[ad + '_son'] = time.time()
    print(ad, nav.getResult(), round(zaman[ad + '_son'] - zaman[ad + '_bas'], 1), 'sn', flush=True)
json.dump({'p0': p0, 'B': B, 'zaman': zaman}, open('/tmp/yalpa_rota.json', 'w'))
