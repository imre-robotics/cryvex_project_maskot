#!/usr/bin/env python3
"""
Cryvex Tablet Server Node
- HTTP server sunarak tablet arayüzünü sağlar
- /patrol_command topic'ine komut yayınlar
- /patrol_status topic'ini dinleyerek durumu izler
"""
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy, HistoryPolicy
from rclpy.time import Time as RclpyTime
from rclpy.duration import Duration
from std_msgs.msg import String
from nav_msgs.msg import OccupancyGrid
from tf2_ros import Buffer, TransformListener
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import json
import math
import os
import shutil
import signal
import socket
import subprocess
import time
import sys
import struct
import zlib
import ast
from ament_index_python.packages import get_package_share_directory

# Operator (kurulum/haritalama) ekraninin sifresi - musteri ekranindaki "Devriyeyi
# Durdur" sifresiyle AYNI (1234), garsonun zaten bildigi tek kod. Sadece server
# tarafinda da kontrol edilir cunku bu uclar Nav2/SLAM surecini durdurup baslatiyor.
OPERATOR_PASSWORD = '1234'

# /map (nav_msgs/OccupancyGrid) hem nav2 map_server'dan hem slam_toolbox'tan ayni
# QoS ile TRANSIENT_LOCAL + RELIABLE yayinlanir - abone de eslesmezse mesaj hic gelmez.
MAP_QOS = QoSProfile(
    depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL,
    reliability=ReliabilityPolicy.RELIABLE, history=HistoryPolicy.KEEP_LAST)


# ==================== Harita gorseli (PGM -> PNG, sadece stdlib) ====================
def _parse_pgm(path):
    """P2 (ASCII) veya P5 (binary) PGM okur -> (genislik, yukseklik, piksel bytes)."""
    with open(path, 'rb') as f:
        data = f.read()
    pos = 0

    def next_token():
        nonlocal pos
        while True:
            while pos < len(data) and data[pos:pos + 1].isspace():
                pos += 1
            if pos < len(data) and data[pos:pos + 1] == b'#':
                while pos < len(data) and data[pos:pos + 1] != b'\n':
                    pos += 1
                continue
            break
        start = pos
        while pos < len(data) and not data[pos:pos + 1].isspace():
            pos += 1
        return data[start:pos]

    magic = next_token()
    width = int(next_token())
    height = int(next_token())
    int(next_token())  # maxval (0-255 varsayiyoruz)
    pos += 1  # header'dan sonraki tek ayirici karakter

    if magic == b'P5':
        pixels = data[pos:pos + width * height]
    elif magic == b'P2':
        vals = bytearray()
        while len(vals) < width * height:
            vals.append(int(next_token()))
        pixels = bytes(vals)
    else:
        raise ValueError(f'Desteklenmeyen PGM turu: {magic}')
    return width, height, pixels


def _gray_bytes_to_png(width, height, pixels):
    """Gri tonlamali ham piksel bytes (satir 0 = ustte) -> PNG. Ne PGM ne
    OccupancyGrid'e ozel - ikisi de bunu kullanir."""
    raw = bytearray()
    for y in range(height):
        raw.append(0)  # satir filtresi: None
        raw.extend(pixels[y * width:(y + 1) * width])
    compressed = zlib.compress(bytes(raw), 6)

    def chunk(tag, payload):
        return (struct.pack('>I', len(payload)) + tag + payload +
                struct.pack('>I', zlib.crc32(tag + payload) & 0xffffffff))

    ihdr = struct.pack('>IIBBBBB', width, height, 8, 0, 0, 0, 0)  # 8-bit grayscale
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) +
            chunk(b'IDAT', compressed) + chunk(b'IEND', b''))


def _pgm_to_png_bytes(path):
    """Gri tonlamali PGM -> PNG (zlib disinda ekstra kutuphane gerektirmez)."""
    width, height, pixels = _parse_pgm(path)
    return _gray_bytes_to_png(width, height, pixels)


