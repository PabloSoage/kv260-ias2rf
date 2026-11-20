#!/usr/bin/env python3
"""
The PSU board's enclosure (docs/PSU_ENCLOSURE.md): a printed tray and lid with the main case's honeycomb (10 mm cells,
1.6 mm walls).

  - Tray: M3 heat-set inserts in four stand-offs under the board's holes, a honeycomb-ribbed floor, the three
    connectors' openings in the left wall with a cable-tie shelf below them, two rows of honeycomb vents in each long
    wall (low intake, high exhaust), and four ears with M5 slots.
  - Lid: honeycomb ribs under a closed top (nothing drips in from above), and four posts that clamp the board. One
    M3 x 25 socket screw per hole runs through lid, post and board into the tray's insert, so the same four screws
    hold the board and close the case.

Frame: mm, X = KiCad x, Y = -KiCad y, Z = 0 on the board's underside (the board is 0..1.6). That is the frame of
site/assets/psu_board.glb once Blender has turned its Y-up into Z-up, so the board drops straight in.

Usage:  python _work/psu/psu_case.py            # writes mech/psu_case_{tray,lid}.stl, their STEP in
                                                # _work/psu/cache/ and psu_case_geom.json there
Imported by psu_case_fea.py for the same solids.
"""
import json
import math
import os

try:
    import gmsh         # not in Blender's Python: psu_case_render.py only needs the dimensions
except ImportError:
    gmsh = None

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE = os.path.join(ROOT, "_work", "psu", "cache")
MECH = os.path.join(ROOT, "mech")

# ---- the board (site/assets/psu.json): outline, holes, connector bodies (KiCad mm) ---------------------------------
BX0, BX1, BY0, BY1, BT = 100.0, 210.0, 100.0, 170.0, 1.6
HOLES = {"H1": (103.5, 103.5), "H2": (206.5, 157.0), "H3": (141.0, 166.5), "H4": (103.5, 135.0)}
# opening per connector: KiCad y range and Z range of the mating face, from the 3-D bodies plus 0.8 mm all round
OPENINGS = {"J1": (107.85, 121.15, -0.5, 8.0), "J2": (142.25, 151.71, -0.5, 10.9), "J3": (157.25, 166.71, -0.5, 10.9)}
TALLEST = 11.64           # C6, C17, C18 (10 mm electrolytics) above the board's underside

# ---- the case ------------------------------------------------------------------------------------------------------
WALL = 2.5
IX0, IX1, IY0, IY1 = 99.0, 211.0, 97.5, 172.5      # cavity: 1 mm past J1's overhang, 2.5 mm air gap on the long sides
OX0, OX1, OY0, OY1 = IX0 - WALL, IX1 + WALL, IY0 - WALL, IY1 + WALL
Z_BOT, Z_FLOOR = -8.5, -6.0                        # floor 2.5 mm; the board stands 6 mm above it
Z_CEIL, Z_TOP = 19.0, 21.5                         # lid 2.5 mm; its ribs run 14.0..19.0, 2.4 mm over the tallest part
R_OUT, R_IN = 4.0, 1.5
HEX_S, HEX_T = 10.0, 1.6                           # the main case's honeycomb: cell flat to flat, wall
FLOOR_RIB = 2.0
LID_RIB = 5.0                                      # deep enough that 300 N on the lid stays clear of C6
LIP_T, LIP_H, LIP_GAP = 1.2, 1.2, 0.25
POST_R, INSERT_R, INSERT_D = 3.5, 2.0, 7.0         # M3 x 5.7 heat-set insert in a 4.0 mm hole 7 deep (the screw's tip)
BASE_R, BASE_H = 6.0, 4.0                          # conical foot of each stand-off and rest on the floor ribs
# rests under the board where its underside is bare (no through-hole pad within 3 mm): it lies on them, so a shock
# down no longer bends its far corners round the four holes
RESTS = [(205.0, 104.0), (160.0, 104.0), (205.0, 130.0), (160.0, 135.0), (180.0, 166.0), (125.0, 128.0)]
REST_R = 3.0
SCREW_R, CBORE_R, CBORE_D = 1.7, 3.25, 3.0         # M3 clearance; DIN 912 M3 x 25, head 5.5 mm in a 6.5 mm counterbore
VENT_X = [118.0 + 10.0 * i for i in range(8)]     # vent columns (pitch = the honeycomb's 10 mm)
VENT_Z = (-1.0, 12.8)                              # intake and exhaust rows (cell centres): 13.8 mm of chimney
EARS_X = (104.0, 206.0)
EAR_W, EAR_L, EAR_T = 14.0, 12.0, 5.0
SLOT_W, SLOT_L = 5.5, 8.0                          # M5
SHELF_X0 = OX0 - 12.0
SHELF_KY = (101.0, 171.0)
TIE_SLOTS_KY = (105.0, 119.0, 138.0, 152.5, 167.0)  # cable ties either side of J1 (112), J2 (145), J3 (160)
TIE_W, TIE_L = 4.5, 2.2


