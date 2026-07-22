#!/usr/bin/env python3
"""
Step 2 - Image-to-3D reconstruction via a hosted Replicate model.

Primary path: multi-view Hunyuan3D-2 (`tencent/hunyuan3d-2mv`), passing the
front + back RGBA cutouts together (fields `front_image` / `back_image`).
Fallback: single-image Hunyuan3D-2 (`ndreca/hunyuan3d-2`, field `image`) on the
front cutout only -- this is logged clearly.

The resulting GLB is downloaded to ./work/reconstruction.glb.

Requires REPLICATE_API_TOKEN in the environment.

Usage:
    export REPLICATE_API_TOKEN=...
    python 03_reconstruct.py                 # multi-view, auto-fallback on error
    python 03_reconstruct.py --single        # force single-image
    python 03_reconstruct.py --model trellis # use firtoz/trellis (images[] array)

Model input schemas below were read from the live Replicate model pages (not
guessed). Versions are pinned for reproducibility; update if a model is retired.
"""
import argparse
import os
import sys

WORK_DIR = "work"
FRONT = os.path.join(WORK_DIR, "front_rgba.png")
BACK = os.path.join(WORK_DIR, "back_rgba.png")
OUT_GLB = os.path.join(WORK_DIR, "reconstruction.glb")

# Pinned model versions (schema verified from each model's Replicate page).
MODELS = {
    "hunyuan3d-2mv": {
        "ref": "tencent/hunyuan3d-2mv:71798fbc3c9f7b7097e3bb85496e5a797d8b8f616b550692e7c3e176a8e9e5db",
        "kind": "multiview",       # uses front_image/back_image
        "output": "uri",           # returns a plain GLB uri
        "cost_usd": 0.10,
    },
    "hunyuan3d-2-single": {
        "ref": "ndreca/hunyuan3d-2:0602bae6db1ce420f2690339bf2feb47e18c0c722a1f02e9db9abd774abaff5d",
        "kind": "single",          # uses image
        "output": "mesh",          # returns {"mesh": uri}
        "cost_usd": 0.15,
    },
    "trellis": {
        "ref": "firtoz/trellis:4876f2a8da1c544772dffa32e8889da4a1bab3a1f5c1937bfcfccb99ae347251",
        "kind": "images_array",    # uses images[]; must set generate_model=True
        "output": "model_file",    # returns {"model_file": uri, ...}
        "cost_usd": 0.034,
    },
}


def require_inputs(paths):
    missing = [p for p in paths if not os.path.exists(p)]
    if missing:
        sys.exit(f"[reconstruct] missing inputs: {missing}. Run 02_segment.py first.")


def save_output(output, dest):
    """Resolve a Replicate output (FileOutput / str uri / dict / list) to bytes.

    With replicate>=1.0 and use_file_output=True, uri outputs arrive as
    FileOutput objects exposing .read(); we also handle raw str URLs and the
    dict/list shapes different models return.
    """
    import requests

    def _first_fileish(obj):
        if hasattr(obj, "read") or isinstance(obj, str):
            return obj
        if isinstance(obj, dict):
            for key in ("mesh", "model_file", "glb", "file", "output"):
                if key in obj and obj[key]:
                    return obj[key]
            for v in obj.values():
                got = _first_fileish(v)
                if got is not None:
                    return got
        if isinstance(obj, (list, tuple)) and obj:
            return _first_fileish(obj[0])
        return None

    target = _first_fileish(output)
    if target is None:
        sys.exit(f"[reconstruct] could not find a file in model output: {output!r}")

    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if hasattr(target, "read"):                      # FileOutput
        data = target.read()
        with open(dest, "wb") as f:
            f.write(data)
    else:                                            # str URL
        with requests.get(str(target), stream=True, timeout=300) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=1 << 16):
                    f.write(chunk)
    return dest


def build_input(spec, use_back):
    """Open file handles + build the input dict for a model kind."""
    kind = spec["kind"]
    if kind == "multiview":
        data = {"front_image": open(FRONT, "rb"), "file_type": "glb"}
        if use_back:
            data["back_image"] = open(BACK, "rb")
        return data
    if kind == "single":
        return {"image": open(FRONT, "rb")}
    if kind == "images_array":
        imgs = [open(FRONT, "rb")]
        if use_back:
            imgs.append(open(BACK, "rb"))
        # generate_model MUST be true for TRELLIS to emit a GLB (default is false)
        return {"images": imgs, "generate_model": True}
    raise ValueError(f"unknown kind: {kind}")


def run_model(name, use_back):
    import replicate

    spec = MODELS[name]
    print(f"[reconstruct] model={name}  ref={spec['ref'].split(':')[0]}  "
          f"kind={spec['kind']}  est_cost=${spec['cost_usd']:.3f}/run")
    if spec["kind"] != "single" and not use_back:
        print("[reconstruct] (only front view supplied)")
    output = replicate.run(spec["ref"], input=build_input(spec, use_back))
    return save_output(output, OUT_GLB)


def main():
    ap = argparse.ArgumentParser(description="Step 2: hosted image-to-3D")
    ap.add_argument("--single", action="store_true",
                    help="force single-image reconstruction (front only)")
    ap.add_argument("--model", default=None, choices=list(MODELS.keys()),
                    help="pick an explicit model (default: hunyuan3d-2mv)")
    args = ap.parse_args()

    if not os.environ.get("REPLICATE_API_TOKEN"):
        sys.exit("[reconstruct] REPLICATE_API_TOKEN is not set. "
                 "export REPLICATE_API_TOKEN=... and retry.")

    if args.model:
        require_inputs([FRONT])
        out = run_model(args.model, use_back=os.path.exists(BACK))
        print(f"[reconstruct] wrote {out}")
        return

    if args.single:
        require_inputs([FRONT])
        out = run_model("hunyuan3d-2-single", use_back=False)
        print(f"[reconstruct] wrote {out} (single-image, front only)")
        return

    # default: multi-view primary, auto-fallback to single-image on any failure
    require_inputs([FRONT, BACK])
    try:
        out = run_model("hunyuan3d-2mv", use_back=True)
        print(f"[reconstruct] wrote {out} (multi-view front+back)")
    except Exception as exc:
        print(f"[reconstruct] !! multi-view failed: {exc}")
        print("[reconstruct] !! FALLING BACK to single-image (front only) via "
              "ndreca/hunyuan3d-2")
        out = run_model("hunyuan3d-2-single", use_back=False)
        print(f"[reconstruct] wrote {out} (FALLBACK single-image, front only)")


if __name__ == "__main__":
    main()
