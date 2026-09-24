#!/bin/bash
# Cryvex kiosk oturumu - xinit'in son istemcisi olarak calisir (bu betik
# CIKARSA X de kapanir, bu yuzden sonunda "exec chromium ..." ile devam
# ediyoruz, ayri bir arka plan surecine birakmiyoruz).
set -u

xset s off
xset -dpms
xset s noblank
command -v unclutter >/dev/null 2>&1 && unclutter -idle 0.5 -root &

# cafe_ui_server (bkz. cryvex_bringup/cafe_ui_server.py) ayaga kalkana
# kadar bekle - erken acilirsa Chromium "baglanti reddedildi" sayfasinda
# TAKILI KALIR (otomatik yenilemez). En fazla 30sn bekle, sonra yine de
# ac (kullanici manuel F5/yeniden baslatma yapabilir).
for i in $(seq 1 30); do
    curl -sf http://localhost:8080/ >/dev/null 2>&1 && break
    sleep 1
done

exec chromium \
    --kiosk \
    --no-first-run \
    --disable-infobars \
    --disable-session-crashed-bubble \
    --noerrdialogs \
    --check-for-update-interval=31536000 \
    --disable-features=Translate \
    --overscroll-history-navigation=0 \
    --autoplay-policy=no-user-gesture-required \
    http://localhost:8080/
