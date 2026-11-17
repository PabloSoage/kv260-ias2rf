"""
IAS_LINK sheet - the connection specification. See docs/IAS_LINK_SPEC.md.

J101: the Hirose BM20B(0.8)-34DP on the KV260's IAS1 (J8), the functional
connector. J102: the same part on IAS0 (J7), mechanical only - reached from
the SOM only through the carrier's AP1302 (B-01, INTERFACE_SPEC §3.1), so
nothing but its grounds is connected.

Pin allocation: INTERFACE_SPEC §2-§4, frozen and verified against the
carrier schematic XTP682 sheet 13, polarity included (§3.1). Pairs 26/27 and
29/30 are N-before-P on both sides; the labels here say which is which.

All five pairs are AC-coupled (INTERFACE_SPEC §6.1: the SOM's HPA bank is at
1.2 V, the FPGA's LVDS is not). The two pairs the FPGA RECEIVES then need a
termination that also sets their common mode: 2 x 49.9 ohm per pair with the
centre at +1V2, decoupled. The three pairs the Kria receives are terminated
and biased inside the SOM (constraints: DIFF_TERM_ADV, DQS_BIAS - to confirm
in AMD's UltraScale+ SelectIO guide).
"""

from kit import R, C

HIROSE = ("Connector_Generic:Conn_02x17_Odd_Even", "BM20B(0.8)-34DP",
          "kv260-ias2rf:J-BM20B(0.8)-34DP")   # _work/make_footprints.py

PARTS = {
    "J101": (*HIROSE, "IAS1 (J8 on the KV260): the link. Footprint as the original layout"),
    "J102": (*HIROSE, "IAS0 (J7): mechanical and ground only (INTERFACE_SPEC §1.1 of ARCHITECTURE)"),
}
# pair name -> (P pin, N pin, towards the Kria?)
PAIRS = {
    "LINK_RX_D0": (4, 5, True),
    "LINK_RX_CLK": (7, 8, True),       # HPA05_CC: clock capable (§3)
    "LINK_RX_D1": (30, 29, True),      # N before P on the connector
    "LINK_TX_D0": (27, 26, False),     # N before P
    "LINK_TX_CLK": (10, 11, False),
}
# What the carrier puts on each single-ended pin (XTP682 sheets 8 and 13, read
# 25 Sep 2026): 14/22 IAS1_I2C_SCK/SDA through the TCA9546A, 2.21 k to PL_1V8;
# 21 IAS1_RESET_B from the SLG7XL46528 (SOM pin HDA04), 10 k to PL_1V8;
# 15 HPA13_FLASH, an INPUT to the SOM through an SN74AVC4T245 (A side at
# 1.8 V, 2DIR high); 20 HPA13_TRIGGER, an output of the SOM through the same
# part (1DIR low); 32 IAS1_EXTCLK, the Si5332's 48 MHz OUT2b, always on.
# So the interrupt goes on 15: pin 32 is a clock the carrier drives.
SINGLE = {"HK_SCL": (14, "bidirectional"), "HK_SDA": (22, "bidirectional"),
          "FPGA_PROG_B": (21, "output"), "FPGA_IRQ": (15, "input")}
GND_PINS = (2, 3, 6, 9, 12, 16, 19, 25, 28, 31, 33)
# Carrier rails (13: PL_1V8, 17/18: IAS_2V75, 23/24: PL_1V2): the adapter takes
# no power from the connector (ARCHITECTURE §9.1). 1: test point on the
# carrier. 20: HPA13_TRIGGER, unused. 32: the carrier's clock, not taken.
# 34: VDD_AF2V8 through the carrier's unfitted jumper J19.
NC_PINS = (1, 13, 17, 18, 20, 23, 24, 32, 34)

cap = 101
REFS = {}
for name, (pp, pn, to_kria) in PAIRS.items():
    r = {"cp": f"C{cap}", "cn": f"C{cap + 1}"}
    cap += 2
    PARTS[r["cp"]] = C("100n", "INTERFACE_SPEC §6.1: series AC coupling on every pair "
                               "(0 ohm as the alternative stuffing if VCCO_HPA proves 1.8 V)")
    PARTS[r["cn"]] = C("100n", "Same")
    REFS[name] = r
