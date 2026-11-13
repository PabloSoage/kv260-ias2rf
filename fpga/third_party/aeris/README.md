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
