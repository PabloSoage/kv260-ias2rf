#!/usr/bin/env python3
"""
Rev08 symbols for the project library (16 Nov 2026): the VHF/UHF front end (REV08_PLAN section 5), the
I2C expanders (sections 3.1 and 5.8). Appended to symbols/kv260-ias2rf.kicad_sym, or replaced in place.

Every pin table was read from the maker's data sheet, as fetched through JLCPCB's parts API on 16 Nov 2026
and kept (not committed) in _work/datasheets/rev08/:

  SPF5043Z        Qorvo data sheet (June 2018) p.13 "Pin Configuration and Description"
  PE4259          pSemi DOC-03694-3 Table 2; single-pin control: CTRL high = RFC-RF1 (Table 5)
  PE42442         pSemi DOC-...; Table 2 and Table 5A (2-pin control, V3 = pin 19 grounded):
                  V2 V1 = 00 RF1, 01 RF2, 10 RF3, 11 RF4
  SKY13418-485LF  Skyworks 201712F Table 1, Table 4: V1 V2 V3 = 000 RF1 ... 111 RF8 (V3 the LSB)
  PE4312          pSemi DOC-81482-2 Table 2; serial mode with P/S high
  RFFC5072        RFMD DS140110 p.5 "Pin Names and Descriptions"; mixer 2 only (13, 14, 17, 18 are NC)
  AP22652W6-7     Diodes DS41186 Rev.2 "Pin Descriptions", SOT26 column; EN is ACTIVE LOW on the AP22652
  TCA6416ARTW     TI ZHCSM91F Table 5-1, QFN (RTW) column; pad 25 the exposed thermal pad
  TC4-1W+         Mini-Circuits REV.F "Pin Connections": primary dot 6, primary 4, secondary dot 1,
                  secondary 3, secondary CT 2 (impedance ratio 4, secondary/primary)
  TC1-1-13M+      Mini-Circuits case AT224-1A, the same pad pattern: primary 6 / 4, secondary 1 / 3, pad 2 not used
  TA1090EC        Tai-Saw SAW, SMD3838-6P: no data sheet on the API; pins from LCSC's EasyEDA symbol
                  (C20415295): 2 IN, 5 OUT, 1/3/4/6 GND. Second-hand: check against the maker's drawing
  1XXD26000MAA    KDS DSB211SDN family (2.0 x 1.6 mm): 1 Vcont / GND / standby (by variant), 2 GND,
                  3 output, 4 Vcc

Usage:  py _work/rev08_symbols.py
"""
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB = os.path.join(ROOT, "symbols", "kv260-ias2rf.kicad_sym")
T = "\t"


def pin(kind, x, y, ang, name, num):
    # the same text as _work/make_eth_symbols.py writes (that script writes the library when imported)
    return (f'{T*3}(pin {kind} line\n{T*4}(at {x:.2f} {y:.2f} {ang})\n{T*4}(length 2.54)\n'
            f'{T*4}(name "{name}" (effects (font (size 1.27 1.27))))\n'
            f'{T*4}(number "{num}" (effects (font (size 1.27 1.27))))\n{T*3})')


def prop(name, val, x=0, y=0, hide=True):
    return (f'{T*2}(property "{name}" "{val}"\n{T*3}(at {x} {y} 0)\n'
            f'{T*3}(effects (font (size 1.27 1.27)) (hide {"yes" if hide else "no"}))\n{T*2})')


SRC = "Pin table read from the maker's data sheet (JLCPCB parts API copy, 16 Nov 2026); see _work/rev08_symbols.py"


def body(name, ref, desc, fp, w, h, pins, source=SRC):
    out = [f'{T}(symbol "{name}"', f'{T*2}(pin_names (offset 0.508))', f'{T*2}(exclude_from_sim no)',
           f'{T*2}(in_bom yes)', f'{T*2}(on_board yes)',
           prop("Reference", ref, 0, h + 1.27, False), prop("Value", name, 0, -h - 1.27, False),
           prop("Footprint", fp), prop("Datasheet", ""), prop("Description", desc),
           prop("ki_keywords", "kv260-ias2rf"), prop("SymbolSource", source),
           f'{T*2}(symbol "{name}_0_1"\n{T*3}(rectangle\n{T*4}(start {-w:.2f} {h:.2f})\n{T*4}(end {w:.2f} {-h:.2f})\n'
           f'{T*4}(stroke (width 0.254) (type default))\n{T*4}(fill (type background))\n{T*3})\n{T*2})',
           f'{T*2}(symbol "{name}_1_1"'] + pins + [f'{T*2})', f'{T})']
    return "\n".join(out)


