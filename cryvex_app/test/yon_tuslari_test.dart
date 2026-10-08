import 'dart:convert';
import 'package:cryvex_control/api/robot_api.dart';
import 'package:cryvex_control/screens/joystick_screen.dart';
import 'package:cryvex_control/state/robot_state.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:provider/provider.dart';

void main() {
  testWidgets('Yön tuşları: basılı tutunca ileri, bırakınca dur (telefon boyutu)', (tester) async {
    final gelen = <String>[];
    final client = MockClient((req) async {
      if (req.method == 'POST') {
        gelen.add('${req.url.path} ${req.body}');
        return http.Response('{"result":"ok"}', 200);
      }
      return http.Response(jsonEncode({'tables': []}), 200);
    });
    await http.runWithClient(() async {
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 2.75;
      final st = RobotState()..api = RobotApi(baseUrl: 'http://robot:8080');
      await tester.pumpWidget(ChangeNotifierProvider.value(
          value: st, child: const MaterialApp(home: JoystickScreen(mode: JoyMode.control))));
      for (var i = 0; i < 5; i++) {
        await tester.pump(const Duration(milliseconds: 100));
      }
      await tester.tap(find.text('⬆️ Yön tuşları'));
      await tester.pump(const Duration(milliseconds: 200));
      expect(tester.takeException(), isNull);
      gelen.clear();

      final g = await tester.startGesture(tester.getCenter(find.text('İleri')));
      await tester.pump(const Duration(milliseconds: 400));
      expect(gelen.where((e) => e.startsWith('/api/teleop ')), isNotEmpty);
      final ilk = jsonDecode(gelen.firstWhere((e) => e.startsWith('/api/teleop ')).split(' ').skip(1).join(' '));
      expect((ilk['lx'] as num).toDouble(), closeTo(0.15, 1e-6));
      expect((ilk['az'] as num).toDouble(), 0.0);

      await g.up();
      await tester.pump(const Duration(milliseconds: 300));
      expect(gelen.last, startsWith('/api/teleop_stop'));
      final sayi = gelen.length;
      await tester.pump(const Duration(milliseconds: 500));
      expect(gelen.length, sayi, reason: 'bırakınca komut gönderimi durmalı');

      final s = await tester.startGesture(tester.getCenter(find.text('Sağa')));
      await tester.pump(const Duration(milliseconds: 300));
      final donus = jsonDecode(gelen.lastWhere((e) => e.startsWith('/api/teleop ')).split(' ').skip(1).join(' '));
      expect((donus['az'] as num).toDouble(), lessThan(0));
      await s.up();
      await tester.pumpWidget(const SizedBox());
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    }, () => client);
  });
}
