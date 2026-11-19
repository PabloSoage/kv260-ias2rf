#!/usr/bin/env python3
"""
docs/img/power_options.png: the two ways to power the adapter and the KV260, drawn on the boards' own top renders
(docs/img/board_top.png, docs/img/psu/psu_top.png). Connector positions come from the PCBs (site/assets/
components.json and psu.json), mapped onto each render through the board outline found in the image.

  A. Bench: one 12 V / 5 A brick on the adapter's J1001; the short VHR-2N jumper from J1004 to the KV260's J12.
  B. Car or bench: the PSU board. Battery (or 6 to 36 V bench supply) on J1; J2 to the adapter's J1001, J3 to the
     KV260's J12. J1004 unused.

Usage:  python _work/power/power_options.py
"""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                      # noqa: E402
import numpy as np                                    # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Circle   # noqa: E402
from PIL import Image                                 # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "docs", "img", "power_options.png")
RED, BLK, GRN, INK, MUTED = "#c62828", "#263238", "#1e6b30", "#1b2631", "#4a5a6a"


def board_px(img):
    """Pixel bbox of the green board in a top render."""
    a = np.asarray(img.convert("RGB")).astype(int)
    m = (a[..., 1] > a[..., 0] + 15) & (a[..., 1] > a[..., 2] + 5)
    ys, xs = np.nonzero(m)
    return xs.min(), ys.min(), xs.max(), ys.max()


def mapper(img, outline, margin=0.07, rotate=False):
    """Crop the render to the board (plus a margin for overhanging connectors), optionally turn it 180 degrees;
    return the cropped image and a KiCad mm -> image pixel map."""
    x0, y0, x1, y1 = board_px(img)
    mx, my = int((x1 - x0) * margin), int((y1 - y0) * margin)
    cx0, cy0, cx1, cy1 = max(0, x0 - mx), max(0, y0 - my), min(img.width, x1 + mx), min(img.height, y1 + my)
    crop = img.convert("RGB").crop((cx0, cy0, cx1, cy1))
    kx0, ky0, kx1, ky1 = outline

    def f(x, y):
        px = x0 + (x - kx0) / (kx1 - kx0) * (x1 - x0) - cx0
        py = y0 + (y - ky0) / (ky1 - ky0) * (y1 - y0) - cy0
        return (crop.width - px, crop.height - py) if rotate else (px, py)
    return (crop.rotate(180) if rotate else crop), f


def place(ax, img, box):
    """Draw img into axes-data box (x, y, w) keeping aspect; return a KiCad->axes mapper factory."""
    x, y, w = box
    h = w * img.height / img.width
    ax.imshow(img, extent=(x, x + w, y + h, y), zorder=1)
    return lambda f: (lambda kx, ky: (lambda p: (x + p[0] / img.width * w, y + p[1] / img.height * h))(f(kx, ky)))


def tag(ax, xy, text, colour=RED, dx=0, dy=0, ha="center"):
    ax.add_patch(Circle(xy, 1.6, fill=False, lw=2.2, ec=colour, zorder=5))
    if text:
        ax.text(xy[0] + dx, xy[1] + dy, text, color=colour, fontsize=10.5, weight="bold", ha=ha, va="center",
                zorder=6, bbox=dict(boxstyle="round,pad=0.25", fc="white", ec=colour, lw=1))


def box(ax, x, y, w, h, title, sub, fc, ec):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.4,rounding_size=1.2", fc=fc, ec=ec, lw=2,
                                zorder=3))
    ax.text(x + w / 2, y + h * 0.36, title, ha="center", va="center", fontsize=12, weight="bold", color=INK, zorder=4)
    ax.text(x + w / 2, y + h * 0.70, sub, ha="center", va="center", fontsize=9, color=MUTED, zorder=4)


def wire(ax, pts, colour, label=None, lpos=0.5, lw=3.2, arrow=True):
    xs, ys = zip(*pts)
    ax.plot(xs[:-1] + (xs[-1],), ys, color=colour, lw=lw, solid_capstyle="round", zorder=4)
    if arrow:
        ax.add_patch(FancyArrowPatch(pts[-2], pts[-1], arrowstyle="-|>", mutation_scale=18, color=colour, lw=0,
                                     zorder=4))
    if label:
        i = max(0, min(len(pts) - 2, int(lpos * (len(pts) - 1))))
        mx, my = (pts[i][0] + pts[i + 1][0]) / 2, (pts[i][1] + pts[i + 1][1]) / 2
        ax.text(mx, my - 1.8, label, color=colour, fontsize=9.5, weight="bold", ha="center", va="bottom", zorder=6,
                bbox=dict(boxstyle="round,pad=0.2", fc="#ffffffd0", ec="none"))