term = 101
for name in ("LINK_TX_D0", "LINK_TX_CLK"):
    r = REFS[name]
    r.update({"rp": f"R{term}", "rn": f"R{term + 1}", "cc": f"C{cap}"})
    PARTS[r["rp"]] = R("49.9", "Receiver termination, half of 100 ohm; centre at +1V2 sets "
                               "the common mode the AC coupling removed")
    PARTS[r["rn"]] = R("49.9", "Same")
    PARTS[r["cc"]] = C("100n", "Decouples the termination's centre at the resistors")
    term += 2
    cap += 1

HIER = {**{f"{n}_{s}": ("input" if tk else "output") for n, (_, _, tk) in PAIRS.items()
           for s in "PN"},
        **{n: shape for n, (_, shape) in SINGLE.items()}}
POWER = ["+1V2", "GND"]

NETS = {"GND": [f"J101.{p}" for p in GND_PINS] + [f"J102.{p}" for p in GND_PINS], "+1V2": []}
for name, (pp, pn, to_kria) in PAIRS.items():
    r = REFS[name]
    NETS[f"J_{name}_P"] = [f"J101.{pp}", f"{r['cp']}.2"]
    NETS[f"J_{name}_N"] = [f"J101.{pn}", f"{r['cn']}.2"]
    NETS[f"{name}_P"] = [f"{r['cp']}.1"]
    NETS[f"{name}_N"] = [f"{r['cn']}.1"]
    if not to_kria:
        NETS[f"{name}_P"] += [f"{r['rp']}.1"]
        NETS[f"{name}_N"] += [f"{r['rn']}.2"]
        NETS["+1V2"] += [f"{r['rp']}.2", f"{r['rn']}.1", f"{r['cc']}.1"]
        NETS["GND"] += [f"{r['cc']}.2"]
for name, (pin, _) in SINGLE.items():
    NETS[name] = [f"J101.{pin}"]

NO_CONNECT = [f"J101.{p}" for p in NC_PINS] + [
    f"J102.{p}" for p in range(1, 35) if p not in GND_PINS]

# ---- Rev08 (REV08_PLAN 4.3, _work/rev08_schematic.py): J103, the camera pass-through receptacle on the top face.
# Every contact of J102 (IAS0, the carrier's J7) goes to the same contact of J103, so an IAS camera module plugged
# into J103 sees the carrier exactly as on the bare KV260. Nothing else on the adapter touches these nets.
PARTS["J103"] = ("Connector_Generic_MountingPin:Conn_02x17_Odd_Even_MountingPin", "BM20B(0.8)-34DS-0.4V(51)",
                 "kv260-ias2rf:CONN-SMD_34P-P0.40_BM20B-0.8-34DS-0.4V-51",
                 "IAS0 camera pass-through receptacle, contact for contact with J102")
IAS0 = {1: "IAS0_P1", 4: "IAS0_D0_4", 5: "IAS0_D0_5", 7: "IAS0_CLK_7", 8: "IAS0_CLK_8", 10: "IAS0_D3_10",
        11: "IAS0_D3_11", 13: "IAS0_PL_1V8", 14: "IAS0_SCL", 15: "IAS0_FLASH", 17: "IAS0_2V75", 18: "IAS0_2V75",
        20: "IAS0_TRIGGER", 21: "IAS0_RESET", 22: "IAS0_SDA", 23: "IAS0_PL_1V2", 24: "IAS0_PL_1V2",
        26: "IAS0_D2_26", 27: "IAS0_D2_27", 29: "IAS0_D1_29", 30: "IAS0_D1_30", 32: "IAS0_EXTCLK",
        34: "IAS0_VDD_AF2V8"}
for _p, _n in IAS0.items():
    NETS.setdefault(_n, []).extend([f"J102.{_p}", f"J103.{_p}"])
NETS["GND"] += [f"J103.{p}" for p in GND_PINS] + ["J103.MP"]
NO_CONNECT = [p for p in NO_CONNECT if not (p.startswith("J102.") and int(p[5:]) in IAS0)]
