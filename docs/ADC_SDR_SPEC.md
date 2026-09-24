# ADC_SDR sheet — specification and review guide

*24 September 2026 · `rev03/ADC_SDR.kicad_sch` · drawn by `_work/sheets/adc_sdr.py` from the
connection list in `_work/sheets/adc_sdr_spec.py`*

The SDR receive path: two single-ended inputs into two channels of the AD9253, each through an
AD8352. The same method and building blocks as [ADC_RADAR](ADC_RADAR_SPEC.md); read that one first,
this document only covers what differs.

```
IF_RX_A ──► U602 AD8352, 12 dB ──► AD9253 channel A ─┐
IF_RX_C ──► U603 AD8352, 12 dB ──► AD9253 channel B ─┴─► one lane each (ADCS_D0, ADCS_D1) + DCO + FCO
            AD9253 channels C and D unused
```

---

## 1. Decisions this sheet makes, for your approval

| Decision | Evidence | Alternative |
|---|---|---|
| **Two channels, not one.** A second SDR input, **`IF_RX_C`**, is added to the interface (and `IF_TX_C` for the AD9767's second DAC) | The interface already carried two data lanes (`ADCS_D0`, `ADCS_D1`), and ARCHITECTURE §5.1 had "2 of 4 channels"; but only one analogue input existed. Two channels give diversity, two antennas, or I/Q from a quadrature front end | One channel: drop U603 and its network, and the second lane |
| **AD8352 drivers**, as on the radar chain | One verified part for both ADCs, and a single-ended input without a balun. The AD9253 datasheet recommends a transformer for the best SNR (p.22); but a transformer gives no gain and most cut off above 100 kHz, which loses the bottom of HF. The SDR front end has its own LNA | A wideband 1:1 transformer (Mini-Circuits' T1-1T class reaches down to about 100 kHz; check the exact part): cheaper and quieter, no gain |
| **12 dB per channel** (Table 7: RG 120 Ω) | Full scale (2 V p-p) at about 0.5 V p-p in, **roughly −2 dBm**, a sensible top for an HF SDR behind an LNA | Any row of Table 7; one resistor per channel |
| **Channels C and D unused, inputs tied to VCM** | Their outputs are left open and they are powered down through SPI. Held at VCM, their inputs sit at the common mode with no differential signal | Leave them floating. The datasheet does not say either way |
| **SYNC tied low** | One ADC, so its clock divider has nothing to line up with | An FPGA line, if a second AD9253 is ever added |

---

## 2. What differs from ADC_RADAR

- **The inputs need a bias.** The AD9253's analogue inputs *"are not internally dc-biased"*
  (p.22). The centre tap of each channel's load legs goes to the ADC's **VCM** output through
  200 Ω, and VCM is decoupled at the pin, as in AD9253 **Figure 58**. On the AD9484 the inputs
  bias themselves.
- **Series resistors and shunt capacitor from AD9253 Figure 58:** 33 Ω per leg, 5 pF across.
- **One-lane mode**, set by SPI (register 0x21). In one-lane mode, channel A comes out on
  **D0±B** (pins 24/23) and channel B on **D1±B** (22/21), per Table 8 and its footnote 1. The
  sample rate must then be ≤ 62.5 MSPS, which is the 500 MHz master clock divided by 8.
- **Reference:** SENSE to ground selects the internal 1.0 V reference (Table 9). VREF is
  decoupled with 1 µF ∥ 0.1 µF, and RBIAS takes 10 kΩ 1 % (p.38, Table 8).
- **The footprint is stock:** CP-48-13 has a 5.60 mm pad (Figure 77), matching KiCad's
  `QFN-48-1EP_7x7mm_P0.5mm_EP5.6x5.6mm`.
- **A symbol layout was added for the AD9253**, like the AD9484's. It puts channel A at the top of
  the left side and channel B at the bottom, so each chain runs in without crossing the clock and
  SPI wires. The pin numbers are unchanged.

Every value, with its source, is in `adc_sdr_spec.py`. The judgement calls are the ferrites, as on
ADC_RADAR, and the decisions in §1.

---

## 3. How the drawing was verified

| Check | Result |
|---|---|
| `_work/check_sheet.py adc_sdr`: 55 nets exact, labels and rails named, 12 unused outputs alone, every pin of the 63 parts accounted for | **PASS** |
| KiCad ERC on the sheet | 2 × `pin_not_driven`, SCLK and CSB, until CONTROL drives them. The rails' "not driven" errors show once for the whole design, on ADC_RADAR |

---

## 4. How to review this sheet

About 30 minutes, with `_work/datasheets/AD9253.pdf` and `ad8352.pdf` (§2 of ADC_RADAR_SPEC).

1. **§1's decisions**, especially the second channel and the AD8352s instead of a transformer.
2. **U601's pins against Table 8** (p.12). The one-lane pins are the ones to check: 24/23 and
   22/21, and that 28–25 and 16–9 are the unused ones.
3. **One channel's input network against AD8352 Figure 26 and AD9253 Figure 58** (p.23). The
   other channel is identical.
4. **The reference pins:** SENSE, VREF, RBIAS and VCM against p.38.

```
py _work/check_sheet.py adc_sdr
```
