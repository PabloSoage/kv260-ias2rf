"""Exports the enclosure's two shells in assembly coordinates (mm, not the print orientation) and the boards'
outlines for fea3d_case.py.

    blender -b _work/mech/cache/case.blend    --python _work/mech/fea3d_export.py -- v1
    blender -b _work/mech/cache/case_v2.blend --python _work/mech/fea3d_export.py -- v2
"""
import bpy, json, os, sys
from mathutils import Vector

tag = sys.argv[sys.argv.index("--") + 1]
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
out = os.path.join(ROOT, "_work", "mech", "cache", "fea3d", tag)
os.makedirs(out, exist_ok=True)
MM = 0.001
dg = bpy.context.evaluated_depsgraph_get()


def write_stl(o, fn):
    e = o.evaluated_get(dg)
    m = e.to_mesh()
    m.calc_loop_triangles()
    with open(fn, "w") as f:
        f.write("solid s\n")
        for t in m.loop_triangles:
            vs = [o.matrix_world @ m.vertices[i].co / MM for i in t.vertices]
            f.write(" facet normal 0 0 0\n  outer loop\n")
            for v in vs:
                f.write(f"   vertex {v.x:.5f} {v.y:.5f} {v.z:.5f}\n")
            f.write("  endloop\n endfacet\n")
        f.write("endsolid s\n")
    e.to_mesh_clear()


for n in ("case_bottom", "case_lid"):
    write_stl(bpy.data.objects[n], os.path.join(out, n + ".stl"))


def under(o, prefix):
    while o:
        if o.name.startswith(prefix):
            return True
        o = o.parent
    return False


def dims(o):
    vs = [o.matrix_world @ Vector(b) / MM for b in o.bound_box]
    lo = [min(v[i] for v in vs) for i in range(3)]
    hi = [max(v[i] for v in vs) for i in range(3)]
    return lo, hi


def base_color(o):
    for s in o.material_slots:
        if s.material and s.material.use_nodes:
            b = s.material.node_tree.nodes.get("Principled BSDF")
            if b:
                return tuple(round(x, 2) for x in b.inputs["Base Color"].default_value[:3])
    return None


# the boards as solids: the adapter's FR-4 body from KiCad's glTF (its laminate material), the KV260 carrier's
# laminate from AMD's STEP (the large 1.6 mm green body); written for fea3d_case.py, which unites them with the shells
boards = {}
for o in bpy.data.objects:
    if o.type != "MESH":
        continue
    lo, hi = dims(o)
    sx, sy, sz = (hi[i] - lo[i] for i in range(3))
    if under(o, "ADAPTER") and base_color(o) == (0.42, 0.45, 0.29) and sx > 100:
        boards["adapter_pcb"] = o
    if under(o, "KV260") and sx > 100 and sy > 100 and 1.0 < sz < 2.0:
        c = base_color(o)
        if c and c[1] > 2 * c[0]:
            boards["carrier_pcb"] = o
for k, o in boards.items():
    write_stl(o, os.path.join(out, k + ".stl"))
    print("board", k, o.name, [round(v, 2) for v in dims(o)[0]], [round(v, 2) for v in dims(o)[1]])
# the Hirose BM20B pair under the adapter (J101, J102): their mated stack bridges the 0.8 mm to the carrier
parts = {}
for o in bpy.data.objects:
    if o.name in ("J101", "J102", "U1101", "U501", "U601") and under(o, "ADAPTER"):
        vs, st = [], [o]
        while st:
            c = st.pop()
            st += list(c.children)
            if c.type == "MESH":
                vs += [c.matrix_world @ Vector(b) / MM for b in c.bound_box]
        parts[o.name] = ([min(v[i] for v in vs) for i in range(3)], [max(v[i] for v in vs) for i in range(3)])


def bbox(root):
    vs, st = [], [root]
    while st:
        c = st.pop()
        st += list(c.children)
        if c.type == "MESH" and not c.hide_render:
            vs += [c.matrix_world @ Vector(b) / MM for b in c.bound_box]
    return [min(v[i] for v in vs) for i in range(3)], [max(v[i] for v in vs) for i in range(3)]


info = {}
for key, name in (("kv260", "KV260_STARTERKIT_ASM_2_ASM_3_ASM"), ("adapter", "ADAPTER")):
    o = bpy.data.objects.get(name)
    if o:
        info[key] = bbox(o)
info["hirose"] = parts
info["board_files"] = sorted(boards)
json.dump(info, open(os.path.join(out, "boards.json"), "w"), indent=1)
print("exported", out, info)
