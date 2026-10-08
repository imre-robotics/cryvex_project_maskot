# Sürüş (yalpalama) testi

Nav2 denetleyicisini değiştirdikten sonra düz yolda salınımı **ölçmek** için.

1. **Robotta (boşta, önünde 2,5 m boşluk):**
   ```bash
   source /opt/ros/jazzy/setup.bash
   python3 yalpa_kayit.py ETIKET &   # /cmd_vel + map->base_footprint kaydı
   python3 yalpa_git.py              # boşluk kontrolü, Nav2 ile 2 m ileri ve geri
   kill -INT %1
   cp /tmp/yalpa_rota.json /tmp/yalpa_rota_ETIKET.json
   ```
   `yalpa_git.py` yol boş değilse hareket etmeden çıkar.
2. **Bilgisayarda:** `/tmp/yalpa_ETIKET.npz` ve `/tmp/yalpa_rota_ETIKET.json` dosyalarını alıp şunu çalıştırın:
   ```bash
   python3 yalpa_ana.py ETIKET1 ETIKET2
   ```

Ölçülenler (yalnız düz kısım, baş/son 30 cm hariç):
- dönüş komutunun saniyede kaç kez sağ/sol değiştirdiği;
- ortalama |wz|;
- yana sapma;
- yön salınımı.

2026-10-09 sonuçları: DWB 0,70/sn, ±8,7°, 15 cm → RPP 0/sn, ±3,0°, 9,6 cm.
