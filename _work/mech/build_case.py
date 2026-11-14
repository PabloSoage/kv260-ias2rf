"""The closed enclosure (docs/ENCLOSURE.md): a bottom tray and a lid around the KV260 and the adapter, with a
honeycomb that carries both boards from below, clamp posts that hold them from above, and lugs that close it
with printed snap pins (bench) or M4 stainless screws and nyloc nuts (field).

    blender -b _work/mech/cache/assembly.blend --python _work/mech/build_case.py -- [--stl mech]

Needs assembly.blend from build_mount.py (the KV260 and the adapter placed; the mount's parts are removed here).
Writes _work/mech/cache/case.blend (for render_case.py) and, with --stl DIR, case_bottom.stl, case_lid.stl,
case_pin.stl and case_pad.stl. Frame and units as build_mount.py: mm, Z = 0 on the carrier's top face.
"""
import bpy, bmesh, math, os, sys
from mathutils import Vector

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
D = os.path.join(ROOT, "_work", "mech", "cache")
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
V2 = "--v2" in argv        # enclosure v2: adapter fan + filtered grille, SMA vents closed (docs/ENCLOSURE.md section 7)
MM = 0.001
sc = bpy.context.scene

# ---- heights ----------------------------------------------------------------------------------------
Z_BOT = -11.0          # outside of the floor
Z_FLOOR = -8.0         # inside of the floor (3 mm)
Z_SPLIT = 2.84         # the SMAs' centre line: their square bodies are clamped half by each shell
Z_TOP_IN = 32.75       # 4 mm over the KV260's fan (28.75)
Z_TOP = 35.75          # 3 mm lid
CARRIER_BOT = -1.59    # the carrier PCB's underside
ADAPTER_BOT = 0.8      # the adapter's underside
ADAPTER_TOP = 2.4
PAD = 1.0              # TPU 95A pad between every clamp and the board (compressed ~0.2 mm)
TONGUE_W, TONGUE_H, TONGUE_GAP = 1.6, 3.0, 0.2
HEX_S, HEX_T = 10.0, 1.6   # honeycomb cell (flat to flat) and wall

# ---- remove the open mount, keep the boards ---------------------------------------------------------
for o in list(bpy.data.objects):
    if o.name.startswith(("Base", "rj45_strap", "screw_7", "screw_8")):
        bpy.data.objects.remove(o, do_unlink=True)


def mat(name, rgb, rough=0.5, metal=0.0, alpha=1.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    return m


CASE = mat("case PETG-CF", (0.030, 0.032, 0.036), 0.78)
LID = mat("lid PETG-CF", (0.030, 0.032, 0.036), 0.78)
TPU = mat("TPU pads", (0.80, 0.33, 0.05), 0.6)
PIN = mat("pins", (0.80, 0.33, 0.05), 0.55)
STEEL = mat("stainless", (0.75, 0.75, 0.77), 0.28, 1.0)


# ---- geometry helpers -------------------------------------------------------------------------------
def round_poly(pts, radii, seg=8):
    """Orthogonal CCW polygon -> rounded polygon; the same vertex count for any radii (lofts need that)."""
    out, n = [], len(pts)
    for i in range(n):
        v, a, b = Vector(pts[i]), Vector(pts[i - 1]), Vector(pts[(i + 1) % n])
        d1, d2 = (v - a).normalized(), (b - v).normalized()
        r = radii[i]
        c = v - d1 * r + d2 * r
        p1, p2 = v - d1 * r, v + d2 * r
        a1, a2 = math.atan2(*(p1 - c).yx), math.atan2(*(p2 - c).yx)
        da = a2 - a1
        if d1.x * d2.y - d1.y * d2.x > 0:      # left turn (convex): counter-clockwise arc
            da = da % (2 * math.pi)
        else:
            da = -((-da) % (2 * math.pi))
        for k in range(seg + 1):
            t = a1 + da * k / seg
            out.append((c.x + r * math.cos(t), c.y + r * math.sin(t)))
    return out


def offset_ortho(pts, t):
    """Offset an orthogonal CCW polygon outwards by t[i] on edge i (edge i runs pts[i] -> pts[i+1])."""
    n, out = len(pts), []
    nrm = []
    for i in range(n):
        d = (Vector(pts[(i + 1) % n]) - Vector(pts[i])).normalized()
        nrm.append(Vector((d.y, -d.x)))
    for i in range(n):
        v = Vector(pts[i]) + nrm[i - 1] * t[i - 1] + nrm[i] * t[i]
        out.append((v.x, v.y))
    return out


def convex(pts):
    n = len(pts)
    res = []
    for i in range(n):
        a, v, b = Vector(pts[i - 1]), Vector(pts[i]), Vector(pts[(i + 1) % n])
        d1, d2 = v - a, b - v
        res.append(d1.x * d2.y - d1.y * d2.x > 0)
    return res


def loft(name, ring0, z0, ring1, z1, m=CASE):
    """A closed solid between two rings of equal length (CCW, mm)."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    lo = [bm.verts.new((x * MM, y * MM, z0 * MM)) for x, y in ring0]
    hi = [bm.verts.new((x * MM, y * MM, z1 * MM)) for x, y in ring1]
    n = len(lo)
    bm.faces.new(list(reversed(lo)))
    bm.faces.new(hi)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((lo[i], lo[j], hi[j], hi[i]))
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    sc.collection.objects.link(o)
    o.data.materials.append(m)
    return o


def stack(name, levels, m=CASE):
    """A closed solid through rings of equal length at rising heights: [(ring, z), ...]."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    vs = [[bm.verts.new((x * MM, y * MM, z * MM)) for x, y in ring] for ring, z in levels]
    n = len(vs[0])
    bm.faces.new(list(reversed(vs[0])))
    bm.faces.new(vs[-1])
    for lo, hi in zip(vs, vs[1:]):
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((lo[i], lo[j], hi[j], hi[i]))
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    sc.collection.objects.link(o)
    o.data.materials.append(m)
    return o


def prism(name, ring, z0, z1, m=CASE):
    return loft(name, ring, z0, ring, z1, m)


def box(name, x0, x1, y0, y1, z0, z1, m=CASE):
    return prism(name, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], z0, z1, m)


def cyl(name, x, y, z0, z1, d, m=CASE, verts=40, rot=0.0):
    r = d / 2
    ring = [(x + r * math.cos(rot + 2 * math.pi * k / verts), y + r * math.sin(rot + 2 * math.pi * k / verts))
            for k in range(verts)]
    return prism(name, ring, z0, z1, m)


