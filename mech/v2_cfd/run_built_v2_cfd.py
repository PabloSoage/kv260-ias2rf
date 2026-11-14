#!/usr/bin/env python3
"""
3D Conjugate Heat Transfer (CHT) CFD Verification of the Built Enclosure v2
(`mech/case_v2_bottom.stl`, `mech/case_v2_lid.stl`, `mech/case_v2_filter_frame.stl`).

Models exact built v2 geometry differences from `_work/mech/build_case.py --v2` & Rev06:
  - Adapter 50x50x10 mm 5V fan centered at (-40.0, +14.0) mm (not (-45, +45)),
    sitting inside a 1.2 mm square PETG-CF duct skirt (x [-66.2,-13.8], y [-12.2,40.2]),
    z = 18.75..28.75 mm fan housing + 20 mm hub below a 4 mm ceiling plenum (z = 28.75..32.75 mm).
  - Double 7 mm hex grille (1.6 mm walls, 39 cells -> 984.9 mm^2 open area inside 38x38 mm
    filter recess frame) + 100-mesh stainless filter (clean & 2x clogged).
  - SMA left wall closed (zero vent slots); right-wall exhaust widened to 13 slots of 3x16 mm
    (y = 10..85 mm, z = 10..26 mm).
  - Updated Rev06 adapter coordinates & thermal vias: Y401 Si549 at (-35.0, 8.8),
    U502/U503 AD8352 separated at (-48.9, -1.2) / (-57.2, -2.4), U1201 RTL8211FSI with
    10 thermal vias in exposed pad (theta_JB reduced from 12.0 to 5.0 C/W), J1002 fan header.
  - Stick-on aluminum heatsinks (thermally conductive epoxy, 0.15 mm @ 1.2 W/mK):
      U401 ADCLK948: 9x9x5 mm, Y401 Si549: 9x9x5 mm, U501 AD9484: 14x14x6 mm,
    plus no-heatsink baseline at 70 C and wide-grille/open-plenum sensitivity check.

Requires OpenFOAM v2412 in WSL (`/home/varuna/.local/bin/micromamba run -n cfd`).
"""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

# ---------------------------------------------------------------------------
# Built v2 Enclosure & PCB Geometric Constants (mm -> m, matching build_case.py --v2)
# ---------------------------------------------------------------------------
CAV_X0, CAV_X1 = -109.6e-3, 131.0e-3
CAV_Y0, CAV_Y1 = -12.2e-3, 112.0e-3
CAV_Z0, CAV_Z1 = -8.0e-3, 32.75e-3

ADAPTER_X0, ADAPTER_X1 = -107.2e-3, -10.0e-3
ADAPTER_Y0, ADAPTER_Y1 = -9.7e-3, 108.7e-3
ADAPTER_Z0, ADAPTER_Z1 = 0.8e-3, 2.4e-3

CARRIER_X0, CARRIER_X1 = -9.7e-3, 129.7e-3
CARRIER_Y0, CARRIER_Y1 = -9.7e-3, 108.7e-3
CARRIER_Z0, CARRIER_Z1 = -1.6e-3, 0.0e-3

KV_FAN_X, KV_FAN_Y, KV_FAN_R = 86.1e-3, 47.0e-3, 27.0e-3

# Built v2 fan centered at (-40.0, +14.0) mm over front hot strip
AD_FAN_X, AD_FAN_Y = -40.0e-3, 14.0e-3
FAN2_HALF = 25.0e-3
DUCT_T = 1.2e-3
FAN2_Z0, FAN2_Z1 = 18.75e-3, 28.75e-3  # ZF = Z_TOP_IN - 4 mm = 28.75 mm
FAN2_BORE_R = 24.0e-3
FAN2_HUB_R = 10.0e-3

# Built v2 39-cell hex grille aperture (~41x41 mm) inside 58x58 filter recess frame
GRILLE_HALF = 20.5e-3

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


@dataclass
class ComponentSpec:
    name: str
    x_mm: float
    y_mm: float
    footprint_mm: float
    power_w: float
    theta_jb: float
    theta_jc_top: float
    tj_max_c: float
    hs_size_mm: Optional[Tuple[float, float, float]] = None  # (wx, wy, h)
    r_tim: float = 0.0
    k_pkg: float = 1.5


# Rev06 adapter specs & coords (task23.md + Rev06 RTL8211FSI 10 thermal vias)
COMPONENTS: List[ComponentSpec] = [
    ComponentSpec("U401_ADCLK948",    -34.90,  -0.20,  6.0, 0.95,  8.8, 12.0, 150.0, hs_size_mm=(9.0, 9.0, 5.0),  r_tim=5.0, k_pkg=1.51),
    ComponentSpec("Y401_Si549",       -35.00,   8.80,  5.0, 0.50, 20.0, 25.0, 105.0, hs_size_mm=(9.0, 9.0, 5.0),  r_tim=6.0, k_pkg=1.10),
    ComponentSpec("U501_AD9484",      -51.80,  10.60,  8.0, 1.05,  8.5,  1.7, 125.0, hs_size_mm=(14.0, 14.0, 6.0), r_tim=1.95, k_pkg=1.79),
    ComponentSpec("U502_AD8352",      -48.90,  -1.20,  4.0, 0.20, 14.0, 20.0, 125.0),
    ComponentSpec("U503_AD8352",      -57.20,  -2.40,  4.0, 0.20, 14.0, 20.0, 125.0),
    ComponentSpec("U601_AD9253",      -70.25,  10.35,  8.0, 0.46, 12.0,  7.1, 125.0),
    ComponentSpec("U1101_XC7A50T",    -42.75,  40.00, 17.0, 0.73,  8.4,  4.24, 100.0),
    ComponentSpec("U1001_LMR33630",   -30.25,  94.00,  6.0, 0.88, 13.6, 22.0, 150.0),
    ComponentSpec("U1002_TPS562201",  -54.75, 104.50,  4.0, 0.41, 15.0, 28.0, 125.0),
    ComponentSpec("U1003_TPS562201",  -54.75,  95.50,  4.0, 0.20, 15.0, 28.0, 125.0),
    ComponentSpec("U1004_TPS562201",  -54.75,  86.50,  4.0, 0.10, 15.0, 28.0, 125.0),
    ComponentSpec("U1005_TPS7A8300",  -43.25,  81.00,  4.5, 0.50, 12.3, 25.0, 125.0),
    ComponentSpec("U1006_TPS7A8300",  -35.25,  81.00,  4.5, 0.35, 12.3, 25.0, 125.0),
    ComponentSpec("U1007_TPS7A8300",  -27.25,  81.00,  4.5, 0.17, 12.3, 25.0, 125.0),
    ComponentSpec("U1201_RTL8211FSI", -18.20,  -1.00,  6.0, 0.50,  5.0, 18.0, 125.0),  # Rev06: 10 thermal vias (was 12.0 C/W)
    ComponentSpec("AD9708_AD9767",    -45.50,  71.00, 14.0, 0.30, 18.0, 30.0, 125.0),
]

