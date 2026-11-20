#!/usr/bin/env python3
"""
PSU board in its enclosure (psu_case.py): does the case need vents, and how hot do the board and the shell run?

Coupled steady model:
  - The board: psu_thermal.py's 2-D model (0.5 mm cells, its copper and FR4, h = 10 W/m2K convection + 5 W/m2K
    radiation from both faces), with the losses recomputed at the temperature the board actually sees inside the
    case (psu_design.operating_point takes it), instead of psu_thermal's fixed 70 C.
  - The shell: 3-D conduction in the printed tray and lid (gmsh, linear tetrahedra, about 1.5 mm), bonded where the
    lid sits on the walls.
      - Outside: natural convection on each face by its orientation (vertical 1.42 (dT/L)^0.25, facing up
        1.32 (dT/L)^0.25, facing down 0.59 (dT/L)^0.25 [C]) plus radiation, emissivity 0.9 (black print [E]),
        to the surroundings at ambient.
      - Inside: convection to one well-mixed air node; ribs in the honeycomb at half that, as the air in a cell
        barely moves [E].
  - The board's convective share (10 of 15) heats the air node. Its radiative share (5 of 15) lands on the lid's
    underside and the floor under the board, spread by the board's own temperature map, so the hot spots above
    U2, Q3 and L1 appear on the lid.
  - Vents (as built): stack flow through the low row, up the 2.5 mm gaps beside the board, out of the high row:
    Q = Cd A_eff sqrt(2 g H dT / T), 1/A_eff^2 = sum 1/(Cd A)^2 over the three in series, Cd 0.6 for the
    honeycomb's orifices and 0.8 for the gaps [E], H = the rows' 13.8 mm.
  - Sealed: the same case with its vents closed (taped, or printed without them).
  - The board sees T_env = (10 T_air + 5 T_lid,floor under it) / 15 and the loop runs until T_env settles.

Cases as psu_thermal.py: 13.5 V and 24 V at the worst load, 6.0 V at the worst load (a weak battery: the most
loss), and the Level IV cranking (10 s at 6.5 V) from the 13.5 V steady state, the case's own state frozen
(its time constant is many minutes). Each at 70 C ambient, then an ambient sweep for the ratings.

Writes docs/sim/psu_case_thermal.json, docs/sim/psu_case_thermal.png and the shell's temperature as PLY
(_work/psu/cache/psu_case_T_{tray,lid}_<case>.ply) for psu_case_render.py's thermal view.

Usage:  python _work/psu/psu_case_thermal.py
"""
import json
import math
import os
import sys
import time

import gmsh
import numpy as np
from scipy.sparse import coo_matrix, csr_matrix, diags
from scipy.sparse.linalg import cg, spsolve
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                                   # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import psu_case as G                                              # noqa: E402
import psu_thermal as PT                                          # noqa: E402
import psu_params as P                                            # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
CACHE = os.path.join(ROOT, "_work", "psu", "cache")
OUT_JSON = os.path.join(ROOT, "docs", "sim", "psu_case_thermal.json")
OUT_PNG = os.path.join(ROOT, "docs", "sim", "psu_case_thermal.png")

SIG = 5.670e-8
EPS = 0.9
K_SHELL = {"PETG-CF": 0.25, "ASA": 0.17}          # W/mK, solid perimeters [I]
HDT = {"PETG-CF": 74.0, "ASA": 100.0}             # C at 0.45 MPa (fea_case.py's table)
SHELL = "ASA"
CD_ORIFICE, CD_GAP = 0.6, 0.8
T_AMB = 70.0
SWEEP = [25.0, 40.0, 55.0, 70.0, 85.0]
FOCUS = ("U2", "Q3", "Q1", "U4", "L1", "C17")
P_MAX = P.VOUT * (P.I_ADAPTER_MAX + P.I_KV_LIMIT)
CASES = (("13.5 V, worst load", 13.5), ("24 V jump start, worst load", 24.0), ("6.0 V weak battery, worst load", 6.0))


