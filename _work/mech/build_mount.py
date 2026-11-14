"""The mount (docs/MECHANICAL.md): builds the KV260 + adapter + printed mount scene in Blender and writes
the printable parts as STL.

    blender -b --factory-startup --python _work/mech/build_mount.py -- [--stl mech]

Needs, in _work/mech/cache/ (git-ignored):
  kv260.glb  AMD's KV260 model (XTP679, KV260V2-Starter-Kit.stp; not redistributed here), converted with
             _work/mech/step2glb.py
  board.glb  kicad-cli pcb export glb --subst-models --include-tracks --include-pads --include-zones
             --include-silkscreen --include-soldermask --user-origin 0x0mm
             -o _work/mech/cache/board.glb CSI2-KRIA-KV260_Rev01.kicad_pcb
Writes _work/mech/cache/assembly.blend (for render_mount.py) and, with --stl DIR, the parts as STL.

All dimensions in mm, in the KV260 model's frame: Z = 0 is the carrier's top face, the table is at
Z -7.11 (the bottom of its rubber feet). The adapter is placed by INTERFACE_SPEC 5.3's registration:
KiCad (x, y) -> (107.247 - y, 198.004 - x), its underside 0.8 mm above the carrier.
"""
import bpy, math, os, sys
from mathutils import Vector, Matrix

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
D = os.path.join(ROOT, "_work", "mech", "cache")
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
MM = 0.001
TABLE = -7.11                  # the bottom of the KV260's rubber feet
PLATE_T = 4.0
BOARD_Z = 0.8                  # the adapter's underside (Hirose BM20B mated height)
PCB_T = 1.6


def k2m(x, y):
    """KiCad board coordinates -> the KV260 model's frame (mm)."""
    return (107.247 - y, 198.004 - x)


bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene


def imp(f):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=os.path.join(D, f))
    return [o for o in bpy.data.objects if o not in before]


# ---- the KV260, its rubber feet replaced by the mount's posts ----------------------------------
kv = imp("kv260.glb")
for o in kv:
    if "RUBBER_BUMPER" in o.name:
        o.hide_render = True
        o.hide_viewport = True
# ---- the adapter --------------------------------------------------------------------------------
bd = imp("board.glb")
rig = bpy.data.objects.new("ADAPTER", None)
sc.collection.objects.link(rig)
for o in bd:
    if o.parent is None:
        o.parent = rig
# KiCad's glTF frame is (x, -y, z) with the underside at z = 0: rotate -90 about Z, then translate
rig.matrix_world = Matrix.Translation(Vector((107.247, 198.004, BOARD_Z)) * MM) @ Matrix.Rotation(math.radians(-90), 4, "Z")


# ---- helpers ------------------------------------------------------------------------------------
def mat(name, rgb, rough=0.45, metal=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    return m


PETG = mat("PETG", (0.045, 0.05, 0.06), 0.55)
ALU = mat("Alu", (0.80, 0.80, 0.82), 0.3, 1.0)


def box(name, x0, x1, y0, y1, z0, z1, m=PETG, bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1)
    o = bpy.context.object
    o.name = name
    o.scale = ((x1 - x0) * MM, (y1 - y0) * MM, (z1 - z0) * MM)
    o.location = ((x0 + x1) / 2 * MM, (y0 + y1) / 2 * MM, (z0 + z1) / 2 * MM)
    bpy.ops.object.transform_apply(scale=True)
    if bevel:
        b = o.modifiers.new("bevel", "BEVEL")
        b.width = bevel * MM
        b.segments = 4
        b.limit_method = "ANGLE"
    o.data.materials.append(m)
    return o


def cyl(name, x, y, z0, z1, d, m=PETG, verts=48):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=d / 2 * MM, depth=(z1 - z0) * MM,
                                        location=(x * MM, y * MM, (z0 + z1) / 2 * MM))
    o = bpy.context.object
    o.name = name
    o.data.materials.append(m)
    return o


def boolean(target, tool, op):
    b = target.modifiers.new(op[:3] + "_" + tool.name, "BOOLEAN")
    b.operation = op
    b.object = tool
    b.solver = "EXACT"
    tool.hide_render = True
    tool.hide_viewport = True


def cut(target, tool):
    boolean(target, tool, "DIFFERENCE")


def union(target, tool):
    boolean(target, tool, "UNION")


# ---- the base: one printed plate, the table plane on top ---------------------------------------
base = box("Base", -120.5, 133.5, -36.0, 113.0, TABLE - PLATE_T, TABLE, bevel=1.5)
for (x0, x1, y0, y1) in ((5, 115, 8, 92), (-95, -20, 15, 95)):          # windows: air, weight
    cut(base, box("win", x0, x1, y0, y1, TABLE - PLATE_T - 1, TABLE + 1))

# carrier posts in place of the four rubber feet, M3 heat-set inserts under the corner holes
CARRIER_HOLES = [(-5, -5), (-5, 104), (125, -5), (125, 104)]
for i, (x, y) in enumerate(CARRIER_HOLES):
    union(base, cyl(f"post_carrier_{i}", x, y, TABLE, -1.59, 9.0))
# the adapter's outer supports H3-H5, up to its underside
ADAPTER_SUP = {n: k2m(*xy) for n, xy in {"H3": (93.0, 209.75), "H4": (148.5, 192.5), "H5": (204.0, 209.75)}.items()}
for n, (x, y) in ADAPTER_SUP.items():
    union(base, cyl(f"post_{n}", x, y, TABLE, BOARD_Z, 8.0))