KV260_CARRIER_W = 2.0
K26_SOM_W = 9.0
K26_R_JC = 1.4
K26_TJ_MAX = 100.0

# Sunon MF50100V1-1000U 5V: 8.5 CFM (4.00e-3 m3/s) max, 22.0 Pa shutoff
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
class BuiltCaseConfig:
    name: str
    ambient_c: float = 70.0
    mesh_level: str = "medium"       # medium | fine
    with_heatsinks: bool = True      # stick-on heatsinks on U401, Y401, U501
    filter_clog_factor: float = 1.0  # 1.0 = clean 100-mesh; 2.0 = 2x clogged
    wide_grille: bool = False        # Improvement 1: widen 39-hex (985 mm^2) to 48 mm bore (~1700 mm^2)
    decouple_hs: bool = False        # Improvement 2: trim U401/Y401 sinks so >=1.8 mm air gap separates them
    expand_exhaust: bool = False     # Improvement 3: widen right-wall slots y=4..106, z=6..28 mm
    keep_vtk: bool = False


def mesh_counts(level: str) -> Tuple[int, int, int]:
    if level == "fine":
        return (128, 72, 51)        # dz = 0.799 mm -> adapter_pcb snaps directly to 1.60 mm (2 cells)
    return (96, 54, 30)


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


def box_src(name: str, b: Tuple[float, float, float, float, float, float], action: str = "new") -> str:
    return f"""
    {{
        name    {name};
        type    cellSet;
        action  {action};
        source  boxToCell;
        box     ({b[0] + 1e-6:.6f} {b[2] + 1e-6:.6f} {b[4] + 1e-6:.6f}) ({b[1] - 1e-6:.6f} {b[3] - 1e-6:.6f} {b[5] - 1e-6:.6f});
    }}"""


def cyl_src(name: str, cx: float, cy: float, z0: float, z1: float, r: float, action: str = "new") -> str:
    return f"""
    {{
        name    {name};
        type    cellSet;
        action  {action};
        source  cylinderToCell;
        p1      ({cx:.6f} {cy:.6f} {z0:.6f});
        p2      ({cx:.6f} {cy:.6f} {z1:.6f});
        radius  {r:.6f};
    }}"""


