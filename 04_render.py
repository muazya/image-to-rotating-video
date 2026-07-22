#!/usr/bin/env python3
"""
Step 3 - Turntable render (CPU).

Import ./work/reconstruction.glb in Blender, center + normalize scale, apply
three-point studio lighting, orbit the camera 360deg over 4s @ 30fps (120 frames)
at 1024x1024, and write PNG frames to ./work/frames/.

Engine: Cycles on CPU (~64 samples + OpenImageDenoise) by default.
--fast switches to the Workbench engine for quick iteration.

Usage:
    python 04_render.py
    python 04_render.py --fast
    python 04_render.py --frames 120 --res 1024 --samples 64
"""
import argparse
import glob
import os
import subprocess
import sys

WORK_DIR = "work"
GLB = os.path.join(WORK_DIR, "reconstruction.glb")
FRAMES_DIR = os.path.join(WORK_DIR, "frames")
BLENDER_SCRIPT = os.path.join("blender", "render_turntable.py")


def blender_env():
    """Scrubbed env so Blender uses the SYSTEM python (which has numpy), not the
    pyenv/venv python -- otherwise its glTF importer crashes on a bundled-python
    mismatch (undefined symbol / ModuleNotFoundError: numpy)."""
    env = os.environ.copy()
    for k in ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONEXECUTABLE",
              "VIRTUAL_ENV"):
        env.pop(k, None)
    env["PATH"] = "/usr/local/bin:/usr/bin:/bin"
    return env


def clean_frames():
    os.makedirs(FRAMES_DIR, exist_ok=True)
    for f in glob.glob(os.path.join(FRAMES_DIR, "frame_*.png")):
        os.remove(f)


def main():
    ap = argparse.ArgumentParser(description="Step 3: turntable frame render")
    ap.add_argument("--fast", action="store_true",
                    help="use Workbench engine for a quick preview")
    ap.add_argument("--frames", type=int, default=120, help="frame count (120 = 4s@30fps)")
    ap.add_argument("--res", type=int, default=1024)
    ap.add_argument("--samples", type=int, default=64, help="Cycles samples (ignored in --fast)")
    args = ap.parse_args()

    if not os.path.exists(GLB):
        sys.exit(f"[render] {GLB} not found. Run 03_reconstruct.py first.")

    engine = "BLENDER_WORKBENCH" if args.fast else "CYCLES"
    clean_frames()

    cmd = [
        "blender", "--background", "--python", BLENDER_SCRIPT, "--",
        GLB, FRAMES_DIR,
        "--frames", str(args.frames),
        "--res", str(args.res),
        "--engine", engine,
        "--samples", str(args.samples),
    ]
    print(f"[render] engine={engine} frames={args.frames} res={args.res}")
    print(f"[render] running Blender: {' '.join(cmd)}")
    subprocess.run(cmd, check=True, env=blender_env())

    produced = sorted(glob.glob(os.path.join(FRAMES_DIR, "frame_*.png")))
    if len(produced) != args.frames:
        print(f"[render] WARNING: expected {args.frames} frames, got {len(produced)}")
    print(f"[render] done -> {len(produced)} frames in {FRAMES_DIR}")


if __name__ == "__main__":
    main()
