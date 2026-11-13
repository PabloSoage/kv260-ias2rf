# JLCPCB order — quote

*10 November 2026, bare boards re-quoted on 8 layers on 12 November, parts and assembly for the Ethernet option on 13 November · board CSI2-KRIA-KV260_Rev01 · not ordered yet*

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
| Bare boards, 8 layers (5 made either way) | 282.92 | 282.92 | JLCPCB's quote page, §2 |
| Assembly fees | 265.73 | 290.51 | JLCPCB's price page, §3 |
| Parts (107 LCSC codes) | 1,503.56 | 3,602.84 | JLCPCB's parts search, §4 |
| Si549 oscillator, bought apart and consigned | ~40 `[E]` | ~100 `[E]` | No LCSC code, §5 |
| Shipping, UPS Express Saver, duties paid (DDP) | 26.60 | 26.60 | Quote page, for the bare boards' 0.42 kg; more for assembled ones |
| **Total** | **≈ 2,119** | **≈ 4,303** | |
| Per board | ≈ 1,059 | ≈ 861 | |

On 6 layers the bare boards were $236.88, so the move to 8 layers adds **$46.04 to the order**,
2 % of the total for two boards. The parts list grew by two 0402 resistors (R105, R106), a few cents.

**The Ethernet option (13 November, CONTROL_SPEC §7) adds about $46 to two boards:** $25 of parts
(the PHY and the RJ45 are most of it) and $21 of assembly, mostly the 12 new feeders. Its four
DNP capacitors are not in the BOM. **The bare boards were not re-quoted:** the RJ45's tab makes the
board's bounding box 140 × 132 mm (119 × 132 before), and JLCPCB prices by it. Re-quote before
ordering.

**Parts are three quarters of the cost,** and eight lines are almost 90 % of the parts (about $654 of $739 per board):

| Part | Each | ×/board | Per board |
|---|---|---|---|
| M3SWA2-34DR+ (RF switch) | 45.70 | 4 | 182.82 |
| AD9253BCPZ-125 (ADC) | 97.26 | 1 | 97.26 |
| AD9484BCPZ-500 (ADC) | 97.17 | 1 | 97.17 |
| XC7A50T-2FTG256I (FPGA) | 93.36 | 1 | 93.36 |
| AD8352ACPZ (ADC driver) | 20.84 | 4 | 83.37 |
| SMA edge connectors | 4.77 | 12 | 57.20 |
| ADCLK948BCPZ (clock) | 20.76 | 1 | 20.76 |
| ADT2-1T+ (balun) | 7.22 | 3 | 21.67 |

Prices from LCSC, at the tier for two boards' quantity.

**Eight parts are short of stock** for even two boards: ADCLK948, AD9484, AD9253, AD9708 and
M3SWA2-34DR+ have none, AD8352 has 7 of 8, ADT2-1T+ 1 of 6 and TMP1075DR 1 of 2 (13 November). JLCPCB's "global sourcing" buys them
in and its price can differ from LCSC's list price above. The other choice is to buy them from a
distributor and consign them. The ADI parts and the Mini-Circuits switches are sold at Digi-Key and
Mouser, often for less than the LCSC list price.

---

## 2. Bare boards: $282.92 for 5

