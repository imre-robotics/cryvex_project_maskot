#!/usr/bin/env python3
"""cafe_map.yaml ile AYNI cozunurluk/origin/boyutta iki maske uretir:
   - keepout_mask.pgm : masalarin GERCEK govde/tabla izdusumunu (LiDAR'in
     gormedigi kismi da dahil) isgalli isaretler.
   - speed_mask.pgm   : kapi ve barmen/mutfak bolgesini yavaslama alani
     yapar (orta gri = ~%45 hiz).
Kaynak veri: patrol.py'deki WAYPOINTS yorumlarindaki gercek masa merkezleri
(table_0..table_7) + DOOR_POS + BARISTA_POS.

Gercek masa/kapi/barmen konumlari veya boyutlari degisirse: asagidaki
TABLES/DOOR/BARISTA/TABLE_HALF_M/ZONE_RADIUS_M degerlerini guncelleyip
`python3 make_masks.py` calistir - bu dosyanin bulundugu dizine (maps/)
keepout_mask.pgm ve speed_mask.pgm'i dogrudan yazar.
"""
import os
from PIL import Image

_HERE = os.path.dirname(os.path.abspath(__file__))

RES = 0.05
ORIGIN_X, ORIGIN_Y = -8.49, -7.3
W, H = 344, 287

TABLES = [
    (6.5, 3.0), (5.5, -1.0), (5.5, -5.0), (0.0, -5.0),
    (-5.5, -5.0), (-5.5, -1.0), (-6.5, 3.0), (0.0, -1.0),
]
DOOR = (0.85, -5.95)
BARISTA = (-3.43, 4.05)

TABLE_HALF_M = 0.40   # masa govdesi ~0.8x0.8 m kabul edildi (gercek olcu ile guncellenecek)
ZONE_RADIUS_M = 1.1   # kapi/barmen yavaslama alani yaricapi


def world_to_px(wx, wy):
    px = (wx - ORIGIN_X) / RES
    py_from_bottom = (wy - ORIGIN_Y) / RES
    row = H - 1 - int(round(py_from_bottom))   # PGM row 0 = ust = max y
    col = int(round(px))
    return col, row


def make_keepout():
    img = Image.new('L', (W, H), 254)   # 254 = free (ROS map_server trinary convention)
    px = img.load()
    half = int(round(TABLE_HALF_M / RES))
    for tx, ty in TABLES:
        cx, cy = world_to_px(tx, ty)
        for dx in range(-half, half + 1):
            for dy in range(-half, half + 1):
                x, y = cx + dx, cy + dy
                if 0 <= x < W and 0 <= y < H:
                    px[x, y] = 0   # 0 = occupied
    img.save(os.path.join(_HERE, 'keepout_mask.pgm'))
    print('keepout table pixel centers:', [world_to_px(tx, ty) for tx, ty in TABLES])


def make_speed():
    # scale modu: acik(254)=serbest hiz, koyu gri(~140)=~%45 hiz kisitlamasi
    img = Image.new('L', (W, H), 254)
    px = img.load()
    rad = int(round(ZONE_RADIUS_M / RES))
    for cx_w, cy_w in (DOOR, BARISTA):
        cx, cy = world_to_px(cx_w, cy_w)
        for dx in range(-rad, rad + 1):
            for dy in range(-rad, rad + 1):
                if dx * dx + dy * dy <= rad * rad:
                    x, y = cx + dx, cy + dy
                    if 0 <= x < W and 0 <= y < H:
                        px[x, y] = 140
    img.save(os.path.join(_HERE, 'speed_mask.pgm'))
    print('speed zone pixel centers:', world_to_px(*DOOR), world_to_px(*BARISTA))


make_keepout()
make_speed()
print('done')
