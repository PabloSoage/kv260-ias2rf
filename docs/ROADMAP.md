# Work plan

*21 September 2026 · Rev03 architecture*

Every phase has a **verifiable exit criterion**. A phase is not finished because files were
touched; it is finished when its criterion is met. Rev01 was declared complete with no exit
criteria, and that is where all of it came from.

---

## Phase 0 — Close the blockers ✅ COMPLETE

| Blocker | Outcome |
|---|---|
| **B-01** — Interface to the Kria | ⛔ **Against.** IAS0 ends at the AP1302 ISP; there is no 40-pin RPi header; the GTHs are not reachable. Real budget: **8 pairs + ~14 loose signals** |
| **B-02** — AD9253 1-lane mode | ⛔ **Against.** Capped at **62.5 MSPS** |
| **B-03** — RF switches | ✅ **In favour.** M3SWA2-34DR+ has an internal driver, positive 3.3 V control |
| **B-04** — AERIS-10 IF | ✅ **In favour.** 120 MHz; the `BPF2` filters are unspecified placeholders |
| **B-05** — Extended variant | ⚠️ **Partial.** Not published. Sized for 8 chips |

Evidence and sources in [BLOCKERS_AND_RISKS.md](BLOCKERS_AND_RISKS.md). Consequence: the Rev02
architecture was not realisable and has been replaced by **Rev03, with a front-end FPGA**.

Still outstanding — not blocking the decision, but blocking schematic sign-off:

| Task | Source |
|---|---|
| Exact `VCCO` of the HPA bank as the KV260 sets it | Carrier card schematic |
| Confirm the AERIS Extended variant (B-05) | The project's author |
| Measure the mechanical envelope on the KV260 | The physical board |

---

## Phase 0.5 — Architecture decision ✅ DECIDED (21 September 2026)

**The front-end FPGA is accepted.** The reason is the one in phase 0: the KV260 does not expose
enough pins for a converter to connect directly.

**The radar is AERIS-10**, for surveillance at range, understood as a project rather than
something that will be operated (see the licensing position in
[BLOCKERS_AND_RISKS.md](BLOCKERS_AND_RISKS.md) R-06).

**Obstacle detection leaves this board.** It will be a commercial automotive radar connected over
USB — cheaper, licence-free at 76–77 GHz, and purpose-built. It is therefore **not** a subsystem of
this adapter, and nothing in the schematic has to account for it.

The comparison that led here:

| | With front-end FPGA | Without |
|---|---|---|
| Radar resolution | **0.75 m** | 3.0 – 6.0 m |
| RX channels | 2 at 400 MSPS + 2 for SDR | 2 at 62.5 MSPS |
| Direction finding | **4 coherent channels** | 2, with ambiguity |
| Transmission | 14 bits, local bus | 8 bits split across 2 connectors |
| ADAR1000 control | Trivial, with a synchronous strobe | Unsolved for 8 chips |
| AERIS firmware | **Runs almost unported** | Has to be rewritten |
| Connectors used | J8 + Pmod | J8 + J9 (FFC) + Pmod |
| Board complexity | **An FPGA board**: boot, sequencing, JTAG | Passive board |
| Second toolchain | Yes (Vivado for the front-end FPGA) | No |

**Exit criterion:** decision taken and recorded. Without it, any schematic is wasted work.

