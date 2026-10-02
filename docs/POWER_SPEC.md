# POWER sheet — specification and review guide

*25 September 2026 · `rev03/POWER.kicad_sch` (A2) · drawn by `_work/sheets/power.py` from the
connection list in `_work/sheets/power_spec.py`*

The whole power tree on one sheet. Every regulator circuit is its datasheet's typical
application, with the values read from the datasheet's own table. The loads and the regulator
sizing are in [POWER_AND_STACKUP.md](POWER_AND_STACKUP.md) §1, recomputed by `_work/power_budget.py`
for the tree as drawn.

```
12 V jack ─ PTC ─ P-MOSFET (reverse polarity) ─ TVS ─► +12V
+12V   ─ U1001 LMR33630  buck ─► +5V0    1605 mA   (3 A part)
+5V0   ─ U1002 TPS562201 buck ─► +3V3_D  1157 mA   (2 A part)
       ─ U1003 TPS562201 buck ─► +2V5     601 mA   FPGA LVDS banks, and feeds +1V8_A
       ─ U1004 TPS562201 buck ─► +1V0     700 mA   FPGA VCCINT
       ─ U1007 TPS7A8300 LDO  ─► +3V3_A   100 mA   DACs' AVDD
+2V5   ─ U1005 TPS7A8300 LDO  ─► +1V8_A   500 mA   ADCs' AVDD
       ─ divider              ─► +1V2       1 mA   link termination bias
+3V3_D ─ U1006 TPS7A8300 LDO  ─► +1V8_D   300 mA   FPGA VCCAUX, ADCs' DRVDD
       ─ U1008 LM2663         ─► −3V3       8 mA   RF switches' VEE
```

Input: **733 mA at 12 V, 8.8 W**; 0.95 A and 11.4 W with the 30 % margin (with CONTROL drawn and its small parts at their datasheet figures, 2 October).

---

## 1. Parts, and where each circuit comes from

