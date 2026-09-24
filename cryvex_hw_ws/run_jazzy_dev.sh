#!/usr/bin/env bash
# Cryvex gercek donanim gelistirme konteynerini kurar/acar.
# Ilk calistirmada imaji derler (birkac dakika surer, internet gerekir),
# sonrakilerde direkt acar. src/ klasoru host ile PAYLASILIR (bind mount) -
# dosyayi burada (VSCode/editor) duzenle, icerde ANINDA gorunur, yeniden
# `docker build` gerekmez (sadece Dockerfile'i degistirirsen gerekir).
#
# Kullanim:
#   ./run_jazzy_dev.sh          # konteyneri ac (yoksa once inşa eder)
#
# NOT: kullanici 'docker' grubuna eklendi ama mevcut kabuk oturumu bunu
# HENUZ gormeyebilir (Linux supplementary group'lar oturum acilisinda
# sabitlenir, canli okunmaz). Tam cikis/giris ya da `newgrp docker`
# gerekmeden calismasi icin: docker calismiyorsa otomatik olarak
# `sg docker -c` ile (grup canli aktif edilerek) kendini yeniden calistirir.
set -euo pipefail
cd "$(dirname "$0")"

if ! docker info >/dev/null 2>&1; then
    if command -v sg >/dev/null 2>&1 && sg docker -c "docker info" >/dev/null 2>&1; then
        echo ">>> Bu oturumda 'docker' grubu henuz aktif degil, 'sg docker' ile calistiriliyor..."
        exec sg docker -c "$0 $*"
    else
        echo "HATA: docker calismiyor ve 'sg docker' ile de calismadi." >&2
        echo "  sudo usermod -aG docker \$USER  calistirdiysan tam oturum kapatip acman gerekebilir." >&2
        exit 1
    fi
fi

IMG=cryvex-jazzy-dev

if ! docker image inspect "$IMG" >/dev/null 2>&1; then
    echo ">>> Imaj bulunamadi, insa ediliyor (ilk sefer birkac dakika surer)..."
    docker build -t "$IMG" .
fi

echo ">>> Konteyner aciliyor, workspace: $(pwd)/src -> /workspace/src"
docker run -it --rm \
    --name cryvex-jazzy \
    --network host \
    -v "$(pwd)/src:/workspace/src" \
    -w /workspace \
    "$IMG" bash
