import 'api/robot_api.dart';

/// Robotun GERÇEK sesini kendi hoparlöründe (Pi'ye bağlı JBL vb.) çaldırır -
/// telefonda DEĞİL, komut telefondan verilse bile ses robottan çıkar.
/// Sunucu üretemezse (ör. offline) SESSİZCE geçer, hiçbir buton hata göstermez.
Future<void> speak(RobotApi api, String text) async {
  if (text.isEmpty) return;
  try {
    await api.speakHere(text);
  } catch (_) {
    // sessiz geç
  }
}
