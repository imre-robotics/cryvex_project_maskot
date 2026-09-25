import 'dart:async';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../api/robot_api.dart';
import '../state/robot_state.dart';
import '../theme.dart';
import '../tts.dart';
import '../widgets/password_sheet.dart';
import 'connect_screen.dart';
import 'joystick_screen.dart';
import 'setup_webview_screen.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  int _volume = 50;
  bool _volumeLoaded = false;
  Timer? _volumeDebounce;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => context.read<RobotState>().startPolling());
    _loadVolume();
  }

  Future<void> _loadVolume() async {
    final v = await _api.getVolume();
    if (mounted && v >= 0) setState(() { _volume = v; _volumeLoaded = true; });
  }

  void _onVolumeChanged(double v) {
    setState(() => _volume = v.round());
    _volumeDebounce?.cancel();
    _volumeDebounce = Timer(const Duration(milliseconds: 200), () => _api.setVolume(_volume));
  }

  @override
  void dispose() {
    context.read<RobotState>().stopPolling();
    _volumeDebounce?.cancel();
    super.dispose();
  }

  RobotApi get _api => context.read<RobotState>().api!;

  Future<void> _requireMapReady(VoidCallback action) async {
    final st = context.read<RobotState>();
    if (!st.mapReady) {
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('⚠ Kurulum/haritalama sürüyor, önce "Ortamı Haritala" akışını bitirin.')));
      return;
    }
    action();
  }

  Future<void> _stopPatrol() async {
    final ok = await askPassword(context, subtitle: 'Devriyeyi durdurmak için 4 haneli şifre');
    if (!ok) return;
    await _api.stopPatrol();
    if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Devriye durduruldu')));
    speak(_api, 'Devriyeyi durdurdum.', expr: 'happy');
  }

  void _openJoystick(JoyMode mode) async {
    final result = await Navigator.of(context).push(MaterialPageRoute(builder: (_) => JoystickScreen(mode: mode)));
    if (result == true && mounted) {
      // finish_mapping sonrasi "true" doner - kuruluma yonlendir.
      Navigator.of(context).push(MaterialPageRoute(builder: (_) => const SetupWebviewScreen()));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<RobotState>(
      builder: (context, st, _) {
        return Scaffold(
          appBar: AppBar(
            title: const Text('CRYVEX'),
            actions: [
              IconButton(
                icon: const Icon(Icons.wifi_tethering),
                tooltip: st.ip ?? '',
                onPressed: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => const ConnectScreen())),
              ),
            ],
          ),
          body: SafeArea(
            child: ListView(
              padding: const EdgeInsets.all(16),
              children: [
                _statusCard(st),
                const SizedBox(height: 12),
                _volumeCard(),
                const SizedBox(height: 18),
                _sectionLabel('Devriye'),
                _actionButton('🚀 Devriyeyi Başlat', CryvexButtonStyle.green,
                    () => _requireMapReady(() { _api.startPatrol(); speak(_api, 'Devriyeye başlıyorum.', expr: 'alert'); })),
                _actionButton('🚪 Karşılama (Kapıda, 3 dk)', CryvexButtonStyle.cyan,
                    () => _requireMapReady(() { _api.greetDoor(); speak(_api, 'Kapıda karşılamaya gidiyorum.', expr: 'love'); })),
                _actionButton('🎈 Sosyalleşme (Gezinme)', CryvexButtonStyle.cyan,
                    () => _requireMapReady(() { _api.wander(); speak(_api, 'Kafede geziniyorum.', expr: 'happy'); })),
                _actionButton('🏠 Üsse Dön', CryvexButtonStyle.cyan,
                    () => _requireMapReady(() { _api.goHome(); speak(_api, 'Üsse dönüyorum.'); })),
                _actionButton('🔒 Devriyeyi Durdur', CryvexButtonStyle.red, _stopPatrol),
                const SizedBox(height: 18),
                _sectionLabel('Manuel'),
                _actionButton('🆘 Kurtar (Manuel Sürüş)', CryvexButtonStyle.amber,
                    () => _openJoystick(JoyMode.rescue)),
                _actionButton('🕹️ Kontrol Sende', CryvexButtonStyle.cyan,
                    () => _openJoystick(JoyMode.control)),
                const SizedBox(height: 18),
                _sectionLabel('Kurulum'),
                _actionButton('🗺️ Ortamı Haritala', CryvexButtonStyle.cyan,
                    () => _openJoystick(JoyMode.map)),
                _actionButton('📍 Masa/Kapı Noktaları', CryvexButtonStyle.gray,
                    () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => const SetupWebviewScreen()))),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _sectionLabel(String s) => Padding(
        padding: const EdgeInsets.only(bottom: 8, top: 4),
        child: Text(s.toUpperCase(),
            style: const TextStyle(color: CryvexColors.textMuted, fontSize: 11, letterSpacing: 1.2, fontWeight: FontWeight.w600)),
      );

  Widget _actionButton(String label, ButtonStyle style, VoidCallback onTap) => Padding(
        padding: const EdgeInsets.only(bottom: 10),
        child: SizedBox(width: double.infinity, child: ElevatedButton(style: style, onPressed: onTap, child: Text(label))),
      );

  Widget _volumeCard() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      decoration: BoxDecoration(
        color: CryvexColors.card,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: CryvexColors.cardLine),
      ),
      child: Row(children: [
        const Icon(Icons.volume_up, color: CryvexColors.textMuted, size: 20),
        Expanded(
          child: Slider(
            value: _volume.toDouble().clamp(0, 100),
            min: 0, max: 100,
            activeColor: CryvexColors.cyan,
            onChanged: _volumeLoaded ? _onVolumeChanged : null,
          ),
        ),
        SizedBox(width: 38, child: Text('$_volume%', textAlign: TextAlign.right,
            style: const TextStyle(color: CryvexColors.textMuted, fontSize: 12.5))),
      ]),
    );
  }

  Widget _statusCard(RobotState st) {
    final dotColor = st.isLive ? CryvexColors.green : CryvexColors.amber;
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: CryvexColors.card,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: CryvexColors.cardLine),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Container(width: 10, height: 10, decoration: BoxDecoration(color: dotColor, shape: BoxShape.circle)),
            const SizedBox(width: 8),
            Text(st.isLive ? 'Robot bağlı' : 'Robota ulaşılamıyor…', style: const TextStyle(color: CryvexColors.textMuted, fontSize: 13)),
          ]),
          const SizedBox(height: 8),
          Row(children: [
            Container(
                width: 10, height: 10,
                decoration: BoxDecoration(color: st.configured ? CryvexColors.green : CryvexColors.amber, shape: BoxShape.circle)),
            const SizedBox(width: 8),
            Text(st.configured ? 'Kurulum tamam · masalar tanımlı' : 'Kurulum eksik · henüz masa/harita yok',
                style: const TextStyle(color: CryvexColors.textMuted, fontSize: 13)),
          ]),
          const Divider(height: 24, color: CryvexColors.cardLine),
          Text('Durum: ${st.state}', style: const TextStyle(color: CryvexColors.textPrimary, fontWeight: FontWeight.w600)),
          if (st.waypoint.isNotEmpty) Text(st.waypoint, style: const TextStyle(color: CryvexColors.textMuted, fontSize: 12.5)),
          if (st.rescueActive)
            const Padding(
              padding: EdgeInsets.only(top: 6),
              child: Text('🆘 Kurtarma modu aktif', style: TextStyle(color: CryvexColors.amber, fontWeight: FontWeight.w600)),
            ),
        ],
      ),
    );
  }
}
