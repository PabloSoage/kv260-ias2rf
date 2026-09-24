"""
DAC_RADAR sheet - the connection specification. See docs/DAC_RADAR_SPEC.md.

  DACR_D0..7, DACR_CLK (FPGA, 3.3 V CMOS) -> U701 AD9708 -> IOUTA/IOUTB
    -> 50 ohm loads -> AERIS-10's differential LC reconstruction filter
    -> T701 balun -> IF_TX_B, single-ended 50 ohm, to the routing switch.

The output network is AERIS-10's (R115/R116, C308/C309, C127, L22/L25,
C141, L26/L27, C59: _work/aeris_reference_circuit.py L26 L27 C141), which
fed its LTC5552 mixer differentially. Here a balun follows it, because the
routing switch and the SMAs are single-ended.

The reference is NOT AERIS's. AERIS ties REFLO to AVDD (internal reference
off) and REFIO to +3.3 V: an external reference of 3.3 V, outside the
datasheet's reference-input compliance range of 0.1-1.25 V. Here the
internal 1.2 V reference is used, as the datasheet describes: REFLO to
ACOM, 0.1 uF on REFIO, and RSET on FS ADJ.
"""

from kit import R, C, C0805

PARTS = {
    "U701": ("kv260-ias2rf:AD9708AR", "AD9708AR", "Package_SO:SOIC-28W_7.5x17.9mm_P1.27mm",
             "Radar DAC, AERIS-10's part. R-28: body 17.70-18.10 x 7.40-7.60 mm (outline)"),
    "C701": C("100n", "AD9708 pin 19: 'COMP1 ... Add 0.1 uF to AVDD' (AERIS C39)"),
    "C702": C("10u", "AD9708 Figure 22: bulk on AVDD (10-22 uF tantalum there; ceramic here)",
              C0805),
    "C703": C("100n", "AD9708 p.10: AVDD decoupled to ACOM as close to the chip as possible"),
    "C704": C("100n", "AD9708 p.10: DVDD decoupled to DCOM as close as possible"),
    "C705": C("100n", "AD9708 pin 17: REFIO 'requires 0.1 uF capacitor to ACOM when internal "
                      "reference activated'"),
    "R701": R("1.91k 1%", "Full scale IOUTFS = 32 x VREFIO / RSET (Table 1 note 2): "
                          "32 x 1.20 V / 1.91 kohm = 20.1 mA, the rated maximum"),
    "C706": C("100n", "AD9708 pin 23: COMP2 'Decouple to ACOM with 0.1 uF' (AERIS C38)"),
    # output: AERIS-10's network, then a balun
    "R702": R("49.9", "Load, IOUTA to ground: AERIS R116 (50 ohm). 20 mA x 49.9 = 1.0 V, "
                      "inside the 1.25 V output compliance (Table 1)"),
    "R703": R("49.9", "Load, IOUTB to ground: AERIS R115"),
    "C707": C("22p", "AERIS C309, IOUTA to ground. C0G"),
    "C708": C("22p", "AERIS C308, IOUTB to ground. C0G"),
    "C709": C("33p", "AERIS C127 (32.8 pF as designed; nearest E12). C0G"),
    "L701": ("Device:L", "107.3n", "Inductor_SMD:L_0603_1608Metric", "AERIS L22 (107.3 nH)"),
    "L702": ("Device:L", "107.3n", "Inductor_SMD:L_0603_1608Metric", "AERIS L25"),
    "C710": C("106p", "AERIS C141 (106 pF as designed: 100 p + 5.6 p, or nearest). C0G"),
    "L703": ("Device:L", "107.3n", "Inductor_SMD:L_0603_1608Metric", "AERIS L26"),
    "L704": ("Device:L", "107.3n", "Inductor_SMD:L_0603_1608Metric", "AERIS L27"),
    "C711": C("33p", "AERIS C59 (32.8 pF), at the far end of the filter. C0G"),
    "T701": ("Device:Transformer_1P_1S", "balun 2:1 Z, 100R:50R", "",
             "Judgement, part not chosen: 100 ohm differential (two 50 ohm loads) to 50 ohm "
             "single-ended, passband covering the chirp. Footprint with the part"),
}

DATA = {f"DACR_D{i}": pin for i, pin in zip(range(8), (8, 7, 6, 5, 4, 3, 2, 1))}
HIER = {**{k: "input" for k in DATA}, "DACR_CLK": "input", "IF_TX_B": "output"}
POWER = ["+3V3_A", "+3V3_D", "GND"]

NETS = {
    "+3V3_A": ["U701.24", "C701.1", "C702.1", "C703.1"],
    "+3V3_D": ["U701.27", "C704.1"],
    "GND": ["C702.2", "C703.2", "C704.2", "C705.2", "R701.2", "C706.2", "U701.15",
            "U701.16", "U701.20", "U701.26", "R702.2", "R703.2", "C707.2", "C708.2", "T701.3"],
    "COMP1": ["U701.19", "C701.2"],
    "REFIO": ["U701.17", "C705.1"],
    "FS_ADJ": ["U701.18", "R701.1"],
    "COMP2": ["U701.23", "C706.1"],
    "DACR_CLK": ["U701.28"],
    **{k: [f"U701.{p}"] for k, p in DATA.items()},
    "IOUTA": ["U701.22", "R702.1", "C707.1", "C709.1", "L701.1"],
    "IOUTB": ["U701.21", "R703.1", "C708.1", "C709.2", "L702.1"],
    "F1_P": ["L701.2", "C710.1", "L703.1"],
    "F1_N": ["L702.2", "C710.2", "L704.1"],
    "F2_P": ["L703.2", "C711.1", "T701.1"],
    "F2_N": ["L704.2", "C711.2", "T701.2"],
    "IF_TX_B": ["T701.4"],
}
NO_CONNECT = [f"U701.{p}" for p in (9, 10, 11, 12, 13, 14, 25)]
