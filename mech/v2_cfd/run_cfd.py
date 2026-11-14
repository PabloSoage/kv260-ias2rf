#!/usr/bin/env python3
"""
3D Conjugate Heat Transfer (CHT) CFD study for KV260-IAS2RF Enclosure v2.

Uses OpenFOAM v2412 (`chtMultiRegionSimpleFoam`) with resolved fluid (`air`) and
solid (`adapter_pcb`, `kv260_carrier`, `k26_sink`, optional `spreader_al`) regions.
Case scratch directories live in a separate temporary workspace (e.g. /home/varuna/cfd_scratch)
and only lightweight numeric summaries and 2D field slices are retained here.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

# ---------------------------------------------------------------------------
# Enclosure and PCB Geometric Constants (mm -> m, matching build_case.py)
# ---------------------------------------------------------------------------
# Inner cavity bounds (mm): x [-109.6, 131.0], y [-12.2, 112.0], z [-8.0, 32.75]
CAV_X0, CAV_X1 = -109.6e-3, 131.0e-3
CAV_Y0, CAV_Y1 = -12.2e-3, 112.0e-3
CAV_Z0, CAV_Z1 = -8.0e-3, 32.75e-3

ADAPTER_X0, ADAPTER_X1 = -107.2e-3, -10.0e-3
ADAPTER_Y0, ADAPTER_Y1 = -9.7e-3, 108.7e-3
ADAPTER_Z0, ADAPTER_Z1 = 0.8e-3, 2.4e-3

CARRIER_X0, CARRIER_X1 = -9.7e-3, 129.7e-3
CARRIER_Y0, CARRIER_Y1 = -9.7e-3, 108.7e-3
CARRIER_Z0, CARRIER_Z1 = -1.6e-3, 0.0e-3

# K26 SOM + KV260 OEM finned heatsink footprint centered around fan (86.1, 47.0)
KV_FAN_X, KV_FAN_Y, KV_FAN_R = 86.1e-3, 47.0e-3, 27.0e-3
AD_FAN_X, AD_FAN_Y = -45.0e-3, 45.0e-3  # Centered over U1101/U501/U401/regulators

SINK_X0, SINK_X1 = 52.0e-3, 120.0e-3
SINK_Y0, SINK_Y1 = 18.0e-3, 76.0e-3
SINK_BASE_Z0, SINK_BASE_Z1 = 4.0e-3, 10.0e-3
SINK_FIN_Z1 = 22.0e-3
FIN_Y_SPANS = [
    (19.0e-3, 22.5e-3),
    (32.0e-3, 35.5e-3),
    (45.2e-3, 48.8e-3),
    (58.5e-3, 62.0e-3),
    (71.5e-3, 75.0e-3),
]

# ---------------------------------------------------------------------------
# Thermal Sources (exact KiCad Rev01 mount coords & SIGNAL_INTEGRITY.md / power_budget.py)
# Total adapter baseline continuous dissipation = 7.50 W (8.8 W max budget).
# ---------------------------------------------------------------------------
@dataclass
class ComponentSpec:
    name: str
    x_mm: float
    y_mm: float
    footprint_mm: float
    power_w: float
    theta_jb: float       # C/W junction-to-board
    theta_jc_top: float   # C/W junction-to-case top (for gap-pad conduction)
    tj_max_c: float


COMPONENTS: List[ComponentSpec] = [
    ComponentSpec("U401_ADCLK948",   -34.90, -0.20,  6.0, 0.95,  8.8, 12.0, 150.0),
    ComponentSpec("U402_Si549",      -34.90, 12.00,  5.0, 0.50, 20.0, 25.0, 105.0),
    ComponentSpec("U501_AD9484",     -51.80, 10.55,  8.0, 1.05,  8.5,  1.7, 125.0),
    ComponentSpec("U601_AD9253",     -70.25, 10.35,  8.0, 0.46, 12.0,  7.1, 125.0),
    ComponentSpec("U1101_XC7A50T",   -42.75, 40.00, 17.0, 0.73,  8.4,  4.24, 100.0),
    ComponentSpec("U1001_LMR33630",  -30.25, 94.00,  6.0, 0.88, 13.6, 22.0, 150.0),
    ComponentSpec("U1002_TPS562201", -54.75, 104.50, 4.0, 0.41, 15.0, 28.0, 125.0),
    ComponentSpec("U1003_TPS562201", -54.75, 95.50,  4.0, 0.20, 15.0, 28.0, 125.0),
    ComponentSpec("U1004_TPS562201", -54.75, 86.50,  4.0, 0.10, 15.0, 28.0, 125.0),
    ComponentSpec("U1005_TPS7A8300", -43.25, 81.00,  4.5, 0.50, 12.3, 25.0, 125.0),
    ComponentSpec("U1006_TPS7A8300", -35.25, 81.00,  4.5, 0.35, 12.3, 25.0, 125.0),
    ComponentSpec("U1007_TPS7A8300", -27.25, 81.00,  4.5, 0.17, 12.3, 25.0, 125.0),
    ComponentSpec("U1201_RTL8211FSI",-18.25, -1.00,  6.0, 0.50, 12.0, 18.0, 125.0),
    ComponentSpec("AD8352_drivers",  -62.00, -0.50, 16.0, 0.40, 14.0, 20.0, 125.0),
    ComponentSpec("AD9708_AD9767",   -45.50, 71.00, 14.0, 0.30, 18.0, 30.0, 125.0),
]

KV260_CARRIER_W = 2.0
K26_SOM_W = 9.0       # Typical continuous K26 workload (UG1089/DS986; 12 W max sensitivity)
K26_R_JC = 1.4        # C/W TIM + heatspreader junction-to-sink base (UG1089)
K26_TJ_MAX = 100.0    # Commercial/Industrial Zynq US+ Tj_max ceiling check (0..85C / 100C)


# ---------------------------------------------------------------------------
# Fan P-Q Curves: (flow_rate_m3_per_s, static_pressure_Pa)
# ---------------------------------------------------------------------------
# Noctua NF-A4x10 5V: 4.8 CFM = 8.2 m3/h = 2.28e-3 m3/s max, 17.5 Pa shutoff
FAN_40_PQ = [
    (0.0,      17.5),
    (0.00076,  12.0),
    (0.00152,   6.0),
    (0.00228,   0.0),
    (0.00500, -15.0),
]
# Sunon MF50100V1-1000U 5V: 8.5 CFM = 14.4 m3/h = 4.00e-3 m3/s max, 22.0 Pa shutoff
FAN_50_PQ = [
    (0.0,      22.0),
    (0.00133,  15.2),
    (0.00267,   8.0),
    (0.00400,   0.0),
    (0.00800, -22.0),
]

FOAM_HEADER = """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  v2412                                 |
|   \\\\  /    A nd           | Website:  www.openfoam.com                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
"""


def foam_file(cls: str, obj: str, loc: Optional[str] = None) -> str:
    loc_line = f'    location    "{loc}";\n' if loc else ""
    return (
        FOAM_HEADER
        + "FoamFile\n{\n    version     2.0;\n    format      ascii;\n"
        + f"    class       {cls};\n{loc_line}    object      {obj};\n}}\n"
        + "// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //\n\n"
    )


@dataclass
class CaseConfig:
    name: str
    ambient_c: float = 70.0
    mesh_level: str = "medium"     # coarse | medium | fine
    k_shell: float = 0.25          # PETG-CF=0.25, PAHT-CF=0.35
    # Venting & lid options
    kv_top_grille: bool = True
    right_slots: bool = True       # x = +131 mm slots (9 slots v1 or widened)
    right_slots_open_frac: float = 1.0  # 1.0 = 9x(3x14mm) v1; 1.6 = 12x(4x16mm)
    sma_left_slots: bool = True    # x = -109.6 mm 14 slots (v1 baseline only)
    adapter_grille: bool = False   # Owner's second hex honeycomb grille at (-45, 45)
    adapter_grille_r_mm: float = 24.0
    lid_fan_mode: str = "none"     # none | impinge40 | impinge50 | exhaust50
    kv260_fan_on: bool = True
    dust_filter: bool = False
    filter_clog_factor: float = 1.0  # 1.0 = clean 100-mesh; 2.0 = dust-loaded
    alu_spreader: bool = False     # Option 3: sealed Al lid + internal pedestals
    som_power_w: float = K26_SOM_W
    adapter_scale: float = 1.0     # 1.0 = 7.50 W typ, 1.173 = 8.8 W max


def mesh_counts(level: str) -> Tuple[int, int, int]:
    if level == "coarse":
        return (60, 36, 22)
    if level == "fine":
        return (112, 66, 38)
    return (82, 48, 28)  # medium: ~110k hexahedral CHT cells across regions


def run_cmd(cmd: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        ["bash", "-c", cmd],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(f"Command failed ({proc.returncode}): {cmd}\n{proc.stderr[-1500:]}\n{proc.stdout[-1500:]}")
    return proc


def snap_bounds(n: int, lo: float, hi: float) -> np.ndarray:
    return np.linspace(lo, hi, n + 1)


def nearest_grid_box(
    x0: float, x1: float, y0: float, y1: float, z0: float, z1: float,
    xs: np.ndarray, ys: np.ndarray, zs: np.ndarray
) -> Tuple[float, float, float, float, float, float]:
    """Expand or snap box slightly to cell faces so every zone has >= 1 cell layer."""
    def snap_pair(a: float, b: float, arr: np.ndarray) -> Tuple[float, float]:
        i0 = int(np.argmin(np.abs(arr - a)))
        i1 = int(np.argmin(np.abs(arr - b)))
        if i1 <= i0:
            if i0 < len(arr) - 1:
                i1 = i0 + 1
            else:
                i0 = max(0, i1 - 1)
        return float(arr[i0]), float(arr[i1])
    sx0, sx1 = snap_pair(x0, x1, xs)
    sy0, sy1 = snap_pair(y0, y1, ys)
    sz0, sz1 = snap_pair(z0, z1, zs)
    return sx0, sx1, sy0, sy1, sz0, sz1


def generate_case(cfg: CaseConfig, case_dir: Path, nprocs: int = 16) -> dict:
    if case_dir.exists():
        shutil.rmtree(case_dir)
    case_dir.mkdir(parents=True)

    nx, ny, nz = mesh_counts(cfg.mesh_level)
    xs = snap_bounds(nx, CAV_X0, CAV_X1)
    ys = snap_bounds(ny, CAV_Y0, CAV_Y1)
    zs = snap_bounds(nz, CAV_Z0, CAV_Z1)

    t_amb_k = cfg.ambient_c + 273.15
    fan_extra_w = 0.15 if cfg.lid_fan_mode != "none" else 0.0

    # Snapped solid boxes
    ad_box = nearest_grid_box(ADAPTER_X0, ADAPTER_X1, ADAPTER_Y0, ADAPTER_Y1, ADAPTER_Z0, ADAPTER_Z1, xs, ys, zs)
    ca_box = nearest_grid_box(CARRIER_X0, CARRIER_X1, CARRIER_Y0, CARRIER_Y1, CARRIER_Z0, CARRIER_Z1, xs, ys, zs)
    sb_box = nearest_grid_box(SINK_X0, SINK_X1, SINK_Y0, SINK_Y1, SINK_BASE_Z0, SINK_BASE_Z1, xs, ys, zs)
    fin_boxes = [
        nearest_grid_box(SINK_X0, SINK_X1, fy0, fy1, sb_box[5], SINK_FIN_Z1, xs, ys, zs)
        for fy0, fy1 in FIN_Y_SPANS
    ]

    # Spreader pedestals for Option 3 (connects hot adapter components to top lid)
    spreader_boxes = []
    if cfg.alu_spreader:
        # Aluminum lid plate inside top 3 mm + pillars down to key ICs
        spreader_boxes.append(nearest_grid_box(CAV_X0 + 2e-3, -4.0e-3, CAV_Y0 + 2e-3, CAV_Y1 - 2e-3, zs[-2], CAV_Z1, xs, ys, zs))
        spreader_boxes.append(nearest_grid_box(-76e-3, -16e-3, -5e-3, 18e-3, ad_box[5], zs[-2], xs, ys, zs))   # ADCLK/AD9484/AD9253/RTL8211 bank
        spreader_boxes.append(nearest_grid_box(-52e-3, -32e-3, 30e-3, 50e-3, ad_box[5], zs[-2], xs, ys, zs))  # XC7A50T pedestal
        spreader_boxes.append(nearest_grid_box(-60e-3, -24e-3, 76e-3, 108e-3, ad_box[5], zs[-2], xs, ys, zs)) # Regulators pedestal

    regions_solid = ["adapter_pcb", "kv260_carrier", "k26_sink"]
    if cfg.alu_spreader:
        regions_solid.append("spreader_al")

    # ------------------------------------------------------------------
    # Write blockMeshDict with explicit boundary patches for vents & fans
    # ------------------------------------------------------------------
    # To carve exact rectangular openings on the top/side boundary faces cleanly,
    # we use topoSet faceSets + createPatch -overwrite after blockMesh.
    (case_dir / "system").mkdir()
    (case_dir / "constant").mkdir()
    (case_dir / "0.orig").mkdir()

    bmesh = foam_file("dictionary", "blockMeshDict", "system")
    bmesh += f"""scale 1;

