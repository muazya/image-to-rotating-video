#!/usr/bin/env python3
"""
Step 1 - Object isolation (CPU).

Remove the background from ./input/front.png and ./input/back.png with rembg and
save RGBA cutouts to ./work/front_rgba.png and ./work/back_rgba.png.

Usage:
    python 02_segment.py
    python 02_segment.py --model u2net        # or isnet-general-use, etc.
"""
import argparse
import os
import sys

INPUT_DIR = "input"
WORK_DIR = "work"

PAIRS = [
    (os.path.join(INPUT_DIR, "front.png"), os.path.join(WORK_DIR, "front_rgba.png")),
    (os.path.join(INPUT_DIR, "back.png"), os.path.join(WORK_DIR, "back_rgba.png")),
]


def main():
    ap = argparse.ArgumentParser(description="rembg background removal (CPU)")
    ap.add_argument("--model", default="u2net",
                    help="rembg model name (default: u2net)")
    args = ap.parse_args()

    # imported here so --help works without the (heavy) deps installed
    from rembg import new_session, remove
    from PIL import Image

    os.makedirs(WORK_DIR, exist_ok=True)
    session = new_session(args.model)

    missing = [src for src, _ in PAIRS if not os.path.exists(src)]
    if missing:
        sys.exit(f"[segment] missing inputs: {missing}. Run 01_make_inputs.py first.")

    for src, dst in PAIRS:
        img = Image.open(src).convert("RGBA")
        out = remove(img, session=session)  # returns RGBA with cut-out alpha
        out.save(dst)
        # quick sanity: how much of the image survived the cut
        alpha = out.split()[-1]
        kept = sum(alpha.getdata()) / (255 * out.width * out.height)
        print(f"[segment] {src} -> {dst}  (kept {kept:6.1%} as foreground)")
        if kept < 0.01:
            print(f"[segment] WARNING: near-empty mask for {src}; check the input.")

    print("[segment] done.")


if __name__ == "__main__":
    main()
