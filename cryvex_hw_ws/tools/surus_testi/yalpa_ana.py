import json, math, sys, numpy as np
def analiz(tag):
    d = np.load(f'yalpa_{tag}.npz'); R = json.load(open(f'yalpa_rota_{tag}.json'))
    C, P = d['cmd'], d['poz']; p0, B, z = R['p0'], R['B'], R['zaman']
    print(f'=== {tag.upper()} ===')
    tum = {'gecis': 0, 'sure': 0, 'sapma': [], 'wz': [], 'yon': []}
    for ad, (a, b) in (('gidis', (p0, B)), ('donus', (B, p0))):
        t0, t1 = z[ad+'_bas'], z[ad+'_son']
        ax, ay, bx, by = a[0], a[1], b[0], b[1]; L = math.hypot(bx-ax, by-ay); ux, uy = (bx-ax)/L, (by-ay)/L
        pp = P[(P[:,0] >= t0) & (P[:,0] <= t1)]
        s = (pp[:,1]-ax)*ux + (pp[:,2]-ay)*uy          # yol boyunca ilerleme
        e = -(pp[:,1]-ax)*uy + (pp[:,2]-ay)*ux         # yana sapma
        duz = (s > 0.3) & (s < L - 0.3)                 # bas/son donusleri haric
        if duz.sum() < 5: print(ad, 'duz kisim yok'); continue
        td0, td1 = pp[duz,0].min(), pp[duz,0].max()
        cc = C[(C[:,0] >= td0) & (C[:,0] <= td1)]
        w = cc[:,2]; anlamli = w[np.abs(w) > 0.04]
        gecis = int(np.sum(np.diff(np.sign(anlamli)) != 0))
        hed_yaw = math.atan2(uy, ux); yerr = np.degrees(np.arctan2(np.sin(pp[duz,3]-hed_yaw), np.cos(pp[duz,3]-hed_yaw)))
        sure = td1 - td0
        print(f'{ad}: duz kisim {sure:.1f} sn, ort hiz {np.mean(cc[:,1]):.2f} m/s | donus komutu yon degisimi {gecis} ({gecis/sure:.2f}/sn) | '
              f'|wz| ort {np.mean(np.abs(w)):.3f} en buyuk {np.max(np.abs(w)):.2f} rad/s | yana sapma en buyuk {np.max(np.abs(e[duz]))*100:.1f} cm | '
              f'yon salinimi +-{np.std(yerr):.1f} der (en buyuk {np.max(np.abs(yerr)):.1f})')
        tum['gecis'] += gecis; tum['sure'] += sure; tum['sapma'].append(np.max(np.abs(e[duz]))); tum['wz'] += list(np.abs(w)); tum['yon'] += list(yerr)
    print(f'TOPLAM: yon degisimi {tum["gecis"]/tum["sure"]:.2f}/sn, |wz| ort {np.mean(tum["wz"]):.3f}, sapma en buyuk {max(tum["sapma"])*100:.1f} cm, yon salinimi +-{np.std(tum["yon"]):.1f} der, toplam sure gidis+donus {sum(z[k+"_son"]-z[k+"_bas"] for k in ("gidis","donus")):.1f} sn')
for t in sys.argv[1:]: analiz(t)