vertices
(
    ({CAV_X0:.6f} {CAV_Y0:.6f} {CAV_Z0:.6f})
    ({CAV_X1:.6f} {CAV_Y0:.6f} {CAV_Z0:.6f})
    ({CAV_X1:.6f} {CAV_Y1:.6f} {CAV_Z0:.6f})
    ({CAV_X0:.6f} {CAV_Y1:.6f} {CAV_Z0:.6f})
    ({CAV_X0:.6f} {CAV_Y0:.6f} {CAV_Z1:.6f})
    ({CAV_X1:.6f} {CAV_Y0:.6f} {CAV_Z1:.6f})
    ({CAV_X1:.6f} {CAV_Y1:.6f} {CAV_Z1:.6f})
    ({CAV_X0:.6f} {CAV_Y1:.6f} {CAV_Z1:.6f})
);

blocks
(
    hex (0 1 2 3 4 5 6 7) ({nx} {ny} {nz}) simpleGrading (1 1 1)
);

boundary
(
    wall_bottom
    {{
        type wall;
        faces ( (0 3 2 1) );
    }}
    wall_top
    {{
        type wall;
        faces ( (4 5 6 7) );
    }}
    wall_left
    {{
        type wall;
        faces ( (0 4 7 3) );
    }}
    wall_right
    {{
        type wall;
        faces ( (1 2 6 5) );
    }}
    wall_front
    {{
        type wall;
        faces ( (0 1 5 4) );
    }}
    wall_back
    {{
        type wall;
        faces ( (3 7 6 2) );
    }}
);
"""
    (case_dir / "system" / "blockMeshDict").write_text(bmesh)

    # ------------------------------------------------------------------
    # createPatch + topoSet to separate exterior vents/fans AND solid cellZones
    # ------------------------------------------------------------------
    top_actions = []
    create_patches = []

    if cfg.kv_top_grille:
        r_kv = KV_FAN_R * 0.90  # 24.3 mm active circular hex opening
        top_actions.append(f"""
    {{
        name    f_kv_grille;
        type    faceSet;
        action  new;
        source  cylinderToFace;
        p1      ({KV_FAN_X:.5f} {KV_FAN_Y:.5f} {CAV_Z1 - 0.002:.5f});
        p2      ({KV_FAN_X:.5f} {KV_FAN_Y:.5f} {CAV_Z1 + 0.002:.5f});
        radius  {r_kv:.5f};
    }}
    {{
        name    f_kv_grille;
        type    faceSet;
        action  subset;
        source  patchToFace;
        patch   wall_top;
    }}""")
        create_patches.append("""
    {
        name kv_grille;
        patchInfo { type patch; }
        constructFrom set;
        set f_kv_grille;
    }""")

    if cfg.adapter_grille or cfg.lid_fan_mode != "none":
        r_ad = (
            23.0e-3 if "50" in cfg.lid_fan_mode else
            19.0e-3 if "40" in cfg.lid_fan_mode else
            cfg.adapter_grille_r_mm * 1e-3
        )
        top_actions.append(f"""
    {{
        name    f_ad_opening;
        type    faceSet;
        action  new;
        source  cylinderToFace;
        p1      ({AD_FAN_X:.5f} {AD_FAN_Y:.5f} {CAV_Z1 - 0.002:.5f});
        p2      ({AD_FAN_X:.5f} {AD_FAN_Y:.5f} {CAV_Z1 + 0.002:.5f});
        radius  {r_ad:.5f};
    }}
    {{
        name    f_ad_opening;
        type    faceSet;
        action  subset;
        source  patchToFace;
        patch   wall_top;
    }}""")
        create_patches.append("""
    {
        name adapter_opening;
        patchInfo { type patch; }
        constructFrom set;
        set f_ad_opening;
    }""")

    if cfg.right_slots:
        y_span_lo = 22.0e-3 if cfg.right_slots_open_frac <= 1.05 else 12.0e-3
        y_span_hi = 73.0e-3 if cfg.right_slots_open_frac <= 1.05 else 92.0e-3
        z_hi = 26.0e-3 if cfg.right_slots_open_frac <= 1.05 else 28.0e-3
        top_actions.append(f"""
    {{
        name    f_right_vents;
        type    faceSet;
        action  new;
        source  boxToFace;
        box     ({CAV_X1 - 0.002:.5f} {y_span_lo:.5f} 12.0e-3) ({CAV_X1 + 0.002:.5f} {y_span_hi:.5f} {z_hi:.5f});
    }}
    {{
        name    f_right_vents;
        type    faceSet;
        action  subset;
        source  patchToFace;
        patch   wall_right;
    }}""")
        create_patches.append("""
    {
        name right_vents;
        patchInfo { type patch; }
        constructFrom set;
        set f_right_vents;
    }""")

    if cfg.sma_left_slots:
        top_actions.append(f"""
    {{
        name    f_left_vents;
        type    faceSet;
        action  new;
        source  boxToFace;
        box     ({CAV_X0 - 0.002:.5f} 4.0e-3 12.0e-3) ({CAV_X0 + 0.002:.5f} 98.0e-3 26.0e-3);
    }}
    {{
        name    f_left_vents;
        type    faceSet;
        action  subset;
        source  patchToFace;
        patch   wall_left;
    }}""")
        create_patches.append("""
    {
        name left_vents;
        patchInfo { type patch; }
        constructFrom set;
        set f_left_vents;
    }""")

    # Global topoSet: patches + solid cellZones + fluid cellZone ("air")
    def box_src(name: str, b: Tuple[float, float, float, float, float, float], action: str = "new") -> str:
        return f"""
    {{
        name    {name};
        type    cellSet;
        action  {action};
        source  boxToCell;
        box     ({b[0] + 1e-6:.6f} {b[2] + 1e-6:.6f} {b[4] + 1e-6:.6f}) ({b[1] - 1e-6:.6f} {b[3] - 1e-6:.6f} {b[5] - 1e-6:.6f});
    }}"""

    solid_actions = []
    solid_actions.append(box_src("adapter_pcb", ad_box, "new"))
    solid_actions.append(box_src("kv260_carrier", ca_box, "new"))
    solid_actions.append(box_src("k26_sink", sb_box, "new"))
    for fb in fin_boxes:
        solid_actions.append(box_src("k26_sink", fb, "add"))
    if cfg.alu_spreader:
        for i, spb in enumerate(spreader_boxes):
            solid_actions.append(box_src("spreader_al", spb, "new" if i == 0 else "add"))

    air_invert = "".join(
        f"""
    {{
        name    air;
        type    cellSet;
        action  delete;
        source  cellToCell;
        set     {r};
    }}"""
        for r in regions_solid
    )

    zone_list = "".join(
        f"""
    {{
        name    {z};
        type    cellZoneSet;
        action  new;
        source  setToCellZone;
        set     {z};
    }}"""
        for z in ["air"] + regions_solid
    )

    tdict = foam_file("dictionary", "topoSetDict", "system")
    tdict += "actions\n(\n"
    tdict += "".join(top_actions)
    tdict += "".join(solid_actions)
    tdict += f"""
    {{
        name    air;
        type    cellSet;
        action  new;
        source  boxToCell;
        box     (-1 -1 -1) (1 1 1);
    }}
    {air_invert}
    {zone_list}
);\n"""
    (case_dir / "system" / "topoSetDict").write_text(tdict)

    cpdict = foam_file("dictionary", "createPatchDict", "system")
    cpdict += "pointSync false;\npatches\n(\n" + "\n".join(create_patches) + "\n);\n"
    (case_dir / "system" / "createPatchDict").write_text(cpdict)

    # ------------------------------------------------------------------
    # Region-specific topoSet for heat sources (adapter_pcb, k26_sink, kv260_carrier)
    # and porous/fan zones inside `air`
    # ------------------------------------------------------------------
    ic_actions = []
    ic_zones = []
    ic_boxes: Dict[str, Tuple[float, float, float, float, float, float]] = {}
    for c in COMPONENTS:
        h = max(c.footprint_mm * 0.5e-3, 3.0e-3)
        b = nearest_grid_box(c.x_mm * 1e-3 - h, c.x_mm * 1e-3 + h,
                             c.y_mm * 1e-3 - h, c.y_mm * 1e-3 + h,
                             ad_box[4], ad_box[5], xs, ys, zs)
        ic_boxes[c.name] = b
        ic_actions.append(box_src(c.name, b, "new"))
        ic_actions.append(f"""
    {{
        name    {c.name};
        type    cellZoneSet;
        action  new;
        source  setToCellZone;
        set     {c.name};
    }}""")
        ic_zones.append(c)

    (case_dir / "system" / "adapter_pcb").mkdir(parents=True, exist_ok=True)
    (case_dir / "system" / "adapter_pcb" / "topoSetDict").write_text(
        foam_file("dictionary", "topoSetDict", "system") + "actions\n(\n" + "".join(ic_actions) + "\n);\n"
    )

    som_box = nearest_grid_box(66e-3, 106e-3, 27e-3, 67e-3, sb_box[4], sb_box[5], xs, ys, zs)
    (case_dir / "system" / "k26_sink").mkdir(parents=True, exist_ok=True)
    (case_dir / "system" / "k26_sink" / "topoSetDict").write_text(
        foam_file("dictionary", "topoSetDict", "system")
        + "actions\n(\n"
        + box_src("k26_som", som_box, "new")
        + """
    {
        name    k26_som;
        type    cellZoneSet;
        action  new;
        source  setToCellZone;
        set     k26_som;
    }
);\n"""
    )

    # Fluid zones in `air`: KV260 OEM fan disk + optional dust filter & grille resistance
    air_actions = []
    if cfg.kv260_fan_on:
        air_actions.append(f"""
    {{
        name    kv260_fan_zone;
        type    cellSet;
        action  new;
        source  cylinderToCell;
        p1      ({KV_FAN_X:.5f} {KV_FAN_Y:.5f} {SINK_FIN_Z1 + 0.5e-3:.5f});
        p2      ({KV_FAN_X:.5f} {KV_FAN_Y:.5f} {CAV_Z1 - 1.5e-3:.5f});
        radius  {KV_FAN_R * 0.90:.5f};
    }}
    {{
        name    kv260_fan_zone;
        type    cellZoneSet;
        action  new;
        source  setToCellZone;
        set     kv260_fan_zone;
    }}""")

    if cfg.right_slots:
        y_span_lo = 22.0e-3 if cfg.right_slots_open_frac <= 1.05 else 12.0e-3
        y_span_hi = 73.0e-3 if cfg.right_slots_open_frac <= 1.05 else 92.0e-3
        z_hi = 26.0e-3 if cfg.right_slots_open_frac <= 1.05 else 28.0e-3
        air_actions.append(f"""
    {{
        name    right_slot_zone;
        type    cellSet;
        action  new;
        source  boxToCell;
        box     ({CAV_X1 - 0.005:.5f} {y_span_lo:.5f} 12.0e-3) ({CAV_X1:.5f} {y_span_hi:.5f} {z_hi:.5f});
    }}
    {{
        name    right_slot_zone;
        type    cellZoneSet;
        action  new;
        source  setToCellZone;
        set     right_slot_zone;
    }}""")

    if cfg.sma_left_slots:
        air_actions.append(f"""
    {{
        name    left_slot_zone;
        type    cellSet;
        action  new;
        source  boxToCell;
        box     ({CAV_X0:.5f} 4.0e-3 12.0e-3) ({CAV_X0 + 0.005:.5f} 98.0e-3 26.0e-3);
    }}
    {{
        name    left_slot_zone;
        type    cellZoneSet;
        action  new;
        source  setToCellZone;
        set     left_slot_zone;
    }}""")

    if cfg.dust_filter and (cfg.adapter_grille or cfg.lid_fan_mode != "none"):
        r_ad = 23.0e-3 if "50" in cfg.lid_fan_mode else 19.0e-3 if "40" in cfg.lid_fan_mode else cfg.adapter_grille_r_mm * 1e-3
        air_actions.append(f"""
    {{
        name    dust_filter_zone;
        type    cellSet;
        action  new;
        source  cylinderToCell;
        p1      ({AD_FAN_X:.5f} {AD_FAN_Y:.5f} {CAV_Z1 - 0.005:.5f});
        p2      ({AD_FAN_X:.5f} {AD_FAN_Y:.5f} {CAV_Z1:.5f});
        radius  {r_ad:.5f};
    }}
    {{
        name    dust_filter_zone;
        type    cellZoneSet;
        action  new;
        source  setToCellZone;
        set     dust_filter_zone;
    }}""")

    if air_actions:
        (case_dir / "system" / "air").mkdir(parents=True, exist_ok=True)
        (case_dir / "system" / "air" / "topoSetDict").write_text(
            foam_file("dictionary", "topoSetDict", "system") + "actions\n(\n" + "".join(air_actions) + "\n);\n"
        )

    # ------------------------------------------------------------------
    # Global constant & system dicts
    # ------------------------------------------------------------------
    (case_dir / "constant" / "regionProperties").write_text(
        foam_file("dictionary", "regionProperties", "constant")
        + "regions\n(\n    fluid       (air)\n    solid       ("
        + " ".join(regions_solid)
        + ")\n);\n"
    )
    (case_dir / "constant" / "g").write_text(
        foam_file("uniformDimensionedVectorField", "g", "constant")
        + "dimensions      [0 1 -2 0 0 0 0];\nvalue           (0 0 -9.81);\n"
    )

    n_iter = 600 if cfg.mesh_level != "fine" else 750
    (case_dir / "system" / "controlDict").write_text(
        foam_file("dictionary", "controlDict", "system")
        + f"""application     chtMultiRegionSimpleFoam;
