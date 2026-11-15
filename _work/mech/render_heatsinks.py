"""Blender 5.2 Cycles GPU script to model & render HS1..HS4 heatsinks on assembly.blend + project 2D callouts."""
import json
import math
import os
import sys
import bpy
import bmesh
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

MECH_DIR = os.path.dirname(os.path.abspath(__file__))
if MECH_DIR not in sys.path:
    sys.path.insert(0, MECH_DIR)
import render_common

ROOT = os.path.dirname(os.path.dirname(MECH_DIR))
OUT_HR = os.path.join(ROOT, "_work", "mech", "cache", "renders4k")  # PNG masters (git-ignored); publish_4k.py writes the JPEGs
OUT_WORK = os.path.join(ROOT, "_work", "mech")
MM = 0.001
os.makedirs(OUT_HR, exist_ok=True)


def make_metal_mat(name, rgba, metallic=0.88, roughness=0.26):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = rgba
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    return mat


def add_wireframe_box(name, cx, cy, z0, sx, sy, sz, thickness, mat):
    mesh = bpy.data.meshes.new(name + "_mesh")
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=bm.verts)
    bmesh.ops.translate(bm, vec=(cx, cy, z0 + sz * 0.5), verts=bm.verts)
    bm.faces.ensure_lookup_table()
    bmesh.ops.wireframe(bm, faces=bm.faces[:], thickness=thickness, use_replace=True)
    bm.to_mesh(mesh)
    bm.free()
    obj.data.materials.append(mat)
    return obj


def add_box(name, cx, cy, z0, sx, sy, sz, mat):
    mesh = bpy.data.meshes.new(name + "_mesh")
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=bm.verts)
    bmesh.ops.translate(bm, vec=(cx, cy, z0 + sz * 0.5), verts=bm.verts)
    bm.to_mesh(mesh)
    bm.free()
    obj.data.materials.append(mat)
    return obj


def add_finned_heatsink(name, cx, cy, z0, sx, sy, sz, n_fins, mat_hs, mat_pad):
    pad_t = 0.00018  # 0.18 mm blue thermal gap pad
    add_box(name + "_PAD", cx, cy, z0, sx * 0.94, sy * 0.94, pad_t, mat_pad)
    bz = z0 + pad_t
    base_h = min(0.0014, sz * 0.28)
    fin_h = sz - base_h
    add_box(name + "_BASE", cx, cy, bz, sx, sy, base_h, mat_hs)
    fin_t = (sx * 0.44) / n_fins
    pitch = (sx - fin_t) / max(1, n_fins - 1)
    x_start = cx - sx * 0.5 + fin_t * 0.5
    for i in range(n_fins):
        fx = x_start + i * pitch
        add_box(f"{name}_FIN_{i}", fx, cy, bz + base_h, fin_t, sy, fin_h, mat_hs)


def add_camera(name, loc, target, lens_mm=50.0):
    cdata = bpy.data.cameras.new(name=name)
    cdata.lens = lens_mm
    cdata.clip_start = 0.001
    cdata.clip_end = 5.0
    cobj = bpy.data.objects.new(name=name, object_data=cdata)
    bpy.context.collection.objects.link(cobj)
    cobj.location = Vector(loc)
    direction = Vector(target) - Vector(loc)
    cobj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    return cobj


