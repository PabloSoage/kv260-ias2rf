"""Interference check of the enclosure against the KV260 and the adapter (docs/ENCLOSURE.md section 4).

    blender -b _work/mech/cache/case.blend --python _work/mech/check_case.py

Prints every part the tray or the lid intersects (triangle against triangle, BVH overlap), with where.
"""
import bpy
from mathutils.bvhtree import BVHTree

MM = 0.001
dg = bpy.context.evaluated_depsgraph_get()


def tree(o):
    m = o.evaluated_get(dg).to_mesh()
    vs = [o.matrix_world @ v.co for v in m.vertices]
    ps = [tuple(p.vertices) for p in m.polygons]
    o.evaluated_get(dg).to_mesh_clear()
    return BVHTree.FromPolygons(vs, ps), vs, ps


case = {n: tree(bpy.data.objects[n]) for n in ("case_bottom", "case_lid")}
skip = ("case_", "pin", "pad", "Text")
hits = 0
for o in bpy.data.objects:
    if o.type != "MESH" or o.name.startswith(skip) or o.hide_render:
        continue
    t, vs, ps = tree(o)
    if not ps:
        continue
    for n, (ct, cvs, cps) in case.items():
        pairs = ct.overlap(t)
        if pairs:
            hits += 1
            pts = [cvs[cps[a][0]] for a, b in pairs[:200]]
            c = sum(pts, pts[0] * 0) / len(pts)
            top = o
            while top.parent and top.parent.name not in ("COMPONENTS", "ADAPTER") and top.parent.parent:
                top = top.parent
            print(f"INTERFERENCE {n:12s} x {top.name[:30]:30s} [{o.name[:24]} {o.dimensions.x/MM:.1f}x{o.dimensions.y/MM:.1f}x{o.dimensions.z/MM:.2f}] {len(pairs):5d} tri pairs near "
                  f"({c.x / MM:7.1f}, {c.y / MM:7.1f}, {c.z / MM:6.2f})")
print("interferences:", hits)