> **Note:** the DSP core for the "with FPGA" branch already exists and is measured on silicon —
> [scanner64](https://github.com/PabloSoage/scanner64). That removes a large part of the risk from
> this decision: the hard question (can the PL sustain a converter stream in real time?) has been
> answered with hardware.

---

## Phase 1 — Frozen specification

| Task | Deliverable |
|---|---|
| Fix the ADC sample rate and lane mode | Update §4.1 of the master document |
| Fix the DAC bus width, rate and part | Update §5.1 |
| Freeze the pin-by-pin map of IAS1, J9 and the Pmod | Complete assignment table, with physical pins |
| Freeze the control connector to AERIS-10 | IDC 2×20 pinout, with levels and directions |
| Per-rail current budget from datasheet figures | Replace the `[E]` estimates in §10.1 |
| Define the 6-layer stackup with computed impedances | Stackup sheet for the fabricator |

**Status (21 September 2026):** partly done — see [INTERFACE_SPEC.md](INTERFACE_SPEC.md).

| Item | State |
|---|---|
| Pin map of J8 and the Pmod | ✅ frozen |
| Mechanical envelope | ✅ measured from the official 3D model |
| Growth direction within that envelope | ❌ needs XTP681, or a ruler on the assembled board |
| `VCCO` of the HPA bank | ❌ **needs XTP682**, the carrier card schematic |
| Per-rail current budget | ⬜ pending datasheets |
| 6-layer stackup | ⬜ pending fabricator |

**Exit criterion:** the master document with no `[?]` marks left in sections 4, 5, 6 and 10, and
the power `[E]` marks replaced by datasheet values.

---

## Phase 2 — Schematic

Start from `CSI2-KRIA-KV260_Rev01-2.kicad_sch` (the purge, which is valid work). The two
script-generated sheets have already been **removed** from the project and moved to
`_deprecated/`.

> **Manual capture in the KiCad GUI, not script generation.** See the
> [method note](AUDIT_Rev01.md#8-method-note). Scripts are for purging and extracting data, not for
> drawing circuits nobody will be able to review.

| Sheet | Contents |
|---|---|
| Root | Hierarchy and the Hirose connectors |
| `IAS_LINK` | Hirose IAS1, the serial link to the Kria, terminations |
| `CONVERTERS` | ADC, DAC, input conditioning, reconstruction filter |
| `CLOCK` | Reference selector, TCXO, ADCLK944 with coupling and bias |
| `ROUTING` | 4 SPDT switches, IF SMAs, clock SMAs |
| `CONTROL` | Pmod header, front-end FPGA (if adopted), level translators, IDC to AERIS and the SDR board |
| `POWER` | Full tree with reverse-polarity protection and analogue/digital separation |

**Non-negotiable quality requirements:**

- Symbols with **correct electrical types** on every pin. If an EasyEDA symbol arrives with
  everything marked `Unspecified`, fix it before using it: otherwise ERC checks nothing.
- Connections with **wires**, not labels alone. Labels are fine for buses and rails; RF and power
  topology has to be visible.
- An explicit `no_connect` on every deliberately unused pin.

**Prerequisite — multi-channel annotation.** ✅ **Done** (21 September 2026). It had two causes:
duplicate instance references on the shared sheet, and a root schematic whose declared UUID did not
match its own instance paths. Both fixed by `_work/fix_multichannel_annotation.py`. The netlist now
exports with 48 components and 61 nets, so `Update PCB from Schematic` is unblocked and phase 3 can
start once the schematic is done.

**Exit criteria:**

1. ERC with **zero errors** and warnings justified one by one in an exclusions file.
2. `kicad-cli sch export netlist` succeeds.
3. Visual review sheet by sheet against the master document.
4. Every BOM item with a real part number, package and checked availability.

---

## Phase 3 — Layout

| Task | Note |
|---|---|
| Extend the board outline | Keeping the two Hirose positions fixed |
| Define the 6-layer stackup in KiCad | With the fabricator's real dielectrics and thicknesses |
| Placement | Converters and clock as close to the Hirose as possible |
| Route the IAS pairs | 100 Ω differential, length-matched, continuous reference plane |
| Route the DAC bus | Series termination at source, close return path |
| Power planes | Real separation between analogue and digital, ferrites at the junctions |
| Route the IF lines | 50 Ω to the SMAs |

**Exit criteria:**

1. DRC with zero errors **and the correct rules enabled** (not inherited from the import).
2. Zero unconnected pads — and this time with actual pads.
3. Impedances verified with the fabricator's stackup calculator.
4. Manufacturability review with the chosen fabricator before ordering.

---

## Phase 4 — Prototype and bring-up

Deliberate order: each step validates the previous one and does not depend on the next.

| Step | What it validates | How |
|---|---|---|
| 1 | Power | Voltages and ripple on every rail, with no converters fitted |
| 2 | Clock | ADCLK944 outputs on the scope: levels, jitter, terminations |
| 3 | **IAS1 link to the PL** | Inject a known sine at the ADC input and recover it in the PL. **This is the critical validation of the whole project** (it closes B-01 in practice) |
| 4 | **PL to DAC link** | Generate a sine from the PL and see it at the DAC output |
| 5 | DAC bus crosstalk | Sweep the sample rate until the real limit appears |
| 6 | Switches and routing | The 3 operating modes |
| 7 | Integration with AERIS-10 | Common clock, IF both ways, beam control |

**Exit criterion:** a closed loop DAC → switch → switch → ADC working, with the signal generated by
the PL recovered by the PL.

---

## Phase 5 — Gateware

Can overlap phases 2 and 3.

| Task | Note |
|---|---|
| ADC serial LVDS receiver | `ISERDESE3` + frame alignment |
| DAC bus generator | |
| SPI master and beam control | |
| Port the AERIS-10 radar processing | Adapt clock (400 → 80/125 MHz), bits (8 → 14), host (USB → AXI/DMA) |
| SDR chain | DDC, decimation, demodulation. **Reuse [scanner64](https://github.com/PabloSoage/scanner64)** |
| Host application | |

**Exit criterion:** ADC capture and DAC generation working on real hardware, with the AERIS firmware
regressions passing in the new clock domain.

---

## Later phases

- **SDR front-end board.** Independent. Can start as soon as phase 1 freezes the IF interface.
- **Integration with AERIS-10X.** Depends on the author publishing the Extended variant (B-05).

---

## Current state

**Phase 0 complete. Blocked at phase 0.5**, awaiting the front-end FPGA decision.

### Work done on the KiCad files

| Action | State |
|---|---|
| Removed the **34 empty footprints** Rev01 had inserted in the `.kicad_pcb` | ✅ Done. Prior copy in `_backup_original/CSI2-KRIA-KV260_Rev01_preRev02cleanup.kicad_pcb` |
| Verified file integrity after the edit | ✅ Balanced parentheses; **488 pads untouched**, none belonged to the deleted footprints |
| Kept the 5 pad-less footprints that **are** original to the import (`LA1`, `T1`, `T2`, `J5_IAS0`, `J5_IAS1`) | ✅ |
| **Removed the two dead sheets from the project** (`FRONTEND`, `PHASED_ARRAY`) | ✅ Done by `_work/rev03_drop_dead_sheets.py`. Moved to `_deprecated/` |
| **ERC measured before and after** with `kicad-cli 10.0.1` | ✅ **1130 → 427 violations.** All the serious electrical categories at zero |
| Repository cleaned for publication | ✅ Broken `.history` gitlinks, autosave zips and `.kicad_prl` untracked. 67 MB → 25 MB |

**What has deliberately not been done, and why:**

- **No new schematic drawn.** The architecture changed when B-01 closed and the phase 0.5 decision
  is open. Drawing now would be wasted work.
- **No placement or routing.** Same reason, and because doing it by hand-writing S-expressions
  would produce exactly the kind of unreviewable artefact that caused the Rev01 problems.
- **The board outline has not been extended** and the 6-layer stackup is not defined: both depend on
  the architecture decision and on the mechanical envelope, which is still unmeasured.
- **No pinouts invented.** Symbols for the new parts will be built from their datasheets, with
  correct electrical types, not copied from untyped third-party libraries.
