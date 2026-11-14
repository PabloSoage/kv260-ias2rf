"""Plausible materials for the renders (render_case.py, render_mount.py), applied after their mask/silk lift.

The KV260's STEP and the parts' models arrive with every material metallic = 1, roughness = 1 and many pure
white (1, 1, 1) bodies: a mirror-green carrier, gold pads that only reflect the dark world, and white parts that
burn out under the key light. Each material is classed by its colour and by which assembly uses it:
  - the adapter's solder mask: the KV260 carrier's own green, translucent over its copper, which is a lighter
    ENIG tone than the bare laminate, so tracks and pours read through the mask as on a real board;
  - green laminate (KV260 carrier, K26 SOM): dielectric, satin;
  - KV260 connector shells (white or neutral grey in its STEP): nickel-plated steel;
  - gold / brass (pins, contacts): metal, ENIG/brass gold;
  - mid/light neutral grey (shields, tin): metal;
  - white plastics on the adapter (JST housings, transformer cases): ivory, never above 0.8 albedo;
  - everything else: dielectric, its colour capped at 0.8 so nothing renders as pure white.
"""

KV_GREEN = (0.0, 0.107, 0.009)          # the KV260 carrier's laminate colour in its STEP (linear)


def _lum(c):
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def _set(b, name, v):
    if name in b.inputs:
        b.inputs[name].default_value = v


def _roots(objects):
    use = {}
    for o in objects:
        if o.type != "MESH":
            continue
        tag, r = "other", o
        while r:
            if r.name.startswith("KV260"):
                tag = "kv"
                break
            if r.name.startswith("ADAPTER"):
                tag = "ad"
                break
            r = r.parent
        for s in o.material_slots:
            if s.material:
                use.setdefault(s.material.name, set()).add(tag)
    return use


def studio_world(world, color=(0.20, 0.22, 0.25), strength=0.25):
    """The renders' flat grey world, but with a soft-box sky and a dark floor in the reflections only: a metal in
    a uniform world mirrors one grey and reads as white plastic; this gives the shells a horizon to reflect.
    Camera rays still see the original flat colour, so the backgrounds do not change."""
    nt = world.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    flat = nt.nodes.new("ShaderNodeBackground")
    flat.inputs[0].default_value = (*color, 1)
    flat.inputs[1].default_value = strength
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    els = ramp.color_ramp.elements
    els[0].position, els[0].color = 0.40, (0.015, 0.016, 0.018, 1)       # floor
    els[1].position, els[1].color = 0.62, (0.85, 0.88, 0.92, 1)          # soft-box sky
    e = els.new(0.52)
    e.color = (0.10, 0.11, 0.12, 1)                                      # horizon
    refl = nt.nodes.new("ShaderNodeBackground")
    refl.inputs[1].default_value = strength * 2.2
    mapr = nt.nodes.new("ShaderNodeMapRange")                            # z in -1..1 -> 0..1
    mapr.inputs["From Min"].default_value = -1.0
    lp = nt.nodes.new("ShaderNodeLightPath")
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(tc.outputs["Generated"], sep.inputs[0])
    nt.links.new(sep.outputs["Z"], mapr.inputs["Value"])
    nt.links.new(mapr.outputs["Result"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], refl.inputs[0])
    nt.links.new(lp.outputs["Is Camera Ray"], mix.inputs[0])
    nt.links.new(refl.outputs[0], mix.inputs[1])
    nt.links.new(flat.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs[0])