def xprism(name, prof, x0, x1, m=CASE):
    """A solid extruded along X from a (y, z) profile (any winding)."""
    area = sum(prof[i][0] * prof[(i + 1) % len(prof)][1] - prof[(i + 1) % len(prof)][0] * prof[i][1]
               for i in range(len(prof)))
    if area < 0:
        prof = list(reversed(prof))
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    a = [bm.verts.new((x0 * MM, y * MM, z * MM)) for y, z in prof]
    b = [bm.verts.new((x1 * MM, y * MM, z * MM)) for y, z in prof]
    n = len(prof)
    bm.faces.new(list(reversed(a)))
    bm.faces.new(b)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((a[i], a[j], b[j], b[i]))
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    sc.collection.objects.link(o)
    o.data.materials.append(m)
    return o


def join(objs, name):
    objs = [o for o in objs if o]
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    objs[0].name = name
    return objs[0]


def boolean(target, tool, op, self_ix=False):
    b = target.modifiers.new(op[:3], "BOOLEAN")
    b.operation = op
    b.object = tool
    b.solver = "EXACT"
    b.use_self = self_ix
    b.use_hole_tolerant = self_ix
    bpy.context.view_layer.objects.active = target
    n0 = len(target.data.polygons)
    bpy.ops.object.modifier_apply(modifier=b.name)
    bm = bmesh.new()
    bm.from_mesh(target.data)
    nm = sum(not e.is_manifold for e in bm.edges)
    bm.free()
    print(f"  {op[:3]} {tool.name[:14]:14s} -> {target.name}: {n0} -> {len(target.data.polygons)} faces, non-manifold edges {nm}")
    bpy.data.objects.remove(tool, do_unlink=True)


def cut(t, tool, self_ix=False):
    boolean(t, tool, "DIFFERENCE", self_ix)


def union(t, tool, self_ix=False):
    boolean(t, tool, "UNION", self_ix)


# ---- outline -----------------------------------------------------------------------------------------
# Inner faces: the SMA wall's inside (X -109.6, as the mount), 1 mm past the carrier on the right, the rear
# connectors' faces + 0.5 at the back, the carrier's front edge -2.2 at the front, and a nose around the RJ45 tab.
INNER = [(-109.6, -12.2), (-34.0, -12.2), (-34.0, -32.3), (-5.0, -32.3), (-5.0, -12.2), (131.0, -12.2),
         (131.0, 112.0), (-109.6, 112.0)]
WALL = [3.5, 3.5, 3.5, 3.5, 3.5, 3.5, 3.5, 4.0]      # edge i: INNER[i] -> INNER[i+1]; the SMA wall is 4 mm
OUTER = offset_ortho(INNER, WALL)
cvx = convex(INNER)
R_IN = [2.5 if c else 6.0 for c in cvx]
R_OUT = [r + 3.5 if c else r - 3.5 for r, c in zip(R_IN, cvx)]
ring_in = round_poly(INNER, R_IN)
ring_out = round_poly(OUTER, R_OUT)
CH = 2.0                                             # chamfer on the outer top and bottom edges
ring_out_ch = round_poly(offset_ortho(OUTER, [-CH] * len(OUTER)), [max(r - CH, 0.5) if c else r + CH
                                                                    for r, c in zip(R_OUT, cvx)])
ring_tongue = round_poly(offset_ortho(INNER, [TONGUE_W] * 8), [r + TONGUE_W if c else r - TONGUE_W
                                                               for r, c in zip(R_IN, cvx)])
ring_groove = round_poly(offset_ortho(INNER, [TONGUE_W + TONGUE_GAP] * 8),
                         [r + TONGUE_W + TONGUE_GAP if c else r - TONGUE_W - TONGUE_GAP for r, c in zip(R_IN, cvx)])
ring_in_gap = round_poly(offset_ortho(INNER, [-TONGUE_GAP] * 8), [max(r - TONGUE_GAP, 0.3) if c else r + TONGUE_GAP
                                                                 for r, c in zip(R_IN, cvx)])

# ---- bottom tray ---------------------------------------------------------------------------------------
bottom = stack("case_bottom", [(ring_out_ch, Z_BOT), (ring_out, Z_BOT + CH), (ring_out, Z_SPLIT)])
cut(bottom, prism("b_cav", ring_in, Z_FLOOR, Z_SPLIT + 1))
tongue = prism("tongue", ring_tongue, Z_SPLIT - 0.5, Z_SPLIT + TONGUE_H)
cut(tongue, prism("t_in", ring_in, Z_SPLIT - 1, Z_SPLIT + TONGUE_H + 1))
union(bottom, tongue)

# honeycomb: three slabs (the carrier at its underside, the adapter's overhang and its tab at theirs)
SLABS = [((-9.7, 129.7, -9.7, 108.7), CARRIER_BOT),
         ((-107.2, -10.0, -9.7, 108.7), ADAPTER_BOT),
         ((-28.5, -10.6, -30.7, -10.0), ADAPTER_BOT)]
slabs = [box(f"slab{i}", x0, x1, y0, y1, Z_FLOOR - 0.2, zt) for i, ((x0, x1, y0, y1), zt) in enumerate(SLABS)]
hc = join(slabs, "honeycomb")
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.mesh.remove_doubles(threshold=1e-6)
bpy.ops.object.mode_set(mode="OBJECT")
holes = []
rc = (HEX_S - HEX_T) / math.sqrt(3)            # circumradius of a hole
py = HEX_S * math.sqrt(3) / 2
for j in range(-5, 18):
    for i in range(-14, 16):
        x, y = i * HEX_S + (HEX_S / 2 if j % 2 else 0), j * py
        for (x0, x1, y0, y1), _ in SLABS:
            if x0 + rc + HEX_T <= x <= x1 - rc - HEX_T and y0 + rc + HEX_T <= y <= y1 - rc - HEX_T:
                holes.append(cyl("hex", x, y, Z_FLOOR + 0.6, 5, 2 * rc, verts=6, rot=math.pi / 6))
                break
print("honeycomb cells", len(holes))
cut(hc, join(holes, "hexes"))

# pockets under everything that hangs below either board: each part's footprint + 0.8, down to its bottom - 0.6
def parts():
    kv = bpy.data.objects["KV260_STARTERKIT_ASM_2_ASM_3_ASM"]
    comp = [o for o in bpy.data.objects if o.name == "COMPONENTS"][0]
    groups = list(comp.children)
    for o in bpy.data.objects:
        if o.parent and o.parent.parent == kv and o.name.startswith("J"):
            groups.append(o)
    ad = bpy.data.objects["ADAPTER"]
    n_kv = len(groups)
    groups += list(ad.children[0].children)
    for k, g in enumerate(groups):
        vs, st = [], [g]
        while st:
            c = st.pop()
            st += list(c.children)
            if c.type == "MESH":
                vs += [c.matrix_world @ Vector(b) / MM for b in c.bound_box]
        if vs:
            yield g.name, [min(v[i] for v in vs) for i in range(3)], [max(v[i] for v in vs) for i in range(3)], k >= n_kv


