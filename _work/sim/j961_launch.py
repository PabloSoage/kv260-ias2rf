"""j961_launch.py CASE  (openEMS 0.37, inside the rfsim env: ~/rfsim.sh python j961_launch.py CASE)

Rev08 phase 6: the launch of J961 (the VHF/UHF front end's SMA) as it is on the board, on the 8-layer stack
JLC08161H-2116C, with the method of SIGNAL_INTEGRITY 2.1 (sma_launch.py, STACK=8). A through line: port 1 on a
0.2 mm microstrip standing in for the connector's coax, the SMA's 1.27 x 3.2 mm signal pad, then VU_ANT as
routed (0.2 mm on L1 over L2) past D1301 (PESD5V0F1BL, 0.5 pF), L1302's pad (the bias tee's 56 nH choke, its
pad only: the chokes are a circuit effect, see j961_plot.py) and C1301 (1 nF DC block, taken as a short), to
port 2. Board coordinates: pad 89.5..92.7, D1301 at x 94.6, L1302 at 95.75, C1301 97.32..98.84 (y = 121.3).

Every case has L2, L4 and L5 cleared under the pad (the keep-outs "J961 launch: L2-L6 clear under the signal
pad", x 89-93, y 120.25-122.35, as under J921; L3 and L6 carry no plane there): the pad references L7.

CASE:
  p5       the phase 5 copper: the SMA's ground legs (1.35 x 3.7 mm, y +-2.825 mm) on L1 with the GND vias near
           them as placed, (89.8, 118.05) inside the north leg, (89.8, 123.05) and (89.8, 125.55) beside the
           south one; D1301's GND pad with no via of its own (nearest GND vias (96.55, 122.1), (97.85, 122.35));
           no L1 ground pour, no via fence
  fixed    phase 6: three GND vias in each leg (x 90.5, 91.5, 92.5, as J921's), fence vias at (93.3, 120.5),
           (93.3, 122.1) and (95.25, 122.1) (the last on D1301's ground), and the L1 pour "L1 VU_ANT GND"
           (0.5 mm clearance) on the legs and south of the line
  j921     the other SMAs' pattern on the same stack (J921): legs and leg vias as fixed, fence pairs 0.8 mm off
           the line at x 93.3, 95.3 and 97.3, the pour both sides; a bare line, no parts
  line     the 0.2 mm line straight through, no pad, no parts: the set-up's own floor
Writes docs/sim/j961_<CASE>.csv (f, |S11| dB, |S21| dB). FR-4 loss tan d = 0.02 at 3 GHz, as
conductivity. Stops at -40 dB energy or 400k steps. Mesh: transverse cells (y, z) at most 40 um in the board and
near the PML, lumped elements above the metal in priority.
"""
import os, sys, numpy as np
from CSXCAD import ContinuousStructure
from openEMS import openEMS
from openEMS.physical_constants import C0

case = sys.argv[1]; fmax = 3e9
here = os.path.dirname(os.path.abspath(__file__))
sim = os.path.join("/tmp", "j961_" + case + os.environ.get("TAG", ""))
# 8-layer stack, um, L7 at z = 0 (sma_launch.py, STACK=8)
zB, z6, zM, zL4, zL3, zL2, zL1 = 0.0, 145.2, 526.2, 671.4, 1052.4, 1197.6, 1317.0
W, PW, PL = 200.0, 1270.0, 3200.0
X0, XP0 = 0.0, 10000.0; XP1 = XP0 + PL
bx = lambda x: round(XP0 + (x - 89.5) * 1000.0)           # board x (mm) -> model x (um); y: board y - 121.3
by = lambda y: round((y - 121.3) * 1000.0)
XD, XL, XC0, XC1 = bx(94.6), bx(95.75), bx(97.32), bx(98.84)
X1 = XC1 + 10000.0
YB = float(os.environ.get("YB", "5500"))       # the outermost via (89.8, 125.55) 1.25 mm inside the PML side