def main():
    scene, _tgt = render_common.setup_studio(
        samples=96,
        res=(3840, 2160),
        light_energies=(22.0, 9.0, 8.0),
        floor_z=-11.2 * MM,
        target_loc=(0.0, 0.03, 0.0),
        is_case=False,
    )

    mat_black = make_metal_mat("HS_BlackAl",  (0.025, 0.027, 0.032, 1.0), metallic=1.0, roughness=0.45)
    mat_blue  = make_metal_mat("HS_BlueAl",   (0.012, 0.035, 0.095, 1.0), metallic=1.0, roughness=0.42)
    mat_cu    = make_metal_mat("HS_CopperAl", (0.18, 0.068, 0.024, 1.0),  metallic=1.0, roughness=0.40)
    mat_pad   = make_metal_mat("TIM_PadBlue", (0.015, 0.055, 0.12, 1.0),  metallic=0.0, roughness=0.65)
    mat_fan   = make_metal_mat("FanEnvelope", (0.02, 0.11, 0.19, 1.0),    metallic=0.5, roughness=0.45)

    # Mounted heatsinks matching assembly.blend exact IC top surfaces (meters):
    # HS1: U501 AD9484 14x14x8.5 mm at (-51.8, +10.55) mm, IC top z=3.34 mm (8.5 mm since 15 Nov)
    add_finned_heatsink("HS1_U501_AD9484",  -0.05180,  0.01055, 0.00334, 0.014, 0.014, 0.0085, 7, mat_black, mat_pad)
    # HS2: U401 ADCLK948 9x7x8 mm shifted -1.0 mm Y -> cy=-1.2 mm, IC top z=3.15 mm
    add_finned_heatsink("HS2_U401_ADCLK948",-0.03490, -0.00120, 0.00315, 0.009, 0.007, 0.008, 5, mat_blue,  mat_pad)
    # HS3: Y401 Si549 9x7x8 mm shifted +1.0 mm Y -> cy=+9.8 mm, IC top z=3.99 mm -> 4.0 mm air gap!
    add_finned_heatsink("HS3_Y401_Si549",   -0.03500,  0.00980, 0.00399, 0.009, 0.007, 0.008, 5, mat_blue,  mat_pad)
    # HS4: U1101 XC7A50T 14x14x5 mm optional low-profile at (-42.75, +40.0) mm, IC top z=3.84 mm
    add_finned_heatsink("HS4_U1101_XC7A50T",-0.04275,  0.04000, 0.00384, 0.014, 0.014, 0.005, 8, mat_cu,    mat_pad)

    # Overhead 50x50x15 mm Fan Wireframe Cage (OD5015, since 15 Nov) at (-40.0, +14.0) mm, z in [13.75, 28.75] mm
    fan_obj = add_wireframe_box("ENCLOSURE_FAN_50MM_ENVELOPE", -0.040, 0.014, 0.01375, 0.050, 0.050, 0.015, 0.0007, mat_fan)

    # Hero isometric view showing both ADAPTER heatsinks (left) & KV260 OEM heatsink (right)
    cam_hero = add_camera("Cam_Heatsinks_Hero", (-0.115, -0.145, 0.135), (0.008, 0.028, 0.006), lens_mm=44.0)
    scene.camera = cam_hero
    bpy.context.view_layer.update()

    # Project 3D anchor points for annotated callout overlay
    anchors_world = {
        "HS1_U501":  (-0.05180,  0.01055, 0.0120),
        "HS2_U401":  (-0.03490, -0.00120, 0.0113),
        "HS3_Y401":  (-0.03500,  0.00980, 0.0121),
        "GAP_4MM":   (-0.03500,  0.00430, 0.0052),
        "HS4_U1101": (-0.04275,  0.04000, 0.0090),
        "HS5_K26":   ( 0.08600,  0.04700, 0.0250),
        "FAN_50MM":  (-0.04000,  0.01400, 0.0288),
    }
    proj = {}
    for k, pt in anchors_world.items():
        co = world_to_camera_view(scene, cam_hero, Vector(pt))
        proj[k] = [round(co.x, 5), round(1.0 - co.y, 5)]  # normalized (u, v from top-left)
    with open(os.path.join(OUT_WORK, "hs_screen_pts.json"), "w", encoding="utf-8") as f:
        json.dump(proj, f, indent=2)

    raw_4k = os.path.join(OUT_HR, "board_heatsinks_clean_4k.png")
    scene.render.filepath = raw_4k
    bpy.ops.render.render(write_still=True)

    # Also render a tight macro close-up of the ADAPTER RF/Clock heatsink zone (hide fan ghost so zero haze)
    fan_obj.hide_render = True
    cam_macro = add_camera("Cam_Heatsinks_Macro", (-0.088, -0.052, 0.058), (-0.041, 0.016, 0.006), lens_mm=56.0)
    scene.camera = cam_macro
    bpy.context.view_layer.update()
    scene.render.filepath = os.path.join(OUT_HR, "board_heatsinks_closeup_4k.png")
    bpy.ops.render.render(write_still=True)
    print("DONE: Blender 4K heatsink renders written.")


if __name__ == "__main__":
    main()
