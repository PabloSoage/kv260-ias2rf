#!/usr/bin/env python3
"""
Renders of the PSU board's enclosure (docs/PSU_ENCLOSURE.md), Cycles on the GPU, the main case's studio
(_work/mech/render_common.py's lights and world, matfix.py's materials).

    python _work/psu/psu_case_render.py [views] [--samples N] [--res WxH]

views (comma separated, default all): closed, closed_back, exploded, lid_under, section, fea, thermal
The driver exports the board's full GLB (tracks, pours, mask, silk) from the filled copy _render_psu/psu.kicad_pcb
(psu_render.py makes it) and runs Blender on this same file. Writes docs/img/psu/case_<view>.png (1600 wide,
JPEG-sized PNG) and 3840 x 2160 masters in docs/img/highres/renders/psu_case_<view>_4k.png with --4k.
"""
import json
import math
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE = os.path.join(ROOT, "_work", "psu", "cache")
BLENDER = r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
CLI = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "KiCad", "10.0", "bin", "kicad-cli.exe")
ALL = ["closed", "closed_back", "exploded", "lid_under", "section", "thermal", "fea_press"]

try:
    import bpy  # noqa: F401
    IN_BLENDER = True
except ImportError:
    IN_BLENDER = False


def driver():
    args = sys.argv[1:]
    glb = os.path.join(CACHE, "psu_full.glb")
    pcb = os.path.join(ROOT, "_render_psu", "psu.kicad_pcb")
    if not os.path.exists(pcb):
        sys.exit("run _work/psu/psu_render.py first (it fills a copy of the board in _render_psu/)")
    if not os.path.exists(glb) or os.path.getmtime(glb) < os.path.getmtime(pcb):
        cli = CLI if os.path.exists(CLI) else "kicad-cli"
        subprocess.run([cli, "pcb", "export", "glb", "--subst-models", "--include-tracks", "--include-pads",
                        "--include-zones", "--include-silkscreen", "--include-soldermask", "--user-origin", "0x0mm",
                        "-f", "-o", glb, pcb], check=True, capture_output=True)
    r = subprocess.run([BLENDER, "-b", "--python", os.path.abspath(__file__), "--"] + args)
    if r.returncode:
        sys.exit(r.returncode)
    views = args[0].split(",") if args and not args[0].startswith("--") else ALL
    hi = "--4k" in args
    for v in views:
        if v in ("thermal", "fea_shock", "fea_press"):
            colourbar(v, hi)