startFrom       latestTime;
startTime       0;
stopAt          endTime;
endTime         {n_iter};
deltaT          1;
writeControl    timeStep;
writeInterval   {n_iter};
purgeWrite      1;
writeFormat     ascii;
writePrecision  6;
writeCompression off;
timeFormat      general;
timePrecision   6;
runTimeModifiable true;
"""
    )

    # 4-way decompose across 16 cores on WSL (4x2x2)
    decomp_d = (
        foam_file("dictionary", "decomposeParDict", "system")
        + f"numberOfSubdomains {nprocs};\nmethod          scotch;\n"
    )
    (case_dir / "system" / "decomposeParDict").write_text(decomp_d)
    (case_dir / "system" / "air").mkdir(parents=True, exist_ok=True)
    (case_dir / "system" / "air" / "decomposeParDict").write_text(decomp_d)

    (case_dir / "system" / "fvSchemes").write_text(
        foam_file("dictionary", "fvSchemes", "system")
        + "ddtSchemes { default steadyState; }\ngradSchemes { default Gauss linear; }\n"
        + "divSchemes { default none; }\nlaplacianSchemes { default Gauss linear limited 0.5; }\n"
        + "interpolationSchemes { default linear; }\nsnGradSchemes { default limited 0.5; }\n"
    )
    (case_dir / "system" / "fvSolution").write_text(
        foam_file("dictionary", "fvSolution", "system")
        + "SIMPLE { nOuterCorrectors 1; }\n"
    )

    # ------------------------------------------------------------------
    # Region constant & system dictionaries
    # ------------------------------------------------------------------
    (case_dir / "constant" / "air").mkdir(parents=True, exist_ok=True)
    (case_dir / "system" / "air").mkdir(parents=True, exist_ok=True)

    (case_dir / "constant" / "air" / "thermophysicalProperties").write_text(
        foam_file("dictionary", "thermophysicalProperties", "constant")
        + """thermoType
{
    type            heRhoThermo;
    mixture         pureMixture;
    transport       const;
    thermo          hConst;
    equationOfState perfectGas;
    specie          specie;
    energy          sensibleEnthalpy;
}
mixture
{
    specie          { molWeight 28.97; }
    thermodynamics  { Cp 1007; Hf 0; }
    transport       { mu 1.98e-05; Pr 0.708; }
}
"""
    )
    (case_dir / "constant" / "air" / "turbulenceProperties").write_text(
        foam_file("dictionary", "turbulenceProperties", "constant")
        + """simulationType RAS;
