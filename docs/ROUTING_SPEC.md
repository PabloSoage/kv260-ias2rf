# ROUTING sheet — specification and review guide

*25 September 2026 · `rev03/ROUTING.kicad_sch` · drawn by `_work/sheets/routing.py` from the
connection list in `_work/sheets/routing_spec.py`*

Four M3SWA2-34DR+ SPDT switches between the converters and the SMAs. Each converter port goes by
default to its own chain, and on command to the other one. The second SDR channels go straight to
their SMAs.

| Switch | Converter | RF1 — control low, **default** | RF2 — control high | What RF2 enables |
|---|---|---|---|---|
| SW1 (U901) | `IF_RX_A`, AD9253 ch A | `SDR_RX_A` | `AERIS_IF_A` | Radar IF sampled at 14 bits |
| SW2 (U902) | `IF_RX_B`, AD9484 | `AERIS_IF` | `SDR_RX_WB` | Wideband SDR at 400/500 MSPS, 8 bits |
| SW3 (U903) | `IF_TX_A`, AD9767 DAC1 | `SDR_TX_A` | `AERIS_TX_A` | Chirp from the 14-bit DAC |
| SW4 (U904) | `IF_TX_B`, AD9708 | `AERIS_TX` | `SDR_TX_WB` | SDR transmit from the fast 8-bit DAC |
| — | `IF_RX_C`, AD9253 ch B | `SDR_RX_C` (J951) | — | — |
| — | `IF_TX_C`, AD9767 DAC2 | `SDR_TX_C` (J952) | — | — |

---

## 1. Decisions this sheet makes, for your approval

| Decision | Evidence | Alternative |
|---|---|---|
| **The switching plan above** | ARCHITECTURE §7.4 asked for switches that *"let each converter channel be reassigned between the SDR chain and the radar chain"*, without naming the ports. This is the reading that gives each converter both uses and keeps each one's home chain as the default | A different pairing; it's only labels and SMA names |
| **Ten edge SMAs** | Every switch throw and every direct channel gets its own connector | U.FL for internal links. Ten SMAs need edge length the board may not have (INTERFACE_SPEC §5.3) |
| **The interface is single-ended**, `SW_CTRL0..3` one label per line | Single-ended, because that is how the M3SWA2 and the SMAs carry it (ADC_RADAR_SPEC §1.2). The control lines come one per label, as on the other sheets | — |
| **Pull-down on each control** (10 kΩ) | Keeps every switch on its default (RF1) while the FPGA is unconfigured. Control current is below 1 µA low (DC Electrical Specifications) | Pull-up, if the other chain should be the default |
| **DC block on every SMA** (100 nF) | Electrical Specifications, note 3: *"All RF-ports must be DC blocked or held at 0 V DC"*. The converter side is already at 0 V: the ADC inputs are terminated to ground and the DAC baluns' secondaries are grounded. The SMA side is whatever is plugged in. 100 nF into 50 Ω gives a 32 kHz corner, below the SDR's 100 kHz | — |

---

## 2. Every value, and where it comes from

The supply and control parts for each switch are the datasheet's **Figure 2, "Characterization
and Application Circuit"** (M3SWA2-34DR+, Rev. B, p.10), part for part:

| Item | Value | Datasheet |
|---|---|---|
| VDD series R, R9n1 | 11.5 Ω | R1 |
| VDD decoupling | 0.1 µF + 100 pF | C1, C2 |
| VDD zener | 5.6 V, SOD-123 | D1 (SZMMSZ5232BT1G) |
| VEE series R, R9n2 | 11.5 Ω | R2 |
| VEE decoupling | 0.1 µF + 100 pF | C4, C3 |
| VEE zener | 5.6 V, reversed | D2 |
| VCTRL series R, R9n3 | 100 Ω | R3 |
| NC pads 1, 12, 13 | to ground | *"Not used internally. Connected to ground on test board"* |

**Truth table** (p.3): VCTRL low connects RFC to RF1, high to RF2. Logic high is 1.8–3.6 V, so a
3.3 V or 1.8 V FPGA bank drives it directly.

**Footprint:** Mini-Circuits' 3×3 mm QFN (case DG1677, suggested layout PL-768), not stocked by
KiCad. It gets drawn at layout from PL-768.

---

## 3. How the drawing was verified

| Check | Result |
|---|---|
| `_work/check_sheet.py routing`: 43 nets exact, every pin of the 64 parts accounted for | **PASS** |
| KiCad ERC on the sheet | 1 × `power_pin_not_driven` on `-3V3`, until POWER exists. The local VDD/VEE nodes behind the 11.5 Ω resistors carry PWR_FLAGs |

---

## 4. How to review this sheet

About 20 minutes, with `M3SWA2-34DR+.pdf` from the AERIS-10 component folder.

1. **The switching plan and the SMA count** (§1). Those are your call.
2. **One switch block against Figure 2** (p.10). The other three are identical.
3. **U901's pads against the Pad Description** (p.10): RFC 15, RF1 3, RF2 10, VDD 8, VEE 5,
   VCTRL 6.

```
py _work/check_sheet.py routing
```
