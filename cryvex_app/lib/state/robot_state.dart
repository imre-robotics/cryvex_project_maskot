import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../api/robot_api.dart';

/// Uygulama genelinde paylaşılan bağlantı + robot durumu. index.html'deki
/// pollStatus()'un Flutter karşılığı - /api/status'u periyodik okur, /patrol_status
/// JSON'unu (data.status alani, string olarak geliyor) parse eder.
class RobotState extends ChangeNotifier {
  RobotApi? api;
  String? ip;
  bool connected = false;
  int statusCount = 0;
  double statusAge = -1;

  // patrol.py /patrol_status alanlari (index.html'deki 'info' nesnesiyle ayni)
  String state = 'idle';
  String waypoint = '';
  bool mapReady = true;
  bool rescueActive = false;
  bool screenOn = false;
  bool configured = false;
  String mode = 'unconfigured';

  Timer? _pollTimer;

  bool get isLive => connected && statusCount > 0 && statusAge >= 0 && statusAge < 4.0;

  Future<void> loadSavedIp() async {
    final prefs = await SharedPreferences.getInstance();
    ip = prefs.getString('robot_ip');
    if (ip != null && ip!.isNotEmpty) {
      api = RobotApi(baseUrl: 'http://$ip:8080');
    }
    notifyListeners();
  }

  Future<void> setIp(String newIp) async {
    ip = newIp.trim();
    api = RobotApi(baseUrl: 'http://$ip:8080');
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('robot_ip', ip!);
    notifyListeners();
  }

  void startPolling() {
    _pollTimer?.cancel();
    _poll();
    _pollTimer = Timer.periodic(const Duration(milliseconds: 1200), (_) => _poll());
  }

  void stopPolling() {
    _pollTimer?.cancel();
    _pollTimer = null;
  }

  Future<void> _poll() async {
    if (api == null) return;
    try {
      final data = await api!.status();
      connected = true;
      statusCount = (data['count'] ?? 0) as int;
      statusAge = ((data['age'] ?? -1) as num).toDouble();
      final raw = data['status'];
      if (raw is String && raw.isNotEmpty) {
        try {
          final info = jsonDecode(raw) as Map<String, dynamic>;
          state = (info['state'] ?? state) as String;
          waypoint = (info['waypoint'] ?? '') as String;
          mapReady = (info['map_ready'] ?? true) as bool;
          rescueActive = (info['rescue_active'] ?? false) as bool;
          screenOn = (info['screen_on'] ?? false) as bool;
        } catch (_) {
          // henuz patrol.py'den veri gelmemis olabilir - sessiz gec
        }
      }
      final modeData = await api!.mode();
      configured = (modeData['configured'] ?? false) as bool;
      mode = (modeData['mode'] ?? 'unconfigured') as String;
    } catch (_) {
      connected = false;
    }
    notifyListeners();
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    super.dispose();
  }
}
