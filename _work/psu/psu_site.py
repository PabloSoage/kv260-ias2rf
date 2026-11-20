#!/usr/bin/env python3
"""
The PSU board on the project site, beside the adapter in the main 3-D explorer (site/index.html):

  site/assets/psu.json         every part (position, courtyard, pads and nets, the description from psu_spec.py,
                               LCSC code, the audit row from psu_audit.json and the thermal results from
                               psu_thermal.json), the routed copper of every net (tracks, and the outline of each
                               filled pour), the board outline and the simulation figures
  site/assets/psu_layers/*.svg copper, mask, silkscreen and outline, baked into the board's surface in the browser
  site/assets/psu_board.glb    the 3-D parts, built by site/scripts/build_assets.mjs --psu from KiCad's GLB
  site/assets/img/sim/psu_*.png the PSU simulation figures

Works on a copy of psu/ beside it (_site_psu/, model paths resolve) with its zones refilled; psu/ stays unfilled.

Usage:  python _work/psu/psu_site.py
"""
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import psu_fab                                        # noqa: E402
import psu_silk                                       # noqa: E402
import psu_spec                                       # noqa: E402

CLI = os.path.expandvars(r"%LOCALAPPDATA%\Programs\KiCad\10.0\bin\kicad-cli.exe")
WORK = os.path.join(ROOT, "_site_psu")
SITE = os.path.join(ROOT, "site")
ASSETS = os.path.join(SITE, "assets")
LAYERS = ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu", "F.Mask", "B.Mask", "F.SilkS", "B.SilkS", "Edge.Cuts"]
LAYER_STACK = [                                    # the Layers tab of the site, top to bottom (psu.kicad_pcb stackup)
    {"id": "F.Cu", "name": "L1 Top Copper (F.Cu)", "role": "2 oz parts and the power pours (VBAT, VS, switch nodes, +12V)",
     "thickness_mm": 0.07, "color": "#d99b38"},
    {"id": "In1.Cu", "name": "L2 Ground (In1.Cu)", "role": "0.5 oz solid ground under the power stage",
     "thickness_mm": 0.0152, "color": "#4aa868"},
    {"id": "In2.Cu", "name": "L3 +12V Plane (In2.Cu)", "role": "0.5 oz +12V output plane to J2 and J3",
     "thickness_mm": 0.0152, "color": "#5c9ce6"},
    {"id": "B.Cu", "name": "L4 Bottom Copper (B.Cu)", "role": "2 oz ground pour and short signal runs",
     "thickness_mm": 0.07, "color": "#48b5c4"},
    {"id": "F.Mask", "name": "Top Soldermask (F.Mask)", "role": "Green LPI mask", "thickness_mm": 0.01,
     "color": "#197a3a"},
    {"id": "F.SilkS", "name": "Top Silkscreen (F.SilkS)", "role": "Reference designators and pin-1 markers",
     "thickness_mm": 0.01, "color": "#e6e6e0"},
    {"id": "Edge.Cuts", "name": "Board Outline (Edge.Cuts)", "role": "110 x 70 mm, four M3 holes", "thickness_mm": 0,
     "color": "#f0b429"},
]
LAYER_IDX = {"F.Cu": 0, "In1.Cu": 1, "In2.Cu": 6, "B.Cu": 7}       # the site draws 0..3 on top, 4..7 underneath
FIGURES = [
    ("psu_design.png", "PSU operating points", "Efficiency, losses and MOSFET temperatures from 4.4 to 36 V input "
     "and through cranking (psu_design.py)."),
    ("psu_transient.png", "Surge stopper transients", "ISO 16750-2 Load Dump A, ISO 7637-2 pulses 1, 2a, 3a/3b and "
     "reverse battery: VBAT, the 48 V clamp on B0 and +12V (psu_transient.py)."),
    ("psu_loop.png", "LM5177 control loop", "Loop gain and phase in buck, buck-boost and boost (worst phase margin "
     "in the title) and the input filter's output impedance against the converter's input (psu_loop.py)."),
    ("psu_thermal.png", "PSU board thermal map", "Board temperature at 70 C ambient, worst load, 13.5 V and the "
     "corner cases (psu_thermal.py)."),
    ("psu_emi.png", "Conducted emissions", "CISPR 25 class 5 peak limits against the input filter's attenuated "
     "ripple (psu_emi.py)."),
]


