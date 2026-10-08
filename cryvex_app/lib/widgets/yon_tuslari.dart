import 'package:flutter/material.dart';
import '../theme.dart';

/// Joystick'e alternatif: ileri / geri / sola / sağa tuşları. Tuş BASILI
/// TUTULDUKÇA robot gider, parmak kalkınca (ya da ekrandan kayınca) durur -
/// joystick ile aynı "bırakınca dur" güvenliği. Joystick ile aynı geri
/// çağırmaları kullanır: onMove(lx, az), onRelease().
class YonTuslari extends StatefulWidget {
  const YonTuslari({
    super.key,
    required this.onMove,
    required this.onRelease,
    this.ileriHiz = 0.15,
    this.geriHiz = 0.10,
    this.donusHiz = 0.50,
  });

  final void Function(double lx, double az) onMove;
  final VoidCallback onRelease;
  final double ileriHiz;   // m/s
  final double geriHiz;    // m/s
  final double donusHiz;   // rad/s

  @override
  State<YonTuslari> createState() => _YonTuslariState();
}

class _YonTuslariState extends State<YonTuslari> {
  String? _basili;   // 'ileri' | 'geri' | 'sol' | 'sag'

  void _bas(String yon) {
    setState(() => _basili = yon);
    final (lx, az) = switch (yon) {
      'ileri' => (widget.ileriHiz, 0.0),
      'geri' => (-widget.geriHiz, 0.0),
      'sol' => (0.0, widget.donusHiz),
      _ => (0.0, -widget.donusHiz),
    };
    widget.onMove(lx, az);
  }

  void _birak() {
    if (_basili == null) return;
    setState(() => _basili = null);
    widget.onRelease();
  }

  Widget _tus(String yon, IconData ikon, String etiket) {
    final aktif = _basili == yon;
    return Listener(
      // Listener: basılı tutma için ham dokunuş olayları (kaydırma/tıklama
      // tanıyıcılarıyla yarışmaz); iptal ve kaldırmada mutlaka durur.
      onPointerDown: (_) => _bas(yon),
      onPointerUp: (_) => _birak(),
      onPointerCancel: (_) => _birak(),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 90),
        width: 84,
        height: 84,
        decoration: BoxDecoration(
          color: aktif ? CryvexColors.cyan.withValues(alpha: 0.30) : CryvexColors.card,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: aktif ? CryvexColors.cyan : CryvexColors.cardLine, width: aktif ? 2 : 1),
        ),
        child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
          Icon(ikon, size: 38, color: aktif ? CryvexColors.cyan : CryvexColors.textPrimary),
          Text(etiket, style: const TextStyle(fontSize: 11, color: CryvexColors.textMuted)),
        ]),
      ),
    );
  }

  @override
  void dispose() {
    if (_basili != null) widget.onRelease();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    const bosluk = SizedBox(width: 84, height: 84);
    return Column(mainAxisSize: MainAxisSize.min, children: [
      Row(mainAxisSize: MainAxisSize.min, children: [bosluk, _tus('ileri', Icons.arrow_upward, 'İleri'), bosluk]),
      const SizedBox(height: 8),
      Row(mainAxisSize: MainAxisSize.min, children: [
        _tus('sol', Icons.rotate_left, 'Sola'),
        const SizedBox(width: 8),
        Container(
          width: 84,
          height: 84,
          alignment: Alignment.center,
          child: Text(_basili == null ? 'Basılı\ntut' : 'Gidiyor',
              textAlign: TextAlign.center,
              style: TextStyle(color: _basili == null ? CryvexColors.textMuted : CryvexColors.cyan, fontSize: 12)),
        ),
        const SizedBox(width: 8),
        _tus('sag', Icons.rotate_right, 'Sağa'),
      ]),
      const SizedBox(height: 8),
      Row(mainAxisSize: MainAxisSize.min, children: [bosluk, _tus('geri', Icons.arrow_downward, 'Geri'), bosluk]),
    ]);
  }
}
