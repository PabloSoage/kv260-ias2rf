"""
DAC_SDR sheet - the connection specification. See docs/DAC_SDR_SPEC.md.

  DACS_D0..13, DACS_IQWRT/IQSEL/IQCLK/IQRESET (FPGA, 3.3 V CMOS)
    -> U801 AD9767, interleaved mode (MODE low): one 14-bit port feeds both DACs
    -> DAC1 -> IF_TX_A,  DAC2 -> IF_TX_C
  each through the same output network as DAC_RADAR: 49.9 ohm loads,
  AERIS-10's differential LC filter, a 2:1 balun.

Datasheet: AD9763/AD9765/AD9767 Rev. G (_work/datasheets/AD9767.pdf).
"""

from kit import R, C, C0805

PARTS = {
    "U801": ("kv260-ias2rf:AD9767ASTZ", "AD9767ASTZ", "Package_QFP:LQFP-48_7x7mm_P0.5mm",
             "Dual 14-bit DAC, 48-lead LQFP (ST-48)"),
    "C801": C("100n", "p.22: 'To use the internal reference, simply decouple the REFIO pin to "
                      "ACOM with a 0.1 uF capacitor'"),
    "C804": C("10u", "Bulk on AVDD", C0805),
    "C805": C("100n", "AVDD pin 47 decoupling"),
    "C806": C("100n", "DVDD1 pin 16 decoupling"),
    "C807": C("100n", "DVDD2 pin 22 decoupling"),
    "C808": C("10u", "Bulk on DVDD", C0805),
}
# One full-scale network per DAC (GAINCTRL low = independent mode, p.22):
# RSET, and the 256 ohm + 22 nF series network the datasheet requires on
# each FSADJ (p.22, 'To ensure ... performs properly', Figure 59).
for k, (pin, rs, rn, cn) in enumerate(((44, "R801", "R802", "C802"), (41, "R803", "R804", "C803"))):
    PARTS[rs] = R("3.83k", "1 %. IOUTFS = 32 x 1.20 V / 3.83 kohm = 10.0 mA, so a 49.9 ohm load "
                              "sees 0.5 V: p.24, 'optimum distortion ... when the maximum "
                              "full-scale signal at IOUTA and IOUTB does not exceed 0.5 V'")
    PARTS[rn] = R("255", "Figure 59: 256 ohm (nearest E96)")
    PARTS[cn] = C("22n", "Figure 59: 22 nF")

# Output chains: (DAC, IOUTA pin, IOUTB pin, label, ref base)
CHAINS = [(1, 46, 45, "IF_TX_A", 810), (2, 39, 40, "IF_TX_C", 830)]
CHAIN_REFS = []
for dac, pa, pb, label, b in CHAINS:
    r = {"rp": f"R{b + 1}", "rn": f"R{b + 2}", "cp": f"C{b + 1}", "cn": f"C{b + 2}",
         "c1": f"C{b + 3}", "c3": f"C{b + 4}", "c5": f"C{b + 5}", "l1p": f"L{b + 1}",
         "l1n": f"L{b + 2}", "l2p": f"L{b + 3}", "l2n": f"L{b + 4}", "t": f"T80{dac}"}
    CHAIN_REFS.append((dac, pa, pb, label, r))
    L0603 = "Inductor_SMD:L_0603_1608Metric"
    PARTS.update({
        r["rp"]: R("49.9", f"DAC{dac} IOUTA load, as DAC_RADAR (AERIS R116)"),
        r["rn"]: R("49.9", f"DAC{dac} IOUTB load (AERIS R115)"),
        r["cp"]: C("22p", "AERIS C309. C0G"),
        r["cn"]: C("22p", "AERIS C308. C0G"),
        r["c1"]: C("33p", "AERIS C127 (32.8 pF). C0G"),
        r["l1p"]: ("Device:L", "107.3n", L0603, "AERIS L22"),
        r["l1n"]: ("Device:L", "107.3n", L0603, "AERIS L25"),
        r["c3"]: C("106p", "AERIS C141. C0G"),
        r["l2p"]: ("Device:L", "107.3n", L0603, "AERIS L26"),
        r["l2n"]: ("Device:L", "107.3n", L0603, "AERIS L27"),
        r["c5"]: C("33p", "AERIS C59 (32.8 pF). C0G"),
        r["t"]: ("Device:Transformer_1P_1S", "balun 2:1 Z, 100R:50R", "",
                 "As T701 on DAC_RADAR: part not chosen"),
    })

DATA = {f"DACS_D{i}": 14 - i for i in range(14)}     # DB13P1 = pin 1 ... DB0P1 = pin 14
CTRL = {"DACS_IQWRT": 17, "DACS_IQCLK": 18, "DACS_IQRESET": 19, "DACS_IQSEL": 20}
HIER = {**{k: "input" for k in DATA}, **{k: "input" for k in CTRL},
        "IF_TX_A": "output", "IF_TX_C": "output"}
POWER = ["+3V3_A", "+3V3_D", "GND"]

TIED_LOW = [48, 42, 37] + list(range(23, 37))     # MODE, GAINCTRL, SLEEP, port 2
NETS = {
    "+3V3_A": ["U801.47", "C804.1", "C805.1"],
    "+3V3_D": ["U801.16", "U801.22", "C806.1", "C807.1", "C808.1"],
    "GND": ["C801.2", "C804.2", "C805.2", "C806.2", "C807.2", "C808.2", "R801.2", "C802.2",
            "R803.2", "C803.2", "U801.38", "U801.15", "U801.21"]
           + [f"U801.{p}" for p in TIED_LOW],
    "REFIO": ["U801.43", "C801.1"],
    "FSADJ1": ["U801.44", "R801.1", "R802.1"],
    "FSADJ1_RC": ["R802.2", "C802.1"],
    "FSADJ2": ["U801.41", "R803.1", "R804.1"],
    "FSADJ2_RC": ["R804.2", "C803.1"],
    **{k: [f"U801.{p}"] for k, p in {**DATA, **CTRL}.items()},
}
for dac, pa, pb, label, r in CHAIN_REFS:
    NETS["GND"] += [f"{r['rp']}.2", f"{r['rn']}.2", f"{r['cp']}.2", f"{r['cn']}.2", f"{r['t']}.3"]
    NETS.update({
        f"IOUTA{dac}": [f"U801.{pa}", f"{r['rp']}.1", f"{r['cp']}.1", f"{r['c1']}.1", f"{r['l1p']}.1"],
        f"IOUTB{dac}": [f"U801.{pb}", f"{r['rn']}.1", f"{r['cn']}.1", f"{r['c1']}.2", f"{r['l1n']}.1"],
        f"F{dac}1_P": [f"{r['l1p']}.2", f"{r['c3']}.1", f"{r['l2p']}.1"],
        f"F{dac}1_N": [f"{r['l1n']}.2", f"{r['c3']}.2", f"{r['l2n']}.1"],
        f"F{dac}2_P": [f"{r['l2p']}.2", f"{r['c5']}.1", f"{r['t']}.1"],
        f"F{dac}2_N": [f"{r['l2n']}.2", f"{r['c5']}.2", f"{r['t']}.2"],
        label: [f"{r['t']}.4"],
    })
NO_CONNECT = []
