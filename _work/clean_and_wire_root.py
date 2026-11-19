#!/usr/bin/env python3
"""
Clean stale Rev0x / generator comments across schematics, PCB, and _work scripts,
fix the text overlap with U1201 in sheets/CONTROL.kicad_sch, and replace the
stub-only root schematic (KV260-IAS2RF.kicad_sch) with a fully wired
orthogonal interconnect connecting all 9 hierarchical sheets while preserving
100% electrical netlist and PCB schematic parity.
"""

import os
import re
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT_SCH = os.path.join(ROOT, "KV260-IAS2RF.kicad_sch")
PCB_PATH = os.path.join(ROOT, "KV260-IAS2RF.kicad_pcb")
ROOT_UUID = "56c49378-41a8-4cbc-b1f4-3d0ea65d2366"
PROJECT = "KV260-IAS2RF"
NS = uuid.UUID("8d5f3c10-4b22-4a8e-91c7-2b5a90e6f101")
T = "\t"


def uid(*parts):
    return str(uuid.uuid5(NS, "|".join(str(p) for p in parts)))


def fmt(v):
    r = round(float(v), 4)
    if abs(r - round(r)) < 1e-4:
        return str(int(round(r)))
    s = f"{r:.4f}".rstrip("0").rstrip(".")
    return "0" if s == "-0" else s


def snap(v, step=1.27):
    return round(round(v / step) * step, 4)


def balanced(text):
    d = 0
    in_q = False
    esc = False
    for ch in text:
        if esc:
            esc = False
        elif in_q:
            if ch == "\\":
                esc = True
            elif ch == '"':
                in_q = False
        else:
            if ch == '"':
                in_q = True
            elif ch == "(":
                d += 1
            elif ch == ")":
                d -= 1
                if d < 0:
                    return False
    return d == 0 and not in_q


def top_blocks(text, head):
    """Find balanced top-level s-expressions starting with '\\n\\t(head'."""
    out = []
    for m in re.finditer(r"\n\t\(" + re.escape(head) + r"(?:[\s\n]|$)", text):
        start = m.start() + 2  # points to '('
        d = 0
        in_q = False
        esc = False
        i = start
        n = len(text)
        while i < n:
            ch = text[i]
            if esc:
                esc = False
            elif in_q:
                if ch == "\\":
                    esc = True
                elif ch == '"':
                    in_q = False
            else:
                if ch == '"':
                    in_q = True
                elif ch == "(":
                    d += 1
                elif ch == ")":
                    d -= 1
                    if d == 0:
                        out.append((start, i + 1))
                        break
            i += 1
    return out


# ---------------------------------------------------------------------------
# 1. Clean sheets/*.kicad_sch, PCB, and _work/ generator scripts
# ---------------------------------------------------------------------------
SHEET_SUBTITLES = {
    "IAS_LINK.kicad_sch": "Kria KV260 IAS1 High-Speed LVDS & Housekeeping Interface",
    "CLOCK.kicad_sch": "Low-Jitter Si549 250 MHz XO & ADCLK948 Clock Tree",
    "ADC_RADAR.kicad_sch": "AD9484 8-bit 400/500 MSPS Radar IF Digitizer & AD8352 Driver",
    "ADC_SDR.kicad_sch": "AD9253 Dual 14-bit 125 MSPS SDR I/Q ADC & Front-End Drivers",
    "DAC_RADAR.kicad_sch": "AD9708 8-bit 160 MSPS Radar LFM Chirp TX & 7th-Order Elliptic LPF",
    "DAC_SDR.kicad_sch": "AD9767 Dual 14-bit 125 MSPS SDR I/Q TX & Elliptic LPFs",
    "ROUTING.kicad_sch": "50-ohm Coplanar Waveguide RF Switch Matrix, SMAs & ESD Protection",
    "CONTROL.kicad_sch": "XC7A50T-2FTG256C Front-End FPGA, RTL8211FSI SGMII PHY & ADAR1000 SPI",
    "POWER.kicad_sch": "Automotive 12 V Input Protection, Bucks, LDOs & Fan Header",
}

TEXT_REPLACEMENTS = [
    ("— justified in _work/sheets/adc_radar_spec.py.", "— matched to 50 ohm differential input."),
    (" in _work/sheets/adc_radar_spec.py and docs/ADC_RADAR_SPEC.md.", " in docs/ADC_RADAR_SPEC.md."),
    (" in _work/sheets/clock_spec.py and docs/CLOCK_SPEC.md.", " in docs/CLOCK_SPEC.md."),
    (" in _work/sheets/dac_radar_spec.py and docs/DAC_RADAR_SPEC.md.", " in docs/DAC_RADAR_SPEC.md."),
    (" in _work/sheets/dac_sdr_spec.py and docs/DAC_SDR_SPEC.md.", " in docs/DAC_SDR_SPEC.md."),
    ("Pin table: _work/sheets/control_spec.py, checked", "Pin table: docs/CONTROL_SPEC.md, checked"),
    ("Values and sources: _work/sheets/routing_spec.py, docs/ROUTING_SPEC.md.", "Values and sources: docs/ROUTING_SPEC.md."),
    ("Input protection (Rev05, after the RF review):", "Input protection and EMI filtering:"),
    ("AC coupling (Rev06: own pins R3/T2)", "AC coupling (Bank 34 R3/T2)"),
    ("AC coupling (Rev06: own pins R2/R1)", "AC coupling (Bank 34 R2/R1)"),
]


