# Rev06 review: the board, its enclosure and both FPGAs together

*14 November 2026, branch `rev06`, before ordering. Every check below was re-run on the final board file.*

Rev06 makes two changes and one addition:

- **Ethernet:** the PHY gets its own Artix pins (CONTROL_SPEC §8), so IAS1 is complete and Ethernet adds to it.
- **Fan header:** enclosure v2's fan gets a header (POWER_SPEC §1.2).
- **Added:** the closed enclosure, in two versions (ENCLOSURE.md).

This review covers every area the owner asked for:

- RF / UHF;
- power;
- ESD and static;
- thermal;
- routing;
- an end-to-end simulation of the system.

It also covers the mechanical side. Each item has a verdict:

- **OK**;
- **Accepted** (a known compromise, quantified);
- **Open** (to close before or after ordering, with who closes it).

---

## 1. Design rules and connectivity

| Check | Result | Verdict |
|---|---|---|
| KiCad DRC with zone refill and schematic parity | 0 errors, 0 unconnected items, parity 0. One warning, a footprint differing from its library copy (D1003) | OK |
| Supply tracks on the ground planes L2/L5 | none (`_work/layout/planechk.py`) | OK |
| Fabrication outputs | gerbers, BOM (129 lines, 551 parts) and CPL regenerated from the final board on 14 Nov, after the last routing change; DRC on the zone-filled copy 0 errors, 0 unrouted (FABRICATION.md) | OK |

## 2. High-speed and RF routing

Compared against Rev05, with the same checks run on both board files. Rev05 had been reviewed in full (SIGNAL_INTEGRITY.md, RF_REVIEW_GEMINI.md §12).

| Check | Rev05 | Rev06 | Verdict |
|---|---|---|---|
| Fast segments over a void of their reference plane for more than 1 mm | 6 runs, 6 mm of 3,236 mm | 6 runs, 6 mm of 3,228 mm (the same six: F_CCLK, F_DACR_CLK, PMOD_SCLK, 1.0–1.2 mm each) | OK |
| Reference-plane changes without a ground via within 1 mm (RF) / 3 mm (others) | 0 of 98 | 0 of 96 | OK |
| LVDS P/N skew, end to end | all pairs within ±9 ps except CLK_ADCS +23, CLK_FPGA −41 (Rev05, documented) | unchanged; ETH_SGTX +2 ps, ETH_SGRX −4 ps, LINK_RX_D0 +0 ps (re-matched) | OK |
| Stubs on LVDS legs | ≤ 9 ps on the data pairs | ETH legs 6–9 ps (the bias resistors now sit on the legs) | OK |
| Eyes at 1.25 Gb/s (SGMII) | — | FPGA → PHY 616 mV, PHY → FPGA 521 mV (> 200 mV needed) | OK |
| Parallel runs closer than 3 widths for > 2 mm | 56 pairs of nets | 55 pairs. One is new and one is dropped: **ETH_MDIO beside LINK_RX_D1_N**, 16.5 mm at 0.18 mm on L1 | Accepted, below |
| Analogue and clock neighbours | — | two new short pairings, both negligible (CONTROL_SPEC §8) | OK |

**ETH_MDIO beside LINK_RX_D1_N.**

