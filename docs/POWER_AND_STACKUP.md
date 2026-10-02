# Power budget and stackup — phase 1

*21 September 2026 · Rev03 architecture, approved · updated 2 October 2026*

The two remaining phase 1 items that do not depend on AMD. Both are produced by scripts in
`_work/`, so re-running them after any change is one command.

| | Script | Status |
|---|---|---|
| Per-rail current budget | `_work/power_budget.py` | Structure settled; **18 of 24 loads verified from datasheets** — see §1.4. The 6 left are the FPGA's rails and one pull-down pair |
| Stackup and trace widths | `_work/stackup_impedance.py` | Computed; needs the fabricator's field solver to confirm — see §2.5 |

---

## 1. Power budget

### 1.1 The tree

```
As drawn on rev03/POWER (docs/POWER_SPEC.md), 25 September; loads as of 2 October:

12 V in  (733 mA, 8.8 W)
  └── LMR33630 buck → +5V0   1584 mA   and directly: AD8352 drivers (via ferrites → +5V_IFR/+5V_IFS)
        ├── TPS562201 → +3V3_D   1128 mA   digital: FPGA VCCO, DAC DVDD, clock (via FB401 → +3V3_CLK), switches
        │     ├── TPS7A8300 → +1V8_D  332 mA   FPGA VCCAUX and VCCO_35, AD9484 DRVDD, AD9253 DRVDD, housekeeping
        │     └── LM2663 → −3V3        8 mA   RF switch VEE
        ├── TPS7A8300 → +3V3_A    100 mA   DAC AVDD (no pre-regulator needed any more)
        ├── TPS562201 → +2V5      601 mA   FPGA bank 34 (link outputs), and:
        │     ├── TPS7A8300 → +1V8_A  500 mA   AD9484 AVDD, AD9253 AVDD
        │     └── divider → +1V2        1 mA   termination bias only (2 link pairs, CLK_FPGA)
        └── TPS562201 → +1V0      700 mA   FPGA VCCINT
```

**The −3.3 V rail is there because B-03 was wrong the first time.** The M3SWA2-34DR+ needs
VDD +3.3 V *and* VEE −3.3 V; what is positive is its control logic, not its supply. See
[BLOCKERS_AND_RISKS.md](BLOCKERS_AND_RISKS.md) B-03. The draw is 1.8 mA maximum per switch, so a
small charge pump covers all four with room to spare.

### 1.2 What the budget caught

The first pass had the obvious tree: `+3V3_A` as an LDO straight off 5 V, and `+1V8_A` off 3V3.
The script flagged both:

```
+1V8_A   1.8V   600mA   ldo   +3V3_A   0.90W   <-- too hot for an LDO, use a buck
+3V3_A   3.3V   840mA   ldo     +5V0   1.43W   <-- too hot for an LDO, use a buck
```

**This is the same class of mistake the Rev01 design made** with its ADP151 dropping 5 V to 1.8 V
at 1.6 W in a TSOT-23-5 (see [AUDIT_Rev01.md](AUDIT_Rev01.md) §3). Worth noting that it is an easy
mistake to repeat: the tree looks perfectly reasonable until you multiply the drop by the current.

The fix is a pre-regulating buck in front of each analogue LDO. The LDO keeps its noise rejection
where the analogue rails need it, but only has to drop a few hundred millivolts:

| Rail | Before | After |
|---|---|---|
| `+3V3_A` | LDO from 5 V, **1.43 W** | buck to 3.6 V, then LDO, **0.07 W** |
| `+1V8_A` | LDO from 3.3 V, **0.90 W** | buck to 2.5 V, then LDO, **0.42 W** |

Cost: two extra bucks. A multi-rail PMIC would consolidate them if board area gets tight.

**A second catch, on 23 September: the AD9253's DRVDD was on the wrong rail.** The budget had it on
`+3V3_D`. The datasheet (Rev. D, Table 1) gives DRVDD **1.7–1.9 V**, with an **absolute maximum of
2.0 V**, so the first power-up would have destroyed the ADC. It's now on `+1V8_D`. That rail rises
to 300 mA and its LDO to 0.45 W, which needs a part with a thermal pad but no change of topology.

This one doesn't come from the arithmetic. It came from reading the datasheet's supply table
instead of assuming that "the digital drivers go on the digital 3.3 V". The AD9484 next to it runs
DRVDD at 1.8 V as well.