def leaves():
    """Every mesh of the KV260 and the adapter smaller than 60 mm (not the boards' own layers): world bbox."""
    for r in (bpy.data.objects["KV260_STARTERKIT_ASM_2_ASM_3_ASM"], bpy.data.objects["ADAPTER"]):
        st = [r]
        while st:
            c = st.pop()
            st += list(c.children)
            if c.type == "MESH" and not c.hide_render:
                vs = [c.matrix_world @ Vector(b) / MM for b in c.bound_box]
                lo, hi = [min(v[i] for v in vs) for i in range(3)], [max(v[i] for v in vs) for i in range(3)]
                if hi[0] - lo[0] < 60 and hi[1] - lo[1] < 60:
                    yield c.name, lo, hi


PARTS = [(n, lo, hi) for n, lo, hi, _ in parts()]
pk_rects = []
for name, lo, hi, on_adapter in parts():
    ref = ADAPTER_BOT if on_adapter and lo[0] < -10.0 else CARRIER_BOT
    if lo[2] < ref - 0.05 and hi[2] > Z_FLOOR:
        pk_rects.append((lo[0] - 0.8, hi[0] + 0.8, lo[1] - 0.8, hi[1] + 0.8, max(lo[2] - 0.6, Z_FLOOR + 0.6)))
# and any single mesh the part groups missed (parts outside COMPONENTS, loose pins)
for name, lo, hi in leaves():
    ref = ADAPTER_BOT if lo[0] < -10.0 else CARRIER_BOT
    if lo[2] < ref - 0.05 and hi[2] > Z_FLOOR:
        r = (lo[0] - 0.8, hi[0] + 0.8, lo[1] - 0.8, hi[1] + 0.8, max(lo[2] - 0.6, Z_FLOOR + 0.6))
        if not any(p[0] <= r[0] and r[1] <= p[1] and p[2] <= r[2] and r[3] <= p[3] and p[4] <= r[4] for p in pk_rects):
            pk_rects.append(r)
pockets = [box("pk", *r, 6) for r in pk_rects]
# the RJ45's through-hole pins (its footprint has no 3D model): as the mount's pin pocket
pockets.append(box("pk_rj45", -28.0, -11.0, -27.2, -11.2, ADAPTER_BOT - 4.5, 6))
# Rev05 input protection on the adapter's underside (U1009, Q1003, D1003 SMC 2.3 mm, C1090, C1091), not in the
# assembly's glTF yet: board x 95.6-111.4, y 137.6-151.2 (courtyards) through k2m, 0.6 mm margin, 3.1 mm deep
pockets.append(box("pk_prot", -44.6, -29.8, 86.0, 103.0, ADAPTER_BOT - 3.1, 6))
print("pockets", len(pockets))
cut(hc, join(pockets, "pockets"), self_ix=True)

# posts: carrier corners and H3-H5 to the boards, with M3 heat-set insert holes (as the mount)
def k2m(x, y):
    return (107.247 - y, 198.004 - x)


CARRIER_HOLES = [(-5, -5), (-5, 104), (125, -5), (125, 104)]
ADAPTER_SUP = [k2m(93.0, 209.75), k2m(148.5, 192.5), k2m(204.0, 209.75)]
posts = [cyl(f"pc{i}", x, y, Z_FLOOR - 0.2, CARRIER_BOT, 9.0) for i, (x, y) in enumerate(CARRIER_HOLES)]
posts += [cyl(f"pa{i}", x, y, Z_FLOOR - 0.2, ADAPTER_BOT, 8.0) for i, (x, y) in enumerate(ADAPTER_SUP)]
union(hc, join(posts, "posts"), self_ix=True)
inserts = [cyl(f"ic{i}", x, y, CARRIER_BOT - 5.7, 5, 4.0) for i, (x, y) in enumerate(CARRIER_HOLES)]
inserts += [cyl(f"ia{i}", x, y, ADAPTER_BOT - 5.7, 5, 4.0) for i, (x, y) in enumerate(ADAPTER_SUP)]
cut(hc, join(inserts, "inserts"), self_ix=True)
union(bottom, hc)

# ---- lugs: lid and tray close on them; vehicle ears ------------------------------------------------------
LUG_X = {"front": [-95.0, 70.0, 127.0], "back": [-95.0, -20.0, 127.0]}   # clear of the I/O openings and J1001
Y_OUT = {"front": OUTER[0][1], "back": OUTER[6][1]}
LUG_W, LUG_D = 14.0, 10.0
LUG_HOLE = 4.4                        # M4 clearance; the snap pins are 4.1
NUT_AF, NUT_H = 7.2, 3.4              # M4 nut (7 mm AF) trap under the tray's lug
lugs_b, lugs_l, lug_holes = [], [], []
for side, xs in LUG_X.items():
    s = -1 if side == "front" else 1
    y0 = Y_OUT[side]
    for x in xs:
        ya, yb = sorted((y0 - s * 0.5, y0 + s * LUG_D))
        yc = y0 + s * (LUG_D - 4.8)
        lb = box("lugb", x - LUG_W / 2, x + LUG_W / 2, ya, yb, Z_SPLIT - 8.0, Z_SPLIT)
        for gx in (x - LUG_W / 2, x + LUG_W / 2 - 3.0):           # two ribs under each lug, down the wall
            lugs_b.append(xprism("gus", [(y0 - s * 0.5, Z_BOT + CH + 0.5), (y0 - s * 0.5, Z_SPLIT - 7.9),
                                         (y0 + s * (LUG_D - 0.5), Z_SPLIT - 7.9)], gx, gx + 3.0))
        lugs_b.append(lb)
        lugs_l.append(box("lugl", x - LUG_W / 2, x + LUG_W / 2, ya, yb, Z_SPLIT, Z_SPLIT + 7.0, LID))
        for gx in (x - LUG_W / 2, x + LUG_W / 2 - 3.0):           # 45-degree ribs above: the lid prints upside down
            lugs_l.append(xprism("lgus", [(y0 - s * 0.5, Z_SPLIT + 6.9), (y0 + s * (LUG_D - 0.5), Z_SPLIT + 6.9),
                                          (y0 - s * 0.5, Z_SPLIT + 6.9 + LUG_D)], gx, gx + 3.0, LID))
        lug_holes.append((x, yc))