def _occgrid_to_png_bytes(msg):
    """nav_msgs/OccupancyGrid (canli SLAM haritasi) -> PNG. map_server'in
    map_saver'iyla AYNI gri kural: bilinmeyen(-1)->205 gri, bos(0)->254 beyaz,
    dolu(100)->0 siyah (arasi orantili). OccupancyGrid satir 0 = ALT (dunya y
    min) - PGM/PNG'de satir 0 = UST oldugundan (setup.html bunu varsayiyor)
    satirlari DIKEY CEVIRIYORUZ ki ayni worldToFrac kurali her ikisinde de gecerli olsun."""
    w, h = msg.info.width, msg.info.height
    data = msg.data
    pixels = bytearray(w * h)
    for i, v in enumerate(data):
        if v < 0:
            pixels[i] = 205
        else:
            pixels[i] = max(0, min(255, round(254 - (v / 100.0) * 254)))
    flipped = bytearray(w * h)
    for row in range(h):
        src = row * w
        dst = (h - 1 - row) * w
        flipped[dst:dst + w] = pixels[src:src + w]
    return _gray_bytes_to_png(w, h, bytes(flipped))


class LaunchManager:
    """Nav2 (localizasyon+surus) ile canli-haritalama (slam_toolbox) SIRAYLA
    calisir, ASLA AYNI ANDA degil - ikisi de /map + map->odom TF yayinlar,
    birlikte cakisir. Bu sinif hangisinin o an ayakta oldugunu TEK YERDEN
    yonetir (subprocess.Popen, kendi sureç grubunda) boylece biri digerine
    gecerken temiz kapatilip acilir."""

    def __init__(self, node):
        self.node = node
        self.proc = None   # subprocess.Popen | None
        self.kind = None   # 'nav' | 'slam' | None
        self._lock = threading.Lock()

    def _log(self, msg):
        self.node.get_logger().info(f'[LaunchManager] {msg}')

    def _stop_locked(self):
        if self.proc is None:
            return
        if self.proc.poll() is None:      # hala calisiyor
            pid = self.proc.pid
            try:
                os.killpg(os.getpgid(pid), signal.SIGINT)   # Ctrl+C gibi - temiz kapanma sansi
                self.proc.wait(timeout=8.0)
            except Exception:  # noqa: BLE001
                try:
                    os.killpg(os.getpgid(pid), signal.SIGKILL)
                    self.proc.wait(timeout=3.0)
                except Exception:  # noqa: BLE001
                    pass
        self.proc = None
        self.kind = None

    def stop(self):
        with self._lock:
            if self.kind:
                self._log(f"'{self.kind}' surumu durduruluyor...")
            self._stop_locked()

    def start_nav(self, map_yaml):
        with self._lock:
            self._stop_locked()
            self._log(f'Nav2/AMCL baslatiliyor (harita: {map_yaml})')
            cmd = ['ros2', 'launch', 'cryvex_gazebo', 'navigation.launch.py',
                   f'map:={map_yaml}', 'use_sim_time:=true']
            self.proc = subprocess.Popen(cmd, start_new_session=True)
            self.kind = 'nav'

    def start_slam(self):
        with self._lock:
            self._stop_locked()
            self._log('Canli haritalama (slam_toolbox) baslatiliyor...')
            cmd = ['ros2', 'launch', 'cryvex_gazebo', 'mapping.launch.py', 'use_sim_time:=true']
            self.proc = subprocess.Popen(cmd, start_new_session=True)
            self.kind = 'slam'


def _kill_stray_processes(logger):
    """Onceki (crash/kill olmus) bir tablet_server'dan kalma yetim Nav2/SLAM
    surecleri varsa temizler - yoksa LaunchManager kendi baslattigi surecin
    YANINA ikinci bir kopya daha baslatir (bu oturumda daha once patrol.py'de
    yasanan 'duplicate node' sorununun ayni surum yonetimi tarafi)."""
    patterns = ['navigation.launch.py', 'mapping.launch.py', 'slam_toolbox',
                'pointcloud_to_laserscan_node', 'bringup_launch.py']
    for pat in patterns:
        try:
            subprocess.run(['pkill', '-9', '-f', pat],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3.0)
        except Exception:  # noqa: BLE001
            pass
    logger.info('[LaunchManager] Onceki oturumdan kalmis olabilecek Nav2/SLAM surecleri temizlendi.')


