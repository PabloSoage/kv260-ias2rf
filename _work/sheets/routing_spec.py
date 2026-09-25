"""
ROUTING sheet - the connection specification. See docs/ROUTING_SPEC.md.

Four M3SWA2-34DR+ SPDTs. Each connects one converter port (RFC) to one of two
SMAs: RF1, the converter's own chain (the default: control low, pulled
down), or RF2, the other chain. The second SDR channels (IF_RX_C, IF_TX_C)
go straight to their SMAs.

  SW  converter  RF1 (control low, default)   RF2 (control high)
  1   IF_RX_A    SDR_RX_A  (SDR front end)     AERIS_IF_A  (radar IF into the 14-bit ADC)
  2   IF_RX_B    AERIS_IF  (radar IF)          SDR_RX_WB   (wideband SDR into the 8-bit ADC)
  3   IF_TX_A    SDR_TX_A  (SDR front end)     AERIS_TX_A  (14-bit chirp to AERIS)
  4   IF_TX_B    AERIS_TX  (radar chirp)       SDR_TX_WB   (8-bit DAC to the SDR)

Per switch, the datasheet's own "Characterization and Application Circuit"
(M3SWA2-34DR+ Rev. B, Figure 2): 11.5 ohm + 0.1 uF + 100 pF + 5.6 V zener on
each supply, 100 ohm in series with VCTRL; NC pads grounded as on its test
board. Every SMA port is DC-blocked: "All RF-ports must be DC blocked or held
at 0 V DC" (Electrical Specifications, note 3).
"""

from kit import R, C

SMA_FP = "Connector_Coaxial:SMA_Samtec_SMA-J-P-H-ST-EM1_EdgeMount"
SW_FP = "kv260-ias2rf:MiniCircuits_DQ3005"   # case DQ3005 (datasheet p.12), 3x3 mm QFN-16; layout PL-768

SWITCHES = [  # n, converter label, shape, RF1 name, RF2 name
    (1, "IF_RX_A", "output", "SDR_RX_A", "AERIS_IF_A"),
    (2, "IF_RX_B", "output", "AERIS_IF", "SDR_RX_WB"),
    (3, "IF_TX_A", "input", "SDR_TX_A", "AERIS_TX_A"),
    (4, "IF_TX_B", "input", "AERIS_TX", "SDR_TX_WB"),
]
DIRECT = [(1, "IF_RX_C", "output", "SDR_RX_C"), (2, "IF_TX_C", "input", "SDR_TX_C")]

PARTS = {}
REFS = {}
for n, lbl, shape, rf1, rf2 in SWITCHES:
    b = 900 + 10 * n
    r = {"u": f"U90{n}", "r_vdd": f"R{b + 1}", "r_vee": f"R{b + 2}", "r_ctl": f"R{b + 3}",
         "r_pd": f"R{b + 4}", "c_vdd1": f"C{b + 1}", "c_vdd2": f"C{b + 2}", "c_vee2": f"C{b + 3}",
         "c_vee1": f"C{b + 4}", "c_rf1": f"C{b + 5}", "c_rf2": f"C{b + 6}", "d_vdd": f"D{b + 1}",
         "d_vee": f"D{b + 2}", "j1": f"J{b + 1}", "j2": f"J{b + 2}"}
    REFS[n] = r
    PARTS.update({
        r["u"]: ("kv260-ias2rf:M3SWA2-34DR", "M3SWA2-34DR+", SW_FP,
                 "SPDT, DC-30 GHz. Mini-Circuits 3x3 mm QFN (case DG1677, PCB layout PL-768): "
                 "footprint at layout from PL-768"),
        r["r_vdd"]: R("11.5", "M3SWA2 Figure 2: R1 11.5 ohm in series with VDD"),
        r["r_vee"]: R("11.5", "M3SWA2 Figure 2: R2 11.5 ohm in series with VEE"),
        r["r_ctl"]: R("100", "M3SWA2 Figure 2: R3 100 ohm in series with VCTRL"),
        r["r_pd"]: R("10k", "Judgement: holds VCTRL low (RF1, the default chain) while the "
                            "FPGA is unconfigured. Control current is < 1 uA low (DC specs)"),
        r["c_vdd1"]: C("100n", "M3SWA2 Figure 2: C1 0.1 uF on VDD"),
        r["c_vdd2"]: C("100p", "M3SWA2 Figure 2: C2 100 pF on VDD. C0G"),
        r["c_vee2"]: C("100p", "M3SWA2 Figure 2: C3 100 pF on VEE. C0G"),
        r["c_vee1"]: C("100n", "M3SWA2 Figure 2: C4 0.1 uF on VEE"),
        r["c_rf1"]: C("100n", "DC block, RF1 SMA: note 3 of the Electrical Specifications. "
                              "100 nF into 50 ohm: corner 32 kHz, below the SDR's 100 kHz"),
        r["c_rf2"]: C("100n", "DC block, RF2 SMA (as above)"),
        r["d_vdd"]: ("Device:D_Zener", "5.6V", "Diode_SMD:D_SOD-123",
                     "M3SWA2 Figure 2: D1, VZ 5.6 V, SOD-123 (SZMMSZ5232BT1G)"),
        r["d_vee"]: ("Device:D_Zener", "5.6V", "Diode_SMD:D_SOD-123",
                     "M3SWA2 Figure 2: D2, VZ 5.6 V (SZMMSZ5232BT1G), reversed on the negative rail"),
        r["j1"]: ("Connector:Conn_Coaxial", rf1, SMA_FP, "RF1 port; edge-mount SMA"),
        r["j2"]: ("Connector:Conn_Coaxial", rf2, SMA_FP, "RF2 port; edge-mount SMA"),
    })