union(bottom, join(lugs_b, "lugs_b"), self_ix=True)
# vehicle ears at the floor, M5 slots
EAR_X = [-65.0, 100.0]
ears, slots = [], []
for side in ("front", "back"):
    s = -1 if side == "front" else 1
    y0 = Y_OUT[side]
    for x in EAR_X:
        ya, yb = sorted((y0 - s * 0.5, y0 + s * 15.0))
        ears.append(box("ear", x - 11, x + 11, ya, yb, Z_BOT, Z_BOT + 5.0))
        for dx in (-11.0, 8.0):                                    # two ribs per ear, up the wall
            ears.append(xprism("eg", [(y0 - s * 0.5, Z_BOT + 4.9), (y0 - s * 0.5, -1.0),
                                      (y0 + s * 14.5, Z_BOT + 4.9)], x + dx, x + dx + 3.0))
        yc = y0 + s * 9.0
        slots.append(join([cyl("s1", x, yc - 2, Z_BOT - 1, Z_BOT + 6, 5.5), cyl("s2", x, yc + 2, Z_BOT - 1, Z_BOT + 6, 5.5),
                           box("s3", x - 2.75, x + 2.75, yc - 2, yc + 2, Z_BOT - 1, Z_BOT + 6)], "slot"))
union(bottom, join(ears, "ears"), self_ix=True)
cut(bottom, join(slots, "slots"), self_ix=True)
holes_b = []
for x, y in lug_holes:
    holes_b.append(cyl("lh", x, y, Z_SPLIT - 9, Z_SPLIT + 1, LUG_HOLE))
    holes_b.append(cyl("nut", x, y, Z_SPLIT - 8.1, Z_SPLIT - 8.0 + NUT_H, NUT_AF / math.cos(math.pi / 6), verts=6))
cut(bottom, join(holes_b, "lug_holes_b"), self_ix=True)

# ---- the lid -----------------------------------------------------------------------------------------------
lid = stack("case_lid", [(ring_out, Z_SPLIT), (ring_out, Z_TOP - CH), (ring_out_ch, Z_TOP)])
lid.data.materials.clear()
lid.data.materials.append(LID)
_bm = bmesh.new(); _bm.from_mesh(lid.data); print("lid start non-manifold", sum(not e.is_manifold for e in _bm.edges)); _bm.free()
cut(lid, prism("l_cav", ring_in, Z_SPLIT - 1, Z_TOP_IN))
cut(lid, prism("groove", ring_groove, Z_SPLIT - 1, Z_SPLIT + TONGUE_H + TONGUE_GAP))
union(lid, join(lugs_l, "lugs_l"), self_ix=True)
holes_l = []
for x, y in lug_holes:
    holes_l.append(cyl("lhl", x, y, Z_SPLIT - 1, Z_SPLIT + 8, LUG_HOLE))
cut(lid, join(holes_l, "lug_holes_l"), self_ix=True)

# lid honeycomb under the ceiling, 4.5 mm deep, clear of the fan
FAN = (49.0, 123.0, 17.0, 77.0)
FAN_C, FAN_R = (86.1, 47.0), 27.0
lhc = box("lid_honeycomb", INNER[0][0] + 0.5, INNER[5][0] - 0.5, INNER[0][1] + 0.5, INNER[6][1] - 0.5,
          Z_TOP_IN - 4.5, Z_TOP_IN + 0.2)
lholes = []
for j in range(-3, 15):
    for i in range(-13, 15):
        x, y = i * HEX_S + (HEX_S / 2 if j % 2 else 0), j * py
        if INNER[0][0] + rc + 2.5 < x < INNER[5][0] - rc - 2.5 and INNER[0][1] + rc + 2.5 < y < INNER[6][1] - rc - 2.5:
            lholes.append(cyl("lhex", x, y, Z_TOP_IN - 6, Z_TOP_IN - 0.6, 2 * rc, verts=6, rot=math.pi / 6))
cut(lhc, join(lholes, "lhexes"))
cut(lhc, box("fan_clear", FAN[0], FAN[1], FAN[2], FAN[3], Z_TOP_IN - 6, Z_TOP_IN + 1))
union(lid, lhc)

# clamp posts: over the screw heads at the corners and H3-H5 (a ring on the board around the head), and a
# block on the RJ45; each stops PAD above its target for a TPU pad
clamps, recesses = [], []
for (x, y) in [(-5, -5), (-5, 104)] + ADAPTER_SUP:
    clamps.append(cyl("cl", x, y, ADAPTER_TOP + PAD, Z_TOP_IN + 0.2, 10.0 if (x, y) in [(-5, -5), (-5, 104)] else 9.0))
    recesses.append(cyl("rc", x, y, ADAPTER_TOP + PAD - 1, ADAPTER_TOP + 2.6, 7.0))
for (x, y) in [(125, -5), (125, 104)]:
    clamps.append(cyl("cl", x, y, 0.0 + PAD, Z_TOP_IN + 0.2, 10.0))
    recesses.append(cyl("rc", x, y, PAD - 1, 2.6, 7.0))
clamps.append(box("rj_clamp", -27.0, -12.0, -30.5, -12.5, 15.9 + PAD, Z_TOP_IN + 0.2))
union(lid, join(clamps, "clamps"))
cut(lid, join(recesses, "recesses"))
# notch the clamps (and their pads) around any part that stands taller than the board under them
CLAMP_FOOT = [((x, y), 5.0, ADAPTER_TOP) for x, y in [(-5, -5), (-5, 104)]] + \
             [((x, y), 4.5, ADAPTER_TOP) for x, y in ADAPTER_SUP] + [((x, y), 5.0, 0.0) for x, y in [(125, -5), (125, 104)]]
NOTCH = []
for name, lo, hi in leaves():
    for (cx, cy), r, zb in CLAMP_FOOT:
        if lo[0] < cx + r and hi[0] > cx - r and lo[1] < cy + r and hi[1] > cy - r and zb + 0.1 < hi[2] < zb + 20:
            if math.hypot(max(lo[0] - cx, 0, cx - hi[0]), max(lo[1] - cy, 0, cy - hi[1])) < r and \
                    math.hypot(max(lo[0] - cx, 0, cx - hi[0]), max(lo[1] - cy, 0, cy - hi[1])) > 2.6:
                NOTCH.append((lo[0] - 0.6, hi[0] + 0.6, lo[1] - 0.6, hi[1] + 0.6, zb - 1, hi[2] + PAD + 0.6))
print("clamp notches", len(NOTCH))
if NOTCH:
    cut(lid, join([box("notch", *n) for n in NOTCH], "notches"), self_ix=True)

# fan grille (hexagonal holes in a circle over the fan) and side vents
grille = []
gs, gt = 7.0, 1.6
grc = (gs - gt) / math.sqrt(3)
for j in range(-5, 6):
    for i in range(-5, 6):
        x = FAN_C[0] + i * gs + (gs / 2 if j % 2 else 0)
        y = FAN_C[1] + j * gs * math.sqrt(3) / 2
        if math.hypot(x - FAN_C[0], y - FAN_C[1]) < FAN_R - grc:
            grille.append(cyl("g", x, y, Z_TOP_IN - 1, Z_TOP + 1, 2 * grc, verts=6, rot=math.pi / 6))
