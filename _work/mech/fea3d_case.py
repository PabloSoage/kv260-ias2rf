"""3-D finite-element model of the enclosure as built WITH the two boards in it (docs/ENCLOSURE.md section 5.3).

    blender -b _work/mech/cache/case.blend --python _work/mech/fea3d_export.py -- v1      # Windows
    micromamba run -n fea python _work/mech/fea3d_case.py v1 [--h 4] [--eps 0.0015]       # WSL

Unlike fea_case.py (a simplified gmsh model for modes, drop and fatigue across materials), this meshes the real
printed geometry -- build_case.py's tray and lid with every rib, honeycomb, lug, clamp post, vent and cut-out --
together with the boards themselves, all exported by fea3d_export.py:
  - the adapter's FR-4 body (KiCad's 3-D export of the Rev06 board) and the KV260 carrier's PCB (AMD's STEP);
  - the two 0.8 mm aluminium spacers at H1/H2 and the mated Hirose BM20B pair (J101/J102) that join them.
fTetWild (pytetwild) unites them into one bonded body -- each board bonded where it rests on the case's
honeycomb and posts (the TPU-padded clamp posts above are not in contact, so not bonded: conservative) -- and
meshes it in 10-node tetrahedra for CalculiX. Each tet takes its material from where its centroid lies: inside
a board's outline and thickness -> FR-4, between the boards at a spacer or the Hirose pair -> bridge, else
PETG-CF. The parts' masses ride on the boards as density: adapter 110 g, carrier 90 g + K26 SOM with its
fan-sink 120 g (smeared over the carrier -- the SOM's own stiffness is left out, conservative for the carrier).

Loads: quasi-static 50 g shocks (the vehicle envelope of ENCLOSURE.md section 5) down (Zm), along X (Xp) and Y
(Yp), as body forces on everything. Supports: the four vehicle ears held at their M5 washers (10 mm).
Results from the nodal strain (CalculiX's extrapolated strain, continuous across the bonded interfaces):
  - case: von Mises stress from PETG-CF's constants, against the across-layer strength 29 MPa at 23 C and
    29 x 0.6 at 70 C (post_fea.py's assumption) -- a deliberately conservative pairing for a printed part;
  - boards: the largest principal strain in microstrain, against the usual 500 ue guide for BGA solder
    joints under shock (IPC/JEDEC-9704A practice), and at the BGAs U1101 (FPGA), U501/U601 (ADCs);
    each board's out-of-plane bow (max - min Uz over its nodes).
Writes _work/mech/cache/fea3d/<tag>/ (decks, results, coloured PLYs for render_fea3d.py) and
docs/sim/case3d_<tag>.json.
"""
import json, math, os, subprocess, sys
import numpy as np

tag = sys.argv[1]
argv = sys.argv[2:]
H = float(argv[argv.index("--h") + 1]) if "--h" in argv else 4.0
EPS = float(argv[argv.index("--eps") + 1]) if "--eps" in argv else 0.0015
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
D = os.path.join(ROOT, "_work", "mech", "cache", "fea3d", tag)
G = 9810.0
MAT = {  # E (MPa), nu, density set later for the boards (t/mm3)
    "PETG": dict(E=2460.0, nu=0.38, rho=1.25e-9),
    "FR4AD": dict(E=22000.0, nu=0.15, rho=None),
    "FR4KV": dict(E=22000.0, nu=0.15, rho=None),
    "BRIDGE": dict(E=20000.0, nu=0.3, rho=2.0e-9),
}
M_AD, M_KV = 0.110e-3, 0.210e-3                   # t
S_ALLOW = {"23C": 29.0, "70C": 29.0 * 0.6}
UE_GUIDE = 500.0
Z_BOT = -11.0
EARS = [(x, y) for x in (-65.0, 100.0) for y in (-24.7, 124.5)]
SPACERS = [(-5.0, 104.0), (-5.0, -5.0)]
LCS = {"Zm": (0, 0, -1), "Xp": (1, 0, 0), "Yp": (0, 1, 0)}