# ---- mesh ----------------------------------------------------------------------------------------------------------
def build_mesh(h=1.6):
    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.model.add("thermal")
    b = G.Builder()
    tray, lid = b.tray(), b.lid()
    out, _ = gmsh.model.occ.fragment(tray, lid)
    gmsh.model.occ.synchronize()
    gmsh.option.setNumber("Mesh.MeshSizeMax", h)
    gmsh.option.setNumber("Mesh.MeshSizeMin", 0.5)
    gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 6)
    gmsh.option.setNumber("Mesh.Algorithm3D", 10)
    gmsh.model.mesh.generate(3)
    tags, xyz, _ = gmsh.model.mesh.getNodes()
    idx = np.full(int(tags.max()) + 1, -1)
    idx[tags.astype(int)] = np.arange(len(tags))
    xyz = xyz.reshape(-1, 3)
    tets, part = [], []
    for dim, tag in gmsh.model.getEntities(3):
        cz = gmsh.model.occ.getCenterOfMass(3, tag)[2]
        types, _, nodes = gmsh.model.mesh.getElements(3, tag)
        for t, n in zip(types, nodes):
            if t == 4:
                c = idx[n.astype(int)].reshape(-1, 4)
                tets.append(c)
                part += ["lid" if cz > 10.0 else "tray"] * len(c)
    gmsh.finalize()
    t = np.vstack(tets)
    used = np.unique(t)
    remap = -np.ones(len(xyz), int)
    remap[used] = np.arange(len(used))
    return xyz[used] * 1e-3, remap[t], np.array(part)          # metres


def stiffness(p, t, k):
    """P1 conduction matrix."""
    X = p[t]                                                      # (m, 4, 3)
    J = np.stack([X[:, 1] - X[:, 0], X[:, 2] - X[:, 0], X[:, 3] - X[:, 0]], axis=1)   # rows: edges
    det = np.linalg.det(J)
    Ji = np.linalg.inv(J)                                         # columns: gradients of phi1..3
    g = np.concatenate([-Ji.sum(axis=2, keepdims=True), Ji], axis=2)   # (m, 3, 4)
    vol = np.abs(det) / 6
    Ke = k * vol[:, None, None] * np.einsum("mki,mkj->mij", g, g)
    rows = np.repeat(t, 4, axis=1).ravel()
    cols = np.tile(t, (1, 4)).ravel()
    return coo_matrix((Ke.ravel(), (rows, cols)), shape=(len(p), len(p))).tocsr(), vol


def boundary(p, t):
    f = np.vstack([t[:, [1, 2, 3]], t[:, [0, 3, 2]], t[:, [0, 1, 3]], t[:, [0, 2, 1]]])
    opp = np.concatenate([t[:, 0], t[:, 1], t[:, 2], t[:, 3]])
    owner = np.tile(np.arange(len(t)), 4)
    key = np.sort(f, axis=1)
    _, inv, cnt = np.unique(key, axis=0, return_inverse=True, return_counts=True)
    keep = cnt[inv.ravel()] == 1
    f, opp, owner = f[keep], opp[keep], owner[keep]
    a, b, c = p[f[:, 0]], p[f[:, 1]], p[f[:, 2]]
    n = np.cross(b - a, c - a)
    flip = np.einsum("ij,ij->i", n, p[opp] - a) > 0
    f[flip] = f[flip][:, [0, 2, 1]]
    n[flip] *= -1
    area = np.linalg.norm(n, axis=1) / 2
    n /= (2 * area)[:, None]
    return f, n, area, (a + b + c) / 3, owner