### 1.3 Regulator sizing

With 30 % margin:

| Rail | V | I | Type | From | Dissipation | Size for |
|---|---|---|---|---|---|---|
| `+5V0` | 5.0 | 1584 mA | buck | +12V | 0.88 W | ≥ 2.06 A |
| `+3V3_D` | 3.3 | 1128 mA | buck | +5V0 | 0.41 W | ≥ 1.47 A |
| `+1V0` | 1.0 | 700 mA | buck | +5V0 | 0.10 W | ≥ 0.91 A |
| `+2V5` | 2.5 | 601 mA | buck | +5V0 | 0.20 W | ≥ 0.78 A |
| `+1V8_A` | 1.8 | 500 mA | LDO | +2V5 | 0.35 W | ≥ 0.65 A |
| `+3V3_A` | 3.3 | 100 mA | LDO | +5V0 | 0.17 W | ≥ 0.13 A |
| `+1V8_D` | 1.8 | 332 mA | LDO | +3V3_D | **0.50 W** | ≥ 0.43 A — thermal pad |
| `+1V2` | 1.2 | 1 mA | divider | +2V5 | 0.00 W | — |
| `−3V3` | −3.3 | 8 mA | charge pump | +3V3_D | 0.01 W | ≥ 0.01 A |

**Input: 733 mA at 12 V = 8.8 W.** With margin, 0.95 A and 11.4 W. (2 October: 755 mA before
the flash, translator and housekeeping estimates were replaced by their datasheets.) The rise since the first
budget is the clock, as drawn: the ADCLK948 (330 mA max) and the Si549 (153 mA) replaced an
ADCLK944 (165 mA) and a TCXO (20 mA), see [CLOCK_SPEC.md](CLOCK_SPEC.md). Then, when the radar
ADC sheet was drawn, the AD8352 drivers moved from `+3V3_A` to 5 V, the only supply their
datasheet characterises (Table 1) and the one AERIS-10 uses; there are four of them, two per ADC
([ADC_RADAR_SPEC.md](ADC_RADAR_SPEC.md), [ADC_SDR_SPEC.md](ADC_SDR_SPEC.md)). The jack, the PTC and the
reverse-polarity MOSFET want ≥ 1.0 A, and 2 A costs nothing extra.

For context: the KV260 itself is a 12 V, 3 A supply. Adding ~1 A for the adapter is comfortable on
the same brick, though the vehicle installation
([VEHICLE_PLATFORM.md](VEHICLE_PLATFORM.md) §4) should keep the two separate anyway.

### 1.4 Confidence: 18 verified, 6 estimated

**Eighteen of the twenty-four load figures now come from manufacturer datasheets.** analog.com refuses
to serve its PDFs to this machine (repeated 60 s timeouts; the mirrors return 403 and 410). They
came from two other places: the AERIS-10 repository's component folder, and the **Internet
Archive's copies of analog.com's own URLs**, fetched by `_work/fetch_datasheets.py`. That script
records the snapshot, size and SHA-256 of each file.

