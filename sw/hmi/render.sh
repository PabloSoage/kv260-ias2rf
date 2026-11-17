#!/bin/bash
# Render the HMI screens (sw/hmi/screens/*.dc.html) to docs/img/hmi/hmi_<screen>.png with headless Chrome.
# screens/support.js is a small offline renderer for the screens' template format (sc-for, sc-if, {{holes}}),
# so each screen also opens directly in a browser. Usage: sw/hmi/render.sh [path-to-chrome]
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
OUT="$HERE/../../docs/img/hmi"
CHROME=${1:-"/c/Program Files/Google/Chrome/Application/chrome.exe"}
mkdir -p "$OUT"
win() { if command -v cygpath > /dev/null; then cygpath -m "$1"; else echo "$1"; fi; }
for f in Main Vehicle Radio Spectrum Adsb Radar Transmit System; do
    name=$(echo "$f" | tr 'A-Z' 'a-z'); [ "$name" = main ] && name=home
    "$CHROME" --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=1.5 \
        --window-size=1280,720 --virtual-time-budget=8000 \
        --screenshot="$(win "$OUT")/hmi_$name.png" "file:///$(win "$HERE/screens")/$f.dc.html" > /dev/null 2>&1
    echo "hmi_$name.png"
done
