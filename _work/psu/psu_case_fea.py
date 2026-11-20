#!/usr/bin/env python3
"""
FEA of the PSU board's enclosure (psu_case.py) with the board in it, CalculiX (C3D10), the main case's method
(_work/mech/fea3d_case.py, docs/ENCLOSURE.md section 5.3):

  - Bodies: tray, lid and the board (FR-4, 22 GPa, its 50 g of parts [E] carried as density) meshed together.
    The board is bonded to the tray's stand-offs and to the lid's posts: the M3 screw clamps that stack. The lid
    is bonded where it sits on the walls: exact for loads that press it on (a knee, a shock down), slightly stiff
    for those that would lift it, which the four screws then carry.
  - Supports: the four ears held at their M5 washers (10 mm diameter, underside).
  - Loads (each an engineering estimate, stated):
      - 50 g quasi-static shock down, sideways (Y) and fore-aft (X);
      - a cable pulled at 50 N out of J1 (the 16 AWG battery lead), and at 30 N out of J2 and J3 together;
      - 300 N pressed on the lid over a 30 mm disc at its centre (a knee, or luggage on it);
      - the first natural frequency.
  - Materials: ASA (the shell this case is meant for, see psu_case_thermal.py) and PETG-CF, each at 23 C and at
    70 C with fea_case.py's modulus factors (k70) and post_fea.py's strength factors (S70). The shell's von Mises
    stress against the across-layer strength, as for the main case. Board: the largest principal strain against
    the 500 microstrain guide.
  - Lid press: the remaining gap between the lid's ribs and the tallest parts under them (C6, C17, C18; 2.36 mm
    unloaded).

    python _work/psu/psu_case_fea.py [--h 1.6]     # meshes here, runs ccx in WSL (micromamba env "fea")

Writes docs/sim/psu_case_fea.json and _work/psu/cache/psu_case_fea_<case>.ply (von Mises on the shell, for the
render).
"""
import json
import math
import os
import subprocess
import sys
import time

import gmsh
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import psu_case as G                                              # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
CACHE = os.path.join(ROOT, "_work", "psu", "cache")
OUT_JSON = os.path.join(ROOT, "docs", "sim", "psu_case_fea.json")
H = float(sys.argv[sys.argv.index("--h") + 1]) if "--h" in sys.argv else 1.6
G0 = 9810.0                                     # mm/s2
M_BOARD = 0.050e-3                              # t (50 g) [E]
FR4 = dict(E=22000.0, nu=0.15)
MATS = {  # fea_case.py's table and post_fea.py's S70
    "ASA": dict(Exy=2000, Ez=1900, nu=0.35, rho=1.05e-9, sz=25.0, k70=0.80, s70=0.80),
    "PETG-CF": dict(Exy=2460, Ez=1340, nu=0.38, rho=1.25e-9, sz=29.0, k70=0.45, s70=0.60),
}
UE_GUIDE = 500.0
# load cases: name -> (kind, data)
CASES = {
    "shock_down": ("grav", (0, 0, -1)),
    "shock_side": ("grav", (0, 1, 0)),
    "shock_fore_aft": ("grav", (1, 0, 0)),
    "cable_J1_50N": ("cable", {"J1": 50.0}),
    "cable_J2_J3_30N": ("cable", {"J2": 30.0, "J3": 30.0}),
    "lid_press_300N": ("press", 300.0),
}
PADS = {"J1": (100.0, 113.0, 107.5, 117.0), "J2": (103.0, 117.0, 143.0, 151.0), "J3": (103.0, 117.0, 158.0, 166.0)}
TALL = {"C6": (149.25, 158.75, 121.85, 130.15), "C17": (195.5, 207.5, 116.35, 126.65),
        "C18": (195.5, 207.5, 103.85, 114.15)}


def win2wsl(p):
    p = os.path.abspath(p).replace("\\", "/")
    return "/mnt/" + p[0].lower() + p[2:]