def Y(ky):
    return -ky


def hex_cell_area():
    a = HEX_S - HEX_T
    return math.sqrt(3) / 2 * a * a


class Builder:
    def __init__(self):
        self.occ = gmsh.model.occ

    def box_k(self, x0, x1, ky0, ky1, z0, z1):
        return (3, self.occ.addBox(x0, Y(ky1), z0, x1 - x0, ky1 - ky0, z1 - z0))

    def rbox_k(self, x0, x1, ky0, ky1, z0, z1, r):
        s = self.occ.addRectangle(x0, Y(ky1), z0, x1 - x0, ky1 - ky0, roundedRadius=r)
        out = self.occ.extrude([(2, s)], 0, 0, z1 - z0)
        return [d for d in out if d[0] == 3][0]

    def cyl_k(self, x, ky, r, z0, z1):
        return (3, self.occ.addCylinder(x, Y(ky), z0, 0, 0, z1 - z0, r))

    def prism(self, pts, axis, length):
        """A closed polygon (3-D points) extruded along axis (dx, dy, dz) * length."""
        occ = self.occ
        p = [occ.addPoint(*q) for q in pts]
        ln = [occ.addLine(p[i], p[(i + 1) % len(p)]) for i in range(len(p))]
        s = occ.addPlaneSurface([occ.addCurveLoop(ln)])
        out = occ.extrude([(2, s)], axis[0] * length, axis[1] * length, axis[2] * length)
        return [d for d in out if d[0] == 3][0]

    def hex_z(self, cx, ky, z0, z1, flat):
        """Hexagonal prism, vertical axis, flats facing +-Y (cells of a horizontal honeycomb)."""
        r = flat / math.sqrt(3)
        pts = [(cx + r * math.cos(math.radians(60 * k)), Y(ky) + r * math.sin(math.radians(60 * k)), z0)
               for k in range(6)]
        return self.prism(pts, (0, 0, 1), z1 - z0)

    def hex_y(self, cx, ky0, cz, ky1, flat):
        """Hexagonal prism through a long wall (axis along Y), vertex up: the vents' cells."""
        r = flat / math.sqrt(3)
        pts = [(cx + r * math.cos(math.radians(90 + 60 * k)), Y(ky0), cz + r * math.sin(math.radians(90 + 60 * k)))
               for k in range(6)]
        return self.prism(pts, (0, -1, 0), ky1 - ky0)

    def honeycomb(self, x0, x1, ky0, ky1, z0, z1, keep_out=()):
        """A slab of honeycomb ribs: the slab minus whole and partial cells (pitch HEX_S, wall HEX_T). Cells whose
        centre lies within a keep-out circle (x, ky, r) are left solid."""
        slab = self.box_k(x0, x1, ky0, ky1, z0, z1)
        dx, dy = HEX_S * math.sqrt(3) / 2, HEX_S       # columns of flats-along-Y cells
        cells = []
        cx0, cy0 = (x0 + x1) / 2, (ky0 + ky1) / 2
        nx, ny = int((x1 - x0) / dx / 2) + 2, int((ky1 - ky0) / dy / 2) + 2
        for i in range(-nx, nx + 1):
            for j in range(-ny, ny + 1):
                cx = cx0 + i * dx
                cy = cy0 + j * dy + (dy / 2 if i % 2 else 0)
                if not (x0 - dx < cx < x1 + dx and ky0 - dy < cy < ky1 + dy):
                    continue
                if any(math.hypot(cx - kx, cy - kky) < r for kx, kky, r in keep_out):
                    continue
                cells.append(self.hex_z(cx, cy, z0 - 0.1, z1 + 0.1, HEX_S - HEX_T))
        out, _ = self.occ.cut([slab], cells)
        return out

    # ---- parts -----------------------------------------------------------------------------------------------------
    def tray(self):
        occ = self.occ
        outer = self.rbox_k(OX0, OX1, OY0, OY1, Z_BOT, Z_CEIL, R_OUT)
        cavity = self.rbox_k(IX0, IX1, IY0, IY1, Z_FLOOR, Z_CEIL + 1, R_IN)
        shell, _ = occ.cut([outer], [cavity])
        keep = [(x, ky, POST_R + 2.0) for x, ky in list(HOLES.values()) + RESTS]
        floor = self.honeycomb(IX0, IX1, IY0, IY1, Z_FLOOR - 0.2, Z_FLOOR + FLOOR_RIB, keep)
        posts = [self.cyl_k(x, ky, POST_R, Z_FLOOR - 0.2, 0.0) for x, ky in HOLES.values()]
        posts += [self.cyl_k(x, ky, REST_R, Z_FLOOR - 0.2, 0.0) for x, ky in RESTS]
        for x, ky in list(HOLES.values()) + RESTS:
            posts.append((3, self.occ.addCone(x, Y(ky), Z_FLOOR - 0.2, 0, 0, BASE_H + 0.2, BASE_R, POST_R - 0.5)))
        ears = []
        for x in EARS_X:
            ears.append(self.rbox_k(x - EAR_W / 2, x + EAR_W / 2, OY0 - EAR_L, OY0 + 1.0, Z_BOT, Z_BOT + EAR_T, 2.0))
            ears.append(self.rbox_k(x - EAR_W / 2, x + EAR_W / 2, OY1 - 1.0, OY1 + EAR_L, Z_BOT, Z_BOT + EAR_T, 2.0))
        shelf = self.rbox_k(SHELF_X0, OX0 + 1.0, SHELF_KY[0], SHELF_KY[1], Z_BOT, Z_BOT + WALL, 2.0)
        body, _ = occ.fuse(shell, floor + posts + ears + [shelf])
        tools = []
        for x, ky in HOLES.values():
            tools.append(self.cyl_k(x, ky, INSERT_R, -INSERT_D, 0.5))
        for ky0, ky1, z0, z1 in OPENINGS.values():
            tools.append(self.box_k(OX0 - 0.5, IX0 + 0.5, ky0, ky1, z0, z1))
        for x in VENT_X:
            for z in VENT_Z:
                tools.append(self.hex_y(x, OY0 - 0.1, z, IY0 + 0.6, HEX_S - HEX_T))
                tools.append(self.hex_y(x, IY1 - 0.6, z, OY1 + 0.1, HEX_S - HEX_T))
        for x in EARS_X:
            for c in (OY0 - EAR_L / 2 - 0.5, OY1 + EAR_L / 2 + 0.5):
                tools.append(self.rbox_k(x - SLOT_W / 2, x + SLOT_W / 2, c - SLOT_L / 2, c + SLOT_L / 2,
                                         Z_BOT - 1, Z_BOT + EAR_T + 1, SLOT_W / 2 - 0.01))
        for ky in TIE_SLOTS_KY:
            tools.append(self.rbox_k(SHELF_X0 + 3.0, SHELF_X0 + 3.0 + TIE_W, ky - TIE_L / 2, ky + TIE_L / 2,
                                     Z_BOT - 1, Z_BOT + WALL + 1, 0.8))
        out, _ = occ.cut(body, tools)
        return out

    def lid(self):
        occ = self.occ
        plate = self.rbox_k(OX0, OX1, OY0, OY1, Z_CEIL, Z_TOP, R_OUT)
        lx0, lx1, ly0, ly1 = IX0 + LIP_GAP, IX1 - LIP_GAP, IY0 + LIP_GAP, IY1 - LIP_GAP
        lip_o = self.rbox_k(lx0, lx1, ly0, ly1, Z_CEIL - LIP_H, Z_CEIL + 0.1, R_IN)
        lip_i = self.rbox_k(lx0 + LIP_T, lx1 - LIP_T, ly0 + LIP_T, ly1 - LIP_T, Z_CEIL - LIP_H - 1, Z_CEIL + 1, 0.5)
        lip, _ = occ.cut([lip_o], [lip_i])
        keep = [(x, ky, POST_R + 1.5) for x, ky in HOLES.values()]
        ribs = self.honeycomb(lx0 + LIP_T - 0.1, lx1 - LIP_T + 0.1, ly0 + LIP_T - 0.1, ly1 - LIP_T + 0.1,
                              Z_CEIL - LID_RIB, Z_CEIL + 0.2, keep)
        posts = [self.cyl_k(x, ky, POST_R, BT, Z_CEIL + 0.2) for x, ky in HOLES.values()]
        body, _ = occ.fuse([plate], lip + ribs + posts)
        tools = []
        for x, ky in HOLES.values():
            tools.append(self.cyl_k(x, ky, SCREW_R, BT - 1, Z_TOP + 1))
            tools.append(self.cyl_k(x, ky, CBORE_R, Z_TOP - CBORE_D, Z_TOP + 1))
        out, _ = occ.cut(body, tools)
        return out

    def board(self):
        b = self.box_k(BX0, BX1, BY0, BY1, 0.0, BT)
        holes = [self.cyl_k(x, ky, 1.6, -1, BT + 1) for x, ky in HOLES.values()]
        out, _ = self.occ.cut([b], holes)
        return out


