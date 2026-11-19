#!/usr/bin/env python3
"""
Rev08 phase 4: the schematic changes outside the new RX_VU sheet (REV08_PLAN section 11, phase 4).

  root      RX_VU's sheet block (XO_SCL, XO_SDA in; IF_VU out) and ROUTING's new IF_VU pin, joined by labels
  ROUTING   C927: the second source for SW2's RF2 throw (section 5.7). C926 (J922) becomes DNP, C927 (IF_VU from the
            front end) is fitted: the board is built with the front end on SW2. Swap the two for the Rev07 J922 input.
  IAS_LINK  J103, the camera pass-through receptacle (section 4.3): every contact to the same contact of J102,
            whose non-ground pins were no-connects until now. Net names carry the carrier's function and the pin.
  STATUS    a new sheet (status.py): the LED expander, status, heartbeat and rail LEDs, the debug USB bridge
            (sections 3.1, 3.2). Planned on CONTROL; that sheet has no free area to draw them legibly.
  CONTROL   two sheet pins, PMOD_SPARE1 and PMOD_SPARE2, so the bridge and the heartbeat LED reach the spare lines

Runs _work/sheets/rx_vu.py and status.py; run _work/rev08_symbols.py and _work/rev08_footprints.py first. Text edits in the style of
_work/add_ethernet.py; each step refuses to run twice.

Usage:  py _work/rev08_schematic.py
"""
import os
import re
import sys
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "_work"))
sys.path.insert(0, os.path.join(ROOT, "_work", "sheets"))
from add_esd import lib_symbol, prop, label, noconn            # noqa: E402
import rx_vu                                                   # noqa: E402  (importing draws, write() saves)
import status                                                  # noqa: E402
import schgen                                                  # noqa: E402

U = lambda: str(uuid.uuid4())
T, NL = "\t", "\n"
ROOT_SCH = os.path.join(ROOT, "KV260-IAS2RF.kicad_sch")
PROJ_LIB = os.path.join(ROOT, "symbols", "kv260-ias2rf.kicad_sym")
R0402, C0402, C0805 = ("Resistor_SMD:R_0402_1005Metric", "Capacitor_SMD:C_0402_1005Metric",
                       "Capacitor_SMD:C_0805_2012Metric")
LED0402 = "LED_SMD:LED_0402_1005Metric"


def highest(tag):
    n = 0
    for f in os.listdir(os.path.join(ROOT, "sheets")):
        if f.endswith(".kicad_sch"):
            for m in re.finditer(r'"' + tag + r'(\d+)"', open(os.path.join(ROOT, "sheets", f), encoding="utf-8").read()):
                n = max(n, int(m.group(1)))
    return n


PWR = [0]


def proj_symbol(name):
    t = open(PROJ_LIB, encoding="utf-8").read()
    i = t.find(f'\n\t(symbol "{name}"\n'); j = t.find('\n\t(symbol "', i + 5); j = j if j > 0 else t.rfind("\n)")
    b = t[i + 1:j].replace(f'(symbol "{name}"', f'(symbol "kv260-ias2rf:{name}"', 1)
    return "\n".join("\t" + ln for ln in b.split("\n"))


def wire(a, b):
    return (f"{T}(wire{NL}{T*2}(pts{NL}{T*3}(xy {a[0]:.2f} {a[1]:.2f}) (xy {b[0]:.2f} {b[1]:.2f}){NL}{T*2}){NL}"
            f"{T*2}(stroke{NL}{T*3}(width 0){NL}{T*3}(type default){NL}{T*2}){NL}{T*2}(uuid \"{U()}\"){NL}{T})")


def junction(x, y):
    return (f"{T}(junction{NL}{T*2}(at {x:.2f} {y:.2f}){NL}{T*2}(diameter 0){NL}{T*2}(color 0 0 0 0){NL}"
            f"{T*2}(uuid \"{U()}\"){NL}{T})")


