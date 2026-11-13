"""Renders of the enclosure (docs/ENCLOSURE.md), Cycles on the GPU (OptiX).

    blender -b _work/mech/cache/case.blend --python _work/mech/render_case.py -- closed,closed_back,open,tray,lid,section
            [--samples N] [--res WxH] [--exposure E]

Writes docs/img/case_<view>.png (kept in the repo as 1600-wide JPEGs, as the mount's renders).
"""
import bpy, math, os, re, sys
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
views = argv[0].split(",")
samples = int(argv[argv.index("--samples") + 1]) if "--samples" in argv else 256
W, H = (int(v) for v in (argv[argv.index("--res") + 1] if "--res" in argv else "1920x1200").split("x"))
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MM = 0.001
MASK_ALPHA = float(argv[argv.index("--mask") + 1]) if "--mask" in argv else 0.72
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
sc.view_settings.exposure = float(argv[argv.index("--exposure") + 1]) if "--exposure" in argv else -1.8

w = bpy.data.worlds.new("w")
sc.world = w
w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.20, 0.22, 0.25, 1)
w.node_tree.nodes["Background"].inputs[1].default_value = 0.25
bpy.ops.mesh.primitive_plane_add(size=4, location=(0, 0, -11.0 * MM))
fl = bpy.context.object
fl.name = "floor"
m = bpy.data.materials.new("floor")
m.use_nodes = True
b = m.node_tree.nodes["Principled BSDF"]
b.inputs["Base Color"].default_value = (0.16, 0.17, 0.19, 1)
b.inputs["Roughness"].default_value = 0.7
fl.data.materials.append(m)

# the adapter's glTF materials, as render_mount.py: opaque matte mask, lifted off the copper
for m in bpy.data.materials:
    b = m.node_tree.nodes.get("Principled BSDF") if m.use_nodes else None
    if not b:
        continue
    col = tuple(round(x, 2) for x in b.inputs["Base Color"].default_value)[:3]
    if col == (0.08, 0.2, 0.14):
        # translucent like real LPI mask: the copper under it reads as lighter green, as in KiCad's raytracer
        b.inputs["Base Color"].default_value = (0.010, 0.085, 0.030, 1)
        b.inputs["Alpha"].default_value = MASK_ALPHA
        b.inputs["Roughness"].default_value = 0.42
        if "Specular IOR Level" in b.inputs:
            b.inputs["Specular IOR Level"].default_value = 0.3
    elif col == (1.0, 1.0, 1.0) and b.inputs["Alpha"].default_value < 1:
        b.inputs["Alpha"].default_value = 1.0
        b.inputs["Base Color"].default_value = (0.9, 0.9, 0.88, 1)
rig = bpy.data.objects.get("ADAPTER")
if rig:
    stack = list(rig.children)
    while stack:
        o = stack.pop()
        stack += list(o.children)
        if o.type != "MESH" or not o.material_slots or not o.material_slots[0].material:
            continue
        b = o.material_slots[0].material.node_tree.nodes.get("Principled BSDF")
        col = tuple(round(x, 2) for x in b.inputs["Base Color"].default_value)[:3]
        if col in ((0.01, 0.09, 0.03), (0.9, 0.9, 0.88)) and o.dimensions.z < 1e-5:
            zc = (rig.matrix_world.inverted() @ o.matrix_world.translation).z + \
                 sum(v.co.z for v in o.data.vertices[:50]) / min(50, len(o.data.vertices)) * o.matrix_world.to_scale().z
            lift = (0.04 if col[0] < 0.5 else 0.06) * MM
            o.location.z += lift if zc > 0.8 * MM else -lift

# the case: charcoal PETG-CF, matte with a little sheen
for name in ("case PETG-CF", "lid PETG-CF"):
    m = bpy.data.materials.get(name)
    if m:
        b = m.node_tree.nodes["Principled BSDF"]
        b.inputs["Base Color"].default_value = (0.022, 0.024, 0.027, 1)
        b.inputs["Roughness"].default_value = 0.72
        if "Specular IOR Level" in b.inputs:
            b.inputs["Specular IOR Level"].default_value = 0.35

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


light("key", (0.25, -0.35, 0.45), 26, 0.35)
light("fill", (-0.45, 0.2, 0.30), 11, 0.6)
light("rim", (0.1, 0.55, 0.25), 10, 0.4)

# leftovers of the open mount's scene (assembly.blend): not part of the case
for o in [o for o in bpy.data.objects if o.name.startswith("RJ45_opening")]:
    bpy.data.objects.remove(o, do_unlink=True)