def mesh():
    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.model.add("fea")
    b = G.Builder()
    occ = gmsh.model.occ
    tray, lid, board = b.tray(), b.lid(), b.board()
    occ.fragment(board, tray + lid)
    occ.synchronize()
    gmsh.option.setNumber("Mesh.MeshSizeMax", H)
    gmsh.option.setNumber("Mesh.MeshSizeMin", 0.4)
    gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 6)
    gmsh.option.setNumber("Mesh.Algorithm3D", 10)
    gmsh.model.mesh.generate(3)
    tags, xyz, _ = gmsh.model.mesh.getNodes()
    idx = np.full(int(tags.max()) + 1, -1)
    idx[tags.astype(int)] = np.arange(len(tags))
    xyz = xyz.reshape(-1, 3)
    tets, part = [], []
    for _, tag in gmsh.model.getEntities(3):
        x0, y0, z0, x1, y1, z1 = gmsh.model.getBoundingBox(3, tag)
        name = "tray" if z0 < -5 else ("lid" if z1 > G.Z_TOP - 0.5 else "board")
        types, _, nodes = gmsh.model.mesh.getElements(3, tag)
        for t, n in zip(types, nodes):
            if t == 4:
                c = idx[n.astype(int)].reshape(-1, 4)
                tets.append(c)
                part += [name] * len(c)
    gmsh.finalize()
    t = np.vstack(tets)
    used = np.unique(t)
    remap = -np.ones(len(xyz), int)
    remap[used] = np.arange(len(used))
    return xyz[used], remap[t], np.array(part)


def orient(v, t):
    a, b, c, d = (v[t[:, k]] for k in range(4))
    neg = np.einsum("ij,ij->i", np.cross(b - a, c - a), d - a) < 0
    t = t.copy()
    t[neg] = t[neg][:, [0, 2, 1, 3]]
    return t


def quadratic(v, t):
    """C3D10: corners, then mid-edge nodes 1-2, 2-3, 3-1, 1-4, 2-4, 3-4 (CalculiX order)."""
    pairs = [(0, 1), (1, 2), (2, 0), (0, 3), (1, 3), (2, 3)]
    e = np.stack([np.sort(t[:, [a, b]], axis=1) for a, b in pairs], axis=1).reshape(-1, 2)
    uq, inv = np.unique(e, axis=0, return_inverse=True)
    mid = (v[uq[:, 0]] + v[uq[:, 1]]) / 2
    xyz = np.vstack([v, mid])
    t10 = np.hstack([t, len(v) + inv.reshape(-1, 6)])
    return xyz, t10


def boundary(t):
    faces = np.vstack([t[:, [0, 1, 2]], t[:, [0, 1, 3]], t[:, [0, 2, 3]], t[:, [1, 2, 3]]])
    owner = np.tile(np.arange(len(t)), 4)
    key = np.sort(faces, axis=1)
    _, idx, cnt = np.unique(key, axis=0, return_index=True, return_counts=True)
    keep = idx[cnt == 1]
    return faces[keep], owner[keep]


def tri_areas(v, f):
    return np.linalg.norm(np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]]), axis=1) / 2


def nodal_forces(v, f, sel, total):
    """Spread a force vector over the corner nodes of the selected boundary faces by area."""
    A = tri_areas(v, f[sel])
    F = {}
    for face, a in zip(f[sel], A):
        for n in face:
            F[n] = F.get(n, 0.0) + a / 3
    s = sum(F.values())
    return {n: (np.array(total) * w / s) for n, w in F.items()}


def deck(path, xyz, t10, part, fixed, mat, T, loads, rho_board):
    k = mat["k70"] if T == 70 else 1.0
    E = 0.5 * (mat["Exy"] + mat["Ez"]) * k
    with open(path, "w") as f:
        f.write("*HEADING\nPSU enclosure + board\n*NODE, NSET=NALL\n")
        for i, p in enumerate(xyz, 1):
            f.write(f"{i},{p[0]:.5f},{p[1]:.5f},{p[2]:.5f}\n")
        for name in ("tray", "lid", "board"):
            ids = np.where(part == name)[0]
            f.write(f"*ELEMENT, TYPE=C3D10, ELSET=E{name}\n")
            for i in ids:
                f.write(f"{i + 1}," + ",".join(str(n + 1) for n in t10[i]) + "\n")
        f.write("*ELSET, ELSET=ESHELL\nEtray,Elid\n*ELSET, ELSET=EALL\nESHELL,Eboard\n")
        f.write("*NSET, NSET=FIX\n")
        for j in range(0, len(fixed), 16):
            f.write(",".join(str(n + 1) for n in fixed[j:j + 16]) + "\n")
        f.write(f"*MATERIAL, NAME=MSHELL\n*ELASTIC\n{E:.1f},{mat['nu']}\n*DENSITY\n{mat['rho']:.4e}\n")
        f.write(f"*SOLID SECTION, ELSET=ESHELL, MATERIAL=MSHELL\n")
        f.write(f"*MATERIAL, NAME=MFR4\n*ELASTIC\n{FR4['E']},{FR4['nu']}\n*DENSITY\n{rho_board:.4e}\n")
        f.write("*SOLID SECTION, ELSET=Eboard, MATERIAL=MFR4\n")
        f.write("*BOUNDARY\nFIX,1,3\n")
        # every step replaces the loads of the one before (OP=NEW): CalculiX otherwise keeps them
        for lc, (kind, data) in loads.items():
            f.write(f"*STEP\n*STATIC, SOLVER=SPOOLES\n")
            if kind == "grav":
                f.write(f"*DLOAD, OP=NEW\nEALL,GRAV,{50 * G0:.1f},{data[0]},{data[1]},{data[2]}\n")
                f.write(f"*CLOAD, OP=NEW\n{fixed[0] + 1},1,0.\n")
            else:
                f.write("*DLOAD, OP=NEW\nEALL,GRAV,0.,0.,0.,-1.\n*CLOAD, OP=NEW\n")
                for n, F in data.items():
                    for d in range(3):
                        if abs(F[d]) > 1e-12:
                            f.write(f"{n + 1},{d + 1},{F[d]:.6e}\n")
            f.write("*NODE FILE\nU\n*EL FILE\nE\n*END STEP\n")
        f.write("*STEP\n*FREQUENCY, SOLVER=SPOOLES\n4\n*END STEP\n")


