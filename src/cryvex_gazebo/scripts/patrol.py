#!/usr/bin/env python3
"""
Cryvex Restaurant Patrol Node
=============================
Kafe garson-robotu davranis beyni. nav2_simple_commander uzerinden calisir.

Durum makinesi:
  idle -> patrol -> waiting_at_table -> (siparis) delivering_order
       -> at_barista -> (resume) patrol ...
  wander     : bos zamanda oda icinde sosyallesir (Wander & Greet senaryosu)
  going_home : barmen/us noktasina doner

Senaryolar:
  * Wander & Greet   : `wander` komutu ile bos alanlarda gezip pazarlama yapar.
  * Kapida Karsilama : `greet_door` -> kapi noktasinda 3 dk "hos geldiniz".
  * Mesaj Tasima     : `msg:<from>|<to>|<text>` -> birinden birine not goturur.
  * Garson Yonlendirme: `goto:<masa>:<welcome|menu|welcome_menu|cute>`.

(Goruntu isleme / "yol isteme" senaryolari kaldirildi.)

Konumlar `worlds/cafe.world` geometrisine gore hesaplanmistir.
"""
import os
import math
import json
import time
import random
import threading

import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter
from rclpy.executors import SingleThreadedExecutor
from rclpy.qos import qos_profile_sensor_data
from nav2_simple_commander.robot_navigator import BasicNavigator, TaskResult
from geometry_msgs.msg import PoseStamped, Twist
from sensor_msgs.msg import Range
from std_msgs.msg import String
from ament_index_python.packages import get_package_share_directory


# --- Masa yaklasim pozlari ---
# Kullanicinin RViz'de tiklattigi noktalar masa/sandalyeye cok yakindi; her nokta
# `worlds/cafe.world` geometrisine gore en yakin masaya ~1.3 m mesafeye, yuzu
# masaya donuk, engellere >=0.6 m bosluk kalacak sekilde kaydirildi.
WAYPOINTS = [
    {"isim": "Masa 1", "x":  6.33, "y":  1.73, "yaw":  1.436},   # table_7 (6.5, 3.0)
    {"isim": "Masa 2", "x":  4.59, "y": -0.10, "yaw": -0.776},   # table_5 (5.5,-1.0)
    {"isim": "Masa 3", "x":  4.62, "y": -3.99, "yaw": -0.855},   # table_2 (5.5,-5.0)
    {"isim": "Masa 4", "x":  0.91, "y": -4.09, "yaw": -2.356},   # table_1 (0.0,-5.0)
    {"isim": "Masa 5", "x": -4.49, "y": -4.12, "yaw": -2.422},   # table_0 (-5.5,-5.0)
    {"isim": "Masa 6", "x": -4.40, "y": -1.87, "yaw":  2.471},   # table_3 (-5.5,-1.0)
    {"isim": "Masa 7", "x": -6.07, "y":  1.79, "yaw":  1.915},   # table_6 (-6.5, 3.0)
    {"isim": "Masa 8", "x": -0.89, "y":  0.00, "yaw": -0.844},   # table_4 (0.0,-1.0)
]

# Barmen / garson noktasi = robotun uslendigi "ev". Siparis buraya goturulur.
BARISTA_POS   = {"isim": "Barmen", "x": -3.43, "y": 4.05, "yaw": 0.40}
HOME_POSITION = {"isim": "Us",     "x": -3.43, "y": 4.05, "yaw": 0.40}

# Kapi karsilama noktasi: her turda bir kez buraya gelip gelenlere "Hos geldiniz" der.
DOOR_POS = {"isim": "Kapi", "x": 0.85, "y": -5.95, "yaw": -1.571}

# Wander & Greet: cafe.world'de dogrulanmis bos koridor noktalari.
WANDER_POINTS = [
    (0.0, -3.0), (2.5, -3.0), (-2.5, -3.0),
    (0.0, 1.0), (2.5, 1.0), (-2.5, 1.0),
    (5.5, -3.0), (-5.5, -3.0),
]

ROOM_CENTER = (0.0, 0.0)
RETRY_OFFSETS = [0.0, 0.35, 0.75]     # hedef reddedilirse oda merkezine dogru kaydir

# --- Ultrasonik kurtulma (takilip kalmayi onler) ---
# 4x HC-SR04 taban kosede; base_link'e gore yaklasik yon aci (rad).
SONAR_YAW = {'fl': 0.30, 'fr': -0.30, 'rl': 2.84, 'rr': -2.84}
ESCAPE_TRIGGER = 0.10        # < 10 cm -> kurtulma manevrasi (fiziksel temas esigi)
SONAR_STALE_SECONDS = 1.0    # bu suredir veri gelmeyen sensoru yok say
STALL_ESCAPE_SECONDS = 15.0  # hedefe 15 sn ilerleme yoksa "kor" kurtulma
MAX_ESCAPES_PER_GOAL = 5

# Masaya/hedefe FAZLA yanasmayi onler: kurtulmadan (fiziksel tehlike, 10 cm) AYRI,
# daha yumusak bir sinir. On sensorlerden biri bu mesafenin altina duserse (ve
# hedefe zaten yaklasilmisken) Nav2 gorevi TEMIZ iptal edilip "vardim" sayilir -
# robot daha fazla ittirmeye/yanasmaya calismaz, takilmaz.
APPROACH_STANDOFF = 0.25     # bu mesafeden sonra yaklasma, yeterli say (25 cm)
APPROACH_GATE_DIST = 1.5     # sadece hedefe bu kadar YAKINKEN gecerli (koridorda degil)

# Masadan AYRILIRKEN: donup gitmeden once duz geri cekil - masaya/sandalyeye
# yakinken hemen donmeye/ilerlemeye calismak surtunmeye/takilmaya sebep oluyordu.
DEPART_BACK_METERS = 1.0
DEPART_BACK_LIN = 0.15                              # m/s
DEPART_BACK_SECONDS = DEPART_BACK_METERS / DEPART_BACK_LIN

# Kurtulma SABIT ADIMLI bir manevra (surekli itme DEGIL - o donguye giriyordu):
#   1) DUR, 2 sn bekle (algiyi dogrula)
#   2) duz GERI (onde engel) veya duz ILERI (arkada engel)
#   3) DON (yakin taraftan uzaga; sol yakinsa saga, sag yakinsa sola)
#   4) az ILERI
#   5) ayni hedefe tekrar dene (robot artik farkli yerde/yonde -> Nav2 yeniden planlar)
ESCAPE_SETTLE_SECONDS = 2.0
ESCAPE_BACK_SECONDS = 1.0
ESCAPE_TURN_SECONDS = 0.9
ESCAPE_FWD_SECONDS = 0.6
ESCAPE_BACK_LIN = 0.12
ESCAPE_TURN_ANG = 0.80
ESCAPE_FWD_LIN = 0.10

# --- Operator ekrani: canli haritalama joystick'i (STATE_TELEOP) ---
# Wifi/arayuz kopukluguna karsi guvenlik: bu suredir taze 'teleop:' komutu
# gelmezse (parmak ekrandan kalkti, baglanti koptu) motor otomatik durur.
TELEOP_WATCHDOG_SECONDS = 0.6
TELEOP_MAX_LIN = 0.30
TELEOP_MAX_ANG = 1.00