Entered on [jlcpcb.com/quote](https://cart.jlcpcb.com/quote) on 12 Nov 2026 with the values of
FABRICATION §2 (8 layers); the 6-layer column is the same page on 10 Nov. Nothing was uploaded: the
page prices from the dimensions.

| Field | Value | 6 layers (2116A) | 8 layers (2116C) |
|---|---|---|---|
| Layers, size, quantity | 119 × 120 mm, 5 | Board **9.30** | Board **11.90** |
| Thickness, finish | 1.6 mm (2116C is 1.52 mm actual), ENIG 1 µ" | Surface finish **18.20** | **18.20** |
| Material | FR4 TG155 | **3.66** | 0.00 |
| Copper | 1 oz outer, 0.5 oz inner | — | — |
| **Stack** | JLC06161H-2116A / **JLC08161H-2116C** | Stack-up fee **102.79** | **83.89** |
| Impedance control | ±10 % | **33.08** | **33.08** |
| Via covering | Epoxy filled & capped (POFV) | 0.00 | 0.00 |
| Min via | 0.2 mm hole (the board's 0.20 / 0.45 mm vias) | **18.31** | **18.31** |
| 4-wire Kelvin test | Forced on by the 0.2 mm vias | **17.49** | **17.49** |
| Confirm production file | Forced on by the specified stack | **1.05** | **1.05** |
| Engineering fee | | **33.00** | **99.00** |
| Build time | 7–8 days | 0.00 | 0.00 |
| **Total** | | **236.88** | **282.92** (desktop app: 277.92) |

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
| SMT joints (1,930 per board) | 0.0016 / joint | 6.18 | 15.44 |
| Hand-soldered joints (85 per board: J1001, J1101, J1102, J1103, J1201) | 0.0164 / joint | 2.79 | 6.97 |
| Hand-soldering labour | 3.58 / order | 3.58 | 3.58 |
| Feeder loading: every part on Standard, basic or extended | 1.53 × 106 parts | 162.18 | 162.18 |
| X-ray, 14 parts per board with hidden joints (FPGA, QFNs, LFCSPs) | 0.82 / 0.49 per part | 22.96 | 34.30 |
| Packing | 0.50 + area | 0.50 | 0.50 |
| **Total** | | **265.73** | **290.51** |

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
*Searched 2026-11-13 by `_work/fab/quote.py`; prices in USD, JLCPCB's tier for the quantity bought.*

| LCSC | Part | Maker | Value | Lib | Per board | Stock | Buy 2 / unit / cost | Buy 5 / unit / cost |
|---|---|---|---|---|---|---|---|---|
| [C33062043](https://jlcpcb.com/partdetail/MiniCircuits-M3SWA2_34DR/C33062043) | [M3SWA2-34DR+](https://lcsc.com/product-detail/rf-switches_mini-circuits-m3swa2-34dr_C33062043.html) | Mini-Circuits | M3SWA2-34DR+ | extended | 4 | **0** | 8 / 45.7 / 365.59 | 20 / 44.22 / 884.42 |
| [C514282](https://jlcpcb.com/partdetail/AnalogDevices-AD9253BCPZ125/C514282) | [AD9253BCPZ-125](https://www.lcsc.com/product-detail/analog-to-digital-converters-adc_analog-devices-ad9253bcpz-125_C514282.html) | Analog Devices | AD9253BCPZ-125 | extended | 1 | **0** | 2 / 97.25 / 194.50 | 5 / 97.25 / 486.25 |
| [C653480](https://jlcpcb.com/partdetail/AnalogDevices-AD9484BCPZ500/C653480) | [AD9484BCPZ-500](https://www.lcsc.com/product-detail/analog-to-digital-converters-adc_analog-devices-ad9484bcpz-500_C653480.html) | Analog Devices | AD9484BCPZ-500 | extended | 1 | **0** | 2 / 97.16 / 194.32 | 5 / 97.16 / 485.79 |
| [C2976033](https://jlcpcb.com/partdetail/AMDXILINX-XC7A50T2FTG256I/C2976033) | [XC7A50T-2FTG256I](https://www.lcsc.com/product-detail/programmable-logic-device-cplds-fpgas_amd-xilinx-xc7a50t-2ftg256i_C2976033.html) | AMD/XILINX | XC7A50T-2FTG256I | extended | 1 | 27 | 2 / 93.35 / 186.69 | 5 / 93.35 / 466.73 |
| [C578707](https://jlcpcb.com/partdetail/AnalogDevices-AD8352ACPZR7/C578707) | [AD8352ACPZ-R7](https://www.lcsc.com/product-detail/rf-amplifiers_analog-devices-ad8352acpz-r7_C578707.html) | Analog Devices | AD8352ACPZ | extended | 4 | **7** | 8 / 20.84 / 166.72 | 20 / 19.96 / 399.18 |
| [C5199907](https://jlcpcb.com/partdetail/Samtec-SMA_J_P_H_STEM1/C5199907) | [SMA-J-P-H-ST-EM1](https://www.lcsc.com/product-detail/coaxial-connectors-rf_samtec-sma-j-p-h-st-em1_C5199907.html) | Samtec | CLK_REF_IN / CLK_OUT / SDR_RX_A / AERIS_IF_A / AERIS_IF / SDR_RX_WB / SDR_TX_A / AERIS_TX_A / AERIS_TX / SDR_TX_WB / SDR_RX_C / SDR_TX_C | extended | 12 | 174 | 24 / 4.766 / 114.38 | 60 / 4.363 / 261.80 |
| [C5223988](https://jlcpcb.com/partdetail/MiniCircuits-ADT2_1T/C5223988) | [ADT2-1T+](https://www.lcsc.com/product-detail/balun_mini-circuits-adt2-1t_C5223988.html) | Mini-Circuits | ADT2-1T+ | extended | 3 | **1** | 6 / 7.223 / 43.34 | 15 / 6.259 / 93.89 |
| [C578960](https://jlcpcb.com/partdetail/AnalogDevices-ADCLK948BCPZ/C578960) | [ADCLK948BCPZ](https://www.lcsc.com/product-detail/clock-buffers-drivers-distributors_analog-devices-adclk948bcpz_C578960.html) | Analog Devices | ADCLK948BCPZ | extended | 1 | **0** | 2 / 20.76 / 41.52 | 5 / 20.76 / 103.80 |
| [C653734](https://jlcpcb.com/partdetail/AnalogDevices-AD9708ARZ/C653734) | [AD9708ARZ](https://www.lcsc.com/product-detail/digital-to-analog-converters-dac_analog-devices-ad9708arz_C653734.html) | Analog Devices | AD9708AR | extended | 1 | **0** | 2 / 16.83 / 33.66 | 5 / 16.83 / 84.15 |
| [C653820](https://jlcpcb.com/partdetail/AnalogDevices-AD9767ASTZRL/C653820) | [AD9767ASTZRL](https://www.lcsc.com/product-detail/digital-to-analog-converters-dac_analog-devices-ad9767astzrl_C653820.html) | Analog Devices | AD9767ASTZ | extended | 1 | 206 | 2 / 14.54 / 29.08 | 5 / 14.54 / 72.71 |
| [C41359590](https://jlcpcb.com/partdetail/MicronTech-MT25QL128ABA1ESE0SIT/C41359590) | [MT25QL128ABA1ESE-0SIT](https://www.lcsc.com/product-detail/nor-flash_micron-tech-mt25ql128aba1ese-0sit_C41359590.html) | Micron Tech | MT25QL128ABA1ESE | extended | 1 | 2040 | 2 / 12.96 / 25.91 | 5 / 12.96 / 64.78 |
| [C544500](https://jlcpcb.com/partdetail/TexasInstruments-TPS7A8300RGRR/C544500) | [TPS7A8300RGRR](https://www.lcsc.com/product-detail/voltage-regulators-linear-low-drop-out-ldo-regulators_texas-instruments-tps7a8300rgrr_C544500.html) | Texas Instruments | TPS7A8300RGR | extended | 3 | 201 | 6 / 2.5 / 15.00 | 15 / 2.2 / 33.01 |
| [C2878381](https://jlcpcb.com/partdetail/TexasInstruments-TMP1075DR/C2878381) | [TMP1075DR](https://www.lcsc.com/product-detail/temperature-sensors_texas-instruments-tmp1075dr_C2878381.html) | Texas Instruments | TMP1075DR | extended | 1 | **1** | 23 / 0.396 / 9.11 | 23 / 0.396 / 9.11 |
| [C138714](https://jlcpcb.com/partdetail/TexasInstruments-TPD4E05U06DQAR/C138714) | [TPD4E05U06DQAR](https://www.lcsc.com/product-detail/esd-and-surge-protection-tvs-esd_texas-instruments-tpd4e05u06dqar_C138714.html) | Texas Instruments | TPD4E05U06DQAR | extended | 3 | 338 | 137 / 0.066 / 9.04 | 137 / 0.066 / 9.04 |
| [C264098](https://jlcpcb.com/partdetail/DiodesIncorporated-DMP3013SFV7/C264098) | [DMP3013SFV-7](https://www.lcsc.com/product-detail/mosfets_diodes-incorporated-dmp3013sfv-7_C264098.html) | Diodes Incorporated | DMP3013SFV | extended | 1 | 458 | 5 / 1.234 / 6.17 | 5 / 1.234 / 6.17 |
| [C2904132](https://jlcpcb.com/partdetail/RealtekSemicon-RTL8211FSICG/C2904132) | [RTL8211FSI-CG](https://www.lcsc.com/product-detail/ethernet-transceivers_realtek-semicon-rtl8211fsi-cg_C2904132.html) | Realtek Semicon | RTL8211FSI-CG | extended | 1 | 3236 | 2 / 2.871 / 5.74 | 5 / 2.871 / 14.36 |
| [C50933](https://jlcpcb.com/partdetail/51945-HR911130C/C50933) | [HR911130C](https://www.lcsc.com/product-detail/ethernet-connectors-modular-connectors-rj45-rj11_hanrun-zhongshan-hanrun-elec-hr911130c_C50933.html) | HANRUN(Zhongshan HanRun Elec) | HR911130C | extended | 1 | 7247 | 2 / 2.858 / 5.72 | 5 / 2.858 / 14.29 |
| [C90143](https://jlcpcb.com/partdetail/TaiyoYuden-EMK325ABJ107MMP/C90143) | [EMK325ABJ107MM-P](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_taiyo-yuden-emk325abj107mm-p_C90143.html) | Taiyo Yuden | 100u | extended | 1 | 13554 | 5 / 1.022 / 5.11 | 5 / 1.022 / 5.11 |
| [C544380](https://jlcpcb.com/partdetail/TexasInstruments-LM2663MNOPB/C544380) | [LM2663M/NOPB](https://www.lcsc.com/product-detail/dc-dc-converters_texas-instruments-lm2663m-nopb_C544380.html) | Texas Instruments | LM2663M | extended | 1 | 5285 | 2 / 2.392 / 4.78 | 5 / 2.392 / 11.96 |
| [C2041815](https://jlcpcb.com/partdetail/BOURNS-SRP7028A8R2M/C2041815) | [SRP7028A-8R2M](https://www.lcsc.com/product-detail/power-inductors_bourns-srp7028a-8r2m_C2041815.html) | BOURNS | SRP7028A-8R2M | extended | 1 | 215 | 2 / 1.821 / 3.64 | 5 / 1.821 / 9.10 |
| [C45783](https://jlcpcb.com/partdetail/46786-CL21A226MAQNNNE/C45783) | [CL21A226MAQNNNE](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_samsung-electro-mechanics-cl21a226maqnnne_C45783.html) | Samsung Electro-Mechanics | 22u 10V | basic | 13 | 4184516 | 30 / 0.1084 / 3.25 | 69 / 0.1084 / 7.48 |
| [C492354](https://jlcpcb.com/partdetail/MOLEX-878321420/C492354) | [878321420](https://www.lcsc.com/product-detail/wire-to-board-connector_molex-878321420_C492354.html) | MOLEX | JTAG 2x7 2mm | extended | 1 | 3373 | 2 / 1.401 / 2.80 | 5 / 1.401 / 7.00 |
| [C45961](https://jlcpcb.com/partdetail/Nexperia-PESD5V0F1BL315/C45961) | [PESD5V0F1BL,315](https://www.lcsc.com/product-detail/esd-and-surge-protection-tvs-esd_nexperia-pesd5v0f1bl-315_C45961.html) | Nexperia | PESD5V0F1BL | extended | 12 | 138020 | 32 / 0.0841 / 2.69 | 68 / 0.066 / 4.49 |
| [C77101](https://jlcpcb.com/partdetail/MurataElectronics-GRM32ER61C476KE15L/C77101) | [GRM32ER61C476KE15L](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_murata-electronics-grm32er61c476ke15l_C77101.html) | Murata Electronics | 47u | extended | 5 | 102428 | 12 / 0.216 / 2.59 | 27 / 0.216 / 5.83 |
| [C136150](https://jlcpcb.com/partdetail/KEMET-T520V337M006ATE025/C136150) | [T520V337M006ATE025](https://www.lcsc.com/product-detail/tantalum-capacitors_kemet-t520v337m006ate025_C136150.html) | KEMET | 330u | extended | 1 | 1454 | 2 / 1.278 / 2.56 | 5 / 1.278 / 6.39 |
| [C913186](https://jlcpcb.com/partdetail/BOURNS-SRP7028A3R3M/C913186) | [SRP7028A-3R3M](https://www.lcsc.com/product-detail/power-inductors_bourns-srp7028a-3r3m_C913186.html) | BOURNS | SRP7028A-3R3M | extended | 2 | 1060 | 4 / 0.5923 / 2.37 | 10 / 0.4712 / 4.71 |
| [C3096093](https://jlcpcb.com/partdetail/CUI-PJ102AH/C3096093) | [PJ-102AH](https://www.lcsc.com/product-detail/dc-power-connectors_cui-pj-102ah_C3096093.html) | CUI | 12V IN | extended | 1 | 706 | 2 / 1.055 / 2.11 | 5 / 1.055 / 5.28 |
| [C2886897](https://jlcpcb.com/partdetail/ESwitch-TL3342F450QG/C2886897) | [TL3342F450QG](https://www.lcsc.com/product-detail/tactile-switches_e-switch-tl3342f450qg_C2886897.html) | E-Switch | PROG | extended | 1 | 384 | 2 / 0.9375 / 1.88 | 5 / 0.9375 / 4.69 |
| [C7432791](https://jlcpcb.com/partdetail/Chinocera-HGC1210R5476M250NSVK/C7432791) | [HGC1210R5476M250NSVK](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_chinocera-hgc1210r5476m250nsvk_C7432791.html) | Chinocera | 47u 25V | extended | 1 | 90150 | 5 / 0.3256 / 1.63 | 5 / 0.3256 / 1.63 |
| [C15850](https://jlcpcb.com/partdetail/16532-CL21A106KAYNNNE/C15850) | [CL21A106KAYNNNE](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_samsung-electro-mechanics-cl21a106kaynnne_C15850.html) | Samsung Electro-Mechanics | 10u / 10u 10V | basic | 20 | 8435217 | 50 / 0.0315 / 1.57 | 110 / 0.0315 / 3.46 |
| [C424540](https://jlcpcb.com/partdetail/HRS_Hirose-BM20B_0_8_34DP_0_4V_51/C424540) | [BM20B(0.8)-34DP-0.4V(51)](https://www.lcsc.com/product-detail/board-to-board-and-backplane-connector_hrs-hirose-bm20b-0-8-34dp-0-4v-51_C424540.html) | HRS(Hirose) | BM20B(0.8)-34DP | extended | 2 | 18280 | 6 / 0.2216 / 1.33 | 12 / 0.2216 / 2.66 |
| [C96123](https://jlcpcb.com/partdetail/97327-CL31A476MPHNNNE/C96123) | [CL31A476MPHNNNE](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_samsung-electro-mechanics-cl31a476mphnnne_C96123.html) | Samsung Electro-Mechanics | 47u | basic | 2 | 501278 | 8 / 0.1628 / 1.30 | 14 / 0.1628 / 2.28 |
| [C841384](https://jlcpcb.com/partdetail/TexasInstruments-LMR33630ADDAR/C841384) | [LMR33630ADDAR](https://www.lcsc.com/product-detail/dc-dc-converters_texas-instruments-lmr33630addar_C841384.html) | Texas Instruments | LMR33630ADDA | extended | 1 | 26750 | 2 / 0.6315 / 1.26 | 5 / 0.6315 / 3.16 |
| [C1779](https://jlcpcb.com/partdetail/2131-CL21A475KAQNNNE/C1779) | [CL21A475KAQNNNE](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_samsung-electro-mechanics-cl21a475kaqnnne_C1779.html) | Samsung Electro-Mechanics | 4.7u | basic | 13 | 2234182 | 36 / 0.0342 / 1.23 | 75 / 0.0342 / 2.56 |
| [C113130](https://jlcpcb.com/partdetail/MurataElectronics-LQW18ANR11G00D/C113130) | [LQW18ANR11G00D](https://www.lcsc.com/product-detail/power-inductors_murata-electronics-lqw18anr11g00d_C113130.html) | Murata Electronics | 107.3n | extended | 12 | 5576 | 28 / 0.0436 / 1.22 | 64 / 0.0436 / 2.79 |
| [C1329579](https://jlcpcb.com/partdetail/BOURNS-SRP7028A2R2M/C1329579) | [SRP7028A-2R2M](https://www.lcsc.com/product-detail/power-inductors_bourns-srp7028a-2r2m_C1329579.html) | BOURNS | SRP7028A-2R2M | extended | 1 | 930 | 2 / 0.5596 / 1.12 | 5 / 0.5596 / 2.80 |
| [C2049745](https://jlcpcb.com/partdetail/2141314-DFE201210U_2R2MP2/C2049745) | [DFE201210U-2R2M=P2](https://www.lcsc.com/product-detail/power-inductors_murata-electronics-dfe201210u-2r2m-p2_C2049745.html) | Murata Electronics | 2.2u | extended | 1 | 5386 | 5 / 0.2091 / 1.05 | 5 / 0.2091 / 1.05 |
| [C132439](https://jlcpcb.com/partdetail/143738-B_3000S40P0110/C132439) | [B-3000S40P-0110](https://www.lcsc.com/product-detail/idc-connectors_ckmtw-shenzhen-cankemeng-b-3000s40p-0110_C132439.html) | Ckmtw(Shenzhen Cankemeng) | AERIS ADAR | extended | 1 | 678 | 2 / 0.4499 / 0.90 | 5 / 0.4499 / 2.25 |
| [C13585](https://jlcpcb.com/partdetail/14236-CL31A106KBHNNNE/C13585) | [CL31A106KBHNNNE](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_samsung-electro-mechanics-cl31a106kbhnnne_C13585.html) | Samsung Electro-Mechanics | 10u 25V | basic | 1 | 3636726 | 6 / 0.121 / 0.73 | 9 / 0.121 / 1.09 |
| [C1525](https://jlcpcb.com/partdetail/1877-CL05B104KO5NNNC/C1525) | [CL05B104KO5NNNC](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_samsung-electro-mechanics-cl05b104ko5nnnc_C1525.html) | Samsung Electro-Mechanics | 100n | basic | 125 | 32047940 | 265 / 0.0024 / 0.64 | 640 / 0.0024 / 1.54 |
| [C1623](https://jlcpcb.com/partdetail/1975-CL10B474KA8NNNC/C1623) | [CL10B474KA8NNNC](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_samsung-electro-mechanics-cl10b474ka8nnnc_C1623.html) | Samsung Electro-Mechanics | 0.47u / 470n | basic | 26 | 1441006 | 62 / 0.0092 / 0.57 | 140 / 0.0092 / 1.29 |
| [C90061](https://jlcpcb.com/partdetail/TexasInstruments-TPS562201DDCR/C90061) | [TPS562201DDCR](https://www.lcsc.com/product-detail/dc-dc-converters_texas-instruments-tps562201ddcr_C90061.html) | Texas Instruments | TPS562201 | extended | 3 | 524244 | 10 / 0.0565 / 0.57 | 19 / 0.0565 / 1.07 |
| [C9006](https://jlcpcb.com/partdetail/YXC_CrystalOscillators-X322525MOB4SI/C9006) | [X322525MOB4SI](https://www.lcsc.com/product-detail/crystals_yxc-crystal-oscillators-x322525mob4si_C9006.html) | YXC Crystal Oscillators | 25MHz | basic | 1 | 343129 | 6 / 0.0951 / 0.57 | 9 / 0.0951 / 0.86 |
| [C1855147](https://jlcpcb.com/partdetail/YAGEO-CQ0402ARNPO0BNR30/C1855147) | [CQ0402ARNPO0BNR30](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cq0402arnpo0bnr30_C1855147.html) | YAGEO | 0.3p | extended | 2 | 6908 | 20 / 0.028 / 0.56 | 20 / 0.028 / 0.56 |
| [C7829](https://jlcpcb.com/partdetail/TexasInstruments-SN74LVC1G07DBVR/C7829) | [SN74LVC1G07DBVR](https://www.lcsc.com/product-detail/buffers-drivers-receivers-transceivers_texas-instruments-sn74lvc1g07dbvr_C7829.html) | Texas Instruments | 74LVC1G07 | extended | 1 | 35854 | 6 / 0.0931 / 0.56 | 9 / 0.0931 / 0.84 |
| [C326067](https://jlcpcb.com/partdetail/YAGEO-CQ0402ARNPO9BNR20/C326067) | [CQ0402ARNPO9BNR20](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cq0402arnpo9bnr20_C326067.html) | YAGEO | 0.2p | extended | 1 | 5006 | 20 / 0.0267 / 0.53 | 20 / 0.0267 / 0.53 |
| [C577389](https://jlcpcb.com/partdetail/YAGEO-CQ0402BRNPO9BNR60/C577389) | [CQ0402BRNPO9BNR60](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cq0402brnpo9bnr60_C577389.html) | YAGEO | 0.6p | extended | 1 | 28769 | 20 / 0.0241 / 0.48 | 20 / 0.0241 / 0.48 |
| [C369174](https://jlcpcb.com/partdetail/343087-JK_MSMD15024V/C369174) | [JK-MSMD150-24V](https://www.lcsc.com/product-detail/resettable-fuses_jinrui-electronic-materials-co-jk-msmd150-24v_C369174.html) | Jinrui Electronic Materials Co. | PTC 1.5A hold | extended | 1 | 19382 | 6 / 0.056 / 0.34 | 9 / 0.056 / 0.50 |
| [C19077423](https://jlcpcb.com/partdetail/hongjiacheng-MMSZ5232B/C19077423) | [MMSZ5232B](https://www.lcsc.com/product-detail/zener-diodes_hongjiacheng-mmsz5232b_C19077423.html) | hongjiacheng | 5.6V | preferred | 8 | 37986 | 20 / 0.0145 / 0.29 | 44 / 0.0145 / 0.64 |
| [C114502](https://jlcpcb.com/partdetail/STMicroelectronics-M24C02FMN6TP/C114502) | [M24C02-FMN6TP](https://www.lcsc.com/product-detail/eeprom_stmicroelectronics-m24c02-fmn6tp_C114502.html) | STMicroelectronics | M24C02-FMN6TP | extended | 1 | 16192 | 2 / 0.1422 / 0.28 | 5 / 0.1422 / 0.71 |
| [C108301](https://jlcpcb.com/partdetail/ChilisinElec-PBY160808T_601YN/C108301) | [PBY160808T-601Y-N](https://www.lcsc.com/product-detail/ferrite-beads_chilisin-elec-pby160808t-601y-n_C108301.html) | Chilisin Elec | 600R@100MHz >=1A / 600R@100MHz | extended | 6 | 788604 | 22 / 0.0114 / 0.25 | 40 / 0.0114 / 0.46 |
| [C47339](https://jlcpcb.com/partdetail/48344-CL05A474KP5NNNC/C47339) | [CL05A474KP5NNNC](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_samsung-electro-mechanics-cl05a474kp5nnnc_C47339.html) | Samsung Electro-Mechanics | 0.47u | preferred | 4 | 565200 | 20 / 0.012 / 0.24 | 32 / 0.012 / 0.38 |
| [C19077428](https://jlcpcb.com/partdetail/hongjiacheng-MMSZ5245B/C19077428) | [MMSZ5245B](https://www.lcsc.com/product-detail/zener-diodes_hongjiacheng-mmsz5245b_C19077428.html) | hongjiacheng | 15V | preferred | 1 | 52941 | 15 / 0.0161 / 0.24 | 15 / 0.0161 / 0.24 |
| [C12624](https://jlcpcb.com/partdetail/Hubei_KENTOElec-KT0603G/C12624) | [KT-0603G](https://www.lcsc.com/product-detail/led-indication-discrete_hubei-kento-elec-kt-0603g_C12624.html) | Hubei KENTO Elec | green | extended | 1 | 263745 | 20 / 0.0119 / 0.24 | 21 / 0.0119 / 0.25 |
| [C23733](https://jlcpcb.com/partdetail/24469-CL05A475MP5NRNC/C23733) | [CL05A475MP5NRNC](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_samsung-electro-mechanics-cl05a475mp5nrnc_C23733.html) | Samsung Electro-Mechanics | 4.7u | basic | 1 | 645594 | 20 / 0.0113 / 0.23 | 20 / 0.0113 / 0.23 |
| [C169449](https://jlcpcb.com/partdetail/180834-SMBJ15CA/C169449) | [SMBJ15CA](https://www.lcsc.com/product-detail/esd-and-surge-protection-tvs-esd_shandong-jingdao-microelectronics-smbj15ca_C169449.html) | Shandong Jingdao Microelectronics | SMBJ15CA | extended | 1 | 123765 | 6 / 0.0388 / 0.23 | 9 / 0.0388 / 0.35 |
| [C304314](https://jlcpcb.com/partdetail/TAITECH-HCB1608KF221T20/C304314) | [HCB1608KF-221T20](https://www.lcsc.com/product-detail/ferrite-beads_tai-tech-hcb1608kf-221t20_C304314.html) | TAI-TECH | 220R@100MHz | extended | 4 | 863722 | 20 / 0.0116 / 0.23 | 30 / 0.0116 / 0.35 |
| [C32713279](https://jlcpcb.com/partdetail/hanxia-HX_PZ2_54_2x6PZZ/C32713279) | [HX PZ2.54-2x6P ZZ](https://www.lcsc.com/product-detail/pin-headers_hanxia-hx-pz2-54-2x6p-zz_C32713279.html) | hanxia | Pmod | extended | 1 | 23114 | 2 / 0.093 / 0.19 | 5 / 0.093 / 0.46 |
| [C21120](https://jlcpcb.com/partdetail/21832-CL10B224KA8NNNC/C21120) | [CL10B224KA8NNNC](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_samsung-electro-mechanics-cl10b224ka8nnnc_C21120.html) | Samsung Electro-Mechanics | 220n 25V | basic | 1 | 1040643 | 20 / 0.0089 / 0.18 | 20 / 0.0089 / 0.18 |
| [C8545](https://jlcpcb.com/partdetail/9040-2N7002/C8545) | [2N7002](https://www.lcsc.com/product-detail/mosfets_jiangsu-changjing-electronics-technology-co-ltd-2n7002_C8545.html) | Jiangsu Changjing Electronics Technology Co., Ltd. | 2N7002 | basic | 1 | 6275872 | 10 / 0.0154 / 0.15 | 13 / 0.0154 / 0.20 |
| [C25087](https://jlcpcb.com/partdetail/25830-0402WGF2000TCE/C25087) | [0402WGF2000TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf2000tce_C25087.html) | UNI-ROYAL(Uniroyal Elec) | 200 | basic | 21 | 1643640 | 52 / 0.0029 / 0.15 | 115 / 0.0029 / 0.33 |
| [C52923](https://jlcpcb.com/partdetail/53938-CL05A105KA5NQNC/C52923) | [CL05A105KA5NQNC](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_samsung-electro-mechanics-cl05a105ka5nqnc_C52923.html) | Samsung Electro-Mechanics | 1u | basic | 5 | 10466734 | 22 / 0.0057 / 0.13 | 37 / 0.0057 / 0.21 |
| [C541339](https://jlcpcb.com/partdetail/YAGEO-CC0402BRNPO9BN5R0/C541339) | [CC0402BRNPO9BN5R0](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402brnpo9bn5r0_C541339.html) | YAGEO | 5p | extended | 2 | 78903 | 20 / 0.0065 / 0.13 | 20 / 0.0065 / 0.13 |
| [C576704](https://jlcpcb.com/partdetail/YAGEO-CC0402JRNPO9BN111/C576704) | [CC0402JRNPO9BN111](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402jrnpo9bn111_C576704.html) | YAGEO | 106p | extended | 3 | 53406 | 20 / 0.0066 / 0.13 | 25 / 0.0066 / 0.17 |
| [C25499](https://jlcpcb.com/partdetail/26242-4D02WGJ0220TCE/C25499) | [4D02WGJ0220TCE](https://www.lcsc.com/product-detail/resistor-networks-arrays_uni-royal-uniroyal-elec-4d02wgj0220tce_C25499.html) | UNI-ROYAL(Uniroyal Elec) | 4x22 | extended | 7 | 631680 | 24 / 0.0052 / 0.12 | 45 / 0.0052 / 0.23 |
| [C1523](https://jlcpcb.com/partdetail/1875-0402B102K500NT/C1523) | [0402B102K500NT](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_fh-guangdong-fenghua-advanced-tech-0402b102k500nt_C1523.html) | FH (Guangdong Fenghua Advanced Tech) | 1n | basic | 6 | 3596926 | 27 / 0.0036 / 0.10 | 45 / 0.0036 / 0.16 |
| [C15195](https://jlcpcb.com/partdetail/15869-CL05B103KB5NNNC/C15195) | [CL05B103KB5NNNC](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_samsung-electro-mechanics-cl05b103kb5nnnc_C15195.html) | Samsung Electro-Mechanics | 10n | basic | 6 | 5548044 | 27 / 0.0037 / 0.10 | 45 / 0.0037 / 0.17 |
| [C106200](https://jlcpcb.com/partdetail/YAGEO-CC0402JRNPO9BN101/C106200) | [CC0402JRNPO9BN101](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402jrnpo9bn101_C106200.html) | YAGEO | 100p | extended | 16 | 6718852 | 52 / 0.0017 / 0.09 | 100 / 0.0017 / 0.17 |
| [C226372](https://jlcpcb.com/partdetail/YAGEO-AC0402FR0724R9L/C226372) | [AC0402FR-0724R9L](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_yageo-ac0402fr-0724r9l_C226372.html) | YAGEO | 24.9 | extended | 7 | 193726 | 24 / 0.0039 / 0.09 | 45 / 0.0039 / 0.18 |
| [C100316](https://jlcpcb.com/partdetail/LIZElec-CR0402FF2262G/C100316) | [CR0402FF2262G](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_liz-elec-cr0402ff2262g_C100316.html) | LIZ Elec | 22.6k | extended | 1 | 19400 | 20 / 0.0043 / 0.09 | 20 / 0.0043 / 0.09 |
| [C1532](https://jlcpcb.com/partdetail/1884-0402B223K500NT/C1532) | [0402B223K500NT](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_fh-guangdong-fenghua-advanced-tech-0402b223k500nt_C1532.html) | FH (Guangdong Fenghua Advanced Tech) | 22n | basic | 2 | 650801 | 20 / 0.0042 / 0.08 | 20 / 0.0042 / 0.08 |
| [C326937](https://jlcpcb.com/partdetail/YAGEO-CC0402BRNPO9BN2R7/C326937) | [CC0402BRNPO9BN2R7](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402brnpo9bn2r7_C326937.html) | YAGEO | 2.7p | extended | 1 | 164692 | 20 / 0.0037 / 0.07 | 20 / 0.0037 / 0.07 |
| [C25076](https://jlcpcb.com/partdetail/25819-0402WGF1000TCE/C25076) | [0402WGF1000TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf1000tce_C25076.html) | UNI-ROYAL(Uniroyal Elec) | 100 | basic | 22 | 10923790 | 59 / 0.0012 / 0.07 | 125 / 0.0012 / 0.15 |
| [C477610](https://jlcpcb.com/partdetail/YAGEO-RC0402FR07130RL/C477610) | [RC0402FR-07130RL](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_yageo-rc0402fr-07130rl_C477610.html) | YAGEO | 130 | extended | 2 | 46498 | 20 / 0.0037 / 0.07 | 20 / 0.0037 / 0.07 |
| [C25092](https://jlcpcb.com/partdetail/25835-0402WGF220JTCE/C25092) | [0402WGF220JTCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf220jtce_C25092.html) | UNI-ROYAL(Uniroyal Elec) | 22 | basic | 1 | 4821332 | 20 / 0.0033 / 0.07 | 20 / 0.0033 / 0.07 |
| [C25744](https://jlcpcb.com/partdetail/26487-0402WGF1002TCE/C25744) | [0402WGF1002TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf1002tce_C25744.html) | UNI-ROYAL(Uniroyal Elec) | 10k / 10k 1% | basic | 22 | 21310056 | 59 / 0.001 / 0.06 | 125 / 0.001 / 0.12 |
| [C25900](https://jlcpcb.com/partdetail/26643-0402WGF4701TCE/C25900) | [0402WGF4701TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf4701tce_C25900.html) | UNI-ROYAL(Uniroyal Elec) | 4.7k | basic | 14 | 14338431 | 38 / 0.0017 / 0.06 | 80 / 0.0017 / 0.14 |
| [C25867](https://jlcpcb.com/partdetail/26610-0402WGF1501TCE/C25867) | [0402WGF1501TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf1501tce_C25867.html) | UNI-ROYAL(Uniroyal Elec) | 1.5k | basic | 1 | 1287261 | 20 / 0.0029 / 0.06 | 20 / 0.0029 / 0.06 |
| [C226375](https://jlcpcb.com/partdetail/YAGEO-AC0402FR07255RL/C226375) | [AC0402FR-07255RL](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_yageo-ac0402fr-07255rl_C226375.html) | YAGEO | 255 | extended | 2 | 7293 | 20 / 0.0024 / 0.05 | 20 / 0.0024 / 0.05 |
| [C106203](https://jlcpcb.com/partdetail/YAGEO-CC0402JRNPO9BN220/C106203) | [CC0402JRNPO9BN220](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402jrnpo9bn220_C106203.html) | YAGEO | 22p | extended | 6 | 2328980 | 22 / 0.0019 / 0.04 | 40 / 0.0019 / 0.08 |
| [C107005](https://jlcpcb.com/partdetail/YAGEO-CC0402JRNPO9BN330/C107005) | [CC0402JRNPO9BN330](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402jrnpo9bn330_C107005.html) | YAGEO | 33p | extended | 6 | 5575974 | 22 / 0.0018 / 0.04 | 40 / 0.0018 / 0.07 |
| [C107002](https://jlcpcb.com/partdetail/YAGEO-CC0402JRNPO9BN270/C107002) | [CC0402JRNPO9BN270](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402jrnpo9bn270_C107002.html) | YAGEO | 27p | extended | 2 | 1035493 | 20 / 0.0018 / 0.04 | 22 / 0.0018 / 0.04 |
| [C25792](https://jlcpcb.com/partdetail/26535-0402WGF4702TCE/C25792) | [0402WGF4702TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf4702tce_C25792.html) | UNI-ROYAL(Uniroyal Elec) | 47k | basic | 1 | 5758864 | 20 / 0.0019 / 0.04 | 20 / 0.0019 / 0.04 |
| [C25120](https://jlcpcb.com/partdetail/25863-0402WGF499JTCE/C25120) | [0402WGF499JTCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf499jtce_C25120.html) | UNI-ROYAL(Uniroyal Elec) | 49.9 | basic | 7 | 1361368 | 24 / 0.0012 / 0.03 | 45 / 0.0012 / 0.05 |
| [C25105](https://jlcpcb.com/partdetail/25848-0402WGF330JTCE/C25105) | [0402WGF330JTCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf330jtce_C25105.html) | UNI-ROYAL(Uniroyal Elec) | 33 | basic | 4 | 3494122 | 23 / 0.0011 / 0.03 | 35 / 0.0011 / 0.04 |
| [C138027](https://jlcpcb.com/partdetail/YAGEO-RC0402FR0724K9L/C138027) | [RC0402FR-0724K9L](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_yageo-rc0402fr-0724k9l_C138027.html) | YAGEO | 24.9k | extended | 1 | 866009 | 20 / 0.0014 / 0.03 | 20 / 0.0014 / 0.03 |
| [C11702](https://jlcpcb.com/partdetail/12256-0402WGF1001TCE/C11702) | [0402WGF1001TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf1001tce_C11702.html) | UNI-ROYAL(Uniroyal Elec) | 1k | basic | 4 | 31596761 | 20 / 0.0013 / 0.03 | 30 / 0.0013 / 0.04 |
| [C3013184](https://jlcpcb.com/partdetail/FOJAN-FRC0402F64R9TS/C3013184) | [FRC0402F64R9TS](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_fojan-frc0402f64r9ts_C3013184.html) | FOJAN | 64.9 | extended | 3 | 59037 | 20 / 0.0012 / 0.02 | 25 / 0.0012 / 0.03 |
| [C2909380](https://jlcpcb.com/partdetail/FOJAN-FRC0402F68R0TS/C2909380) | [FRC0402F68R0TS](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_fojan-frc0402f68r0ts_C2909380.html) | FOJAN | 68 | extended | 1 | 1114219 | 20 / 0.0011 / 0.02 | 20 / 0.0011 / 0.02 |
| [C2930008](https://jlcpcb.com/partdetail/FOJAN-FRC0402F4301TS/C2930008) | [FRC0402F4301TS](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_fojan-frc0402f4301ts_C2930008.html) | FOJAN | 4.3k | extended | 4 | 212421 | 20 / 0.0012 / 0.02 | 30 / 0.0012 / 0.04 |
| [C7467414](https://jlcpcb.com/partdetail/FOJAN-FRC0402F1150TS/C7467414) | [FRC0402F1150TS](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_fojan-frc0402f1150ts_C7467414.html) | FOJAN | 115 | extended | 1 | 12182 | 20 / 0.001 / 0.02 | 20 / 0.001 / 0.02 |
| [C270625](https://jlcpcb.com/partdetail/260005-0402WGF240JTCE/C270625) | [0402WGF240JTCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf240jtce_C270625.html) | UNI-ROYAL(Uniroyal Elec) | 24 | extended | 2 | 203664 | 20 / 0.0012 / 0.02 | 20 / 0.0012 / 0.02 |
| [C25765](https://jlcpcb.com/partdetail/26508-0402WGF2002TCE/C25765) | [0402WGF2002TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf2002tce_C25765.html) | UNI-ROYAL(Uniroyal Elec) | 20k | basic | 1 | 2917079 | 20 / 0.001 / 0.02 | 20 / 0.001 / 0.02 |
| [C25079](https://jlcpcb.com/partdetail/25822-0402WGF1200TCE/C25079) | [0402WGF1200TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf1200tce_C25079.html) | UNI-ROYAL(Uniroyal Elec) | 120 | basic | 2 | 3420195 | 20 / 0.0012 / 0.02 | 25 / 0.0012 / 0.03 |
| [C2998115](https://jlcpcb.com/partdetail/FOJAN-FRC0402F1911TS/C2998115) | [FRC0402F1911TS](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_fojan-frc0402f1911ts_C2998115.html) | FOJAN | 1.91k 1% | extended | 1 | 53093 | 20 / 0.0011 / 0.02 | 20 / 0.0011 / 0.02 |
| [C5159686](https://jlcpcb.com/partdetail/FOJAN-FRC0402F3831TS/C5159686) | [FRC0402F3831TS](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_fojan-frc0402f3831ts_C5159686.html) | FOJAN | 3.83k | extended | 2 | 34553 | 20 / 0.001 / 0.02 | 20 / 0.001 / 0.02 |
| [C3015726](https://jlcpcb.com/partdetail/VO-SCR0402F11R5/C3015726) | [SCR0402F11R5](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_vo-scr0402f11r5_C3015726.html) | VO | 11.5 | extended | 8 | 9218 | 26 / 0.0006 / 0.02 | 50 / 0.0006 / 0.03 |
| [C25741](https://jlcpcb.com/partdetail/26484-0402WGF1003TCE/C25741) | [0402WGF1003TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf1003tce_C25741.html) | UNI-ROYAL(Uniroyal Elec) | 100k | basic | 2 | 8515617 | 20 / 0.0011 / 0.02 | 22 / 0.0011 / 0.02 |
| [C122548](https://jlcpcb.com/partdetail/123817-0402WGF3322TCE/C122548) | [0402WGF3322TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf3322tce_C122548.html) | UNI-ROYAL(Uniroyal Elec) | 33.2k | extended | 1 | 615873 | 20 / 0.001 / 0.02 | 20 / 0.001 / 0.02 |
| [C11460](https://jlcpcb.com/partdetail/12014-0402WGF3091TCE/C11460) | [0402WGF3091TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf3091tce_C11460.html) | UNI-ROYAL(Uniroyal Elec) | 3.09k | extended | 1 | 10009 | 20 / 0.0009 / 0.02 | 20 / 0.0009 / 0.02 |
| [C25860](https://jlcpcb.com/partdetail/26603-0402WGF1101TCE/C25860) | [0402WGF1101TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf1101tce_C25860.html) | UNI-ROYAL(Uniroyal Elec) | 1.10k 1% | extended | 1 | 602604 | 20 / 0.0012 / 0.02 | 20 / 0.0012 / 0.02 |
| [C49653224](https://jlcpcb.com/partdetail/GiantOhm-GR0402F1K02TAG00/C49653224) | GR0402F1K02TAG00 | GiantOhm | 1.02k 1% | extended | 1 | 7777 | 20 / 0.0008 / 0.02 | 20 / 0.0008 / 0.02 |
| [C25882](https://jlcpcb.com/partdetail/26625-0402WGF2401TCE/C25882) | [0402WGF2401TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf2401tce_C25882.html) | UNI-ROYAL(Uniroyal Elec) | 2.4k | preferred | 1 | 699114 | 20 / 0.0012 / 0.02 | 20 / 0.0012 / 0.02 |
| [C25104](https://jlcpcb.com/partdetail/25847-0402WGF3300TCE/C25104) | [0402WGF3300TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf3300tce_C25104.html) | UNI-ROYAL(Uniroyal Elec) | 330 | basic | 1 | 1514472 | 20 / 0.0011 / 0.02 | 20 / 0.0011 / 0.02 |
| [C2933083](https://jlcpcb.com/partdetail/FOJAN-FRC0402F2491TS/C2933083) | [FRC0402F2491TS](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_fojan-frc0402f2491ts_C2933083.html) | FOJAN | 2.49k 1% | extended | 1 | 1747393 | 20 / 0.0012 / 0.02 | 20 / 0.0012 / 0.02 |
| [C25123](https://jlcpcb.com/partdetail/25866-0402WGF5100TCE/C25123) | [0402WGF5100TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf5100tce_C25123.html) | UNI-ROYAL(Uniroyal Elec) | 510 | basic | 2 | 2558428 | 20 / 0.0011 / 0.02 | 22 / 0.0011 / 0.02 |
| none |  |  | Si549 LVPECL 3V3 pinout C |  | 1 |  | 2 / — / — | 5 / — / — |
| | **Total** | | | | | | **1503.56** | **3602.84** |
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
| Kria KV260 | The host | Already bought |
| 12 V supply, ribbon to AERIS-10 | | See [SHOPPING_LIST.md](SHOPPING_LIST.md) |
