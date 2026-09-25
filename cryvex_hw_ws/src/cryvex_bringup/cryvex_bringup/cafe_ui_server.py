#!/usr/bin/env python3
"""
Cryvex Kafe Arayuzu - gercek donanim (Asama 4'un ERKEN/KISMI portu)
=====================================================================
~/cryvex_ws/src/cryvex_gazebo/web/index.html'i (goz animasyonlari, sanal
joystick, "Ortami Haritala" akisi) DEGISTIRMEDEN, gercek donanimda sunar.
patrol.py'nin TAM durum makinesi (masalar, siparis, mesajlasma, devriye)
HENUZ yok - motor/STM32 gelmeden bunlarin bir anlami olmadigi icin bilincli
olarak SIMDILIK STUB birakildi:

  - /api/status: sabit "idle" durumu doner (gozler normal gorunur, ekran acik) -
    devriye/siparis/mesaj alanlari hep bos/kapali.
  - /api/start_patrol, /wander, /goto, /rescue_* vb. (patrol.py'ye ozel
    komutlar): /patrol_command'a yayinlanir (DINLEYEN YOK, zararsiz) ve
    {'result':'ok'} doner - butonlar hata GOSTERMEZ ama gercek bir sey de
    YAPMAZ (motor yok).
  - /api/teleop, /start_mapping, /finish_mapping, /cancel_mapping,
    /live_map.png: GERCEK calisir (LiDAR+slam_toolbox+/cmd_vel gercek).
  - /setup (masa/kapi/barmen noktalarini isaretleme) + /api/waypoints: GERCEK
    calisir (tablet_server.py'den birebir portlandi, 2026-09-24).
  - /api/tts_audio + /api/speak_here: robotun TEK sesi (edge-tts, kadin).
    Uretilen her cumle KALICI onbellege yazilir ve arayuzun sabit cumleleri
    internet gelir gelmez onceden uretilir - acilista internet/saat henuz
    hazir degilken de robot hep ayni sesle konusur.

Motor/STM32 baglaninca ve patrol.py gercek donanima portlaninca bu dosyanin
stub kisimlari GERCEK patrol_status/is_configured mantigiyla degisecek -
index.html'de TEK SATIR degisiklik gerekmeyecek (zaten aynen kullaniliyor).
"""
import ast
import asyncio
import hashlib
import json
import os
import re
import signal
import struct
import subprocess
import tempfile
import threading
import time
import urllib.parse
import zlib
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy, HistoryPolicy
from ament_index_python.packages import get_package_share_directory
from geometry_msgs.msg import Twist
from nav_msgs.msg import OccupancyGrid
from std_msgs.msg import String

try:
    import edge_tts  # kurulu degilse yalnizca onbellekteki cumleler calinir
    _EDGE_TTS_AVAILABLE = True
except ImportError:
    _EDGE_TTS_AVAILABLE = False

OPERATOR_PASSWORD = '1234'  # index.html/Flutter app ile AYNI (sim ile tutarli)

MAP_QOS = QoSProfile(
    depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL,
    reliability=ReliabilityPolicy.RELIABLE, history=HistoryPolicy.KEEP_LAST)

JOY_MAX_LIN = 0.30
JOY_MAX_ANG = 1.00

ROBOT_EXPRESSIONS = ('happy', 'love', 'alert', 'sad')  # index.html setExpression() ile ayni

TTS_VOICE = 'tr-TR-EmelNeural'
TTS_CACHE_DIR = os.path.expanduser('~/.cache/cryvex_tts')  # /tmp degil: acilista silinmesin


# ==================== PNG kodlama (tablet_server.py'den birebir) ====================
def _gray_bytes_to_png(width, height, pixels):
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        raw.extend(pixels[y * width:(y + 1) * width])
    compressed = zlib.compress(bytes(raw), 6)

    def chunk(tag, payload):
        return (struct.pack('>I', len(payload)) + tag + payload +
                struct.pack('>I', zlib.crc32(tag + payload) & 0xffffffff))

    ihdr = struct.pack('>IIBBBBB', width, height, 8, 0, 0, 0, 0)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) +
            chunk(b'IDAT', compressed) + chunk(b'IEND', b''))


