# KV260-IAS2RF — an RF front-end carrier for the AMD Kria KV260

**Status: architecture stage. Not manufacturable. No hardware has been validated.**

An adapter board for the **AMD Kria KV260 Vision AI Starter Kit** that mounts on the Hirose
connectors of the IAS interfaces and carries the converters, the common clock and a front-end
FPGA, serving two chains:

- **Software-defined radio** — HF, AM, FM, airband, amateur bands and PMR446 walkies. Receive,
  and transmit on the bands a licence covers.
- **Radar at 10.5 GHz** — the IF of the X-band chain from the open
  [AERIS-10 / PLFM_RADAR](https://github.com/NawfalMotii79/PLFM_RADAR) project, with ADAR1000
  beamforming.

The 10.5 GHz chain is **not redesigned here**: AERIS-10 is reused. The board is sized for
**8 ADAR1000s (32 channels)** so that it supports both the Nexus variant (4 chips) and the
Extended one (8 chips).

> ### The finding that shapes the whole project
>
> The **IAS0 (J7) connector on the KV260 does not reach the programmable logic**: its MIPI lanes
> run into an AP1302 ISP soldered on the carrier card. Only **IAS1 (J8)** is wired straight to
> the SOM. On top of that, **the KV260 has no 40-pin Raspberry Pi header** — J9 is a 15-pin
> camera connector — and **the GTH transceivers are not exposed**.
>
> The real I/O budget between a KV260 and an external board is **8 differential pairs and about
> 14 single-ended signals**. That is where the front-end FPGA comes from. Evidence and sources in
> [docs/BLOCKERS_AND_RISKS.md](docs/BLOCKERS_AND_RISKS.md).

---

## This board is one subsystem of something larger

The end goal is a sensing and communications platform for an expedition 4×4: LiDAR for fog and
night driving, SDR to listen and **locate** transmissions, emergency radio, radar, and OBD2
telemetry. See [docs/VEHICLE_PLATFORM.md](docs/VEHICLE_PLATFORM.md) — **read it before making any
design decision**, because it changes the priorities completely.

In particular: **four high-value stages need no custom hardware at all** and come before this
board. They are listed in [docs/SHOPPING_LIST.md](docs/SHOPPING_LIST.md).

---

## Where the project came from, and attribution

This is a **fork** of the open hardware design
[Allied Vision Adapter Board CSI-2 for Kria KV260](https://github.com/alliedvision), published
under the MIT licence (see [LICENSE](LICENSE)). What is kept from that design:

- the board outline and its mechanical fit to the KV260
- the two Hirose BM20B(0.8)-34DP connectors (IAS0 / IAS1) and their wiring to the SOM
- the original stackup and fabrication rules

Everything else — the MIPI camera electronics, level shifters, USB power — was removed and is
being replaced by the RF chain described in the documentation. **This repository no longer
produces an Allied Vision camera adapter board.** If that is what you want, use the original
project.

---

## Documentation

| Document | Contents |
|---|---|
| **[HANDOFF.md](HANDOFF.md)** | **Start here if you are picking the project up.** Self-contained: state, findings, open decisions and working rules |
| **[docs/VEHICLE_PLATFORM.md](docs/VEHICLE_PLATFORM.md)** | **System view.** The whole vehicle project: LiDAR, SDR, radar, OBD2 |
| **[docs/SHOPPING_LIST.md](docs/SHOPPING_LIST.md)** | Parts and checklist per stage, with indicative costs |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Master document **for this board**. Rev03 architecture |
| [docs/BLOCKERS_AND_RISKS.md](docs/BLOCKERS_AND_RISKS.md) | The 5 blockers, closed, with evidence and sources, plus the open risks |
| [docs/AUDIT_Rev01.md](docs/AUDIT_Rev01.md) | What the KiCad files actually contain, with evidence |
| [docs/INTERFACE_SPEC.md](docs/INTERFACE_SPEC.md) | **Phase 1.** Frozen pin map for J8 and the Pmod, the mechanical envelope, and the adapter registered on the KV260 model — where the board can grow |
| [docs/POWER_AND_STACKUP.md](docs/POWER_AND_STACKUP.md) | **Phase 1.** Per-rail current budget (15 of 23 loads from datasheets) and the 6-layer stackup with computed trace widths |
| [docs/SYMBOLS.md](docs/SYMBOLS.md) | **Phase 2.** 17 symbols, 15 from datasheets, cross-checked against a second source where one exists |
| [docs/CLOCK_SPEC.md](docs/CLOCK_SPEC.md) | **Phase 2.** The first drawn sheet, reviewed and accepted: the clock plan, every value's source |
| [docs/ADC_RADAR_SPEC.md](docs/ADC_RADAR_SPEC.md) | **Phase 2.** The radar ADC and its two AD8352 drivers, the split of CONVERTERS in four, and how to review it |
| [docs/ADC_SDR_SPEC.md](docs/ADC_SDR_SPEC.md) | **Phase 2.** The SDR ADC, two channels, and the second SDR input `IF_RX_C` |
| [docs/DAC_RADAR_SPEC.md](docs/DAC_RADAR_SPEC.md) | **Phase 2.** The radar DAC, its reconstruction filter and balun, and a reference error found in AERIS-10 |
| [docs/DAC_SDR_SPEC.md](docs/DAC_SDR_SPEC.md) | **Phase 2.** The dual SDR DAC in interleaved mode, two output chains |
| [docs/ROUTING_SPEC.md](docs/ROUTING_SPEC.md) | **Phase 2.** The four RF switches, the switching plan, ten SMAs |
| [docs/IAS_LINK_SPEC.md](docs/IAS_LINK_SPEC.md) | **Phase 2.** The Hirose connectors, AC coupling and terminations of the link |
| [docs/POWER_SPEC.md](docs/POWER_SPEC.md) | **Phase 2.** The power tree as drawn: the regulators and where every value comes from |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Staged plan with verifiable exit criteria |
| [docs/HISTORY_Rev01.md](docs/HISTORY_Rev01.md) | Record of the earlier work and an assessment of it |

---

## Related work

The DSP core this board will need already exists, runs on real silicon and is published
separately:

**[scanner64](https://github.com/PabloSoage/scanner64)** — a real-time multichannel DDC bank for
the KV260's PL. Measured on the board: 100.05 MSPS sustained, no samples dropped across
200 million, bit-exact against its Python model, 8.38 mW per channel, 169.9 MHz Fmax post-route.

That project answers, with hardware, the question this board is built around: whether the PL can
sustain a converter stream in real time. It can.

---

## State of the design files

The KiCad files correspond to a **Rev01 work-in-progress** and **do not implement the Rev03
architecture** documented here.

| File | Actual state |
|---|---|
| `CSI2-KRIA-KV260_Rev01-2.kicad_sch` | Original schematic with the camera electronics purged. **Usable as a base.** |
| `CSI2-KRIA-KV260_Rev01.kicad_pcb` | Original layout, intact and valid. Cleared of the 34 empty footprints a previous pass had inserted. |
| `PCB/`, `Documents/` | Original Altium sources and fabrication outputs, untouched. |
| `_deprecated/` | The two script-generated sheets, removed from the project. See the README in that folder. |
| `_work/` | Analysis and transformation scripts. Every finding in the documentation has its script here. |

Detail and evidence in [docs/AUDIT_Rev01.md](docs/AUDIT_Rev01.md).

### Measured ERC state

Removing the two dead sheets took the root schematic from **1130 to 427 violations**, measured
with `kicad-cli 10.0.1`:

| Category | Before | After |
|---|---|---|
| `pin_not_connected` | 442 | 71 |
| `endpoint_off_grid` | 209 | 136 |
| `lib_symbol_issues` | 119 | 99 |
| `label_dangling` | 97 | 23 |
| **`pin_to_pin`** | **63** | **0** |
| `hier_label_mismatch` | 36 | 36 |
| `isolated_pin_label` | 26 | 0 |
| `lib_symbol_mismatch` | 25 | 0 |
| `no_connect_dangling` | 24 | 22 |
| `same_local_global_label` | 13 | 0 |
| `power_pin_not_driven` | 10 | 9 |
| **`missing_power_pin`** | **8** | **0** |
| `missing_unit` | 8 | 0 |
| `footprint_link_issues` | 39 | 28 |
| `multiple_net_names` | 6 | 0 |
| `unconnected_wire_endpoint` | 4 | 3 |
| `label_multiple_wires` | 1 | 0 |
| **Total** | **1130** | **427** |

Two further passes since, both measured:

| Stage | Total | Notable |
|---|---|---|
| Dead sheets removed | 427 | `pin_to_pin` 63 → 0 |
| Multi-channel annotation fixed | **411** | netlist exports: 48 components, 61 nets |
| Rev03 hierarchy skeleton added | 496 | **`hier_label_mismatch` 36 → 0**; +121 `label_dangling`, which is the 108 new interface labels awaiting their circuits |
| CLOCK sheet drawn | 500 | On the sheet: 2 "power input not driven" (`+3V3_D`, `GND`, until POWER exists) and 6 `isolated_pin_label` (outputs, until their receivers exist). Wiring verified by `_work/check_sheet.py clock`: PASS |
| CONVERTERS split, ADC_RADAR drawn | 672 | +144 `pin_not_connected` on root sheet pins that KiCad had not reported before, though they were just as unwired (why is not established; the root is wired last). On ADC_RADAR: 3 rails and 2 SPI inputs undriven until POWER and CONTROL exist. `check_sheet.py adc_radar`: PASS. [ADC_RADAR_SPEC.md](docs/ADC_RADAR_SPEC.md) §4 |

What remains is pre-existing noise from the Altium import (off-grid endpoints, library symbols
the CLI cannot resolve) plus leftovers of the purge. The serious electrical categories are gone.

Reproduce it with:

```bash
kicad-cli sch erc --severity-all -o erc.rpt CSI2-KRIA-KV260_Rev01.kicad_sch
```

### Measured mechanical fit

The adapter is registered on AMD's official 3D model of the KV260 (the STEP, XTP679). The IAS
connectors are found in it by part name, and the fit is confirmed three independent ways. The
decisive one: **the adapter's two M3 holes land on the carrier's corner holes within 5 µm.**

![Clearance under the adapter](docs/img/kv260_clearance.svg)

Red is a carrier part that would rise through the adapter, which sits only 0.8 mm above the
carrier. **The board can grow outward, off the side of the KV260, and in no other direction.**
Detail, and one tight spot (the J18 jumper), in [docs/INTERFACE_SPEC.md](docs/INTERFACE_SPEC.md)
§5.3. Reproduced by `_work/kv260_register_adapter.py`.

### Measured PCB state

**DRC: 1909 violations** (down from 1942, the 33 difference being the 34 empty footprints that
were removed). They are pre-existing violations of the original Altium design: 502 clearance,
199 track width, 199 silkscreen overlap, 199 drill out of range, 145 library footprint issues.

### The netlist now exports — a blocker that is closed

`kicad-cli sch export netlist` used to fail with *"the schematic has annotation errors"*, which
meant `Update PCB from Schematic` could never run and no schematic change could reach the layout.

There were **two independent causes**, both now fixed by `_work/fix_multichannel_annotation.py`:

1. **Duplicate instance references.** `CSI2-KRIA-KV260_Rev01-2.kicad_sch` is instantiated twice (as
   IAS0 and as IAS1), and both instance paths carried the *same* reference. Rewritten as
   `<ref>_IAS0` / `<ref>_IAS1` — which is the convention the PCB already used, so schematic and
   layout now agree on all 38 references.
2. **The root schematic's UUID did not match its own instance paths.** The file declared
   `(uuid "e5fa38a9-…")` while every instance path in the project pointed at `/56c49378-…`. The
   instance tree referenced a root that did not exist, so KiCad could not resolve a single
   annotation. The declared UUID appeared **once** in the whole project; the one used by the paths
   appeared **188 times**, so the declaration was the outlier and was rewritten.

Result, measured:

| | Before | After |
|---|---|---|
| `sch export netlist` | fails | **48 components, 61 nets** |
| `sch export bom` | fails | **48 rows** |
| ERC violations | 427 | **411** |

The 19 `_IAS0` + 19 `_IAS1` + 10 root-sheet components in the netlist are exactly what the
schematic contains.

---

## Environment

- **KiCad 10** for schematic and layout (migrated from Altium Designer 22)
- The original Altium files are kept in `PCB/` for reference
- Scripts in `_work/` run with plain Python 3, no dependencies

---

## Legal notice

This design transmits on regulated bands. Operating the SDR transmitter requires an amateur radio
licence or equivalent authorisation, and emission in 10.4–10.6 GHz is subject to national
allocations that are **not** free to use in every country. See the compliance section of
[ARCHITECTURE.md](ARCHITECTURE.md). Staying within the applicable law is the responsibility of
whoever builds and operates the equipment.

## Licence

MIT — see [LICENSE](LICENSE). The licence and attribution of the original Allied Vision project
are preserved.