FDTD = openEMS(EndCriteria=1e-4, NrTS=int(os.environ.get("NRTS", "400000")))
TAU = 1 / (np.pi * 1.2e9 * np.sqrt(2)); T0 = 5 * TAU      # derivative of a Gaussian (no DC), peak 1.2 GHz
FDTD.SetCustomExcite(f"-(t-{T0})/{TAU}*exp(-((t-{T0})/{TAU})^2)", 1.2e9, fmax)
FDTD.SetBoundaryCond(['PML_8', 'PML_8', 'PML_8', 'PML_8', 'PEC', 'PML_8'])
CSX = ContinuousStructure(); FDTD.SetCSX(CSX)
mesh = CSX.GetGrid(); mesh.SetDeltaUnit(1e-6)

EPS0, TAND, F0 = 8.854e-12, 0.02, 3e9
def kappa(er): return 2 * np.pi * F0 * EPS0 * er * TAND
for k, (z0, z1, er) in enumerate(((zB, z6, 4.17), (z6, zM, 4.29), (zM, zL4, 4.17), (zL4, zL3, 4.29),
                                  (zL3, zL2, 4.17), (zL2, zL1, 4.29))):
    CSX.AddMaterial(f"d8_{k}", epsilon=er, kappa=kappa(er)).AddBox([X0, -YB, z0], [X1, YB, z1], priority=1)
gnd = CSX.AddMetal("gnd"); l4 = CSX.AddMetal("l4"); sig = CSX.AddMetal("sig")
for z in (zB, zM, zL2):
    gnd.AddBox([X0, -YB, z], [X1, YB, z], priority=10)          # L7, L5, L2
l4.AddBox([X0, -YB, zL4], [X1, YB, zL4], priority=10)           # L4 (+3V3_D), not tied to GND
cut = [bx(89.0), bx(93.0)]
if case != "line":
    for z in (zL2, zL4, zM):
        CSX.AddMaterial(f"hole{z}", epsilon=4.17, kappa=kappa(4.17)).AddBox([cut[0], by(120.25), z],
                                                                             [cut[1], by(122.35), z], priority=20)
# vias (GND, L1 to L7 through a 0.35 mm antipad in L4), board positions
vias = [(89.8, 118.05), (89.8, 123.05), (89.8, 125.55), (96.55, 122.1), (97.85, 122.35)]
LEGV = [(x, y) for y in (118.475, 124.125) for x in (90.5, 91.5, 92.5)]
if case == "fixed":
    vias += LEGV + [(93.3, 120.5), (93.3, 122.1), (95.25, 122.1)]
if case == "j921":
    vias += LEGV + [(x, y) for x in (93.3, 95.3, 97.3) for y in (120.5, 122.1)]
# the L1 ground pour (0.5 mm clearance from VU_ANT's copper), board rectangles x0, y0, x1, y1
POUR = {"fixed": [(89.3, 117.6, 93.6, 120.165), (89.3, 122.435, 93.6, 125.0), (93.6, 122.15, 95.7, 122.8),
                  (96.8, 122.15, 97.9, 123.3)],
        "j921": [(89.3, 117.6, 93.6, 120.165), (89.3, 122.435, 93.6, 125.0), (93.2, 117.6, 99.0, 120.7),
                 (93.2, 121.9, 99.0, 125.0)]}.get(case, [])
vias = [(bx(x), by(y)) for x, y in vias]
for k, (x, y) in enumerate(vias):
    CSX.AddMaterial(f"ap{k}", epsilon=4.17, kappa=kappa(4.17)).AddBox([x - 350, y - 350, zL4], [x + 350, y + 350, zL4],
                                                                     priority=25)
    gnd.AddCylinder([x, y, zB], [x, y, zL1], 100, priority=30)
for x0, y0, x1, y1 in POUR:
    gnd.AddBox([bx(x0), by(y0), zL1], [bx(x1), by(y1), zL1], priority=10)
if case != "line":
    # the SMA's ground legs on L1 (pad 2, rotated with the part: centre x 91.35, 3.7 along x, 1.35 across)
    for yc in (by(118.475), by(124.125)):
        gnd.AddBox([bx(91.35) - 1850, yc - 675, zL1], [bx(91.35) + 1850, yc + 675, zL1], priority=10)
    # the signal pad
    sig.AddBox([XP0, -PW / 2, zL1], [XP1, PW / 2, zL1], priority=15)
