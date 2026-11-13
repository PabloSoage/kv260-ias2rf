#!/usr/bin/env python3
"""
Gigabit Ethernet added to the CONTROL sheet (13 Nov 2026, docs/CONTROL_SPEC.md section 7): a second way
to reach the board, from a laptop or the KV260's own Ethernet port, if the IAS1 link is not there.

RGMII needs 14 FPGA balls and SGMII two LVDS pairs, and none of the FPGA's free balls can be routed
out on the signal layers any more (not even MDC/MDIO's two). So the PHY's SGMII
shares two of the IAS1 link's pairs by an ASSEMBLY OPTION: LINK_RX_D0 (an FPGA LVDS output) can
also reach the PHY's SGMII input through C1220/C1221, and the PHY's SGMII output can reach
LINK_TX_D0 (an FPGA LVDS input, already terminated by R105 and biased to +1V2 by R101/R102)
through C1218/C1219. The four are not fitted (DNP): the board is built for IAS1. For Ethernet,
fit C1218-C1221 and remove C101, C102, C107, C108. The PHY runs unmanaged, set up by its straps
(UTP <-> SGMII with auto-negotiation, what the SGMII core expects); MDC and MDIO end on test pads
TP14/TP15 beside it (MDC pulled down by R1211, MDIO up by R1213) for a probe or a flying lead.
The gateware needs Xilinx's 1G/2.5G PCS/PMA core in its "SGMII over LVDS, asynchronous
oversampling" form (PG047, XAPP523; Artix-7 -2).

  U1201 RTL8211FSI-CG  UTP <-> SGMII (CFG_MODE = 011), industrial; its I/O pads (MDC/MDIO) at 2.5 V from
                       its own LDO (CFG_LDO = 01: DVDD_RG is then an output, decoupled only)
  SGMII                both directions AC-coupled (100 nF, DNP). HSOP/N -> LINK_TX_D0 (terminated and
                       biased at the FPGA already); LINK_RX_D0 (LVDS_25) -> HSIP/N, terminated (100
                       ohm) and biased inside the PHY.
  J1201 HR911130C      RJ45 with magnetics and LEDs, on a tab off the board's east edge
  Y1201 25 MHz         crystal, 20 pF load, two 27 pF
  L1201 2.2 uH         the PHY's 1.0 V switching regulator (REG_OUT -> DVDD10/AVDD10 only)
  straps (4.7 k)       CFG_MODE 011 (RXD1, RXD2 high, RXD3 low); PHY address 1 (LED0 high; RXC and
                       RXCTL low by their internal pull-downs, datasheet table 6: no resistor);
                       RXDLY 0; CFG_LDO 01 (LED1 high, LED2 low)
  LEDs                 LED1 (strap 1: active low) drives the green LED from +3V3_D; LED2 (strap 0:
                       active high) the yellow one to ground; LED0 only straps PHYAD0
  PHYRSTB              10 k / 4.7 uF power-on reset
  unused               RGMII TX inputs tied to ground; INTB, CLKOUT, HSOP_CLK/HSON_CLK, NC(DBG) open

Text edit of rev03/CONTROL.kicad_sch, as _work/add_esd.py. Run once; it refuses to run twice.

Usage:  py _work/add_ethernet.py
"""
import os, re, sys, uuid
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "_work"))
from add_esd import lib_symbol, prop, label, noconn          # noqa: E402

SHEET = os.path.join(ROOT, "rev03", "CONTROL.kicad_sch")
PROJ_LIB = os.path.join(ROOT, "symbols", "kv260-ias2rf.kicad_sym")
U = lambda: str(uuid.uuid4())
PWR = [1226]                                    # the highest #PWR in the project on 13 Nov

# FPGA ball -> net: none (MDC/MDIO could not be routed to the FPGA; see the docstring)
BALLS = {}

R0402, C0402, C0805 = ("Resistor_SMD:R_0402_1005Metric", "Capacitor_SMD:C_0402_1005Metric",
                       "Capacitor_SMD:C_0805_2012Metric")
