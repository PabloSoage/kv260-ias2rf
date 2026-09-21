# Interface specification — phase 1

*21 September 2026 · Rev03 architecture, approved*

The pin-by-pin freeze for everything crossing between the Kria KV260 and the adapter board. What
is `[V]` here was measured; what is `[?]` still gates schematic sign-off.

---

## 1. What is settled and what is not

| Item | State |
|---|---|
| J8 / IAS1 connector pinout | ✅ `[V]` measured from the `.kicad_pcb` |
| Allocation of the 5 differential pairs | ✅ Frozen below |
| Single-ended allocation on J8 | ✅ Frozen below |
| Pmod J2 allocation | ✅ Frozen below |
| KV260 mechanical envelope | ✅ `[V]` measured from the official 3D model (§5) |
| Where the adapter sits within that envelope | ❌ `[?]` **not registered** — see §5.3 |
| `VCCO` of the HPA bank | ❌ `[?]` **blocking** — see §6 |
| Serial link electrical standard | ❌ depends on `VCCO` |
| Per-rail current budget | ⬜ pending datasheet figures |
| 6-layer stackup and impedances | ⬜ pending fabricator |

---

## 2. J8 / IAS1 — verified pinout

Extracted from `CSI2-KRIA-KV260_Rev01.kicad_pcb`, footprint `J8_IAS0` `[V]`. Both IAS connectors on
the adapter are the same part, `AVT_KHK_Lib:J-BM20B(0.8)-34DP`, 50.040 mm apart on the X axis and
2.8 mm from the board edge `[V]`.

| Pin | Original net | Pin | Original net |
|---|---|---|---|
| 1 | *(free)* | 18 | `VCC2V75` |
| 2, 3 | GND | 19 | GND |
| 4 / 5 | `B7-CSI2-TXD0_P` / `_N` | 20 | *(free)* |
| 6 | GND | 21 | `PWDN` |
| 7 / 8 | `B7-CSI2-TXC_P` / `_N` | 22 | `I2C_SDA` |
| 9 | GND | 23, 24 | `VCC1V2` |
| 10 / 11 | `B7-CSI2-TXD3_P` / `_N` | 25 | GND |
| 12 | GND | 26 / 27 | `B7-CSI2-TXD2_N` / `_P` |
| 13 | `VCC1V8` | 28 | GND |
| 14 | `I2C_SCL` | 29 / 30 | `B7-CSI2-TXD1_N` / `_P` |
| 15 | *(free)* | 31 | GND |
| 16 | GND | 32 | `GPIO2` |
| 17 | `VCC2V75` | 33 | GND · 34 *(free)* |

Per connector: **5 differential pairs**, 4 single-ended, 4 free pins, 3 incoming rails, 11 grounds.

---

## 3. Link allocation — frozen

The architecture calls for 3 pairs receive and 2 pairs transmit ([ARCHITECTURE.md](../ARCHITECTURE.md)
§4.1). Assignment:

| Signal | Hirose pair | Pins | Direction | Rate `[E]` |
|---|---|---|---|---|
| `LINK_RX_D0±` | `TXD0` | 4 / 5 | FPGA → Kria | ≤1 Gbps |
| `LINK_RX_D1±` | `TXD1` | 29 / 30 | FPGA → Kria | ≤1 Gbps |
| **`LINK_RX_CLK±`** | **`TXC`** | **7 / 8** | FPGA → Kria | source-synchronous |
| `LINK_TX_D0±` | `TXD2` | 26 / 27 | Kria → FPGA | ≤1 Gbps |
| `LINK_TX_CLK±` | `TXD3` | 10 / 11 | Kria → FPGA | source-synchronous |

**Why the clock goes on `TXC`.** In the original design that pair is the MIPI **clock lane**, so on
the SOM side it is the one most likely to land on a clock-capable pin (MRCC/SRCC). A source-
synchronous receiver needs its clock on a pin that can drive a BUFG/MMCM directly; anything else
costs a routing detour and jitter.

`[?]` **To confirm** against the KV260 carrier card schematic: that the SOM pin behind `TXC` really
is clock-capable. If it is not, `LINK_RX_CLK` moves to whichever pair is, and the rest shuffle.

### 3.1 Note on pair polarity

Three of the pairs are listed `_P` / `_N` and two `_N` / `_P` (pins 26/27 and 29/30) `[V]`. That is
how the original design routed them. Polarity inversion is harmless on a self-synchronising serial
link provided the receiver is told, but it **must be carried into the constraints file** rather than
discovered on the bench.

---

## 4. Single-ended allocation

### 4.1 On J8

| Signal | Pin | Direction | Function |
|---|---|---|---|
| `HK_SCL` | 14 | Kria → adapter | Housekeeping I2C: temperature sensor, board ID EEPROM |
| `HK_SDA` | 22 | bidirectional | Same bus |
| `FPGA_PROG_B` | 21 | Kria → adapter | Front-end FPGA reset / reconfigure (was `PWDN`) |
| `FPGA_IRQ` | 32 | adapter → Kria | Interrupt: link error, overflow, beam-update done (was `GPIO2`) |
| — | 1, 15, 20, 34 | — | Free on the connector. Left unconnected |

