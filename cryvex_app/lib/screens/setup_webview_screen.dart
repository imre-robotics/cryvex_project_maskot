import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:webview_flutter/webview_flutter.dart';
import '../state/robot_state.dart';
import '../theme.dart';

/// Masa/kapı/robot noktası işaretleme (web/setup.html) tekerleği yeniden icat
/// etmek yerine DOĞRUDAN gömülüyor - o ekran zaten haritayı gösterip
/// dokunma+yön ile nokta toplayan, çalışan, test edilmiş bir arayüz.
class SetupWebviewScreen extends StatefulWidget {
  const SetupWebviewScreen({super.key});

  @override
  State<SetupWebviewScreen> createState() => _SetupWebviewScreenState();
}

class _SetupWebviewScreenState extends State<SetupWebviewScreen> {
  late final WebViewController _controller;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    final baseUrl = context.read<RobotState>().api!.baseUrl;
    _controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setBackgroundColor(CryvexColors.bg)
      ..setNavigationDelegate(NavigationDelegate(
        onPageFinished: (_) => setState(() => _loading = false),
        // Kurulumdaki "Devriye Ekranı" bağlantısı robotun YÜZ arayüzüne (/)
        // gider; telefonda onu açmak yerine uygulamanın ana ekranına dön.
        onNavigationRequest: (req) {
          if (Uri.parse(req.url).path == '/') {
            if (mounted) Navigator.of(context).pop();
            return NavigationDecision.prevent;
          }
          return NavigationDecision.navigate;
        },
      ))
      ..loadRequest(Uri.parse('$baseUrl/setup'));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('📍 Kurulum'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: () => _controller.reload(),
          ),
        ],
      ),
      body: Stack(
        children: [
          WebViewWidget(controller: _controller),
          if (_loading) const Center(child: CircularProgressIndicator(color: CryvexColors.cyan)),
        ],
      ),
    );
  }
}
