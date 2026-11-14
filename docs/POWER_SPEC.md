# POWER sheet — specification and review guide

*25 September 2026 · `rev03/POWER.kicad_sch` (A2) · drawn by `_work/sheets/power.py` from the
connection list in `_work/sheets/power_spec.py`*

The whole power tree on one sheet. Every regulator circuit is its datasheet's typical
application, with the values read from the datasheet's own table. The loads and the regulator
sizing are in [POWER_AND_STACKUP.md](POWER_AND_STACKUP.md) §1, recomputed by `_work/power_budget.py`
for the tree as drawn.

```
12 V jack ─ PTC ─ SMCJ33CA ─ Q1001 ┐ back-to-back N-FETs, LM74502-Q1 (U1009): reverse battery,
                              Q1003 ┘ overvoltage cut-off at 18.3 V ─ SMBJ18CA ─► +12V   (§1.1, Rev05)
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
| +1V8_A, +1V8_D, +3V3_A | **TPS7A8300RGR** | Figure 51, ANY-OUT: SNS to OUT, 10 nF feed-forward OUT→FB, 10 nF on NR/SS, EN to IN, BIAS open (*"VIN ≥ 1.4 V ... BIAS pin can be left floating"*). CIN 10 µF, COUT 22 µF (Pin Functions). Voltage set by grounding pins (Table 2): 1.8 V = 200 mV + 800 mV pins; 3.3 V = 100 mV + 800 mV + 1.6 V pins. **+1V8_A is 1.85 V** (50 mV pin as well, 12 Nov): its LDO is 75 mm from the ADCs and the copper and ferrite drop up to 0.1 V on the way ([SIGNAL_INTEGRITY.md](SIGNAL_INTEGRITY.md) §9.1) | SBVS197F, AERIS-10 folder |
| −3V3 | **LM2663M** | Pin Functions: SD to GND for normal operation, LV to GND below 3.5 V in, OSC open. 47 µF flying and output capacitors, as its Electrical Characteristics are measured with | SNVS002E, AERIS-10 folder |
| +1V2 | Divider, 1.10 k / 1.02 k, 1 µF | 2.5 V × 1.02 / 2.12 = 1.203 V | — |

The four regulator symbols are new, each transcribed from its datasheet's pin table. KiCad has an
LMR33630 symbol, but it inherits from another one (`extends`), which the generator doesn't
support.


### 1.1 Input protection for a vehicle supply (Rev05, 13 Nov)

The RF review of 13 November (finding B1) was right: the old chain was jack, PTC, a −30 V P-MOSFET and only
then the TVS. ISO 7637-2 pulse 1 (−150 V from 10 Ω, LM74502-Q1 datasheet §10.2.3) puts its whole amplitude
across that MOSFET before anything clamps. The input is now TI's 12 V battery design (LM74502-Q1 datasheet
SNOSDE0A, Figure 10-1), oversized where the board allows it:

| Part | Value | Why |
|---|---|---|
| F1001 | PTC 1.5 A hold, 24 V (unchanged) | Ahead of everything. Only a sustained input above the TVS breakdown (36.7 V) can trip it: an abnormal fault, see the limits below |
| D1003 | **SMCJ33CA**, bidirectional, 1500 W, at VIN_F | Breakdown ≥ 36.7 V: above the 24 V jump start and the 35 V suppressed load dump (ISO 16750-2 test B), as §10.2.3 requires; ≥ 16 V reverse battery. Clamps pulse 1 to about 47–53 V at 15 A. TI's design uses the 600 W SMBJ33CA; the SMC part doubles its energy rating |
| Q1001, Q1003 | **DMT10H015LFG**, 100 V, 13.5 mΩ at 10 V, PowerDI3333-8 | Back to back, common source. With the TVS clamping pulse 1 at −53 V and the output held at +12 V by its capacitors, the blocking FET sees about 65 V: TI's 60 V example would have no margin. VGS(max) ±20 V > the 13.9 V gate drive (§10.2.2.2). Q1001 keeps its footprint |
| U1009 | **LM74502-Q1** (SOT-23-8) | 3.2–65 V, −65 V reverse (Features), charge pump 12.4 V, 60 µA gate source, 2 A sink |
| R1004, R1005 | 100 k / 7.32 k (0603) | Overvoltage cut-off. V<sub>OVR</sub> = 1.165 / 1.25 / 1.333 V (§7.5) gives **17.1 / 18.3 / 19.5 V**. That is above the 14.8 V a charging alternator gives and below D1001's 20.0 V minimum breakdown, so D1001 never conducts steadily. 171 µA in the divider against 110 nA OV leakage |
| C1090 | 100 nF 100 V at VS | Pin Functions: "Connect a 100-nF capacitor across VS and GND" |
| C1091 | 220 nF 25 V, VCAP to VS | §10.2.2.4: ≥ 10 × C<sub>ISS</sub> of the two FETs; TI's value |
| D1001 | **SMBJ18CA** on +12V (was SMBJ15CA) | Catches the microseconds before the OV comparator opens the FETs, at ≤ 29 V: inside the 36 V of the LMR33630 and a brief overshoot for the 25 V input capacitors. Its 20 V minimum breakdown keeps it off below the cut-off |

EN/UVLO is tied to VS (always on). The +12V rail now sees at most about 19.5 V steady state; anything above
opens both FETs and the board resets, which is the intended response to a load dump or a 24 V jump start.

**Layout.** Q1001 stays where it was on the top side. U1009, Q1003, D1003, C1090 and C1091 are on the bottom
under the jack, outside the KV260's outline (y > 117.25 mm), where the bottom was empty; R1004 and R1005 take
D1002's and R1001's place on the top. DRC with zones refilled and schematic parity: 0 errors, 0 unconnected,
0 parity issues (one warning: D1003's flipped footprint differs from the library copy in its silkscreen only).

**Limits, said plainly.**
- A sustained input above 36.7 V (an unsuppressed load dump, or a 24 V system's alternator fault) makes D1003
  conduct; the PTC then trips with more than its 24 V rating across it. A 1812 PTC rated 60 V at 1.5 A does
  not exist. Fit the vehicle harness with its usual inline fuse (3 A) in any case.
- The new parts are not in [JLCPCB_QUOTE.md](JLCPCB_QUOTE.md) yet; LCSC stock of the DMT10H015LFG was not
  confirmed (alternative: any 80–100 V N-FET, ≤ 20 mΩ at 10 V, VGS ±20 V, in PowerDI3333-8).
- The enclosure's tray honeycomb must be pocketed under the new bottom parts (D1003 is 2.3 mm tall) before
  printing: see [ENCLOSURE.md](ENCLOSURE.md).

---

### 1.2 Fan header for enclosure v2 (Rev06, 14 Nov)

`_work/rev06_fan.py`. **J1002** (JST PH 2-pin, vertical, LCSC C131337): pin 1 FAN_5V, pin 2 GND, for a 50 × 50 ×
10 mm 5 V fan (docs/ENCLOSURE.md section 6). **F1002**, a 0.5 A-hold 1206 PTC (SMD1206P050TF, C43379), keeps a
shorted fan lead from pulling +5V0, and the whole board, down; **C1092** 10 µF holds the motor's commutation current
at the header. Always on: the FPGA has no escapable ball left for PWM or tach, and HK_ALERT (TMP1075) would leave the
fan off at power-up, the wrong failure. Placed near the input section, through-hole, outside the carrier's
footprint (LAYOUT §1). The fan's ~0.1 A adds about 2 % to +5V0's load (LMR33630, 3 A).

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
| **Bidirectional TVS** (SMBJ15CA, now SMBJ18CA on +12V and SMCJ33CA at the input) | Superseded by §1.1 | — |

**Chosen at layout (25 Sep; [LAYOUT.md](LAYOUT.md) §5), each against its datasheet:**
- **Inductors:** Bourns SRP7028A. The 8R2M has Isat 7.5 A, above the LMR33630's 5.05 A current
  limit. The 3R3M and 2R2M have Isat 12 A and 14 A, above the 3.5 A needed.
- **P-MOSFET:** Diodes DMP3013SFV (−30 V, −12 A, 9.5 mΩ, VGSS ±25 V), with numbered pins that
  match its PowerDI3333-8 footprint. **Replaced on 13 Nov (§1.1).**

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