def _occgrid_to_png_bytes(msg):
    w, h = msg.info.width, msg.info.height
    data = msg.data
    pixels = bytearray(w * h)
    for i, v in enumerate(data):
        pixels[i] = 205 if v < 0 else max(0, min(255, round(254 - (v / 100.0) * 254)))
    flipped = bytearray(w * h)
    for row in range(h):
        src, dst = row * w, (h - 1 - row) * w
        flipped[dst:dst + w] = pixels[src:src + w]
    return _gray_bytes_to_png(w, h, bytes(flipped))


def _parse_pgm(path):
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
    int(next_token())
    pos += 1
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


def _pgm_to_png_bytes(path):
    width, height, pixels = _parse_pgm(path)
    return _gray_bytes_to_png(width, height, pixels)


# ==================== Ses (TTS) ====================
# Robotun TEK sesi edge-tts (kadin). Baska bir sese (Piper/tarayici) dusmez:
# internet yokken ve cumle daha once hic uretilmediyse sessiz gecer.
def _tts_path(text):
    """text -> robotun sesiyle uretilmis mp3'un onbellek yolu ya da None."""
    key = hashlib.sha1(f'edge:{TTS_VOICE}:{text}'.encode('utf-8')).hexdigest()
    path = os.path.join(TTS_CACHE_DIR, key + '.mp3')
    if os.path.isfile(path) and os.path.getsize(path) > 0:
        return path
    if not _EDGE_TTS_AVAILABLE:
        return None
    os.makedirs(TTS_CACHE_DIR, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=TTS_CACHE_DIR, suffix='.part')
    os.close(fd)
    try:
        asyncio.run(asyncio.wait_for(edge_tts.Communicate(text, TTS_VOICE).save(tmp), timeout=8.0))
        if os.path.getsize(tmp) == 0:
            return None
        os.replace(tmp, path)  # atomik: yarim yazilmis dosya onbellekte asla gorunmez
        return path
    except Exception:  # noqa: BLE001
        return None
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def _ui_phrases(web_dir):
    """index.html'deki sabit cumleler: speak/robotSays('...') + *_PHRASES/*_LINES dizileri."""
    try:
        with open(os.path.join(web_dir, 'index.html'), encoding='utf-8') as f:
            html = f.read()
    except OSError:
        return []
    phrases = set(re.findall(r"(?:speak|robotSays)\('([^'\\]+)'\)", html))
    for body in re.findall(r'const [A-Z_]+(?:PHRASES|LINES) = \[(.*?)\];', html, re.DOTALL):
        phrases.update(re.findall(r"'([^'\\]+)'", body))
    return sorted(phrases)


# ==================== Hoparlor sesi (PulseAudio) ====================
# cafe_ui_server systemd servisi olarak (User=main) calisiyor ama systemd
# system-unit'leri varsayilan olarak XDG_RUNTIME_DIR ayarlamaz - bu olmadan
# pactl "Connection refused" verir (kullanicinin oturum PulseAudio'suna
# ulasamaz). Asagida her cagrida acikca ekleniyor.
def _pactl_env():
    env = dict(os.environ)
    env.setdefault('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')
    return env


def get_volume_pct():
    try:
        result = subprocess.run(
            ['pactl', 'get-sink-volume', '@DEFAULT_SINK@'],
            capture_output=True, text=True, timeout=3.0, env=_pactl_env())
        if result.returncode != 0:
            return None
        m = re.search(r'(\d+)%', result.stdout)
        return int(m.group(1)) if m else None
    except Exception:  # noqa: BLE001
        return None


def set_volume_pct(pct):
    pct = max(0, min(100, int(pct)))
    try:
        result = subprocess.run(
            ['pactl', 'set-sink-volume', '@DEFAULT_SINK@', f'{pct}%'],
            capture_output=True, text=True, timeout=3.0, env=_pactl_env())
        return result.returncode == 0
    except Exception:  # noqa: BLE001
        return False



