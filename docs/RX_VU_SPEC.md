# RX_VU and STATUS sheets (Rev08)

Two sheets added in Rev08 phase 4 (16 November 2026), and what changed on the others. The plan behind them is
[REV08_PLAN.md](REV08_PLAN.md), sections 3–5.

| Sheet | What | Drawn by | Checked by |
|---|---|---|---|
| `RX_VU` | VHF/UHF receive front end: `J961`, bias tee, LNA, two preselectors, RFFC5072 converter, IF chain, its expander (0x20) and LDO | `_work/sheets/rx_vu.py` from `rx_vu_spec.py` | `_work/check_sheet.py rx_vu`: PASS, 131 parts, 95 nets |
| `STATUS` | Status, heartbeat and rail LEDs, the LED expander (0x21), the debug USB bridge | `_work/sheets/status.py` from `status_spec.py` | `_work/check_sheet.py status`: PASS |
| `IAS_LINK` | `J103`, the IAS0 camera pass-through, contact for contact with `J102` | `_work/rev08_schematic.py` | `_work/check_sheet.py ias_link`: PASS |
| `ROUTING` | `C927`: `SW2`'s RF2 throw now takes `IF_VU`; `C926` (`J922`) is DNP | `_work/rev08_schematic.py` | Netlist: `C926.1`, `C927.1`, `U902.10` on one net |
| `CONTROL` | Two sheet pins, `PMOD_SPARE1` and `PMOD_SPARE2` | `_work/rev08_schematic.py` | Netlist |
| Root | Blocks for `RX_VU` (page 11) and `STATUS` (page 12) | `_work/rev08_schematic.py` | ERC |

ERC after the change: the same 7 warnings as before it (all `pin_to_pin` on `CONTROL`, Rev07), no error.

The two new sheets are generated from a connection table, unlike the Rev03 sheets: every IC is drawn with a lead on
each pin ending in its net's label, power symbol or no-connect flag, and its passives labelled beneath it; the four
filters are drawn as ladders with wires. `check_sheet.py` compares KiCad's own netlist of the drawing with the
table, so it proves the drawing makes exactly the table's connections; the design is reviewed in the table.

Symbols: `_work/rev08_symbols.py`, pin tables from the makers' data sheets (named in that file). Footprints:
`_work/rev08_footprints.py`, the placement trial's LCSC land patterns and the vertical USB-C drawn from its maker's
recommended layout.

## 1. RX_VU

### 1.1 Signal path

```
J961 ─ D1301 ESD ─┬─ C1301 ─ U1302 ─┬─ U1301 LNA ─┬─ U1303 ─ U1304 ─┬─ straight ─────────────┬─ U1305 ─ U1308 ─┬─ T1301 ─ U1312 RFFC5072 ─ T1302 ─┬─ U1309 ─ AA LPF ─ U1310 IF amp ─ U1311 att ─ IF_VU
                  │                 └─ bypass ─────┘                 ├─ FM band-pass ─────────┤                 └─ bypass ─────────────────────────┘
 FB1302 + L1301 ──┘ (bias tee)                                       ├─ FM reject (9th) ──────┤
 U1314 AP22652, JP1301 5 V / 3.3 V                                   └─ HP 300 MHz ─ U1306 ─┬─ UHF LPF ──┬─ U1307 ─┘
                                                                                            ├─ SAW 1090 ─┤
                                                                                            ├─ HPF 1 GHz ┤
                                                                                            └─ LPF 1 GHz ┘
```

The 300 MHz high-pass (`C1441`-`C1445`, `L1441`-`L1442`) was added by the Rev08 RF audit (section 1.5).

### 1.2 Control lines (U1313, TCA6416A at 0x20, ports at 2.8 V)

