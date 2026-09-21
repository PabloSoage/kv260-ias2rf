# Audit of the Rev01 work-in-progress

*21 September 2026*

What this repository's files actually contain, against what the earlier report claimed. Everything
marked `[V]` was checked against the files, with the path cited.

**Summary:** the earlier report declared *"16/16 phases complete"* with a status table that was
entirely ✅. The real, usable work is the **purge of the original schematic** and the **pinout
extraction**. Beyond that, what exists is symbols instantiated by script with no electrical review,
and a "placement" that does not exist.

---

## 1. The PCB placement does not exist

The report claimed *"Phase F — 34 footprints placed"*.

**What is actually there `[V]`:** the 34 footprints were in `CSI2-KRIA-KV260_Rev01.kicad_pcb`, but
they were **empty shells with not a single pad**. Example:

```
(footprint "Capacitor_SMD:C_0603_1608Metric"
    (layer "F.Cu")
    (at 40 245.853605 0)
    (property "Reference" "CF1" ...)
    (property "Value" "100n" ...)
    (uuid "043435f6-...")
)
```

No pads, no nets, no graphics. The whole file holds **488 pads** `[V]`, exactly those of the
original Altium import.

They have since been removed; see §6.

### 1.1 The DRC metric was misleading

> *"PCB DRC: 1,942 violations, **0 unconnected items** — electrical connectivity is correct"*

The DRC report says literally `** Found 0 unconnected pads **` `[V — _work/pcb_drc.rpt:6834]`. But
it is zero **because there were no pads to connect**. It is not a health metric; it is the artefact
of having inserted footprints with no geometry and no netlist. The conclusion drawn from it was
false.

### 1.2 The footprints sat outside the board

The board outline (`Edge.Cuts`) runs from X 89.0 to 208.0 mm and Y 82.8 to 127.3 mm: a board of
**119 × 44.5 mm** `[V]`.

The new footprints were at Y = 145 … 245 mm `[V]`, that is, **floating up to 120 mm below the board
edge**. The report itself said so without noticing: *"Positions over free area (Y > 145 mm)"*.

There was no placement. And the intended content does not fit in 119 × 44.5 mm by a wide margin.

### 1.3 References did not match between schematic and PCB

| Schematic | PCB `[V]` |
|---|---|
| `U_ADC1`, `U_DAC1`, `U_CLK1`, `U_MIX1` | `U_ADC`, `U_DAC`, `U_CLK`, `U_MIX` |
| `J_RPI1`, `J_PWR1`, `D_TVS1`, `Y_CLK1` | `J_RPI`, `J_PWR`, `D_TVS`, `Y_CLK` |

On *Update PCB from Schematic*, KiCad would not have matched these and would have duplicated them.

---

## 2. The script-generated schematics had no electrical review

### 2.1 Real ERC count

The report presented a table attributing *"about 70 % of violations"* to the Altium import. The
real per-type count, measured with `kicad-cli 10.0.1` `[V]`:

| Type | Root | FRONTEND | PHASED_ARRAY |
|---|---|---|---|
| `pin_not_connected` | 442 | 450 | 248 |
| `endpoint_off_grid` | 209 | 36 | 8 |
| `lib_symbol_issues` | 119 | 15 | — |
| `label_dangling` | 97 | 50 | 25 |
| **`pin_to_pin`** | **63** | **48** | — |
| `footprint_link_issues` | 39 | 6 | 1 |
| `hier_label_mismatch` | 36 | — | — |
| `isolated_pin_label` | 26 | 24 | — |
| `lib_symbol_mismatch` | 25 | 9 | 8 |
| `no_connect_dangling` | 24 | — | — |
| `same_local_global_label` | 13 | 3 | 6 |
| `power_pin_not_driven` | 10 | 3 | — |
| **`missing_power_pin`** | — | **8** | **8** |
| `missing_unit` | — | 8 | 8 |
| **Total** | **1130** | **660** | **312** |

**The root's 442 unconnected pins were mostly new**, not inherited from the import. Attributing 70 %
to Altium does not hold up.

### 2.2 What the report's table left out

**63 `pin_to_pin` conflicts in the root** `[V]`, which the report folded into *"Rest ~167
pre-existing"*. They were not pre-existing: they belonged to `U_PWR1`, `U_PWR2`, `Y_CLK1`,
`D_TVS1`, `J_PWR1` — all **new** components. Example `[V]`:

```
[pin_to_pin]: Pins of type Unspecified and Unspecified are connected
    @(77.30 mm, 37.46 mm): Symbol U_PWR1 Pin 1 [GND, Unspecified, Line]
```

The symbols imported from EasyEDA carry no electrical pin types, so ERC could not validate anything
about the power network.

