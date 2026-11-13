#!/usr/bin/env python3
"""
Rev06: Ethernet on its own FPGA pins, IAS1 complete (13 Nov 2026; fpga/eth/REDUNDANCY.md section 4,
docs/CONTROL_SPEC.md section 7).

Rev05 shared two IAS1 pairs with the PHY by an assembly option (C1218-C1221 DNP, C101/C102/C107/C108 to
be removed for Ethernet). Rev06 gives the PHY its own bank-34 pairs, on the OUTER ring of the BGA so they
can be escaped (Rev05 could not escape any inner free ball). Chosen by what the board allows: T4/T3 and
N1 are walled in by matched LVDS legs; R2/R1 escape with a via in each ball, and R3 does once a
LINK_RX_D0_N skew meander that ran under the corner is moved:

  ETH_SGTX_FPGA_P/N  R2 / R1 (IO_L7P/N_T1_34), LVDS_25 out  -> C1220/C1221 (at the PHY) -> HSIP/N
  ETH_SGRX_FPGA_P/N  R3 / T2 (IO_L8P/N_T1_34), LVDS_25 in, DIFF_TERM <- C1218/C1219 <- HSOP/N;
                     R1215/R1216 10 k to +1V2 restore the common mode the capacitors remove
                     (the scheme of R101-R104 on LINK_TX)
  ETH_MDC            P1 (IO_L4N_T0_34), LVCMOS25 (the PHY's I/O run at 2.5 V: CFG_LDO = 01)
  ETH_MDIO           M15 (IO_L3N_T0_DQS_EMCCLK_14), LVCMOS33 driven OPEN-DRAIN (the gateware only pulls low);
                     R1213 1.5 k pulls it up to ETH_DVDDRG (2.5 V), which the 3.3 V bank reads as high (VIH 2.0 V),
                     so the PHY never sees 3.3 V. P5, the 2.5 V choice, sits on a +3V3_D run that feeds ball L6
  ETH_RSTN           K13 (IO_L5P_T0_D06_14), LVCMOS33; R1214/C1216 power-on reset stays,
                     the FPGA can hold the PHY in reset or release it
  INTB               open, as before (the gateware polls MDIO)

C1218-C1221 are fitted; C101, C102, C107, C108 stay fitted: IAS1 keeps both uplink lanes and its downlink.
Text edit of rev03/CONTROL.kicad_sch with add_ethernet.py's helpers. Refuses to run twice.

Usage:  py _work/rev06_eth.py
"""
import os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "_work"))
import add_ethernet as AE                                          # noqa: E402

AE.BALLS = {"R2": "ETH_SGTX_FPGA_P", "R1": "ETH_SGTX_FPGA_N", "R3": "ETH_SGRX_FPGA_P", "T2": "ETH_SGRX_FPGA_N",
            "P1": "ETH_MDC", "M15": "ETH_MDIO", "K13": "ETH_RSTN"}
# cap -> (pin, old net, new net): the side that used to tap the IAS1 pair
RELABEL = {"C1218": ("2", "LINK_TX_D0_P", "ETH_SGRX_FPGA_P"), "C1219": ("2", "LINK_TX_D0_N", "ETH_SGRX_FPGA_N"),
           "C1220": ("1", "LINK_RX_D0_P", "ETH_SGTX_FPGA_P"), "C1221": ("1", "LINK_RX_D0_N", "ETH_SGTX_FPGA_N")}
DESC = {"C1218": "SGMII PHY -> FPGA, AC coupling (Rev06: own pins R3/T2)",
        "C1219": "SGMII PHY -> FPGA, AC coupling (Rev06: own pins R3/T2)",
        "C1220": "SGMII FPGA -> PHY, AC coupling (Rev06: own pins R2/R1)",
        "C1221": "SGMII FPGA -> PHY, AC coupling (Rev06: own pins R2/R1)"}


def highest(tag):
    n = 0
    for f in os.listdir(os.path.join(ROOT, "rev03")):
        if f.endswith(".kicad_sch"):
            for m in re.finditer(r'"' + tag + r'(\d+)"', open(os.path.join(ROOT, "rev03", f), encoding="utf-8").read()):
                n = max(n, int(m.group(1)))
    return n


def sym_block(t, ref):
    i = t.find(f'(property "Reference" "{ref}"'); s = t.rfind("\n\t(symbol", 0, i); e = t.find("\n\t)\n", i)
    return s, e


def main():
    s = AE.Sheet()
    if "ETH_SGTX_FPGA_P" in s.t: sys.exit("already applied")
    AE.PWR[0] = highest("#PWR")
    AE.balls(s)
    # relabel the caps' IAS1 side: the label sits on the cap's pin end
    pins = s.need("Device:C")
    for ref, (pin, old, new) in RELABEL.items():
        st, en = sym_block(s.t, ref)
        b = s.t[st:en]
        x, y, rot = map(float, re.search(r"\n\t\t\(at ([-\d.]+) ([-\d.]+) ([-\d.]+)\)", b).groups())
        assert rot == 0, ref
        px, py, _ = pins[pin]; X, Y = round(x + px, 2), round(y - py, 2)
        lab = re.compile(r'\(label "' + re.escape(old) + r'"\s*\(at ' + re.escape(f"{X:g}") + r'\s+'
                         + re.escape(f"{Y:g}") + r'\s')
        m = lab.search(s.t)
        assert m, f"{ref}: no label {old} at ({X}, {Y})"
        s.t = s.t[:m.start()] + s.t[m.start():m.end()].replace(f'"{old}"', f'"{new}"') + s.t[m.end():]
        st, en = sym_block(s.t, ref)
        b = s.t[st:en].replace("(dnp yes)", "(dnp no)")
        b = re.sub(r'(\(property "Description" ")[^"]*(")', r"\g<1>" + DESC[ref] + r"\g<2>", b, count=1)
        s.t = s.t[:st] + b + s.t[en:]
    # the receiver's common-mode bias, beside the caps' grid
    st, en = sym_block(s.t, "C1218")
    x, y = map(float, re.search(r"\n\t\t\(at ([-\d.]+) ([-\d.]+)", s.t[st:en]).groups())
    AE.POWER["+1V2"] = ("power:+1V2", "+1V2")
    for k, (ref, net) in enumerate((("R1215", "ETH_SGRX_FPGA_P"), ("R1216", "ETH_SGRX_FPGA_N"))):
        p = s.inst("Device:R", ref, "10k", AE.R0402, x + 40.64 + 10.16 * k, y + 25.4,
                   "SGMII receiver common-mode bias to +1V2 (FPGA side of the AC caps)")
        s.connect(p["1"], net); s.connect(p["2"], "+1V2")
    # MDC is driven now: its pull-down only holds it during configuration
    st, en = sym_block(s.t, "R1211")
    s.t = s.t[:st] + s.t[st:en].replace("MDC pull-down: nothing drives it", "MDC pull-down while the FPGA configures") + s.t[en:]
    s.save()
    print("Rev06 Ethernet pins applied; #PWR up to", AE.PWR[0])


if __name__ == "__main__":
    main()