TABLE_WAIT_SECONDS = 10.0             # masada siparis icin bekleme
INTERACT_TIMEOUT_SECONDS = 90.0      # menu bu kadar acik kalirsa sayac zorla devam
WANDER_GREET_SECONDS = 4.0           # wander duraginda selamlasma molasi
DOOR_GREET_SECONDS = 180.0          # kapida "hos geldiniz" molasi (3 dakika)
DIRECTED_GREET_SECONDS = 8.0        # garsonun yolladigi masada selam/sevimlilik suresi

# Garsonun secebilecegi hazir mesaj kaliplari (robot bunlari sesli okur).
DIRECTED_MESSAGES = {
    'welcome':      'Hos geldiniz! Cryvex kafeye buyurun, keyifli vakit gecirmenizi dileriz.',
    'menu':         'Menumuze goz atmak icin ekrana dokunabilirsiniz.',
    'welcome_menu': 'Hos geldiniz! Menumuzu gormek icin ekrana dokunun, siparisinizi hemen alalim.',
    'cute':         'Merhabaa! Seni gordugume cok sevindim, hos geldin kucuk dostum!',
}
DIRECTED_ACTIONS = tuple(DIRECTED_MESSAGES.keys())

# --- Mesajlasma (robot postaci) ---
PEOPLE = ['Masa 1', 'Masa 2', 'Masa 3', 'Masa 4', 'Masa 5',
          'Masa 6', 'Masa 7', 'Masa 8', 'Garson']
MSG_OPEN_TIMEOUT = 25.0     # alici dokunmazsa mesaj acilmadan vazgec
MSG_READ_SECONDS = 20.0     # mesaji okuma + "cevap ver"e karar verme suresi
MSG_COMPOSE_TIMEOUT = 45.0  # "cevap ver"e basildi -> yazma icin guvenlik suresi
                            #   (arayuz 30 sn'de kendisi iptal eder; bu yedek)

# --- Durumlar ---
STATE_IDLE = 'idle'
STATE_PATROL = 'patrol'
STATE_WAITING = 'waiting_at_table'
STATE_DELIVERING = 'delivering_order'
STATE_AT_BARISTA = 'at_barista'
STATE_GOING_HOME = 'going_home'
STATE_WANDER = 'wander'
STATE_GREET_DOOR = 'greet_door'      # garson "kapida karsila" dedi -> 3 dk kapida
STATE_DIRECTED = 'directed'          # garson telefondan bir masaya yonlendirdi
STATE_MESSENGER = 'messenger'        # birinden birine mesaj tasiyor
STATE_TELEOP = 'teleop'              # operator ekranindan canli joystick suruşu