PHY = {2: "ETH_MDI0_P", 3: "ETH_MDI0_N", 5: "ETH_MDI1_P", 6: "ETH_MDI1_N", 7: "ETH_MDI2_P", 8: "ETH_MDI2_N",
       10: "ETH_MDI3_P", 11: "ETH_MDI3_N", 4: "ETH_1V0", 9: "ETH_1V0", 47: "ETH_1V0", 22: "ETH_1V0",
       1: "ETH_AVDD33", 12: "ETH_AVDD33", 30: "+3V3_D", 31: "+3V3_D", 29: "ETH_DVDDRG", 32: "ETH_REGOUT",
       49: "GND", 13: "ETH_RSTN", 14: "ETH_MDC", 15: "ETH_MDIO",
       38: "ETH_SGTX_PHY_P", 39: "ETH_SGTX_PHY_N", 40: "ETH_SGRX_PHY_P", 41: "ETH_SGRX_PHY_N",
       42: "NC", 43: "NC", 33: "NC", 34: "NC", 44: "NC",
       16: "GND", 17: "GND", 18: "GND", 19: "GND", 20: "GND", 21: "GND",
       23: "ETH_RXD3", 24: "ETH_RXD2", 25: "ETH_RXD1", 26: "ETH_RXD0", 27: "NC", 28: "NC",
       35: "ETH_LED0", 36: "ETH_LED1", 37: "ETH_LED2", 45: "ETH_XI", 46: "ETH_XO", 48: "ETH_RSET"}
JACK = {"1": "ETH_CT", "2": "ETH_MDI0_P", "3": "ETH_MDI0_N", "4": "ETH_MDI1_P", "7": "ETH_MDI1_N",
        "5": "ETH_MDI2_P", "6": "ETH_MDI2_N", "8": "ETH_MDI3_P", "9": "ETH_MDI3_N", "10": "GND", "SH": "GND",
        "11": "ETH_LEDG_A", "12": "ETH_LED1", "14": "ETH_LEDY_A", "13": "GND"}
