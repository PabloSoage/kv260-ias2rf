#!/usr/bin/env python3
"""
Simple 3D models (VRML) for the parts whose footprint has no model, or names a model file that the
KiCad 10 3D library does not ship, and the board's model paths pointed at them.

The models are boxes and cylinders at the data sheets' outline sizes and heights, coloured like the
part: good enough for the renders and for checking heights, not for mechanical fit to 0.1 mm. Where
the KiCad library has a model of the same package under another name (a different exposed pad, a
generic BGA of the same body and pitch), the footprint is pointed at that one instead.

Written to footprints/kv260-ias2rf.3dshapes/ and referenced as ${KIPRJMOD}/footprints/...; the
project library's own footprints get the same model, so the board and the library agree.

Usage:  py _work/layout/models3d.py            (writes the models, patches the board and the library)
        py _work/layout/models3d.py --models   (only the .wrl files)
"""
import math
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "footprints", "kv260-ias2rf.3dshapes")
BOARD = os.path.join(ROOT, "CSI2-KRIA-KV260_Rev01.kicad_pcb")
LIB = os.path.join(ROOT, "footprints", "kv260-ias2rf.pretty")
PRJ = "${KIPRJMOD}/footprints/kv260-ias2rf.3dshapes/"
STOCK = "${KICAD10_3DMODEL_DIR}/"

BLACK = (0.08, 0.08, 0.09, 0.3)
GREY = (0.32, 0.33, 0.35, 0.3)
PIN = (0.78, 0.78, 0.76, 0.9)
GOLD = (0.85, 0.68, 0.30, 0.9)
WHITE = (0.90, 0.89, 0.84, 0.2)
METAL = (0.58, 0.59, 0.62, 0.9)
BEIGE = (0.86, 0.80, 0.64, 0.2)
DOT = (0.55, 0.55, 0.55, 0.3)
GREEN = (0.10, 0.75, 0.20, 0.5)
AMBER = (0.95, 0.65, 0.10, 0.5)


class Model:
    """Shapes in mm, KiCad's footprint frame: X right, Y down (flipped here), Z up from the board."""

    def __init__(self):
        self.s = []

    def box(self, cx, cy, z0, sx, sy, sz, col):
        self.s.append(("box", (cx, -cy, z0 + sz / 2), (sx, sy, sz), col))

    def cyl(self, cx, cy, z0, r, h, col, axis="z"):
        self.s.append(("cyl", (cx, -cy, z0), (r, h, axis), col))

    def wrl(self):
        out = ["#VRML V2.0 utf8", "# simple model, kv260-ias2rf _work/layout/models3d.py",
               "Transform { scale 0.393701 0.393701 0.393701 children ["]
        for kind, (x, y, z), dims, (r, g, b, shin) in self.s:
            mat = (f"appearance Appearance {{ material Material {{ diffuseColor {r:.3f} {g:.3f} {b:.3f} "
                   f"specularColor {shin*0.6:.2f} {shin*0.6:.2f} {shin*0.6:.2f} shininess {shin:.2f} }} }}")
            if kind == "box":
                sx, sy, sz = dims
                out.append(f"Transform {{ translation {x:.4f} {y:.4f} {z:.4f} children Shape {{ {mat} "
                           f"geometry Box {{ size {sx:.4f} {sy:.4f} {sz:.4f} }} }} }}")
            else:
                rad, h, axis = dims
                if axis == "z":      # VRML cylinders stand on Y
                    rot, t = "1 0 0 1.570796", (x, y, z + h / 2)
                elif axis == "y":    # along the footprint's Y
                    rot, t = "0 0 1 0", (x, y - h / 2, z)
                else:
                    rot, t = "0 0 1 1.570796", (x + h / 2, y, z)
                out.append(f"Transform {{ translation {t[0]:.4f} {t[1]:.4f} {t[2]:.4f} rotation {rot} children "
                           f"Shape {{ {mat} geometry Cylinder {{ radius {rad:.4f} height {h:.4f} }} }} }}")
        out.append("] }")
        return "\n".join(out) + "\n"


def qfn(body, n, pitch, h, pin_w=0.25, pin_l=0.4, col=BLACK):
    """QFN / LFCSP: n pins a side, pin 1 at the top left, as KiCad's footprints."""
    m = Model()
    m.box(0, 0, 0, body, body, h, col)
    first = -(n - 1) / 2 * pitch
    e = body / 2
    for k in range(n):
        p = first + k * pitch
        m.box(-e + pin_l / 2 - 0.01, p, 0, pin_l, pin_w, 0.2, PIN)       # left
        m.box(p, e - pin_l / 2 + 0.01, 0, pin_w, pin_l, 0.2, PIN)        # bottom
        m.box(e - pin_l / 2 + 0.01, -p, 0, pin_l, pin_w, 0.2, PIN)       # right
        m.box(-p, -e + pin_l / 2 - 0.01, 0, pin_w, pin_l, 0.2, PIN)      # top
    m.cyl(-e + 0.55, -e + 0.55, h, min(0.25, body / 14), 0.01, DOT)
    return m


