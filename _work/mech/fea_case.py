"""Finite-element checks of the enclosure (docs/ENCLOSURE.md section 5): modes, 50 g shock, a 1 m corner drop
(energy method) and random vibration (Miles), for each print material at 23 and 70 C.

    micromamba run -n fea python _work/mech/fea_case.py [--h 4] [--only PETG-CF] [--keep]

Runs in WSL (gmsh's OpenCASCADE kernel for the geometry, CalculiX ccx for the solves). Writes
_work/mech/cache/fea/<material>_<T>/ (ccx decks and results, git-ignored) and docs/sim/case_fea.json.

The model is a simplification of build_case.py's parts, stated here so the numbers can be judged:
- tray and lid as one bonded body (the tongue, six M4 screws and the clamp posts tie them);
  sharp inside corners (the real ones are rounded), vents, the rear I/O band, the SMA row and the
  grille (as a 40 mm hole) cut out; no text, no chamfers;
- the honeycombs (under the boards, under the lid) as homogenised orthotropic layers, Gibson & Ashby's
  regular-hexagon relations at relative density 0.29 (10 mm cells, 1.6 mm walls), in-plane stiffness
  neglected on purpose (conservative for the lid);
- the boards as FR-4 plates carrying their parts' mass smeared; the K26 SOM with its fan-sink as one block
  bonded to the carrier; TPU pads (1 mm) between the clamp posts and the boards;
- the vehicle mount: the four ears held at their M5 washers' footprint (fixed).
"""
import gmsh, json, math, os, re, subprocess, sys
import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.environ.get("FEA_OUT", os.path.join(ROOT, "_work", "mech", "cache", "fea"))
argv = sys.argv[1:]
H = float(argv[argv.index("--h") + 1]) if "--h" in argv else 4.0
ONLY = argv[argv.index("--only") + 1] if "--only" in argv else None
G = 9810.0                                  # mm/s^2 (units: N, mm, t, s, MPa)

# ---- materials ---------------------------------------------------------------------------------------
# E (MPa) in the print plane and across layers, density (t/mm^3), tensile strength in and across layers (MPa),
# HDT at 0.45 MPa (C), and the modulus kept at 70 C. [S] = maker's data sheet, [I] = typical/inferred.
MATS = {
    "PLA":      dict(Exy=2750, Ez=2000, nu=0.35, rho=1.24e-9, sxy=35, sz=25, hdt=57,  k70=0.05,
                     src="Bambu PLA Basic class [I]; above its glass transition at 70 C", printer="A1"),
    "PETG":     dict(Exy=2000, Ez=1500, nu=0.38, rho=1.27e-9, sxy=33, sz=25, hdt=69,  k70=0.35,
                     src="PETG typical [I]", printer="A1"),
    "PETG-CF":  dict(Exy=2460, Ez=1340, nu=0.38, rho=1.25e-9, sxy=35, sz=29, hdt=74,  k70=0.45,
                     src="Bambu PETG-CF TDS V3 [S]; k70 [I]", printer="A1, hardened nozzle"),
    "ASA":      dict(Exy=2000, Ez=1900, nu=0.35, rho=1.05e-9, sxy=37, sz=25, hdt=100, k70=0.80,
                     src="Bambu ASA TDS [S] (Ez, sxy); Exy from its bending modulus, sz, HDT [I]",
                     printer="A1 with care (open frame warps large ASA parts)"),
    "PAHT-CF":  dict(Exy=3860, Ez=2180, nu=0.35, rho=1.06e-9, sxy=80, sz=45, hdt=194, k70=0.70,
                     src="Bambu PAHT-CF TDS V2 [S] (E); strengths, density, k70 [I]",
                     printer="A1, hardened nozzle, dried; an enclosed printer is better"),
    "Resin ABS-like": dict(Exy=1500, Ez=1500, nu=0.40, rho=1.15e-9, sxy=35, sz=35, hdt=50, k70=0.10,
                     src="Elegoo ABS-like 3.0+ class [I]: no figures published", printer="Saturn 4 Ultra"),
}
FR4 = dict(E=22000.0, nu=0.15)
TPU = dict(E=26.0, nu=0.45, rho=1.2e-9)
RHO_STAR = 0.29                              # honeycomb relative density
M_CARRIER, M_ADAPTER, M_SOM = 0.090e-3, 0.110e-3, 0.120e-3     # t (90, 110, 120 g) [I]