# two-pin parts: ref -> (lib, value, footprint, net on pin 1, net on pin 2, description)
TWO = {
    "R1201": ("Device:R", "2.49k 1%", R0402, "ETH_RSET", "GND", "RSET: 2.49 k 1 %, as Realtek's reference designs"),
    "C1201": ("Device:C", "27p", C0402, "ETH_XI", "GND", "crystal load"),
    "C1202": ("Device:C", "27p", C0402, "ETH_XO", "GND", "crystal load"),
    "L1201": ("Device:L", "2.2u", "Inductor_SMD:L_0805_2012Metric", "ETH_REGOUT", "ETH_1V0", "switching regulator inductor"),
    "C1203": ("Device:C", "10u", C0805, "ETH_1V0", "GND", "1.0 V output"),
    "C1204": ("Device:C", "100n", C0402, "ETH_1V0", "GND", "AVDD10 pin 4"),
    "C1205": ("Device:C", "100n", C0402, "ETH_1V0", "GND", "AVDD10 pin 9"),
    "C1206": ("Device:C", "100n", C0402, "ETH_1V0", "GND", "AVDD10 pin 47"),
    "C1207": ("Device:C", "100n", C0402, "ETH_1V0", "GND", "DVDD10 pin 22"),
    "FB1201": ("Device:FerriteBead", "600R@100MHz", "Inductor_SMD:L_0603_1608Metric", "+3V3_D", "ETH_AVDD33", "AVDD33 filter"),
    "C1208": ("Device:C", "10u", C0805, "ETH_AVDD33", "GND", "AVDD33 bulk"),
    "C1209": ("Device:C", "100n", C0402, "ETH_AVDD33", "GND", "AVDD33 pin 1"),
    "C1210": ("Device:C", "100n", C0402, "ETH_AVDD33", "GND", "AVDD33 pin 12"),
    "C1211": ("Device:C", "100n", C0402, "+3V3_D", "GND", "DVDD33 pin 30"),
    "C1212": ("Device:C", "10u", C0805, "+3V3_D", "GND", "VDD_REG pin 31, the regulator's input"),
    "C1213": ("Device:C", "100n", C0402, "+3V3_D", "GND", "VDD_REG pin 31"),
    "C1214": ("Device:C", "1u", C0402, "ETH_DVDDRG", "GND", "DVDD_RG, the internal 2.5 V LDO's output"),
    "C1215": ("Device:C", "100n", C0402, "ETH_DVDDRG", "GND", "DVDD_RG pin 29"),
    "R1202": ("Device:R", "4.7k", R0402, "ETH_LED0", "+3V3_D", "strap PHYAD0 = 1"),
    "R1203": ("Device:R", "4.7k", R0402, "ETH_LED1", "+3V3_D", "strap CFG_LDO0 = 1"),
    "R1204": ("Device:R", "4.7k", R0402, "ETH_LED2", "GND", "strap CFG_LDO1 = 0: CFG_LDO = 01, 2.5 V I/O"),
    "R1205": ("Device:R", "510", R0402, "+3V3_D", "ETH_LEDG_A", "green LED (LED1, active low)"),
    "R1206": ("Device:R", "510", R0402, "ETH_LED2", "ETH_LEDY_A", "yellow LED (LED2, active high)"),
    "R1207": ("Device:R", "4.7k", R0402, "ETH_RXD3", "GND", "strap CFG_MODE2 = 0"),
    "R1208": ("Device:R", "4.7k", R0402, "ETH_RXD2", "ETH_DVDDRG", "strap CFG_MODE1 = 1"),
    "R1209": ("Device:R", "4.7k", R0402, "ETH_RXD1", "ETH_DVDDRG", "strap CFG_MODE0 = 1: CFG_MODE = 011, UTP <-> SGMII"),
    "R1210": ("Device:R", "4.7k", R0402, "ETH_RXD0", "GND", "strap RXDLY = 0"),
    "R1211": ("Device:R", "4.7k", R0402, "ETH_MDC", "GND", "MDC pull-down: nothing drives it"),
    "R1213": ("Device:R", "1.5k", R0402, "ETH_MDIO", "ETH_DVDDRG", "MDIO pull-up (datasheet: 1.5 k)"),
    "R1214": ("Device:R", "10k", R0402, "ETH_RSTN", "+3V3_D", "power-on reset"),
    "C1216": ("Device:C", "4.7u", C0402, "ETH_RSTN", "GND", "power-on reset"),
    "C1217": ("Device:C", "100n", C0402, "ETH_CT", "GND", "magnetics centre taps"),
    "C1218": ("Device:C", "100n", C0402, "ETH_SGRX_PHY_P", "LINK_TX_D0_P", "DNP: SGMII into the FPGA on LINK_TX_D0"),
    "C1219": ("Device:C", "100n", C0402, "ETH_SGRX_PHY_N", "LINK_TX_D0_N", "DNP: SGMII into the FPGA on LINK_TX_D0"),
    "C1220": ("Device:C", "100n", C0402, "LINK_RX_D0_P", "ETH_SGTX_PHY_P", "DNP: SGMII out of the FPGA on LINK_RX_D0"),
    "C1221": ("Device:C", "100n", C0402, "LINK_RX_D0_N", "ETH_SGTX_PHY_N", "DNP: SGMII out of the FPGA on LINK_RX_D0"),
}
DNP = {"C1218", "C1219", "C1220", "C1221"}
POWER = {"GND": ("power:GND", "GND"), "+3V3_D": ("power:+3V3", "+3V3_D")}


def proj_symbol(name):
    t = open(PROJ_LIB, encoding="utf-8").read()
    i = t.find(f'\n\t(symbol "{name}"\n'); j = t.find('\n\t(symbol "', i + 5); j = j if j > 0 else t.rfind("\n)")
    b = t[i + 1:j].replace(f'(symbol "{name}"', f'(symbol "kv260-ias2rf:{name}"', 1)
    return "\n".join("\t" + l for l in b.split("\n"))