class TabletHandler(BaseHTTPRequestHandler):
    """Web isteklerini karşılayan HTTP handler."""
    ros_node = None  # Class variable, dışarıdan set edilir

    def do_GET(self):
        # Ignore query parameters
        path = self.path.split('?')[0]
        if path == '/' or path == '/index.html':
            self._serve_html('index.html')          # musteri ekrani (robot yuzu)
        elif path == '/setup' or path == '/setup.html':
            self._serve_html('setup.html')          # nokta tanimlama (kurulum) ekrani
        elif path == '/operator' or path == '/operator.html':
            # 2026-09-11: ayri operator ekrani KALDIRILDI - "Ortami Haritala" artik
            # index.html'in yonetici panelinde (ayni sifreyle) - garsonun telefonu
            # da ROBOTLA AYNI URL'yi (http://<ip>:8080/) acar. Eski link/yer imi
            # kirilmasin diye ana ekrana yonlendiriyoruz.
            self.send_response(302)
            self.send_header('Location', '/')
            self.end_headers()
        elif path == '/api/mode':
            n = self.ros_node
            self._send_json({'mode': n.mode, 'configured': n.is_configured()})
        elif path == '/api/live_map.png':
            self._serve_live_map_png()
        elif path == '/api/status':
            n = self.ros_node
            age = (time.time() - n.last_status_time) if n.status_count else -1.0
            self._send_json({
                'status': n.current_status,
                'count': n.status_count,      # kac /patrol_status mesaji alindi
                'age': round(age, 1),         # son mesajin kac sn once geldigi (-1 = hic)
            })
        elif path == '/api/map.png':
            self._serve_map_png()
        elif path == '/api/map_info':
            self._send_json(self.ros_node.map_info())
        elif path == '/api/waypoints':
            self._send_json(self.ros_node.load_waypoints_cfg())
        else:
            self.send_error(404)

    def _serve_map_png(self):
        try:
            png = self.ros_node.map_png_bytes()
        except Exception as e:  # noqa: BLE001
            self.send_error(500, f'Harita donusturulemedi: {e}')
            return
        self.send_response(200)
        self.send_header('Content-Type', 'image/png')
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        self.send_header('Content-Length', str(len(png)))
        self.end_headers()
        self.wfile.write(png)

    def _serve_live_map_png(self):
        png = self.ros_node.live_map_png_bytes()
        if png is None:
            self.send_error(503, 'Henuz canli harita verisi gelmedi (slam_toolbox baslatiliyor olabilir)')
            return
        self.send_response(200)
        self.send_header('Content-Type', 'image/png')
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        self.send_header('Content-Length', str(len(png)))
        self.end_headers()
        self.wfile.write(png)

    def do_POST(self):
        path = self.path.split('?')[0]
        if path == '/api/start_patrol':
            self._publish_command('start')
            self._send_json({'result': 'ok'})
        elif path == '/api/stop_patrol':
            self._publish_command('stop')
            self._send_json({'result': 'ok'})
        elif path == '/api/go_home':
            self._publish_command('go_home')
            self._send_json({'result': 'ok'})
        elif path == '/api/wander':
            self._publish_command('wander')
            self._send_json({'result': 'ok'})
        elif path == '/api/interacting':
            self._publish_command('interacting')
            self._send_json({'result': 'ok'})
        elif path == '/api/done_interacting':
            self._publish_command('done_interacting')
            self._send_json({'result': 'ok'})
        elif path == '/api/place_order':
            # Müşterinin sipariş verilerini almak için gövdeyi okuyabiliriz ama şimdilik sadece komut iletiyoruz
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length > 0:
                body = self.rfile.read(content_length).decode('utf-8')
                self._publish_command(f'order:{body}')
            else:
                self._publish_command('order:{}')
            self._send_json({'result': 'ok'})
        elif path == '/api/resume_patrol':
            self._publish_command('resume')
            self._send_json({'result': 'ok'})
        elif path == '/api/greet_door':
            self._publish_command('greet_door')
            self._send_json({'result': 'ok'})
        elif path == '/api/relocalize':
            self._publish_command('relocalize')
            self._send_json({'result': 'ok'})
        elif path == '/api/wake':
            self._publish_command('wake')
            self._send_json({'result': 'ok'})
        elif path == '/api/sleep':
            self._publish_command('sleep')
            self._send_json({'result': 'ok'})
        elif path == '/api/teleop':
            # govde: {"lx": -0.3..0.3, "az": -1.0..1.0}  (operator sanal joystick)
            try:
                d = json.loads(self._read_body() or '{}')
                lx = float(d.get('lx', 0.0))
                az = float(d.get('az', 0.0))
            except (ValueError, TypeError):
                lx = az = 0.0
            self._publish_command(f'teleop:{lx:.3f}:{az:.3f}')
            self._send_json({'result': 'ok'})
        elif path == '/api/teleop_stop':
            self._publish_command('teleop_stop')
            self._send_json({'result': 'ok'})
        elif path == '/api/rescue_start':
            # Robot herhangi bir gorevde (devriye/siparis/vs) takilirsa garson
            # devralir - "Devriyeyi Durdur" ile ayni sifre gerekir (Nav2 gorevini
            # iptal edip manuel surus baslatan, geri donusu olmayan bir eylem).
            try:
                d = json.loads(self._read_body() or '{}')
            except (ValueError, TypeError):
                d = {}
            if str(d.get('password', '')) != OPERATOR_PASSWORD:
                self._send_json({'result': 'error', 'reason': 'wrong password'})
                return
            self._publish_command('rescue_start')
            self._send_json({'result': 'ok'})
        elif path == '/api/rescue_teleop':
            # govde: {"lx":-0.3..0.3, "az":-1.0..1.0} - kurtarma joystick'i.
            # Sifre YOK - rescue_start zaten sifreyle acildi, her hareket icin
            # tekrar sifre istemek joystick'i kullanilamaz hale getirir.
            try:
                d = json.loads(self._read_body() or '{}')
                lx = float(d.get('lx', 0.0))
                az = float(d.get('az', 0.0))
            except (ValueError, TypeError):
                lx = az = 0.0
            self._publish_command(f'rescue_teleop:{lx:.3f}:{az:.3f}')
            self._send_json({'result': 'ok'})
        elif path == '/api/rescue_stop':
            # Kurtarma modundan CIK -> gorev kaldigi yerden devam eder. Sifre
            # gerekmez (bitirmek/gorevi geri vermek riskli bir eylem degil).
            self._publish_command('rescue_stop')
            self._send_json({'result': 'ok'})
        elif path == '/api/start_mapping':
            try:
                d = json.loads(self._read_body() or '{}')
            except (ValueError, TypeError):
                d = {}
            if str(d.get('password', '')) != OPERATOR_PASSWORD:
                self._send_json({'result': 'error', 'reason': 'wrong password'})
                return
            self._publish_command('mapping_start')
            self.ros_node.mode = 'mapping'
            self.ros_node.launch_mgr.start_slam()
            self._send_json({'result': 'ok'})
        elif path == '/api/finish_mapping':
            try:
                d = json.loads(self._read_body() or '{}')
            except (ValueError, TypeError):
                d = {}
            if str(d.get('password', '')) != OPERATOR_PASSWORD:
                self._send_json({'result': 'error', 'reason': 'wrong password'})
                return
            try:
                pose_captured = self.ros_node.finish_mapping()
            except Exception as e:  # noqa: BLE001
                self._send_json({'result': 'error', 'reason': str(e)})
                return
            self._send_json({'result': 'ok', 'pose_captured': pose_captured})
        elif path == '/api/set_pose':
            # govde: {"x":..., "y":..., "yaw":...} - kurulum ekranindan "Robot
            # Burada" ile MANUEL 2D pose estimate (otomatik yakalama basarisiz
            # olduysa ya da garson duzeltmek isterse).
            try:
                d = json.loads(self._read_body() or '{}')
                x, y, yaw = float(d['x']), float(d['y']), float(d.get('yaw', 0.0))
            except (KeyError, ValueError, TypeError):
                self._send_json({'result': 'error', 'reason': 'bad body'})
                return
            self._publish_command(f'set_pose:{x:.3f}:{y:.3f}:{yaw:.3f}')
            self._send_json({'result': 'ok'})
        elif path == '/api/cancel_mapping':
            # Haritalamadan VAZGEC - harita henuz KAYDEDILMEDIYSE (finish_mapping
            # cagrilmadiysa) eski harita hala diskte duruyor, sadece Nav2'ye geri donulur.
            try:
                d = json.loads(self._read_body() or '{}')
            except (ValueError, TypeError):
                d = {}
            if str(d.get('password', '')) != OPERATOR_PASSWORD:
                self._send_json({'result': 'error', 'reason': 'wrong password'})
                return
            self.ros_node.launch_mgr.start_nav(self.ros_node.active_map_yaml_path())
            self.ros_node.mode = 'operating'
            self._publish_command('mapping_done')
            self._send_json({'result': 'ok'})
        elif path == '/api/send_message':
            # gövde: {"from": "Masa 1", "to": "Garson", "text": "..."}
            try:
                d = json.loads(self._read_body() or '{}')
                frm = str(d.get('from', '')).strip()
                to = str(d.get('to', '')).strip()
                text = str(d.get('text', '')).replace('|', '/').replace('\n', ' ').strip()
            except (ValueError, TypeError):
                frm = to = text = ''
            if frm and to and text:
                self._publish_command(f'msg:{frm}|{to}|{text}')
                self._send_json({'result': 'ok'})
            else:
                self._send_json({'result': 'error', 'reason': 'missing field'})
        elif path == '/api/msg_open':
            self._publish_command('msg_open')
            self._send_json({'result': 'ok'})
        elif path == '/api/msg_compose_start':
            self._publish_command('msg_compose_start')
            self._send_json({'result': 'ok'})
        elif path == '/api/msg_compose_cancel':
            self._publish_command('msg_compose_cancel')
            self._send_json({'result': 'ok'})
        elif path == '/api/msg_reply':
            try:
                d = json.loads(self._read_body() or '{}')
                text = str(d.get('text', '')).replace('|', '/').replace('\n', ' ').strip()
            except (ValueError, TypeError):
                text = ''
            self._publish_command(f'msg_reply:{text}')
            self._send_json({'result': 'ok'})
        elif path == '/api/waypoints':
            # govde: {"barista": {...}, "door": {...}, "tables": [{...}, ...]}
            try:
                cfg = json.loads(self._read_body() or '{}')
            except (ValueError, TypeError):
                self._send_json({'result': 'error', 'reason': 'bad json'})
                return
            try:
                self.ros_node.save_waypoints_cfg(cfg)
            except Exception as e:  # noqa: BLE001
                self._send_json({'result': 'error', 'reason': str(e)})
                return
            self._publish_command('reload_waypoints')
            # Kurulum ekrani "haritalama/tagging" akisindan geldiyse (yeni harita
            # cizildikten sonraki nokta tanimlama) - bu kaydet, akisi BITIRIR ve
            # devriyeyi tekrar kullanilabilir kilar. Var olan kafede sadece nokta
            # duzeltmesi yapiliyorsa (mode zaten 'operating') hicbir sey degismez.
            if self.ros_node.mode in ('tagging', 'mapping'):
                self.ros_node.mode = 'operating'
                self._publish_command('mapping_done')
            self._send_json({'result': 'ok', 'mode': self.ros_node.mode})
        else:
            self.send_error(404)

    def _read_body(self):
        n = int(self.headers.get('Content-Length', 0))
        return self.rfile.read(n).decode('utf-8') if n > 0 else ''

    def _serve_html(self, filename):
        html_path = os.path.join(self.ros_node.web_dir, filename)
        try:
            with open(html_path, 'r', encoding='utf-8') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')
            self.end_headers()
            self.wfile.write(content.encode('utf-8'))
        except FileNotFoundError:
            self.send_error(500, filename + ' not found at: ' + html_path)

    def _send_json(self, data):
        body = json.dumps(data).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _publish_command(self, cmd):
        msg = String()
        msg.data = cmd
        self.ros_node.command_pub.publish(msg)
        self.ros_node.get_logger().info(f'Komut yayinlandi: {cmd}')

    def log_message(self, format, *args):
        # HTTP loglarını sustur (ROS loglarına güveniyoruz)
        pass