class LaunchManager:
    """mapping.launch.py'yi baslatir/durdurur (tablet_server.py deseninin
    sadelesmis hali - Nav2 tarafi henuz otomatik tetiklenmiyor, bilinçli)."""

    def __init__(self, node):
        self.node = node
        self.proc = None
        self._lock = threading.Lock()

    def is_running(self):
        return self.proc is not None and self.proc.poll() is None

    def stop(self):
        with self._lock:
            if self.proc is None:
                return
            if self.proc.poll() is None:
                pid = self.proc.pid
                try:
                    os.killpg(os.getpgid(pid), signal.SIGINT)
                    self.proc.wait(timeout=8.0)
                except Exception:  # noqa: BLE001
                    try:
                        os.killpg(os.getpgid(pid), signal.SIGKILL)
                        self.proc.wait(timeout=3.0)
                    except Exception:  # noqa: BLE001
                        pass
            self.proc = None
            self.node.get_logger().info('[LaunchManager] Haritalama durduruldu.')

    def start_slam(self):
        with self._lock:
            if self.proc is not None and self.proc.poll() is None:
                return
            self.node.get_logger().info('[LaunchManager] Haritalama (slam_toolbox) basliyor...')
            cmd = ['ros2', 'launch', 'cryvex_bringup', 'mapping.launch.py']
            self.proc = subprocess.Popen(cmd, start_new_session=True)


