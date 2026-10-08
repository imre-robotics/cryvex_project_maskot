"""Yalpalama kaydi: /cmd_vel (vx, wz) + map->base_footprint (20 Hz). SIGINT ya da 120 sn'de kaydeder."""
import math, sys, time, signal, numpy as np, rclpy
from rclpy.node import Node
from rclpy.time import Time
from geometry_msgs.msg import Twist
from tf2_ros import Buffer, TransformListener
tag = sys.argv[1]
def yaw(q): return math.atan2(2*(q.w*q.z+q.x*q.y), 1-2*(q.y*q.y+q.z*q.z))
rclpy.init(); n = Node('yalpa_kayit'); tf = Buffer(); TransformListener(tf, n)
C, P = [], []
n.create_subscription(Twist, '/cmd_vel', lambda m: C.append((time.time(), m.linear.x, m.angular.z)), 50)
dur = {'d': False}; signal.signal(signal.SIGINT, lambda *a: dur.__setitem__('d', True)); signal.signal(signal.SIGTERM, lambda *a: dur.__setitem__('d', True))
t0 = time.time(); son = 0
while not dur['d'] and time.time() - t0 < 120:
    rclpy.spin_once(n, timeout_sec=0.01)
    if time.time() - son > 0.05:
        son = time.time()
        try:
            t = tf.lookup_transform('map', 'base_footprint', Time())
            P.append((son, t.transform.translation.x, t.transform.translation.y, yaw(t.transform.rotation)))
        except Exception: pass
np.savez(f'/tmp/yalpa_{tag}.npz', cmd=np.array(C), poz=np.array(P))
print('kayit', tag, len(C), len(P), flush=True)