# ---- geometry (gmsh OCC), mm, the KV260 model frame as build_case.py -------------------------------------
Z_BOT, Z_FLOOR, Z_TOP_IN, Z_TOP = -11.0, -8.0, 32.75, 35.75
CARRIER_BOT, ADAPTER_BOT, ADAPTER_TOP = -1.59, 0.8, 2.4


def build():
    occ = gmsh.model.occ
    B = lambda x0, y0, z0, x1, y1, z1: occ.addBox(x0, y0, z0, x1 - x0, y1 - y0, z1 - z0)
    C = lambda x, y, z0, z1, d: occ.addCylinder(x, y, z0, 0, 0, z1 - z0, d / 2)
    outer = occ.fuse([(3, B(-113.6, -15.7, Z_BOT, 134.5, 115.5, Z_TOP))], [(3, B(-37.5, -35.8, Z_BOT, -1.5, -15.7, Z_TOP))])[0]
    inner = occ.fuse([(3, B(-109.6, -12.2, Z_FLOOR, 131.0, 112.0, Z_TOP_IN))], [(3, B(-34.0, -32.3, Z_FLOOR, -5.0, -12.2, Z_TOP_IN))])[0]
    holes = [(3, B(-0.2, 105, -1.5, 119.2, 120, 17.7)),             # rear I/O band
             (3, B(-27.9, -40, 2.0, -11.1, -30, 16.3)),             # RJ45
             (3, B(37.6, -20, -1.5, 51.2, -10, 5.4)),               # micro-USB
             (3, B(92.4, -20, -1.0, 108.2, -10, 2.9)),              # microSD
             (3, B(-120, -1.4, -0.5, -105, 101.9, 6.2)),            # the SMA row
             (3, C(86.1, 47.0, 30, 40, 40.0))]                      # the grille, as a hole
    for k in range(9):
        holes.append((3, B(128, 22.0 + 6 * k, 12, 140, 25.0 + 6 * k, 26)))
    for k in range(14):
        holes.append((3, B(-120, 4.0 + 7 * k, 12, -105, 7.0 + 7 * k, 26)))
    shell = occ.cut(outer, inner + holes)[0]
    lugs = []
    for x in (-95.0, 70.0, 127.0):
        lugs.append((3, B(x - 7, -25.7, -5.16, x + 7, -15.2, 9.84)))
    for x in (-95.0, -40.0, 127.0):
        lugs.append((3, B(x - 7, 115.0, -5.16, x + 7, 125.5, 9.84)))
    ears = []
    for x in (-65.0, 100.0):
        ears.append((3, B(x - 11, -30.7, Z_BOT, x + 11, -15.2, Z_BOT + 5)))
        ears.append((3, B(x - 11, 115.0, Z_BOT, x + 11, 130.5, Z_BOT + 5)))
    shell = occ.fuse(shell, lugs + ears)[0]
    honey = [(3, B(-9.7, -9.7, Z_FLOOR, 129.7, 108.7, CARRIER_BOT)),
             (3, B(-107.2, -9.7, Z_FLOOR, -10.0, 108.7, ADAPTER_BOT)),
             (3, B(-28.5, -30.7, Z_FLOOR, -10.6, -10.0, ADAPTER_BOT))]
    lidhc = occ.cut([(3, B(-109.1, -11.7, Z_TOP_IN - 4.5, 130.5, 111.5, Z_TOP_IN))],
                    [(3, B(49.0, 17.0, Z_TOP_IN - 5, 123.0, 77.0, Z_TOP_IN + 1))])[0]
    H34 = [(107.247 - 209.75, 198.004 - 93.0), (107.247 - 192.5, 198.004 - 148.5), (107.247 - 209.75, 198.004 - 204.0)]
    posts = [(3, C(x, y, Z_FLOOR, CARRIER_BOT, 9.0)) for x, y in [(-5, -5), (-5, 104), (125, -5), (125, 104)]]
    posts += [(3, C(x, y, Z_FLOOR, ADAPTER_BOT, 8.0)) for x, y in H34]
    clamps, pads = [], []
    for (x, y) in [(-5, -5), (-5, 104)] + H34:
        clamps.append((3, C(x, y, ADAPTER_TOP + 1.0, Z_TOP_IN, 9.0)))
        pads.append((3, C(x, y, ADAPTER_TOP, ADAPTER_TOP + 1.0, 9.0)))
    for (x, y) in [(125, -5), (125, 104)]:
        clamps.append((3, C(x, y, 1.0, Z_TOP_IN, 10.0)))
        pads.append((3, C(x, y, 0.0, 1.0, 10.0)))
    carrier = [(3, B(-10.0, -10.0, CARRIER_BOT, 130.0, 109.0, 0.0))]
    adapter = [(3, B(-107.5, -10.0, ADAPTER_BOT, 0.0, 109.0, ADAPTER_TOP)),
               (3, B(-28.8, -31.0, ADAPTER_BOT, -10.3, -10.0, ADAPTER_TOP))]
    adapter = occ.fuse(adapter[:1], adapter[1:])[0]
    som = [(3, B(51.1, 19.0, 0.0, 121.1, 75.0, 28.75))]
    spacers = [(3, C(x, y, 0.0, ADAPTER_BOT, 6.0)) for x, y in [(-5, -5), (-5, 104)]]
    groups = [("PRINT", shell), ("HONEY", honey + lidhc), ("PRINT", posts + clamps), ("TPU", pads),
              ("CARRIER", carrier), ("ADAPTER", adapter), ("SOM", som), ("SPACER", spacers)]
    allv = [d for _, g in groups for d in g]
    frag, fmap = occ.fragment(allv, [])
    occ.synchronize()
    owner = {}
    k = 0
    for name, g in groups:                     # later groups win the shared pieces
        for _ in g:
            for d in fmap[k]:
                owner[d] = name
            k += 1
    return owner