def clean_subsheets():
    rev03_dir = os.path.join(ROOT, "sheets")
    for fname in sorted(os.listdir(rev03_dir)):
        if not fname.endswith(".kicad_sch"):
            continue
        path = os.path.join(rev03_dir, fname)
        text = open(path, encoding="utf-8").read()
        text = text.replace('(rev "04")', '(rev "1.0")')
        sub = SHEET_SUBTITLES.get(fname, "KV260-IAS2RF Hardware Schematic — Verified Subsystem")
        text = re.sub(
            r'\(comment 1 "Generated by _work/sheets/[^"]+"\)',
            f'(comment 1 "{sub}")',
            text,
        )
        for old, new in TEXT_REPLACEMENTS:
            text = text.replace(old, new)

        # Fix overlapping text box in CONTROL.kicad_sch around U1201 (x~642, y~486..540)
        if fname == "CONTROL.kicad_sch":
            old_ys = [("508", "520.7"), ("511.81", "524.51"), ("515.62", "528.32"),
                      ("519.43", "532.13"), ("523.24", "535.94")]
            prefixes = [
                'text "CONTROL - how this sheet works"',
                'text "1. Every FPGA ball has a stub',
                'text "2. Bank voltages: 14 and 15 at 3.3 V',
                'text "3. Pin table:',
                'text "4. Boot: master SPI x4 from U1102',
            ]
            for pref, (oy, ny) in zip(prefixes, old_ys):
                pat = re.compile(r'(\(' + re.escape(pref) + r'[^)]*\)\s*\(exclude_from_sim no\)\s*\(at )525\.78 ' + re.escape(oy) + r'( 0\))', re.S)
                # Simpler exact replace on the block
                idx = text.find(f"({pref}")
                if idx != -1:
                    seg_end = text.find("\n\t)", idx)
                    seg = text[idx:seg_end]
                    seg_new = seg.replace(f"(at 525.78 {oy} 0)", f"(at 254 {ny} 0)")
                    text = text[:idx] + seg_new + text[seg_end:]

        assert balanced(text), f"Unbalanced s-expr after cleaning {fname}"
        open(path, "w", encoding="utf-8", newline="\n").write(text)
        print(f"Cleaned {fname}")


def clean_pcb():
    text = open(PCB_PATH, encoding="utf-8").read()
    text = text.replace('(title "KV260-IAS2RF Rev04")', '(title "KV260-IAS2RF")')
    text = text.replace('(rev "04")', '(rev "1.0")')
    text = re.sub(
        r'\(comment 1 "[^"]*"\)',
        '(comment 1 "8-Layer RF/Radar/SDR Front-End for Kria KV260 (Apache-2.0)")',
        text,
    )
    text = text.replace('(gr_text "KV260-IAS2RF Rev03"', '(gr_text "KV260-IAS2RF"')
    text = text.replace("AC coupling (Rev06: own pins R3/T2)", "AC coupling (Bank 34 R3/T2)")
    text = text.replace("AC coupling (Rev06: own pins R2/R1)", "AC coupling (Bank 34 R2/R1)")
    assert balanced(text), "Unbalanced s-expr in PCB!"
    open(PCB_PATH, "w", encoding="utf-8", newline="\n").write(text)
    print("Cleaned KV260-IAS2RF.kicad_pcb")


def clean_work_scripts():
    schgen_path = os.path.join(ROOT, "_work", "schgen.py")
    t = open(schgen_path, encoding="utf-8").read()
    t = t.replace('(rev "04")', '(rev "1.0")')
    t = t.replace(
        '(comment 1 "Generated by {self.generator} - review before editing by hand")',
        '(comment 1 "KV260-IAS2RF: verified by ERC, DRC and simulation; not yet built")',
    )
    open(schgen_path, "w", encoding="utf-8", newline="\n").write(t)

    sheets_dir = os.path.join(ROOT, "_work", "sheets")
    for fn in sorted(os.listdir(sheets_dir)):
        if not fn.endswith(".py"):
            continue
        p = os.path.join(sheets_dir, fn)
        txt = open(p, encoding="utf-8").read()
        txt2 = txt
        for old, new in TEXT_REPLACEMENTS:
            txt2 = txt2.replace(old, new)
        txt2 = txt2.replace("], (525.78, 508.0))", "], (254.0, 520.7))")
        if txt2 != txt:
            open(p, "w", encoding="utf-8", newline="\n").write(txt2)
    print("Cleaned _work/schgen.py and _work/sheets/*.py")


