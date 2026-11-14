"""Colour bars, call-outs and captions on render_fea3d_hero.py's two renders.

    micromamba run -n fea python _work/mech/compose_fea3d_hero.py v2 Zm   # docs/img/case3d_<tag>_{stress,boards}.jpg
"""
import json, os, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.image as mpimg

tag, lc = sys.argv[1], sys.argv[2]
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
D = os.path.join(ROOT, "_work", "mech", "cache", "fea3d", tag)
res = json.load(open(os.path.join(ROOT, "docs", "sim", f"case3d_{tag}.json")))
c = res["cases"][lc]
meta = json.load(open(os.path.join(D, f"hero_{lc}.json")))
LOAD = {"Zm": "50 g downwards", "Xp": "50 g sideways", "Yp": "50 g fore-aft"}[lc]


def wsl(fn):
    fn = fn.replace("\\", "/")
    return "/mnt/" + fn[0].lower() + fn[2:] if fn[1] == ":" else fn


def figure(img, cmap, vmax, label, title, sub, calls, out):
    im = mpimg.imread(wsl(img))
    H0, W0 = im.shape[:2]
    ink = (im[..., :3].min(axis=2) < 0.97).nonzero()          # crop to the object, 50 px margin
    y0, y1 = max(ink[0].min() - 50, 0), min(ink[0].max() + 50, H0)
    x0, x1 = max(ink[1].min() - 160, 0), min(ink[1].max() + 50, W0)
    im = im[y0:y1, x0:x1]
    calls = [(((x * W0 - x0) / (x1 - x0), (y * H0 - y0) / (y1 - y0)), t, d) for (x, y), t, d in calls]
    h, w = im.shape[:2]
    fig = plt.figure(figsize=(16, 16 * h / w * 0.86 + 1.4), dpi=110)
    ax = fig.add_axes([0.0, 0.0, 0.9, 0.86])
    ax.imshow(im)
    ax.set_axis_off()
    for (x, y), text, (dx, dy) in calls:
        ax.annotate(text, xy=(x * w, y * h), xytext=(x * w + dx, y * h + dy), fontsize=13,
                    color="#111", ha="center",
                    bbox=dict(boxstyle="round,pad=0.35", fc="white", ec="#333", lw=0.8, alpha=0.92),
                    arrowprops=dict(arrowstyle="-|>", color="#222", lw=1.4, shrinkA=0, shrinkB=4))
    cax = fig.add_axes([0.915, 0.12, 0.016, 0.62])
    cb = fig.colorbar(plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(0, vmax)), cax=cax)
    cb.set_label(label, fontsize=13)
    cb.ax.tick_params(labelsize=11)
    fig.text(0.02, 0.975, title, fontsize=18, weight="bold", va="top")
    fig.text(0.02, 0.935, sub, fontsize=13, va="top", color="#333")
    fig.savefig(out, dpi=110, pil_kwargs={"quality": 90})
    plt.close(fig)
    print("wrote", out)


ca = c["case"]
os.makedirs(os.path.join(ROOT, "docs", "img"), exist_ok=True)
figure(meta["case"]["file"], "turbo", res["scale_MPa"], f"von Mises stress (MPa), scale capped at {res['scale_MPa']:.1f}",
       f"Enclosure {tag}, {LOAD}: stress in the printed case",
       f"PETG-CF, both boards inside, held at the four M5 ears. 99.7 % of the case below {ca['vm_p997']:.1f} MPa; "
       f"safety factor {ca['sf_23C']:.1f} at 23 °C, {ca['sf_70C']:.1f} at 70 °C. Max displacement {c['umax_mm']:.2f} mm.",
       [(meta["case"]["peak_xy"], f"peak {ca['vm_peak']:.1f} MPa\nrib above the ear", (-300, -170))],
       os.path.join(ROOT, "docs", "img", f"case3d_{tag}_stress.jpg"))
ad, kv = c["adapter"], c["carrier"]
calls = []
offs = {"U1101": (80, -200), "U501": (-60, -230), "U601": (-200, -130)}
for ref, xy in meta["boards"]["bga_xy"].items():
    calls.append((xy, f"{ref} {c['bga'][ref]['ue_max']:.0f} µε", offs.get(ref, (0, -200))))
figure(meta["boards"]["file"], "viridis", res["scale_ue"], "largest principal strain (µε)",
       f"Enclosure {tag}, {LOAD}: strain in the two boards",
       f"Adapter bow {ad['bow_mm'] * 1000:.0f} µm, KV260 carrier {kv['bow_mm'] * 1000:.0f} µm. "
       f"At the BGAs at most {max(v['ue_max'] for v in c['bga'].values()):.0f} µε against a {res['ue_guide']:.0f} µε "
       f"guide for solder joints under shock.",
       calls, os.path.join(ROOT, "docs", "img", f"case3d_{tag}_boards.jpg"))
