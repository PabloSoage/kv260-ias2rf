"""Renders of the mount (docs/MECHANICAL.md), Cycles on the GPU (OptiX).

    blender -b _work/mech/cache/assembly.blend --python _work/mech/render_mount.py -- iso,rj45,sma,iso_back,side
            [--samples N] [--res WxH]

Writes docs/img/mount_<view>.png (the repo keeps them as 1600-wide JPEGs: magick in.png -resize 1600x -quality 88 out.jpg).
"""
import bpy, os, sys
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
views = argv[0].split(",")
samples = int(argv[argv.index("--samples") + 1]) if "--samples" in argv else 256
W, H = (int(v) for v in (argv[argv.index("--res") + 1] if "--res" in argv else "1920x1200").split("x"))
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MM = 0.001
sc = bpy.context.scene
sc.render.engine = "CYCLES"
prefs = bpy.context.preferences.addons["cycles"].preferences
prefs.compute_device_type = "OPTIX"
prefs.get_devices()
for d in prefs.devices:
    d.use = d.type == "OPTIX"
sc.cycles.device = "GPU"
sc.cycles.samples = samples
sc.cycles.use_denoising = True
sc.render.resolution_x, sc.render.resolution_y = W, H
sc.view_settings.view_transform = "AgX"
sc.view_settings.look = "AgX - Medium High Contrast"

w = bpy.data.worlds.new("w")
sc.world = w
w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.82, 0.84, 0.88, 1)
w.node_tree.nodes["Background"].inputs[1].default_value = 0.25
bpy.ops.mesh.primitive_plane_add(size=4, location=(0, 0, -11.2 * MM))
fl = bpy.context.object
m = bpy.data.materials.new("floor")
m.use_nodes = True
b = m.node_tree.nodes["Principled BSDF"]
b.inputs["Base Color"].default_value = (0.75, 0.76, 0.78, 1)
b.inputs["Roughness"].default_value = 0.6
fl.data.materials.append(m)

# KiCad's glTF gives the solder mask alpha 0.83, which lets the laminate show through in Cycles
for m in bpy.data.materials:
    b = m.node_tree.nodes.get("Principled BSDF") if m.use_nodes else None
    if not b:
        continue
    col = tuple(round(x, 2) for x in b.inputs["Base Color"].default_value)[:3]
    if col == (0.08, 0.2, 0.14):
        b.inputs["Base Color"].default_value = (0.012, 0.11, 0.035, 1)
        b.inputs["Alpha"].default_value = 1.0
        b.inputs["Roughness"].default_value = 0.42
    elif col == (1.0, 1.0, 1.0) and b.inputs["Alpha"].default_value < 1:
        b.inputs["Alpha"].default_value = 1.0
        b.inputs["Base Color"].default_value = (0.9, 0.9, 0.88, 1)

tgt = bpy.data.objects.new("tgt", None)
sc.collection.objects.link(tgt)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
sc.collection.objects.link(cam)
sc.camera = cam
cc = cam.constraints.new("TRACK_TO")
cc.target = tgt
cc.track_axis = "TRACK_NEGATIVE_Z"
cc.up_axis = "UP_Y"


def light(name, loc, energy, size):
    L = bpy.data.lights.new(name, "AREA")
    L.energy = energy
    L.size = size
    o = bpy.data.objects.new(name, L)
    sc.collection.objects.link(o)
    o.location = loc
    c = o.constraints.new("TRACK_TO")
    c.target = tgt
    c.track_axis = "TRACK_NEGATIVE_Z"
    c.up_axis = "UP_Y"


light("key", (0.25, -0.35, 0.45), 22, 0.35)
light("fill", (-0.45, 0.2, 0.30), 9, 0.6)
light("rim", (0.1, 0.55, 0.25), 8, 0.4)

VIEWS = {   # name: (target mm, camera mm, lens mm)
    "iso":      ((5, 38, 0), (330, -330, 300), 50),
    "iso_back": ((5, 38, 0), (-360, 330, 300), 50),
    "top":      ((6, 38, 0), (6, 38, 600), 50),
    "rj45":     ((-19, -21, 5), (60, -110, 70), 60),
    "sma":      ((-110, 50, 2), (-230, -40, 80), 55),
    "side":     ((5, 38, 0), (5, -420, 40), 60),
}
os.makedirs(os.path.join(ROOT, "docs", "img"), exist_ok=True)
for v in views:
    t, c, lens = VIEWS[v]
    tgt.location = Vector(t) * MM
    cam.location = Vector(c) * MM
    cam.data.lens = lens
    cam.data.clip_start = 0.005
    sc.render.filepath = os.path.join(ROOT, "docs", "img", f"mount_{v}.png")
    bpy.ops.render.render(write_still=True)
    print("rendered", sc.render.filepath)
