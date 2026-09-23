# CLOCK sheet — specification and review guide

*23 September 2026 · first sheet drawn for Rev03 · pilot for the drawing method*

`rev03/CLOCK.kicad_sch`, drawn by `_work/sheets/clock.py` from the connection list in
`_work/sheets/clock_spec.py`, and checked against that list by `_work/check_sheet.py`.

---

## 1. What drawing it changed in the architecture

Drawing this sheet exposed three problems in the clock plan of `ARCHITECTURE.md` §5.3. It had a
TCXO, a selector and an ADCLK944 fan-out feeding ADC, DAC, FPGA and a spare output. Each problem was
checked against a datasheet before changing anything:

| Problem | Evidence | Resolution |
|---|---|---|
| A fan-out copies **one** frequency to every output, but the converters run at different rates (AD9484 400 MSPS, AD9253 ≤ 62.5 MSPS, DACs ≤ 125 MSPS) | ADCLK944 has no dividers | The AD9253 **divides its clock internally**, 1 to 8, with inputs up to 1 GHz (AD9253 Rev. D, "Input Clock Divider"). One master clock serves both ADCs |
| The DACs cannot take a differential LVPECL clock | AD9767 Rev. G Table 6: `CLK1/IQCLK` is a CMOS input; AD9708 likewise | DAC clocks come from the **FPGA**, which sends the DACs their data anyway. `CLK_DAC_P/N` removed from the interface |
| A TCXO cannot produce 400–500 MHz | TCXOs are tens of MHz | Local master is a **Si549** programmable XO, 0.2–1500 MHz, 95 fs jitter |

And one addition: the selector and the fan-out became **one chip, the ADCLK948** (two selectable
inputs, eight LVPECL outputs), instead of a separate selector feeding an ADCLK944.

### 1.1 The frequency plan

| Master | AD9484 | AD9253 (÷8) | FPGA | Use |
|---|---|---|---|---|
| **400 MHz** | 400 MSPS | 50 MSPS → HF to 25 MHz | 400 MHz ref | Radar mode: AERIS-10 runs at 400 MSPS, so its firmware ports unchanged |
| **500 MHz** | 500 MSPS | **62.5 MSPS → all of HF** | 500 MHz ref | SDR mode: the AD9253's full 1-lane rate (B-02), covering to 30 MHz |

The Si549 is reprogrammed over I²C to switch between the two. Its **±950 ppm fine-tuning with
100 µs settling** (Si549 Rev. H, DCO) lets the FPGA discipline it to the GPS PPS. That recovers
the frequency accuracy the TCXO was there for, and does it better.

### 1.2 Interface changes

Made by `_work/rev03_clock_interface.py`, then `_work/sync_sheet_pins.py`:

| Signal | Change | Why |
|---|---|---|
| `CLK_DAC_P/N` | **removed** | DACs take CMOS clocks from the FPGA |
| `DACS_IQCLK`, `DACS_IQRESET` | **added**, FPGA → AD9767 | Interleaved mode needs IQCLK, IQWRT, IQSEL and IQRESET (Table 6); the hierarchy only had two of the four |
| `CLK_SEL` | **added**, FPGA → CLOCK | Reference select, driven open-drain (§3) |
| `XO_SCL`, `XO_SDA` | **added**, FPGA → CLOCK | Programs the Si549. 3.3 V levels: its I²C needs VIH ≥ 0.7·VDD, which the Kria's IAS I²C would not give |

---

## 2. Parts

| Ref | Part | Source |
|---|---|---|
| U401 | ADCLK948BCPZ | Datasheet Rev. B (Internet Archive, `_work/fetch_datasheets.py`) |
| Y401 | Si549, LVPECL, 3.3 V, 5×7 mm, **pinout code C** | Datasheet Revision H. Code C is the Si570-compatible pinout, so the stock KiCad `Si570` footprint fits |
| J401, J402 | Edge-mount SMA | On the edge the board grows towards (INTERFACE_SPEC §5.3) |
| FB401 + 25 passives | see `clock_spec.py` | Each with its source |

**The Si549 is ordered configured.** Its part number encodes output format, supply, package, pinout
and startup frequency, and Skyworks ships samples in 1–2 weeks. Order it as LVPECL, 3.3 V, 5×7 mm,
pinout C, total stability ±25 ppm or better. The startup frequency doesn't matter, because the FPGA
sets 400 or 500 MHz at boot.

**The ADCLK948 has no stock footprint.** Its package (CP-32-21) has a 2.70 mm exposed pad; every
stock 5×5 mm LFCSP-32 in KiCad has 3.1 mm or more. Draw one at layout from the package drawing on
datasheet page 12.

---

## 3. Every value, and where it comes from

