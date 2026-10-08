import 'dart:async';
import 'dart:math' as math;
import 'dart:typed_data';
import 'package:flutter/material.dart';
import '../api/robot_api.dart';
import '../durum.dart';
import '../theme.dart';

/// Ana ekranın takip haritası: "garson robot nerede, ne yapıyor".
/// Kayıtlı harita (/api/map.png) bir kez alınır; üstüne uygulama kendisi çizer:
/// robot (nokta + yön oku), Nav2'nin izlediği yol (sarı), masalar (numaralı),
/// Üs (U), Kapı (K) ve o an gidilen hedef (halkayla vurgulu).
/// Robotun konumu ve yolu /api/robot_pose ile saniyede bir yenilenir; harita
/// değişirse (yeniden haritalama, fırça) map_info 'stamp' ile fark edilip yeniden alınır.
class TakipHaritasi extends StatefulWidget {
  const TakipHaritasi({
    super.key,
    required this.api,
    required this.state,
    this.hedef = '',
    this.teslimMasa = '',
  });

  final RobotApi? api;
  final String state;
  final String hedef;
  final String teslimMasa;

  @override
  State<TakipHaritasi> createState() => _TakipHaritasiState();
}

class _Isaret {
  _Isaret(this.tur, this.etiket, this.isim, this.x, this.y);
  final String tur;   // masa | us | kapi
  final String etiket;
  final String isim;
  final double x, y;
}

