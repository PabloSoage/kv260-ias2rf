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
SINGLE = {"HK_SCL": (14, "bidirectional"), "HK_SDA": (22, "bidirectional"),
          "FPGA_PROG_B": (21, "output"), "FPGA_IRQ": (32, "input")}
GND_PINS = (2, 3, 6, 9, 12, 16, 19, 25, 28, 31, 33)
# Carrier rails (13: VCC1V8, 17/18: VCC2V75, 23/24: VCC1V2) and free pins:
# the adapter takes no power from the connector (ARCHITECTURE §9.1).
NC_PINS = (1, 13, 15, 17, 18, 20, 23, 24, 34)

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
