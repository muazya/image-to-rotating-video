#!/usr/bin/env bash
# Run the full CPU-only image-to-turntable-video pipeline end to end.
#
# Stages (each is also runnable on its own):
#   01_make_inputs.py  -> input/front.png, input/back.png
#   02_segment.py      -> work/front_rgba.png, work/back_rgba.png
#   03_reconstruct.py  -> work/reconstruction.glb   (needs REPLICATE_API_TOKEN)
#   04_render.py       -> work/frames/frame_*.png
#   05_encode.sh       -> output/turntable.mp4
#
# Usage:
#   export REPLICATE_API_TOKEN=...
#   ./run_all.sh                 # full quality
#   FAST=1 ./run_all.sh          # Workbench render for a quick preview
#   SLUG=ArmChair_01 ./run_all.sh
set -euo pipefail
cd "$(dirname "$0")"

# activate venv if present
if [ -f ".venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

SLUG="${SLUG:-WoodenChair_01}"
RENDER_FLAGS=""
[ "${FAST:-0}" = "1" ] && RENDER_FLAGS="--fast"

if [ -z "${REPLICATE_API_TOKEN:-}" ]; then
  echo "!! REPLICATE_API_TOKEN is not set — Step 2 (03_reconstruct.py) will fail." >&2
  echo "   export REPLICATE_API_TOKEN=... before running." >&2
fi

echo "== Step 0: make inputs (slug=$SLUG) =="
python 01_make_inputs.py --slug "$SLUG"

echo "== Step 1: segment =="
python 02_segment.py

echo "== Step 2: reconstruct (Replicate) =="
python 03_reconstruct.py

echo "== Step 3: turntable render ${RENDER_FLAGS} =="
python 04_render.py $RENDER_FLAGS

echo "== Step 4: encode =="
bash 05_encode.sh

echo "== DONE -> output/turntable.mp4 =="
