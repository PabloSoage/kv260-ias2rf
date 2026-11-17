"""
The placed footprints of the board, read from the .kicad_pcb as text (never through pcbnew).

parts(pcb_path) -> list of Part: reference, value, footprint name, side, position, rotation,
sheet, and the outline (courtyard, else fabrication layer, else pads) as a polygon in board
coordinates. outline(pcb_path) -> the Edge.Cuts segments and arcs.
"""
import math
import re


class Part:
    def __init__(self, **kw):
        self.__dict__.update(kw)

    def __repr__(self):
        return f"{self.ref} {self.value} {self.side} ({self.x:.1f}, {self.y:.1f})"


def _blocks(text, head):
    """Top-level blocks that start with `\\n\\t(head`."""
    key = "\n\t(" + head
    i = text.find(key)
    while i >= 0:
        s = i + 2
        depth, j, n = 0, s, len(text)
        in_str = False
        while j < n:
            ch = text[j]
            if in_str:
                if ch == "\\":
                    j += 1
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        yield text[s:j + 1]
        i = text.find(key, j)


def _prop(b, name):
    m = re.search(r'\(property "' + re.escape(name) + r'" "((?:[^"\\]|\\.)*)"', b)
    return m.group(1) if m else ""


def _local_pts(b, layers):
    """Points of the graphic items on `layers`, footprint-local."""
    pts = []
    for m in re.finditer(r'\((fp_line|fp_rect|fp_poly|fp_circle|fp_arc)\b(.*?)\(layer "([^"]+)"\)', b, re.S):
        if m.group(3) not in layers:
            continue
        body = m.group(2)
        xy = [(float(a), float(c)) for a, c in re.findall(r'\((?:start|end|mid|center|xy) ([-\d.]+) ([-\d.]+)\)', body)]
        if m.group(1) == "fp_circle" and len(xy) == 2:
            (cx, cy), (ex, ey) = xy
            r = math.hypot(ex - cx, ey - cy)
            xy = [(cx - r, cy - r), (cx + r, cy + r)]
        pts += xy
    return pts


def _pad_pts(b):
    pts = []
    for m in re.finditer(r'\(pad "[^"]*" \w+ \w+\s*\(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)\s*\(size ([-\d.]+) ([-\d.]+)\)', b):
        x, y, w, h = float(m.group(1)), float(m.group(2)), float(m.group(4)), float(m.group(5))
        pts += [(x - w / 2, y - h / 2), (x + w / 2, y + h / 2)]
    return pts


def parts(pcb_path):
    text = open(pcb_path, encoding="utf-8").read()
    out = []
    for b in _blocks(text, "footprint "):
        name = re.match(r'\(footprint "([^"]+)"', b).group(1)
        side = "bottom" if re.search(r'^\t\t\(layer "B\.Cu"\)', b, re.M) else "top"
        at = re.search(r'^\t\t\(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)', b, re.M)
        x, y, rot = float(at.group(1)), float(at.group(2)), float(at.group(3) or 0)
        ref = _prop(b, "Reference")
        sheet = re.search(r'\(sheetname "([^"]*)"\)', b)
        f = "B" if side == "bottom" else "F"
        pts = (_local_pts(b, {f + ".CrtYd"}) or _local_pts(b, {f + ".Fab"}) or _pad_pts(b))
        # KiCad: board = R(-rot) * local + at (y down, rotation counter-clockwise on screen)
        a = math.radians(rot)
        ca, sa = math.cos(a), math.sin(a)
        if pts:
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            corners = [(min(xs), min(ys)), (max(xs), min(ys)), (max(xs), max(ys)), (min(xs), max(ys))]
        else:
            corners = [(-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)]
        poly = [(x + px * ca + py * sa, y - px * sa + py * ca) for px, py in corners]
        out.append(Part(ref=ref, value=_prop(b, "Value"), footprint=name.split(":")[-1], side=side,
                        x=x, y=y, rot=rot, sheet=(sheet.group(1).strip("/") if sheet else "") or "root",
                        poly=poly, dnp="(attr" in b and " dnp" in re.search(r'\(attr[^)]*\)', b).group(0)
                        if re.search(r'\(attr[^)]*\)', b) else False))
    return out


def outline(pcb_path):
    text = open(pcb_path, encoding="utf-8").read()
    segs = []
    for b in list(_blocks(text, "gr_poly")):
        if '(layer "Edge.Cuts")' in b:
            xy = [(float(a), float(c)) for a, c in re.findall(r'\(xy ([-\d.]+) ([-\d.]+)\)', b)]
            segs.append(xy + xy[:1])
    for b in list(_blocks(text, "gr_line")) + list(_blocks(text, "gr_arc")) + list(_blocks(text, "gr_rect")):
        if '(layer "Edge.Cuts")' not in b:
            continue
        xy = [(float(a), float(c)) for a, c in re.findall(r'\((?:start|mid|end) ([-\d.]+) ([-\d.]+)\)', b)]
        if b.startswith("(gr_rect"):
            (x0, y0), (x1, y1) = xy
            segs += [[(x0, y0), (x1, y0)], [(x1, y0), (x1, y1)], [(x1, y1), (x0, y1)], [(x0, y1), (x0, y0)]]
        elif b.startswith("(gr_arc"):
            (sx, sy), (mx, my), (ex, ey) = xy
            segs.append(_arc_pts((sx, sy), (mx, my), (ex, ey)))
        else:
            segs.append(xy)
    return segs


def _arc_pts(p1, p2, p3, n=24):
    (x1, y1), (x2, y2), (x3, y3) = p1, p2, p3
    d = 2 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
    if abs(d) < 1e-9:
        return [p1, p3]
    ux = ((x1 ** 2 + y1 ** 2) * (y2 - y3) + (x2 ** 2 + y2 ** 2) * (y3 - y1) + (x3 ** 2 + y3 ** 2) * (y1 - y2)) / d
    uy = ((x1 ** 2 + y1 ** 2) * (x3 - x2) + (x2 ** 2 + y2 ** 2) * (x1 - x3) + (x3 ** 2 + y3 ** 2) * (x2 - x1)) / d
    r = math.hypot(x1 - ux, y1 - uy)
    a1, a2, a3 = (math.atan2(p[1] - uy, p[0] - ux) for p in (p1, p2, p3))

    def ccw(a, b):
        return (b - a) % (2 * math.pi)
    span = ccw(a1, a3)
    if ccw(a1, a2) > span:                      # the mid point is on the other way round
        span -= 2 * math.pi
    return [(ux + r * math.cos(a1 + span * k / n), uy + r * math.sin(a1 + span * k / n)) for k in range(n + 1)]