def mesh(owner):
    gmsh.option.setNumber("Mesh.MeshSizeMax", H)
    gmsh.option.setNumber("Mesh.MeshSizeMin", 0.8)
    gmsh.option.setNumber("Mesh.ElementOrder", 2)
    gmsh.option.setNumber("Mesh.Algorithm3D", 1)
    gmsh.option.setNumber("Mesh.HighOrderOptimize", 0)
    gmsh.option.setNumber("Mesh.SecondOrderLinear", 1)     # straight-sided C3D10: no inverted curved tets
    gmsh.model.mesh.generate(3)
    tags, xyz, _ = gmsh.model.mesh.getNodes()
    xyz = xyz.reshape(-1, 3)
    nid = {int(t): i for i, t in enumerate(tags)}
    els = {}
    for (d, t), name in owner.items():
        et, etags, enodes = gmsh.model.mesh.getElements(d, t)
        for typ, a, b in zip(et, etags, enodes):
            if typ != 11:                       # 10-node tetrahedron
                continue
            conn = np.asarray(b, dtype=np.int64).reshape(-1, 10)[:, [0, 1, 2, 3, 4, 5, 6, 7, 9, 8]]
            els.setdefault(name, []).append((np.asarray(a, dtype=np.int64), conn))
    for k in els:
        els[k] = (np.concatenate([a for a, _ in els[k]]), np.concatenate([b for _, b in els[k]]))
    return tags.astype(np.int64), xyz, els