class TabletServerNode(Node):
    """ROS2 node - tablet sunucu."""

    def __init__(self):
        super().__init__('tablet_server')
        self.command_pub = self.create_publisher(String, '/patrol_command', 10)
        self.status_sub = self.create_subscription(
            String, '/patrol_status', self._status_callback, 10)
        self.current_status = 'idle'
        self.status_count = 0
        self.last_status_time = 0.0
        share_dir = get_package_share_directory('cryvex_gazebo')
        self.web_dir = os.path.join(share_dir, 'web')
        # config/ ve maps/ ALTINDA YENI DOSYA OLUSTURABILECEGIMIZ (waypoints.json,
        # harita .bak yedekleri, haritalama sonrasi kaydedilen YENI cafe_map.*) her
        # yer, --symlink-install ile GERCEK kaynak agacina cozulmeli - yoksa yeni
        # dosya install/ paylasim dizinine dusup bir sonraki `colcon build`'da
        # kaybolur (src/'a symlink olamaz, cunku derleme aninda yoktu). Bu betigin
        # GERCEK (symlink cozulmus) yeri src/cryvex_gazebo/scripts/tablet_server.py.
        real_script = os.path.realpath(os.path.abspath(__file__))
        src_root = os.path.dirname(os.path.dirname(real_script))
        src_config_dir = os.path.join(src_root, 'config')
        src_maps_dir = os.path.join(src_root, 'maps')
        in_source_tree = os.path.isfile(os.path.join(src_config_dir, 'nav2_params.yaml'))
        self.config_dir = src_config_dir if in_source_tree else os.path.join(share_dir, 'config')
        self.maps_dir = src_maps_dir if in_source_tree else os.path.join(share_dir, 'maps')
        self._map_png_cache = None  # (mtime, bytes)
        self.get_logger().info(f'Web dizini: {self.web_dir}')
        self.create_timer(5.0, self._health_check)

        # ---- Nav2 <-> canli haritalama (slam_toolbox) surum yonetimi ----
        # Onceki (crash/kill olmus) tablet_server'dan kalma yetim Nav2/SLAM
        # sureclerini temizle - yoksa asagida baslattigimizin YANINDA ikinci
        # bir kopya kalir (patrol.py'de daha once yasanan 'duplicate node'un
        # surum tarafindaki karsiligi).
        _kill_stray_processes(self.get_logger())
        self._live_map_msg = None
        self.map_sub = self.create_subscription(
            OccupancyGrid, '/map', self._map_cb, MAP_QOS)
        # Haritalama bitince robotun O ANKI gercek pozunu (map->base_footprint,
        # slam_toolbox'in kendi TF'i) OKUYUP yeni AMCL'e otomatik veriyoruz -
        # RViz'deki "2D Pose Estimate"i elle yapmaya gerek kalmasin diye.
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
        self.launch_mgr = LaunchManager(self)
        # 'configured' = daha once en az bir masa kaydedilmis (bu kafede zaten
        # oyle) -> normal calisma: Nav2/AMCL hemen baslar, degisen bir sey yok.
        # Degilse (yeni/bos kurulum) garson ana ekrandaki (/) Yonetici Paneli ->
        # "Ortami Haritala"ya basana kadar Nav2 BASLATILMAZ.
        if self.is_configured():
            self.mode = 'operating'
            self.launch_mgr.start_nav(self.active_map_yaml_path())
        else:
            self.mode = 'unconfigured'
            self.get_logger().warn(
                'HENUZ MASA/HARITA YOK - Nav2 baslatilmadi. '
                'http://<ip>:8080/ -> Yonetici Paneli -> "Ortami Haritala" ile kurulumu tamamlayin.')

    def active_map_yaml_path(self):
        """Su an TEK bir aktif harita var (cafe_map). Ileride birden fazla
        kafe/harita desteklenmek istenirse burasi genisletilir."""
        return os.path.join(self.maps_dir, 'cafe_map.yaml')

    # ---- canli harita (SLAM sirasinda, operator ekrani icin) ----
    def _map_cb(self, msg):
        self._live_map_msg = msg

    def live_map_png_bytes(self):
        msg = self._live_map_msg
        if msg is None or msg.info.width == 0 or msg.info.height == 0:
            return None
        return _occgrid_to_png_bytes(msg)

    # ---- harita gorseli (kurulum ekrani icin) ----
    def map_png_bytes(self):
        pgm_path = os.path.join(self.maps_dir, self._map_yaml().get('image', 'cafe_map.pgm'))
        mtime = os.path.getmtime(pgm_path)
        if self._map_png_cache and self._map_png_cache[0] == mtime:
            return self._map_png_cache[1]
        png = _pgm_to_png_bytes(pgm_path)
        self._map_png_cache = (mtime, png)
        return png

    def _map_yaml(self):
        """cafe_map.yaml'i sade sekilde okur (yaml kutuphanesi gerektirmez)."""
        info = {'resolution': 0.05, 'origin': [0.0, 0.0, 0.0], 'image': 'cafe_map.pgm'}
        yaml_path = os.path.join(self.maps_dir, 'cafe_map.yaml')
        try:
            with open(yaml_path, encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#') or ':' not in line:
                        continue
                    key, val = line.split(':', 1)
                    key, val = key.strip(), val.strip()
                    if key == 'resolution':
                        info['resolution'] = float(val)
                    elif key == 'origin':
                        info['origin'] = list(ast.literal_eval(val))
                    elif key == 'image':
                        info['image'] = val
        except Exception as e:  # noqa: BLE001
            self.get_logger().warn(f'cafe_map.yaml okunamadi: {e}')
        return info

    def map_info(self):
        info = self._map_yaml()
        try:
            w, h, _ = _parse_pgm(os.path.join(self.maps_dir, info['image']))
            info['width'], info['height'] = w, h
        except Exception as e:  # noqa: BLE001
            self.get_logger().warn(f'PGM boyutu okunamadi: {e}')
            info['width'] = info['height'] = 0
        return info

    # ---- masa/kapi/barmen noktalari (kurulum ekrani kaydeder, patrol.py okur) ----
    def _waypoints_path(self):
        return os.path.join(self.config_dir, 'waypoints.json')

    def load_waypoints_cfg(self):
        path = self._waypoints_path()
        if os.path.exists(path):
            try:
                with open(path, encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:  # noqa: BLE001
                self.get_logger().warn(f'waypoints.json okunamadi: {e}')
        return {'barista': None, 'door': None, 'tables': []}

    def save_waypoints_cfg(self, cfg):
        os.makedirs(self.config_dir, exist_ok=True)
        with open(self._waypoints_path(), 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        self.get_logger().info(f'waypoints.json kaydedildi ({len(cfg.get("tables", []))} masa).')

    def is_configured(self):
        """En az bir masa kaydedilmis mi? (bos kurulum = Nav2 otomatik baslamaz)."""
        return bool(self.load_waypoints_cfg().get('tables'))

    def reset_waypoints_cfg(self):
        """Yeniden haritalama sonrasi ESKI noktalar YENI haritada anlamsizdir
        (SLAM haritayi farkli bir orijine gore cizer) - kurulum ekrani BOS
        acilsin diye temizlenir. patrol.py'nin bellekteki WAYPOINTS'i (hala
        eskisi) 'Kaydet'e kadar map_ready=False oldugu icin zaten kullanilmaz."""
        self.save_waypoints_cfg({'barista': None, 'door': None, 'tables': []})

    def _backup_current_map(self):
        """Yeniden haritalamadan once eski haritayi .bak olarak sakla (geri
        donus icin manuel kurtarma - otomatik bir 'geri al' arayuzu yok)."""
        for ext in ('.pgm', '.yaml'):
            src = os.path.join(self.maps_dir, 'cafe_map' + ext)
            if os.path.exists(src):
                try:
                    shutil.copy2(src, src + '.bak')
                except Exception as e:  # noqa: BLE001
                    self.get_logger().warn(f'Harita yedeklenemedi ({src}): {e}')
        try:
            wp_path = self._waypoints_path()
            if os.path.exists(wp_path):
                shutil.copy2(wp_path, wp_path + '.bak')
        except Exception as e:  # noqa: BLE001
            self.get_logger().warn(f'waypoints.json yedeklenemedi: {e}')

    def _capture_robot_pose(self):
        """SLAM haritalama BITMEDEN once robotun o anki gercek pozunu
        (map->base_footprint TF) okur. None = alinamadi (garson kurulum
        ekranindan 'Robot Burada' ile elle ayarlamali)."""
        try:
            tf = self.tf_buffer.lookup_transform(
                'map', 'base_footprint', RclpyTime(), timeout=Duration(seconds=1.5))
        except Exception as e:  # noqa: BLE001
            self.get_logger().warn(f'Robot pozu TF ile okunamadi ({e}) - "Robot Burada" ile elle ayarlanmali.')
            return None
        t = tf.transform.translation
        q = tf.transform.rotation
        yaw = math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))
        return (t.x, t.y, yaw)

    def publish_command(self, cmd):
        msg = String()
        msg.data = cmd
        self.command_pub.publish(msg)
        self.get_logger().info(f'Komut yayinlandi: {cmd}')

    def finish_mapping(self):
        """'Haritalamayi Bitir' -> robotun O ANKI pozunu (TF) yakala, canli
        /map'i diske yaz, slam_toolbox'i durdur, YENI haritayla Nav2'yi baslat,
        eski (artik anlamsiz) noktalari temizle, YAKALANAN pozu yeni AMCL'e
        otomatik ver (RViz '2D Pose Estimate'in otomatik karsiligi). Kurulum
        ekrani (setup.html) bundan sonra BOS acilip operator masalari/kapiyi/
        barmeni (ve gerekirse pozu elle duzeltmek icin 'Robot Burada'yi)
        yeniden isaretler."""
        if self._live_map_msg is None:
            raise RuntimeError('Henuz canli harita verisi yok - biraz daha surup dolasin.')
        captured_pose = self._capture_robot_pose()   # slam_toolbox HALA ayaktayken oku
        self._backup_current_map()
        map_path_noext = os.path.join(self.maps_dir, 'cafe_map')
        cmd = ['ros2', 'run', 'nav2_map_server', 'map_saver_cli',
               '-t', '/map', '-f', map_path_noext,
               '--ros-args', '-p', 'save_map_timeout:=5.0', '-p', 'use_sim_time:=true']
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15.0)
        if result.returncode != 0:
            raise RuntimeError(f'map_saver_cli basarisiz: {result.stderr[-400:]}')
        self.get_logger().info('Yeni harita diske kaydedildi (cafe_map.pgm/.yaml).')
        self._map_png_cache = None   # eski PGM cache'i gecersiz
        self.reset_waypoints_cfg()
        self.launch_mgr.start_nav(self.active_map_yaml_path())
        self.mode = 'tagging'        # setup.html "Kaydet"e basana kadar bu modda kalir
        if captured_pose:
            x, y, yaw = captured_pose
            self.publish_command(f'set_pose:{x:.3f}:{y:.3f}:{yaw:.3f}')
            self.get_logger().info(f'Robot pozu otomatik yakalandi: ({x:.2f}, {y:.2f}, yaw={yaw:.2f})')
        return captured_pose is not None

    def _status_callback(self, msg):
        self.current_status = msg.data
        self.status_count += 1
        self.last_status_time = time.time()
        if self.status_count == 1:
            self.get_logger().info('/patrol_status ILK mesaji alindi -> arayuz canli olmali.')
        elif self.status_count % 30 == 0:
            self.get_logger().info(
                f'/patrol_status #{self.status_count}: {msg.data[:90]}')

    def _health_check(self):
        if self.status_count == 0:
            self.get_logger().warn(
                "/patrol_status HIC gelmedi! patrol.py calisiyor mu ve AYNI ROS_DOMAIN_ID / "
                "ayni makinede mi? Test: `ros2 topic echo /patrol_status`")