cut(lid, join(grille, "grille"))
vents = []
# v2: the box runs at overpressure, so the exhaust sets the fan's flow: 17 slots of 3.5 x 21 mm along the whole
# right wall (the CFD of the built v2: 13 slots of 3 x 16 mm held the cavity at +9.7 Pa; these and the open intake
# bring it to +6.0 Pa and the fan from 2.57 to 3.62 CFM). They start 1.5 mm above the tongue's groove.
NR = 17 if V2 else 9
for k in range(NR):                                            # right wall, beside the fan-sink
    y = (4.0 if V2 else 22.0) + k * 6.0
    vents.append(box("vr", INNER[5][0] - 1, OUTER[5][0] + 1, y, y + (3.5 if V2 else 3.0),
                     7.5 if V2 else 12.0, 28.5 if V2 else 26.0))
if not V2:                                                     # v2 closes the SMA wall: dust stays out
    for k in range(14):                                        # SMA wall, above the SMAs: air across the adapter
        y = 4.0 + k * 7.0
        vents.append(box("vl", OUTER[7][0] - 1, INNER[7][0] + 1, y, y + 3.0, 12.0, 26.0))
cut(lid, join(vents, "vents"))

# ---- v2: a 50 x 50 x 10 mm 5 V fan blowing onto the adapter's hot strip, under a filtered grille ----------
# Over U401 / Y401 / U501 / U502-U503 / U1201 (the strip along the adapter's front edge; ENCLOSURE_V2_THERMAL.md).
# Inside: a 4 mm square duct from the ceiling to the fan, so it can only draw through the grille; four bosses with
# 2.5 mm pilots for M3 self-tapping fan screws from below. Outside: a 58 x 58 x 1.2 mm recess for a 100-mesh
# stainless filter, held by a printed grille frame (case_v2_filter_frame.stl) with four M2.5 x 6 screws.
FAN2_C, FAN2, FAN2_P = (-40.0, 14.0), 50.0, 40.0
filter_frame = None
if V2:
    fx, fy = FAN2_C
    h = FAN2 / 2
    ZF = Z_TOP_IN - 4.0                                        # fan top: 4 mm plenum under the grille
    cut(lid, box("fan2_clear", fx - h - 1.5, fx + h + 1.5, fy - h - 1.5, fy + h + 1.5, ZF - 0.5, Z_TOP_IN + 0.01))
    duct = [box("d1", fx - h - 1.2, fx + h + 1.2, fy - h - 1.2, fy - h, ZF, Z_TOP_IN + 0.2),
            box("d2", fx - h - 1.2, fx + h + 1.2, fy + h, fy + h + 1.2, ZF, Z_TOP_IN + 0.2),
            box("d3", fx - h - 1.2, fx - h, fy - h, fy + h, ZF, Z_TOP_IN + 0.2),
            box("d4", fx + h, fx + h + 1.2, fy - h, fy + h, ZF, Z_TOP_IN + 0.2)]
    for sx in (-1, 1):
        for sy in (-1, 1):
            duct.append(cyl("fb", fx + sx * FAN2_P / 2, fy + sy * FAN2_P / 2, ZF, Z_TOP_IN + 0.2, 7.0))
    union(lid, join(duct, "fan2_duct"), self_ix=True)
    pil = [cyl("fp", fx + sx * FAN2_P / 2, fy + sy * FAN2_P / 2, ZF - 1, Z_TOP_IN - 0.8, 2.5) for sx in (-1, 1) for sy in (-1, 1)]
    cut(lid, join(pil, "fan2_pilots"))
    # the filter recess and the frame's screw pilots, outside the duct
    R2 = 29.0
    cut(lid, box("frecess", fx - R2, fx + R2, fy - R2, fy + R2, Z_TOP - 1.2, Z_TOP + 1))
    fsp = [cyl("fs", fx + sx * (R2 - 3.0), fy + sy * (R2 - 3.0), Z_TOP - 6.0, Z_TOP, 2.1) for sx in (-1, 1) for sy in (-1, 1)]
    cut(lid, join(fsp, "frame_pilots"))
    # Intake: the fan's whole 47 mm bore, open but for six 1.6 mm spokes and a 10 mm hub (86 % open, 1550 mm2).
    # A 7 mm honeycomb here (built first) left 39 cells, 985 mm2, and the CFD of the built v2 found the fan choked
    # by it: 2.57 CFM against 3.62 with this ring and the wider exhaust below (ENCLOSURE_V2_THERMAL.md, built v2).
    # The lid's spokes and the frame's, one above the other, clamp the mesh between them.
    def spoke_ring(name, z0, z1, r_out=23.5, r_hub=5.0, spoke=1.6, n=6):
        secs = []
        for k in range(n):
            a0, a1 = 2 * math.pi * k / n, 2 * math.pi * (k + 1) / n
            do, di = math.asin(spoke / 2 / r_out), math.asin(spoke / 2 / r_hub)
            pts = [(fx + r_out * math.cos(a), fy + r_out * math.sin(a))
                   for a in (a0 + do + (a1 - a0 - 2 * do) * t / 16 for t in range(17))]
            pts += [(fx + r_hub * math.cos(a), fy + r_hub * math.sin(a))
                    for a in (a1 - di - (a1 - a0 - 2 * di) * t / 6 for t in range(7))]
            secs.append(prism(name, pts, z0, z1))
        return join(secs, name)
    cut(lid, spoke_ring("grille2", Z_TOP_IN - 1, Z_TOP + 1))
    # the printed frame that holds the mesh: the same spoke ring, 1.2 mm, four countersunk-free M2.5 holes
    filter_frame = box("case_v2_filter_frame", fx - R2 + 0.2, fx + R2 - 0.2, fy - R2 + 0.2, fy + R2 - 0.2, Z_TOP - 1.2, Z_TOP, LID)
    g3 = [spoke_ring("g3", Z_TOP - 2, Z_TOP + 1)]
    g3 +=[cyl("fh", fx + sx * (R2 - 3.0), fy + sy * (R2 - 3.0), Z_TOP - 2, Z_TOP + 1, 2.8) for sx in (-1, 1) for sy in (-1, 1)]
    cut(filter_frame, join(g3, "frame_holes"))
    # the fan itself, for the renders only (not exported): a 5010 axial fan blowing down onto the adapter.
    # Frame with rounded corners, venturi bore and four 4.3 mm holes; seven swept, pitched blades on the rotor;
    # the motor hub with its label on the intake side; four struts holding the motor on the exhaust side.
    FANM = mat("fan PBT", (0.035, 0.035, 0.038), 0.55)
    LABEL = mat("fan label", (0.07, 0.07, 0.075), 0.45)        # dark: through the open intake it is in plain view
    sq = [(fx - h, fy - h), (fx + h, fy - h), (fx + h, fy + h), (fx - h, fy + h)]
    frame = prism("fan2_vis", round_poly(sq, [3.5] * 4), ZF - 10.0, ZF, FANM)
    cut(frame, cyl("fan2_bore", fx, fy, ZF - 11, ZF + 1, 47.0, verts=96))
    cut(frame, join([cyl("fan2_hole", fx + sx * 20, fy + sy * 20, ZF - 11, ZF + 1, 4.3, verts=24)
                     for sx in (-1, 1) for sy in (-1, 1)], "fan2_holes"))
    parts_v = [cyl("fan2_hub", fx, fy, ZF - 9.0, ZF - 0.6, 21.0, FANM, verts=64),
               cyl("fan2_label", fx, fy, ZF - 0.6, ZF - 0.5, 15.0, LABEL, verts=64),
               cyl("fan2_motor", fx, fy, ZF - 10.0, ZF - 9.0, 23.0, FANM, verts=64)]
    for k in range(4):                                        # motor struts, exhaust side
        a = math.pi / 4 + k * math.pi / 2
        st = box("strut", 11.0, 33.0, -1.0, 1.0, ZF - 10.0, ZF - 8.8, FANM)
        st.rotation_euler = (0, 0, a)
        st.location = (fx * MM, fy * MM, 0)
        parts_v.append(st)
    # blades: a ruled surface swept 50 degrees round the hub, leading edge 6 mm above the trailing edge,
    # more twist at the root than at the tip, 0.9 mm thick
    NR, NS = 8, 14
    for k in range(7):
        a0 = k * 2 * math.pi / 7
        bm = bmesh.new()
        grid = []
        for i in range(NR + 1):
            r = 10.2 + (23.0 - 10.2) * i / NR
            row = []
            for j in range(NS + 1):
                s = j / NS
                th = a0 + s * math.radians(50) + (r - 10.2) * 0.018
                pitch = 6.4 - 1.6 * (r - 10.2) / 12.8
                z = ZF - 5.0 + (0.5 - s) * pitch
                row.append(bm.verts.new((fx + r * math.cos(th), fy + r * math.sin(th), z)))
            grid.append(row)
        for i in range(NR):
            for j in range(NS):
                bm.faces.new((grid[i][j], grid[i + 1][j], grid[i + 1][j + 1], grid[i][j + 1]))
        me = bpy.data.meshes.new("blade")
        bm.to_mesh(me)
        bm.free()
        for v in me.vertices:
            v.co *= MM
        ob = bpy.data.objects.new("blade", me)
        bpy.context.scene.collection.objects.link(ob)
        me.materials.append(FANM)
        sol = ob.modifiers.new("t", "SOLIDIFY")
        sol.thickness, sol.offset = 0.9 * MM, 0.0
        bpy.context.view_layer.objects.active = ob
        bpy.ops.object.select_all(action="DESELECT")
        ob.select_set(True)
        bpy.ops.object.modifier_apply(modifier="t")
        parts_v.append(ob)
    for o in parts_v:
        if not o.data.materials:
            o.data.materials.append(FANM)
    fan_vis_all = join([frame] + parts_v, "fan2_vis")
    for p in fan_vis_all.data.polygons:
        p.use_smooth = True
    fan_vis_all.data.set_sharp_from_angle(angle=0.6)