class Shell:
    def __init__(self):
        t0 = time.time()
        self.p, self.t, self.part = build_mesh()
        self.K, vol = stiffness(self.p, self.t, K_SHELL[SHELL])
        self.f, self.n, self.A, self.c, owner = boundary(self.p, self.t)
        self.fpart = self.part[owner]
        mm = self.c * 1e3
        kx, ky, z = mm[:, 0], -mm[:, 1], mm[:, 2]
        tol = 0.05
        self.inner = ((kx > G.IX0 + tol) & (kx < G.IX1 - tol) & (ky > G.IY0 + tol) & (ky < G.IY1 - tol) &
                      (z > G.Z_FLOOR - tol) & (z < G.Z_CEIL + tol))
        self.outer = ~self.inner
        nz = self.n[:, 2]
        on_board = (kx > G.BX0) & (kx < G.BX1) & (ky > G.BY0) & (ky < G.BY1)
        self.rad_top = self.inner & on_board & (nz < -0.5) & (z > G.BT)
        self.rad_bot = self.inner & on_board & (nz > 0.5) & (z < 0.0)
        in_cells = self.inner & (np.abs(nz) < 0.5) & ((z < G.Z_FLOOR + G.FLOOR_RIB) | (z > G.Z_CEIL - G.LID_RIB))
        self.h_in_scale = np.where(in_cells, 0.5, 1.0)
        self.kind = np.where(nz > 0.7, 1, np.where(nz < -0.7, 2, 0))      # 0 vertical, 1 up, 2 down
        self.bij = (np.clip(((kx - G.BX0) / 0.5).astype(int), 0, PT.NX - 1),
                    np.clip(((ky - G.BY0) / 0.5).astype(int), 0, PT.NY - 1))
        self.N = len(self.p)
        self.case_mass_g = float(vol.sum() * 1.05e6)
        # face mass pattern
        self.fr = np.repeat(self.f, 3, axis=1).ravel()
        self.fc = np.tile(self.f, (1, 3)).ravel()
        self.Tw = None
        geom = json.load(open(os.path.join(CACHE, "psu_case_geom.json")))
        self.A_lo = geom["vent_area_low_mm2"] * 1e-6
        self.A_hi = geom["vent_area_high_mm2"] * 1e-6
        self.A_gap = 2 * (G.BX1 - G.BX0) * (G.BY0 - G.IY0) * 1e-6
        self.H_ch = geom["chimney_mm"] * 1e-3
        Lc = (G.OX1 - G.OX0) * (G.OY1 - G.OY0) / (2 * ((G.OX1 - G.OX0) + (G.OY1 - G.OY0))) * 1e-3
        self.L = {0: (G.Z_TOP - G.Z_BOT) * 1e-3, 1: Lc, 2: Lc}
        print(f"shell mesh: {len(self.t)} tets, {self.N} nodes, {len(self.f)} faces "
              f"({self.inner.sum()} inside, {self.rad_top.sum()}+{self.rad_bot.sum()} take the board's radiation), "
              f"{time.time() - t0:.0f} s", flush=True)

    def face_mass(self, w):
        """sum over faces of w_f * int(phi_i phi_j) (P1 triangle: A/12 (1 + delta_ij))."""
        m = np.array([2, 1, 1, 1, 2, 1, 1, 1, 2], float) / 12.0
        vals = (w * self.A)[:, None] * m[None, :]
        return coo_matrix((vals.ravel(), (self.fr, self.fc)), shape=(self.N, self.N)).tocsr()

    def face_load(self, q):
        """int(q phi_i) with q per face (W/m2)."""
        out = np.zeros(self.N)
        np.add.at(out, self.f.ravel(), np.repeat(q * self.A / 3, 3))
        return out

    def solve(self, Q_conv, q_rad, T_amb, vented, Tw0=None, Ta0=None):
        """Shell temperatures (per node) and the air's for a given heat input; h's iterated on the result."""
        Tw = np.full(self.N, T_amb + 5.0) if Tw0 is None else Tw0.copy()
        Ta = T_amb + 8.0 if Ta0 is None else Ta0
        F = self.face_load(q_rad)
        x = np.append(Tw, Ta)
        for it in range(6):
            Tf = Tw[self.f].mean(axis=1)
            dT = np.maximum(np.abs(Tf - T_amb), 0.05)
            coef = np.choose(self.kind, [1.42, 1.32, 0.59])
            Lf = np.choose(self.kind, [self.L[0], self.L[1], self.L[2]])
            hc = coef * (dT / Lf) ** 0.25
            T1, T2 = Tf + 273.15, T_amb + 273.15
            hr = EPS * SIG * (T1 * T1 + T2 * T2) * (T1 + T2)
            # vent cell walls and connector openings: convection only (they see the case itself)
            h_out = np.where(self.outer, hc + hr, 0.0)
            dTi = np.maximum(np.abs(Ta - Tf), 0.05)
            h_in = np.where(self.inner, 1.42 * (dTi / ((G.Z_CEIL - G.Z_FLOOR) * 1e-3)) ** 0.25 * self.h_in_scale, 0.0)
            M_out = self.face_mass(h_out)
            M_in = self.face_mass(h_in)
            c_in = self.face_load(h_in)                               # int(h_in phi_i)
            if vented and Ta > T_amb:
                a_eff = 1 / math.sqrt(1 / (CD_ORIFICE * self.A_lo) ** 2 + 1 / (CD_GAP * self.A_gap) ** 2 +
                                      1 / (CD_ORIFICE * self.A_hi) ** 2)
                v = math.sqrt(2 * 9.81 * self.H_ch * (Ta - T_amb) / (T_amb + 273.15))
                rho = 353.0 / (T_amb + 273.15)
                G_v = rho * a_eff * v * 1007.0
            else:
                G_v = 0.0
            Kw = self.K + M_out + M_in
            from scipy.sparse import bmat
            A = bmat([[Kw, csr_matrix(-c_in[:, None])],
                      [csr_matrix(-c_in[None, :]), csr_matrix([[c_in.sum() + G_v]])]], format="csr")
            rhs = np.append(F + self.face_load(h_out * T_amb), Q_conv + G_v * T_amb)
            Mpre = diags(1.0 / A.diagonal())
            x, info = cg(A, rhs, x0=x, rtol=1e-9, maxiter=4000, M=Mpre)
            if info:
                x = spsolve(A.tocsc(), rhs)
            Tw_new, Ta_new = x[:-1], x[-1]
            done = np.abs(Tw_new - Tw).max() < 0.02 and abs(Ta_new - Ta) < 0.02
            Tw, Ta = Tw_new, Ta_new
            if done and it:
                break
        Tf = Tw[self.f].mean(axis=1)
        q_out = float((h_out * self.A * (Tf - T_amb)).sum())
        q_vent = G_v * (Ta - T_amb)
        return Tw, Ta, dict(G_vent_W_K=G_v, vent_W=q_vent, surface_W=q_out,
                            vent_flow_l_min=(G_v / (353.0 / (T_amb + 273.15) * 1007.0)) * 6e4 if G_v else 0.0)