def tet_volume(xyz, idx, conn):
    p = xyz[np.vectorize(idx.get)(conn[:, :4])]
    return np.abs(np.einsum("ij,ij->i", p[:, 1] - p[:, 0], np.cross(p[:, 2] - p[:, 0], p[:, 3] - p[:, 0]))) / 6


def write_deck(path, tags, xyz, els, mat, T, fixed, drop_fix, drop_dir):
    k = mat["k70"] if T == 70 else 1.0
    E = 0.5 * (mat["Exy"] + mat["Ez"]) * k
    nu = mat["nu"]
    Gs = E / (2 * (1 + nu))
    E3, E1 = RHO_STAR * E, 2.3 * RHO_STAR ** 3 * E
    G13 = 0.16 * Gs
    idx = {int(t): i for i, t in enumerate(tags)}
    vol = {n: tet_volume(xyz, idx, c).sum() for n, (_, c) in els.items()}
    rho = {"PRINT": mat["rho"], "HONEY": mat["rho"] * RHO_STAR, "TPU": TPU["rho"],
           "CARRIER": M_CARRIER / vol["CARRIER"], "ADAPTER": M_ADAPTER / vol["ADAPTER"], "SOM": M_SOM / vol["SOM"],
           "SPACER": 2.7e-9}
    with open(path, "w") as f:
        f.write("*HEADING\nKV260 + adapter enclosure\n*NODE, NSET=Nall\n")
        for t, (x, y, z) in zip(tags, xyz):
            f.write(f"{t},{x:.5f},{y:.5f},{z:.5f}\n")
        for name, (et, conn) in els.items():
            f.write(f"*ELEMENT, TYPE=C3D10, ELSET={name}\n")
            for e, c in zip(et, conn):
                f.write(f"{e}," + ",".join(str(int(tags[0] * 0 + n)) for n in c) + "\n")
        f.write("*ELSET, ELSET=Eall\n" + ",".join(els) + "\n")
        for name, ids in (("FIX", fixed), ("DROPFIX", drop_fix)):
            f.write(f"*NSET, NSET={name}\n")
            for i in range(0, len(ids), 12):
                f.write(",".join(str(int(n)) for n in ids[i:i + 12]) + "\n")
        f.write(f"*MATERIAL, NAME=M_PRINT\n*ELASTIC\n{E:.1f},{nu}\n*DENSITY\n{rho['PRINT']:.4e}\n")
        f.write(f"*MATERIAL, NAME=M_HONEY\n*ELASTIC, TYPE=ENGINEERING CONSTANTS\n"
                f"{E1:.2f},{E1:.2f},{E3:.2f},0.5,{nu * E1 / E3:.4f},{nu * E1 / E3:.4f},{E1 / 3:.2f},{G13:.2f},\n"
                f"{G13:.2f},{T}\n*DENSITY\n{rho['HONEY']:.4e}\n")
        f.write(f"*MATERIAL, NAME=M_TPU\n*ELASTIC\n{TPU['E']},{TPU['nu']}\n*DENSITY\n{rho['TPU']:.4e}\n")
        for n in ("CARRIER", "ADAPTER"):
            f.write(f"*MATERIAL, NAME=M_{n}\n*ELASTIC\n{FR4['E']},{FR4['nu']}\n*DENSITY\n{rho[n]:.4e}\n")
        f.write(f"*MATERIAL, NAME=M_SOM\n*ELASTIC\n3000.,0.3\n*DENSITY\n{rho['SOM']:.4e}\n")
        f.write(f"*MATERIAL, NAME=M_SPACER\n*ELASTIC\n70000.,0.33\n*DENSITY\n{rho['SPACER']:.4e}\n")
        for n in els:
            f.write(f"*SOLID SECTION, ELSET={n}, MATERIAL=M_{n}\n")
        f.write("*BOUNDARY\nFIX,1,3\n")
        f.write("*STEP\n*FREQUENCY\n10\n*NODE FILE\nU\n*END STEP\n")
        for name, d in (("vert", (0, 0, -1)), ("lat", (1, 0, 0)), ("long", (0, 1, 0))):
            f.write(f"*STEP\n*STATIC\n*DLOAD\nEall,GRAV,{G:.1f},{d[0]},{d[1]},{d[2]}\n"
                    "*NODE FILE\nU\n*EL FILE\nS\n*EL PRINT, ELSET=Eall, TOTALS=ONLY\nELSE\n*END STEP\n")
        # the drop: held at the struck corner, 1 g towards it; ccx changes the boundary per step
        f.write("*STEP\n*STATIC\n*BOUNDARY, OP=NEW\nDROPFIX,1,3\n"
                f"*DLOAD, OP=NEW\nEall,GRAV,{G:.1f},{drop_dir[0]:.5f},{drop_dir[1]:.5f},{drop_dir[2]:.5f}\n"
                "*NODE FILE\nU\n*EL FILE\nS\n*EL PRINT, ELSET=Eall, TOTALS=ONLY\nELSE\n*END STEP\n")
    return {n: float(rho[n] * vol[n]) for n in els}


