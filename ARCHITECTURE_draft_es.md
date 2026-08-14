# KV260-IAS2RF — Informe de Arquitectura Rev03

**Placa adaptadora para AMD Kria KV260 con FPGA de front-end**
**Cadena SDR (HF / VHF / UHF) + cadena de radar 10.5 GHz sobre AERIS-10**

*Revisión 03 · 14 de agosto de 2026 · Los 5 bloqueantes del Rev02 están cerrados*

---

## 0. Por qué hay un Rev03

El Rev02 partía de: *IAS0 como camino de recepción, IAS1 como camino de transmisión, reloj
común*. Al cerrar los bloqueantes, esa premisa resultó ser irrealizable:

> **El conector IAS0 (J7) de la KV260 no llega a la lógica programable.** Sus cuatro carriles
> MIPI entran en un ISP AP1302 soldado en la carrier card. Solo **IAS1 (J8)** está cableado
> directamente al SoM.
>
> **Y no existe ninguna cabecera Raspberry Pi de 40 pines en la KV260.** J9 es un conector de
> *cámara* de 15 pines. La única expansión de propósito general es el **Pmod J2**, de 8 señales.

Evidencia completa en [docs/RIESGOS.md](docs/RIESGOS.md).

El presupuesto real de E/S entre una KV260 y una placa externa es de **8 pares diferenciales y
unas 14 señales sueltas**. Eso es un orden de magnitud menos de lo que la arquitectura anterior
suponía, y obliga a un cambio de fondo: **una FPGA de front-end en la placa adaptadora**, que es
exactamente la "placa embudo" que planteaste.

### Notación

| Marca | Significado |
|---|---|
| `[V]` | **Verificado** contra ficheros de este repositorio, de `PLFM_RADAR`, o documentación oficial citada |
| `[E]` | **Estimación** de ingeniería, a confirmar con datasheet o simulación |
| `[?]` | **Desconocido** que condiciona el diseño |

### Índice

