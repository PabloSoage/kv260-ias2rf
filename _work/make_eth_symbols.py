#!/usr/bin/env python3
"""
Ethernet symbols for the project library (13 Nov 2026), appended to symbols/kv260-ias2rf.kicad_sym
or replaced in place:

  RTL8211FSI-CG  Realtek gigabit PHY with an SGMII port, 48-pin QFN 6x6 mm with exposed pad (pin 49
                 here). Pin table from the RTL8211FS(I)(-VS) datasheet Rev. 1.8 (2021), section 6.
                 Types as given there; the strap pins (LED, RXD, RXC, RXCTL) are latched inputs at
                 reset and outputs after, so bidirectional.
  HR911130C      HanRun gigabit RJ45 with magnetics and two LEDs, Rev. B drawing: chip-side
                 pins 1-10 (1 = the windings' centre taps, 10 = chassis ground through the
                 1000 pF / 4 x 75 ohm termination), LED pins 11-14, two shield pins (SH).

Usage:  py _work/make_eth_symbols.py
"""
import os, re
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB = os.path.join(ROOT, "symbols", "kv260-ias2rf.kicad_sym")
T = "\t"


def pin(kind, x, y, ang, name, num, hide=False):
    h = " (hide yes)" if hide else ""
    return (f'{T*3}(pin {kind} line\n{T*4}(at {x:.2f} {y:.2f} {ang})\n{T*4}(length 2.54){h}\n'
            f'{T*4}(name "{name}" (effects (font (size 1.27 1.27))))\n'
            f'{T*4}(number "{num}" (effects (font (size 1.27 1.27))))\n{T*3})')


def prop(name, val, x=0, y=0, hide=True):
    return (f'{T*2}(property "{name}" "{val}"\n{T*3}(at {x} {y} 0)\n'
            f'{T*3}(effects (font (size 1.27 1.27)) (hide {"yes" if hide else "no"}))\n{T*2})')


def symbol(name, ref, desc, source, fp, w, h, pins):
    out = [f'{T}(symbol "{name}"', f'{T*2}(pin_names (offset 0.508))', f'{T*2}(exclude_from_sim no)',
           f'{T*2}(in_bom yes)', f'{T*2}(on_board yes)',
           prop("Reference", ref, 0, h + 1.27, False), prop("Value", name, 0, -h - 1.27, False),
           prop("Footprint", fp), prop("Datasheet", ""), prop("Description", desc),
           prop("ki_keywords", "kv260-ias2rf"), prop("SymbolSource", source),
           f'{T*2}(symbol "{name}_0_1"\n{T*3}(rectangle\n{T*4}(start {-w:.2f} {h:.2f})\n{T*4}(end {w:.2f} {-h:.2f})\n'
           f'{T*4}(stroke (width 0.254) (type default))\n{T*4}(fill (type background))\n{T*3})\n{T*2})',
           f'{T*2}(symbol "{name}_1_1"'] + pins + [f'{T*2})', f'{T})']
    return "\n".join(out)


# ---- RTL8211FSI-CG: left = MAC side (SGMII, management, unused RGMII), right = line side, top = supplies
W, H = 17.78, 38.1
L = [("input", "HSIP", 38), ("input", "HSIN", 39), ("output", "HSOP", 40), ("output", "HSON", 41),
     ("output", "HSOP_CLK", 42), ("output", "HSON_CLK", 43), None,
     ("input", "MDC", 14), ("bidirectional", "MDIO", 15), ("input", "~{PHYRSTB}", 13),
     ("open_collector", "~{INTB}/~{PMEB}", 34), ("no_connect", "NC(DBG)", 33), None,
     ("input", "TXC", 21), ("input", "TXCTL", 20), ("input", "TXD0", 19), ("input", "TXD1", 18),
     ("input", "TXD2", 17), ("input", "TXD3", 16), None,
     ("bidirectional", "RXC/PHYAD1", 28), ("bidirectional", "RXCTL/PHYAD2", 27),
     ("bidirectional", "RXD0/RXDLY", 26), ("bidirectional", "RXD1/CFG_MODE0", 25),
     ("bidirectional", "RXD2/CFG_MODE1", 24), ("bidirectional", "RXD3/CFG_MODE2", 23)]
