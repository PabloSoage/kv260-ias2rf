#!/usr/bin/env python3
"""Possible integrations: sensor ranges in fog and a fused bird's-eye-view grid (docs/INTEGRATIONS.md).

1. Detection range of a car-sized target against meteorological visibility for a 905 nm LiDAR, a 77 GHz
   automotive radar and the 10.5 GHz AERIS radar. LiDAR: Koschmieder extinction (sigma = 3.912 / V) on both
   ways. Radars: ITU-R P.840 liquid-water attenuation (double-Debye permittivity) with the fog's liquid water
   content from its visibility (Eldridge). Each sensor is scaled from its clear-air range.
2. A bit-exact model of fpga/kria/integrations/kria_bev_grid.v, a scene (car, truck, guard rail, post) seen by a
   LiDAR and a 77 GHz radar in clear air and in fog, the fused grid, and the stimulus and expected-dump files for
   fpga/sim/tb_kria_bev_grid.v.

Usage: python bev_fusion_sim.py [--out DIR]   (figures go to docs/img/integrations/)
"""
import argparse
import math
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
IMG = os.path.join(REPO, "docs", "img", "integrations")

# ----------------------------------------------------------------------------------------------------------------
# 1. ranges in fog
# ----------------------------------------------------------------------------------------------------------------
def p840_kl(f_ghz, t_c=10.0):
    """ITU-R P.840 specific attenuation coefficient of liquid water, (dB/km)/(g/m^3)."""
    theta = 300.0 / (273.15 + t_c)
    e0 = 77.66 + 103.3 * (theta - 1)
    e1 = 0.0671 * e0
    e2 = 3.52
    fp = 20.20 - 146 * (theta - 1) + 316 * (theta - 1) ** 2
    fs = 39.8 * fp
    epp = f_ghz * (e0 - e1) / (fp * (1 + (f_ghz / fp) ** 2)) + f_ghz * (e1 - e2) / (fs * (1 + (f_ghz / fs) ** 2))
    ep = (e0 - e1) / (1 + (f_ghz / fp) ** 2) + (e1 - e2) / (1 + (f_ghz / fs) ** 2) + e2
    eta = (2 + ep) / epp
    return 0.819 * f_ghz / (epp * (1 + eta ** 2))


def fog_lwc(vis_m):
    """Liquid water content (g/m^3) of fog from its visibility, Eldridge: V[km] = 0.024 M^-0.65."""
    return (0.024 / (vis_m / 1000.0)) ** (1 / 0.65)


def lidar_range(r0, vis_m):
    """Range where rho/R^2 * exp(-2 sigma R) equals the clear-air threshold at r0."""
    sigma = 3.912 / vis_m
    lo, hi = 0.01, r0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if math.exp(-2 * sigma * mid) / mid ** 2 >= 1 / r0 ** 2:
            lo = mid
        else:
            hi = mid
    return lo


def radar_range(r0, f_ghz, vis_m):
    """Range where 1/R^4 * 10^(-2 a R / 10) equals the clear-air threshold at r0 (a in dB/m)."""
    a = p840_kl(f_ghz) * fog_lwc(vis_m) / 1000.0
    lo, hi = 0.01, r0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if 10 ** (-2 * a * mid / 10) / mid ** 4 >= 1 / r0 ** 4:
            lo = mid
        else:
            hi = mid
    return lo, a * 1000


# ----------------------------------------------------------------------------------------------------------------
# 2. the grid core, bit-exact
# ----------------------------------------------------------------------------------------------------------------
class BevGrid:
    def __init__(self, origin_x, origin_y, hit, miss, ray, decay_shift=3):
        self.g = np.zeros((256, 256), dtype=np.int16)
        self.ox, self.oy, self.hit, self.miss, self.ray = origin_x, origin_y, hit, miss, ray
        self.ds = decay_shift

    def _upd(self, x, y, d):
        v = int(self.g[x, y]) + d
        self.g[x, y] = max(-127, min(127, v))

    def detect(self, qx, qy, s):
        hx = ((qx >> 8) + 128) & 0xFF
        hy = ((qy >> 8) + 128) & 0xFF
        ox, oy = self.ox[s], self.oy[s]
        if self.ray[s] and not (ox == hx and oy == hy):
            dx, dy = abs(hx - ox), -abs(hy - oy)
            err = dx + dy
            sx, sy = (1 if hx >= ox else -1), (1 if hy >= oy else -1)
            x, y = ox, oy
            while not (x == hx and y == hy):
                self._upd(x, y, -self.miss[s])
                e2 = 2 * err
                stx, sty = e2 >= dy, e2 <= dx
                err += (dy if stx else 0) + (dx if sty else 0)
                if stx:
                    x = (x + sx) & 0xFF
                if sty:
                    y = (y + sy) & 0xFF
        self._upd(hx, hy, self.hit[s])

    def decay(self):
        v = self.g.astype(np.int32)
        mag = np.abs(v)
        step = np.where(mag >> self.ds == 0, np.where(mag == 0, 0, 1), mag >> self.ds)
        self.g = (v - np.sign(v) * step).astype(np.int16)