def get_local_ips():
    """Makinenin tüm yerel IP adreslerini döndürür."""
    ips = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip not in ips and not ip.startswith('127.'):
                ips.append(ip)
    except Exception:
        pass
    if not ips:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('8.8.8.8', 80))
            ips.append(s.getsockname()[0])
            s.close()
        except Exception:
            ips.append('127.0.0.1')
    return ips


def main():
    rclpy.init()
    node = TabletServerNode()

    # HTTP handler'a ROS node referansını ver
    TabletHandler.ros_node = node

    port = 8080
    try:
        server = HTTPServer(('0.0.0.0', port), TabletHandler)
    except OSError as exc:
        node.get_logger().error(
            f'PORT {port} ACILAMADI ({exc}). Eski bir tablet_server hala calisiyor olabilir. '
            f'Kapatmak icin:  pkill -f tablet_server.py   sonra tekrar baslatin.')
        rclpy.shutdown()
        sys.exit(1)

    # HTTP server'ı ayrı thread'de çalıştır
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    # Bağlantı bilgilerini yazdır
    ips = get_local_ips()
    node.get_logger().info('=' * 50)
    node.get_logger().info('  CRYVEX TABLET SERVER AKTIF')
    node.get_logger().info('=' * 50)
    for ip in ips:
        node.get_logger().info(f'  Tablet tarayicida ac: http://{ip}:{port}')
    node.get_logger().info('=' * 50)

    # Tarayıcıyı tam ekran (Kiosk) modunda otomatik aç (Dokunmatik ekranlar için ideal)
    import webbrowser

    url = f'http://127.0.0.1:{port}'
    node.get_logger().info('Tablet arayuzu pencere olarak baslatiliyor...')
    
    commands = [
        ['google-chrome', f'--app={url}', '--window-size=800,600'],
        ['chromium-browser', f'--app={url}', '--window-size=800,600'],
        ['firefox', '--width=800', '--height=600', url],
    ]
    
    browser_opened = False
    for cmd in commands:
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            node.get_logger().info(f"{cmd[0]} ile acildi.")
            browser_opened = True
            break
        except FileNotFoundError:
            continue
            
    if not browser_opened:
        node.get_logger().warn('Chrome/Firefox bulunamadi, varsayilan tarayici aciliyor.')
        try:
            webbrowser.open(url)
        except Exception as e:
            node.get_logger().error(f'Tarayici acilamadi: {e}')

    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, rclpy.executors.ExternalShutdownException):
        pass
    finally:
        server.shutdown()
        try:
            node.destroy_node()
            rclpy.shutdown()
        except Exception:
            pass


if __name__ == '__main__':
    main()