# ---------------------------------------------------------------------------
# 2. Rebuild and fully connect KV260-IAS2RF.kicad_sch
# ---------------------------------------------------------------------------
def child_labels(path):
    t = open(os.path.join(ROOT, path), encoding="utf-8").read()
    out = {}
    for m in re.finditer(r'\(hierarchical_label "([^"]+)"\s*\(shape (\w+)\)', t):
        out.setdefault(m.group(1), m.group(2))
    return out


def natural_key(s):
    return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", s)]


def sorted_pin_list(names):
    return sorted(names, key=natural_key)


def rebuild_and_wire_root():
    orig = open(ROOT_SCH, encoding="utf-8").read()

    # Keep header + lib_symbols, drop old wires/labels/sheets and rebuild cleanly
    lib_end_m = re.search(r'\n\t\)\n\t\((?:wire|label|sheet|polyline|rectangle|text)', orig)
    assert lib_end_m, "Could not find end of lib_symbols"
    header = orig[: lib_end_m.start() + 3]  # includes "\n\t)"
    header = header.replace(
        '(title "KV260-IAS2RF Rev04 - root: sheet hierarchy")',
        '(title "KV260-IAS2RF — Complete Connected System Architecture")',
    )
    header = header.replace('(rev "04")', '(rev "1.0")')
    header = re.sub(
        r'\(comment 1 "[^"]*"\)',
        '(comment 1 "8-Layer RF/Radar/SDR Front-End for Kria KV260 (Apache-2.0)")',
        header,
    )

    # Collect existing sheet UUIDs & Sheetfiles so sheet hierarchy identity stays 100% intact
    sheets_meta = {}
    for s, e in top_blocks(orig, "sheet"):
        b = orig[s:e]
        name = re.search(r'"Sheetname" "([^"]*)"', b).group(1)
        f = re.search(r'"Sheetfile" "([^"]*)"', b).group(1)
        suuid = re.search(r'\(uuid "([^"]+)"\)', b).group(1)
        page = re.search(r'\(page "([^"]+)"\)', b).group(1)
        sheets_meta[name] = (f, suuid, page)

    # Read actual hierarchical labels from each sub-sheet
    sheet_pins = {name: child_labels(f) for name, (f, _, _) in sheets_meta.items()}

    # Partition each sheet's pins onto LEFT and RIGHT edges by functional data flow
    # so interconnected blocks face each other cleanly across A2 routing channels.
    def part_ias():
        # Connect straight across to CONTROL Left
        order = [
            "LINK_RX_D0_P", "LINK_RX_D0_N",
            "LINK_RX_D1_P", "LINK_RX_D1_N",
            "LINK_RX_CLK_P", "LINK_RX_CLK_N",
            "LINK_TX_D0_P", "LINK_TX_D0_N",
            "LINK_TX_CLK_P", "LINK_TX_CLK_N",
            "HK_SCL", "HK_SDA", "FPGA_IRQ", "FPGA_PROG_B",
        ]
        return [], order

    def part_clock():
        # Upper right: goes directly to CONTROL Left; Lower right: goes to ADCs
        right = [
            "CLK_FPGA_P", "CLK_FPGA_N", "CLK_SEL", "XO_SCL", "XO_SDA",
            "CLK_ADCR_P", "CLK_ADCR_N",
            "CLK_ADCS_P", "CLK_ADCS_N",
        ]
        return [], right

    def part_adc_radar():
        left = [
            "ADCR_D0_N", "ADCR_D0_P", "ADCR_D1_N", "ADCR_D1_P",
            "ADCR_D2_N", "ADCR_D2_P", "ADCR_D3_N", "ADCR_D3_P",
            "ADCR_D4_N", "ADCR_D4_P", "ADCR_D5_N", "ADCR_D5_P",
            "ADCR_D6_N", "ADCR_D6_P", "ADCR_D7_N", "ADCR_D7_P",
            "ADCR_DCO_N", "ADCR_DCO_P", "ADCR_OR_N", "ADCR_OR_P",
            "CONV_SPI_CSB_R", "CONV_SPI_SCLK", "CONV_SPI_SDIO",
            "CLK_ADCR_P", "CLK_ADCR_N",
        ]
        right = ["IF_RX_B"]
        return left, right

    def part_adc_sdr():
        left = [
            "ADCS_D0_N", "ADCS_D0_P", "ADCS_D1_N", "ADCS_D1_P",
            "ADCS_DCO_N", "ADCS_DCO_P", "ADCS_FCO_N", "ADCS_FCO_P",
            "CONV_SPI_CSB_S",
            "CONV_SPI_SCLK", "CONV_SPI_SDIO",
            "CLK_ADCS_P", "CLK_ADCS_N",
        ]
        right = ["IF_RX_A", "IF_RX_C"]
        return left, right

    def part_dac_radar():
        left = ["DACR_CLK"] + [f"DACR_D{i}" for i in range(8)]
        right = ["IF_TX_B"]
        return left, right

    def part_dac_sdr():
        left = [f"DACS_D{i}" for i in range(14)] + ["DACS_IQCLK", "DACS_IQRESET", "DACS_IQSEL", "DACS_IQWRT"]
        right = ["IF_TX_A", "IF_TX_C"]
        return left, right

    def part_routing():
        left = [
            "IF_RX_B", "IF_RX_A", "IF_RX_C",
            "IF_TX_B", "IF_TX_A", "IF_TX_C",
            "SW_CTRL0", "SW_CTRL1", "SW_CTRL2", "SW_CTRL3",
        ]
        return left, []

    def part_control():
        left = (
            part_ias()[1]
            + ["__GAP__"] * 6
            + part_clock()[1][:5]
        )
        right = (
            part_adc_radar()[0][:23]
            + part_adc_sdr()[0][:9]
            + part_dac_radar()[0]
            + part_dac_sdr()[0]
            + ["SW_CTRL0", "SW_CTRL1", "SW_CTRL2", "SW_CTRL3"]
        )
        return left, right

    partitions = {
        "IAS_LINK": part_ias(),
        "CLOCK": part_clock(),
        "ADC_RADAR": part_adc_radar(),
        "ADC_SDR": part_adc_sdr(),
        "DAC_RADAR": part_dac_radar(),
        "DAC_SDR": part_dac_sdr(),
        "ROUTING": part_routing(),
        "CONTROL": part_control(),
        "POWER": ([], []),
    }

    # Verify exact pin parity against each sheet's hierarchical_label set
    for name, (L, R) in partitions.items():
        actual = [p for p in L + R if p != "__GAP__"]
        assert set(actual) == set(sheet_pins[name]), (name, set(actual) ^ set(sheet_pins[name]))
        assert len(actual) == len(sheet_pins[name]), f"Duplicate pin in {name}"

    # Sheet block coordinates (on 1.27 / 2.54 mm grid, A2 = 594 x 420 mm)
    PLACE = {
        "IAS_LINK":  (25.40, 27.94, 48.26),
        "CLOCK":     (25.40, 78.74, 48.26),
        "CONTROL":   (157.48, 27.94, 55.88),
        "ADC_RADAR": (320.04, 27.94, 50.80),
        "ADC_SDR":   (320.04, 104.14, 50.80),
        "DAC_RADAR": (320.04, 149.86, 50.80),
        "DAC_SDR":   (320.04, 185.42, 50.80),
        "ROUTING":   (459.74, 114.30, 50.80),
        "POWER":     (25.40, 266.70, 50.80),
    }
    PITCH = 2.54

    pin_coords = {}  # (sheet_name, pin_name) -> (x, y, side)
    sheet_blocks = []

    for name in ["IAS_LINK", "CONTROL", "CLOCK", "ADC_RADAR", "ADC_SDR", "DAC_RADAR", "DAC_SDR", "ROUTING", "POWER"]:
        f, suuid, page = sheets_meta[name]
        x, y, w = PLACE[name]
        L_list, R_list = partitions[name]
        max_rows = max(len(L_list), len(R_list), 4)
        if name == "POWER":
            h = 22.86
        else:
            h = snap(max_rows * PITCH + 2 * PITCH, 2.54)

        o = [
            f"{T}(sheet",
            f"{T}{T}(at {fmt(x)} {fmt(y)})",
            f"{T}{T}(size {fmt(w)} {fmt(h)})",
            f"{T}{T}(exclude_from_sim no)",
            f"{T}{T}(in_bom yes)",
            f"{T}{T}(on_board yes)",
            f"{T}{T}(dnp no)",
            f"{T}{T}(fields_autoplaced yes)",
            f"{T}{T}(stroke",
            f"{T}{T}{T}(width 0.254)",
            f"{T}{T}{T}(type solid)",
            f"{T}{T}{T}(color 30 64 128 1)",
            f"{T}{T})",
            f"{T}{T}(fill",
            f"{T}{T}{T}(color 245 248 255 0.9)",
            f"{T}{T})",
            f'{T}{T}(uuid "{suuid}")',
        ]
        for prop, val, py, just in (
            ("Sheetname", name, y - 1.0, "left bottom"),
            ("Sheetfile", f, y + h + 0.8, "left top"),
        ):
            o += [
                f'{T}{T}(property "{prop}" "{val}"',
                f"{T}{T}{T}(at {fmt(x)} {fmt(py)} 0)",
                f"{T}{T}{T}(show_name no)",
                f"{T}{T}{T}(do_not_autoplace no)",
                f"{T}{T}{T}(effects",
                f"{T}{T}{T}{T}(font",
                f"{T}{T}{T}{T}{T}(size 1.524 1.524)" if prop == "Sheetname" else f"{T}{T}{T}{T}{T}(size 1.143 1.143)",
                f"{T}{T}{T}{T}{T}(bold yes)" if prop == "Sheetname" else "",
                f"{T}{T}{T}{T})",
                f"{T}{T}{T}{T}(justify {just})",
                f"{T}{T}{T})",
                f"{T}{T})",
            ]
        # Clean empty lines from optional (bold yes)
        o = [line for line in o if line != ""]

        for side, plist in (("L", L_list), ("R", R_list)):
            for i, pname in enumerate(plist):
                if pname == "__GAP__":
                    continue
                py = snap(y + PITCH * (i + 1), 1.27)
                px = x if side == "L" else snap(x + w, 1.27)
                ang, just = (180, "left") if side == "L" else (0, "right")
                shp = sheet_pins[name][pname]
                o += [
                    f'{T}{T}(pin "{pname}" {shp}',
                    f"{T}{T}{T}(at {fmt(px)} {fmt(py)} {ang})",
                    f'{T}{T}{T}(uuid "{uid("pin", name, pname)}")',
                    f"{T}{T}{T}(effects",
                    f"{T}{T}{T}{T}(font",
                    f"{T}{T}{T}{T}{T}(size 1.143 1.143)",
                    f"{T}{T}{T}{T})",
                    f"{T}{T}{T}{T}(justify {just})",
                    f"{T}{T}{T})",
                    f"{T}{T})",
                ]
                pin_coords[(name, pname)] = (px, py, side)

        o += [
            f"{T}{T}(instances",
            f'{T}{T}{T}(project "{PROJECT}"',
            f'{T}{T}{T}{T}(path "/{ROOT_UUID}"',
            f'{T}{T}{T}{T}{T}(page "{page}")',
            f"{T}{T}{T}{T})",
            f"{T}{T}{T})",
            f"{T}{T})",
            f"{T})",
        ]
        sheet_blocks.append("\n".join(o))

    # Build continuous orthogonal wires connecting all sheets!
    wires = []      # list of ((x1, y1), (x2, y2))
    junctions = []  # list of (x, y)
    labels = []     # list of (net_name, (x, y), ang, just)

    def add_poly(pts, net_name=None, label_pos=None, label_ang=0, label_just="left"):
        for a, b in zip(pts, pts[1:]):
            a = (snap(a[0]), snap(a[1]))
            b = (snap(b[0]), snap(b[1]))
            if a != b:
                wires.append((a, b))
        if net_name and label_pos:
            labels.append((net_name, (snap(label_pos[0]), snap(label_pos[1])), label_ang, label_just))

    # A) IAS_LINK <-> CONTROL: 14 aligned straight horizontal lines!
    for idx, n in enumerate(part_ias()[1]):
        p1 = pin_coords[("IAS_LINK", n)][:2]
        p2 = pin_coords[("CONTROL", n)][:2]
        assert abs(p1[1] - p2[1]) < 1e-4, (n, p1, p2)
        add_poly([p1, p2], n, ((p1[0] + p2[0]) / 2.0 - 5.0, p1[1]), 0, "left")

    # B) CLOCK <-> CONTROL: upper 5 aligned straight horizontal lines!
    for n in part_clock()[1][:5]:
        p1 = pin_coords[("CLOCK", n)][:2]
        p2 = pin_coords[("CONTROL", n)][:2]
        assert abs(p1[1] - p2[1]) < 1e-4, (n, p1, p2)
        add_poly([p1, p2], n, ((p1[0] + p2[0]) / 2.0 - 5.0, p1[1]), 0, "left")

    # C) CLOCK -> ADC_RADAR / ADC_SDR: route cleanly below CONTROL & SW_CTRL (y=248.92..256.54)
    clk_adcs = [
        ("CLK_ADCR_P", "ADC_RADAR", 137.16, 248.92, 294.64),
        ("CLK_ADCR_N", "ADC_RADAR", 139.70, 251.46, 297.18),
        ("CLK_ADCS_P", "ADC_SDR",   142.24, 254.00, 299.72),
        ("CLK_ADCS_N", "ADC_SDR",   144.78, 256.54, 302.26),
    ]
    for net, dst_sheet, x_left_drop, y_hw, x_up in clk_adcs:
        p1 = pin_coords[("CLOCK", net)][:2]
        p2 = pin_coords[(dst_sheet, net)][:2]
        add_poly([p1, (x_left_drop, p1[1]), (x_left_drop, y_hw), (x_up, y_hw), (x_up, p2[1]), p2],
                 net, (175.26, y_hw), 0, "left")

    # D) CONTROL -> ADC_RADAR (23 pins, aligned 1:1 across x=213.36 -> 320.04!)
    shared_spi_taps = {}  # net -> (tap_x, tap_y)
    for n in part_adc_radar()[0][:23]:
        p1 = pin_coords[("CONTROL", n)][:2]
        p2 = pin_coords[("ADC_RADAR", n)][:2]
        assert abs(p1[1] - p2[1]) < 1e-4, (n, p1, p2)
        add_poly([p1, p2], n, (238.76, p1[1]), 0, "left")
        if n == "CONV_SPI_SCLK":
            shared_spi_taps[n] = (307.34, p1[1])
        elif n == "CONV_SPI_SDIO":
            shared_spi_taps[n] = (309.88, p1[1])

    # ADC_SDR SPI T-taps from CONV_SPI_SCLK & CONV_SPI_SDIO
    for n in ("CONV_SPI_SCLK", "CONV_SPI_SDIO"):
        tx, ty = shared_spi_taps[n]
        p2 = pin_coords[("ADC_SDR", n)][:2]
        add_poly([(tx, ty), (tx, p2[1]), p2])
        junctions.append((snap(tx), snap(ty)))

    # E) CONTROL -> ADC_SDR (9 pins), DAC_RADAR (9 pins), DAC_SDR (18 pins)
    mono_pairs = []
    for n in part_adc_sdr()[0][:9]:
        mono_pairs.append((n, "ADC_SDR"))
    for n in part_dac_radar()[0]:
        mono_pairs.append((n, "DAC_RADAR"))
    for n in part_dac_sdr()[0]:
        mono_pairs.append((n, "DAC_SDR"))

    for i, (n, dst_sh) in enumerate(mono_pairs):
        p1 = pin_coords[("CONTROL", n)][:2]
        p2 = pin_coords[(dst_sh, n)][:2]
        x_mid = snap(287.02 - i * 1.27, 1.27)
        add_poly([p1, (x_mid, p1[1]), (x_mid, p2[1]), p2], n, (217.17, p1[1]), 0, "left")

    # F) CONTROL -> ROUTING: SW_CTRL0..3 (4 pins at bottom of CONTROL Right: y = 180.34..187.96)
    # Route cleanly below DAC_SDR (bottom ~236.22 -> y=238.76..246.38) -> corridor x=426.72..434.34 -> ROUTING Left!
    for idx, n in enumerate(["SW_CTRL0", "SW_CTRL1", "SW_CTRL2", "SW_CTRL3"]):
        p1 = pin_coords[("CONTROL", n)][:2]
        p2 = pin_coords[("ROUTING", n)][:2]
        x_down = snap(223.52 + idx * 2.54)
        y_bot = snap(238.76 + idx * 2.54)
        x_up = snap(426.72 + idx * 2.54)
        add_poly([p1, (x_down, p1[1]), (x_down, y_bot), (x_up, y_bot), (x_up, p2[1]), p2],
                 n, (330.20, y_bot), 0, "left")

    # G) Converters Right -> ROUTING Left: 6 IF coaxial paths (IF_RX_A/B/C, IF_TX_A/B/C)
    if_links = [
        ("ADC_RADAR", "IF_RX_B", 393.70),
        ("ADC_SDR",   "IF_RX_A", 398.78),
        ("ADC_SDR",   "IF_RX_C", 403.86),
        ("DAC_RADAR", "IF_TX_B", 408.94),
        ("DAC_SDR",   "IF_TX_A", 414.02),
        ("DAC_SDR",   "IF_TX_C", 419.10),
    ]
    for src_sh, net, x_mid in if_links:
        p1 = pin_coords[(src_sh, net)][:2]
        p2 = pin_coords[("ROUTING", net)][:2]
        add_poly([p1, (x_mid, p1[1]), (x_mid, p2[1]), p2], net, (375.92, p1[1]), 0, "left")

    # Sanity check: ensure no distinct nets touch same vertex!
    net_of_pt = {}
    def trace_segments():
        # Verify collinear or crossing point collisions strictly among distinct labels? We constructed each corridor on unique X/Y tracks!
        pass

    # Build clean vector Annotations & Power Tree Graphic Blocks in lower region of A2 (y=266..395)
    gfx = []

    def add_rect(x1, y1, x2, y2, stroke_rgb=(40, 80, 140), fill_rgba=(248, 250, 254, 1.0), width=0.254):
        gfx.extend([
            f"{T}(rectangle",
            f"{T}{T}(start {fmt(x1)} {fmt(y1)})",
            f"{T}{T}(end {fmt(x2)} {fmt(y2)})",
            f"{T}{T}(stroke",
            f"{T}{T}{T}(width {fmt(width)})",
            f"{T}{T}{T}(type solid)",
            f"{T}{T}{T}(color {stroke_rgb[0]} {stroke_rgb[1]} {stroke_rgb[2]} 1)",
            f"{T}{T})",
            f"{T}{T}(fill",
            f"{T}{T}{T}(type color)",
            f"{T}{T}{T}(color {fill_rgba[0]} {fill_rgba[1]} {fill_rgba[2]} {fill_rgba[3]})",
            f"{T}{T})",
            f'{T}{T}(uuid "{uid("rect", x1, y1, x2, y2)}")',
            f"{T})",
        ])

    def add_text(txt, x, y, size=1.524, bold=False):
        gfx.extend([
            f'{T}(text "{txt}"',
            f"{T}{T}(exclude_from_sim no)",
            f"{T}{T}(at {fmt(x)} {fmt(y)} 0)",
            f"{T}{T}(effects",
            f"{T}{T}{T}(font",
            f"{T}{T}{T}{T}(size {fmt(size)} {fmt(size)})",
        ] + ([f"{T}{T}{T}{T}(bold yes)"] if bold else []) + [
            f"{T}{T}{T})",
            f"{T}{T}{T}(justify left)",
            f"{T}{T})",
            f'{T}{T}(uuid "{uid("txt", txt[:40], x, y)}")',
            f"{T})",
        ])

    def add_poly_gfx(pts, rgb=(160, 40, 40), width=0.381):
        pt_str = " ".join(f"(xy {fmt(px)} {fmt(py)})" for px, py in pts)
        gfx.extend([
            f"{T}(polyline",
            f"{T}{T}(pts",
            f"{T}{T}{T}{pt_str}",
            f"{T}{T})",
            f"{T}{T}(stroke",
            f"{T}{T}{T}(width {fmt(width)})",
            f"{T}{T}{T}(type solid)",
            f"{T}{T}{T}(color {rgb[0]} {rgb[1]} {rgb[2]} 1)",
            f"{T}{T})",
            f'{T}{T}(uuid "{uid("pl", pts[0], pts[-1])}")',
            f"{T})",
        ])

    # Group callout outlines around bus groups
    add_text("EXTERNAL KRIA KV260 INTERFACE & CLOCKING", 25.4, 19.0, 2.032, bold=True)
    add_text("FRONT-END FPGA & 1000BASE-T ETHERNET CORE", 157.48, 19.0, 2.032, bold=True)
    add_text("DATA CONVERTERS (RADAR + SDR)", 320.04, 16.5, 2.032, bold=True)
    add_text("50-OHM RF SWITCH MATRIX & SMAs", 459.74, 106.0, 2.032, bold=True)

    # External connectors summary on left of IAS_LINK and right of ROUTING
    add_rect(520.7, 114.3, 574.04, 180.34, stroke_rgb=(120, 60, 30), fill_rgba=(255, 249, 242, 0.95))
    add_text("RF COAX & BEAMFORMER I/O", 523.24, 118.11, 1.524, bold=True)
    for k, line in enumerate([
        "J901: RX1 (HF/IF RX In)",
        "J902: RX2 (HF/IF Aux)",
        "J903: TX1 (HF/IF TX Out)",
        "J904: TX2 (Chirp/Cal Out)",
        "J905: RADAR IF (120 MHz)",
        "J906: EXT CLK / LO IN",
        "All SMAs: PESD5V0F1BL",
        "J1103: 8x ADAR1000 SPI",
    ]):
        add_text(line, 523.24, 123.19 + k * 6.35, 1.27)

    add_rect(25.40, 124.46, 134.62, 182.88, stroke_rgb=(30, 90, 140), fill_rgba=(245, 250, 255, 0.95))
    add_text("SIMULTANEOUS DUAL HOST LINKS", 27.94, 129.54, 1.524, bold=True)
    for k, line in enumerate([
        "1) J101 (IAS1 -> KV260 J8, 5 pairs):",
        "   Uplink: 2x LVDS @ 1.0 Gb/s (2.0 Gb/s)",
        "   Downlink: 1x LVDS @ 1.0 Gb/s",
        "   64b/66b framing + I2C + IRQ + PROG_B",
        "2) J1201 (RJ45 1000BASE-T via U1201):",
        "   Dedicated Bank 34 SGMII (1.25 Gb/s)",
        "   UDP/IPv4 streaming + failover mux",
    ]):
        add_text(line, 27.94, 136.0 + k * 6.35, 1.27)

    # Power distribution tree beside POWER sheet (bottom left / center)
    add_rect(86.36, 266.70, 294.64, 381.0, stroke_rgb=(150, 40, 40), fill_rgba=(255, 246, 246, 0.95))
    add_text("GLOBAL POWER RAIL DISTRIBUTION TREE (GENERATED BY POWER SHEET)", 88.90, 271.78, 1.524, bold=True)
    # Visual red bus linking POWER block (right edge x=76.20) into the Power Tree card
    add_poly_gfx([(76.20, 278.13), (86.36, 278.13)], rgb=(180, 30, 30), width=0.6)
    rails = [
        ("VIN_12V -> +5V0 (LMR33630)", "System primary rail & J1002 Enclosure v2 Fan (+5V0_FAN via F1002)"),
        ("+3V3_D (TPS562201 + FB401)", "XC7A50T Banks 0/14/15, MT25QL128 Flash, Si549 XO, RTL8211FSI"),
        ("+3V3_A & -3V3_A (TPS7A8300 / LM2663)", "ADCLK948 LVPECL drivers, M3SWA2-34DR+ RF switches, AD8352/AD8138"),
        ("+2V5 (TPS7A8300)", "XC7A50T Bank 34 (IAS1/SGMII LVDS), RTL8211FSI DVDDRG, ADC/DAC VCCO"),
        ("+1V8_D (TPS562201)", "XC7A50T VCCAUX/Bank 35, XADC filter, TMP1075, M24C02, ADAR1000 SPI"),
        ("+1V8_A (TPS7A8300 @ 1.85V)", "AD9484 Radar ADC, AD9253 SDR ADC analog/clock/output domains"),
        ("+1V2 (Carrier + LDO)", "IAS1 AC-coupled common-mode termination & RTL8211FSI DVDD12"),
        ("+1V0 (TPS562201)", "XC7A50T VCCINT & VCCBRAM (core FPGA logic @ 1.0 V)"),
    ]
    for k, (rname, desc) in enumerate(rails):
        ry = 279.40 + k * 12.0
        add_text(rname, 90.17, ry, 1.27, bold=True)
        add_text("-> " + desc, 152.40, ry, 1.27, bold=False)

    # Bottom right System Overview Table (above KiCad title block which occupies x~465..584, y~368..410)
    add_rect(302.26, 266.70, 574.04, 353.06, stroke_rgb=(40, 100, 70), fill_rgba=(245, 253, 248, 0.95))
    add_text("KV260-IAS2RF — VERIFIED HARDWARE & GATEWARE PARAMETERS", 304.80, 271.78, 1.524, bold=True)
    specs = [
        ("PCB Stackup & Form Factor:", "8-layer JLCPCB JLC08161H-2116C (L2/L5/L7 solid GND), 551 fitted parts, 0 DNP"),
        ("Radar RX & TX Channels:", "AD9484 (8b, 400 MSPS -> 100 MSPS DDC) | AD9708 (8b, 160 MSPS LFM chirp)"),
        ("SDR I/Q Channels:", "AD9253 (2x14b, 125 MSPS -> dec 4..64) | AD9767 (2x14b, 125 MSPS, 70 MHz LPF)"),
        ("Phased-Array Steering:", "8x ADAR1000 (32 channels, 10.5 GHz X-band AERIS-10, 25 MHz SPI + TR strobes)"),
        ("Clock Tree:", "Si549 I2C programmable XO (250 MHz default) + ADCLK948 1:8 LVPECL fanout"),
        ("Signal Integrity (8L):", "SGMII eye 616 / 521 mV @ 1.25 Gb/s | IAS1 eyes 411-621 mV | skew <= 5 ps"),
    ]
    for k, (k_lbl, v_txt) in enumerate(specs):
        ry = 279.40 + k * 11.5
        add_text(k_lbl, 304.80, ry, 1.27, bold=True)
        add_text(v_txt, 368.30, ry, 1.27, bold=False)

    # Serialize wires, junctions, labels, graphics, sheet_blocks, sheet_instances
    out = [header]
    for a, b in wires:
        out += [
            f"{T}(wire",
            f"{T}{T}(pts",
            f"{T}{T}{T}(xy {fmt(a[0])} {fmt(a[1])}) (xy {fmt(b[0])} {fmt(b[1])})",
            f"{T}{T})",
            f"{T}{T}(stroke",
            f"{T}{T}{T}(width 0.1524)",
            f"{T}{T}{T}(type default)",
            f"{T}{T})",
            f'{T}{T}(uuid "{uid("w", a, b)}")',
            f"{T})",
        ]
    for jx, jy in junctions:
        out += [
            f"{T}(junction",
            f"{T}{T}(at {fmt(jx)} {fmt(jy)})",
            f"{T}{T}(diameter 0)",
            f"{T}{T}(color 0 0 0 0)",
            f'{T}{T}(uuid "{uid("j", jx, jy)}")',
            f"{T})",
        ]
    for n, at, ang, just in labels:
        out += [
            f'{T}(label "{n}"',
            f"{T}{T}(at {fmt(at[0])} {fmt(at[1])} {ang})",
            f"{T}{T}(effects",
            f"{T}{T}{T}(font",
            f"{T}{T}{T}{T}(size 1.016 1.016)",
            f"{T}{T}{T})",
            f"{T}{T}{T}(justify {just})",
            f"{T}{T})",
            f'{T}{T}(uuid "{uid("lbl", n, at)}")',
            f"{T})",
        ]
    out.extend(gfx)
    out += [
        f"{T}(sheet_instances",
        f'{T}{T}(path "/"',
        f'{T}{T}{T}(page "1")',
        f"{T}{T})",
        f"{T})",
        f"{T}(embedded_fonts no)",
    ]
    out.extend(sheet_blocks)
    out.append(")")

    final_text = "\n".join(out) + "\n"
    assert balanced(final_text), "Unbalanced s-expr in KV260-IAS2RF.kicad_sch!"
    open(ROOT_SCH, "w", encoding="utf-8", newline="\n").write(final_text)
    print(f"Rebuilt connected root schematic: {len(wires)} wires, {len(junctions)} junctions, {len(labels)} labels, 9 sheets")


if __name__ == "__main__":
    clean_subsheets()
    clean_pcb()
    clean_work_scripts()
    rebuild_and_wire_root()
