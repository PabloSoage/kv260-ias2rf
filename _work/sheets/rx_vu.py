"""
Draw rev03/RX_VU.kicad_sch (Rev08, the VHF/UHF receive front end) from rx_vu_spec.py with labdraw.py, and check it
with _work/check_sheet.py rx_vu. The four filters are drawn as ladders along the bottom, the way they are analysed
(_work/sim/rev08_filters_mc.py). The root block and the other sheets' Rev08 changes: _work/rev08_schematic.py.

Usage:  py _work/sheets/rx_vu.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import labdraw as D                                               # noqa: E402
import rx_vu_spec as S                                            # noqa: E402

s, PATH, BLOCK_UUID = D.setup(S, "RX_VU", "RX_VU - VHF/UHF receive front end", "A1", 2000,
                              {"VU_LDO_IN", "VU_BIAS_IN", "VU_TCXO_VCC"})
ROOT_UUID = D.ROOT_UUID
GROUPS = [
    (["J961", "D1301"], ["C1301", "FB1302", "L1301"]),
    (["U1314", "JP1301"], ["C1360", "C1361", "R1360", "R1361", "R1362"]),
    (["U1302"], ["C1306"]),
    (["U1301"], ["C1302", "C1303", "L1303", "FB1304", "C1304", "C1305"]),
    (["U1303"], ["C1307"]),
    (["U1313"], ["R1370", "C1370", "C1371"]),
    (["U1315", "FB1301"], ["C1380", "C1381", "C1382"]),
    (["U1304"], ["C1310"]),
    (["U1305"], ["C1311"]),
    (["U1306"], ["C1312"]),
    (["FL1301", "FL1302", "FL1303"], []),
    (["U1307"], ["C1313"]),
    (["U1308", "T1301"], ["C1308", "C1320", "C1321"]),
    (["U1312", "Y1301", "T1302"], ["C1322", "C1323", "C1324", "C1340", "R1340", "C1341", "R1341", "R1342", "R1343",
                                   "R1344", "R1345", "R1346", "C1342", "C1343", "C1344", "C1345", "C1346", "C1347",
                                   "R1347", "C1348", "R1348", "C1349", "R1349", "C1350", "C1351", "C1352", "C1353",
                                   "C1354", "C1355", "C1356"]),
    (["U1309"], ["C1309"]),
    (["U1310"], ["C1330", "L1305", "C1331", "C1332"]),
    (["U1311"], ["R1330", "C1333", "C1334"]),
]
y_ladders = D.layout(GROUPS)
X0 = D.X0
yl = y_ladders + 12.7
for k, name in enumerate(("FMREJ", "FMBP", "AA", "UHF")):
    D.ladder(name, yl + 43.18 * (k // 2), X0 + 254.0 * (k % 2))
yl += 2 * 43.18
notes = [
    "RX_VU - how this sheet works (REV08_PLAN section 5; RX_VU_SPEC)",
    "1. J961 -> ESD -> bias tee (U1314, JP1301: 5 V as built, 3.3 V by the jumper) -> LNA U1301 or its bypass (U1302/U1303).",
    "2. Preselector A (U1304/U1305, V2V1): 00 straight, 01 FM band-pass, 10 FM reject, 11 preselector B.",
    "3. Preselector B (U1306/U1307, V1V2V3): 000 UHF low-pass 480 MHz, 001 SAW 1090 MHz, 010 HPF 1 GHz, 011 LPF 1 GHz, 1xx spare.",
    "4. Converter bypass (U1308/U1309): CTRL high = through the RFFC5072 (LO 85-4200 MHz, IF 135 MHz), low = direct 30-170 MHz.",
    "5. Anti-alias 170 MHz, IF amplifier U1310, attenuator U1311 (0-31.5 dB, powers up at 31.5 dB) -> IF_VU -> SW2 (ROUTING, C927).",
    "6. Control: U1313 TCA6416A at 0x20 on XO_SCL/XO_SDA. P00-P01 PSA_V1-V2, P02-P04 PSB_V1-V3, P05 LNA_ON, P06 CONV_ON,",
    "   P07 BIAS_EN_N, P10 BIAS_FLT_N (in), P11 ENX, P12 SCLK, P13 SDATA (RFFC5072 and, through R1330, PE4312), P14 LD (in),",
    "   P15 RESETX, P16 ATT_LE, P17 ENBL. Pull resistors keep the bias off, the converter off and deselected until it is written.",
    "7. +3V0_RF: U1315 LP5907-3.0 from +3V3_D through FB1301, 180 mA budgeted of 250. The mixer's current flows through T1302's",
    "   centre tap: program MIX2_IDD <= 3 (TC4-1W+ rated 30 mA DC).",
]
for i, t in enumerate(notes):
    s.text(t, (530.0, y_ladders + 4.5 * i), size=1.524 if i == 0 else 1.27)


def write():
    n, w, j = s.write()
    print(f"wrote {os.path.relpath(PATH, D.ROOT)}: {n} symbols, {w} wire segments, {j} junctions; "
          f"ladders end at y {yl:.0f} of 594")


if __name__ == "__main__":
    write()