| Load | Figure | Source |
|---|---|---|
| AD9484 AVDD | **300 mA** max | `AD9484.pdf` Rev. A, POWER SUPPLY table. IAVDD 283 typ / 300 max, at the rated 500 MSPS — using it at 400 MSPS is conservative |
| AD9484 DRVDD | **100 mA** max | Same table. IDRVDD 89 typ / 100 max, SDR mode |
| AD9253 AVDD | **200 mA** max | `AD9253.pdf` Rev. D, Table 1, -125 grade: IAVDD 183 typ / 200 max. That is **four** channels at 125 MSPS; we use two, at 62.5 MSPS, so it is an upper bound |
| AD9253 DRVDD | **100 mA** max, **on 1.8 V** | Same table: IDRVDD 71 typ / 100 max, ANSI-644. See §1.2 for the rail |
| AD9708 AVDD | **25 mA** | `AD9708.pdf`, Analog Supply Current |
| AD9708 DVDD | **3 mA** | Same, Digital Supply Current |
| AD9767 AVDD | **75 mA** max | `AD9763_9765_9767.pdf` Rev. G, Table 1: IAVDD 71 typ / 75 max, both DACs at 20 mA full scale |
| AD9767 DVDD | **19 mA** | Same table: 15 mA at 100 MSPS, scaled to 125 MSPS. Measured at 5 V, so an over-estimate at 3.3 V |
| AD8352 ×4 | **2 × 78 mA** at 5 V | `ad8352.pdf` Rev. C, Table 1: quiescent current 37 typ / 39 max each. Two on `rev03/ADC_RADAR`, two on `rev03/ADC_SDR` |
| ADCLK948 | **330 mA** max | `ADCLK948.pdf` Rev. B, Table 4: IVCC 288 typ / 330 max, **with the outputs loaded** — so it includes the current into the 200 Ω pull-downs. Half the outputs are unused and open, so it is an upper bound |
| Si549 | **153 mA** max | `Si549.pdf` Revision H: IDD LVPECL 107 typ / 153 max |
| M3SWA2 ×4, VDD | **12 mA** | `M3SWA2-34DR+.pdf`, IDD 2.9 mA max each |
| M3SWA2 ×4, VEE | **8 mA** | Same, IEE 1.8 mA max each |
| MT25QL128 flash | **35 mA** max | `MT25QL128.pdf` Table 42: 22 mA max reading quad at 133 MHz, 35 mA max while programming (I<sub>CC4</sub>, I<sub>CC5</sub>). The larger is counted |
| Housekeeping on `+1V8_D` | **2 mA** | TMP1075 85 µA max while converting (`TMP1075.pdf` §6.5); M24C02-F 0.8 mA max reading (`M24C02.pdf` DS9398 Table 14); 74LVC1G07 10 µA (its datasheet); 0.18 mA in each 10 kΩ pull-up held low. Sum 1.6 mA |

The old "level translators, 50 mA" line is gone: the one translator drawn is the 74LVC1G07 on
PROG_B. Bank 35 at 1.8 V talks to the ADAR1000s and to the carrier directly (CONTROL_SPEC §1).

Three of these cross-check against the datasheet's own dissipation figure. That's what gives
confidence the tables were read correctly, since text extraction shuffles their columns:

| Part | Currents × voltage | Datasheet dissipation |
|---|---|---|
| AD9484 | (283 + 89) mA × 1.8 V = 670 mW | 670 mW, SDR mode ✓ |
| AD9253 | (183 + 71) mA × 1.8 V = 457 mW | 457 mW, four channels, ANSI-644 ✓ |
| AD9767 | (75 + 15) mA × 5 V = 450 mW | 450 mW ✓ |

**The LVPECL question is answered.** The budget had asked whether the fan-out's quoted supply
current included its termination current, because LVPECL budgets are routinely wrong by exactly
that amount. It does, for the ADCLK944 first considered and for the ADCLK948 drawn: both tables
are measured with the outputs loaded. What stays a separate estimated line is the Si549's two
130 Ω pull-downs, whose inclusion in its IDD the datasheet doesn't state.

This budget is good enough to **choose the topology and size the regulators** — and it has now
caught three structural errors: two overheating LDOs and an ADC supply above its absolute maximum.
It is **not a thermal sign-off**.

The six that remain estimates:

| Load | What to check |
|---|---|
| XC7A50T VCCINT, 700 mA | The strongest of the estimates: AERIS-10's design on the same part reports **0.730 W total** in Vivado `[V, from its implementation log]`. VCCINT dominates that; 700 mA at 1.0 V leaves room for our link SerDes. Confirm with a Vivado power estimate once the design exists — a datasheet cannot give this, it depends on the design |
| XC7A50T VCCAUX, VCCO ×3 | Same: Vivado's power report, not a datasheet |
| Si549 LVPECL pull-downs | Whether its IDD figure already includes them is not stated |

Replacing any of them is one line; the totals, the regulator choices and the dissipation all
recompute.

---

## 2. Stackup

> **Superseded for the board by §2.6** (26 September 2026): the fabricator's stack, JLCPCB
> JLC06161H-2116A, and widths from a field solver. §2.1–§2.5 are kept as the reasoning that
> chose the stack's shape.

### 2.1 Proposed stack — 6 layers, 1.6 mm

