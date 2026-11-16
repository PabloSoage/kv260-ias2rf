# SPDX-License-Identifier: Apache-2.0
"""Crisp 150-dpi vector-to-PNG publication plot helpers using PyMuPDF (fitz) + Pillow + NumPy."""

import base64
import html
import io
import os
import fitz
import numpy as np
from PIL import Image


def _viridis_lut():
    """256x3 uint8 approximation of Viridis colormap (perceptually uniform, dark-to-bright)."""
    anchors = np.array([
        [0.00, 68, 1, 84],
        [0.13, 72, 40, 120],
        [0.25, 62, 74, 137],
        [0.38, 49, 104, 142],
        [0.50, 38, 130, 142],
        [0.63, 31, 158, 137],
        [0.75, 53, 183, 121],
        [0.88, 109, 205, 89],
        [1.00, 253, 231, 37],
    ], dtype=float)
    t = np.linspace(0.0, 1.0, 256)
    rgb = np.zeros((256, 3), dtype=np.uint8)
    for c in range(3):
        rgb[:, c] = np.clip(np.round(np.interp(t, anchors[:, 0], anchors[:, c + 1])), 0, 255).astype(np.uint8)
    return rgb


VIRIDIS = _viridis_lut()

PALETTE = [
    "#0f4c81",  # deep navy
    "#d94e1f",  # burnt orange
    "#1b8a5a",  # emerald
    "#7b3fa0",  # purple
    "#c28800",  # ochre
    "#333333",  # charcoal
]


def _nice_ticks(vmin, vmax, n=6):
    if vmax <= vmin:
        return [vmin]
    span = vmax - vmin
    raw_step = span / max(n - 1, 1)
    mag = 10.0 ** np.floor(np.log10(raw_step))
    norm = raw_step / mag
    for m in (1.0, 2.0, 2.5, 5.0, 10.0):
        if norm <= m + 1e-12:
            step = m * mag
            break
    else:
        step = 10.0 * mag
    start = np.ceil((vmin - 1e-9 * span) / step) * step
    vals = []
    v = start
    while v <= vmax + 1e-9 * span and len(vals) < 16:
        if abs(v) < 1e-9 * step:
            v = 0.0
        vals.append(float(v))
        v += step
    return vals


def _fmt_tick(v):
    if abs(v) >= 1000 or (0 < abs(v) < 0.01):
        return f"{v:.3g}"
    if abs(v - round(v)) < 1e-6:
        return f"{int(round(v))}"
    return f"{v:.2f}".rstrip("0").rstrip(".")