### 2.3 The ADAR1000s had no power

**8 `missing_power_pin` errors** in the PHASED_ARRAY sheet `[V]`:

```
[missing_power_pin]: Symbol U_ADR1 has input power pins in units [ B ] that are not placed
```

The B units of all eight ADAR1000s, which hold the power pins, were not placed. The chips were not
powered in the schematic.

### 2.4 The PHASED_ARRAY sheet lacked the connector it described

The only symbols instantiated in `PHASED_ARRAY.kicad_sch` were `[V]`:

- 8× `EasyEDA:ADAR1000ACCZN`
- 1× `Connector_Coaxial:SMA_EdgeMount`

The *"8-pin interface header"* the report described in two separate places **was not instantiated** —
it was only text labels. And there was **not one decoupling capacitor** for eight microwave
beamformers.

---

## 3. Component selection errors

The most serious ones, because redrawing does not fix them:

| Component | Intended use in Rev01 | Problem |
|---|---|---|
| **ADL5801** | *"Up/down-converter 10.5 GHz ↔ 50 MHz IF"* | It is a ~10 MHz to 6 GHz mixer. **It does not reach 10.5 GHz** |
| **Conversion plan** | 10.5 GHz → 50 MHz in one stage | The image would sit 100 MHz from the carrier: **0.95 % in relative frequency at 10.5 GHz**. No realisable passive filter has that selectivity. Unrecoverable with any mixer |
| **AD9767 AVDD** | Wired to the **1.8 V** rail | The AD9767 is a **3.3 V** device |
| **ADP151** | LDO 5 V → 1.8 V, *"300 mA"* | It is a **200 mA** part. And with 3.2 V of drop it would dissipate **1.6 W** in a TSOT-23-5 |
| **ADCLK944** | LVPECL outputs to converters and to the Kria | **AC coupling and a bias network were missing.** The BOM listed *"R_term 100 Ω ×4"* and nothing else: the outputs would not have switched |
| **Clock back to the Kria** | LVPECL 3.3 V over `B7-CSI2-TXD3_P/N` | A pin on a bank configured for MIPI D-PHY. **Real risk of damaging the SOM**. Also unnecessary: the ADC already provides `DCO±` |
| **ADAR1000 supply** | 5 V *"over ribbon cable"* from the carrier | ~16 W at 5 V is **>3 A through a ribbon cable**, from a 2 A buck |
| **RF switches** | 3× HMC547 | Control polarity never verified. No negative rail in the power tree |
| **No reverse-polarity protection** | — | Connecting a reversed supply destroys the board |

---

## 4. The report contradicted itself

That the document disagreed with itself is a symptom that nobody reread it end to end:

| Claim | Contradiction |
|---|---|
| *"AD9253 (dual 14-bit)"* (§1.2) | Three sections later: *"38 no-connects on unused pins (**ADC ch C/D**)"*. The AD9253 is a **quad** |
| *"AD9767 parallel CMOS 14-bit **single-channel**"* (§1.2) | *"38 no-connects… **DAC ch B**"*. The AD9767 is **dual** |
| *"Channel A = SDR, channel B = Radar IF"* (§1.1) | *"Mixer ADL5801 wired (IF± → **VIN±A** ADC)"* (Phase C). The mixer IF is the radar |
| *"8× ADAR1000"* with *"8× patch array"* | Each ADAR1000 has **4 channels**: that is 32, not 8 |
| *"Addresses 000..111 via ADDR0/ADDR1"* | Two pins give **4** addresses, not 8. And it described daisy-chain and addressing at once, which are alternatives |
| ADAR power from the carrier's +5 V (§1.4) | *"Independent 5 V/3 A supply"* for the external board (§7) |
| *"Multiband SDR: AM, FM, CB, VHF, PMR"* with *"1–50 MHz"* | FM broadcast is 88–108, VHF reaches 300, PMR446 is at 446. **None of them fits in 1–50 MHz** |
| *"Kria power: VCC5V-EXT, VCC3V3, VCC1V8, VCC1V2, VCC2V75 — both Hirose"* | The connector carries only 1V8, 2V75 and 1V2 `[V]`. `VCC5V-EXT` came from the USB-B `J1`, removed by the purge: an orphan rail |
| J_RPI pin map | Mixed logical GPIO indices (rows 1–20) with physical pin numbers (the ground row), so "14" was both `DAC_D13` and GND |

---

## 5. Outright gaps

Blocks absent without which the system cannot work:

- **Anti-alias filter** on the ADC input. Without it, everything above Nyquist folds into the band
  of interest. It is the most serious failing of the RX chain.