| Item | Value | Source |
|---|---|---|
| ADCLK948 output pull-downs (R404–R411) | 200 Ω | Datasheet Figure 17, AC-coupled LVPECL |
| Output series capacitors (C414–C421) | 100 pF | Figure 17: "0.1 nF" |
| **Receiver** termination | 100 Ω across each pair | Figure 17 — drawn on the **consuming** sheet, next to the receiver |
| Unused outputs Q4–Q7 | left open | Output stage is an open emitter (Figure 13): no pull-down, no current |
| CLK1 input (Si549) | series 100 nF, VT1 tied to VREF1, 100 nF to ground | Figure 21, AC-coupled differential input |
| CLK0 input (SMA) | series 100 nF; CLK0-bar, VT0 and VREF0 tied, 100 nF to ground | Figure 22, AC-coupled single-ended input |
| Reference level at J401 | 0.4 – 3.4 Vpp | Table 1, input differential range. 50 Ω on chip |
| Si549 source pull-downs (R402, R403) | 130 Ω | Si549 Figure 4.1, AC-coupled LVPECL at VDD 3.3 V |
| Si549 I²C pull-ups (R413, R414) | 4.7 kΩ to VDD | Si549: "must be connected to VDD via an external pull-up" |
| `IN_SEL` pull-up (R401) | 10 kΩ | Table 3: logic 1 ≥ VCC − 0.4 V, and **0.6 mA flows out at logic 0**, so there is an internal pull-up. Default (open) = CLK1 = the Si549. The FPGA drives it open-drain, so the high level is exactly VCC |
| ADCLK948 decoupling | 6 × 1 nF, one per VCC pin; 1 µF; 10 µF | Datasheet p.10 |

**Judgement calls**, not from a datasheet, which deserve the hardest look:

| Item | Choice | Reasoning |
|---|---|---|
| FB401 | ferrite, 600 Ω @ 100 MHz, ≥ 1 A | Keeps +3V3_D switching noise off the clock chips. The branch draws up to 483 mA |
| C401 | 10 µF ceramic | The datasheet mentions a 1 µF electrolytic for bulk; a ceramic does the same job with lower ESR |
| C422 | 100 nF at the Si549 | Its datasheet gives no decoupling recommendation |
| R412 | 49.9 Ω on Q3-bar | Loads Q3-bar like the instrument loads Q3 on J402, so the pair stays balanced |
| C409–C413 | 100 nF | Figures 21 and 22 show the capacitors without a value |

---

## 4. How the drawing was verified

| Check | Result |
|---|---|
| `_work/check_sheet.py clock`: all 30 specified nets exist with **exactly** their pins; interface nets carry their labels; the 10 no-connects are alone; all 119 pins of the 41 parts accounted for; no part missing or extra | **PASS** |
| The same check with one wire deleted on purpose | Fails, naming the pin: `CLK1_P: not connected: ['U401.5']` — the check can see an error |
| KiCad ERC on the sheet | 2 errors, both "power input not driven" on `+3V3_D` and `GND`: nothing drives them until the POWER sheet exists. 6 warnings, `isolated_pin_label` on the clock outputs, until the receiving sheets are drawn |
| Pin tables of the two new symbols | Si549 agrees with KiCad's stock Si570 pin for pin. The ADCLK948 has **no independent second source**, only its datasheet's own Figure 2 and Table 7, which agree |

The fan-out on the right is drawn so no lines cross: lines that rise turn top-first, lines that
fall turn bottom-first.

---

## 5. How to review this sheet

Open the project in KiCad and go into the CLOCK sheet. Keep this document and the two datasheets
next to it (`_work/datasheets/`, fetched by `_work/fetch_datasheets.py`). About 30 minutes.

1. **The plan (§1).** Do 400/500 MHz and dividing inside the AD9253 fit what you want from the
   SDR? That's the decision everything else hangs on.
2. **U401's pin numbers against the datasheet.** Page 6, Figure 2 and Table 7. This is the part
   with no second source. Check CLK0/CLK1, VREF/VT, IN_SEL, and that each `Qn` (true) sits on the
   higher of its two pin numbers.
3. **The two input networks against Figures 21 and 22** (page 11). CLK1 is differential; CLK0 is
   single-ended, with CLK0-bar tied to VT0 and VREF0.
4. **One output block against Figure 17** (page 9). The other three are identical.
5. **The judgement calls in §3.** They're the ones not backed by a datasheet.
6. **Anything that reads badly.** Layout, labels, where text lands. Fix that directly in KiCad: from
   now on the `.kicad_sch` is the source, and the generator is not re-run over hand edits.

To confirm the wiring after you've touched it:

```
py _work/check_sheet.py clock
```
