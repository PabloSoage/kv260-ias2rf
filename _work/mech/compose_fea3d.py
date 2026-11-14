"""One figure per load case from render_fea3d.py's views: the case's von Mises stress (top row) and the boards'
largest principal strain (bottom row), each with its colour bar and verdict.

    micromamba run -n fea python _work/mech/compose_fea3d.py v1        # writes docs/sim/case3d_<tag>_<lc>.png
"""
import json, os, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.image as mpimg

tag = sys.argv[1]
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
D = os.path.join(ROOT, "_work", "mech", "cache", "fea3d", tag)
res = json.load(open(os.path.join(ROOT, "docs", "sim", f"case3d_{tag}.json")))
rend = json.load(open(os.path.join(D, "renders.json")))
NAMES = {"Zm": "50 g down", "Xp": "50 g along X (sideways)", "Yp": "50 g along Y (fore-aft)"}
TITLES = ["case, from above", "case, from below (ears, floor)", "case, close-up of the peak",
          "boards, top side", "boards, underside", "adapter around the FPGA (U1101)"]


def wsl(fn):
    fn = fn.replace("\\", "/")
    return "/mnt/" + fn[0].lower() + fn[2:] if fn[1] == ":" else fn


for lc, files in rend.items():
    c = res["cases"][lc]
    fig = plt.figure(figsize=(18, 12.5), dpi=100)
    for k, fn in enumerate(files):
        ax = fig.add_axes([0.01 + 0.31 * (k % 3), 0.50 - 0.43 * (k // 3), 0.305, 0.36])
        ax.imshow(mpimg.imread(wsl(fn)))
        ax.set_axis_off()
        ax.set_title(TITLES[k], fontsize=12)
    for row, (cmap, vmax, label) in enumerate((("turbo", res["scale_MPa"], "case: von Mises stress (MPa)"),
                                                ("viridis", res["scale_ue"], "boards: max principal strain (µε)"))):
        cax = fig.add_axes([0.945, 0.53 - 0.43 * row, 0.012, 0.3])
        cb = fig.colorbar(plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(0, vmax)), cax=cax)
        cb.set_label(label, fontsize=11)
    ca, ad, kv = c["case"], c["adapter"], c["carrier"]
    bga = ", ".join(f"{k} {v['ue_max']:.0f} µε" for k, v in c.get("bga", {}).items())
    fig.text(0.01, 0.985, f"Enclosure {tag} with both boards: {NAMES[lc]}, quasi-static. PETG-CF case, FR-4 boards, "
             f"ears held at the M5 washers. {res['tets']:,} tets, {res['nodes']:,} nodes",
             fontsize=13, va="top", weight="bold")
    fig.text(0.01, 0.955, f"Case: 99.7th pct {ca['vm_p997']:.1f} MPa (peak {ca['vm_peak']:.1f} at "
             f"{tuple(round(x) for x in ca['peak_at'])}), safety factor {ca['sf_23C']:.1f} at 23 C / "
             f"{ca['sf_70C']:.1f} at 70 C on the across-layer strength.   Max displacement {c['umax_mm']:.2f} mm.",
             fontsize=12, va="top")
    fig.text(0.01, 0.93, f"Boards: adapter {ad['ue_p997']:.0f} µε (peak {ad['ue_peak']:.0f}), bow "
             f"{ad['bow_mm'] * 1000:.0f} µm; KV260 carrier {kv['ue_p997']:.0f} µε (peak {kv['ue_peak']:.0f}), "
             f"bow {kv['bow_mm'] * 1000:.0f} µm; at the BGAs: {bga}.   Guide for BGA joints under shock: "
             f"{res['ue_guide']:.0f} µε.", fontsize=12, va="top")
    out = os.path.join(ROOT, "docs", "sim", f"case3d_{tag}_{lc}.png")
    fig.savefig(out, dpi=100)
    plt.close(fig)
    print("wrote", out)