class _TakipHaritasiState extends State<TakipHaritasi> with WidgetsBindingObserver {
  Map<String, dynamic>? _info;
  Uint8List? _png;
  List<_Isaret> _isaretler = [];
  Map<String, dynamic>? _poz;
  String? _hata;
  Timer? _timer;
  int _tik = 0;
  bool _mesgul = false;
  bool _arkaPlanda = false;
  bool _araniyor = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _yenile();
    _timer = Timer.periodic(const Duration(seconds: 1), (_) => _yenile());
  }

  @override
  void dispose() {
    _timer?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState s) => _arkaPlanda = s != AppLifecycleState.resumed;

  Future<void> _yenile() async {
    final api = widget.api;
    if (api == null || _mesgul || _arkaPlanda || !mounted) return;
    _mesgul = true;
    try {
      // Harita ve noktalar 10 sn'de bir (ya da hiç yoksa), konum her saniye.
      if (_info == null || _tik % 10 == 0) {
        final info = await api.mapInfo();
        if (((info['width'] ?? 0) as num) == 0) {
          if (mounted) setState(() => _hata = 'Robotta kayıtlı harita yok');
          return;
        }
        if (_info == null || info['stamp'] != _info!['stamp'] || _png == null) {
          final png = await api.mapPng();
          if (png != null) _png = png;
        }
        _info = info;
        _isaretler = _noktalar(await api.waypoints());
      }
      _tik++;
      final p = await api.robotPose();
      if (mounted) {
        setState(() {
          _poz = p['ok'] == true ? p : null;
          _hata = null;
        });
      }
    } catch (_) {
      if (mounted) setState(() => _hata = 'Robota ulaşılamıyor');
    } finally {
      _mesgul = false;
    }
  }

  List<_Isaret> _noktalar(Map<String, dynamic> wp) {
    _Isaret? n(dynamic j, String tur, String etiket, String varsayilan) => j is Map
        ? _Isaret(tur, etiket, (j['isim'] ?? varsayilan).toString(), (j['x'] as num).toDouble(), (j['y'] as num).toDouble())
        : null;
    return [
      for (final (i, t) in ((wp['tables'] as List?) ?? []).indexed) ?n(t, 'masa', '${i + 1}', 'Masa ${i + 1}'),
      ?n(wp['barista'], 'us', 'U', 'Üs'),
      ?n(wp['door'], 'kapi', 'K', 'Kapı'),
    ];
  }

  /// O an gidilen nokta: devriye/yönlendirmede hedef adı, teslimatta masa,
  /// barmene giderken/üsse dönerken Üs.
  _Isaret? get _hedefIsaret {
    final s = widget.state;
    String? ad;
    if (s == 'going_home' || s == 'pickup' || s == 'delivering_order') return _bul('us');
    if (s == 'greet_door') return _bul('kapi');
    if (s == 'serving' && widget.teslimMasa.isNotEmpty) ad = widget.teslimMasa;
    if ({'patrol', 'directed', 'messenger', 'waiting_at_table', 'served_wait'}.contains(s)) ad = widget.hedef;
    if (ad == null || ad.isEmpty) return null;
    final temiz = ad.replaceAll(RegExp(r'\s*\(.*\)$'), '').trim();   // "Masa 1 (+0.35m ic)" -> "Masa 1"
    for (final m in _isaretler) {
      if (m.isim == temiz) return m;
    }
    return null;
  }

  _Isaret? _bul(String tur) {
    for (final m in _isaretler) {
      if (m.tur == tur) return m;
    }
    return null;
  }

  /// Robotun tarama-harita uyumu (0..1); robot_pose 'uyum'. Haritalamada yok.
  double? get _uyum => (_poz?['uyum'] as num?)?.toDouble();
  bool get _kayip => _uyum != null && _uyum! < 0.55;

  Future<void> _konumBul() async {
    final api = widget.api;
    if (api == null || _araniyor) return;
    setState(() => _araniyor = true);
    final r = await api.konumBul();
    if (!mounted) return;
    setState(() => _araniyor = false);
    final mesaj = r['result'] != 'ok'
        ? '❌ Bulunamadı: ${r['reason'] ?? ''}'
        : r['emin'] == true
            ? '✅ Robot yerini buldu (uyum %${((r['uyum'] as num) * 100).round()})'
            : '⚠ Emin olamadı (en iyi %${((r['uyum'] as num) * 100).round()}). Harita Kurulumu → Robot + Yön ile elle verin.';
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(mesaj)));
  }

  void _tamEkran() {
    if (_png == null) return;
    Navigator.of(context).push(MaterialPageRoute(builder: (_) => _TamEkran(ust: this)));
  }

  @override
  Widget build(BuildContext context) {
    final (ikon, metin) = durumMetni(widget.state, hedef: widget.hedef, teslimMasa: widget.teslimMasa);
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: CryvexColors.card,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: CryvexColors.cardLine),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Row(children: [
          Text(ikon, style: const TextStyle(fontSize: 22)),
          const SizedBox(width: 8),
          Expanded(
            child: Text(metin,
                style: const TextStyle(color: CryvexColors.textPrimary, fontWeight: FontWeight.w700, fontSize: 15)),
          ),
          if (_png != null)
            IconButton(onPressed: _tamEkran, icon: const Icon(Icons.fullscreen), tooltip: 'Büyüt'),
        ]),
        const SizedBox(height: 6),
        ClipRRect(
          borderRadius: BorderRadius.circular(10),
          child: Container(
            color: Colors.black,
            height: 300,
            child: _png == null || _info == null
                ? Center(child: Text(_hata ?? 'Harita yükleniyor…', style: const TextStyle(color: CryvexColors.textMuted)))
                : GestureDetector(onTap: _tamEkran, child: _harita()),
          ),
        ),
        if (_kayip) ...[
          const SizedBox(height: 8),
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: CryvexColors.amber.withValues(alpha: 0.12),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: CryvexColors.amber.withValues(alpha: 0.4)),
            ),
            child: Row(children: [
              Expanded(
                child: Text('⚠ Robot yerini kaybetmiş olabilir (uyum %${(_uyum! * 100).round()}). Devriyeden önce düzeltin.',
                    style: const TextStyle(color: CryvexColors.amber, fontSize: 12.5)),
              ),
              const SizedBox(width: 8),
              FilledButton(
                onPressed: _araniyor ? null : _konumBul,
                child: Text(_araniyor ? 'Arıyor…' : '🔍 Konumumu Bul'),
              ),
            ]),
          ),
        ],
        const SizedBox(height: 6),
        Text(
          _hata != null && _png != null
              ? '⚠ $_hata · son konum gösteriliyor'
              : _poz == null
                  ? '⚠ Robotun haritadaki yeri bilinmiyor (Harita Kurulumu → Robot Burada)'
                  : 'Mavi: robot · sarı: gideceği yol · halka: hedefi${_uyum != null ? ' · konum güveni %${(_uyum! * 100).round()}' : ''}',
          style: TextStyle(color: _hata != null || _poz == null ? CryvexColors.amber : CryvexColors.textMuted, fontSize: 11.5),
        ),
      ]),
    );
  }

  Widget _harita({bool etkilesimli = false}) {
    final w = (_info!['width'] as num).toDouble(), h = (_info!['height'] as num).toDouble();
    final cizim = AspectRatio(
      aspectRatio: w / h,
      child: Stack(fit: StackFit.expand, children: [
        Image.memory(_png!, fit: BoxFit.fill, filterQuality: FilterQuality.none, gaplessPlayback: true),
        CustomPaint(painter: _TakipCizer(_info!, _isaretler, _poz, _hedefIsaret)),
      ]),
    );
    final ortali = Center(child: cizim);
    return etkilesimli ? InteractiveViewer(minScale: 1, maxScale: 8, child: ortali) : ortali;
  }
}