def chip(lx, ly, h, body, cap_len, term=PIN):
    """Two-terminal block along X: terminations cap_len long at each end."""
    m = Model()
    m.box(0, 0, 0, lx - 2 * cap_len, ly, h, body)
    for s in (-1, 1):
        m.box(s * (lx / 2 - cap_len / 2), 0, 0, cap_len, ly, h, term)
    return m


def cd542():
    """Mini-Circuits CD542 transformer: ceramic base, 6 J-leads, dome; 2.84 mm tall."""
    m = Model()
    m.box(0, 0, 0, 7.0, 7.6, 1.6, WHITE)
    m.box(0, 0, 1.6, 6.2, 6.6, 1.24, BLACK)
    for x in (-2.54, 0, 2.54):
        for s in (-1, 1):
            m.box(x, s * 3.6, 0, 1.0, 0.6, 0.6, GOLD)
    m.cyl(-2.4, -2.6, 2.84, 0.3, 0.01, DOT)
    return m


def srp7028a():
    """Bourns SRP7028A: 7.3 x 6.6 x 2.8, terminals on the X ends."""
    m = Model()
    m.box(0, 0, 0, 7.3, 6.6, 2.8, GREY)
    for s in (-1, 1):
        m.box(s * 3.0, 0, 0, 1.4, 4.0, 0.15, PIN)
    return m


def si570():
    """Si570/Si571 7 x 5 mm: ceramic base and a metal lid, 1.65 mm."""
    m = Model()
    m.box(0, 0, 0, 7.0, 5.0, 0.8, WHITE)
    m.box(0, 0, 0.8, 6.6, 4.6, 0.85, METAL)
    for x in (-2.54, 0, 2.54):
        for s in (-1, 1):
            m.box(x, s * 2.1, 0, 1.2, 0.9, 0.05, GOLD)
    return m


def pj102ah():
    """CUI PJ-102AH barrel jack: 9.0 wide, 14.4 deep, 11 tall; the opening at the footprint's +Y end."""
    m = Model()
    m.box(0, 6.8, 0, 9.0, 14.4, 11.0, BLACK)
    m.cyl(0, 14.0 + 0.05, 5.5 - 3.25, 3.25, 0.1, GREY, axis="y")     # the opening, a darker disc
    m.cyl(0, 14.0 + 0.1, 5.5 - 1.0, 1.0, 0.1, PIN, axis="y")         # the centre pin
    return m


def dq3005():
    """Mini-Circuits DQ case (DQ3005 switch): 3.0 x 3.0 x 0.9 QFN-like, 4 pins a side."""
    return qfn(3.0, 4, 0.65, 0.9)


def hr911130c():
    """Hanrun HR911130C RJ45 with magnetics and LEDs: 15.9 x 21.3 x 13.5 shield, opening at the
    footprint's -Y end (the board edge)."""
    m = Model()
    m.box(0, 0.0, 0, 15.9, 21.3, 13.5, METAL)
    m.box(0, -10.66, 1.5, 11.7, 0.1, 8.0, BLACK)                     # the socket
    m.box(0, -10.70, 6.5, 6.0, 0.1, 3.0, (0.02, 0.02, 0.02, 0.1))
    for x, col in ((-6.3, GREEN), (6.3, AMBER)):
        m.box(x, -10.7, 10.8, 2.6, 0.12, 1.8, col)
    return m


def bm20b():
    """Hirose BM20B(0.8)-34DP header, the adapter's half: 8.2 x 1.8, 0.6 tall."""
    m = Model()
    m.box(0, 0, 0, 8.2, 1.8, 0.6, BEIGE)
    for k in range(17):
        x = -3.2 + k * 0.4
        for s in (-1, 1):
            m.box(x, s * 0.78, 0, 0.18, 0.3, 0.62, GOLD)
    return m


# file name -> builder
MODELS = {
    "QFN-20-1EP_3.5x3.5mm_P0.5mm.wrl": lambda: qfn(3.5, 5, 0.5, 0.9),
    "QFN-48-1EP_6x6mm_P0.4mm.wrl": lambda: qfn(6.0, 12, 0.4, 0.85, pin_w=0.2),
    "LFCSP-56-1EP_8x8mm_P0.5mm.wrl": lambda: qfn(8.0, 14, 0.5, 0.85),
    "Mini-Circuits_CD542_H2.84mm.wrl": cd542,
    "Fuse_1812_4532Metric.wrl": lambda: chip(4.5, 3.2, 1.6, (0.55, 0.45, 0.30, 0.3), 0.6),
    "L_Bourns_SRP7028A.wrl": srp7028a,
    "Oscillator_SI570_SI571.wrl": si570,
    "BarrelJack_CUI_PJ-102AH.wrl": pj102ah,
    "MiniCircuits_DQ3005.wrl": dq3005,
    "RJ45_Hanrun_HR911130C.wrl": hr911130c,
    "Hirose_BM20B_0.8_34DP.wrl": bm20b,
}