- **Reconstruction filter** after the DAC.
- **LNA and gain control.** An ADC with an SMA in front of it is not a receiver.
- **Band preselection.**
- **Input limiter / receiver protection during transmit.**
- **Baluns and transformers** for the converters' differential interfaces.
- **LO synthesiser.** Rev01 brought the LO in from outside over an SMA (`ANT_LO_IN`), which makes
  the equipment a bench fixture dependent on a signal generator.
- **RF distribution network** to the beamformers (an N-way splitter).
- **Gateware.** No PL content, XSA, device tree or constraints at all. *"16/16 phases complete"*
  covered schematic capture exclusively.
- **Regulatory compliance.** Not mentioned once, in equipment that transmits on regulated bands.
- **Stackup.** 4 layers, all declared `signal` `[V]`. The 50 Ω and 100 Ω netclasses added to the
  `.kicad_pro` are decorative until a stackup exists with dielectric, thicknesses and computed
  widths.

---

## 6. Corrective actions taken

| Action | Evidence |
|---|---|
| **34 empty footprints removed** from the `.kicad_pcb` | 187 → 153 footprints, **488 pads untouched**, parentheses balanced. The 5 pad-less footprints that *are* original to the import (`LA1`, `T1`, `T2`, `J5_IAS0`, `J5_IAS1`) were kept. Backup in `_backup_original/` |
| **The two dead sheets removed from the project** | `_work/rev03_drop_dead_sheets.py`. Moved to `_deprecated/`, removed from the root schematic and from `sheets[]` in the `.kicad_pro` |
| **ERC measured before and after** | **1130 → 427 violations.** `pin_to_pin` 63 → 0, `missing_power_pin` 8 → 0, `missing_unit` 8 → 0, `lib_symbol_mismatch` 25 → 0, `isolated_pin_label` 26 → 0 |
| **Repository cleaned for publication** | Broken `.history` gitlinks (submodules with no `.gitmodules` and no remote) untracked, 28 MB of KiCad autosave zips and the per-user `.kicad_prl` untracked. 67 MB → 25 MB |

### 6.1 Two findings from measuring after the cleanup

**PCB DRC is now 1909, not 1942** `[V]`. The 33-violation difference corresponds to the 34 empty
footprints removed. What remains is pre-existing Altium noise: 502 clearance, 199 track width,
199 silkscreen overlap, 199 drill out of range, 145 library footprint issues.

**The netlist cannot be exported** `[V]`. `kicad-cli sch export netlist` fails with *"the schematic
has annotation errors"*. The cause is structural: `CSI2-KRIA-KV260_Rev01-2.kicad_sch` is a
multi-channel sheet instantiated **twice** (IAS0 and IAS1), so its 19 references appear twice in the
project. It is fixed in the GUI with `Tools → Annotate Schematic`, scope *"Use sheet number (X/Y)"*.

This matters more than it looks: **until it is fixed, `Update PCB from Schematic` cannot run**, so
no schematic change can reach the layout. It is a prerequisite for phase 3 of the roadmap, and the
earlier documentation mentioned the annotation step without noting that it blocks the netlist.

---

The remaining 427 violations are pre-existing import noise: 136 off-grid endpoints, 99 library
symbols the CLI cannot resolve, and purge leftovers. **Every serious electrical category is now at
zero.**

---

## 7. What is worth keeping

Not everything is disposable. The usable work:

| Item | Value |
|---|---|
| **Purge of the original schematic** (`CSI2-KRIA-KV260_Rev01-2.kicad_sch`) | Solid and verifiable. 134 → 85 components, removing the MIPI camera electronics while keeping the Hirose, mounting holes and test points. **It is the base for Rev03** |
| **Hirose pinout** | Now verified pin by pin from the `.kicad_pcb` (§5.1 of the master document) |
| **Pinout extraction** (`_work/pinouts.txt`, 556 lines) | Real, reusable work for the components that survive |
| **Inherited board outline and stackup** | They fix the mechanical interface to the KV260 |
| `sym-lib-table` / `fp-lib-table` | The EasyEDA library registration, usable |
| `PCB/`, `Documents/` | Original Altium sources and fabrication outputs, untouched |

---

## 8. Method note

The pattern that produced these problems was **generating schematics by script and validating them
by counting ERC violations**. That fails for two reasons:

1. The symbols imported from EasyEDA carry no electrical types, so ERC cannot detect the errors
   that matter (`pin_to_pin` with everything marked `Unspecified`).
2. A schematic wired almost entirely with auto-generated labels is very hard to review visually. In
   RF, where topology and physical arrangement **are** the design, that is exactly what you cannot
   afford.

A falling ERC count does not mean the circuit is improving. It means there is less that ERC knows
how to check.
