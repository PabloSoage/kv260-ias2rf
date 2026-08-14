# INFORME DE ARQUITECTURA Y DESARROLLO: ADAPTADOR KV260-IAS2RF (SDR + RADAR PHASED ARRAY)

## 0. Objetivo del Proyecto

Desarrollar una placa adaptadora (*Carrier Board* pasiva/activa) para la **AMD Kria KV260** que actúe como *Front-End* de radiofrecuencia unificado, gestionando de forma síncrona la transmisión (TX) y recepción (RX) para:

- **SDR multi-banda:** AM, FM, CB, VHF, PMR (1–50 MHz)
- **Radar Phased Array:** 10.5 GHz banda X con beamforming electrónico (8× ADAR1000)

### Punto de partida

Proyecto KiCad 10 (`CSI2-KRIA-KV260_Rev01`) importado desde Altium — placa adaptadora de cámaras MIPI Allied Vision con:
- 2 conectores Hirose BM20B(0.8)-34DP (IAS0 e IAS1) hacia la Kria KV260
- Conectores FFC/FPC MIPI (FH55-22S-0.5SH), reguladores, *level shifters* I2C/GPIO y alimentación USB para control de óptica y sensores

### Decisiones de diseño clave

| Decisión | Motivo |
|---|---|
| **ADC cambiado de AD9268 a AD9253** | Serial-LVDS 1-lane por canal → 4 pares para 2 canales (cabe en IAS0) |
| **DAC cambiado de AD9779 a AD9767** | CMOS paralelo 14-bit vía cabezal RPi 40-pin de la Kria (28 GPIO disponibles) |
| **8× ADAR1000 a placa externa** | 10.5 GHz + 20W térmicos → sustrato Rogers obligatorio; inviable en FR4 |
| **Clock buffer ADCLK944 añadido** | Fan-out LVPECL 1:4 ultrabajo jitter (50 fs) para sincronizar ADC, DAC y Kria |
| **Alimentación independiente** | Barrel jack 12V DC → bucks onboard; no se alimenta desde los Hirose |

---

## 1. Arquitectura Final — Placa Carrier KV260-IAS2RF

### 1.1 Hoja 1: IAS0/IAS1 (conexión física a la Kria KV260)

Archivo: `CSI2-KRIA-KV260_Rev01-2.kicad_sch` — multi-channel reutilizado para las 2 instancias.

| Subsistema | Chip | Pines Hirose | Función |
|---|---|---|---|
| **RX ADC** | AD9253BCPZ-125 (dual 14-bit, Serial-LVDS 1-lane) | IAS0: 4 pares (D0±A, D0±B, DCO±, FCO±) | Canal A=SDR, Canal B=Radar IF |
| **Clock retorno** | ADCLK944 Q2± | IAS0: 1 par (B7-CSI2-TXD3_P/N) | Reloj maestro 125 MHz devuelto a la Kria |
| **Control SPI** | I2C_SCL_3V3, I2C_SDA_3V3, EXT-GPIO2 | IAS0: pines GPIO reutilizados | Configuración ADC |
| **Power Kria** | VCC5V-EXT, VCC3V3, VCC1V8, VCC1V2, VCC2V75 | Ambos Hirose | Solo I/O baja potencia |

### 1.2 Hoja 2: FRONTEND (electrónica de la placa adaptadora)

Archivo: `FRONTEND.kicad_sch` — hoja plana con 14 chips + conectores + bypass.

| Bloque | Componentes | Detalle |
|---|---|---|
| **Power Tree** | Barrel PJ-102AH → TVS SMBJ15A → TPS54202 (12V→5V) → TPS82140 (5V→3V3) → ADP151 (5V→1V8) | Independiente del Hirose |
| **Master Clock** | TCXO 8132H 125MHz + ADCLK944BCPZ-R2 | 4 salidas LVPECL (ADC, DAC, Kria, terminada) |
| **RX ADC** | AD9253BCPZ-125 | Serial-LVDS 1-lane dual-channel 14-bit |
| **TX DAC** | AD9767ASTZ | CMOS paralelo 14-bit single-channel |
| **Mezclador RF** | ADL5801ACPZ | Up/down-converter 10.5 GHz ↔ IF 50 MHz |
| **RF Switching** | 3× HMC547ALC3TR (SPDT) | Multiplexación bandas SDR + duplexor T/R + ruta Radar |
| **Interfaz RPi** | J_RPI 40-pin hembra 2.54mm | 14 GPIO datos DAC + 1 WRCLK + 4 control + 8 GND |
| **Conectores SMA** | 4× SMA edge-mount | ANT_SDR_RX, ANT_SDR_TX, ANT_LO_IN, ANT_RADAR_RF |
| **Bypass** | 16× CF1..CF16 (100n/10µ/47µ) | Decoupling en todos los rails |