def read_frd(fn, nn, nsteps):
    U = [np.zeros((nn, 3)) for _ in range(nsteps)]
    E = [np.zeros((nn, 6)) for _ in range(nsteps)]
    freqs = []
    step, block = -1, None
    seen = {"DISP": -1, "TOSTRAIN": -1}
    for ln in open(fn):
        if ln.startswith("    1PMODE") or ln.startswith("    1PGM"):
            pass
        if ln.startswith("    1PSTEP"):
            pass
        if ln.startswith("  100C"):
            try:
                val = float(ln[12:24])
            except ValueError:
                val = 0.0
            block_val = val
        if ln.startswith(" -4"):
            block = ln.split()[1]
            if block in seen:
                seen[block] += 1
                if seen[block] >= nsteps:
                    if block == "DISP":
                        freqs.append(block_val)
                    block = None
        elif ln.startswith(" -1") and block in seen:
            n = int(ln[3:13]) - 1
            k = seen[block]
            vals = [float(ln[13 + 12 * j:25 + 12 * j]) for j in range((len(ln.rstrip()) - 13) // 12)]
            if block == "DISP":
                U[k][n] = vals[:3]
            else:
                E[k][n] = vals[:6]
        elif ln.startswith(" -3"):
            block = None
    return U, E, freqs


def read_freqs(dat):
    out, on = [], False
    for ln in open(dat):
        if "E I G E N V A L U E   O U T P U T" in ln:
            on = True
            continue
        if on:
            s = ln.split()
            if len(s) >= 4 and s[0].isdigit():
                out.append(float(s[3]))
            elif out and not s:
                break
    return out


def vm_from_strain(E6, Em, nu):
    exx, eyy, ezz, exy, eyz, ezx = E6.T
    lam = Em * nu / ((1 + nu) * (1 - 2 * nu))
    mu = Em / (2 * (1 + nu))
    tr = exx + eyy + ezz
    sx, sy, sz = lam * tr + 2 * mu * exx, lam * tr + 2 * mu * eyy, lam * tr + 2 * mu * ezz
    txy, tyz, tzx = 2 * mu * exy, 2 * mu * eyz, 2 * mu * ezx
    return np.sqrt(0.5 * ((sx - sy) ** 2 + (sy - sz) ** 2 + (sz - sx) ** 2) + 3 * (txy ** 2 + tyz ** 2 + tzx ** 2))


def max_principal_abs(E6):
    exx, eyy, ezz, exy, eyz, ezx = E6.T
    T = np.stack([np.stack([exx, exy, ezx], -1), np.stack([exy, eyy, eyz], -1), np.stack([ezx, eyz, ezz], -1)], -2)
    return np.abs(np.linalg.eigvalsh(T)).max(axis=1)


def write_ply(fn, v, faces, val, vmax, cmap="turbo"):
    import matplotlib
    cm = matplotlib.colormaps[cmap]
    used = np.unique(faces)
    rgb = (np.array(cm(np.clip(val[used] / vmax, 0, 1)))[:, :3] * 255).astype(int)
    remap = -np.ones(len(v), int)
    remap[used] = np.arange(len(used))
    with open(fn, "w") as f:
        f.write(f"ply\nformat ascii 1.0\nelement vertex {len(used)}\nproperty float x\nproperty float y\n"
                f"property float z\nproperty uchar red\nproperty uchar green\nproperty uchar blue\n"
                f"element face {len(faces)}\nproperty list uchar int vertex_indices\nend_header\n")
        for k, i in enumerate(used):
            f.write(f"{v[i, 0] * 1e-3:.6f} {v[i, 1] * 1e-3:.6f} {v[i, 2] * 1e-3:.6f} {rgb[k, 0]} {rgb[k, 1]} {rgb[k, 2]}\n")
        for a, b, c in remap[faces]:
            f.write(f"3 {a} {b} {c}\n")


def main():
    os.makedirs(CACHE, exist_ok=True)
    t0 = time.time()
    v, t, part = mesh()
    t = orient(v, t)
    cnt = {p: int((part == p).sum()) for p in ("tray", "lid", "board")}
    print("tets", len(t), "nodes", len(v), cnt, f"{time.time() - t0:.0f} s", flush=True)
    assert all(c > 100 for c in cnt.values())
    bf, owner = boundary(t)
    fpart = part[owner]
    vol = np.abs(np.einsum("ij,ij->i", np.cross(v[t[:, 1]] - v[t[:, 0]], v[t[:, 2]] - v[t[:, 0]]),
                           v[t[:, 3]] - v[t[:, 0]])) / 6
    rho_board = M_BOARD / vol[part == "board"].sum()
    # supports: ear undersides within the washer
    slots = [(x, -c) for x in G.EARS_X for c in (G.OY0 - G.EAR_L / 2 - 0.5, G.OY1 + G.EAR_L / 2 + 0.5)]
    bn = np.unique(bf)
    pb = v[bn]
    near = np.array([min(math.hypot(p[0] - x, p[1] - y) for x, y in slots) for p in pb])
    fixed = bn[(np.abs(pb[:, 2] - G.Z_BOT) < 0.05) & (near < 5.0) & (near > G.SLOT_W / 2 + 0.1)]
    print("fixed nodes", len(fixed), flush=True)
    assert len(fixed) > 20
    # loads on faces
    fc = v[bf].mean(axis=1)
    fn = np.cross(v[bf[:, 1]] - v[bf[:, 0]], v[bf[:, 2]] - v[bf[:, 0]])
    nz = fn[:, 2] / np.linalg.norm(fn, axis=1)
    loads = {}
    for name, (kind, data) in CASES.items():
        if kind == "grav":
            loads[name] = ("grav", data)
        elif kind == "cable":
            F = {}
            for ref, mag in data.items():
                x0, x1, ky0, ky1 = PADS[ref]
                sel = ((fpart == "board") & (np.abs(fc[:, 2] - G.BT) < 0.05) & (fc[:, 0] > x0) & (fc[:, 0] < x1) &
                       (-fc[:, 1] > ky0) & (-fc[:, 1] < ky1))
                assert sel.sum() > 3, (ref, sel.sum())
                for n, f in nodal_forces(v, bf, sel, (-mag, 0.0, 0.0)).items():
                    F[n] = F.get(n, 0) + f
            loads[name] = ("cload", F)
        else:
            sel = (fpart == "lid") & (np.abs(fc[:, 2] - G.Z_TOP) < 0.05) & \
                  (np.hypot(fc[:, 0] - 155.0, -fc[:, 1] - 135.0) < 15.0)
            loads[name] = ("cload", nodal_forces(v, bf, sel, (0.0, 0.0, -data)))
    xyz, t10 = quadratic(v, t)
    shell_nodes = np.unique(t[part != "board"])
    board_nodes = np.unique(t[part == "board"])
    shell_only = np.setdiff1d(shell_nodes, board_nodes)
    bulk = shell_only[~np.isin(shell_only, fixed)]
    lid_ribs = np.unique(bf[(fpart == "lid") & (np.abs(fc[:, 2] - (G.Z_CEIL - G.LID_RIB)) < 0.05)])
    res = dict(h_mm=H, tets=int(len(t)), nodes=int(len(xyz)), tets_by_part=cnt, board_mass_g=M_BOARD * 1e6,
               shell_mass_g={m: float(vol[part != "board"].sum() * p["rho"] * 1e6) for m, p in MATS.items()},
               ue_guide=UE_GUIDE, runs={})
    fields = {}
    for mname, mat in MATS.items():
        for T in (23, 70):
            tag = f"{mname}_{T}C"
            wd = os.path.join(CACHE, "fea_" + tag)
            os.makedirs(wd, exist_ok=True)
            deck(os.path.join(wd, "case.inp"), xyz, t10, part, fixed, mat, T, loads, rho_board)
            t1 = time.time()
            cmd = (f"cd {win2wsl(wd)} && OMP_NUM_THREADS=24 CCX_NPROC_EQUATION_SOLVER=24 CCX_NPROC_RESULTS=24 "
                   f"micromamba run -n fea ccx -i case")
            r = subprocess.run(["wsl", "-d", "Ubuntu", "--", "bash", "-lc", cmd], capture_output=True, text=True)
            if r.returncode or "*ERROR" in r.stdout:
                print(r.stdout[-3000:], r.stderr[-2000:])
                sys.exit(1)
            U, E6, _ = read_frd(os.path.join(wd, "case.frd"), len(xyz), len(loads))
            freqs = read_freqs(os.path.join(wd, "case.dat"))
            k = mat["k70"] if T == 70 else 1.0
            Em = 0.5 * (mat["Exy"] + mat["Ez"]) * k
            allow = mat["sz"] * (mat["s70"] if T == 70 else 1.0)
            out = dict(E_MPa=Em, allow_MPa=allow, f1_Hz=freqs[0] if freqs else None, freqs_Hz=freqs[:4], cases={})
            for j, lc in enumerate(loads):
                U4, E4 = U[j][:len(v)], E6[j][:len(v)]
                vm = vm_from_strain(E4, Em, mat["nu"])
                ue = max_principal_abs(E4) * 1e6
                p997 = float(np.percentile(vm[bulk], 99.7))
                kk = bulk[np.argmax(vm[bulk])]
                kb = board_nodes[np.argmax(ue[board_nodes])]
                c = dict(vm_p997=p997, vm_peak=float(vm[bulk].max()),
                         peak_at_kicad=[round(float(v[kk, 0]), 1), round(float(-v[kk, 1]), 1), round(float(v[kk, 2]), 1)],
                         sf=allow / p997, sf_peak=allow / float(vm[bulk].max()),
                         board_ue_p997=float(np.percentile(ue[board_nodes], 99.7)), board_ue_peak=float(ue[kb]),
                         umax_mm=float(np.linalg.norm(U4, axis=1).max()))
                if lc == "lid_press_300N":
                    gaps = {}
                    for ref, (x0, x1, ky0, ky1) in TALL.items():
                        above = lid_ribs[(v[lid_ribs, 0] > x0) & (v[lid_ribs, 0] < x1) &
                                         (-v[lid_ribs, 1] > ky0) & (-v[lid_ribs, 1] < ky1)]
                        under = board_nodes[(v[board_nodes, 0] > x0) & (v[board_nodes, 0] < x1) &
                                            (-v[board_nodes, 1] > ky0) & (-v[board_nodes, 1] < ky1)]
                        dz_lid = float(U4[above, 2].min()) if len(above) else 0.0
                        dz_board = float(U4[under, 2].max()) if len(under) else 0.0
                        gaps[ref] = round((G.Z_CEIL - G.LID_RIB - G.TALLEST) + dz_lid - dz_board, 3)
                    c["gap_to_tall_parts_mm"] = gaps
                    c["lid_centre_deflection_mm"] = float(-U4[lid_ribs, 2].min())
                out["cases"][lc] = c
                if mname == "ASA" and T == 23:
                    fields[lc] = vm
                print(tag, lc, json.dumps({kx: (round(vx, 3) if isinstance(vx, float) else vx)
                                           for kx, vx in c.items()}), flush=True)
            out["solve_s"] = time.time() - t1
            print(tag, "f1", out["f1_Hz"], f"{out['solve_s']:.0f} s", flush=True)
            res["runs"][tag] = out
    shell_faces = bf[fpart != "board"]
    vmax = max(res["runs"]["ASA_23C"]["cases"][lc]["vm_p997"] for lc in fields) * 1.25
    res["render_scale_MPa"] = vmax
    for lc in ("shock_down", "cable_J1_50N", "lid_press_300N"):
        write_ply(os.path.join(CACHE, f"psu_case_fea_{lc}.ply"), v, shell_faces, fields[lc], vmax)
    json.dump(res, open(OUT_JSON, "w"), indent=1)
    print("wrote", OUT_JSON, f"{time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