def apply(materials, objects):
    roots = _roots(objects)
    n = {}

    def count(k):
        n[k] = n.get(k, 0) + 1

    for m in materials:
        b = m.node_tree.nodes.get("Principled BSDF") if m.use_nodes and m.node_tree else None
        if not b:
            continue
        c = tuple(b.inputs["Base Color"].default_value)[:3]
        met = b.inputs["Metallic"].default_value
        rough = b.inputs["Roughness"].default_value
        alpha = b.inputs["Alpha"].default_value
        r, g, bl = c
        sat = max(c) - min(c)
        L = _lum(c)
        who = roots.get(m.name, set())
        greenish = g > 2.2 * r and g > 1.4 * bl and L < 0.25
        if greenish and alpha < 1.0:                                   # the adapter's mask
            b.inputs["Base Color"].default_value = (*KV_GREEN, 1)
            b.inputs["Alpha"].default_value = 0.86
            _set(b, "Metallic", 0.0)
            _set(b, "Roughness", 0.6)
            _set(b, "Specular IOR Level", 0.3)
            count("mask")
            continue
        if greenish:                                                   # green laminate (carrier, SOM)
            _set(b, "Metallic", 0.0)
            _set(b, "Roughness", 0.6)
            _set(b, "Specular IOR Level", 0.3)
            count("laminate")
            continue
        if "ad" in who and met > 0.5 and abs(r - 0.7) < 0.02 and abs(g - 0.61) < 0.02 and bl < 0.02:
            b.inputs["Base Color"].default_value = (0.88, 0.70, 0.40, 1)   # the adapter's copper (KiCad glTF)
            _set(b, "Metallic", 0.85)
            _set(b, "Roughness", 0.32)
            count("copper")
            continue
        if "ad" in who and met < 0.5 and abs(r - 0.42) < 0.02 and abs(g - 0.45) < 0.02:
            b.inputs["Base Color"].default_value = (0.20, 0.21, 0.12, 1)   # the adapter's bare laminate
            count("fr4")
            continue
        if met < 0.5 or (rough < 0.99 and not who & {"kv", "ad"}):
            continue                                                   # already tuned (our own materials)
        if rough < 0.99 and met > 0.5 and "ad" in who:
            continue                                                   # the adapter's tuned glTF metals
        goldish = r > 0.45 and r > g > bl and bl < 0.45 * r and sat > 0.25
        if goldish:
            b.inputs["Base Color"].default_value = (0.86, 0.68, 0.36, 1)
            _set(b, "Metallic", 1.0)
            _set(b, "Roughness", 0.38)
            count("gold")
        elif "kv" in who and sat < 0.13 and L > 0.3:
            v = min(0.62, max(0.5, L))                                 # KV260 shells: nickel
            b.inputs["Base Color"].default_value = (v, v, v * 0.98, 1)
            _set(b, "Metallic", 1.0)
            _set(b, "Roughness", 0.22)
            count("nickel")
        elif sat < 0.1 and 0.35 < L < 0.9:
            _set(b, "Metallic", 1.0)
            _set(b, "Roughness", 0.35)
            count("metal")
        elif L >= 0.9:
            b.inputs["Base Color"].default_value = (0.66, 0.64, 0.58, 1)   # white plastic -> ivory
            _set(b, "Metallic", 0.0)
            _set(b, "Roughness", 0.5)
            _set(b, "Specular IOR Level", 0.3)
            count("ivory")
        else:
            k = min(1.0, 0.8 / max(max(c), 1e-6))
            b.inputs["Base Color"].default_value = (r * k, g * k, bl * k, 1)
            _set(b, "Metallic", 0.0)
            _set(b, "Roughness", 0.6 if L < 0.08 else 0.5)
            _set(b, "Specular IOR Level", 0.35)
            count("dielectric")
    # meshes the STEP left without any material (the KV260's USB, RJ45 and HDMI shells among them) render in
    # Blender's default white: on the KV260 those are the stamped connector shells -> nickel
    import bpy
    nickel = bpy.data.materials.get("matfix nickel") or bpy.data.materials.new("matfix nickel")
    nickel.use_nodes = True
    nb = nickel.node_tree.nodes["Principled BSDF"]
    nb.inputs["Base Color"].default_value = (0.58, 0.58, 0.57, 1)
    nb.inputs["Metallic"].default_value = 1.0
    nb.inputs["Roughness"].default_value = 0.22
    ink = bpy.data.materials.get("matfix ink") or bpy.data.materials.new("matfix ink")
    ink.use_nodes = True
    ib = ink.node_tree.nodes["Principled BSDF"]
    ib.inputs["Base Color"].default_value = (0.62, 0.62, 0.62, 1)
    ib.inputs["Roughness"].default_value = 0.6
    from mathutils import Vector
    bare = 0
    for o in objects:
        if o.type != "MESH" or any(s.material for s in o.material_slots):
            continue
        r = o
        while r and not r.name.startswith("KV260"):
            r = r.parent
        if r:
            ztop = max((o.matrix_world @ Vector(c)).z for c in o.bound_box) / 0.001
            o.data.materials.clear()
            # the fan-sink's printed logo sits above 18 mm; the connector shells are below
            o.data.materials.append(ink if ztop > 18.0 else nickel)
            bare += 1
    n["bare->nickel"] = bare
    print("matfix", n)
    return n
