# JLCPCB order: quote

*10 November 2026, bare boards re-quoted on 8 layers on 12 November, parts, assembly and bare boards for the Ethernet option (140 × 132 mm) on 13 November, parts and assembly for Rev08 on 17 November · board CSI2-KRIA-KV260_Rev01 · not ordered yet*

What ordering the board from JLCPCB, made and assembled, would cost today. This is a budget, not an
order: nothing was uploaded and no cart was created. How to enter the order is in
[FABRICATION.md](FABRICATION.md); the files come from `python _work/fab/make_fab.py`.

**Prices are in US dollars, before VAT.** Stock and prices change daily: run
`python _work/fab/quote.py` again before ordering. It refreshes `_work/fab/quote.csv` and the parts
table in §4.

---

## 1. Summary

| | 2 assembled boards | 5 assembled boards | Source |
|---|---|---|---|
| Bare boards, 8 layers, 140 × 132 mm (5 made either way) | 287.96 | 287.96 | JLCPCB's quote page, §2 (13 Nov; same outline and stack since) |
| Assembly fees | 405.25 | 440.24 | JLCPCB's price page, §3 (17 Nov counts) |
| Parts (187 LCSC codes, 17 Nov) | 1,652.38 | 3,939.97 | JLCPCB's parts search, §4 |
| Si549 oscillator and TC1-1-13M+ balun, bought apart and consigned | ~45 `[E]` | ~110 `[E]` | No usable LCSC code, §5 |
| Shipping, UPS Express Saver, duties paid (DDP) | 26.08 | 26.08 | Quote page, for the bare boards' 0.50 kg; more for assembled ones |
| **Total** | **≈ 2,417** | **≈ 4,804** | |
| Per board | ≈ 1,208 | ≈ 961 | |

**Rev08 (17 November), re-priced with `lcsc_select.py` on live stock and `quote.py`:** 214 BOM lines, 739 parts, 212
lines with a code and 187 distinct codes (+72 since Rev06): the VHF/UHF front end, the 14 LEDs, the USB bridge and the
IAS0 receptacle. Parts rise by about $64 a board, most of it the RFFC5072 ($14.64), the two PE42442 and two SKY13418
switches, the SPF5043Z amplifiers, the PE4312 and the thirteenth SMA. **Feeder loading is now the largest assembly
fee, $286** (187 × $1.53), against $174 for Rev06: the front end's filters use many distinct C0G and wirewound values.
The rows below are the history of this quote.

On 6 layers the bare boards were $236.88, so the move to 8 layers adds **$46.04 to the order**,
2 % of the total for two boards. The parts list grew by two 0402 resistors (R105, R106), a few cents.

**The Ethernet option (13 November, CONTROL_SPEC §7) adds about $46 to two boards:** $25 of parts
(the PHY and the RJ45 are most of it) and $21 of assembly, mostly the 12 new feeders. Its four
DNP capacitors are not in the BOM. **The bare boards, re-quoted for the tab's 140 × 132 mm bounding
box, cost $5.04 more** ($287.96 against $282.92): the board line $15.30 against $11.90, the rest a
few cents up since 12 Nov (§2).

**Rev06 (14 November, branch `rev06`), re-priced the same way:** parts $1,523.80 for two boards and $3,644.36 for
five (115 LCSC codes; +$20 and +$41), feeder loading 114 × $1.53 = $174.42 (+$12). The difference is the Rev05 input
protection, now with codes (LM74502-Q1, two DMT10H015LFG, SMCJ33CA, SMBJ18CA), the fan header with its PTC, and the
SGMII bias network; C1218–C1221 are now fitted. Two boards come to **≈ $2,156**, five to **≈ $4,361**.

**Rev07 (15 November):** the HF input's anti-alias low-pass (SIGNAL_INTEGRITY §9.9) adds ten parts and nine LCSC
codes, all extended and in stock (`_work/fab/lcsc_parts.csv`): six C0G 0402 capacitors and three 0805 wirewound
inductors (LQW2BASR22J00L, SDWL2012CR27GSTF, LQW2BASR33G00L, the scarcest at 949 in stock). Estimated, not
re-quoted: 9 × $1.53 of feeder loading and about $1 of parts per board, so **≈ $2,172** for two boards and
**≈ $4,385** for five. Run `quote.py` before ordering. The same
eight parts are short (plus TPD4E05U06DQAR, 71 in stock for 80): see below.

**Parts are two thirds of the cost,** and eight lines are 80 % of the parts (about $659 of $826 per board, 17 Nov):

| Part | Each | ×/board | Per board |
|---|---|---|---|
| M3SWA2-34DR+ (RF switch) | 45.76 | 4 | 183.03 |
| AD9253BCPZ-125 (ADC) | 97.38 | 1 | 97.38 |
| AD9484BCPZ-500 (ADC) | 97.29 | 1 | 97.29 |
| XC7A50T-2FTG256I (FPGA) | 93.47 | 1 | 93.47 |
| AD8352ACPZ (ADC driver) | 20.87 | 4 | 83.47 |
| SMA edge connectors | 4.77 | 13 | 62.03 |
| ADT2-1T+ (balun) | 7.23 | 3 | 21.70 |
| ADCLK948BCPZ (clock) | 20.79 | 1 | 20.79 |

Prices from LCSC, at the tier for two boards' quantity.

**Nine parts are short of stock** for even two boards (17 November): ADCLK948, AD9484, AD9253, AD9708 and
M3SWA2-34DR+ have none, AD8352 has 7 of 8, ADT2-1T+ 1 of 6, TMP1075DR 1 of 2, and **the SMA, SMA-J-P-H-ST-EM1, 5 of
26** (905 on 2 October). The Rev08 parts are all in stock for five boards; the scarcest are the RFFC5072 (61), the
TA1090EC SAW filter (149) and the PE42442 (245). JLCPCB's "global sourcing" buys them
in and its price can differ from LCSC's list price above. The other choice is to buy them from a
distributor and consign them. The ADI parts and the Mini-Circuits switches are sold at Digi-Key and
Mouser, often for less than the LCSC list price.

---

## 2. Bare boards: $287.96 for 5

