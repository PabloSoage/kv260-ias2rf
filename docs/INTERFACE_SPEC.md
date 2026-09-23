# Interface specification — phase 1

*21 September 2026 · Rev03 architecture, approved*

The pin-by-pin freeze for everything crossing between the Kria KV260 and the adapter board. What
is `[V]` here was measured; what is `[?]` still gates schematic sign-off.

*Updated 23 September 2026: §5.3 registration closed from the STEP model.*

---

## 1. What is settled and what is not

| Item | State |
|---|---|
| J8 / IAS1 connector pinout | ✅ `[V]` measured from the `.kicad_pcb` |
| Allocation of the 5 differential pairs | ✅ Frozen below |
| Single-ended allocation on J8 | ✅ Frozen below |
| Pmod J2 allocation | ✅ Frozen below |
| KV260 mechanical envelope | ✅ `[V]` measured from the official 3D model (§5) |
| Where the adapter sits within that envelope | ✅ `[V]` registered on the STEP, three independent checks — §5.3 |
| `VCCO` of the HPA bank | ✅ 1.2 V `[E, strongly supported]` — see §6 |
| Serial link electrical standard | ✅ `LVDS_12` with AC coupling — see §6.1 |
| Per-rail current budget | ⚠️ 13 of 21 loads from datasheets — [POWER_AND_STACKUP.md](POWER_AND_STACKUP.md) |
| 6-layer stackup and impedances | ✅ computed; fabricator to confirm |

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

**Why the clock goes on `TXC` — now confirmed** `[V]`. The reasoning was that the pair had been the
MIPI clock lane, so it was the one most likely to land on a clock-capable SOM pin. The carrier card
schematic (XTP682, `038-05058-03-A1.pdf`, sheet 13) settles it: **that pair is `HPA05_CC`, and the
`_CC` suffix is AMD's own marking for clock capable.** A source-synchronous receiver needs its clock
on a pin that can drive a BUFG/MMCM directly; this one can.

### 3.1 SOM-side mapping — verified against the carrier schematic

Every one of the five pairs was cross-checked against XTP682 sheet 13, where the IAS1 connector is
designator `J8`, a `BM20B_0.8_-34DS-0.4V`. **All five match, polarity included** `[V]`:

| Adapter net (from `.kicad_pcb`) | Pins | Carrier net (XTP682) | SOM bank pin |
|---|---|---|---|
| `B7-CSI2-TXD0_P` / `_N` | 4 / 5 | `HPA06_P` / `HPA06_N` | HPA06 |
| **`B7-CSI2-TXC_P` / `_N`** | **7 / 8** | **`HPA05_CC_P` / `HPA05_CC_N`** | **HPA05, clock capable** |
| `B7-CSI2-TXD3_P` / `_N` | 10 / 11 | `HPA09_P` / `HPA09_N` | HPA09 |
| `B7-CSI2-TXD2_N` / `_P` | 26 / 27 | `HPA08_N` / `HPA08_P` | HPA08 |
| `B7-CSI2-TXD1_N` / `_P` | 29 / 30 | `HPA07_N` / `HPA07_P` | HPA07 |

The `_N`-before-`_P` ordering on pins 26/27 and 29/30 that §3.2 notes is **not** an adapter quirk:
the carrier is wired the same way. Both sides agree, so the pairs mate correctly — but the
constraints file still has to know.

**And B-01 is now confirmed from the primary source.** Sheet 13 is titled *"IMAGE CO-PROCESSOR FOR
IAS 0 CONNECTOR"* and shows the AP1302's sensor-side pins (`S0_CLK_DP`, `S0_D0_DP` …) wired to the
IAS0 connector, with its host-side pins (`H_CLK_DP`, `H_D0_DP` …) wired to `HPA00_CC`, `HPA01`,
`HPA02`, `HPA03`, `HPA04`. IAS0 reaches the SOM **only through the ISP**. IAS1 is direct.

### 3.2 Note on pair polarity

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

### 5.3 Registration and growth direction — measured `[V]`

**Closed without touching the hardware.** Neither the STL nor the `.brd` could do it, but the
**STEP** the STL was made from can. It is a Creo assembly with every part named and every placement
stored as a transform, so the IAS connectors can be found by name instead of by shape.