class Panel:
    def __init__(self, x0, y0, w, h, title="", xlabel="", ylabel=""):
        self.x0, self.y0, self.w, self.h = x0, y0, w, h
        self.title = title
        self.xlabel = xlabel
        self.ylabel = ylabel
        self.items = []  # ("line"|"h"|"v"|"img"|"scatter"|"fill"|"text"|"bar", data)
        self.xlim = None
        self.ylim = None
        self.legend_items = []
        self.colorbar_label = None
        self.colorbar_range = None

    def set_xlim(self, lo, hi):
        self.xlim = (float(lo), float(hi))

    def set_ylim(self, lo, hi):
        self.ylim = (float(lo), float(hi))

    def plot(self, x, y, color=None, lw=1.6, dash="", label=None):
        c = color or PALETTE[len([i for i in self.items if i[0] == "line"]) % len(PALETTE)]
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        self.items.append(("line", (x, y, c, lw, dash)))
        if label:
            self.legend_items.append((label, c, dash))

    def scatter(self, x, y, color="#d94e1f", r=4.0, marker="o", label=None):
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        self.items.append(("scatter", (x, y, color, r, marker)))
        if label:
            self.legend_items.append((label, color, ""))

    def axhline(self, y, color="#555555", lw=1.1, dash="4,3", label=None):
        self.items.append(("hline", (float(y), color, lw, dash)))
        if label:
            self.legend_items.append((label, color, dash))

    def axvline(self, x, color="#555555", lw=1.1, dash="4,3", label=None):
        self.items.append(("axvline", (float(x), color, lw, dash)))
        if label:
            self.legend_items.append((label, color, dash))

    def text_ann(self, x, y, txt, color="#111111", size=9.5, anchor="start"):
        self.items.append(("text", (float(x), float(y), txt, color, size, anchor)))

    def table_lines(self, headers, rows):
        """Render a clean crisp data table directly inside the panel area."""
        self.items.append(("table", (headers, rows)))
        self.xlim = (0.0, 1.0)
        self.ylim = (0.0, 1.0)

    def imshow(self, arr, extent, vmin=None, vmax=None, clabel="Power (dB)"):
        """arr shape (rows, cols); extent = (xmin, xmax, ymin, ymax)."""
        a = np.asarray(arr, dtype=float)
        v0 = float(np.min(a)) if vmin is None else float(vmin)
        v1 = float(np.max(a)) if vmax is None else float(vmax)
        if v1 <= v0:
            v1 = v0 + 1.0
        ex0, ex1, ey0, ey1 = float(extent[0]), float(extent[1]), float(extent[2]), float(extent[3])
        if ex1 <= ex0:
            ex0, ex1 = ex0 - 1.0, ex1 + 1.0
        if ey1 <= ey0:
            ey0, ey1 = ey0 - 1.0, ey1 + 1.0
        self.items.append(("img", (a, (ex0, ex1, ey0, ey1), v0, v1)))
        self.colorbar_label = clabel
        self.colorbar_range = (v0, v1)
        self.xlim = (ex0, ex1)
        self.ylim = (ey0, ey1)

    def _compute_bounds(self):
        xs, ys = [], []
        for kind, data in self.items:
            if kind in ("line", "scatter"):
                x, y = data[0], data[1]
                m = np.isfinite(x) & np.isfinite(y)
                if np.any(m):
                    xs.append(x[m])
                    ys.append(y[m])
            elif kind == "img":
                ex = data[1]
                xs.append(np.array([ex[0], ex[1]]))
                ys.append(np.array([ex[2], ex[3]]))
        x0 = float(np.min([np.min(a) for a in xs])) if xs else 0.0
        x1 = float(np.max([np.max(a) for a in xs])) if xs else 1.0
        y0 = float(np.min([np.min(a) for a in ys])) if ys else 0.0
        y1 = float(np.max([np.max(a) for a in ys])) if ys else 1.0
        if self.xlim is not None:
            x0, x1 = self.xlim
        elif x1 <= x0:
            x0, x1 = x0 - 0.5, x1 + 0.5
        if self.ylim is not None:
            y0, y1 = self.ylim
        else:
            pad = 0.08 * (y1 - y0) if y1 > y0 else 1.0
            y0, y1 = y0 - pad, y1 + pad
        return x0, x1, y0, y1

    def to_svg(self, clip_id):
        x0, x1, y0, y1 = self._compute_bounds()
        pw = self.w - (52 if self.colorbar_label else 0)
        ph = self.h
        px0, py0 = self.x0, self.y0

        def tx(vx):
            return px0 + (vx - x0) / (x1 - x0) * pw

        def ty(vy):
            return py0 + ph - (vy - y0) / (y1 - y0) * ph

        out = []
        # Background & border
        out.append(f'<rect x="{px0:.1f}" y="{py0:.1f}" width="{pw:.1f}" height="{ph:.1f}" fill="#ffffff" stroke="#888888" stroke-width="1"/>')

        # Grid & ticks (skip for table-only panels)
        is_table_only = (len(self.items) == 1 and self.items[0][0] == "table")
        xticks = [] if is_table_only else _nice_ticks(x0, x1, 6)
        yticks = [] if is_table_only else _nice_ticks(y0, y1, 5)
        for xv in xticks:
            sx = tx(xv)
            if px0 <= sx <= px0 + pw + 0.5:
                out.append(f'<line x1="{sx:.1f}" y1="{py0:.1f}" x2="{sx:.1f}" y2="{py0+ph:.1f}" stroke="#e2e6ea" stroke-width="0.8"/>')
                out.append(f'<line x1="{sx:.1f}" y1="{py0+ph:.1f}" x2="{sx:.1f}" y2="{py0+ph+4:.1f}" stroke="#444444" stroke-width="1"/>')
                out.append(f'<text x="{sx:.1f}" y="{py0+ph+15:.1f}" text-anchor="middle" font-size="9.5" fill="#222222">{html.escape(_fmt_tick(xv))}</text>')
        for yv in yticks:
            sy = ty(yv)
            if py0 - 0.5 <= sy <= py0 + ph + 0.5:
                out.append(f'<line x1="{px0:.1f}" y1="{sy:.1f}" x2="{px0+pw:.1f}" y2="{sy:.1f}" stroke="#e2e6ea" stroke-width="0.8"/>')
                out.append(f'<line x1="{px0-4:.1f}" y1="{sy:.1f}" x2="{px0:.1f}" y2="{sy:.1f}" stroke="#444444" stroke-width="1"/>')
                out.append(f'<text x="{px0-7:.1f}" y="{sy+3:.1f}" text-anchor="end" font-size="9.5" fill="#222222">{html.escape(_fmt_tick(yv))}</text>')

        # Clipped content
        out.append(f'<defs><clipPath id="{clip_id}"><rect x="{px0:.1f}" y="{py0:.1f}" width="{pw:.1f}" height="{ph:.1f}"/></clipPath></defs>')
        out.append(f'<g clip-path="url(#{clip_id})">')
        for kind, data in self.items:
            if kind == "img":
                arr, ex, v0, v1 = data
                norm = np.clip((arr - v0) / (v1 - v0), 0.0, 1.0)
                idx = np.round(norm * 255).astype(np.uint8)
                rgb = VIRIDIS[idx[::-1, :]] # origin lower
                im = Image.fromarray(rgb, mode="RGB")
                buf = io.BytesIO()
                im.save(buf, format="PNG")
                b64 = base64.b64encode(buf.getvalue()).decode("ascii")
                out.append(
                    f'<image x="{px0:.1f}" y="{py0:.1f}" width="{pw:.1f}" height="{ph:.1f}" '
                    f'preserveAspectRatio="none" href="data:image/png;base64,{b64}"/>'
                )
            elif kind == "line":
                x, y, c, lw, dash = data
                m = np.isfinite(x) & np.isfinite(y)
                x, y = x[m], y[m]
                if len(x) > 1200:
                    step = len(x) // 1000
                    x, y = x[::step], y[::step]
                pts = " ".join(f"{tx(xx):.1f},{ty(yy):.1f}" for xx, yy in zip(x, y))
                d_attr = f' stroke-dasharray="{dash}"' if dash else ""
                out.append(f'<polyline fill="none" stroke="{c}" stroke-width="{lw}"{d_attr} points="{pts}"/>')
            elif kind == "scatter":
                x, y, c, r, marker = data
                for xx, yy in zip(x, y):
                    if np.isfinite(xx) and np.isfinite(yy):
                        if marker == "x":
                            sx, sy = tx(xx), ty(yy)
                            out.append(f'<line x1="{sx-r:.1f}" y1="{sy-r:.1f}" x2="{sx+r:.1f}" y2="{sy+r:.1f}" stroke="{c}" stroke-width="1.8"/>')
                            out.append(f'<line x1="{sx-r:.1f}" y1="{sy+r:.1f}" x2="{sx+r:.1f}" y2="{sy-r:.1f}" stroke="{c}" stroke-width="1.8"/>')
                        else:
                            out.append(f'<circle cx="{tx(xx):.1f}" cy="{ty(yy):.1f}" r="{r:.1f}" fill="{c}" stroke="#ffffff" stroke-width="0.8"/>')
            elif kind == "hline":
                yv, c, lw, dash = data
                sy = ty(yv)
                d_attr = f' stroke-dasharray="{dash}"' if dash else ""
                out.append(f'<line x1="{px0:.1f}" y1="{sy:.1f}" x2="{px0+pw:.1f}" y2="{sy:.1f}" stroke="{c}" stroke-width="{lw}"{d_attr}/>')
            elif kind == "axvline":
                xv, c, lw, dash = data
                sx = tx(xv)
                d_attr = f' stroke-dasharray="{dash}"' if dash else ""
                out.append(f'<line x1="{sx:.1f}" y1="{py0:.1f}" x2="{sx:.1f}" y2="{py0+ph:.1f}" stroke="{c}" stroke-width="{lw}"{d_attr}/>')
            elif kind == "text":
                xv, yv, txt, c, sz, anc = data
                out.append(f'<text x="{tx(xv):.1f}" y="{ty(yv):.1f}" font-size="{sz}" text-anchor="{anc}" fill="{c}" font-weight="bold">{html.escape(txt)}</text>')
            elif kind == "table":
                headers, rows = data
                row_h = min(22.0, (ph - 12.0) / max(len(rows) + 1, 2))
                col_w = pw / max(len(headers), 1)
                # Header row
                out.append(f'<rect x="{px0:.1f}" y="{py0:.1f}" width="{pw:.1f}" height="{row_h:.1f}" fill="#0f3a60"/>')
                for ci, hd in enumerate(headers):
                    out.append(f'<text x="{px0 + ci*col_w + 6:.1f}" y="{py0 + row_h*0.68:.1f}" font-size="9" font-weight="bold" fill="#ffffff">{html.escape(str(hd))}</text>')
                for ri, row in enumerate(rows):
                    ry = py0 + (ri + 1) * row_h
                    bg = "#f6f8fa" if (ri % 2 == 1) else "#ffffff"
                    out.append(f'<rect x="{px0:.1f}" y="{ry:.1f}" width="{pw:.1f}" height="{row_h:.1f}" fill="{bg}" stroke="#dde2e7" stroke-width="0.6"/>')
                    for ci, cell in enumerate(row):
                        out.append(f'<text x="{px0 + ci*col_w + 6:.1f}" y="{ry + row_h*0.68:.1f}" font-size="8.5" fill="#111111">{html.escape(str(cell))}</text>')
        out.append('</g>')

        # Colorbar if heatmap
        if self.colorbar_label and self.colorbar_range:
            v0, v1 = self.colorbar_range
            cb_x = px0 + pw + 8
            cb_w = 11
            grad_im = Image.fromarray(VIRIDIS[::-1][:, None, :].repeat(2, axis=1), mode="RGB")
            buf = io.BytesIO()
            grad_im.save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            out.append(f'<image x="{cb_x:.1f}" y="{py0:.1f}" width="{cb_w}" height="{ph:.1f}" preserveAspectRatio="none" href="data:image/png;base64,{b64}"/>')
            out.append(f'<rect x="{cb_x:.1f}" y="{py0:.1f}" width="{cb_w}" height="{ph:.1f}" fill="none" stroke="#666666" stroke-width="0.8"/>')
            out.append(f'<text x="{cb_x+cb_w+3:.1f}" y="{py0+8:.1f}" font-size="8.5" fill="#222222">{_fmt_tick(v1)}</text>')
            out.append(f'<text x="{cb_x+cb_w+3:.1f}" y="{py0+ph/2+3:.1f}" font-size="8.5" fill="#222222">{_fmt_tick((v0+v1)/2)}</text>')
            out.append(f'<text x="{cb_x+cb_w+3:.1f}" y="{py0+ph:.1f}" font-size="8.5" fill="#222222">{_fmt_tick(v0)}</text>')
            out.append(f'<text x="{cb_x+cb_w+14:.1f}" y="{py0+ph/2:.1f}" font-size="8.5" text-anchor="middle" fill="#222222" transform="rotate(-90 {cb_x+cb_w+14:.1f},{py0+ph/2:.1f})">{html.escape(self.colorbar_label)}</text>')

        # Legend
        if self.legend_items:
            lh = 13 * len(self.legend_items) + 6
            lw_box = max(95, max(len(lbl) * 5.6 + 26 for lbl, _, _ in self.legend_items))
            lx = px0 + pw - lw_box - 6
            ly = py0 + 6
            out.append(f'<rect x="{lx:.1f}" y="{ly:.1f}" width="{lw_box:.1f}" height="{lh:.1f}" fill="#ffffff" fill-opacity="0.90" stroke="#aaaaaa" stroke-width="0.7" rx="2"/>')
            for idx_l, (lbl, c, dash) in enumerate(self.legend_items):
                yy = ly + 11 + idx_l * 13
                d_attr = f' stroke-dasharray="{dash}"' if dash else ""
                out.append(f'<line x1="{lx+6:.1f}" y1="{yy-3:.1f}" x2="{lx+20:.1f}" y2="{yy-3:.1f}" stroke="{c}" stroke-width="1.8"{d_attr}/>')
                out.append(f'<text x="{lx+24:.1f}" y="{yy:.1f}" font-size="8.5" fill="#111111">{html.escape(lbl)}</text>')

        # Labels & Title
        if self.title:
            out.append(f'<text x="{px0+pw/2:.1f}" y="{py0-8:.1f}" text-anchor="middle" font-size="11" font-weight="bold" fill="#111111">{html.escape(self.title)}</text>')
        if self.xlabel:
            out.append(f'<text x="{px0+pw/2:.1f}" y="{py0+ph+30:.1f}" text-anchor="middle" font-size="10" fill="#222222">{html.escape(self.xlabel)}</text>')
        if self.ylabel:
            out.append(f'<text x="{px0-42:.1f}" y="{py0+ph/2:.1f}" text-anchor="middle" font-size="10" fill="#222222" transform="rotate(-90 {px0-42:.1f},{py0+ph/2:.1f})">{html.escape(self.ylabel)}</text>')

        return "\n".join(out)