def hlabel(name, shape, x, y, ang):
    j = "right" if ang == 180 else "left"
    return (f'{T}(hierarchical_label "{name}"{NL}{T*2}(shape {shape}){NL}{T*2}(at {x:.2f} {y:.2f} {ang}){NL}'
            f"{T*2}(effects{NL}{T*3}(font{NL}{T*4}(size 1.27 1.27){NL}{T*3}){NL}{T*3}(justify {j}){NL}{T*2}){NL}"
            f'{T*2}(uuid "{U()}"){NL}{T})')


def text(s_, x, y, size=1.27):
    return (f'{T}(text "{s_}"{NL}{T*2}(exclude_from_sim no){NL}{T*2}(at {x:.2f} {y:.2f} 0){NL}{T*2}(effects{NL}'
            f"{T*3}(font{NL}{T*4}(size {size} {size}){NL}{T*3}){NL}{T*3}(justify left){NL}{T*2}){NL}"
            f'{T*2}(uuid "{U()}"){NL}{T})')


def pin_angles(text, key):
    i = text.find(key)
    depth, j = 0, i
    while True:
        if text[j] == "(":
            depth += 1
        elif text[j] == ")":
            depth -= 1
            if depth == 0:
                break
        j += 1
    return pins_of(text[i:j])


def pins_of(block):
    out = {}
    for m in re.finditer(r'\(pin \w+ \w+\s*\(at ([-\d.]+) ([-\d.]+) ([-\d.]+)\).*?\(number "([^"]+)"', block, re.S):
        out[m[4]] = (float(m[1]), float(m[2]), int(float(m[3])))
    return out


