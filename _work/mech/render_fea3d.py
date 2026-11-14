"""Renders fea3d_case.py's maps: the case's surface coloured by von Mises stress (turbo) and the boards' surfaces
by their largest principal strain (viridis), three views each per load case, for compose_fea3d.py.

    blender -b --python _work/mech/render_fea3d.py -- v1
"""
import bpy, json, os, sys
from mathutils import Vector

tag = sys.argv[sys.argv.index("--") + 1]
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
D = os.path.join(ROOT, "_work", "mech", "cache", "fea3d", tag)
res = json.load(open(os.path.join(ROOT, "docs", "sim", f"case3d_{tag}.json")))
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
    me.update()
    attr = me.color_attributes.new("val", "FLOAT_COLOR", "POINT")
    for k, c in enumerate(cs):
        attr.data[k].color = (c[0] ** 2.2, c[1] ** 2.2, c[2] ** 2.2, 1)
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    return o


bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = "BLENDER_WORKBENCH"
sc.render.resolution_x, sc.render.resolution_y = 1200, 800
sh = sc.display.shading
sh.light = "STUDIO"
sh.color_type = "VERTEX"
sh.show_cavity = True
sh.cavity_type = "WORLD"
sh.show_specular_highlight = False
sh.background_type = "VIEWPORT"
sh.background_color = (1, 1, 1)
sc.view_settings.view_transform = "Standard"
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
sc.collection.objects.link(cam)
sc.camera = cam
cam.data.clip_start, cam.data.clip_end = 0.001, 10.0
tgt = bpy.data.objects.new("tgt", None)
sc.collection.objects.link(tgt)
c = cam.constraints.new("TRACK_TO")
c.target = tgt
c.track_axis = "TRACK_NEGATIVE_Z"
c.up_axis = "UP_Y"


def shoot(o, views, prefix):
    bb = [o.matrix_world @ Vector(b) for b in o.bound_box]
    ctr = sum(bb, Vector()) / 8
    size = max(b.x for b in bb) - min(b.x for b in bb)
    files = []
    for vn, (d, focus, dist) in views.items():
        p = Vector(focus) * MM if focus else ctr
        if d == "out":                     # look at a point from outside the body, along centre -> point
            d = tuple((p - ctr).normalized() + Vector((0, 0, 0.35)))
        tgt.location = p
        cam.location = p + Vector(d).normalized() * size * dist
        cam.data.lens = 50
        fn = os.path.join(D, f"{prefix}_{vn}.png")
        sc.render.filepath = fn
        bpy.ops.render.render(write_still=True)
        files.append(fn)
    return files


outs = {}
for lc, case in res["cases"].items():
    oc = load_ply(os.path.join(D, f"case3d_{tag}_{lc}.ply"), "case")
    ob = load_ply(os.path.join(D, f"boards3d_{tag}_{lc}.ply"), "boards")
    ob.hide_render = True
    f1 = shoot(oc, {"top": ((0.55, -0.9, 0.75), None, 2.0), "under": ((0.5, -0.8, -0.6), None, 2.0),
                    "peak": ("out", case["case"]["peak_at"], 0.32)}, f"r_{lc}_case")
    oc.hide_render, ob.hide_render = True, False
    bga = case.get("bga", {})
    focus = None
    if "U1101" in bga:
        lo, hi = json.load(open(os.path.join(D, "boards.json")))["hirose"]["U1101"]
        focus = [(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, 1.5]
    f2 = shoot(ob, {"top": ((0.3, -0.6, 1.0), None, 1.6), "under": ((0.3, -0.6, -1.0), None, 1.6),
                    "bga": ((0.25, -0.45, 1.0), focus or case["adapter"]["peak_at"], 0.6)}, f"r_{lc}_boards")
    outs[lc] = f1 + f2
    for o in (oc, ob):
        bpy.data.objects.remove(o, do_unlink=True)
json.dump(outs, open(os.path.join(D, "renders.json"), "w"))
print("renders", outs)