for k, lbl, shape, name in DIRECT:
    PARTS[f"C95{k}"] = C("100n", "DC block, as the switched ports")
    PARTS[f"J95{k}"] = ("Connector:Conn_Coaxial", name, SMA_FP,
                        "Second SDR channel, not switched; edge-mount SMA")

HIER = {**{lbl: shape for _, lbl, shape, _, _ in SWITCHES},
        **{lbl: shape for _, lbl, shape, _ in DIRECT},
        **{f"SW_CTRL{n - 1}": "input" for n, *_ in SWITCHES}}
POWER = ["+3V3_D", "-3V3", "GND"]

GND_PADS = (2, 4, 7, 9, 11, 14, 16, 17, 1, 12, 13)
NETS = {"+3V3_D": [], "-3V3": [], "GND": []}
for n, lbl, shape, rf1, rf2 in SWITCHES:
    r = REFS[n]
    u = r["u"]
    NETS["+3V3_D"] += [f"{r['r_vdd']}.1"]
    NETS["-3V3"] += [f"{r['r_vee']}.2"]
    NETS["GND"] += [f"{u}.{p}" for p in GND_PADS] + [
        f"{r['c_vdd1']}.2", f"{r['c_vdd2']}.2", f"{r['d_vdd']}.2", f"{r['c_vee1']}.1",
        f"{r['c_vee2']}.1", f"{r['d_vee']}.1", f"{r['r_pd']}.2", f"{r['j1']}.2", f"{r['j2']}.2"]
    NETS.update({
        f"VDD{n}": [f"{u}.8", f"{r['r_vdd']}.2", f"{r['c_vdd1']}.1", f"{r['c_vdd2']}.1",
                    f"{r['d_vdd']}.1"],
        f"VEE{n}": [f"{u}.5", f"{r['r_vee']}.1", f"{r['c_vee1']}.2", f"{r['c_vee2']}.2",
                    f"{r['d_vee']}.2"],
        f"SW_CTRL{n - 1}": [f"{r['r_ctl']}.1", f"{r['r_pd']}.1"],
        f"VCTRL{n}": [f"{r['r_ctl']}.2", f"{u}.6"],
        lbl: [f"{u}.15"],
        f"RF1_{n}": [f"{u}.3", f"{r['c_rf1']}.1"],
        f"RF2_{n}": [f"{u}.10", f"{r['c_rf2']}.1"],
        f"{rf1}": [f"{r['c_rf1']}.2", f"{r['j1']}.1"],
        f"{rf2}": [f"{r['c_rf2']}.2", f"{r['j2']}.1"],
    })
for k, lbl, shape, name in DIRECT:
    NETS["GND"] += [f"J95{k}.2"]
    NETS[lbl] = [f"C95{k}.1"]
    NETS[name] = [f"C95{k}.2", f"J95{k}.1"]
NO_CONNECT = []
