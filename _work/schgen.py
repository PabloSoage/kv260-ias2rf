#!/usr/bin/env python3
"""
A small writer for KiCad 10 schematic sheets: placed symbols joined by REAL
WIRES, the way a person draws them.

This is not the Rev01 approach. That generated untyped symbols joined by
auto-named labels, which nobody could review and nothing verified
(docs/AUDIT_Rev01.md). Here:

  * every symbol comes from a library with typed pins - the project library
    (datasheet-sourced) or KiCad's own;
  * every connection is a wire whose ends sit exactly on pin endpoints, on
    the 1.27 mm grid, so the sheet reads like a hand drawing;
  * the result is checked by KiCad itself (ERC) and by
    _work/check_sheet.py, which compares the exported netlist against a
    connection list written separately from the drawing.

Coordinates are millimetres, sheet frame (Y down). Symbol rotation follows
KiCad: counter-clockwise as displayed.

Once a generated sheet has been reviewed and accepted, the .kicad_sch becomes
the source and is edited in KiCad from then on; the generator is not re-run
over hand edits.
"""

import math
import re
import uuid

KICAD_SYM = "E:/Program Files/KiCad/10.0/share/kicad/symbols/"
GRID = 1.27
NS = uuid.UUID("5b1c2d6e-7f80-4a91-b2c3-d4e5f6a7b8c9")


def uid(*parts):
    return str(uuid.uuid5(NS, "|".join(str(p) for p in parts)))


def snap(v):
    return round(round(v / GRID) * GRID, 4)


def fmt(v):
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return s if s not in ("-0", "") else "0"