if case in ("p5", "fixed"):
    # D1301: its pad on the line (0.6 x 0.3) and its GND pad 0.7 mm south (0.7 x 0.4, no via of its own),
    # 0.5 pF from the line pad to L2 (data sheet maximum, as in SIGNAL_INTEGRITY 7.1)
    sig.AddBox([XD - 300, -150, zL1], [XD + 300, 150, zL1], priority=16)
    gnd.AddBox([XD - 350, by(122.0) - 200, zL1], [XD + 350, by(122.0) + 200, zL1], priority=16)
    CSX.AddLumpedElement("esd", ny="z", caps=True, C=0.5e-12).AddBox([XD - 50, -50, zL2], [XD + 50, 50, zL1],
                                                                      priority=40)
    # L1302's pad on the line (0.64 x 0.59), C1301 as metal across both pads (0.62 wide, taken as 0.59)
    sig.AddBox([XL - 320, -295, zL1], [XL + 320, 295, zL1], priority=16)
    sig.AddBox([XC0, -295, zL1], [XC1, 295, zL1], priority=16)
# the line from the pad to port 2 (and from port 1 to the pad)
sig.AddBox([X0, -W / 2, zL1], [X1, W / 2, zL1], priority=14)

# mesh: x follows the parts, y and z at most 40 um in the board, near the line and at the PML
res_x = 150.0
xl = [X0, X1, XP0, XP1, cut[0], cut[1], XD - 350, XD - 300, XD - 50, XD + 50, XD + 300, XD + 350, XL - 320, XL + 320,
      XC0, XC1, bx(91.35) - 1850, bx(91.35) + 1850] + [v[0] + d for v in vias for d in (-100, 100)]
xl += [bx(v) for r in POUR for v in (r[0], r[2])]
mesh.AddLine('x', np.unique(np.round(xl))); mesh.SmoothMeshLines('x', res_x)
yl = [0, 50, -50, W / 2, -W / 2, 150, -150, 295, -295, PW / 2, -PW / 2, by(120.25), by(122.35), YB, -YB,
      by(122.0) - 200, by(122.0) + 200, by(118.475) - 675, by(118.475) + 675, by(124.125) - 675, by(124.125) + 675]
yl += [v[1] + d for v in vias for d in (-100, 100)] + [by(v) for r in POUR for v in (r[1], r[3])]
mesh.AddLine('y', np.unique(np.round(yl))); mesh.SmoothMeshLines('y', 40)
zl = [zB, z6, zM, zL4, zL3, zL2, zL1] + list(np.linspace(zL2, zL1, 4)) + [zL1 + 1500]
mesh.AddLine('z', zl); mesh.SmoothMeshLines('z', 40)
p1 = FDTD.AddMSLPort(1, sig, [X0, -W / 2, zL1], [XP0 - 3000, W / 2, zL2], 'x', 'z', excite=-1, Feed_R=50,
                     FeedShift=1000, MeasPlaneShift=3000, priority=15)
p2 = FDTD.AddMSLPort(2, sig, [X1, -W / 2, zL1], [XC1 + 4000, W / 2, zL2], 'x', 'z', Feed_R=50,
                     MeasPlaneShift=3000, priority=15)
if os.environ.get("DRY"):
    for ax in "xyz":
        ln = np.array(mesh.GetLines(ax)); d = np.diff(ln); i = d.argmin()
        print(ax, len(ln), "min %.2f um at %.1f" % (d[i], ln[i]), "max %.1f" % d.max())
    sys.exit()
FDTD.Run(sim, cleanup=True, verbose=0, numThreads=int(os.environ.get("NTHREADS", "8")))
f = np.linspace(0.1e9, fmax, 291)
for p in (p1, p2): p.CalcPort(sim, f, ref_impedance=50)
s11 = p1.uf_ref / p1.uf_inc; s21 = p2.uf_ref / p1.uf_inc
out = os.path.join(os.path.dirname(os.path.dirname(here)), "docs", "sim", f"j961_{case}.csv")
np.savetxt(out, np.c_[f, 20 * np.log10(abs(s11)), 20 * np.log10(abs(s21))], delimiter=",",
           header="f_Hz,S11_dB,S21_dB", comments="")
for fq in (0.15e9, 0.5e9, 1.0e9, 1.1e9, 2.0e9, 3.0e9):
    k = np.argmin(abs(f - fq))
    print(f"{case}: {fq/1e9:.2f} GHz  S11 {20*np.log10(abs(s11[k])):6.1f} dB  S21 {20*np.log10(abs(s21[k])):5.2f} dB")