def generate_case(cfg: BuiltCaseConfig, case_dir: Path, nprocs: int = 16) -> dict:
    if case_dir.exists():
        shutil.rmtree(case_dir)
    case_dir.mkdir(parents=True)

    nx, ny, nz = mesh_counts(cfg.mesh_level)
    xs = snap_bounds(nx, CAV_X0, CAV_X1)
    ys = snap_bounds(ny, CAV_Y0, CAV_Y1)
    zs = snap_bounds(nz, CAV_Z0, CAV_Z1)

    t_amb_k = cfg.ambient_c + 273.15
    k_shell = 0.25

    ad_box = nearest_grid_box(ADAPTER_X0, ADAPTER_X1, ADAPTER_Y0, ADAPTER_Y1, ADAPTER_Z0, ADAPTER_Z1, xs, ys, zs)
    ca_box = nearest_grid_box(CARRIER_X0, CARRIER_X1, CARRIER_Y0, CARRIER_Y1, CARRIER_Z0, CARRIER_Z1, xs, ys, zs)
    sb_box = nearest_grid_box(SINK_X0, SINK_X1, SINK_Y0, SINK_Y1, SINK_BASE_Z0, SINK_BASE_Z1, xs, ys, zs)
    fin_boxes = [
        nearest_grid_box(SINK_X0, SINK_X1, fy0, fy1, sb_box[5], SINK_FIN_Z1, xs, ys, zs)
        for fy0, fy1 in FIN_Y_SPANS
    ]

    # Fan shroud + 4mm ceiling plenum duct (PETG-CF) in built v2
    # Outer square: x [-66.2, -13.8], y [-12.2, 40.2]; inner square bore: x [-65, -15], y [-11, 39]
    duct_outer = nearest_grid_box(
        AD_FAN_X - FAN2_HALF - DUCT_T, AD_FAN_X + FAN2_HALF + DUCT_T,
        AD_FAN_Y - FAN2_HALF - DUCT_T, AD_FAN_Y + FAN2_HALF + DUCT_T,
        FAN2_Z0, CAV_Z1, xs, ys, zs
    )
    duct_inner_plenum = nearest_grid_box(
        AD_FAN_X - FAN2_HALF, AD_FAN_X + FAN2_HALF,
        AD_FAN_Y - FAN2_HALF, AD_FAN_Y + FAN2_HALF,
        FAN2_Z1, CAV_Z1, xs, ys, zs
    )
    fan_outer = nearest_grid_box(
        AD_FAN_X - FAN2_HALF - DUCT_T, AD_FAN_X + FAN2_HALF + DUCT_T,
        AD_FAN_Y - FAN2_HALF - DUCT_T, AD_FAN_Y + FAN2_HALF + DUCT_T,
        FAN2_Z0, FAN2_Z1, xs, ys, zs
    )
    fan_z0_snap = fan_outer[4]
    fan_z1_snap = fan_outer[5]

    hs_specs = [c for c in COMPONENTS if c.hs_size_mm is not None]
    pkg_boxes: Dict[str, Tuple[float, float, float, float, float, float]] = {}
    hs_boxes: Dict[str, Tuple[float, float, float, float, float, float]] = {}
    if cfg.with_heatsinks:
        for c in hs_specs:
            # Package + TIM layer on top of adapter_pcb
            hp = c.footprint_mm * 0.5e-3
            pkg_z1 = ad_box[5] + 1.5e-3
            pb = nearest_grid_box(
                c.x_mm * 1e-3 - hp, c.x_mm * 1e-3 + hp,
                c.y_mm * 1e-3 - hp, c.y_mm * 1e-3 + hp,
                ad_box[5], pkg_z1, xs, ys, zs
            )
            pkg_boxes[c.name] = pb
            # Heatsink body directly on top of pb[5]
            wx, wy, hz = c.hs_size_mm
            if cfg.decouple_hs and c.name == "U401_ADCLK948":
                # Trim +Y edge so a clean air gap isolates U401 (0.95 W) from Y401 while covering 6x6 mm pkg
                y0_hs, y1_hs = c.y_mm * 1e-3 - 4.5e-3, c.y_mm * 1e-3 + 2.5e-3
            elif cfg.decouple_hs and c.name == "Y401_Si549":
                # Trim -Y edge so >=3 mm air gap separates hs_U401 and hs_Y401 while covering 5x5 mm pkg
                y0_hs, y1_hs = c.y_mm * 1e-3 - 2.5e-3, c.y_mm * 1e-3 + 4.5e-3
            else:
                y0_hs, y1_hs = c.y_mm * 1e-3 - 0.5e-3 * wy, c.y_mm * 1e-3 + 0.5e-3 * wy
            hb = nearest_grid_box(
                c.x_mm * 1e-3 - 0.5e-3 * wx, c.x_mm * 1e-3 + 0.5e-3 * wx,
                y0_hs, y1_hs,
                pb[5], pb[5] + hz * 1e-3, xs, ys, zs
            )
            # Note: in nominal built v2, Y401 & U401 are 9.0 mm c-c so un-trimmed 9x9 sinks touch at y=4.3 mm
            hs_boxes[c.name] = hb

    regions_solid = ["adapter_pcb", "kv260_carrier", "k26_sink", "duct_petg"]
    if cfg.with_heatsinks:
        for c in hs_specs:
            short = c.name.split("_")[0]
            regions_solid.append(f"pkg_{short}")
            regions_solid.append(f"hs_{short}")

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
    wall_bottom {{ type wall; faces ( (0 3 2 1) ); }}
    wall_top    {{ type wall; faces ( (4 5 6 7) ); }}
    wall_left   {{ type wall; faces ( (0 4 7 3) ); }}
    wall_right  {{ type wall; faces ( (1 2 6 5) ); }}
    wall_front  {{ type wall; faces ( (0 1 5 4) ); }}
    wall_back   {{ type wall; faces ( (3 7 6 2) ); }}
);
"""
    (case_dir / "system" / "blockMeshDict").write_text(bmesh)

    # Vent boundary patches: kv_grille, built adapter_opening, 13x right_vents (NO left SMA vents!)
    top_actions = []
    create_patches = []

    r_kv = KV_FAN_R * 0.90
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

    if cfg.wide_grille:
        top_actions.append(f"""
    {{
        name    f_ad_opening;
        type    faceSet;
        action  new;
        source  cylinderToFace;
        p1      ({AD_FAN_X:.5f} {AD_FAN_Y:.5f} {CAV_Z1 - 0.002:.5f});
        p2      ({AD_FAN_X:.5f} {AD_FAN_Y:.5f} {CAV_Z1 + 0.002:.5f});
        radius  {FAN2_BORE_R:.5f};
    }}""")
    else:
        # Built v2: 39 hex cells clipped inside ~41x41 mm filter frame inner aperture
        top_actions.append(f"""
    {{
        name    f_ad_opening;
        type    faceSet;
        action  new;
        source  boxToFace;
        box     ({AD_FAN_X - GRILLE_HALF:.5f} {AD_FAN_Y - GRILLE_HALF:.5f} {CAV_Z1 - 0.002:.5f}) ({AD_FAN_X + GRILLE_HALF:.5f} {AD_FAN_Y + GRILLE_HALF:.5f} {CAV_Z1 + 0.002:.5f});
    }}""")
    top_actions.append("""
    {
        name    f_ad_opening;
        type    faceSet;
        action  subset;
        source  patchToFace;
        patch   wall_top;
    }""")
    create_patches.append("""
    {
        name adapter_opening;
        patchInfo { type patch; }
        constructFrom set;
        set f_ad_opening;
    }""")

    # Built v2 right-wall exhaust: 13 slots 3x16 mm (y=10..85 mm, z=10..26 mm), or expanded 17x(3.5x22 mm) y=4..106, z=6..28 mm
    rv_y0, rv_y1 = (4.0e-3, 106.0e-3) if cfg.expand_exhaust else (10.0e-3, 85.0e-3)
    rv_z0, rv_z1 = (6.0e-3, 28.0e-3) if cfg.expand_exhaust else (10.0e-3, 26.0e-3)
    top_actions.append(f"""
    {{
        name    f_right_vents;
        type    faceSet;
        action  new;
        source  boxToFace;
        box     ({CAV_X1 - 0.002:.5f} {rv_y0:.5f} {rv_z0:.5f}) ({CAV_X1 + 0.002:.5f} {rv_y1:.5f} {rv_z1:.5f});
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

    # Solid cellZones
    solid_actions = []
    solid_actions.append(box_src("adapter_pcb", ad_box, "new"))
    solid_actions.append(box_src("kv260_carrier", ca_box, "new"))
    solid_actions.append(box_src("k26_sink", sb_box, "new"))
    for fb in fin_boxes:
        solid_actions.append(box_src("k26_sink", fb, "add"))

    # Duct + fan shroud + center motor hub in `duct_petg` (full z=18.75..32.75 mm shroud)
    solid_actions.append(box_src("duct_petg", duct_outer, "new"))
    solid_actions.append(box_src("duct_petg", duct_inner_plenum, "delete"))
    solid_actions.append(cyl_src("duct_petg", AD_FAN_X, AD_FAN_Y, fan_z0_snap - 1e-4, fan_z1_snap + 1e-4, FAN2_BORE_R, "delete"))
    solid_actions.append(cyl_src("duct_petg", AD_FAN_X, AD_FAN_Y, fan_z0_snap + 0.5e-3, fan_z1_snap - 0.5e-3, FAN2_HUB_R, "add"))

    if cfg.with_heatsinks:
        for c in hs_specs:
            short = c.name.split("_")[0]
            solid_actions.append(box_src(f"pkg_{short}", pkg_boxes[c.name], "new"))
            solid_actions.append(box_src(f"hs_{short}", hs_boxes[c.name], "new"))

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
    tdict += "actions\n(\n" + "".join(top_actions) + "".join(solid_actions) + f"""
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

    # adapter_pcb IC zones (for non-heatsinked ICs, or all ICs when without heatsinks)
    ic_actions = []
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
    (case_dir / "system" / "adapter_pcb").mkdir(parents=True, exist_ok=True)
    (case_dir / "system" / "adapter_pcb" / "topoSetDict").write_text(
        foam_file("dictionary", "topoSetDict", "system") + "actions\n(\n" + "".join(ic_actions) + "\n);\n"
    )

    som_box = nearest_grid_box(66e-3, 106e-3, 27e-3, 67e-3, sb_box[4], sb_box[5], xs, ys, zs)
    (case_dir / "system" / "k26_sink").mkdir(parents=True, exist_ok=True)
    (case_dir / "system" / "k26_sink" / "topoSetDict").write_text(
        foam_file("dictionary", "topoSetDict", "system")
        + "actions\n(\n" + box_src("k26_som", som_box, "new")
        + "\n    { name k26_som; type cellZoneSet; action new; source setToCellZone; set k26_som; }\n);\n"
    )

    # Air cellZones: KV260 OEM fan, built right exhaust slots, built double-hex-grille + 100-mesh filter
    air_actions = [
        f"""
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
    }}
    {{
        name    right_slot_zone;
        type    cellSet;
        action  new;
        source  boxToCell;
        box     ({CAV_X1 - 0.005:.5f} {rv_y0:.5f} {rv_z0:.5f}) ({CAV_X1:.5f} {rv_y1:.5f} {rv_z1:.5f});
    }}
    {{
        name    right_slot_zone;
        type    cellZoneSet;
        action  new;
        source  setToCellZone;
        set     right_slot_zone;
    }}"""
    ]
    if cfg.wide_grille:
        air_actions.append(f"""
    {{
        name    dust_filter_zone;
        type    cellSet;
        action  new;
        source  cylinderToCell;
        p1      ({AD_FAN_X:.5f} {AD_FAN_Y:.5f} {CAV_Z1 - 0.004:.5f});
        p2      ({AD_FAN_X:.5f} {AD_FAN_Y:.5f} {CAV_Z1:.5f});
        radius  {FAN2_BORE_R:.5f};
    }}""")
    else:
        air_actions.append(f"""
    {{
        name    dust_filter_zone;
        type    cellSet;
        action  new;
        source  boxToCell;
        box     ({AD_FAN_X - GRILLE_HALF:.5f} {AD_FAN_Y - GRILLE_HALF:.5f} {CAV_Z1 - 0.004:.5f}) ({AD_FAN_X + GRILLE_HALF:.5f} {AD_FAN_Y + GRILLE_HALF:.5f} {CAV_Z1:.5f});
    }}""")
    air_actions.append("""
    {
        name    dust_filter_zone;
        type    cellZoneSet;
        action  new;
        source  setToCellZone;
        set     dust_filter_zone;
    }""")

    (case_dir / "system" / "air").mkdir(parents=True, exist_ok=True)
    (case_dir / "system" / "air" / "topoSetDict").write_text(
        foam_file("dictionary", "topoSetDict", "system") + "actions\n(\n" + "".join(air_actions) + "\n);\n"
    )

    (case_dir / "constant" / "regionProperties").write_text(
        foam_file("dictionary", "regionProperties", "constant")
        + "regions\n(\n    fluid       (air)\n    solid       (" + " ".join(regions_solid) + ")\n);\n"
    )
    (case_dir / "constant" / "g").write_text(
        foam_file("uniformDimensionedVectorField", "g", "constant")
        + "dimensions      [0 1 -2 0 0 0 0];\nvalue           (0 0 -9.81);\n"
    )

    n_iter = 900 if cfg.mesh_level != "fine" else 1100
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

    decomp_d = foam_file("dictionary", "decomposeParDict", "system") + f"numberOfSubdomains {nprocs};\nmethod          scotch;\n"
    (case_dir / "system" / "decomposeParDict").write_text(decomp_d)
    (case_dir / "system" / "air" / "decomposeParDict").write_text(decomp_d)

    (case_dir / "system" / "fvSchemes").write_text(
        foam_file("dictionary", "fvSchemes", "system")
        + "ddtSchemes { default steadyState; }\ngradSchemes { default Gauss linear; }\n"
        + "divSchemes { default none; }\nlaplacianSchemes { default Gauss linear limited 0.5; }\n"
        + "interpolationSchemes { default linear; }\nsnGradSchemes { default limited 0.5; }\n"
    )
    (case_dir / "system" / "fvSolution").write_text(
        foam_file("dictionary", "fvSolution", "system") + "SIMPLE { nOuterCorrectors 1; }\n"
    )

    (case_dir / "constant" / "air").mkdir(parents=True, exist_ok=True)
    (case_dir / "constant" / "air" / "thermophysicalProperties").write_text(
        foam_file("dictionary", "thermophysicalProperties", "constant")
        + """thermoType { type heRhoThermo; mixture pureMixture; transport const; thermo hConst; equationOfState perfectGas; specie specie; energy sensibleEnthalpy; }
