# Power budget and stackup — phase 1

*21 September 2026 · Rev03 architecture, approved · updated 23 September 2026*

The two remaining phase 1 items that do not depend on AMD. Both are produced by scripts in
`_work/`, so re-running them after any change is one command.

| | Script | Status |
|---|---|---|
| Per-rail current budget | `_work/power_budget.py` | Structure settled; **12 of 21 loads verified from datasheets** — see §1.4 |
| Stackup and trace widths | `_work/stackup_impedance.py` | Computed; needs the fabricator's field solver to confirm — see §2.5 |

---

## 1. Power budget

### 1.1 The tree

```
12 V in  (608 mA, 7.3 W)
  └── buck → +5V0        1312 mA
        ├── buck → +3V3_D    989 mA   digital: FPGA VCCO, DAC DVDD, clock, switches
        │     ├── LDO → +1V8_D  300 mA   FPGA VCCAUX, AD9484 DRVDD, AD9253 DRVDD
        │     └── LDO → +1V2    100 mA   FPGA VCCO, IAS-facing bank
        ├── buck → +3V6      180 mA   pre-regulator, analogue only
        │     └── LDO → +3V3_A  180 mA   DAC AVDD, AD8352 drivers, references
        ├── buck → +2V5      500 mA   pre-regulator, analogue only
        │     └── LDO → +1V8_A  500 mA   AD9484 AVDD, AD9253 AVDD
        ├── buck → +1V0      700 mA   FPGA VCCINT
        └── (from +3V3_D) charge pump → −3V3   8 mA   RF switch VEE
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
| `+5V0` | 5.0 | 1312 mA | buck | +12V | 0.73 W | ≥ 1.71 A |
| `+3V3_D` | 3.3 | 989 mA | buck | +5V0 | 0.36 W | ≥ 1.29 A |
| `+1V0` | 1.0 | 700 mA | buck | +5V0 | 0.10 W | ≥ 0.91 A |
| `+2V5` | 2.5 | 500 mA | buck | +5V0 | 0.17 W | ≥ 0.65 A |
| `+1V8_A` | 1.8 | 500 mA | LDO | +2V5 | 0.35 W | ≥ 0.65 A |
| `+3V6` | 3.6 | 180 mA | buck | +5V0 | 0.07 W | ≥ 0.23 A |
| `+3V3_A` | 3.3 | 180 mA | LDO | +3V6 | 0.05 W | ≥ 0.23 A |
| `+1V8_D` | 1.8 | 300 mA | LDO | +3V3_D | **0.45 W** | ≥ 0.39 A — thermal pad |
| `+1V2` | 1.2 | 100 mA | LDO | +3V3_D | 0.21 W | ≥ 0.13 A |
| `−3V3` | −3.3 | 8 mA | charge pump | +3V3_D | 0.01 W | ≥ 0.01 A |

**Input: 608 mA at 12 V = 7.3 W.** With margin, 0.79 A and 9.5 W. The jack, the PTC and the
reverse-polarity MOSFET want ≥ 1.0 A, and 2 A costs nothing extra.

For context: the KV260 itself is a 12 V, 3 A supply. Adding ~1 A for the adapter is comfortable on
the same brick, though the vehicle installation
([VEHICLE_PLATFORM.md](VEHICLE_PLATFORM.md) §4) should keep the two separate anyway.

### 1.4 Confidence: 12 verified, 9 estimated

**Twelve of the twenty-one load figures now come from manufacturer datasheets.** analog.com refuses
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
| AD8352 ×2 | **80 mA** | `ad8352.pdf` Rev. C, quiescent current 39 mA max each |
| ADCLK944 | **165 mA** max | `ADCLK944.pdf` Rev. 0, Table 3: IVCC 138 typ / 165 max, **with the outputs loaded** — so it includes the current delivered to the terminations |
| M3SWA2 ×4, VDD | **12 mA** | `M3SWA2-34DR+.pdf`, IDD 2.9 mA max each |
| M3SWA2 ×4, VEE | **8 mA** | Same, IEE 1.8 mA max each |

Three of these cross-check against the datasheet's own dissipation figure. That's what gives
confidence the tables were read correctly, since text extraction shuffles their columns:

| Part | Currents × voltage | Datasheet dissipation |
|---|---|---|
| AD9484 | (283 + 89) mA × 1.8 V = 670 mW | 670 mW, SDR mode ✓ |
| AD9253 | (183 + 71) mA × 1.8 V = 457 mW | 457 mW, four channels, ANSI-644 ✓ |
| AD9767 | (75 + 15) mA × 5 V = 450 mW | 450 mW ✓ |

**The ADCLK944 question is answered.** The budget had asked whether the quoted supply current
included the LVPECL termination current, because LVPECL budgets are routinely wrong by exactly that
amount. It does: the table is measured with the outputs loaded 50 Ω to VCC − 2 V. What it doesn't
include is the through-current of Thevenin bias dividers on AC-coupled inputs. That stays a
separate estimated line, since it depends on resistor values not yet chosen.

This budget is good enough to **choose the topology and size the regulators** — and it has now
caught three structural errors: two overheating LDOs and an ADC supply above its absolute maximum.
It is **not a thermal sign-off**.

The nine that remain estimates:

| Load | What to check |
|---|---|
| XC7A50T VCCINT, 700 mA | The strongest of the estimates: AERIS-10's design on the same part reports **0.730 W total** in Vivado `[V, from its implementation log]`. VCCINT dominates that; 700 mA at 1.0 V leaves room for our link SerDes. Confirm with a Vivado power estimate once the design exists — a datasheet cannot give this, it depends on the design |
| XC7A50T VCCAUX, VCCO ×2 | Same: Vivado's power report, not a datasheet |
| QSPI flash, TCXO, level translators, housekeeping | Parts not chosen yet. Each is a line in the budget |
| LVPECL bias networks | Resistor values, above |

Replacing any of them is one line; the totals, the regulator choices and the dissipation all
recompute.

---

## 2. Stackup

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

---

## 3. Phase 1 status after this

| Item | State |
|---|---|
| Pin map of J8 and the Pmod | ✅ [INTERFACE_SPEC.md](INTERFACE_SPEC.md) §3, §4 |
| SOM-side mapping verified | ✅ against XTP682 |
| `VCCO` and the link I/O standard | ✅ 1.2 V, `LVDS_12` with AC coupling |
| Mechanical envelope | ✅ measured |
| Power tree topology and regulator sizing | ✅ §1.1–1.3 |
| Per-rail load figures | ⚠️ 12 of 21 from datasheets — §1.4; the rest need Vivado or parts not yet chosen |
| Stackup and trace widths | ✅ §2.1–2.3, pending fabricator confirmation |
| Growth direction within the envelope | ✅ [INTERFACE_SPEC.md](INTERFACE_SPEC.md) §5.3 — outward, off the carrier's side |

One item left, and it doesn't block the schematic: the remaining load figures refine a budget
whose **structure** is already settled, and most of them can only come from Vivado once the FPGA
design exists.
