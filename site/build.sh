#!/usr/bin/env bash
# Reproducible asset build pipeline for site/ (no Python, zero changes outside site/).
set -euo pipefail

SITE_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SITE_DIR/.." && pwd)"
PCB="$ROOT_DIR/CSI2-KRIA-KV260_Rev01.kicad_pcb"

find_kicad_cli() {
  if [ -n "${KICAD_CLI:-}" ] && [ -x "$KICAD_CLI" ]; then
    echo "$KICAD_CLI"
    return
  fi
  if command -v kicad-cli >/dev/null 2>&1; then
    command -v kicad-cli
    return
  fi
  for p in \
    "${LOCALAPPDATA:-}/Programs/KiCad/10.0/bin/kicad-cli.exe" \
    "/c/Users/${USERNAME:-}/AppData/Local/Programs/KiCad/10.0/bin/kicad-cli.exe" \
    "/c/Program Files/KiCad/10.0/bin/kicad-cli.exe"; do
    if [ -x "$p" ]; then
      echo "$p"
      return
    fi
  done
  echo "ERROR: kicad-cli not found (set KICAD_CLI or install KiCad 10)" >&2
  exit 1
}

KICAD="$(find_kicad_cli)"
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/ias2rf_site.XXXXXX")"
trap 'rm -rf "$TMP_DIR"' EXIT

# Convert MSYS/Git-Bash paths for Windows kicad-cli if cygpath exists
win_path() {
  if command -v cygpath >/dev/null 2>&1; then
    cygpath -m "$1"
  else
    echo "$1"
  fi
}

ROOT_W="$(win_path "$ROOT_DIR")"
PCB_W="$(win_path "$PCB")"
CLEAN_PCB="$TMP_DIR/board_clean.kicad_pcb"
CLEAN_PCB_W="$(win_path "$CLEAN_PCB")"
RAW_GLB="$TMP_DIR/raw_board.glb"
RAW_GLB_W="$(win_path "$RAW_GLB")"

echo "[1/6] Stripping cached EasyEDA model references on temp PCB copy..."
node "$SITE_DIR/scripts/strip_pcb.mjs" "$PCB" "$CLEAN_PCB"

echo "[2/6] Exporting clean KiCad GLB..."
"$KICAD" pcb export glb \
  --subst-models \
  --include-tracks \
  --include-pads \
  --include-zones \
  --include-silkscreen \
  --include-soldermask \
  --user-origin 0x0mm \
  -D "KIPRJMOD=$ROOT_W" \
  -f -o "$RAW_GLB_W" "$CLEAN_PCB_W"

echo "[3/6] Exporting per-layer SVGs..."
LAYERS_DIR="$SITE_DIR/assets/layers"
mkdir -p "$LAYERS_DIR"
LAYERS="F.Cu In1.Cu In2.Cu In3.Cu In4.Cu In5.Cu In6.Cu B.Cu F.SilkS B.SilkS F.Mask B.Mask Edge.Cuts"
for L in $LAYERS; do
  OUT_SVG="$LAYERS_DIR/${L//./_}.svg"
  "$KICAD" pcb export svg \
    --layers "$L" \
    --page-size-mode 2 \
    --exclude-drawing-sheet \
    --mode-single \
    -o "$(win_path "$OUT_SVG")" \
    "$PCB_W" >/dev/null
done

echo "[4/6] Building components.json catalogue..."
node "$SITE_DIR/scripts/build_components.mjs"

echo "[5/6] Optimizing board.glb and building kv260.glb + enclosure.glb..."
node "$SITE_DIR/scripts/build_assets.mjs" "$RAW_GLB"

echo "[6/7] Building Rust core (site/core) and Slint WebAssembly HMI..."
mkdir -p "$SITE_DIR/core/pkg"
CARGO_TARGET_DIR="$TMP_DIR/core_target" cargo build \
  --manifest-path "$SITE_DIR/core/Cargo.toml" \
  --release --lib --target wasm32-unknown-unknown
wasm-bindgen --target web --no-typescript \
  --out-dir "$SITE_DIR/core/pkg" \
  "$TMP_DIR/core_target/wasm32-unknown-unknown/release/ias2rf_site_core.wasm"

mkdir -p "$SITE_DIR/hmi/pkg"
CARGO_TARGET_DIR="$TMP_DIR/hmi_target" cargo build \
  --manifest-path "$ROOT_DIR/sw/hmi/app/Cargo.toml" \
  --release --lib --target wasm32-unknown-unknown
wasm-bindgen --target web --no-typescript \
  --out-dir "$SITE_DIR/hmi/pkg" \
  "$TMP_DIR/hmi_target/wasm32-unknown-unknown/release/kria_hmi.wasm"

echo "[7/7] Copying doc figures..."
mkdir -p "$SITE_DIR/assets/img/sim" "$SITE_DIR/assets/img/integrations"
cp -f "$ROOT_DIR"/docs/img/sim/*.png "$SITE_DIR/assets/img/sim/"
cp -f "$ROOT_DIR"/docs/img/integrations/*.png "$SITE_DIR/assets/img/integrations/"
cp -f "$ROOT_DIR"/docs/img/board_top.png "$ROOT_DIR"/docs/img/board_bottom.png "$ROOT_DIR"/docs/img/board_iso.png "$SITE_DIR/assets/img/"
cp -f "$ROOT_DIR"/docs/img/case_v2_closed.jpg "$ROOT_DIR"/docs/img/case_v2_open.jpg "$SITE_DIR/assets/img/"

echo "Build complete. Asset sizes:"
ls -lh "$SITE_DIR/assets/"*.glb "$SITE_DIR/assets/"*.json "$SITE_DIR/core/pkg/" "$SITE_DIR/hmi/pkg/"
