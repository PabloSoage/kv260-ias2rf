"""Turns fea_case.py's raw results into the figures and the table of docs/ENCLOSURE.md section 5.

    micromamba run -n fea python _work/mech/post_fea.py [FEA_OUT dir]

Reads <FEA_OUT>/case_fea_raw.json (and PETG-CF_70's case.inp/.frd for the field plots); writes
docs/sim/case_fea.json, docs/sim/case_materials.png and _work/mech/cache/fea_*.ply (for render_fea.py).

Derived quantities, each an engineering estimate with its assumption stated:
- 50 g shock: the 1 g static stress x 50 (linear), against the across-layer strength at that temperature.
- 1 m corner drop: the case held at the struck corner and pushed towards it by g gives the strain energy U1 at
  1 g; the drop's energy m g h stored elastically needs n = sqrt(m g h / U1) g, and the stress scales by n.
  The 15 mm around the corner (where the plastic crushes locally) is left out of the stress.
  This is deliberately pessimistic (rigid floor, all the energy stored elastically in the case).
- Same drop with the TPU 95A corner bumpers (build_case.py, 18 mm thick, gyroid infill): a crushable layer that
  stops the case over d = 0.6 x 18 mm of crush at a near-constant force (efficiency 0.8) gives n = h / (0.8 d)
  g; the stress per g is the bare case's.
- Random vibration: Miles' equation at the first mode with a large vertical effective mass, Q = 10
  (plastic, 5 % damping), on an assumed off-road envelope of 0.04 g^2/Hz flat (about 4.4 g rms from 10 to
  500 Hz); 3-sigma stress against a fatigue limit of 0.3 x the across-layer strength.
"""
import json, math, os, sys
import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FEA = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "_work", "mech", "cache", "fea")
raw = json.load(open(os.path.join(FEA, "case_fea_raw.json")))
MATS = raw["mats"]
S70 = {"PLA": 0.10, "PETG": 0.50, "PETG-CF": 0.60, "ASA": 0.80, "PAHT-CF": 0.70, "Resin ABS-like": 0.30}   # [I]
PSD, Q, H_DROP, FAT = 0.04, 10.0, 1000.0, 0.30
BUMP, CRUSH, EFF = 18.0, 0.6, 0.8

rows = []
for mname, mat in MATS.items():
    for T in (23, 70):
        key = f"{mname.replace(' ', '_')}_{T}"
        r = raw["results"].get(key)
        if not r:
            continue
        s_allow = mat["sz"] * (S70[mname] if T == 70 else 1.0)
        m_kg = r["mass_kg"]
        mm = np.array(r["modal_mass"]) if r["modal_mass"] else np.zeros((len(r["freqs"]), 3))
        zfrac = mm[:, 2] / max(mm[:, 2].sum(), 1e-30) if len(mm) else []
        fz = next((f for f, z in zip(r["freqs"], zfrac) if z > 0.10), r["freqs"][0])
        s1v = r["vert"]["vm_max_away"]
        s1l = max(r["lat"]["vm_max_away"], r["long"]["vm_max_away"])
        U1 = r["drop"]["energy"]                                 # N mm at 1 g
        Ed = m_kg * 1e-3 * 9810.0 * H_DROP                       # t * mm/s^2 * mm = N mm
        n_drop = math.sqrt(Ed / U1) if U1 else float("nan")
        s_drop = n_drop * r["drop"]["vm_max_away"]
        n_bump = min(n_drop, H_DROP / (EFF * CRUSH * BUMP))
        s_bump = n_bump * r["drop"]["vm_max_away"]
        g_rms = math.sqrt(math.pi / 2 * fz * Q * PSD)
        s_vib = 3 * g_rms * s1v
        rows.append(dict(material=mname, T=T, mass_kg=m_kg, f1=r["freqs"][0], fz=fz, s_allow=s_allow,
                         shock_v=50 * s1v, shock_l=50 * s1l, sf_shock=s_allow / (50 * max(s1v, s1l)),
                         drop_g=n_drop, drop_s=s_drop, sf_drop=s_allow / s_drop,
                         bump_g=n_bump, bump_s=s_bump, sf_bump=s_allow / s_bump,
                         vib_grms=g_rms, vib_s3=s_vib, sf_vib=FAT * s_allow / s_vib,
                         u_shock=50 * r["vert"]["u_max"], hdt=mat["hdt"], printer=mat["printer"], src=mat["src"]))