class _TamEkran extends StatefulWidget {
  const _TamEkran({required this.ust});
  final _TakipHaritasiState ust;

  @override
  State<_TamEkran> createState() => _TamEkranState();
}

class _TamEkranState extends State<_TamEkran> {
  Timer? _t;

  @override
  void initState() {
    super.initState();
    // Ana ekrandaki kart arka planda saniyede bir yenilemeye devam eder.
    _t = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) setState(() {});
    });
  }

  @override
  void dispose() {
    _t?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final u = widget.ust;
    final (ikon, metin) = durumMetni(u.widget.state, hedef: u.widget.hedef, teslimMasa: u.widget.teslimMasa);
    return Scaffold(
      appBar: AppBar(title: Text('$ikon $metin', style: const TextStyle(fontSize: 15))),
      backgroundColor: Colors.black,
      body: SafeArea(child: u._png == null ? const SizedBox() : u._harita(etkilesimli: true)),
    );
  }
}

class _TakipCizer extends CustomPainter {
  _TakipCizer(this.info, this.isaretler, this.poz, this.hedef);
  final Map<String, dynamic> info;
  final List<_Isaret> isaretler;
  final Map<String, dynamic>? poz;
  final _Isaret? hedef;

  @override
  void paint(Canvas canvas, Size size) {
    final res = (info['resolution'] as num).toDouble();
    final ox = ((info['origin'] as List)[0] as num).toDouble();
    final oy = ((info['origin'] as List)[1] as num).toDouble();
    final w = (info['width'] as num).toDouble(), h = (info['height'] as num).toDouble();
    // Dünya (m) -> ekran: PNG'de satır 0 = üst, dünyada y yukarı.
    Offset ekran(double x, double y) =>
        Offset((x - ox) / res / w * size.width, (h - (y - oy) / res) / h * size.height);
    final mPx = size.width / (w * res);   // 1 metre kaç ekran pikseli

    final plan = poz?['plan'];
    if (plan is List && plan.length > 1) {
      final yol = Path();
      for (final (i, p) in plan.indexed) {
        final e = ekran((p[0] as num).toDouble(), (p[1] as num).toDouble());
        i == 0 ? yol.moveTo(e.dx, e.dy) : yol.lineTo(e.dx, e.dy);
      }
      canvas.drawPath(yol, Paint()
        ..color = const Color(0xFFFFD500)
        ..strokeWidth = 3
        ..style = PaintingStyle.stroke
        ..strokeCap = StrokeCap.round);
    }

    final hd = hedef;
    if (hd != null) {
      canvas.drawCircle(ekran(hd.x, hd.y), 15,
          Paint()..color = Colors.white..style = PaintingStyle.stroke..strokeWidth = 2.5);
    }
    for (final m in isaretler) {
      final renk = switch (m.tur) { 'us' => CryvexColors.green, 'kapi' => CryvexColors.amber, _ => CryvexColors.cyan };
      final e = ekran(m.x, m.y);
      canvas.drawCircle(e, 9, Paint()..color = renk);
      final tp = TextPainter(
        text: TextSpan(text: m.etiket, style: const TextStyle(color: Colors.black, fontSize: 10, fontWeight: FontWeight.w800)),
        textDirection: TextDirection.ltr,
      )..layout();
      tp.paint(canvas, e - Offset(tp.width / 2, tp.height / 2));
    }

    final p = poz;
    if (p != null) {
      final e = ekran((p['x'] as num).toDouble(), (p['y'] as num).toDouble());
      final yaw = (p['yaw'] as num).toDouble();
      final r = math.max(7.0, 0.30 * mPx);   // gövde yarıçapı 0,30 m; çok küçük haritada en az 7 px
      const mavi = Color(0xFF00AAFF);
      canvas.drawCircle(e, r + 4, Paint()..color = mavi.withValues(alpha: 0.25));
      canvas.drawCircle(e, r, Paint()..color = mavi);
      canvas.drawLine(e, e + Offset(math.cos(yaw), -math.sin(yaw)) * (r + 12),
          Paint()..color = mavi..strokeWidth = 3..strokeCap = StrokeCap.round);
    }
  }

  @override
  bool shouldRepaint(covariant _TakipCizer o) => true;
}