def _block(text, start):
    """Balanced (...) block starting at `start`."""
    depth, i, in_str = 0, start, False
    while i < len(text):
        c = text[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
        i += 1
    raise ValueError("unbalanced")


class LibSymbol:
    def __init__(self, lib_id, path):
        lib, name = lib_id.split(":")
        text = open(path, encoding="utf-8").read()
        m = re.search(r'\n\s*\(symbol "' + re.escape(name) + r'"\s*\n', text)
        if not m:
            raise KeyError(lib_id)
        body = _block(text, text.index("(symbol", m.start()))
        ext = re.search(r'\(extends "([^"]+)"\)', body)
        if ext:
            # A derived symbol (KiCad's "extends") has only properties; its
            # pins and graphics are the parent's. Flatten it the way KiCad
            # embeds it in a schematic: the parent's body under this name,
            # with this symbol's property values.
            parent = ext.group(1)
            flat = LibSymbol(f"{lib}:{parent}", path).body
            flat = flat.replace(f'(symbol "{lib}:{parent}"', f'(symbol "{name}"', 1)
            flat = flat.replace(f'(symbol "{parent}_', f'(symbol "{name}_')
            for key, val in re.findall(r'\(property "([^"]+)" "((?:[^"\\]|\\.)*)"', body):
                flat = re.sub(r'(\(property "' + re.escape(key) + r'" ")(?:[^"\\]|\\.)*"',
                              lambda m, v=val: m.group(1) + v + '"', flat, count=1)
            body = flat
        self.lib_id = lib_id
        self.body = body.replace(f'(symbol "{name}"', f'(symbol "{lib_id}"', 1)
        self.power = "(power" in body[:400]
        # a solder jumper is not a part to buy: the library says so, and the
        # footprint agrees (exclude_from_bom), which DRC checks
        self.in_bom = "(in_bom no)" not in body[:600]
        self.pins = {}     # number -> (x, y, electrical type, name)
        self.unit = {}     # number -> unit (0 = common to every unit)
        for sm in re.finditer(r'\(symbol "' + re.escape(name) + r'_(\d+)_\d+"', body):
            for pm in re.finditer(r'\(pin (\w+) \w+\s*\(at ([-\d.]+) ([-\d.]+)[^)]*\)'
                                  r'.*?\(name "([^"]*)".*?\(number "([^"]*)"',
                                  _block(body, sm.start()), re.S):
                self.pins.setdefault(pm.group(5), (float(pm.group(2)), float(pm.group(3)),
                                                   pm.group(1), pm.group(4)))
                self.unit.setdefault(pm.group(5), int(sm.group(1)))
        self.units = max(self.unit.values(), default=1) or 1


class Part:
    def __init__(self, sheet, sym, ref, value, at, rot, mirror=False, unit=1):
        self.sheet, self.sym, self.ref, self.value = sheet, sym, ref, value
        self.at, self.rot = (snap(at[0]), snap(at[1])), rot % 360
        self.mirror, self.unit = mirror, unit
        assert not (mirror and self.rot), "mirror only supported at rotation 0"
        assert 1 <= unit <= sym.units, f"{ref}: {sym.lib_id} has no unit {unit}"
        # the pins this unit draws: its own, plus any common to every unit
        self.pins = [n for n in sym.pins if sym.unit.get(n, 0) in (0, unit)]

    def pin(self, number):
        number = str(number)
        assert number in self.pins, f"{self.ref}: pin {number} is not in unit {self.unit}"
        x, y = self.sym.pins[number][:2]
        dx, dy = x, -y                                   # library Y is up
        if self.mirror:                                  # KiCad "(mirror y)": left-right
            dx = -dx
        a = math.radians(self.rot)
        rx = dx * math.cos(a) + dy * math.sin(a)
        ry = -dx * math.sin(a) + dy * math.cos(a)
        return (snap(self.at[0] + rx), snap(self.at[1] + ry))


class Sheet:
    def __init__(self, path, file_uuid, title, project, instance_path, paper="A3",
                 generator="", ref_base=400):
        self.path, self.file_uuid, self.title = path, file_uuid, title
        self.generator, self.ref_base = generator, ref_base
        self.project, self.instance_path, self.paper = project, instance_path, paper
        self.libs, self.parts, self.wires = {}, [], []
        self.labels, self.nocon, self.texts = [], [], []
        self.pwr_count = 0
        self.lib_paths = {}

    # ---- symbols ------------------------------------------------------
    def lib(self, nickname, path):
        self.lib_paths[nickname] = path

    def _sym(self, lib_id):
        if lib_id not in self.libs:
            nick = lib_id.split(":")[0]
            path = self.lib_paths.get(nick, KICAD_SYM + nick + ".kicad_sym")
            self.libs[lib_id] = LibSymbol(lib_id, path)
        return self.libs[lib_id]

    def place(self, lib_id, ref, value, at, rot=0, footprint="", fields=None, mirror=False,
              text_at=None, unit=1):
        """text_at=(x, y): put Reference there and Value 2.54 mm below it,
        left-justified, instead of the automatic placement. unit: which unit
        of a multi-unit symbol this placement is (place each unit once)."""
        p = Part(self, self._sym(lib_id), ref, value, at, rot, mirror, unit)
        p.footprint, p.fields = footprint, dict(fields or {})
        p.text_at = (snap(text_at[0]), snap(text_at[1])) if text_at else None
        self.parts.append(p)
        return p

    def power(self, lib_id, value, at, rot=0, hide_value=False, text_at=None):
        """A power symbol. hide_value: for a ground turned sideways beside a
        connector pin, where its name would land on the next row. text_at:
        where the name goes (left-justified), for a symbol turned sideways."""
        self.pwr_count += 1
        n = self.ref_base + self.pwr_count
        p = self.place(lib_id, f"#PWR{n:03d}" if "PWR_FLAG" not in lib_id else f"#FLG{n:03d}",
                       value, at, rot,
                       text_at=(text_at[0], text_at[1] - 2.54) if text_at else None)
        p.hide_value = hide_value
        return p

    # ---- connections --------------------------------------------------
    def wire(self, *pts):
        pts = [(snap(x), snap(y)) for x, y in pts]
        for a, b in zip(pts, pts[1:]):
            if a != b:
                if a[0] != b[0] and a[1] != b[1]:
                    raise ValueError(f"diagonal wire {a} -> {b}")
                self.wires.append((a, b))

    def hlabel(self, name, shape, at, side="right"):
        """Hierarchical label; its text extends towards `side`."""
        self.labels.append(("hierarchical_label", name, shape,
                            (snap(at[0]), snap(at[1])), side))

    def label(self, name, at, side="right"):
        self.labels.append(("label", name, None, (snap(at[0]), snap(at[1])), side))

    def no_connect(self, at):
        self.nocon.append((snap(at[0]), snap(at[1])))

    def text(self, s, at, size=1.27):
        self.texts.append((s, (snap(at[0]), snap(at[1])), size))

    # ---- output -------------------------------------------------------
    def _split_wires(self):
        """Split wires at every node that lies inside another wire, so that
        every connection happens at a wire END, then return the junctions."""
        nodes = set()
        for a, b in self.wires:
            nodes.update((a, b))
        for p in self.parts:
            for n in p.pins:
                nodes.add(p.pin(n))
        for _, _, _, at, _ in self.labels:
            nodes.add(at)
        out = []
        for a, b in self.wires:
            inner = [n for n in nodes if n not in (a, b) and _on_segment(n, a, b)]
            pts = sorted([a, b] + inner, key=lambda q: (q[0] - a[0]) ** 2 + (q[1] - a[1]) ** 2)
            out += list(zip(pts, pts[1:]))
        self.wires = out
        degree = {}
        for a, b in out:
            degree[a] = degree.get(a, 0) + 1
            degree[b] = degree.get(b, 0) + 1
        pinpts = {p.pin(n) for p in self.parts for n in p.pins}
        return sorted(q for q, d in degree.items() if d + (1 if q in pinpts else 0) >= 3)

    def write(self):
        junctions = self._split_wires()
        T = "\t"
        L = ["(kicad_sch", f"{T}(version 20260306)", f'{T}(generator "eeschema")',
             f'{T}(generator_version "10.0")', f'{T}(uuid "{self.file_uuid}")',
             f'{T}(paper "{self.paper}")', f"{T}(title_block", f'{T}{T}(title "{self.title}")',
             f'{T}{T}(rev "03")', f'{T}{T}(company "KV260-IAS2RF")',
             f'{T}{T}(comment 1 "Generated by {self.generator} - review before editing by hand")',
             f"{T})", f"{T}(lib_symbols"]
        for s in self.libs.values():
            L.append(T + T + s.body.replace("\n", "\n" + T))
        L.append(f"{T})")
        for q in junctions:
            L += [f"{T}(junction", f"{T}{T}(at {fmt(q[0])} {fmt(q[1])})", f"{T}{T}(diameter 0)",
                  f"{T}{T}(color 0 0 0 0)", f'{T}{T}(uuid "{uid(self.path, "j", q)}")', f"{T})"]
        for q in self.nocon:
            L += [f"{T}(no_connect", f"{T}{T}(at {fmt(q[0])} {fmt(q[1])})",
                  f'{T}{T}(uuid "{uid(self.path, "nc", q)}")', f"{T})"]
        for a, b in self.wires:
            L += [f"{T}(wire", f"{T}{T}(pts", f"{T}{T}{T}(xy {fmt(a[0])} {fmt(a[1])}) (xy {fmt(b[0])} {fmt(b[1])})",
                  f"{T}{T})", f"{T}{T}(stroke", f"{T}{T}{T}(width 0)", f"{T}{T}{T}(type default)",
                  f"{T}{T})", f'{T}{T}(uuid "{uid(self.path, "w", a, b)}")', f"{T})"]
        for kind, name, shape, at, side in self.labels:
            ang = 0 if side == "right" else 180
            just = "left" if side == "right" else "right"
            L += [f'{T}({kind} "{name}"']
            if shape:
                L += [f"{T}{T}(shape {shape})"]
            L += [f"{T}{T}(at {fmt(at[0])} {fmt(at[1])} {ang})",
                  f"{T}{T}(effects", f"{T}{T}{T}(font", f"{T}{T}{T}{T}(size 1.27 1.27)", f"{T}{T}{T})",
                  f"{T}{T}{T}(justify {just})", f"{T}{T})",
                  f'{T}{T}(uuid "{uid(self.path, kind, name, at)}")', f"{T})"]
        for s, at, size in self.texts:
            L += [f'{T}(text "{s}"', f"{T}{T}(exclude_from_sim no)",
                  f"{T}{T}(at {fmt(at[0])} {fmt(at[1])} 0)", f"{T}{T}(effects",
                  f"{T}{T}{T}(font", f"{T}{T}{T}{T}(size {size} {size})", f"{T}{T}{T})",
                  f"{T}{T}{T}(justify left)", f"{T}{T})",
                  f'{T}{T}(uuid "{uid(self.path, "t", s[:40], at)}")', f"{T})"]
        for p in self.parts:
            L += self._symbol(p)
        L.append(")")
        text = "\n".join(L) + "\n"
        assert text.count("(") == text.count(")") or _balanced(text)
        with open(self.path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        return len(self.parts), len(self.wires), len(junctions)

    def _symbol(self, p):
        T = "\t"
        x, y = p.at
        power = p.ref.startswith("#")
        vertical = p.rot in (0, 180)
        # Field placement: beside a vertical part, above/below a horizontal one.
        if power:
            below = "GND" in p.sym.lib_id or p.value.startswith("-")   # symbols that point down
            ref_at, val_at, rj = (x, y + 3.81), (x, y + (3.81 if below else -3.81)), None
        elif p.sym.lib_id.startswith("Connector:"):
            ref_at, val_at, rj = (x, y - 6.35), (x, y - 3.81), None
        elif len(p.pins) <= 2:
            if vertical:
                ref_at, val_at, rj = (x + 2.54, y - 1.27), (x + 2.54, y + 1.27), "left"
            else:
                ref_at, val_at, rj = (x, y - 3.81), (x, y + 3.81), None
        else:
            ys = [p.pin(n)[1] for n in p.pins]
            xs = [p.pin(n)[0] for n in p.pins]
            # value below the power/ground symbols hanging off the bottom pins
            ref_at, val_at, rj = (min(xs), min(ys) - 3.81), (min(xs), max(ys) + 6.35), "left"
        if p.text_at:
            ref_at, val_at, rj = p.text_at, (p.text_at[0], p.text_at[1] + 2.54), "left"
        # KiCad adds the symbol's rotation to a field's stored angle; storing
        # 90 on a part rotated 90/270 displays the text horizontal.
        fang = 90 if p.rot in (90, 270) else 0
        # ...but at 90 + 90 = 180 KiCad also mirrors the justification, so a
        # power symbol's name placed with text_at would run back over the
        # symbol. 270 + 90 = 360 reads the right way. Power symbols only:
        # other parts drawn so far rely on the mirrored placement.
        if p.rot == 90 and power and p.text_at:
            fang = 270
        hide_val = power and ("PWR_FLAG" in p.sym.lib_id or getattr(p, "hide_value", False))
        props = [("Reference", p.ref, ref_at, power), ("Value", p.value, val_at, hide_val),
                 ("Footprint", p.footprint, (x, y), True), ("Datasheet", "", (x, y), True),
                 ("Description", "", (x, y), True)]
        props += [(k, v, (x, y), True) for k, v in p.fields.items()]
        # unit 1 keeps the key it always had, so sheets drawn before
        # multi-unit support regenerate with the same UUIDs
        sym_uuid = (uid(self.path, "sym", p.ref) if p.unit == 1
                    else uid(self.path, "sym", p.ref, p.unit))
        L = [f"{T}(symbol", f'{T}{T}(lib_id "{p.sym.lib_id}")',
             f"{T}{T}(at {fmt(x)} {fmt(y)} {p.rot})"] + ([f"{T}{T}(mirror y)"] if p.mirror else []) + [
             f"{T}{T}(unit {p.unit})", f"{T}{T}(body_style 1)",
             f"{T}{T}(exclude_from_sim no)", f"{T}{T}(in_bom {'no' if power or not p.sym.in_bom else 'yes'})",
             f"{T}{T}(on_board {'no' if power else 'yes'})", f"{T}{T}(in_pos_files {'no' if power else 'yes'})",
             f"{T}{T}(dnp no)", f'{T}{T}(uuid "{sym_uuid}")']
        for k, v, at, hide in props:
            L += [f'{T}{T}(property "{k}" "{v}"', f"{T}{T}{T}(at {fmt(at[0])} {fmt(at[1])} {fang})"]
            if hide:
                L.append(f"{T}{T}{T}(hide yes)")
            L += [f"{T}{T}{T}(effects", f"{T}{T}{T}{T}(font", f"{T}{T}{T}{T}{T}(size 1.27 1.27)",
                  f"{T}{T}{T}{T})"]
            if rj and k in ("Reference", "Value"):
                L.append(f"{T}{T}{T}{T}(justify {rj})")
            L += [f"{T}{T}{T})", f"{T}{T})"]
        for n in p.pins:
            L += [f'{T}{T}(pin "{n}"', f'{T}{T}{T}(uuid "{uid(self.path, "pin", p.ref, n)}")', f"{T}{T})"]
        L += [f"{T}{T}(instances", f'{T}{T}{T}(project "{self.project}"',
              f'{T}{T}{T}{T}(path "{self.instance_path}"', f'{T}{T}{T}{T}{T}(reference "{p.ref}")',
              f"{T}{T}{T}{T}{T}(unit {p.unit})", f"{T}{T}{T}{T})", f"{T}{T}{T})", f"{T}{T})", f"{T})"]
        return L


def _on_segment(q, a, b):
    if a[0] == b[0] == q[0]:
        return min(a[1], b[1]) < q[1] < max(a[1], b[1])
    if a[1] == b[1] == q[1]:
        return min(a[0], b[0]) < q[0] < max(a[0], b[0])
    return False


def _balanced(text):
    depth, in_str, i = 0, False, 0
    while i < len(text):
        c = text[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        i += 1
    return depth == 0
