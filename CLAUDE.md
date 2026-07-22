# CLAUDE.md — project state & handoff

Context for Claude Code picking this project up on another machine. This file is
the source of truth for **what exists, what's done, and how to run it**. (Claude
Code auto-loads `CLAUDE.md`.)

## What this is
A **CPU-only proof-of-concept**: turn **two product photos (front + back)** into a
**360° turntable MP4**. GPU-heavy 3D reconstruction is offloaded to **Replicate**;
everything else (Blender render, ffmpeg encode, rembg) runs on CPU. Fully
containerized with Docker.

Repo: **https://github.com/goodluck1103/image-to-rotating-video**
Release with demo video: **v0.1.0** (`turntable.mp4` asset, embedded in README).

## Current status: COMPLETE ✅
The pipeline is built, containerized, validated end-to-end with real runs, and
pushed to GitHub. Nothing is half-finished. Recent commits:
- `e2d1504` docs: embed turntable MP4 via GitHub Release for inline playback
- `dc8425d` CPU-only image-to-360°-turntable pipeline (POC)

All 5 stages were validated in-container producing correct output. Step 2 was run
live on Replicate (both models) — real reconstruction + textured turntable
produced. Two demo videos were generated: textured (TRELLIS) and shape-only
(Hunyuan3D-2mv).

## Pipeline (numbered stages, each rerunnable)
```
front.png + back.png
  01_make_inputs.py     Blender: render a Poly Haven chair as test input (front/back)
  02_segment.py         rembg: background removal -> work/*_rgba.png
  03_reconstruct.py     Replicate: image-to-3D -> work/reconstruction.glb
  04_render.py          Blender: 360° turntable, 120 frames, CPU Cycles + OIDN
  05_encode.sh          ffmpeg: frames -> output/turntable.mp4 (H.264/yuv420p)
run_all.sh              runs 01..05 in order
blender/render_inputs.py, blender/render_turntable.py   (invoked by 01 and 04)
```

## What's in the repo vs. NOT (gitignored — must be regenerated)
Committed: all scripts, `blender/`, `Dockerfile`, `docker-compose.yml`,
`requirements.txt`, `README.md`, and `docs/` (example front/back PNGs, a preview
GIF, and the demo MP4).
**Gitignored / absent after a fresh clone:** `.venv/`, `assets/` (downloaded
chair), `input/`, `work/`, `output/`. These are produced by running the pipeline.

## Running it on the new machine
Everything runs through Docker — no host Blender/ffmpeg needed.
```bash
export REPLICATE_API_TOKEN=r8_...          # required for Step 2 (never commit it)
docker compose build                        # bakes Blender 4.2 LTS + ffmpeg + deps
docker compose run --rm pipeline            # full run_all -> output/turntable.mp4
# individual stages:
docker compose run --rm pipeline python 01_make_inputs.py --slug WoodenChair_01
docker compose run --rm pipeline python 02_segment.py
docker compose run --rm pipeline python 03_reconstruct.py            # multi-view Hunyuan3D-2mv
docker compose run --rm pipeline python 03_reconstruct.py --model trellis   # textured
docker compose run --rm pipeline python 04_render.py [--fast]
docker compose run --rm pipeline bash 05_encode.sh
```
There's also a host (non-Docker) path documented in `README.md`, but Docker is the
supported route.

## Step 2 — Replicate models (field names/versions read from live model pages)
| Model | Role | Image input | Output | ~Cost | Texture? |
|---|---|---|---|---|---|
| `tencent/hunyuan3d-2mv` | **primary** multi-view | `front_image`,`back_image` | GLB uri | $0.10 | **shape only** (gray verts) |
| `firtoz/trellis` (`--model trellis`) | textured | `images[]` (+`generate_model=True`) | `model_file` | $0.034 | **yes** (PBR 1024² tex) |
| `ndreca/hunyuan3d-2` | single-image fallback | `image` | `mesh` | $0.15 | shape only |

`03_reconstruct.py` default = multi-view, auto-falls back to single-image on
failure. **Key finding:** hunyuan3d-2mv gives great geometry but NO texture (clay
look); use `--model trellis` for a textured result.

## Environment reality & gotchas (important — the original task assumptions were wrong)
- **No local GPU.** Design is CPU + Replicate. Don't assume CUDA.
- **Docker daemon:** on the original machine it ran via **Docker Desktop**
  (`docker context use desktop-linux`, works without sudo). The systemd socket
  needed sudo (user not in `docker` group). On a new machine just ensure the Docker
  daemon is up.
- **`REPLICATE_API_TOKEN` is passed via env only — never written to any file or
  committed.** The token used during development is NOT in the repo.
- **Image is Python 3.12** to match pinned deps (onnxruntime 1.27 has no 3.10
  wheel). Blender uses its own bundled Python regardless.
- **Blender:** the Docker image bundles official **Blender 4.2.9 LTS** (has Cycles +
  OpenImageDenoise). The Ubuntu `apt` Blender lacks OIDN and uses system python —
  avoid it. Scripts launch Blender with a scrubbed env (no PYTHONPATH/HOME/VENV) so
  it doesn't grab a venv Python and crash the glTF importer.
- **Blender framing:** glTF nests meshes under node empties — centering transforms
  hierarchy *roots*, and the camera auto-fits the bounding sphere and aims at the
  true center. (See `center_and_normalize` / `setup_camera` in `blender/`.)
- **OIDN detection:** the denoiser enum reports empty headless even when OIDN works;
  code detects OIDN by *trying to assign* the denoiser and catching failure.
- **`--fast` (Workbench) preview** renders a dark background in a headless container
  (no GL context); the default **Cycles** path gives the spec'd light-gray bg.

## Not included / removed
- **Step 2b local TripoSR fallback: intentionally NOT included.** It was attempted
  and removed at the user's request (heavy `torch` + compiled `torchmcubes` stack,
  dependency conflicts). `README.md` notes it's not included. Do not re-add unless
  asked.

## Git / GitHub
- Git identity for this repo: `goodluck1103` / `andriiholovanov3@gmail.com`.
- Remote `origin` = the GitHub repo above; branch `main`.
- Pushing/releases use `gh` (GitHub CLI). On a new machine you'd need
  `gh auth login` (device flow) as **goodluck1103** before pushing.
- Commit trailer used on this project: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
