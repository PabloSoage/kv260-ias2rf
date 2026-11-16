# RFFC5072 programming guide (RX_VU converter, U1312)

How software brings up the VHF/UHF converter of the Rev08 front end (RX_VU_SPEC §1) and tunes it to each band of
the frequency plan (REV08_PLAN §5.6). Sources: the RFFC5071/5072 data sheet DS140110 [DS], and the open-source
HackRF firmware, which drives the RFFC5071 (the same synthesiser, serial block and register map, with a second
mixer) in production [HackRF: `firmware/common/rffc5071*.c`, `rffc5071_regs.def`]. RFMD's separate "Register Map
and Programming Guide", which [DS] refers to, is no longer published; where this guide relies on HackRF for a
detail that [DS] does not state, it says so, and the first board confirms it (§7).

## 1. What the board gives the chip

| Item | On this board | Consequence |
|---|---|---|
| Reference | 26 MHz TCXO (`1XXD26000MAA`), AC-coupled | R = 1, phase detector at 26 MHz; step 0.1–6.2 Hz (§4) |
| `MODE` | Tied high (R1345) | PLL bank 2 and mixer 2, the RFFC5072's only mixer [DS p.9] |
| `ENBL` | Expander `P17`, pulled low (R1343) | Converter off at power-up; a rising edge starts VCO selection and coarse tuning [DS p.9] |
| `RESETX` | Expander `P15`, pulled high (R1344) | Power-on reset is internal; the pin is only for recovery |
| `ENX`, `SCLK`, `SDATA` | Expander `P11`, `P12`, `P13` | Three-wire bus, bit-banged through the TCA6416A; `SDATA` is turned around for read-back |
| `GPO4` / `LD` | Expander `P14` (input) | Lock detect, once the `LOCK` bit routes it to the pin (§3) |
| Output balun | TC4-1W+, mixer current through its centre tap | `P2MIXIDD` ≤ 3 (about 30 mA, the balun's DC rating) |

The expander is U1313, a TCA6416A at I²C address 0x20 on the `XO_SCL`/`XO_SDA` bus that the Artix-7 masters
(`hk_i2c_master`). Every edge on the three-wire bus is one write to the expander's output port 1 (register
`0x03`), so one RFFC5072 register costs about 58 I²C writes of three bytes each. At the bus's 100 kHz
(`CLK_DIV` 250 at 100 MHz) a three-byte write takes about 0.29 ms, so one register takes **about 17 ms** and the
power-on table of §3 about half a second. That is fast enough for tuning by hand or by band; a gateware three-wire
master is the upgrade if fast hopping is ever needed.