def read_frd(path):
    """Result blocks of an ascii .frd in file order: [(name, {node: values})], name DISP or STRESS."""
    blocks, cur = [], None
    with open(path) as f:
        for line in f:
            if line.startswith(" -4 "):
                name = line.split()[1]
                cur = {} if name in ("DISP", "STRESS") else None
                if cur is not None:
                    blocks.append((name, cur))
            elif line.startswith(" -3"):
                cur = None
            elif cur is not None and line.startswith(" -1"):
                n = int(line[3:13])
                k = (len(line.rstrip()) - 13) // 12
                cur[n] = [float(line[13 + 12 * i:25 + 12 * i]) for i in range(k)]
    return blocks


def vm(s):
    s = np.asarray(s)
    return np.sqrt(0.5 * ((s[:, 0] - s[:, 1]) ** 2 + (s[:, 1] - s[:, 2]) ** 2 + (s[:, 2] - s[:, 0]) ** 2)
                   + 3 * (s[:, 3] ** 2 + s[:, 4] ** 2 + s[:, 5] ** 2))


def read_dat(path):
    txt = open(path).read()
    freqs = []
    m = re.search(r"E I G E N V A L U E   O U T P U T(.*?)P A R T I C I P A T I O N", txt, re.S)
    if m:
        for line in m.group(1).splitlines():
            p = line.split()
            if len(p) == 5 and p[0].isdigit():
                freqs.append(float(p[3]))
    mass = []
    m = re.search(r"E F F E C T I V E   M O D A L   M A S S(.*?)T O T A L", txt, re.S)
    if m:
        for line in m.group(1).splitlines():
            p = line.split()
            if len(p) == 7 and p[0].isdigit():
                mass.append([float(v) for v in p[1:4]])
    m = re.search(r"T O T A L   E F F E C T I V E   M A S S(.*?)\n\s*\n(.*?)\n", txt, re.S)
    energies = [float(x) for x in re.findall(r"internal energy \(element set EALL\).*?\n\s*\n\s*([-\d.E+]+)", txt, re.S)]
    if not energies:
        energies = [float(x) for x in re.findall(r"internal energy[^\n]*\n\s*\n\s*([-\d.E+]+)", txt)]
    return freqs, mass, energies