RAS
{
    RASModel        kOmegaSST;
    turbulence      on;
    printCoeffs     on;
}
"""
    )

    (case_dir / "system" / "air" / "fvSchemes").write_text(
        foam_file("dictionary", "fvSchemes", "system")
        + """ddtSchemes      { default steadyState; }
divSchemes
{
    div(phi,U)      bounded Gauss upwind;
    div(phi,k)      bounded Gauss upwind;
    div(phi,omega)  bounded Gauss upwind;
    div(phi,K)      bounded Gauss upwind;
    div(phi,h)      bounded Gauss upwind;
    div(phid,p)     bounded Gauss upwind;
    div(((rho*nuEff)*dev2(T(grad(U))))) Gauss linear;
}
laplacianSchemes { default Gauss linear corrected; }
interpolationSchemes { default linear; }
snGradSchemes   { default corrected; }
gradSchemes     { default Gauss linear; }
fluxRequired    { default no; pCorr ; p_rgh ; }
wallDist        { method meshWave; nRequired false; }
"""
    )

    (case_dir / "system" / "air" / "fvSolution").write_text(
        foam_file("dictionary", "fvSolution", "system")
        + """solvers
{
    rho { solver PCG; preconditioner DIC; tolerance 1e-7; relTol 0; }
    p_rgh { solver GAMG; smoother GaussSeidel; tolerance 1e-6; relTol 0.05; }
    "(U|k|omega|h)" { solver PBiCGStab; preconditioner DILU; tolerance 1e-6; relTol 0.05; }
}
SIMPLE
{
    momentumPredictor true;
    nNonOrthogonalCorrectors 0;
    frozenFlow false;
    pRefCell 0;
    pRefValue 101325;
}
relaxationFactors
{
    fields { p_rgh 0.35; rho 1; }
    equations { U 0.55; h 0.80; k 0.60; omega 0.60; }
}
"""
    )

    # air fvOptions: KV260 OEM fan momentum source + Darcy-Forchheimer slots/filter
    fv_air = foam_file("dictionary", "fvOptions", "system")
    if cfg.kv260_fan_on:
        # Axial downdraft source inside kv260_fan_zone (approx ~22 Pa across ~4.5 mm disk -> ~2.6 CFM)
        fv_air += """kv260_fan_momentum
{
    type            vectorSemiImplicitSource;
    active          true;
    selectionMode   cellZone;
    cellZone        kv260_fan_zone;
    volumeMode      specific;
    sources
    {
        U           ( (0 0 -5200) -25.0 );
    }
}
"""
    if cfg.right_slots:
        # Slot opening fraction (~36% of y_span is actual 3 mm slot width / 6 mm pitch -> K_slot)
        f_slot = 550.0 if cfg.right_slots_open_frac <= 1.05 else 240.0
        fv_air += f"""right_slot_loss
{{
    type            explicitPorositySource;
    active          true;
    explicitPorositySourceCoeffs
    {{
        selectionMode   cellZone;
        cellZone        right_slot_zone;
        type DarcyForchheimer;
        d   (1e6 1e6 1e6);
        f   ({f_slot:.1f} {f_slot:.1f} {f_slot:.1f});
        coordinateSystem {{ origin (0 0 0); e1 (1 0 0); e2 (0 1 0); }}
    }}
}}
"""
    if cfg.sma_left_slots:
        fv_air += """left_slot_loss
{
    type            explicitPorositySource;
    active          true;
    explicitPorositySourceCoeffs
    {
        selectionMode   cellZone;
        cellZone        left_slot_zone;
        type DarcyForchheimer;
        d   (1e6 1e6 1e6);
        f   (720.0 720.0 720.0);
        coordinateSystem { origin (0 0 0); e1 (1 0 0); e2 (0 1 0); }
    }
}
"""
    if cfg.dust_filter and (cfg.adapter_grille or cfg.lid_fan_mode != "none"):
        # 100-mesh nylon dust filter (150 um pore, ~36% open area) + 7 mm hex grille (60% open area)
        # Across 5 mm cell thickness: ~10-14 Pa at 1.8 m/s (scales by filter_clog_factor)
        c = cfg.filter_clog_factor
        d_coef = 2.0e7 * c
        f_coef = 1400.0 * c
        fv_air += f"""dust_filter_loss
{{
    type            explicitPorositySource;
    active          true;
    explicitPorositySourceCoeffs
    {{
        selectionMode   cellZone;
        cellZone        dust_filter_zone;
        type DarcyForchheimer;
        d   (1e5 1e5 {d_coef:.2e});
        f   (50 50 {f_coef:.1f});
        coordinateSystem {{ origin (0 0 0); e1 (1 0 0); e2 (0 1 0); }}
    }}
}}
"""
    (case_dir / "system" / "air" / "fvOptions").write_text(fv_air)

    # Solid region configs
    solid_k = {
        "adapter_pcb":   18.0,   # Effective multi-layer RF/Cu FR4 in-plane spreading
        "kv260_carrier": 18.0,
        "k26_sink":      85.0,   # Extruded Al6061 heatsink + TIM spreading
        "spreader_al":  167.0,   # Pure Al6061-T6 lid & pedestals
    }
    for sreg in regions_solid:
        (case_dir / "constant" / sreg).mkdir(parents=True, exist_ok=True)
        (case_dir / "system" / sreg).mkdir(parents=True, exist_ok=True)
        (case_dir / "constant" / sreg / "thermophysicalProperties").write_text(
            foam_file("dictionary", "thermophysicalProperties", "constant")
            + f"""thermoType
{{
    type            heSolidThermo;
    mixture         pureMixture;
    transport       constIso;
    thermo          hConst;
    equationOfState rhoConst;
    specie          specie;
    energy          sensibleEnthalpy;
}}
mixture
{{
    specie          {{ molWeight 50; }}
    transport       {{ kappa {solid_k[sreg]}; }}
    thermodynamics  {{ Hf 0; Cp 500; }}
    equationOfState {{ rho 2700; }}
}}
"""
        )
        (case_dir / "system" / sreg / "fvSchemes").write_text(
            foam_file("dictionary", "fvSchemes", "system")
            + "ddtSchemes { default steadyState; }\ngradSchemes { default Gauss linear; }\n"
            + "divSchemes { default none; }\nlaplacianSchemes { default Gauss linear corrected; }\n"
            + "interpolationSchemes { default linear; }\nsnGradSchemes { default corrected; }\n"
        )
        (case_dir / "system" / sreg / "fvSolution").write_text(
            foam_file("dictionary", "fvSolution", "system")
            + """solvers
{
    h { solver PCG; preconditioner DIC; tolerance 1e-8; relTol 0.05; }
}
SIMPLE {}
relaxationFactors { equations { h 1.0; } }
"""
        )
        (case_dir / "system" / sreg / "decomposeParDict").write_text(decomp_d)

    # Solid fvOptions heat sources
    fv_ad = foam_file("dictionary", "fvOptions", "system")
    for c in ic_zones:
        pw = c.power_w * cfg.adapter_scale
        if c.name == "U1001_LMR33630":
            pw += fan_extra_w
        fv_ad += f"""src_{c.name}
{{
    type            scalarSemiImplicitSource;
    active          true;
    selectionMode   cellZone;
    cellZone        {c.name};
    volumeMode      absolute;
    sources {{ h ( {pw:.4f} 0 ); }}
}}
"""
    (case_dir / "system" / "adapter_pcb" / "fvOptions").write_text(fv_ad)

    (case_dir / "system" / "kv260_carrier" / "fvOptions").write_text(
        foam_file("dictionary", "fvOptions", "system")
        + f"""src_carrier
{{
    type            scalarSemiImplicitSource;
    active          true;
    selectionMode   all;
    volumeMode      absolute;
    sources {{ h ( {KV260_CARRIER_W:.4f} 0 ); }}
}}
"""
    )

    (case_dir / "system" / "k26_sink" / "fvOptions").write_text(
        foam_file("dictionary", "fvOptions", "system")
        + f"""src_k26_som
{{
    type            scalarSemiImplicitSource;
    active          true;
    selectionMode   cellZone;
    cellZone        k26_som;
    volumeMode      absolute;
    sources {{ h ( {cfg.som_power_w:.4f} 0 ); }}
}}
"""
    )

    # ------------------------------------------------------------------
    # Region 0.orig boundary conditions
    # ------------------------------------------------------------------
    (case_dir / "0.orig" / "air").mkdir()
    for sreg in regions_solid:
        (case_dir / "0.orig" / sreg).mkdir()

    # Helper for external wall thermal BC on shell surfaces
    def ext_wall_t(thickness_m: float, k_wall: float, h_ext: float) -> str:
        return f"""
        type            externalWallHeatFluxTemperature;
        kappaMethod     fluidThermo;
        mode            coefficient;
        h               uniform {h_ext:.2f};
        Ta              uniform {t_amb_k:.2f};
        thicknessLayers ({thickness_m:.5f});
        kappaLayers     ({k_wall:.3f});
        value           uniform {t_amb_k:.2f};"""

    def ext_wall_t_solid(thickness_m: float, k_wall: float, h_ext: float) -> str:
        return f"""
        type            externalWallHeatFluxTemperature;
        kappaMethod     solidThermo;
        mode            coefficient;
        h               uniform {h_ext:.2f};
        Ta              uniform {t_amb_k:.2f};
        thicknessLayers ({thickness_m:.5f});
        kappaLayers     ({k_wall:.3f});
        value           uniform {t_amb_k:.2f};"""

    top_h_ext = 26.0 if cfg.alu_spreader else 12.0  # Aluminum external fins vs PETG-CF top face
    top_k = 167.0 if cfg.alu_spreader else cfg.k_shell

    coupled_fluid = f"""
        type            compressible::turbulentTemperatureRadCoupledMixed;
        qrNbr           none;
        qr              none;
        Tnbr            T;
        kappaMethod     fluidThermo;
        useImplicit     false;
        value           uniform {t_amb_k:.2f};"""
    coupled_solid = f"""
        type            compressible::turbulentTemperatureRadCoupledMixed;
        qrNbr           none;
        qr              none;
        Tnbr            T;
        kappaMethod     solidThermo;
        useImplicit     false;
        value           uniform {t_amb_k:.2f};"""

    # Build open vent list for `air` fields
    open_patches = []
    if cfg.kv_top_grille:
        open_patches.append("kv_grille")
    if cfg.adapter_grille or cfg.lid_fan_mode != "none":
        open_patches.append("adapter_opening")
    if cfg.right_slots:
        open_patches.append("right_vents")
    if cfg.sma_left_slots:
        open_patches.append("left_vents")

    # U in air
    u_txt = foam_file("volVectorField", "U", "0/air") + f"dimensions [0 1 -1 0 0 0 0];\ninternalField uniform (0 0 0);\nboundaryField\n{{\n    #includeEtc \"caseDicts/setConstraintTypes\"\n"
    for w in ["wall_bottom", "wall_top", "wall_left", "wall_right", "wall_front", "wall_back"]:
        u_txt += f"    {w} {{ type noSlip; }}\n"
    u_txt += '    "air_to_.*" { type noSlip; }\n'
    for op in open_patches:
        u_txt += f"    {op} {{ type pressureInletOutletVelocity; value uniform (0 0 0); }}\n"
    (case_dir / "0.orig" / "air" / "U").write_text(u_txt + "}\n")

    # T in air
    t_txt = foam_file("volScalarField", "T", "0/air") + f"dimensions [0 0 0 1 0 0 0];\ninternalField uniform {t_amb_k:.2f};\nboundaryField\n{{\n    #includeEtc \"caseDicts/setConstraintTypes\"\n"
    t_txt += f"    wall_bottom {{ {ext_wall_t(0.0030, cfg.k_shell, 8.0)} }}\n"
    t_txt += f"    wall_top    {{ {ext_wall_t(0.0030, top_k, top_h_ext)} }}\n"
    for w in ["wall_left", "wall_right", "wall_front", "wall_back"]:
        t_txt += f"    {w} {{ {ext_wall_t(0.0035, cfg.k_shell, 10.5)} }}\n"
    t_txt += f'    "air_to_.*" {{ {coupled_fluid} }}\n'
    for op in open_patches:
        t_txt += f"    {op} {{ type inletOutlet; inletValue uniform {t_amb_k:.2f}; value uniform {t_amb_k:.2f}; }}\n"
    (case_dir / "0.orig" / "air" / "T").write_text(t_txt + "}\n")

    # p_rgh and p in air
    pr_txt = foam_file("volScalarField", "p_rgh", "0/air") + "dimensions [1 -1 -2 0 0 0 0];\ninternalField uniform 101325;\nboundaryField\n{\n    #includeEtc \"caseDicts/setConstraintTypes\"\n"
    for w in ["wall_bottom", "wall_top", "wall_left", "wall_right", "wall_front", "wall_back"]:
        pr_txt += f"    {w} {{ type fixedFluxPressure; value $internalField; }}\n"
    pr_txt += '    "air_to_.*" { type fixedFluxPressure; value $internalField; }\n'
    for op in open_patches:
        if op == "adapter_opening" and cfg.lid_fan_mode in ("impinge40", "impinge50", "exhaust50"):
            pq = FAN_40_PQ if "40" in cfg.lid_fan_mode else FAN_50_PQ
            direction = "in" if "impinge" in cfg.lid_fan_mode else "out"
            pts = " ".join(f"({q:.6f} {dp:.2f})" for q, dp in pq)
            pr_txt += f"""    {op}
    {{
        type            fanPressure;
        direction       {direction};
        fanCurve
        {{
            type        table;
            values      ( {pts} );
        }}
        p0              uniform 101325;
        value           $internalField;
    }}
