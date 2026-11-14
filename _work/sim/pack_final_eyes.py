"""Pack 8-layer routed LVDS/SGMII eye waveforms and final PCB skew data into compact repo artifacts."""
import json
import os
import shutil
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SIM_DIR = os.path.join(ROOT, "_work", "sim")
SCRATCH = os.environ.get("EYE_SCRATCH", os.path.join(ROOT, "_work", "sim", "eyes_raw"))  # routed-eye CSVs

EYE_SOURCES = {
    "LINK_RX_D0_1G":    os.path.join(SCRATCH, "cmp8", "final3.txt.eyes", "eye_LINK_RX_D0_1G_routed.csv"),
    "LINK_RX_D1_1G":    os.path.join(SCRATCH, "cmp8", "final3.txt.eyes", "eye_LINK_RX_D1_1G_routed.csv"),
    "LINK_RX_CLK_1G":   os.path.join(SCRATCH, "cmp8", "final3.txt.eyes", "eye_LINK_RX_CLK_1G_routed.csv"),
    "LINK_TX_D0_1G":    os.path.join(SCRATCH, "cmp8", "final3.txt.eyes", "eye_LINK_TX_D0_1G_routed.csv"),
    "LINK_TX_CLK_1G":   os.path.join(SCRATCH, "cmp8", "final3.txt.eyes", "eye_LINK_TX_CLK_1G_routed.csv"),
    "ADCS_FCO_1G":      os.path.join(SCRATCH, "cmp8", "final3.txt.eyes", "eye_ADCS_FCO_1G_routed.csv"),
    "ADCS_DCO_1G":      os.path.join(SCRATCH, "cmp8", "final3.txt.eyes", "eye_ADCS_DCO_1G_routed.csv"),
    "ADCS_D0_1G":       os.path.join(SCRATCH, "cmp8", "final3.txt.eyes", "eye_ADCS_D0_1G_routed.csv"),
    "ADCR_DCO_1G":      os.path.join(SCRATCH, "cmp8", "final3.txt.eyes", "eye_ADCR_DCO_1G_routed.csv"),
    "ADCR_D0_1G":       os.path.join(SCRATCH, "cmp8", "final3.txt.eyes", "eye_ADCR_D0_1G_routed.csv"),
    "CLK_ADCS_1G":      os.path.join(SCRATCH, "cmp8", "final3.txt.eyes", "eye_CONTROL_FPGA_CLK_1G_routed.csv"),
    "ETH_SGTX_1P25G":   os.path.join(SCRATCH, "eyes", "eye_CONTROL_ETH_SGTX_PHY_1.25G_routed.csv"),
    "ETH_SGRX_1P25G":   os.path.join(SCRATCH, "eyes", "eye_CONTROL_ETH_SGRX_PHY_1.25G_routed.csv"),
}


def extract_2ui_traces(csv_path, grid, n_keep=160):
    data = np.loadtxt(csv_path, delimiter=",", skiprows=1, dtype=np.float64)
    ph = data[:, 0]
    vm = data[:, 1]
    wraps = np.where(np.diff(ph) < -0.5)[0] + 1
    bounds = np.concatenate(([0], wraps, [len(ph)]))
    full_1ui = []
    traces_2ui = []
    for i in range(len(bounds) - 1):
        s, e = bounds[i], bounds[i + 1]
        if e - s < 25:
            continue
        seg_ph = ph[s:e]
        seg_vm = vm[s:e]
        if seg_ph[0] <= 0.05 and seg_ph[-1] >= 1.90:
            _, uniq_idx = np.unique(seg_ph, return_index=True)
            traces_2ui.append(np.interp(grid, seg_ph[uniq_idx], seg_vm[uniq_idx]))
        elif seg_ph[0] <= 0.05 and seg_ph[-1] >= 0.95:
            _, uniq_idx = np.unique(seg_ph, return_index=True)
            full_1ui.append((seg_ph[uniq_idx], seg_vm[uniq_idx]))
    if not traces_2ui and len(full_1ui) >= 2:
        for k in range(len(full_1ui) - 1):
            p1, v1 = full_1ui[k]
            p2, v2 = full_1ui[k + 1]
            p12 = np.concatenate([p1, p2 + 1.0])
            v12 = np.concatenate([v1, v2])
            _, uniq_idx = np.unique(p12, return_index=True)
            traces_2ui.append(np.interp(grid, p12[uniq_idx], v12[uniq_idx]))
    arr = np.array(traces_2ui, dtype=np.float32) if traces_2ui else np.zeros((0, len(grid)), dtype=np.float32)
    if len(arr) > n_keep:
        sel = np.linspace(0, len(arr) - 1, n_keep, dtype=int)
        arr = arr[sel]
    return arr


def main():
    os.makedirs(SIM_DIR, exist_ok=True)
    grid = np.linspace(0.0, 2.0, 201, dtype=np.float32)
    packed = {"phase_grid": grid}
    summary = {}
    for key, path in EYE_SOURCES.items():
        if not os.path.isfile(path):
            print(f"MISSING: {path}")
            continue
        arr = extract_2ui_traces(path, grid, n_keep=160)
        if len(arr) == 0:
            print(f"EMPTY: {key}")
            continue
        packed[key] = arr
        # Measure vertical eye height at 0.5 UI & 1.5 UI centers (indices ~50 and ~150)
        heights = []
        for idx in (50, 150):
            col = arr[:, idx]
            hi = col[col > 0]
            lo = col[col < 0]
            if len(hi) and len(lo):
                heights.append(float(np.min(hi) - np.max(lo)))
        eye_h = float(min(heights)) if heights else 0.0
        summary[key] = {"n_traces": int(arr.shape[0]), "eye_height_mV": round(eye_h, 1)}
        print(f"Packed {key:18s}: {arr.shape} | center eye height = {eye_h:.1f} mV")

    out_npz = os.path.join(SIM_DIR, "eyes_8layer_routed.npz")
    np.savez_compressed(out_npz, **packed)
    print(f"Saved {out_npz} ({os.path.getsize(out_npz) / 1024:.1f} KB)")

    # Preserve routed summary CSVs + skew JSON cleanly inside _work/sim/
    shutil.copy2(os.path.join(SCRATCH, "cmp8", "final3.txt.eyes", "lvds_eye.csv"), os.path.join(SIM_DIR, "lvds_eye_8layer.csv"))
    tmp_skew = os.path.join(ROOT, "_work", "_tmp_skew.json")
    dst_skew = os.path.join(SIM_DIR, "lvds_skew_8layer.json")
    if os.path.isfile(tmp_skew):
        shutil.move(tmp_skew, dst_skew)
        print(f"Moved {tmp_skew} -> {dst_skew}")

    with open(os.path.join(SIM_DIR, "eye_summary_8layer.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)


if __name__ == "__main__":
    main()
