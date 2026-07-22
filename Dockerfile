# CPU-only image-to-rotating-video pipeline.
# Bakes in: official Blender 4.2 LTS (Cycles + OpenImageDenoise, bundled Python),
# ffmpeg, and the Python deps. No GPU required (Step 2 is offloaded to Replicate).
# Python 3.12 to match the validated/pinned deps in requirements.txt exactly.
# (Blender bundles its own Python, so this only governs the pipeline's pip deps.)
FROM python:3.12-slim-bookworm

ARG BLENDER_VERSION=4.2.9
ARG BLENDER_MAJOR=4.2

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1

# ---- system deps: ffmpeg + Blender headless runtime libraries -------------
RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg \
      wget ca-certificates xz-utils \
      libgl1 libglx-mesa0 libglu1-mesa libegl1 \
      libx11-6 libxi6 libxxf86vm1 libxfixes3 libxrender1 libxext6 \
      libxkbcommon0 libsm6 libxrandr2 libxinerama1 libxcursor1 \
      libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# ---- official Blender (self-contained: bundles Python + numpy + OIDN) ------
RUN wget -q "https://download.blender.org/release/Blender${BLENDER_MAJOR}/blender-${BLENDER_VERSION}-linux-x64.tar.xz" \
      -O /tmp/blender.tar.xz \
    && mkdir -p /opt/blender \
    && tar -xJf /tmp/blender.tar.xz -C /opt/blender --strip-components=1 \
    && ln -sf /opt/blender/blender /usr/local/bin/blender \
    && rm /tmp/blender.tar.xz \
    && blender --version

WORKDIR /app

# ---- python deps (cached layer) -------------------------------------------
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---- pre-cache the rembg u2net model so Step 1 needs no runtime download ---
RUN python -c "from rembg import new_session; new_session('u2net')"

# ---- pipeline code ---------------------------------------------------------
COPY . .
RUN chmod +x 01_make_inputs.py 02_segment.py 03_reconstruct.py 04_render.py \
             05_encode.sh run_all.sh

# REPLICATE_API_TOKEN is provided at run time (-e), never baked into the image.
CMD ["bash", "run_all.sh"]