R = [("bidirectional", "MDIP0", 2), ("bidirectional", "MDIN0", 3), ("bidirectional", "MDIP1", 5),
     ("bidirectional", "MDIN1", 6), ("bidirectional", "MDIP2", 7), ("bidirectional", "MDIN2", 8),
     ("bidirectional", "MDIP3", 10), ("bidirectional", "MDIN3", 11), None,
     ("bidirectional", "LED0/PHYAD0", 35), ("bidirectional", "LED1/CFG_LDO0", 36),
     ("bidirectional", "LED2/CFG_LDO1", 37), None,
     ("input", "XTAL_IN", 45), ("output", "XTAL_OUT", 46), ("output", "CLKOUT", 44), None,
     ("passive", "RSET", 48), ("power_out", "REG_OUT", 32), ("power_out", "DVDD_RG", 29)]
TOP = [("AVDD33", 1), ("AVDD33", 12), ("DVDD33", 30), ("VDD_REG", 31),
       ("AVDD10", 4), ("AVDD10", 9), ("AVDD10", 47), ("DVDD10", 22)]
pins = []
y = H - 3.81
for p in L:
    if p: pins.append(pin(p[0], -W - 2.54, y, 0, p[1], p[2]))
    y -= 2.54
y = H - 3.81
for p in R:
    if p: pins.append(pin(p[0], W + 2.54, y, 180, p[1], p[2]))
    y -= 2.54
x = -8.89
for name, num in TOP:
    pins.append(pin("power_in", x, H + 2.54, 270, name, num)); x += 2.54
pins.append(pin("power_in", 0, -H - 2.54, 90, "GND", 49))
phy = symbol("RTL8211FSI-CG", "U", "Gigabit Ethernet PHY with SGMII, industrial (-40 to 85 C), QFN-48 6x6 mm",
             "Pin table from the Realtek RTL8211FS(I)(-VS) datasheet Rev. 1.8 (2021), section 6 (Tables 1-10) and "
             "Figure 8; pin 49 is the exposed pad (ground). DVDD_RG is the internal LDO's output when CFG_LDO is not 00 "
             "(section 7.18), hence power_out. LCSC C2904132.",
             "Package_DFN_QFN:QFN-48-1EP_6x6mm_P0.4mm_EP4.4x4.4mm", W, H, pins)

# ---- HR911130C
W2, H2 = 10.16, 20.32
JL = [("CT", 1), ("MDI0+", 2), ("MDI0-", 3), ("MDI1+", 4), ("MDI1-", 7), ("MDI2+", 5), ("MDI2-", 6),
      ("MDI3+", 8), ("MDI3-", 9), None, ("CHS_GND", 10), ("SHIELD", "SH"), None,
      ("LEDG_A", 11), ("LEDG_K", 12), ("LEDY_A", 14), ("LEDY_K", 13)]
pins = []
y = H2 - 2.54
for p in JL:
    if p: pins.append(pin("passive", -W2 - 2.54, y, 0, p[0], p[1]))
    y -= 2.54
jack = symbol("HR911130C", "J", "RJ45 jack, 10/100/1000Base-T, integrated magnetics, green and yellow LEDs, right angle",
              "HanRun HR911130C drawing Rev. B: chip-side pins 1-10 (1 the windings' centre taps, 10 chassis ground "
              "via the 1000 pF / 4 x 75 ohm termination), LEDs green 11 (A) 12 (K), yellow 14 (A) 13 (K), shield SH. LCSC C50933.",
              "kv260-ias2rf:RJ45_Hanrun_HR911130C", W2, H2, pins)

t = open(LIB, encoding="utf-8").read()
for name, block in (("RTL8211FSI-CG", phy), ("HR911130C", jack)):
    i = t.find(f'\n\t(symbol "{name}"\n')
    if i >= 0:
        j = t.find('\n\t(symbol "', i + 5); j = j if j > 0 else t.rfind("\n)")
        t = t[:i] + "\n" + block + t[j:]
    else:
        k = t.rfind("\n)"); t = t[:k] + "\n" + block + t[k:]
open(LIB, "w", encoding="utf-8", newline="\n").write(t)
print("symbols written")
