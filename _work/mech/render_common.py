"""Shared Cycles OPTIX studio lighting, AgX color management, mask Z-lift & matfix pipeline."""
import os
import sys
import bpy

MECH_DIR = os.path.dirname(os.path.abspath(__file__))
if MECH_DIR not in sys.path:
    sys.path.insert(0, MECH_DIR)
import matfix

MM = 0.001
MASK_ALPHA = 0.9


def setup_studio(
    samples=96,
    res=(3840, 2160),
    light_energies=(22.0, 9.0, 8.0),
    floor_z=-11.0 * MM,
    target_loc=(0.0, 0.03, 0.0),
    is_case=False,
    remove_rj45_openings=False,
):
    """Configure Cycles OPTIX GPU, AgX tone mapping, mask/silk Z-lift, matfix & 3-point lighting."""
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "OPTIX"
    prefs.get_devices()
    for d in prefs.devices:
        d.use = (d.type == "OPTIX")
    sc.cycles.device = "GPU"
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGB"

    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"
    sc.view_settings.exposure = -1.8

    w = bpy.data.worlds.new("w")
    sc.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.20, 0.22, 0.25, 1)
    w.node_tree.nodes["Background"].inputs[1].default_value = 0.25

    bpy.ops.mesh.primitive_plane_add(size=20, location=(0.0, 0.0, floor_z))
    fl = bpy.context.object
    fl.name = "floor"
    m = bpy.data.materials.new("floor")
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.16, 0.17, 0.19, 1)
    b.inputs["Roughness"].default_value = 0.7
    fl.data.materials.append(m)

    # Adapter glTF solder mask & silkscreen calibration + Z-lift off copper (before matfix.apply)
    for mat in bpy.data.materials:
        bsdf = mat.node_tree.nodes.get("Principled BSDF") if mat.use_nodes else None
        if not bsdf:
            continue
        col = tuple(round(x, 2) for x in bsdf.inputs["Base Color"].default_value)[:3]
        if col == (0.08, 0.2, 0.14):
            bsdf.inputs["Base Color"].default_value = (0.006, 0.07, 0.022, 1)
            bsdf.inputs["Alpha"].default_value = MASK_ALPHA
            bsdf.inputs["Roughness"].default_value = 0.62
            if "Specular IOR Level" in bsdf.inputs:
                bsdf.inputs["Specular IOR Level"].default_value = 0.3
        elif col == (1.0, 1.0, 1.0) and bsdf.inputs["Alpha"].default_value < 1:
            bsdf.inputs["Alpha"].default_value = 1.0
            bsdf.inputs["Base Color"].default_value = (0.9, 0.9, 0.88, 1)

    rig = bpy.data.objects.get("ADAPTER")
    if rig:
        stack = list(rig.children)
        while stack:
            o = stack.pop()
            stack += list(o.children)
            if o.type != "MESH" or not o.material_slots or not o.material_slots[0].material:
                continue
            mat0 = o.material_slots[0].material
            bsdf = mat0.node_tree.nodes.get("Principled BSDF") if mat0.use_nodes else None
            if not bsdf:
                continue
            col = tuple(round(x, 2) for x in bsdf.inputs["Base Color"].default_value)[:3]
            if col in ((0.01, 0.07, 0.02), (0.9, 0.9, 0.88)) and o.dimensions.z < 1e-5:
                nv = min(50, len(o.data.vertices))
                zc_local = (sum(v.co.z for v in o.data.vertices[:nv]) / max(1, nv)) * o.matrix_world.to_scale().z
                zc = (rig.matrix_world.inverted() @ o.matrix_world.translation).z + zc_local
                lift = (0.04 if col[0] < 0.5 else 0.06) * MM
                o.location.z += lift if zc > 0.8 * MM else -lift

    matfix.apply(bpy.data.materials, bpy.data.objects)
    matfix.studio_world(w)

    if is_case:
        for name in ("case PETG-CF", "lid PETG-CF"):
            mc = bpy.data.materials.get(name)
            if mc:
                bc = mc.node_tree.nodes["Principled BSDF"]
                bc.inputs["Base Color"].default_value = (0.022, 0.024, 0.027, 1)
                bc.inputs["Roughness"].default_value = 0.72
                if "Specular IOR Level" in bc.inputs:
                    bc.inputs["Specular IOR Level"].default_value = 0.35

    if remove_rj45_openings:
        for o in [o for o in bpy.data.objects if o.name.startswith("RJ45_opening")]:
            bpy.data.objects.remove(o, do_unlink=True)

    tgt = bpy.data.objects.new("tgt", None)
    sc.collection.objects.link(tgt)
    tgt.location = target_loc

    def add_area(name, loc, energy, size):
        ldata = bpy.data.lights.new(name, "AREA")
        ldata.energy = energy
        ldata.size = size
        lobj = bpy.data.objects.new(name, ldata)
        sc.collection.objects.link(lobj)
        lobj.location = loc
        con = lobj.constraints.new("TRACK_TO")
        con.target = tgt
        con.track_axis = "TRACK_NEGATIVE_Z"
        con.up_axis = "UP_Y"
        return lobj

    e_key, e_fill, e_rim = light_energies
    add_area("key",  ( 0.25, -0.35, 0.45), e_key,  0.35)
    add_area("fill", (-0.45,  0.20, 0.30), e_fill, 0.60)
    add_area("rim",  ( 0.10,  0.55, 0.25), e_rim,  0.40)

    return sc, tgt
