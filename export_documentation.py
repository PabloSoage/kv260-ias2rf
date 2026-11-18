#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Export complete KV260-IAS2RF documentation into a unified offline PDF book.

Combines:
  - Cover page & executive platform summary
  - Auto-paginated Table of Contents with exact page numbers
  - Structured active Markdown specifications (architecture, dual-FPGA gateware,
    schematic sheet specs, 8-layer layout & SI, mechanical/heatsinks/Enclosure v2,
    fabrication & BOM) with compressed high-res figures and rendered flowcharts
  - Dedicated 4K hardware, heatsink placement, and Enclosure v2 visual plates
  - Lossless vector Vivado FPGA silicon floorplans & circuit schematics
  - Lossless vector heatsink mechanical map
  - Lossless vector 11-sheet KiCad schematic PDF (normalized to uniform width)
  - Lossless vector 10-sheet 8-layer PCB layout PDF (L1-L8 + composite + tracks-only)

Requirements:
  pip install pymupdf pillow

Usage:
  python export_documentation.py
  python export_documentation.py --out docs/KV260-IAS2RF_Documentation.pdf
"""
from __future__ import annotations

import argparse
import hashlib
import html
import io
import re
import sys
import tempfile
from pathlib import Path
from typing import Iterable

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz

try:
    from PIL import Image
except ImportError:
    Image = None


REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_OUT = REPO_ROOT / "docs" / "KV260-IAS2RF_Documentation.pdf"

A4_W, A4_H = fitz.paper_size("a4")  # ~595.28 x 841.89 pt
MARGIN_X = 42
MARGIN_TOP = 46
MARGIN_BOT = 42
CONTENT_RECT = fitz.Rect(MARGIN_X, MARGIN_TOP, A4_W - MARGIN_X, A4_H - MARGIN_BOT)
WIN_FONTS_DIR = Path("C:/Windows/Fonts")

PARTS: list[tuple[str, list[tuple[str, str]]]] = [
    (
        "Part I: Board Overview",
        [
            ("Project Overview", "README.md"),
            ("Board Manual: Connectors, LEDs, Switches & Chips", "docs/BOARD_MANUAL.md"),
        ],
    ),
    (
        "Part II: Dual-FPGA Gateware & XSim Verification",
        [
            ("Dual-FPGA Gateware & Vivado Implementation", "docs/FPGA_GATEWARE.md"),
            ("FPGA Gateware Directory & Build Scripts", "fpga/README.md"),
            ("End-to-End Mixed-Signal XSim Verification", "fpga/SYSTEM_SIM.md"),
            ("IAS1 Clause-49 64B/66B Link Protocol & CSR Map", "fpga/link/LINK_PROTOCOL.md"),
            ("End-to-End LVDS & Control Pin Map", "fpga/link/PINMAP.md"),
            ("Dedicated-Pin 1000BASE-T Ethernet Architecture", "fpga/eth/REV06.md"),
            ("Ethernet Load-Balancing & Failover Policies", "fpga/eth/REDUNDANCY.md"),
            ("Host Software & PS Bring-Up", "sw/README.md"),
            ("In-Car HMI & Processing Partition", "docs/HMI.md"),
            ("Possible Integrations: GPS, 77 GHz Radar, Telemetry, LiDAR & PL Fusion", "docs/INTEGRATIONS.md"),
        ],
    ),
    (
        "Part III: Schematic Subsystem Specifications",
        [
            ("IAS1 High-Speed Link Sheet", "docs/IAS_LINK_SPEC.md"),
            ("Clock Tree & LVPECL Distribution (Si549 + ADCLK948)", "docs/CLOCK_SPEC.md"),
            ("Radar ADC Chain (AD9484 + Dual AD8352)", "docs/ADC_RADAR_SPEC.md"),
            ("SDR ADC Chain (AD9253 + AD8352)", "docs/ADC_SDR_SPEC.md"),
            ("Radar Chirp DAC Chain (AD9708)", "docs/DAC_RADAR_SPEC.md"),
            ("SDR Transmit DAC Chain (AD9767)", "docs/DAC_SDR_SPEC.md"),
            ("RF Switch Matrix & SMA Routing (M3SWA2-34DR+)", "docs/ROUTING_SPEC.md"),
            ("Front-End Artix-7 Control & Ethernet PHY", "docs/CONTROL_SPEC.md"),
            ("Power Tree, Sequencing & Protection", "docs/POWER_SPEC.md"),
            ("KiCad Symbol Library Verification", "docs/SYMBOLS.md"),
        ],
    ),
    (
        "Part IV: 8-Layer PCB Layout & Signal/Power Integrity",
        [
            ("8-Layer PCB Layout & Rules (JLC08161H-2116C)", "docs/LAYOUT.md"),
            ("Signal Integrity, openEMS, ngspice & Thermal Maps", "docs/SIGNAL_INTEGRITY.md"),
            ("3-D Component Model Mapping Audit", "docs/3D_MODELS.md"),
        ],
    ),
    (
        "Part V: Mechanical Integration, Heatsinks & Enclosure v2",
        [
            ("Mechanical Base & KV260 Mounting", "docs/MECHANICAL.md"),
            ("Enclosure v2 CAD & 3-D Shock/Vibration FEA", "docs/ENCLOSURE.md"),
            ("Enclosure v2 Thermal CFD & Heatsink Sizing", "docs/ENCLOSURE_V2_THERMAL.md"),
        ],
    ),
    (
        "Part VI: Fabrication & Costing",
        [
            ("JLCPCB Fabrication & Impedance Order Guide", "docs/FABRICATION.md"),
            ("JLCPCB Assembly & Component Quote", "docs/JLCPCB_QUOTE.md"),
            ("High-Resolution & Vector Assets Index", "docs/img/highres/README.md"),
        ],
    ),
]

# Not in the book (it documents the final board only): the vehicle platform, and the planning documents of the
# first revisions. README lines (table rows, bullets) that link to them are dropped from the book's copy.
PDF_EXCLUDED_DOCS = (
    "VEHICLE_PLATFORM.md", "SHOPPING_LIST.md", "ARCHITECTURE.md", "BLOCKERS_AND_RISKS.md",
    "INTERFACE_SPEC.md", "ROADMAP.md", "FEASIBILITY.md", "POWER_AND_STACKUP.md", "docs/history/",
)


def drop_excluded_lines(md_text: str) -> str:
    out = []
    for line in md_text.splitlines():
        s = line.lstrip()
        if (s.startswith("|") or s.startswith("- ") or s.startswith("* ")) and any(
            f"{x})" in line or f"{x}#" in line or f"({x}" in line or f"/{x}" in line for x in PDF_EXCLUDED_DOCS
        ):
            continue
        out.append(line)
    return "\n".join(out)


SHOWCASE_4K_RENDERS: list[tuple[str, str]] = [
    ("Adapter PCB: 4K Isometric Raytrace", "docs/img/highres/renders/board_iso_4k.png"),
    ("Adapter PCB: 4K Top Copper & Assembly", "docs/img/highres/renders/board_top_4k.png"),
    ("Adapter PCB: 4K Bottom Copper & Assembly", "docs/img/highres/renders/board_bottom_4k.png"),
    ("Heatsink Placement Overview (HS1–HS5 + 50 mm Fan Wireframe)", "docs/img/highres/renders/board_heatsinks_4k.jpg"),
    ("Heatsink Macro Close-Up (4.0 mm Thermal Gap U401/Y401)", "docs/img/highres/renders/board_heatsinks_closeup_4k.jpg"),
    ("Enclosure v2: Closed Assembly with Filtered Intake & TPU Bumpers", "docs/img/highres/renders/case_v2_closed_4k.jpg"),
    ("Enclosure v2: Open Tray with Kria K26 + RF Adapter Seated", "docs/img/highres/renders/case_v2_open_4k.jpg"),
    ("Enclosure v2: Longitudinal Cross-Section (Fan Duct, SMAs & K26 Cooler)", "docs/img/highres/renders/case_v2_section_4k.jpg"),
]

VECTOR_FPGA_PDFS: list[tuple[str, str]] = [
    ("Artix-7 XC7A50T Silicon Die Floorplan", "docs/img/highres/fpga/artix7_silicon_floorplan.pdf"),
    ("Artix-7 Post-Route Vivado Circuit Schematic", "docs/img/highres/fpga/artix7_vivado_schematic.pdf"),
    ("Kria K26 XCK26 Silicon Die Floorplan", "docs/img/highres/fpga/kria_k26_silicon_floorplan.pdf"),
    ("Kria K26 PS + PL Vivado Block Design Schematic", "docs/img/highres/fpga/kria_k26_vivado_bd_schematic.pdf"),
    ("Dual-FPGA AERIS-10 Radar & Wideband SDR Signal Chain", "docs/img/highres/fpga/dsp_radar_sdr_pipeline_schematic.pdf"),
]


def _font_css() -> tuple[str, bool]:
    """Return TrueType @font-face declarations when Windows Unicode fonts exist."""
    req = ["arial.ttf", "arialbd.ttf", "ariali.ttf", "arialbi.ttf", "consola.ttf", "consolab.ttf"]
    if WIN_FONTS_DIR.is_dir() and all((WIN_FONTS_DIR / f).is_file() for f in req):
        faces = """