# ---- openings: every connector that faces a wall, through both shells -------------------------------------
def merged(spans, gap=4.0):
    """(x0, x1, z0, z1) spans along a wall -> merged where closer than gap (no slivers between openings)."""
    out = []
    for a in sorted(spans):
        if out and a[0] - out[-1][1] < gap:
            b = out[-1]
            out[-1] = (b[0], max(b[1], a[1]), min(b[2], a[2]), max(b[3], a[3]))
        else:
            out.append(a)
    return out


def ribbed(spans, rib=1.6):
    """(x0, x1, z0, z1) spans along a wall, one cut-out per connector: where two would come closer than
    rib, both give way to a rib of that width centred in their gap (the wall stays closed between the
    KV260's connectors instead of one long window). Overlapping spans are merged."""
    out = []
    for a in sorted(spans):
        if out and a[0] < out[-1][1] - 2.0:          # true overlap (beyond the margins): one opening
            b = out[-1]
            out[-1] = (b[0], max(b[1], a[1]), min(b[2], a[2]), max(b[3], a[3]))
            continue
        if out and a[0] - out[-1][1] < rib:
            mid = (a[0] + out[-1][1]) / 2
            b = out[-1]
            out[-1] = (b[0], mid - rib / 2, b[2], b[3])
            a = (mid + rib / 2, a[1], a[2], a[3])
        out.append(a)
    return out


rear, front = [], []
for name, lo, hi in PARTS:
    if name in ("J10", "J5", "J6", "J12", "U44", "U46") and hi[1] > INNER[6][1] - 5.0:       # rear I/O
        # 1 mm round each connector's face for the plugs' overmoulds, from just under its body
        rear.append((lo[0] - 1.0, hi[0] + 1.0, max(lo[2], -0.5) - 0.5, hi[2] + 1.0))
    if name in ("J4", "J11", "J2") and lo[1] < INNER[0][1] + 5.0:                              # front
        m = 2.5 if name == "J4" else 1.0
        front.append((lo[0] - m, hi[0] + m, max(lo[2], -0.5) - m * 0.6, hi[2] + m))
