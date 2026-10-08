"""Robotun kayitli haritadaki yerini LiDAR taramasindan bulur (AMCL'den bagimsiz).

2026-10-09: AMCL bir kez kayinca (takilma/kurtarma manevrasi) yanlis konumu
last_pose.json'a yaziyor, yeniden acilista da oradan basliyordu; AMCL'in "butun
haritada kendini ara" yetenegi yok. Sahada robot 1.3 m / 121 derece yanlis
konumda kalmisti. Bu modul:
  * uyum(): taramanin yuzde kaci haritadaki duvarlara (<10 cm) oturuyor - konum
    kalitesi olcusu (iyi: >%80, kaybolmus: <%50),
  * bul(): haritadaki her bos noktayi (20 cm adim) ve her yonu (5 derece) dener,
    en iyi adaylari ince ayarlar.
Yalniz numpy + OpenCV (Pi'de scipy yok).
"""
import math

import cv2
import numpy as np

# Nokta duvara bu kadar yakinsa "oturdu". Sahada olculdu (2026-10-09): 15 cm'de dogru
# konum %96, 10 cm/3 derece kayma %82, 25 cm/8 derece %63, gercek kayip %49. 10 cm
# esikte zararsiz birkac cm'lik AMCL titremesi bile %54'e dusurup yalanci alarm veriyordu.
UYUM_ESIK_M = 0.15
GOVDE_ICI_M = 0.35          # robotun kendi govdesi/kablosu: bu yaricapin icindeki noktalar atilir


class KonumBulucu:
    def __init__(self, img, res, ox, oy, robot_r=0.30, aday_adim_m=0.20):
        """img: harita (uint8, satir 0 = UST; PGM: 0 dolu, 254 bos, 205 bilinmiyor)."""
        self.h, self.w = img.shape
        self.res, self.ox, self.oy = float(res), float(ox), float(oy)
        dolu = img < 100
        # her hucrenin en yakin dolu hucreye uzakligi (m), 1 m'de kesilir
        self.mesafe = np.minimum(
            cv2.distanceTransform((~dolu).astype(np.uint8), cv2.DIST_L2, 5) * self.res, 1.0
        ).astype(np.float32)
        # aday robot merkezleri: bos ve duvardan en az robot yaricapi kadar uzak
        bos = (img > 250).astype(np.uint8)
        k = max(1, int(round(robot_r / self.res)))
        bos = cv2.erode(bos, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * k + 1, 2 * k + 1)))
        ys, xs = np.nonzero(bos)
        adim = max(1, int(round(aday_adim_m / self.res)))
        sec = (xs % adim == 0) & (ys % adim == 0)
        self.aday_x = (self.ox + (xs[sec] + 0.5) * self.res).astype(np.float32)
        self.aday_y = (self.oy + (self.h - ys[sec] - 0.5) * self.res).astype(np.float32)

    # ---- yardimci ----
    def _mesafeler(self, wx, wy):
        px = ((wx - self.ox) / self.res).astype(np.int32)
        py = (self.h - 1 - ((wy - self.oy) / self.res)).astype(np.int32)
        ok = (px >= 0) & (px < self.w) & (py >= 0) & (py < self.h)
        d = np.ones(wx.shape, dtype=np.float32)
        d[ok] = self.mesafe[py[ok], px[ok]]
        return d

    @staticmethod
    def temizle(pts):
        pts = np.asarray(pts, dtype=np.float32).reshape(-1, 2)
        return pts[np.hypot(pts[:, 0], pts[:, 1]) > GOVDE_ICI_M]

    def uyum(self, pts, x, y, yaw):
        """pts: tarama noktalari robot (base_footprint) cercevesinde, Nx2."""
        pts = self.temizle(pts)
        if len(pts) < 20:
            return None
        c, s = math.cos(yaw), math.sin(yaw)
        wx = x + pts[:, 0] * c - pts[:, 1] * s
        wy = y + pts[:, 0] * s + pts[:, 1] * c
        return float(np.mean(self._mesafeler(wx, wy) < UYUM_ESIK_M))

    def bul(self, pts, aci_adim_derece=5.0, aday_sayisi=3):
        """Butun haritada arar. Doner: [(uyum, x, y, yaw), ...] en iyiden kotuye,
        birbirinden farkli (60 cm / 17 derece) en fazla aday_sayisi konum."""
        pts = self.temizle(pts)
        if len(pts) < 20 or len(self.aday_x) == 0:
            return []
        kaba = pts[:: max(1, len(pts) // 150)]
        sonuclar = []
        for yaw in np.radians(np.arange(-180.0, 180.0, aci_adim_derece)):
            c, s = math.cos(yaw), math.sin(yaw)
            rx = kaba[:, 0] * c - kaba[:, 1] * s
            ry = kaba[:, 0] * s + kaba[:, 1] * c
            puan = np.mean(self._mesafeler(self.aday_x[:, None] + rx[None, :],
                                           self.aday_y[:, None] + ry[None, :]) < UYUM_ESIK_M, axis=1)
            for i in np.argsort(-puan)[:3]:
                sonuclar.append((float(puan[i]), float(self.aday_x[i]), float(self.aday_y[i]), float(yaw)))
        sonuclar.sort(reverse=True)
        secilen = []
        for _, x, y, yaw in sonuclar:
            if any(math.hypot(x - a, y - b) < 0.6 and abs(math.atan2(math.sin(yaw - t), math.cos(yaw - t))) < 0.3
                   for _, a, b, t in secilen):
                continue
            secilen.append(self._ince_ayar(pts, x, y, yaw))
            if len(secilen) >= aday_sayisi:
                break
        secilen.sort(reverse=True)
        return secilen

    def _ince_ayar(self, pts, x, y, yaw):
        en_iyi = (self.uyum(pts, x, y, yaw), x, y, yaw)
        for adim_m, adim_a in ((0.10, math.radians(2.0)), (0.05, math.radians(1.0)), (0.02, math.radians(0.5))):
            degisti = True
            while degisti:
                degisti = False
                _, bx, by, bt = en_iyi
                for dx, dy, dt in ((adim_m, 0, 0), (-adim_m, 0, 0), (0, adim_m, 0), (0, -adim_m, 0),
                                   (0, 0, adim_a), (0, 0, -adim_a)):
                    u = self.uyum(pts, bx + dx, by + dy, bt + dt)
                    if u is not None and u > en_iyi[0] + 1e-4:
                        en_iyi, degisti = (u, bx + dx, by + dy, bt + dt), True
        return en_iyi
