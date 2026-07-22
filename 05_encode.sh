#!/usr/bin/env bash
# Step 4 - Encode the turntable frames into an MP4 (H.264 / yuv420p, high quality).
#
# Usage:
#   ./05_encode.sh                 # 30 fps, work/frames -> output/turntable.mp4
#   FPS=30 CRF=17 ./05_encode.sh   # override fps / quality via env
set -euo pipefail

FRAMES_DIR="${FRAMES_DIR:-work/frames}"
OUT="${OUT:-output/turntable.mp4}"
FPS="${FPS:-30}"
CRF="${CRF:-17}"   # lower = higher quality (17 is visually ~lossless)

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "[encode] ffmpeg not found on PATH" >&2
  exit 1
fi

count=$(find "$FRAMES_DIR" -maxdepth 1 -name 'frame_*.png' 2>/dev/null | wc -l)
if [ "$count" -eq 0 ]; then
  echo "[encode] no frames in $FRAMES_DIR — run 04_render.py first" >&2
  exit 1
fi

mkdir -p "$(dirname "$OUT")"
echo "[encode] $count frames @ ${FPS}fps, crf=${CRF} -> $OUT"

ffmpeg -y \
  -framerate "$FPS" \
  -i "$FRAMES_DIR/frame_%04d.png" \
  -c:v libx264 \
  -preset slow \
  -crf "$CRF" \
  -pix_fmt yuv420p \
  -movflags +faststart \
  "$OUT"

echo "[encode] done -> $OUT"