def board_state(vin, T_env, A, hconv):
    PT.T_AIR = T_env
    loss, op = PT.losses(vin, P_MAX)
    T = PT.solve_steady(PT.grid_sources(loss), A, hconv)
    return loss, T


def coupled(shell, vin, T_amb, vented, A, hconv, warm=None):
    T_env = T_amb + 10.0 if warm is None else warm["T_env"]
    Tw, Ta = (None, None) if warm is None else (warm["Tw"], warm["Ta"])
    for k in range(40):
        loss, T = board_state(vin, T_env, A, hconv)
        Q = sum(loss.values())
        ex = np.maximum(T - T_env, 0.0)
        w_top = np.where(shell.rad_top, ex[shell.bij] * shell.A, 0.0)
        w_bot = np.where(shell.rad_bot, ex[shell.bij] * shell.A, 0.0)
        q_face = np.zeros(len(shell.A))
        q_rad = Q * 5.0 / 15.0
        if w_top.sum() > 0:
            q_face += 0.5 * q_rad * w_top / w_top.sum() / shell.A
        if w_bot.sum() > 0:
            q_face += 0.5 * q_rad * w_bot / w_bot.sum() / shell.A
        Tw, Ta, flow = shell.solve(Q * 10.0 / 15.0, q_face, T_amb, vented, Tw, Ta)
        rec = shell.rad_top | shell.rad_bot
        Tf = Tw[shell.f].mean(axis=1)
        T_rec = float((Tf[rec] * shell.A[rec]).sum() / shell.A[rec].sum())
        new = (10.0 * Ta + 5.0 * T_rec) / 15.0
        if abs(new - T_env) < 0.03:
            T_env = new
            break
        T_env = T_env + 0.7 * (new - T_env)
    loss, T = board_state(vin, T_env, A, hconv)
    parts = PT.junctions(T, loss)
    Tf = Tw[shell.f].mean(axis=1)
    lid = shell.fpart == "lid"
    out = dict(T_amb_C=T_amb, vented=vented, T_air_inside_C=float(Ta), T_env_board_C=float(T_env),
               total_loss_W=float(sum(loss.values())), board_max_C=float(T.max()),
               shell_max_C=float(Tw.max()), shell_mean_outer_C=float((Tf[shell.outer] * shell.A[shell.outer]).sum() /
                                                                     shell.A[shell.outer].sum()),
               lid_max_C=float(Tf[lid].max()), iterations=k + 1, **flow,
               parts={r: {kk: (round(vv, 2) if isinstance(vv, float) else vv) for kk, vv in parts[r].items()}
                      for r in FOCUS})
    c = parts["C17"]["junction_C"]
    out["C17_life_vs_rated"] = 2 ** ((105.0 - c) / 10.0)
    return out, dict(T_env=T_env, Tw=Tw, Ta=Ta, T=T, loss=loss)