### 1.3 Hoja 3: PHASED_ARRAY (placa externa de alta frecuencia)

Archivo: `PHASED_ARRAY.kicad_sch` — 8 ADAR1000 + SPI daisy-chain + SMA RF.

| Bloque | Componentes | Detalle |
|---|---|---|
| **8× Beamformers** | ADAR1000ACCZN ×8 | Direcciones 000..111 por ADDR0/ADDR1 hardwired |
| **SPI Daisy-Chain** | SCLK, CSB compartidos; SDIO→SDO en cadena | Control desde J_RPI de la Carrier |
| **Control T/R** | TR_CTRL, TX_LOAD comunes | Sincronización de haz |
| **RF** | 1× SMA_RF_IN | Entrada combinada 10.5 GHz desde la Carrier |
| **Antenas** | 8× RF_ANT_1..8 labels | Salidas individuales a patch array |
| **Interfaz** | Header 8 pines (VCC5V, GND, SCLK, CSB, SDIO_IN, SDO_8, TR_CTRL, TX_LOAD) | Cable plano hacia J_RPI de la Carrier |

### 1.4 Árbol de tensiones

```
Barrel Jack (12V DC, ≥1A)
  ├── TVS SMBJ15A (protección)
  ├── Fuse PTC 1.1A
  └── TPS54202DDCR (Buck 12V→5V/2A) → VCC5V_RAW
        ├── ADL5801 VPOS, HMC547 VDD, ADAR1000 (vía cable plano a placa externa)
        ├── TPS82140SILR (Buck 5V→3V3/1A) → VCC3V3_RAW
        │     └── AD9253 DRVDD, AD9767 DVDD, ADCLK944 VDD, TCXO VCC
        └── ADP151AUJZ-1.8 (LDO 5V→1V8/300mA) → VCC1V8_RAW
              └── AD9253 AVDD, AD9767 AVDD
```

*Nota:* VCC5V-EXT, VCC3V3, VCC1V8, VCC1V2, VCC2V75 del Hirose Kria se conservan solo para I/O de baja potencia.

### 1.5 Mapeo J_RPI 40-pin (GPIO → DAC + Control)

| GPIO RPi | Señal | Función |
|---|---|---|
| 1-14 | DAC_D00..DAC_D13 | Bus paralelo DAC (14 bits) |
| 15 | DAC_WRT | Write strobe |
| 16 | SPI_SCLK_EXT | SPI clock (placa externa) |
| 17 | SPI_SDIO_EXT | SPI data in (placa externa) |
| 18 | SPI_CSB_EXT | SPI chip select (placa externa) |
| 19 | TR_CTRL_EXT | T/R control |
| 20 | TX_LOAD_EXT | Latch datos TX |
| 6,9,14,20,25,30,34,39 | GND | Retorno de masa obligatorio |

### 1.6 Arquitectura de hojas KiCad

```
CSI2-KRIA-KV260_Rev01.kicad_pro
├── Hoja "IAS0" ──┐
│                 ├── CSI2-KRIA-KV260_Rev01-2.kicad_sch (multi-channel ×2)
├── Hoja "IAS1" ──┘    2× Hirose BM20B-34DP (purgado de cámaras MIPI)
├── Hoja "FRONTEND" → FRONTEND.kicad_sch
│     14 chips: power tree + clock + ADC + DAC + mixer + 3×RF switches + J_RPI + 4×SMA + 16 caps
└── Hoja "PHASED_ARRAY" → PHASED_ARRAY.kicad_sch
      8× ADAR1000 + SPI daisy-chain + SMA_RF_IN + header interfaz
```

---

## 2. Historial de Fases

### Phase A — Purga del esquema original (`-2.kicad_sch`)