1. [Presupuesto de E/S de la KV260](#1-presupuesto-de-es-de-la-kv260)
2. [Arquitectura: FPGA de front-end](#2-arquitectura-fpga-de-front-end)
3. [Cómo se muestrea a 400 MSPS](#3-cómo-se-muestrea-a-400-msps)
4. [Enlace con la Kria](#4-enlace-con-la-kria)
5. [Conversores y reloj](#5-conversores-y-reloj)
6. [Plan de frecuencias](#6-plan-de-frecuencias)
7. [Integración con AERIS-10](#7-integración-con-aeris-10)
8. [Reparto de procesado](#8-reparto-de-procesado)
9. [Árbol de alimentación](#9-árbol-de-alimentación)
10. [BOM Rev03](#10-bom-rev03)
11. [Alternativas a la KV260](#11-alternativas-a-la-kv260)
12. [Cumplimiento normativo](#12-cumplimiento-normativo)

---

## 1. Presupuesto de E/S de la KV260

`[V]` Verificado en UG1089 v1.0 y v1.3, y corroborado por la documentación de plataforma de AMD.

| Conector | Pares diferenciales | Single-ended | Destino |
|---|---|---|---|
| **J8 — IAS1** | **5** (4 datos + 1 reloj) | ~4 (I2C, PWDN, GPIO) | **Directo al banco HPA del SoM** |
| **J9 — cámara RPi** | **3** (2 datos + 1 reloj) | ~2 | **Directo al banco HPA del SoM** |
| **J2 — Pmod** | — | **8**, 3.3 V, 100 mA | Banco HD |
| ~~J7 — IAS0~~ | ~~4~~ | — | **Termina en el ISP AP1302** |
| **Total** | **8 pares** | **~14** | |

Tres hechos que conviene tener presentes:

- **Los pines de J8 y J9 van directamente al SoM**, sin buffers ni traductores. Son E/S de FPGA
  normales sobre un banco HP: bidireccionales y configurables como LVDS o LVCMOS.
- **Los GTH del K26 no salen a ningún conector de usuario** en la KV260. JESD204B queda
  descartado, que era la vía natural para un conversor rápido con pocos pines.
- `[?]` Falta confirmar la `VCCO` exacta del banco HPA (los bancos HP admiten 1.0–1.8 V; MIPI
  D-PHY suele implicar 1.2 V). Determina el estándar de E/S y si hace falta acoplo en AC.

### 1.1 Qué se hace con el conector IAS0 del adaptador

La placa heredada tiene dos huellas Hirose. La de IAS0 se mantiene **poblada por razones
mecánicas** (sujeción de la placa) y para tomar los raíles de 2.75 V / 1.8 V / 1.2 V, pero **sus
pares diferenciales quedan sin conectar**. `[?]` Está por ver si sus señales I2C y GPIO llegan al
SoM o al AP1302; hasta saberlo, no se cuenta con ellas.

---

## 2. Arquitectura: FPGA de front-end

Con ocho pares diferenciales no se puede conectar un conversor rápido directamente a la Kria. La
solución es poner una FPGA en la placa adaptadora que hable **ancho y corto** con los conversores
y **estrecho y rápido** con la Kria.

```
┌──────────────┐                  ┌─────────────────────────────────────────┐
│              │   J8 / IAS1      │        PLACA ADAPTADORA                 │
│  Kria KV260  │◄════ 3 pares ════│                                         │
│              │      RX          │   ┌───────────────────┐                 │
│  PL: pulse   │═════ 2 pares ═══►│   │  FPGA front-end   │◄──10 pares──ADC │
│   compress., │      TX          │   │  XC7A50T-FTG256   │                 │
│   Doppler,   │                  │   │                   │──parallel──►DAC │
│   CFAR,      │   J2 / Pmod      │   │  · captura ADC    │                 │
│   tracking   │◄──── 8 SE ──────►│   │  · DDC + diezmado │──43 líneas──►   │
│  PS: Linux,  │      control     │   │  · chirp FMCW     │      control    │
│   DPU / IA,  │                  │   │  · fan-out ADAR   │      ADAR1000   │
│   red, GUI   │   J7 / IAS0      │   │  · traducción de  │                 │
│              │◄─ solo mecánica ─│   │    niveles        │──SPI/UART──►    │
└──────────────┘   y alimentación │   └───────────────────┘   STM32 AERIS   │
                                  │   Reloj común · Alimentación · 4× SPDT  │
                                  └────────────┬──────────────┬─────────────┘
                                          IF+ctrl │           │ IF+ctrl
                                    ┌─────────────┴──┐  ┌─────┴──────────────┐
                                    │ Front-end SDR  │  │  AERIS-10          │
                                    │ (placa B)      │  │  4 ú 8× ADAR1000   │
                                    └────────────────┘  └────────────────────┘
```

### 2.1 Qué resuelve de golpe

La FPGA de front-end no es un parche: resuelve simultáneamente **los cinco problemas** que la
arquitectura anterior no podía cerrar.

| Problema | Cómo lo resuelve |
|---|---|
| Solo 8 pares hacia la Kria | Enlace serie propio, con el caudal que se decida |
| El AD9484 necesita 10 pares | Se conectan a la FPGA, que está a 2 cm |
| 43 líneas de control de los ADAR1000 | Fan-out desde la FPGA, con estrobo síncrono |
| Traducción de niveles 1.2 / 1.8 / 3.3 V | Bancos de E/S distintos de la propia FPGA |
| Diafonía al usar pares acoplados como single-ended | Desaparece: los pares se usan como LVDS, que es para lo que están |

### 2.2 Elección de la FPGA

**Recomendación: XC7A50T-2FTG256I** — exactamente la que usa AERIS-10 `[V]`.

El argumento decisivo no es técnico sino de riesgo: **todo el firmware FPGA de AERIS-10 corre en
esa pieza sin portar nada**. `ddc_400m.v`, el controlador de chirp, la compresión de pulso, el
Doppler, el MTI y el CFAR están escritos y probados para ella, con regresiones documentadas y
cierre de temporización a 400 MHz `[V]`. Su diseño ocupa 6.092 LUT (4.5 %), 9.024 FF, 16 BRAM y
140 DSP48 `[V]`: hay sitio de sobra para añadir el enlace hacia la Kria.

Alternativas si se quiere abaratar: Spartan-7 XC7S25/S50 (mismo flujo Vivado, sin transceptores,
que aquí no hacen falta). El coste sería tener que portar el firmware.

### 2.3 El coste, dicho claramente

Esto deja de ser una placa adaptadora y pasa a ser **una placa FPGA**: memoria de arranque QSPI,
alimentación multi-raíl con secuencia (VCCINT, VCCAUX, VCCO×3), JTAG, desacoplo denso, y un
segundo flujo de herramientas. Es la decisión de proyecto más importante que queda por tomar
(R-09 en [docs/RIESGOS.md](docs/RIESGOS.md)).

**La alternativa sin FPGA existe** pero es muy pobre: 2 canales a 62.5 MSPS por IAS1 (4 pares) y
un DAC de 8 bits repartido entre J9 y el Pmod con traductores. Resolución de radar de 6 m, tres
conectores distintos, y el fan-out de los ADAR1000 sin resolver. No la recomiendo.

---

## 3. Cómo se muestrea a 400 MSPS

*Respuesta directa a la pregunta.* Sí, con la placa embudo — y hay dos formas de hacerlo.

### 3.1 Embudo tonto: serializar y ya

La FPGA captura los 10 pares del AD9484 y re-serializa hacia la Kria.

| Concepto | Cálculo |
|---|---|
| Caudal bruto, 1 canal | 8 bits × 400 MSPS = **3.2 Gbps** |
| Pares disponibles hacia la Kria (IAS1) | 4 datos + 1 reloj |
| Caudal por par | 3.2 / 4 = **800 Mbps** `[E]` — cómodo para LVDS sobre banco HP |

Cabe **un canal a 400 MSPS en crudo**. Dos canales serían 6.4 Gbps, es decir 1.6 Gbps por par:
al límite, y sin margen.

Ventaja: la Kria recibe las muestras crudas y hace todo el procesado, que era tu intención
original. Inconveniente: consume el enlace entero y no deja sitio para el camino de transmisión.

### 3.2 Embudo inteligente: DDC y diezmado antes del enlace *(recomendado)*

En un radar nadie procesa la corriente cruda del ADC: lo primero que se hace es bajar a banda
base y diezmar. **AERIS ya tiene ese módulo escrito**: `ddc_400m.v`, que convierte una IF de
120 MHz muestreada a 400 MSPS `[V]`.

| Etapa | Caudal |
|---|---|
| ADC crudo, 1 canal | 8 b × 400 MSPS = 3.2 Gbps |
| Tras DDC y diezmado ÷16 | 2 × 16 b × 25 MSPS = **0.8 Gbps** |
| **2 canales** | **1.6 Gbps** |

Con 2 pares de datos hacia la Kria sobran. Y quedan pares libres para el camino de transmisión.

**Esta es la recomendación**: portar `ddc_400m.v` a la FPGA de front-end, que trabajaría en su
dominio nativo de 400 MSPS sin adaptación alguna, y enviar a la Kria I/Q diezmado.

### 3.3 Lo que se gana

| Configuración | Ancho de banda | Resolución ΔR = c/2B |
|---|---|---|
| **Con FPGA embudo (AD9484 a 400 MSPS)** | 200 MHz | **0.75 m** |
| Sin embudo, AD9253 1 canal a 125 MSPS | ~50 MHz | 3.0 m |
| Sin embudo, AD9253 2 canales a 62.5 MSPS | ~25 MHz | 6.0 m |

La FPGA embudo **recupera íntegras las prestaciones de AERIS-10**. Sin ella se pierde un factor
de 4 a 8 en resolución.

---

## 4. Enlace con la Kria

### 4.1 Reparto propuesto

Se usa **solo J8 (IAS1) y el Pmod**. J9 queda como ampliación opcional: aporta 3 pares más pero
es un FFC de 15 pines situado en otra zona de la carrier, lo que complica la mecánica (R-04).

| Recurso | Pares / señales | Uso | Caudal `[E]` |
|---|---|---|---|
| J8, pares 1–2 | 2 | **RX**: I/Q diezmado, FPGA → Kria | 2 × 1 Gbps |
| J8, par 3 | 1 | Reloj de fuente síncrona, FPGA → Kria | — |
| J8, par 4 | 1 | **TX**: banda base, Kria → FPGA | 1 Gbps |
| J8, par 5 | 1 | Reloj, Kria → FPGA | — |
| J8, single-ended | ~4 | I2C de housekeeping, reset, interrupción | — |
| Pmod J2 | 8 | SPI de control (3), estrobo de haz, PPS, 3 reserva | — |

Caudal útil: **2 Gbps de recepción y 1 Gbps de transmisión**, holgado para I/Q diezmado de dos
canales en cada sentido.

### 4.2 Protocolo

`[E]` Enlace serie propio, de fuente síncrona, DDR, con:

- palabra de alineación al inicio de trama (equivalente al `FCO` de un ADC serie);
- codificación 8b/10b **o** *scrambling*, para garantizar transiciones y permitir que el
  receptor de la Kria alinee el reloj recuperado;
- un canal de retorno para control y contadores de error.

No hace falta inventar nada: es el mismo patrón que implementa cualquier receptor serie LVDS, y
la Kria lo deserializa con `ISERDESE3`.

---

## 5. Conversores y reloj

### 5.1 ADC

**Recomendación: AD9484BCPZ-500**, el mismo que AERIS-10 `[V]`. 8 bits, hasta 500 MSPS, salida
LVDS paralela en 10 pares (`D0..D7`, `DCO`, `OR`) `[V — nets del esquemático de AERIS]`.

Ocho bits parecen pocos hasta que se recuerda que la compresión de pulso recupera el rango
dinámico: es la elección de un radar de 10.5 GHz que funciona.

> **El AD9253 queda descartado como pieza principal.** Cerrado B-02: su modo de 1 carril está
> limitado a **62.5 MSPS** (16 bits de trama × f_s ÷ carriles, con un máximo de 1000 Mbps por
> carril). Sigue siendo un buen candidato para un **segundo ADC dedicado al SDR**, donde 14 bits
> importan mucho más que la velocidad.

**Configuración de dos conversores** — es lo que mejor encaja con las dos cadenas:

| Conversor | Cadena | Bits | f_s | Justificación |
|---|---|---|---|---|
| AD9484-500 | Radar | 8 | 400 MSPS | Ancho de banda; la compresión de pulso da el rango dinámico |
| AD9253 (2 de 4 canales) | SDR | 14 | 62.5 MSPS | Rango dinámico; el SDR no necesita 400 MSPS |

Ambos cuelgan de la FPGA, que tiene E/S de sobra. Es más barato que forzar un solo conversor a
hacer dos trabajos incompatibles.

### 5.2 DAC

**AD9708AR** (8 bits, 125 MSPS), el de AERIS `[V]`, para el chirp de radar; y **AD9767** (dual
14 bits) para el SDR si se quiere calidad de transmisión. Ambos con bus paralelo **local a la
FPGA**, donde el ancho de bus ya no es un problema.

Esto elimina de raíz el compromiso del Rev02, que obligaba a 8 bits de transmisión por falta de
pines.

### 5.3 Reloj

Sin cambios respecto al Rev02, y sigue siendo correcto:

```
  ┌── SMA CLK_REF_IN ◄── AERIS-10, salida del AD9523          (modo radar)
  ├── TCXO on-board                                           (modo SDR autónomo)
  └──► Selector ──► ADCLK944 (fan-out LVPECL 1:4)
                      ├─[acoplo AC + bias]──► ADC CLK
                      ├─[acoplo AC + bias]──► DAC CLK
                      ├────────────────────► FPGA front-end
                      └────────────────────► terminada 100 Ω
```

**El reloj maestro es el AD9523 de AERIS cuando el radar está en uso** `[V]`: ya alinea en fase
las referencias del ADC, del DAC y de los dos sintetizadores ADF4382. Duplicarlo rompería esa
alineación, que es justo lo que hay que conservar para un radar coherente.

Cada salida LVPECL necesita **condensadores de acoplo y red de polarización** — lo que faltaba
en el Rev01, donde el BOM listaba solo *"R_term 100 Ω ×4"*.

---

## 6. Plan de frecuencias

### 6.1 Radar — IF de 120 MHz

`[V]` **La IF de AERIS-10 es 120 MHz** (`ddc_400m.v`, parámetro `IF_FREQ = 120_000_000`),
muestreada a 400 MSPS. Como 120 < 200 MHz, cae en la primera zona de Nyquist: muestreo directo,
sin trucos.

Y **los filtros de IF de AERIS no están especificados**: el componente `BPF2` de su BOM (2
unidades, `U$2, U$3`) tiene como número de fabricante literalmente *"Not a component"* `[V]`. No
hay hardware ajeno que modificar, y la IF es un parámetro libre si conviniera cambiarla.

### 6.2 SDR

Sin cambios respecto al Rev02. Dos caminos, en la placa B:

**Camino 1 — HF por muestreo directo, 0.1–30 MHz**
```
Antena ─ Limitador ─ Conmutador T/R ─ LPF 30 MHz ─ Atenuador ─ LNA ─► ADC SDR
```
Cubre LW/MW, SW, **CB (26.9–27.4)** y 10 m.

**Camino 2 — VHF/UHF por conversión**

| Sub-banda | LO (IF = 20 MHz) | Bandas |
|---|---|---|
| 50–70 MHz | 30–50 MHz | 6 m |
| 85–150 MHz | 65–130 MHz | **FM comercial 88–108**, aeronáutica, **2 m** |
| 400–470 MHz | 380–450 MHz | 70 cm, **PMR446 / walkie 446** |

> El *walkie* que quieres escuchar está en 446 MHz. El Rev01 declaraba cobertura *"AM, FM, CB,
> VHF, PMR"* en un rango de *"1–50 MHz"*: ninguna de esas tres bandas entra ahí. El camino 2
> existe para eso.

**Bloques que faltaban por completo en el Rev01** y siguen siendo imprescindibles: filtro
anti-alias, filtro de reconstrucción, LNA, control de ganancia, preselector, limitador de
entrada, baluns, y **sintetizador de LO** (el Rev01 lo traía de fuera por un SMA).

---

## 7. Integración con AERIS-10

### 7.1 Qué se reutiliza

| Bloque de AERIS-10 | Destino |
|---|---|
| ADAR1000, ADTR1107, array, mezcladores LTC5552, sintetizadores ADF4382, reloj AD9523 | **Se reutiliza tal cual** |
| AD9484 y AD9708 de la Main Board | Se replican en la placa adaptadora, junto a la FPGA |
| XC7A50T y su firmware | **Se conserva la pieza y el firmware**, ahora en la placa adaptadora |
| STM32F746 (housekeeping) | **Se conserva** en AERIS — ver §7.3 |

### 7.2 Control de los ADAR1000

`[V]` AERIS da a cada chip cuatro líneas propias: `ADAR_n_CS`, `ADAR_TX_LOAD_n`,
`ADAR_RX_LOAD_n`, `ADAR_TR_n`, más `TR_SW_POS_n` por grupo y el SPI compartido.

| | 4 chips (Nexus) | 8 chips (Extended) |
|---|---|---|
| Total de señales | 23 | **43** |

Se dimensiona para **8 chips / 32 canales**. Con la FPGA de front-end esto deja de ser un
problema: 43 salidas son triviales para un FTG256, y además permite **aplicarlas todas con un
estrobo síncrono**, que es exactamente la semántica que quiere un array coherente. La Kria envía
un comando compacto por el Pmod y la FPGA lo expande.

`[?]` **B-05 sigue parcialmente abierto**: la Main Board publicada de AERIS lleva 4 ADAR1000, y
su README menciona 16 placas de PA para la variante Extended (que encajan con 16 canales, no 32).
Conviene confirmarlo con el autor antes de congelar el conector.

### 7.3 Por qué conservar el STM32 de AERIS

`[V]` El STM32 hace el **secuenciado de encendido y apagado** y la calibración de corriente de
reposo de los amplificadores, mediante 2× DAC5578 y 2× ADS7830 con INA241A3.

Un fallo de secuencia **destruye los amplificadores GaN**. Ese código existe, funciona y está
probado. Reparto por requisito temporal:

| Función | Quién |
|---|---|
| Secuenciado, calibración de Idq, GPS, IMU, térmica | **STM32 de AERIS** |
| SPI de haz, `LOAD`, `TR` (actualización pulso a pulso) | **FPGA de front-end** |
| Captura de ADC, DDC, diezmado, generación de chirp | **FPGA de front-end** |
| Compresión de pulso, Doppler, MTI, CFAR, seguimiento, IA | **Kria** |

### 7.4 Conmutadores de enrutado

`[V]` **B-03 cerrado a favor:** el `M3SWA2-34DR+` es un SPDT absortivo GaAs con **driver
interno**, DC–30 GHz, alimentación de 3.3–3.6 V. Control lógico positivo: **no hace falta raíl
negativo**. Se elimina el inversor de carga del árbol de alimentación.

Cuatro SPDT en el adaptador permiten reasignar cada canal de conversor entre la cadena SDR y la
de radar, habilitando modo mixto, SDR I/Q y **radar I/Q** (necesario para distinguir el signo del
Doppler).

---

## 8. Reparto de procesado

Con la FPGA de front-end, la pregunta legítima es *«¿y entonces para qué está la Kria?»*. La
respuesta es que cada una hace lo suyo:

| FPGA de front-end (XC7A50T) | Kria KV260 (K26) |
|---|---|
| Captura del ADC a 400 MSPS | Compresión de pulso |
| DDC, diezmado, filtrado CIC/FIR | FFT de Doppler, MTI, CFAR |
| Generación del chirp y control del DAC | Seguimiento de blancos |
| Fan-out y estrobo de los ADAR1000 | **Inferencia sobre el DPU**: clasificación de blancos |
| Traducción de niveles | Linux, red, almacenamiento, interfaz de usuario |
| *Firmware de AERIS, casi sin portar* | *Sustituye al PC con GUI Python de AERIS* |

Ese último punto es el valor real: AERIS termina en un enlace USB hacia un PC con una GUI en
Python. Con la Kria tienes un SoC empotrado con cuatro Cortex-A53, DPU para inferencia y red,
justo detrás del radar.

---

## 9. Árbol de alimentación

```
Jack 12 V DC (≥ 3 A)
  ├── TVS SMBJ15A · PTC 3 A · MOSFET-P en diodo ideal   ← protección de polaridad, faltaba
  └── Buck 12 V → 5 V / 3 A ─────────────────── +5V
        ├── Buck 5 V → 3.3 V / 2 A ──── +3V3_D    lógica, conmutadores, ADCLK944, TCXO
        ├── LDO  5 V → 3.3 V / 300 mA ─ +3V3_A    analógico, tras ferrita
        ├── (desde +3V3_A) LDO → 1.8 V ─ +1V8_A   AVDD de los ADC
        └── Alimentación de la FPGA  ← NUEVO, con secuencia
              ├── VCCINT 1.0 V / 2 A
              ├── VCCAUX 1.8 V / 500 mA
              └── VCCO ×3 bancos (1.2 / 1.8 / 3.3 V)
```

La alimentación de la FPGA es lo que más crece respecto al Rev02: exige **secuencia de arranque**
y bastante corriente en VCCINT. Un controlador de secuencia o un PMIC integrado resuelve esto de
forma limpia.

### 9.1 Correcciones que siguen vigentes del Rev01

| Rev01 | Problema | Rev03 |
|---|---|---|
| `ADP151` como LDO de 1.8 V, *"300 mA"* | Es de **200 mA**, y con 3.2 V de caída disipa 1.6 W en TSOT-23-5 | LDO de ≥ 500 mA con thermal pad, alimentado **desde 3.3 V** |
| `AD9767 AVDD` al raíl de 1.8 V | El AD9767 es de **3.3 V** | A `+3V3_A` |
| Un solo raíl de 3.3 V | Ruido digital sobre las referencias analógicas | `+3V3_D` y `+3V3_A` separados |
| Sin protección de polaridad | Una fuente invertida destruye la placa | MOSFET-P en diodo ideal |
| ADAR1000 alimentados por cable plano desde el +5 V | >3 A por un cable plano | AERIS se alimenta sola |
| Raíles del Hirose usados como fuente | Corriente disponible desconocida | No se usan como fuente de potencia |

---

## 10. BOM Rev03

**C** = confirmado · **X** = candidato razonado · **P** = pendiente · **D** = descartado.

| Ref | Función | Parte | Estado | Nota |
|---|---|---|---|---|
| `U_FPGA1` | FPGA de front-end | XC7A50T-2FTG256I | X | La misma que AERIS `[V]`: su firmware corre sin portar |
| `U_CFG1` | Flash de configuración | QSPI 32 Mb | P | |
| `U_ADC1` | ADC de radar | AD9484BCPZ-500 | X | 8 b / 400 MSPS, el de AERIS `[V]` |
| `U_ADC2` | ADC de SDR | AD9253BCPZ-125 | X | 14 b, 2 de 4 canales, ≤62.5 MSPS en 1-lane |
| `U_DAC1` | DAC de radar | AD9708AR | X | El de AERIS `[V]` |
| `U_DAC2` | DAC de SDR | AD9767ASTZ | X | Dual 14 b, 3.3 V |
| `U_AMP1..2` | Drivers diferenciales de entrada | AD8352ACPZ | X | Los usa AERIS `[V]` |
| `U_CLK1` | Fan-out LVPECL 1:4 | ADCLK944BCPZ-R2 | C | Con acoplo AC + bias |
| `Y_CLK1` | TCXO, modo autónomo | ±0.5 ppm | P | |
| `U_SW1..4` | SPDT de enrutado | M3SWA2-34DR+ | X | Control positivo 3.3 V, confirmado |
| `U_PWR*` | Bucks, LDO y secuenciador | — | P | Incluye alimentación de FPGA |
| `Q_REV1` | Protección de polaridad | MOSFET-P + Zener | P | |
| `D_TVS1` | TVS | SMBJ15A | C | |
| `J_PWR1` | Jack de alimentación | PJ-102AH | C | |
| `J8` ×2 | Hirose BM20B(0.8)-34DP | — | C | IAS1 funcional; IAS0 solo mecánico y alimentación |
| `J_PMOD1` | Cable al Pmod J2 de la KV260 | 2×6, 2.54 mm | P | |
| `J_IF*` | SMA de IF y reloj | Edge-mount | P | |
| `J_EXT1` | IDC 2×20 hacia AERIS | — | P | Hasta 8 ADAR1000 |
| ~~`U_MIX1`~~ | ~~ADL5801~~ | | **D** | No llega a 10.5 GHz; el mezclado lo hace AERIS |
| ~~`U_PWR3`~~ | ~~ADP151~~ | | **D** | 200 mA insuficientes |
| ~~`U_INV1`~~ | ~~LM2663~~ | | **D** | Innecesario: B-03 cerrado a favor |
| ~~`U_DEC1`~~ | ~~74HC138~~ | | **D** | El fan-out lo hace la FPGA |
| ~~8× `U_ADR`~~ | ~~ADAR1000~~ | | **D** | Los aporta AERIS |

---

## 11. Alternativas a la KV260

Conviene decirlo con claridad: **la KV260 es una plataforma pobre en E/S para este proyecto.**
Ocho pares diferenciales y catorce señales sueltas es muy poco. Si el objetivo real es el radar,
merece la pena valorar:

| Opción | E/S disponible | Coste |
|---|---|---|
| **KV260 + FPGA de front-end** *(esta arquitectura)* | 8 pares, enlace serie propio | Una FPGA en el adaptador |
| **KR260** (Robotics Starter Kit) | 4× Pmod, Ethernet de PL, más E/S | Cambiar de placa |
| **Carrier propia para el SoM K26** | ~180 E/S de usuario + **4 carriles GTH a 12.5 Gb/s** | Diseñar una carrier de 240 pines |

La tercera habilita JESD204B y elimina toda esta gimnasia, a cambio de un proyecto bastante
mayor. No la propongo, pero debe estar sobre la mesa antes de comprometerse.

---

## 12. Cumplimiento normativo

| Subsistema | Situación |
|---|---|
| **RX** | Sin restricción de emisión. Vigilar la reemisión del LO por la antena `[E]` |
| **TX SDR** | Requiere **licencia de radioaficionado** y ceñirse a bandas asignadas. FM comercial, aeronáutica y PMR446 son de **solo recepción** aquí |
| **TX 10.5 GHz** | `[?]` **Verificar el cuadro nacional de atribución.** No es banda ISM libre en todos los países. Con amplificadores GaN de 10 W por canal, la variante Extended no se enciende sin más |
| **CEM** | Un prototipo de banco no requiere marcado CE; distribuir el equipo sí |

**Recomendación de diseño:** cargas de 50 Ω conmutables en las salidas de TX, para validar todo
el sistema en *loopback* conducido sin radiar. Cuesta casi nada y desbloquea la puesta en marcha
sin depender de una licencia.

---

## 13. Documentos relacionados

| Documento | Contenido |
|---|---|
| [docs/RIESGOS.md](docs/RIESGOS.md) | Los 5 bloqueantes cerrados, con evidencia y fuentes, más los riesgos abiertos |
| [docs/AUDITORIA_Rev01.md](docs/AUDITORIA_Rev01.md) | Qué contienen realmente los ficheros del repositorio |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Plan por fases con criterios de salida |
| [docs/HISTORIAL_Rev01.md](docs/HISTORIAL_Rev01.md) | Registro del trabajo previo y su valoración |

---

*Rev03 · 14 de agosto de 2026. La decisión pendiente es §2.3: si se acepta la FPGA de front-end.
De esa respuesta depende todo el esquemático.*
