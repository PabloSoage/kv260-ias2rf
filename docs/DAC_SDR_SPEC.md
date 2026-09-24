# DAC_SDR sheet — specification and review guide

*25 September 2026 · `rev03/DAC_SDR.kicad_sch` · drawn by `_work/sheets/dac_sdr.py` from the
connection list in `_work/sheets/dac_sdr_spec.py`*

The SDR transmit DAC: the dual 14-bit AD9767 in interleaved mode, each DAC through the same output
network as [DAC_RADAR](DAC_RADAR_SPEC.md) (loads, AERIS-10's filter, balun).

```
DACS_D0..13 + IQWRT/IQSEL/IQCLK/IQRESET ──► U801 AD9767 ─┬─ DAC1 ──► filter ──► T801 ──► IF_TX_A
(FPGA, 3.3 V CMOS, one 14-bit port)       interleaved     └─ DAC2 ──► filter ──► T802 ──► IF_TX_C
```

Datasheet: AD9763/AD9765/AD9767 Rev. G, `_work/datasheets/AD9767.pdf`.

---

## 1. Decisions this sheet makes, for your approval

| Decision | Evidence | Alternative |
|---|---|---|
| **Interleaved mode** (MODE low) | The interface already carried one 14-bit bus plus `IQWRT`, `IQSEL`, `IQCLK` and `IQRESET`, which is what interleaved mode uses (p.25, *Interleaved Mode Timing*). It needs 18 FPGA lines instead of 32 | Dual-port mode: two 14-bit buses, 14 more FPGA lines |
| **Port 2's data pins tied to ground** | Unused in interleaved mode; CMOS inputs should not float. The datasheet doesn't say either way | — |
| **Independent gain** (GAINCTRL low), one full-scale network per DAC | p.22, *Gain Control Mode*. Each DAC can then be trimmed on its own; identical values here | Master/slave (GAINCTRL to AVDD): one RSET for both |
| **10 mA full scale**, RSET 3.83 kΩ | p.24: *"optimum distortion performance ... when the maximum full-scale signal at IOUTA and IOUTB does not exceed 0.5 V"*. 10 mA on 49.9 Ω is 0.5 V. Keeps the loads, filter and balun of DAC_RADAR | 20 mA (1.91 kΩ): 6 dB more output, more distortion |
| **The 256 Ω + 22 nF network on each FSADJ** | p.22: *"To ensure that the AD9763/AD9765/AD9767 performs properly, connect a 22 nF capacitor and 256 Ω resistor network ... from the FSADJ1 terminal to ground and from the FSADJ2 terminal to ground"* (Figure 59). The note under Figure 58 says it isn't needed with RSET = 2 kΩ; the text is the stronger statement, and the network costs two parts | Leave it out |
| **The same filter as the radar DAC** | Cut-off around 50 MHz, the right place for a DAC clocked up to 125 MSPS; one design for both. The SDR's own band plan may want its own later | A filter for the SDR transmit band |
| **SLEEP tied low** | It has an active pull-down (p.25); FPGA control not needed | An FPGA line |

**Still open, as on DAC_RADAR: the baluns T801 and T802 have no part yet.**

---

## 2. Other values

| Item | Value | Source |
|---|---|---|
| REFIO, C801 | 100 nF | p.22: *"simply decouple the REFIO pin to ACOM with a 0.1 µF capacitor"* |
| AVDD, DVDD1, DVDD2 decoupling | 100 nF per pin, 10 µF per rail | As the other converters |
| Supplies | AVDD on `+3V3_A`, DVDD on `+3V3_D` | Table 1: AVDD 3.0–5.5 V, DVDD 2.7–5.5 V |
| Footprint | `LQFP-48_7x7mm_P0.5mm` | 48-lead LQFP |

A symbol layout was added for the AD9767, like the others: port 1 and the IQ controls at the top
of the left side, every tied-low pin in one block under them (grounded by one bus), and each DAC's
outputs 15.24 mm apart on the right. The pin numbers are unchanged.

---

## 3. How the drawing was verified

| Check | Result |
|---|---|
| `_work/check_sheet.py dac_sdr`: 40 nets exact, every pin of the 37 parts accounted for | **PASS** |
| KiCad ERC on the sheet | 18 × `pin_not_driven`: the 14 data lines and 4 IQ controls, until CONTROL drives them |

---

## 4. How to review this sheet

About 25 minutes.

1. **§1's decisions**: interleaved mode and the 10 mA full scale.
2. **U801's pins against the Pin Function Descriptions** (p.10): port 1 on 1–14, the IQ controls
   on 17–20, MODE 48, GAINCTRL 42, the outputs 46/45 and 39/40.
3. **The FSADJ networks against Figure 59** (p.22).
4. **One output chain against DAC_RADAR's.** The other is identical.

```
py _work/check_sheet.py dac_sdr
```