# footprint (lib:name) -> model path: library models of the same package, or ours
ASSIGN = {
    "Package_BGA:Xilinx_FTG256": STOCK + "Package_BGA.3dshapes/BGA-256_17.0x17.0mm_Layout16x16_P1.0mm_Ball0.5mm_Pad0.4mm_NSMD.step",
    "Package_SO:Texas_HSOP-8-1EP_3.9x4.9mm_P1.27mm": STOCK + "Package_SO.3dshapes/HSOP-8-1EP_3.9x4.9mm_P1.27mm_EP2.41x3.1mm.step",
    "Package_DFN_QFN:QFN-48-1EP_7x7mm_P0.5mm_EP5.6x5.6mm": STOCK + "Package_DFN_QFN.3dshapes/QFN-48-1EP_7x7mm_P0.5mm_EP5.15x5.15mm.step",
    "kv260-ias2rf:LFCSP-32-1EP_5x5mm_P0.5mm_EP2.7x2.7mm": STOCK + "Package_CSP.3dshapes/LFCSP-32-1EP_5x5mm_P0.5mm_EP3.6x3.6mm.step",
    "Package_DFN_QFN:QFN-20-1EP_3.5x3.5mm_P0.5mm_EP2x2mm": PRJ + "QFN-20-1EP_3.5x3.5mm_P0.5mm.wrl",
    "Package_DFN_QFN:QFN-48-1EP_6x6mm_P0.4mm_EP4.4x4.4mm": PRJ + "QFN-48-1EP_6x6mm_P0.4mm.wrl",
    "kv260-ias2rf:LFCSP-56-1EP_8x8mm_P0.5mm_EP5.1x5.1mm": PRJ + "LFCSP-56-1EP_8x8mm_P0.5mm.wrl",
    "RF_Mini-Circuits:Mini-Circuits_CD542_H2.84mm": PRJ + "Mini-Circuits_CD542_H2.84mm.wrl",
    "Fuse:Fuse_1812_4532Metric": PRJ + "Fuse_1812_4532Metric.wrl",
    "Inductor_SMD:L_Bourns_SRP7028A_7.3x6.6mm": PRJ + "L_Bourns_SRP7028A.wrl",
    "Oscillator:Oscillator_SMD_SI570_SI571_Standard": PRJ + "Oscillator_SI570_SI571.wrl",
    "Connector_BarrelJack:BarrelJack_CUI_PJ-102AH_Horizontal": PRJ + "BarrelJack_CUI_PJ-102AH.wrl",
    "kv260-ias2rf:MiniCircuits_DQ3005": PRJ + "MiniCircuits_DQ3005.wrl",
    "kv260-ias2rf:RJ45_Hanrun_HR911130C": PRJ + "RJ45_Hanrun_HR911130C.wrl",
    "kv260-ias2rf:J-BM20B(0.8)-34DP": PRJ + "Hirose_BM20B_0.8_34DP.wrl",
}

MODEL_BLOCK = ("(model \"{p}\"\n{i}\t(offset\n{i}\t\t(xyz 0 0 0)\n{i}\t)\n{i}\t(scale\n{i}\t\t(xyz 1 1 1)\n{i}\t)\n"
               "{i}\t(rotate\n{i}\t\t(xyz 0 0 0)\n{i}\t)\n{i})")


def set_model(body, path, indent):
    """body: a footprint without its closing paren. Its model(s) replaced by one, at the end."""
    body = re.sub(r"\n" + indent + r"\(model \"[^\"]*\".*?\n" + indent + r"\)", "", body, flags=re.S)
    return body.rstrip() + "\n" + indent + MODEL_BLOCK.format(p=path, i=indent)


def patch_board():
    t = open(BOARD, encoding="utf-8").read()
    n = 0

    def fix(m):
        nonlocal n
        name = m.group(1)
        if name not in ASSIGN:
            return m.group(0)
        n += 1
        return set_model(m.group(0)[:-3], ASSIGN[name], "\t\t") + "\n\t)"
    t = re.sub(r'\n\t\(footprint "([^"]+)".*?\n\t\)', fix, t, flags=re.S)
    open(BOARD, "w", encoding="utf-8", newline="\n").write(t)
    return n


def patch_library():
    done = []
    for name, path in ASSIGN.items():
        lib, fp = name.split(":", 1)
        if lib != "kv260-ias2rf":
            continue
        f = os.path.join(LIB, fp + ".kicad_mod")
        if not os.path.exists(f):
            continue
        t = open(f, encoding="utf-8").read().rstrip()
        assert t.endswith(")")
        t = set_model(t[:-1], path, "\t") + "\n)"
        open(f, "w", encoding="utf-8", newline="\n").write(t + "\n")
        done.append(fp)
    return done


def main():
    os.makedirs(OUT, exist_ok=True)
    for f, build in MODELS.items():
        open(os.path.join(OUT, f), "w", newline="\n").write(build().wrl())
    print(f"{len(MODELS)} models in {os.path.relpath(OUT, ROOT)}")
    if "--models" in sys.argv:
        return 0
    print(f"board: {patch_board()} footprints pointed at a model")
    print("library:", ", ".join(patch_library()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