"""
        else:
            pr_txt += f"    {op} {{ type totalPressure; p0 uniform 101325; value $internalField; }}\n"
    (case_dir / "0.orig" / "air" / "p_rgh").write_text(pr_txt + "}\n")

    open_boundary = "    #includeEtc \"caseDicts/setConstraintTypes\"\n    \"wall_.*\" { type calculated; value $internalField; }\n    \"air_to_.*\" { type calculated; value $internalField; }\n"
    for op in open_patches:
        open_boundary += f"    {op} {{ type calculated; value $internalField; }}\n"
    p_txt = foam_file("volScalarField", "p", "0/air") + "dimensions [1 -1 -2 0 0 0 0];\ninternalField uniform 101325;\nboundaryField\n{\n" + open_boundary + "}\n"
    (case_dir / "0.orig" / "air" / "p").write_text(p_txt)

    # k, omega, nut, alphat in air
    k_txt = foam_file("volScalarField", "k", "0/air") + "dimensions [0 2 -2 0 0 0 0];\ninternalField uniform 0.01;\nboundaryField\n{\n    #includeEtc \"caseDicts/setConstraintTypes\"\n"
    om_txt = foam_file("volScalarField", "omega", "0/air") + "dimensions [0 0 -1 0 0 0 0];\ninternalField uniform 50;\nboundaryField\n{\n    #includeEtc \"caseDicts/setConstraintTypes\"\n"
    nut_txt = foam_file("volScalarField", "nut", "0/air") + "dimensions [0 2 -1 0 0 0 0];\ninternalField uniform 0;\nboundaryField\n{\n    #includeEtc \"caseDicts/setConstraintTypes\"\n"
    at_txt = foam_file("volScalarField", "alphat", "0/air") + "dimensions [1 -1 -1 0 0 0 0];\ninternalField uniform 0;\nboundaryField\n{\n    #includeEtc \"caseDicts/setConstraintTypes\"\n"
    for w in ["wall_bottom", "wall_top", "wall_left", "wall_right", "wall_front", "wall_back"]:
        k_txt += f"    {w} {{ type kqRWallFunction; value $internalField; }}\n"
        om_txt += f"    {w} {{ type omegaWallFunction; value $internalField; }}\n"
        nut_txt += f"    {w} {{ type nutkWallFunction; value $internalField; }}\n"
        at_txt += f"    {w} {{ type compressible::alphatWallFunction; Prt 0.85; value $internalField; }}\n"
    k_txt += '    "air_to_.*" { type kqRWallFunction; value $internalField; }\n'
    om_txt += '    "air_to_.*" { type omegaWallFunction; value $internalField; }\n'
    nut_txt += '    "air_to_.*" { type nutkWallFunction; value $internalField; }\n'
    at_txt += '    "air_to_.*" { type compressible::alphatWallFunction; Prt 0.85; value $internalField; }\n'
    for op in open_patches:
        k_txt += f"    {op} {{ type inletOutlet; inletValue $internalField; value $internalField; }}\n"
        om_txt += f"    {op} {{ type inletOutlet; inletValue $internalField; value $internalField; }}\n"
        nut_txt += f"    {op} {{ type calculated; value uniform 0; }}\n"
        at_txt += f"    {op} {{ type calculated; value uniform 0; }}\n"
    (case_dir / "0.orig" / "air" / "k").write_text(k_txt + "}\n")
    (case_dir / "0.orig" / "air" / "omega").write_text(om_txt + "}\n")
    (case_dir / "0.orig" / "air" / "nut").write_text(nut_txt + "}\n")
    (case_dir / "0.orig" / "air" / "alphat").write_text(at_txt + "}\n")

    # T in solid regions
    for sreg in regions_solid:
        st_txt = foam_file("volScalarField", "T", f"0/{sreg}") + f"dimensions [0 0 0 1 0 0 0];\ninternalField uniform {t_amb_k + 10.0:.2f};\nboundaryField\n{{\n    #includeEtc \"caseDicts/setConstraintTypes\"\n"
        st_txt += f'    "{sreg}_to_.*" {{ {coupled_solid} }}\n'
        if cfg.alu_spreader and sreg == "spreader_al":
            st_txt += f"    wall_top {{ {ext_wall_t_solid(0.0030, 167.0, 26.0)} }}\n"
        st_txt += f'    "wall_.*" {{ {ext_wall_t_solid(0.0035, cfg.k_shell, 10.5)} }}\n}}\n'
        (case_dir / "0.orig" / sreg / "T").write_text(st_txt)
        (case_dir / "0.orig" / sreg / "p").write_text(
            foam_file("volScalarField", "p", f"0/{sreg}")
            + f'dimensions [1 -1 -2 0 0 0 0];\ninternalField uniform 101325;\nboundaryField\n{{\n    #includeEtc "caseDicts/setConstraintTypes"\n    "{sreg}_to_.*" {{ type zeroGradient; }}\n    "wall_.*" {{ type zeroGradient; }}\n}}\n'
        )

    return {
        "xs": xs, "ys": ys, "zs": zs,
        "ad_box": ad_box, "ca_box": ca_box, "sb_box": sb_box,
        "som_box": som_box, "ic_boxes": ic_boxes,
        "open_patches": open_patches, "n_iter": n_iter,
    }


def read_foam_scalar_field(path: Path) -> np.ndarray:
    txt = path.read_text()
    m = re.search(r"internalField\s+nonuniform\s+List<scalar>\s+(\d+)\s*\((.*?)\)\s*;", txt, re.S)
    if m:
        return np.fromstring(m.group(2), sep="\n")
    m_uni = re.search(r"internalField\s+uniform\s+([0-9.eE+-]+)\s*;", txt)
    if m_uni:
        return np.array([float(m_uni.group(1))])
    raise ValueError(f"Could not parse scalar field {path}")


def read_foam_vector_field(path: Path) -> np.ndarray:
    txt = path.read_text()
    m = re.search(r"internalField\s+nonuniform\s+List<vector>\s+(\d+)\s*\((.*?)\)\s*;", txt, re.S)
    if m:
        rows = re.findall(r"\(\s*([0-9.eE+-]+)\s+([0-9.eE+-]+)\s+([0-9.eE+-]+)\s*\)", m.group(2))
        return np.array(rows, dtype=np.float64)
    return np.zeros((1, 3))


def parse_cell_centers(post_dir: Path, region: str) -> np.ndarray:
    cx = read_foam_scalar_field(post_dir / region / "Cx")
    cy = read_foam_scalar_field(post_dir / region / "Cy")
    cz = read_foam_scalar_field(post_dir / region / "Cz")
    return np.column_stack([cx, cy, cz])


def run_case(cfg: CaseConfig, scratch_root: Path, out_slices_dir: Path, nprocs: int = 16) -> dict:
    t0 = time.time()
    case_dir = scratch_root / cfg.name
    meta = generate_case(cfg, case_dir, nprocs=nprocs)
    n_iter = meta["n_iter"]

    setup_cmds = [
        "blockMesh > log.blockMesh 2>&1",
        "topoSet > log.topoSet 2>&1",
    ]
    if meta["open_patches"]:
        setup_cmds.append("createPatch -overwrite > log.createPatch 2>&1")
    setup_cmds += [
        "decomposePar > log.decomp 2>&1",
        "rm -rf 0 && cp -r 0.orig 0",
        "for d in processor*; do rm -rf \"$d/0\" && cp -r 0.orig \"$d/0\"; done",
        f"mpirun -np {nprocs} bash ./run_par.sh splitMeshRegions -cellZones -overwrite -parallel > log.split 2>&1",
        f"mpirun -np {nprocs} bash ./run_par.sh topoSet -region adapter_pcb -parallel > log.topoAdapter 2>&1",
        f"mpirun -np {nprocs} bash ./run_par.sh topoSet -region k26_sink -parallel > log.topoK26 2>&1",
    ]
    if (case_dir / "system" / "air" / "topoSetDict").exists():
        setup_cmds.append(f"mpirun -np {nprocs} bash ./run_par.sh topoSet -region air -parallel > log.topoAir 2>&1")
    setup_cmds += [
        f"mpirun -np {nprocs} bash ./run_par.sh chtMultiRegionSimpleFoam -parallel > log.solver 2>&1",
        "reconstructParMesh -allRegions -constant > log.recmesh 2>&1 || true",
        "reconstructPar -allRegions -latestTime > log.rec 2>&1",
        "postProcess -func writeCellCentres -region air -latestTime > log.ccAir 2>&1",
        "postProcess -func writeCellCentres -region adapter_pcb -latestTime > log.ccAd 2>&1",
        "postProcess -func writeCellCentres -region k26_sink -latestTime > log.ccK26 2>&1",
    ]
    # Patch flow rates (mass flux sum) and pressure averages for P-Q operating point
    if meta["open_patches"]:
        post_dict = foam_file("dictionary", "postDict", "system") + "\nfunctions\n{\n"
        for op in meta["open_patches"]:
            post_dict += f"""