**Why the STL search failed.** `_work/kv260_locate_ias.py` looked for bodies of about
11.6 × 2.9 mm. The STEP shows the carrier's IAS connector is **9.38 × 2.40 × 0.80 mm**. At 0.8 mm
tall it is nearly flush with the board, so it was never going to show up as a separate body.

#### How it was done — three sources, three independent checks

| Source | What it gives |
|---|---|
| **STEP** (`_work/kv260_step_locate.py`) | Two instances of `CONN_928X90X80_38P` at X 21.647, Y 11.986 and Y 62.024: **50.038 mm apart**. The adapter's pair is 50.040 mm apart, and that match is what identifies the part |
| **XTP681 plot** (`default.pdf`) | It has no text layer, but its silkscreen **renders**. **J7 (IAS0) is the +Y connector, J8 (IAS1) the −Y one**, and the pin-1 marks are at the −Y end |
| **Our `.kicad_pcb`** | `J8_IAS0` and `J8_IAS1` on the bottom face, with their pad 1 |

`_work/kv260_register_adapter.py` builds the rigid transform (adapter → carrier: **rotation
−90.00°**, residual **2 µm** at the second connector) and then checks it three ways. None of the
three was used to build it:

| Check | Result |
|---|---|
| 1. The adapter's pad 1 lands on the carrier connector's pin-1 end | ✅ 3.20 mm towards −Y, where the silkscreen draws the mark |
| 2. The original Allied Vision outline is a product that fits, so nothing may rise through it | ✅ 11,948 of 11,958 cells clear. The other 10 are **J18**, below |
| 3. The adapter's two M3 holes land on the carrier's corner holes | ✅ **both within 5 µm**. Holes have nothing to do with the connectors |

Check 3 also answers a mechanical question: the original board is not cantilevered off two 0.8 mm
connectors. It **screws down through the KV260's own corner holes**, the same ones the rubber feet
sit under.

**The original board, seen from the carrier:** 119.00 × 44.50 mm (the designer's own dimensions in
`Dwgs.User` agree). It lies along the carrier's side edge, **flush with the front and rear edges**
(Y −10.00 and 109.00), and overhangs the side by 10 mm. It is U-shaped, with one tongue reaching each
IAS connector.

#### Which way it can grow

![Clearance map under the adapter](img/kv260_clearance.svg)

The map is drawn in the KiCad frame of `CSI2-KRIA-KV260_Rev01.kicad_pcb`, so it reads the way the
board is edited. Red means something on the carrier rises through the adapter's PCB. The adapter
sits at **0.8 mm** above the carrier (the Hirose mated height), so any part taller than that
collides, and nothing can be fitted on the adapter's underside.

| Direction on the carrier | In KiCad | Clear |
|---|---|---|
| **Outward, off the carrier's side edge** | **down (+Y)** | **25+ mm along the full 119 mm — nothing at all in the model** |
| Past the front edge | right (+X) | 25+ mm for the part already off the carrier; 2–8.5 mm over it |
| Past the rear edge | left (−X) | 25+ mm for the part off the carrier; 8.5–16.5 mm for the IAS0 tongue |
| Inward, towards the SOM | up (−Y) | **1.5–5 mm** almost everywhere. The carrier is crowded |

**The answer: grow outward, off the side of the KV260.** Every other direction runs into the carrier
within a few millimetres. The Rev03 target of ~120 × 90 mm fits: that is the same 119 mm length,
with the width growing from 44.5 to ~90 mm, all of it outward. The overhang past the carrier edge
goes from 10 mm to about 55 mm.

**That overhang needs a support at its outer edge**, because two corner screws are not enough for a
board carrying an FPGA and SMA connectors. The model gives the height exactly: the rubber feet reach
**Z −7.085**, so from the adapter's underside (Z +0.8) to the surface the KV260 stands on is
**7.9 mm**. An 8 mm M3 standoff under the outer edge lands on the same plane.

#### A constraint the original design only just meets: J18

**J18** is the IAS0 autofocus jumper (`VDD_AF2V8` → `VDD_AF2V8_J7`, XTP682 p. 13): a 2-pin header,
**fitted**, with a 2.4 mm body and pins to 7.5 mm. Its IAS1 twin, J19, is `DNP`. Allied Vision
cut a notch for it, but in the official model the notch edge (KiCad X 144.901) **overlaps the
header body by 1.0 mm**, 20 % of its footprint.