# ----------------------------------------------------------------------------------------------------------------
# scene: vehicle at the grid centre, x forward, y left, metres
# ----------------------------------------------------------------------------------------------------------------
CELL = 0.5
OBST = [  # (name, x0, x1, y0, y1, LiDAR reflectivity, radar RCS m^2)
    ("car", 24.0, 28.5, 0.8, 2.6, 0.10, 10.0),
    ("truck", 46.0, 54.0, -1.6, 0.9, 0.30, 100.0),
    ("post", 14.0, 14.3, 4.0, 4.3, 0.50, 1.0),
    ("guard rail", 6.0, 60.0, -5.2, -5.0, 0.60, 3.0),
]


def ray_hit(ang):
    """First obstacle a ray from (0, 0) at azimuth ang meets: (range, obstacle) or None."""
    c, s = math.cos(ang), math.sin(ang)
    best = None
    for o in OBST:
        _, x0, x1, y0, y1 = o[:5]
        tmin, tmax = 0.0, 1e9
        ok = True
        for p, d, lo, hi in ((0.0, c, x0, x1), (0.0, s, y0, y1)):
            if abs(d) < 1e-12:
                if not (lo <= p <= hi):
                    ok = False
                continue
            t1, t2 = (lo - p) / d, (hi - p) / d
            tmin, tmax = max(tmin, min(t1, t2)), min(tmax, max(t1, t2))
        if ok and tmin <= tmax and tmin > 0 and (best is None or tmin < best[0]):
            best = (tmin, o)
    return best


def q88(m):
    return int(round(m / CELL * 256)) & 0xFFFF


def scene_words(vis_m, rng, frames=4):
    """Command words for `frames` frames of LiDAR (sensor 0) and 77 GHz radar (sensor 1) data, decay between."""
    words = []
    lidar_r0 = 40.0                                  # 10 % target, clear air (Mid-360 class)
    sigma = 0.0 if vis_m is None else 3.912 / vis_m
    for _ in range(frames):
        for k in range(-300, 301):                   # +-60 degrees, 0.2 degree steps
            ang = math.radians(k * 0.2)
            h = ray_hit(ang)
            if vis_m is not None and rng.random() < min(0.7, 2.0 * sigma):
                r = rng.uniform(0.8, 6.0)            # fog backscatter: a false return close to the sensor
                words.append((q88(r * math.cos(ang)), q88(r * math.sin(ang)), 0))
                continue
            if h is None:
                continue
            r, o = h
            rmax = lidar_r0 * math.sqrt(o[5] / 0.10)
            rdet = rmax if vis_m is None else lidar_range(rmax, vis_m)
            if r <= rdet:
                rr = r + rng.normal(0, 0.03)
                words.append((q88(rr * math.cos(ang)), q88(rr * math.sin(ang)), 0))
        for o in OBST:                               # radar: a few scatterers per object, 0.25 m noise
            name, x0, x1, y0, y1 = o[:5]
            n = 6 if name == "guard rail" else 2
            for j in range(n):
                xm = x0 + (x1 - x0) * (j + 0.5) / n if name == "guard rail" else x0
                ym = 0.5 * (y0 + y1) + (rng.normal(0, 0.2) if name != "guard rail" else 0)
                words.append((q88(xm + rng.normal(0, 0.15)), q88(ym + rng.normal(0, 0.15)), 1))
        words.append(("decay",))
    return words


def run(words, cfg):
    g = BevGrid(**cfg)
    for w in words:
        if w[0] == "decay":
            g.decay()
        else:
            qx, qy, s = w
            g.detect(qx - 65536 if qx & 0x8000 else qx, qy - 65536 if qy & 0x8000 else qy, s)
    return g.g


