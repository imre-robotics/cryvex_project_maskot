#!/usr/bin/env python3
"""
Cryvex Tablet Server Node
- HTTP server sunarak tablet arayüzünü sağlar
- /patrol_command topic'ine komut yayınlar
- /patrol_status topic'ini dinleyerek durumu izler
"""
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import json
import os
import socket
import time
import sys
from ament_index_python.packages import get_package_share_directory


class TabletHandler(BaseHTTPRequestHandler):
    """Web isteklerini karşılayan HTTP handler."""
    ros_node = None  # Class variable, dışarıdan set edilir

    def do_GET(self):
        # Ignore query parameters
        path = self.path.split('?')[0]
        if path == '/' or path == '/index.html':
            self._serve_html('index.html')          # musteri ekrani (robot yuzu)
        elif path == '/api/status':
            n = self.ros_node
            age = (time.time() - n.last_status_time) if n.status_count else -1.0
            self._send_json({
                'status': n.current_status,
                'count': n.status_count,      # kac /patrol_status mesaji alindi
                'age': round(age, 1),         # son mesajin kac sn once geldigi (-1 = hic)
            })
        else:
            self.send_error(404)

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
        self.web_dir = os.path.join(
            get_package_share_directory('cryvex_gazebo'), 'web')
        self.get_logger().info(f'Web dizini: {self.web_dir}')
        self.create_timer(5.0, self._health_check)

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
    import subprocess
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