def main():
    comps = {c["ref"]: c for c in json.load(open(os.path.join(ROOT, "site", "assets", "components.json"), encoding="utf-8"))["components"]}
    psu = {c["ref"]: c for c in json.load(open(os.path.join(ROOT, "site", "assets", "psu.json"), encoding="utf-8"))["components"]}
    o = json.load(open(os.path.join(ROOT, "site", "assets", "components.json"), encoding="utf-8"))["board_outline"]
    adp = Image.open(os.path.join(ROOT, "docs", "img", "board_top.png"))
    pimg = Image.open(os.path.join(ROOT, "docs", "img", "psu", "psu_top.png"))
    adp, m_adp = mapper(adp, (o["xmin"], o["ymin"], o["xmax"], o["ymax"]))
    pimg, m_psu = mapper(pimg, (100, 100, 210, 170), margin=0.04, rotate=True)

    fig, axes = plt.subplots(1, 2, figsize=(20, 9.6), dpi=150)
    fig.patch.set_facecolor("#e8ecf0")
    fig.suptitle("Powering the adapter and the KV260: one supply, one ground", fontsize=19, weight="bold",
                 color=INK, y=0.975)
    fig.text(0.5, 0.925, "The boards share ground through the 22 BM20 contacts (0.3 A each): never a second, "
             "unrelated supply on the KV260's J12", ha="center", fontsize=11.5, color=MUTED)
    for ax, title in zip(axes, ("A. Bench: one 12 V / 5 A brick", "B. Car or bench: the PSU board")):
        ax.set_xlim(0, 100)
        ax.set_ylim(80, 0)
        ax.set_aspect("equal")
        ax.axis("off")
        ax.add_patch(FancyBboxPatch((0.5, 0.5), 99, 79, boxstyle="round,pad=0,rounding_size=2", fc="#dfe4ea",
                                    ec="#a9b3bd", lw=1.5, zorder=0))
        ax.text(3, 5, title, fontsize=15, weight="bold", color=INK, va="center")

    # ---- A
    ax = axes[0]
    f = place(ax, adp, (40, 9, 54))(m_adp)
    j1001, j1004 = f(comps["J1001"]["x_mm"], comps["J1001"]["y_mm"]), f(comps["J1004"]["x_mm"], comps["J1004"]["y_mm"])
    box(ax, 3, 14, 20, 11, "12 V brick", ">= 5 A, Class II (2-prong)", "#d5dbe1", "#59636d")
    box(ax, 3, 52, 20, 13, "KV260", "J12: 12 V in\n(sits under the adapter)", "#a5d6a7", GRN)
    wire(ax, [(23.8, 19.5), (j1001[0] - 6, 19.5), (j1001[0] - 6, j1001[1]), (j1001[0] - 1.8, j1001[1])], RED,
         "12 V to J1001", 0.2)
    wire(ax, [(j1004[0] - 1.8, j1004[1]), (j1004[0] - 6, j1004[1]), (j1004[0] - 6, 58.5), (23.8, 58.5)], RED,
         "J1004 -> J12 jumper (VHR-2N, 15 cm)", 0.95)
    tag(ax, j1001, "J1001", dx=0, dy=-4.2)
    tag(ax, j1004, "J1004 (3.0 A eFuse)", dx=4, dy=4.2)
    ax.text(3, 74.5, "U1010 on the adapter protects the KV260's feed (3.0 A, 14.4 V overvoltage, reverse to -60 V).\n"
            "J1004 is that protected output; nothing else goes on J12.", fontsize=9.5, color=INK, va="center")

    # ---- B
    ax = axes[1]
    fp = place(ax, pimg, (4, 26, 40))(m_psu)
    fa = place(ax, adp, (60, 27, 37))(m_adp)
    j1, j2, j3 = (fp(psu[r]["x_mm"], psu[r]["y_mm"]) for r in ("J1", "J2", "J3"))
    a1001 = fa(comps["J1001"]["x_mm"], comps["J1001"]["y_mm"])
    a1004 = fa(comps["J1004"]["x_mm"], comps["J1004"]["y_mm"])
    box(ax, 66, 9, 22, 11, "KV260", "J12: 12 V in", "#a5d6a7", GRN)
    box(ax, 4, 64, 30, 10, "Battery or 6-36 V bench", "20 A fuse at the battery, 16 AWG", "#d5dbe1", "#59636d")
    wire(ax, [(j3[0] + 1.8, j3[1]), (52, j3[1]), (52, 14.5), (65.2, 14.5)], RED, "J3 -> J12 (3.0 A eFuse)", 0.75)
    wire(ax, [(j2[0] + 1.8, j2[1]), (56, j2[1]), (56, a1001[1]), (a1001[0] - 1.8, a1001[1])], RED,
         "J2 -> J1001 (2.0 A eFuse)", 0.95)
    wire(ax, [(34.8, 69), (j1[0] + 6, 69), (j1[0] + 6, j1[1]), (j1[0] + 1.8, j1[1])], RED, "XT30 to J1", 0.1)
    tag(ax, j1, "J1", dx=0, dy=3.8)
    tag(ax, j2, "J2", dx=0, dy=-3.8)
    tag(ax, j3, "J3", dx=0, dy=-3.8)
    tag(ax, a1001, "J1001", dx=0, dy=-4.2)
    tag(ax, a1004, "J1004 unused", colour=MUTED, dx=0, dy=4.2)
    ax.text(4, 78, "Load dump clamped at 48 V, reverse battery blocked, 12.0 V out from 4.4 to 36 V in "
            "(cranking included).", fontsize=9.5, color=INK, va="bottom")
    plt.subplots_adjust(left=0.01, right=0.99, top=0.9, bottom=0.01, wspace=0.03)
    fig.savefig(OUT, facecolor=fig.get_facecolor())
    print("wrote", OUT)


if __name__ == "__main__":
    main()