def pins_of(block):
    """pin number -> (x, y, angle) in symbol coordinates (y up)."""
    out = {}
    for m in re.finditer(r'\(pin \w+ \w+\s*\(at ([-\d.]+) ([-\d.]+) ([-\d.]+)\).*?\(number "([^"]+)"', block, re.S):
        out[m[4]] = (float(m[1]), float(m[2]), int(float(m[3])))
    return out


class Sheet:
    def __init__(s):
        s.t = open(SHEET, encoding="utf-8").read()
        m = re.search(r'\(instances\s*\(project "([^"]+)"\s*\(path "([^"]+)"', s.t)
        s.project, s.ipath = m.group(1), m.group(2)
        s.new = []; s.libs = {}

    def need(s, lib_id):
        if lib_id in s.libs: return s.libs[lib_id]
        key = f'(symbol "{lib_id}"'
        if key not in s.t:
            lib, name = lib_id.split(":")
            block = proj_symbol(name) if lib == "kv260-ias2rf" else lib_symbol(lib, name)
            i = s.t.find("(lib_symbols"); j = s.t.find("\n\t)", i)
            s.t = s.t[:j] + "\n" + block + s.t[j:]
        i = s.t.find(key); j = s.t.find("\n\t\t)\n", i)
        s.libs[lib_id] = pins_of(s.t[i:j]); return s.libs[lib_id]

    def inst(s, lib_id, ref, value, fp, x, y, desc="", in_bom=True):
        pins = s.need(lib_id); b = "yes" if in_bom else "no"; dnp = "yes" if ref in DNP else "no"
        pp = "\n".join(f'\t\t(pin "{p}"\n\t\t\t(uuid "{U()}")\n\t\t)' for p in pins)
        hide = ref.startswith("#")
        s.new.append(
            f'\t(symbol\n\t\t(lib_id "{lib_id}")\n\t\t(at {x:.2f} {y:.2f} 0)\n\t\t(unit 1)\n\t\t(body_style 1)\n'
            f'\t\t(exclude_from_sim no)\n\t\t(in_bom {b})\n\t\t(on_board {b})\n\t\t(in_pos_files {b})\n\t\t(dnp {dnp})\n'
            f'\t\t(uuid "{U()}")\n' + prop("Reference", ref, x + 2.54, y - 1.27, hide=hide) + "\n"
            + prop("Value", value, x + 2.54, y + 1.27, hide=hide) + "\n"
            + prop("Footprint", fp, x, y, hide=True) + "\n" + prop("Datasheet", "", x, y, hide=True) + "\n"
            + prop("Description", "", x, y, hide=True) + "\n" + pp
            + f'\n\t\t(instances\n\t\t\t(project "{s.project}"\n\t\t\t\t(path "{s.ipath}"\n'
            f'\t\t\t\t\t(reference "{ref}")\n\t\t\t\t\t(unit 1)\n\t\t\t\t)\n\t\t\t)\n\t\t)\n\t)')
        return {p: (round(x + px, 2), round(y - py, 2), a) for p, (px, py, a) in pins.items()}

    def connect(s, at, net):
        x, y, a = at
        if net == "NC":
            s.new.append(noconn(x, y))
        elif net in POWER:
            lib_id, val = POWER[net]; PWR[0] += 1
            s.inst(lib_id, f"#PWR{PWR[0]}", val, "", x, y, in_bom=False)
        else:
            # the label reads away from the part: a pin pointing left (angle 0) gets its text to the left
            s.new.append(label(net, x, y, {0: 180, 180: 0, 90: 0, 270: 0}[a]))

    def save(s):
        end = s.t.rstrip().rfind(")")
        s.t = s.t[:end].rstrip("\n") + "\n" + "\n".join(s.new) + "\n)\n"
        open(SHEET, "w", encoding="utf-8", newline="\n").write(s.t)