def check_posts():
    """The lid's posts press on the board around each hole: nothing taller than the board may sit under them."""
    d = json.load(open(os.path.join(ROOT, "site", "assets", "psu.json"), encoding="utf-8"))
    bad = []
    for c in d["components"]:
        if c["ref"].startswith("H"):
            continue
        x0, y0, x1, y1 = c["bbox_board_mm"]
        for h, (x, ky) in HOLES.items():
            dx = max(x0 - x, 0, x - x1)
            dy = max(y0 - ky, 0, ky - y1)
            if math.hypot(dx, dy) < POST_R + 0.3:
                bad.append((h, c["ref"], round(math.hypot(dx, dy), 2)))
    return bad


def volume_area(dimtags):
    occ = gmsh.model.occ
    vol = sum(occ.getMass(3, t) for _, t in dimtags)
    surf = gmsh.model.getBoundary(dimtags, combined=False, oriented=False)
    area = sum(occ.getMass(2, abs(t)) for _, t in surf)
    return vol, area


def main():
    os.makedirs(CACHE, exist_ok=True)
    bad = check_posts()
    print("parts under the lid's posts:", bad or "none")
    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0)
    geom = {}
    for name in ("tray", "lid"):
        gmsh.model.add(name)
        b = Builder()
        dt = getattr(b, name)()
        b.occ.synchronize()
        vol, area = volume_area(dt)
        geom[name] = dict(volume_mm3=vol, surface_mm2=area, solids=len(dt))
        gmsh.write(os.path.join(CACHE, f"psu_case_{name}.step"))
        gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 20)
        gmsh.option.setNumber("Mesh.MeshSizeMax", 3.0)
        gmsh.option.setNumber("Mesh.MeshSizeMin", 0.15)
        gmsh.option.setNumber("Mesh.Binary", 1)
        gmsh.model.mesh.generate(2)
        gmsh.write(os.path.join(MECH, f"psu_case_{name}.stl"))
        print(name, f"{len(dt)} solid(s), {vol / 1000:.1f} cm3, {area / 100:.0f} cm2", flush=True)
        gmsh.model.remove()
    gmsh.finalize()
    cell = hex_cell_area()
    geom.update(
        outer_mm=[OX1 - OX0, OY1 - OY0, Z_TOP - Z_BOT],
        cavity_mm=[IX1 - IX0, IY1 - IY0, Z_CEIL - Z_FLOOR],
        vent_cell_mm2=cell, vent_cells_per_row=len(VENT_X) * 2,
        vent_area_low_mm2=cell * len(VENT_X) * 2, vent_area_high_mm2=cell * len(VENT_X) * 2,
        vent_rows_z=list(VENT_Z), chimney_mm=VENT_Z[1] - VENT_Z[0],
        board_gap_long_mm=BY0 - IY0, clearance_over_tallest_mm=Z_CEIL - LID_RIB - TALLEST,
        holes=HOLES, ears_x=EARS_X, parts_under_posts=bad,
    )
    json.dump(geom, open(os.path.join(CACHE, "psu_case_geom.json"), "w"), indent=1)
    print(json.dumps({k: geom[k] for k in ("outer_mm", "vent_area_low_mm2", "chimney_mm")}))


if __name__ == "__main__":
    main()