def read_stl(fn):
    vs = []
    for ln in open(fn):
        p = ln.split()
        if p and p[0] == "vertex":
            vs.append([float(p[1]), float(p[2]), float(p[3])])
    vs = np.array(vs)
    uq, inv = np.unique(np.round(vs, 4), axis=0, return_inverse=True)
    return uq, inv.reshape(-1, 3).astype(np.int32)


def prism(poly, z0, z1):
    """Closed triangle mesh of a vertical prism over a CCW polygon."""
    n = len(poly)
    v = np.array([[x, y, z0] for x, y in poly] + [[x, y, z1] for x, y in poly])
    f = []
    for i in range(1, n - 1):
        f.append([0, i + 1, i])
        f.append([n, n + i, n + i + 1])
    for i in range(n):
        j = (i + 1) % n
        f.append([i, j, n + j])
        f.append([i, n + j, n + i])
    return v, np.array(f, np.int32)


def circle(x, y, r, k=24):
    return [(x + r * math.cos(2 * math.pi * i / k), y + r * math.sin(2 * math.pi * i / k)) for i in range(k)]


def footprint(v, f):
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    tris = []
    for a, b, c in f:
        p = Polygon([v[a][:2], v[b][:2], v[c][:2]])
        if p.area > 1e-6:
            tris.append(p)
    return unary_union(tris).buffer(0.05)


def inputs(info):
    parts = [read_stl(os.path.join(D, n + ".stl")) for n in ("case_bottom", "case_lid")]
    boards = {}
    for n in info["board_files"]:
        v, f = read_stl(os.path.join(D, n + ".stl"))
        parts.append((v, f))
        boards[n] = dict(z0=float(v[:, 2].min()), z1=float(v[:, 2].max()), poly=footprint(v, f))
    bridges = []
    for x, y in SPACERS:
        bridges.append(prism(circle(x, y, 3.0), -0.01, 0.81))
    for k in ("J101", "J102"):
        lo, hi = info["hirose"][k]
        bridges.append(prism([(lo[0], lo[1]), (hi[0], lo[1]), (hi[0], hi[1]), (lo[0], hi[1])], -0.01, 0.81))
    parts += bridges
    vs, fs, off = [], [], 0
    for v, f in parts:
        vs.append(v)
        fs.append(f + off)
        off += len(v)
    return np.vstack(vs), np.vstack(fs).astype(np.int32), boards


def mesh(info):
    import pytetwild
    cache = os.path.join(D, f"tetb_h{H}_e{EPS}.npz")
    v, f, boards = inputs(info)
    if os.path.exists(cache):
        z = np.load(cache)
        return z["v"], z["t"], boards
    print("surface", len(v), "verts", len(f), "tris", flush=True)
    tv, tt = pytetwild.tetrahedralize(v, f, edge_length_abs=H, epsilon=EPS, optimize=True)
    np.savez(cache, v=tv, t=tt)
    return tv, tt, boards


def quadratic(v, t):
    pairs = [(0, 1), (1, 2), (2, 0), (0, 3), (1, 3), (2, 3)]
    e = np.sort(np.stack([t[:, [a, b]] for a, b in pairs], axis=1).reshape(-1, 2), axis=1)
    ue, inv = np.unique(e, axis=0, return_inverse=True)
    mid = (v[ue[:, 0]] + v[ue[:, 1]]) / 2
    return np.vstack([v, mid]), np.hstack([t, (inv.reshape(-1, 6) + len(v))])


def orient(v, t):
    a, b, c, d = (v[t[:, i]] for i in range(4))
    neg = np.einsum("ij,ij->i", np.cross(b - a, c - a), d - a) < 0
    t = t.copy()
    t[neg, 1], t[neg, 2] = t[neg, 2].copy(), t[neg, 1].copy()
    return t