class CommandListener(Node):
    """Arayuz komutlarini dinler, durumu /patrol_status (JSON) ile yayinlar."""

    def __init__(self):
        super().__init__('patrol_command_listener')
        self.state = STATE_IDLE
        self.current_waypoint = ''
        self.table_index = 0
        self.order_data = ''
        self.interacting = False
        self.wait_total = TABLE_WAIT_SECONDS
        self.wait_remaining = 0.0
        self.last_pos = None
        self.greeting = False           # kapida/wander/masa'da selamlama molasi
        self.cute = False               # sevimlilik modu (garson 'goto:N:cute')
        self.directed_table = 0         # garsonun yonlendirdigi masa index'i
        self.directed_action = 'menu'   # DIRECTED_ACTIONS'tan biri
        self.relocalize_req = False     # arayuzden "robotu usse sabitle"
        self.screen_on = False          # musteri ekrani acik mi
        self.speak_text = ''            # robotun sesli okuyacagi hazir mesaj
        self.speak_seq = 0              # her yeni mesajda artar (arayuz dedupe icin)
        # mesajlasma
        self.msg_from = ''
        self.msg_to = ''
        self.msg_text = ''
        self.msg_phase = ''             # '' | travel | pending | reading | reply | replying
        self.msg_open_req = False       # alici "ac" icin ekrana dokundu
        self.msg_composing = False      # alici "cevap ver"e basti, yaziyor -> BEKLE
        self.msg_reply_text = None      # cevap metni (None = cevap yok)
        self.msg_total = 0.0
        self.msg_remaining = 0.0
        self.sonar = None              # main()'de SonarReader baglanir
        # operator kurulum ekrani: harita+masalar KAYDEDILENE kadar devriye/goto
        # komutlari reddedilir (yeni haritada anlamsiz eski WAYPOINTS'e gitmesin).
        # Var olan kafede (baslangicta mevcut waypoints.json) True baslar.
        self.map_ready = True
        self.teleop_lx = 0.0            # operator joystick (canli haritalama)
        self.teleop_az = 0.0
        self.teleop_last_t = 0.0
        self.set_pose_req = None        # (x,y,yaw) | None - haritalama sonrasi AMCL'e "buradayim" bilgisi

        self.create_subscription(String, '/patrol_command', self._command_callback, 10)
        self.status_pub = self.create_publisher(String, '/patrol_status', 10)
        # /cmd_vel = robota giden; /cmd_vel_nav = Nav2 velocity_smoother girisi.
        # Ikisine de yayinla ki stack'te smoother olsa da olmasa da kurtulma calissin.
        self.cmd_pub = self.create_publisher(Twist, '/cmd_vel', 10)
        self.cmd_nav_pub = self.create_publisher(Twist, '/cmd_vel_nav', 10)
        # NOT: /patrol_status yayini bir ROS timer'i ile DEGIL, main()'deki
        # duvar-saati (wall-clock) thread'i ile yapilir. Boylece use_sim_time /
        # executor sorunlarindan bagimsiz olarak arayuz her zaman guncellenir.
        self.get_logger().info('Restaurant komut dinleyici baslatildi.')

    # ---- komutlar ----
    def _command_callback(self, msg):
        cmd = msg.data.strip()

        # Siparis tasirken (DELIVERING/AT_BARISTA) garson override'lari yok sayilir.
        busy_with_order = self.state in (STATE_DELIVERING, STATE_AT_BARISTA)

        # Kurulum/haritalama surerken (map_ready=False) devriye/yonlendirme
        # komutlari YOK SAYILIR - operator "Kaydet"e basip yeni noktalari
        # onaylayana kadar robot eski (artik anlamsiz) WAYPOINTS'e gitmeye
        # calismaz. Teleop bu kontrolden MUAF (haritalama tam da bunu kullanir).
        nav_cmd = cmd in ('start', 'wander', 'go_home', 'greet_door') or cmd.startswith('goto:')
        if nav_cmd and not self.map_ready:
            self.get_logger().warn(
                f"KOMUT '{cmd}' reddedildi: kurulum/haritalama surüyor (map_ready=False).")
            return

        if cmd == 'start':
            if busy_with_order:
                self.get_logger().warn("KOMUT: 'start' - once siparis teslim edilmeli.")
            else:
                self.state = STATE_PATROL
                self.greeting = False
                self.cute = False
                self.get_logger().info('KOMUT: Devriye BASLAT')

        elif cmd == 'stop':
            self.state = STATE_IDLE
            self.interacting = False
            self.wait_remaining = 0.0
            self.get_logger().info('KOMUT: DURDUR')

        elif cmd == 'wander':
            if not busy_with_order:
                self.state = STATE_WANDER
                self.greeting = False
                self.get_logger().info('KOMUT: Sosyallesme (Wander) modu')

        elif cmd == 'go_home':
            if not busy_with_order:
                self.state = STATE_GOING_HOME
                self.interacting = False
                self.greeting = False
                self.cute = False
                self.get_logger().info('KOMUT: Use DON')

        elif cmd == 'interacting':
            self.interacting = True
            self.get_logger().info('KOMUT: Musteri menuye bakiyor (sayac donduruldu)')

        elif cmd == 'done_interacting':
            self.interacting = False
            self.get_logger().info('KOMUT: Menu kapandi (sayac devam)')

        elif cmd.startswith('order:'):
            if self.state == STATE_WAITING:
                self.order_data = cmd[len('order:'):]
                self.interacting = False
                self.state = STATE_DELIVERING
                self.get_logger().info('KOMUT: Siparis alindi -> Barmene gidiliyor')
            else:
                self.get_logger().warn(
                    f'Siparis geldi ama durum uygun degil ({self.state}), yok sayildi.')

        elif cmd == 'resume':
            if self.state == STATE_AT_BARISTA:
                self.state = STATE_PATROL
                self.order_data = ''
                self.get_logger().info('KOMUT: Barmen onayladi -> Devriyeye devam')

        elif cmd == 'greet_door':
            if not busy_with_order:
                self.interacting = False
                self.state = STATE_GREET_DOOR
                self.get_logger().info('KOMUT: Kapida karsilama (3 dk)')

        elif cmd == 'relocalize':
            self.relocalize_req = True
            self.get_logger().info('KOMUT: Robotu Us pozuna sabitle (AMCL)')

        elif cmd == 'reload_waypoints':
            # Kurulum ekranindan yeni noktalar kaydedildi -> restart gerekmeden uygula
            cfg = load_or_seed_waypoints_cfg()
            if apply_waypoints_cfg(cfg, logger=self.get_logger()):
                self.get_logger().info('KOMUT: Noktalar (waypoints.json) yeniden yuklendi.')
            else:
                self.get_logger().warn('KOMUT: reload_waypoints basarisiz, eski degerler korundu.')

        elif cmd == 'wake':
            self.screen_on = True
            self.get_logger().info('KOMUT: Robot ekrani ACIK')

        elif cmd == 'sleep':
            self.screen_on = False
            self.get_logger().info('KOMUT: Robot ekrani KAPALI')

        elif cmd.startswith('msg:'):
            # msg:<gonderen>|<alici>|<metin>
            parts = cmd[len('msg:'):].split('|', 2)
            if busy_with_order:
                self.get_logger().warn('KOMUT: msg - once siparis teslim edilmeli.')
            elif len(parts) == 3 and parts[0].strip() in PEOPLE and parts[1].strip() in PEOPLE:
                self.msg_from = parts[0].strip()
                self.msg_to = parts[1].strip()
                self.msg_text = parts[2].strip()
                self.msg_phase = 'travel'
                self.msg_open_req = False
                self.msg_reply_text = None
                self.interacting = False
                self.greeting = False
                self.screen_on = True
                self.state = STATE_MESSENGER
                self.get_logger().info(f'KOMUT: Mesaj {self.msg_from} -> {self.msg_to}')
            else:
                self.get_logger().warn(f'Gecersiz msg komutu: {cmd}')

        elif cmd == 'msg_open':
            self.msg_open_req = True

        elif cmd == 'msg_compose_start':
            self.msg_composing = True      # cevap yaziliyor -> robot bekleyecek

        elif cmd == 'msg_compose_cancel':
            self.msg_composing = False

        elif cmd.startswith('msg_reply:'):
            self.msg_composing = False
            self.msg_reply_text = cmd[len('msg_reply:'):].strip()

        elif cmd.startswith('goto:'):
            # goto:<masa_no>:<eylem>   eylem = welcome | menu | welcome_menu | cute
            parts = cmd.split(':')
            try:
                idx = int(parts[1]) - 1
            except (IndexError, ValueError):
                idx = -1
            action = parts[2] if len(parts) > 2 else 'menu'
            if busy_with_order:
                self.get_logger().warn("KOMUT: goto - once siparis teslim edilmeli.")
            elif 0 <= idx < len(WAYPOINTS) and action in DIRECTED_ACTIONS:
                self.directed_table = idx
                self.directed_action = action
                self.interacting = False
                self.greeting = False
                self.cute = False
                self.screen_on = True     # garson yonlendirince ekran otomatik acilir
                self.state = STATE_DIRECTED
                self.get_logger().info(
                    f'KOMUT: Garson -> {WAYPOINTS[idx]["isim"]} ({action})')
            else:
                self.get_logger().warn(f'Gecersiz goto komutu: {cmd}')

        elif cmd.startswith('teleop:'):
            # teleop:<lx>:<az>  - operator ekrani sanal joystick (canli haritalama)
            if busy_with_order:
                self.get_logger().warn('KOMUT: teleop - siparis tasinirken kabul edilmez.')
            else:
                try:
                    _, lx_s, az_s = cmd.split(':')
                    lx = max(-TELEOP_MAX_LIN, min(TELEOP_MAX_LIN, float(lx_s)))
                    az = max(-TELEOP_MAX_ANG, min(TELEOP_MAX_ANG, float(az_s)))
                except (ValueError, IndexError):
                    lx = az = 0.0
                self.teleop_lx = lx
                self.teleop_az = az
                self.teleop_last_t = time.time()
                if self.state != STATE_TELEOP:
                    self.get_logger().info('KOMUT: Teleop (canli haritalama joystick) basladi')
                self.state = STATE_TELEOP

        elif cmd == 'teleop_stop':
            self.teleop_lx = 0.0
            self.teleop_az = 0.0
            if self.state == STATE_TELEOP:
                self.state = STATE_IDLE
                self.get_logger().info('KOMUT: Teleop durdu')

        elif cmd == 'mapping_start':
            if busy_with_order:
                self.get_logger().warn('KOMUT: mapping_start - once siparis teslim edilmeli.')
            else:
                self.map_ready = False
                self.interacting = False
                self.greeting = False
                self.state = STATE_IDLE
                self.get_logger().warn('KOMUT: Haritalama/kurulum BASLADI - devriye kilitlendi.')

        elif cmd == 'mapping_done':
            self.map_ready = True
            self.get_logger().info('KOMUT: Kurulum TAMAMLANDI - devriye tekrar kullanilabilir.')

        elif cmd.startswith('set_pose:'):
            # set_pose:<x>:<y>:<yaw> - AMCL'e "robot su an TAM OLARAK burada" de.
            # Haritalama bitince OTOMATIK (tablet_server, SLAM'in son TF'inden) veya
            # kurulum ekranindan "Robot Burada" ile MANUEL tetiklenir. map_ready
            # kontrolune TABI DEGIL - bu bir devriye komutu degil, altyapi.
            try:
                _, x_s, y_s, yaw_s = cmd.split(':')
                self.set_pose_req = (float(x_s), float(y_s), float(yaw_s))
                self.get_logger().info(f'KOMUT: AMCL pozu ayarlanacak -> {self.set_pose_req}')
            except (ValueError, IndexError):
                self.get_logger().warn(f'Gecersiz set_pose komutu: {cmd}')

        else:
            self.get_logger().warn(f'Bilinmeyen komut: {cmd}')

    def say(self, text):
        """Robotun (musteri ekrani hoparloru uzerinden) sesli okuyacagi mesaj."""
        self.speak_text = text
        self.speak_seq += 1
        self.get_logger().info(f'ROBOT KONUSUR: {text}')

    def drive_raw(self, twist):
        self.cmd_pub.publish(twist)
        self.cmd_nav_pub.publish(twist)

    def stop_motion(self):
        self.drive_raw(Twist())

    # ---- ultrasonik (SonarReader varsa; yoksa hepsi 'engel yok' doner) ----
    def ultra_blocked(self):
        return self.sonar.ultra_blocked() if self.sonar else False

    def blocked_sides(self):
        return self.sonar.blocked_sides() if self.sonar else (False, False, False, False)

    def closest_range(self):
        """4 sensorun en yakin okumasi (m) - sadece on degil, her yon. Veri yoksa sonsuz."""
        return self.sonar.min_range(SONAR_YAW.keys()) if self.sonar else float('inf')

    def publish_status_now(self):
        status = {
            'state': self.state,
            'waypoint': self.current_waypoint,
            'table_index': self.table_index,
            'wait_total': round(self.wait_total, 1),
            'wait_remaining': round(self.wait_remaining, 1),
            'interacting': self.interacting,
            'greeting': self.greeting,
            'cute': self.cute,
            'screen_on': self.screen_on,
            'speak_text': self.speak_text,
            'speak_seq': self.speak_seq,
            'order': self.order_data,
            'msg_phase': self.msg_phase,
            'msg_from': self.msg_from,
            'msg_to': self.msg_to,
            'msg_text': self.msg_text,
            'msg_total': round(self.msg_total, 1),
            'msg_remaining': round(self.msg_remaining, 1),
            'msg_composing': self.msg_composing,
            'map_ready': self.map_ready,
        }
        msg = String()
        msg.data = json.dumps(status)
        self.status_pub.publish(msg)