def colourbar(view, hi):
    """The scale of a field render, drawn on the image's lower right."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from PIL import Image
    fn = os.path.join(ROOT, "docs", "img", "highres", "renders", f"psu_case_{view}_4k.png") if hi else         os.path.join(ROOT, "docs", "img", "psu", f"case_{view}.png")
    img = Image.open(fn).convert("RGB")
    if view == "thermal":
        lo, hi_ = json.load(open(os.path.join(ROOT, "docs", "sim", "psu_case_thermal.json")))["render_scale_C"]
        cmap, label = "inferno", "shell temperature, C (6.0 V, worst load, 70 C ambient, vented)"
    else:
        lo, hi_ = 0.0, json.load(open(os.path.join(ROOT, "docs", "sim", "psu_case_fea.json")))["render_scale_MPa"]
        cmap = "turbo"
        label = ("von Mises, MPa (50 g down, ASA)" if view == "fea_shock" else "von Mises, MPa (300 N on the lid, ASA)")
    s = img.width / 1600
    fig = plt.figure(figsize=(5.2 * s, 0.95 * s), dpi=100)
    ax = fig.add_axes([0.04, 0.55, 0.92, 0.25])
    cm = matplotlib.colormaps[cmap]
    if cmap == "inferno":       # the field's PLY stops at 0.85 of inferno: its top end reads white
        cm = matplotlib.colors.ListedColormap(cm(np.linspace(0, 0.85, 256)))
    cb = matplotlib.colorbar.ColorbarBase(ax, cmap=cm,
                                          norm=matplotlib.colors.Normalize(lo, hi_), orientation="horizontal")
    cb.ax.tick_params(labelsize=9 * s, colors="#e8ecf0")
    cb.outline.set_edgecolor("#e8ecf0")
    ax.set_title(label, fontsize=9.5 * s, color="#e8ecf0")
    fig.patch.set_alpha(0)
    tmp = fn + ".bar.png"
    fig.savefig(tmp, transparent=True)
    plt.close(fig)
    bar = Image.open(tmp).convert("RGBA")
    img.paste(bar, (img.width - bar.width - int(20 * s), img.height - bar.height - int(16 * s)), bar)
    img.save(fn)
    os.remove(tmp)
    print("scale on", fn)


# ------------------------------------------------------------------------------------------------- Blender side
def blender_main():
    import bpy
    from mathutils import Vector, Matrix
    sys.path.insert(0, os.path.join(ROOT, "_work", "mech"))
    sys.path.insert(0, os.path.join(ROOT, "_work", "psu"))
    import matfix
    import psu_case as G

    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    views = argv[0].split(",") if argv and not argv[0].startswith("--") else ALL
    samples = int(argv[argv.index("--samples") + 1]) if "--samples" in argv else 192
    hi = "--4k" in argv
    W, H = (3840, 2160) if hi else (1600, 1000)
    if "--res" in argv:
        W, H = (int(v) for v in argv[argv.index("--res") + 1].split("x"))
    MM = 0.001

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
    sc.render.resolution_x, sc.render.resolution_y = W, H
    sc.render.film_transparent = False
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"
    sc.view_settings.exposure = -1.8
    w = bpy.data.worlds.new("w")
    sc.world = w
    w.use_nodes = True

    def material(name, rgb, rough=0.6, metal=0.0, spec=0.35):
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        b = m.node_tree.nodes["Principled BSDF"]
        b.inputs["Base Color"].default_value = (*rgb, 1)
        b.inputs["Roughness"].default_value = rough
        b.inputs["Metallic"].default_value = metal
        if "Specular IOR Level" in b.inputs:
            b.inputs["Specular IOR Level"].default_value = spec
        return m

    CASE = material("psu case", (0.022, 0.024, 0.027), 0.72)
    STEEL = material("black oxide steel", (0.06, 0.06, 0.065), 0.45, 0.8)
    FLOOR = material("floor", (0.16, 0.17, 0.19), 0.7)

    bpy.ops.mesh.primitive_plane_add(size=3, location=(0.155, -0.135, G.Z_BOT * MM))
    floor = bpy.context.object
    floor.name = "floor"
    floor.data.materials.append(FLOOR)

    def stl(name):
        bpy.ops.wm.stl_import(filepath=os.path.join(ROOT, "mech", f"psu_case_{name}.stl"), global_scale=MM)
        o = bpy.context.selected_objects[0]
        o.name = name
        o.data.materials.clear()
        o.data.materials.append(CASE)
        bpy.ops.object.shade_auto_smooth(angle=math.radians(35))
        return o

    tray, lid = stl("tray"), stl("lid")

    # the board: KiCad's GLB, under a root named ADAPTER_* so matfix treats it as the adapter
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=os.path.join(CACHE, "psu_full.glb"))
    new = [o for o in bpy.data.objects if o not in before]
    rig = bpy.data.objects.new("ADAPTER_PSU", None)
    sc.collection.objects.link(rig)
    for o in new:
        if o.parent is None:
            o.parent = rig
    matfix.apply(bpy.data.materials, bpy.data.objects)
    matfix.studio_world(w)

    # screws: DIN 912 M3 x 25, head 5.5 x 3, seated in the lid's counterbores
    screws = []
    for k, (x, ky) in G.HOLES.items():
        z_seat = G.Z_TOP - G.CBORE_D
        bpy.ops.mesh.primitive_cylinder_add(radius=1.5 * MM, depth=25 * MM, vertices=24,
                                            location=(x * MM, -ky * MM, (z_seat - 12.5) * MM))
        s = bpy.context.object
        bpy.ops.mesh.primitive_cylinder_add(radius=2.75 * MM, depth=3 * MM, vertices=32,
                                            location=(x * MM, -ky * MM, (z_seat + 1.5) * MM))
        h = bpy.context.object
        bpy.ops.mesh.primitive_cylinder_add(radius=1.25 * MM, depth=2.6 * MM, vertices=6,
                                            location=(x * MM, -ky * MM, (z_seat + 2.0) * MM))
        hx = bpy.context.object
        bm = h.modifiers.new("hex", "BOOLEAN")
        bm.operation = "DIFFERENCE"
        bm.object = hx
        bpy.context.view_layer.objects.active = h
        bpy.ops.object.modifier_apply(modifier="hex")
        bpy.data.objects.remove(hx, do_unlink=True)
        for o in (s, h):
            o.data.materials.clear()        # the boolean leaves an empty first slot: Blender's white
            o.data.materials.append(STEEL)
            o.name = f"screw_{k}"
        h.parent = s
        h.matrix_parent_inverse = s.matrix_world.inverted()
        screws.append(s)

    tgt = bpy.data.objects.new("tgt", None)
    sc.collection.objects.link(tgt)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.data.clip_start = 0.001
    c = cam.constraints.new("TRACK_TO")
    c.target = tgt
    c.track_axis = "TRACK_NEGATIVE_Z"
    c.up_axis = "UP_Y"
    centre = Vector((0.155, -0.135, 0.005))
    tgt.location = centre

    def light(name, off, energy, size):
        L = bpy.data.lights.new(name, "AREA")
        L.energy = energy
        L.size = size
        o = bpy.data.objects.new(name, L)
        sc.collection.objects.link(o)
        o.location = centre + Vector(off)
        lc = o.constraints.new("TRACK_TO")
        lc.target = tgt
        lc.track_axis = "TRACK_NEGATIVE_Z"
        lc.up_axis = "UP_Y"

    light("key", (0.18, -0.26, 0.34), 14, 0.28)
    light("fill", (-0.34, 0.15, 0.22), 6, 0.45)
    light("rim", (0.08, 0.40, 0.18), 6, 0.3)

    home = {o.name: o.matrix_world.copy() for o in [lid, rig, tray] + screws}

    def reset():
        for o in [lid, rig, tray] + screws:
            o.matrix_world = home[o.name]
            for k in [o] + list(o.children):
                k.hide_render = False
        for o in [tray, lid] + [c for c in rig.children_recursive if c.type == "MESH"]:
            for m in list(o.modifiers):
                o.modifiers.remove(m)
            o.hide_render = False
        for o in [o for o in bpy.data.objects if o.name.startswith("cutter")]:
            bpy.data.objects.remove(o, do_unlink=True)

    def shoot(name, cam_dir, dist, target=None, lens=50):
        tgt.location = target if target is not None else centre
        d = Vector(cam_dir).normalized()
        cam.location = tgt.location + d * dist
        cam.data.lens = lens
        out = os.path.join(ROOT, "docs", "img", "highres", "renders", f"psu_case_{name}_4k.png") if hi else \
            os.path.join(ROOT, "docs", "img", "psu", f"case_{name}.png")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        sc.render.filepath = out
        bpy.ops.render.render(write_still=True)
        print("wrote", out, flush=True)

    def lift(objs, dz):
        for o in objs:
            o.matrix_world = Matrix.Translation((0, 0, dz * MM)) @ o.matrix_world

    def ply(path, name):
        before = set(bpy.data.objects)
        bpy.ops.wm.ply_import(filepath=path)
        o = [x for x in bpy.data.objects if x not in before][0]
        o.name = name
        import bmesh
        bm = bmesh.new()
        bm.from_mesh(o.data)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(o.data)
        bm.free()
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        nt = m.node_tree
        b = nt.nodes["Principled BSDF"]
        ca = nt.nodes.new("ShaderNodeVertexColor")
        nt.links.new(ca.outputs["Color"], b.inputs["Base Color"])
        b.inputs["Roughness"].default_value = 0.65
        if "Specular IOR Level" in b.inputs:
            b.inputs["Specular IOR Level"].default_value = 0.25
        o.data.materials.append(m)
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.shade_auto_smooth(angle=math.radians(35))
        o.hide_render = True
        return o

    fields = {}
    for v in views:
        if v == "thermal":
            fields[v] = [ply(os.path.join(CACHE, f"psu_case_T_{p}_weak.ply"), f"T_{p}") for p in ("tray", "lid")]
        elif v.startswith("fea_"):
            lc = {"fea_shock": "shock_down", "fea_press": "lid_press_300N"}[v]
            fields[v] = [ply(os.path.join(CACHE, f"psu_case_fea_{lc}.ply"), f"S_{lc}")]

    for v in views:
        reset()
        for objs in fields.values():
            for o in objs:
                o.hide_render = True
        if v == "closed":
            shoot(v, (-0.95, -1.0, 0.85), 0.30)
        elif v == "closed_back":
            shoot(v, (0.95, 1.0, 0.75), 0.30)
        elif v == "exploded":
            lift([rig], 26)
            lift([lid] + screws, 58)
            lift(screws, 16)
            shoot(v, (-0.9, -1.15, 0.95), 0.40, centre + Vector((0, 0, 0.032)))
        elif v == "lid_under":
            # the lid turned over beside the tray, the board in the tray
            lid.matrix_world = Matrix.Translation((0, 0.098, (G.Z_TOP + G.Z_BOT) * MM)) @ \
                Matrix.Translation(centre * 1) @ Matrix.Rotation(math.pi, 4, "X") @ \
                Matrix.Translation(-centre) @ home["lid"]
            for s in screws:
                for o in [s] + list(s.children):
                    o.hide_render = True
            shoot(v, (-0.35, -1.0, 1.25), 0.36, centre + Vector((0, 0.05, 0)))
        elif v == "section":
            # cut at x = 148 mm (a vent column) and look in from -X: the intake and exhaust rows, ribs, posts
            bpy.ops.mesh.primitive_cube_add(size=1, location=(0.148 - 0.5, -0.135, 0.0))
            cutter = bpy.context.object
            cutter.name = "cutter"
            cutter.hide_render = True
            for o in (tray, lid):
                m = o.modifiers.new("cut", "BOOLEAN")
                m.operation = "DIFFERENCE"
                m.object = cutter
                m.solver = "EXACT"
                with bpy.context.temp_override(object=o):
                    bpy.ops.object.modifier_move_to_index(modifier="cut", index=0)
            rig.hide_render = False
            for o in rig.children_recursive:
                if o.type != "MESH":
                    continue
                bb = [o.matrix_world @ Vector(cn) for cn in o.bound_box]
                if max(p.x for p in bb) < 0.148:
                    o.hide_render = True
                elif min(p.x for p in bb) < 0.148:
                    m = o.modifiers.new("cut", "BOOLEAN")
                    m.operation = "DIFFERENCE"
                    m.object = cutter
                    m.solver = "FLOAT"
            for s in screws:
                for o in [s] + list(s.children):
                    o.hide_render = True
            lid.hide_render = False
            shoot(v, (-1.0, -0.55, 0.55), 0.19, Vector((0.152, -0.135, 0.004)))
        elif v == "thermal":
            # the shell's temperature: tray with the board in it, the lid turned over beside it (its hot spots face up)
            tray.hide_render = True
            lid.hide_render = True
            for s in screws:
                for o in [s] + list(s.children):
                    o.hide_render = True
            Tt, Tl = fields[v]
            Tt.hide_render = False
            Tl.hide_render = False
            Tl.matrix_world = Matrix.Translation((0, 0.098, (G.Z_TOP + G.Z_BOT) * MM)) @                 Matrix.Translation(centre) @ Matrix.Rotation(math.pi, 4, "X") @ Matrix.Translation(-centre)
            shoot(v, (-0.35, -1.0, 1.25), 0.36, centre + Vector((0, 0.05, 0)))
            Tl.matrix_world = Matrix.Identity(4)
        elif v.startswith("fea_"):
            (S,) = fields[v]
            tray.hide_render = True
            lid.hide_render = True
            rig.hide_render = True
            for o in rig.children_recursive:
                o.hide_render = True
            for s in screws:
                for o in [s] + list(s.children):
                    o.hide_render = True
            S.hide_render = False
            if v == "fea_shock":
                shoot(v, (0.95, -1.05, 0.55), 0.29)
            else:
                shoot(v, (-0.95, -1.0, 0.85), 0.30)
    print("done")


if __name__ == "__main__":
    if IN_BLENDER:
        blender_main()
    else:
        driver()