def refilled_copy():
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(WORK)
    for f in os.listdir(os.path.join(ROOT, "psu")):
        src = os.path.join(ROOT, "psu", f)
        (shutil.copytree if os.path.isdir(src) else shutil.copy)(src, os.path.join(WORK, f))
    pcb = os.path.join(WORK, "psu.kicad_pcb")
    subprocess.run([CLI, "pcb", "drc", "--refill-zones", "--save-board", "-o", os.path.join(WORK, "drc.rpt"), pcb],
                   check=False, capture_output=True)
    return pcb


def export(pcb):
    raw = os.path.join(WORK, "raw_psu.glb")
    subprocess.run([CLI, "pcb", "export", "glb", "--subst-models", "--include-pads", "--user-origin", "0x0mm",
                    "-f", "-o", raw, pcb], check=True, capture_output=True)
    out = os.path.join(ASSETS, "psu_layers")
    os.makedirs(out, exist_ok=True)
    for lay in LAYERS:
        subprocess.run([CLI, "pcb", "export", "svg", "--layers", lay, "--page-size-mode", "2",
                        "--exclude-drawing-sheet", "--mode-single", "-o",
                        os.path.join(out, lay.replace(".", "_") + ".svg"), pcb], check=True, capture_output=True)
    return raw


def net_name(n):
    return n[1:] if n.startswith("/") else n


def traces(text):
    out = {}
    for s, e in psu_silk.blocks(text, "segment"):
        b = text[s:e]
        m = re.search(r'\(start ([-\d.]+) ([-\d.]+)\)\s*\(end ([-\d.]+) ([-\d.]+)\)[\s\S]*?\(layer "([^"]+)"\)'
                      r'[\s\S]*?\(net (?:\d+ )?"([^"]*)"\)', b)
        if m and m.group(5) in LAYER_IDX:
            x1, y1, x2, y2 = (round(float(m.group(k)), 2) for k in range(1, 5))
            out.setdefault(net_name(m.group(6)), []).append([x1, y1, x2, y2, LAYER_IDX[m.group(5)]])
    pours = 0
    for s, e in psu_silk.blocks(text, "zone"):
        z = text[s:e]
        nm = re.search(r'\(net_name "([^"]*)"\)', z) or re.search(r'\(net (?:\d+ )?"([^"]*)"\)', z)
        if not nm or not nm.group(1):
            continue
        for fs, fe in psu_silk.blocks(z, "filled_polygon"):
            fp = z[fs:fe]
            lay = re.search(r'\(layer "([^"]+)"\)', fp).group(1)
            if lay not in LAYER_IDX:
                continue
            pts = [(float(a), float(b)) for a, b in re.findall(r'\(xy ([-\d.]+) ([-\d.]+)\)', fp)]
            keep = [pts[0]]                       # outline only, thinned to 0.4 mm steps
            for p in pts[1:]:
                if abs(p[0] - keep[-1][0]) + abs(p[1] - keep[-1][1]) >= 0.4:
                    keep.append(p)
            keep.append(pts[0])
            segs = out.setdefault(net_name(nm.group(1)), [])
            for a, b in zip(keep, keep[1:]):
                segs.append([round(a[0], 2), round(a[1], 2), round(b[0], 2), round(b[1], 2), LAYER_IDX[lay]])
            pours += 1
    return out, pours