class SonarReader(Node):
    """4x HC-SR04'u AYRI bir node + executor'da dinler. Burada bir sorun olsa
    bile (deserialize hatasi vb.) patrol beyni etkilenmez."""

    def __init__(self):
        super().__init__('sonar_reader')
        self.ranges = {k: float('inf') for k in SONAR_YAW}
        self.range_t = {k: 0.0 for k in SONAR_YAW}
        for k in SONAR_YAW:
            self.create_subscription(
                Range, f'/ultrasonic/{k}',
                lambda m, key=k: self._cb(key, m),
                qos_profile_sensor_data)          # sensor verisi = BEST_EFFORT

    def _cb(self, key, msg):
        try:
            self.ranges[key] = float(msg.range)
            self.range_t[key] = time.time()
        except Exception:  # noqa: BLE001
            pass

    def _fresh(self):
        now = time.time()
        return {k: r for k, r in self.ranges.items()
                if now - self.range_t[k] < SONAR_STALE_SECONDS and 0.0 < r < 100.0}

    def ultra_blocked(self):
        return any(r < ESCAPE_TRIGGER for r in self._fresh().values())

    def min_range(self, keys):
        vals = [r for k, r in self._fresh().items() if k in keys]
        return min(vals) if vals else float('inf')

    def blocked_sides(self):
        """Hangi taraf(lar) < ESCAPE_TRIGGER? -> (on, arka, sol, sag) bool'lari."""
        trig = {k for k, r in self._fresh().items() if r < ESCAPE_TRIGGER}
        front = bool(trig & {'fl', 'fr'})
        rear = bool(trig & {'rl', 'rr'})
        left = bool(trig & {'fl', 'rl'})
        right = bool(trig & {'fr', 'rr'})
        return front, rear, left, right


# ==================== yardimcilar ====================
def person_location(name):
    """Mesajlasmada kisi adini bir hedef poza cevirir."""
    if name == 'Garson':
        return dict(BARISTA_POS, isim='Garson')
    for wp in WAYPOINTS:
        if wp['isim'] == name:
            return wp
    return None


# ==================== masa/kapi/barmen noktalari (kurulum ekranindan) ====================
# web/setup.html haritaya tiklayarak nokta toplar, tablet_server.py bunu
# config/waypoints.json'a yazar, biz burada okuyup WAYPOINTS/BARISTA_POS/
# HOME_POSITION/DOOR_POS'u YERINDE guncelleriz (restart gerekmez, 'reload_waypoints'
# komutuyla veya acilista otomatik).
def _waypoints_config_path():
    """config/waypoints.json konumu. --symlink-install ile calisiyoruz: bu
    betigin GERCEK (symlink cozulmus) yeri src/cryvex_gazebo/scripts/patrol.py'dir.
    Oradan kaynak agacindaki config/'u bulup KAYNAGA yaziyoruz - yoksa dosya
    install/ icine dusup bir sonraki `colcon build`'da kaybolur / tablet_server
    ile farkli yerlere yazip okumaya baslarlar."""
    real_script = os.path.realpath(os.path.abspath(__file__))
    src_config_dir = os.path.join(os.path.dirname(os.path.dirname(real_script)), 'config')
    if os.path.isfile(os.path.join(src_config_dir, 'nav2_params.yaml')):
        return os.path.join(src_config_dir, 'waypoints.json')  # symlink-install: kaynak agaci
    try:
        share_config_dir = os.path.join(get_package_share_directory('cryvex_gazebo'), 'config')
    except Exception:  # noqa: BLE001
        share_config_dir = src_config_dir
    return os.path.join(share_config_dir, 'waypoints.json')


def _default_waypoints_cfg():
    """Su anki sabit degerlerden bir konfigurasyon uretir (ilk kurulum tohumu)."""
    return {
        'barista': {'isim': 'Barmen', 'x': BARISTA_POS['x'], 'y': BARISTA_POS['y'],
                    'yaw': BARISTA_POS['yaw']},
        'door': {'isim': 'Kapi', 'x': DOOR_POS['x'], 'y': DOOR_POS['y'], 'yaw': DOOR_POS['yaw']},
        'tables': [{'isim': wp['isim'], 'x': wp['x'], 'y': wp['y'], 'yaw': wp['yaw']}
                   for wp in WAYPOINTS],
    }


def load_or_seed_waypoints_cfg():
    """config/waypoints.json varsa okur; yoksa mevcut sabit degerlerden bir tane
    yazar (kurulum ekrani ilk acildiginda bos degil, mevcut duzeni gorur)."""
    path = _waypoints_config_path()
    if os.path.exists(path):
        try:
            with open(path, encoding='utf-8') as f:
                return json.load(f)
        except Exception as exc:  # noqa: BLE001
            print(f'[UYARI] waypoints.json okunamadi ({exc}), varsayilanlar kullanilacak.')
            return None
    cfg = _default_waypoints_cfg()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        print(f'[BILGI] Ilk waypoints.json olusturuldu: {path}')
    except Exception as exc:  # noqa: BLE001
        print(f'[UYARI] waypoints.json yazilamadi ({exc}).')
    return cfg