mixture { specie { molWeight 28.97; } thermodynamics { Cp 1007; Hf 0; } transport { mu 1.98e-05; Pr 0.708; } }
"""
    )
    (case_dir / "constant" / "air" / "turbulenceProperties").write_text(
        foam_file("dictionary", "turbulenceProperties", "constant")
        + "simulationType RAS;\nRAS { RASModel kOmegaSST; turbulence on; printCoeffs on; }\n"
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
SIMPLE { momentumPredictor true; nNonOrthogonalCorrectors 0; frozenFlow false; pRefCell 0; pRefValue 101325; }
relaxationFactors { fields { p_rgh 0.35; rho 1; } equations { U 0.55; h 0.80; k 0.60; omega 0.60; } }
"""
    )

    # Built right exhaust: 13 slots 3x16 mm (y=10..85, z=10..26 -> f=210), or expanded 17x(3.5x22 mm) -> f=120
    # Built filter + double 3mm hex grille (39 cells = 984.9 mm2 inside 41x41mm -> 3.38x higher dyn loss vs 48 mm open bore)
    c = cfg.filter_clog_factor
    f_rv = 120.0 if cfg.expand_exhaust else 210.0
    if cfg.wide_grille:
        d_coef, f_coef = 1.65e7 * c, 740.0 * c
    else:
        d_coef, f_coef = 2.80e7 * c, 2100.0 * c

    fv_air = foam_file("dictionary", "fvOptions", "system") + f"""kv260_fan_momentum
{{
    type            vectorSemiImplicitSource;
    active          true;
    selectionMode   cellZone;
    cellZone        kv260_fan_zone;
    volumeMode      specific;
    sources {{ U ( (0 0 -5200) -25.0 ); }}
}}
right_slot_loss
{{
    type            explicitPorositySource;
    active          true;
    explicitPorositySourceCoeffs
    {{
        selectionMode   cellZone;
        cellZone        right_slot_zone;
        type DarcyForchheimer;
        d   (1e6 1e6 1e6);
        f   ({f_rv:.1f} {f_rv:.1f} {f_rv:.1f});
        coordinateSystem {{ origin (0 0 0); e1 (1 0 0); e2 (0 1 0); }}
    }}
}}
dust_filter_loss
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

    # Conserve exact 1.60 mm PCB in-plane conductance (k * t = 18.0 * 1.6e-3 W/K) across grid snaps
    t_ad = max(ad_box[5] - ad_box[4], 1e-4)
    t_ca = max(ca_box[5] - ca_box[4], 1e-4)
    solid_k: Dict[str, float] = {
        "adapter_pcb":   18.0 * (1.6e-3 / t_ad),
        "kv260_carrier": 18.0 * (1.6e-3 / t_ca),
        "k26_sink":      85.0,
        "duct_petg":     0.25,
    }
    if cfg.with_heatsinks:
        for cspec in hs_specs:
            short = cspec.name.split("_")[0]
            t_pkg = max(pkg_boxes[cspec.name][5] - pkg_boxes[cspec.name][4], 1e-4)
            solid_k[f"pkg_{short}"] = cspec.k_pkg * (t_pkg / 1.5e-3)
            solid_k[f"hs_{short}"] = 167.0  # Aluminum 6063/6061 stick-on heatsink

    for sreg in regions_solid:
        (case_dir / "constant" / sreg).mkdir(parents=True, exist_ok=True)
        (case_dir / "system" / sreg).mkdir(parents=True, exist_ok=True)
        (case_dir / "constant" / sreg / "thermophysicalProperties").write_text(
            foam_file("dictionary", "thermophysicalProperties", "constant")
            + f"""thermoType {{ type heSolidThermo; mixture pureMixture; transport constIso; thermo hConst; equationOfState rhoConst; specie specie; energy sensibleEnthalpy; }}