def main():
    os.makedirs(OUT, exist_ok=True)
    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.model.add("case")
    owner = build()
    tags, xyz, els = mesh(owner)
    print("nodes", len(tags), {k: len(v[0]) for k, v in els.items()}, flush=True)
    # the ears' washers (M5, 10 mm) on the vehicle: bottom-face nodes within 5 mm of each slot centre
    ears = [(x, y) for x in (-65.0, 100.0) for y in (-24.7, 124.5)]
    fixed = [int(t) for t, p in zip(tags, xyz) if abs(p[2] - Z_BOT) < 1e-3 and
             any(math.hypot(p[0] - x, p[1] - y) < 5.0 for x, y in ears)]
    corner = np.array([-113.6, -15.7, Z_BOT])
    drop_fix = [int(t) for t, p in zip(tags, xyz) if np.linalg.norm(p - corner) < 8.0]
    print("fixed nodes", len(fixed), "drop patch", len(drop_fix), flush=True)
    printed_nodes = np.unique(np.concatenate([els["PRINT"][1].ravel(), els["HONEY"][1].ravel()]))
    pos = dict(zip(tags.tolist(), xyz))
    results = {}
    for mname, mat in MATS.items():
        if ONLY and mname != ONLY:
            continue
        for T in (23, 70):
            run = f"{mname.replace(' ', '_')}_{T}"
            d = os.path.join(OUT, run)
            os.makedirs(d, exist_ok=True)
            com = np.array([0.0, 0.0, 0.0])
            masses = write_deck(os.path.join(d, "case.inp"), tags, xyz, els, mat, T, fixed, drop_fix, (0, 0, 0))
            m_tot = sum(masses.values())
            # centre of mass from the element masses would be better; the box's centre is close enough to aim
            com = np.array([10.0, 48.0, 8.0])
            ddir = (corner - com) / np.linalg.norm(corner - com)
            write_deck(os.path.join(d, "case.inp"), tags, xyz, els, mat, T, fixed, drop_fix, ddir)
            print(run, "solving", flush=True)
            subprocess.run(["ccx", "-i", "case"], cwd=d, stdout=open(os.path.join(d, "ccx.log"), "w"),
                           stderr=subprocess.STDOUT, check=True, env=dict(os.environ, OMP_NUM_THREADS="16"))
            freqs, mass, energies = read_dat(os.path.join(d, "case.dat"))
            blocks = read_frd(os.path.join(d, "case.frd"))
            S = [b for n, b in blocks if n == "STRESS"]
            U = [b for n, b in blocks if n == "DISP"]
            modes = U[:len(U) - len(S)]
            U = U[len(U) - len(S):]
            out = dict(mass_kg=m_tot * 1e3, masses_g={k: v * 1e6 for k, v in masses.items()}, freqs=freqs[:10],
                       modal_mass=mass[:10])
            names = ["vert", "lat", "long", "drop"]
            far = lambda n: (np.linalg.norm(pos[n] - corner) > 15.0)
            for i, nm in enumerate(names):
                st = S[i]
                pn = [n for n in printed_nodes if n in st]
                v = vm([st[n] for n in pn])
                if nm == "drop":
                    keep = np.array([far(n) for n in pn])
                else:
                    keep = np.array([min(math.hypot(pos[n][0] - x, pos[n][1] - y) for x, y in ears) > 10.0 for n in pn])
                u = U[i]
                umax = max(np.linalg.norm(u[n]) for n in u)
                out[nm] = dict(vm_max=float(v.max()), vm_max_away=float(v[keep].max()),
                               vm_p999=float(np.percentile(v[keep], 99.9)), u_max=float(umax),
                               energy=energies[i] if i < len(energies) else None)
            results[run] = out
            print(run, json.dumps({k: out[k] for k in ("mass_kg", "freqs")}), flush=True)
            if "--keep" not in argv:
                for fn in ("case.frd",):
                    if run not in ("PETG-CF_70", "PETG-CF_23"):
                        os.remove(os.path.join(d, fn))
            json.dump(dict(model=__doc__, mats=MATS, h=H, results=results),
                      open(os.path.join(OUT, "case_fea_raw.json"), "w"), indent=1)
    gmsh.finalize()


if __name__ == "__main__":
    main()