@font-face { font-family: BodyFont; src: url(arial.ttf); font-weight: normal; font-style: normal; }
@font-face { font-family: BodyFont; src: url(arialbd.ttf); font-weight: bold; font-style: normal; }
@font-face { font-family: BodyFont; src: url(ariali.ttf); font-weight: normal; font-style: italic; }
@font-face { font-family: BodyFont; src: url(arialbi.ttf); font-weight: bold; font-style: italic; }
@font-face { font-family: MonoFont; src: url(consola.ttf); font-weight: normal; font-style: normal; }
@font-face { font-family: MonoFont; src: url(consolab.ttf); font-weight: bold; font-style: normal; }
"""
        return faces, True
    return "", False


def build_base_css(has_ttf: bool) -> str:
    body_fam = "BodyFont, Helvetica, Arial, sans-serif" if has_ttf else "Helvetica, Arial, sans-serif"
    mono_fam = "MonoFont, Consolas, Courier, monospace" if has_ttf else "Courier, monospace"
    font_faces, _ = _font_css()
    return f"""
{font_faces}
@page {{ size: a4 portrait; }}
body {{
    font-family: {body_fam};
    font-size: 9pt;
    line-height: 1.42;
    color: #1c2430;
}}
h1 {{
    font-size: 16pt;
    color: #0b2e4f;
    border-bottom: 1.5pt solid #0b2e4f;
    padding-bottom: 3pt;
    margin-top: 2pt;
    margin-bottom: 8pt;
    page-break-after: avoid;
}}
h2 {{
    font-size: 12pt;
    color: #134a7a;
    border-bottom: 0.6pt solid #cbd5e1;
    padding-bottom: 2pt;
    margin-top: 12pt;
    margin-bottom: 5pt;
    page-break-after: avoid;
}}
h3 {{
    font-size: 10.2pt;
    color: #1e3a5f;
    margin-top: 9pt;
    margin-bottom: 4pt;
    page-break-after: avoid;
}}
h4, h5, h6 {{
    font-size: 9.4pt;
    color: #334155;
    margin-top: 7pt;
    margin-bottom: 3pt;
    page-break-after: avoid;
}}
p {{ margin: 4pt 0 5pt 0; }}
ul, ol {{ margin: 3pt 0 6pt 14pt; padding-left: 6pt; }}
li {{ margin-bottom: 2pt; }}
blockquote {{
    margin: 6pt 0;
    padding: 5pt 8pt;
    background-color: #f1f5f9;
    border-left: 3pt solid #2563eb;
    color: #1e293b;
}}
blockquote h1, blockquote h2, blockquote h3, blockquote h4 {{
    margin-top: 2pt;
    margin-bottom: 3pt;
    border-bottom: none;
}}
code {{
    font-family: {mono_fam};
    font-size: 7.8pt;
    background-color: #f1f5f9;
    padding: 0.5pt 2pt;
    color: #0f172a;
}}
pre {{
    font-family: {mono_fam};
    font-size: 6.2pt;
    line-height: 1.24;
    background-color: #f8fafc;
    border: 0.5pt solid #cbd5e1;
    padding: 5pt 6pt;
    white-space: pre-wrap;
    word-wrap: break-word;
    margin: 5pt 0 7pt 0;
}}
table {{
    width: 100%;
    border-collapse: separate;
    border-spacing: 0;
    border-top: 0.5pt solid #cbd5e1;
    border-left: 0.5pt solid #cbd5e1;
    margin: 6pt 0 9pt 0;
    line-height: 1.26;
}}
table.tbl-std {{ font-size: 7.4pt; }}
table.tbl-med {{ font-size: 6.3pt; }}
table.tbl-wide {{ font-size: 5.4pt; }}
th {{
    background-color: #0f3a60;
    color: #ffffff;
    font-weight: bold;
    text-align: left;
    border-right: 0.5pt solid #94a3b8;
    border-bottom: 0.5pt solid #94a3b8;
    word-wrap: break-word;
}}
th code {{
    background-color: #0f3a60;
    color: #ffffff;
    padding: 0;
}}
td {{
    border-right: 0.5pt solid #cbd5e1;
    border-bottom: 0.5pt solid #cbd5e1;
    vertical-align: top;
    word-wrap: break-word;
}}
table.tbl-std th {{ padding: 3.5pt 4pt; }}
table.tbl-std td {{ padding: 3pt 4pt; }}
table.tbl-med th {{ padding: 2.5pt 3pt; }}
table.tbl-med td {{ padding: 2.2pt 3pt; }}
table.tbl-wide th {{ padding: 2pt 2.4pt; }}
table.tbl-wide td {{ padding: 1.8pt 2.4pt; }}
tr.alt td {{ background-color: #f8fafc; }}
table.cont {{ margin-top: 0; }}
tr {{ page-break-inside: avoid; }}
hr {{ border: none; border-top: 0.6pt solid #cbd5e1; margin: 9pt 0; }}
figure {{
    margin: 6pt 0 8pt 0;
    text-align: center;
    page-break-inside: avoid;
}}
img {{
    display: block;
    margin: 0 auto;
}}
figcaption {{
    font-size: 7.6pt;
    color: #475569;
    margin-top: 2.5pt;
    font-style: italic;
}}
a {{ color: #1d4ed8; text-decoration: none; }}
.doc-path {{
    font-family: {mono_fam};
    font-size: 7.5pt;
    color: #64748b;
    margin-bottom: 6pt;
}}
.toc-part td {{
    background-color: #eaf0f7;
    color: #0b2e4f;
    font-weight: bold;
    font-size: 8.2pt;
    padding: 4pt 6pt;
}}
.toc-item td {{
    font-size: 7.8pt;
    padding: 2.5pt 6pt;
}}
.toc-sub td {{
    font-size: 7.2pt;
    color: #475569;
    padding: 1.8pt 6pt 1.8pt 16pt;
}}
"""


_SYMBOL_MAP = {
    "⚠️": "[WARN]",
    "⚠": "[WARN]",
    "✅": "[PASS]",
    "❌": "[NO]",
    "⬜": "[TODO]",
    "⛔": "[BLOCKED]",
    "⚑": "[!]",
    "☑": "[x]",
    "☐": "[ ]",
    "✓": "[OK]",
    "⬅": "<-",
    "\ufe0f": "",
}


def normalize_symbols(text: str) -> str:
    """Replace unsupported color emojis with crisp ASCII status tags."""
    for src, dst in _SYMBOL_MAP.items():
        if src in text:
            text = text.replace(src, dst)
    return text


class AssetPacker:
    """Normalizes and compresses referenced raster/SVG/diagram images and tracks pixel dimensions."""

    def __init__(self, tmp_dir: Path, max_w: int = 2000, jpeg_quality: int = 86):
        self.tmp_dir = tmp_dir
        self.max_w = max_w
        self.jpeg_quality = jpeg_quality
        self._cache: dict[str, tuple[str, int, int] | None] = {}

    def prepare(self, img_path: Path) -> tuple[str, int, int] | None:
        resolved = img_path.resolve()
        cache_key = f"file:{resolved}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        if not resolved.is_file():
            self._cache[cache_key] = None
            return None

        key = hashlib.sha1(str(resolved).encode("utf-8")).hexdigest()[:14]
        out_name = f"img_{key}.jpg"
        out_path = self.tmp_dir / out_name

        try:
            suffix = resolved.suffix.lower()
            if suffix == ".svg":
                svg_doc = fitz.open(str(resolved))
                page = svg_doc[0]
                scale = min(3.0, max(1.0, self.max_w / max(page.rect.width, 1.0)))
                pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                svg_doc.close()
                px_w, px_h = pix.width, pix.height
                if Image is not None:
                    im = Image.frombytes("RGB", [px_w, px_h], pix.samples)
                    im.save(out_path, format="JPEG", quality=self.jpeg_quality, optimize=True)
                else:
                    pix.save(str(out_path))
            elif Image is not None:
                with Image.open(resolved) as im:
                    if im.mode in ("RGBA", "LA", "P"):
                        bg = Image.new("RGB", im.size, (255, 255, 255))
                        rgba = im.convert("RGBA")
                        bg.paste(rgba, mask=rgba.split()[-1])
                        rgb = bg
                    else:
                        rgb = im.convert("RGB")
                    if rgb.width > self.max_w:
                        new_h = max(1, int(round(rgb.height * (self.max_w / rgb.width))))
                        rgb = rgb.resize((self.max_w, new_h), Image.Resampling.LANCZOS)
                    px_w, px_h = rgb.size
                    rgb.save(out_path, format="JPEG", quality=self.jpeg_quality, optimize=True)
            else:
                pix = fitz.Pixmap(str(resolved))
                if pix.alpha:
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                px_w, px_h = pix.width, pix.height
                pix.save(str(out_path))
            res = (out_name, px_w, px_h)
            self._cache[cache_key] = res
            return res
        except Exception as exc:
            print(f"[warn] skipping image {resolved}: {exc}", file=sys.stderr)
            self._cache[cache_key] = None
            return None

    def register_pixmap(self, pix: fitz.Pixmap, tag: str) -> tuple[str, int, int] | None:
        cache_key = f"pix:{tag}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        key = hashlib.sha1(tag.encode("utf-8")).hexdigest()[:14]
        out_name = f"img_{key}.jpg"
        out_path = self.tmp_dir / out_name
        try:
            if pix.alpha:
                pix = fitz.Pixmap(fitz.csRGB, pix)
            px_w, px_h = pix.width, pix.height
            if Image is not None:
                im = Image.frombytes("RGB", [px_w, px_h], pix.samples)
                im.save(out_path, format="JPEG", quality=92, optimize=True)
            else:
                pix.save(str(out_path))
            res = (out_name, px_w, px_h)
            self._cache[cache_key] = res
            return res
        except Exception as exc:
            print(f"[warn] skipping diagram {tag}: {exc}", file=sys.stderr)
            self._cache[cache_key] = None
            return None


def _draw_arrow_line(
    page: fitz.Page,
    pts: list[tuple[float, float]],
    color: tuple[float, float, float],
    width: float = 1.6,
    bidir: bool = False,
    end_arrow: bool = True,
) -> None:
    """Draw a clean polyline with filled vector arrowheads at ends."""
    fpts = [fitz.Point(x, y) for x, y in pts]
    for a, b in zip(fpts[:-1], fpts[1:]):
        page.draw_line(a, b, color=color, width=width)

    def _head(p_from: fitz.Point, p_tip: fitz.Point) -> None:
        dx, dy = p_tip.x - p_from.x, p_tip.y - p_from.y
        ln = (dx * dx + dy * dy) ** 0.5
        if ln < 1e-3:
            return
        ux, uy = dx / ln, dy / ln
        px, py = -uy, ux
        sz, hw = 7.0, 3.2
        base = fitz.Point(p_tip.x - ux * sz, p_tip.y - uy * sz)
        p1 = fitz.Point(base.x + px * hw, base.y + py * hw)
        p2 = fitz.Point(base.x - px * hw, base.y - py * hw)
        sh = page.new_shape()
        sh.draw_polyline([p_tip, p1, p2, p_tip])
        sh.finish(color=color, fill=color, width=0.5, closePath=True)
        sh.commit()

    if end_arrow and len(fpts) >= 2:
        _head(fpts[-2], fpts[-1])
    if bidir and len(fpts) >= 2:
        _head(fpts[1], fpts[0])


def _draw_node_box(
    page: fitz.Page,
    rect: fitz.Rect,
    title: str,
    subtitle: str,
    fill: tuple[float, float, float],
    border: tuple[float, float, float],
    text_col: tuple[float, float, float],
) -> None:
    sh = page.new_shape()
    sh.draw_rect(rect, radius=0.06)
    sh.finish(color=border, fill=fill, width=1.4)
    sh.commit()
    mid_y = (rect.y0 + rect.y1) * 0.5
    if subtitle:
        page.insert_textbox(
            fitz.Rect(rect.x0 + 4, rect.y0 + 7, rect.x1 - 4, mid_y + 2),
            title,
            fontname="hebo",
            fontsize=10.2,
            color=text_col,
            align=fitz.TEXT_ALIGN_CENTER,
        )
        page.insert_textbox(
            fitz.Rect(rect.x0 + 4, mid_y, rect.x1 - 4, rect.y1 - 4),
            subtitle,
            fontname="helv",
            fontsize=8.3,
            color=text_col,
            align=fitz.TEXT_ALIGN_CENTER,
        )
    else:
        page.insert_textbox(
            fitz.Rect(rect.x0 + 4, mid_y - 8, rect.x1 - 4, mid_y + 10),
            title,
            fontname="hebo",
            fontsize=10.0,
            color=text_col,
            align=fitz.TEXT_ALIGN_CENTER,
        )


def _draw_edge_badge(page: fitz.Page, cx: float, cy: float, label: str, w: float = 104, h: float = 24) -> None:
    r = fitz.Rect(cx - w * 0.5, cy - h * 0.5, cx + w * 0.5, cy + h * 0.5)
    sh = page.new_shape()
    sh.draw_rect(r, radius=0.12)
    sh.finish(color=(0.76, 0.82, 0.89), fill=(0.98, 0.99, 1.0), width=0.8)
    sh.commit()
    lines = label.count("\n") + 1
    top_pad = 3 if lines > 1 else 6
    page.insert_textbox(
        fitz.Rect(r.x0 + 2, r.y0 + top_pad, r.x1 - 2, r.y1 - 2),
        label,
        fontname="helv",
        fontsize=7.3,
        color=(0.16, 0.22, 0.30),
        align=fitz.TEXT_ALIGN_CENTER,
    )


def render_mermaid_flowchart(mermaid_src: str, packer: AssetPacker) -> tuple[str, int, int] | None:
    """Render Mermaid flowchart blocks to a crisp vector-rasterized diagram via PyMuPDF."""
    node_labels: dict[str, tuple[str, str]] = {}
    for m in re.finditer(r'\b([A-Za-z0-9_]+)\s*\["([^"]+)"\]', mermaid_src):
        nid = m.group(1)
        parts = re.split(r"<br\s*/?>", m.group(2), flags=re.I)
        t = parts[0].strip()
        sub = " / ".join(p.strip() for p in parts[1:] if p.strip())
        node_labels[nid] = (t, sub)

    doc = fitz.open()
    W, H = 960.0, 380.0
    page = doc.new_page(width=W, height=H)
    page.draw_rect(fitz.Rect(0, 0, W, H), color=(0.82, 0.86, 0.91), fill=(0.985, 0.99, 0.996), width=1.0)

    # Check if this is the README system flowchart
    known_ids = {"KV260", "FPGA", "ADCR", "ADCS", "DACR", "DACS", "CLK", "RF", "AERIS"}
    if known_ids.issubset(node_labels.keys()):
        def lbl(nid: str, ft: str, fs: str) -> tuple[str, str]:
            return node_labels.get(nid, (ft, fs))

        boxes = {
            "KV260": (fitz.Rect(24, 96, 152, 152),  (0.043, 0.180, 0.310), (0.043, 0.180, 0.310), (1.0, 1.0, 1.0), lbl("KV260", "Kria KV260", "(K26 SOM)")),
            "FPGA":  (fitz.Rect(280, 88, 412, 160), (0.082, 0.365, 0.620), (0.043, 0.230, 0.420), (1.0, 1.0, 1.0), lbl("FPGA", "XC7A50T", "front-end FPGA")),
            "CLK":   (fitz.Rect(272, 268, 420, 326), (0.98, 0.94, 0.85),   (0.75, 0.48, 0.08),   (0.28, 0.18, 0.04), lbl("CLK", "Si549 + ADCLK948", "clock")),
            "ADCR":  (fitz.Rect(515, 22, 635, 68),  (0.91, 0.95, 0.99),   (0.16, 0.41, 0.72),   (0.08, 0.19, 0.34), lbl("ADCR", "AD9484", "radar ADC")),
            "ADCS":  (fitz.Rect(515, 84, 635, 130), (0.91, 0.95, 0.99),   (0.16, 0.41, 0.72),   (0.08, 0.19, 0.34), lbl("ADCS", "AD9253", "SDR ADC")),
            "DACR":  (fitz.Rect(515, 146, 635, 192), (0.90, 0.97, 0.94),  (0.06, 0.50, 0.36),   (0.05, 0.25, 0.19), lbl("DACR", "AD9708", "radar DAC")),
            "DACS":  (fitz.Rect(515, 208, 635, 254), (0.90, 0.97, 0.94),  (0.06, 0.50, 0.36),   (0.05, 0.25, 0.19), lbl("DACS", "AD9767", "SDR DAC")),
            "RF":    (fitz.Rect(730, 108, 860, 166), (0.93, 0.92, 0.99),  (0.38, 0.28, 0.76),   (0.18, 0.12, 0.42), lbl("RF", "RF switches", "10 SMAs")),
            "AERIS": (fitz.Rect(730, 270, 922, 328), (0.99, 0.92, 0.92),  (0.72, 0.16, 0.16),   (0.38, 0.08, 0.08), lbl("AERIS", "AERIS-10", "8 × ADAR1000")),
        }

        c_navy = (0.14, 0.26, 0.42)
        c_lvds = (0.12, 0.42, 0.74)
        c_clk = (0.76, 0.48, 0.08)
        c_rf = (0.40, 0.28, 0.72)
        c_ctrl = (0.68, 0.16, 0.18)

        # KV260 <-> FPGA
        _draw_arrow_line(page, [(152, 124), (280, 124)], c_navy, width=2.0, bidir=True)
        _draw_edge_badge(page, 216, 94, "IAS1: 5 LVDS pairs\nPmod: control", w=104, h=26)

        # FPGA <-> ADCs / DACs
        _draw_arrow_line(page, [(412, 104), (450, 104), (450, 45), (515, 45)], c_lvds, width=1.6, bidir=True)
        _draw_arrow_line(page, [(412, 114), (466, 114), (466, 107), (515, 107)], c_lvds, width=1.6, bidir=True)
        _draw_arrow_line(page, [(412, 134), (466, 134), (466, 169), (515, 169)], c_lvds, width=1.6, bidir=False)
        _draw_arrow_line(page, [(412, 144), (450, 144), (450, 231), (515, 231)], c_lvds, width=1.6, bidir=False)
        _draw_edge_badge(page, 466, 76, "LVDS", w=40, h=16)

        # CLK -> FPGA & Converters
        _draw_arrow_line(page, [(346, 268), (346, 160)], c_clk, width=1.4, bidir=False)
        _draw_arrow_line(page, [(420, 297), (488, 297), (488, 55), (515, 55)], c_clk, width=1.3, bidir=False)
        _draw_arrow_line(page, [(488, 117), (515, 117)], c_clk, width=1.3, bidir=False)
        _draw_arrow_line(page, [(488, 179), (515, 179)], c_clk, width=1.3, bidir=False)
        _draw_arrow_line(page, [(488, 241), (515, 241)], c_clk, width=1.3, bidir=False)

        # Converters <-> RF Switches
        _draw_arrow_line(page, [(635, 45), (682, 45), (682, 120), (730, 120)], c_rf, width=1.5, bidir=True)
        _draw_arrow_line(page, [(635, 107), (694, 107), (694, 131), (730, 131)], c_rf, width=1.5, bidir=True)
        _draw_arrow_line(page, [(635, 169), (694, 169), (694, 143), (730, 143)], c_rf, width=1.5, bidir=True)
        _draw_arrow_line(page, [(635, 231), (682, 231), (682, 155), (730, 155)], c_rf, width=1.5, bidir=True)

        # FPGA <-> AERIS (bottom bus below CLK)
        _draw_arrow_line(page, [(310, 160), (310, 212), (242, 212), (242, 352), (826, 352), (826, 328)], c_ctrl, width=1.7, bidir=True)
        _draw_edge_badge(page, 560, 352, "IDC ribbon (8x ADAR1000 SPI / TR control)", w=206, h=18)

        # RF <-> AERIS
        _draw_arrow_line(page, [(795, 166), (795, 270)], c_ctrl, width=1.8, bidir=True)
        _draw_edge_badge(page, 795, 218, "X-Band IF / LO", w=86, h=17)

        for _, (rect, fill, border, tc, (t, sub)) in boxes.items():
            _draw_node_box(page, rect, t, sub, fill, border, tc)
    else:
        # Generic fallback grid for any other Mermaid flowchart
        nodes = list(node_labels.items()) or [("N0", ("Mermaid Diagram", ""))]
        cols = min(4, max(1, len(nodes)))
        box_w, box_h = 175.0, 52.0
        gap_x, gap_y = 45.0, 34.0
        for idx, (_nid, (t, sub)) in enumerate(nodes):
            r_idx, c_idx = divmod(idx, cols)
            x0 = 40.0 + c_idx * (box_w + gap_x)
            y0 = 40.0 + r_idx * (box_h + gap_y)
            rect = fitz.Rect(x0, y0, x0 + box_w, min(H - 20, y0 + box_h))
            _draw_node_box(page, rect, t, sub, (0.91, 0.95, 0.99), (0.16, 0.41, 0.72), (0.08, 0.19, 0.34))

    pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), alpha=False)
    doc.close()
    return packer.register_pixmap(pix, f"mermaid:{mermaid_src}")


def _soft_break_html(html_str: str) -> str:
    """Insert zero-width break hints inside long plain-text tokens of wide table cells."""
    parts = re.split(r"(<[^>]+>|&[A-Za-z0-9#]+;)", html_str)
    out: list[str] = []
    for seg in parts:
        if not seg or seg.startswith("<") or (seg.startswith("&") and seg.endswith(";")):
            out.append(seg)
            continue
        words = seg.split(" ")
        new_words: list[str] = []
        for w in words:
            if len(w) >= 13:
                w = re.sub(r"([_/,])(?=[A-Za-z0-9])", r"\1&#8203;", w)
            new_words.append(w)
        out.append(" ".join(new_words))
    return "".join(out)


def _format_label_markup(text: str) -> str:
    """Escape plain text parts of a link label while keeping @@MDTOK placeholders intact."""
    parts = re.split(r"(@@MDTOK_\d+_END@@)", text)
    out: list[str] = []
    for p in parts:
        if re.fullmatch(r"@@MDTOK_\d+_END@@", p):
            out.append(p)
        else:
            esc = html.escape(p)
            esc = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", esc)
            esc = re.sub(r"\*([^*\n]+)\*", r"<em>\1</em>", esc)
            out.append(esc)
    return "".join(out)


def inline_md(text: str, base_dir: Path, packer: AssetPacker, table_cols: int = 0) -> str:
    """Convert inline Markdown formatting (code, images, links, HTML breaks/sub, bold/italic) to HTML."""
    text = normalize_symbols(text)
    tokens: list[str] = []

    def stash(html_frag: str) -> str:
        idx = len(tokens)
        tokens.append(html_frag)
        return f"@@MDTOK_{idx}_END@@"

    # 1. Inline images ![alt](target)
    def repl_img(m: re.Match[str]) -> str:
        alt_raw = m.group(1).strip()
        alt = html.escape(alt_raw)
        raw_tgt = m.group(2).strip().split()[0]
        if raw_tgt.startswith(("http://", "https://")):
            return stash(f"<span>[{alt}]</span>")
        tgt_path = (base_dir / raw_tgt.split("#", 1)[0]).resolve()
        info = packer.prepare(tgt_path)
        if not info:
            return stash(f"<code>[{alt}: {html.escape(raw_tgt)}]</code>")
        asset, px_w, px_h = info
        if table_cols > 0:
            max_cell_w = max(80.0, (490.0 / table_cols) - 14.0)
            max_cell_h = 185.0
            scale = min(max_cell_w / max(px_w, 1), max_cell_h / max(px_h, 1))
            w_pt = max(1, int(round(px_w * scale)))
            h_pt = max(1, int(round(px_h * scale)))
            cap = f'<div style="font-size:7pt;color:#475569;margin-top:2pt;"><em>{alt}</em></div>' if alt else ""
            return stash(
                f'<div style="text-align:center;margin:2pt 0;">'
                f'<img src="{asset}" width="{w_pt}" height="{h_pt}" alt="{alt}"/>{cap}</div>'
            )
        scale = min(485.0 / max(px_w, 1), 260.0 / max(px_h, 1))
        w_pt = max(1, int(round(px_w * scale)))
        h_pt = max(1, int(round(px_h * scale)))
        cap = f"<figcaption>{alt}</figcaption>" if alt else ""
        return stash(f'<figure><img src="{asset}" width="{w_pt}" height="{h_pt}" alt="{alt}"/>{cap}</figure>')

    text = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", repl_img, text)

    # 2. Inline code ``...`` (GFM double backticks) then single `...`
    text = re.sub(r"``\s*(.+?)\s*``", lambda m: stash(f"<code>{html.escape(m.group(1))}</code>"), text)
    text = re.sub(r"`([^`]+)`", lambda m: stash(f"<code>{html.escape(m.group(1))}</code>"), text)

    # 3. Links [label](url)
    def repl_link(m: re.Match[str]) -> str:
        label_html = _format_label_markup(m.group(1))
        url = m.group(2).strip()
        if url.startswith(("http://", "https://")):
            return stash(f'<a href="{html.escape(url)}">{label_html}</a>')
        return stash(f"<strong>{label_html}</strong>")

    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", repl_link, text)

    # 4. Preserve safe inline HTML tags (<br/>, <sub>...</sub>, <sup>...</sup>)
    text = re.sub(r"<br\s*/?>", lambda _m: stash("<br/>"), text, flags=re.I)
    text = re.sub(
        r"<(sub|sup)>(.*?)</\1>",
        lambda m: stash(f"<{m.group(1).lower()}>{html.escape(m.group(2))}</{m.group(1).lower()}>"),
        text,
        flags=re.I | re.S,
    )

    escaped = html.escape(text)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"\*([^*\n]+)\*", r"<em>\1</em>", escaped)
    escaped = re.sub(r"~~([^~]+)~~", r"<del>\1</del>", escaped)

    # Expand placeholders in reverse order so nested tokens resolve completely
    for _pass in range(4):
        if "@@MDTOK_" not in escaped:
            break
        for idx in range(len(tokens) - 1, -1, -1):
            ph = f"@@MDTOK_{idx}_END@@"
            if ph in escaped:
                escaped = escaped.replace(ph, tokens[idx])

    if table_cols >= 6:
        escaped = _soft_break_html(escaped)

    return escaped


def split_table_row(row: str) -> list[str]:
    s = row.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    return [c.replace("\\|", "|").strip() for c in re.split(r"(?<!\\)\|", s)]


def is_table_sep(line: str) -> bool:
    cells = split_table_row(line)
    if not cells:
        return False
    return all(bool(re.fullmatch(r":?-{2,}:?", c)) for c in cells)


def md_to_html(md_text: str, md_path: Path, packer: AssetPacker) -> str:
    """Convert GitHub-flavored Markdown into clean print HTML for PyMuPDF Story."""
    base_dir = md_path.parent
    brk = breakable if md_path.name in BREAKABLE_DOCS else (lambda h: h)
    lines = md_text.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        # Fenced code / Mermaid block
        if stripped.startswith("```"):
            lang = stripped[3:].strip().lower()
            i += 1
            code_lines: list[str] = []
            while i < n and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            if i < n:
                i += 1
            if lang == "mermaid":
                info = render_mermaid_flowchart("\n".join(code_lines), packer)
                if info:
                    asset, px_w, px_h = info
                    scale = min(485.0 / max(px_w, 1), 240.0 / max(px_h, 1))
                    w_pt = max(1, int(round(px_w * scale)))
                    h_pt = max(1, int(round(px_h * scale)))
                    out.append(
                        f'<figure><img src="{asset}" width="{w_pt}" height="{h_pt}" '
                        f'alt="System Flowchart"/><figcaption>System Architecture &amp; Signal-Chain Flowchart</figcaption></figure>'
                    )
                    continue
            norm_lines = [normalize_symbols(cl) for cl in code_lines]
            max_len = max((len(cl) for cl in norm_lines), default=0)
            fs = 6.5 if max_len <= 85 else (5.5 if max_len <= 105 else (4.7 if max_len <= 125 else 4.1))
            out.append(f'<pre style="font-size:{fs}pt;">{html.escape(chr(10).join(norm_lines))}</pre>')
            continue

        # Horizontal rule
        if re.fullmatch(r"[-*_]{3,}", stripped):
            out.append("<hr/>")
            i += 1
            continue

        # Headings
        hm = re.match(r"^(#{1,6})\s+(.*)$", line)
        if hm:
            lvl = len(hm.group(1))
            out.append(f"<h{lvl}>{inline_md(hm.group(2).strip(), base_dir, packer)}</h{lvl}>")
            i += 1
            continue

        # Multi-line Blockquote (recursively parsed so nested ###/lists render cleanly)
        if stripped.startswith(">"):
            bq_lines: list[str] = []
            while i < n and lines[i].strip().startswith(">"):
                inner = lines[i].strip()[1:]
                if inner.startswith(" "):
                    inner = inner[1:]
                bq_lines.append(inner)
                i += 1
            inner_html = md_to_html("\n".join(bq_lines), md_path, packer)
            out.append(f"<blockquote>{inner_html}</blockquote>")
            continue

        # Markdown pipe table
        if "|" in stripped and i + 1 < n and is_table_sep(lines[i + 1]):
            headers = split_table_row(line)
            i += 2
            rows: list[list[str]] = []
            while i < n and lines[i].strip() and "|" in lines[i]:
                rows.append(split_table_row(lines[i]))
                i += 1
            ncols = max(1, len(headers))
            tbl_cls = "tbl-std" if ncols <= 5 else ("tbl-med" if ncols <= 8 else "tbl-wide")
            empty_hdr = all(not h.strip() for h in headers)
            th_html = None
            if not empty_hdr:
                th_html = "".join(f"<th>{inline_md(h, base_dir, packer, table_cols=ncols)}</th>" for h in headers)
            body_html: list[str] = []
            for r in rows:
                padded = r + [""] * max(0, ncols - len(r))
                body_html.append("".join(
                    f"<td>{brk(inline_md(c, base_dir, packer, table_cols=ncols))}</td>" for c in padded[:ncols]
                ))
            out.append(register_table(tbl_cls, th_html, body_html))
            continue

        # Unordered / ordered list
        if re.match(r"^\s*([-*+]|\d+\.)\s+", line):
            ordered = bool(re.match(r"^\s*\d+\.\s+", line))
            tag = "ol" if ordered else "ul"
            items: list[str] = []
            while i < n:
                cur = lines[i]
                if not cur.strip():
                    break
                m_item = re.match(r"^\s*(?:[-*+]|\d+\.)\s+(.*)$", cur)
                if m_item:
                    items.append(m_item.group(1).strip())
                    i += 1
                elif cur.startswith(("  ", "\t")) and items:
                    items[-1] += " " + cur.strip()
                    i += 1
                else:
                    break
            li_html = "".join(f"<li>{inline_md(it, base_dir, packer)}</li>" for it in items)
            out.append(f"<{tag}>{li_html}</{tag}>")
            continue

        # Paragraph
        para: list[str] = []
        while i < n:
            cur = lines[i]
            s = cur.strip()
            if not s:
                break
            if (
                s.startswith(("```", ">", "#"))
                or re.fullmatch(r"[-*_]{3,}", s)
                or re.match(r"^\s*(?:[-*+]|\d+\.)\s+", cur)
                or ("|" in s and i + 1 < n and is_table_sep(lines[i + 1]))
            ):
                break
            para.append(s)
            i += 1
        out.append(f"<p>{inline_md(' '.join(para), base_dir, packer)}</p>")

    return "\n".join(out)


def _open_story_archive(tmp_dir: Path, has_ttf: bool) -> fitz.Archive:
    dirs = [str(tmp_dir)]
    if has_ttf:
        dirs.append(str(WIN_FONTS_DIR))
    return fitz.Archive(dirs)


def _stamp_page_header(page: fitz.Page, doc_label: str) -> None:
    w = page.rect.width
    page.insert_text(
        fitz.Point(MARGIN_X, 26),
        f"KV260-IAS2RF Technical Documentation  |  {doc_label}",
        fontname="helv",
        fontsize=7.5,
        color=(0.40, 0.46, 0.54),
    )
    page.draw_line(
        fitz.Point(MARGIN_X, 31),
        fitz.Point(w - MARGIN_X, 31),
        color=(0.82, 0.86, 0.90),
        width=0.5,
    )


def _stamp_page_footer(page: fitz.Page, page_num: int, total_pages: int) -> None:
    w = page.rect.width
    h = page.rect.height
    page.draw_line(
        fitz.Point(MARGIN_X, h - 28),
        fitz.Point(w - MARGIN_X, h - 28),
        color=(0.82, 0.86, 0.90),
        width=0.5,
    )
    page.insert_text(
        fitz.Point(MARGIN_X, h - 16),
        "KV260-IAS2RF  |  Apache-2.0",
        fontname="helv",
        fontsize=7.5,
        color=(0.45, 0.52, 0.60),
    )
    page.insert_text(
        fitz.Point(w - MARGIN_X - 58, h - 16),
        f"Page {page_num} / {total_pages}",
        fontname="helv",
        fontsize=7.5,
        color=(0.45, 0.52, 0.60),
    )


# Tables are paginated here, not by MuPDF's Story: when Story breaks a table across pages it repeats the
# header where an earlier layout pass split it (a navy band in the middle of a page) and its cells stop lining
# up with their rows. md_to_html registers each table and leaves a token; render_html_pages lays the document
# out, finds the rows that start a new page, splits the table there into complete tables that each begin with
# the header row, and lays it out again until the split points stop moving. Every chunk then fits on its page.
_TABLES: dict[int, tuple[str, str | None, list[str]]] = {}
_TABLE_TOKEN = re.compile(r"@@TBL(\d+)@@")
ALT = " class='alt'"
TABLE_REPORT: list[str] = []


# Documents whose tables hold part numbers longer than their columns. Only these get break points: put in every
# table of the book, the break points made Story's table layout run for over two hours and 30 GB without finishing.
BREAKABLE_DOCS = {"JLCPCB_QUOTE.md"}
_LONG_WORD = re.compile(r"(?=[^\s<>&;]*\d)[^\s<>&;]{12,}")


def breakable(cell_html: str) -> str:
    """Zero-width spaces every 8 characters in words of 12 or more that hold a digit (manufacturer part numbers) in a
    cell's text, never inside a tag or an entity: Story cannot break a word, so such a word ran over its column's
    border (pdf_table_check.py (b)). Text only; the Markdown sources are unchanged."""
    def text_part(m: re.Match) -> str:
        return _LONG_WORD.sub(lambda w: "​".join(w.group(0)[i:i + 8] for i in range(0, len(w.group(0)), 8)),
                              m.group(0))
    return re.sub(r"(?<=>)[^<]+|^[^<]+", text_part, cell_html)


def register_table(tbl_cls: str, header_cells: str | None, rows_cells: list[str]) -> str:
    k = len(_TABLES)
    _TABLES[k] = (tbl_cls, header_cells, rows_cells)
    return f"@@TBL{k}@@"


def _table_html(k: int, splits: dict[int, set[int]], spacers: dict[tuple[int, int], float]) -> str:
    tbl_cls, header_cells, rows = _TABLES[k]
    cuts = [0] + sorted(s for s in splits.get(k, ()) if 0 < s < len(rows)) + [len(rows)]
    chunks = []
    for a, b in zip(cuts, cuts[1:]):
        if (k, a) in spacers:  # fills the foot of the page, so the header moves down with its first row
            chunks.append(f"<div style='height:{spacers[(k, a)]:.1f}pt'></div>")
        trs = [f"<tr id='t{k}h{a}' class='hdr'>{header_cells}</tr>"] if header_cells else []
        trs += [f"<tr id='t{k}r{j}'{ALT if j % 2 else ''}>{rows[j]}</tr>" for j in range(a, b)]
        cont = " cont" if a else ""
        chunks.append(f"<table class='{tbl_cls}{cont}'>{''.join(trs)}</table>")
    return "".join(chunks)


def _layout(full_html: str, user_css: str, arch: fitz.Archive) -> tuple[bytes, dict[str, tuple[int, float]]]:
    """One Story layout; returns the PDF bytes and the page and top of every element with an id."""
    story = fitz.Story(html=full_html, user_css=user_css, archive=arch)
    buf = io.BytesIO()
    writer = fitz.DocumentWriter(buf)
    pages: dict[str, tuple[int, float]] = {}

    def where(pos) -> None:
        if pos.id and pos.id not in pages:
            pages[pos.id] = (pos.page, pos.rect[1])

    more, pno = 1, 0
    while more:
        dev = writer.begin_page(fitz.Rect(0, 0, A4_W, A4_H))
        more, _ = story.place(CONTENT_RECT)
        story.element_positions(where, {"page": pno})
        story.draw(dev, None)
        writer.end_page()
        pno += 1
    writer.close()
    return buf.getvalue(), pages


def render_html_pages(html_body: str, tmp_dir: Path, doc_label: str, user_css: str, has_ttf: bool) -> fitz.Document:
    """Render an HTML fragment to A4 portrait PDF pages via PyMuPDF Story + DocumentWriter."""
    header_tag = f"<div class='doc-path'>Source: {html.escape(doc_label)}</div>" if doc_label else ""
    arch = _open_story_archive(tmp_dir, has_ttf)
    tables = [int(m) for m in _TABLE_TOKEN.findall(html_body)]
    splits: dict[int, set[int]] = {}
    spacers: dict[tuple[int, int], float] = {}
    seen_split: dict[tuple[int, int], int] = {}
    # Each pass fixes only the first problem in reading order, so everything above it is final: a row
    # that starts a page without a split, a split that is no longer at a page top, or a header left alone
    # at the foot of a page. Story lays out the rows of a table that runs over a page taller than they
    # are, so the row it puts at the top of the next page often fits once the table is cut there; such a
    # split moves down one row at a time until its row really starts the next page.
    for _ in range(3000):
        body = _TABLE_TOKEN.sub(lambda m: _table_html(int(m.group(1)), splits, spacers), html_body)
        full_html = f"<!DOCTYPE html><html><head><meta charset='utf-8'></head><body>{header_tag}{body}</body></html>"
        pdf_bytes, pages = _layout(full_html, user_css, arch)
        issues: list[tuple[int, float, str, int, int]] = []
        for k in tables:
            cuts = splits.get(k, set())
            for j in range(1, len(_TABLES[k][2])):
                cur, prev = pages.get(f"t{k}r{j}"), pages.get(f"t{k}r{j - 1}")
                if cur is None or prev is None:
                    continue
                if cur[0] != prev[0] and j not in cuts:
                    issues.append((cur[0], cur[1], "split", k, j))
                elif cur[0] == prev[0] and j in cuts:
                    issues.append((cur[0], cur[1], "unsplit", k, j))
            if _TABLES[k][1]:
                for a in {0} | cuts:
                    h, r = pages.get(f"t{k}h{a}"), pages.get(f"t{k}r{a}")
                    if h is not None and r is not None and h[0] != r[0] and (k, a) not in spacers:
                        issues.append((h[0], h[1], "orphan", k, a))
        if not issues:
            break
        _, y, kind, k, j = min(issues)
        if kind == "split":
            splits.setdefault(k, set()).add(j)
            seen_split[(k, j)] = seen_split.get((k, j), 0) + 1
        elif kind == "unsplit" and seen_split.get((k, j), 0) >= 3 and pages.get(f"t{k}h{j}"):
            # A cycle: cut at j, the rows from j fit on this page; uncut, row j starts the next one (the cut
            # tables lay out a little tighter than the whole). Keep the cut and push its part to the next page
            # with a spacer, as for an orphan header.
            spacers[(k, j)] = CONTENT_RECT.y1 - pages[f"t{k}h{j}"][1] - 1.0
        elif kind == "unsplit":
            splits[k].discard(j)
            if j + 1 < len(_TABLES[k][2]):
                splits[k].add(j + 1)
        else:
            spacers[(k, j)] = CONTENT_RECT.y1 - y - 1.0
    else:
        TABLE_REPORT.append(f"{doc_label}: table layout did not settle")
    doc = fitz.open("pdf", pdf_bytes)
    lbl = doc_label or "Table of Contents"
    for p in doc:
        _stamp_page_header(p, lbl)
    return doc


COVER_OUTLINE = REPO_ROOT / "docs" / "img" / "highres" / "layout" / "cover_outline.pdf"
DOC_REVISION = "1.0"
DOC_AUTHOR = "Pablo Soage"
DOC_REPO = "github.com/PabloSoage/kv260-ias2rf"


def add_cover_page(master: fitz.Document) -> None:
    """Title page: name, what the board is, a line drawing of it, revision, author and licence. Nothing else."""
    import datetime as _dt
    page = master.new_page(width=A4_W, height=A4_H)
    navy = (0.043, 0.180, 0.310)
    ink = (0.12, 0.16, 0.22)
    grey = (0.45, 0.50, 0.57)
    rule = (0.80, 0.84, 0.89)
    x0, x1 = 56, A4_W - 56

    page.draw_rect(fitz.Rect(x0, 64, x0 + 36, 67), color=None, fill=navy)
    page.insert_text(fitz.Point(x0, 86), "TECHNICAL DOCUMENTATION", fontname="helv", fontsize=8.5, color=grey)
    page.insert_text(fitz.Point(x0, 128), "KV260-IAS2RF", fontname="hebo", fontsize=34, color=navy)
    page.insert_text(fitz.Point(x0, 154), "RF front-end adapter for the AMD Kria KV260", fontname="helv", fontsize=13, color=ink)
    page.insert_text(
        fitz.Point(x0, 172),
        "Radar (AERIS-10, 10.5 GHz) and wideband SDR  \u00b7  Artix-7 front-end FPGA  \u00b7  8-layer PCB",
        fontname="helv", fontsize=9, color=grey,
    )

    # the board, as KiCad draws it: outline and component courtyards, top view
    area = fitz.Rect(x0, 205, x1, 640)
    if COVER_OUTLINE.is_file():
        src = fitz.open(str(COVER_OUTLINE))
        sr = src[0].rect
        k = min(area.width / sr.width, area.height / sr.height)
        w, h = sr.width * k, sr.height * k
        r = fitz.Rect(area.x0 + (area.width - w) / 2, area.y0 + (area.height - h) / 2, 0, 0)
        r.x1, r.y1 = r.x0 + w, r.y0 + h
        page.show_pdf_page(r, src, 0)
        src.close()
        page.insert_text(fitz.Point(r.x0, r.y1 + 16), "Top view: board outline and component courtyards (KiCad), 140 \u00d7 132 mm",
                         fontname="helv", fontsize=7.5, color=grey)

    rows = [
        ("Revision", DOC_REVISION),
        ("Date", _dt.date.today().strftime("%d %B %Y").lstrip("0")),
        ("Author", DOC_AUTHOR),
        ("Licence", "Apache-2.0  (third-party MIT notices in LICENSE)"),
        ("Source", DOC_REPO),
    ]
    y = 690
    page.draw_line(fitz.Point(x0, y - 14), fitz.Point(x1, y - 14), color=rule, width=0.6)
    for k_, v in rows:
        page.insert_text(fitz.Point(x0, y), k_.upper(), fontname="helv", fontsize=7.5, color=grey)
        page.insert_text(fitz.Point(x0 + 90, y), v, fontname="helv", fontsize=9.5, color=ink)
        y += 18
    page.draw_line(fitz.Point(x0, y - 6), fitz.Point(x1, y - 6), color=rule, width=0.6)


def add_summary_page(master: fitz.Document, part_summary: Iterable[tuple[str, int]]) -> None:
    """The platform summary and the book's structure, on the page after the cover."""
    page = master.new_page(width=A4_W, height=A4_H)
    navy = (0.043, 0.180, 0.310)
    slate = (0.28, 0.35, 0.43)
    light_bg = (0.945, 0.962, 0.985)
    y = 80
    page.insert_text(fitz.Point(48, y), "Platform Baseline Summary", fontname="hebo", fontsize=12.5, color=navy)
    y += 10
    card_rect = fitz.Rect(48, y, A4_W - 48, y + 231)
    page.draw_rect(card_rect, color=(0.78, 0.83, 0.89), fill=light_bg, width=0.8)

    facts = [
        ("PCB & Stackup", "8-layer JLC08161H-2116C (140 x 132 mm, 0 DRC / 0 ERC, openEMS S11 = -30.9 dB @ 1 GHz)"),
        ("High-Speed Link", "2-lane IAS1 LVDS (2.0-2.5 Gb/s UL, 1.0 Gb/s DL) + dedicated-pin 1000BASE-T RTL8211FSI UDP"),
        ("Artix-7 (XC7A50T)", "15,681 LUTs (48.1%), 18,084 FFs (27.7%), 16 BRAM36 (21.3%), 110 DSPs (91.7%), WNS = +0.111 ns at 400 and 500 MHz"),
        ("Kria K26 (XCK26)", "Full BD: 11,034 LUTs (9.4%), 18,212 FFs (7.8%), 3 BRAM36 (2.1%), WNS = +1.291 ns"),
        ("RF Missions", "AERIS-10 X-Band Radar (10.5 GHz, 20 km, 8x ADAR1000) + Wideband SDR (0-62.5 MHz HF/CB + VHF/UHF)"),
        ("HF input", "J951: 30 MHz 7th-order elliptic anti-alias filter on the board, >= 60 dB from 50 MHz; no RF switch in the path"),
        ("Thermal & Mech.", "Enclosure v2 (50x15 mm filtered lid fan, HS1-HS3, 50 g FEA BGA <= 162 ue): rated 56 C ambient with the stock KV260, 70 C with a K26I SOM"),
        ("XSim Co-Sim", "Dual-FPGA Artix-7 + PCB channels + K26 PL + RTL8211FSI/GEM3 UDP end-to-end PASS (S1..S6)"),
    ]
    ry = y + 12
    for k, v in facts:
        page.insert_text(fitz.Point(58, ry + 9), f"{k}:", fontname="hebo", fontsize=8.4, color=navy)
        page.insert_textbox(
            fitz.Rect(162, ry, A4_W - 56, ry + 26),
            v,
            fontname="helv",
            fontsize=8.1,
            color=(0.12, 0.16, 0.22),
            align=fitz.TEXT_ALIGN_LEFT,
        )
        ry += 27

    y = card_rect.y1 + 28
    page.insert_text(fitz.Point(48, y), "Compendium Structure", fontname="hebo", fontsize=12.5, color=navy)
    y += 18
    for title, count in part_summary:
        page.insert_text(fitz.Point(56, y), f"- {title}", fontname="helv", fontsize=9.5, color=slate)
        page.insert_text(fitz.Point(A4_W - 95, y), f"{count} item(s)", fontname="helv", fontsize=8.5, color=(0.45, 0.52, 0.60))
        y += 18


def add_section_divider(master: fitz.Document, title: str, subtitle: str) -> int:
    """Insert a clean A4 divider page and return its 1-based page number."""
    page = master.new_page(width=A4_W, height=A4_H)
    navy = (0.043, 0.180, 0.310)
    page.draw_rect(fitz.Rect(0, 290, A4_W, 430), color=None, fill=(0.94, 0.96, 0.99))
    page.draw_rect(fitz.Rect(42, 290, 48, 430), color=None, fill=navy)
    page.insert_text(fitz.Point(68, 345), title, fontname="hebo", fontsize=19, color=navy)
    page.insert_text(fitz.Point(68, 378), subtitle, fontname="helv", fontsize=10.5, color=(0.30, 0.38, 0.48))
    return len(master)


def add_showcase_pages(
    master: fitz.Document, packer: AssetPacker, tmp_dir: Path, user_css: str, has_ttf: bool
) -> list[tuple[int, str, int]]:
    """Build two-up A4 visual plates from the 4K hardware/heatsink/enclosure renders."""
    html_parts: list[str] = ["<h1>4K Hardware, Heatsink &amp; Enclosure v2 Visual Plates</h1>"]
    for caption, rel in SHOWCASE_4K_RENDERS:
        info = packer.prepare(REPO_ROOT / rel)
        if info:
            asset, px_w, px_h = info
            scale = min(485.0 / max(px_w, 1), 295.0 / max(px_h, 1))
            w_pt = max(1, int(round(px_w * scale)))
            h_pt = max(1, int(round(px_h * scale)))
            html_parts.append(
                f"<figure><img src='{asset}' width='{w_pt}' height='{h_pt}' alt='{html.escape(caption)}'/>"
                f"<figcaption>{html.escape(caption)} ({html.escape(rel)})</figcaption></figure>"
            )
    doc = render_html_pages("\n".join(html_parts), tmp_dir, "4K Hardware & Enclosure Gallery", user_css, has_ttf)
    start_page = len(master) + 1
    master.insert_pdf(doc)
    doc.close()
    return [(2, "4K Hardware, Heatsinks & Enclosure v2 Plates", start_page)]


def _embed_vector_document(master: fitz.Document, src: fitz.Document, title: str) -> int:
    """Embed every page of a vector PDF onto A4_W-wide pages with headers & proportional height."""
    start_page = len(master) + 1
    margin_x = 18.0
    header_h = 42.0
    footer_h = 34.0
    draw_w = A4_W - 2.0 * margin_x
    total_sheets = len(src)
    for pno in range(total_sheets):
        sr = src[pno].rect
        aspect = sr.height / max(sr.width, 1.0)
        draw_h = draw_w * aspect
        page_h = max(380.0, min(A4_H, header_h + draw_h + footer_h))
        avail_h = page_h - header_h - footer_h
        if draw_h > avail_h:
            scale = avail_h / max(draw_h, 1.0)
            box_w = draw_w * scale
            x0 = (A4_W - box_w) * 0.5
            target = fitz.Rect(x0, header_h, x0 + box_w, header_h + avail_h)
        else:
            target = fitz.Rect(margin_x, header_h, A4_W - margin_x, header_h + draw_h)
        page = master.new_page(width=A4_W, height=page_h)
        page.show_pdf_page(target, src, pno, keep_proportion=True)
        lbl = f"{title} ({pno + 1}/{total_sheets})" if total_sheets > 1 else title
        _stamp_page_header(page, lbl)
    return start_page


def insert_vector_pdf(master: fitz.Document, pdf_path: Path, toc: list[list], level: int, title: str) -> None:
    if not pdf_path.is_file():
        print(f"[warn] missing vector PDF: {pdf_path}", file=sys.stderr)
        return
    src = fitz.open(str(pdf_path))
    start_page = _embed_vector_document(master, src, title)
    src.close()
    toc.append([level, title, start_page])


def insert_vector_svg(master: fitz.Document, svg_path: Path, toc: list[list], level: int, title: str) -> None:
    if not svg_path.is_file():
        print(f"[warn] missing vector SVG: {svg_path}", file=sys.stderr)
        return
    svg_doc = fitz.open(str(svg_path))
    pdf_bytes = svg_doc.convert_to_pdf()
    svg_doc.close()
    vec_doc = fitz.open("pdf", pdf_bytes)
    start_page = _embed_vector_document(master, vec_doc, title)
    vec_doc.close()
    toc.append([level, title, start_page])


def _render_toc_document(toc_entries: list[list], offset: int, tmp_dir: Path, user_css: str, has_ttf: bool) -> fitz.Document:
    rows_html: list[str] = ["<h1>Table of Contents</h1><table class='tbl-std'><tbody>"]
    for lvl, title, pg in toc_entries:
        display_pg = pg + offset if pg > 1 else pg
        if lvl == 1:
            cls = "toc-part"
        elif lvl == 2:
            cls = "toc-item"
        else:
            cls = "toc-sub"
        rows_html.append(
            f"<tr class='{cls}'><td>{html.escape(title)}</td>"
            f"<td style='width:54pt;text-align:right;'>{display_pg}</td></tr>"
        )
    rows_html.append("</tbody></table>")
    return render_html_pages("\n".join(rows_html), tmp_dir, "", user_css, has_ttf)


def build_documentation_pdf(out_path: Path, max_img_width: int, jpeg_quality: int, include_vectors: bool) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _, has_ttf = _font_css()
    user_css = build_base_css(has_ttf)

    master = fitz.open()
    summary = [(p, len(docs)) for p, docs in PARTS]
    if include_vectors:
        summary.extend([
            ("Appendix A: Vector Vivado FPGA Silicon Floorplans & Schematics", len(VECTOR_FPGA_PDFS)),
            ("Appendix B: Vector Heatsink Mechanical Map", 1),
            ("Appendix C: Vector 11-Sheet Hierarchical KiCad Schematic", 11),
            ("Appendix D: Vector 10-Sheet 8-Layer PCB Layout", 10),
        ])
    add_cover_page(master)
    add_summary_page(master, summary)

    toc: list[list] = [[1, "Cover", 1], [1, "Platform Summary", 2]]

    with tempfile.TemporaryDirectory(prefix="kv260_doc_") as tmp_str:
        tmp_dir = Path(tmp_str)
        packer = AssetPacker(tmp_dir, max_w=max_img_width, jpeg_quality=jpeg_quality)

        for part_title, docs in PARTS:
            pnum = add_section_divider(master, part_title, f"{len(docs)} technical document(s)")
            toc.append([1, part_title, pnum])

            for doc_title, rel_md in docs:
                md_path = REPO_ROOT / rel_md
                if not md_path.is_file():
                    print(f"[warn] missing markdown: {md_path}", file=sys.stderr)
                    continue
                md_text = md_path.read_text(encoding="utf-8", errors="replace")
                md_text = drop_excluded_lines(md_text)
                html_body = md_to_html(md_text, md_path, packer)
                rendered = render_html_pages(html_body, tmp_dir, rel_md, user_css, has_ttf)
                start_page = len(master) + 1
                master.insert_pdf(rendered)
                rendered.close()
                toc.append([2, doc_title, start_page])

            if part_title.startswith("Part V:"):
                sub_toc = add_showcase_pages(master, packer, tmp_dir, user_css, has_ttf)
                for lvl, ttl, pg in sub_toc:
                    toc.append([lvl, ttl, pg])

        if include_vectors:
            pnum = add_section_divider(
                master,
                "Appendix A: Vivado FPGA Silicon & Schematics",
                "Lossless vector Artix-7 XC7A50T & Kria K26 floorplans and post-route circuit diagrams",
            )
            toc.append([1, "Appendix A: Vector Vivado FPGA Floorplans & Schematics", pnum])
            for title, rel in VECTOR_FPGA_PDFS:
                insert_vector_pdf(master, REPO_ROOT / rel, toc, 2, title)

            pnum = add_section_divider(
                master,
                "Appendix B: Heatsink Mechanical Keep-Out Drawing",
                "Lossless vector dimensions, clearances & HS1-HS5 thermal zones",
            )
            toc.append([1, "Appendix B: Vector Heatsink Mechanical Map", pnum])
            insert_vector_svg(
                master,
                REPO_ROOT / "docs/img/highres/renders/heatsink_mechanical_map.svg",
                toc,
                2,
                "Heatsink Placement & Mechanical Clearance Drawing",
            )

            pnum = add_section_divider(
                master,
                "Appendix C: 11-Sheet Hierarchical KiCad Schematic",
                "Complete connected overview + all 10 hierarchical schematic sheets (11 vector sheets)",
            )
            toc.append([1, "Appendix C: Vector 11-Sheet Hierarchical KiCad Schematic", pnum])
            sch_start = len(master) + 1
            insert_vector_pdf(
                master,
                REPO_ROOT / "docs/KV260-IAS2RF_schematic.pdf",
                toc,
                2,
                "Complete 11-Page Hierarchical KiCad Schematic",
            )
            sch_labels = [
                "Sheet 1: ROOT Hierarchical Top",
                "Sheet 2: FULL_CIRCUIT Complete Wired Overview",
                "Sheet 3: IAS_LINK (J101 / J102 / AC Coupling)",
                "Sheet 4: CONTROL (XC7A50T + Flash + JTAG + PHY)",
                "Sheet 5: CLOCK (Si549 + ADCLK948 LVPECL)",
                "Sheet 6: ADC_RADAR (AD9484 + Dual AD8352)",
                "Sheet 7: ADC_SDR (AD9253 + AD8352)",
                "Sheet 8: DAC_RADAR (AD9708 + Balun)",
                "Sheet 9: DAC_SDR (AD9767 Dual Channel)",
                "Sheet 10: ROUTING (RF Switches + SMAs)",
                "Sheet 11: POWER (12V Buck/LDO/Inverter Tree)",
            ]
            sch_end = len(master)
            for off, lbl in enumerate(sch_labels):
                if sch_start + off <= sch_end:
                    toc.append([3, lbl, sch_start + off])

            pnum = add_section_divider(
                master,
                "Appendix D: 8-Layer PCB Layout (JLC08161H-2116C)",
                "L1..L8 individual copper layers, all 8 layers combined & transparent signal routing (vector)",
            )
            toc.append([1, "Appendix D: Vector 8-Layer PCB Layout", pnum])
            layout_start = len(master) + 1
            insert_vector_pdf(
                master,
                REPO_ROOT / "docs/KV260-IAS2RF_layout.pdf",
                toc,
                2,
                "10-Sheet 8-Layer PCB Vector Layout",
            )
            layer_labels = [
                "Page 1: L1 (F.Cu Top Signal)",
                "Page 2: L2 (In1.Cu Solid GND)",
                "Page 3: L3 (In2.Cu Inner Signal)",
                "Page 4: L4 (In3.Cu Split Power)",
                "Page 5: L5 (In4.Cu Solid GND)",
                "Page 6: L6 (In5.Cu Inner Signal)",
                "Page 7: L7 (In6.Cu Solid GND)",
                "Page 8: L8 (B.Cu Bottom Signal)",
                "Page 9: Combined 8-Layer Composite",
                "Page 10: Transparent Tracks (GND/PWR Hidden)",
            ]
            layout_end = len(master)
            for off, lbl in enumerate(layer_labels):
                if layout_start + off <= layout_end:
                    toc.append([3, lbl, layout_start + off])

        # Build Table of Contents and converge offset after insertion at page index 1
        toc_offset = 0
        toc_doc = _render_toc_document(toc, toc_offset, tmp_dir, user_css, has_ttf)
        for _ in range(3):
            new_off = len(toc_doc)
            if new_off == toc_offset:
                break
            toc_doc.close()
            toc_offset = new_off
            toc_doc = _render_toc_document(toc, toc_offset, tmp_dir, user_css, has_ttf)

        master.insert_pdf(toc_doc, start_at=1)
        toc_doc.close()

    # Shift bookmark page numbers past inserted TOC and add TOC bookmark at page 2
    shifted_toc: list[list] = []
    inserted_toc_entry = False
    for lvl, title, pg in toc:
        shifted_toc.append([lvl, title, pg + toc_offset if pg > 1 else pg])
        if not inserted_toc_entry and pg == 1:
            shifted_toc.append([1, "Table of Contents", 2])
            inserted_toc_entry = True

    total_pages = len(master)
    for idx in range(1, total_pages):
        _stamp_page_footer(master[idx], idx + 1, total_pages)

    master.set_toc(shifted_toc)
    master.set_metadata({
        "title": "KV260-IAS2RF Technical Reference Documentation",
        "author": "Pablo Soage",
        "subject": "8-Layer RF Front-End Adapter, Dual-FPGA Vivado Gateware, AERIS-10 Radar & Wideband SDR",
    })
    master.save(str(out_path), garbage=4, deflate=True, clean=True)
    master.close()
    size_mb = out_path.stat().st_size / (1024.0 * 1024.0)
    print(f"Wrote {out_path} ({total_pages} pages, {size_mb:.2f} MB)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build unified offline PDF documentation for KV260-IAS2RF.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Output PDF path")
    parser.add_argument("--max-img-width", type=int, default=1600, help="Max raster image pixel width (default: 1600, about 220 dpi across A4)")
    parser.add_argument("--jpeg-quality", type=int, default=82, help="Embedded JPEG quality (default: 82)")
    parser.add_argument("--skip-vectors", action="store_true", help="Skip appending Vivado/KiCad vector PDF appendices")
    args = parser.parse_args()
    build_documentation_pdf(args.out, args.max_img_width, args.jpeg_quality, not args.skip_vectors)
    for line in TABLE_REPORT:
        print(f"[table] {line}", file=sys.stderr)
    return 1 if TABLE_REPORT else 0


if __name__ == "__main__":
    raise SystemExit(main())
