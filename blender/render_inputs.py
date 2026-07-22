"""
Blender headless script: render an object from FRONT (0deg) and BACK (180deg).

Invoked by 01_make_inputs.py as:
    blender --background --python blender/render_inputs.py -- \
        <model_path> <out_front_png> <out_back_png> \
        [--engine CYCLES|BLENDER_WORKBENCH] [--samples 64] [--res 1024]

CPU-only friendly: defaults to Cycles with CPU device + OpenImageDenoise at low
samples. Never uses Eevee (which needs a GPU/EGL context and fails headless here).
Background is a plain light-gray world color.
"""
import bpy
import sys
import math
from mathutils import Vector


# ---------------------------------------------------------------------------
# arg parsing (everything after the standalone "--")
# ---------------------------------------------------------------------------
argv = sys.argv
argv = argv[argv.index("--") + 1:] if "--" in argv else []
if len(argv) < 3:
    raise SystemExit("usage: render_inputs.py -- <model> <front.png> <back.png> "
                     "[--engine ...] [--samples N] [--res N]")

model_path, out_front, out_back = argv[0], argv[1], argv[2]

def _opt(flag, default):
    return argv[argv.index(flag) + 1] if flag in argv else default

engine = _opt("--engine", "CYCLES")
samples = int(_opt("--samples", "64"))
res = int(_opt("--res", "1024"))

BG_GRAY = 0.8  # light-gray background


# ---------------------------------------------------------------------------
# scene reset + import
# ---------------------------------------------------------------------------
def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def import_model(path):
    lower = path.lower()
    if lower.endswith((".glb", ".gltf")):
        bpy.ops.import_scene.gltf(filepath=path)
    elif lower.endswith((".fbx",)):
        bpy.ops.import_scene.fbx(filepath=path)
    elif lower.endswith((".obj",)):
        bpy.ops.wm.obj_import(filepath=path)
    else:
        raise SystemExit(f"unsupported model format: {path}")
    return [o for o in bpy.context.scene.objects if o.type == "MESH"]


def mesh_world_bounds(meshes):
    """Combined world-space AABB min/max over all mesh objects."""
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
    """Move combined bbox center to the origin and scale so the max dimension ==
    target_size.

    We parent every current top-level object (glTF imports nest meshes under node
    empties, so we must transform the hierarchy *roots*, not the mesh objects) to
    a single empty and transform that empty.
    """
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


# ---------------------------------------------------------------------------
# world / lighting / camera
# ---------------------------------------------------------------------------
def setup_world():
    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (BG_GRAY, BG_GRAY, BG_GRAY, 1.0)
    bg.inputs[1].default_value = 1.0
    bpy.context.scene.world = world


def add_area_light(name, location, energy, size=5.0):
    data = bpy.data.lights.new(name, type="AREA")
    data.energy = energy
    data.size = size
    obj = bpy.data.objects.new(name, data)
    obj.location = location
    bpy.context.scene.collection.objects.link(obj)
    # aim at origin
    track = obj.constraints.new(type="TRACK_TO")
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"
    return obj


def setup_studio_lights(target):
    # neutral, roughly even studio fill: key + fill + top
    key = add_area_light("Key", (3, -3, 4), energy=800, size=6)
    fill = add_area_light("Fill", (-3, -2, 2), energy=350, size=8)
    top = add_area_light("Top", (0, 2, 5), energy=500, size=8)
    for lgt in (key, fill, top):
        lgt.constraints[0].target = target


def bounding_sphere_radius(meshes):
    """Radius of a sphere centered at the origin enclosing the (already
    centered+normalized) model -- i.e. the farthest AABB corner from origin."""
    mins, maxs = mesh_world_bounds(meshes)
    corners = [Vector((x, y, z))
               for x in (mins.x, maxs.x)
               for y in (mins.y, maxs.y)
               for z in (mins.z, maxs.z)]
    return max(c.length for c in corners)


def setup_camera(meshes, margin=1.25, height_frac=0.12):
    """Aim at the object's true center (world origin after normalize) and back
    the camera off far enough to frame the whole bounding sphere with margin."""
    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50
    cam = bpy.data.objects.new("Cam", cam_data)
    bpy.context.scene.collection.objects.link(cam)

    # a dedicated target empty AT the object center (not the offset model root)
    target = bpy.data.objects.new("CAM_TARGET", None)
    bpy.context.scene.collection.objects.link(target)
    target.location = (0.0, 0.0, 0.0)

    r = bounding_sphere_radius(meshes)
    distance = r / math.sin(cam_data.angle / 2.0) * margin
    cam.location = (0.0, -distance, height_frac * r)

    track = cam.constraints.new(type="TRACK_TO")
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"
    track.target = target
    bpy.context.scene.camera = cam
    print(f"[render_inputs] frame: sphere_r={r:.2f} cam_dist={distance:.2f}")
    return cam, target


# ---------------------------------------------------------------------------
# render settings
# ---------------------------------------------------------------------------
def setup_render(engine, samples, res):
    scene = bpy.context.scene
    scene.render.resolution_x = res
    scene.render.resolution_y = res
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False  # keep the gray world visible

    if engine == "BLENDER_WORKBENCH":
        scene.render.engine = "BLENDER_WORKBENCH"
        scene.display.shading.background_type = "VIEWPORT"
        scene.display.shading.background_color = (BG_GRAY, BG_GRAY, BG_GRAY)
    else:
        scene.render.engine = "CYCLES"
        scene.cycles.device = "CPU"
        scene.cycles.samples = samples
        setup_denoising(scene, "render_inputs")


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


def render_at_angle(cam, angle_deg, out_path):
    """Orbit the camera around Z to the given angle and render."""
    ang = math.radians(angle_deg)
    radius = math.hypot(cam.location.x, cam.location.y)
    cam.location.x = radius * math.sin(ang)
    cam.location.y = -radius * math.cos(ang)
    bpy.context.view_layer.update()
    bpy.context.scene.render.filepath = out_path
    bpy.ops.render.render(write_still=True)
    print(f"[render_inputs] wrote {out_path} (angle={angle_deg})")


# ---------------------------------------------------------------------------
def main():
    reset_scene()
    meshes = import_model(model_path)
    if not meshes:
        raise SystemExit("no mesh objects imported from model")
    center_and_normalize(meshes)
    setup_world()
    cam, target = setup_camera(meshes)
    setup_studio_lights(target)
    setup_render(engine, samples, res)

    print(f"[render_inputs] engine={bpy.context.scene.render.engine} "
          f"samples={samples} res={res} meshes={len(meshes)}")
    render_at_angle(cam, 0.0, out_front)     # front
    render_at_angle(cam, 180.0, out_back)    # back


main()