def balls(s):
    """The bank-34 balls: drop their no-connect flags and put the nets' labels there."""
    i = s.t.find('(symbol "FPGA_Xilinx_Artix7:XC7A50T-FTG256"'); e = s.t.find("\n\t\t)\n", i)
    lib = s.t[i:e]
    units = sorted((m.start(), m.group(1)) for m in re.finditer(r'\(symbol "XC7A50T-FTG256_(\d+)_\d+"', lib))
    pos = {}
    for m in re.finditer(r'\(pin \w+ \w+\s*\(at ([-\d.]+) ([-\d.]+) ([-\d.]+)\).*?\(number "([^"]+)"', lib, re.S):
        u = [n for st, n in units if st < m.start()][-1]
        pos[m[4]] = (u, float(m[1]), float(m[2]), int(float(m[3])))
    inst = {m[4]: (float(m[1]), float(m[2])) for m in re.finditer(
        r'\(lib_id "FPGA_Xilinx_Artix7:XC7A50T-FTG256"\)\s*\(at ([-\d.]+) ([-\d.]+) ([-\d.]+)\).*?\(unit (\d+)\)', s.t, re.S)}
    for ball, net in BALLS.items():
        u, px, py, a = pos[ball]; X, Y = inst[u]; x, y = round(X + px, 2), round(Y - py, 2)
        nc = re.compile(r'\n\t\(no_connect\s*\(at ' + re.escape(f"{x:g}") + r'\s+' + re.escape(f"{y:g}")
                        + r'\)\s*\(uuid "[^"]+"\)\s*\)')
        m = nc.search(s.t)
        assert m, f"no no-connect at ball {ball} ({x}, {y})"
        s.t = s.t[:m.start()] + s.t[m.end():]
        s.new.append(label(net, x, y, {0: 180, 180: 0}[a]))


def main():
    s = Sheet()
    if "RTL8211FSI-CG" in s.t: sys.exit("already added")
    balls(s)
    X0, Y0 = 640.08, 487.68                     # a free area of the A1 sheet, below unit 4
    p = s.inst("kv260-ias2rf:RTL8211FSI-CG", "U1201", "RTL8211FSI-CG",
               "Package_DFN_QFN:QFN-48-1EP_6x6mm_P0.4mm_EP4.4x4.4mm", X0, Y0, "Gigabit Ethernet PHY, SGMII")
    for num, net in PHY.items(): s.connect(p[str(num)], net)
    p = s.inst("kv260-ias2rf:HR911130C", "J1201", "HR911130C", "kv260-ias2rf:RJ45_Hanrun_HR911130C",
               X0 + 91.44, Y0, "Ethernet RJ45")
    for num, net in JACK.items(): s.connect(p[num], net)
    p = s.inst("Device:Crystal_GND24", "Y1201", "25MHz", "Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm",
               X0 + 50.8, Y0 + 45.72, "25 MHz, 20 pF load, +-20 ppm, -40 to 85 C (X322525MOB4SI)")
    for num, net in {"1": "ETH_XI", "3": "ETH_XO", "2": "GND", "4": "GND"}.items(): s.connect(p[num], net)
    # the PHY's own rails (after the ferrite, after its regulator's inductor) need a driver for ERC
    for k, net in enumerate(("ETH_AVDD33", "ETH_1V0")):
        fx, fy = X0 + 40.64 + k * 10.16, Y0 - 50.8
        p = s.inst("power:PWR_FLAG", f"#FLG{1201 + k}", "PWR_FLAG", "", fx, fy, in_bom=False)
        s.connect(p["1"], net)
    x, y = X0 - 66.04, Y0 + 50.8                 # the two-pin parts in a grid
    for k, (ref, (lib, val, fp, n1, n2, desc)) in enumerate(TWO.items()):
        px, py = x + (k % 20) * 10.16, y + (k // 20) * 25.4
        p = s.inst(lib, ref, val, fp, px, py, desc)
        s.connect(p["1"], n1); s.connect(p["2"], n2)
    s.save()
    print(f"added U1201, J1201, Y1201 and {len(TWO)} passives; #PWR up to {PWR[0]}")


if __name__ == "__main__":
    main()