def make(name, ref, desc, fp, left=(), right=(), top=(), bottom=(), w=None, source=SRC):
    """Sides are lists of (type, pin name, number) or None (a gap), listed top to bottom (left/right) and
    left to right (top/bottom). The body is sized to fit; every pin end lands on the 1.27 mm grid."""
    n_side = max(len(left), len(right), 2)
    n_tb = max(len(top), len(bottom), 1)
    h = 2.54 * ((n_side + 1) // 2) + 1.27 * ((n_side + 1) % 2) + 1.27
    h = round(h / 1.27) * 1.27
    h += 5.08 if (top or bottom) else 0                 # room for the top/bottom pins' names inside
    w = w or max(7.62, round((2.54 * (n_tb + 1) / 2) / 2.54) * 2.54)
    pins = []
    y0 = 1.27 * (n_side - 1)
    for side, x, ang in ((left, -w - 2.54, 0), (right, w + 2.54, 180)):
        y = y0
        for p in side:
            if p:
                pins.append(pin(p[0], x, y, ang, p[1], p[2]))
            y -= 2.54
    for side, y, ang in ((top, h + 2.54, 270), (bottom, -h - 2.54, 90)):
        x = -1.27 * (len(side) - 1)
        for p in side:
            if p:
                pins.append(pin(p[0], x, y, ang, p[1], p[2]))
            x += 2.54
    return body(name, ref, desc, fp, w, h, pins, source)


P, I, O, B, PW, NC, OC = "passive", "input", "output", "bidirectional", "power_in", "no_connect", "open_collector"
FP = "kv260-ias2rf:"
SYMS = [
    make("SPF5043Z", "U", "Low-noise amplifier 50-4000 MHz, GaAs pHEMT, SOT-343; drain fed through RF OUT",
         FP + "SOT343_L2.0-W1.3-P1.30-LS2.1-BL",
         left=[(P, "RF_IN", 3)], right=[(P, "RF_OUT", 1)], bottom=[(PW, "GND", 2), (PW, "GND", 4)]),
    make("PE4259", "U", "SPDT RF switch 10 MHz-3 GHz, SC-70-6; single-pin control: CTRL high = RFC-RF1",
         FP + "SC-70-6_L2.2-W1.3-P0.65-LS2.1-BL",
         left=[(P, "RFC", 5), None, (I, "CTRL", 4)], right=[(P, "RF1", 1), None, (P, "RF2", 3)],
         top=[(PW, "VDD", 6)], bottom=[(PW, "GND", 2)]),
    make("PE42442", "U", "SP4T RF switch 30 MHz-6 GHz, QFN-24 4x4; 2-pin control (V3 grounded): V2V1 00 RF1 .. 11 RF4",
         FP + "QFN-24_L4.0-W4.0-P0.50-BL-EP2.8",
         left=[(P, "RFC", 22), None, (I, "V1", 17), (I, "V2", 18), (I, "V3", 19), (I, "VSS_EXT", 20)],
         right=[(P, "RF1", 14), (P, "RF2", 11), (P, "RF3", 8), (P, "RF4", 5)],
         top=[(PW, "VDD", 16)],
         bottom=[(PW, "GND", n) for n in (1, 2, 3, 4, 6, 7, 9, 10, 12, 13, 15, 21, 23, 24, 25)]),
    make("SKY13418-485LF", "U", "SP8T RF switch 0.1-6.0 GHz, QFN-14 2x2; V1V2V3 = 000 RF1 .. 111 RF8",
         FP + "QFN-14_L2.0-W2.0-P0.45-BL-EP",
         left=[(P, "ANT", 13), None, (I, "V1", 7), (I, "V2", 6), (I, "V3", 5), (NC, "N/C", 8)],
         right=[(P, f"RF{k}", n) for k, n in ((1, 3), (2, 9), (3, 2), (4, 10), (5, 1), (6, 11), (7, 14), (8, 12))],
         top=[(PW, "VDD", 4)], bottom=[(PW, "GND", 15)]),
    make("PE4312", "U", "Digital step attenuator 1 MHz-4 GHz, 0-31.5 dB in 0.5 dB, QFN-20 4x4; serial with P/S high",
         FP + "QFN-20_L4.0-W4.0-P0.50-BL-EP2.2",
         left=[(P, "RF1", 2), None, (I, "DATA", 3), (I, "CLOCK", 4), (I, "LE", 5), (I, "P/S", 13), None,
               (I, "PUP1", 7), (I, "PUP2", 8), (I, "VSS_EXT/GND", 12)],
         right=[(P, "RF2", 14), None, (I, "C0.5", 20), (I, "C1", 19), (I, "C2", 17), (I, "C4", 16), (I, "C8", 15),
                (I, "C16", 1)],
         top=[(PW, "VDD", 6), (PW, "VDD", 9)], bottom=[(PW, "GND", n) for n in (10, 11, 18, 21)]),
    make("RFFC5072", "U", "Wideband synthesiser and mixer, LO 85-4200 MHz, QFN-32 5x5; mixer 2 only",
         "Package_DFN_QFN:QFN-32-1EP_5x5mm_P0.5mm_EP3.45x3.45mm",
         left=[(P, "MIX2_IPP", 23), (P, "MIX2_IPN", 24), None, (I, "REF_IN", 10), None,
               (I, "ENX", 30), (I, "SCLK", 31), (B, "SDATA", 32), (I, "ENBL/GPO5", 1), (I, "MODE/GPO6", 9),
               (I, "RESETX", 29), None, (P, "REXT", 4), (P, "EXT_LO", 2), (P, "EXT_LO_DEC", 3), (I, "TM", 12)],
         right=[(O, "MIX2_OPP", 28), (O, "MIX2_OPN", 27), None, (P, "LFILT1", 6), (P, "LFILT2", 7), (P, "LFILT3", 8),
                None, (O, "GPO4/LD/DO", 26), (B, "GPO3/FM", 25), (O, "GPO1/ADD1", 15), (O, "GPO2/ADD2", 16), None,
                (NC, "NC", 11), (NC, "NC", 13), (NC, "NC", 14), (NC, "NC", 17), (NC, "NC", 18), (NC, "NC", 20),
                (NC, "NC", 21)],
         top=[(PW, "ANA_VDD1", 5), (PW, "ANA_VDD2", 22), (PW, "DIG_VDD", 19)], bottom=[(PW, "GND", 33)], w=15.24),
    make("AP22652W6", "U", "Current-limited load switch, adjustable 125 mA-2.1 A, ACTIVE-LOW enable, SOT-26",
         FP + "SOT-23-6_L2.9-W1.6-P0.95-LS2.8-BL",
         left=[(PW, "IN", 1), None, (I, "~{EN}", 3), (P, "ILIM", 5)], right=[(O, "OUT", 6), None, (OC, "~{FAULT}", 4)],
         bottom=[(PW, "GND", 2)]),
    make("TCA6416ARTW", "U", "16-bit I2C I/O expander with two supply levels, WQFN-24 4x4",
         FP + "WQFN-24_L4.0-W4.0-P0.50-TL-EP2.5",
         left=[(I, "SCL", 19), (B, "SDA", 20), (OC, "~{INT}", 22), (I, "~{RESET}", 24), (I, "ADDR", 18), None]
              + [(B, f"P0{k}", 1 + k) for k in range(8)],
         right=[(B, f"P1{k}", 10 + k) for k in range(8)],
         top=[(PW, "VCCI", 23), (PW, "VCCP", 21)], bottom=[(PW, "GND", 9), (PW, "EP", 25)]),
    make("TA1090EC", "FL", "SAW band-pass 1090 MHz, 30 MHz wide, 50 ohm, SMD 3.8 x 3.8 mm",
         FP + "FILTER-SMD_6P-L3.8-W3.8-P1.27-TL-3",
         left=[(P, "IN", 2)], right=[(P, "OUT", 5)], bottom=[(P, "GND", n) for n in (1, 3, 4, 6)],
         source="LCSC EasyEDA symbol for C20415295 (no data sheet on the parts API): 2 IN, 5 OUT, others GND"),
    make("TC4-1W+", "T", "RF transformer 4:1 (secondary/primary impedance), 3-800 MHz, secondary centre tap",
         FP + "XFMR-SMD_TC1-1TX",
         left=[(P, "PRI_DOT", 6), None, (P, "PRI", 4)], right=[(P, "SEC_DOT", 1), None, (P, "SEC", 3)],
         bottom=[(P, "SEC_CT", 2)]),
    make("TC1-1-13M+", "T", "RF transformer 1:1, 4.5-3000 MHz, case AT224-1A (pad 2 not used)",
         FP + "XFMR-SMD_TC1-1TX",
         left=[(P, "PRI_DOT", 6), None, (P, "PRI", 4)], right=[(P, "SEC_DOT", 1), None, (P, "SEC", 3)],
         bottom=[(NC, "NC", 2)]),
    make("TCXO_2016_4P", "Y", "TCXO 2.0 x 1.6 mm, clipped sine; pin 1 Vcont / GND / standby by variant",
         FP + "OSC-SMD_4P-L2.0-W1.6-BL",
         left=[(P, "VC/EN", 1)], right=[(O, "OUT", 3)], top=[(PW, "VCC", 4)], bottom=[(PW, "GND", 2)]),
]


def main():
    t = open(LIB, encoding="utf-8").read()
    for block in SYMS:
        name = block.split('"')[1]
        i = t.find(f'\n\t(symbol "{name}"\n')
        if i >= 0:
            j = t.find('\n\t(symbol "', i + 5)
            j = j if j > 0 else t.rfind("\n)")
            t = t[:i] + "\n" + block + t[j:]
        else:
            k = t.rfind("\n)")
            t = t[:k] + "\n" + block + t[k:]
    open(LIB, "w", encoding="utf-8", newline="\n").write(t)
    print(f"{len(SYMS)} symbols written to {os.path.relpath(LIB, ROOT)}")


if __name__ == "__main__":
    main()