### 4.2 On the Pmod J2

Eight signals at 3.3 V, 100 mA on the supply pin `[V — UG1089]`.

| Signal | Count | Function |
|---|---|---|
| `SPI_SCLK`, `SPI_MOSI`, `SPI_MISO` | 3 | Control bus to the FPGA, and through it to everything downstream |
| `SPI_CS` | 1 | Chip select for the FPGA's register file |
| `BEAM_STROBE` | 1 | Synchronous apply of a loaded beam across all ADAR1000s |
| `PPS_SYNC` | 1 | Timing reference in, for correlating detections with GPS |
| *spare* | 2 | Reserved |

**The 100 mA limit means the Pmod supply pin is for signalling only.** The adapter takes its power
from its own 12 V jack.

---

## 5. Mechanical envelope — measured

### 5.1 What was measured

From the official 3D CAD model (XTP679), `KV260V2-Starter-Kit.stl`, 1,320,454 triangles, by
`_work/kv260_envelope.py` `[V]`:

| | Value |
|---|---|
| Overall bounding box | **140.00 × 123.10 × 35.84 mm** |
| X range | −10.00 … 130.00 |
| Y range | −11.57 … 111.53 |
| Z range | −7.09 … 28.75 |
| Anything above 40 mm | **nothing** |

### 5.2 The obstacles an adapter has to clear

| Height above the model's Z minimum | Footprint | Area |
|---|---|---|
| > 10 mm | X −4 … 124, Y −11.6 … 110.4 | 6,216 mm² |
| > 20 mm | X 58 … 112, Y 18.4 … 110.4 | 3,660 mm² |
| > 30 mm | X 60 … 110, Y 18.4 … 74.4 | 2,584 mm² |
| > 35 mm | X 62 … 108, Y 18.4 … 72.4 | 1,396 mm² |

The block above 30 mm — roughly **50 × 56 mm** — is the fansink. It is the dominant obstacle. The
band above 20 mm that extends to high Y is the rear I/O (USB, Ethernet, video).

**The useful conclusion:** an adapter sitting at Hirose stacking height, a handful of millimetres
above the carrier PCB, **cannot pass over the fansink**. It can extend freely over the low regions.

### 5.3 `[?]` What could not be established

**The registration between the adapter's coordinate system and the model's.** The plan was to find
the two mating IAS connectors in the model by their signature — two bodies 50.040 mm apart on one
axis, each about 11.6 × 2.9 mm — and use them to align the two frames.

It did not work. `_work/kv260_locate_ias.py` searched several Z bands at 0.5 mm resolution,
segmented the geometry into connected components and tested every pair. **No axis-aligned pair of
connector-sized bodies at 50.040 mm was found.** The IAS connectors are not resolvable as distinct
bodies in this STL at the fidelity available — they are presumably merged into a larger assembly
body, or simplified out.

So the envelope is known, but **which way the board may grow is not**. Two ways to close it, the
second faster than the first:

1. **XTP681**, the carrier card PCB layout (Allegro), which gives exact connector placements.
2. **A ruler.** Mount the existing adapter and measure the clearance from its edges to the fansink
   and to the rear connectors. Five minutes, and it settles it.

Until then the growth direction stays `[E]` and the ~120 × 90 mm figure in the architecture document
remains an estimate.

---

## 6. `[?]` The blocking unknown: `VCCO` of the HPA bank

Everything electrical about the link depends on one number that is not in this repository: the
`VCCO` the KV260 applies to the SOM bank behind J8.

| If `VCCO` is | Then |
|---|---|
| 1.2 V (likely, MIPI D-PHY convention) | The link runs `LVDS_12`. The ADC's ANSI LVDS output, at 1.2 V common mode, has no headroom into a 1.2 V bank → **AC coupling and re-biasing are required**, and that has to be on the board from the start |
| 1.8 V | `LVDS` outright, DC-coupled, simplest case |

It also decides whether level translation is needed on the single-ended signals, since the Pmod is
on a 3.3 V HD bank while J8 is on an HP bank.

**How to close it:** download **XTP682** (Kria KV260 Starter Kit Carrier Card Schematic, PDF) from
the AMD product page and look up the bank the `B7-CSI2-*` nets land on. It is the single most
valuable document still missing.

**Design mitigation in the meantime:** lay out AC-coupling capacitor footprints in series on all
five pairs, with 0 Ω links as the alternative. If `VCCO` turns out to be 1.8 V they get stuffed with
0 Ω and nothing is lost; if it is 1.2 V the board already has what it needs. The cost is ten
footprints.

---

## 7. Exit criteria for phase 1

| Criterion | State |
|---|---|
| Pin map of J8 and the Pmod frozen | ✅ §3, §4 |
| Mechanical envelope measured | ✅ §5.1, §5.2 |
| Growth direction established | ❌ §5.3 |
| `VCCO` of the HPA bank known | ❌ §6 |
| ADC/DAC operating points fixed | ✅ [ARCHITECTURE.md](../ARCHITECTURE.md) §5 |
| Per-rail current budget from datasheets | ⬜ pending |
| 6-layer stackup with computed impedances | ⬜ pending fabricator |

Two of these need something from outside this repository. Everything else is ready.