def apply_waypoints_cfg(cfg, logger=None):
    """cfg -> WAYPOINTS / BARISTA_POS / HOME_POSITION / DOOR_POS (yerinde degistirir,
    boylece calisan patrol dongusu de aninda yeni degerleri gorur)."""
    def log(msg):
        logger.info(msg) if logger else print(msg)

    if not cfg:
        log('[UYARI] Gecersiz waypoints konfigurasyonu, degisiklik yapilmadi.')
        return False
    try:
        new_tables = []
        for i, t in enumerate(cfg.get('tables') or []):
            new_tables.append({
                'isim': str(t.get('isim') or f'Masa {i + 1}'),
                'x': float(t['x']), 'y': float(t['y']), 'yaw': float(t.get('yaw', 0.0)),
            })
        if new_tables:
            WAYPOINTS[:] = new_tables
        else:
            log('[UYARI] Konfigurasyonda masa yok, mevcut masalar korundu.')

        b = cfg.get('barista')
        if b:
            BARISTA_POS.clear()
            BARISTA_POS.update({'isim': b.get('isim') or 'Barmen', 'x': float(b['x']),
                                 'y': float(b['y']), 'yaw': float(b.get('yaw', 0.0))})
            HOME_POSITION.clear()
            HOME_POSITION.update({'isim': 'Us', 'x': BARISTA_POS['x'],
                                   'y': BARISTA_POS['y'], 'yaw': BARISTA_POS['yaw']})

        d = cfg.get('door')
        if d:
            DOOR_POS.clear()
            DOOR_POS.update({'isim': d.get('isim') or 'Kapi', 'x': float(d['x']),
                              'y': float(d['y']), 'yaw': float(d.get('yaw', 0.0))})

        log(f'[BILGI] Noktalar yuklendi: {len(WAYPOINTS)} masa, '
            f'barmen/us=({BARISTA_POS["x"]:.2f},{BARISTA_POS["y"]:.2f}), '
            f'kapi=({DOOR_POS["x"]:.2f},{DOOR_POS["y"]:.2f})')
        return True
    except Exception as exc:  # noqa: BLE001
        log(f'[HATA] waypoints uygulanamadi: {exc}')
        return False


def yaw_to_quaternion(yaw):
    return math.sin(yaw / 2.0), math.cos(yaw / 2.0)


def make_pose(navigator, x, y, yaw=0.0, frame_id='map'):
    pose = PoseStamped()
    pose.header.frame_id = frame_id
    pose.header.stamp = navigator.get_clock().now().to_msg()
    pose.pose.position.x = float(x)
    pose.pose.position.y = float(y)
    z, w = yaw_to_quaternion(yaw)
    pose.pose.orientation.z = z
    pose.pose.orientation.w = w
    return pose


def _nudge_to_center(x, y, dist):
    if dist <= 0.0:
        return x, y
    dx, dy = ROOM_CENTER[0] - x, ROOM_CENTER[1] - y
    n = math.hypot(dx, dy) or 1.0
    return x + dx / n * dist, y + dy / n * dist


def _escape_maneuver(listener, reason, expected_state):
    """Nav2 gorevi IPTAL edildikten sonra cagrilir. SABIT ADIMLI manevra:
    dur+bekle -> duz geri/ileri -> don -> az ileri -> hedefe tekrar dene.
    Surekli "it/yakinlas" dongusu YERINE tek seferlik, kesin bir hareket -
    boylece robot ayni noktaya/yone geri donup tekrar tekrar sikismiyor."""
    log = listener.get_logger()

    def _still_active():
        return listener.state == expected_state

    def _phase(vx, wz, seconds, label):
        log.info(f'  kurtulma adimi: {label} ({seconds:.1f} sn, vx={vx:.2f} wz={wz:.2f})')
        t0 = time.time()
        while time.time() - t0 < seconds:
            if not _still_active():
                return False
            tw = Twist()
            tw.linear.x = vx
            tw.angular.z = wz
            listener.drive_raw(tw)
            time.sleep(0.1)
        return True

    log.warn(f'KURTULMA MANEVRASI baslıyor ({reason})...')

    # 1) DUR ve ESCAPE_SETTLE_SECONDS bekle (aninda tepki yerine algiyi dogrula)
    listener.stop_motion()
    t0 = time.time()
    while time.time() - t0 < ESCAPE_SETTLE_SECONDS:
        if not _still_active():
            return
        time.sleep(0.1)

    # Hangi taraf tetiklendi? -> yon kararlari
    front, rear, left, right = listener.blocked_sides() if reason == 'ultra' else (False,) * 4

    # On yakinsa GERI, SADECE arka yakinsa ILERI git.
    back_vx = ESCAPE_BACK_LIN if (rear and not front) else -ESCAPE_BACK_LIN
    # Sol yakinsa SAGA don (REP-103: -wz = saga/CW), sag yakinsa SOLA; bilinmezse varsayilan SAG.
    turn_wz = ESCAPE_TURN_ANG if (right and not left) else -ESCAPE_TURN_ANG

    if not _phase(back_vx, 0.0, ESCAPE_BACK_SECONDS, 'duz geri' if back_vx < 0 else 'duz ileri'):
        listener.stop_motion(); return
    if not _phase(0.0, turn_wz, ESCAPE_TURN_SECONDS, 'saga don' if turn_wz < 0 else 'sola don'):
        listener.stop_motion(); return
    _phase(ESCAPE_FWD_LIN, 0.0, ESCAPE_FWD_SECONDS, 'az ileri')

    listener.stop_motion()
    time.sleep(0.3)
    log.info('KURTULMA tamam -> hedefe tekrar deneniyor.')


def _depart_maneuver(listener, expected_state):
    """Masadan ayrilirken donup gitmeden once ~1 m DUZ geri cekilir. Boylece
    Nav2 donusu/sonraki hedefe gidisi masaya/sandalyeye cok yakinken degil,
    acik alanda yapar. Arkada bir sey algilanirsa (10 cm) erken durur."""
    log = listener.get_logger()
    log.info(f'[AYRILIS] {listener.current_waypoint} -> {DEPART_BACK_METERS:.0f} m geri cekiliniyor...')
    t0 = time.time()
    while time.time() - t0 < DEPART_BACK_SECONDS:
        if listener.state != expected_state:
            break
        if listener.ultra_blocked():
            log.warn('[AYRILIS] Arkada engel algilandi, geri cekilme erken kesildi.')
            break
        tw = Twist()
        tw.linear.x = -DEPART_BACK_LIN
        listener.drive_raw(tw)
        time.sleep(0.1)
    listener.stop_motion()
    time.sleep(0.3)
    log.info('[AYRILIS] Tamam -> sonraki konuma donuluyor.')


