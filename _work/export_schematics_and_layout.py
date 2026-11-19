#!/usr/bin/env python3
"""
Export 100% vector KiCad schematics, full connected circuit composite,
10-page vector 8-layer PCB layout PDF, vector SVGs, and high-res PNGs.

Usage:
    D:/Tools/KiCadRoutingTools/.venv/Scripts/python.exe _work/export_schematics_and_layout.py
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile

import pymupdf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from toolpaths import KICAD_CLI

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCH_FILE = os.path.join(ROOT, "CSI2-KRIA-KV260_Rev01.kicad_sch")
PCB_FILE = os.path.join(ROOT, "CSI2-KRIA-KV260_Rev01.kicad_pcb")

DOCS_DIR = os.path.join(ROOT, "docs")
SCH_PDF = os.path.join(DOCS_DIR, "KV260-IAS2RF_schematic.pdf")
LAY_PDF = os.path.join(DOCS_DIR, "KV260-IAS2RF_layout.pdf")

IMG_DIR = os.path.join(DOCS_DIR, "img")
SCH_PNG_DIR = os.path.join(IMG_DIR, "sch")
HR_SCH_DIR = os.path.join(IMG_DIR, "highres", "sch")
HR_LAY_DIR = os.path.join(IMG_DIR, "highres", "layout")


def ensure_dirs():
    for d in (DOCS_DIR, IMG_DIR, SCH_PNG_DIR, HR_SCH_DIR, HR_LAY_DIR):
        os.makedirs(d, exist_ok=True)


def run_kicad(args):
    cmd = [KICAD_CLI] + args
    res = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=True)
    return res


def render_page_width(page, out_path, target_width_px, alpha=False):
    scale = target_width_px / page.rect.width
    mat = pymupdf.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=mat, alpha=alpha)
    pix.save(out_path)


def hex_to_rgb01(h):
    h = h.lstrip("#")
    return tuple(int(h[i : i + 2], 16) / 255.0 for i in (0, 2, 4))


# ---------------------------------------------------------------------------
# Part A: Schematics + Full Connected Circuit Composite
# ---------------------------------------------------------------------------

def identify_sch_pages(doc):
    """Map sheet name -> page index inside raw kicad-cli schematic PDF."""
    mapping = {}
    for idx in range(len(doc)):
        txt = doc[idx].get_text()
        if idx == 0 or "Complete Connected System Architecture" in txt:
            mapping["ROOT"] = idx
            continue
        m = re.search(r"File:\s*([A-Za-z0-9_]+)\.kicad_sch", txt)
        if m:
            mapping[m.group(1)] = idx
    return mapping


def build_full_circuit_pdf(raw_doc, page_map, out_pdf, out_svg):
    """
    Create an A0-landscape 100% vector composite containing all 12 sub-circuits
    arranged in signal-flow order and linked by color-coded inter-sheet bus trunks.
    """
    W, H = 3370.39, 2383.94  # A0 Landscape in pt (1189 x 841 mm)
    comp = pymupdf.open()
    p = comp.new_page(width=W, height=H)

    # Background + header bar
    p.draw_rect(pymupdf.Rect(0, 0, W, H), color=None, fill=(0.985, 0.988, 0.994))
    p.draw_rect(pymupdf.Rect(0, 0, W, 94), color=None, fill=(0.08, 0.13, 0.24))

    p.insert_text(
        (36, 40),
        "KV260-IAS2RF - COMPLETE CONNECTED SYSTEM SCHEMATIC (ALL 12 HIERARCHICAL CIRCUITS + INTER-SHEET BUSES)",
        fontsize=24, fontname="helv", color=(1, 1, 1),
    )
    p.insert_text(
        (36, 70),
        "8-Layer Simultaneous IAS1 (12x LVDS @ 1 Gbps) + 1000BASE-T SGMII  |  Artix-7 XC7A50T Front-End  |  AD9484 500 MSPS & AD9253 125 MSPS ADCs  |  AD9708 & AD9767 DACs",
        fontsize=12.5, fontname="helv", color=(0.78, 0.87, 0.98),
    )

    # Color legend bar below header
    legend_y0, legend_y1 = 94, 130
    p.draw_rect(pymupdf.Rect(0, legend_y0, W, legend_y1), color=None, fill=(0.93, 0.95, 0.98))
    p.draw_line((0, legend_y1), (W, legend_y1), color=(0.75, 0.80, 0.88), width=1.2)

    bus_specs = [
        ("#1565C0", "IAS1 LVDS + SGMII + Kria I2C/SPI/GPIO"),
        ("#6A1B9A", "25 MHz / 125 MHz / 500 MHz LVPECL Clock Tree"),
        ("#D84315", "Converter LVDS / Parallel CMOS Data & SPI"),
        ("#00838F", "RF / IF / Baseband SMA Paths"),
        ("#B7791F", "Power Distribution (12V -> 5V / 3V3 / 2V5 / 1V8 / 1V0 / -3V3)"),
    ]
    lx = 36
    p.insert_text((lx, 117), "INTER-SHEET BUSES:", fontsize=11, fontname="helv", color=(0.15, 0.20, 0.30))
    lx += 165
    for col_hex, label in bus_specs:
        c = hex_to_rgb01(col_hex)
        p.draw_line((lx, 113), (lx + 38, 113), color=c, width=4.0)
        p.insert_text((lx + 46, 117), label, fontsize=10.5, fontname="helv", color=(0.12, 0.16, 0.22))
        lx += 48 + len(label) * 6.0 + 30

    # 3x4 grid layout of all 12 sheets with gutters for trunk buses (KVPWR fills the fourth column of row 3)
    grid = [
        ["IAS_LINK", "CONTROL", "CLOCK", "STATUS"],
        ["ADC_RADAR", "DAC_RADAR", "ROUTING", "RX_VU"],
        ["ADC_SDR", "DAC_SDR", "POWER", "KVPWR"],
    ]
    titles = {
        "IAS_LINK": "1. IAS1 KV260 CONNECTOR + RJ45 1000BASE-T",
        "CONTROL": "2. ARTIX-7 XC7A50T FPGA + RTL8211F PHY + USB + ADAR SPI",
        "CLOCK": "3. SI5351A + SI549 VCXO + ADCLK948 LVPECL CLOCK TREE",
        "ADC_RADAR": "4. RADAR RX: AD9484 (500 MSPS) + AD8352 DIFF DRIVERS",
        "DAC_RADAR": "5. RADAR TX: AD9708 CHIRP DAC + RECONSTRUCTION FILTER",
        "ROUTING": "6. 4x M3SWA-2+ RF SWITCHES + IF SMAs + ESD TVS",
        "ADC_SDR": "7. SDR RX: AD9253 (QUAD 14-BIT 125 MSPS) + AD8352 DRIVERS",
        "DAC_SDR": "8. SDR TX: AD9767 (DUAL 14-BIT 125 MSPS) + FILTERS & BALUNS",
        "POWER": "9. POWER: 12V LM74502 ORing + LMR33630/TPS562201 BUCKS + TPS7A8300 LDOs",
        "RX_VU": "10. VHF/UHF FRONT END (J961): LNA + PRESELECTOR + RFFC5072 + IF CHAIN",
        "STATUS": "11. STATUS: TCA6416A + LEDs + CH340X USB-C DEBUG UART",
        "KVPWR": "12. KV260 POWER FEED: J1004 + TPS26631 eFUSE (U1010, 3.0 A) + L1004 CMC",
    }

    margin_x, margin_top, margin_bot = 34, 152, 26
    gap_x, gap_y = 66, 56
    cell_w = (W - 2 * margin_x - 3 * gap_x) / 4.0
    cell_h = (H - margin_top - margin_bot - 2 * gap_y) / 3.0
    header_h = 24

    boxes = {}
    for r, row in enumerate(grid):
        for c, sname in enumerate(row):
            if sname is None:
                continue
            x0 = margin_x + c * (cell_w + gap_x)
            y0 = margin_top + r * (cell_h + gap_y)
            x1 = x0 + cell_w
            y1 = y0 + cell_h
            boxes[sname] = pymupdf.Rect(x0, y0, x1, y1)

            # Card shadow/border + title strip
            p.draw_rect(pymupdf.Rect(x0, y0, x1, y1), color=(0.25, 0.35, 0.52), fill=(1, 1, 1), width=1.6)
            p.draw_rect(pymupdf.Rect(x0, y0, x1, y0 + header_h), color=None, fill=(0.14, 0.22, 0.38))
            p.insert_text((x0 + 10, y0 + 16), titles[sname], fontsize=10.5, fontname="helv", color=(1, 1, 1))

            # Embed exact vector schematic inside body area maintaining aspect ratio
            body = pymupdf.Rect(x0 + 4, y0 + header_h + 4, x1 - 4, y1 - 4)
            src_idx = page_map[sname]
            src_rect = raw_doc[src_idx].rect
            scale = min(body.width / src_rect.width, body.height / src_rect.height)
            dw, dh = src_rect.width * scale, src_rect.height * scale
            dx = body.x0 + (body.width - dw) / 2.0
            dy = body.y0 + (body.height - dh) / 2.0
            p.show_pdf_page(pymupdf.Rect(dx, dy, dx + dw, dy + dh), raw_doc, src_idx)

    # Draw crisp color-coded inter-sheet trunks in the gutters
    def draw_bus(pts, col_hex, width=4.0, label=None, label_pos=None):
        c = hex_to_rgb01(col_hex)
        for a, b in zip(pts, pts[1:]):
            p.draw_line(a, b, color=c, width=width)
        # Arrowhead at end
        ex, ey = pts[-1]
        px, py = pts[-2]
        vx, vy = ex - px, ey - py
        ln = max((vx * vx + vy * vy) ** 0.5, 1e-6)
        ux, uy = vx / ln, vy / ln
        nx, ny = -uy, ux
        p.draw_polyline(
            [(ex - ux * 11 + nx * 5.5, ey - uy * 11 + ny * 5.5),
             (ex, ey),
             (ex - ux * 11 - nx * 5.5, ey - uy * 11 - ny * 5.5)],
            color=c, fill=c, width=1.5, closePath=True,
        )
        # Junction dot at start
        p.draw_circle(pts[0], 4.5, color=c, fill=c)
        if label and label_pos:
            lx0, ly0 = label_pos
            tw = len(label) * 5.1 + 10
            p.draw_rect(pymupdf.Rect(lx0 - 4, ly0 - 11, lx0 + tw, ly0 + 4), color=c, fill=(1, 1, 1), width=0.9)
            p.insert_text((lx0, ly0), label, fontsize=8.5, fontname="helv", color=c)

    def mid_r(name, frac=0.5):
        r = boxes[name]
        return (r.x1, r.y0 + r.height * frac)

    def mid_l(name, frac=0.5):
        r = boxes[name]
        return (r.x0, r.y0 + r.height * frac)

    def mid_b(name, frac=0.5):
        r = boxes[name]
        return (r.x0 + r.width * frac, r.y1)

    def mid_t(name, frac=0.5):
        r = boxes[name]
        return (r.x0 + r.width * frac, r.y0)

    gx01 = (boxes["IAS_LINK"].x1 + boxes["CONTROL"].x0) / 2.0
    gx12 = (boxes["CONTROL"].x1 + boxes["CLOCK"].x0) / 2.0
    gy01 = (boxes["IAS_LINK"].y1 + boxes["ADC_RADAR"].y0) / 2.0
    gy12 = (boxes["ADC_RADAR"].y1 + boxes["ADC_SDR"].y0) / 2.0

    # 1. IAS_LINK <-> CONTROL (LVDS + SGMII + SPI/I2C)
    draw_bus([mid_r("IAS_LINK", 0.35), mid_l("CONTROL", 0.35)], "#1565C0", 4.5, "12x IAS LVDS + SGMII", (gx01 - 28, mid_r("IAS_LINK", 0.35)[1] - 10))
    draw_bus([mid_r("IAS_LINK", 0.62), mid_l("CONTROL", 0.62)], "#1565C0", 3.5, "I2C / SPI / GPIO / PPS", (gx01 - 28, mid_r("IAS_LINK", 0.62)[1] - 10))

    # 2. CLOCK -> CONTROL, ADC_RADAR, DAC_RADAR, ADC_SDR, DAC_SDR
    clk_x, clk_y = mid_l("CLOCK", 0.45)
    draw_bus([(clk_x, clk_y), mid_r("CONTROL", 0.45)], "#6A1B9A", 4.0, "25M / 125M / 200M CLK", (gx12 - 28, clk_y - 10))
    # Vertical clock spine down right gutter gx12 - 12
    ck_spine_x = gx12 - 14
    ck_bot = mid_b("CLOCK", 0.35)
    draw_bus([ck_bot, (ck_bot[0], gy01 - 10), (ck_spine_x, gy01 - 10), (ck_spine_x, gy12 + 12), (boxes["DAC_SDR"].x1 + 12, gy12 + 12), mid_r("DAC_SDR", 0.25)], "#6A1B9A", 3.5)
    draw_bus([(ck_spine_x, gy01 - 10), mid_r("DAC_RADAR", 0.22)], "#6A1B9A", 3.5, "500M / 125M LVPECL CLK", (ck_spine_x + 8, gy01 - 24))
    draw_bus([(ck_spine_x, gy01 - 10), (gx01 + 14, gy01 - 10), mid_t("ADC_RADAR", 0.80)], "#6A1B9A", 3.2)
    draw_bus([(ck_spine_x, gy12 + 12), (gx01 + 14, gy12 + 12), mid_t("ADC_SDR", 0.80)], "#6A1B9A", 3.2)

    # 3. CONTROL <-> Converters (LVDS / Parallel CMOS + SPI)
    ctrl_b1 = mid_b("CONTROL", 0.25)
    draw_bus([ctrl_b1, (ctrl_b1[0], gy01 + 8), (mid_t("ADC_RADAR", 0.45)[0], gy01 + 8), mid_t("ADC_RADAR", 0.45)], "#D84315", 4.0, "RADAR ADC LVDS + SPI", (gx01 - 50, gy01 + 16))
    ctrl_b2 = mid_b("CONTROL", 0.50)
    draw_bus([ctrl_b2, mid_t("DAC_RADAR", 0.50)], "#D84315", 4.0, "RADAR DAC 8b CMOS", (ctrl_b2[0] + 6, gy01 - 2))
    # Spine down gx01 + 8 to SDR row
    sdr_spine_x = gx01 - 12
    draw_bus([mid_b("CONTROL", 0.12), (mid_b("CONTROL", 0.12)[0], gy01 + 18), (sdr_spine_x, gy01 + 18), (sdr_spine_x, gy12 - 12), mid_t("ADC_SDR", 0.42)], "#D84315", 3.5, "SDR LVDS/CMOS + ADAR SPI", (sdr_spine_x + 8, gy12 - 18))
    draw_bus([(sdr_spine_x, gy12 - 12), (mid_t("DAC_SDR", 0.42)[0], gy12 - 12), mid_t("DAC_SDR", 0.42)], "#D84315", 3.5)

    # 4. RF / IF / Baseband Converters <-> ROUTING
    draw_bus([mid_r("DAC_RADAR", 0.55), mid_l("ROUTING", 0.55)], "#00838F", 4.0, "TX RF + ADAR1000 / GPIO", (gx12 - 30, mid_r("DAC_RADAR", 0.55)[1] - 10))
    draw_bus([mid_r("ADC_RADAR", 0.55), (gx01 + 22, mid_r("ADC_RADAR", 0.55)[1]), (gx01 + 22, gy01 - 18), (boxes["ROUTING"].x0 - 20, gy01 - 18), mid_l("ROUTING", 0.22)], "#00838F", 3.5, "RADAR RX/TX IF SMA", (boxes["DAC_RADAR"].x0 + 20, gy01 - 25))
    draw_bus([mid_r("DAC_SDR", 0.55), (gx12 - 22, mid_r("DAC_SDR", 0.55)[1]), (gx12 - 22, mid_b("ROUTING", 0.25)[1] + 22), mid_b("ROUTING", 0.25)], "#00838F", 3.5, "SDR TX/RX SMA", (gx12 - 32, gy12 + 28))
    draw_bus([mid_b("ADC_SDR", 0.50), (mid_b("ADC_SDR", 0.50)[0], H - 14), (boxes["ROUTING"].x0 - 12, H - 14), (boxes["ROUTING"].x0 - 12, mid_b("ROUTING", 0.12)[1] + 28), mid_b("ROUTING", 0.12)], "#00838F", 3.0)

    # 5. POWER -> All sheets & KVPWR single-entry feed
    gx23 = (boxes["ROUTING"].x1 + boxes["RX_VU"].x0) / 2.0
    draw_bus([mid_t("POWER", 0.50), (mid_t("POWER", 0.50)[0], gy12), (boxes["ADC_SDR"].x0 + 60, gy12)], "#B7791F", 3.8, "12V -> 5V / 3V3 / 2V5 / 1V8 / 1V0 / -3V3 POWER", (boxes["DAC_SDR"].x0 + 20, gy12 - 6))
    draw_bus([mid_l("POWER", 0.50), mid_r("DAC_SDR", 0.50)], "#B7791F", 3.2)
    draw_bus([mid_r("POWER", 0.65), mid_l("KVPWR", 0.65)], "#B7791F", 3.2, "12V_IN / +12V_KV", (boxes["POWER"].x1 + 2, mid_r("POWER", 0.65)[1] + 15))

    # 6. VHF/UHF front end IF into ROUTING's SW2, its +3V0_FE from POWER +3V3_D via gutter, and STATUS control bus
    draw_bus([mid_l("RX_VU", 0.40), mid_r("ROUTING", 0.40)], "#00838F", 4.0, "IF_VU -> SW2",
             (boxes["ROUTING"].x1 + 8, mid_r("ROUTING", 0.40)[1] - 10))
    draw_bus([mid_r("POWER", 0.25), (gx23, mid_r("POWER", 0.25)[1]), (gx23, mid_l("RX_VU", 0.72)[1]), mid_l("RX_VU", 0.72)], "#B7791F", 3.2, "+3V3_D -> +3V0_FE",
             (gx23 - 26, (mid_r("POWER", 0.25)[1] + mid_l("RX_VU", 0.72)[1]) / 2))
    top_y = boxes["CONTROL"].y0 - 14
    draw_bus([mid_t("CONTROL", 0.80), (mid_t("CONTROL", 0.80)[0], top_y), (mid_t("STATUS", 0.30)[0], top_y), mid_t("STATUS", 0.30)],
             "#1565C0", 3.2, "XO I2C (TCA6416A x2) + DEBUG UART", (mid_t("CLOCK", 0.30)[0], top_y - 6))
    st_b = mid_b("STATUS", 0.50)
    draw_bus([st_b, mid_t("RX_VU", 0.50)], "#1565C0", 3.0, "FE control lines", (st_b[0] + 8, (st_b[1] + mid_t("RX_VU", 0.5)[1]) / 2))

    comp.save(out_pdf, garbage=4, deflate=True)
    # Save pure SVG version as well
    svg_txt = p.get_svg_image(text_as_path=False)
    with open(out_svg, "w", encoding="utf-8") as f:
        f.write(svg_txt)
    comp.close()


def export_schematics():
    print("[A] Exporting schematics...")
    raw_pdf = os.path.join(ROOT, "_tmp_raw_sch.pdf")
    run_kicad(["sch", "export", "pdf", "--output", raw_pdf, SCH_FILE])
    run_kicad(["sch", "export", "svg", "--output", HR_SCH_DIR, SCH_FILE])

    raw_doc = pymupdf.open(raw_pdf)
    page_map = identify_sch_pages(raw_doc)
    print("   Schematic page map:", page_map)

    full_pdf = os.path.join(HR_SCH_DIR, "FULL_CIRCUIT.pdf")
    full_svg = os.path.join(HR_SCH_DIR, "FULL_CIRCUIT.svg")
    build_full_circuit_pdf(raw_doc, page_map, full_pdf, full_svg)
    full_doc = pymupdf.open(full_pdf)

    # Build ordered KV260-IAS2RF_schematic.pdf:
    # Page 1: Root Connected Hierarchy
    # Page 2: Full Connected All-Sheets Circuit Composite (A0 Vector)
    # Pages 3..14: 12 individual sub-sheets
    out_doc = pymupdf.open()
    ordered_sheets = [
        "IAS_LINK", "CONTROL", "CLOCK", "ADC_RADAR", "ADC_SDR",
        "DAC_RADAR", "DAC_SDR", "ROUTING", "POWER", "RX_VU", "STATUS", "KVPWR",
    ]
    out_doc.insert_pdf(raw_doc, from_page=page_map["ROOT"], to_page=page_map["ROOT"])
    out_doc.insert_pdf(full_doc, from_page=0, to_page=0)
    for s in ordered_sheets:
        idx = page_map[s]
        out_doc.insert_pdf(raw_doc, from_page=idx, to_page=idx)

    toc = [
        [1, "1. Root - Connected System Architecture", 1],
        [1, "2. Complete Connected Circuit Composite (All 12 Sheets)", 2],
    ]
    for pno, s in enumerate(ordered_sheets, start=3):
        toc.append([1, f"{pno}. {s}", pno])
    out_doc.set_toc(toc)
    out_doc.save(SCH_PDF, garbage=4, deflate=True)

    # Render PNGs (docs/img/sch/ ~2200px wide + docs/img/highres/sch/ 3840-4800px 4K)
    render_page_width(raw_doc[page_map["ROOT"]], os.path.join(SCH_PNG_DIR, "ROOT_HIERARCHY.png"), 2400)
    render_page_width(raw_doc[page_map["ROOT"]], os.path.join(HR_SCH_DIR, "ROOT_HIERARCHY_4k.png"), 3840)

    render_page_width(full_doc[0], os.path.join(SCH_PNG_DIR, "FULL_CIRCUIT.png"), 2800)
    render_page_width(full_doc[0], os.path.join(HR_SCH_DIR, "FULL_CIRCUIT_4k.png"), 4800)

    # ROOT.png: make ROOT.png show the newly wired connected Root schematic (crystal clear in GitHub inline view),
    # AND keep FULL_CIRCUIT.png right beside it (we will verify both visually).
    shutil.copyfile(os.path.join(SCH_PNG_DIR, "ROOT_HIERARCHY.png"), os.path.join(SCH_PNG_DIR, "ROOT.png"))
    shutil.copyfile(os.path.join(HR_SCH_DIR, "ROOT_HIERARCHY_4k.png"), os.path.join(HR_SCH_DIR, "ROOT_4k.png"))

    for s in ordered_sheets:
        pg = raw_doc[page_map[s]]
        render_page_width(pg, os.path.join(SCH_PNG_DIR, f"{s}.png"), 2200)
        render_page_width(pg, os.path.join(HR_SCH_DIR, f"{s}_4k.png"), 3840)

    full_doc.close()
    raw_doc.close()
    out_doc.close()
    os.remove(raw_pdf)
    sz_mb = os.path.getsize(SCH_PDF) / (1024 * 1024)
    print(f"   Saved {SCH_PDF} ({sz_mb:.2f} MB, 14 vector pages)")


# ---------------------------------------------------------------------------
# Part B: 10-Page 100% Vector PCB Layout PDF + Layer SVGs/PNGs
# ---------------------------------------------------------------------------

def strip_copper_zones_from_pcb(pcb_text: str, target_layers: set[str] | None = None) -> str:
    """
    Remove filled copper (zone ...) blocks (except rule-area/keepout zones without nets)
    so GND and Power plane copper pours disappear while tracks, vias, and pads remain intact.
    """
    out = []
    i = 0
    n = len(pcb_text)
    while i < n:
        pos = pcb_text.find("\n\t(zone", i)
        if pos == -1:
            pos = pcb_text.find("\n(zone", i)
        if pos == -1:
            out.append(pcb_text[i:])
            break
        # Append everything before the zone block
        out.append(pcb_text[i:pos])
        # Find balanced end of this (zone ...)
        start = pcb_text.find("(", pos)
        depth = 0
        j = start
        in_str = False
        esc = False
        while j < n:
            ch = pcb_text[j]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        j += 1
                        break
            j += 1
        block = pcb_text[start:j]
        is_keepout = "(keepout" in block
        keep = is_keepout
        if not is_keepout and target_layers is not None:
            m = re.search(r'\(layer\s+"([^"]+)"\)', block)
            if m and m.group(1) not in target_layers:
                keep = True
        if keep:
            out.append(pcb_text[pos:j])
        i = j
    return "".join(out)


def find_layers_with_segments(pcb_text: str) -> list[str]:
    # A segment's (start ...) and (end ...) come before its (layer ...), so match up to the layer
    # without crossing into the next top-level item (segments and arcs are one block each).
    found = set(re.findall(r'\((?:segment|arc)\b(?:(?!\n\t\().)*?\(layer\s+"([^"]+)"\)', pcb_text,
                           flags=re.DOTALL))
    order = ["F.Cu", "In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu", "In5.Cu", "In6.Cu", "B.Cu"]
    return [ly for ly in order if ly in found]


def recolor_kicad_layer_pdf(pdf_path: str, rgb01: tuple[float, float, float], alpha: float, out_path: str):
    """
    Take a single-layer borderless KiCad vector PDF and cleanly recolor all copper strokes/fills
    to rgb01 (preserving white 1 1 1 drill holes) + set Multiply blend mode & opacity alpha.
    100% vector output preserved.
    """
    doc = pymupdf.open(pdf_path)
    page = doc[0]
    r_val, g_val, b_val = rgb01
    new_rgb = f"{r_val:.4f} {g_val:.4f} {b_val:.4f}"

    # Add ExtGState GS_TR for Multiply + translucency
    gs_xref = doc.get_new_xref()
    doc.update_object(
        gs_xref,
        f"<< /Type /ExtGState /BM /Multiply /ca {alpha:.2f} /CA {alpha:.2f} >>",
    )
    page_xref = page.xref
    res_obj = doc.xref_get_key(page_xref, "Resources")
    # Ensure /ExtGState dict exists in page resources
    if res_obj[0] == "dict" or res_obj[0] == "xref":
        doc.xref_set_key(page_xref, "Resources/ExtGState/GS_TR", f"{gs_xref} 0 R")

    c_xref = page.get_contents()[0]
    stream = doc.xref_stream(c_xref).decode("latin1")

    def repl_rg(m):
        vals = [float(m.group(1)), float(m.group(2)), float(m.group(3))]
        op = m.group(4)
        # Keep white (1 1 1) untouched so drill knockouts disappear under Multiply
        if all(v > 0.96 for v in vals):
            return m.group(0)
        return f"{new_rgb} {op}"

    # Replace RGB fill/stroke operators in KiCad stream
    stream_recolored = re.sub(
        r"([0-9.]+)\s+([0-9.]+)\s+([0-9.]+)\s+(rg|RG)\b",
        repl_rg,
        stream,
    )
    # Apply ExtGState after the opening CTM setup (prepend /GS_TR gs)
    stream_recolored = "/GS_TR gs\n" + stream_recolored
    doc.update_stream(c_xref, stream_recolored.encode("latin1"))
    doc.save(out_path, garbage=4, deflate=True)
    doc.close()


def add_layout_banner(page, page_idx, total_pages, title, subtitle):
    W = page.rect.width
    bar_h = 34
    page.draw_rect(pymupdf.Rect(14, 10, W - 14, 10 + bar_h), color=(0.15, 0.25, 0.42), fill=(0.08, 0.13, 0.24), width=1.0)
    page.insert_text((26, 31), f"Page {page_idx}/{total_pages}  |  {title}", fontsize=13.5, fontname="helv", color=(1, 1, 1))
    page.insert_text((W - 26 - len(subtitle) * 5.2, 30), subtitle, fontsize=10, fontname="helv", color=(0.80, 0.89, 0.98))


def export_cover_outline():
    """Line drawing of the board for the documentation's cover: Edge.Cuts + F.Courtyard, black and white, cropped
    to the drawing. Written to docs/img/highres/layout/cover_outline.pdf (vector)."""
    raw = os.path.join(HR_LAY_DIR, "_cover_raw.pdf")
    run_kicad(["pcb", "export", "pdf", "--black-and-white", "--mode-single", "--scale", "0",
               "--layers", "Edge.Cuts,F.Courtyard", "-o", raw, PCB_FILE])
    src = pymupdf.open(raw)
    bbox = pymupdf.Rect()
    for d in src[0].get_drawings():
        bbox |= d["rect"]
    out = pymupdf.open()
    pg = out.new_page(width=bbox.width, height=bbox.height)
    pg.show_pdf_page(pg.rect, src, 0, clip=bbox)
    out.save(os.path.join(HR_LAY_DIR, "cover_outline.pdf"), garbage=4, deflate=True)
    out.close()
    src.close()
    os.remove(raw)


def export_layout():
    print("[B] Exporting 10-page 100% vector layout PDF + layer SVGs/PNGs...")
    tmp_dir = os.path.join(ROOT, "_work", "_tmp_layout")
    os.makedirs(tmp_dir, exist_ok=True)

    # Layer roles from the board's stackup (JLC08161H-2116C) and the nets actually routed on each layer.
    layers_8 = [
        ("F.Cu,Edge.Cuts", "layer_01_L1_F_Cu", "L1 SIG — F.Cu (RF microstrip to the SMAs, BGA fan-out, LVDS pairs)", "JLC08161H-2116C | outer 1 oz | 0.119 mm to L2 GND"),
        ("In1.Cu,Edge.Cuts", "layer_02_L2_In1_GND", "L2 GND — In1.Cu (solid reference for L1 and L3)", "0.5 oz inner Cu"),
        ("In2.Cu,Edge.Cuts", "layer_03_L3_In2_SIG", "L3 SIG — In2.Cu (DAC buses, radar ADC LVDS, SPI and switch control, supply fingers)", "0.5 oz | 0.13 mm to L2 GND, 0.37 mm to L4"),
        ("In3.Cu,Edge.Cuts", "layer_04_L4_In3_PWR", "L4 PWR — In3.Cu (split planes: +3V3_D, +1V, +1V8_D)", "0.5 oz inner Cu"),
        ("In4.Cu,Edge.Cuts", "layer_05_L5_In4_GND", "L5 GND — In4.Cu (solid reference for L6)", "0.5 oz inner Cu"),
        ("In5.Cu,Edge.Cuts", "layer_06_L6_In5_SIG", "L6 SIG — In5.Cu (ADC LVDS and clocks, LINK_RX_CLK, SGMII TX, flash, I2C)", "0.5 oz | 0.13 mm to L7 GND, 0.37 mm to L5 GND"),
        ("In6.Cu,Edge.Cuts", "layer_07_L7_In6_GND", "L7 GND — In6.Cu (solid reference for L6 and L8)", "0.5 oz inner Cu"),
        ("B.Cu,Edge.Cuts", "layer_08_L8_B_Cu", "L8 SIG — B.Cu (BGA decoupling, fan-out, LVDS pairs)", "outer 1 oz | 0.119 mm to L7 GND | 1.6 mm board"),
    ]

    page_pdfs = []
    # Pages 1..8
    for idx, (lay_str, slug, title, sub) in enumerate(layers_8, start=1):
        pdf_i = os.path.join(tmp_dir, f"{slug}.pdf")
        svg_i = os.path.join(HR_LAY_DIR, f"{slug}.svg")
        run_kicad([
            "pcb", "export", "pdf", "--check-zones", "--include-border-title",
            "--mode-single", "--scale", "0", "--layers", lay_str, "-o", pdf_i, PCB_FILE,
        ])
        run_kicad([
            "pcb", "export", "svg", "--check-zones", "--mode-single",
            "--page-size-mode", "2", "--fit-page-to-board", "--layers", lay_str, "-o", svg_i, PCB_FILE,
        ])
        # Stamp banner header
        d = pymupdf.open(pdf_i)
        add_layout_banner(d[0], idx, 10, title, sub)
        stamped = os.path.join(tmp_dir, f"{slug}_stamped.pdf")
        d.save(stamped, garbage=4, deflate=True)
        d.close()
        page_pdfs.append((stamped, title, slug))

    # Page 9: All 8 Copper Layers Combined
    all_layers_str = "F.Cu,In1.Cu,In2.Cu,In3.Cu,In4.Cu,In5.Cu,In6.Cu,B.Cu,Edge.Cuts"
    p9_raw = os.path.join(tmp_dir, "layer_09_all_copper.pdf")
    p9_svg = os.path.join(HR_LAY_DIR, "layer_09_all_8_layers.svg")
    run_kicad([
        "pcb", "export", "pdf", "--check-zones", "--include-border-title",
        "--mode-single", "--scale", "0", "--layers", all_layers_str, "-o", p9_raw, PCB_FILE,
    ])
    run_kicad([
        "pcb", "export", "svg", "--check-zones", "--mode-single",
        "--page-size-mode", "2", "--fit-page-to-board", "--layers", all_layers_str, "-o", p9_svg, PCB_FILE,
    ])
    d9 = pymupdf.open(p9_raw)
    add_layout_banner(d9[0], 9, 10, "All 8 Copper Layers Combined (L1–L8 Stacked + Board Outline)", "Complete 8-Layer Composite | Includes GND & Power Planes")
    p9_stamped = os.path.join(tmp_dir, "layer_09_stamped.pdf")
    d9.save(p9_stamped, garbage=4, deflate=True)
    d9.close()
    page_pdfs.append((p9_stamped, "All 8 Copper Layers Combined (L1–L8)", "layer_09_all_8_layers"))

    # Page 10: Transparent Signal Tracks View (GND L2/L5/L7 & Power L4 Planes Removed)
    pcb_txt = open(PCB_FILE, encoding="utf-8").read()
    seg_layers = find_layers_with_segments(pcb_txt)
    print("   Copper layers with routed tracks:", seg_layers)
    stripped_txt = strip_copper_zones_from_pcb(pcb_txt, target_layers=None)
    no_planes_pcb = os.path.join(tmp_dir, "CSI2-KRIA-KV260_Rev01.kicad_pcb")
    with open(no_planes_pcb, "w", encoding="utf-8") as f:
        f.write(stripped_txt)

    # Export frame/border + Edge.Cuts from original board so title block shows exact filename
    p10_frame = os.path.join(tmp_dir, "p10_frame.pdf")
    run_kicad([
        "pcb", "export", "pdf", "--include-border-title",
        "--mode-single", "--scale", "0", "--layers", "Edge.Cuts", "-o", p10_frame, PCB_FILE,
    ])
    d10 = pymupdf.open(p10_frame)
    p10 = d10[0]

    # Distinct high-contrast color palette per track layer (Multiply blend + 0.68 alpha)
    layer_styles = [
        ("F.Cu",   "#E6194B", "L1 F.Cu (top: RF, BGA fan-out)",     0.70),
        ("In1.Cu", "#808080", "L2 In1.Cu (Any Local Traces)",      0.55),
        ("In2.Cu", "#0082C8", "L3 In2.Cu (inner signal)",          0.72),
        ("In3.Cu", "#F58231", "L4 In3.Cu (power tracks)",          0.75),
        ("In4.Cu", "#707070", "L5 In4.Cu (Any Local Traces)",      0.55),
        ("In5.Cu", "#2E9E3E", "L6 In5.Cu (inner signal)",          0.72),
        ("In6.Cu", "#606060", "L7 In6.Cu (Any Local Traces)",      0.55),
        ("B.Cu",   "#8E24AA", "L8 B.Cu (Bottom Fanout & Tracks)",  0.70),
    ]
    used_styles = [(ly, hx, lbl, al) for (ly, hx, lbl, al) in layer_styles if ly in seg_layers or ly in ("F.Cu", "In2.Cu", "In3.Cu", "In5.Cu", "B.Cu")]

    for ly, hx, lbl, al in used_styles:
        raw_l = os.path.join(tmp_dir, f"trk_{ly}.pdf")
        col_l = os.path.join(tmp_dir, f"trk_{ly}_col.pdf")
        run_kicad([
            "pcb", "export", "pdf", "--mode-single", "--scale", "0",
            "--layers", ly, "-o", raw_l, no_planes_pcb,
        ])
        recolor_kicad_layer_pdf(raw_l, hex_to_rgb01(hx), al, col_l)
        ldoc = pymupdf.open(col_l)
        p10.show_pdf_page(p10.rect, ldoc, 0)
        ldoc.close()

    # Re-overlay opaque Edge.Cuts border/title cleanly + add transparent tracks SVG too
    add_layout_banner(
        p10, 10, 10,
        "All Signal Tracks Combined — Transparent Multi-Layer View (GND L2/L5/L7 & Power L4 Planes Removed)",
        "100% Vector Multiply-Blend Overlay | Signal & Power Traces Only",
    )
    # Legend box on left margin of Page 10
    leg_rect = pymupdf.Rect(24, 58, 285, 76 + len(used_styles) * 18 + 10)
    p10.draw_rect(leg_rect, color=(0.25, 0.35, 0.50), fill=(0.98, 0.99, 1.0), width=1.0)
    p10.insert_text((34, 73), "TRANSPARENT TRACK OVERLAY KEY", fontsize=9.5, fontname="helv", color=(0.10, 0.16, 0.28))
    for i, (ly, hx, lbl, _) in enumerate(used_styles):
        yy = 90 + i * 18
        c = hex_to_rgb01(hx)
        p10.draw_rect(pymupdf.Rect(34, yy - 7, 56, yy + 3), color=c, fill=c)
        p10.insert_text((64, yy + 1), lbl, fontsize=8.5, fontname="helv", color=(0.12, 0.14, 0.18))

    p10_stamped = os.path.join(tmp_dir, "layer_10_stamped.pdf")
    d10.save(p10_stamped, garbage=4, deflate=True)

    # Save SVG of Page 10
    svg10_txt = p10.get_svg_image(text_as_path=False)
    with open(os.path.join(HR_LAY_DIR, "layer_10_tracks_transparent.svg"), "w", encoding="utf-8") as f:
        f.write(svg10_txt)
    d10.close()
    page_pdfs.append((p10_stamped, "All Signal Tracks Combined (Transparent — No GND/PWR Planes)", "layer_10_tracks_transparent"))

    # Remove temporary no-planes PCB immediately
    if os.path.exists(no_planes_pcb):
        os.remove(no_planes_pcb)

    # Assemble 10-page vector docs/KV260-IAS2RF_layout.pdf
    final_lay = pymupdf.open()
    toc = []
    for pno, (ppath, title, slug) in enumerate(page_pdfs, start=1):
        d = pymupdf.open(ppath)
        final_lay.insert_pdf(d, from_page=0, to_page=0)
        render_page_width(d[0], os.path.join(HR_LAY_DIR, f"{slug}_4k.png"), 3840)
        d.close()
        toc.append([1, f"{pno}. {title}", pno])

    final_lay.set_toc(toc)
    final_lay.save(LAY_PDF, garbage=4, deflate=True)
    export_cover_outline()

    # Export clean web PNGs in docs/img/ for direct markdown embedding
    web_map = {
        0: "pcb_top.png",
        1: "pcb_in1.png",
        2: "pcb_in2.png",
        7: "pcb_bottom.png",
        8: "pcb_all_layers.png",
        9: "pcb_tracks_transparent.png",
    }
    for pidx, fname in web_map.items():
        render_page_width(final_lay[pidx], os.path.join(IMG_DIR, fname), 2200)

    final_lay.close()
    shutil.rmtree(tmp_dir, ignore_errors=True)
    sz_mb = os.path.getsize(LAY_PDF) / (1024 * 1024)
    print(f"   Saved {LAY_PDF} ({sz_mb:.2f} MB, 10 vector pages)")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--schematics-only", action="store_true")
    ap.add_argument("--layout-only", action="store_true")
    args = ap.parse_args()
    ensure_dirs()
    if not args.layout_only:
        export_schematics()
    if not args.schematics_only:
        export_layout()
    print("DONE: Schematics & 10-page Vector Layout exported.")