mixture {{ specie {{ molWeight 50; }} transport {{ kappa {solid_k[sreg]}; }} thermodynamics {{ Hf 0; Cp 500; }} equationOfState {{ rho 2700; }} }}
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
            + "solvers { h { solver PCG; preconditioner DIC; tolerance 1e-8; relTol 0.05; } }\nSIMPLE {}\nrelaxationFactors { equations { h 1.0; } }\n"
        )
        (case_dir / "system" / sreg / "decomposeParDict").write_text(decomp_d)

    # Heat sources: if with_heatsinks, inject hs-IC power inside pkg_<short>; else all in adapter_pcb
    hs_names = {c.name for c in hs_specs}
    fv_ad = foam_file("dictionary", "fvOptions", "system")
    for cspec in COMPONENTS:
        if cfg.with_heatsinks and cspec.name in hs_names:
            continue
        pw = cspec.power_w + (0.15 if cspec.name == "U1001_LMR33630" else 0.0)
        fv_ad += f"""src_{cspec.name}
{{
    type            scalarSemiImplicitSource;
    active          true;
    selectionMode   cellZone;
    cellZone        {cspec.name};
    volumeMode      absolute;
    sources {{ h ( {pw:.4f} 0 ); }}
}}
"""
    (case_dir / "system" / "adapter_pcb" / "fvOptions").write_text(fv_ad)

    if cfg.with_heatsinks:
        for cspec in hs_specs:
            short = cspec.name.split("_")[0]
            (case_dir / "system" / f"pkg_{short}" / "fvOptions").write_text(
                foam_file("dictionary", "fvOptions", "system")
                + f"""src_{cspec.name}
{{
    type            scalarSemiImplicitSource;
    active          true;
    selectionMode   all;
    volumeMode      absolute;
    sources {{ h ( {cspec.power_w:.4f} 0 ); }}
}}
"""
            )

    (case_dir / "system" / "kv260_carrier" / "fvOptions").write_text(
        foam_file("dictionary", "fvOptions", "system")
        + f"src_carrier {{ type scalarSemiImplicitSource; active true; selectionMode all; volumeMode absolute; sources {{ h ( {KV260_CARRIER_W:.4f} 0 ); }} }}\n"
    )
    (case_dir / "system" / "k26_sink" / "fvOptions").write_text(
        foam_file("dictionary", "fvOptions", "system")
        + f"src_k26_som {{ type scalarSemiImplicitSource; active true; selectionMode cellZone; cellZone k26_som; volumeMode absolute; sources {{ h ( {K26_SOM_W:.4f} 0 ); }} }}\n"
    )

    # Boundary conditions
    (case_dir / "0.orig" / "air").mkdir()
    for sreg in regions_solid:
        (case_dir / "0.orig" / sreg).mkdir()

    def ext_wall_t(thickness_m: float, k_w: float, h_ext: float, method: str = "fluidThermo") -> str:
        return f"""type externalWallHeatFluxTemperature; kappaMethod {method}; mode coefficient; h uniform {h_ext:.2f}; Ta uniform {t_amb_k:.2f}; thicknessLayers ({thickness_m:.5f}); kappaLayers ({k_w:.3f}); value uniform {t_amb_k:.2f};"""

    coupled_fluid = f"""type compressible::turbulentTemperatureRadCoupledMixed; qrNbr none; qr none; Tnbr T; kappaMethod fluidThermo; useImplicit false; value uniform {t_amb_k:.2f};"""
    coupled_solid = f"""type compressible::turbulentTemperatureRadCoupledMixed; qrNbr none; qr none; Tnbr T; kappaMethod solidThermo; useImplicit false; value uniform {t_amb_k:.2f};"""

    open_patches = ["kv_grille", "adapter_opening", "right_vents"]

    u_txt = foam_file("volVectorField", "U", "0/air") + "dimensions [0 1 -1 0 0 0 0];\ninternalField uniform (0 0 0);\nboundaryField\n{\n    #includeEtc \"caseDicts/setConstraintTypes\"\n"
    for w in ["wall_bottom", "wall_top", "wall_left", "wall_right", "wall_front", "wall_back"]:
        u_txt += f"    {w} {{ type noSlip; }}\n"
    u_txt += '    "air_to_.*" { type noSlip; }\n'
    for op in open_patches:
        u_txt += f"    {op} {{ type pressureInletOutletVelocity; value uniform (0 0 0); }}\n"
    (case_dir / "0.orig" / "air" / "U").write_text(u_txt + "}\n")

    t_txt = foam_file("volScalarField", "T", "0/air") + f"dimensions [0 0 0 1 0 0 0];\ninternalField uniform {t_amb_k:.2f};\nboundaryField\n{{\n    #includeEtc \"caseDicts/setConstraintTypes\"\n"
    t_txt += f"    wall_bottom {{ {ext_wall_t(0.0030, k_shell, 8.0)} }}\n"
    t_txt += f"    wall_top    {{ {ext_wall_t(0.0030, k_shell, 12.0)} }}\n"
    for w in ["wall_left", "wall_right", "wall_front", "wall_back"]:
        t_txt += f"    {w} {{ {ext_wall_t(0.0035, k_shell, 10.5)} }}\n"
    t_txt += f'    "air_to_.*" {{ {coupled_fluid} }}\n'
    for op in open_patches:
        t_txt += f"    {op} {{ type inletOutlet; inletValue uniform {t_amb_k:.2f}; value uniform {t_amb_k:.2f}; }}\n"
    (case_dir / "0.orig" / "air" / "T").write_text(t_txt + "}\n")

    pr_txt = foam_file("volScalarField", "p_rgh", "0/air") + "dimensions [1 -1 -2 0 0 0 0];\ninternalField uniform 101325;\nboundaryField\n{\n    #includeEtc \"caseDicts/setConstraintTypes\"\n"
    for w in ["wall_bottom", "wall_top", "wall_left", "wall_right", "wall_front", "wall_back"]:
        pr_txt += f"    {w} {{ type fixedFluxPressure; value $internalField; }}\n"
    pr_txt += '    "air_to_.*" { type fixedFluxPressure; value $internalField; }\n'
    pts = " ".join(f"({q:.6f} {dp:.2f})" for q, dp in FAN_50_PQ)
    pr_txt += f"""    kv_grille {{ type totalPressure; p0 uniform 101325; value $internalField; }}
    right_vents {{ type totalPressure; p0 uniform 101325; value $internalField; }}
    adapter_opening
    {{
        type            fanPressure;
        direction       in;
        fanCurve
        {{
            type        table;
            values      ( {pts} );
        }}
        p0              uniform 101325;
        value           $internalField;
    }}
}}
"""
    (case_dir / "0.orig" / "air" / "p_rgh").write_text(pr_txt)

    open_boundary = "    #includeEtc \"caseDicts/setConstraintTypes\"\n    \"wall_.*\" { type calculated; value $internalField; }\n    \"air_to_.*\" { type calculated; value $internalField; }\n"
    for op in open_patches:
        open_boundary += f"    {op} {{ type calculated; value $internalField; }}\n"
    (case_dir / "0.orig" / "air" / "p").write_text(
        foam_file("volScalarField", "p", "0/air") + "dimensions [1 -1 -2 0 0 0 0];\ninternalField uniform 101325;\nboundaryField\n{\n" + open_boundary + "}\n"
    )

    for fld, dim, val, wf in [
        ("k", "[0 2 -2 0 0 0 0]", "0.01", "kqRWallFunction"),
        ("omega", "[0 0 -1 0 0 0 0]", "50", "omegaWallFunction"),
        ("nut", "[0 2 -1 0 0 0 0]", "0", "nutkWallFunction"),
        ("alphat", "[1 -1 -1 0 0 0 0]", "0", "compressible::alphatWallFunction"),
    ]:
        txt = foam_file("volScalarField", fld, "0/air") + f"dimensions {dim};\ninternalField uniform {val};\nboundaryField\n{{\n    #includeEtc \"caseDicts/setConstraintTypes\"\n"
        extra = " Prt 0.85;" if fld == "alphat" else ""
        for w in ["wall_bottom", "wall_top", "wall_left", "wall_right", "wall_front", "wall_back"]:
            txt += f"    {w} {{ type {wf};{extra} value $internalField; }}\n"
        txt += f'    "air_to_.*" {{ type {wf};{extra} value $internalField; }}\n'
        for op in open_patches:
            if fld in ("k", "omega"):
                txt += f"    {op} {{ type inletOutlet; inletValue $internalField; value $internalField; }}\n"
            else:
                txt += f"    {op} {{ type calculated; value uniform 0; }}\n"
        (case_dir / "0.orig" / "air" / fld).write_text(txt + "}\n")

    for sreg in regions_solid:
        st_txt = foam_file("volScalarField", "T", f"0/{sreg}") + f"dimensions [0 0 0 1 0 0 0];\ninternalField uniform {t_amb_k + 10.0:.2f};\nboundaryField\n{{\n    #includeEtc \"caseDicts/setConstraintTypes\"\n"
        st_txt += f'    "{sreg}_to_.*" {{ {coupled_solid} }}\n'
        st_txt += f'    "wall_.*" {{ {ext_wall_t(0.0035, k_shell, 10.5, "solidThermo")} }}\n}}\n'
        (case_dir / "0.orig" / sreg / "T").write_text(st_txt)
        (case_dir / "0.orig" / sreg / "p").write_text(
            foam_file("volScalarField", "p", f"0/{sreg}")
            + f'dimensions [1 -1 -2 0 0 0 0];\ninternalField uniform 101325;\nboundaryField\n{{\n    #includeEtc "caseDicts/setConstraintTypes"\n    "{sreg}_to_.*" {{ type zeroGradient; }}\n    "wall_.*" {{ type zeroGradient; }}\n}}\n'
        )

    return {
        "xs": xs, "ys": ys, "zs": zs,
        "ad_box": ad_box, "ca_box": ca_box, "sb_box": sb_box,
        "som_box": som_box, "ic_boxes": ic_boxes,
        "pkg_boxes": pkg_boxes, "hs_boxes": hs_boxes,
        "regions_solid": regions_solid,
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
    return np.column_stack([
        read_foam_scalar_field(post_dir / region / "Cx"),
        read_foam_scalar_field(post_dir / region / "Cy"),
        read_foam_scalar_field(post_dir / region / "Cz"),
    ])


def run_case(cfg: BuiltCaseConfig, scratch_root: Path, out_slices_dir: Path, nprocs: int = 16) -> dict:
    t0 = time.time()
    case_dir = scratch_root / cfg.name
    meta = generate_case(cfg, case_dir, nprocs=nprocs)
    n_iter = meta["n_iter"]

    setup_cmds = [
        "blockMesh > log.blockMesh 2>&1",
        "topoSet > log.topoSet 2>&1",
        "createPatch -overwrite > log.createPatch 2>&1",
        "decomposePar > log.decomp 2>&1",
        "rm -rf 0 && cp -r 0.orig 0",
        "for d in processor*; do rm -rf \"$d/0\" && cp -r 0.orig \"$d/0\"; done",
        f"mpirun -np {nprocs} bash ./run_par.sh splitMeshRegions -cellZonesOnly -overwrite -parallel > log.split 2>&1",
        f"mpirun -np {nprocs} bash ./run_par.sh topoSet -region adapter_pcb -parallel > log.topoAdapter 2>&1",
        f"mpirun -np {nprocs} bash ./run_par.sh topoSet -region k26_sink -parallel > log.topoK26 2>&1",
        f"mpirun -np {nprocs} bash ./run_par.sh topoSet -region air -parallel > log.topoAir 2>&1",
        f"mpirun -np {nprocs} bash ./run_par.sh chtMultiRegionSimpleFoam -parallel > log.solver 2>&1",
        "reconstructParMesh -allRegions -constant > log.recmesh 2>&1 || true",
        "reconstructPar -allRegions -latestTime > log.rec 2>&1",
        "postProcess -func writeCellCentres -region air -latestTime > log.ccAir 2>&1",
        "postProcess -func writeCellCentres -region adapter_pcb -latestTime > log.ccAd 2>&1",
        "postProcess -func writeCellCentres -region k26_sink -latestTime > log.ccK26 2>&1",
    ]
    if cfg.with_heatsinks:
        for cspec in COMPONENTS:
            if cspec.hs_size_mm is not None:
                short = cspec.name.split("_")[0]
                setup_cmds.append(f"postProcess -func writeCellCentres -region hs_{short} -latestTime > log.cc_{short} 2>&1")

    post_dict = foam_file("dictionary", "postDict", "system") + "\nfunctions\n{\n"
    for op in meta["open_patches"]:
        post_dict += f"""
phi_{op}
{{
    type surfaceFieldValue; libs ("libfieldFunctionObjects.so"); region air;
    writeControl timeStep; writeInterval 1; writeFields false; log true;
    regionType patch; name {op}; operation sum; fields (phi);
}}
p_{op}
{{
    type surfaceFieldValue; libs ("libfieldFunctionObjects.so"); region air;
    writeControl timeStep; writeInterval 1; writeFields false; log true;
    regionType patch; name {op}; operation areaAverage; fields (p_rgh);
}}
"""
    post_dict += "}\n"
    (case_dir / "system" / "postDict").write_text(post_dict)
    setup_cmds.append("postProcess -dict system/postDict -region air -latestTime -fields '(phi p_rgh)' > log.post 2>&1 || true")
    if cfg.keep_vtk:
        setup_cmds.append("foamToVTK -allRegions -latestTime > log.vtk 2>&1")

    (case_dir / "run_par.sh").write_text(
        "#!/usr/bin/env bash\nexport LD_PRELOAD=\"${FOAM_LIBBIN:-/home/varuna/micromamba/envs/cfd/lib}/mpich-3.3/libPstream.so\"\nexec \"$@\"\n",
        newline="\n",
    )
    script_header = (
        "#!/usr/bin/env bash\nset -e\nexport FOAM_MPI=mpich-3.3\n"
        "export LD_LIBRARY_PATH=\"${FOAM_LIBBIN:-/home/varuna/micromamba/envs/cfd/lib}/mpich-3.3:${FOAM_LIBBIN:-/home/varuna/micromamba/envs/cfd/lib}:${LD_LIBRARY_PATH:-}\"\n"
    )
    (case_dir / "run_all.sh").write_text(script_header + "\n".join(setup_cmds) + "\n", newline="\n")
    run_cmd("/home/varuna/.local/bin/micromamba run -n cfd bash run_all.sh", cwd=case_dir)

    t_dir = case_dir / str(n_iter)
    if not t_dir.exists():
        num_dirs = sorted([int(d.name) for d in case_dir.iterdir() if d.is_dir() and d.name.isdigit()])
        t_dir = case_dir / str(num_dirs[-1])

    T_air = read_foam_scalar_field(t_dir / "air" / "T") - 273.15
    U_air = read_foam_vector_field(t_dir / "air" / "U")
    cc_air = parse_cell_centers(t_dir, "air")

    T_ad = read_foam_scalar_field(t_dir / "adapter_pcb" / "T") - 273.15
    cc_ad = parse_cell_centers(t_dir, "adapter_pcb")

    T_k26 = read_foam_scalar_field(t_dir / "k26_sink" / "T") - 273.15
    cc_k26 = parse_cell_centers(t_dir, "k26_sink")

    hs_temps: Dict[str, Tuple[float, float]] = {}
    if cfg.with_heatsinks:
        for cspec in COMPONENTS:
            if cspec.hs_size_mm is not None:
                short = cspec.name.split("_")[0]
                t_hs = read_foam_scalar_field(t_dir / f"hs_{short}" / "T") - 273.15
                cc_hs = parse_cell_centers(t_dir, f"hs_{short}")
                zmin = float(np.min(cc_hs[:, 2]))
                base_mask = cc_hs[:, 2] <= zmin + 1.2e-3
                hs_temps[cspec.name] = (float(np.mean(t_hs[base_mask])), float(np.mean(t_hs)))

    comp_results = {}
    hottest_name = ""
    hottest_tj = -999.0
    for cspec in COMPONENTS:
        b = meta["ic_boxes"][cspec.name]
        mask = (
            (cc_ad[:, 0] >= b[0] - 1e-6) & (cc_ad[:, 0] <= b[1] + 1e-6) &
            (cc_ad[:, 1] >= b[2] - 1e-6) & (cc_ad[:, 1] <= b[3] + 1e-6)
        )
        t_board = float(np.mean(T_ad[mask])) if np.any(mask) else float(np.max(T_ad))
        pw = cspec.power_w + (0.15 if cspec.name == "U1001_LMR33630" else 0.0)
        if cfg.with_heatsinks and cspec.name in hs_temps:
            t_hs_base, t_hs_mean = hs_temps[cspec.name]
            r_top = cspec.theta_jc_top + cspec.r_tim
            # Two-path parallel junction temperature between board below & heatsink above
            t_j = (t_board / cspec.theta_jb + t_hs_base / r_top + pw) / (1.0 / cspec.theta_jb + 1.0 / r_top)
            q_hs_w = round((t_j - t_hs_base) / r_top, 3)
        else:
            t_hs_base, t_hs_mean, q_hs_w = None, None, 0.0
            t_j = t_board + pw * cspec.theta_jb
        entry = {
            "T_board_C": round(t_board, 2),
            "T_j_C": round(t_j, 2),
            "margin_C": round(cspec.tj_max_c - t_j, 2),
        }
        if t_hs_base is not None:
            entry["T_hs_base_C"] = round(t_hs_base, 2)
            entry["T_hs_mean_C"] = round(t_hs_mean, 2)
            entry["Q_to_hs_W"] = q_hs_w
        comp_results[cspec.name] = entry
        if t_j > hottest_tj:
            hottest_tj = t_j
            hottest_name = cspec.name

    sb = meta["som_box"]
    som_mask = (
        (cc_k26[:, 0] >= sb[0]) & (cc_k26[:, 0] <= sb[1]) &
        (cc_k26[:, 1] >= sb[2]) & (cc_k26[:, 1] <= sb[3]) &
        (cc_k26[:, 2] <= sb[5] + 1e-5)
    )
    t_k26_sink_c = float(np.mean(T_k26[som_mask])) if np.any(som_mask) else float(np.max(T_k26))
    t_k26_j_c = t_k26_sink_c + K26_SOM_W * K26_R_JC

    t_amb_k = cfg.ambient_c + 273.15
    rho_amb = 101325.0 / (287.058 * t_amb_k)
    log_post = (case_dir / "log.post").read_text() if (case_dir / "log.post").exists() else ""
    patch_flows = {}
    for op in meta["open_patches"]:
        m_phi = re.findall(rf"sum\({re.escape(op)}\)\s+of\s+phi\s*=\s*([0-9.eE+-]+)", log_post)
        vol_m3_s = (float(m_phi[-1]) / rho_amb) if m_phi else 0.0
        m_p = re.findall(rf"areaAverage\({re.escape(op)}\)\s+of\s+p_rgh\s*=\s*([0-9.eE+-]+)", log_post)
        p_pa = (float(m_p[-1]) - 101325.0) if m_p else 0.0
        patch_flows[op] = {
            "vol_m3_s": round(vol_m3_s, 6),
            "cfm": round(vol_m3_s * 2118.88, 2),
            "dp_Pa": round(p_pa, 2),
        }

    # Save XZ slice through fan axis (Y ~ 14 mm), YZ slice through adapter front strip (X ~ -40 mm),
    # XY slice at Z ~ 8 mm, and full adapter PCB top surface
    out_slices_dir.mkdir(parents=True, exist_ok=True)
    y_fan_mask = np.abs(cc_air[:, 1] - 14.0e-3) < 3.5e-3
    x_fan_mask = np.abs(cc_air[:, 0] - (-40.0e-3)) < 3.5e-3
    z_mid_mask = np.abs(cc_air[:, 2] - 11.0e-3) < 2.5e-3
    np.savez_compressed(
        out_slices_dir / f"{cfg.name}.npz",
        xz_x=cc_air[y_fan_mask, 0] * 1e3, xz_z=cc_air[y_fan_mask, 2] * 1e3,
        xz_T=T_air[y_fan_mask], xz_U=U_air[y_fan_mask],
        yz_y=cc_air[x_fan_mask, 1] * 1e3, yz_z=cc_air[x_fan_mask, 2] * 1e3,
        yz_T=T_air[x_fan_mask], yz_U=U_air[x_fan_mask],
        xy_x=cc_air[z_mid_mask, 0] * 1e3, xy_y=cc_air[z_mid_mask, 1] * 1e3,
        xy_T=T_air[z_mid_mask], xy_U=U_air[z_mid_mask],
        ad_x=cc_ad[:, 0] * 1e3, ad_y=cc_ad[:, 1] * 1e3, ad_T=T_ad,
    )

    log_sol = (case_dir / "log.solver").read_text()
    m_res = re.findall(r"Solving for h, Initial residual = ([0-9.eE+-]+)", log_sol)
    p_air = read_foam_scalar_field(t_dir / "air" / "p_rgh") - 101325.0

    # Interpolate theoretical fan static pressure at actual flow rate on FAN_50_PQ
    q_fan = max(0.0, -patch_flows["adapter_opening"]["vol_m3_s"])
    pq_q = [pt[0] for pt in FAN_50_PQ]
    pq_dp = [pt[1] for pt in FAN_50_PQ]
    fan_curve_dp = float(np.interp(q_fan, pq_q, pq_dp))

    return {
        "name": cfg.name,
        "ambient_c": cfg.ambient_c,
        "mesh_level": cfg.mesh_level,
        "with_heatsinks": cfg.with_heatsinks,
        "filter_clog_factor": cfg.filter_clog_factor,
        "wide_grille": cfg.wide_grille,
        "decouple_hs": cfg.decouple_hs,
        "expand_exhaust": cfg.expand_exhaust,
        "cells_air": int(len(T_air)),
        "cells_solid": int(len(T_ad) + len(T_k26)),
        "T_air_mean_C": round(float(np.mean(T_air)), 2),
        "T_air_max_C": round(float(np.max(T_air)), 2),
        "U_air_max_mps": round(float(np.max(np.linalg.norm(U_air, axis=1))), 2),
        "p_cav_mean_Pa": round(float(np.mean(p_air)), 2),
        "fan50_flow_cfm": round(q_fan * 2118.88, 2),
        "fan50_curve_dp_Pa": round(fan_curve_dp, 2),
        "K26_sink_C": round(t_k26_sink_c, 2),
        "K26_Tj_C": round(t_k26_j_c, 2),
        "K26_margin_C": round(K26_TJ_MAX - t_k26_j_c, 2),
        "hottest_ic": hottest_name,
        "hottest_Tj_C": round(hottest_tj, 2),
        "patch_flows": patch_flows,
        "components": comp_results,
        "final_h_res": float(m_res[-1]) if m_res else -1.0,
        "elapsed_s": round(time.time() - t0, 1),
    }


def build_suite() -> List[BuiltCaseConfig]:
    return [
        BuiltCaseConfig("v2_built_hs_clean_25C", ambient_c=25.0, with_heatsinks=True, filter_clog_factor=1.0),
        BuiltCaseConfig("v2_built_hs_clean_45C", ambient_c=45.0, with_heatsinks=True, filter_clog_factor=1.0),
        BuiltCaseConfig("v2_built_hs_clean_70C", ambient_c=70.0, with_heatsinks=True, filter_clog_factor=1.0, keep_vtk=True),
        BuiltCaseConfig("v2_built_hs_clogged_45C", ambient_c=45.0, with_heatsinks=True, filter_clog_factor=2.0),
        BuiltCaseConfig("v2_built_hs_clogged_70C", ambient_c=70.0, with_heatsinks=True, filter_clog_factor=2.0),
        BuiltCaseConfig("v2_built_nohs_clean_70C", ambient_c=70.0, with_heatsinks=False, filter_clog_factor=1.0, keep_vtk=True),
        BuiltCaseConfig("v2_built_widegrille_hs_70C", ambient_c=70.0, with_heatsinks=True, filter_clog_factor=1.0, wide_grille=True),
        BuiltCaseConfig("v2_built_decoupled_hs_70C", ambient_c=70.0, with_heatsinks=True, filter_clog_factor=1.0, decouple_hs=True),
        BuiltCaseConfig("v2_built_proposed_70C", ambient_c=70.0, with_heatsinks=True, filter_clog_factor=1.0, wide_grille=True, decouple_hs=True, expand_exhaust=True, keep_vtk=True),
        BuiltCaseConfig("v2_built_hs_clean_fine_70C", ambient_c=70.0, mesh_level="fine", with_heatsinks=True, filter_clog_factor=1.0, keep_vtk=True),
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scratch", default="/home/varuna/cfd_scratch_v2")
    parser.add_argument("--nprocs", type=int, default=16)
    parser.add_argument("--only", help="Run single case by name")
    parser.add_argument("--keep-scratch", action="store_true")
    args = parser.parse_args()

    out_dir = Path(__file__).resolve().parent
    slices_dir = out_dir / "slices"
    res_file = out_dir / "results_built_v2.json"
    scratch = Path(args.scratch)
    scratch.mkdir(parents=True, exist_ok=True)

    existing = {}
    if res_file.exists():
        for row in json.loads(res_file.read_text()):
            existing[row["name"]] = row

    suite = build_suite()
    if args.only:
        suite = [c for c in suite if c.name == args.only]
        if not suite:
            raise SystemExit(f"Case {args.only} not found")

    for cfg in suite:
        print(f"=== Running {cfg.name} (Ta={cfg.ambient_c}C, hs={cfg.with_heatsinks}, clog={cfg.filter_clog_factor}, mesh={cfg.mesh_level}) ===", flush=True)
        res = run_case(cfg, scratch, slices_dir, nprocs=args.nprocs)
        existing[cfg.name] = res
        res_file.write_text(json.dumps(list(existing.values()), indent=2))
        print(
            f"  Done {cfg.name}: air={res['cells_air']}, Tair_max={res['T_air_max_C']}C, "
            f"fan={res['fan50_flow_cfm']} CFM @ {res['fan50_curve_dp_Pa']} Pa, "
            f"K26={res['K26_Tj_C']}C, Y401={res['components']['Y401_Si549']['T_j_C']}C, "
            f"U401={res['components']['U401_ADCLK948']['T_j_C']}C, "
            f"U501={res['components']['U501_AD9484']['T_j_C']}C, "
            f"LMR={res['components']['U1001_LMR33630']['T_j_C']}C, t={res['elapsed_s']}s",
            flush=True,
        )
        if not args.keep_scratch and not cfg.keep_vtk and (scratch / cfg.name).exists():
            shutil.rmtree(scratch / cfg.name)


if __name__ == "__main__":
    main()