**Objetivo:** Eliminar componentes de cámara MIPI, conservando Hirose + alimentación Kria.

| Acción | Detalle |
|---|---|
| **Borrado directo (15 bloques)** | J1 (USB-B), J7 (FFC22 MIPI), J2/J5/J6/J9/J10 (headers), U1 (INA260), U2 (TPS25200), U3 (PCA9306 level shifter I2C), U4 (NTB0104 level shifter), U5 (NCP114 LDO), D1 (ESD), D2/D3 (LEDs) |
| **Borrado cascada (34 R/C)** | 4 iteraciones ERC → 24+7+2+1 resistencias y condensadores huérfanos |
| **Limpieza wires** | 133 wires + 22 junctions colgados eliminados mediante coordenadas del informe ERC |
| **Conservado** | J8 (Hirose ×2), X1 (mount hole), TP1-6, MRK1-6, PCB1, LA1, T1/T2, 66 power symbols |

**Métricas:** 134 → 85 componentes (−49) · 29.298 → ~19.430 líneas (−9.868) · ERC 774 → 396

### Phase B — Extracción de pinouts

Pinouts de **15 chips** extraídos de `C:\Users\pablo\KiCad\EasyEDA.kicad_sym` y documentados en `_work/pinouts.txt` (556 líneas). Creados `sym-lib-table` y `fp-lib-table` en el proyecto apuntando a `${KICAD_3RD_PARTY}/EasyEDA`.

### Phase C — Construcción de FRONTEND.kicad_sch

Generación del archivo con Python (`phaseC_gen_frontend.py`):
- **14 instancias** de chips EasyEDA con lib_symbols inlined y propiedades correctas
- **60 hierarchical labels** para exponer nets al sheet padre
- **Power tree** cableado con labels (12V_RAW → 5V_RAW → 3V3_RAW → 1V8_RAW)
- **Master Clock** cableado (TCXO → ADCLK944 → 3 salidas)
- **ADC AD9253** cableado (canal A=SDR en D0±A, canal B=Radar en D0±B, DCO±, FCO±, SPI, CLK)
- **DAC AD9767** cableado (14 bits paralelo, WRT, CLK, SLEEP)
- **Mixer ADL5801** cableado (IF± → VIN±A ADC, LO± → labels, RF± → RF switches)
- **3× HMC547** cableados con labels de control y GND
- **J_RPI** 40-pin: 14 GPIO datos + WRCLK + 8 GND oficiales + 4 GPIO control
- **4× SMA** global labels + instancias edge-mount
- **16× bypass caps** (CF1..CF16) 100n/10µ/47µ en todos los rails
- **38 no-connect** en pines no usados (ADC ch C/D, DAC ch B)
- **17 wires visuales** en power chain + clock chain
- **Labels interfaz SPI externa** (SPI_SCLK_EXT, SPI_SDIO_EXT, SPI_CSB_EXT, TR_CTRL_EXT, TX_LOAD_EXT)

### Phase D — Sincronización jerárquica y netclasses

- **54 labels locales** de `-2.kicad_sch` convertidos a `hierarchical_label` para exponer nets al padre
- **13 sheet pins** añadidos a bloques IAS0 y FRONTEND en el esquema raíz
- **Netclass "50 Ohm"** añadida a `.kicad_pro` con patrones `ANT_*`, `MIX_*`, `RF_SW*`
- **Netclass "100 Ohm"** ampliada con patrones `CLK_ADC_*`, `CLK_DAC_*`, `CLK_KRIA_*`, `B7-CSI2-*`

### Phase E — Hoja PHASED_ARRAY (placa externa)

Generación de `PHASED_ARRAY.kicad_sch` con Python (`phaseE_phased_array.py`):
- 8× ADAR1000ACCZN con símbolo importado de EasyEDA
- SPI daisy-chain completo (SCLK y CSB compartidos; SDO→SDIO en cadena)
- ADDR0/ADDR1 hardwired a GND/VCC3V3 para addressing binario
- TR_CTRL y TX_LOAD comunes a los 8 chips
- 8× labels RF_ANT_1..8 para conexión al patch array
- 1× SMA_RF_IN para entrada combinada de RF desde la Carrier
- Header de interfaz de 8 pines hacia cable plano desde J_RPI
- Añadida como 4ª sub-hoja al proyecto (`.kicad_pro sheets[]`, root `sheet` block)

