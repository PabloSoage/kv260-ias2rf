# AERIS-10 (`PLFM_RADAR`) Third-Party DDC Modules

- **Upstream repository:** `https://github.com/NawfalMotii79/PLFM_RADAR`
- **Upstream path:** `9_Firmware/9_2_FPGA/`
- **Upstream commit hash:** `62d4c556508927a4192acca24422bd16a979c7dc`

## Licence

The upstream `README.md` (`License -> Software and Firmware`) explicitly places `/9_Firmware` under the **MIT License**:

> "The software components—including:
> - FPGA code (VHDL/Verilog in `/9_Firmware`)
> - Microcontroller firmware (STM32)
> - Python GUI and utilities
>
> remain under the **MIT License** for maximum flexibility."

Note: the hardware files of `PLFM_RADAR` use CERN-OHL-P v2 (in upstream root `Licence`), whereas software and firmware under `9_Firmware/` are MIT-licensed as quoted above.

## Files imported (DDC chain only)

| File | Upstream source | Role |
|---|---|---|
| `ddc_400m.v` | `9_Firmware/9_2_FPGA/ddc_400m.v` | `ddc_400m_enhanced` + `lfsr_dither_enhanced` (400 MSPS -> 100 MSPS I/Q DDC top for 120 MHz IF) |
| `nco_400m_enhanced.v` | `9_Firmware/9_2_FPGA/nco_400m_enhanced.v` | `nco_400m_enhanced` 6-stage pipelined NCO (`PHASE_INC_120MHZ = 32'h4CCCCCCD`) |
| `cic_decimator_4x_enhanced.v` | `9_Firmware/9_2_FPGA/cic_decimator_4x_enhanced.v` | `cic_decimator_4x_enhanced` 5-stage 4x CIC decimator |
| `fir_lowpass.v` | `9_Firmware/9_2_FPGA/fir_lowpass.v` | `fir_lowpass_parallel_enhanced` 32-tap symmetric low-pass FIR compensation filter (100 MHz) |
| `cdc_modules.v` | `9_Firmware/9_2_FPGA/cdc_modules.v` | `cdc_adc_to_processing`, `cdc_single_bit`, `cdc_handshake` Gray/handshake CDC helpers |
| `ddc_input_interface.v` | `9_Firmware/9_2_FPGA/ddc_input_interface.v` | `ddc_input_interface` 18-bit to 16-bit convergent rounding + saturation |

## Local changes

Timing and reset changes for 400 MHz at 77 % LUT are marked in each file. Two changes alter the NCO's output (`tb_nco_image`):

- `nco_400m_enhanced.v`: the quarter-wave table is `round(32767 * sin(2 pi (k + 0.5) / 256))`. The upstream table, sampled at `k`, put `cos` (or `sin`, in odd quadrants) one step away from the other output under the `63 - k` fold, so the image of the input around the LO was about 52 dB down.
- `ddc_400m.v` and `nco_400m_enhanced.v`: a byte from a 23-bit LFSR (x^23 + x^18 + 1, eight steps per clock) is added to accumulator bits `[23:16]` before the 8-bit truncation. The upstream 8-bit LFSR dithered the FTW's low byte instead, which left the truncation error periodic at a 120 MHz LO and its image between 46 and 61 dB down.