phi_{op}
{{
    type            surfaceFieldValue;
    libs            ("libfieldFunctionObjects.so");
    region          air;
    writeControl    timeStep;
    writeInterval   1;
    writeFields     false;
    log             true;
    regionType      patch;
    name            {op};
    operation       sum;
    fields          (phi);
}}

p_{op}
{{
    type            surfaceFieldValue;
    libs            ("libfieldFunctionObjects.so");
    region          air;
    writeControl    timeStep;
    writeInterval   1;
    writeFields     false;
    log             true;
    regionType      patch;
    name            {op};
    operation       areaAverage;
    fields          (p_rgh);
}}
"""
        post_dict += "}\n"
        (case_dir / "system" / "postDict").write_text(post_dict)
        setup_cmds.append(
            "postProcess -dict system/postDict -region air -latestTime -fields '(phi p_rgh)' > log.post 2>&1 || true"
        )

    par_wrapper = case_dir / "run_par.sh"
    par_wrapper.write_text(
        "#!/usr/bin/env bash\n"
        "export LD_PRELOAD=\"${FOAM_LIBBIN:-/home/varuna/micromamba/envs/cfd/lib}/mpich-3.3/libPstream.so\"\n"
        "exec \"$@\"\n",
        newline="\n",
    )

    script_path = case_dir / "run_all.sh"
    script_header = (
        "#!/usr/bin/env bash\n"
        "set -e\n"
        "export FOAM_MPI=mpich-3.3\n"
        "export LD_LIBRARY_PATH=\"${FOAM_LIBBIN:-/home/varuna/micromamba/envs/cfd/lib}/mpich-3.3:${FOAM_LIBBIN:-/home/varuna/micromamba/envs/cfd/lib}:${LD_LIBRARY_PATH:-}\"\n"
    )
    script_path.write_text(script_header + "\n".join(setup_cmds) + "\n", newline="\n")
    run_cmd("/home/varuna/.local/bin/micromamba run -n cfd bash run_all.sh", cwd=case_dir)

    t_dir = case_dir / str(n_iter)
    if not t_dir.exists():
        # Find highest numeric time dir
        num_dirs = sorted([int(d.name) for d in case_dir.iterdir() if d.is_dir() and d.name.isdigit()])
        t_dir = case_dir / str(num_dirs[-1])

    # Read temperature and velocity fields
    T_air = read_foam_scalar_field(t_dir / "air" / "T") - 273.15
    U_air = read_foam_vector_field(t_dir / "air" / "U")
    cc_air = parse_cell_centers(t_dir, "air")

    T_ad = read_foam_scalar_field(t_dir / "adapter_pcb" / "T") - 273.15
    cc_ad = parse_cell_centers(t_dir, "adapter_pcb")

    T_k26 = read_foam_scalar_field(t_dir / "k26_sink" / "T") - 273.15
    cc_k26 = parse_cell_centers(t_dir, "k26_sink")

    # Component board and junction temperatures
    fan_extra = 0.15 if cfg.lid_fan_mode != "none" else 0.0
    comp_results = {}
    hottest_name = ""
    hottest_tj = -999.0
    for c in COMPONENTS:
        b = meta["ic_boxes"][c.name]
        mask = (
            (cc_ad[:, 0] >= b[0] - 1e-6) & (cc_ad[:, 0] <= b[1] + 1e-6) &
            (cc_ad[:, 1] >= b[2] - 1e-6) & (cc_ad[:, 1] <= b[3] + 1e-6)
        )
        t_board = float(np.mean(T_ad[mask])) if np.any(mask) else float(np.max(T_ad))
        pw = c.power_w * cfg.adapter_scale + (fan_extra if c.name == "U1001_LMR33630" else 0.0)
        if cfg.alu_spreader:
            # Parallel top thermal pad (0.5 mm 3 W/mK) + PCB path
            r_top = c.theta_jc_top + 1.8
            r_eff = (c.theta_jb * r_top) / (c.theta_jb + r_top)
            t_j = t_board + pw * r_eff
        else:
            t_j = t_board + pw * c.theta_jb
        comp_results[c.name] = {
            "T_board_C": round(t_board, 2),
            "T_j_C": round(t_j, 2),
            "margin_C": round(c.tj_max_c - t_j, 2),
        }
        if t_j > hottest_tj:
            hottest_tj = t_j
            hottest_name = c.name

    # K26 SOM junction temperature
    sb = meta["som_box"]
    som_mask = (
        (cc_k26[:, 0] >= sb[0]) & (cc_k26[:, 0] <= sb[1]) &
        (cc_k26[:, 1] >= sb[2]) & (cc_k26[:, 1] <= sb[3]) &
        (cc_k26[:, 2] <= sb[5] + 1e-5)
    )
    t_k26_sink_c = float(np.mean(T_k26[som_mask])) if np.any(som_mask) else float(np.max(T_k26))
    t_k26_j_c = t_k26_sink_c + cfg.som_power_w * K26_R_JC

    # Extract mass flux & pressure at vents from log.post
    t_amb_k = cfg.ambient_c + 273.15
    rho_amb = 101325.0 / (287.058 * t_amb_k)
    log_post = (case_dir / "log.post").read_text() if (case_dir / "log.post").exists() else ""

    patch_flows = {}
    for op in meta["open_patches"]:
        m_phi = re.findall(rf"sum\({re.escape(op)}\)\s+of\s+phi\s*=\s*([0-9.eE+-]+)", log_post)
        mass_kg_s = float(m_phi[-1]) if m_phi else 0.0
        vol_m3_s = mass_kg_s / rho_amb
        m_p = re.findall(rf"areaAverage\({re.escape(op)}\)\s+of\s+p_rgh\s*=\s*([0-9.eE+-]+)", log_post)
        p_pa = (float(m_p[-1]) - 101325.0) if m_p else 0.0
        patch_flows[op] = {
            "vol_m3_s": round(vol_m3_s, 6),
            "cfm": round(vol_m3_s * 2118.88, 2),
            "dp_Pa": round(p_pa, 2),
        }

    # Save 2D mid-plane Z~8 mm and X-Z slice Y~40 mm for plotting
    out_slices_dir.mkdir(parents=True, exist_ok=True)
    z_slice_mask = np.abs(cc_air[:, 2] - 7.5e-3) < 2.2e-3
    y_slice_mask = np.abs(cc_air[:, 1] - 42.0e-3) < 3.5e-3
    np.savez_compressed(
        out_slices_dir / f"{cfg.name}.npz",
        xy_x=cc_air[z_slice_mask, 0] * 1e3,
        xy_y=cc_air[z_slice_mask, 1] * 1e3,
        xy_T=T_air[z_slice_mask],
        xy_U=U_air[z_slice_mask],
        xz_x=cc_air[y_slice_mask, 0] * 1e3,
        xz_z=cc_air[y_slice_mask, 2] * 1e3,
        xz_T=T_air[y_slice_mask],
        xz_U=U_air[y_slice_mask],
        ad_x=cc_ad[:, 0] * 1e3,
        ad_y=cc_ad[:, 1] * 1e3,
        ad_T=T_ad,
    )

    # Check solver final residuals & cell count
    log_sol = (case_dir / "log.solver").read_text()
    m_res = re.findall(r"Solving for h, Initial residual = ([0-9.eE+-]+)", log_sol)
    final_h_res = float(m_res[-1]) if m_res else -1.0

    # Inner cavity pressure (relative to 101325 Pa)
    p_air = read_foam_scalar_field(t_dir / "air" / "p_rgh") - 101325.0

    res = {
        "name": cfg.name,
        "ambient_c": cfg.ambient_c,
        "mesh_level": cfg.mesh_level,
        "cells_air": int(len(T_air)),
        "cells_solid": int(len(T_ad) + len(T_k26)),
        "T_air_mean_C": round(float(np.mean(T_air)), 2),
        "T_air_max_C": round(float(np.max(T_air)), 2),
        "U_air_max_mps": round(float(np.max(np.linalg.norm(U_air, axis=1))), 2),
        "p_cav_mean_Pa": round(float(np.mean(p_air)), 2),
        "XC7A50T_board_C": comp_results["U1101_XC7A50T"]["T_board_C"],
        "XC7A50T_Tj_C": comp_results["U1101_XC7A50T"]["T_j_C"],
        "ADCLK948_Tj_C": comp_results["U401_ADCLK948"]["T_j_C"],
        "AD9484_Tj_C": comp_results["U501_AD9484"]["T_j_C"],
        "LMR33630_Tj_C": comp_results["U1001_LMR33630"]["T_j_C"],
        "TPS7A8300_Tj_C": comp_results["U1005_TPS7A8300"]["T_j_C"],
        "RTL8211_Tj_C": comp_results["U1201_RTL8211FSI"]["T_j_C"],
        "K26_sink_C": round(t_k26_sink_c, 2),
        "K26_Tj_C": round(t_k26_j_c, 2),
        "hottest_ic": hottest_name,
        "hottest_Tj_C": round(hottest_tj, 2),
        "patch_flows": patch_flows,
        "components": comp_results,
        "final_h_res": final_h_res,
        "elapsed_s": round(time.time() - t0, 1),
    }
    return res


def build_suite() -> List[CaseConfig]:
    cases = [
        # 1. Option 1: v1 Baseline at 25, 45, 70 C
        CaseConfig("v1_open_25C", ambient_c=25.0),
        CaseConfig("v1_open_45C", ambient_c=45.0),
        CaseConfig("v1_open_70C", ambient_c=70.0),

        # 2. Option 2: Sealed PETG-CF box (25, 45, 70 C) + PAHT-CF at 70 C
        CaseConfig("sealed_petg_25C", ambient_c=25.0, kv_top_grille=False, right_slots=False, sma_left_slots=False),
        CaseConfig("sealed_petg_45C", ambient_c=45.0, kv_top_grille=False, right_slots=False, sma_left_slots=False),
        CaseConfig("sealed_petg_70C", ambient_c=70.0, kv_top_grille=False, right_slots=False, sma_left_slots=False),
        CaseConfig("sealed_paht_70C", ambient_c=70.0, k_shell=0.35, kv_top_grille=False, right_slots=False, sma_left_slots=False),

        # 3. Option 3: Sealed + Internal Al Spreader/Pads + External Finned Al Lid (25, 45, 70 C)
        CaseConfig("sealed_alu_25C", ambient_c=25.0, alu_spreader=True, kv_top_grille=False, right_slots=False, sma_left_slots=False),
        CaseConfig("sealed_alu_45C", ambient_c=45.0, alu_spreader=True, kv_top_grille=False, right_slots=False, sma_left_slots=False),
        CaseConfig("sealed_alu_70C", ambient_c=70.0, alu_spreader=True, kv_top_grille=False, right_slots=False, sma_left_slots=False),

        # 4. Owner's 2nd Hex Grille over Adapter (Passive, Bare vs Dust Mesh) at 70 C
        CaseConfig("hex2_passive_bare_70C", ambient_c=70.0, adapter_grille=True, sma_left_slots=False, dust_filter=False),
        CaseConfig("hex2_passive_filt_70C", ambient_c=70.0, adapter_grille=True, sma_left_slots=False, dust_filter=True),

        # 5. Option 4a: 40x40x10mm 5V Lid Fan Impingement w/ Dust Filter (SMA slots closed for dust seal)
        CaseConfig("fan40_imp_filt_70C", ambient_c=70.0, adapter_grille=True, lid_fan_mode="impinge40",
                   sma_left_slots=False, right_slots_open_frac=1.6, dust_filter=True),

        # 6. Option 4b (Recommended): 50x50x10mm 5V Lid Fan Impingement w/ Removable Dust Filter (25, 45, 70 C)
        CaseConfig("fan50_imp_filt_25C", ambient_c=25.0, adapter_grille=True, lid_fan_mode="impinge50",
                   sma_left_slots=False, right_slots_open_frac=1.6, dust_filter=True),
        CaseConfig("fan50_imp_filt_45C", ambient_c=45.0, adapter_grille=True, lid_fan_mode="impinge50",
                   sma_left_slots=False, right_slots_open_frac=1.6, dust_filter=True),
        CaseConfig("fan50_imp_filt_70C", ambient_c=70.0, adapter_grille=True, lid_fan_mode="impinge50",
                   sma_left_slots=False, right_slots_open_frac=1.6, dust_filter=True),

        # 7. Exhaust mode + Dust-loaded filter + Worst-case power sensitivity at 70 C
        CaseConfig("fan50_exh_filt_70C", ambient_c=70.0, adapter_grille=True, lid_fan_mode="exhaust50",
                   sma_left_slots=False, right_slots_open_frac=1.6, dust_filter=True),
        CaseConfig("fan50_imp_clogged_70C", ambient_c=70.0, adapter_grille=True, lid_fan_mode="impinge50",
                   sma_left_slots=False, right_slots_open_frac=1.6, dust_filter=True, filter_clog_factor=2.0),
        CaseConfig("fan50_imp_maxpwr_70C", ambient_c=70.0, adapter_grille=True, lid_fan_mode="impinge50",
                   sma_left_slots=False, right_slots_open_frac=1.6, dust_filter=True,
                   som_power_w=12.0, adapter_scale=8.8 / 7.5),

        # 8. Mesh Convergence on Recommended Variant (coarse, medium already run above, fine)
        CaseConfig("conv_coarse_70C", ambient_c=70.0, mesh_level="coarse", adapter_grille=True, lid_fan_mode="impinge50",
                   sma_left_slots=False, right_slots_open_frac=1.6, dust_filter=True),
        CaseConfig("conv_fine_70C", ambient_c=70.0, mesh_level="fine", adapter_grille=True, lid_fan_mode="impinge50",
                   sma_left_slots=False, right_slots_open_frac=1.6, dust_filter=True),
    ]
    return cases


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scratch", default="/home/varuna/cfd_scratch")
    parser.add_argument("--nprocs", type=int, default=16)
    parser.add_argument("--only", help="Run single case by name")
    parser.add_argument("--keep-scratch", action="store_true")
    args = parser.parse_args()

    out_dir = Path(__file__).resolve().parent
    slices_dir = out_dir / "slices"
    res_file = out_dir / "results.json"
    scratch = Path(args.scratch)
    scratch.mkdir(parents=True, exist_ok=True)

    existing = {}
    if res_file.exists():
        existing = {r["name"]: r for r in json.loads(res_file.read_text())}

    suite = build_suite()
    if args.only:
        suite = [c for c in suite if c.name == args.only]
        if not suite:
            raise SystemExit(f"Unknown case {args.only}")

    for cfg in suite:
        print(f"=== Running {cfg.name} (Ta={cfg.ambient_c}C, mesh={cfg.mesh_level}) ===", flush=True)
        res = run_case(cfg, scratch, slices_dir, nprocs=args.nprocs)
        existing[cfg.name] = res
        res_file.write_text(json.dumps(list(existing.values()), indent=2))
        print(
            f"  Done in {res['elapsed_s']}s: air_max={res['T_air_max_C']}C "
            f"XC7A50T_Tj={res['XC7A50T_Tj_C']}C ADCLK948_Tj={res['ADCLK948_Tj_C']}C "
            f"K26_Tj={res['K26_Tj_C']}C flows={res['patch_flows']}",
            flush=True,
        )
        if not args.keep_scratch and (scratch / cfg.name).exists():
            shutil.rmtree(scratch / cfg.name)


if __name__ == "__main__":
    main()
