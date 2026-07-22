#!/usr/bin/env python3
"""
Step 0 - Generate test input images.

1. Download a CC0 textured chair (glTF) from Poly Haven into ./assets/<slug>/.
   If the download fails, fall back to any *.glb already sitting in ./assets/.
2. Render it headless in Blender from FRONT (0deg) and BACK (180deg) at 1024x1024
   with neutral studio lighting on a plain light-gray background.
3. Save ./input/front.png and ./input/back.png.

Usage:
    python 01_make_inputs.py
    python 01_make_inputs.py --slug ArmChair_01 --res 1024 --samples 64
    python 01_make_inputs.py --asset ./assets/mychair.glb      # skip download
    python 01_make_inputs.py --engine BLENDER_WORKBENCH        # fast preview

Poly Haven chair slugs that work well: WoodenChair_01 (default), ArmChair_01,
GreenChair_01, SchoolChair_01, chinese_armchair.
"""
import argparse
import glob
import os
import subprocess
import sys

import requests

ASSETS_DIR = "assets"
INPUT_DIR = "input"
BLENDER_SCRIPT = os.path.join("blender", "render_inputs.py")
PH_FILES_API = "https://api.polyhaven.com/files/{slug}"


def pick_resolution(section):
    """Prefer the smallest available resolution (fast download, plenty for POC)."""
    for res in ("1k", "2k", "4k", "8k"):
        if res in section:
            return res
    # otherwise take whatever is first
    return next(iter(section))


def download_file(url, dest):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 16):
                f.write(chunk)
    return dest


def download_polyhaven_gltf(slug):
    """Download the glTF + its texture/bin includes. Returns local .gltf path."""
    print(f"[make_inputs] querying Poly Haven files for '{slug}' ...")
    meta = requests.get(PH_FILES_API.format(slug=slug), timeout=60).json()
    if "gltf" not in meta:
        raise RuntimeError(f"no glTF variant listed for '{slug}'")

    res = pick_resolution(meta["gltf"])
    node = meta["gltf"][res]["gltf"]
    out_dir = os.path.join(ASSETS_DIR, slug)

    gltf_name = os.path.basename(node["url"])
    gltf_path = os.path.join(out_dir, gltf_name)
    print(f"[make_inputs] downloading {res} glTF -> {gltf_path}")
    download_file(node["url"], gltf_path)

    # includes are keyed by their path relative to the .gltf (textures/*, *.bin)
    for rel_path, info in node.get("include", {}).items():
        dest = os.path.join(out_dir, rel_path)
        download_file(info["url"], dest)
        print(f"[make_inputs]   + {rel_path}")

    return gltf_path


def resolve_model(args):
    """Return a local model path, using --asset / download / local-glb fallback."""
    if args.asset:
        if not os.path.exists(args.asset):
            sys.exit(f"[make_inputs] --asset not found: {args.asset}")
        print(f"[make_inputs] using provided asset: {args.asset}")
        return args.asset

    try:
        return download_polyhaven_gltf(args.slug)
    except Exception as exc:
        print(f"[make_inputs] Poly Haven download failed: {exc}")
        local = sorted(glob.glob(os.path.join(ASSETS_DIR, "*.glb")) +
                       glob.glob(os.path.join(ASSETS_DIR, "*.gltf")))
        if local:
            print(f"[make_inputs] falling back to local model: {local[0]}")
            return local[0]
        sys.exit(
            "[make_inputs] No model available.\n"
            f"  Place a CC0 .glb in ./{ASSETS_DIR}/ and re-run, e.g.:\n"
            f"    cp /path/to/chair.glb ./{ASSETS_DIR}/\n"
            f"    python 01_make_inputs.py --asset ./{ASSETS_DIR}/chair.glb"
        )


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


def render_inputs(model_path, args):
    os.makedirs(INPUT_DIR, exist_ok=True)
    out_front = os.path.join(INPUT_DIR, "front.png")
    out_back = os.path.join(INPUT_DIR, "back.png")
    cmd = [
        "blender", "--background", "--python", BLENDER_SCRIPT, "--",
        model_path, out_front, out_back,
        "--engine", args.engine,
        "--samples", str(args.samples),
        "--res", str(args.res),
    ]
    print(f"[make_inputs] running Blender: {' '.join(cmd)}")
    subprocess.run(cmd, check=True, env=blender_env())
    for p in (out_front, out_back):
        if not os.path.exists(p):
            sys.exit(f"[make_inputs] expected output missing: {p}")
    print(f"[make_inputs] done -> {out_front}, {out_back}")


def main():
    ap = argparse.ArgumentParser(description="Step 0: make front/back input renders")
    ap.add_argument("--slug", default="WoodenChair_01", help="Poly Haven asset slug")
    ap.add_argument("--asset", default=None, help="path to a local .glb/.gltf (skip download)")
    ap.add_argument("--engine", default="CYCLES",
                    choices=["CYCLES", "BLENDER_WORKBENCH"])
    ap.add_argument("--samples", type=int, default=64)
    ap.add_argument("--res", type=int, default=1024)
    args = ap.parse_args()

    model_path = resolve_model(args)
    render_inputs(model_path, args)


if __name__ == "__main__":
    main()