class Sheet:
    """A sheet edited as text: parts placed at rotation 0 or 90, their pins led out to labels and power symbols."""

    def __init__(s, rel):
        s.path = os.path.join(ROOT, rel)
        s.t = open(s.path, encoding="utf-8").read()
        m = re.search(r'\(instances\s*\(project "([^"]+)"\s*\(path "([^"]+)"', s.t)
        s.project, s.ipath = m.group(1), m.group(2)
        s.new, s.libs, s.dnp = [], {}, set()

    def need(s, lib_id):
        if lib_id in s.libs:
            return s.libs[lib_id]
        key = f'(symbol "{lib_id}"'
        if key not in s.t:
            lib, name = lib_id.split(":")
            if lib == "kv260-ias2rf":
                block = proj_symbol(name)
            else:                                     # flattened as KiCad embeds a derived symbol (schgen)
                body = schgen.LibSymbol(lib_id, schgen.KICAD_SYM + lib + ".kicad_sym").body
                block = "\t\t" + body.replace("\n", "\n\t")
            i = s.t.find("(lib_symbols"); j = s.t.find("\n\t)", i)
            s.t = s.t[:j] + "\n" + block + s.t[j:]
        s.libs[lib_id] = pin_angles(s.t, key)
        return s.libs[lib_id]

    def inst(s, lib_id, ref, value, fp, x, y, rot=0, in_bom=True, ref_at=None):
        pins = s.need(lib_id)
        b = "yes" if in_bom else "no"
        dnp = "yes" if ref in s.dnp else "no"
        pp = "\n".join(f'{T*2}(pin "{p}"{NL}{T*3}(uuid "{U()}"){NL}{T*2})' for p in pins)
        hide = ref.startswith("#")
        fa = 90 if rot in (90, 270) else 0
        s.new.append(
            f"{T}(symbol{NL}{T*2}(lib_id \"{lib_id}\"){NL}{T*2}(at {x:.2f} {y:.2f} {rot}){NL}{T*2}(unit 1){NL}"
            f"{T*2}(body_style 1){NL}{T*2}(exclude_from_sim no){NL}{T*2}(in_bom {b}){NL}{T*2}(on_board {b}){NL}"
            f"{T*2}(in_pos_files {b}){NL}{T*2}(dnp {dnp}){NL}{T*2}(uuid \"{U()}\"){NL}"
            + prop("Reference", ref, *(ref_at or (x + 2.54, y - 2.54)), hide=hide, ang=fa) + NL
            + prop("Value", value, *((ref_at[0], ref_at[1] + 2.54) if ref_at else (x + 2.54, y + 2.54)), hide=hide, ang=fa) + NL
            + prop("Footprint", fp, x, y, hide=True) + NL + prop("Datasheet", "", x, y, hide=True) + NL
            + prop("Description", "", x, y, hide=True) + NL + pp
            + f"{NL}{T*2}(instances{NL}{T*3}(project \"{s.project}\"{NL}{T*4}(path \"{s.ipath}\"{NL}"
            f"{T*5}(reference \"{ref}\"){NL}{T*5}(unit 1){NL}{T*4}){NL}{T*3}){NL}{T*2}){NL}{T})")
        out = {}
        for p, (px, py, a) in pins.items():
            for _ in range(rot // 90):
                px, py, a = -py, px, (a + 90) % 360
            out[p] = (round(x + px, 2), round(y - py, 2), a)
        return out

    def power(s, lib_id, value, x, y, rot=0):
        PWR[0] += 1
        tag = "#FLG" if "PWR_FLAG" in lib_id else "#PWR"
        s.inst(lib_id, f"{tag}{PWR[0]}", value, "", x, y, rot, in_bom=False)

    def lead(s, at, net, n=2.54):
        """Lead a pin out by n and end it on its net. at = (x, y, library angle after rotation)."""
        x, y, a = at
        if net == "NC":
            s.new.append(noconn(x, y)); return
        d = {0: (-1, 0), 180: (1, 0), 90: (0, 1), 270: (0, -1)}[a]
        e = (round(x + d[0] * n, 2), round(y + d[1] * n, 2))
        s.new.append(wire((x, y), e))
        if net == "GND":
            s.power("power:GND", "GND", *e, rot={(0, 1): 0, (-1, 0): 270, (1, 0): 90, (0, -1): 180}[d])
        elif net in RAILS:
            s.power(RAILS[net], net, *e, rot={(0, -1): 0, (-1, 0): 90, (1, 0): 270, (0, 1): 180}[d])
        else:
            if d[1]:
                e2 = (round(e[0] + 2.54, 2), e[1]); s.new.append(wire(e, e2)); e = e2
            s.new.append(label(net, e[0], e[1], 180 if d[0] < 0 else 0))
        return e

    def part(s, lib_id, ref, value, fp, x, y, nets, rot=0, ref_at=None):
        p = s.inst(lib_id, ref, value, fp, x, y, rot, ref_at=ref_at)
        for num, net in nets.items():
            s.lead(p[num], net)
        assert set(nets) == set(p), (ref, set(p) ^ set(nets))
        return p

    def save(s):
        end = s.t.rstrip().rfind(")")
        s.t = s.t[:end].rstrip("\n") + "\n" + "\n".join(s.new) + "\n)\n"
        open(s.path, "w", encoding="utf-8", newline="\n").write(s.t)


RAILS = {"+3V3_D": "power:+3V3", "+5V0": "power:+5V", "+12V": "power:+12V", "+1V8_D": "power:+1V8",
         "+1V0": "power:+1V0", "+3V3_USB": "power:+3V3", "VBUS_USB": "power:VBUS"}


# ---------------------------------------------------------------- root
def sheet_pin(name, shape, x, y, ang):
    return (f'{T*2}(pin "{name}" {shape}{NL}{T*3}(at {x:.2f} {y:.2f} {ang}){NL}{T*3}(uuid "{U()}"){NL}'
            f"{T*3}(effects{NL}{T*4}(font{NL}{T*5}(size 1.143 1.143){NL}{T*4}){NL}{T*4}(justify left){NL}{T*3}){NL}{T*2})")


def root_label(name, x, y):
    return (f'{T}(label "{name}"{NL}{T*2}(at {x:.2f} {y:.2f} 0){NL}{T*2}(effects{NL}{T*3}(font{NL}'
            f"{T*4}(size 1.016 1.016){NL}{T*3}){NL}{T*3}(justify left){NL}{T*2}){NL}{T*2}(uuid \"{U()}\"){NL}{T})")


def block(name, block_uuid, X, Y, W, pins, page):
    H = 2.54 * (len(pins) + 2)
    out = (f"{T}(sheet{NL}{T*2}(at {X} {Y}){NL}{T*2}(size {W} {H:.2f}){NL}{T*2}(exclude_from_sim no){NL}"
           f"{T*2}(in_bom yes){NL}{T*2}(on_board yes){NL}{T*2}(dnp no){NL}{T*2}(fields_autoplaced yes){NL}"
           f"{T*2}(stroke{NL}{T*3}(width 0.254){NL}{T*3}(type solid){NL}{T*3}(color 30 64 128 1){NL}{T*2}){NL}"
           f"{T*2}(fill{NL}{T*3}(color 245 248 255 0.9){NL}{T*2}){NL}{T*2}(uuid \"{block_uuid}\"){NL}"
           f'{T*2}(property "Sheetname" "{name}"{NL}{T*3}(at {X} {Y - 1:.2f} 0){NL}{T*3}(show_name no){NL}'
           f"{T*3}(do_not_autoplace no){NL}{T*3}(effects{NL}{T*4}(font{NL}{T*5}(size 1.524 1.524){NL}"
           f"{T*5}(bold yes){NL}{T*4}){NL}{T*4}(justify left bottom){NL}{T*3}){NL}{T*2}){NL}"
           f'{T*2}(property "Sheetfile" "sheets/{name}.kicad_sch"{NL}{T*3}(at {X} {Y + H + 0.8:.2f} 0){NL}'
           f"{T*3}(show_name no){NL}{T*3}(do_not_autoplace no){NL}{T*3}(effects{NL}{T*4}(font{NL}"
           f"{T*5}(size 1.143 1.143){NL}{T*4}){NL}{T*4}(justify left top){NL}{T*3}){NL}{T*2}){NL}"
           + NL.join(sheet_pin(n, sh, X, Y + 2.54 * (k + 1), 180) for k, (n, sh) in enumerate(pins))
           + f"{NL}{T*2}(instances{NL}{T*3}(project \"KV260-IAS2RF\"{NL}"
           f"{T*4}(path \"/{rx_vu.ROOT_UUID}\"{NL}{T*5}(page \"{page}\"){NL}{T*4}){NL}{T*3}){NL}{T*2}){NL}{T})")
    new = [out]
    for k, (n, _) in enumerate(pins):
        y = Y + 2.54 * (k + 1)
        new += [wire((X, y), (X - 12.7, y)), root_label(n, X - 12.7, y)]
    return new


def do_root():
    t = open(ROOT_SCH, encoding="utf-8").read()
    if '"RX_VU"' in t:
        print("root: already done"); return
    new = block("RX_VU", rx_vu.BLOCK_UUID, 459.74, 160.02, 50.8,
                [("XO_SCL", "input"), ("XO_SDA", "bidirectional"), ("IF_VU", "output")], "11")
    new += block("STATUS", status.BLOCK_UUID, 459.74, 187.96, 50.8,
                 [("XO_SCL", "input"), ("XO_SDA", "bidirectional"), ("PMOD_SPARE1", "output"),
                  ("PMOD_SPARE2", "input")], "12")
    # ROUTING's new input pin
    m = re.search(r'\(property "Sheetname" "ROUTING"', t)
    k = t.find(T * 2 + "(instances", m.start())
    t = t[:k] + sheet_pin("IF_VU", "input", 459.74, 142.24, 180) + NL + t[k:]
    new += [wire((459.74, 142.24), (447.04, 142.24)), root_label("IF_VU", 447.04, 142.24)]
    # CONTROL's block: PMOD_SPARE1 and PMOD_SPARE2 on its bottom edge (its sides have the SW_CTRL and other buses
    # running past them), led down to labels clear of the block's file name
    m = re.search(r'\(property "Sheetname" "CONTROL"', t)
    k = t.find(T * 2 + "(instances", m.start())
    t = t[:k] + sheet_pin("PMOD_SPARE1", "input", 200.66, 193.04, 270) + NL +         sheet_pin("PMOD_SPARE2", "output", 205.74, 193.04, 270) + NL + t[k:]
    for n, x, y in (("PMOD_SPARE1", 200.66, 198.12), ("PMOD_SPARE2", 205.74, 203.2)):
        new += [wire((x, 193.04), (x, y)), root_label(n, x, y)]
    end = t.rstrip().rfind(")")
    t = t[:end].rstrip(NL) + NL + NL.join(new) + NL + ")" + NL
    open(ROOT_SCH, "w", encoding="utf-8", newline=NL).write(t)
    print("root: RX_VU and STATUS blocks; IF_VU on ROUTING; PMOD_SPARE1/2 on CONTROL")


def do_control_hier():
    s = Sheet("sheets/CONTROL.kicad_sch")
    if 'hierarchical_label "PMOD_SPARE1"' in s.t:
        print("CONTROL: already done"); return
    # beside the existing local labels: a hierarchical label of the same name joins the net on this sheet
    for n, shape in (("PMOD_SPARE1", "input"), ("PMOD_SPARE2", "output")):
        m = re.search(r'\(label "' + n + r'"\s*\(at ([-\d.]+) ([-\d.]+) (\d+)\)', s.t)
        assert m, n
        x, y, a = float(m.group(1)), float(m.group(2)), int(m.group(3))
        d = -1 if a == 180 else 1
        e = (round(x + d * 15.24, 2), y)
        s.new.append(wire((x, y), e))
        s.new.append(hlabel(n, shape, e[0], e[1], 180 if d < 0 else 0))
    s.save()
    print("CONTROL: PMOD_SPARE1/2 hierarchical labels for STATUS")


# ---------------------------------------------------------------- ROUTING
def do_routing():
    s = Sheet("sheets/ROUTING.kicad_sch")
    if '"C927"' in s.t:
        print("ROUTING: already done"); return
    i = s.t.find('(property "Reference" "C926"'); st = s.t.rfind("\n\t(symbol", 0, i)
    blk = s.t[st:i]
    assert "(dnp no)" in blk
    s.t = s.t[:st] + blk.replace("(dnp no)", "(dnp yes)", 1) + s.t[i:]
    x, y0 = 247.65, 86.36                                   # C926 pin 1, the switch's RF2 side
    s.new.append(junction(x, y0))
    s.new.append(wire((x, y0), (x, 104.14)))
    p = s.inst("Device:C", "C927", "100n", C0402, x, 107.95)
    assert p["1"][:2] == (x, 104.14), p
    s.new.append(wire((x, 111.76), (x, 114.3)))
    s.new.append(wire((x, 114.3), (x + 2.54, 114.3)))
    s.new.append(hlabel("IF_VU", "input", x + 2.54, 114.3, 0))
    for k, line in enumerate(("Rev08 (REV08_PLAN 5.7): two sources for SW2's RF2 throw.",
                              "As built C927 is fitted (IF_VU from RX_VU over the L6 line)",
                              "and C926 (J922) is DNP; swap them for the Rev07 J922 input.")):
        s.new.append(text(line, 215.9, 119.38 + 2.54 * k))
    s.save()
    print("ROUTING: C927 and IF_VU; C926 DNP")


# ---------------------------------------------------------------- IAS_LINK: J103
IAS0 = {1: "IAS0_P1", 4: "IAS0_D0_4", 5: "IAS0_D0_5", 7: "IAS0_CLK_7", 8: "IAS0_CLK_8", 10: "IAS0_D3_10",
        11: "IAS0_D3_11", 13: "IAS0_PL_1V8", 14: "IAS0_SCL", 15: "IAS0_FLASH", 17: "IAS0_2V75", 18: "IAS0_2V75",
        20: "IAS0_TRIGGER", 21: "IAS0_RESET", 22: "IAS0_SDA", 23: "IAS0_PL_1V2", 24: "IAS0_PL_1V2",
        26: "IAS0_D2_26", 27: "IAS0_D2_27", 29: "IAS0_D1_29", 30: "IAS0_D1_30", 32: "IAS0_EXTCLK",
        34: "IAS0_VDD_AF2V8"}
GND_PINS = (2, 3, 6, 9, 12, 16, 19, 25, 28, 31, 33)


def do_ias_link():
    s = Sheet("sheets/IAS_LINK.kicad_sch")
    if '"J103"' in s.t:
        print("IAS_LINK: already done"); return
    # J102's pin positions: its symbol instance, Conn_02x17_Odd_Even (odd pins left at -5.08, even right at 7.62)
    i = s.t.find('(property "Reference" "J102"'); st = s.t.rfind("\n\t(symbol", 0, i)
    jx, jy = map(float, re.search(r"\n\t\t\(at ([-\d.]+) ([-\d.]+)", s.t[st:i]).groups())
    lib = s.need("Connector_Generic:Conn_02x17_Odd_Even")
    removed = 0
    for pin, net in IAS0.items():
        px, py, a = lib[str(pin)]
        x, y = round(jx + px, 2), round(jy - py, 2)
        m = re.compile(r'\n\t\(no_connect\s*\(at ' + re.escape(f"{x:g}") + r'\s+' + re.escape(f"{y:g}")
                       + r'\)\s*\(uuid "[^"]+"\)\s*\)').search(s.t)
        assert m, f"J102.{pin}: no-connect not found at ({x}, {y})"
        s.t = s.t[:m.start()] + s.t[m.end():]
        removed += 1
        s.lead((x, y, a), net, 5.08)
    # J103 beside it, the same pin for pin; its metal fittings (MP) to ground
    X, Y = jx + 55.88, jy
    nets = {str(p): IAS0.get(p, "GND" if p in GND_PINS else "NC") for p in range(1, 35)}
    nets["MP"] = "GND"
    s.part("Connector_Generic_MountingPin:Conn_02x17_Odd_Even_MountingPin", "J103", "BM20B(0.8)-34DS-0.4V(51)",
           "kv260-ias2rf:CONN-SMD_34P-P0.40_BM20B-0.8-34DS-0.4V-51", X, Y, nets,
           ref_at=(X - 2.54, Y - 25.4))
    s.new.append(text("J103 (Rev08): IAS0 camera pass-through receptacle on the top face, contact for contact with J102 "
                      "(REV08_PLAN 4.3).", jx - 27.94, Y + 30.48))
    s.new.append(text("Nothing on the adapter uses these nets: the carrier's camera signals and rails pass straight "
                      "through to an IAS camera module.", jx - 27.94, Y + 33.02))
    old = "J102: IAS0 (KV260 J7), mechanical only: grounds, nothing else."
    assert old in s.t
    s.t = s.t.replace(old, "J102: IAS0 (KV260 J7): grounds; every other contact passes to J103 (Rev08).")
    s.save()
    print(f"IAS_LINK: J103 added, {removed} of J102's no-connects replaced by the pass-through nets")


def main():
    PWR[0] = max(highest("#PWR"), highest("#FLG"))
    rx_vu.write()
    status.write()
    PWR[0] = max(PWR[0], highest("#PWR"), highest("#FLG"))
    do_root()
    do_routing()
    do_ias_link()
    do_control_hier()
    print("power symbols up to", PWR[0])


if __name__ == "__main__":
    main()