def write_ply(fn, p, f, Tnode, sel, lo, hi):
    cm = matplotlib.colormaps["inferno"]
    ff = f[sel]
    used = np.unique(ff)
    remap = -np.ones(len(p), int)
    remap[used] = np.arange(len(used))
    # 0..0.85 of inferno: its top end reads white in the renders
    rgb = (np.array(cm(0.85 * np.clip((Tnode[used] - lo) / (hi - lo), 0, 1)))[:, :3] * 255).astype(int)
    with open(fn, "w") as fh:
        fh.write(f"ply\nformat ascii 1.0\nelement vertex {len(used)}\nproperty float x\nproperty float y\n"
                 f"property float z\nproperty uchar red\nproperty uchar green\nproperty uchar blue\n"
                 f"element face {len(ff)}\nproperty list uchar int vertex_indices\nend_header\n")
        for k, i in enumerate(used):
            fh.write(f"{p[i, 0]:.6f} {p[i, 1]:.6f} {p[i, 2]:.6f} {rgb[k, 0]} {rgb[k, 1]} {rgb[k, 2]}\n")
        for a, b, c in remap[ff]:
            fh.write(f"3 {a} {b} {c}\n")


def main():
    os.makedirs(CACHE, exist_ok=True)
    A, hconv = PT.operator()
    shell = Shell()
    res = {"model": dict(shell_material=SHELL, k_shell_W_mK=K_SHELL[SHELL], emissivity=EPS, Cd_orifice=CD_ORIFICE,
                         Cd_gap=CD_GAP, vent_area_low_mm2=shell.A_lo * 1e6, vent_area_high_mm2=shell.A_hi * 1e6,
                         gap_area_mm2=shell.A_gap * 1e6, chimney_mm=shell.H_ch * 1e3, tets=int(len(shell.t)),
                         nodes=int(shell.N), hdt_C=HDT, board_alone_ref="docs/sim/psu_thermal.json (70 C air)"),
           "at_70C": {}, "cranking": {}, "sweep": {}}
    states = {}
    for vented in (True, False):
        tag = "vented" if vented else "sealed"
        for name, vin in CASES:
            t0 = time.time()
            r, st = coupled(shell, vin, T_AMB, vented, A, hconv)
            res["at_70C"].setdefault(tag, {})[name] = r
            states[(tag, name)] = st
            print(f"{tag:7s} {name:32s} air {r['T_air_inside_C']:.1f}  env {r['T_env_board_C']:.1f}  shell max "
                  f"{r['shell_max_C']:.1f}  U2 {r['parts']['U2']['junction_C']:.1f}  Q3 "
                  f"{r['parts']['Q3']['junction_C']:.1f}  C17 {r['parts']['C17']['junction_C']:.1f}  vent "
                  f"{r['vent_W']:.2f} W  ({time.time() - t0:.0f} s)", flush=True)
        # cranking Level IV: the board's 10 s transient at 6.5 V from the 13.5 V state, the case frozen
        st = states[(tag, CASES[0][0])]
        PT.T_AIR = st["T_env"]
        l65, _ = PT.losses(6.5, P_MAX)
        Tc = PT.transient(PT.grid_sources(l65), st["T"], A, hconv)
        pj = PT.junctions(Tc, l65)
        res["cranking"][tag] = dict(T_env_board_C=st["T_env"], board_max_C=float(Tc.max()),
                                    parts={r: round(pj[r]["junction_C"], 2) for r in FOCUS})
    # shell temperature fields for the render: the worst steady case, vented, on one scale
    st = states[("vented", CASES[2][0])]
    lo, hi = T_AMB, float(st["Tw"].max())
    for prt in ("tray", "lid"):
        sel = (shell.fpart == prt)
        write_ply(os.path.join(CACHE, f"psu_case_T_{prt}_weak.ply"), shell.p, shell.f, st["Tw"], sel, lo, hi)
    st13 = states[("vented", CASES[0][0])]
    for prt in ("tray", "lid"):
        sel = (shell.fpart == prt)
        write_ply(os.path.join(CACHE, f"psu_case_T_{prt}_13v5.ply"), shell.p, shell.f, st13["Tw"], sel, lo, hi)
    res["render_scale_C"] = [lo, hi]

    # ambient sweep: 13.5 V (the car running) and 6.0 V (the worst), vented and sealed
    for vented in (True, False):
        tag = "vented" if vented else "sealed"
        for name, vin in (CASES[0], CASES[2]):
            rows, warm = [], None
            for ta in SWEEP:
                r, st = coupled(shell, vin, ta, vented, A, hconv, warm)
                warm = st
                rows.append(dict(T_amb_C=ta, T_env_board_C=r["T_env_board_C"], shell_max_C=r["shell_max_C"],
                                 U2=r["parts"]["U2"]["junction_C"], Q3=r["parts"]["Q3"]["junction_C"],
                                 C17=r["parts"]["C17"]["junction_C"], C17_life=r["C17_life_vs_rated"]))
            res["sweep"].setdefault(tag, {})[name] = rows
            print(tag, name, [(r_["T_amb_C"], round(r_["U2"], 1), round(r_["C17"], 1), round(r_["shell_max_C"], 1))
                              for r_ in rows], flush=True)

    def rating(rows, key, limit):
        xs = [r["T_amb_C"] for r in rows]
        ys = [r[key] for r in rows]
        return float(np.interp(limit, ys, xs)) if ys[-1] > limit else None

    res["ratings_max_ambient_C"] = {}
    for tag in ("vented", "sealed"):
        for name in (CASES[0][0], CASES[2][0]):
            rows = res["sweep"][tag][name]
            res["ratings_max_ambient_C"].setdefault(tag, {})[name] = dict(
                U2_125C=rating(rows, "U2", 125.0), Q3_150C=rating(rows, "Q3", 150.0),
                C17_105C=rating(rows, "C17", 105.0), shell_ASA_HDT_100C=rating(rows, "shell_max_C", HDT["ASA"]),
                shell_PETG_CF_HDT_74C=rating(rows, "shell_max_C", HDT["PETG-CF"]))
    ref = json.load(open(os.path.join(ROOT, "docs", "sim", "psu_thermal.json")))
    res["board_alone_70C"] = {n: {r: round(ref["cases"][n]["parts"][r]["junction_C"], 2) for r in FOCUS}
                              for n, _ in CASES}
    json.dump(res, open(OUT_JSON, "w"), indent=1)
    plot(res)
    print("wrote", OUT_JSON, OUT_PNG)


