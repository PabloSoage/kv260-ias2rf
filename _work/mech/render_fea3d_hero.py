"""Photographic renders (Cycles) of fea3d_case.py's maps, one load case: the case coloured by von Mises stress, and
the two boards, lifted out of it, coloured by their largest principal strain. The colours are the PLYs' own (turbo
for the case, viridis for the boards, on the scales in docs/sim/case3d_<tag>.json); compose_fea3d_hero.py adds the
colour bars and the call-outs.

    blender -b --python _work/mech/render_fea3d_hero.py -- v2 Zm [--samples N]
"""
import bmesh, bpy, json, os, sys
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view

argv = sys.argv[sys.argv.index("--") + 1:]
tag, lc = argv[0], argv[1]
samples = int(argv[argv.index("--samples") + 1]) if "--samples" in argv else 192
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
D = os.path.join(ROOT, "_work", "mech", "cache", "fea3d", tag)
res = json.load(open(os.path.join(ROOT, "docs", "sim", f"case3d_{tag}.json")))
case = res["cases"][lc]
boards = json.load(open(os.path.join(D, "boards.json")))
MM = 0.001


def load_ply(fn, name):
    lines = open(fn).read().split("\n")
    nv = nf = i = 0
    while lines[i] != "end_header":
        p = lines[i].split()
        if p[:2] == ["element", "vertex"]:
            nv = int(p[2])
        if p[:2] == ["element", "face"]:
            nf = int(p[2])
        i += 1
    i += 1
    vs, cs = [], []
    for k in range(nv):
        p = lines[i + k].split()
        vs.append((float(p[0]) * MM, float(p[1]) * MM, float(p[2]) * MM))
        cs.append((int(p[3]) / 255, int(p[4]) / 255, int(p[5]) / 255))
    i += nv
    fs = [tuple(int(x) for x in lines[i + k].split()[1:4]) for k in range(nf)]
    me = bpy.data.meshes.new(name)
    me.from_pydata(vs, [], fs)
    attr = me.color_attributes.new("val", "FLOAT_COLOR", "POINT")
    for k, c in enumerate(cs):                       # sRGB colour map -> linear
        attr.data[k].color = tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c) + (1,)
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-7)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)     # the PLY's winding is not consistent
    bm.to_mesh(me)
    bm.free()
    me.update()
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    return o


def vcol_material(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    a = nt.nodes.new("ShaderNodeAttribute")
    a.attribute_name = "val"
    nt.links.new(a.outputs["Color"], b.inputs["Base Color"])
    nt.links.new(a.outputs["Color"], b.inputs["Emission Color"])
    b.inputs["Emission Strength"].default_value = 0.08     # keeps the map readable in the shadows
    b.inputs["Roughness"].default_value = 0.5
    if "Specular IOR Level" in b.inputs:
        b.inputs["Specular IOR Level"].default_value = 0.25
    return m


bpy.ops.wm.read_factory_settings(use_empty=True)
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
sc.render.resolution_x, sc.render.resolution_y = 1920, 1200
sc.view_settings.view_transform = "Standard"     # the colour map's own colours, not a filmic remap
sc.view_settings.exposure = 0.0

w = bpy.data.worlds.new("w")
sc.world = w
w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.93, 0.94, 0.95, 1)
w.node_tree.nodes["Background"].inputs[1].default_value = 0.25

bpy.ops.mesh.primitive_plane_add(size=6, location=(0, 0, -14 * MM))
fl = bpy.context.object
fm = bpy.data.materials.new("floor")
fm.use_nodes = True
fm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.80, 0.81, 0.83, 1)
fm.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.8
fl.data.materials.append(fm)

cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
sc.collection.objects.link(cam)
sc.camera = cam
cam.data.clip_start, cam.data.clip_end = 0.001, 20.0
tgt = bpy.data.objects.new("tgt", None)
sc.collection.objects.link(tgt)
c = cam.constraints.new("TRACK_TO")
c.target, c.track_axis, c.up_axis = tgt, "TRACK_NEGATIVE_Z", "UP_Y"


def light(name, loc, energy, size):
    L = bpy.data.lights.new(name, "AREA")
    L.energy, L.size = energy, size
    o = bpy.data.objects.new(name, L)
    sc.collection.objects.link(o)
    o.location = loc
    k = o.constraints.new("TRACK_TO")
    k.target, k.track_axis, k.up_axis = tgt, "TRACK_NEGATIVE_Z", "UP_Y"


light("key", (0.30, -0.35, 0.50), 14, 0.6)
light("fill", (-0.45, 0.25, 0.35), 6, 0.9)
light("rim", (0.15, 0.60, 0.30), 6, 0.6)

oc = load_ply(os.path.join(D, f"case3d_{tag}_{lc}.ply"), "case")
ob = load_ply(os.path.join(D, f"boards3d_{tag}_{lc}.ply"), "boards")
for o, n in ((oc, "case map"), (ob, "boards map")):
    o.data.materials.append(vcol_material(n))
    for p in o.data.polygons:
        p.use_smooth = True
    o.data.set_sharp_from_angle(angle=0.6)            # smooth across the mesh, sharp at the case's real edges


def project(pts_mm):
    sc.view_layers[0].update()
    out = []
    for p in pts_mm:
        v = world_to_camera_view(sc, cam, Vector(p) * MM)
        out.append((v.x, 1 - v.y))
    return out


meta = {}
# 1) the case, from the side of its peak (right rear), the boards inside it
peak = case["case"]["peak_at"]
tgt.location = Vector((10, 50, 0)) * MM
cam.location = Vector((330, 430, 270)) * MM
cam.data.lens = 50
ob.hide_render = True
fn1 = os.path.join(D, f"hero_{lc}_case.png")
sc.render.filepath = fn1
bpy.ops.render.render(write_still=True)
meta["case"] = {"file": fn1, "peak_xy": project([peak])[0], "peak_mm": peak}

# 2) the boards out of the case, from the front left, with the three BGAs called out
oc.hide_render, ob.hide_render = True, False
ob.location.z = 0
tgt.location = Vector((0, 50, 0)) * MM
cam.location = Vector((170, -260, 300)) * MM
cam.data.lens = 50
fn2 = os.path.join(D, f"hero_{lc}_boards.png")
sc.render.filepath = fn2
bpy.ops.render.render(write_still=True)
bga = {}
for ref, (lo, hi) in boards["hirose"].items():
    if ref in case.get("bga", {}):
        ztop = 3.0 if ref == "U1101" else 1.0
        bga[ref] = project([((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, ztop)])[0]
meta["boards"] = {"file": fn2, "bga_xy": bga}
json.dump(meta, open(os.path.join(D, f"hero_{lc}.json"), "w"), indent=1)
print("hero", meta)
