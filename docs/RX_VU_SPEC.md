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
 L1302 + L1301 ───┘ (bias tee)                                       ├─ FM reject (9th) ──────┤
 U1314 AP22652, JP1301 5 V / 3.3 V                                   └─ U1306 ─┬─ UHF LPF ──┬─ U1307 ─┘
                                                                               ├─ SAW 1090 ─┤
                                                                               ├─ HPF 1 GHz ┤
                                                                               └─ LPF 1 GHz ┘
```

### 1.2 Control lines (U1313, TCA6416A at 0x20, ports at 3.0 V)

| Port | Net | Function | At power-up (pins are inputs) |
|---|---|---|---|
| P00, P01 | `VU_PSA_V1`, `VU_PSA_V2` | Preselector A, PE42442 2-pin control: V2V1 00 straight, 01 FM band-pass, 10 FM reject, 11 preselector B | Floating |
| P02–P04 | `VU_PSB_V1`…`V3` | Preselector B, SKY13418: V1V2V3 000 UHF LPF, 001 SAW 1090, 010 HPF 1 GHz, 011 LPF 1 GHz, 1xx spare (open) | Floating |
| P05 | `VU_LNA_ON` | High: LNA in; low: bypassed | Floating |
| P06 | `VU_CONV_ON` | High: through the converter; low: direct 30–170 MHz | Floating |
| P07 | `VU_BIAS_EN_N` | Low: bias tee on (the AP22652's enable is active low) | High (R1360): bias **off** |
| P10 | `VU_BIAS_FLT_N` | Input: bias-tee over-current or over-temperature | — |
| P11 | `VU_ENX` | RFFC5072 serial select | High (R1342): deselected |
| P12 | `VU_SCLK` | Serial clock, RFFC5072 and PE4312 | Floating |
| P13 | `VU_SDATA` | Serial data, bidirectional (RFFC5072 read-back); to the PE4312 through R1330 (10 k) | Floating |
| P14 | `VU_LD` | Input: RFFC5072 lock detect (GPO4) | — |
| P15 | `VU_RESETX` | RFFC5072 reset | High (R1344) |
| P16 | `VU_ATT_LE` | PE4312 latch | High (internal pull-up) |
| P17 | `VU_ENBL` | RFFC5072 enable (and VCO calibration trigger) | Low (R1343): converter **off** |

The PE4312 powers up at 31.5 dB (its parallel bits are tied high in serial mode), so the ADC is protected until
the gateware sets the gain. `MODE` is tied high (R1345): mixer 2 and the PLL2 bank, the RFFC5072's normal use; the
gateware can take over with the `SIPIN` bit.

### 1.3 Values and where they come from

| Block | Values | Source |
|---|---|---|
| Anti-alias LPF | 11p, 56n‖5.6p, 22p, 62n‖7.5p, 24p, 75n‖1.2p, 20p | `rev08_filters_mc.py`, plan 5.4 |
| UHF image LPF | 6.2p, 22n‖1.8p, 6.8p, 27n‖2p, 6.8p, 22n‖0.4p, 1.3p | Same |
| FM reject, 9th order | 18p, 68n+110p, 13p, 82n+36p, 18p, 100n+24p, 24p, 220n+10p, 91p | Same; G2 passed |
| **FM band-pass (new in phase 4)** | shunt 24n‖110p, series 560n + 4.7p, shunt 24n‖110p: 3-pole Butterworth, 84–113 MHz | Designed here: 2.5 dB loss in 88–108 MHz (Q 40), 22 dB at 70 and 137 MHz; Monte Carlo (L ±2 %, C ±2 % / ±0.1 pF, 2,000 runs): loss ≤ 3.0 dB p99, rejection ≥ 21.2 dB p1 [V arithmetic]. To be added to `rev08_filters_mc.py` in phase 9 |
| RFFC5072 loop filter, reference, supplies | C8 8.2p, R3 22k + C9 180p, R2 470 / C10 330p, R6 470 / C17 330p; REXT 51k; 1 nF reference coupling; 120 Ω + 10 nF TCXO supply; 33 pF on the serial lines | Data sheet DS140110 p.13, wideband application schematic |
| SPF5043Z bias | 1 µH (0603) + 56 nH (0402) choke, 1 nF blocks; IF amplifier 1 µH | Qorvo evaluation board (100 nH, 100 pF), scaled down to 30 MHz |
| Bias tee | 56 nH + 1 µH (0805) chokes, 1 nF block, AP22652 with RLIM 210 k: 125 mA typical (95–155) | AP22652 data sheet table |

### 1.4 Corrections to the plan found while drawing

| Item | Plan said | Schematic does | Why |
|---|---|---|---|
| AP22652 enable | Active high | **Active low**, pulled high: bias off until written | Diodes DS41186: the AP22652 is the active-low part (AP22653 is active high) |
| Bias-tee low voltage | 3.0 V | **3.3 V from `+3V3_D`** (JP1301 2-3) | The 3.0 V LDO has 70 mA of headroom; an active antenna can take 100 mA |
| Mixer output balun | TC4-1W+ | TC4-1W+ with the mixer's bias through its centre tap | Rated 30 mA DC: the gateware must keep `MIX2_IDD` ≤ 3 (about 30 mA). Two RF chokes would lift the limit if high linearity is ever needed |
| TCXO pin 1 | — | 10 k to its supply | KDS uses pin 1 as Vcont, ground or standby by variant; 10 k is correct for all three |
| `SW2` source | "selects the source" | **C927 fitted (front end), C926 DNP** | The board is built for the front end; `J922` returns by swapping two 0402s |

## 2. STATUS

| Ref | Function |
|---|---|
| U1501 | TCA6416A at 0x21 on `XO_SCL`/`XO_SDA`; P00–P07 sink the status LEDs; P10–P17 unused |
| D1501–D1508 | CFG (green), CLK (yellow: on = 500 MHz), LINK (green), ADC-R, ADC-S (red, sticky clip), LO (green), TX (red), ERR (red) |
| D1509 | Heartbeat (blue) on `PMOD_SPARE2`, the debug UART's transmit line: lit while it is low |
| D1520–D1524 | Rail LEDs: `+12V`, `+5V0`, `+3V3_D` direct; `+1V8_D` and `+1V0` switched from `+3V3_D` by Q1520/Q1521 (MMBT3904, 10 k base) |
| J1501 | Vertical USB-C, HX-TYPE-C 16P 180 LT H10.0, on the IAS0 tongue |
| U1503 | USBLC6-2SC6 on D+/D− |
| U1502 | CH340X at 3.3 V; V3 tied to VCC through R1535 (0 Ω; 100 nF instead if ever run at 5 V) |
| U1504 | LP5907-3.3 from the cable's VBUS: the bridge enumerates with the board off |
| R1533, R1534 | 1 k: bridge TXD → `PMOD_SPARE1` (a Kria on the Pmod wins), `PMOD_SPARE2` → bridge RXD |

**Why a sheet of its own.** The plan put these parts on `CONTROL`. That A1 sheet has no free area large enough to
draw 60 parts legibly; on their own sheet they are joined to `CONTROL` by two sheet pins and to the Si549's bus by
`XO_SCL`/`XO_SDA`, which is also how `RX_VU` reaches it. **+1V8_D gets a transistor too** (the plan gave one only to
`+1V0`): a green 0402 LED barely lights at 1.8 V.

## 3. Open for phase 5

- Shield-can frames are not yet parts: their LCSC part and footprint are chosen with the layout.
- `J103` and `J102` footprints number their contacts differently (placement trial); the schematic connects pin *n*
  to pin *n* by Hirose's numbering, and phase 5 checks each footprint against the Hirose drawings (now in hand:
  BM20 catalogue via LCSC) so that the copper follows the contacts, not the numbers.
- The USB-C's locating pegs against the carrier, and the TA1090EC's pin-out against the maker's drawing (only
  LCSC's symbol was available).