def write_bench_files(words, grid, outdir):
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "bev_stim.hex"), "w") as f:
        for w in words:
            if w[0] == "decay":
                f.write("%09X\n" % (1 << 34))
            else:
                qx, qy, s = w
                f.write("%09X\n" % ((s << 32) | (qy << 16) | qx))
        f.write("%09X\n" % (2 << 34))
    with open(os.path.join(outdir, "bev_expect.hex"), "w") as f:
        flat = grid.astype(np.int16).reshape(-1)     # address {x, y}: row x, column y
        for b in range(0, 65536, 8):
            word = 0
            for k in range(8):
                word |= (int(flat[b + k]) & 0xFF) << (8 * k)
            f.write("%016X\n" % word)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(REPO, "fpga", "sim", "out", "bev"))
    args = ap.parse_args()
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    os.makedirs(IMG, exist_ok=True)

    # ---- ranges in fog ----
    vis = np.logspace(np.log10(20), np.log10(2000), 120)
    lid10 = [lidar_range(40.0, v) for v in vis]
    lid80 = [lidar_range(70.0, v) for v in vis]
    r77 = [radar_range(200.0, 77.0, v)[0] for v in vis]
    r10 = [radar_range(400.0, 10.5, v)[0] for v in vis]
    fig, ax = plt.subplots(figsize=(8, 4.6))
    ax.semilogx(vis, lid10, label="LiDAR 905 nm, 10 % target (40 m clear)", color="#d6604d")
    ax.semilogx(vis, lid80, label="LiDAR 905 nm, 80 % target (70 m clear)", color="#f4a582", ls="--")
    ax.semilogx(vis, r77, label="77 GHz radar, car (200 m clear)", color="#2166ac")
    ax.semilogx(vis, r10, label="10.5 GHz AERIS, car (400 m clear)", color="#4393c3", ls="--")
    ax.set_xlabel("meteorological visibility (m)")
    ax.set_ylabel("detection range (m)")
    ax.set_ylim(0, 420)
    ax.grid(True, which="both", alpha=0.3)
    ax.legend(loc="center left", bbox_to_anchor=(0.01, 0.42), fontsize=8)
    ax.set_title("Detection range in fog (LiDAR: Koschmieder; radar: ITU-R P.840)")
    fig.tight_layout()
    fig.savefig(os.path.join(IMG, "fog_ranges.png"), dpi=150)
    plt.close(fig)
    fog_tab = []
    for v in (1000, 200, 100, 50, 30):
        fog_tab.append((v, fog_lwc(v), lidar_range(40, v), lidar_range(70, v), radar_range(200, 77, v)[1],
                        radar_range(200, 77, v)[0], radar_range(400, 10.5, v)[1]))

    # ---- fused grid ----
    cfg = dict(origin_x=[128, 132, 132, 128], origin_y=[128, 128, 128, 128],
               hit=[24, 64, 48, 0], miss=[6, 0, 0, 0], ray=[1, 0, 0, 0])
    # fog mode: the host sees the LiDAR's near returns multiply (backscatter) and trusts it less
    cfg_fog = dict(cfg, hit=[6, 64, 48, 0], miss=[3, 0, 0, 0])
    rng = np.random.default_rng(7)
    w_clear = scene_words(None, rng)
    w_fog = scene_words(30.0, rng)
    lidar_only = dict(cfg, hit=[24, 0, 0, 0])
    grids = {
        "clear, LiDAR only": run([w for w in w_clear if w[0] == "decay" or w[2] == 0], lidar_only),
        "fog 30 m, LiDAR only": run([w for w in w_fog if w[0] == "decay" or w[2] == 0], lidar_only),
        "fog 30 m, LiDAR + 77 GHz radar": run(w_fog, cfg),
        "fog 30 m, fused, fog mode": run(w_fog, cfg_fog),
    }
    fig, axs = plt.subplots(1, 4, figsize=(16, 4.8))
    for ax, (title, g) in zip(axs, grids.items()):
        # forward up, left to the left: show x 0..64 m (rows 128..255), y -16..16 m (columns 96..160)
        sub = g[128:256, 96:161][::-1, ::-1]
        im = ax.imshow(sub, cmap="RdBu_r", vmin=-127, vmax=127, extent=[16, -16, 0, 64], aspect="auto")
        for o in OBST:
            _, x0, x1, y0, y1 = o[:5]
            ax.add_patch(plt.Rectangle((y0, x0), y1 - y0, x1 - x0, fill=False, ec="k", lw=0.8))
        ax.set_xlim(16, -16)
        ax.set_title(title, fontsize=10)
        ax.set_xlabel("y, left (m)")
    axs[0].set_ylabel("x, forward (m)")
    fig.colorbar(im, ax=axs, shrink=0.8, label="log-odds (red occupied, blue free)")
    fig.savefig(os.path.join(IMG, "bev_fusion_fog.png"), dpi=150)
    plt.close(fig)

    write_bench_files(w_fog, grids["fog 30 m, fused, fog mode"], args.out)
    with open(os.path.join(args.out, "bev_cfg.txt"), "w") as f:
        for k in ("origin_x", "origin_y", "hit", "miss"):
            f.write(" ".join(str(v) for v in cfg_fog[k]) + "\n")
        f.write(" ".join(str(v) for v in cfg_fog["ray"]) + "\n")
    n_det = sum(1 for w in w_fog if w[0] != "decay")
    print("fog table: vis m, LWC g/m3, LiDAR10 m, LiDAR80 m, 77GHz dB/km, 77GHz range m, 10.5GHz dB/km")
    for row in fog_tab:
        print("  %5d %.3f %6.1f %6.1f %.3f %6.1f %.4f" % row)
    for title, g in grids.items():
        occ = int((g > 20).sum())
        free = int((g < -20).sum())
        car = int(g[128 + 48:128 + 57, 128 + 2:128 + 5].max())
        print("%-32s occupied %5d free %5d car max %4d" % (title, occ, free, car))
    print("stimulus: %d detections, %d frames -> %s" % (n_det, sum(1 for w in w_fog if w[0] == "decay"), args.out))


if __name__ == "__main__":
    main()