| Layer | Use | Copper |
|---|---|---|
| **L1** | **SIG** — IAS pairs, converter LVDS | 35 µm |
| | prepreg 0.100 mm, Er 4.05 | |
| **L2** | **GND** — solid reference for L1 | 17.5 µm |
| | core 0.200 mm, Er 4.30 | |
| **L3** | SIG — general routing | 17.5 µm |
| | prepreg 0.800 mm, Er 4.30 | |
| **L4** | PWR — split planes | 17.5 µm |
| | core 0.200 mm, Er 4.30 | |
| **L5** | GND — solid reference for L6 | 17.5 µm |
| | prepreg 0.100 mm, Er 4.05 | |
| **L6** | SIG — slow signals, fan-out | 35 µm |

Total 1.540 mm before soldermask.

The shape of this stack is driven by one requirement: **the IAS pairs run on L1 over an unbroken
L2 ground, at a thin 0.100 mm dielectric.** Thin prepreg there buys narrow traces at 100 Ω, which
keeps the five pairs in a manageable routing channel, and it puts the return current directly
underneath.

### 2.2 Trace widths — L1 microstrip

Computed by `_work/stackup_impedance.py`, h = 0.100 mm, Er = 4.05, t = 35 µm:

**50 Ω single-ended: W = 174 µm** — for the IF lines to the SMAs.

**100 Ω differential**, several workable geometries:

| W (µm) | S (µm) | Z0 (Ω) | Zdiff (Ω) | Comment |
|---|---|---|---|---|
| 113 | 100 | 61.3 | 100.0 | Tightest. 100 µm gap is at the edge of low-cost fab capability |
| 126 | 125 | 58.5 | 100.0 | |
| **136** | **150** | **56.4** | **100.0** | **Recommended** — comfortable for any fabricator |
| 145 | 175 | 54.9 | 100.0 | |
| 151 | 200 | 53.8 | 100.0 | |

**The recommendation is W = 136 µm, S = 150 µm**, not the tightest option the script prints. A
100 µm gap sits at the limit of standard process and pushes the board into a more expensive class
for no benefit — the 150 µm gap gets the same impedance with margin. A pair then occupies 422 µm of
routing channel, so the five IAS pairs need about 2.1 mm plus spacing between pairs.

### 2.3 Trace widths — L3 stripline

Between L2 (0.200 mm away) and L4 (0.800 mm away), Er = 4.30, t = 17.5 µm:

| Target | Width |
|---|---|
| 50 Ω single-ended | 377 µm |
| 100 Ω differential, S = 150 µm | 201 µm |
| 100 Ω differential, S = 200 µm | 238 µm |
| 100 Ω differential, S = 250 µm | 268 µm |

**These are the least reliable numbers on this page.** The closed form for an offset stripline is
weakest exactly when the two planes are as asymmetric as they are here (0.2 against 0.8 mm), and it
is likely running wide. Treat L3 as a routing layer for slower signals and keep anything impedance
controlled on L1.

### 2.4 Rules that matter more than the widths

- **L2 must be solid under every IAS pair, end to end.** A split under a differential pair costs
  far more than any width error in this table.
- **Keep the IAS pairs on L1 for their whole run.** Every via pair is a stub and a reference
  change, and there are only five pairs — there is no routing pressure that justifies dropping
  them to an inner layer.
- **Er falls with frequency.** A fabricator quoting Er at 1 MHz will hand back widths that run high
  in impedance at 1 Gbps. Ask what frequency their number is for.
- **Length matching** within a pair to the usual fraction of a bit time; between pairs it does not
  matter, because the link is source-synchronous and each pair carries its own alignment.

### 2.5 `[E]` What has to be confirmed

These are **IPC-2141 / Hammerstad-Jensen closed forms, good to roughly ±10 %**. They are enough to
choose the stack, size the routing channel and sanity-check a quote. They are not the final
geometry.

Before ordering: send this stack to the chosen fabricator, ask for **their** laminate Er at 1 GHz
and **their** field-solver widths, and put those on the board. Most fabricators do this for free as
part of an impedance-controlled quote.

### 2.6 The fabricator's stack: JLCPCB JLC06161H-2116A

**Chosen: JLC06161H-2116A**, 6 layers, 1.556 mm nominal, outer 1 oz, inner 0.5 oz, NP-155F laminate.
Among JLCPCB's eleven 1.6 mm six-layer stacks, it is the one with the shape §2.1 asked for. The layer
data comes from JLCPCB's own stackup API, as extracted by
`github.com/gsuberland/jlcpcb_autogenerated_stackups` (fetched 26 September 2026). The dielectric
constants are as on `jlcpcb.com/impedance`.

