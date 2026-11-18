"""Render 4K (3840x2400) Cycles OPTIX enclosure views from case_v2.blend via shared render_common pipeline."""
import os
import re
import sys
import bpy
from mathutils import Vector

MECH_DIR = os.path.dirname(os.path.abspath(__file__))
if MECH_DIR not in sys.path:
    sys.path.insert(0, MECH_DIR)
import render_common

ROOT = os.path.dirname(os.path.dirname(MECH_DIR))
BLEND_PATH = os.path.join(ROOT, "_work", "mech", "cache", "case_v2.blend")
OUT_DIR = os.path.join(ROOT, "_work", "mech", "cache", "renders4k")  # PNG masters (git-ignored); publish_4k.py writes the JPEGs
MM = render_common.MM
os.makedirs(OUT_DIR, exist_ok=True)


def main():
    if os.path.basename(bpy.data.filepath) != "case_v2.blend":
        bpy.ops.wm.open_mainfile(filepath=BLEND_PATH)

    sc, tgt = render_common.setup_studio(
        samples=96,
        res=(3840, 2400),
        light_energies=(26.0, 11.0, 10.0),
        floor_z=-11.0 * MM,
        target_loc=(0.008, 0.045, 0.005),
        is_case=True,
        remove_rj45_openings=True,
    )

    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    sc.collection.objects.link(cam)
    sc.camera = cam
    cc = cam.constraints.new("TRACK_TO")
    cc.target = tgt
    cc.track_axis = "TRACK_NEGATIVE_Z"
    cc.up_axis = "UP_Y"

    lid = bpy.data.objects["case_lid"]
    bottom = bpy.data.objects["case_bottom"]
    pins = [o for o in bpy.data.objects if re.fullmatch(r"pin\d+", o.name)]
    pads = [o for o in bpy.data.objects if o.name.startswith("pad")]
    bumpers = [o for o in bpy.data.objects if o.name.startswith("bumper")]
    boards = [
        o for o in bpy.data.objects
        if o.parent is None
        and o.name not in ("case_lid", "case_bottom", "floor", "tgt", "cam", "key", "fill", "rim")
        and not o.name.startswith(("pin", "pad", "bumper", "fan2_vis", "case_v2_filter_frame", "grommet"))
    ]
    home = {o.name: (o.location.copy(), o.rotation_euler.copy()) for o in [lid] + pins + pads + bumpers}

    for o in [o for o in bpy.data.objects if o.name.startswith(("fan2_vis", "case_v2_filter_frame", "grommet"))]:
        mw = o.matrix_world.copy()
        o.parent = lid
        o.matrix_world = mw

    cutters = []

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

    def section_cut(y):
        bpy.ops.mesh.primitive_cube_add(size=1)
        c = bpy.context.object
        c.name = "section_cutter"
        c.scale = (0.4, 0.4, 0.2)
        c.location = (0, y * MM - 0.2, 0)
        c.hide_render = True
        cutters.append(c)
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
        for c in cutters:
            bpy.data.objects.remove(c, do_unlink=True)
        cutters.clear()

    views = {
        "closed":  ((8, 45, 5),  (300, -330, 280), 50),
        "open":    ((8, 45, 25), (320, -360, 330), 46),
        "section": ((5, 47, -2), (110, -300, 75),  40),
    }

    for v, (t, c, lens) in views.items():
        reset()
        if v == "open":
            lid.location.z += 75 * MM
            for p in pins:
                p.location.z += 120 * MM
            for b in bumpers:
                b.location.y += (-30 if "front" in b.name else 30) * MM
        elif v == "section":
            for b in bumpers:
                b.hide_render = True
            section_cut(47.0)
        tgt.location = Vector(t) * MM
        cam.location = Vector(c) * MM
        cam.data.lens = lens
        out_path = os.path.join(OUT_DIR, f"case_v2_{v}_4k.png")
        sc.render.filepath = out_path
        bpy.ops.render.render(write_still=True)
        print("rendered", out_path)
        if v == "section":
            section_undo()


if __name__ == "__main__":
    main()
