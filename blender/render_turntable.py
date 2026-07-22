"""
Blender headless script: import a GLB, center + normalize, three-point studio
lighting, and orbit the camera 360deg rendering a turntable frame sequence.

Invoked by 04_render.py as:
    blender --background --python blender/render_turntable.py -- \
        <glb_path> <frames_dir> \
        [--frames 120] [--res 1024] [--engine CYCLES|BLENDER_WORKBENCH] [--samples 64]

CPU-only friendly (Cycles CPU + OpenImageDenoise). --engine BLENDER_WORKBENCH is
the fast preview path (04_render.py's --fast flag). Never uses Eevee.
"""
import bpy
import sys
import math
import os
from mathutils import Vector


argv = sys.argv
argv = argv[argv.index("--") + 1:] if "--" in argv else []
if len(argv) < 2:
    raise SystemExit("usage: render_turntable.py -- <glb> <frames_dir> "
                     "[--frames N] [--res N] [--engine ...] [--samples N]")

glb_path, frames_dir = argv[0], argv[1]

def _opt(flag, default):
    return argv[argv.index(flag) + 1] if flag in argv else default

n_frames = int(_opt("--frames", "120"))
res = int(_opt("--res", "1024"))
engine = _opt("--engine", "CYCLES")
samples = int(_opt("--samples", "64"))

BG_GRAY = 0.8
os.makedirs(frames_dir, exist_ok=True)


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def import_glb(path):
    bpy.ops.import_scene.gltf(filepath=path)
    return [o for o in bpy.context.scene.objects if o.type == "MESH"]


def mesh_world_bounds(meshes):
    mins = Vector((math.inf, math.inf, math.inf))
    maxs = Vector((-math.inf, -math.inf, -math.inf))
    for o in meshes:
        for corner in o.bound_box:
            wc = o.matrix_world @ Vector(corner)
            for i in range(3):
                mins[i] = min(mins[i], wc[i])
                maxs[i] = max(maxs[i], wc[i])
    return mins, maxs


def center_and_normalize(meshes, target_size=2.0):
    # transform the hierarchy *roots* (glTF nests meshes under node empties)
    roots = [o for o in bpy.context.scene.objects if o.parent is None]
    parent = bpy.data.objects.new("MODEL_ROOT", None)
    bpy.context.scene.collection.objects.link(parent)
    for o in roots:
        o.parent = parent
    bpy.context.view_layer.update()  # parent at identity -> world unchanged
    mins, maxs = mesh_world_bounds(meshes)
    center = (mins + maxs) / 2.0
    size = maxs - mins
    max_dim = max(size.x, size.y, size.z) or 1.0
    scale = target_size / max_dim
    parent.scale = (scale, scale, scale)
    parent.location = -center * scale
    bpy.context.view_layer.update()
    return parent


def setup_world():
    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (BG_GRAY, BG_GRAY, BG_GRAY, 1.0)
    bg.inputs[1].default_value = 1.0
    bpy.context.scene.world = world


def add_area_light(name, location, energy, target, size=6.0):
    data = bpy.data.lights.new(name, type="AREA")
    data.energy = energy
    data.size = size
    obj = bpy.data.objects.new(name, data)
    obj.location = location
    bpy.context.scene.collection.objects.link(obj)
    track = obj.constraints.new(type="TRACK_TO")
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"
    track.target = target
    return obj


def setup_three_point(target):
    add_area_light("Key", (4, -4, 4), 900, target, size=6)
    add_area_light("Fill", (-4, -2, 2), 350, target, size=9)
    add_area_light("Rim", (0, 5, 5), 700, target, size=6)


def bounding_sphere_radius(meshes):
    """Farthest AABB corner from origin (model already centered+normalized)."""
    mins, maxs = mesh_world_bounds(meshes)
    corners = [Vector((x, y, z))
               for x in (mins.x, maxs.x)
               for y in (mins.y, maxs.y)
               for z in (mins.z, maxs.z)]
    return max(c.length for c in corners)


def setup_camera(meshes, margin=1.25, height_frac=0.15):
    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50
    cam = bpy.data.objects.new("Cam", cam_data)
    bpy.context.scene.collection.objects.link(cam)
    # orbit pivot at object center (origin after normalize)
    pivot = bpy.data.objects.new("PIVOT", None)
    bpy.context.scene.collection.objects.link(pivot)
    pivot.location = (0, 0, 0)
    cam.parent = pivot

    r = bounding_sphere_radius(meshes)
    distance = r / math.sin(cam_data.angle / 2.0) * margin
    cam.location = (0.0, -distance, height_frac * r)

    track = cam.constraints.new(type="TRACK_TO")
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"
    track.target = pivot
    bpy.context.scene.camera = cam
    print(f"[render_turntable] frame: sphere_r={r:.2f} cam_dist={distance:.2f}")
    return cam, pivot


def setup_render(engine, samples, res):
    scene = bpy.context.scene
    scene.render.resolution_x = res
    scene.render.resolution_y = res
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    if engine == "BLENDER_WORKBENCH":
        scene.render.engine = "BLENDER_WORKBENCH"
        # Workbench ignores the world color; set a solid light-gray viewport bg
        scene.display.shading.background_type = "VIEWPORT"
        scene.display.shading.background_color = (BG_GRAY, BG_GRAY, BG_GRAY)
    else:
        scene.render.engine = "CYCLES"
        scene.cycles.device = "CPU"
        scene.cycles.samples = samples
        setup_denoising(scene, "render_turntable")


def setup_denoising(scene, tag):
    """Enable OpenImageDenoise if this Blender build supports it, else disable
    denoising. We try to *assign* the denoiser rather than read enum_items --
    the enum reports empty in headless/background mode even when OIDN works,
    while a build genuinely without OIDN (e.g. the Ubuntu apt package) raises
    on assignment."""
    scene.cycles.use_denoising = True
    for name in ("OPENIMAGEDENOISE", "OPTIX"):
        try:
            scene.cycles.denoiser = name
            print(f"[{tag}] denoiser={name}")
            return
        except Exception:
            continue
    scene.cycles.use_denoising = False
    print(f"[{tag}] WARNING: no denoiser in this Blender build; denoising OFF "
          "(expect more noise at low samples)")


def main():
    reset_scene()
    meshes = import_glb(glb_path)
    if not meshes:
        raise SystemExit("no mesh objects imported from GLB")
    center_and_normalize(meshes)
    setup_world()
    cam, pivot = setup_camera(meshes)
    setup_three_point(pivot)
    setup_render(engine, samples, res)

    print(f"[render_turntable] engine={bpy.context.scene.render.engine} "
          f"frames={n_frames} samples={samples} res={res}")

    for i in range(n_frames):
        pivot.rotation_euler[2] = 2.0 * math.pi * (i / n_frames)
        bpy.context.view_layer.update()
        out = os.path.join(frames_dir, f"frame_{i:04d}.png")
        bpy.context.scene.render.filepath = out
        bpy.ops.render.render(write_still=True)
        if i % 10 == 0:
            print(f"[render_turntable] frame {i + 1}/{n_frames}")

    print(f"[render_turntable] done -> {frames_dir}")


main()