def anchored(v, t):
    """Keep only the tets joined FACE to face to the ears' footprints: fTetWild can leave a piece of a board that
    touches the rest through an edge or a vertex only, a hinge that makes the stiffness singular (a body
    rotating freely). Vertices compacted."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    faces = np.sort(np.vstack([t[:, [0, 1, 2]], t[:, [0, 1, 3]], t[:, [0, 2, 3]], t[:, [1, 2, 3]]]), axis=1)
    owner = np.tile(np.arange(len(t)), 4)
    order = np.lexsort(faces.T[::-1])
    fs, ow = faces[order], owner[order]
    same = np.all(fs[1:] == fs[:-1], axis=1)
    a, b = ow[:-1][same], ow[1:][same]
    g = coo_matrix((np.ones(len(a)), (a, b)), shape=(len(t), len(t)))
    n, lab = connected_components(g, directed=False)
    cen = v[t].mean(axis=1)
    ear = [int(np.argmin(np.hypot(cen[:, 0] - x, cen[:, 1] - y) + 10 * np.abs(cen[:, 2] - Z_BOT))) for x, y in EARS]
    keep_lab = set(lab[ear])
    keep = np.isin(lab, list(keep_lab))
    used = np.unique(t[keep])
    remap = -np.ones(len(v), int)
    remap[used] = np.arange(len(used))
    sizes = np.bincount(lab)
    print("face components", n, "kept", len(keep_lab), "dropped tets", int((~keep).sum()),
          "largest dropped", int(np.sort(sizes)[-2]) if n > 1 else 0, flush=True)
    return v[used], remap[t[keep]]


def classify(v, t, boards, info):
    from shapely import contains_xy
    c = v[t].mean(axis=1)
    mat = np.array(["PETG"] * len(t), dtype=object)
    for n, key in (("carrier_pcb", "FR4KV"), ("adapter_pcb", "FR4AD")):
        b = boards[n]
        inz = (c[:, 2] > b["z0"] - 0.05) & (c[:, 2] < b["z1"] + 0.05)
        idx = np.where(inz)[0]
        ok = contains_xy(b["poly"], c[idx, 0], c[idx, 1])
        mat[idx[ok]] = key
    br = (c[:, 2] > 0.0) & (c[:, 2] < 0.8)
    near = np.zeros(len(t), bool)
    for x, y in SPACERS:
        near |= np.hypot(c[:, 0] - x, c[:, 1] - y) < 3.2
    for k in ("J101", "J102"):
        lo, hi = info["hirose"][k]
        near |= (c[:, 0] > lo[0] - 0.2) & (c[:, 0] < hi[0] + 0.2) & (c[:, 1] > lo[1] - 0.2) & (c[:, 1] < hi[1] + 0.2)
    mat[br & near] = "BRIDGE"
    return mat


def boundary(t):
    faces = np.vstack([t[:, [0, 1, 2]], t[:, [0, 1, 3]], t[:, [0, 2, 3]], t[:, [1, 2, 3]]])
    owner = np.tile(np.arange(len(t)), 4)
    key = np.sort(faces, axis=1)
    uq, idx, cnt = np.unique(key, axis=0, return_index=True, return_counts=True)
    keep = idx[cnt == 1]
    return faces[keep], owner[keep]


def deck(path, xyz, t10, mat, fixed, lc, rho):
    with open(path, "w") as f:
        f.write("*HEADING\nenclosure + boards 3-D, " + lc + "\n*NODE, NSET=NALL\n")
        for i, p in enumerate(xyz, 1):
            f.write(f"{i},{p[0]:.5f},{p[1]:.5f},{p[2]:.5f}\n")
        for m in MAT:
            ids = np.where(mat == m)[0]
            if not len(ids):
                continue
            f.write(f"*ELEMENT, TYPE=C3D10, ELSET=E{m}\n")
            for i in ids:
                f.write(f"{i + 1}," + ",".join(str(n + 1) for n in t10[i]) + "\n")
        f.write("*ELSET, ELSET=EALL\n" + ",".join(f"E{m}" for m in MAT if (mat == m).any()) + "\n")
        f.write("*NSET, NSET=FIX\n")
        for k in range(0, len(fixed), 16):
            f.write(",".join(str(n + 1) for n in fixed[k:k + 16]) + "\n")
        for m, p in MAT.items():
            if not (mat == m).any():
                continue
            f.write(f"*MATERIAL, NAME=M{m}\n*ELASTIC\n{p['E']},{p['nu']}\n*DENSITY\n{rho[m]:.5e}\n")
            f.write(f"*SOLID SECTION, ELSET=E{m}, MATERIAL=M{m}\n")
        f.write("*BOUNDARY\nFIX,1,3\n*STEP\n*STATIC, SOLVER=SPOOLES\n")
        d = LCS[lc]
        f.write(f"*DLOAD\nEALL,GRAV,{50 * G:.1f},{d[0]},{d[1]},{d[2]}\n")
        f.write("*NODE FILE\nU\n*EL FILE\nE\n*END STEP\n")


def read_frd(fn, nn):
    U = np.zeros((nn, 3))
    E = np.zeros((nn, 6))
    block = None
    for ln in open(fn):
        if ln.startswith(" -4"):
            block = ln.split()[1]
        elif ln.startswith(" -1") and block in ("DISP", "TOSTRAIN"):
            n = int(ln[3:13]) - 1
            vals = [float(ln[13 + 12 * k:25 + 12 * k]) for k in range((len(ln.rstrip()) - 13) // 12)]
            if block == "DISP":
                U[n] = vals[:3]
            else:
                E[n] = vals[:6]
        elif ln.startswith(" -3"):
            block = None
    return U, E


def vm_from_strain(E6, Em, nu):
    exx, eyy, ezz, exy, eyz, ezx = E6.T          # CalculiX: tensor shear components
    lam = Em * nu / ((1 + nu) * (1 - 2 * nu))
    mu = Em / (2 * (1 + nu))
    tr = exx + eyy + ezz
    sx, sy, sz = lam * tr + 2 * mu * exx, lam * tr + 2 * mu * eyy, lam * tr + 2 * mu * ezz
    txy, tyz, tzx = 2 * mu * exy, 2 * mu * eyz, 2 * mu * ezx
    return np.sqrt(0.5 * ((sx - sy) ** 2 + (sy - sz) ** 2 + (sz - sx) ** 2) + 3 * (txy ** 2 + tyz ** 2 + tzx ** 2))


def max_principal_abs(E6):
    exx, eyy, ezz, exy, eyz, ezx = E6.T
    T = np.stack([np.stack([exx, exy, ezx], -1), np.stack([exy, eyy, eyz], -1), np.stack([ezx, eyz, ezz], -1)], -2)
    w = np.linalg.eigvalsh(T)
    return np.abs(w).max(axis=1)


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
                f"property float val\nelement face {len(faces)}\nproperty list uchar int vertex_indices\nend_header\n")
        for k, i in enumerate(used):
            f.write(f"{v[i, 0]:.4f} {v[i, 1]:.4f} {v[i, 2]:.4f} {rgb[k, 0]} {rgb[k, 1]} {rgb[k, 2]} {val[i]:.4f}\n")
        for a, b, c in remap[faces]:
            f.write(f"3 {a} {b} {c}\n")


def main():
    info = json.load(open(os.path.join(D, "boards.json")))
    v, t, boards = mesh(info)
    v, t = anchored(v, t)
    t = orient(v, t)
    mat = classify(v, t, boards, info)
    cnt = {m: int((mat == m).sum()) for m in MAT}
    print("tets", len(t), "nodes", len(v), cnt, flush=True)
    vol = np.abs(np.einsum("ij,ij->i", np.cross(v[t[:, 1]] - v[t[:, 0]], v[t[:, 2]] - v[t[:, 0]]),
                           v[t[:, 3]] - v[t[:, 0]])) / 6
    rho = {m: p["rho"] for m, p in MAT.items()}
    rho["FR4AD"] = M_AD / vol[mat == "FR4AD"].sum()
    rho["FR4KV"] = M_KV / vol[mat == "FR4KV"].sum()
    bf, owner = boundary(t)
    fmat = mat[owner]
    bnodes = np.unique(bf)
    pb = v[bnodes]
    fixed = bnodes[(np.abs(pb[:, 2] - Z_BOT) < 0.4) &
                   np.array([min(math.hypot(p[0] - x, p[1] - y) for x, y in EARS) < 5.0 for p in pb])]
    print("fixed", len(fixed), "rho", {k: f"{r:.3e}" for k, r in rho.items()}, flush=True)
    assert len(fixed) > 20 and cnt["FR4AD"] > 100 and cnt["FR4KV"] > 100
    xyz, t10 = quadratic(v, t)
    case_f = bf[fmat == "PETG"]
    board_f = bf[(fmat == "FR4AD") | (fmat == "FR4KV")]
    case_n = np.unique(case_f)
    nodes_of = {m: np.unique(t[mat == m]) for m in ("FR4AD", "FR4KV")}
    res = dict(tag=tag, h_mm=H, eps=EPS, tets=int(len(t)), nodes=int(len(xyz)), tets_by_material=cnt,
               case_mass_g=float(vol[mat == "PETG"].sum() * MAT["PETG"]["rho"] * 1e6),
               allow_MPa=S_ALLOW, ue_guide=UE_GUIDE, cases={})
    spots = {k: info["hirose"][k] for k in ("U1101", "U501", "U601") if k in info["hirose"]}
    fields = {}
    for lc in LCS:
        wd = os.path.join(D, "b_" + lc)
        os.makedirs(wd, exist_ok=True)
        deck(os.path.join(wd, "case.inp"), xyz, t10, mat, fixed, lc, rho)
        env = dict(os.environ, OMP_NUM_THREADS="24", CCX_NPROC_EQUATION_SOLVER="24", CCX_NPROC_RESULTS="24")
        r = subprocess.run(["ccx", "-i", "case"], cwd=wd, capture_output=True, text=True, env=env)
        if r.returncode or "ERROR" in r.stdout:
            print(r.stdout[-3000:], r.stderr[-2000:])
            sys.exit(1)
        U, E6 = read_frd(os.path.join(wd, "case.frd"), len(xyz))
        U4, E4 = U[:len(v)], E6[:len(v)]
        vm = vm_from_strain(E4, MAT["PETG"]["E"], MAT["PETG"]["nu"])
        ue = max_principal_abs(E4) * 1e6
        bulk = case_n[~np.isin(case_n, fixed)]
        p997 = float(np.percentile(vm[bulk], 99.7))
        k = bulk[np.argmax(vm[bulk])]
        out = dict(case=dict(vm_peak=float(vm[bulk].max()), vm_p997=p997, peak_at=[round(float(x), 1) for x in v[k]],
                             sf_23C=S_ALLOW["23C"] / p997, sf_70C=S_ALLOW["70C"] / p997),
                   umax_mm=float(np.linalg.norm(U4, axis=1).max()))
        for m, name in (("FR4AD", "adapter"), ("FR4KV", "carrier")):
            nn = nodes_of[m]
            kk = nn[np.argmax(ue[nn])]
            out[name] = dict(ue_peak=float(ue[nn].max()), ue_p997=float(np.percentile(ue[nn], 99.7)),
                             peak_at=[round(float(x), 1) for x in v[kk]],
                             bow_mm=float(U4[nn, 2].max() - U4[nn, 2].min()))
        for s, (lo, hi) in spots.items():
            nn = nodes_of["FR4AD"]
            p = v[nn]
            sel = nn[(p[:, 0] > lo[0]) & (p[:, 0] < hi[0]) & (p[:, 1] > lo[1]) & (p[:, 1] < hi[1])]
            if len(sel):
                out.setdefault("bga", {})[s] = dict(ue_max=float(ue[sel].max()), nodes=int(len(sel)))
        res["cases"][lc] = out
        fields[lc] = (vm, ue)
        print(lc, json.dumps(out), flush=True)
    vmax = max(c["case"]["vm_p997"] for c in res["cases"].values()) * 1.25
    uemax = max(max(c["adapter"]["ue_p997"], c["carrier"]["ue_p997"]) for c in res["cases"].values()) * 1.25
    res["scale_MPa"], res["scale_ue"] = vmax, uemax
    for lc, (vm, ue) in fields.items():
        write_ply(os.path.join(D, f"case3d_{tag}_{lc}.ply"), v, case_f, vm, vmax)
        write_ply(os.path.join(D, f"boards3d_{tag}_{lc}.ply"), v, board_f, ue, uemax, "viridis")
    json.dump(res, open(os.path.join(ROOT, "docs", "sim", f"case3d_{tag}.json"), "w"), indent=1)
    print("done", json.dumps({k: res[k] for k in ("tets", "nodes", "case_mass_g", "scale_MPa", "scale_ue")}))


main()
