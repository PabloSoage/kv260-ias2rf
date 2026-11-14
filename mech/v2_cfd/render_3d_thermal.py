#!/usr/bin/env python3
"""
High-resolution (1600+ px) offscreen 3D thermal & airflow renders of the
Built Enclosure v2 using PyVista + VTK (`micromamba run -n fea`).

Combines CAD STLs (`mech/case_v2_bottom.stl`, `mech/case_v2_lid.stl` rotated
180 deg around X, `mech/case_v2_filter_frame.stl`) with solved 3D OpenFOAM VTK
fields (`results_built_v2.json` + `/home/varuna/cfd_scratch_v2/<case>/VTK`).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("PYVISTA_OFF_SCREEN", "true")

import numpy as np
import pyvista as pv

pv.OFF_SCREEN = True

ROOT = Path(__file__).resolve().parents[2]
MECH_DIR = ROOT / "mech"
OUT_DIR = ROOT / "docs" / "sim"
SCRATCH = Path("/home/varuna/cfd_scratch_v2")
RESULTS = json.loads((ROOT / "mech" / "v2_cfd" / "results_built_v2.json").read_text())
BY_NAME = {r["name"]: r for r in RESULTS}


def find_region_vtu(case_name: str, region: str) -> Path:
    reg_dir = SCRATCH / case_name / "VTK" / region
    subdirs = [d for d in reg_dir.iterdir() if d.is_dir() and d.name.startswith(f"{region}_") or d.is_dir() and d.name.startswith(case_name)]
    # Subdirectories are named `<case_name>_<time>`
    time_dirs = sorted([d for d in reg_dir.iterdir() if d.is_dir()], key=lambda p: p.name)
    for d in reversed(time_dirs):
        p = d / "internal.vtu"
        if p.exists():
            return p
    raise FileNotFoundError(f"No internal.vtu for {case_name}/{region} under {reg_dir}")


def load_region_mm(case_name: str, region: str) -> pv.UnstructuredGrid:
    grid = pv.read(str(find_region_vtu(case_name, region)))
    grid.points = grid.points * 1000.0
    if "T" in grid.point_data:
        grid.point_data["T_C"] = grid.point_data["T"] - 273.15
    if "T" in grid.cell_data:
        grid.cell_data["T_C"] = grid.cell_data["T"] - 273.15
    return grid


def load_stls() -> tuple[pv.PolyData, pv.PolyData, pv.PolyData]:
    bottom = pv.read(str(MECH_DIR / "case_v2_bottom.stl"))
    lid = pv.read(str(MECH_DIR / "case_v2_lid.stl"))
    # case_v2_lid.stl is exported upside-down for printing (rotate 180 deg around X)
    lid.points[:, 1] = -lid.points[:, 1]
    lid.points[:, 2] = -lid.points[:, 2]
    filt = pv.read(str(MECH_DIR / "case_v2_filter_frame.stl"))
    return bottom, lid, filt


def solid_surfaces(case_name: str, with_hs: bool = True) -> list[tuple[str, pv.PolyData]]:
    regs = ["adapter_pcb", "kv260_carrier", "k26_sink"]
    if with_hs:
        regs += ["pkg_U401", "hs_U401", "pkg_Y401", "hs_Y401", "pkg_U501", "hs_U501"]
    out = []
    for r in regs:
        g = load_region_mm(case_name, r)
        if "T_C" not in g.point_data and "T_C" in g.cell_data:
            g = g.cell_data_to_point_data()
        surf = g.extract_surface(algorithm=None)
        out.append((r, surf))
    return out


def render_cutaway() -> None:
    case = "v2_built_hs_clean_fine_70C"
    row = BY_NAME[case]
    bottom, lid, filt = load_stls()
    solids = solid_surfaces(case, with_hs=True)
    duct = load_region_mm(case, "duct_petg").extract_surface(algorithm=None)

    pl = pv.Plotter(off_screen=True, window_size=(1800, 1080))
    pl.set_background("white")

    # Ghosted 3D-printed enclosure STL shell
    pl.add_mesh(bottom, color="#78909c", opacity=0.22, smooth_shading=True)
    pl.add_mesh(lid, color="#90a4ae", opacity=0.14, smooth_shading=True)
    pl.add_mesh(filt, color="#455a64", opacity=0.45, smooth_shading=True)
    pl.add_mesh(duct, color="#37474f", opacity=0.22, smooth_shading=True)

    clim = (75.0, 115.0)
    sbar_args = dict(
        title="Solid Temperature (C)\n",
        vertical=True,
        position_x=0.88,
        position_y=0.18,
        height=0.64,
        width=0.035,
        title_font_size=22,
        label_font_size=18,
        fmt="%.0f",
    )
    for idx, (rname, surf) in enumerate(solids):
        pl.add_mesh(
            surf,
            scalars="T_C",
            cmap="turbo",
            clim=clim,
            smooth_shading=False,
            show_scalar_bar=(idx == 0),
            scalar_bar_args=sbar_args if idx == 0 else None,
        )

    # Clear 3D hotspot & feature labels
    comps = row["components"]
    label_pts = np.array([
        [-34.9,  -0.2,  9.2],   # hs_U401 top
        [-35.0,   8.8,  9.2],   # hs_Y401 top
        [-51.8,  10.6, 10.2],   # hs_U501 top
        [-30.25, 94.0,  3.2],   # U1001_LMR33630
        [-42.75, 40.0,  3.2],   # U1101_XC7A50T
        [-14.0,   3.0,  5.0],   # U1201_RTL8211FSI (slightly clear of U401 label)
        [ 86.0,  47.0, 22.5],   # K26 heatsink
        [-40.0,  14.0, 35.8],   # 50x50 fan grille/filter
    ])
    label_txt = [
        f"U401 ADCLK948\nTj={comps['U401_ADCLK948']['T_j_C']} C",
        f"Y401 Si549\nTj={comps['Y401_Si549']['T_j_C']} C",
        f"U501 AD9484\nTj={comps['U501_AD9484']['T_j_C']} C",
        f"U1001 LMR33630\nTj={comps['U1001_LMR33630']['T_j_C']} C",
        f"U1101 XC7A50T\nTj={comps['U1101_XC7A50T']['T_j_C']} C",
        f"U1201 RTL8211FSI (10 vias)\nTj={comps['U1201_RTL8211FSI']['T_j_C']} C",
        f"K26 SOM Heatsink\nTj={row['K26_Tj_C']} C",
        f"50x50 Fan (-40,+14)\n{row['fan50_flow_cfm']} CFM @ {row['fan50_curve_dp_Pa']} Pa",
    ]
    pl.add_point_labels(
        label_pts,
        label_txt,
        font_size=15,
        bold=True,
        text_color="#111111",
        shape_color="white",
        shape_opacity=0.88,
        margin=4,
        point_size=8,
        point_color="#111111",
        render_points_as_spheres=True,
        always_visible=True,
    )

    pl.add_text(
        "Built Enclosure v2 — 3D CHT Thermal Cutaway (Ta = 70 C, Fine Mesh 432k air cells)",
        position="upper_left",
        font_size=16,
        color="#111111",
    )

    pl.camera_position = [
        (-85.0, -235.0, 215.0),
        (10.0, 48.0, 12.0),
        (0.0, 0.0, 1.0),
    ]
    pl.screenshot(str(OUT_DIR / "v2_thermal_3d_cutaway.png"))
    pl.close()


def render_streamlines() -> None:
    case = "v2_built_hs_clean_fine_70C"
    row = BY_NAME[case]
    bottom, lid, filt = load_stls()
    solids = solid_surfaces(case, with_hs=True)
    duct = load_region_mm(case, "duct_petg").extract_surface(algorithm=None)

    air = load_region_mm(case, "air")
    if "U" not in air.point_data and "U" in air.cell_data:
        air = air.cell_data_to_point_data()
    air.point_data["U_mag"] = np.linalg.norm(air.point_data["U"], axis=1)

    # Seed circles under the 50 mm adapter fan (-40, 14) and KV260 OEM blower (86.1, 47)
    seed_ad = pv.Disc(center=(-40.0, 14.0, 26.5), inner=10.5, outer=23.0, r_res=4, c_res=24)
    seed_kv = pv.Disc(center=(86.1, 47.0, 27.0), inner=6.0, outer=22.0, r_res=3, c_res=16)
    seeds = seed_ad.merge(seed_kv)

    streams = air.streamlines_from_source(
        seeds,
        vectors="U",
        integration_direction="forward",
        max_length=420.0,
        initial_step_length=0.5,
        max_steps=2000,
    )
    streams.point_data["U_mag"] = np.linalg.norm(streams.point_data["U"], axis=1)
    tubes = streams.tube(radius=0.55)

    pl = pv.Plotter(off_screen=True, window_size=(1800, 1080))
    pl.set_background("white")
    pl.add_mesh(bottom, color="#78909c", opacity=0.16, smooth_shading=True)
    pl.add_mesh(lid, color="#90a4ae", opacity=0.10, smooth_shading=True)
    pl.add_mesh(filt, color="#455a64", opacity=0.35, smooth_shading=True)
    pl.add_mesh(duct, color="#37474f", opacity=0.22, smooth_shading=True)

    for _, surf in solids:
        pl.add_mesh(
            surf,
            scalars="T_C",
            cmap="inferno",
            clim=(75.0, 115.0),
            opacity=0.85,
            show_scalar_bar=False,
        )

    pl.add_mesh(
        tubes,
        scalars="U_mag",
        cmap="viridis",
        clim=(0.0, 6.5),
        smooth_shading=True,
        scalar_bar_args=dict(
            title="Air Speed |U| (m/s)\n",
            vertical=True,
            position_x=0.88,
            position_y=0.18,
            height=0.64,
            width=0.035,
            title_font_size=22,
            label_font_size=18,
            fmt="%.1f",
        ),
    )

    label_pts = np.array([
        [-40.0, 14.0, 36.0],
        [ 76.0, 58.0, 33.0],
        [114.0, 18.0, 18.0],
        [-35.0,  4.3,  9.2],
    ])
    label_txt = [
        f"50x50 Intake (-40,+14)\n{row['fan50_flow_cfm']} CFM @ {row['fan50_curve_dp_Pa']} Pa",
        f"KV260 OEM Blower Intake\n{-row['patch_flows']['kv_grille']['cfm']:.2f} CFM",
        f"13 Right-Wall Slots (No SMA Slots)\n{row['patch_flows']['right_vents']['cfm']:.2f} CFM Exhaust (+{row['p_cav_mean_Pa']} Pa)",
        "Air Impinges Directly on\nU401 / Y401 / U501 Heatsinks",
    ]
    pl.add_point_labels(
        label_pts, label_txt,
        font_size=15, bold=True, text_color="#111111",
        shape_color="white", shape_opacity=0.88, margin=4,
        point_size=8, point_color="#111111", always_visible=True,
    )

    pl.add_text(
        "Built Enclosure v2 — 3D Internal Airflow Streamlines (Ta = 70 C)",
        position="upper_left",
        font_size=16,
        color="#111111",
    )
    pl.camera_position = [
        (-55.0, -225.0, 210.0),
        (12.0, 48.0, 13.0),
        (0.0, 0.0, 1.0),
    ]
    pl.screenshot(str(OUT_DIR / "v2_thermal_3d_streamlines.png"))
    pl.close()


def render_heatsink_comparison() -> None:
    panels = [
        ("v2_built_nohs_clean_70C", False, "1) Built v2 — NO Heatsinks\nY401=113.8 C (FAIL -8.8C) | U401=116.3 C | U501=108.5 C"),
        ("v2_built_hs_clean_70C",   True,  "2) Built v2 — Touching 9x9 Sinks\nY401=107.1 C (bridged!) | U401=108.0 C | U501=99.0 C"),
        ("v2_built_proposed_70C",   True,  "3) Proposed: Open Grille + Gap + Exhaust\nY401=101.7 C (PASS +3.3C) | U401=105.4 C | U501=96.4 C"),
    ]
    pl = pv.Plotter(off_screen=True, shape=(1, 3), window_size=(2250, 860))
    pl.set_background("white")
    clim = (82.0, 116.0)

    # Clip box focusing on the adapter PCB & front hot strip
    clip_bounds = (-92.0, -10.0, -11.0, 62.0, -1.0, 34.0)

    for col_idx, (cname, has_hs, subtitle) in enumerate(panels):
        pl.subplot(0, col_idx)
        solids = solid_surfaces(cname, with_hs=has_hs)
        duct = load_region_mm(cname, "duct_petg").extract_surface()

        for idx, (rname, surf) in enumerate(solids):
            if rname in ("kv260_carrier", "k26_sink"):
                continue
            clipped = surf.clip_box(clip_bounds, invert=False)
            if clipped.n_points == 0:
                continue
            pl.add_mesh(
                clipped,
                scalars="T_C",
                cmap="turbo",
                clim=clim,
                smooth_shading=False,
                show_scalar_bar=(col_idx == 2 and idx == 0),
                scalar_bar_args=dict(
                    title="Temp (C)\n",
                    vertical=True,
                    position_x=0.89,
                    position_y=0.16,
                    height=0.68,
                    width=0.05,
                    title_font_size=18,
                    label_font_size=16,
                    fmt="%.0f",
                ) if (col_idx == 2 and idx == 0) else None,
            )

        # Show ghosted fan shroud outline above the hot strip
        pl.add_mesh(duct, color="#455a64", opacity=0.14, smooth_shading=True)

        row = BY_NAME[cname]
        c = row["components"]
        pts = np.array([
            [-34.9, -0.2, 9.5 if has_hs else 3.2],
            [-35.0,  8.8, 9.5 if has_hs else 3.2],
            [-51.8, 10.6, 10.5 if has_hs else 3.2],
            [-42.75, 40.0, 3.2],
        ])
        txts = [
            f"U401 {c['U401_ADCLK948']['T_j_C']}C",
            f"Y401 {c['Y401_Si549']['T_j_C']}C",
            f"U501 {c['U501_AD9484']['T_j_C']}C",
            f"XC7A50T {c['U1101_XC7A50T']['T_j_C']}C",
        ]
        pl.add_point_labels(
            pts, txts,
            font_size=13, bold=True, text_color="#111111",
            shape_color="white", shape_opacity=0.88, margin=3,
            point_size=7, point_color="#111111", always_visible=True,
        )
        pl.add_text(subtitle, position="upper_left", font_size=12, color="#111111")
        pl.camera_position = [
            (-52.0, -95.0, 88.0),
            (-45.0, 15.0, 4.0),
            (0.0, 0.0, 1.0),
        ]

    pl.screenshot(str(OUT_DIR / "v2_thermal_3d_heatsinks_compare.png"))
    pl.close()


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    render_cutaway()
    print("Wrote v2_thermal_3d_cutaway.png", flush=True)
    render_streamlines()
    print("Wrote v2_thermal_3d_streamlines.png", flush=True)
    render_heatsink_comparison()
    print("Wrote v2_thermal_3d_heatsinks_compare.png", flush=True)


if __name__ == "__main__":
    main()