**Reaching the expander from the Kria.** The raw I²C registers `XO_RAW` (`0xB0`/`0xB4`, LINK_PROTOCOL's CSR map)
carry a register address, a data byte and a read/write bit, but no device address: `clk_mode_ctrl` sends every raw
request to the Si549 (`SI549_ADDR`, 0x55). In today's gateware the Kria therefore cannot write the TCA6416A at
0x20. Rev08 item G-2 (REV08_PLAN §7) turns `hk_xo_ctrl` into a shared master for the Si549 and both expanders, and
G-3 adds the RFFC5072 and PE4312 sequencers on top of it; until then the sequence below can only be exercised in
simulation.

## 2. The three-wire bus

The protocol below is HackRF's working implementation [HackRF `rffc5071_spi.c`]; [DS] gives the pins only.

- Data is driven while `SCLK` is low and sampled on the rising edge, MSB first.
- **Two clock pulses with `ENX` high** before every transaction, and **one after** it. HackRF notes that the
  device needs them although they are not clearly documented.
- `ENX` low, then a **9-bit header**: one leading 0, the read/write bit (1 = read), and the 7-bit register
  address.
- **Write:** 16 data bits follow, then `ENX` high.
- **Read:** after the header the master releases `SDATA` (expander `P13` to input), gives **one turnaround
  clock**, then clocks 16 bits in. Read-back register `0x1F` returns what `READSEL` (register `0x1D`, bits 15:12)
  selects.

## 3. Bring-up sequence

1. Expander: port 1 pins `P11` (`ENX`) high, `P12` low, `P13` low, `P15` (`RESETX`) high, `P17` (`ENBL`) low,
   all outputs except `P14`; this matches the pull resistors, so nothing glitches.
2. Write the 31 registers `0x00`–`0x1E` with the power-on values below (HackRF writes the same table at start so
   that a warm restart behaves like a cold one).
3. Read the device ID: `READSEL` = 0 in `0x1D`, read `0x1F`. HackRF accepts the part when bits 15:3 read 4416
   (`0x8A0x`); record what the RFFC5072 returns on the first board (§7).
4. Configure:
   - `0x16` `GPO`: `LOCK` (bit 0) = 1, so `GPO4` carries lock detect to `P14`; `GATE` (bit 1) = 1.
   - `0x03` `VCO_CTRL`: `REFST` (bit 3) = 1, reference kept running in standby for the fastest lock [DS p.7].
   - `0x09` `PLL_CTRL`: `TVCO` (bits 10:6) = 31, the longest VCO warm-up (HackRF).
   - `0x12` `FN_CTRL`: `SDM` (bits 13:12) = 3, dither off (HackRF; revisit if fractional spurs show, §6).
   - `0x0B` `MIX_CONT`: `P2MIXIDD` (bits 11:9) between 1 and 3; `FULLD` (bit 15) = 0.
   - `0x15` `SDI_CTRL`: leave `SIPIN` = 0, so `ENBL` and `MODE` stay on their pins. (HackRF sets `SIPIN` = 1 and
     drives `ENBL` by register; either works here.)
5. Tune (§4), then take `ENBL` high: VCO auto-select and coarse tuning run, then the PLL locks [DS p.9].
6. Wait for `P14` high, or poll read-back with `READSEL` = 1 (bit 15 of `0x1F` is lock). With a 26 MHz phase
   detector allow 1 ms; HackRF waits 1 ms at 40 MHz.
7. Expander port 0: `VU_CONV_ON` (`P06`) high, preselector path (`P00`–`P04`), `VU_LNA_ON` (`P05`); then the
   PE4312 attenuation (it powers up at 31.5 dB).

Power-on register values [HackRF]:

| Reg | Value | Reg | Value | Reg | Value | Reg | Value |
|---|---|---|---|---|---|---|---|
| `0x00` | `0xFFFB` | `0x08` | `0xFC06` | `0x10` | `0x89D8` | `0x18` | `0x0281` |
| `0x01` | `0x4064` | `0x09` | `0x8220` | `0x11` | `0x9D00` | `0x19` | `0xF00F` |
| `0x02` | `0x9055` | `0x0A` | `0x0202` | `0x12` | `0x2A80` | `0x1A` | `0x0000` |
| `0x03` | `0x2D02` | `0x0B` | `0x0400` | `0x13` | `0x0000` | `0x1B` | `0x0000` |
| `0x04` | `0xB0BF` | `0x0C` | `0x1A94` | `0x14` | `0x0000` | `0x1C` | `0xC840` |
| `0x05` | `0xB0BF` | `0x0D` | `0xD89D` | `0x15` | `0x0000` | `0x1D` | `0x0000` |
| `0x06` | `0x0028` | `0x0E` | `0x8900` | `0x16` | `0x0206` | `0x1E` | `0x0005` |
| `0x07` | `0x0028` | `0x0F` | `0x1E84` | `0x17` | `0x4900` | | |

## 4. Tuning

The LO is the VCO divided by `LO_DIV` = 2^`n_lo`; the VCO runs between 2.7 and 5.4 GHz (HackRF's limits; [DS]
quotes 3.0–5.2 GHz examples), so `n_lo` is the smallest
value that puts `LO × 2^n_lo` above 2.7 GHz. The feedback path divides the VCO by the prescaler `P` (2 up to
3.2 GHz, 4 above, with the charge-pump leakage `PLLCPL` in `0x00` bits 2:0 set to 2 and 3 respectively) and by the
fractional N:

    N = f_VCO / (P × 26 MHz),   N = n + frac / 2^24,   step = 26 MHz × P / (2^24 × LO_DIV)   [DS p.7]

Bank 2 registers:

| Reg | Bits | Field |
|---|---|---|
| `0x0F` `P2_FREQ1` | 15:7 `n`, 6:4 `n_lo`, 3:2 `PRESC` (1 = ÷2, 2 = ÷4), 1:0 `VCOSEL` (0, auto-select on) | Integer part and dividers |
| `0x10` `P2_FREQ2` | 15:0 | `frac` bits 23:8 |
| `0x11` `P2_FREQ3` | 15:8 | `frac` bits 7:0 (bits 7:0 of the register are 0) |

After a new frequency, either toggle `ENBL` low and high or set `RELOK` (`0x09` bit 3, self-clearing): both rerun
the VCO selection [DS p.9]. Rerun it also after a 30 °C change while enabled [DS p.9]; a lost lock flag is the
sign.

### 4.1 The bands of the frequency plan

The IF is centred on 135 MHz (REV08_PLAN §5.6). LO above the signal for UHF, below it for ADS-B (the side whose
image the preselector filter rejects). Values computed with the code of §4.2; "error" is the programmed LO minus the wanted LO, in Hz.

| Band | RF (MHz) | LO (MHz) | LO_DIV | f_VCO (MHz) | P | `n` | `0x0F` | `0x10` | `0x11` | Error (Hz) | Step (Hz) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| PMR446 | 446.1 | 581.1 | 8 | 4648.80 | 4 | 44 | `0x1638` | `0xB333` | `0x3300` | −0.16 | 0.78 |
| 70 cm | 435 | 570 | 8 | 4560.00 | 4 | 43 | `0x15B8` | `0xD89D` | `0x8A00` | +0.12 | 0.78 |
| TETRA | 390 | 525 | 8 | 4200.00 | 4 | 40 | `0x1438` | `0x6276` | `0x2700` | −0.30 | 0.78 |
| ADS-B | 1090 | 955 | 4 | 3820.00 | 4 | 36 | `0x1228` | `0xBB13` | `0xB100` | −0.36 | 1.55 |
| 868 MHz | 868 | 1003 | 4 | 4012.00 | 4 | 38 | `0x1328` | `0x93B1` | `0x3B00` | −0.12 | 1.55 |
| GNSS L1 | 1575.42 | 1440.42 | 2 | 2880.84 | 2 | 55 | `0x1B94` | `0x6698` | `0xD000` | +0.08 | 1.55 |
| 2.4 GHz | 2440 | 2305 | 2 | 4610.00 | 4 | 44 | `0x1618` | `0x53B1` | `0x3B00` | −0.24 | 3.10 |
| Lowest LO | | 85 | 32 | 2720.00 | 2 | 52 | `0x1A54` | `0x4EC4` | `0xEC00` | −0.03 | 0.10 |
| Highest LO | | 4200 | 1 | 4200.00 | 4 | 40 | `0x1408` | `0x6276` | `0x2700` | −2.38 | 6.20 |

The TCXO's own tolerance (a few ppm) is far larger than the step: at 1 GHz, 2 ppm is 2 kHz. The receiver's
DDC takes out the remaining offset, or the LO is trimmed against a known carrier.

### 4.2 Reference code

```python
def rffc5072_regs(lo_hz, fref=26e6):
    n_lo = 0
    while lo_hz * 2 ** n_lo <= 2.7e9 and n_lo < 5:
        n_lo += 1
    fvco = lo_hz * 2 ** n_lo
    presc = 2 if fvco > 3.2e9 else 1               # field value: 1 = /2, 2 = /4
    ntot = fvco / (fref * 2 ** presc)
    n, frac = int(ntot), round((ntot - int(ntot)) * 2 ** 24)
    if frac == 2 ** 24:
        n, frac = n + 1, 0
    return {0x0F: (n << 7) | (n_lo << 4) | (presc << 2),
            0x10: frac >> 8,
            0x11: (frac & 0xFF) << 8,
            "PLLCPL": 3 if presc == 2 else 2}
```

## 5. Power and standby

- `ENBL` low turns the analog blocks off; with `REFST` = 1 the reference circuits stay on (about 2 mA) for a fast
  restart, with `REFST` = 0 they need the `SU_WAIT` warm-up [DS p.7].
- `VU_CONV_ON` low routes the direct 30–170 MHz path around the converter; take `ENBL` low as well, so the LO
  is off when it is not used (REV08_PLAN's risk table: LO coupling into an ADC or the clock tree).

## 6. Things to watch

- **Mixer current.** Up to 45 mA is available [DS p.7], but the TC4-1W+ carries the mixer current through its
  centre tap and is rated 30 mA: keep `P2MIXIDD` ≤ 3 (RX_VU_SPEC §1.4).
- **Fractional spurs.** Dither is off (HackRF's setting). If a spur lands in the IF, turn dither on (`SDM`) or move
  the LO by a step that keeps the signal inside the 100–170 MHz IF window.
- **Lock detect window.** The flag reports a tuning voltage of 0.30–1.25 V [DS p.6]; it drops when temperature
  drifts the VCO, which is the cue to rerun calibration (`RELOK`).
- **LO leakage.** The LO is always above 230 MHz, in the anti-alias filter's stop band; at the ADC it appears as
  one tone at a known frequency (REV08_PLAN §5.6 "LO as seen by the ADC").

## 7. To confirm on the first board

| Item | How |
|---|---|
| Device ID read-back | §3 step 3; record the value here |
| Three-wire framing (leading clocks, turnaround) | A write then read-back of `0x0B` |
| Lock at every LO of §4.1 | `P14` and read-back bit 15; 1 ms after `ENBL` |
| Mixer current against `P2MIXIDD` | The 3.0 V rail's current |
| LO tone at the ADC | Spectrum at each band's LO, against the "LO as seen by the ADC" column |