def drive(navigator, listener, target, expected_state):
    """target -> hedefe git. Durum expected_state disina cikarsa iptal.

    - Hedef reddedilirse oda merkezine dogru kademeli kaydirip tekrar dener.
    - Hedefe yaklasilmisken on sensor < APPROACH_STANDOFF (25 cm) okursa: fazla
      yanasmaya calismadan gorevi TEMIZ bitirip basarili sayar (masaya/insana
      cok yaklasip takilmayi onler).
    - Ultrasonik < 10 cm (fiziksel temas) veya 15 sn ilerleme yok -> kurtulma
      manevrasi + ayni hedefe tekrar dene.
    Donus: True basarili / False kesildi veya basarisiz.
    """
    log = listener.get_logger()

    if not navigator.nav_to_pose_client.wait_for_server(timeout_sec=5.0):
        log.error(
            "NAV2 YOK: 'navigate_to_pose' sunucusu bulunamadi. "
            "'ros2 launch cryvex_gazebo navigation.launch.py' calisiyor mu?")
        for _ in range(6):
            if listener.state != expected_state:
                return False
            time.sleep(0.5)
        return False

    tx, ty = float(target['x']), float(target['y'])
    yaw = target.get('yaw')
    if yaw is None:
        prev = listener.last_pos if listener.last_pos else HOME_POSITION
        yaw = math.atan2(ty - prev['y'], tx - prev['x'])
    listener.current_waypoint = target['isim']

    oi = 0                 # offset index (sadece gercek nav hatasinda artar)
    escapes = 0
    while oi < len(RETRY_OFFSETS):
        off = RETRY_OFFSETS[oi]
        gx, gy = _nudge_to_center(tx, ty, off)
        tag = target['isim'] + ('' if off == 0.0 else f' (+{off:.2f}m ic)')
        log.info(f"Hedef gonderiliyor -> {tag}  x={gx:.2f} y={gy:.2f}")

        accepted = navigator.goToPose(make_pose(navigator, gx, gy, yaw))
        if accepted is False:
            log.warn(f"{tag}: hedef REDDEDILDI. Kaydirip deniyorum.")
            oi += 1
            if listener.state != expected_state:
                return False
            continue

        escape_reason = None
        best_dist = None
        last_progress = time.time()
        last_fb_log = 0.0
        while not navigator.isTaskComplete():
            if listener.state != expected_state:
                navigator.cancelTask()
                listener.last_pos = target
                return False

            fb = navigator.getFeedback()
            dist_left = None
            now = time.time()
            if fb is not None:
                try:
                    dist_left = float(fb.distance_remaining)
                except Exception:  # noqa: BLE001
                    dist_left = None
                if dist_left is not None and (best_dist is None or dist_left < best_dist - 0.10):
                    best_dist = dist_left
                    last_progress = now
                if dist_left is not None and now - last_fb_log > 4.0:
                    last_fb_log = now
                    log.info(f"  ...{tag} yolunda, kalan ~{dist_left:.2f} m")

            # Hedefe zaten YAKINKEN herhangi bir sensor cok yakin okursa fazla
            # yanasmaya calisma - "yeterince yaklasildi" say ve orada dur.
            near_r = listener.closest_range()
            if (dist_left is not None and dist_left < APPROACH_GATE_DIST
                    and near_r < APPROACH_STANDOFF):
                log.info(f"{tag}: sensor {near_r*100:.0f} cm -> "
                         f"yeterince yaklasildi, fazla yanasilmiyor.")
                navigator.cancelTask()
                listener.stop_motion()
                listener.last_pos = target
                return True

            if listener.ultra_blocked():                 # < 10 cm fiziksel engel
                escape_reason = 'ultra'
                break

            if now - last_progress > STALL_ESCAPE_SECONDS:  # 15 sn takildi kaldi
                escape_reason = 'stall'
                break
            time.sleep(0.2)

        if escape_reason:
            navigator.cancelTask()
            escapes += 1
            _escape_maneuver(listener, escape_reason, expected_state)
            listener.last_pos = target
            if listener.state != expected_state:
                return False
            if escapes >= MAX_ESCAPES_PER_GOAL:
                log.error(f"{target['isim']}: {escapes} kurtulma denemesi yetmedi, "
                          "adim atlaniyor -> devriyeye devam.")
                return False
            continue                                     # ayni offset, tekrar dene

        listener.last_pos = target
        if listener.state != expected_state:
            return False

        result = navigator.getResult()
        if result == TaskResult.SUCCEEDED:
            log.info(f"{tag}: ULASILDI.")
            return True
        log.warn(f"{tag}: Nav2 sonucu {result}, kaydirip deniyorum.")
        oi += 1
        if listener.state != expected_state:
            return False

    log.error(f"{target['isim']}: tum denemeler basarisiz, sonraki adima geciliyor.")
    return False


