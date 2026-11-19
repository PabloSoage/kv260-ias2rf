"""Interference check of the enclosure against the KV260 and the adapter (docs/ENCLOSURE.md section 4).

    blender -b _work/mech/cache/case.blend --python _work/mech/check_case.py

Prints every part the tray or the lid intersects (triangle against triangle, BVH overlap), with where,
and checks mated VHR-2N plug + 18 AWG jumper wire (R = 10 mm bend) clearances for J1004 -> KV260 J12.
"""
import math

import bmesh
import bpy
from mathutils import Vector
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


def _bm_box(x0, x1, y0, y1, z0, z1):
    """Create a triangulated axis-aligned box BMesh in Blender scene meters from mm bounds."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    cx, cy, cz = 0.5 * (x0 + x1) * MM, 0.5 * (y0 + y1) * MM, 0.5 * (z0 + z1) * MM
    sx, sy, sz = (x1 - x0) * MM, (y1 - y0) * MM, (z1 - z0) * MM
    for v in bm.verts:
        v.co.x = cx + v.co.x * sx
        v.co.y = cy + v.co.y * sy
        v.co.z = cz + v.co.z * sz
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    return bm


def _add_tube(bm, pts_mm, r_mm, segs=16):
    """Sweep a closed circular tube along a 3D mm polyline into an existing BMesh."""
    rings = []
    for i, p in enumerate(pts_mm):
        pv = Vector(p) * MM
        t = (Vector(pts_mm[min(i + 1, len(pts_mm) - 1)]) - Vector(pts_mm[max(i - 1, 0)])).normalized()
        up = Vector((0.0, 0.0, 1.0)) if abs(t.z) < 0.9 else Vector((1.0, 0.0, 0.0))
        u = t.cross(up).normalized()
        w = u.cross(t).normalized()
        ring = [
            bm.verts.new(pv + (u * math.cos(2 * math.pi * k / segs) + w * math.sin(2 * math.pi * k / segs)) * (r_mm * MM))
            for k in range(segs)
        ]
        rings.append(ring)
    for r0, r1 in zip(rings, rings[1:]):
        for k in range(segs):
            kn = (k + 1) % segs
            bm.faces.new((r0[k], r0[kn], r1[kn], r1[k]))
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])


def _bvh_and_samples(bm):
    """Build BVHTree plus dense surface sample points (vertices + face/edge midpoints) from a BMesh."""
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    vs = [v.co.copy() for v in bm.verts]
    ps = [tuple(v.index for v in f.verts) for f in bm.faces]
    samples = list(vs) + [f.calc_center_median() for f in bm.faces]
    return BVHTree.FromPolygons(vs, ps), samples


def _min_clearance_mm(bm, targets):
    """Return dict target_name -> (overlap_pairs, min_distance_mm) for bm against named BVHTrees."""
    src_bvh, src_pts = _bvh_and_samples(bm)
    out = {}
    for name, (t_bvh, t_pts) in targets.items():
        ov = len(src_bvh.overlap(t_bvh))
        if ov:
            out[name] = (ov, 0.0)
            continue
        d_min = min(
            min((t_bvh.find_nearest(p)[3] for p in src_pts), default=1e9),
            min((src_bvh.find_nearest(p)[3] for p in t_pts), default=1e9),
        )
        out[name] = (0, d_min / MM)
    return out


def check_j1004_plug(case_trees):
    """Verify mated VHR-2N plug body, insertion corridor, and 18 AWG wire bend (R=10 mm) clearances."""
    housing = bpy.data.objects.get("pa66_housing")
    if housing is None:
        print("J1004 VHR-2N check skipped: pa66_housing not found")
        return
    hvs = [housing.matrix_world @ v.co for v in housing.data.vertices]
    hx0, hx1 = min(v.x for v in hvs) / MM, max(v.x for v in hvs) / MM
    hy0, hy1 = min(v.y for v in hvs) / MM, max(v.y for v in hvs) / MM
    hz0, hz1 = min(v.z for v in hvs) / MM, max(v.z for v in hvs) / MM
    # VHR-2N (7.8 x 9.0 x 13.3 mm) mated 16.4 mm past B2PS-VH rear flange (hy0 + 3.2 mm -> Y = 117.70 mm)
    plug_cx = 0.5 * (hx0 + hx1)
    plug_x0, plug_x1 = plug_cx - 3.90, plug_cx + 3.90
    plug_y0, plug_y1 = hy0 + 3.20 + 16.40 - 13.30, hy0 + 3.20 + 16.40
    plug_z0, plug_z1 = hz0, hz0 + 9.00

    targets = {}
    for tname in ("case_bottom", "case_lid", "bumper_Lback"):
        if tname in case_trees:
            ct, cvs, _ = case_trees[tname]
            targets[tname] = (ct, cvs)

    # Wire centerline coordinates: 2x 18 AWG (OD 2.2 mm -> r=1.1 mm), straight 4 mm back then R=10 mm turn +X to KV260 J12
    j12_x, j12_y, j12_z = 6.50, 115.50, 5.75
    pin_z = 0.5 * (plug_z0 + plug_z1) - 0.25
    r_bend = 10.0
    plug_bm = _bm_box(plug_x0, plug_x1, plug_y0, plug_y1, plug_z0, plug_z1)
    corr_bm = _bm_box(plug_x0, plug_x1, plug_y1, plug_y1 + 25.0, plug_z0, plug_z1)
    wire_bm = bmesh.new()
    for px in (plug_cx - 1.98, plug_cx + 1.98):
        pts = [(px, plug_y1, pin_z), (px, plug_y1 + 4.0, pin_z)]
        cy1 = plug_y1 + 4.0
        for s in range(1, 13):
            th = math.pi - s * (math.pi / 24.0)
            pts.append((px + r_bend + r_bend * math.cos(th), cy1 + r_bend * math.sin(th), pin_z))
        y_run = cy1 + r_bend
        x_end_run = j12_x - r_bend
        x_start_run = pts[-1][0]
        for s in range(1, 13):
            pts.append((x_start_run + (x_end_run - x_start_run) * (s / 12.0), y_run, pin_z))
        for s in range(1, 13):
            th = math.pi / 2.0 - s * (math.pi / 24.0)
            z_cur = pin_z + (j12_z - pin_z) * (s / 12.0)
            pts.append((j12_x - r_bend + r_bend * math.cos(th), y_run - r_bend + r_bend * math.sin(th), z_cur))
        pts.append((j12_x, j12_y, j12_z))
        _add_tube(wire_bm, pts, 1.1)
    bmesh.ops.triangulate(wire_bm, faces=wire_bm.faces[:])

    # Path length of centerline (center pin) from VHR-2N exit (plug_y1) to J12 wall (j12_y)
    path_mm = 4.0 + 0.5 * math.pi * r_bend + ((j12_x - r_bend) - (plug_cx + r_bend)) + 0.5 * math.pi * r_bend + ((plug_y1 + 4.0) - j12_y)
    print(f"J1004 pa66 bbox mm: X=[{hx0:.2f},{hx1:.2f}] Y=[{hy0:.2f},{hy1:.2f}] Z=[{hz0:.2f},{hz1:.2f}]")
    print(f"J1004->J12 span X={j12_x - plug_cx:.1f} mm, VHR-2N->J12 R=10 mm path={path_mm:.1f} mm (150 mm jumper)")
    for label, bm in (("VHR-2N plug", plug_bm), ("VHR-2N corridor", corr_bm), ("18AWG R10 wires", wire_bm)):
        res = _min_clearance_mm(bm, targets)
        msg = " | ".join(f"{k}: ov={ov}, clr={clr:.2f} mm" for k, (ov, clr) in res.items())
        print(f"  {label:16s} -> {msg}")
        bm.free()


check_j1004_plug({**case, **({ "bumper_Lback": tree(bpy.data.objects["bumper_Lback"]) } if "bumper_Lback" in bpy.data.objects else {})})
