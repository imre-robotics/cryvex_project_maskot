import 'dart:convert';
import 'package:cryvex_control/api/robot_api.dart';
import 'package:cryvex_control/state/robot_state.dart';
import 'package:cryvex_control/widgets/password_sheet.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:provider/provider.dart';

/// Robottaki şifre 4821; uygulama şifreyi bilmez, robota sorar.
MockClient _robot(List<String> sorulan) => MockClient((req) async {
      if (req.url.path == '/api/pin_kontrol') {
        final pin = (jsonDecode(req.body) as Map)['password'];
        sorulan.add('$pin');
        return http.Response(pin == '4821' ? '{"result":"ok"}' : '{"result":"error","reason":"wrong password"}', 200);
      }
      return http.Response('{}', 404);
    });

Future<String?> _gir(WidgetTester tester, String rakamlar, {bool dogrula = true}) async {
  final st = RobotState()..api = RobotApi(baseUrl: 'http://robot:8080');
  String? sonuc = 'acilmadi';
  await tester.pumpWidget(ChangeNotifierProvider.value(
    value: st,
    child: MaterialApp(home: Builder(builder: (ctx) => TextButton(
      onPressed: () async => sonuc = await pinIste(ctx, dogrula: dogrula),
      child: const Text('ac'),
    ))),
  ));
  await tester.tap(find.text('ac'));
  await tester.pumpAndSettle();
  for (final r in rakamlar.split('')) {
    await tester.tap(find.text(r));
    await tester.pump(const Duration(milliseconds: 50));
  }
  await tester.pump(const Duration(milliseconds: 600));
  await tester.pumpAndSettle();
  return sonuc;
}

void main() {
  testWidgets('Doğru şifre: robot onaylar, operatorPin yazılır', (tester) async {
    final sorulan = <String>[];
    await http.runWithClient(() async {
      operatorPin = '';
      expect(await _gir(tester, '4821'), '4821');
      expect(operatorPin, '4821');
      expect(sorulan, ['4821']);
    }, () => _robot(sorulan));
  });

  testWidgets('Yanlış şifre: pencere kapanmaz, operatorPin değişmez', (tester) async {
    final sorulan = <String>[];
    await http.runWithClient(() async {
      operatorPin = '';
      expect(await _gir(tester, '1234'), 'acilmadi');   // pencere açık kaldı, sonuç dönmedi
      expect(operatorPin, '');
      expect(find.text('🔒 Şifre Gerekli'), findsOneWidget);
    }, () => _robot(sorulan));
  });

  testWidgets('Yeni şifre belirlerken robota sorulmaz', (tester) async {
    final sorulan = <String>[];
    await http.runWithClient(() async {
      expect(await _gir(tester, '5555', dogrula: false), '5555');
      expect(sorulan, isEmpty);
    }, () => _robot(sorulan));
  });
}
