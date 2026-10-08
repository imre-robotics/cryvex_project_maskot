import 'dart:convert';
import 'package:cryvex_control/api/robot_api.dart';
import 'package:cryvex_control/screens/dashboard_screen.dart';
import 'package:cryvex_control/screens/joystick_screen.dart';
import 'package:cryvex_control/screens/kurulum_screen.dart';
import 'package:cryvex_control/screens/otonom_screen.dart';
import 'package:cryvex_control/state/robot_state.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:provider/provider.dart';

final _png = base64Decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==');

MockClient _robot() => MockClient((req) async {
      if (req.method == 'POST') return http.Response('{"result":"ok"}', 200);
      return switch (req.url.path) {
        '/api/map_info' => http.Response('{"resolution":0.05,"origin":[-11,-8,0],"width":279,"height":259}', 200),
        '/api/map.png' => http.Response.bytes(_png, 200),
        '/api/waypoints' => http.Response(
            '{"barista":{"isim":"Barmen","x":-4.8,"y":-4.6,"yaw":0},"door":{"isim":"Kapi","x":-6,"y":-3.4,"yaw":0},'
            '"tables":[{"isim":"Masa 1","x":-4,"y":-3,"yaw":0},{"isim":"Masa 2","x":-0.3,"y":-0.2,"yaw":0}]}', 200),
        '/api/robot_pose' => http.Response('{"ok":true,"x":-4.4,"y":-2.1,"yaw":0.5}', 200),
        '/api/status' => http.Response(jsonEncode({'count': 3, 'age': 0.2, 'health': {}, 'orders_seq': 1,
            'status': jsonEncode({'state': 'patrol', 'waypoint': 'Masa 1', 'map_ready': true})}), 200),
        '/api/mode' => http.Response('{"mode":"operating","configured":true}', 200),
        '/api/orders' => http.Response('{"orders":[],"now":0}', 200),
        '/api/volume' => http.Response('{"volume":50}', 200),
        '/api/theme' => http.Response('{"eye":"#00d4ff","mouth":"#ff5fc8","light":"#ffd500","face":"#06060e"}', 200),
        '/api/live_map.png' => http.Response.bytes(_png, 200),
        '/api/otonom' => http.Response('{"calisiyor":false,"log":["a","b"]}', 200),
        _ => http.Response('{}', 404),
      };
    });

/// Redmi Note 10 Pro: 1080x2400 piksel, 2.75 -> 393x873 mantıksal.
Future<void> _telefon(WidgetTester tester, Widget ekran) async {
  tester.view.physicalSize = const Size(1080, 2400);
  tester.view.devicePixelRatio = 2.75;
  final st = RobotState()..api = RobotApi(baseUrl: 'http://robot:8080');
  await tester.pumpWidget(ChangeNotifierProvider.value(value: st, child: MaterialApp(home: ekran)));
  for (var i = 0; i < 5; i++) {
    await tester.pump(const Duration(milliseconds: 100));
  }
}

void main() {
  testWidgets('Harita Kurulumu telefonda taşmıyor (her araçta)', (tester) async {
    await http.runWithClient(() async {
      await _telefon(tester, const KurulumScreen());
      for (final arac in ['🍽️ Masa', '⬜ Beyaz Fırça', '⬛ Siyah Fırça']) {
        final cubuk = find.byWidgetPredicate((w) => w is ListView && w.scrollDirection == Axis.horizontal);
        await tester.dragUntilVisible(find.text(arac), cubuk, const Offset(-80, 0));
        await tester.pumpAndSettle();
        await tester.tap(find.text(arac));
        await tester.pump(const Duration(milliseconds: 200));
        expect(tester.takeException(), isNull, reason: arac);
      }
      // Kaydet düğmesi ekranda (alt kenarın üstünde) olmalı
      final kaydet = tester.getRect(find.text('Kaydet'));
      expect(kaydet.bottom, lessThan(873));
      await tester.pumpWidget(const SizedBox());
    }, _robot);
  });

  testWidgets('Otonom ekranı telefonda taşmıyor', (tester) async {
    await http.runWithClient(() async {
      await _telefon(tester, const OtonomScreen());
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox());
    }, _robot);
  });

  testWidgets('Ana ekran ve joystick telefonda taşmıyor', (tester) async {
    await http.runWithClient(() async {
      await _telefon(tester, const DashboardScreen());
      for (var i = 0; i < 6; i++) {
        await tester.drag(find.byType(ListView).first, const Offset(0, -500));
        await tester.pump(const Duration(milliseconds: 300));
        expect(tester.takeException(), isNull, reason: "ana ekran kaydirma $i");
      }
      await tester.pumpWidget(const SizedBox());
      // map/rescue açılışta şifre penceresi gösterir; pencere animasyonunun tek
      // karesinde test yazı tipiyle (gerçekten geniş) yalancı taşma çıkıyor.
      for (final m in [JoyMode.control]) {
        await _telefon(tester, JoystickScreen(mode: m));
        expect(tester.takeException(), isNull, reason: 'joystick $m');
        await tester.pumpWidget(const SizedBox());
      }
    }, _robot);
  });
}