for i, (x, y) in enumerate(CARRIER_HOLES):                               # insert holes, 4.0 x 5.7
    cut(base, cyl(f"ins_c{i}", x, y, -1.59 - 5.7, -1.0, 4.0))
for n, (x, y) in ADAPTER_SUP.items():
    cut(base, cyl(f"ins_{n}", x, y, BOARD_Z - 5.7, BOARD_Z + 1, 4.0))

# RJ45 tab pedestal: the tab (KiCad x 208-229.85, y 117.5-136) is model X -28.75..-10.25, Y -31.85..-10
union(base, box("pedestal", -33.0, -6.0, -33.5, -10.6, TABLE, BOARD_Z))
cut(base, box("pin_pocket", -28.0, -11.0, -27.2, -11.2, BOARD_Z - 4.5, BOARD_Z + 1))   # its THT pins
STRAP_X = (-30.7, -8.3)
for x in STRAP_X:
    cut(base, cyl(f"ins_strap{x}", x, -20.5, BOARD_Z - 5.7, BOARD_Z + 1, 4.0))

# SMA front wall: cradles each SMA's 6.35 mm square body between the board edge (X -107.5) and its thread
WALL_X0, WALL_X1 = -113.6, -109.6
union(base, box("sma_wall", WALL_X0, WALL_X1, -12.0, 111.0, TABLE, 6.2))
sma = []
for o in bd:
    if "." in o.name or not o.name.startswith(("J4", "J9")):
        continue
    vs, stack = [], [o]
    while stack:
        c = stack.pop()
        stack += list(c.children)
        if c.type == "MESH":
            vs += [c.matrix_world @ v.co for v in c.data.vertices]
    if vs and max(v.x for v in vs) - min(v.x for v in vs) > 0.008:
        sma.append(((min(v.y for v in vs) + max(v.y for v in vs)) / 2 / MM,
                    (min(v.z for v in vs) + max(v.z for v in vs)) / 2 / MM, o.name))
print("SMAs", [(round(y, 2), round(z, 2), r) for y, z, r in sorted(sma)])
for y, z, r in sma:
    cut(base, box(f"slot_{r}", WALL_X0 - 1, WALL_X1 + 1, y - 3.35, y + 3.35, z - 3.35, 20))

# ---- the RJ45 (HR911130C, 15.9 x 21.3 x 13.5, opening at the tab's end) comes with board.glb: its
# EasyEDA STEP, re-placed in its VRML's frame (docs/3D_MODELS.md), so no stand-in box here any more
top = BOARD_Z + PCB_T

# RJ45 strap: a bridge over the jack, screwed into the pedestal either side of the tab
strap = box("rj45_strap", -32.4, -6.6, -23.0, -18.0, top + 13.5, top + 16.5, PETG, bevel=0.8)
for x0, x1 in ((-32.4, -29.0), (-10.0, -6.6)):
    union(strap, box("leg", x0, x1, -23.0, -18.0, BOARD_Z, top + 13.6))
for x in STRAP_X:
    cut(strap, cyl(f"strap_hole{x}", x, -20.5, BOARD_Z - 1, 40, 3.4))

# 0.8 mm spacers between the adapter and the carrier at H1/H2, and the screw heads
for n, xy in {"H1": (94.0, 112.25), "H2": (203.0, 112.25)}.items():
    x, y = k2m(*xy)
    sp = cyl(f"spacer_{n}", x, y, 0.0, BOARD_Z, 6.0, ALU)
    cut(sp, cyl(f"sph_{n}", x, y, -1, 2, 3.3))
SCREWS = [(k2m(94.0, 112.25), top), (k2m(203.0, 112.25), top), ((125, -5), 0.0), ((125, 104), 0.0)] + \
         [(xy, top) for xy in ADAPTER_SUP.values()] + [((x, -20.5), top + 16.5) for x in STRAP_X]
for i, ((x, y), z) in enumerate(SCREWS):
    h = cyl(f"screw_{i}", x, y, z, z + 2.0, 5.5, ALU, 32)
    cut(h, cyl(f"hex_{i}", x, y, z + 0.8, z + 2.2, 2.5, ALU, 6))

for o in (base, strap):
    bpy.context.view_layer.objects.active = o
    for m in list(o.modifiers):
        bpy.ops.object.modifier_apply(modifier=m.name)

# ---- outputs -------------------------------------------------------------------------------------
if "--stl" in argv:
    out = os.path.join(ROOT, argv[argv.index("--stl") + 1])
    os.makedirs(out, exist_ok=True)
    for o, fn in ((base, "mount_base.stl"), (strap, "mount_rj45_strap.stl")):
        bpy.ops.object.select_all(action="DESELECT")
        o.select_set(True)
        bpy.context.view_layer.objects.active = o
        bpy.ops.wm.stl_export(filepath=os.path.join(out, fn), export_selected_objects=True,
                              global_scale=1000.0, apply_modifiers=True)
        d = o.dimensions
        print(f"{fn}: {d.x / MM:.1f} x {d.y / MM:.1f} x {d.z / MM:.1f} mm")
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(D, "assembly.blend"))
print("saved", os.path.join(D, "assembly.blend"))
