# JLCPCB order: quote

*10 November 2026, bare boards re-quoted on 8 layers on 12 November, parts, assembly and bare boards for the Ethernet option (140 × 132 mm) on 13 November, parts and assembly for Rev08 on 17 November, re-priced on 18 November and on 19 November for the single power entry · board CSI2-KRIA-KV260_Rev01 · not ordered yet*

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
| Assembly fees | 445.49 | 482.44 | JLCPCB's price page, §3 (17 Nov counts + 12 audit + 10 single-entry + 2 RJ45 shield RC feeders, +2 hand joints, +53 SMT joints, +2 X-ray parts) |
| Parts (209 LCSC codes, 19 Nov, single power entry + RJ45 shield RC) | 1,638.38 | 3,878.89 | JLCPCB's parts search, §4 |
| Si549 oscillator and TC1-1-13M+ balun, bought apart and consigned | ~45 `[E]` | ~110 `[E]` | No usable LCSC code, §5 |
| Shipping, UPS Express Saver, duties paid (DDP) | 26.08 | 26.08 | Quote page, for the bare boards' 0.50 kg; more for assembled ones |
| **Total** | **≈ 2,443** | **≈ 4,785** | |
| Per board | ≈ 1,221 | ≈ 957 | |

**Rev08 (17 November), re-priced with `lcsc_select.py` on live stock and `quote.py`:** 214 BOM lines, 739 parts, 212
lines with a code and 187 distinct codes (+72 since Rev06): the VHF/UHF front end, the 14 LEDs, the USB bridge and the
IAS0 receptacle. Parts rise by about $64 a board, most of it the RFFC5072 ($14.64), the two PE42442 and two SKY13418
switches, the SPF5043Z amplifiers, the PE4312 and the thirteenth SMA. **Feeder loading is now the largest assembly
fee, $286** (187 × $1.53), against $174 for Rev06: the front end's filters use many distinct C0G and wirewound values.
The rows below are the history of this quote.

**18 November, before the tag:** 219 lines, 751 parts, 217 lines with a code, 192 distinct codes. New: the HRO
TYPE-C-31-E-17 in place of the HX vertical USB-C (LAYOUT 6.8), the GPS PPS block (the XUNPU 15-way FPC receptacle,
the JST-SH header, an SN74LVC1G17, a 0.2 A PTC and seven passives). Five new codes add $7.65 of feeder loading. The parts
total is lower than on 17 November, by $52 for two boards, because the XC7A50T-2FTG256I's price fell overnight ($56.54 less for the
two boards' units); the new parts themselves cost about $1.50 a board. The 15-way FFC to the
KV260 is not assembled: it is on the shopping list.

**19 November (single power entry `KVPWR` + RJ45 shield RC):** 236 lines, 785 parts, 234 lines with a code, 209 distinct codes. Fifteen parts are added: thirteen on `KVPWR` (three reuse existing codes: `DMT10H015LFG-7` `C5245407` extended qty +1, `2N7002` `C8545` basic qty +1, `10u 25V 1206` `C13585` basic qty +1; ten add new codes: `ZEGMCM9070-501T` `C53154905` extended `$0.54` stock `1,400`, `TPS26631PWPR` `C2866319` extended `$5.52` **stock `0`** global sourcing/consignment, `SS34` `C8678` basic `$0.035`, `B2PS-VH` `C158007` extended `$0.152`, `316k` 0603 `C25814` extended, `24.9k` 0603 `C137761` extended, `30.9k` 0603 `C2930090` extended, `6.04k` 0603 `C25977` extended stock `85,053` `$0.0017` setting the `3.0 A` limit, `22n` 0603 `C21122` basic, `1u 100V` 1206 X7R `C13832` extended -> **4 basic / 9 extended** across the 13 `KVPWR` parts, 2 new basic / 8 new extended) plus two on `J1201`'s shield RC (`C1223` `1n 2kV` 1206 X7R `C23631` extended stock `1,130,950` `$0.0179`, and `R1218` `1M` 0603 1% `C22935` basic stock `5,150,785` `$0.0018`). Live quote rises over the 18 Nov audit total by **+$29.45** on parts (`$1,608.93 -> $1,638.38`; `+$53.68` for 5 boards) and **+$21.88** on assembly (12 new feeders `+$18.36`, `J1004` +2 hand joints `+$0.07`, ~53 SMT joints `+$0.17`, `U1010`/`Q1010` +2 X-ray `+$3.28`), shifting two boards by **+$51** (`≈ $2,392 -> ≈ $2,443`) and five boards by **+$77** (`≈ $4,708 -> ≈ $4,785`). The off-board `J1004`-to-`J12` jumper (`VHR-2N` + `2 × SVH-21T-P1.1`, 18 AWG, `5.5 × 2.5 mm` plug) and `5 A` fuse are on the [shopping list](SHOPPING_LIST.md).

**18 November, after the RF and power audit ([AUDIT_Rev08.md](AUDIT_Rev08.md)):** 224 lines, 770 parts, 222 lines with
a code, 199 distinct codes. New or changed: the TCAN3403DDFRQ1 (C35926232) for the TCAN330, the TPS563201DDCR (C116592)
for one TPS562201, the LP5907MFX-2.8 (C186700) for the -3.0, the mSMD200-24V PTC (C143954) for the 1.5 A one, the
LQW15AN24NG00D (C167472) of the new 300 MHz high-pass (its six other parts reuse codes already on the board), 3.24 k and 330 ohm
values. Parts rise by $8.56 for two boards, assembly by about $11 of feeder loading (7 new codes).

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
| Copper | 1 oz outer, 0.5 oz inner | n/a | n/a | n/a |
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

Counted on 17 November from the board file and the BOM (19 Nov single power entry + RJ45 shield RC add 12 feeders `+$18.36`, 2 hand joints on `J1004`, ~53 SMT joints and 2 X-ray parts `U1010`/`Q1010`, reflected in §1; Rev06: 1,930 joints, 85 by hand, 106 feeders, 14 X-ray parts; $265.73 and $290.51).

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
*Searched 2026-11-19 by `_work/fab/quote.py`; prices in USD, JLCPCB's tier for the quantity bought.*