lid = bpy.data.objects["case_lid"]
bottom = bpy.data.objects["case_bottom"]
pins = [o for o in bpy.data.objects if re.fullmatch(r"pin\d+", o.name)]     # not the mount's hidden pin_pocket
pads = [o for o in bpy.data.objects if o.name.startswith("pad")]
bumpers = [o for o in bpy.data.objects if o.name.startswith("bumper")]
boards = [o for o in bpy.data.objects if o.parent is None and o.name not in
          ("case_lid", "case_bottom", "floor", "tgt", "cam", "key", "fill", "rim") and not o.name.startswith(("pin", "pad", "bumper"))]
home = {o.name: (o.location.copy(), o.rotation_euler.copy()) for o in [lid] + pins + pads + bumpers}


def reset():
    for o in [lid] + pins + pads + bumpers:
        o.location, o.rotation_euler = home[o.name][0].copy(), home[o.name][1].copy()
    for o in bpy.data.objects:
        if o.name not in ("tgt",):
            o.hide_render = o.hide_viewport
    for o in [lid, bottom] + pins + pads + bumpers:
        o.hide_render = False
    cam.data.type = "PERSP"
    cam.data.clip_start = 0.005
    cam.data.clip_end = 100


def tree_hide(roots, hide):
    st = list(roots)
    while st:
        o = st.pop()
        st += list(o.children)
        if o.type == "MESH":
            o.hide_render = hide or o.hide_viewport


CUTTERS = []


def section_cut(y):
    """Section at Y = y, everything with Y < y removed: the tray, the lid and the boards' large meshes are cut
    (capped where they are solids), the small parts in front of the plane are hidden."""
    bpy.ops.mesh.primitive_cube_add(size=1)
    c = bpy.context.object
    c.name = "section_cutter"
    c.scale = (0.4, 0.4, 0.2)
    c.location = (0, y * MM - 0.2, 0)
    c.hide_render = True
    CUTTERS.append(c)
    st = [bottom, lid] + boards + pins + pads
    while st:
        o = st.pop()
        st += list(o.children)
        if o.type != "MESH" or o.hide_render:
            continue
        vs = [o.matrix_world @ Vector(b) / MM for b in o.bound_box]
        y0, y1 = min(v.y for v in vs), max(v.y for v in vs)
        if y1 < y:
            o.hide_render = True
        elif y0 < y:
            if o in (bottom, lid) or (max(v.x for v in vs) - min(v.x for v in vs) > 20 and y1 - y0 > 20):
                mod = o.modifiers.new("sec", "BOOLEAN")
                mod.operation = "DIFFERENCE"
                mod.object = c
                mod.solver = "EXACT" if o in (bottom, lid) else "FLOAT"
            else:
                o.hide_render = True


def section_undo():
    for o in bpy.data.objects:
        if "sec" in o.modifiers:
            o.modifiers.remove(o.modifiers["sec"])
    for c in CUTTERS:
        bpy.data.objects.remove(c, do_unlink=True)
    CUTTERS.clear()


VIEWS = {   # name: (target mm, camera mm, lens mm)
    "closed":      ((8, 45, 5), (300, -330, 280), 50),
    "closed_back": ((8, 45, 5), (-300, 380, 260), 50),
    "open":        ((8, 45, 25), (320, -360, 330), 46),
    "tray":        ((8, 45, -5), (260, -300, 330), 50),
    "lid":         ((8, 45, 0), (250, -300, 330), 50),
    "section":     ((5, 47, -2), (110, -300, 75), 40),
    "sma":         ((-112, 50, 3), (-260, -60, 70), 55),
}
os.makedirs(os.path.join(ROOT, "docs", "img"), exist_ok=True)
for v in views:
    reset()
    t, c, lens = VIEWS[v]
    if v == "open":
        lid.location.z += 75 * MM
        for p in pins:
            p.location.z += 120 * MM
        for b in bumpers:                      # slid off outwards, as they go on
            b.location.y += (-30 if "front" in b.name else 30) * MM
    elif v == "tray":
        tree_hide(boards, True)
        lid.hide_render = True
        for p in pins + pads + bumpers:
            p.hide_render = True
    elif v == "lid":                           # the lid upside down beside nothing: its inside
        tree_hide(boards, True)
        bottom.hide_render = True
        for p in pins + pads + bumpers:
            p.hide_render = True
        lid.rotation_euler = (math.pi, 0, 0)
        lid.location = Vector((0, 90, 25)) * MM
    elif v == "section":
        for b in bumpers:
            b.hide_render = True
        section_cut(47.0)
    tgt.location = Vector(t) * MM
    cam.location = Vector(c) * MM
    cam.data.lens = lens
    sc.render.filepath = os.path.join(ROOT, "docs", "img", f"case_{v}.png")
    bpy.ops.render.render(write_still=True)
    sc.render.resolution_y = H
    print("rendered", sc.render.filepath)
    if v == "section":
        section_undo()
