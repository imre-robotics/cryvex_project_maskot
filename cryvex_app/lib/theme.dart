import 'package:flutter/material.dart';

/// Web arayüzüyle (index.html) aynı renk paleti - tutarlı görünüm için.
class CryvexColors {
  static const bg = Color(0xFF06060E);
  static const card = Color(0x0BFFFFFF);
  static const cardLine = Color(0x12FFFFFF);
  static const cyan = Color(0xFF00E5FF);
  static const green = Color(0xFF00FF88);
  static const red = Color(0xFFFF4466);
  static const amber = Color(0xFFFFAA00);
  static const textPrimary = Color(0xFFE8EAF6);
  static const textMuted = Color(0xFF8A8AB0);
}

ThemeData buildCryvexTheme() {
  return ThemeData(
    useMaterial3: true,
    brightness: Brightness.dark,
    scaffoldBackgroundColor: CryvexColors.bg,
    colorScheme: const ColorScheme.dark(
      primary: CryvexColors.cyan,
      secondary: CryvexColors.green,
      error: CryvexColors.red,
      surface: CryvexColors.bg,
    ),
    fontFamily: 'Roboto',
    appBarTheme: const AppBarTheme(
      backgroundColor: CryvexColors.bg,
      foregroundColor: CryvexColors.textPrimary,
      elevation: 0,
      centerTitle: true,
    ),
    textTheme: const TextTheme(
      bodyMedium: TextStyle(color: CryvexColors.textPrimary),
      bodyLarge: TextStyle(color: CryvexColors.textPrimary),
    ),
    cardColor: CryvexColors.card,
  );
}

/// Manager panelindeki .btn-* sınıflarıyla eşleşen buton renk kalıpları.
class CryvexButtonStyle {
  static ButtonStyle _make(Color fg, Color bg, Color border) {
    return ElevatedButton.styleFrom(
      foregroundColor: fg,
      backgroundColor: bg,
      side: BorderSide(color: border, width: 1),
      elevation: 0,
      padding: const EdgeInsets.symmetric(vertical: 16, horizontal: 18),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      textStyle: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600),
    );
  }

  static ButtonStyle green = _make(CryvexColors.green, CryvexColors.green.withValues(alpha: 0.10),
      CryvexColors.green.withValues(alpha: 0.25));
  static ButtonStyle cyan = _make(CryvexColors.cyan, CryvexColors.cyan.withValues(alpha: 0.10),
      CryvexColors.cyan.withValues(alpha: 0.22));
  static ButtonStyle red = _make(CryvexColors.red, CryvexColors.red.withValues(alpha: 0.10),
      CryvexColors.red.withValues(alpha: 0.22));
  static ButtonStyle amber = _make(CryvexColors.amber, CryvexColors.amber.withValues(alpha: 0.10),
      CryvexColors.amber.withValues(alpha: 0.25));
  static ButtonStyle gray = _make(CryvexColors.textMuted, Colors.white.withValues(alpha: 0.04),
      Colors.white.withValues(alpha: 0.08));
}