| LCSC | Part | Maker | Value | Lib | Per board | Stock | Buy 2 / unit / cost | Buy 5 / unit / cost |
|---|---|---|---|---|---|---|---|---|
| [C33062043](https://jlcpcb.com/partdetail/MiniCircuits-M3SWA2_34DR/C33062043) | [M3SWA2-34DR+](https://lcsc.com/product-detail/rf-switches_mini-circuits-m3swa2-34dr_C33062043.html) | Mini-Circuits | M3SWA2-34DR+ | extended | 4 | **0** | 8 / 45.73 / 365.81 | 20 / 44.25 / 884.95 |
| [C514282](https://jlcpcb.com/partdetail/AnalogDevices-AD9253BCPZ125/C514282) | [AD9253BCPZ-125](https://www.lcsc.com/product-detail/analog-to-digital-converters-adc_analog-devices-ad9253bcpz-125_C514282.html) | Analog Devices | AD9253BCPZ-125 | extended | 1 | **0** | 2 / 97.31 / 194.62 | 5 / 97.31 / 486.54 |
| [C653480](https://jlcpcb.com/partdetail/AnalogDevices-AD9484BCPZ500/C653480) | [AD9484BCPZ-500](https://www.lcsc.com/product-detail/analog-to-digital-converters-adc_analog-devices-ad9484bcpz-500_C653480.html) | Analog Devices | AD9484BCPZ-500 | extended | 1 | **0** | 2 / 97.22 / 194.43 | 5 / 97.22 / 486.09 |
| [C578707](https://jlcpcb.com/partdetail/AnalogDevices-AD8352ACPZR7/C578707) | [AD8352ACPZ-R7](https://www.lcsc.com/product-detail/rf-amplifiers_analog-devices-ad8352acpz-r7_C578707.html) | Analog Devices | AD8352ACPZ | extended | 4 | **4** | 8 / 20.85 / 166.82 | 20 / 19.97 / 399.42 |
| [C2976033](https://jlcpcb.com/partdetail/AMDXILINX-XC7A50T2FTG256I/C2976033) | [XC7A50T-2FTG256I](https://www.lcsc.com/product-detail/programmable-logic-device-cplds-fpgas_amd-xilinx-xc7a50t-2ftg256i_C2976033.html) | AMD/XILINX | XC7A50T-2FTG256I | extended | 1 | 27 | 2 / 65.17 / 130.33 | 5 / 65.17 / 325.83 |
| [C5199907](https://jlcpcb.com/partdetail/Samtec-SMA_J_P_H_STEM1/C5199907) | [SMA-J-P-H-ST-EM1](https://www.lcsc.com/product-detail/coaxial-connectors-rf_samtec-sma-j-p-h-st-em1_C5199907.html) | Samtec | CLK_REF_IN / CLK_OUT / SDR_RX_A / AERIS_IF_A / AERIS_IF / SDR_RX_WB / SDR_TX_A / AERIS_TX_A / AERIS_TX / SDR_TX_WB / SDR_RX_C / SDR_TX_C / VU_ANT | extended | 13 | **16** | 26 / 4.769 / 123.98 | 65 / 4.366 / 283.78 |
| [C5223988](https://jlcpcb.com/partdetail/MiniCircuits-ADT2_1T/C5223988) | [ADT2-1T+](https://www.lcsc.com/product-detail/balun_mini-circuits-adt2-1t_C5223988.html) | Mini-Circuits | ADT2-1T+ | extended | 3 | **1** | 6 / 7.227 / 43.36 | 15 / 6.263 / 93.95 |
| [C578960](https://jlcpcb.com/partdetail/AnalogDevices-ADCLK948BCPZ/C578960) | [ADCLK948BCPZ](https://www.lcsc.com/product-detail/clock-buffers-drivers-distributors_analog-devices-adclk948bcpz_C578960.html) | Analog Devices | ADCLK948BCPZ | extended | 1 | **0** | 2 / 20.77 / 41.54 | 5 / 20.77 / 103.86 |
| [C653734](https://jlcpcb.com/partdetail/AnalogDevices-AD9708ARZ/C653734) | [AD9708ARZ](https://www.lcsc.com/product-detail/digital-to-analog-converters-dac_analog-devices-ad9708arz_C653734.html) | Analog Devices | AD9708AR | extended | 1 | **0** | 2 / 16.84 / 33.68 | 5 / 16.84 / 84.20 |
| [C3034742](https://jlcpcb.com/partdetail/Qorvo-RFFC5072TR13/C3034742) | [RFFC5072TR13](https://www.lcsc.com/product-detail/pre-ordered-chips_qorvo-rffc5072tr13_C3034742.html) | Qorvo | RFFC5072 | extended | 1 | 36 | 2 / 14.63 / 29.25 | 5 / 14.63 / 73.13 |
| [C653820](https://jlcpcb.com/partdetail/AnalogDevices-AD9767ASTZRL/C653820) | [AD9767ASTZRL](https://www.lcsc.com/product-detail/digital-to-analog-converters-dac_analog-devices-ad9767astzrl_C653820.html) | Analog Devices | AD9767ASTZ | extended | 1 | 169 | 2 / 14.55 / 29.10 | 5 / 14.55 / 72.76 |
| [C41359590](https://jlcpcb.com/partdetail/MicronTech-MT25QL128ABA1ESE0SIT/C41359590) | [MT25QL128ABA1ESE-0SIT](https://www.lcsc.com/product-detail/nor-flash_micron-tech-mt25ql128aba1ese-0sit_C41359590.html) | Micron Tech | MT25QL128ABA1ESE | extended | 1 | 74 | 2 / 12.96 / 25.93 | 5 / 12.96 / 64.82 |
| [C470913](https://jlcpcb.com/partdetail/pSemi-PE42442AZ/C470913) | [PE42442A-Z](https://www.lcsc.com/product-detail/rf-switches_psemi-pe42442a-z_C470913.html) | pSemi | PE42442 | extended | 2 | 245 | 4 / 4.957 / 19.83 | 10 / 4.264 / 42.64 |
| [C5245407](https://jlcpcb.com/partdetail/DiodesIncorporated-DMT10H015LFG7/C5245407) | [DMT10H015LFG-7](https://www.lcsc.com/product-detail/mosfets_diodes-incorporated-dmt10h015lfg-7_C5245407.html) | Diodes Incorporated | DMT10H015LFG | extended | 3 | 65 | 6 / 3.208 / 19.25 | 15 / 2.798 / 41.97 |
| [C544500](https://jlcpcb.com/partdetail/TexasInstruments-TPS7A8300RGRR/C544500) | [TPS7A8300RGRR](https://www.lcsc.com/product-detail/voltage-regulators-linear-low-drop-out-ldo-regulators_texas-instruments-tps7a8300rgrr_C544500.html) | Texas Instruments | TPS7A8300RGR | extended | 3 | 71 | 6 / 3.207 / 19.24 | 15 / 2.768 / 41.52 |
| [C470902](https://jlcpcb.com/partdetail/Qorvo-SPF5043Z/C470902) | [SPF5043Z](https://www.lcsc.com/product-detail/rf-amplifiers_qorvo-spf5043z_C470902.html) | Qorvo | SPF5043Z | extended | 2 | 5902 | 4 / 3.393 / 13.57 | 10 / 2.899 / 28.99 |
| [C2866319](https://jlcpcb.com/partdetail/TexasInstruments-TPS26631PWPR/C2866319) | [TPS26631PWPR](https://www.lcsc.com/product-detail/surge-protection-devices-spds_texas-instruments-tps26631pwpr_C2866319.html) | Texas Instruments | TPS26631PWPR | extended | 1 | **0** | 2 / 5.518 / 11.04 | 5 / 5.518 / 27.59 |
| [C2886897](https://jlcpcb.com/partdetail/ESwitch-TL3342F450QG/C2886897) | [TL3342F450QG](https://www.lcsc.com/product-detail/tactile-switches_e-switch-tl3342f450qg_C2886897.html) | E-Switch | PROG | extended | 1 | 27 | 13 / 0.7482 / 9.73 | 13 / 0.7482 / 9.73 |
| [C5219206](https://jlcpcb.com/partdetail/TexasInstruments-LM74502QDDFRQ1/C5219206) | [LM74502QDDFRQ1](https://www.lcsc.com/product-detail/power-distribution-switches_texas-instruments-lm74502qddfrq1_C5219206.html) | Texas Instruments | LM74502-Q1 | extended | 1 | **0** | 6 / 1.619 / 9.71 | 6 / 1.619 / 9.71 |
| [C470892](https://jlcpcb.com/partdetail/pSemi-PE425963/C470892) | [PE4259-63](https://www.lcsc.com/product-detail/rf-switches_psemi-pe4259-63_C470892.html) | pSemi | PE4259 | extended | 4 | 13691 | 8 / 1.187 / 9.50 | 20 / 1.064 / 21.28 |
| [C2878381](https://jlcpcb.com/partdetail/TexasInstruments-TMP1075DR/C2878381) | [TMP1075DR](https://www.lcsc.com/product-detail/temperature-sensors_texas-instruments-tmp1075dr_C2878381.html) | Texas Instruments | TMP1075DR | extended | 1 | **1** | 23 / 0.3962 / 9.11 | 23 / 0.3962 / 9.11 |
| [C4990147](https://jlcpcb.com/partdetail/MiniCircuits-HFCN_1000/C4990147) | [HFCN-1000+](https://www.lcsc.com/product-detail/ceramic-filters_mini-circuits-hfcn-1000_C4990147.html) | Mini-Circuits | HFCN-1000+ | extended | 1 | 302 | 2 / 3.078 / 6.16 | 5 / 3.078 / 15.39 |
| [C45783](https://jlcpcb.com/partdetail/46786-CL21A226MAQNNNE/C45783) | [CL21A226MAQNNNE](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_samsung-electro-mechanics-cl21a226maqnnne_C45783.html) | Samsung Electro-Mechanics | 22u 10V | basic | 13 | 3626525 | 30 / 0.1975 / 5.93 | 69 / 0.1975 / 13.63 |
| [C2904132](https://jlcpcb.com/partdetail/RealtekSemicon-RTL8211FSICG/C2904132) | [RTL8211FSI-CG](https://www.lcsc.com/product-detail/ethernet-transceivers_realtek-semicon-rtl8211fsi-cg_C2904132.html) | Realtek Semicon | RTL8211FSI-CG | extended | 1 | 4359 | 2 / 2.87 / 5.74 | 5 / 2.87 / 14.35 |
| [C50933](https://jlcpcb.com/partdetail/51945-HR911130C/C50933) | [HR911130C](https://www.lcsc.com/product-detail/ethernet-connectors-modular-connectors-rj45-rj11_hanrun-zhongshan-hanrun-elec-hr911130c_C50933.html) | HANRUN(Zhongshan HanRun Elec) | HR911130C | extended | 1 | 6171 | 2 / 2.86 / 5.72 | 5 / 2.86 / 14.30 |
| [C500480](https://jlcpcb.com/partdetail/pSemi-PE4312CZ/C500480) | [PE4312C-Z](https://www.lcsc.com/product-detail/rf-attenuators_psemi-pe4312c-z_C500480.html) | pSemi | PE4312 | extended | 1 | 1497 | 2 / 2.839 / 5.68 | 5 / 2.839 / 14.19 |
| [C5476329](https://jlcpcb.com/partdetail/WurthElektronik-150040VS73240/C5476329) | [150040VS73240](https://www.lcsc.com/product-detail/light-emitting-diodes-led_wurth-elektronik-150040vs73240_C5476329.html) | Wurth Elektronik | CFG green / LINK green / LO green / +12V green / +5V0 green / +3V3_D green / +1V8_D green / +1V0 green | extended | 8 | 379 | 16 / 0.316 / 5.06 | 40 / 0.28 / 11.20 |
| [C544380](https://jlcpcb.com/partdetail/TexasInstruments-LM2663MNOPB/C544380) | [LM2663M/NOPB](https://www.lcsc.com/product-detail/dc-dc-converters_texas-instruments-lm2663m-nopb_C544380.html) | Texas Instruments | LM2663M | extended | 1 | 5795 | 2 / 2.392 / 4.78 | 5 / 2.392 / 11.96 |
| [C20415295](https://jlcpcb.com/partdetail/TST-TA1090EC/C20415295) | TA1090EC | TST | TA1090EC | extended | 1 | 149 | 2 / 2.166 / 4.33 | 5 / 2.166 / 10.83 |
| [C879868](https://jlcpcb.com/partdetail/MiniCircuits-LFCN_1000/C879868) | [LFCN-1000+](https://www.lcsc.com/product-detail/rf-filters_mini-circuits-lfcn-1000_C879868.html) | Mini-Circuits | LFCN-1000+ | extended | 1 | 456 | 2 / 2.071 / 4.14 | 5 / 2.071 / 10.35 |
| [C150871](https://jlcpcb.com/partdetail/SkyworksSolutions-SKY13418485LF/C150871) | [SKY13418-485LF](https://www.lcsc.com/product-detail/rf-switches_skyworks-solutions-sky13418-485lf_C150871.html) | Skyworks Solutions | SKY13418-485LF | extended | 2 | 4200 | 4 / 1.025 / 4.10 | 10 / 0.8398 / 8.40 |
| [C2041815](https://jlcpcb.com/partdetail/BOURNS-SRP7028A8R2M/C2041815) | [SRP7028A-8R2M](https://www.lcsc.com/product-detail/power-inductors_bourns-srp7028a-8r2m_C2041815.html) | BOURNS | SRP7028A-8R2M | extended | 1 | 201 | 2 / 1.822 / 3.64 | 5 / 1.822 / 9.11 |
| [C879855](https://jlcpcb.com/partdetail/MiniCircuits-TC4_1W/C879855) | [TC4-1W+](https://www.lcsc.com/product-detail/rf-misc-ics-and-modules_mini-circuits-tc4-1w_C879855.html) | Mini-Circuits | TC4-1W+ | extended | 1 | 2142 | 2 / 1.706 / 3.41 | 5 / 1.706 / 8.53 |
| [C182336](https://jlcpcb.com/partdetail/TexasInstruments-TCA6416ARTWR/C182336) | [TCA6416ARTWR](https://www.lcsc.com/product-detail/i-o-expanders_texas-instruments-tca6416artwr_C182336.html) | Texas Instruments | TCA6416ARTWR | extended | 2 | 32351 | 4 / 0.8202 / 3.28 | 10 / 0.6728 / 6.73 |
| [C45961](https://jlcpcb.com/partdetail/Nexperia-PESD5V0F1BL315/C45961) | [PESD5V0F1BL,315](https://www.lcsc.com/product-detail/esd-and-surge-protection-tvs-esd_nexperia-pesd5v0f1bl-315_C45961.html) | Nexperia | PESD5V0F1BL | extended | 14 | 127276 | 36 / 0.0842 / 3.03 | 78 / 0.0662 / 5.16 |
| [C7424785](https://jlcpcb.com/partdetail/Korean_HropartsElec-TYPE_C_31_E17/C7424785) | [TYPE-C-31-E-17](https://www.lcsc.com/product-detail/usb-connectors_korean-hroparts-elec-type-c-31-e-17_C7424785.html) | Korean Hroparts Elec | TYPE-C-31-E-17 | extended | 1 | 1032 | 2 / 1.427 / 2.85 | 5 / 1.427 / 7.14 |
| [C492354](https://jlcpcb.com/partdetail/MOLEX-878321420/C492354) | [878321420](https://www.lcsc.com/product-detail/wire-to-board-connector_molex-878321420_C492354.html) | MOLEX | JTAG 2x7 2mm | extended | 1 | 2901 | 2 / 1.401 / 2.80 | 5 / 1.401 / 7.01 |
| [C35926232](https://jlcpcb.com/partdetail/TexasInstruments-TCAN3403DDFRQ1/C35926232) | [TCAN3403DDFRQ1](https://www.lcsc.com/product-detail/can-transceivers_texas-instruments-tcan3403ddfrq1_C35926232.html) | Texas Instruments | TCAN3403DDFRQ1 | extended | 1 | 858 | 2 / 1.324 / 2.65 | 5 / 1.324 / 6.62 |
| [C77101](https://jlcpcb.com/partdetail/MurataElectronics-GRM32ER61C476KE15L/C77101) | [GRM32ER61C476KE15L](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_murata-electronics-grm32er61c476ke15l_C77101.html) | Murata Electronics | 47u | extended | 5 | 79115 | 12 / 0.2161 / 2.59 | 27 / 0.2161 / 5.83 |
| [C136150](https://jlcpcb.com/partdetail/KEMET-T520V337M006ATE025/C136150) | [T520V337M006ATE025](https://www.lcsc.com/product-detail/tantalum-capacitors_kemet-t520v337m006ate025_C136150.html) | KEMET | 330u | extended | 1 | 1419 | 2 / 1.278 / 2.56 | 5 / 1.278 / 6.39 |
| [C913186](https://jlcpcb.com/partdetail/BOURNS-SRP7028A3R3M/C913186) | [SRP7028A-3R3M](https://www.lcsc.com/product-detail/power-inductors_bourns-srp7028a-3r3m_C913186.html) | BOURNS | SRP7028A-3R3M | extended | 2 | 1022 | 4 / 0.5926 / 2.37 | 10 / 0.4715 / 4.71 |
| [C186700](https://jlcpcb.com/partdetail/TexasInstruments-LP5907MFX_2_8NOPB/C186700) | [LP5907MFX-2.8/NOPB](https://www.lcsc.com/product-detail/voltage-regulators-linear-low-drop-out-ldo-regulators_texas-instruments-lp5907mfx-2-8-nopb_C186700.html) | Texas Instruments | LP5907MFX-2.8 | extended | 1 | 612 | 5 / 0.4617 / 2.31 | 5 / 0.4617 / 2.31 |
| [C3096093](https://jlcpcb.com/partdetail/CUI-PJ102AH/C3096093) | [PJ-102AH](https://www.lcsc.com/product-detail/dc-power-connectors_cui-pj-102ah_C3096093.html) | CUI | 12V IN | extended | 1 | 1682 | 2 / 1.075 / 2.15 | 5 / 1.075 / 5.38 |
| [C146656](https://jlcpcb.com/partdetail/157988-B_3100S40PA110/C146656) | [B-3100S40P-A110](https://www.lcsc.com/product-detail/idc-connectors_ckmtw-shenzhen-cankemeng-b-3100s40p-a110_C146656.html) | Ckmtw(Shenzhen Cankemeng) | AERIS ADAR | extended | 1 | 1150 | 2 / 0.8415 / 1.68 | 5 / 0.8415 / 4.21 |
| [C2158038](https://jlcpcb.com/partdetail/DiodesIncorporated-AP22652W67/C2158038) | [AP22652W6-7](https://www.lcsc.com/product-detail/power-distribution-switches_diodes-incorporated-ap22652w6-7_C2158038.html) | Diodes Incorporated | AP22652W6-7 | extended | 1 | 8442 | 5 / 0.3317 / 1.66 | 5 / 0.3317 / 1.66 |
| [C15850](https://jlcpcb.com/partdetail/16532-CL21A106KAYNNNE/C15850) | [CL21A106KAYNNNE](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_samsung-electro-mechanics-cl21a106kaynnne_C15850.html) | Samsung Electro-Mechanics | 10u / 10u 10V | basic | 21 | 8580560 | 52 / 0.0312 / 1.62 | 115 / 0.0312 / 3.59 |
| [C7432791](https://jlcpcb.com/partdetail/Chinocera-HGC1210R5476M250NSVK/C7432791) | [HGC1210R5476M250NSVK](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_chinocera-hgc1210r5476m250nsvk_C7432791.html) | Chinocera | 47u 25V | extended | 1 | 72648 | 5 / 0.3096 / 1.55 | 5 / 0.3096 / 1.55 |
| [C424540](https://jlcpcb.com/partdetail/HRS_Hirose-BM20B_0_8_34DP_0_4V_51/C424540) | [BM20B(0.8)-34DP-0.4V(51)](https://www.lcsc.com/product-detail/board-to-board-and-backplane-connector_hrs-hirose-bm20b-0-8-34dp-0-4v-51_C424540.html) | HRS(Hirose) | BM20B(0.8)-34DP | extended | 2 | 12985 | 6 / 0.2217 / 1.33 | 12 / 0.2217 / 2.66 |
| [C3035748](https://jlcpcb.com/partdetail/WCH_Jiangsu_Qin_Heng-CH340X/C3035748) | [CH340X](https://www.lcsc.com/product-detail/usb-converters_wch-jiangsu-qin-heng-ch340x_C3035748.html) | WCH(Jiangsu Qin Heng) | CH340X | extended | 1 | 33244 | 2 / 0.663 / 1.33 | 5 / 0.663 / 3.32 |
| [C96123](https://jlcpcb.com/partdetail/97327-CL31A476MPHNNNE/C96123) | [CL31A476MPHNNNE](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_samsung-electro-mechanics-cl31a476mphnnne_C96123.html) | Samsung Electro-Mechanics | 47u | basic | 2 | 440275 | 8 / 0.1629 / 1.30 | 14 / 0.1629 / 2.28 |
| [C98092](https://jlcpcb.com/partdetail/MurataElectronics-LQW18ANR27G00D/C98092) | [LQW18ANR27G00D](https://www.lcsc.com/product-detail/power-inductors_murata-electronics-lqw18anr27g00d_C98092.html) | Murata Electronics | 270n | extended | 12 | 8690 | 28 / 0.0464 / 1.30 | 64 / 0.0464 / 2.97 |
| [C841384](https://jlcpcb.com/partdetail/TexasInstruments-LMR33630ADDAR/C841384) | [LMR33630ADDAR](https://www.lcsc.com/product-detail/dc-dc-converters_texas-instruments-lmr33630addar_C841384.html) | Texas Instruments | LMR33630ADDA | extended | 1 | 25067 | 2 / 0.6319 / 1.26 | 5 / 0.6319 / 3.16 |
| [C167487](https://jlcpcb.com/partdetail/MurataElectronics-LQW15AN82NG00D/C167487) | [LQW15AN82NG00D](https://www.lcsc.com/product-detail/power-inductors_murata-electronics-lqw15an82ng00d_C167487.html) | Murata Electronics | 82n | extended | 1 | 5317 | 20 / 0.0627 / 1.25 | 20 / 0.0627 / 1.25 |
| [C1779](https://jlcpcb.com/partdetail/2131-CL21A475KAQNNNE/C1779) | [CL21A475KAQNNNE](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_samsung-electro-mechanics-cl21a475kaqnnne_C1779.html) | Samsung Electro-Mechanics | 4.7u | basic | 13 | 1880127 | 36 / 0.0343 / 1.23 | 75 / 0.0343 / 2.57 |
| [C49066](https://jlcpcb.com/partdetail/50074-CL32A107MQVNNNE/C49066) | [CL32A107MQVNNNE](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_samsung-electro-mechanics-cl32a107mqvnnne_C49066.html) | Samsung Electro-Mechanics | 100u | extended | 1 | 144383 | 5 / 0.2469 / 1.23 | 7 / 0.2469 / 1.73 |
| [C135223](https://jlcpcb.com/partdetail/KDSDaishinku-1XXD26000MAA/C135223) | [1XXD26000MAA](https://www.lcsc.com/product-detail/temperature-compensated-crystal-oscillators-tcxo_kds-daishinku-1xxd26000maa_C135223.html) | KDS Daishinku | 26MHz 1XXD26000MAA | extended | 1 | 15655 | 2 / 0.6106 / 1.22 | 5 / 0.6106 / 3.05 |
| [C1329579](https://jlcpcb.com/partdetail/BOURNS-SRP7028A2R2M/C1329579) | [SRP7028A-2R2M](https://www.lcsc.com/product-detail/power-inductors_bourns-srp7028a-2r2m_C1329579.html) | BOURNS | SRP7028A-2R2M | extended | 1 | 919 | 2 / 0.5599 / 1.12 | 5 / 0.5599 / 2.80 |
| [C53154905](https://jlcpcb.com/partdetail/ZE-ZEGMCM9070501T/C53154905) | ZEGMCM9070-501T | ZE | ZEGMCM9070-501T | extended | 1 | 1400 | 2 / 0.5353 / 1.07 | 5 / 0.5353 / 2.68 |
| [C86129](https://jlcpcb.com/partdetail/MurataElectronics-LQW15AN22NG00D/C86129) | [LQW15AN22NG00D](https://www.lcsc.com/product-detail/power-inductors_murata-electronics-lqw15an22ng00d_C86129.html) | Murata Electronics | 22n | extended | 3 | 29931 | 20 / 0.0518 / 1.04 | 23 / 0.0518 / 1.19 |
| [C2049745](https://jlcpcb.com/partdetail/2141314-DFE201210U_2R2MP2/C2049745) | [DFE201210U-2R2M=P2](https://www.lcsc.com/product-detail/power-inductors_murata-electronics-dfe201210u-2r2m-p2_C2049745.html) | Murata Electronics | 2.2u | extended | 1 | 13808 | 5 / 0.2001 / 1.00 | 5 / 0.2001 / 1.00 |
| [C13585](https://jlcpcb.com/partdetail/14236-CL31A106KBHNNNE/C13585) | [CL31A106KBHNNNE](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_samsung-electro-mechanics-cl31a106kbhnnne_C13585.html) | Samsung Electro-Mechanics | 10u 25V | basic | 2 | 4161599 | 8 / 0.121 / 0.97 | 14 / 0.121 / 1.69 |
| [C13832](https://jlcpcb.com/partdetail/14487-CL31B105KCHNNNE/C13832) | [CL31B105KCHNNNE](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_samsung-electro-mechanics-cl31b105kchnnne_C13832.html) | Samsung Electro-Mechanics | 1u 100V | extended | 1 | 247743 | 15 / 0.0627 / 0.94 | 15 / 0.0627 / 0.94 |
| [C80670](https://jlcpcb.com/partdetail/TexasInstruments-LP5907MFX_3_3NOPB/C80670) | [LP5907MFX-3.3/NOPB](https://www.lcsc.com/product-detail/voltage-regulators-linear-low-drop-out-ldo-regulators_texas-instruments-lp5907mfx-3-3-nopb_C80670.html) | Texas Instruments | LP5907MFX-3.3 | extended | 1 | 25871 | 5 / 0.165 / 0.83 | 7 / 0.165 / 1.16 |
| [C424541](https://jlcpcb.com/partdetail/HRS_Hirose-BM20B_0_8_34DS_0_4V_51/C424541) | [BM20B(0.8)-34DS-0.4V(51)](https://www.lcsc.com/product-detail/board-to-board-and-backplane-connector_hrs-hirose-bm20b-0-8-34ds-0-4v-51_C424541.html) | HRS(Hirose) | BM20B(0.8)-34DS-0.4V(51) | extended | 1 | 18610 | 4 / 0.185 / 0.74 | 7 / 0.185 / 1.29 |
| [C1525](https://jlcpcb.com/partdetail/1877-CL05B104KO5NNNC/C1525) | [CL05B104KO5NNNC](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_samsung-electro-mechanics-cl05b104ko5nnnc_C1525.html) | Samsung Electro-Mechanics | 100n | basic | 143 | 34579451 | 301 / 0.0024 / 0.72 | 730 / 0.0024 / 1.75 |
| [C333860](https://jlcpcb.com/partdetail/MurataElectronics-LQW2BAS1R0J00L/C333860) | [LQW2BAS1R0J00L](https://www.lcsc.com/product-detail/power-inductors_murata-electronics-lqw2bas1r0j00l_C333860.html) | Murata Electronics | 1u | extended | 1 | 2956 | 5 / 0.1413 / 0.71 | 5 / 0.1413 / 0.71 |
| [C160392](https://jlcpcb.com/partdetail/JST-BM06B_SRSS_TB_LF_SN/C160392) | [BM06B-SRSS-TB(LF)(SN)](https://www.lcsc.com/product-detail/wire-to-board-connector_jst-bm06b-srss-tb-lf-sn_C160392.html) | JST | BM06B-SRSS-TB | extended | 1 | 31052 | 2 / 0.3518 / 0.70 | 5 / 0.3518 / 1.76 |
| [C337958](https://jlcpcb.com/partdetail/MurataElectronics-LQW2BASR22J00L/C337958) | [LQW2BASR22J00L](https://www.lcsc.com/product-detail/power-inductors_murata-electronics-lqw2basr22j00l_C337958.html) | Murata Electronics | 220n | extended | 1 | 7145 | 5 / 0.1376 / 0.69 | 7 / 0.1376 / 0.96 |
| [C2228109](https://jlcpcb.com/partdetail/YAGEO-CQ0402ARNPO9BNR40/C2228109) | [CQ0402ARNPO9BNR40](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cq0402arnpo9bnr40_C2228109.html) | YAGEO | 0.4p | extended | 1 | 2625 | 20 / 0.031 / 0.62 | 20 / 0.031 / 0.62 |
| [C516070](https://jlcpcb.com/partdetail/531919-JK_SMD0805_02030V/C516070) | [JK-SMD0805-020-30V](https://www.lcsc.com/product-detail/resettable-fuses_jinrui-electronic-materials-co-jk-smd0805-020-30v_C516070.html) | Jinrui Electronic Materials Co. | PTC 0.2A hold | extended | 1 | 359354 | 20 / 0.0312 / 0.62 | 20 / 0.0312 / 0.62 |
| [C703717](https://jlcpcb.com/partdetail/MurataElectronics-LQW2BASR33G00L/C703717) | [LQW2BASR33G00L](https://www.lcsc.com/product-detail/power-inductors_murata-electronics-lqw2basr33g00l_C703717.html) | Murata Electronics | 330n | extended | 1 | 2739 | 5 / 0.1218 / 0.61 | 7 / 0.1218 / 0.85 |
| [C2041663](https://jlcpcb.com/partdetail/MurataElectronics-LQW15AN27NG8ZD/C2041663) | [LQW15AN27NG8ZD](https://www.lcsc.com/product-detail/power-inductors_murata-electronics-lqw15an27ng8zd_C2041663.html) | Murata Electronics | 27n | extended | 1 | 20701 | 5 / 0.1156 / 0.58 | 7 / 0.1156 / 0.81 |
| [C86130](https://jlcpcb.com/partdetail/MurataElectronics-LQW15ANR10J00D/C86130) | [LQW15ANR10J00D](https://www.lcsc.com/product-detail/power-inductors_murata-electronics-lqw15anr10j00d_C86130.html) | Murata Electronics | 100n | extended | 1 | 7526 | 6 / 0.0965 / 0.58 | 9 / 0.0965 / 0.87 |
| [C22390021](https://jlcpcb.com/partdetail/DOWO-TPD4E05U06DQAR/C22390021) | [TPD4E05U06DQAR](https://www.lcsc.com/product-detail/esd-and-surge-protection-tvs-esd_dowo-tpd4e05u06dqar_C22390021.html) | DOWO | TPD4E05U06DQAR | extended | 3 | 80819 | 20 / 0.0289 / 0.58 | 21 / 0.0289 / 0.61 |
| [C1623](https://jlcpcb.com/partdetail/1975-CL10B474KA8NNNC/C1623) | [CL10B474KA8NNNC](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_samsung-electro-mechanics-cl10b474ka8nnnc_C1623.html) | Samsung Electro-Mechanics | 0.47u / 470n | basic | 26 | 1327113 | 62 / 0.0092 / 0.57 | 140 / 0.0092 / 1.29 |
| [C9006](https://jlcpcb.com/partdetail/YXC_CrystalOscillators-X322525MOB4SI/C9006) | [X322525MOB4SI](https://www.lcsc.com/product-detail/crystals_yxc-crystal-oscillators-x322525mob4si_C9006.html) | YXC Crystal Oscillators | 25MHz | basic | 1 | 401525 | 6 / 0.0952 / 0.57 | 9 / 0.0952 / 0.86 |
| [C1855147](https://jlcpcb.com/partdetail/YAGEO-CQ0402ARNPO0BNR30/C1855147) | [CQ0402ARNPO0BNR30](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cq0402arnpo0bnr30_C1855147.html) | YAGEO | 0.3p | extended | 2 | 6888 | 20 / 0.028 / 0.56 | 20 / 0.028 / 0.56 |
| [C7829](https://jlcpcb.com/partdetail/TexasInstruments-SN74LVC1G07DBVR/C7829) | [SN74LVC1G07DBVR](https://www.lcsc.com/product-detail/buffers-drivers-receivers-transceivers_texas-instruments-sn74lvc1g07dbvr_C7829.html) | Texas Instruments | 74LVC1G07 | extended | 1 | 31104 | 6 / 0.0932 / 0.56 | 9 / 0.0932 / 0.84 |
| [C343993](https://jlcpcb.com/partdetail/BORN-PESD1CAN/C343993) | [PESD1CAN](https://www.lcsc.com/product-detail/esd-and-surge-protection-tvs-esd_born-pesd1can_C343993.html) | BORN | PESD1CAN | extended | 1 | 136981 | 6 / 0.0893 / 0.54 | 9 / 0.0893 / 0.80 |
| [C370392](https://jlcpcb.com/partdetail/Sunlord-SDWL2012CR27GSTF/C370392) | [SDWL2012CR27GSTF](https://www.lcsc.com/product-detail/inductors-smd_sunlord-sdwl2012cr27gstf_C370392.html) | Sunlord | 270n | extended | 1 | 949 | 5 / 0.1081 / 0.54 | 7 / 0.1081 / 0.76 |
| [C326067](https://jlcpcb.com/partdetail/YAGEO-CQ0402ARNPO9BNR20/C326067) | [CQ0402ARNPO9BNR20](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cq0402arnpo9bnr20_C326067.html) | YAGEO | 0.2p | extended | 1 | 3626 | 20 / 0.0267 / 0.53 | 20 / 0.0267 / 0.53 |
| [C143954](https://jlcpcb.com/partdetail/TECHFUSE-mSMD20024V/C143954) | [mSMD200-24V](https://www.lcsc.com/product-detail/resettable-fuses_techfuse-msmd200-24v_C143954.html) | TECHFUSE | PTC 2A hold | extended | 1 | 2100 | 5 / 0.0994 / 0.50 | 7 / 0.0994 / 0.70 |
| [C577389](https://jlcpcb.com/partdetail/YAGEO-CQ0402BRNPO9BNR60/C577389) | [CQ0402BRNPO9BNR60](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cq0402brnpo9bnr60_C577389.html) | YAGEO | 0.6p | extended | 1 | 28169 | 20 / 0.0241 / 0.48 | 20 / 0.0241 / 0.48 |
| [C158007](https://jlcpcb.com/partdetail/JST-B2PS_VH_LF_SN/C158007) | [B2PS-VH(LF)(SN)](https://www.lcsc.com/product-detail/wire-to-board-connector_jst-b2ps-vh-lf-sn_C158007.html) | JST | B2PS-VH | extended | 1 | 44818 | 3 / 0.152 / 0.46 | 6 / 0.152 / 0.91 |
| [C43379](https://jlcpcb.com/partdetail/44370-SMD1206P050TF_132/C43379) | [SMD1206P050TF/13.2](https://www.lcsc.com/product-detail/resettable-fuses_ruilon-shenzhen-ruilongyuan-elec-smd1206p050tf-13-2_C43379.html) | RUILON(Shenzhen Ruilongyuan Elec) | PTC 0.5A hold | extended | 1 | 12885 | 5 / 0.0901 / 0.45 | 7 / 0.0901 / 0.63 |
| [C90061](https://jlcpcb.com/partdetail/TexasInstruments-TPS562201DDCR/C90061) | [TPS562201DDCR](https://www.lcsc.com/product-detail/dc-dc-converters_texas-instruments-tps562201ddcr_C90061.html) | Texas Instruments | TPS562201 | extended | 2 | 467651 | 8 / 0.0565 / 0.45 | 14 / 0.0565 / 0.79 |
| [C434447](https://jlcpcb.com/partdetail/YongyuPhotoelectric-SZYY0402B/C434447) | [SZYY0402B](https://www.lcsc.com/product-detail/led-indication-discrete_yongyu-photoelectric-szyy0402b_C434447.html) | Yongyu Photoelectric | HB blue | extended | 1 | 479226 | 20 / 0.0215 / 0.43 | 20 / 0.0215 / 0.43 |
| [C341787](https://jlcpcb.com/partdetail/MurataElectronics-LQW15AN75NG00D/C341787) | [LQW15AN75NG00D](https://www.lcsc.com/product-detail/power-inductors_murata-electronics-lqw15an75ng00d_C341787.html) | Murata Electronics | 75n | extended | 1 | 10694 | 6 / 0.0716 / 0.43 | 9 / 0.0716 / 0.64 |
| [C167472](https://jlcpcb.com/partdetail/MurataElectronics-LQW15AN24NG00D/C167472) | [LQW15AN24NG00D](https://www.lcsc.com/product-detail/power-inductors_murata-electronics-lqw15an24ng00d_C167472.html) | Murata Electronics | 24n | extended | 1 | 18760 | 6 / 0.069 / 0.41 | 9 / 0.069 / 0.62 |
| [C108965](https://jlcpcb.com/partdetail/MurataElectronics-LQW15AN68NG00D/C108965) | [LQW15AN68NG00D](https://www.lcsc.com/product-detail/power-inductors_murata-electronics-lqw15an68ng00d_C108965.html) | Murata Electronics | 68n | extended | 1 | 20176 | 6 / 0.0659 / 0.40 | 9 / 0.0659 / 0.59 |
| [C116592](https://jlcpcb.com/partdetail/TexasInstruments-TPS563201DDCR/C116592) | [TPS563201DDCR](https://www.lcsc.com/product-detail/dc-dc-converters_texas-instruments-tps563201ddcr_C116592.html) | Texas Instruments | TPS563201 | extended | 1 | 117588 | 6 / 0.0662 / 0.40 | 9 / 0.0662 / 0.60 |
| [C21516](https://jlcpcb.com/partdetail/MurataElectronics-BLM15HD102SN1D/C21516) | [BLM15HD102SN1D](https://www.lcsc.com/product-detail/ferrite-beads_murata-electronics-blm15hd102sn1d_C21516.html) | Murata Electronics | BLM15HD102SN1 | extended | 2 | 67567 | 20 / 0.0195 / 0.39 | 20 / 0.0195 / 0.39 |
| [C310048](https://jlcpcb.com/partdetail/Brightking-SMCJ33CATR13/C310048) | [SMCJ33CA/TR13](https://www.lcsc.com/product-detail/esd-and-surge-protection-tvs-esd_brightking-smcj33ca-tr13_C310048.html) | Brightking | SMCJ33CA | extended | 1 | 92658 | 3 / 0.1266 / 0.38 | 6 / 0.1266 / 0.76 |
| [C19269358](https://jlcpcb.com/partdetail/XUNPU-FPC_1_0FX_15PWCRH20/C19269358) | [FPC-1.0FX-15PWCR-H20](https://www.lcsc.com/product-detail/ffc-fpc-flat-flexible-connector-assemblies_xunpu-fpc-1-0fx-15pwcr-h20_C19269358.html) | XUNPU | FPC-1.0FX-15PWCR-H20 | extended | 1 | 3573 | 2 / 0.1919 / 0.38 | 5 / 0.1919 / 0.96 |
| [C19829631](https://jlcpcb.com/partdetail/TECHPUBLIC-SN74LVC1G17DCKR/C19829631) | [SN74LVC1G17DCKR](https://www.lcsc.com/product-detail/logic-gates_tech-public-sn74lvc1g17dckr_C19829631.html) | TECH PUBLIC | SN74LVC1G17DCKR | extended | 1 | 19187 | 10 / 0.0375 / 0.38 | 10 / 0.0375 / 0.38 |
| [C8678](https://jlcpcb.com/partdetail/MDD_Microdiode_Semiconductor-SS34/C8678) | [SS34](https://www.lcsc.com/product-detail/schottky-diodes_mdd-microdiode-semiconductor-ss34_C8678.html) | MDD(Microdiode Semiconductor) | SS34 | basic | 1 | 2523304 | 10 / 0.0351 / 0.35 | 13 / 0.0351 / 0.46 |
| [C6364703](https://jlcpcb.com/partdetail/APV-AHW1608F1R0KTF/C6364703) | [AHW1608F-1R0KTF](https://www.lcsc.com/product-detail/inductors-smd_apv-ahw1608f-1r0ktf_C6364703.html) | APV | 1u | extended | 2 | 27488 | 8 / 0.0418 / 0.33 | 14 / 0.0418 / 0.59 |
| [C78413](https://jlcpcb.com/partdetail/Brightking-SMBJ18CATR13/C78413) | [SMBJ18CA/TR13](https://www.lcsc.com/product-detail/esd-and-surge-protection-tvs-esd_brightking-smbj18ca-tr13_C78413.html) | Brightking | SMBJ18CA | extended | 1 | 479678 | 6 / 0.0541 / 0.32 | 9 / 0.0541 / 0.49 |
| [C113110](https://jlcpcb.com/partdetail/MurataElectronics-LQW15AN16NG00D/C113110) | [LQW15AN16NG00D](https://www.lcsc.com/product-detail/power-inductors_murata-electronics-lqw15an16ng00d_C113110.html) | Murata Electronics | 16n | extended | 2 | 12374 | 8 / 0.0406 / 0.32 | 14 / 0.0406 / 0.57 |
| [C86139](https://jlcpcb.com/partdetail/MurataElectronics-LQW18ANR22G00D/C86139) | [LQW18ANR22G00D](https://www.lcsc.com/product-detail/power-inductors_murata-electronics-lqw18anr22g00d_C86139.html) | Murata Electronics | 220n | extended | 1 | 36811 | 6 / 0.0498 / 0.30 | 9 / 0.0498 / 0.45 |
| [C98095](https://jlcpcb.com/partdetail/MurataElectronics-LQW18ANR39G00D/C98095) | [LQW18ANR39G00D](https://www.lcsc.com/product-detail/inductors-smd_murata-electronics-lqw18anr39g00d_C98095.html) | Murata Electronics | 390n | extended | 1 | 2513 | 6 / 0.0495 / 0.30 | 9 / 0.0495 / 0.45 |
| [C19077423](https://jlcpcb.com/partdetail/hongjiacheng-MMSZ5232B/C19077423) | [MMSZ5232B](https://www.lcsc.com/product-detail/zener-diodes_hongjiacheng-mmsz5232b_C19077423.html) | hongjiacheng | 5.6V | preferred | 8 | 37733 | 20 / 0.0145 / 0.29 | 44 / 0.0145 / 0.64 |
| [C114502](https://jlcpcb.com/partdetail/STMicroelectronics-M24C02FMN6TP/C114502) | [M24C02-FMN6TP](https://www.lcsc.com/product-detail/eeprom_stmicroelectronics-m24c02-fmn6tp_C114502.html) | STMicroelectronics | M24C02-FMN6TP | extended | 1 | 13645 | 2 / 0.1423 / 0.28 | 5 / 0.1423 / 0.71 |
| [C167482](https://jlcpcb.com/partdetail/MurataElectronics-LQW15AN56NG00D/C167482) | [LQW15AN56NG00D](https://www.lcsc.com/product-detail/power-inductors_murata-electronics-lqw15an56ng00d_C167482.html) | Murata Electronics | 56n | extended | 1 | 12655 | 6 / 0.0451 / 0.27 | 9 / 0.0451 / 0.41 |
| [C2827654](https://jlcpcb.com/partdetail/TECHPUBLIC-USBLC62SC6/C2827654) | [USBLC6-2SC6](https://www.lcsc.com/product-detail/esd-and-surge-protection-tvs-esd_tech-public-usblc6-2sc6_C2827654.html) | TECH PUBLIC | USBLC6-2SC6 | extended | 1 | 203833 | 6 / 0.0449 / 0.27 | 9 / 0.0449 / 0.40 |
| [C23631](https://jlcpcb.com/partdetail/YAGEO-CC1206KKX7RDBB102/C23631) | [CC1206KKX7RDBB102](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc1206kkx7rdbb102_C23631.html) | YAGEO | 1n 2kV | extended | 1 | 1130950 | 15 / 0.0179 / 0.27 | 15 / 0.0179 / 0.27 |
| [C25503856](https://jlcpcb.com/partdetail/XINGLIGHT-XL1005UYC/C25503856) | [XL-1005UYC](https://www.lcsc.com/product-detail/led-indication-discrete_xinglight-xl-1005uyc_C25503856.html) | XINGLIGHT | CLK yellow | extended | 1 | 172074 | 20 / 0.0132 / 0.26 | 20 / 0.0132 / 0.26 |
| [C108301](https://jlcpcb.com/partdetail/ChilisinElec-PBY160808T_601YN/C108301) | [PBY160808T-601Y-N](https://www.lcsc.com/product-detail/ferrite-beads_chilisin-elec-pby160808t-601y-n_C108301.html) | Chilisin Elec | 600R@100MHz | extended | 6 | 736581 | 22 / 0.0114 / 0.25 | 40 / 0.0114 / 0.46 |
| [C167485](https://jlcpcb.com/partdetail/MurataElectronics-LQW15AN62NG00D/C167485) | [LQW15AN62NG00D](https://www.lcsc.com/product-detail/power-inductors_murata-electronics-lqw15an62ng00d_C167485.html) | Murata Electronics | 62n | extended | 1 | 10983 | 6 / 0.041 / 0.25 | 9 / 0.041 / 0.37 |
| [C47339](https://jlcpcb.com/partdetail/48344-CL05A474KP5NNNC/C47339) | [CL05A474KP5NNNC](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_samsung-electro-mechanics-cl05a474kp5nnnc_C47339.html) | Samsung Electro-Mechanics | 0.47u | preferred | 4 | 532805 | 20 / 0.012 / 0.24 | 32 / 0.012 / 0.38 |
| [C12624](https://jlcpcb.com/partdetail/Hubei_KENTOElec-KT0603G/C12624) | [KT-0603G](https://www.lcsc.com/product-detail/led-indication-discrete_hubei-kento-elec-kt-0603g_C12624.html) | Hubei KENTO Elec | green | extended | 1 | 200324 | 20 / 0.0119 / 0.24 | 21 / 0.0119 / 0.25 |
| [C88219](https://jlcpcb.com/partdetail/89397-0603B104K101NT/C88219) | [0603B104K101NT](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_fh-guangdong-fenghua-advanced-tech-0603b104k101nt_C88219.html) | FH (Guangdong Fenghua Advanced Tech) | 100n 100V | extended | 1 | 1275939 | 20 / 0.0116 / 0.23 | 20 / 0.0116 / 0.23 |
| [C304314](https://jlcpcb.com/partdetail/TAITECH-HCB1608KF221T20/C304314) | [HCB1608KF-221T20](https://www.lcsc.com/product-detail/ferrite-beads_tai-tech-hcb1608kf-221t20_C304314.html) | TAI-TECH | 220R@100MHz | extended | 5 | 862918 | 20 / 0.0116 / 0.23 | 35 / 0.0116 / 0.41 |
| [C25503345](https://jlcpcb.com/partdetail/XINGLIGHT-XL1005SURC/C25503345) | [XL-1005SURC](https://www.lcsc.com/product-detail/led-indication-discrete_xinglight-xl-1005surc_C25503345.html) | XINGLIGHT | ADCR red / ADCS red / TX red / ERR red | extended | 4 | 866655 | 26 / 0.0084 / 0.22 | 38 / 0.0084 / 0.32 |
| [C81464](https://jlcpcb.com/partdetail/onsemi-MMBT3904LT1G/C81464) | [MMBT3904LT1G](https://www.lcsc.com/product-detail/bipolar-bjt_onsemi-mmbt3904lt1g_C81464.html) | onsemi | MMBT3904 | extended | 4 | 1327801 | 13 / 0.0164 / 0.21 | 25 / 0.0164 / 0.41 |
| [C52923](https://jlcpcb.com/partdetail/53938-CL05A105KA5NQNC/C52923) | [CL05A105KA5NQNC](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_samsung-electro-mechanics-cl05a105ka5nqnc_C52923.html) | Samsung Electro-Mechanics | 1u | basic | 11 | 9471974 | 34 / 0.0055 / 0.19 | 67 / 0.0055 / 0.37 |
| [C32713279](https://jlcpcb.com/partdetail/hanxia-HX_PZ2_54_2x6PZZ/C32713279) | [HX PZ2.54-2x6P ZZ](https://www.lcsc.com/product-detail/pin-headers_hanxia-hx-pz2-54-2x6p-zz_C32713279.html) | hanxia | Pmod | extended | 1 | 22794 | 2 / 0.093 / 0.19 | 5 / 0.093 / 0.46 |
| [C8545](https://jlcpcb.com/partdetail/9040-2N7002/C8545) | [2N7002](https://www.lcsc.com/product-detail/mosfets_jiangsu-changjing-electronics-technology-co-ltd-2n7002_C8545.html) | Jiangsu Changjing Electronics Technology Co., Ltd. | 2N7002 | basic | 2 | 6047108 | 12 / 0.0158 / 0.19 | 18 / 0.0158 / 0.28 |
| [C21120](https://jlcpcb.com/partdetail/21832-CL10B224KA8NNNC/C21120) | [CL10B224KA8NNNC](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_samsung-electro-mechanics-cl10b224ka8nnnc_C21120.html) | Samsung Electro-Mechanics | 220n 25V | basic | 2 | 939812 | 20 / 0.0089 / 0.18 | 20 / 0.0089 / 0.18 |
| [C23733](https://jlcpcb.com/partdetail/24469-CL05A475MP5NRNC/C23733) | [CL05A475MP5NRNC](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_samsung-electro-mechanics-cl05a475mp5nrnc_C23733.html) | Samsung Electro-Mechanics | 4.7u | basic | 1 | 981223 | 20 / 0.0077 / 0.15 | 20 / 0.0077 / 0.15 |
| [C327229](https://jlcpcb.com/partdetail/YAGEO-CC0402BRNPO9BN1R3/C327229) | [CC0402BRNPO9BN1R3](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402brnpo9bn1r3_C327229.html) | YAGEO | 1.3p | extended | 1 | 40583 | 20 / 0.0074 / 0.15 | 20 / 0.0074 / 0.15 |
| [C25087](https://jlcpcb.com/partdetail/25830-0402WGF2000TCE/C25087) | [0402WGF2000TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf2000tce_C25087.html) | UNI-ROYAL(Uniroyal Elec) | 200 | basic | 21 | 1532334 | 52 / 0.0029 / 0.15 | 115 / 0.0029 / 0.33 |
| [C1523](https://jlcpcb.com/partdetail/1875-0402B102K500NT/C1523) | [0402B102K500NT](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_fh-guangdong-fenghua-advanced-tech-0402b102k500nt_C1523.html) | FH (Guangdong Fenghua Advanced Tech) | 1n | basic | 12 | 4102044 | 39 / 0.0036 / 0.14 | 75 / 0.0036 / 0.27 |
| [C526982](https://jlcpcb.com/partdetail/YAGEO-CC0402FRNPO9BN820/C526982) | [CC0402FRNPO9BN820](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402frnpo9bn820_C526982.html) | YAGEO | 82p | extended | 1 | 49105 | 20 / 0.0069 / 0.14 | 20 / 0.0069 / 0.14 |
| [C541342](https://jlcpcb.com/partdetail/YAGEO-CC0402BRNPO9BN6R2/C541342) | [CC0402BRNPO9BN6R2](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402brnpo9bn6r2_C541342.html) | YAGEO | 6.2p | extended | 1 | 21193 | 20 / 0.0068 / 0.14 | 20 / 0.0068 / 0.14 |
| [C576706](https://jlcpcb.com/partdetail/YAGEO-CC0402JRNPO9BN161/C576706) | [CC0402JRNPO9BN161](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402jrnpo9bn161_C576706.html) | YAGEO | 160p | extended | 3 | 30334 | 20 / 0.0066 / 0.13 | 25 / 0.0066 / 0.17 |
| [C15195](https://jlcpcb.com/partdetail/15869-CL05B103KB5NNNC/C15195) | [CL05B103KB5NNNC](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_samsung-electro-mechanics-cl05b103kb5nnnc_C15195.html) | Samsung Electro-Mechanics | 10n | basic | 10 | 5492561 | 35 / 0.0037 / 0.13 | 65 / 0.0037 / 0.24 |
| [C576704](https://jlcpcb.com/partdetail/YAGEO-CC0402JRNPO9BN111/C576704) | [CC0402JRNPO9BN111](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402jrnpo9bn111_C576704.html) | YAGEO | 110p | extended | 1 | 52496 | 20 / 0.0066 / 0.13 | 20 / 0.0066 / 0.13 |
| [C106200](https://jlcpcb.com/partdetail/YAGEO-CC0402JRNPO9BN101/C106200) | [CC0402JRNPO9BN101](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402jrnpo9bn101_C106200.html) | YAGEO | 100p | extended | 31 | 6568451 | 82 / 0.0015 / 0.12 | 175 / 0.0015 / 0.26 |
| [C541433](https://jlcpcb.com/partdetail/YAGEO-CC0402FRNPO9BN130/C541433) | [CC0402FRNPO9BN130](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402frnpo9bn130_C541433.html) | YAGEO | 13p | extended | 1 | 12006 | 20 / 0.006 / 0.12 | 20 / 0.006 / 0.12 |
| [C25744](https://jlcpcb.com/partdetail/26487-0402WGF1002TCE/C25744) | [0402WGF1002TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf1002tce_C25744.html) | UNI-ROYAL(Uniroyal Elec) | 10k / 10k 1% | basic | 33 | 35935096 | 81 / 0.0015 / 0.12 | 180 / 0.0015 / 0.27 |
| [C25499](https://jlcpcb.com/partdetail/26242-4D02WGJ0220TCE/C25499) | [4D02WGJ0220TCE](https://www.lcsc.com/product-detail/resistor-networks-arrays_uni-royal-uniroyal-elec-4d02wgj0220tce_C25499.html) | UNI-ROYAL(Uniroyal Elec) | 4x22 | extended | 7 | 610280 | 24 / 0.0048 / 0.12 | 45 / 0.0048 / 0.22 |
| [C131337](https://jlcpcb.com/partdetail/JST-B2B_PH_K_S_LF_SN/C131337) | [B2B-PH-K-S(LF)(SN)](https://www.lcsc.com/product-detail/wire-to-board-connector_jst-b2b-ph-k-s-lf-sn_C131337.html) | JST | FAN 5V | extended | 1 | 267768 | 3 / 0.0356 / 0.11 | 6 / 0.0356 / 0.21 |
| [C21122](https://jlcpcb.com/partdetail/21834-CL10B223KB8NNNC/C21122) | [CL10B223KB8NNNC](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_samsung-electro-mechanics-cl10b223kb8nnnc_C21122.html) | Samsung Electro-Mechanics | 22n | basic | 1 | 973155 | 20 / 0.0056 / 0.11 | 20 / 0.0056 / 0.11 |
| [C327205](https://jlcpcb.com/partdetail/YAGEO-CC0402BRNPO9BN8R2/C327205) | [CC0402BRNPO9BN8R2](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402brnpo9bn8r2_C327205.html) | YAGEO | 8.2p | extended | 5 | 395624 | 20 / 0.0044 / 0.09 | 35 / 0.0044 / 0.15 |
| [C106998](https://jlcpcb.com/partdetail/YAGEO-CC0402JRNPO9BN151/C106998) | [CC0402JRNPO9BN151](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402jrnpo9bn151_C106998.html) | YAGEO | 150p | extended | 1 | 535940 | 20 / 0.0043 / 0.09 | 20 / 0.0043 / 0.09 |
| [C106223](https://jlcpcb.com/partdetail/YAGEO-CC0402JRNPO9BN390/C106223) | [CC0402JRNPO9BN390](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402jrnpo9bn390_C106223.html) | YAGEO | 39p | extended | 1 | 115606 | 20 / 0.0047 / 0.09 | 20 / 0.0047 / 0.09 |
| [C327209](https://jlcpcb.com/partdetail/YAGEO-CC0402BRNPO9BN1R8/C327209) | [CC0402BRNPO9BN1R8](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402brnpo9bn1r8_C327209.html) | YAGEO | 1.8p | extended | 1 | 478293 | 20 / 0.0043 / 0.09 | 20 / 0.0043 / 0.09 |
| [C527000](https://jlcpcb.com/partdetail/YAGEO-CC0402JRNPO9BN110/C527000) | [CC0402JRNPO9BN110](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402jrnpo9bn110_C527000.html) | YAGEO | 11p | extended | 2 | 20404 | 20 / 0.0044 / 0.09 | 20 / 0.0044 / 0.09 |
| [C327292](https://jlcpcb.com/partdetail/YAGEO-CC0402BRNPO9BN1R2/C327292) | [CC0402BRNPO9BN1R2](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402brnpo9bn1r2_C327292.html) | YAGEO | 1.2p | extended | 1 | 115003 | 20 / 0.0046 / 0.09 | 20 / 0.0046 / 0.09 |
| [C226372](https://jlcpcb.com/partdetail/YAGEO-AC0402FR0724R9L/C226372) | [AC0402FR-0724R9L](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_yageo-ac0402fr-0724r9l_C226372.html) | YAGEO | 24.9 | extended | 7 | 192225 | 24 / 0.0039 / 0.09 | 45 / 0.0039 / 0.18 |
| [C100316](https://jlcpcb.com/partdetail/LIZElec-CR0402FF2262G/C100316) | [CR0402FF2262G](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_liz-elec-cr0402ff2262g_C100316.html) | LIZ Elec | 22.6k | extended | 1 | 19140 | 20 / 0.0043 / 0.09 | 20 / 0.0043 / 0.09 |
| [C106999](https://jlcpcb.com/partdetail/YAGEO-CC0402JRNPO9BN181/C106999) | [CC0402JRNPO9BN181](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402jrnpo9bn181_C106999.html) | YAGEO | 180p | extended | 1 | 260215 | 20 / 0.0038 / 0.08 | 20 / 0.0038 / 0.08 |
| [C107006](https://jlcpcb.com/partdetail/YAGEO-CC0402JRNPO9BN331/C107006) | [CC0402JRNPO9BN331](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402jrnpo9bn331_C107006.html) | YAGEO | 330p | extended | 2 | 291980 | 20 / 0.0042 / 0.08 | 20 / 0.0042 / 0.08 |
| [C505468](https://jlcpcb.com/partdetail/YAGEO-CC0402BRNPO9BN5R6/C505468) | [CC0402BRNPO9BN5R6](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402brnpo9bn5r6_C505468.html) | YAGEO | 5.6p | extended | 2 | 199428 | 20 / 0.0042 / 0.08 | 20 / 0.0042 / 0.08 |
| [C541365](https://jlcpcb.com/partdetail/YAGEO-CC0402JRNPO9BN910/C541365) | [CC0402JRNPO9BN910](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402jrnpo9bn910_C541365.html) | YAGEO | 91p | extended | 2 | 15658 | 20 / 0.0041 / 0.08 | 20 / 0.0041 / 0.08 |
| [C326937](https://jlcpcb.com/partdetail/YAGEO-CC0402BRNPO9BN2R7/C326937) | [CC0402BRNPO9BN2R7](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402brnpo9bn2r7_C326937.html) | YAGEO | 2.7p | extended | 1 | 91356 | 20 / 0.0037 / 0.07 | 20 / 0.0037 / 0.07 |
| [C1532](https://jlcpcb.com/partdetail/1884-0402B223K500NT/C1532) | [0402B223K500NT](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_fh-guangdong-fenghua-advanced-tech-0402b223k500nt_C1532.html) | FH (Guangdong Fenghua Advanced Tech) | 22n | basic | 2 | 609358 | 20 / 0.0034 / 0.07 | 20 / 0.0034 / 0.07 |
| [C281756](https://jlcpcb.com/partdetail/YAGEO-CC0402BRNPO9BN2R0/C281756) | [CC0402BRNPO9BN2R0](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402brnpo9bn2r0_C281756.html) | YAGEO | 2p | extended | 1 | 557810 | 20 / 0.0033 / 0.07 | 20 / 0.0033 / 0.07 |
| [C25076](https://jlcpcb.com/partdetail/25819-0402WGF1000TCE/C25076) | [0402WGF1000TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf1000tce_C25076.html) | UNI-ROYAL(Uniroyal Elec) | 100 | basic | 23 | 10081226 | 61 / 0.0012 / 0.07 | 130 / 0.0012 / 0.16 |
| [C25900](https://jlcpcb.com/partdetail/26643-0402WGF4701TCE/C25900) | [0402WGF4701TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf4701tce_C25900.html) | UNI-ROYAL(Uniroyal Elec) | 4.7k | basic | 16 | 12626768 | 42 / 0.0017 / 0.07 | 90 / 0.0017 / 0.15 |
| [C25867](https://jlcpcb.com/partdetail/26610-0402WGF1501TCE/C25867) | [0402WGF1501TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf1501tce_C25867.html) | UNI-ROYAL(Uniroyal Elec) | 1.5k | basic | 4 | 1108765 | 23 / 0.0029 / 0.07 | 35 / 0.0029 / 0.10 |
| [C25890](https://jlcpcb.com/partdetail/26633-0402WGF3301TCE/C25890) | [0402WGF3301TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf3301tce_C25890.html) | UNI-ROYAL(Uniroyal Elec) | 3.3k | basic | 1 | 1526533 | 20 / 0.0036 / 0.07 | 20 / 0.0036 / 0.07 |
| [C130117](https://jlcpcb.com/partdetail/YAGEO-CC0402CRNPO9BN5R0/C130117) | [CC0402CRNPO9BN5R0](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402crnpo9bn5r0_C130117.html) | YAGEO | 5p | extended | 2 | 69734 | 20 / 0.0028 / 0.06 | 20 / 0.0028 / 0.06 |
| [C505479](https://jlcpcb.com/partdetail/YAGEO-CC0402CRNPO9BN7R5/C505479) | [CC0402CRNPO9BN7R5](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402crnpo9bn7r5_C505479.html) | YAGEO | 7.5p | extended | 1 | 23430 | 20 / 0.0031 / 0.06 | 20 / 0.0031 / 0.06 |
| [C106202](https://jlcpcb.com/partdetail/YAGEO-CC0402JRNPO9BN180/C106202) | [CC0402JRNPO9BN180](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402jrnpo9bn180_C106202.html) | YAGEO | 18p | extended | 2 | 1611084 | 20 / 0.003 / 0.06 | 20 / 0.003 / 0.06 |
| [C25803](https://jlcpcb.com/partdetail/26546-0603WAF1003T5E/C25803) | [0603WAF1003T5E](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0603waf1003t5e_C25803.html) | UNI-ROYAL(Uniroyal Elec) | 100k | basic | 1 | 13398501 | 20 / 0.0029 / 0.06 | 20 / 0.0029 / 0.06 |
| [C281763](https://jlcpcb.com/partdetail/YAGEO-CC0402JRNPO9BN620/C281763) | [CC0402JRNPO9BN620](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402jrnpo9bn620_C281763.html) | YAGEO | 62p | extended | 3 | 44145 | 20 / 0.0027 / 0.05 | 25 / 0.0027 / 0.07 |
| [C226375](https://jlcpcb.com/partdetail/YAGEO-AC0402FR07255RL/C226375) | [AC0402FR-07255RL](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_yageo-ac0402fr-07255rl_C226375.html) | YAGEO | 255 | extended | 2 | 7263 | 20 / 0.0024 / 0.05 | 20 / 0.0024 / 0.05 |
| [C11702](https://jlcpcb.com/partdetail/12256-0402WGF1001TCE/C11702) | [0402WGF1001TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf1001tce_C11702.html) | UNI-ROYAL(Uniroyal Elec) | 1k | basic | 16 | 29788366 | 42 / 0.0013 / 0.05 | 90 / 0.0013 / 0.12 |
| [C137761](https://jlcpcb.com/partdetail/YAGEO-RC0603FR0724K9L/C137761) | [RC0603FR-0724K9L](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_yageo-rc0603fr-0724k9l_C137761.html) | YAGEO | 24.9k | extended | 1 | 1639918 | 20 / 0.0023 / 0.05 | 20 / 0.0023 / 0.05 |
| [C106203](https://jlcpcb.com/partdetail/YAGEO-CC0402JRNPO9BN220/C106203) | [CC0402JRNPO9BN220](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402jrnpo9bn220_C106203.html) | YAGEO | 22p | extended | 7 | 2205322 | 24 / 0.0018 / 0.04 | 45 / 0.0018 / 0.08 |
| [C107002](https://jlcpcb.com/partdetail/YAGEO-CC0402JRNPO9BN270/C107002) | [CC0402JRNPO9BN270](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402jrnpo9bn270_C107002.html) | YAGEO | 27p | extended | 2 | 1038024 | 20 / 0.0018 / 0.04 | 22 / 0.0018 / 0.04 |
| [C107005](https://jlcpcb.com/partdetail/YAGEO-CC0402JRNPO9BN330/C107005) | [CC0402JRNPO9BN330](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402jrnpo9bn330_C107005.html) | YAGEO | 33p | extended | 8 | 5461237 | 26 / 0.0017 / 0.04 | 50 / 0.0017 / 0.08 |
| [C189470](https://jlcpcb.com/partdetail/YAGEO-CC0402CRNPO9BN6R8/C189470) | [CC0402CRNPO9BN6R8](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402crnpo9bn6r8_C189470.html) | YAGEO | 6.8p | extended | 3 | 318503 | 20 / 0.0018 / 0.04 | 25 / 0.0018 / 0.04 |
| [C2933256](https://jlcpcb.com/partdetail/FOJAN-FRC0603F7321TS/C2933256) | [FRC0603F7321TS](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_fojan-frc0603f7321ts_C2933256.html) | FOJAN | 7.32k | extended | 1 | 429585 | 20 / 0.0019 / 0.04 | 20 / 0.0019 / 0.04 |
| [C25792](https://jlcpcb.com/partdetail/26535-0402WGF4702TCE/C25792) | [0402WGF4702TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf4702tce_C25792.html) | UNI-ROYAL(Uniroyal Elec) | 47k | basic | 1 | 5394425 | 20 / 0.0019 / 0.04 | 20 / 0.0019 / 0.04 |
| [C25794](https://jlcpcb.com/partdetail/26537-0402WGF5102TCE/C25794) | [0402WGF5102TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf5102tce_C25794.html) | UNI-ROYAL(Uniroyal Elec) | 51k | basic | 1 | 1337921 | 20 / 0.0019 / 0.04 | 20 / 0.0019 / 0.04 |
| [C25814](https://jlcpcb.com/partdetail/26557-0603WAF3163T5E/C25814) | [0603WAF3163T5E](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0603waf3163t5e_C25814.html) | UNI-ROYAL(Uniroyal Elec) | 316k | extended | 1 | 100550 | 20 / 0.0018 / 0.04 | 20 / 0.0018 / 0.04 |
| [C2930090](https://jlcpcb.com/partdetail/FOJAN-FRC0603F3092TS/C2930090) | [FRC0603F3092TS](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_fojan-frc0603f3092ts_C2930090.html) | FOJAN | 30.9k | extended | 1 | 279966 | 20 / 0.0019 / 0.04 | 20 / 0.0019 / 0.04 |
| [C22935](https://jlcpcb.com/partdetail/23662-0603WAF1004T5E/C22935) | [0603WAF1004T5E](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0603waf1004t5e_C22935.html) | UNI-ROYAL(Uniroyal Elec) | 1M | basic | 1 | 5150785 | 20 / 0.0018 / 0.04 | 20 / 0.0018 / 0.04 |
| [C107000](https://jlcpcb.com/partdetail/YAGEO-CC0402JRNPO9BN200/C107000) | [CC0402JRNPO9BN200](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402jrnpo9bn200_C107000.html) | YAGEO | 20p | extended | 4 | 784495 | 20 / 0.0016 / 0.03 | 30 / 0.0016 / 0.05 |
| [C60137](https://jlcpcb.com/partdetail/YAGEO-CC0402JRNPO9BN470/C60137) | [CC0402JRNPO9BN470](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402jrnpo9bn470_C60137.html) | YAGEO | 47p | extended | 1 | 2463875 | 20 / 0.0013 / 0.03 | 20 / 0.0013 / 0.03 |
| [C106199](https://jlcpcb.com/partdetail/YAGEO-CC0402JRNPO9BN100/C106199) | [CC0402JRNPO9BN100](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402jrnpo9bn100_C106199.html) | YAGEO | 10p | extended | 2 | 1553969 | 20 / 0.0016 / 0.03 | 22 / 0.0016 / 0.04 |
| [C281755](https://jlcpcb.com/partdetail/YAGEO-CC0402JRNPO9BN240/C281755) | [CC0402JRNPO9BN240](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402jrnpo9bn240_C281755.html) | YAGEO | 24p | extended | 3 | 273638 | 20 / 0.0014 / 0.03 | 25 / 0.0014 / 0.03 |
| [C114394](https://jlcpcb.com/partdetail/YAGEO-CC0402JRNPO9BN360/C114394) | [CC0402JRNPO9BN360](https://www.lcsc.com/product-detail/multilayer-ceramic-capacitors-mlcc-smd-smt_yageo-cc0402jrnpo9bn360_C114394.html) | YAGEO | 36p | extended | 2 | 183567 | 20 / 0.0014 / 0.03 | 20 / 0.0014 / 0.03 |
| [C25120](https://jlcpcb.com/partdetail/25863-0402WGF499JTCE/C25120) | [0402WGF499JTCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf499jtce_C25120.html) | UNI-ROYAL(Uniroyal Elec) | 49.9 | basic | 7 | 1213441 | 24 / 0.0012 / 0.03 | 45 / 0.0012 / 0.05 |
| [C25079](https://jlcpcb.com/partdetail/25822-0402WGF1200TCE/C25079) | [0402WGF1200TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf1200tce_C25079.html) | UNI-ROYAL(Uniroyal Elec) | 120 | basic | 3 | 3219045 | 21 / 0.0012 / 0.03 | 30 / 0.0012 / 0.04 |
| [C620468](https://jlcpcb.com/partdetail/650339-0402WGF115JTCE/C620468) | [0402WGF115JTCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf115jtce_C620468.html) | UNI-ROYAL(Uniroyal Elec) | 11.5 | extended | 8 | 9670 | 26 / 0.0011 / 0.03 | 50 / 0.0011 / 0.06 |
| [C138027](https://jlcpcb.com/partdetail/YAGEO-RC0402FR0724K9L/C138027) | [RC0402FR-0724K9L](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_yageo-rc0402fr-0724k9l_C138027.html) | YAGEO | 24.9k | extended | 1 | 848658 | 20 / 0.0014 / 0.03 | 20 / 0.0014 / 0.03 |
| [C25905](https://jlcpcb.com/partdetail/26648-0402WGF5101TCE/C25905) | [0402WGF5101TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf5101tce_C25905.html) | UNI-ROYAL(Uniroyal Elec) | 5.1k | basic | 2 | 4283516 | 20 / 0.0014 / 0.03 | 25 / 0.0014 / 0.03 |
| [C25977](https://jlcpcb.com/partdetail/26720-0603WAF6041T5E/C25977) | [0603WAF6041T5E](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0603waf6041t5e_C25977.html) | UNI-ROYAL(Uniroyal Elec) | 6.04k | extended | 1 | 85053 | 20 / 0.0017 / 0.03 | 20 / 0.0017 / 0.03 |
| [C2933071](https://jlcpcb.com/partdetail/FOJAN-FRC0402F1300TS/C2933071) | [FRC0402F1300TS](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_fojan-frc0402f1300ts_C2933071.html) | FOJAN | 130 | extended | 2 | 42680 | 20 / 0.0009 / 0.02 | 20 / 0.0009 / 0.02 |
| [C3013184](https://jlcpcb.com/partdetail/FOJAN-FRC0402F64R9TS/C3013184) | [FRC0402F64R9TS](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_fojan-frc0402f64r9ts_C3013184.html) | FOJAN | 64.9 | extended | 3 | 49037 | 20 / 0.0012 / 0.02 | 25 / 0.0012 / 0.03 |
| [C2909380](https://jlcpcb.com/partdetail/FOJAN-FRC0402F68R0TS/C2909380) | [FRC0402F68R0TS](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_fojan-frc0402f68r0ts_C2909380.html) | FOJAN | 68 | extended | 1 | 1100108 | 20 / 0.0011 / 0.02 | 20 / 0.0011 / 0.02 |
| [C2930008](https://jlcpcb.com/partdetail/FOJAN-FRC0402F4301TS/C2930008) | [FRC0402F4301TS](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_fojan-frc0402f4301ts_C2930008.html) | FOJAN | 4.3k | extended | 4 | 251191 | 20 / 0.0012 / 0.02 | 30 / 0.0012 / 0.04 |
| [C7467414](https://jlcpcb.com/partdetail/FOJAN-FRC0402F1150TS/C7467414) | [FRC0402F1150TS](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_fojan-frc0402f1150ts_C7467414.html) | FOJAN | 115 | extended | 1 | 12182 | 20 / 0.001 / 0.02 | 20 / 0.001 / 0.02 |
| [C270625](https://jlcpcb.com/partdetail/260005-0402WGF240JTCE/C270625) | [0402WGF240JTCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf240jtce_C270625.html) | UNI-ROYAL(Uniroyal Elec) | 24 | extended | 2 | 190739 | 20 / 0.0012 / 0.02 | 20 / 0.0012 / 0.02 |
| [C25765](https://jlcpcb.com/partdetail/26508-0402WGF2002TCE/C25765) | [0402WGF2002TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf2002tce_C25765.html) | UNI-ROYAL(Uniroyal Elec) | 20k | basic | 1 | 2644479 | 20 / 0.001 / 0.02 | 20 / 0.001 / 0.02 |
| [C25105](https://jlcpcb.com/partdetail/25848-0402WGF330JTCE/C25105) | [0402WGF330JTCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf330jtce_C25105.html) | UNI-ROYAL(Uniroyal Elec) | 33 | basic | 4 | 4511554 | 23 / 0.001 / 0.02 | 35 / 0.001 / 0.04 |
| [C2998115](https://jlcpcb.com/partdetail/FOJAN-FRC0402F1911TS/C2998115) | [FRC0402F1911TS](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_fojan-frc0402f1911ts_C2998115.html) | FOJAN | 1.91k 1% | extended | 1 | 52813 | 20 / 0.0011 / 0.02 | 20 / 0.0011 / 0.02 |
| [C5159686](https://jlcpcb.com/partdetail/FOJAN-FRC0402F3831TS/C5159686) | [FRC0402F3831TS](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_fojan-frc0402f3831ts_C5159686.html) | FOJAN | 3.83k | extended | 2 | 34121 | 20 / 0.001 / 0.02 | 20 / 0.001 / 0.02 |
| [C25741](https://jlcpcb.com/partdetail/26484-0402WGF1003TCE/C25741) | [0402WGF1003TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf1003tce_C25741.html) | UNI-ROYAL(Uniroyal Elec) | 100k | basic | 7 | 8467912 | 26 / 0.0009 / 0.02 | 47 / 0.0009 / 0.04 |
| [C122548](https://jlcpcb.com/partdetail/123817-0402WGF3322TCE/C122548) | [0402WGF3322TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf3322tce_C122548.html) | UNI-ROYAL(Uniroyal Elec) | 33.2k | extended | 1 | 607611 | 20 / 0.001 / 0.02 | 20 / 0.001 / 0.02 |
| [C11457](https://jlcpcb.com/partdetail/12011-0402WGF3241TCE/C11457) | [0402WGF3241TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf3241tce_C11457.html) | UNI-ROYAL(Uniroyal Elec) | 3.24k | extended | 1 | 78959 | 20 / 0.0012 / 0.02 | 20 / 0.0012 / 0.02 |
| [C25860](https://jlcpcb.com/partdetail/26603-0402WGF1101TCE/C25860) | [0402WGF1101TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf1101tce_C25860.html) | UNI-ROYAL(Uniroyal Elec) | 1.10k 1% | extended | 1 | 574860 | 20 / 0.0012 / 0.02 | 20 / 0.0012 / 0.02 |
| [C85373](https://jlcpcb.com/partdetail/86546-0402WGF1021TCE/C85373) | [0402WGF1021TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf1021tce_C85373.html) | UNI-ROYAL(Uniroyal Elec) | 1.02k 1% | extended | 1 | 19343 | 20 / 0.0012 / 0.02 | 20 / 0.0012 / 0.02 |
| [C25092](https://jlcpcb.com/partdetail/25835-0402WGF220JTCE/C25092) | [0402WGF220JTCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf220jtce_C25092.html) | UNI-ROYAL(Uniroyal Elec) | 22 | basic | 1 | 4368103 | 20 / 0.001 / 0.02 | 20 / 0.001 / 0.02 |
| [C25882](https://jlcpcb.com/partdetail/26625-0402WGF2401TCE/C25882) | [0402WGF2401TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf2401tce_C25882.html) | UNI-ROYAL(Uniroyal Elec) | 2.4k | preferred | 1 | 674152 | 20 / 0.0012 / 0.02 | 20 / 0.0012 / 0.02 |
| [C25104](https://jlcpcb.com/partdetail/25847-0402WGF3300TCE/C25104) | [0402WGF3300TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf3300tce_C25104.html) | UNI-ROYAL(Uniroyal Elec) | 330 | basic | 3 | 2196676 | 20 / 0.0011 / 0.02 | 25 / 0.0011 / 0.03 |
| [C2933083](https://jlcpcb.com/partdetail/FOJAN-FRC0402F2491TS/C2933083) | [FRC0402F2491TS](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_fojan-frc0402f2491ts_C2933083.html) | FOJAN | 2.49k 1% | extended | 1 | 1727266 | 20 / 0.0012 / 0.02 | 20 / 0.0012 / 0.02 |
| [C25123](https://jlcpcb.com/partdetail/25866-0402WGF5100TCE/C25123) | [0402WGF5100TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf5100tce_C25123.html) | UNI-ROYAL(Uniroyal Elec) | 510 | basic | 2 | 2317042 | 20 / 0.0011 / 0.02 | 22 / 0.0011 / 0.02 |
| [C25908](https://jlcpcb.com/partdetail/26651-0402WGF5601TCE/C25908) | [0402WGF5601TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf5601tce_C25908.html) | UNI-ROYAL(Uniroyal Elec) | 5.6k | preferred | 1 | 251475 | 20 / 0.001 / 0.02 | 20 / 0.001 / 0.02 |
| [C25768](https://jlcpcb.com/partdetail/26511-0402WGF2202TCE/C25768) | [0402WGF2202TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf2202tce_C25768.html) | UNI-ROYAL(Uniroyal Elec) | 22k | basic | 1 | 1187014 | 20 / 0.001 / 0.02 | 20 / 0.001 / 0.02 |
| [C25117](https://jlcpcb.com/partdetail/25860-0402WGF4700TCE/C25117) | [0402WGF4700TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf4700tce_C25117.html) | UNI-ROYAL(Uniroyal Elec) | 470 | basic | 2 | 2343138 | 20 / 0.001 / 0.02 | 20 / 0.001 / 0.02 |
| [C2998176](https://jlcpcb.com/partdetail/FOJAN-FRC0402F2103TS/C2998176) | [FRC0402F2103TS](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_fojan-frc0402f2103ts_C2998176.html) | FOJAN | 210k | extended | 1 | 474495 | 20 / 0.0011 / 0.02 | 20 / 0.0011 / 0.02 |
| [C17168](https://jlcpcb.com/partdetail/17853-0402WGF0000TCE/C17168) | [0402WGF0000TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf0000tce_C17168.html) | UNI-ROYAL(Uniroyal Elec) | 0 | basic | 1 | 14257259 | 20 / 0.0012 / 0.02 | 20 / 0.0012 / 0.02 |
| [C25879](https://jlcpcb.com/partdetail/26622-0402WGF2201TCE/C25879) | [0402WGF2201TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf2201tce_C25879.html) | UNI-ROYAL(Uniroyal Elec) | 2.2k | basic | 3 | 2836474 | 20 / 0.0011 / 0.02 | 25 / 0.0011 / 0.03 |
| [C25871](https://jlcpcb.com/partdetail/26614-0402WGF1801TCE/C25871) | [0402WGF1801TCE](https://www.lcsc.com/product-detail/chip-resistor-surface-mount_uni-royal-uniroyal-elec-0402wgf1801tce_C25871.html) | UNI-ROYAL(Uniroyal Elec) | 1.8k | extended | 1 | 360905 | 20 / 0.001 / 0.02 | 20 / 0.001 / 0.02 |
| none |  |  | TC1-1-13M+ |  | 1 |  | 2 / n/a / n/a | 5 / n/a / n/a |
| none |  |  | Si549 LVPECL 3V3 pinout C |  | 1 |  | 2 / n/a / n/a | 5 / n/a / n/a |
| | **Total** | | | | | | **1638.38** | **3878.89** |
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