class CafeUiServerNode(Node):
    def __init__(self):
        super().__init__('cafe_ui_server')
        self.declare_parameter('http_port', 8080)
        port = self.get_parameter('http_port').value

        real_script = os.path.realpath(os.path.abspath(__file__))
        src_root = os.path.dirname(os.path.dirname(real_script))
        src_web_dir = os.path.join(src_root, 'web')
        src_maps_dir = os.path.join(src_root, 'maps')
        src_config_dir = os.path.join(src_root, 'config')
        if os.path.isdir(src_web_dir):
            self.web_dir = src_web_dir
            self.maps_dir = src_maps_dir
            self.config_dir = src_config_dir
        else:
            share_dir = get_package_share_directory('cryvex_bringup')
            self.web_dir = os.path.join(share_dir, 'web')
            self.maps_dir = os.path.join(share_dir, 'maps')
            self.config_dir = os.path.join(share_dir, 'config')
        os.makedirs(self.maps_dir, exist_ok=True)

        self._lock = threading.Lock()
        self._live_map_msg = None
        self._map_png_cache = None
        self.mode = 'operating'
        self.screen_on = True
        self.speak_text, self.speak_expr, self.speak_seq = '', '', 0

        self.create_subscription(OccupancyGrid, '/map', self._map_cb, MAP_QOS)
        self.cmd_pub = self.create_publisher(Twist, '/cmd_vel', 10)
        self.command_pub = self.create_publisher(String, '/patrol_command', 10)  # dinleyen yok, zararsiz
        self.launch_mgr = LaunchManager(self)

        self._httpd = ThreadingHTTPServer(('0.0.0.0', port), self._make_handler())
        self._http_thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._http_thread.start()
        threading.Thread(target=self._prewarm_tts, daemon=True).start()
        self.get_logger().info(f'Kafe arayuzu (bench) hazir: http://0.0.0.0:{port}/')
        self.get_logger().warn(
            'BU BIR ARA SURUM: patrol.py/motor henuz yok - devriye/siparis/mesaj '
            'butonlari hicbir sey yapmaz (hata da vermez), sadece haritalama+joystick GERCEK calisir.')

    def _prewarm_tts(self):
        # Arayuzun sabit cumleleri internet gelir gelmez kalici onbellege
        # uretilir; acilista (internet/saat henuz hazir degilken) da hazir olsunlar.
        pending = _ui_phrases(self.web_dir)
        delay = 10.0
        while pending:
            pending = [p for p in pending if _tts_path(p) is None]
            if pending:
                self.get_logger().warn(f'{len(pending)} cumlenin sesi uretilemedi (internet?), {delay:.0f}sn sonra tekrar.')
                time.sleep(delay)
                delay = min(delay * 2, 300.0)
        self.get_logger().info('Ses onbellegi hazir (tum arayuz cumleleri).')

    def _map_cb(self, msg):
        with self._lock:
            self._live_map_msg = msg

    def live_map_png_bytes(self):
        with self._lock:
            msg = self._live_map_msg
        if msg is None or msg.info.width == 0:
            return None
        return _occgrid_to_png_bytes(msg)

    def map_info(self):
        info = {'resolution': 0.05, 'origin': [0.0, 0.0, 0.0], 'image': 'cafe_map.pgm'}
        yaml_path = os.path.join(self.maps_dir, 'cafe_map.yaml')
        try:
            with open(yaml_path, encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#') or ':' not in line:
                        continue
                    key, val = (p.strip() for p in line.split(':', 1))
                    if key == 'resolution':
                        info['resolution'] = float(val)
                    elif key == 'origin':
                        info['origin'] = list(ast.literal_eval(val))
                    elif key == 'image':
                        info['image'] = val
            w, h, _ = _parse_pgm(os.path.join(self.maps_dir, info['image']))
            info['width'], info['height'] = w, h
        except Exception:  # noqa: BLE001
            info['width'] = info['height'] = 0
        return info

    def map_png_bytes(self):
        info = self.map_info()
        pgm_path = os.path.join(self.maps_dir, info.get('image', 'cafe_map.pgm'))
        mtime = os.path.getmtime(pgm_path)
        if self._map_png_cache and self._map_png_cache[0] == mtime:
            return self._map_png_cache[1]
        png = _pgm_to_png_bytes(pgm_path)
        self._map_png_cache = (mtime, png)
        return png

    def has_saved_map(self):
        return os.path.isfile(os.path.join(self.maps_dir, 'cafe_map.yaml'))

    # ---- masa/kapi/barmen noktalari (kurulum ekrani kaydeder) ----
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
        return bool(self.load_waypoints_cfg().get('tables'))

    def reset_waypoints_cfg(self):
        # yeniden haritalama sonrasi eski noktalar YENI haritada anlamsizdir
        # (SLAM haritayi farkli bir orijine gore cizer) - kurulum ekrani BOS acilsin.
        self.save_waypoints_cfg({'barista': None, 'door': None, 'tables': []})

    def finish_mapping(self):
        if self._live_map_msg is None:
            raise RuntimeError('Henuz canli harita verisi yok - biraz daha surup dolasin.')
        map_path_noext = os.path.join(self.maps_dir, 'cafe_map')
        cmd = ['ros2', 'run', 'nav2_map_server', 'map_saver_cli',
               '-t', '/map', '-f', map_path_noext,
               '--ros-args', '-p', 'save_map_timeout:=5.0', '-p', 'use_sim_time:=false']
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15.0)
        if result.returncode != 0:
            raise RuntimeError(f'map_saver_cli basarisiz: {result.stderr[-400:]}')
        self.get_logger().info('Harita diske kaydedildi (cafe_map.pgm/.yaml).')
        self._map_png_cache = None
        self.reset_waypoints_cfg()
        self.launch_mgr.stop()
        self.mode = 'operating'

    def publish_cmd(self, lx, az):
        lx = max(-JOY_MAX_LIN, min(JOY_MAX_LIN, float(lx)))
        az = max(-JOY_MAX_ANG, min(JOY_MAX_ANG, float(az)))
        msg = Twist()
        msg.linear.x = lx
        msg.angular.z = az
        self.cmd_pub.publish(msg)

    def request_robot_speech(self, text, expr):
        _tts_path(text)  # ses simdiden hazir olsun: kiosk istediginde aninda calsin
        with self._lock:
            self.speak_text, self.speak_expr = text, expr
            self.speak_seq += 1

    def status_payload(self):
        # patrol.py'nin publish_status_now() ile AYNI anahtarlar - index.html/
        # Flutter app bunlari bekliyor. Motor/patrol yok, hepsi "bos/idle" -
        # goz animasyonu normal (dinlenme) durumunda gorunur, hata vermez.
        stub = {
            'state': 'idle', 'waypoint': None, 'table_index': -1,
            'wait_total': 0.0, 'wait_remaining': 0.0,
            'interacting': False, 'greeting': False, 'cute': False,
            'screen_on': self.screen_on, 'speak_text': self.speak_text,
            'speak_seq': self.speak_seq, 'speak_expr': self.speak_expr,
            'order': None,
            'msg_phase': None, 'msg_from': None, 'msg_to': None, 'msg_text': None,
            'msg_total': 0.0, 'msg_remaining': 0.0, 'msg_composing': False,
            'map_ready': not self.launch_mgr.is_running(),
            'rescue_active': False,
        }
        return {'status': json.dumps(stub), 'count': 1, 'age': 0.1}

    def _make_handler(node_self):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):  # noqa: A003
                pass

            def _read_body(self):
                length = int(self.headers.get('Content-Length', 0) or 0)
                return self.rfile.read(length).decode('utf-8') if length else ''

            def _send_json(self, data):
                body = json.dumps(data).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _serve_file(self, rel_path, content_type):
                path = os.path.join(node_self.web_dir, rel_path)
                try:
                    with open(path, 'rb') as f:
                        body = f.read()
                except FileNotFoundError:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                path = self.path.split('?')[0]
                if path in ('/', '/index.html'):
                    self._serve_file('index.html', 'text/html; charset=utf-8')
                elif path in ('/setup', '/setup.html'):
                    self._serve_file('setup.html', 'text/html; charset=utf-8')
                elif path == '/api/mode':
                    self._send_json({'mode': node_self.mode, 'configured': node_self.is_configured()})
                elif path == '/api/status':
                    self._send_json(node_self.status_payload())
                elif path == '/api/live_map.png':
                    png = node_self.live_map_png_bytes()
                    if png is None:
                        self.send_error(503, 'Henuz canli harita yok')
                        return
                    self._serve_png(png)
                elif path == '/api/map.png':
                    try:
                        png = node_self.map_png_bytes()
                    except Exception as e:  # noqa: BLE001
                        self.send_error(500, str(e))
                        return
                    self._serve_png(png)
                elif path == '/api/map_info':
                    self._send_json(node_self.map_info())
                elif path == '/api/waypoints':
                    self._send_json(node_self.load_waypoints_cfg())
                elif path == '/api/tts_audio':
                    self._serve_tts_audio()
                elif path == '/api/volume':
                    vol = get_volume_pct()
                    self._send_json({'volume': vol if vol is not None else -1})
                else:
                    self.send_error(404)

            def _serve_tts_audio(self):
                qs = urllib.parse.urlparse(self.path).query
                text = urllib.parse.parse_qs(qs).get('text', [''])[0].strip()
                if not text:
                    self.send_error(400, 'text parametresi gerekli')
                    return
                path = _tts_path(text)
                if path is None:
                    self.send_error(503, 'Ses uretilemedi (internet yok ve onbellekte yok)')
                    return
                with open(path, 'rb') as f:
                    audio = f.read()
                self.send_response(200)
                self.send_header('Content-Type', 'audio/mpeg')
                # Tarayici SAKLAMASIN: ses degisirse eski ses kendi disk
                # onbelleginden calinmaya devam ediyordu. Sunucu onbellegi zaten hizli.
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Content-Length', str(len(audio)))
                self.end_headers()
                self.wfile.write(audio)

            def _serve_png(self, png):
                self.send_response(200)
                self.send_header('Content-Type', 'image/png')
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Content-Length', str(len(png)))
                self.end_headers()
                self.wfile.write(png)

            def do_POST(self):
                path = self.path.split('?')[0]
                try:
                    d = json.loads(self._read_body() or '{}')
                except Exception:  # noqa: BLE001
                    d = {}

                def need_password():
                    return str(d.get('password', '')) != OPERATOR_PASSWORD

                if path == '/api/teleop':
                    node_self.publish_cmd(d.get('lx', 0.0), d.get('az', 0.0))
                    self._send_json({'result': 'ok'})
                elif path == '/api/teleop_stop':
                    node_self.publish_cmd(0.0, 0.0)
                    self._send_json({'result': 'ok'})
                elif path == '/api/wake':
                    node_self.screen_on = True
                    self._send_json({'result': 'ok'})
                elif path == '/api/sleep':
                    node_self.screen_on = False
                    self._send_json({'result': 'ok'})
                elif path == '/api/start_mapping':
                    if need_password():
                        self._send_json({'result': 'error', 'reason': 'wrong password'})
                        return
                    node_self.mode = 'mapping'
                    node_self.launch_mgr.start_slam()
                    self._send_json({'result': 'ok'})
                elif path == '/api/finish_mapping':
                    if need_password():
                        self._send_json({'result': 'error', 'reason': 'wrong password'})
                        return
                    try:
                        node_self.finish_mapping()
                    except Exception as e:  # noqa: BLE001
                        self._send_json({'result': 'error', 'reason': str(e)})
                        return
                    self._send_json({'result': 'ok', 'pose_captured': False})
                elif path == '/api/cancel_mapping':
                    if need_password():
                        self._send_json({'result': 'error', 'reason': 'wrong password'})
                        return
                    node_self.launch_mgr.stop()
                    node_self.mode = 'operating'
                    self._send_json({'result': 'ok'})
                elif path == '/api/waypoints':
                    # govde: {"barista": {...}, "door": {...}, "tables": [{...}, ...]}
                    try:
                        node_self.save_waypoints_cfg(d)
                    except Exception as e:  # noqa: BLE001
                        self._send_json({'result': 'error', 'reason': str(e)})
                        return
                    if node_self.mode in ('tagging', 'mapping'):
                        node_self.mode = 'operating'
                    self._send_json({'result': 'ok', 'mode': node_self.mode})
                elif path == '/api/volume':
                    # govde: {"volume": 0-100} - sifre gerekmez (zararsiz, geri alinabilir).
                    try:
                        pct = int(d.get('volume'))
                    except (TypeError, ValueError):
                        self._send_json({'result': 'error', 'reason': 'bad volume'})
                        return
                    ok = set_volume_pct(pct)
                    self._send_json({'result': 'ok' if ok else 'error', 'volume': pct})
                elif path == '/api/speak_here':
                    # govde: {"text": "...", "expr": "happy|love|alert|sad" (istege bagli)}
                    # Telefon vb. uzak istemciler icin: robotun KENDI ekrani bir
                    # sonraki durum sorgusunda konusur, agzi oynar, ifadesi degisir.
                    text = str(d.get('text', '')).strip()
                    if not text:
                        self._send_json({'result': 'error', 'reason': 'text gerekli'})
                        return
                    expr = d.get('expr', '')
                    node_self.request_robot_speech(text, expr if expr in ROBOT_EXPRESSIONS else '')
                    self._send_json({'result': 'ok'})
                elif path.startswith('/api/'):
                    # patrol.py'ye ozel diger komutlar (start_patrol, goto,
                    # rescue_* vb.) - dinleyen yok, zararsiz "ok" - motor/
                    # patrol.py gelince GERCEK davranis kazanacaklar.
                    if d:
                        node_self.command_pub.publish(String(data=json.dumps({'path': path, 'body': d})))
                    self._send_json({'result': 'ok'})
                else:
                    self.send_error(404)

        return Handler

    def destroy_node(self):
        self.launch_mgr.stop()
        self._httpd.shutdown()
        super().destroy_node()


def main():
    rclpy.init()
    node = CafeUiServerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
