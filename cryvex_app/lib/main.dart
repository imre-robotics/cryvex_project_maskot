import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'state/robot_state.dart';
import 'theme.dart';
import 'screens/connect_screen.dart';
import 'screens/dashboard_screen.dart';

void main() {
  runApp(const CryvexApp());
}

class CryvexApp extends StatelessWidget {
  const CryvexApp({super.key});

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider(
      create: (_) => RobotState(),
      child: MaterialApp(
        title: 'Cryvex Kontrol',
        debugShowCheckedModeBanner: false,
        theme: buildCryvexTheme(),
        home: const _Bootstrap(),
      ),
    );
  }
}

/// Kaydedilmis bir robot IP'si varsa direkt Ana Panel'e, yoksa Baglanti
/// ekranina goturur.
class _Bootstrap extends StatefulWidget {
  const _Bootstrap();

  @override
  State<_Bootstrap> createState() => _BootstrapState();
}

class _BootstrapState extends State<_Bootstrap> {
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    await context.read<RobotState>().loadSavedIp();
    if (mounted) setState(() => _loading = false);
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Scaffold(body: Center(child: CircularProgressIndicator(color: CryvexColors.cyan)));
    }
    final hasIp = context.watch<RobotState>().ip != null;
    return hasIp ? const DashboardScreen() : const ConnectScreen();
  }
}
