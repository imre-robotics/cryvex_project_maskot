// Cryvex Kontrol - başlangıç smoke test'i. Ağ/robot bağlantısı gerektiren
// asıl ekranlar (Dashboard/Joystick) manuel cihaz testiyle doğrulanıyor;
// burada sadece uygulamanın çökmeden Bağlantı ekranını açtığını doğrularız.
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:cryvex_control/main.dart';

void main() {
  testWidgets('Uygulama açılır ve Bağlantı ekranını gösterir', (WidgetTester tester) async {
    SharedPreferences.setMockInitialValues({});
    await tester.pumpWidget(const CryvexApp());
    await tester.pumpAndSettle();
    expect(find.text('Bağlan'), findsOneWidget);
  });
}
