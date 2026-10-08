/// patrol.py durum adlarını (STATE_*) garsonun anlayacağı cümleye çevirir.
/// [hedef] = /patrol_status 'waypoint' (ör. "Masa 2"), [teslimMasa] = siparişin masası.
(String ikon, String metin) durumMetni(String state, {String hedef = '', String teslimMasa = ''}) {
  final h = hedef.isNotEmpty ? hedef : 'hedef';
  final m = teslimMasa.isNotEmpty ? teslimMasa : h;
  return switch (state) {
    'idle' => ('😴', 'Boşta bekliyor'),
    'patrol' => ('🚶', '$h için yolda (devriye)'),
    'waiting_at_table' => ('🍽️', '$h başında, sipariş bekliyor'),
    'delivering_order' => ('📝', 'Siparişi barmene götürüyor'),
    'at_barista' => ('🔔', 'Barmende, siparişi iletti'),
    'going_home' => ('🏠', 'Üsse dönüyor'),
    'wander' => ('🎈', 'Kafede geziniyor'),
    'greet_door' => ('🚪', 'Kapıda müşteri karşılıyor'),
    'directed' => ('➡️', '$h için yolda (yönlendirildi)'),
    'messenger' => ('💌', 'Mesaj taşıyor → $h'),
    'teleop' => ('🕹️', 'Elle sürülüyor'),
    'pickup' => ('📦', 'Hazır siparişi almaya barmene gidiyor'),
    'pickup_wait' => ('📦', 'Barmende, sipariş yükleniyor'),
    'serving' => ('🚚', 'Siparişi $m masasına götürüyor'),
    'served_wait' => ('🍽️', '$m masasında, müşteri alıyor'),
    _ => ('🤖', state),
  };
}