json.dump(dict(assumptions=__doc__, psd_g2_hz=PSD, Q=Q, drop_mm=H_DROP, fatigue_fraction=FAT,
               strength_kept_at_70C=S70, rows=rows), open(os.path.join(ROOT, "docs", "sim", "case_fea.json"), "w"), indent=1)
for r in rows:
    print(f"{r['material']:15s} {r['T']:3d}C m={r['mass_kg']:.2f} kg f1={r['f1']:6.0f} fz={r['fz']:6.0f} Hz "
          f"shock {r['shock_v']:5.1f}/{r['shock_l']:5.1f} MPa SF {r['sf_shock']:5.1f} | drop {r['drop_g']:5.0f} g "
          f"{r['drop_s']:5.1f} MPa SF {r['sf_drop']:4.1f} | bumpers {r['bump_g']:4.0f} g SF {r['sf_bump']:4.1f} | vib {r['vib_grms']:4.1f} g {r['vib_s3']:5.1f} MPa SF {r['sf_vib']:4.1f}")

# ---- the materials figure: four small panels, one row per material, 23 C and 70 C ---------------------------
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
INK, MUTED, GRID = "#1f2328", "#59636e", "#e6e9ec"
C23, C70 = "#2f6fb3", "#c4622d"
mats = list(MATS)
panels = [("f1", "First mode, Hz", None), ("sf_shock", "50 g shock: safety factor", 1.0),
          ("sf_drop", "1 m corner drop, bare: SF", 1.0), ("sf_bump", "1 m drop, TPU bumpers: SF", 1.0),
          ("sf_vib", "Vibration fatigue: SF", 1.0)]
fig, axs = plt.subplots(1, 5, figsize=(16, 3.9), dpi=150, sharey=True)
for ax, (k, title, ref) in zip(axs, panels):
    for i, m in enumerate(mats):
        for T, c, dy in ((23, C23, -0.19), (70, C70, 0.19)):
            r = next((x for x in rows if x["material"] == m and x["T"] == T), None)
            if not r:
                continue
            v = r[k]
            y = i + dy
            ax.barh(y, v, height=0.36, color=c, edgecolor="white", linewidth=1.5)
            xv = v * 1.06 if ref is None else min(max(v, 0.035) * 1.12, 14)
            ax.text(xv, y, f"{v:.0f}" if k == "f1" else (f"{v:.2f}" if v < 0.1 else f"{v:.1f}"),
                    va="center", fontsize=7.5, color=INK)
    if ref:
        ax.axvline(ref, color=INK, lw=1, ls=(0, (4, 3)))
        ax.axvline(2 * ref, color=MUTED, lw=0.8, ls=(0, (1, 2)))
        ax.set_xscale("log")
        ax.set_xlim(0.03, 20)
    ax.set_title(title, fontsize=9.5, color=INK, loc="left")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.spines["left"].set_color(MUTED)
    ax.spines["bottom"].set_color(MUTED)
    ax.tick_params(colors=MUTED, labelsize=8)
    ax.xaxis.grid(True, color=GRID, lw=0.8)
    ax.set_axisbelow(True)
axs[0].set_yticks(range(len(mats)))
axs[0].set_yticklabels(mats, fontsize=9, color=INK)
axs[0].invert_yaxis()
from matplotlib.patches import Patch
fig.legend(handles=[Patch(color=C23, label="23 °C"), Patch(color=C70, label="70 °C (hot vehicle)")],
           loc="upper right", ncol=2, frameon=False, fontsize=9)
fig.text(0.01, 0.97, "Enclosure FEA by print material (CalculiX; dashed line: safety factor 1, dotted: 2)",
         fontsize=10.5, color=INK, va="top")