def plot(res):
    fig = plt.figure(figsize=(16, 9.6), dpi=110)
    fig.patch.set_facecolor("white")
    gs = fig.add_gridspec(2, 3, height_ratios=[1, 1], hspace=0.38, wspace=0.28)
    names = [n for n, _ in CASES]
    short = ["13.5 V", "24 V", "6.0 V"]
    cols = {"board alone": "#9aa5b1", "vented": "#2e7d32", "sealed": "#c62828"}
    limits = {"U2": 125, "Q3": 150, "C17": 105}
    for k, part in enumerate(("U2", "Q3", "C17")):
        ax = fig.add_subplot(gs[0, k])
        x = np.arange(3)
        for j, (lab, getter) in enumerate((
                ("board alone", lambda n: res["board_alone_70C"][n][part]),
                ("vented", lambda n: res["at_70C"]["vented"][n]["parts"][part]["junction_C"]),
                ("sealed", lambda n: res["at_70C"]["sealed"][n]["parts"][part]["junction_C"]))):
            v = [getter(n) for n in names]
            ax.bar(x + (j - 1) * 0.27, v, 0.25, color=cols[lab], label=lab if k == 0 else None)
            for xi, vi in zip(x, v):
                ax.text(xi + (j - 1) * 0.27, vi + 1, f"{vi:.0f}", ha="center", fontsize=8)
        ax.axhline(limits[part], color="#111", lw=1.2, ls="--")
        ax.text(-0.45, limits[part] + 1.5, f"limit {limits[part]} C", ha="left", fontsize=9)
        ax.set_xticks(x, short)
        top = max(res["at_70C"]["sealed"][n]["parts"][part]["junction_C"] for n in names)
        ax.set_ylim(60, max(limits[part] + 15, top + 10))
        ax.set_title({"U2": "U2 LM5177 junction", "Q3": "Q3 input high side junction",
                      "C17": "C17 electrolytic core (105 C part)"}[part], fontsize=11)
        ax.set_ylabel("C at 70 C ambient")
        ax.grid(axis="y", alpha=0.3)
    fig.legend(loc="upper center", ncol=3, frameon=False, fontsize=10, bbox_to_anchor=(0.5, 0.965))
    for k, (name, lab) in enumerate(((CASES[0][0], "13.5 V, worst load"), (CASES[2][0], "6.0 V weak battery, worst load"))):
        ax = fig.add_subplot(gs[1, k])
        for tag, ls in (("vented", "-"), ("sealed", "--")):
            rows = res["sweep"][tag][name]
            ta = [r["T_amb_C"] for r in rows]
            ax.plot(ta, [r["U2"] for r in rows], ls, color="#1565c0", label=f"U2, {tag}")
            ax.plot(ta, [r["C17"] for r in rows], ls, color="#ef6c00", label=f"C17, {tag}")
            ax.plot(ta, [r["shell_max_C"] for r in rows], ls, color="#555", label=f"shell max, {tag}")
        for y, lab_ in ((125, "U2 125"), (105, "C17 105"), (100, "ASA HDT 100"), (74, "PETG-CF HDT 74")):
            ax.axhline(y, color="#bbb", lw=0.8)
            ax.text(84, y + 0.8, lab_, fontsize=7.5, color="#666", ha="right")
        ax.set_title(lab, fontsize=11)
        ax.set_xlabel("ambient C")
        ax.set_ylabel("C")
        ax.grid(alpha=0.3)
        if k == 0:
            ax.legend(fontsize=7.5, ncol=2, loc="lower right")
    ax = fig.add_subplot(gs[1, 2])
    ax.axis("off")
    v = res["at_70C"]["vented"][CASES[0][0]]
    s = res["at_70C"]["sealed"][CASES[0][0]]
    w = res["at_70C"]["vented"][CASES[2][0]]
    ws = res["at_70C"]["sealed"][CASES[2][0]]
    lines = [
        "At 70 C ambient, worst load:",
        f"  13.5 V: {v['total_loss_W']:.2f} W in the case",
        f"    air inside {v['T_air_inside_C']:.1f} C vented, {s['T_air_inside_C']:.1f} C sealed",
        f"    vents carry {v['vent_W']:.2f} W ({v['vent_flow_l_min']:.2f} l/min)",
        f"    shell max {v['shell_max_C']:.1f} C vented, {s['shell_max_C']:.1f} C sealed",
        f"  6.0 V: {w['total_loss_W']:.2f} W in the case",
        f"    air inside {w['T_air_inside_C']:.1f} C vented, {ws['T_air_inside_C']:.1f} C sealed",
        f"    shell max {w['shell_max_C']:.1f} C vented, {ws['shell_max_C']:.1f} C sealed",
        "",
        f"Shell: {SHELL}, k {K_SHELL[SHELL]} W/mK, emissivity {EPS}",
        f"Vents: 2 x {res['model']['vent_area_low_mm2']:.0f} mm2 honeycomb rows,",
        f"  {res['model']['chimney_mm']:.1f} mm apart; {res['model']['gap_area_mm2']:.0f} mm2 of gaps beside the board",
        f"Mesh: {res['model']['tets']} tets",
    ]
    ax.text(0.0, 1.0, "\n".join(lines), va="top", family="monospace", fontsize=9.2)
    fig.suptitle("PSU board in its enclosure: board, air and shell at the worst load (psu_case_thermal.py)",
                 fontsize=14, weight="bold", y=0.995)
    fig.savefig(OUT_PNG, bbox_inches="tight")


if __name__ == "__main__":
    main()