| Layer | Use | Dielectric below | Er |
|---|---|---|---|
| L1 | SIG — IAS pairs, LVDS, IF | 2116 prepreg, 0.1164 mm | 4.16 |
| L2 | GND | core, 0.130 mm | 4.17 |
| L3 | SIG | 2116 + core 0.70 + 2116 = 0.933 mm | 4.16 / 4.53 / 4.16 |
| L4 | PWR (split) | core, 0.130 mm | 4.17 |
| L5 | GND | 2116 prepreg, 0.1164 mm | 4.16 |
| L6 | SIG | — | — |

**Why this one and not JLCPCB's default** (JLC06161H-3313, the "no requirement" stack):

| | Default (3313) | 2116A (chosen) |
|---|---|---|
| Under L1 and L6 | 0.0994 mm | 0.1164 mm |
| Between L3 and its planes | L3 is 0.55 mm from L2 and **0.116 mm from L4**, the split power layer | L3 is **0.13 mm from L2**, the solid ground, and 0.93 mm from L4 |

In the default stack, L3's reference would be the split power plane. In 2116A it is ground: that
is the property §2.1 was built around.

**Widths, by field solver** (`_work/field_solver.py`):
- **Method:** finite differences on the cross-section at 5 µm, with the solder mask JLCPCB's
  calculator assumes (1.2 mil on laminate, 0.6 mil on copper; its Er of 3.8 is an estimate).
- **Checked against a symmetric stripline** (Cohn's exact formula): 1.0 % low.
- **Checked against a wide microstrip** (Hammerstad-Jensen, itself about 1 %): 2.4 % low.
- **Mesh:** halving the grid step moves the result by 0.3 %.

| Line | Width / gap | Impedance | §2.2–§2.3 said |
|---|---|---|---|
| **L1, 50 Ω** (IF lines) | **183 µm** | 49.8 Ω | 174 µm |
| **L1, 100 Ω differential** (IAS, LVDS) | **117 / 150 µm** | 100.2 Ω | 136 / 150 µm |
| L1, 100 Ω differential, alternatives | 104 / 127 µm, 137 / 200 µm | 99.7, 100.2 Ω | |
| L3, 50 Ω | 175 µm | 50.2 Ω | 377 µm |
| L3, 100 Ω differential | 104 / 150 µm, 122 / 200 µm | 99.8, 100.7 Ω | 201 / 150 µm |

- **The solder mask is worth 20 µm on the 50 Ω line:** without it the solver gives 203 µm.
- **L3 changes the most**, because it now sits 0.13 mm from its ground, not 0.2 mm.
- **The net classes on the board use 117 / 150 µm and 183 µm.** 117 µm is 4.6 mil, inside
  JLCPCB's 3.5 mil six-layer minimum.
- **Before ordering, run the same geometries through JLCPCB's impedance calculator** with this
  stack selected. It should agree within a few ohms; if it doesn't, use its widths. The solver
  reads 1–2.4 % low against the two exact references, so if anything the true impedance is that
  much higher than the table.

---

## 3. Phase 1 status after this

| Item | State |
|---|---|
| Pin map of J8 and the Pmod | ✅ [INTERFACE_SPEC.md](INTERFACE_SPEC.md) §3, §4 |
| SOM-side mapping verified | ✅ against XTP682 |
| `VCCO` and the link I/O standard | ✅ 1.2 V, `LVDS_12` with AC coupling |
| Mechanical envelope | ✅ measured |
| Power tree topology and regulator sizing | ✅ §1.1–1.3 |
| Per-rail load figures | ⚠️ 16 of 25 from datasheets — §1.4; the rest need Vivado or parts not yet chosen |
| Stackup and trace widths | ✅ §2.1–2.3, pending fabricator confirmation |
| Growth direction within the envelope | ✅ [INTERFACE_SPEC.md](INTERFACE_SPEC.md) §5.3 — outward, off the carrier's side |

One item left, and it doesn't block the schematic: the remaining load figures refine a budget
whose **structure** is already settled, and most of them can only come from Vivado once the FPGA
design exists.