openings = [box("op_rear", x0, x1, INNER[6][1] - 6, OUTER[6][1] + 1, z0, z1) for x0, x1, z0, z1 in ribbed(rear)]
openings += [box("op_front", x0, x1, OUTER[0][1] - 1, INNER[0][1] + 3, z0, z1) for x0, x1, z0, z1 in merged(front)]
print("rear openings", [tuple(round(v, 1) for v in s) for s in ribbed(rear)])
openings.append(box("op_rj45", -27.9, -11.1, OUTER[2][1] - 1, INNER[2][1] + 1, 2.0, 16.3))     # the adapter's RJ45
# the adapter's 12 V jack J1001 (PJ-102AH, barrel axis 6.5 mm over the board) faces the rear wall 3.5 mm inside
# it: a 5.5/2.1 plug's 9.5 mm barrel would not reach through 7 mm of air and wall, so the plug's moulded body
# goes in too, through a U from the shells' joint up round the axis (12 mm: moulded bodies are 8-11 mm)
for name, lo, hi in PARTS:
    if name == "J1001":
        jx, jz = (lo[0] + hi[0]) / 2, ADAPTER_BOT + 1.6 + 6.5
        print("DC jack opening at x", round(jx, 2), "axis z", round(jz, 2))
        prof = [(jx - 6.0, Z_SPLIT - 0.6), (jx + 6.0, Z_SPLIT - 0.6)] + \
               [(jx + 6.0 * math.cos(math.pi * k / 24), jz + 6.0 * math.sin(math.pi * k / 24)) for k in range(25)]
        y0, y1 = INNER[6][1] - 4, OUTER[6][1] + 1
        me = bpy.data.meshes.new("dc_u")
        bm = bmesh.new()
        a = [bm.verts.new((x * MM, y0 * MM, z * MM)) for x, z in prof]
        b = [bm.verts.new((x * MM, y1 * MM, z * MM)) for x, z in prof]
        bm.faces.new(a)
        bm.faces.new(list(reversed(b)))
        for i in range(len(prof)):
            j = (i + 1) % len(prof)
            bm.faces.new((a[j], a[i], b[i], b[j]))
        bm.normal_update()
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me)
        bm.free()
        dco = bpy.data.objects.new("dc_u", me)
        sc.collection.objects.link(dco)
        openings.append(dco)
# J1103, the 2 x 20 IDC header for the ribbon to AERIS-10's ADAR1000 boards, outside the case: the ribbon
# (50.8 mm wide, about 1 mm thick) leaves through a 54 x 2.6 mm slot in the lid right above the header,
# its plug fitted before the lid goes on
for name, lo, hi in PARTS:
    if name == "J1103":
        xc, yc = (lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2
        openings.append(box("op_ribbon", xc - 1.3, xc + 1.3, yc - 27.0, yc + 27.0, Z_TOP_IN - 6, Z_TOP + 1))
        print("ribbon slot at x", round(xc, 2), "y", round(yc - 27, 1), "..", round(yc + 27, 1))
sma = []
for name, lo, hi in PARTS:
    if name.startswith(("J4", "J9")) and lo[0] < -110:
        yc, zc = (lo[1] + hi[1]) / 2, hi[2] - 3.175
        sma.append(box("sma", OUTER[7][0] - 1, INNER[7][0] + 1, yc - 3.35, yc + 3.35, zc - 3.35, zc + 3.35))
# a 1 mm recess along the SMA row on the outside, so the plugs' coupling nuts (7.94 AF) seat against the bodies'
# stops, not against the wall (the SMAs are 8.5 mm apart: one band, not twelve counterbores)
ys = [(lo[1] + hi[1]) / 2 for name, lo, hi in PARTS if name.startswith(("J4", "J9")) and lo[0] < -110]
zc = [hi[2] - 3.175 for name, lo, hi in PARTS if name.startswith(("J4", "J9")) and lo[0] < -110][0]
sma.append(box("cb_band", OUTER[7][0] - 1.0, OUTER[7][0] + 1.0, min(ys) - 4.8, max(ys) + 4.8, zc - 4.8, zc + 4.8))
print("SMA notches", len([o for o in sma if o.name.startswith("sma")]))
cbs = [o for o in sma if o.name.startswith("cb")]
notches = [o for o in sma if not o.name.startswith("cb")]
for group in (openings + notches, cbs):
    a = join(group, "openings")
    b = a.copy()
    b.data = a.data.copy()
    sc.collection.objects.link(b)
    cut(bottom, a)
    cut(lid, b)

# label, debossed 0.6 mm in the lid
# clear of the ribbon slot over J1103 (x -75.7, y 26-80) and of v2's grille
bpy.ops.object.text_add(location=(-70 * MM, 96 * MM, (Z_TOP - 0.6) * MM))
tx = bpy.context.object
tx.data.body = "KV260 · IAS2RF"
tx.data.size = 9 * MM
tx.data.extrude = 1.0 * MM
tx.data.align_x = "CENTER"
tx.data.align_y = "CENTER"
bpy.ops.object.convert(target="MESH")
cut(lid, tx, self_ix=True)

# ---- TPU corner bumpers (optional, for handling and drops) ------------------------------------------------
# An L-shaped TPU 95A block on each corner, BUMP mm thick outside the walls, from the floor to the lid top. It slides
# on from the front or the back (both arms lie outside the walls; the lug and its ribs go into a pocket) and the
# lug's own M4 goes through it, so it cannot come off. The FEA (docs/ENCLOSURE.md section 5) is what sizes BUMP:
# the bare case's 1 m corner drop is far over the plastic's strength; ~8 mm of gyroid TPU crush brings the peak
# to ~115 g.
BUMP, BUMP_ARM, BUMP_CH, BUMP_GAP = 18.0, 22.0, 5.0, 0.15
XL, XR = min(p[0] for p in OUTER), max(p[0] for p in OUTER)
YF, YB = Y_OUT["front"], Y_OUT["back"]
side_lim = {("L", "front"): min(min(ys) - 6.5, 3.5) - YF, ("L", "back"): YB - max(max(ys) + 6.5, 101.5),
            ("R", "front"): 21.0 - YF, ("R", "back"): YB - 76.0}
bumpers = []
for sx, xc in (("L", XL), ("R", XR)):
    for sy, yc in (("front", YF), ("back", YB)):
        u = -1 if sx == "L" else 1                 # outwards in X
        v = -1 if sy == "front" else 1             # outwards in Y
        g, T, A, S = BUMP_GAP, BUMP, BUMP_ARM, side_lim[(sx, sy)]
        # keep the arm along the front/rear wall 4 mm clear of that wall's connector openings (13 Nov: the
        # right-rear bumper half covered the KV260's RJ45, seen in the new KV260-side render)
        for x0, x1, _z0, _z1 in merged(rear if sy == "back" else front):
            lim = (xc - x1 - 4.0) if sx == "R" else (x0 - xc - 4.0)
            if lim < A:
                A = lim
        print(f"bumper {sx}{sy}: arm {A:.1f} mm")
        # L outline in local (outwards-x, outwards-y) coordinates, the outer corner chamfered
        loc = [(g, -S), (T, -S), (T, T - BUMP_CH), (T - BUMP_CH, T), (-A, T), (-A, g), (g, g)]
        ring = [(xc + u * a, yc + v * b) for a, b in loc]
        if u * v < 0:                              # keep it CCW
            ring.reverse()
        bp = prism(f"bumper_{sx}{sy}", ring, Z_BOT, Z_TOP, TPU)
        for src in (bottom, lid):                  # the lugs, their ribs and the ears' ribs go into pockets
            cp = src.copy()
            cp.data = src.data.copy()
            sc.collection.objects.link(cp)
            cut(bp, cp)
        for x, y in lug_holes:
            if abs(x - xc) < A + T and abs(y - yc) < 15:
                h = [cyl("bh", x, y, Z_BOT - 1, Z_TOP + 1, 4.6, TPU),
                     cyl("bcb", x, y, Z_SPLIT + 10.0, Z_TOP + 1, 9.0, TPU),          # M4 x 20 from here
                     cyl("bnut", x, y, Z_BOT - 1, Z_SPLIT - 8.0 + 0.01, 10.0, TPU)]  # nut / pin access below
                for c in h:
                    cut(bp, c)
        bumpers.append(bp)

# ---- loose parts: snap pins and TPU pads (built at the origin, placed for the scene) ------------------------
def snap_pin(name, x, y, z_head):
    """Head 8 x 2 on the lid's lug; shank 4.1 through both lugs; a split tip with barbs that catch on the
    nut trap's ceiling. Printed on its side (the flat at -X), so the prongs bend across the layers."""
    L = 7.0 + 8.0 - NUT_H + 0.2               # lid lug + tray lug - nut trap, to the barb's catch
    parts_ = [cyl("ph", 0, 0, 0, 2.0, 8.0, PIN), cyl("ps", 0, 0, -L - 2.6, 0.1, 4.1, PIN)]
    barb = loft("pb", [(2.05 * math.cos(a), 2.05 * math.sin(a)) for a in [2 * math.pi * k / 32 for k in range(32)]], -L - 1.4,
                [(2.55 * math.cos(a), 2.55 * math.sin(a)) for a in [2 * math.pi * k / 32 for k in range(32)]], -L, PIN)
    tip = loft("pt", [(1.6 * math.cos(a), 1.6 * math.sin(a)) for a in [2 * math.pi * k / 32 for k in range(32)]], -L - 2.6,
               [(2.55 * math.cos(a), 2.55 * math.sin(a)) for a in [2 * math.pi * k / 32 for k in range(32)]], -L - 1.4, PIN)
    p = parts_[0]
    for q in parts_[1:] + [barb, tip]:
        union(p, q)
    p.name = name
    cut(p, box("split", -0.7, 0.7, -5, 5, -L - 3, -L + 5.5))
    cut(p, box("flat", -5, -1.75, -5, 5, -L - 4, 3))
    cut(p, box("flat2", 1.75, 5, -5, 5, -L - 4, 3))
    p.location = Vector((x, y, z_head)) * MM
    return p


pins = [snap_pin(f"pin{i}", x, y, Z_SPLIT + 7.0) for i, (x, y) in enumerate(lug_holes)]
pads = []
for (x, y) in [(-5, -5), (-5, 104)] + ADAPTER_SUP:
    p = cyl("pad", x, y, ADAPTER_TOP, ADAPTER_TOP + PAD, 10.0 if (x, y) in [(-5, -5), (-5, 104)] else 9.0, TPU)
    cut(p, cyl("padh", x, y, ADAPTER_TOP - 1, ADAPTER_TOP + 2, 7.0))
    pads.append(p)
for (x, y) in [(125, -5), (125, 104)]:
    p = cyl("pad", x, y, 0.0, PAD, 10.0, TPU)
    cut(p, cyl("padh", x, y, -1, 2, 7.0))
    pads.append(p)
pads.append(box("pad_rj", -27.0, -12.0, -30.5, -12.5, 15.9, 15.9 + PAD, TPU))
for p in pads[:-1]:
    for n in NOTCH:
        if p.location.length == 0:
            bb = [p.matrix_world @ Vector(b) / MM for b in p.bound_box]
            if n[0] < max(v.x for v in bb) and n[1] > min(v.x for v in bb) and \
                    n[2] < max(v.y for v in bb) and n[3] > min(v.y for v in bb):
                cut(p, box("pad_notch", *n))

# the booleans leave big concave n-gons (the lid's top is one face with every hole in it); triangulate them
# here with ear clipping, so neither Cycles nor the STL exporter has to guess
for o in [bottom, lid] + bumpers:
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4], quad_method="BEAUTY", ngon_method="EAR_CLIP")
    nflip = sum(1 for f in bm.faces if f.normal.z < -0.9 and f.calc_center_median().z > (Z_TOP - 0.01) * MM)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    nm = sum(not e.is_manifold for e in bm.edges)
    print(o.name, "top faces pointing down before recalc:", nflip)
    bm.to_mesh(o.data)
    bm.free()
    if o.data.has_custom_normals:                  # inherited from the joined parts: they shade flat faces as boxes
        bpy.context.view_layer.objects.active = o
        bpy.ops.mesh.customdata_custom_splitnormals_clear()
    print(o.name, "triangulated, non-manifold edges", nm, "custom normals left", o.data.has_custom_normals)