Entered on [jlcpcb.com/quote](https://cart.jlcpcb.com/quote) on 12 Nov 2026 with the values of
FABRICATION §2 (8 layers); the 6-layer column is the same page on 10 Nov. Nothing was uploaded: the
page prices from the dimensions.

| Field | Value | 6 layers (2116A) | 8 layers (2116C) | 8 layers, 140 × 132 (13 Nov) |
|---|---|---|---|---|
| Layers, size, quantity | 119 × 120 mm, 5 (140 × 132 on 13 Nov) | Board **9.30** | Board **11.90** | Board **15.30** |
| Thickness, finish | 1.6 mm (2116C is 1.52 mm actual), ENIG 1 µ" | Surface finish **18.20** | **18.20** | **18.70** |
| Material | FR4 TG155 | **3.66** | 0.00 | 0.00 |
| Copper | 1 oz outer, 0.5 oz inner | — | — | — |
| **Stack** | JLC06161H-2116A / **JLC08161H-2116C** | Stack-up fee **102.79** | **83.89** | **84.24** |
| Impedance control | ±10 % | **33.08** | **33.08** | **33.08** |
| Via covering | Epoxy filled & capped (POFV) | 0.00 | 0.00 | 0.00 |
| Min via | 0.2 mm hole (the board's 0.20 / 0.45 mm vias) | **18.31** | **18.31** | **18.83** |
| 4-wire Kelvin test | Forced on by the 0.2 mm vias | **17.49** | **17.49** | **17.76** |
| Confirm production file | Forced on by the specified stack | **1.05** | **1.05** | **1.05** |
| Engineering fee | | **33.00** | **99.00** | **99.00** |
| Build time | 7–8 days | 0.00 | 0.00 | 0.00 |
| **Total** | | **236.88** | **282.92** (desktop app: 277.92) | **287.96** (desktop app: 282.96) |

The difference is the engineering fee ($99 on 8 layers against $33) and the board itself; the
2116C stack-up fee is lower than 2116A's. The page warns that 2116C is 1.5216 mm thick, not 1.6 mm
(within the ±10 % tolerance); the board has nothing that depends on its thickness.

**The specified stack costs $83.89 on its own** ($102.79 for 2116A on 6 layers), and it rules out JLCPCB's Economic assembly. The page
says the stack "doesn't support economic PCB assembly". Both are the price of the impedances:
POWER_AND_STACKUP §2.6 explains why the board uses this stack and not the default 3313.

**The 0.2 mm vias cost $35.80** (via size and Kelvin test). The fan-out of the 1.0 mm BGA needs them.

---

## 3. Assembly fees: Standard PCBA

The 2116C stack, like 2116A, allows only **Standard** PCBA. Its fees, from JLCPCB's
[price page](https://jlcpcb.com/help/article/pcb-assembly-price) (last updated 22 Oct 2026). The
assembly quote itself needs the Gerbers uploaded, so it was not run:

| Fee | Rate | 2 boards | 5 boards |
|---|---|---|---|
| Setup, **both sides** | 51.12 | 51.12 | 51.12 |
| Stencil, both sides | 16.42 | 16.42 | 16.42 |
| SMT joints (2,685 per board, the SMD pads of the 739 fitted parts) | 0.0016 / joint | 8.59 | 21.48 |
| Hand-soldered joints (87 per board: J1001, J1002, J1101, J1102, J1103, J1201) | 0.0164 / joint | 2.85 | 7.13 |
| Hand-soldering labour | 3.58 / order | 3.58 | 3.58 |
| Feeder loading: every part on Standard, basic or extended | 1.53 × 187 parts | 286.11 | 286.11 |
| X-ray, 22 parts per board with hidden joints (FPGA, QFNs, LFCSPs; Rev08 adds the two PE42442, two SKY13418, the PE4312, the RFFC5072 and the two TCA6416A) | 0.82 / 0.49 per part | 36.08 | 53.90 |
| Packing | 0.50 + area | 0.50 | 0.50 |
| **Total** | | **405.25** | **440.24** |

Counted on 17 November from the board file and the BOM (Rev06: 1,930 joints, 85 by hand, 106 feeders, 14 X-ray
parts; $265.73 and $290.51).

**The setup and stencil are double-sided because of two parts:** J101 and J102, the KV260 connectors,
sit on the bottom face. Their 0.4 mm pitch rules out hand-fitting them.

The **feeder loading** ($162) is the largest assembly fee. On Standard PCBA every part is loaded,
basic or not; fewer distinct values would lower it.

Not counted: a possible fixture fee for the hand-soldered parts ($16.42 for 1–29 boards, if JLCPCB
applies it), and the Si549's consignment handling.

**The FAQ page gives other figures** (setup $8, stencil $1.50, $3 per extended part). The price page
is newer and has the Standard column. The live quote, once the files are uploaded, is the final word.

---

## 4. Parts, line by line

Each line is one LCSC code. **Buy** is what JLCPCB would purchase: the boards' need plus its
attrition, at least its minimum. Links go to JLCPCB's part page (code) and LCSC's (part). Stock in
**bold** is short of the two-board need.

<!-- parts:begin -->
*Searched 2026-11-17 by `_work/fab/quote.py`; prices in USD, JLCPCB's tier for the quantity bought.*

| LCSC | Part | Maker | Value | Lib | Per board | Stock | Buy 2 / unit / cost | Buy 5 / unit / cost |
|---|---|---|---|---|---|---|---|---|
| [C33062043](https://jlcpcb.com/partdetail/MiniCircuits-M3SWA2_34DR/C33062043) | [M3SWA2-34DR+](https://lcsc.com/product-detail/rf-switches_mini-circuits-m3swa2-34dr_C33062043.html) | Mini-Circuits | M3SWA2-34DR+ | extended | 4 | **0** | 8 / 45.76 / 366.06 | 20 / 44.28 / 885.58 |
| [C514282](https://jlcpcb.com/partdetail/AnalogDevices-AD9253BCPZ125/C514282) | [AD9253BCPZ-125](https://www.lcsc.com/product-detail/analog-to-digital-converters-adc_analog-devices-ad9253bcpz-125_C514282.html) | Analog Devices | AD9253BCPZ-125 | extended | 1 | **0** | 2 / 97.38 / 194.75 | 5 / 97.38 / 486.89 |
| [C653480](https://jlcpcb.com/partdetail/AnalogDevices-AD9484BCPZ500/C653480) | [AD9484BCPZ-500](https://www.lcsc.com/product-detail/analog-to-digital-converters-adc_analog-devices-ad9484bcpz-500_C653480.html) | Analog Devices | AD9484BCPZ-500 | extended | 1 | **0** | 2 / 97.29 / 194.57 | 5 / 97.29 / 486.43 |
| [C2976033](https://jlcpcb.com/partdetail/AMDXILINX-XC7A50T2FTG256I/C2976033) | [XC7A50T-2FTG256I](https://www.lcsc.com/product-detail/programmable-logic-device-cplds-fpgas_amd-xilinx-xc7a50t-2ftg256i_C2976033.html) | AMD/XILINX | XC7A50T-2FTG256I | extended | 1 | 27 | 2 / 93.47 / 186.94 | 5 / 93.47 / 467.34 |
| [C578707](https://jlcpcb.com/partdetail/AnalogDevices-AD8352ACPZR7/C578707) | [AD8352ACPZ-R7](https://www.lcsc.com/product-detail/rf-amplifiers_analog-devices-ad8352acpz-r7_C578707.html) | Analog Devices | AD8352ACPZ | extended | 4 | **7** | 8 / 20.87 / 166.93 | 20 / 19.99 / 399.71 |
| [C5199907](https://jlcpcb.com/partdetail/Samtec-SMA_J_P_H_STEM1/C5199907) | [SMA-J-P-H-ST-EM1](https://www.lcsc.com/product-detail/coaxial-connectors-rf_samtec-sma-j-p-h-st-em1_C5199907.html) | Samtec | CLK_REF_IN / CLK_OUT / SDR_RX_A / AERIS_IF_A / AERIS_IF / SDR_RX_WB / SDR_TX_A / AERIS_TX_A / AERIS_TX / SDR_TX_WB / SDR_RX_C / SDR_TX_C / VU_ANT | extended | 13 | **5** | 26 / 4.772 / 124.07 | 65 / 4.369 / 283.99 |
| [C5223988](https://jlcpcb.com/partdetail/MiniCircuits-ADT2_1T/C5223988) | [ADT2-1T+](https://www.lcsc.com/product-detail/balun_mini-circuits-adt2-1t_C5223988.html) | Mini-Circuits | ADT2-1T+ | extended | 3 | **1** | 6 / 7.232 / 43.39 | 15 / 6.268 / 94.01 |
| [C578960](https://jlcpcb.com/partdetail/AnalogDevices-ADCLK948BCPZ/C578960) | [ADCLK948BCPZ](https://www.lcsc.com/product-detail/clock-buffers-drivers-distributors_analog-devices-adclk948bcpz_C578960.html) | Analog Devices | ADCLK948BCPZ | extended | 1 | **0** | 2 / 20.79 / 41.57 | 5 / 20.79 / 103.93 |
| [C653734](https://jlcpcb.com/partdetail/AnalogDevices-AD9708ARZ/C653734) | [AD9708ARZ](https://www.lcsc.com/product-detail/digital-to-analog-converters-dac_analog-devices-ad9708arz_C653734.html) | Analog Devices | AD9708AR | extended | 1 | **0** | 2 / 16.85 / 33.70 | 5 / 16.85 / 84.26 |
| [C3034742](https://jlcpcb.com/partdetail/Qorvo-RFFC5072TR13/C3034742) | [RFFC5072TR13](https://www.lcsc.com/product-detail/pre-ordered-chips_qorvo-rffc5072tr13_C3034742.html) | Qorvo | RFFC5072 | extended | 1 | 61 | 2 / 14.64 / 29.27 | 5 / 14.64 / 73.18 |
| [C653820](https://jlcpcb.com/partdetail/AnalogDevices-AD9767ASTZRL/C653820) | [AD9767ASTZRL](https://www.lcsc.com/product-detail/digital-to-analog-converters-dac_analog-devices-ad9767astzrl_C653820.html) | Analog Devices | AD9767ASTZ | extended | 1 | 172 | 2 / 14.56 / 29.12 | 5 / 14.56 / 72.81 |
| [C41359590](https://jlcpcb.com/partdetail/MicronTech-MT25QL128ABA1ESE0SIT/C41359590) | [MT25QL128ABA1ESE-0SIT](https://www.lcsc.com/product-detail/nor-flash_micron-tech-mt25ql128aba1ese-0sit_C41359590.html) | Micron Tech | MT25QL128ABA1ESE | extended | 1 | 61 | 2 / 12.97 / 25.95 | 5 / 12.97 / 64.86 |
| [C470913](https://jlcpcb.com/partdetail/pSemi-PE42442AZ/C470913) | [PE42442A-Z](https://www.lcsc.com/product-detail/rf-switches_psemi-pe42442a-z_C470913.html) | pSemi | PE42442 | extended | 2 | 245 | 4 / 4.96 / 19.84 | 10 / 4.267 / 42.67 |
| [C544500](https://jlcpcb.com/partdetail/TexasInstruments-TPS7A8300RGRR/C544500) | [TPS7A8300RGRR](https://www.lcsc.com/product-detail/voltage-regulators-linear-low-drop-out-ldo-regulators_texas-instruments-tps7a8300rgrr_C544500.html) | Texas Instruments | TPS7A8300RGR | extended | 3 | 136 | 6 / 2.503 / 15.02 | 15 / 2.203 / 33.05 |
| [C470902](https://jlcpcb.com/partdetail/Qorvo-SPF5043Z/C470902) | [SPF5043Z](https://www.lcsc.com/product-detail/rf-amplifiers_qorvo-spf5043z_C470902.html) | Qorvo | SPF5043Z | extended | 2 | 5902 | 4 / 3.396 / 13.58 | 10 / 2.901 / 29.01 |
| [C5245407](https://jlcpcb.com/partdetail/DiodesIncorporated-DMT10H015LFG7/C5245407) | [DMT10H015LFG-7](https://www.lcsc.com/product-detail/mosfets_diodes-incorporated-dmt10h015lfg-7_C5245407.html) | Diodes Incorporated | DMT10H015LFG | extended | 2 | 65 | 4 / 3.211 / 12.84 | 10 / 2.8 / 28.00 |
| [C2886897](https://jlcpcb.com/partdetail/ESwitch-TL3342F450QG/C2886897) | [TL3342F450QG](https://www.lcsc.com/product-detail/tactile-switches_e-switch-tl3342f450qg_C2886897.html) | E-Switch | PROG | extended | 1 | 86 | 13 / 0.7487 / 9.73 | 13 / 0.7487 / 9.73 |
| [C470892](https://jlcpcb.com/partdetail/pSemi-PE425963/C470892) | [PE4259-63](https://www.lcsc.com/product-detail/rf-switches_psemi-pe4259-63_C470892.html) | pSemi | PE4259 | extended | 4 | 14032 | 8 / 1.188 / 9.50 | 20 / 1.065 / 21.30 |
| [C2878381](https://jlcpcb.com/partdetail/TexasInstruments-TMP1075DR/C2878381) | [TMP1075DR](https://www.lcsc.com/product-detail/temperature-sensors_texas-instruments-tmp1075dr_C2878381.html) | Texas Instruments | TMP1075DR | extended | 1 | **1** | 23 / 0.3965 / 9.12 | 23 / 0.3965 / 9.12 |
| [C4990147](https://jlcpcb.com/partdetail/MiniCircuits-HFCN_1000/C4990147) | [HFCN-1000+](https://www.lcsc.com/product-detail/ceramic-filters_mini-circuits-hfcn-1000_C4990147.html) | Mini-Circuits | HFCN-1000+ | extended | 1 | 302 | 2 / 3.08 / 6.16 | 5 / 3.08 / 15.40 |
| [C2904132](https://jlcpcb.com/partdetail/RealtekSemicon-RTL8211FSICG/C2904132) | [RTL8211FSI-CG](https://www.lcsc.com/product-detail/ethernet-transceivers_realtek-semicon-rtl8211fsi-cg_C2904132.html) | Realtek Semicon | RTL8211FSI-CG | extended | 1 | 4441 | 2 / 2.872 / 5.74 | 5 / 2.872 / 14.36 |
| [C50933](https://jlcpcb.com/partdetail/51945-HR911130C/C50933) | [HR911130C](https://www.lcsc.com/product-detail/ethernet-connectors-modular-connectors-rj45-rj11_hanrun-zhongshan-hanrun-elec-hr911130c_C50933.html) | HANRUN(Zhongshan HanRun Elec) | HR911130C | extended | 1 | 7044 | 2 / 2.862 / 5.72 | 5 / 2.862 / 14.31 |
| [C500480](https://jlcpcb.com/partdetail/pSemi-PE4312CZ/C500480) | [PE4312C-Z](https://www.lcsc.com/product-detail/rf-attenuators_psemi-pe4312c-z_C500480.html) | pSemi | PE4312 | extended | 1 | 1502 | 2 / 2.841 / 5.68 | 5 / 2.841 / 14.20 |
| [C5476329](https://jlcpcb.com/partdetail/WurthElektronik-150040VS73240/C5476329) | [150040VS73240](https://www.lcsc.com/product-detail/light-emitting-diodes-led_wurth-elektronik-150040vs73240_C5476329.html) | Wurth Elektronik | CFG green / LINK green / LO green / +12V green / +5V0 green / +3V3_D green / +1V8_D green / +1V0 green | extended | 8 | 802 | 16 / 0.3162 / 5.06 | 40 / 0.2802 / 11.21 |
| [C544380](https://jlcpcb.com/partdetail/TexasInstruments-LM2663MNOPB/C544380) | [LM2663M/NOPB](https://www.lcsc.com/product-detail/dc-dc-converters_texas-instruments-lm2663m-nopb_C544380.html) | Texas Instruments | LM2663M | extended | 1 | 5243 | 2 / 2.395 / 4.79 | 5 / 2.395 / 11.97 |
| [C20415295](https://jlcpcb.com/partdetail/TST-TA1090EC/C20415295) | TA1090EC | TST | TA1090EC | extended | 1 | 149 | 2 / 2.167 / 4.33 | 5 / 2.167 / 10.84 |
| [C879868](https://jlcpcb.com/partdetail/MiniCircuits-LFCN_1000/C879868) | [LFCN-1000+](https://www.lcsc.com/product-detail/rf-filters_mini-circuits-lfcn-1000_C879868.html) | Mini-Circuits | LFCN-1000+ | extended | 1 | 576 | 2 / 2.072 / 4.14 | 5 / 2.072 / 10.36 |
| [C150871](https://jlcpcb.com/partdetail/SkyworksSolutions-SKY13418485LF/C150871) | [SKY13418-485LF](https://www.lcsc.com/product-detail/rf-switches_skyworks-solutions-sky13418-485lf_C150871.html) | Skyworks Solutions | SKY13418-485LF | extended | 2 | 4507 | 4 / 1.026 / 4.10 | 10 / 0.8404 / 8.40 |
| [C2041815](https://jlcpcb.com/partdetail/BOURNS-SRP7028A8R2M/C2041815) | [SRP7028A-8R2M](https://www.lcsc.com/product-detail/power-inductors_bourns-srp7028a-8r2m_C2041815.html) | BOURNS | SRP7028A-8R2M | extended | 1 | 213 | 2 / 1.823 / 3.65 | 5 / 1.823 / 9.12 |
| [C879855](https://jlcpcb.com/partdetail/MiniCircuits-TC4_1W/C879855) | [TC4-1W+](https://www.lcsc.com/product-detail/rf-misc-ics-and-modules_mini-circuits-tc4-1w_C879855.html) | Mini-Circuits | TC4-1W+ | extended | 1 | 2126 | 2 / 1.707 / 3.41 | 5 / 1.707 / 8.54 |
| [C182336](https://jlcpcb.com/partdetail/TexasInstruments-TCA6416ARTWR/C182336) | [TCA6416ARTWR](https://www.lcsc.com/product-detail/i-o-expanders_texas-instruments-tca6416artwr_C182336.html) | Texas Instruments | TCA6416ARTWR | extended | 2 | 32804 | 4 / 0.8208 / 3.28 | 10 / 0.6733 / 6.73 |
| [C45783](https://jlcpcb.com/partdetail/46786-CL21A226MAQNNNE/C45783) | [CL21A226MAQNNNE](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_samsung-electro-mechanics-cl21a226maqnnne_C45783.html) | Samsung Electro-Mechanics | 22u 10V | basic | 13 | 3830035 | 30 / 0.1085 / 3.25 | 69 / 0.1085 / 7.49 |
| [C5219206](https://jlcpcb.com/partdetail/TexasInstruments-LM74502QDDFRQ1/C5219206) | [LM74502QDDFRQ1](https://www.lcsc.com/product-detail/power-distribution-switches_texas-instruments-lm74502qddfrq1_C5219206.html) | Texas Instruments | LM74502-Q1 | extended | 1 | 584 | 2 / 1.62 / 3.24 | 5 / 1.62 / 8.10 |
| [C45961](https://jlcpcb.com/partdetail/Nexperia-PESD5V0F1BL315/C45961) | [PESD5V0F1BL,315](https://www.lcsc.com/product-detail/esd-and-surge-protection-tvs-esd_nexperia-pesd5v0f1bl-315_C45961.html) | Nexperia | PESD5V0F1BL | extended | 13 | 139208 | 34 / 0.0843 / 2.87 | 73 / 0.0662 / 4.83 |
| [C492354](https://jlcpcb.com/partdetail/MOLEX-878321420/C492354) | [878321420](https://www.lcsc.com/product-detail/wire-to-board-connector_molex-878321420_C492354.html) | MOLEX | JTAG 2x7 2mm | extended | 1 | 2933 | 2 / 1.402 / 2.80 | 5 / 1.402 / 7.01 |
| [C77101](https://jlcpcb.com/partdetail/MurataElectronics-GRM32ER61C476KE15L/C77101) | [GRM32ER61C476KE15L](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_murata-electronics-grm32er61c476ke15l_C77101.html) | Murata Electronics | 47u | extended | 5 | 89457 | 12 / 0.2163 / 2.60 | 27 / 0.2163 / 5.84 |
| [C136150](https://jlcpcb.com/partdetail/KEMET-T520V337M006ATE025/C136150) | [T520V337M006ATE025](https://www.lcsc.com/product-detail/tantalum-capacitors_kemet-t520v337m006ate025_C136150.html) | KEMET | 330u | extended | 1 | 1448 | 2 / 1.279 / 2.56 | 5 / 1.279 / 6.40 |
| [C913186](https://jlcpcb.com/partdetail/BOURNS-SRP7028A3R3M/C913186) | [SRP7028A-3R3M](https://www.lcsc.com/product-detail/power-inductors_bourns-srp7028a-3r3m_C913186.html) | BOURNS | SRP7028A-3R3M | extended | 2 | 1043 | 4 / 0.5931 / 2.37 | 10 / 0.4718 / 4.72 |
| [C3096093](https://jlcpcb.com/partdetail/CUI-PJ102AH/C3096093) | [PJ-102AH](https://www.lcsc.com/product-detail/dc-power-connectors_cui-pj-102ah_C3096093.html) | CUI | 12V IN | extended | 1 | 608 | 2 / 1.057 / 2.11 | 5 / 1.057 / 5.28 |
| [C146656](https://jlcpcb.com/partdetail/157988-B_3100S40PA110/C146656) | [B-3100S40P-A110](https://www.lcsc.com/product-detail/idc-connectors_ckmtw-shenzhen-cankemeng-b-3100s40p-a110_C146656.html) | Ckmtw(Shenzhen Cankemeng) | AERIS ADAR | extended | 1 | 1153 | 2 / 0.8421 / 1.68 | 5 / 0.8421 / 4.21 |
| [C2158038](https://jlcpcb.com/partdetail/DiodesIncorporated-AP22652W67/C2158038) | [AP22652W6-7](https://www.lcsc.com/product-detail/power-distribution-switches_diodes-incorporated-ap22652w6-7_C2158038.html) | Diodes Incorporated | AP22652W6-7 | extended | 1 | 8457 | 5 / 0.3319 / 1.66 | 5 / 0.3319 / 1.66 |
| [C15850](https://jlcpcb.com/partdetail/16532-CL21A106KAYNNNE/C15850) | [CL21A106KAYNNNE](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_samsung-electro-mechanics-cl21a106kaynnne_C15850.html) | Samsung Electro-Mechanics | 10u / 10u 10V | basic | 21 | 9016792 | 52 / 0.0312 / 1.62 | 115 / 0.0312 / 3.59 |
| [C7432791](https://jlcpcb.com/partdetail/Chinocera-HGC1210R5476M250NSVK/C7432791) | [HGC1210R5476M250NSVK](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_chinocera-hgc1210r5476m250nsvk_C7432791.html) | Chinocera | 47u 25V | extended | 1 | 81016 | 5 / 0.3098 / 1.55 | 5 / 0.3098 / 1.55 |
| [C475492](https://jlcpcb.com/partdetail/TexasInstruments-LP5907MFX_3_0NOPB/C475492) | [LP5907MFX-3.0/NOPB](https://www.lcsc.com/product-detail/voltage-regulators-linear-low-drop-out-ldo-regulators_texas-instruments-lp5907mfx-3-0-nopb_C475492.html) | Texas Instruments | LP5907MFX-3.0 | extended | 1 | 32000 | 5 / 0.2785 / 1.39 | 5 / 0.2785 / 1.39 |
| [C424540](https://jlcpcb.com/partdetail/HRS_Hirose-BM20B_0_8_34DP_0_4V_51/C424540) | [BM20B(0.8)-34DP-0.4V(51)](https://www.lcsc.com/product-detail/board-to-board-and-backplane-connector_hrs-hirose-bm20b-0-8-34dp-0-4v-51_C424540.html) | HRS(Hirose) | BM20B(0.8)-34DP | extended | 2 | 13012 | 6 / 0.2219 / 1.33 | 12 / 0.2219 / 2.66 |
| [C3035748](https://jlcpcb.com/partdetail/WCH_Jiangsu_Qin_Heng-CH340X/C3035748) | [CH340X](https://www.lcsc.com/product-detail/usb-converters_wch-jiangsu-qin-heng-ch340x_C3035748.html) | WCH(Jiangsu Qin Heng) | CH340X | extended | 1 | 36690 | 2 / 0.6635 / 1.33 | 5 / 0.6635 / 3.32 |
| [C96123](https://jlcpcb.com/partdetail/97327-CL31A476MPHNNNE/C96123) | [CL31A476MPHNNNE](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_samsung-electro-mechanics-cl31a476mphnnne_C96123.html) | Samsung Electro-Mechanics | 47u | basic | 2 | 455794 | 8 / 0.163 / 1.30 | 14 / 0.163 / 2.28 |
| [C98092](https://jlcpcb.com/partdetail/MurataElectronics-LQW18ANR27G00D/C98092) | [LQW18ANR27G00D](https://www.lcsc.com/product-detail/power-inductors_murata-electronics-lqw18anr27g00d_C98092.html) | Murata Electronics | 270n | extended | 12 | 8690 | 28 / 0.0464 / 1.30 | 64 / 0.0464 / 2.97 |
| [C167487](https://jlcpcb.com/partdetail/MurataElectronics-LQW15AN82NG00D/C167487) | [LQW15AN82NG00D](https://www.lcsc.com/product-detail/power-inductors_murata-electronics-lqw15an82ng00d_C167487.html) | Murata Electronics | 82n | extended | 1 | 5357 | 20 / 0.0628 / 1.26 | 20 / 0.0628 / 1.26 |
| [C841384](https://jlcpcb.com/partdetail/TexasInstruments-LMR33630ADDAR/C841384) | [LMR33630ADDAR](https://www.lcsc.com/product-detail/dc-dc-converters_texas-instruments-lmr33630addar_C841384.html) | Texas Instruments | LMR33630ADDA | extended | 1 | 25875 | 2 / 0.6324 / 1.26 | 5 / 0.6324 / 3.16 |
| [C49066](https://jlcpcb.com/partdetail/50074-CL32A107MQVNNNE/C49066) | [CL32A107MQVNNNE](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_samsung-electro-mechanics-cl32a107mqvnnne_C49066.html) | Samsung Electro-Mechanics | 100u | extended | 1 | 152696 | 5 / 0.2471 / 1.24 | 7 / 0.2471 / 1.73 |
| [C1779](https://jlcpcb.com/partdetail/2131-CL21A475KAQNNNE/C1779) | [CL21A475KAQNNNE](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_samsung-electro-mechanics-cl21a475kaqnnne_C1779.html) | Samsung Electro-Mechanics | 4.7u | basic | 13 | 2039484 | 36 / 0.0343 / 1.23 | 75 / 0.0343 / 2.57 |
| [C135223](https://jlcpcb.com/partdetail/KDSDaishinku-1XXD26000MAA/C135223) | [1XXD26000MAA](https://www.lcsc.com/product-detail/temperature-compensated-crystal-oscillators-tcxo_kds-daishinku-1xxd26000maa_C135223.html) | KDS Daishinku | 26MHz 1XXD26000MAA | extended | 1 | 15650 | 2 / 0.6111 / 1.22 | 5 / 0.6111 / 3.06 |
| [C1329579](https://jlcpcb.com/partdetail/BOURNS-SRP7028A2R2M/C1329579) | [SRP7028A-2R2M](https://www.lcsc.com/product-detail/power-inductors_bourns-srp7028a-2r2m_C1329579.html) | BOURNS | SRP7028A-2R2M | extended | 1 | 916 | 2 / 0.5603 / 1.12 | 5 / 0.5603 / 2.80 |
| [C86129](https://jlcpcb.com/partdetail/MurataElectronics-LQW15AN22NG00D/C86129) | [LQW15AN22NG00D](https://www.lcsc.com/product-detail/power-inductors_murata-electronics-lqw15an22ng00d_C86129.html) | Murata Electronics | 22n | extended | 2 | 35331 | 20 / 0.0518 / 1.04 | 20 / 0.0518 / 1.04 |
| [C2049745](https://jlcpcb.com/partdetail/2141314-DFE201210U_2R2MP2/C2049745) | [DFE201210U-2R2M=P2](https://www.lcsc.com/product-detail/power-inductors_murata-electronics-dfe201210u-2r2m-p2_C2049745.html) | Murata Electronics | 2.2u | extended | 1 | 14104 | 5 / 0.2002 / 1.00 | 5 / 0.2002 / 1.00 |
| [C80670](https://jlcpcb.com/partdetail/TexasInstruments-LP5907MFX_3_3NOPB/C80670) | [LP5907MFX-3.3/NOPB](https://www.lcsc.com/product-detail/voltage-regulators-linear-low-drop-out-ldo-regulators_texas-instruments-lp5907mfx-3-3-nopb_C80670.html) | Texas Instruments | LP5907MFX-3.3 | extended | 1 | 39881 | 5 / 0.1651 / 0.83 | 7 / 0.1651 / 1.16 |
| [C49261569](https://jlcpcb.com/partdetail/C49261569) | HX-TYPE-C 16P 180 LT H10.0 USB 2.0 TYPE-C | hanxia | HX-TYPE-C 16P 180 LT H10.0 | extended | 1 | 3630 | 2 / 0.3747 / 0.75 | 5 / 0.3747 / 1.87 |
| [C424541](https://jlcpcb.com/partdetail/HRS_Hirose-BM20B_0_8_34DS_0_4V_51/C424541) | [BM20B(0.8)-34DS-0.4V(51)](https://www.lcsc.com/product-detail/board-to-board-and-backplane-connector_hrs-hirose-bm20b-0-8-34ds-0-4v-51_C424541.html) | HRS(Hirose) | BM20B(0.8)-34DS-0.4V(51) | extended | 1 | 18635 | 4 / 0.1852 / 0.74 | 7 / 0.1852 / 1.30 |
| [C13585](https://jlcpcb.com/partdetail/14236-CL31A106KBHNNNE/C13585) | [CL31A106KBHNNNE](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_samsung-electro-mechanics-cl31a106kbhnnne_C13585.html) | Samsung Electro-Mechanics | 10u 25V | basic | 1 | 4339656 | 6 / 0.1211 / 0.73 | 9 / 0.1211 / 1.09 |
| [C1525](https://jlcpcb.com/partdetail/1877-CL05B104KO5NNNC/C1525) | [CL05B104KO5NNNC](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_samsung-electro-mechanics-cl05b104ko5nnnc_C1525.html) | Samsung Electro-Mechanics | 100n | basic | 140 | 35743451 | 295 / 0.0024 / 0.71 | 715 / 0.0024 / 1.72 |
| [C333860](https://jlcpcb.com/partdetail/MurataElectronics-LQW2BAS1R0J00L/C333860) | [LQW2BAS1R0J00L](https://www.lcsc.com/product-detail/power-inductors_murata-electronics-lqw2bas1r0j00l_C333860.html) | Murata Electronics | 1u | extended | 1 | 3681 | 5 / 0.1414 / 0.71 | 5 / 0.1414 / 0.71 |
| [C337958](https://jlcpcb.com/partdetail/MurataElectronics-LQW2BASR22J00L/C337958) | [LQW2BASR22J00L](https://www.lcsc.com/product-detail/power-inductors_murata-electronics-lqw2basr22j00l_C337958.html) | Murata Electronics | 220n | extended | 1 | 7157 | 5 / 0.1377 / 0.69 | 7 / 0.1377 / 0.96 |
| [C2228109](https://jlcpcb.com/partdetail/YAGEO-CQ0402ARNPO9BNR40/C2228109) | [CQ0402ARNPO9BNR40](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cq0402arnpo9bnr40_C2228109.html) | YAGEO | 0.4p | extended | 1 | 2625 | 20 / 0.031 / 0.62 | 20 / 0.031 / 0.62 |
| [C703717](https://jlcpcb.com/partdetail/MurataElectronics-LQW2BASR33G00L/C703717) | [LQW2BASR33G00L](https://www.lcsc.com/product-detail/power-inductors_murata-electronics-lqw2basr33g00l_C703717.html) | Murata Electronics | 330n | extended | 1 | 2739 | 5 / 0.1219 / 0.61 | 7 / 0.1219 / 0.85 |
| [C142805](https://jlcpcb.com/partdetail/Littelfuse-1812L15024MR/C142805) | [1812L150/24MR](https://www.lcsc.com/product-detail/resettable-fuses_littelfuse-1812l150-24mr_C142805.html) | Littelfuse | PTC 1.5A hold | extended | 1 | 39123 | 6 / 0.0974 / 0.58 | 9 / 0.0974 / 0.88 |
| [C2041663](https://jlcpcb.com/partdetail/MurataElectronics-LQW15AN27NG8ZD/C2041663) | [LQW15AN27NG8ZD](https://www.lcsc.com/product-detail/power-inductors_murata-electronics-lqw15an27ng8zd_C2041663.html) | Murata Electronics | 27n | extended | 1 | 20740 | 5 / 0.1157 / 0.58 | 7 / 0.1157 / 0.81 |
| [C86130](https://jlcpcb.com/partdetail/MurataElectronics-LQW15ANR10J00D/C86130) | [LQW15ANR10J00D](https://www.lcsc.com/product-detail/power-inductors_murata-electronics-lqw15anr10j00d_C86130.html) | Murata Electronics | 100n | extended | 1 | 8130 | 6 / 0.0965 / 0.58 | 9 / 0.0965 / 0.87 |
| [C22390021](https://jlcpcb.com/partdetail/DOWO-TPD4E05U06DQAR/C22390021) | [TPD4E05U06DQAR](https://www.lcsc.com/product-detail/esd-and-surge-protection-tvs-esd_dowo-tpd4e05u06dqar_C22390021.html) | DOWO | TPD4E05U06DQAR | extended | 3 | 81577 | 20 / 0.0289 / 0.58 | 21 / 0.0289 / 0.61 |
| [C1623](https://jlcpcb.com/partdetail/1975-CL10B474KA8NNNC/C1623) | [CL10B474KA8NNNC](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_samsung-electro-mechanics-cl10b474ka8nnnc_C1623.html) | Samsung Electro-Mechanics | 0.47u / 470n | basic | 26 | 1369463 | 62 / 0.0092 / 0.57 | 140 / 0.0092 / 1.29 |
| [C90061](https://jlcpcb.com/partdetail/TexasInstruments-TPS562201DDCR/C90061) | [TPS562201DDCR](https://www.lcsc.com/product-detail/dc-dc-converters_texas-instruments-tps562201ddcr_C90061.html) | Texas Instruments | TPS562201 | extended | 3 | 471483 | 10 / 0.0566 / 0.57 | 19 / 0.0566 / 1.08 |
| [C9006](https://jlcpcb.com/partdetail/YXC_CrystalOscillators-X322525MOB4SI/C9006) | [X322525MOB4SI](https://www.lcsc.com/product-detail/crystals_yxc-crystal-oscillators-x322525mob4si_C9006.html) | YXC Crystal Oscillators | 25MHz | basic | 1 | 424428 | 6 / 0.0952 / 0.57 | 9 / 0.0952 / 0.86 |
| [C1855147](https://jlcpcb.com/partdetail/YAGEO-CQ0402ARNPO0BNR30/C1855147) | [CQ0402ARNPO0BNR30](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cq0402arnpo0bnr30_C1855147.html) | YAGEO | 0.3p | extended | 2 | 6888 | 20 / 0.0281 / 0.56 | 20 / 0.0281 / 0.56 |
| [C7829](https://jlcpcb.com/partdetail/TexasInstruments-SN74LVC1G07DBVR/C7829) | [SN74LVC1G07DBVR](https://www.lcsc.com/product-detail/buffers-drivers-receivers-transceivers_texas-instruments-sn74lvc1g07dbvr_C7829.html) | Texas Instruments | 74LVC1G07 | extended | 1 | 34541 | 6 / 0.0933 / 0.56 | 9 / 0.0933 / 0.84 |
| [C326067](https://jlcpcb.com/partdetail/YAGEO-CQ0402ARNPO9BNR20/C326067) | [CQ0402ARNPO9BNR20](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cq0402arnpo9bnr20_C326067.html) | YAGEO | 0.2p | extended | 1 | 5006 | 20 / 0.0268 / 0.54 | 20 / 0.0268 / 0.54 |
| [C370392](https://jlcpcb.com/partdetail/Sunlord-SDWL2012CR27GSTF/C370392) | [SDWL2012CR27GSTF](https://www.lcsc.com/product-detail/inductors-smd_sunlord-sdwl2012cr27gstf_C370392.html) | Sunlord | 270n | extended | 1 | 949 | 5 / 0.1082 / 0.54 | 7 / 0.1082 / 0.76 |
| [C577389](https://jlcpcb.com/partdetail/YAGEO-CQ0402BRNPO9BNR60/C577389) | [CQ0402BRNPO9BNR60](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cq0402brnpo9bnr60_C577389.html) | YAGEO | 0.6p | extended | 1 | 28189 | 20 / 0.0241 / 0.48 | 20 / 0.0241 / 0.48 |
| [C43379](https://jlcpcb.com/partdetail/44370-SMD1206P050TF_132/C43379) | [SMD1206P050TF/13.2](https://www.lcsc.com/product-detail/resettable-fuses_ruilon-shenzhen-ruilongyuan-elec-smd1206p050tf-13-2_C43379.html) | RUILON(Shenzhen Ruilongyuan Elec) | PTC 0.5A hold | extended | 1 | 12952 | 5 / 0.0901 / 0.45 | 7 / 0.0901 / 0.63 |
| [C434447](https://jlcpcb.com/partdetail/YongyuPhotoelectric-SZYY0402B/C434447) | [SZYY0402B](https://www.lcsc.com/product-detail/led-indication-discrete_yongyu-photoelectric-szyy0402b_C434447.html) | Yongyu Photoelectric | HB blue | extended | 1 | 480729 | 20 / 0.0215 / 0.43 | 20 / 0.0215 / 0.43 |
| [C341787](https://jlcpcb.com/partdetail/MurataElectronics-LQW15AN75NG00D/C341787) | [LQW15AN75NG00D](https://www.lcsc.com/product-detail/power-inductors_murata-electronics-lqw15an75ng00d_C341787.html) | Murata Electronics | 75n | extended | 1 | 10694 | 6 / 0.0716 / 0.43 | 9 / 0.0716 / 0.64 |
| [C108965](https://jlcpcb.com/partdetail/MurataElectronics-LQW15AN68NG00D/C108965) | [LQW15AN68NG00D](https://www.lcsc.com/product-detail/power-inductors_murata-electronics-lqw15an68ng00d_C108965.html) | Murata Electronics | 68n | extended | 1 | 20223 | 6 / 0.0659 / 0.40 | 9 / 0.0659 / 0.59 |
| [C21516](https://jlcpcb.com/partdetail/MurataElectronics-BLM15HD102SN1D/C21516) | [BLM15HD102SN1D](https://www.lcsc.com/product-detail/ferrite-beads_murata-electronics-blm15hd102sn1d_C21516.html) | Murata Electronics | BLM15HD102SN1 | extended | 2 | 68677 | 20 / 0.0195 / 0.39 | 20 / 0.0195 / 0.39 |
| [C310048](https://jlcpcb.com/partdetail/Brightking-SMCJ33CATR13/C310048) | [SMCJ33CA/TR13](https://www.lcsc.com/product-detail/esd-and-surge-protection-tvs-esd_brightking-smcj33ca-tr13_C310048.html) | Brightking | SMCJ33CA | extended | 1 | 93113 | 3 / 0.1267 / 0.38 | 6 / 0.1267 / 0.76 |
| [C6364703](https://jlcpcb.com/partdetail/APV-AHW1608F1R0KTF/C6364703) | [AHW1608F-1R0KTF](https://www.lcsc.com/product-detail/inductors-smd_apv-ahw1608f-1r0ktf_C6364703.html) | APV | 1u | extended | 2 | 27731 | 8 / 0.0418 / 0.33 | 14 / 0.0418 / 0.59 |
| [C113110](https://jlcpcb.com/partdetail/MurataElectronics-LQW15AN16NG00D/C113110) | [LQW15AN16NG00D](https://www.lcsc.com/product-detail/power-inductors_murata-electronics-lqw15an16ng00d_C113110.html) | Murata Electronics | 16n | extended | 2 | 12594 | 8 / 0.0407 / 0.33 | 14 / 0.0407 / 0.57 |
| [C78413](https://jlcpcb.com/partdetail/Brightking-SMBJ18CATR13/C78413) | [SMBJ18CA/TR13](https://www.lcsc.com/product-detail/esd-and-surge-protection-tvs-esd_brightking-smbj18ca-tr13_C78413.html) | Brightking | SMBJ18CA | extended | 1 | 479789 | 6 / 0.0541 / 0.32 | 9 / 0.0541 / 0.49 |
| [C86139](https://jlcpcb.com/partdetail/MurataElectronics-LQW18ANR22G00D/C86139) | [LQW18ANR22G00D](https://www.lcsc.com/product-detail/power-inductors_murata-electronics-lqw18anr22g00d_C86139.html) | Murata Electronics | 220n | extended | 1 | 36892 | 6 / 0.0498 / 0.30 | 9 / 0.0498 / 0.45 |
| [C98095](https://jlcpcb.com/partdetail/MurataElectronics-LQW18ANR39G00D/C98095) | [LQW18ANR39G00D](https://www.lcsc.com/product-detail/inductors-smd_murata-electronics-lqw18anr39g00d_C98095.html) | Murata Electronics | 390n | extended | 1 | 2139 | 6 / 0.0495 / 0.30 | 9 / 0.0495 / 0.45 |
| [C19077423](https://jlcpcb.com/partdetail/hongjiacheng-MMSZ5232B/C19077423) | [MMSZ5232B](https://www.lcsc.com/product-detail/zener-diodes_hongjiacheng-mmsz5232b_C19077423.html) | hongjiacheng | 5.6V | preferred | 8 | 37783 | 20 / 0.0145 / 0.29 | 44 / 0.0145 / 0.64 |
| [C114502](https://jlcpcb.com/partdetail/STMicroelectronics-M24C02FMN6TP/C114502) | [M24C02-FMN6TP](https://www.lcsc.com/product-detail/eeprom_stmicroelectronics-m24c02-fmn6tp_C114502.html) | STMicroelectronics | M24C02-FMN6TP | extended | 1 | 13655 | 2 / 0.1424 / 0.28 | 5 / 0.1424 / 0.71 |
| [C25503856](https://jlcpcb.com/partdetail/XINGLIGHT-XL1005UYC/C25503856) | [XL-1005UYC](https://www.lcsc.com/product-detail/led-indication-discrete_xinglight-xl-1005uyc_C25503856.html) | XINGLIGHT | CLK yellow | extended | 1 | 172579 | 20 / 0.0133 / 0.27 | 20 / 0.0133 / 0.27 |
| [C167482](https://jlcpcb.com/partdetail/MurataElectronics-LQW15AN56NG00D/C167482) | [LQW15AN56NG00D](https://www.lcsc.com/product-detail/power-inductors_murata-electronics-lqw15an56ng00d_C167482.html) | Murata Electronics | 56n | extended | 1 | 20435 | 6 / 0.0451 / 0.27 | 9 / 0.0451 / 0.41 |
| [C2827654](https://jlcpcb.com/partdetail/TECHPUBLIC-USBLC62SC6/C2827654) | [USBLC6-2SC6](https://www.lcsc.com/product-detail/esd-and-surge-protection-tvs-esd_tech-public-usblc6-2sc6_C2827654.html) | TECH PUBLIC | USBLC6-2SC6 | extended | 1 | 207841 | 6 / 0.0449 / 0.27 | 9 / 0.0449 / 0.40 |
| [C108301](https://jlcpcb.com/partdetail/ChilisinElec-PBY160808T_601YN/C108301) | [PBY160808T-601Y-N](https://www.lcsc.com/product-detail/ferrite-beads_chilisin-elec-pby160808t-601y-n_C108301.html) | Chilisin Elec | 600R@100MHz | extended | 6 | 737266 | 22 / 0.0114 / 0.25 | 40 / 0.0114 / 0.46 |
| [C167485](https://jlcpcb.com/partdetail/MurataElectronics-LQW15AN62NG00D/C167485) | [LQW15AN62NG00D](https://www.lcsc.com/product-detail/power-inductors_murata-electronics-lqw15an62ng00d_C167485.html) | Murata Electronics | 62n | extended | 1 | 11027 | 6 / 0.041 / 0.25 | 9 / 0.041 / 0.37 |
| [C47339](https://jlcpcb.com/partdetail/48344-CL05A474KP5NNNC/C47339) | [CL05A474KP5NNNC](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_samsung-electro-mechanics-cl05a474kp5nnnc_C47339.html) | Samsung Electro-Mechanics | 0.47u | preferred | 4 | 562080 | 20 / 0.012 / 0.24 | 32 / 0.012 / 0.38 |
| [C12624](https://jlcpcb.com/partdetail/Hubei_KENTOElec-KT0603G/C12624) | [KT-0603G](https://www.lcsc.com/product-detail/led-indication-discrete_hubei-kento-elec-kt-0603g_C12624.html) | Hubei KENTO Elec | green | extended | 1 | 211190 | 20 / 0.0119 / 0.24 | 21 / 0.0119 / 0.25 |
| [C88219](https://jlcpcb.com/partdetail/89397-0603B104K101NT/C88219) | [0603B104K101NT](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_fh-guangdong-fenghua-advanced-tech-0603b104k101nt_C88219.html) | FH (Guangdong Fenghua Advanced Tech) | 100n 100V | extended | 1 | 1481714 | 20 / 0.0116 / 0.23 | 20 / 0.0116 / 0.23 |
| [C23733](https://jlcpcb.com/partdetail/24469-CL05A475MP5NRNC/C23733) | [CL05A475MP5NRNC](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_samsung-electro-mechanics-cl05a475mp5nrnc_C23733.html) | Samsung Electro-Mechanics | 4.7u | basic | 1 | 1061714 | 20 / 0.0113 / 0.23 | 20 / 0.0113 / 0.23 |
| [C304314](https://jlcpcb.com/partdetail/TAITECH-HCB1608KF221T20/C304314) | [HCB1608KF-221T20](https://www.lcsc.com/product-detail/ferrite-beads_tai-tech-hcb1608kf-221t20_C304314.html) | TAI-TECH | 220R@100MHz | extended | 5 | 863038 | 20 / 0.0116 / 0.23 | 35 / 0.0116 / 0.41 |
| [C25503345](https://jlcpcb.com/partdetail/XINGLIGHT-XL1005SURC/C25503345) | [XL-1005SURC](https://www.lcsc.com/product-detail/led-indication-discrete_xinglight-xl-1005surc_C25503345.html) | XINGLIGHT | ADCR red / ADCS red / TX red / ERR red | extended | 4 | 886397 | 26 / 0.0084 / 0.22 | 38 / 0.0084 / 0.32 |
| [C32713279](https://jlcpcb.com/partdetail/hanxia-HX_PZ2_54_2x6PZZ/C32713279) | [HX PZ2.54-2x6P ZZ](https://www.lcsc.com/product-detail/pin-headers_hanxia-hx-pz2-54-2x6p-zz_C32713279.html) | hanxia | Pmod | extended | 1 | 22974 | 2 / 0.0931 / 0.19 | 5 / 0.0931 / 0.47 |
| [C52923](https://jlcpcb.com/partdetail/53938-CL05A105KA5NQNC/C52923) | [CL05A105KA5NQNC](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_samsung-electro-mechanics-cl05a105ka5nqnc_C52923.html) | Samsung Electro-Mechanics | 1u | basic | 10 | 9276020 | 32 / 0.0055 / 0.18 | 62 / 0.0055 / 0.34 |
| [C21120](https://jlcpcb.com/partdetail/21832-CL10B224KA8NNNC/C21120) | [CL10B224KA8NNNC](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_samsung-electro-mechanics-cl10b224ka8nnnc_C21120.html) | Samsung Electro-Mechanics | 220n 25V | basic | 2 | 959182 | 20 / 0.0089 / 0.18 | 20 / 0.0089 / 0.18 |
| [C8545](https://jlcpcb.com/partdetail/9040-2N7002/C8545) | [2N7002](https://www.lcsc.com/product-detail/mosfets_jiangsu-changjing-electronics-technology-co-ltd-2n7002_C8545.html) | Jiangsu Changjing Electronics Technology Co., Ltd. | 2N7002 | basic | 1 | 6149457 | 10 / 0.0159 / 0.16 | 13 / 0.0159 / 0.21 |
| [C81464](https://jlcpcb.com/partdetail/onsemi-MMBT3904LT1G/C81464) | [MMBT3904LT1G](https://www.lcsc.com/product-detail/bipolar-bjt_onsemi-mmbt3904lt1g_C81464.html) | onsemi | MMBT3904 | extended | 2 | 1312512 | 10 / 0.0164 / 0.16 | 15 / 0.0164 / 0.25 |
| [C327229](https://jlcpcb.com/partdetail/YAGEO-CC0402BRNPO9BN1R3/C327229) | [CC0402BRNPO9BN1R3](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402brnpo9bn1r3_C327229.html) | YAGEO | 1.3p | extended | 1 | 39905 | 20 / 0.0074 / 0.15 | 20 / 0.0074 / 0.15 |
| [C25087](https://jlcpcb.com/partdetail/25830-0402WGF2000TCE/C25087) | [0402WGF2000TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf2000tce_C25087.html) | UNI-ROYAL(Uniroyal Elec) | 200 | basic | 21 | 1597214 | 52 / 0.0029 / 0.15 | 115 / 0.0029 / 0.33 |
| [C1523](https://jlcpcb.com/partdetail/1875-0402B102K500NT/C1523) | [0402B102K500NT](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_fh-guangdong-fenghua-advanced-tech-0402b102k500nt_C1523.html) | FH (Guangdong Fenghua Advanced Tech) | 1n | basic | 12 | 4233591 | 39 / 0.0036 / 0.14 | 75 / 0.0036 / 0.27 |
| [C106200](https://jlcpcb.com/partdetail/YAGEO-CC0402JRNPO9BN101/C106200) | [CC0402JRNPO9BN101](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402jrnpo9bn101_C106200.html) | YAGEO | 100p | extended | 31 | 6613805 | 82 / 0.0017 / 0.14 | 175 / 0.0017 / 0.30 |
| [C526982](https://jlcpcb.com/partdetail/YAGEO-CC0402FRNPO9BN820/C526982) | [CC0402FRNPO9BN820](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402frnpo9bn820_C526982.html) | YAGEO | 82p | extended | 1 | 49353 | 20 / 0.0069 / 0.14 | 20 / 0.0069 / 0.14 |
| [C541342](https://jlcpcb.com/partdetail/YAGEO-CC0402BRNPO9BN6R2/C541342) | [CC0402BRNPO9BN6R2](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402brnpo9bn6r2_C541342.html) | YAGEO | 6.2p | extended | 1 | 20313 | 20 / 0.0068 / 0.14 | 20 / 0.0068 / 0.14 |
| [C576706](https://jlcpcb.com/partdetail/YAGEO-CC0402JRNPO9BN161/C576706) | [CC0402JRNPO9BN161](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402jrnpo9bn161_C576706.html) | YAGEO | 160p | extended | 3 | 30454 | 20 / 0.0066 / 0.13 | 25 / 0.0066 / 0.17 |
| [C15195](https://jlcpcb.com/partdetail/15869-CL05B103KB5NNNC/C15195) | [CL05B103KB5NNNC](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_samsung-electro-mechanics-cl05b103kb5nnnc_C15195.html) | Samsung Electro-Mechanics | 10n | basic | 10 | 5763867 | 35 / 0.0038 / 0.13 | 65 / 0.0038 / 0.25 |
| [C576704](https://jlcpcb.com/partdetail/YAGEO-CC0402JRNPO9BN111/C576704) | [CC0402JRNPO9BN111](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402jrnpo9bn111_C576704.html) | YAGEO | 110p | extended | 1 | 51906 | 20 / 0.0066 / 0.13 | 20 / 0.0066 / 0.13 |
| [C541433](https://jlcpcb.com/partdetail/YAGEO-CC0402FRNPO9BN130/C541433) | [CC0402FRNPO9BN130](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402frnpo9bn130_C541433.html) | YAGEO | 13p | extended | 1 | 12126 | 20 / 0.006 / 0.12 | 20 / 0.006 / 0.12 |
| [C25744](https://jlcpcb.com/partdetail/26487-0402WGF1002TCE/C25744) | [0402WGF1002TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf1002tce_C25744.html) | UNI-ROYAL(Uniroyal Elec) | 10k / 10k 1% | basic | 33 | 26228336 | 81 / 0.0015 / 0.12 | 180 / 0.0015 / 0.27 |
| [C25499](https://jlcpcb.com/partdetail/26242-4D02WGJ0220TCE/C25499) | [4D02WGJ0220TCE](https://www.lcsc.com/product-detail/resistor-networks-arrays_uni-royal-uniroyal-elec-4d02wgj0220tce_C25499.html) | UNI-ROYAL(Uniroyal Elec) | 4x22 | extended | 7 | 624377 | 24 / 0.0052 / 0.12 | 45 / 0.0052 / 0.23 |
| [C131337](https://jlcpcb.com/partdetail/JST-B2B_PH_K_S_LF_SN/C131337) | [B2B-PH-K-S(LF)(SN)](https://www.lcsc.com/product-detail/wire-to-board-connector_jst-b2b-ph-k-s-lf-sn_C131337.html) | JST | FAN 5V | extended | 1 | 284034 | 3 / 0.0356 / 0.11 | 6 / 0.0356 / 0.21 |
| [C327205](https://jlcpcb.com/partdetail/YAGEO-CC0402BRNPO9BN8R2/C327205) | [CC0402BRNPO9BN8R2](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402brnpo9bn8r2_C327205.html) | YAGEO | 8.2p | extended | 4 | 396074 | 20 / 0.0044 / 0.09 | 30 / 0.0044 / 0.13 |
| [C106998](https://jlcpcb.com/partdetail/YAGEO-CC0402JRNPO9BN151/C106998) | [CC0402JRNPO9BN151](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402jrnpo9bn151_C106998.html) | YAGEO | 150p | extended | 1 | 537588 | 20 / 0.0043 / 0.09 | 20 / 0.0043 / 0.09 |
| [C106223](https://jlcpcb.com/partdetail/YAGEO-CC0402JRNPO9BN390/C106223) | [CC0402JRNPO9BN390](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402jrnpo9bn390_C106223.html) | YAGEO | 39p | extended | 1 | 116138 | 20 / 0.0047 / 0.09 | 20 / 0.0047 / 0.09 |
| [C327209](https://jlcpcb.com/partdetail/YAGEO-CC0402BRNPO9BN1R8/C327209) | [CC0402BRNPO9BN1R8](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402brnpo9bn1r8_C327209.html) | YAGEO | 1.8p | extended | 1 | 480092 | 20 / 0.0043 / 0.09 | 20 / 0.0043 / 0.09 |
| [C527000](https://jlcpcb.com/partdetail/YAGEO-CC0402JRNPO9BN110/C527000) | [CC0402JRNPO9BN110](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402jrnpo9bn110_C527000.html) | YAGEO | 11p | extended | 1 | 20404 | 20 / 0.0044 / 0.09 | 20 / 0.0044 / 0.09 |
| [C327292](https://jlcpcb.com/partdetail/YAGEO-CC0402BRNPO9BN1R2/C327292) | [CC0402BRNPO9BN1R2](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402brnpo9bn1r2_C327292.html) | YAGEO | 1.2p | extended | 1 | 114859 | 20 / 0.0046 / 0.09 | 20 / 0.0046 / 0.09 |
| [C226372](https://jlcpcb.com/partdetail/YAGEO-AC0402FR0724R9L/C226372) | [AC0402FR-0724R9L](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_yageo-ac0402fr-0724r9l_C226372.html) | YAGEO | 24.9 | extended | 7 | 192503 | 24 / 0.0039 / 0.09 | 45 / 0.0039 / 0.18 |
| [C100316](https://jlcpcb.com/partdetail/LIZElec-CR0402FF2262G/C100316) | [CR0402FF2262G](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_liz-elec-cr0402ff2262g_C100316.html) | LIZ Elec | 22.6k | extended | 1 | 19160 | 20 / 0.0043 / 0.09 | 20 / 0.0043 / 0.09 |
| [C106999](https://jlcpcb.com/partdetail/YAGEO-CC0402JRNPO9BN181/C106999) | [CC0402JRNPO9BN181](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402jrnpo9bn181_C106999.html) | YAGEO | 180p | extended | 1 | 263449 | 20 / 0.0038 / 0.08 | 20 / 0.0038 / 0.08 |
| [C107006](https://jlcpcb.com/partdetail/YAGEO-CC0402JRNPO9BN331/C107006) | [CC0402JRNPO9BN331](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402jrnpo9bn331_C107006.html) | YAGEO | 330p | extended | 2 | 292658 | 20 / 0.0042 / 0.08 | 20 / 0.0042 / 0.08 |
| [C505468](https://jlcpcb.com/partdetail/YAGEO-CC0402BRNPO9BN5R6/C505468) | [CC0402BRNPO9BN5R6](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402brnpo9bn5r6_C505468.html) | YAGEO | 5.6p | extended | 1 | 202275 | 20 / 0.0042 / 0.08 | 20 / 0.0042 / 0.08 |
| [C541365](https://jlcpcb.com/partdetail/YAGEO-CC0402JRNPO9BN910/C541365) | [CC0402JRNPO9BN910](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402jrnpo9bn910_C541365.html) | YAGEO | 91p | extended | 1 | 15658 | 20 / 0.0041 / 0.08 | 20 / 0.0041 / 0.08 |
| [C326937](https://jlcpcb.com/partdetail/YAGEO-CC0402BRNPO9BN2R7/C326937) | [CC0402BRNPO9BN2R7](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402brnpo9bn2r7_C326937.html) | YAGEO | 2.7p | extended | 1 | 161258 | 20 / 0.0037 / 0.07 | 20 / 0.0037 / 0.07 |
| [C1532](https://jlcpcb.com/partdetail/1884-0402B223K500NT/C1532) | [0402B223K500NT](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_fh-guangdong-fenghua-advanced-tech-0402b223k500nt_C1532.html) | FH (Guangdong Fenghua Advanced Tech) | 22n | basic | 2 | 619623 | 20 / 0.0034 / 0.07 | 20 / 0.0034 / 0.07 |
| [C281756](https://jlcpcb.com/partdetail/YAGEO-CC0402BRNPO9BN2R0/C281756) | [CC0402BRNPO9BN2R0](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402brnpo9bn2r0_C281756.html) | YAGEO | 2p | extended | 1 | 557880 | 20 / 0.0033 / 0.07 | 20 / 0.0033 / 0.07 |
| [C25076](https://jlcpcb.com/partdetail/25819-0402WGF1000TCE/C25076) | [0402WGF1000TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf1000tce_C25076.html) | UNI-ROYAL(Uniroyal Elec) | 100 | basic | 22 | 10449222 | 59 / 0.0012 / 0.07 | 125 / 0.0012 / 0.15 |
| [C25867](https://jlcpcb.com/partdetail/26610-0402WGF1501TCE/C25867) | [0402WGF1501TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf1501tce_C25867.html) | UNI-ROYAL(Uniroyal Elec) | 1.5k | basic | 4 | 1196933 | 23 / 0.0029 / 0.07 | 35 / 0.0029 / 0.10 |
| [C25890](https://jlcpcb.com/partdetail/26633-0402WGF3301TCE/C25890) | [0402WGF3301TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf3301tce_C25890.html) | UNI-ROYAL(Uniroyal Elec) | 3.3k | basic | 1 | 1105492 | 20 / 0.0036 / 0.07 | 20 / 0.0036 / 0.07 |
| [C130117](https://jlcpcb.com/partdetail/YAGEO-CC0402CRNPO9BN5R0/C130117) | [CC0402CRNPO9BN5R0](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402crnpo9bn5r0_C130117.html) | YAGEO | 5p | extended | 2 | 70324 | 20 / 0.0028 / 0.06 | 20 / 0.0028 / 0.06 |
| [C505479](https://jlcpcb.com/partdetail/YAGEO-CC0402CRNPO9BN7R5/C505479) | [CC0402CRNPO9BN7R5](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402crnpo9bn7r5_C505479.html) | YAGEO | 7.5p | extended | 1 | 22950 | 20 / 0.0031 / 0.06 | 20 / 0.0031 / 0.06 |
| [C106202](https://jlcpcb.com/partdetail/YAGEO-CC0402JRNPO9BN180/C106202) | [CC0402JRNPO9BN180](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402jrnpo9bn180_C106202.html) | YAGEO | 18p | extended | 2 | 1643520 | 20 / 0.0031 / 0.06 | 20 / 0.0031 / 0.06 |
| [C25900](https://jlcpcb.com/partdetail/26643-0402WGF4701TCE/C25900) | [0402WGF4701TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf4701tce_C25900.html) | UNI-ROYAL(Uniroyal Elec) | 4.7k | basic | 14 | 13115489 | 38 / 0.0017 / 0.06 | 80 / 0.0017 / 0.14 |
| [C25803](https://jlcpcb.com/partdetail/26546-0603WAF1003T5E/C25803) | [0603WAF1003T5E](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0603waf1003t5e_C25803.html) | UNI-ROYAL(Uniroyal Elec) | 100k | basic | 1 | 14195162 | 20 / 0.0029 / 0.06 | 20 / 0.0029 / 0.06 |
| [C106203](https://jlcpcb.com/partdetail/YAGEO-CC0402JRNPO9BN220/C106203) | [CC0402JRNPO9BN220](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402jrnpo9bn220_C106203.html) | YAGEO | 22p | extended | 7 | 2255544 | 24 / 0.0019 / 0.05 | 45 / 0.0019 / 0.09 |
| [C281763](https://jlcpcb.com/partdetail/YAGEO-CC0402JRNPO9BN620/C281763) | [CC0402JRNPO9BN620](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402jrnpo9bn620_C281763.html) | YAGEO | 62p | extended | 3 | 53445 | 20 / 0.0027 / 0.05 | 25 / 0.0027 / 0.07 |
| [C107005](https://jlcpcb.com/partdetail/YAGEO-CC0402JRNPO9BN330/C107005) | [CC0402JRNPO9BN330](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402jrnpo9bn330_C107005.html) | YAGEO | 33p | extended | 8 | 5540087 | 26 / 0.0018 / 0.05 | 50 / 0.0018 / 0.09 |
| [C226375](https://jlcpcb.com/partdetail/YAGEO-AC0402FR07255RL/C226375) | [AC0402FR-07255RL](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_yageo-ac0402fr-07255rl_C226375.html) | YAGEO | 255 | extended | 2 | 7313 | 20 / 0.0024 / 0.05 | 20 / 0.0024 / 0.05 |
| [C11702](https://jlcpcb.com/partdetail/12256-0402WGF1001TCE/C11702) | [0402WGF1001TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf1001tce_C11702.html) | UNI-ROYAL(Uniroyal Elec) | 1k | basic | 15 | 30681880 | 40 / 0.0013 / 0.05 | 85 / 0.0013 / 0.11 |
| [C107002](https://jlcpcb.com/partdetail/YAGEO-CC0402JRNPO9BN270/C107002) | [CC0402JRNPO9BN270](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402jrnpo9bn270_C107002.html) | YAGEO | 27p | extended | 2 | 1023070 | 20 / 0.0018 / 0.04 | 22 / 0.0018 / 0.04 |
| [C189470](https://jlcpcb.com/partdetail/YAGEO-CC0402CRNPO9BN6R8/C189470) | [CC0402CRNPO9BN6R8](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402crnpo9bn6r8_C189470.html) | YAGEO | 6.8p | extended | 3 | 319443 | 20 / 0.0018 / 0.04 | 25 / 0.0018 / 0.04 |
| [C2933256](https://jlcpcb.com/partdetail/FOJAN-FRC0603F7321TS/C2933256) | [FRC0603F7321TS](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_fojan-frc0603f7321ts_C2933256.html) | FOJAN | 7.32k | extended | 1 | 429675 | 20 / 0.0019 / 0.04 | 20 / 0.0019 / 0.04 |
| [C25792](https://jlcpcb.com/partdetail/26535-0402WGF4702TCE/C25792) | [0402WGF4702TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf4702tce_C25792.html) | UNI-ROYAL(Uniroyal Elec) | 47k | basic | 1 | 5546839 | 20 / 0.0019 / 0.04 | 20 / 0.0019 / 0.04 |
| [C25794](https://jlcpcb.com/partdetail/26537-0402WGF5102TCE/C25794) | [0402WGF5102TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf5102tce_C25794.html) | UNI-ROYAL(Uniroyal Elec) | 51k | basic | 1 | 1417040 | 20 / 0.0019 / 0.04 | 20 / 0.0019 / 0.04 |
| [C107000](https://jlcpcb.com/partdetail/YAGEO-CC0402JRNPO9BN200/C107000) | [CC0402JRNPO9BN200](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402jrnpo9bn200_C107000.html) | YAGEO | 20p | extended | 4 | 868150 | 20 / 0.0016 / 0.03 | 30 / 0.0016 / 0.05 |
| [C60137](https://jlcpcb.com/partdetail/YAGEO-CC0402JRNPO9BN470/C60137) | [CC0402JRNPO9BN470](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402jrnpo9bn470_C60137.html) | YAGEO | 47p | extended | 1 | 2512032 | 20 / 0.0013 / 0.03 | 20 / 0.0013 / 0.03 |
| [C106199](https://jlcpcb.com/partdetail/YAGEO-CC0402JRNPO9BN100/C106199) | [CC0402JRNPO9BN100](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402jrnpo9bn100_C106199.html) | YAGEO | 10p | extended | 2 | 1599419 | 20 / 0.0016 / 0.03 | 22 / 0.0016 / 0.04 |
| [C281755](https://jlcpcb.com/partdetail/YAGEO-CC0402JRNPO9BN240/C281755) | [CC0402JRNPO9BN240](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402jrnpo9bn240_C281755.html) | YAGEO | 24p | extended | 3 | 273013 | 20 / 0.0014 / 0.03 | 25 / 0.0014 / 0.03 |
| [C114394](https://jlcpcb.com/partdetail/YAGEO-CC0402JRNPO9BN360/C114394) | [CC0402JRNPO9BN360](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402jrnpo9bn360_C114394.html) | YAGEO | 36p | extended | 1 | 194527 | 20 / 0.0014 / 0.03 | 20 / 0.0014 / 0.03 |
| [C25120](https://jlcpcb.com/partdetail/25863-0402WGF499JTCE/C25120) | [0402WGF499JTCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf499jtce_C25120.html) | UNI-ROYAL(Uniroyal Elec) | 49.9 | basic | 7 | 1244937 | 24 / 0.0012 / 0.03 | 45 / 0.0012 / 0.05 |
| [C25079](https://jlcpcb.com/partdetail/25822-0402WGF1200TCE/C25079) | [0402WGF1200TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf1200tce_C25079.html) | UNI-ROYAL(Uniroyal Elec) | 120 | basic | 3 | 3259209 | 21 / 0.0012 / 0.03 | 30 / 0.0012 / 0.04 |
| [C25105](https://jlcpcb.com/partdetail/25848-0402WGF330JTCE/C25105) | [0402WGF330JTCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf330jtce_C25105.html) | UNI-ROYAL(Uniroyal Elec) | 33 | basic | 4 | 3510838 | 23 / 0.0011 / 0.03 | 35 / 0.0011 / 0.04 |
| [C620468](https://jlcpcb.com/partdetail/650339-0402WGF115JTCE/C620468) | [0402WGF115JTCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf115jtce_C620468.html) | UNI-ROYAL(Uniroyal Elec) | 11.5 | extended | 8 | 9670 | 26 / 0.0011 / 0.03 | 50 / 0.0011 / 0.06 |
| [C138027](https://jlcpcb.com/partdetail/YAGEO-RC0402FR0724K9L/C138027) | [RC0402FR-0724K9L](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_yageo-rc0402fr-0724k9l_C138027.html) | YAGEO | 24.9k | extended | 1 | 845998 | 20 / 0.0014 / 0.03 | 20 / 0.0014 / 0.03 |
| [C25905](https://jlcpcb.com/partdetail/26648-0402WGF5101TCE/C25905) | [0402WGF5101TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf5101tce_C25905.html) | UNI-ROYAL(Uniroyal Elec) | 5.1k | basic | 2 | 4473114 | 20 / 0.0014 / 0.03 | 25 / 0.0014 / 0.03 |
| [C2933071](https://jlcpcb.com/partdetail/FOJAN-FRC0402F1300TS/C2933071) | [FRC0402F1300TS](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_fojan-frc0402f1300ts_C2933071.html) | FOJAN | 130 | extended | 2 | 43090 | 20 / 0.0009 / 0.02 | 20 / 0.0009 / 0.02 |
| [C3013184](https://jlcpcb.com/partdetail/FOJAN-FRC0402F64R9TS/C3013184) | [FRC0402F64R9TS](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_fojan-frc0402f64r9ts_C3013184.html) | FOJAN | 64.9 | extended | 3 | 49037 | 20 / 0.0012 / 0.02 | 25 / 0.0012 / 0.03 |
| [C2909380](https://jlcpcb.com/partdetail/FOJAN-FRC0402F68R0TS/C2909380) | [FRC0402F68R0TS](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_fojan-frc0402f68r0ts_C2909380.html) | FOJAN | 68 | extended | 1 | 1111632 | 20 / 0.0011 / 0.02 | 20 / 0.0011 / 0.02 |
| [C2930008](https://jlcpcb.com/partdetail/FOJAN-FRC0402F4301TS/C2930008) | [FRC0402F4301TS](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_fojan-frc0402f4301ts_C2930008.html) | FOJAN | 4.3k | extended | 4 | 260770 | 20 / 0.0012 / 0.02 | 30 / 0.0012 / 0.04 |
| [C7467414](https://jlcpcb.com/partdetail/FOJAN-FRC0402F1150TS/C7467414) | [FRC0402F1150TS](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_fojan-frc0402f1150ts_C7467414.html) | FOJAN | 115 | extended | 1 | 12182 | 20 / 0.001 / 0.02 | 20 / 0.001 / 0.02 |
| [C270625](https://jlcpcb.com/partdetail/260005-0402WGF240JTCE/C270625) | [0402WGF240JTCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf240jtce_C270625.html) | UNI-ROYAL(Uniroyal Elec) | 24 | extended | 2 | 191181 | 20 / 0.0012 / 0.02 | 20 / 0.0012 / 0.02 |
| [C25765](https://jlcpcb.com/partdetail/26508-0402WGF2002TCE/C25765) | [0402WGF2002TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf2002tce_C25765.html) | UNI-ROYAL(Uniroyal Elec) | 20k | basic | 1 | 2777585 | 20 / 0.001 / 0.02 | 20 / 0.001 / 0.02 |
| [C2998115](https://jlcpcb.com/partdetail/FOJAN-FRC0402F1911TS/C2998115) | [FRC0402F1911TS](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_fojan-frc0402f1911ts_C2998115.html) | FOJAN | 1.91k 1% | extended | 1 | 52953 | 20 / 0.0011 / 0.02 | 20 / 0.0011 / 0.02 |
| [C5159686](https://jlcpcb.com/partdetail/FOJAN-FRC0402F3831TS/C5159686) | [FRC0402F3831TS](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_fojan-frc0402f3831ts_C5159686.html) | FOJAN | 3.83k | extended | 2 | 34141 | 20 / 0.001 / 0.02 | 20 / 0.001 / 0.02 |
| [C25741](https://jlcpcb.com/partdetail/26484-0402WGF1003TCE/C25741) | [0402WGF1003TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf1003tce_C25741.html) | UNI-ROYAL(Uniroyal Elec) | 100k | basic | 6 | 9759325 | 24 / 0.0009 / 0.02 | 42 / 0.0009 / 0.04 |
| [C122548](https://jlcpcb.com/partdetail/123817-0402WGF3322TCE/C122548) | [0402WGF3322TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf3322tce_C122548.html) | UNI-ROYAL(Uniroyal Elec) | 33.2k | extended | 1 | 611758 | 20 / 0.001 / 0.02 | 20 / 0.001 / 0.02 |
| [C11460](https://jlcpcb.com/partdetail/12014-0402WGF3091TCE/C11460) | [0402WGF3091TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf3091tce_C11460.html) | UNI-ROYAL(Uniroyal Elec) | 3.09k | extended | 1 | 9749 | 20 / 0.0009 / 0.02 | 20 / 0.0009 / 0.02 |
| [C25860](https://jlcpcb.com/partdetail/26603-0402WGF1101TCE/C25860) | [0402WGF1101TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf1101tce_C25860.html) | UNI-ROYAL(Uniroyal Elec) | 1.10k 1% | extended | 1 | 578696 | 20 / 0.0012 / 0.02 | 20 / 0.0012 / 0.02 |
| [C85373](https://jlcpcb.com/partdetail/86546-0402WGF1021TCE/C85373) | [0402WGF1021TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf1021tce_C85373.html) | UNI-ROYAL(Uniroyal Elec) | 1.02k 1% | extended | 1 | 17345 | 20 / 0.0012 / 0.02 | 20 / 0.0012 / 0.02 |
| [C25092](https://jlcpcb.com/partdetail/25835-0402WGF220JTCE/C25092) | [0402WGF220JTCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf220jtce_C25092.html) | UNI-ROYAL(Uniroyal Elec) | 22 | basic | 1 | 4530321 | 20 / 0.001 / 0.02 | 20 / 0.001 / 0.02 |
| [C25882](https://jlcpcb.com/partdetail/26625-0402WGF2401TCE/C25882) | [0402WGF2401TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf2401tce_C25882.html) | UNI-ROYAL(Uniroyal Elec) | 2.4k | preferred | 1 | 679998 | 20 / 0.0012 / 0.02 | 20 / 0.0012 / 0.02 |
| [C25104](https://jlcpcb.com/partdetail/25847-0402WGF3300TCE/C25104) | [0402WGF3300TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf3300tce_C25104.html) | UNI-ROYAL(Uniroyal Elec) | 330 | basic | 1 | 1406873 | 20 / 0.0011 / 0.02 | 20 / 0.0011 / 0.02 |
| [C2933083](https://jlcpcb.com/partdetail/FOJAN-FRC0402F2491TS/C2933083) | [FRC0402F2491TS](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_fojan-frc0402f2491ts_C2933083.html) | FOJAN | 2.49k 1% | extended | 1 | 1724927 | 20 / 0.0012 / 0.02 | 20 / 0.0012 / 0.02 |
| [C25123](https://jlcpcb.com/partdetail/25866-0402WGF5100TCE/C25123) | [0402WGF5100TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf5100tce_C25123.html) | UNI-ROYAL(Uniroyal Elec) | 510 | basic | 2 | 2407011 | 20 / 0.0011 / 0.02 | 22 / 0.0011 / 0.02 |
| [C25908](https://jlcpcb.com/partdetail/26651-0402WGF5601TCE/C25908) | [0402WGF5601TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf5601tce_C25908.html) | UNI-ROYAL(Uniroyal Elec) | 5.6k | preferred | 1 | 256903 | 20 / 0.001 / 0.02 | 20 / 0.001 / 0.02 |
| [C25768](https://jlcpcb.com/partdetail/26511-0402WGF2202TCE/C25768) | [0402WGF2202TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf2202tce_C25768.html) | UNI-ROYAL(Uniroyal Elec) | 22k | basic | 1 | 1203701 | 20 / 0.001 / 0.02 | 20 / 0.001 / 0.02 |
| [C25117](https://jlcpcb.com/partdetail/25860-0402WGF4700TCE/C25117) | [0402WGF4700TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf4700tce_C25117.html) | UNI-ROYAL(Uniroyal Elec) | 470 | basic | 2 | 2483325 | 20 / 0.001 / 0.02 | 20 / 0.001 / 0.02 |
| [C2998176](https://jlcpcb.com/partdetail/FOJAN-FRC0402F2103TS/C2998176) | [FRC0402F2103TS](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_fojan-frc0402f2103ts_C2998176.html) | FOJAN | 210k | extended | 1 | 485340 | 20 / 0.0011 / 0.02 | 20 / 0.0011 / 0.02 |
| [C17168](https://jlcpcb.com/partdetail/17853-0402WGF0000TCE/C17168) | [0402WGF0000TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf0000tce_C17168.html) | UNI-ROYAL(Uniroyal Elec) | 0 | basic | 1 | 14793195 | 20 / 0.0012 / 0.02 | 20 / 0.0012 / 0.02 |
| none |  |  | TC1-1-13M+ |  | 1 |  | 2 / — / — | 5 / — / — |
| none |  |  | Si549 LVPECL 3V3 pinout C |  | 1 |  | 2 / — / — | 5 / — / — |
| | **Total** | | | | | | **1652.38** | **3939.97** |
<!-- parts:end -->

Two lines changed against the BOM of 2 October, because their part ran out (`lcsc_select.py` re-run
on 10 Nov):
- **22.6 kΩ:** C26960 (16 in stock, sold by the reel) → **C100316**, LIZ CR0402FF2262G. Still
  ±1 %, but ±200 ppm/°C against ±100.
- **PROG switch:** TL3342F160QG (0 in stock) → **TL3342F450QG**, the same switch with a 4.5 N
  actuation force against 1.6 N.

---

## 5. Not from JLCPCB

| Item | Why | Price |
|---|---|---|
| **Si549** (Y401), LVPECL, 3.3 V, pinout C, 5 × 7 mm | Skyworks builds the ordering code per configuration; no LCSC code. Order from Skyworks or a distributor and consign it | Not quoted; ~$15–25 each `[E]` |
| **TC1-1-13M+** (T1301), the mixer's input balun | LCSC's only part of that name is HLT's H3-TC1-1-13M+, a clone in a 5-pad body with another pin-out that does not fit the footprint ([RX_VU_SPEC](RX_VU_SPEC.md)). Order Mini-Circuits' part from a distributor and consign it | Not quoted; ~$3 each `[E]` |
| Kria KV260 | The host | Already bought |
| 12 V supply, ribbon to AERIS-10 | | See [SHOPPING_LIST.md](SHOPPING_LIST.md) |