| Port | Net | Function | At power-up (pins are inputs) |
|---|---|---|---|
| P00, P01 | `VU_PSA_V1`, `VU_PSA_V2` | Preselector A, PE42442 2-pin control: V2V1 00 straight, 01 FM band-pass, 10 FM reject, 11 preselector B | Floating |
| P02–P04 | `VU_PSB_V1`…`V3` | Preselector B, SKY13418: V1V2V3 000 UHF LPF, 001 SAW 1090, 010 HPF 1 GHz, 011 LPF 1 GHz, 1xx spare (open) | Floating |
| P05 | `VU_LNA_ON` | High: LNA in; low: bypassed | Floating |
| P06 | `VU_CONV_ON` | High: through the converter; low: direct 30–170 MHz | Floating |
| P07 | `VU_BIAS_EN_N` | Low: bias tee on (the AP22652's enable is active low) | High (R1360): bias **off** |
| P10 | `VU_BIAS_FLT_N` | Input: bias-tee over-current or over-temperature | n/a |
| P11 | `VU_ENX` | RFFC5072 serial select | High (R1342): deselected |
| P12 | `VU_SCLK` | Serial clock, RFFC5072 and PE4312 | Floating |
| P13 | `VU_SDATA` | Serial data, bidirectional (RFFC5072 read-back); to the PE4312 through R1330 (10 k) | Floating |
| P14 | `VU_LD` | Input: RFFC5072 lock detect (GPO4) | n/a |
| P15 | `VU_RESETX` | RFFC5072 reset | High (R1344) |
| P16 | `VU_ATT_LE` | PE4312 latch | High (internal pull-up) |
| P17 | `VU_ENBL` | RFFC5072 enable (and VCO calibration trigger) | Low (R1343): converter **off** |

The PE4312 powers up at 31.5 dB (its parallel bits are tied high in serial mode), so the ADC is protected until
the gateware sets the gain. `MODE` is tied high (R1345): mixer 2 and the PLL2 bank, the RFFC5072's normal use; the
gateware can take over with the `SIPIN` bit.
Register-level bring-up and the LO settings of every band: [RFFC5072_PROGRAMMING.md](RFFC5072_PROGRAMMING.md).

### 1.3 Values and where they come from

| Block | Values | Source |
|---|---|---|
| Anti-alias LPF | 11p, 56n‖5.6p, 22p, 62n‖7.5p, 24p, 75n‖1.2p, 20p | `rev08_filters_mc.py`, plan 5.4 |
| **Preselector B high-pass (Rev08 audit)** | series 11p, shunt 24n + 36p, series 5.6p, shunt 22n + 91p, series 8.2p: 5th-order elliptic | `_work/sim/rev08_rf_audit.py`: ≤ 1.5 dB p99 from 300 MHz to 3 GHz, ≥ 51.7 dB p1 below 175 MHz (3,000 boards: L ±2 %, C ±0.1 pF or ±2 %, pads, Q 35-55, ESL) |
| UHF image LPF | 6.2p, 22n‖1.8p, 6.8p, 27n‖2p, 6.8p, 22n‖0.4p, 1.3p | Same |
| FM reject, 9th order | 18p, 68n+110p, 13p, 82n+36p, 18p, 100n+24p, 24p, 220n+10p, 91p | Same; G2 passed |
| **FM band-pass (new in phase 4)** | shunt 16n‖160p, series 390n + 6.8p, shunt 16n‖160p: 3-pole band-pass, 88–108 MHz | `rev08_filters_mc.py --fmbp` (phase 5): 2.2 dB loss nominal with Q 40-45 inductors and pad capacitance, Monte Carlo (L ±2 % / ±5 % for the 390 nH, C ±2 % / ±0.1 pF, 2,000 runs) loss ≤ 3.1 dB p99, rejection ≥ 24.3 dB p1 at 70 and 137 MHz [V arithmetic]. Phase 4's first values (24n‖110p, 560n + 4.7p) modelled at 3.4 dB and 21.1 dB p1 once the pads and losses were in, so they were re-chosen |
| RFFC5072 loop filter, reference, supplies | C8 8.2p, R3 22k + C9 180p, R2 470 / C10 330p, R6 470 / C17 330p; REXT 51k; 1 nF reference coupling; 120 Ω + 10 nF TCXO supply; 33 pF on the serial lines | Data sheet DS140110 p.13, wideband application schematic |
| SPF5043Z bias | LNA: `L1303` 1 µH (0603, AHW1608F-1R0KTF) + `FB1304` BLM15HD102SN1 bead (0402), `C1305` not fitted; 1 nF blocks; IF amplifier `L1305` 1 µH | Qorvo evaluation board (100 nH, 100 pF), scaled down to 30 MHz; phase 6 (SIGNAL_INTEGRITY 9.10): the drawn 56 nH with `C1305`'s 100 pF to ground was a series resonance at 67 MHz on the LNA output (22 dB), now at most 0.23 dB from 25 MHz to 1.1 GHz |
| Bias tee | `FB1302` BLM15HD102SN1 GHz bead (0402) + `L1301` 1 µH LQW2BAS1R0J (0805 wirewound), 1 nF block, AP22652 with RLIM 210 k: 125 mA typical (95–155) | AP22652 data sheet table; the chokes from phase 6 (SIGNAL_INTEGRITY 9.10, `_work/sim/bias_tee.py`): the drawn 56 nH + 1 µH resonated near 1 GHz (12 dB notch nominal), the bead leaves at most 0.30 dB from 25 MHz to 1.1 GHz |

### 1.4 Corrections to the plan found while drawing

| Item | Plan said | Schematic does | Why |
|---|---|---|---|
| AP22652 enable | Active high | **Active low**, pulled high: bias off until written | Diodes DS41186: the AP22652 is the active-low part (AP22653 is active high) |
| Bias-tee low voltage | 3.0 V | **3.3 V from `+3V3_D`** (JP1301 2-3) | The 3.0 V LDO has 70 mA of headroom; an active antenna can take 100 mA |
| Mixer output balun | TC4-1W+ | TC4-1W+ with the mixer's bias through its centre tap | Rated 30 mA DC: the gateware must keep `MIX2_IDD` ≤ 3 (about 30 mA). Two RF chokes would lift the limit if high linearity is ever needed |
| TCXO pin 1 | not specified | 10 k to its supply | KDS uses pin 1 as Vcont, ground or standby by variant; 10 k is correct for all three |
| Mixer input balun source | TC1-1-13M+ | **Mini-Circuits TC1-1-13M+ only** (case AT224-1A, 6 pads: primary 6 / 4, secondary 1 / 3) | LCSC's C22383443 is HLT's H3-TC1-1-13M+, a clone in a 5-pad body numbered differently (1 primary dot, 2 primary, 3 secondary, 4 ground, 5 secondary dot): it does not fit the footprint. The BOM names the Mini-Circuits part; order it from a distributor if JLCPCB has none |
| `SW2` source | "selects the source" | **C927 fitted (front end), C926 DNP** | The board is built for the front end; `J922` returns by swapping two 0402s |

## 2. STATUS

| Ref | Function |
|---|---|
| U1501 | TCA6416A at 0x21 on `XO_SCL`/`XO_SDA`; P00–P07 sink the status LEDs; P10–P17 unused |
| D1501–D1508 | CFG (green), CLK (yellow: on = 500 MHz), LINK (green), ADC-R, ADC-S (red, sticky clip), LO (green), TX (red), ERR (red) |
| D1509 | Heartbeat (blue) on `PMOD_SPARE2`, the debug UART's transmit line: lit while it is low |
| D1520–D1524 | Rail LEDs: `+12V`, `+5V0`, `+3V3_D` direct; `+1V8_D` and `+1V0` switched from `+3V3_D` by Q1520/Q1521 (MMBT3904, 10 k base) |
| J1501 | Vertical USB-C, HRO TYPE-C-31-E-17 (surface mount only; the HX-TYPE-C 16P 180 LT H10.0 until 18 Nov, LAYOUT 6.8), on the IAS0 tongue |
| U1503 | USBLC6-2SC6 on D+/D− |
| U1502 | CH340X at 3.3 V; V3 tied to VCC through R1535 (0 Ω; 100 nF instead if ever run at 5 V) |
| U1504 | LP5907-3.3 from the cable's VBUS: the bridge enumerates with the board off |
| R1533, R1534 | 1 k: bridge TXD → `PMOD_SPARE1` (a Kria on the Pmod wins), `PMOD_SPARE2` → bridge RXD |

**Why a sheet of its own.** The plan put these parts on `CONTROL`. That A1 sheet has no free area large enough to
draw 60 parts legibly; on their own sheet they are joined to `CONTROL` by two sheet pins and to the Si549's bus by
`XO_SCL`/`XO_SDA`, which is also how `RX_VU` reaches it. **+1V8_D gets a transistor too** (the plan gave one only to
`+1V0`): a green 0402 LED barely lights at 1.8 V.

## 3. Phase 5 (layout): what was open and how it closed

- **`J103` and `J102` numbering**: closed. The `J103` footprint is renumbered by contact position, so pin *n*
  lands over pin *n* of `J102` (REV08_PLAN §11.6).
- **Preselector B** sits in frame B with the converter; frame A keeps the LNA, the bypass and preselector A.
- **The IF chain** (anti-alias filter, IF amplifier, `PE4312`) is on the bottom, east of frame B;
  `IF_VU` leaves it on L6 (142.3 mm to `C927`).
- **`U1313`** is on the bottom south of frame B with a via on every pin; the rail LEDs are on the tongue.
- Still open, for the first board: the shield-can frames' LCSC parts (their footprints are the walls placed on
  the board), the USB-C's locating pegs against the carrier, and the TA1090EC's pin-out against the maker's
  drawing (only LCSC's symbol was available).

### 1.5 Rev08 RF and power audit (18 November 2026)

[AUDIT_Rev08.md](AUDIT_Rev08.md) found that the converter had no IF rejection (R1). The UHF image filter is a
low-pass, so FM broadcast, airband, 2 m, marine VHF and PMR, all inside the 100-170 MHz IF window, reached the mixer
and leaked through it onto the UHF tuning. The 1 GHz low-pass path did the same. The changes:

| Item | Before | Now | Why |
|---|---|---|---|
| Preselector B input | `VU_PSB_IN` straight to `U1306` | Through the 300 MHz high-pass (`VU_PSB_IN` to `VU_PSB_HP`) | IF rejection 31-46 dB becomes 84-99 dB; every B path (UHF, SAW, both LTCC) starts at 300 MHz |
| Converted coverage | 170 MHz up | **300 MHz up**; 170-300 MHz not covered | A 135 MHz IF cannot reject signals at its own frequency near 170-300 MHz |
| Front-end rail | `+3V0_RF`, LP5907MFX-3.0 | **`+2V8_RF`, LP5907MFX-2.8** | At the worst corner of +3V3_D the 3.0 V part reached dropout (26 mV of headroom against 180 mV); now 232 mV. The RFFC5072 runs from 2.7 V, the SPF5043Z, switches, PE4312, TCXO and expander port from lower |
| `C1305` | DNP | DNP (kept by `rx_vu.py`'s `DNP` set; the generator used to drop it) | Phase 6 |

The expander's ports follow the rail (2.8 V): the PE4259's 0.7 × VDD and the RFFC5072's VDD / 1.5 are the same rail,
and the PE42442 and SKY13418 thresholds (1.17 V, 1.35 V) are far below it.

**Updated front-end simulations with `HP300` in the chain (`_work/sim/rev08_filters_mc.py`, `_work/sim/rev08_frontend.py`):**

- **Monte Carlo cross-check (`HP300`, 3,000 runs):** `rev08_filters_mc.py` (seed 1, `<= 175 MHz`) gives **p99 passband loss `1.52 dB`**, **p1 return loss `10.7 dB`**, and **p1 stopband rejection `51.7 dB`**, agreeing within `0.01 dB` with `rev08_rf_audit.py` (`1.51 / 10.7 / 51.7 dB`). For `<= 170 MHz`, tight B/G yield is **`99.8 %`** against a `<= 1.6 dB / >= 50 dB` mask (`97.3 %` even with loose C/J tolerances: `p99 1.68 dB`, `p1 50.7 dB`).
- **Cascade impact (`rev08_frontend.py`, `1.1 dB` `HP300` loss inserted ahead of preselector B):**
  - Converted UHF (`300–480 MHz`): gain `29.3 -> 28.2 dB`, NF `3.7 -> 4.2 dB`, full scale `−46.3 -> −45.2 dBm` (12.5 kHz noise floor `−129 dBm`).
  - Converted ADS-B (`1090 MHz`): gain `23.4 -> 22.3 dB`, NF `7.1 -> 7.9 dB`, full scale `−40.4 -> −39.3 dBm` (noise floor `−126 -> −125 dBm`).
  - Converted general coverage (`300 MHz–3 GHz`): gain `24.9 -> 23.8 dB`, NF `6.1 -> 6.8 dB`, full scale `−41.9 -> −40.8 dBm` (noise floor `−127 -> −126 dBm`).
- **openEMS 3-D layout model (`HP300`, optional):** dropped per the 1 h solver budget. On the 8-layer `JLC08161H-2116C` stack (`40 um` vertical cell, `dt = 74.5 fs`, `~2.36M–3.5M` cells), a single non-resonant capacitor sanity test ran ~`3.0 ms/TS` (`520 MC/s`); ringing down `HP300`'s `112.5 MHz` (`22 nH + 91 pF`, `Q = 45`, `tau = 127 ns`) and `171.2 MHz` resonators to `-40 dB` requires ~`7.8M` timesteps (`~10–15 h`).