class Figure:
    def __init__(self, rows=2, cols=2, width=1080, height=720, suptitle=""):
        self.rows = rows
        self.cols = cols
        self.width = width
        self.height = height
        self.suptitle = suptitle
        self.panels = []
        top_m = 56 if suptitle else 28
        bot_m = 44
        left_m = 68
        right_m = 24
        hgap = 72
        vgap = 58
        pw = (width - left_m - right_m - (cols - 1) * hgap) / cols
        ph = (height - top_m - bot_m - (rows - 1) * vgap) / rows
        for r in range(rows):
            for c in range(cols):
                x0 = left_m + c * (pw + hgap)
                y0 = top_m + r * (ph + vgap)
                self.panels.append(Panel(x0, y0, pw, ph))

    def ax(self, idx):
        return self.panels[idx]

    def save_png(self, out_path, dpi=150):
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        svg_parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" height="{self.height}" viewBox="0 0 {self.width} {self.height}" font-family="DejaVu Sans, Arial, Helvetica, sans-serif">',
            f'<rect x="0" y="0" width="{self.width}" height="{self.height}" fill="#ffffff"/>',
        ]
        if self.suptitle:
            svg_parts.append(
                f'<text x="{self.width/2:.1f}" y="22" text-anchor="middle" font-size="13.5" font-weight="bold" fill="#0f3a60">{html.escape(self.suptitle)}</text>'
            )
        for i, p in enumerate(self.panels):
            if p.items:
                svg_parts.append(p.to_svg(f"clip_{i}"))
        svg_parts.append("</svg>")
        svg_bytes = "\n".join(svg_parts).encode("utf-8")

        doc = fitz.open("svg", svg_bytes)
        page = doc[0]
        zoom = dpi / 72.0
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        pix.save(out_path)
        doc.close()
        return out_path