for o in (bottom, lid):
    o.data.materials.clear()
    o.data.materials.append(CASE if o is bottom else LID)
    for f in o.data.polygons:
        f.use_smooth = False
    print(o.name, "manifold check: verts", len(o.data.vertices), "faces", len(o.data.polygons))

# ---- outputs ------------------------------------------------------------------------------------------------
def stl(objs, fn, loc0=None):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.wm.stl_export(filepath=fn, export_selected_objects=True, global_scale=1000.0, apply_modifiers=True)


if "--stl" in argv:
    out = os.path.join(ROOT, argv[argv.index("--stl") + 1])
    os.makedirs(out, exist_ok=True)
    PRE = "case_v2_" if V2 else "case_"
    stl([bottom], os.path.join(out, PRE + "bottom.stl"))
    # the lid prints upside down: export it flipped, its top on the bed
    lid.rotation_euler = (math.pi, 0, 0)
    stl([lid], os.path.join(out, PRE + "lid.stl"))
    if filter_frame:
        stl([filter_frame], os.path.join(out, "case_v2_filter_frame.stl"))
    lid.rotation_euler = (0, 0, 0)
    p0 = pins[0]
    loc = p0.location.copy()
    p0.location = (0, 0, 0)
    p0.rotation_euler = (0, math.pi / 2, 0)           # on its flat
    stl([p0], os.path.join(out, "case_pin.stl"))
    p0.location, p0.rotation_euler = loc, (0, 0, 0)
    stl([pads[0]], os.path.join(out, "case_pad_ring.stl"))
    stl([pads[-1]], os.path.join(out, "case_pad_rj45.stl"))
    for b in bumpers:
        stl([b], os.path.join(out, f"case_{b.name.lower()}.stl"))
    for o in (bottom, lid):
        d = o.dimensions
        print(f"{o.name}: {d.x / MM:.1f} x {d.y / MM:.1f} x {d.z / MM:.1f} mm")
BL = os.path.join(D, "case_v2.blend" if V2 else "case.blend")
bpy.ops.wm.save_as_mainfile(filepath=BL)
print("saved", BL)