### Phase F — Placement en PCB y verificación

- **34 footprints** colocados en `CSI2-KRIA-KV260_Rev01.kicad_pcb`:
  - 14 chips (power tree + clock + ADC + DAC + mixer + 3×switches + J_RPI)
  - 4× SMA edge-mount
  - 16× bypass capacitors (CF1..CF16)
- Posiciones sobre zona libre (Y > 145mm, sobre los componentes existentes)
- **PCB DRC**: 1.942 violaciones, **0 elementos desconectados**
- **Anotación**: power symbols anotados (#PWR01..#PWR0151), componentes principales (U_ADC1, U_DAC1, etc.)
- **Caps renombrados** C_BP* → CF* para evitar conflictos con C1..C52 de la sub-hoja IAS0/IAS1

---

## 3. Estado ERC/DRC Final

### ERC (Electrical Rules Check) — 1.129 infracciones

| Infracción | Cantidad | Origen |
|---|---|---|
| pin_not_connected | ~444 | Pines sin conectar (canales extra ADC, canal B DAC, Hirose, ADAR1000) |
| endpoint_off_grid | ~196 | Preexistente: import Altium fuera de grid 50mil |
| lib_symbol_issues | ~118 | Preexistente: CLi no carga librerías externas |
| label_dangling | ~102 | Labels protegidos + hlabels sin driver (esperado en multi-channel) |
| hier_label_mismatch | ~43 | Pins de sheet no sincronizados |
| GND_BAR / VCC*_CIRCLE | ~59 | Preexistente: símbolos de poder heredados |
| Resto | ~167 | Preexistente: footprint_link_issues, no_connect_dangling, etc. |

*La mayoría de infracciones (≈70%) son preexistentes del import Altium y warnings benignos de CLI.*

### PCB DRC — 1.942 violaciones · 0 elementos desconectados

- Violaciones preexistentes del diseño Altium original
- **Ningún net desconectado** — la conectividad eléctrica es correcta

---

## 4. Instrucciones para la GUI de KiCad

### Anotación multi-channel (IAS0/IAS1)

Los componentes de la hoja `-2.kicad_sch` (compartida por IAS0 e IAS1) tienen referencias duplicadas. Solución:

1. `Tools → Annotate Schematic`
2. Scope: **"Use sheet number (X/Y)"** o **"Reset and use sheet number"**
3. Pulsar **Annotate**

KiCad asignará automáticamente sufijos: `C3` → `C3_IAS0` / `C3_IAS1`, `J8` → `J8_IAS0` / `J8_IAS1`, etc.

### Conexiones visuales

El esquema usa **labels** (etiquetas de texto con nombre de net) para las conexiones entre componentes. Dos labels con el mismo nombre = mismo net eléctrico. Se han añadido **17 wires visuales** en las cadenas principales (power tree + clock + ADC/DAC) para facilitar la lectura.

### Sincronización de sheet pins

En la hoja raíz, seleccionar cada bloque de sub-hoja y usar `Synchronize Hierarchical Labels` para que KiCad añada automáticamente los pines de sheet que faltan.

---

## 5. Archivos del Proyecto

| Archivo | Descripción | Estado |
|---|---|---|
| `CSI2-KRIA-KV260_Rev01.kicad_pro` | Proyecto KiCad 10 (4 hojas, netclasses) | ✅ |
| `CSI2-KRIA-KV260_Rev01.kicad_sch` | Hoja raíz (4 sub-hojas) | ✅ |
| `CSI2-KRIA-KV260_Rev01-2.kicad_sch` | IAS0/IAS1 multi-channel (purgado) | ✅ |
| `FRONTEND.kicad_sch` | 14 chips + power + SMA + J_RPI + caps | ✅ |
| `PHASED_ARRAY.kicad_sch` | 8× ADAR1000 + SPI daisy-chain | ✅ |
| `CSI2-KRIA-KV260_Rev01.kicad_pcb` | PCB con 34 nuevos footprints | ✅ |
| `sym-lib-table` | Librería EasyEDA registrada | ✅ |
| `fp-lib-table` | Huellas EasyEDA registradas | ✅ |
| `ARCHITECTURE_draft_es.md` | Este documento | ✅ |
| `_backup_original/` | Backups de archivos originales + post-purga | ✅ |
| `_work/` | Scripts Python de todas las fases | ✅ |

---

## 6. BOM — Bill of Materials

### Carrier KV260-IAS2RF (a soldar en esta placa)

| Cant. | Ref | Parte | Encapsulado | LCSC |
|---|---|---|---|---|
| 1 | U_ADC1 | AD9253BCPZ-125 | LFCSP-48 | C514282 |
| 1 | U_DAC1 | AD9767ASTZ | LQFP-48 | C578873 |
| 1 | U_CLK1 | ADCLK944BCPZ-R2 | LFCSP-16 | (Mouser) |
| 1 | Y_CLK1 | 8132H-T125.000LJ33DT | SMD 3.2×2.5mm | (Digikey) |
| 1 | U_MIX1 | ADL5801ACPZ | LFCSP-24 | (Mouser) |
| 3 | U_SW1..3 | HMC547ALC3TR | QFN-16 | (Mouser) |
| 1 | U_PWR1 | TPS54202DDCR | SOT-23-6 | C191884 |
| 1 | U_PWR2 | TPS82140SILR | USIP-8 | C544385 |
| 1 | U_PWR3 | ADP151AUJZ-1.8-R7 | TSOT-23-5 | C462184 |
| 1 | D_TVS1 | SMBJ15A | SMB | C83846 |
| 1 | J_PWR1 | PJ-102AH | Through-hole | C3096093 |
| 1 | J_RPI1 | PinHeader 2×20 2.54mm | Through-hole | — |
| 4 | J_SMA1..4 | SMA edge-mount | Through-hole | — |
| 16 | CF1..CF16 | MLCC 0603/0805 | SMD | — |
| — | R_term | 100Ω ×4 (LVPECL) | 0603 | — |
| — | L_buck | 10µH inductor | SMD | — |

### Placa Externa "Phased Array" (diseño futuro, no en esta PCB)

| Cant. | Ref | Parte | Encapsulado |
|---|---|---|---|
| 8 | U_ADR1..8 | ADAR1000ACCZN | LGA-88 |
| 1 | J_SMA_RF | SMA edge-mount | — |
| 1 | Header IDC | 2×10 o FPC 20-pin | — |
| — | Antenas | 8× patch array | Rogers |

---

## 7. Placa Externa — Especificaciones para diseño futuro

Los 8 ADAR1000 van en placa separada porque 10.5 GHz + 20W disipación requieren sustrato Rogers, inviable en FR4.

### Especificaciones técnicas

| Parámetro | Valor |
|---|---|
| Sustrato | Rogers RO4350B (capa superior) + FR4 (inferiores) |
| Stackup | 6 capas: SIG_TOP / GND / SIG / PWR / GND / SIG_BOT |
| Espesor Rogers | 0.254 mm (10 mil) |
| Antenas | 8× patch array lineal o Vivaldi |
| Dimensiones | ~120 × 80 mm |
| Alimentación | Fuente 5V/3A independiente |

### Interfaz con la Carrier

| Conexión | Tipo | Señales |
|---|---|---|
| RF 10.5 GHz | Cable SMA-SMA | ANT_RADAR_RF ↔ combinador Wilkinson |
| Control digital | Cable plano 8-pin | SPI_SCLK, SPI_CSB, SPI_SDIO_IN, SPI_SDO_8, TR_CTRL, TX_LOAD, VCC5V, GND |

### Ruteo SPI en placa externa

```
J_RPI (Carrier) → cable plano → Header placa externa
    ├── SCLK, CSB, TR_CTRL, TX_LOAD → común a los 8 ADAR1000
    ├── SDIO_IN → ADAR1000#1 SDIO
    ├── ADR1 SDO → ADR2 SDIO → ... → ADR8 SDIO (daisy-chain)
    └── ADR8 SDO → SPI_SDO_8 (readback opcional a Carrier)
```

---

*Documento final — 3 de agosto de 2026. Proyecto KV260-IAS2RF: 16/16 fases completadas.*
*ERC: 1.129 infracciones · DRC: 1.942 violaciones, 0 elementos desconectados.*