| Block | Part | Circuit from | Datasheet |
|---|---|---|---|
| +5V0 | **LMR33630ADDA**, 400 kHz | Figure 9-1, Table 9-2, row *400 kHz, 5 V*: L 8 µH, COUT 4 × 22 µF, RFBT 100 k, RFBB 24.9 k, CIN 10 µF + CHF 220 nF, CBOOT 100 nF, CVCC 1 µF. EN tied to VIN (*"Can be connected directly to VIN"*), PG left open (*"Can be left open when not used"*) | SNVSAN3F, from ti.com (`_work/fetch_datasheets.py`) |
| +3V3_D, +2V5, +1V0 | **TPS562201**, 580 kHz | Figure 7-1 and Table 7-2: R2 10 k; R1 33.2 k / 22.6 k / 3.09 k; L 3.3 / 3.3 / 2.2 µH; COUT 2 × 22 µF; CIN > 10 µF + 0.1 µF; VBST 0.1 µF; EN pulled up by 10 k (Figure 7-1's R3) | SLVSD91D, AERIS-10 folder |
| +1V8_A, +1V8_D, +3V3_A | **TPS7A8300RGR** | Figure 51, ANY-OUT: SNS to OUT, 10 nF feed-forward OUT→FB, 10 nF on NR/SS, EN to IN, BIAS open (*"VIN ≥ 1.4 V ... BIAS pin can be left floating"*). CIN 10 µF, COUT 22 µF (Pin Functions). Voltage set by grounding pins (Table 2): 1.8 V = 200 mV + 800 mV pins; 3.3 V = 100 mV + 800 mV + 1.6 V pins | SBVS197F, AERIS-10 folder |
| −3V3 | **LM2663M** | Pin Functions: SD to GND for normal operation, LV to GND below 3.5 V in, OSC open. 47 µF flying and output capacitors, as its Electrical Characteristics are measured with | SNVS002E, AERIS-10 folder |
| +1V2 | Divider, 1.10 k / 1.02 k, 1 µF | 2.5 V × 1.02 / 2.12 = 1.203 V | — |

The four regulator symbols are new, each transcribed from its datasheet's pin table. KiCad has an
LMR33630 symbol, but it inherits from another one (`extends`), which the generator doesn't
support.

---

## 2. Decisions this sheet makes, for your approval

| Decision | Evidence | Alternative |
|---|---|---|
| **These regulator parts** | All TI, all with datasheets on hand, and three of the four already used by AERIS-10's own boards | A multi-rail PMIC |
| **No pre-regulator for +3V3_A** | Since the AD8352s moved to 5 V, +3V3_A carries 100 mA. Its LDO straight off +5V0 dissipates 0.17 W | — |
| **+2V5 feeds both the FPGA's LVDS banks and the +1V8_A LDO** | The FPGA's link bank must be at 2.5 V (IAS_LINK_SPEC §3); the rail already existed. The analogue 1.8 V gets there through a low-noise LDO | A separate 2.5 V LDO for the FPGA |
| **+1V2 is a resistor divider** | Its only load is the bias of two AC-coupled terminations, with no DC current. The planned "+1V2 LDO for the IAS bank" was based on the wrong bank voltage | An LDO |
| **No power sequencing** | Every regulator comes up as soon as its input does. Xilinx recommends an order for the 7 series (VCCINT, then VCCAUX, then VCCO) to minimise inrush current. **Checked in DS181 since** ([CONTROL_SPEC.md](CONTROL_SPEC.md) §4): the order is a recommendation; the one hard limit, VCCO − VCCAUX > 2.625 V for at most 300 ms per cycle, is met because +1V8_D is an LDO fed from +3V3_D | An EN chain, or an RC delay on each EN |
| **Switching frequencies 400 and 580 kHz** | The datasheets' own designs. Their harmonics fall in the HF band the SDR receives. The layout has to keep the switchers away from the SDR front-end inputs, and the ADCs have ferrite-filtered rails | 2.1 MHz LMR33630 version: fewer harmonics in HF, a little less efficient |
| **LM2663 gives about −3.25 V** | ROUT 3.5 Ω typ × 8 mA pulls it about 30 mV below −3.3 V in magnitude. The M3SWA2 quotes VEE −3.3 V typical, −3.6 V minimum, and no maximum | A regulated negative rail |
| **Bidirectional TVS** (SMBJ15CA) | KiCad's TVS symbol is bidirectional. The BOM had SMBJ15A. On a DC input either works: reverse polarity is blocked by Q1001 | Unidirectional SMBJ15A with a diode symbol |

**Chosen at layout (25 Sep; [LAYOUT.md](LAYOUT.md) §5), each against its datasheet:**
- **Inductors:** Bourns SRP7028A. The 8R2M has Isat 7.5 A, above the LMR33630's 5.05 A current
  limit. The 3R3M and 2R2M have Isat 12 A and 14 A, above the 3.5 A needed.
- **P-MOSFET:** Diodes DMP3013SFV (−30 V, −12 A, 9.5 mΩ, VGSS ±25 V), with numbered pins that
  match its PowerDI3333-8 footprint.

The TPS7A8300's stock footprint has a 2 × 2 mm pad; check it against the RGR drawing.

---

## 3. How the drawing was verified

| Check | Result |
|---|---|
| `_work/check_sheet.py power`: 38 nets exact, 19 no-connects alone, every pin of the 71 parts accounted for | **PASS** |
| KiCad ERC across the design | Every Rev03 rail is now driven: the `power_pin_not_driven` errors on the other sheets are gone. The 8 left belong to the old Rev01 IAS0/IAS1 sheets, which go when the root is wired |

---

## 4. How to review this sheet

About 30 minutes, with the four datasheets.

1. **§2's decisions**, sequencing above all.
2. **Each regulator block against its datasheet's figure and table** (§1).
3. **The TPS7A8300 program pins**: which are grounded on each of the three.

```
py _work/check_sheet.py power
```
