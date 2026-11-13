#!/usr/bin/env python3
"""Read-only S-expression audit parser for CSI2-KRIA-KV260_Rev01 KiCad files.

Extracts quantitative PCB geometry, stackup, zone/keepout, via/return-via,
RF launch/trace, differential-pair length/skew, thermal-via, power-tree, and
clock/routing schematic connectivity facts without invoking KiCad GUI/pcbnew.
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import os
import re
from collections import Counter, defaultdict
from typing import Any


def tokenize_sexpr(text: str) -> list[Any]:
    """Tokenize a KiCad S-expression string into parens, atoms, and quoted strings."""
    tokens: list[Any] = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c in " \t\r\n":
            i += 1
        elif c in "()":
            tokens.append(c)
            i += 1
        elif c == '"':
            j = i + 1
            while j < n:
                ch = text[j]
                if ch == "\\":
                    j += 2
                elif ch == '"':
                    break
                else:
                    j += 1
            tokens.append(("STR", text[i + 1 : j]))
            i = j + 1
        else:
            j = i
            while j < n and text[j] not in " \t\r\n()":
                j += 1
            tokens.append(text[i:j])
            i = j
    return tokens


def parse_sexpr(tokens: list[Any]) -> list[Any]:
    """Parse flat token list into nested Python lists."""
    stack: list[list[Any]] = []
    cur: list[Any] = []
    for t in tokens:
        if t == "(":
            stack.append(cur)
            cur = []
        elif t == ")":
            node = cur
            cur = stack.pop()
            cur.append(node)
        else:
            cur.append(t[1] if isinstance(t, tuple) else t)
    return cur[0] if len(cur) == 1 else cur


def load_sexpr(path: str) -> list[Any]:
    with open(path, encoding="utf-8") as f:
        return parse_sexpr(tokenize_sexpr(f.read()))


def sub_val(node: list[Any], key: str, default: Any = None) -> Any:
    for item in node:
        if isinstance(item, list) and item and item[0] == key:
            return item[1] if len(item) > 1 else True
    return default


def sub_list(node: list[Any], key: str) -> list[Any] | None:
    for item in node:
        if isinstance(item, list) and item and item[0] == key:
            return item[1:]
    return None


def arc_length(p0: tuple[float, float], pmid: tuple[float, float], p1: tuple[float, float]) -> float:
    """Exact circular-arc length through start, mid, end points in 2D."""
    x1, y1 = p0
    x2, y2 = pmid
    x3, y3 = p1
    d = 2.0 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
    if abs(d) < 1e-9:
        return math.hypot(x3 - x1, y3 - y1)
    ux = ((x1 * x1 + y1 * y1) * (y2 - y3) + (x2 * x2 + y2 * y2) * (y3 - y1) + (x3 * x3 + y3 * y3) * (y1 - y2)) / d
    uy = ((x1 * x1 + y1 * y1) * (x3 - x2) + (x2 * x2 + y2 * y2) * (x1 - x3) + (x3 * x3 + y3 * y3) * (x2 - x1)) / d
    r = math.hypot(x1 - ux, y1 - uy)
    a1 = math.atan2(y1 - uy, x1 - ux)
    am = math.atan2(y2 - uy, x2 - ux)
    a3 = math.atan2(y3 - uy, x3 - ux)

    def norm_ccw(a: float) -> float:
        return a % (2.0 * math.pi)

    ccw_total = norm_ccw(a3 - a1)
    ccw_mid = norm_ccw(am - a1)
    theta = ccw_total if ccw_mid <= ccw_total else (2.0 * math.pi - ccw_total)
    return r * theta


def seg_bbox_crosses_split(p0: tuple[float, float], p1: tuple[float, float], rect: tuple[float, float, float, float]) -> bool:
    """Return True if line segment touches both inside and outside of an axis-aligned rectangle (crosses boundary)."""
    rx0, ry0, rx1, ry1 = rect
    x0, y0 = p0
    x1, y1 = p1
    in0 = (rx0 <= x0 <= rx1) and (ry0 <= y0 <= ry1)
    in1 = (rx0 <= x1 <= rx1) and (ry0 <= y1 <= ry1)
    return in0 != in1


def parse_pcb(root: str) -> dict[str, Any]:
    pcb_path = os.path.join(root, "CSI2-KRIA-KV260_Rev01.kicad_pcb")
    pro_path = os.path.join(root, "CSI2-KRIA-KV260_Rev01.kicad_pro")
    tree = load_sexpr(pcb_path)
    with open(pro_path, encoding="utf-8") as f:
        pro = json.load(f)

    # Setup & stackup
    setup = sub_list(tree, "setup") or []
    stackup_raw = sub_list(setup, "stackup") or []
    stackup = []
    for item in stackup_raw:
        if isinstance(item, list) and item and item[0] == "layer":
            stackup.append({
                "name": item[1],
                "type": sub_val(item[2:], "type"),
                "thickness_mm": float(sub_val(item[2:], "thickness", 0.0)),
                "epsilon_r": float(sub_val(item[2:], "epsilon_r", 0.0)),
                "loss_tangent": float(sub_val(item[2:], "loss_tangent", 0.0)),
            })

    pcb_flags = {
        "thickness_mm": float(sub_val(sub_list(tree, "general") or [], "thickness", 0.0)),
        "tenting": sub_list(setup, "tenting"),
        "covering": sub_list(setup, "covering"),
        "plugging": sub_list(setup, "plugging"),
        "capping": sub_val(setup, "capping"),
        "filling": sub_val(setup, "filling"),
    }

    # Edge cuts polygon
    edge_polys = []
    for item in tree[1:]:
        if isinstance(item, list) and item[0] == "gr_poly":
            if sub_val(item[1:], "layer") == "Edge.Cuts":
                pts_raw = sub_list(item[1:], "pts") or []
                pts = [(float(p[1]), float(p[2])) for p in pts_raw if isinstance(p, list) and p[0] == "xy"]
                edge_polys.append(pts)

    # Footprints, pads, segments, arcs, vias, zones
    footprints = []
    segments = []
    arcs = []
    vias = []
    zones = []

    for item in tree[1:]:
        if not isinstance(item, list):
            continue
        k = item[0]
        if k == "footprint":
            props = {}
            at_raw = sub_list(item[2:], "at") or ["0", "0"]
            fx, fy = float(at_raw[0]), float(at_raw[1])
            frot = float(at_raw[2]) if len(at_raw) > 2 else 0.0
            layer = sub_val(item[2:], "layer")
            pads = []
            for sub in item[2:]:
                if not isinstance(sub, list):
                    continue
                if sub[0] == "property" and len(sub) >= 3:
                    props[sub[1]] = sub[2]
                elif sub[0] == "pad":
                    pat = sub_list(sub[2:], "at") or ["0", "0"]
                    px_loc, py_loc = float(pat[0]), float(pat[1])
                    rad = math.radians(-frot)
                    px_abs = fx + px_loc * math.cos(rad) - py_loc * math.sin(rad)
                    py_abs = fy + px_loc * math.sin(rad) + py_loc * math.cos(rad)
                    psize = sub_list(sub[2:], "size") or ["0", "0"]
                    pnet = sub_val(sub[2:], "net", "")
                    players = sub_list(sub[2:], "layers") or []
                    pads.append({
                        "num": sub[1],
                        "type": sub[2],
                        "x": px_abs,
                        "y": py_abs,
                        "w": float(psize[0]),
                        "h": float(psize[1]),
                        "net": pnet,
                        "layers": players,
                    })
            footprints.append({
                "ref": props.get("Reference", ""),
                "val": props.get("Value", ""),
                "lib": item[1],
                "layer": layer,
                "x": fx,
                "y": fy,
                "rot": frot,
                "pads": pads,
            })
        elif k == "segment":
            s = sub_list(item[1:], "start")
            e = sub_list(item[1:], "end")
            w = float(sub_val(item[1:], "width", 0.0))
            lay = sub_val(item[1:], "layer")
            net = sub_val(item[1:], "net", "")
            x0, y0 = float(s[0]), float(s[1])
            x1, y1 = float(e[0]), float(e[1])
            segments.append({
                "x0": x0, "y0": y0, "x1": x1, "y1": y1,
                "len": math.hypot(x1 - x0, y1 - y0),
                "w": w, "layer": lay, "net": net,
            })
        elif k == "arc":
            s = sub_list(item[1:], "start")
            m = sub_list(item[1:], "mid")
            e = sub_list(item[1:], "end")
            w = float(sub_val(item[1:], "width", 0.0))
            lay = sub_val(item[1:], "layer")
            net = sub_val(item[1:], "net", "")
            p0 = (float(s[0]), float(s[1]))
            pm = (float(m[0]), float(m[1]))
            p1 = (float(e[0]), float(e[1]))
            arcs.append({
                "p0": p0, "pm": pm, "p1": p1,
                "len": arc_length(p0, pm, p1),
                "w": w, "layer": lay, "net": net,
            })
        elif k == "via":
            at = sub_list(item[1:], "at")
            lays = sub_list(item[1:], "layers") or []
            vias.append({
                "x": float(at[0]), "y": float(at[1]),
                "size": float(sub_val(item[1:], "size", 0.0)),
                "drill": float(sub_val(item[1:], "drill", 0.0)),
                "layers": lays,
                "capping": sub_val(item[1:], "capping"),
                "filling": sub_val(item[1:], "filling"),
                "net": sub_val(item[1:], "net", ""),
            })
        elif k == "zone":
            znet = sub_val(item[1:], "net")
            zname = sub_val(item[1:], "name", "")
            zlays = []
            for s in item[1:]:
                if isinstance(s, list) and s[0] == "layer":
                    zlays.append(s[1])
                elif isinstance(s, list) and s[0] == "layers":
                    zlays.extend(s[1:])
            ko = sub_list(item[1:], "keepout")
            poly = sub_list(item[1:], "polygon")
            pts_raw = sub_list(poly or [], "pts") or []
            pts = [(float(p[1]), float(p[2])) for p in pts_raw if isinstance(p, list) and p[0] == "xy"]
            bbox = (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)) if pts else None
            zones.append({
                "net": znet,
                "name": zname,
                "layers": zlays,
                "is_keepout": ko is not None,
                "keepout": ko,
                "bbox": bbox,
                "pts": pts,
            })

    # 1. GND vias and signal return-via spacing
    gnd_vias = [v for v in vias if v["net"] == "GND"]
    via_caps = Counter((v["capping"], v["filling"], v["size"], v["drill"]) for v in vias)

    def nearest_gnd_via_mm(x: float, y: float) -> float:
        return min((math.hypot(x - gv["x"], y - gv["y"]) for gv in gnd_vias), default=999.0)

    # 2. Per-net trace statistics
    net_segs = defaultdict(list)
    net_arcs = defaultdict(list)
    net_vias = defaultdict(list)
    for s in segments:
        net_segs[s["net"]].append(s)
    for a in arcs:
        net_arcs[a["net"]].append(a)
    for v in vias:
        net_vias[v["net"]].append(v)

    def net_metrics(n: str) -> dict[str, Any]:
        segs = net_segs[n]
        al = net_arcs[n]
        vs = net_vias[n]
        by_layer = Counter()
        by_width = Counter()
        total_len = 0.0
        for s in segs:
            total_len += s["len"]
            by_layer[s["layer"]] += s["len"]
            by_width[round(s["w"], 4)] += s["len"]
        for a in al:
            total_len += a["len"]
            by_layer[a["layer"]] += a["len"]
            by_width[round(a["w"], 4)] += a["len"]
        ret_dists = [round(nearest_gnd_via_mm(v["x"], v["y"]), 3) for v in vs]
        return {
            "len_mm": round(total_len, 3),
            "segs": len(segs),
            "arcs": len(al),
            "vias": len(vs),
            "ret_via_dists_mm": ret_dists,
            "by_layer_mm": {k: round(v, 3) for k, v in sorted(by_layer.items())},
            "by_width_mm": {str(k): round(v, 3) for k, v in sorted(by_width.items())},
        }

    # 3. Diff pairs: auto-detect all *_P / *_N nets
    all_nets = set(net_segs.keys()) | set(net_vias.keys())
    p_nets = sorted(n for n in all_nets if n.endswith("_P") or n.endswith("+"))
    diff_pairs = []
    for pn in p_nets:
        if pn.endswith("_P"):
            nn = pn[:-2] + "_N"
        elif pn.endswith("+"):
            nn = pn[:-1] + "-"
        else:
            continue
        if nn not in all_nets:
            continue
        mp = net_metrics(pn)
        mn = net_metrics(nn)
        skew_mm = round(abs(mp["len_mm"] - mn["len_mm"]), 3)
        # Check if any L3 (In2.Cu) segment crosses In3.Cu power zone boundaries
        in3_zones = [z for z in zones if not z["is_keepout"] and "In3.Cu" in z["layers"] and z["bbox"]]
        crossings = []
        for net_side, slist in [(pn, net_segs[pn]), (nn, net_segs[nn])]:
            for s in slist:
                if s["layer"] == "In2.Cu":
                    for z in in3_zones:
                        if z["net"] != "+3V3_D" and seg_bbox_crosses_split((s["x0"], s["y0"]), (s["x1"], s["y1"]), z["bbox"]):
                            crossings.append((net_side, z["net"]))
        diff_pairs.append({
            "pair": pn[:-2] if pn.endswith("_P") else pn[:-1],
            "p": mp,
            "n": mn,
            "intra_skew_mm": skew_mm,
            "l3_over_in3_split_edges": sorted(set(crossings)),
        })

    # 4. RF / IF / CLK coax & balun & ADC input nets
    rf_patterns = (
        "Net-(D96", "Net-(D97", "Net-(D40", "Net-(J9", "Net-(J4",
        "/IF_", "Net-(U90", "Net-(U50", "Net-(U60", "Net-(T701", "Net-(T801", "Net-(T802",
        "Net-(U401", "Net-(Y401", "/CLK_", "Net-(L7", "Net-(L8",
    )
    rf_nets = {}
    for n in sorted(all_nets):
        if any(n.startswith(p) for p in rf_patterns) and not any(x in n for x in ("VCTRL", "VCM", "RBIAS", "RDP", "RGP", "RGN", "RDN", "VREF")):
            m = net_metrics(n)
            if m["len_mm"] > 0 or m["vias"] > 0:
                rf_nets[n] = m

    # 5. Exposed pad thermal/GND via counts for key ICs
    fp_by_ref = {fp["ref"]: fp for fp in footprints if fp["ref"]}
    ic_refs = [
        "U401", "Y401", "U501", "U502", "U503", "U601", "U602", "U603",
        "U701", "U801", "U901", "U902", "U903", "U904",
        "U1001", "U1002", "U1003", "U1004", "U1005", "U1006", "U1007", "U1008",
        "U1101", "U1201",
        "J911", "J912", "J921", "J922", "J931", "J932", "J941", "J942", "J951", "J952", "J401", "J402",
    ]
    ep_audit = {}
    for ref in ic_refs:
        fp = fp_by_ref.get(ref)
        if not fp:
            continue
        gnd_pads = [p for p in fp["pads"] if p["net"] == "GND"]
        ep_pads = sorted(gnd_pads, key=lambda p: p["w"] * p["h"], reverse=True)
        big_ep = [p for p in ep_pads if p["w"] * p["h"] >= 1.5]
        vias_in_ep = []
        vias_near_fp = 0
        for p in big_ep:
            cnt = sum(1 for gv in gnd_vias if abs(gv["x"] - p["x"]) <= p["w"] / 2 + 0.15 and abs(gv["y"] - p["y"]) <= p["h"] / 2 + 0.15)
            vias_in_ep.append({"pad": p["num"], "w": p["w"], "h": p["h"], "gnd_vias_inside": cnt})
        vias_near_fp = sum(1 for gv in gnd_vias if math.hypot(gv["x"] - fp["x"], gv["y"] - fp["y"]) <= 4.0)
        ep_audit[ref] = {
            "val": fp["val"],
            "x": fp["x"], "y": fp["y"], "layer": fp["layer"],
            "ep_vias": vias_in_ep,
            "gnd_vias_r4mm": vias_near_fp,
        }

    # 6. Stitching / fence vias along RF band (y >= 198) and board edge
    rf_band_gnd_vias = [v for v in gnd_vias if v["y"] >= 198.0]
    row_top_vias = sorted([v for v in gnd_vias if v["y"] >= 209.5], key=lambda v: v["x"])
    row_top_gaps = [round(row_top_vias[i+1]["x"] - row_top_vias[i]["x"], 2) for i in range(len(row_top_vias) - 1)]

    # 7. SMA-to-board-edge, ESD diode, and switch clearances
    sma_refs = ["J931", "J932", "J941", "J942", "J952", "J951", "J911", "J912", "J921", "J922", "J401", "J402"]
    sma_order = []
    for ref in sma_refs:
        if ref in fp_by_ref:
            fp = fp_by_ref[ref]
            # Find connected net on pin 1
            pin1 = next((p for p in fp["pads"] if p["num"] == "1"), None)
            # Find nearest PESD diode
            esds = [f for f in footprints if f["val"] == "PESD5V0F1BL"]
            ne = min(esds, key=lambda d: math.hypot(d["x"] - fp["x"], d["y"] - fp["y"]))
            dist_to_h5 = min(math.hypot(fp["x"] - fp_by_ref[h]["x"], fp["y"] - fp_by_ref[h]["y"]) for h in ("H3", "H4", "H5") if h in fp_by_ref)
            sma_order.append({
                "ref": ref, "val": fp["val"], "x": fp["x"], "y": fp["y"],
                "pin1_net": pin1["net"] if pin1 else "",
                "esd_ref": ne["ref"], "esd_dx_dy": (round(ne["x"] - fp["x"], 3), round(ne["y"] - fp["y"], 3)),
                "nearest_m3_mm": round(dist_to_h5, 2),
            })

    # 8. Kria connector J101/J102 and Artix U1101 signal & power mapping
    kria_conns = {}
    for jref in ("J101", "J102"):
        if jref in fp_by_ref:
            fp = fp_by_ref[jref]
            pins = []
            for p in fp["pads"]:
                if p["net"] and p["net"] != "GND" and p["num"]:
                    pins.append((p["num"], p["net"]))
            pins.sort(key=lambda t: (len(t[0]), t[0]))
            kria_conns[jref] = {"x": fp["x"], "y": fp["y"], "non_gnd_pins": pins}

    # Mechanical cantilever & mounting holes
    holes = {}
    for h in ("H1", "H2", "H3", "H4", "H5"):
        if h in fp_by_ref:
            holes[h] = (fp_by_ref[h]["x"], fp_by_ref[h]["y"])

    # Zone summary
    zone_summary = []
    for z in zones:
        if not z["is_keepout"]:
            zone_summary.append({
                "net": z["net"], "name": z["name"], "layers": z["layers"],
                "bbox": [round(c, 2) for c in z["bbox"]] if z["bbox"] else None,
            })
    keepout_summary = Counter((tuple(z["layers"]), z["name"][:25]) for z in zones if z["is_keepout"])

    return {
        "pcb_flags": pcb_flags,
        "stackup": stackup,
        "netclasses": pro.get("net_settings", {}).get("classes", []),
        "edge_poly": edge_polys[0] if edge_polys else [],
        "edge_bbox_mm": {
            "xmin": min(p[0] for p in edge_polys[0]),
            "xmax": max(p[0] for p in edge_polys[0]),
            "ymin": min(p[1] for p in edge_polys[0]),
            "ymax": max(p[1] for p in edge_polys[0]),
            "width": round(max(p[0] for p in edge_polys[0]) - min(p[0] for p in edge_polys[0]), 2),
            "height": round(max(p[1] for p in edge_polys[0]) - min(p[1] for p in edge_polys[0]), 2),
        } if edge_polys else {},
        "mounting_holes": holes,
        "via_stats": {f"{k}": v for k, v in via_caps.items()},
        "gnd_via_total": len(gnd_vias),
        "rf_band_gnd_vias": len(rf_band_gnd_vias),
        "row_top_gnd_via_count": len(row_top_vias),
        "row_top_gnd_via_max_gap_mm": max(row_top_gaps) if row_top_gaps else None,
        "zones": zone_summary,
        "keepouts_count": sum(1 for z in zones if z["is_keepout"]),
        "diff_pairs": diff_pairs,
        "rf_nets": rf_nets,
        "ep_audit": ep_audit,
        "sma_order": sma_order,
        "kria_conns": kria_conns,
    }


def parse_schematics(root: str) -> dict[str, Any]:
    """Extract all symbols (ref, value, footprint, DNP) and hierarchical/global labels from rev03/*.kicad_sch."""
    sheets = {}
    for path in sorted(glob.glob(os.path.join(root, "rev03", "*.kicad_sch"))):
        name = os.path.basename(path)
        tree = load_sexpr(path)
        syms = []
        labels = set()
        for item in tree[1:]:
            if not isinstance(item, list):
                continue
            if item[0] == "symbol":
                props = {}
                dnp = False
                for sub in item[1:]:
                    if isinstance(sub, list) and sub[0] == "property" and len(sub) >= 3:
                        props[sub[1]] = sub[2]
                    elif isinstance(sub, list) and sub[0] == "dnp" and len(sub) >= 2 and sub[1] == "yes":
                        dnp = True
                ref = props.get("Reference", "")
                if ref and not ref.startswith("#"):
                    syms.append({
                        "ref": ref,
                        "val": props.get("Value", ""),
                        "fp": props.get("Footprint", ""),
                        "dnp": dnp,
                    })
            elif item[0] in ("label", "global_label", "hierarchical_label") and len(item) >= 2:
                labels.add(item[1])
        sheets[name] = {
            "symbol_count": len(syms),
            "symbols": sorted(syms, key=lambda s: s["ref"]),
            "labels": sorted(labels),
        }
    return sheets


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
    ap.add_argument("--json-out", default=None, help="Optional path to save full JSON audit data")
    args = ap.parse_args()

    pcb_data = parse_pcb(args.root)
    sch_data = parse_schematics(args.root)
    out = {"pcb": pcb_data, "schematics": sch_data}

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2)

    print("=== BOARD & STACKUP ===")
    print("Dimensions:", pcb_data["edge_bbox_mm"], "Thickness(mm):", pcb_data["pcb_flags"]["thickness_mm"])
    print("Setup flags:", pcb_data["pcb_flags"])
    for layer in pcb_data["stackup"]:
        print(f"  {layer['name']:14s} type={str(layer['type']):10s} t={layer['thickness_mm']:.4f}mm Er={layer['epsilon_r']:.2f}")

    print("\n=== MOUNTING HOLES & SMA LAUNCHES ===")
    print("Holes:", pcb_data["mounting_holes"])
    for s in pcb_data["sma_order"]:
        print(f"  {s['ref']:5s} ({s['val']:10s}) x={s['x']:6.2f} y={s['y']:6.2f} esd={s['esd_ref']} dx/dy={s['esd_dx_dy']} dist_M3={s['nearest_m3_mm']}mm")

    print("\n=== DIFF PAIRS (LENGTH & SKEW & VIA RETURN) ===")
    for dp in pcb_data["diff_pairs"]:
        lp, ln = dp["p"]["len_mm"], dp["n"]["len_mm"]
        lays = set(dp["p"]["by_layer_mm"]) | set(dp["n"]["by_layer_mm"])
        ws = set(dp["p"]["by_width_mm"]) | set(dp["n"]["by_width_mm"])
        vret = dp["p"]["ret_via_dists_mm"] + dp["n"]["ret_via_dists_mm"]
        max_ret = max(vret) if vret else 0.0
        splits = f" SPLITS={dp['l3_over_in3_split_edges']}" if dp["l3_over_in3_split_edges"] else ""
        print(f"  {dp['pair']:24s} P={lp:6.2f}mm N={ln:6.2f}mm skew={dp['intra_skew_mm']:5.3f}mm vias={dp['p']['vias']}/{dp['n']['vias']} maxGNDvia={max_ret:5.2f}mm lays={sorted(lays)} w={sorted(ws)}{splits}")

    print("\n=== RF / IF / CLK SINGLE-ENDED & TRACE SUMMARY ===")
    for n, m in pcb_data["rf_nets"].items():
        max_ret = max(m["ret_via_dists_mm"]) if m["ret_via_dists_mm"] else 0.0
        print(f"  {n:26s} len={m['len_mm']:6.2f}mm vias={m['vias']} maxGNDvia={max_ret:5.2f}mm w={m['by_width_mm']} lays={m['by_layer_mm']}")

    print("\n=== EXPOSED PAD / THERMAL VIAS ===")
    for ref, info in pcb_data["ep_audit"].items():
        if info["ep_vias"] or ref in ("U401", "U501", "U601", "U901", "U902", "U903", "U904", "U1001", "U1101", "U1201"):
            print(f"  {ref:6s} ({info['val']:16s}) r4_GNDvias={info['gnd_vias_r4mm']:3d} ep={info['ep_vias']}")

    print("\n=== VIA & STITCHING SUMMARY ===")
    print("Total GND vias:", pcb_data["gnd_via_total"], "RF band (y>=198):", pcb_data["rf_band_gnd_vias"], "Top edge (y>=209.5):", pcb_data["row_top_gnd_via_count"], "Max X gap top:", pcb_data["row_top_gnd_via_max_gap_mm"])
    print("Via capping/filling breakdown:", pcb_data["via_stats"])


if __name__ == "__main__":
    main()