def components(text):
    audit = {p["ref"]: p for p in json.load(open(os.path.join(ROOT, "docs", "sim", "psu_audit.json")))["parts"]}
    ic_pins = json.load(open(os.path.join(ROOT, "docs", "sim", "psu_audit.json")))["ic_pins"]
    thermal = json.load(open(os.path.join(ROOT, "docs", "sim", "psu_thermal.json")))["cases"]
    fps = {f["ref"]: f for f in psu_silk.parse(text)}
    out = []
    for s, e in psu_silk.blocks(text, "footprint "):
        b = text[s:e]
        ref = re.search(r'\(property "Reference" "([^"]+)"', b).group(1)
        f = fps[ref]
        fpid = re.match(r'\(footprint "([^"]+)"', b).group(1)
        value = re.search(r'\(property "Value" "([^"]*)"', b).group(1)
        pads, nets = {}, set()
        for m in re.finditer(r'\(pad "([^"]*)"((?:(?!\(pad ")[\s\S])*)', b):
            nm = re.search(r'\(net (?:\d+ )?"([^"]*)"\)', m.group(2))
            if not nm or not m.group(1):
                continue
            n = nm.group(1)
            if n.startswith("unconnected-"):
                pads[m.group(1)] = "(nc)"
            else:
                pads[m.group(1)] = net_name(n)
                nets.add(net_name(n))
        part = psu_spec.PARTS.get(ref)
        hole = fpid.startswith("MountingHole")
        th = {case: {k: round(v, 3) for k, v in d["parts"][ref].items() if k != "basis"}
              for case, d in thermal.items() if ref in d.get("parts", {})}
        pins = ic_pins.get(ref) if isinstance(ic_pins, dict) else [p for p in ic_pins if p.get("ic") == ref]
        out.append({
            "id": "PSU:" + ref, "ref": ref, "value": value, "footprint": fpid.split(":")[-1],
            "side": "bottom" if '(layer "B.Cu")' in b[:200] else "top",
            "x_mm": f["x"], "y_mm": f["y"], "rot_deg": f["rot"],
            "bbox_board_mm": [round(v, 3) for v in f["crt"]],
            "nets": sorted(nets), "pads": pads,
            "description": "M3 mounting hole (ground ring)" if hole else (part[3] if part else ""),
            "mpn": value if part and not part[0].startswith(("Device:R", "Device:C")) else "",
            "lcsc": psu_fab.LCSC.get(ref, ""),
            "model_source": "none" if hole else "kicad-step",
            "audit": audit.get(ref), "ic_pins": pins or None, "thermal": th or None,
            "manual_link": "docs/PSU_SPEC.md",
        })
    return out


def main():
    pcb = refilled_copy()
    raw = export(pcb)
    text = open(pcb, encoding="utf-8").read()
    comps = components(text)
    tr, pours = traces(text)
    os.makedirs(os.path.join(ASSETS, "img", "sim"), exist_ok=True)
    figs = []
    for f, title, cap in FIGURES:
        shutil.copy(os.path.join(ROOT, "docs", "sim", f), os.path.join(ASSETS, "img", "sim", f))
        figs.append({"src": "assets/img/sim/" + f, "title": title, "cap": cap})
    audit = json.load(open(os.path.join(ROOT, "docs", "sim", "psu_audit.json")))
    data = {
        "pcb_file": "psu/psu.kicad_pcb",
        "board_outline": {"xmin": 100, "ymin": 100, "xmax": 210, "ymax": 170, "width_mm": 110, "height_mm": 70,
                          "segments": [[[100, 100], [210, 100], [210, 170], [100, 170], [100, 100]]]},
        "thickness_mm": 1.6,
        "layer_stack": LAYER_STACK,
        "counts": {"components": len(comps), "nets": len(tr), "pours": pours,
                   "audit_parts": len(audit["parts"]), "audit_issues": len(audit["issues"])},
        "components": comps,
        "traces": tr,
        "figures": figs,
    }
    with open(os.path.join(ASSETS, "psu.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, separators=(",", ":"))
    subprocess.run(["node", os.path.join(SITE, "scripts", "build_assets.mjs"), "--psu", raw], check=True)
    print(f"psu.json: {len(comps)} parts, {len(tr)} nets with copper ({pours} pours)")


if __name__ == "__main__":
    main()