The model can't tell whether that's real or a generic header drawn slightly too large. It doesn't
matter for Rev03: **keep the board edge at least 1.5 mm clear of KiCad X 143.9–149.0, Y 84.0–86.5**
(the header body in the Rev01 frame). J18 can stay where it is either way. It feeds J7 **pin 34**
only, and the adapter leaves pin 34 of both connectors unconnected: no net on the pads in the
`.kicad_pcb` or in the exported netlist, and §4.1 lists it as free.

#### Reproducing it

```
py _work/kv260_register_adapter.py KV260V2-Starter-Kit.stp KV260V2-Starter-Kit.stl --svg docs/img/kv260_clearance.svg
```

Both model files are the official XTP679 download (not redistributed here). It runs in about 20 s.

---

## 6. `VCCO` of the HPA bank — 1.2 V, on strong evidence

Everything electrical about the link depends on the `VCCO` the KV260 applies to the SOM bank behind
J8. XTP682 does not print a net called `VCCO_HPA`, so this is **not a direct citation**. But the
evidence points one way and it is worth setting out, because the design decision hangs on it.

**What is verified** `[V]` in XTP682:

1. The carrier has a dedicated **`PL_1V2` regulator**, enabled by `VCCOEN_PL_M2C` — the signal the
   SOM asserts when it wants the carrier to bring up the PL's `VCCO` rails.
2. `PL_1V2` is routed to the SOM connector (sheet 6).
3. On sheet 13 the AP1302's MIPI I/O supplies, **`HMIPI_VDD` and `SMIPI_VDD`, are tied to
   `PL_1V2`**.
4. That AP1302 host interface is what drives `HPA00_CC`, `HPA01` … `HPA04` into the SOM.

For a device whose MIPI I/O runs from a 1.2 V rail to signal into the SOM's HPA bank, that bank has
to be at 1.2 V as well. **`VCCO_HPA` = 1.2 V** `[E, strongly supported]`.

### 6.1 What that means for the design

| Consequence | |
|---|---|
| The link runs **`LVDS_12`** | Not plain `LVDS`, which wants 1.8 V |
| The ADC's ANSI LVDS output sits at 1.2 V common mode | Into a 1.2 V bank there is no headroom → **AC coupling and re-biasing are required** |
| The Pmod is on a 3.3 V HD bank | So the single-ended control signals **do** need level translation |

**This is the case the mitigation was designed for, so it stops being a contingency and becomes the
baseline:** series AC-coupling capacitors on all five pairs, with 0 Ω links as the alternative
stuffing option. Ten footprints. If a later measurement shows 1.8 V, they get stuffed with 0 Ω and
nothing is lost.

### 6.2 `[?]` How to turn this from strong evidence into a fact

Either read `VCCO_HPA` directly in the **K26 SOM datasheet (DS987)** pin table, or measure the rail
on an assembled board. Neither is urgent: the design that follows from 1.2 V also survives 1.8 V,
because the AC coupling is stuffable.

---

## 7. Exit criteria for phase 1

| Criterion | State |
|---|---|
| Pin map of J8 and the Pmod frozen | ✅ §3, §4 |
| SOM-side mapping verified | ✅ §3.2, against XTP682 |
| Clock pair on a clock-capable pin | ✅ §3.2, `HPA05_CC` |
| Mechanical envelope measured | ✅ §5.1, §5.2 |
| `VCCO` and the link's I/O standard | ✅ §6, 1.2 V / `LVDS_12` with AC coupling |
| ADC/DAC operating points fixed | ✅ [ARCHITECTURE.md](../ARCHITECTURE.md) §5 |
| Growth direction within the envelope | ✅ §5.3 — registered on the STEP; grow outward, off the carrier's side |
| Per-rail current budget from datasheets | ⚠️ 13 of 21 loads verified — [POWER_AND_STACKUP.md](POWER_AND_STACKUP.md) |
| 6-layer stackup with computed impedances | ✅ computed; ⬜ fabricator's field solver to confirm |

Nothing in this list needs the hardware any more. What remains is the fabricator's impedance
confirmation and the nine power figures still estimated.