- **Coupling.** At 0.18 mm the backward coupling is about 12 % (SIGNAL_INTEGRITY §3.5's field-solver figures).
- **Edges.** MDIO's edges with SLEW = SLOW are about 3 ns. The run is 16.5 mm, much shorter than the 240 mm a
  3 ns edge would need to saturate.
- **Induced noise.** About 25 mV on the one leg, mostly common mode, and only while an MDIO frame is on the wire.
  The 1 Gb/s link has 350 mV of swing and the receiver needs 100 mV.
- **Same case:** ETH_MDC beside ETH_SGTX_FPGA_P (12 mm at 0.18 mm on L6).
- **Mitigation (gateware):**
  - SLEW SLOW, DRIVE 4 on both lines;
  - MDIO polled, never free-running.
  - Asked of the gateware with task 22.

**RF front end and UHF.** Rev06 does not touch the RF band. These are unchanged from Rev05 and reviewed there:

- SMA launches, switch cells, DC blocks, the ESD diodes' compensation;
- the DAC reconstruction filters (re-tuned 13 Nov, RF_REVIEW_GEMINI §12);
- the RF stitching.

The new parts sit away from the band:

- the PHY's pairs;
- the bias network (R1212/R1217/C1222);
- the fan header.

## 3. Power

| Check | Result | Verdict |
|---|---|---|
| Worst neck per rail, against the current it carries (IPC-2221) | No new neck. Rev06 removed Rev05's worst one, +1V8_A 0.1 mm on L3 at 0.5 A (+242 °C on the long-track chart), with a 1.0 mm jog | OK |
| +1V8_A drop, LDO to the ADCs' ferrites | 64 mV at the 500 mA budget; the LDO is set to 1.85 V for it (POWER_SPEC) | OK |
| +2V5 to bank 34's VCCO | 19 mV (Rev05: 11 mV): two VCCO balls on a 0.1 × 13.7 mm track after the corner rework | Accepted (CONTROL_SPEC §8) |
| +3V3_D to FB401 (clock section, 0.48 A) | 10 mV, four 0.1 mm necks 0.2–0.5 mm long between the PHY's pads (from Rev05) | Accepted |
| +1V8_A main run, 0.3 mm on L3 at the full 0.5 A budget | about +40 °C on IPC-2221's inner-layer chart (a conservative chart; IPC-2152 gives far less for inner layers in a plane stack) | Accepted, measure at bring-up |
| FB401 as the clock section's only filter (RF_REVIEW H3) | Modelled on 14 Nov (`_work/power/fb401_filter.py`, [plot](sim/fb401_filter.png)): +3V3_D carries 4.6 mVpp at 580 kHz. With the bead's inductance swept down to 5 % of its zero-bias value under the 483 mA DC, +3V3_CLK keeps ≤ 2.1 mVpp with the new bead (0.65 mVpp with the old), which puts the Si549's supply spur under −110 dBc (its datasheet: −82 dBc for 50 mVpp). The ADCLK948 would need its delay to move by more than 40 ps per volt of supply to make a −90 dBc spur on a 250 MHz input | OK; measure +3V3_CLK ripple at bring-up |
| FB401's DC drop | The drawn bead (600 Ω, 1 A, 0.2 Ω max) dropped up to 97 mV: with +3V3_D at its low tolerance (3.235 V) and 10 mV of copper, +3V3_CLK could reach 3.128 V, 7 mV under the Si549's 3.135 V minimum | **Fixed**: FB401 is now the 220 Ω, 2 A, 0.1 Ω bead already on the BOM (C304314, same 0603 footprint). Drop 48 mV, +3V3_CLK ≥ 3.177 V; the bead runs at 24 % of its rating, so it keeps most of its inductance |
| Fan header J1002 | 5 V through a 0.5 A PTC (F1002) and 10 µF; the fan draws ~0.1 A | OK |
| Ethernet PHY bias ETH_VCM | 1.18 V from +3V3_D (10 k / 5.6 k, 100 nF), inside LVDS_25's 0.3–1.5 V | OK |

## 4. ESD and static

| Check | Result | Verdict |
|---|---|---|
| Every external connector protected | SMAs (PESD5V0F1BL), Pmod and JTAG (TPD4E05U06), 12 V input (SMBJ15CA/SMCJ33CA and the reverse-battery FETs) as Rev05. RJ45: magnetics in the jack, 1500 V isolation | OK |
| New connectors | J1002 (fan) stays inside the case. The 2 × 20 ribbon J1103 leaves the case to AERIS-10's ADAR1000 boards: static control lines, SLEW SLOW (CONTROL_SPEC §2) | OK |
| Floating metal | the case is printed (insulating); the SMA bodies and the KV260 are grounded to the board | OK |

## 5. Thermal

| Check | Result | Verdict |
|---|---|---|
| Ethernet PHY U1201 | 9 vias in its exposed pad (from 1, RF_REVIEW H6) | OK |
| Enclosure v1 (no fan on the adapter) | as the 13 Nov study: fine on a desk, marginal in a hot car | Accepted, v2 for vehicles |
| Enclosure v2 (fan over the adapter's hot strip) | CFD (ENCLOSURE_V2_THERMAL.md): every IC at least 18 °C under its limit at 25–45 °C ambient; at 70 °C the study's fan position left the Si549 and the K26 2–3 °C over | **Open**: the CFD of v2 as built (fan at the Si549's strip, heatsinks) is running (gateware/CFD task 23) |

## 6. Mechanical: the enclosure with the boards in it

The 3-D finite-element model of the enclosure as built, with both boards inside, is in ENCLOSURE.md §5.3, with
its stress and strain maps. It covers the printed geometry with every rib and cut-out, and the boards bonded where
they rest, under 50 g down, sideways and fore-aft.

| Check | v2 result (v1 alike) | Verdict |
|---|---|---|
| Case, 50 g down (worst) | 99.7th pct 3.6 MPa, safety factor 8.1 at 23 °C and 4.9 at 70 °C. Peak 9.3 MPa on the rib between the KV260's RJ45 and USB cut-outs above the right-rear ear: factor 3.2 / 1.9 | OK |
| Boards, at the BGAs | ≤ 160 µε at U1101, U501 and U601 (guide 500 µε) | OK |
| Boards, bow | adapter 0.16 mm, carrier 0.10 mm under 50 g | OK |
| Board strain peaks | 720–980 µε only at the bonded edges over the honeycomb (a modelling singularity, away from parts) | Accepted |

The renders were checked against the board:

- the 12 V jack, the RJ45 and the inductors' models now sit where the footprints put them (3D_MODELS.md);
- every connector that has to leave the case does: the KV260's rear I/O (one cut-out each), the adapter's RJ45,
  12 V jack, twelve SMAs and the ribbon to the antenna boards.

## 7. Both FPGAs together: the end-to-end simulation

The system bench (gateware task 22: `fpga/sim/tb_system.v` with board channel models from this file's delays and
jitter) runs both FPGAs' gateware together:

- the Artix front end;
- the 1 Gb/s two-lane uplink;
- the Kria PL and the downlink;
- SGMII Ethernet.

Every block bench passes (13 benches, with their mutations failing as they should).

**Open: the system bench fails at link training.**

- **Symptom:** the Kria's uplink eye scan finds almost no good taps.
- **Root cause, found on 14 Nov:** the Artix streams ADC packets on the uplink before the Kria has trained it. The
  scan only counts a tap as good after six consecutive idle or alignment blocks, so with a full data stream no tap
  qualifies.
- **Why the block benches pass:** they start sending packets only after link-up.
- **The fix, in the gateware:** hold the Artix's packets until the Kria reports its uplink trained, which it
  already sends back on the downlink. The board is not involved.
- **Owner:** gateware task 22. This review will be updated with the passing run.

## 8. Summary

- **Ready to order:** the board (DRC/parity clean, no new SI or power issue, all rules met).
- **Accepted:** the MDIO/MDC proximity to two fast legs, which is handled in the gateware.
- **Changed on 14 Nov:** FB401 is now a 2 A, 0.1 Ω bead (same footprint, a part already on the BOM), for the
  Si549's supply margin (§3).
- **Open, on the bench or in the gateware:**
  - the v2 CFD as built;
  - the link-training fix and its passing system simulation.

None of the open items needs a board change before ordering.