fig.subplots_adjust(left=0.08, right=0.99, top=0.82, bottom=0.12, wspace=0.14)
fig.savefig(os.path.join(ROOT, "docs", "sim", "case_materials.png"))
print("wrote docs/sim/case_materials.png")

# ---- field plots: PETG-CF at 70 C, the vertical 50 g stress and the first mode, as coloured PLY ------------
run = os.path.join(FEA, "PETG-CF_70")
if os.path.exists(os.path.join(run, "case.frd")):
    sys.path.insert(0, os.path.dirname(__file__))
    from fea_case import read_frd
    nodes, els, cur = {}, {}, None
    for line in open(os.path.join(run, "case.inp")):
        if line.startswith("*"):
            u = line.upper()
            cur = "N" if u.startswith("*NODE,") else (u.split("ELSET=")[1].strip() if u.startswith("*ELEMENT") else None)
            continue
        if cur == "N":
            p = line.split(",")
            nodes[int(p[0])] = [float(v) for v in p[1:4]]
        elif cur:
            p = [int(v) for v in line.split(",")]
            els.setdefault(cur, []).append(p[1:5])
    blocks = read_frd(os.path.join(run, "case.frd"))
    disp = [b for n, b in blocks if n == "DISP"]
    stress = [b for n, b in blocks if n == "STRESS"]
    n_modes = len(disp) - len(stress)
    tets = np.array([t for k in ("PRINT", "HONEY") for t in els[k]])
    faces = np.sort(np.concatenate([tets[:, [0, 1, 2]], tets[:, [0, 1, 3]], tets[:, [0, 2, 3]], tets[:, [1, 2, 3]]]), axis=1)
    uniq, cnt = np.unique(faces, axis=0, return_counts=True)
    surf = uniq[cnt == 1]
    used = np.unique(surf)
    S = stress[0]
    from fea_case import vm
    vals = vm([S[n] for n in used]) * 50.0
    r70 = next(x for x in rows if x["material"] == "PETG-CF" and x["T"] == 70)
    lim = r70["s_allow"]

    def ramp(t):
        """Sequential: light grey-blue to deep orange-red (one warm hue), t in 0..1."""
        a, b = np.array([0.86, 0.88, 0.90]), np.array([0.75, 0.16, 0.05])
        t = np.clip(t, 0, 1) ** 0.6
        return a + (b - a) * t[:, None]

    def ply(path, coords, cols):
        idx = {n: i for i, n in enumerate(used)}
        with open(path, "w") as f:
            f.write(f"ply\nformat ascii 1.0\nelement vertex {len(used)}\nproperty float x\nproperty float y\nproperty float z\n"
                    "property uchar red\nproperty uchar green\nproperty uchar blue\n"
                    f"element face {len(surf)}\nproperty list uchar int vertex_indices\nend_header\n")
            for n, c in zip(used, cols):
                x, y, z = coords[n]
                f.write(f"{x:.4f} {y:.4f} {z:.4f} {int(c[0] * 255)} {int(c[1] * 255)} {int(c[2] * 255)}\n")
            for a, b, c in surf:
                f.write(f"3 {idx[a]} {idx[b]} {idx[c]}\n")

    ply(os.path.join(ROOT, "_work", "mech", "cache", "fea_stress.ply"), nodes, ramp(vals / lim))
    m1 = disp[0]
    amp = np.array([np.linalg.norm(m1[n]) for n in used])
    scale = 6.0 / amp.max()
    moved = {n: [nodes[n][k] + scale * m1[n][k] for k in range(3)] for n in used}
    ply(os.path.join(ROOT, "_work", "mech", "cache", "fea_mode1.ply"), moved, ramp(amp / amp.max()))
    json.dump(dict(stress_limit=lim, stress_max_shown=float(vals.max()), mode1_hz=r70["f1"]),
              open(os.path.join(ROOT, "_work", "mech", "cache", "fea_ply.json"), "w"))
    print("wrote fea_stress.ply, fea_mode1.ply", float(vals.max()), lim)