# ==================== ana dongu ====================
def main():
    rclpy.init()

    # Kurulum ekranindan (web/setup.html) kaydedilmis noktalar varsa yukle;
    # yoksa asagidaki sabit degerlerden ilk waypoints.json'u olustur.
    _cfg = load_or_seed_waypoints_cfg()
    apply_waypoints_cfg(_cfg)

    listener = CommandListener()
    executor = SingleThreadedExecutor()
    executor.add_node(listener)

    def _resilient_spin(exc, node, label, give_up_after=0):
        """Take/deserialize hatasi spin'i OLDURMESIN. give_up_after > 0 ise, o kadar
        art arda hatadan sonra bu executor'i komple birak (opsiyonel ozellik icin)."""
        fails = 0
        warned = False
        while rclpy.ok():
            try:
                exc.spin_once(timeout_sec=0.2)
                fails = 0
            except Exception as e:  # noqa: BLE001
                fails += 1
                if not warned:
                    warned = True
                    node.get_logger().warn(f'{label}: abonelik hatasi ({e}) - yok sayiliyor.')
                if give_up_after and fails >= give_up_after:
                    node.get_logger().warn(
                        f'{label}: surekli hata -> BU OZELLIK DEVRE DISI. '
                        '(patrol normal calismaya devam eder)')
                    return
                time.sleep(0.05)
    threading.Thread(target=_resilient_spin, args=(executor, listener, 'patrol'),
                     daemon=True).start()

    # Ultrasonik: AYRI node + AYRI executor. Sorun cikarsa patrol etkilenmez;
    # surekli hata verirse bu is parcacigi kendini kapatir (sonar'siz devam).
    sonar = SonarReader()
    sonar_exec = SingleThreadedExecutor()
    sonar_exec.add_node(sonar)
    threading.Thread(target=_resilient_spin,
                     args=(sonar_exec, sonar, 'sonar', 30), daemon=True).start()
    listener.sonar = sonar

    # --- Yinelenen node kontrolu (UYARIR, cikmaz) ---
    # Genelde diger 'patrol_node' onceki calismadan kalma OLU bir orphan'dir
    # (executor'i cokmus, hedef gondermiyor). O yuzden bu SAGLIKLI kopya devam
    # eder; sadece kullaniciyi uyaririz. Kesin cozum: eski process'i oldur.
    def _dup_check():
        my_name = listener.get_name()
        warned = False
        while rclpy.ok():
            twins = [n for n in listener.get_node_names() if n == my_name]
            if len(twins) > 1 and not warned:
                warned = True
                listener.get_logger().warn(
                    f"\n{'='*58}\n"
                    f"  UYARI: {len(twins)} adet '{my_name}' graf'ta gorunuyor.\n"
                    f"  Muhtemelen eski calismadan kalma OLU bir process. Bu\n"
                    f"  kopya calismaya devam ediyor. Emin olmak icin:\n"
                    f"     ps -eo pid,cmd | grep patrol.py | grep -v grep\n"
                    f"     kill -9 <ESKI PID>       (bu process haric)\n"
                    f"  Cift makinede/domain'de ise:  export ROS_DOMAIN_ID=7\n"
                    f"{'='*58}")
            elif len(twins) <= 1:
                warned = False
            time.sleep(5.0)
    threading.Thread(target=_dup_check, daemon=True).start()

    # /patrol_status'u duvar saatiyle sabit ~4 Hz yayinla (executor/sim-time'dan bagimsiz)
    def _status_loop():
        while rclpy.ok():
            try:
                listener.publish_status_now()
            except Exception:  # noqa: BLE001
                pass
            time.sleep(0.25)
    threading.Thread(target=_status_loop, daemon=True).start()
    listener.get_logger().info('/patrol_status yayini basladi (wall-clock, 4 Hz).')

    navigator = BasicNavigator()
    try:
        navigator.set_parameters([Parameter('use_sim_time', Parameter.Type.BOOL, True)])
    except Exception as exc:  # noqa: BLE001
        listener.get_logger().warn(f'use_sim_time ayarlanamadi: {exc}')

    # Baslangic pozu = Us noktasi. AMCL geç aktiflesirse /initialpose'u kacirabilir,
    # bu yuzden ~18 sn boyunca tekrar tekrar yayinla. Ayrica arayuzdeki
    # "Robotu Us'e sabitle" (relocalize) komutu da bunu tekrar tetikler.
    def set_home_pose():
        navigator.setInitialPose(
            make_pose(navigator, HOME_POSITION['x'], HOME_POSITION['y'], HOME_POSITION['yaw']))

    def _init_pose_loop():
        listener.get_logger().info('Baslangic pozu yayinlaniyor (Us)...')
        for _ in range(12):
            if not rclpy.ok():
                return
            set_home_pose()
            time.sleep(1.5)
        listener.get_logger().info('Baslangic pozu yayini tamam.')

    threading.Thread(target=_init_pose_loop, daemon=True).start()

    def _relocalize_loop():
        while rclpy.ok():
            if listener.relocalize_req:
                listener.relocalize_req = False
                for _ in range(4):
                    set_home_pose()
                    time.sleep(0.4)
                listener.get_logger().info('AMCL pozu Us noktasina sabitlendi.')
            if listener.set_pose_req is not None:
                x, y, yaw = listener.set_pose_req
                listener.set_pose_req = None
                # Nav2/AMCL yeni haritalamadan sonra taze basladiysa lifecycle
                # aktivasyonu birkac sn surebilir - o yuzden set_home_pose'dan
                # (18 sn) daha uzun ve sabirli tekrar ediyoruz.
                for _ in range(10):
                    navigator.setInitialPose(make_pose(navigator, x, y, yaw))
                    time.sleep(1.0)
                listener.get_logger().info(
                    f'AMCL pozu haritalama sonrasi ({x:.2f}, {y:.2f}, yaw={yaw:.2f}) olarak ayarlandi.')
            time.sleep(0.2)
    threading.Thread(target=_relocalize_loop, daemon=True).start()

    listener.get_logger().info('Nav2 action sunucusu bekleniyor (en fazla 20 sn)...')
    try:
        if navigator.nav_to_pose_client.wait_for_server(timeout_sec=20.0):
            listener.get_logger().info('Nav2 hazir.')
        else:
            listener.get_logger().warn(
                'Nav2 sunucusu 20 sn icinde gelmedi. Node calisiyor; acilinca baglanacak.')
    except Exception as exc:  # noqa: BLE001
        listener.get_logger().warn(f'Nav2 sunucu kontrolu atlandi: {exc}')

    listener.get_logger().info(
        '==================================================\n'
        '  PATROL HAZIR.\n'
        '   Musteri ekrani : http://<ip>:8080/\n'
        '   Garson paneli  : http://<ip>:8080/garson\n'
        '   Komutlar: start / stop / go_home / wander / greet_door /\n'
        '             goto:<masa>:<menu|welcome|cute> / relocalize\n'
        '==================================================')

    wp_index = 0
    wander_prev = None

    while rclpy.ok():
        state = listener.state

        # Robot bir is yapiyorsa musteri ekrani otomatik acilsin
        if state != STATE_IDLE:
            listener.screen_on = True
        if state != STATE_MESSENGER and listener.msg_phase:
            listener.msg_phase = ''
            listener.msg_remaining = 0.0
            listener.msg_composing = False

        # ---------------- DEVRIYE (sadece masalar; kapi karsilamasi AYRI komut) ----------------
        if state == STATE_PATROL:
            if not WAYPOINTS:   # kurulum hicbir masa kaydetmeden bir sekilde buraya dusulduyse
                listener.get_logger().error('WAYPOINTS bos - devriye bekletiliyor.')
                listener.state = STATE_IDLE
                continue
            wp_index %= len(WAYPOINTS)
            wp = WAYPOINTS[wp_index]
            listener.table_index = wp_index
            listener.get_logger().info(f'--> {wp["isim"]} hedefine gidiliyor...')
            reached = drive(navigator, listener, wp, STATE_PATROL)
            if listener.state != STATE_PATROL:
                continue
            if reached:
                listener.get_logger().info(f'{wp["isim"]} ulasildi.')
            else:
                listener.get_logger().warn(f'{wp["isim"]} ulasilamadi, yine de siparis bekleniyor.')
            listener.state = STATE_WAITING

        # ---------------- MASADA BEKLEME ----------------
        elif state == STATE_WAITING:
            listener.wait_total = TABLE_WAIT_SECONDS
            listener.wait_remaining = TABLE_WAIT_SECONDS
            listener.interacting = False
            interact_elapsed = 0.0
            listener.get_logger().info(
                f'[{listener.current_waypoint}] Siparis bekleniyor ({TABLE_WAIT_SECONDS:.0f}s)...')

            while listener.state == STATE_WAITING:
                time.sleep(0.5)
                if listener.interacting:
                    interact_elapsed += 0.5
                    if interact_elapsed >= INTERACT_TIMEOUT_SECONDS:
                        listener.get_logger().warn('Menu cok uzun acik kaldi, sayac devam.')
                        listener.interacting = False
                        interact_elapsed = 0.0
                    continue
                interact_elapsed = 0.0
                listener.wait_remaining = max(0.0, listener.wait_remaining - 0.5)
                if listener.wait_remaining <= 0.0:
                    listener.get_logger().info(
                        f'[{listener.current_waypoint}] Siparis yok, masadan ayriliniyor.')
                    _depart_maneuver(listener, STATE_WAITING)  # once 1 m duz geri
                    if listener.state == STATE_WAITING:        # arada komut gelmediyse
                        wp_index += 1
                        listener.state = STATE_PATROL
                    break

        # ---------------- SIPARISI BARMENE GOTUR ----------------
        elif state == STATE_DELIVERING:
            listener.wait_remaining = 0.0
            listener.interacting = False
            listener.get_logger().info('[SIPARIS] Barmene gidiliyor...')
            reached = drive(navigator, listener, BARISTA_POS, STATE_DELIVERING)
            if listener.state != STATE_DELIVERING:
                continue
            if reached:
                listener.get_logger().info('Barmene ulasildi. Onay bekleniyor...')
            else:
                listener.get_logger().warn('Barmene ulasilamadi, yine de onay bekleniyor.')
            listener.state = STATE_AT_BARISTA

        # ---------------- BARMENDE BEKLE (sadece resume ile cikar) ----------------
        elif state == STATE_AT_BARISTA:
            time.sleep(0.3)
            if listener.state == STATE_PATROL:
                wp_index += 1

        # ---------------- WANDER & GREET ----------------
        elif state == STATE_WANDER:
            choices = [p for p in WANDER_POINTS if p != wander_prev] or WANDER_POINTS
            px, py = random.choice(choices)
            wander_prev = (px, py)
            tgt = {"isim": "Sosyallesme", "x": px, "y": py}
            listener.get_logger().info(f'[WANDER] ({px:.1f}, {py:.1f}) noktasina gidiliyor...')
            drive(navigator, listener, tgt, STATE_WANDER)
            if listener.state != STATE_WANDER:
                continue
            # Selamlasma molasi (arayuz burada pazarlama anonsu yapar)
            listener.current_waypoint = 'Sosyallesme'
            listener.greeting = True
            t = 0.0
            while listener.state == STATE_WANDER and t < WANDER_GREET_SECONDS:
                time.sleep(0.5)
                t += 0.5
            listener.greeting = False

        # ---------------- KAPIDA KARSILAMA (garson komutu, 3 dk) ----------------
        elif state == STATE_GREET_DOOR:
            listener.get_logger().info('--> Kapiya gidiliyor (karsilama)...')
            drive(navigator, listener, DOOR_POS, STATE_GREET_DOOR)
            if listener.state != STATE_GREET_DOOR:
                continue
            listener.current_waypoint = 'Kapi'
            listener.greeting = True
            listener.get_logger().info(f'Kapida "Hos geldiniz" ({DOOR_GREET_SECONDS/60:.0f} dk)...')
            t = 0.0
            while listener.state == STATE_GREET_DOOR and t < DOOR_GREET_SECONDS:
                time.sleep(0.5)
                t += 0.5
            listener.greeting = False
            if listener.state == STATE_GREET_DOOR:      # sure doldu -> use don
                listener.get_logger().info('Karsilama bitti -> Use donuluyor.')
                listener.state = STATE_GOING_HOME

        # ---------------- GARSONUN YONLENDIRDIGI MASA ----------------
        elif state == STATE_DIRECTED:
            idx = listener.directed_table
            action = listener.directed_action
            wp = WAYPOINTS[idx]
            listener.table_index = idx
            listener.get_logger().info(f'--> Garson: {wp["isim"]} ({action}) hedefine gidiliyor...')
            drive(navigator, listener, wp, STATE_DIRECTED)
            if listener.state != STATE_DIRECTED:
                continue
            listener.current_waypoint = wp['isim']

            # Garsonun sectigi hazir mesaji robot sesli okur
            listener.say(DIRECTED_MESSAGES.get(action, DIRECTED_MESSAGES['menu']))

            if action in ('menu', 'welcome_menu'):
                # 10 sn menu sureci; dolarsa normal devriyeye devam et
                wp_index = idx
                listener.state = STATE_WAITING
            elif action == 'welcome':
                listener.greeting = True
                t = 0.0
                while listener.state == STATE_DIRECTED and t < DIRECTED_GREET_SECONDS:
                    time.sleep(0.5)
                    t += 0.5
                listener.greeting = False
                if listener.state == STATE_DIRECTED:
                    listener.state = STATE_IDLE
            elif action == 'cute':
                listener.cute = True
                t = 0.0
                while listener.state == STATE_DIRECTED and t < DIRECTED_GREET_SECONDS:
                    time.sleep(0.5)
                    t += 0.5
                listener.cute = False
                if listener.state == STATE_DIRECTED:
                    listener.state = STATE_IDLE

        # ---------------- MESAJ TASIMA (robot postaci) ----------------
        elif state == STATE_MESSENGER:
            target = person_location(listener.msg_to)
            if target is None:
                listener.get_logger().warn(f'Bilinmeyen alici: {listener.msg_to}')
                listener.msg_phase = ''
                listener.state = STATE_PATROL
                continue

            # 1) Aliciya git
            listener.msg_phase = 'travel'
            listener.get_logger().info(f'[MESAJ] {listener.msg_to} noktasina goturuluyor...')
            drive(navigator, listener, target, STATE_MESSENGER)
            if listener.state != STATE_MESSENGER:
                continue
            listener.current_waypoint = listener.msg_to

            # 2) "Acmak icin dokun" - alici dokununcaya kadar bekle
            #    (SESLI OKUMA YOK - mesaj sadece ekranda gosterilir)
            listener.msg_phase = 'pending'
            listener.msg_open_req = False
            t = 0.0
            while (listener.state == STATE_MESSENGER and not listener.msg_open_req
                   and t < MSG_OPEN_TIMEOUT):
                time.sleep(0.5)
                t += 0.5
            if listener.state != STATE_MESSENGER:
                continue
            if not listener.msg_open_req:
                listener.get_logger().info('[MESAJ] Acilmadi -> devriyeye donuluyor.')
                listener.msg_phase = ''
                listener.state = STATE_PATROL
                continue

            # 3) Okuma + cevap penceresi (15 sn). Mesaj ve "Cevap Ver" butonu
            #    bu 15 sn boyunca ekrandadir. Butona basilirsa (msg_composing)
            #    geri sayim DONAR ve kullanici yazmayi bitirene kadar beklenir.
            #    (Ayri 5 sn'lik pencere kaldirildi - cok kisaydi, robot kaciyordu.)
            listener.msg_phase = 'reading'
            listener.msg_reply_text = None
            listener.msg_composing = False
            listener.msg_total = MSG_READ_SECONDS
            listener.msg_remaining = MSG_READ_SECONDS
            compose_wait = 0.0
            while (listener.state == STATE_MESSENGER
                   and listener.msg_reply_text is None):
                time.sleep(0.5)
                if listener.msg_composing:
                    listener.msg_phase = 'replying'
                    compose_wait += 0.5
                    if compose_wait >= MSG_COMPOSE_TIMEOUT:
                        listener.get_logger().info('[MESAJ] Cevap yazma zaman asimi.')
                        break
                    continue
                listener.msg_phase = 'reading'
                listener.msg_remaining = max(0.0, listener.msg_remaining - 0.5)
                if listener.msg_remaining <= 0.0:
                    # Kisa lutuf suresi: "Cevap Ver"e yeni basildiysa komut ag
                    # gecikmesiyle henuz gelmemis olabilir; 3 sn daha bekle.
                    grace = 0.0
                    while (listener.state == STATE_MESSENGER and grace < 3.0
                           and not listener.msg_composing
                           and listener.msg_reply_text is None):
                        time.sleep(0.2)
                        grace += 0.2
                    if not listener.msg_composing and listener.msg_reply_text is None:
                        break
            if listener.state != STATE_MESSENGER:
                continue

            if listener.msg_reply_text:
                # Cevabi ters yone (alici -> gonderen) tasi, dongu tekrar eder
                listener.msg_from, listener.msg_to = listener.msg_to, listener.msg_from
                listener.msg_text = listener.msg_reply_text
                listener.msg_reply_text = None
                listener.msg_open_req = False
                listener.get_logger().info(f'[MESAJ] Cevap -> {listener.msg_to}')
            else:
                listener.get_logger().info('[MESAJ] Cevap yok -> devriyeye donuluyor.')
                listener.msg_phase = ''
                listener.msg_remaining = 0.0
                listener.state = STATE_PATROL

        # ---------------- TELEOP (operator canli haritalama joystick'i) ----------------
        elif state == STATE_TELEOP:
            if time.time() - listener.teleop_last_t > TELEOP_WATCHDOG_SECONDS:
                # Taze komut yok (parmak kalkti / baglanti koptu) -> guvenlik durusu.
                listener.stop_motion()
                time.sleep(0.05)
                continue
            lx, az = listener.teleop_lx, listener.teleop_az
            front, rear, _left, _right = listener.blocked_sides()
            if lx > 0.0 and front:      # 10 cm altinda engele dogru ilerlemeyi engelle
                lx = 0.0
            if lx < 0.0 and rear:
                lx = 0.0
            tw = Twist()
            tw.linear.x = lx
            tw.angular.z = az
            listener.drive_raw(tw)
            time.sleep(0.05)

        # ---------------- USE DON ----------------
        elif state == STATE_GOING_HOME:
            listener.get_logger().info('[US] Barmen noktasina donuluyor...')
            drive(navigator, listener, HOME_POSITION, STATE_GOING_HOME)
            if listener.state != STATE_GOING_HOME:
                continue
            listener.current_waypoint = ''
            listener.state = STATE_IDLE

        # ---------------- BOSTA ----------------
        else:
            listener.wait_remaining = 0.0
            time.sleep(0.3)

    rclpy.shutdown()


if __name__ == '__main__':
    main()
