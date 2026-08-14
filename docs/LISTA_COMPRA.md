# Lista de la compra y checklist

*14 de agosto de 2026 · Plataforma 4×4 sobre Kria KV260*

Organizada por **etapas** (ver el orden razonado en [PLATAFORMA_4X4.md](PLATAFORMA_4X4.md) §6).
Cada etapa entrega algo utilizable por sí sola.

**Los precios son orientativos `[E]`**, para dimensionar el esfuerzo — no son cotizaciones. IVA
español del 21 % incluido donde aplica.

**Leyenda:** ☑ ya lo tienes · ☐ por comprar · ◆ por diseñar/fabricar · ⚑ trámite

---

## Etapa 0 — Empezar hoy, sin diseñar nada

> **La etapa más importante del proyecto.** No diseñes una placa para averiguar qué necesitas.

| | Artículo | Para qué | Precio `[E]` |
|---|---|---|---|
| ☑ | **Kria KV260** | El cerebro | *ya comprada, €300* |
| ☐ | Fuente 12 V / 3 A o adaptador de a bordo | Alimentar la KV260 | €20 |
| ☐ | microSD 32–64 GB clase A2 | Arranque de Linux | €15 |
| ☐ | SSD USB 3.0 (256 GB+) | Grabar capturas de RF y nubes de puntos | €40 |
| ☐ | **HackRF One** (1 MHz – 6 GHz, TX/RX) | Escuchar **y** cubrir 2.4 y 5.8 GHz de drones | €300 |
| ☐ | Upconverter HF (Ham It Up o similar) | HF decente con el HackRF | €60 |
| ☐ | **KrakenSDR** (5 canales coherentes, 24 MHz – 1.766 GHz) | **Radiogoniometría lista para usar** | €500 |
| ☐ | Juego de antenas: discono, HF de látigo, 5×VHF/UHF para el Kraken | Cobertura y DF | €200 |
| ☐ | GPS USB (u-blox) + IMU | Posición y rumbo para triangular y para SLAM | €80 |
| | | **Subtotal** | **~€1.200** |

**Checklist de etapa 0**
- [ ] Ubuntu/PetaLinux arrancando en la KV260
- [ ] HackRF reconocido por USB; captura con GNU Radio o SoapySDR
- [ ] Escuchar FM, aeronáutica y PMR446 desde el vehículo
- [ ] Detectar un dron por su emisión de 5.8 GHz
- [ ] KrakenSDR dando marcaciones; triangular una fuente desplazando el coche
- [ ] **Anotar qué te limita de verdad** ← el entregable real de esta etapa

---

## Etapa 1 — LiDAR

| | Artículo | Notas | Precio `[E]` |
|---|---|---|---|
| ☐ | **LiDAR 3D**: Livox Mid-360 (360°×59°, Ethernet) o Unitree L2 (360°×96°) | Driver ROS2 oficial; SLAM abierto (FAST-LIO2) | €600 – 900 |
| ☐ | Switch Gigabit industrial o cable directo | El LiDAR va por Ethernet | €30 |
| ☐ | Soporte de barra / baca con amortiguación | Vibración | €80 |
| ☐ | Cableado apantallado y pasamuros | Instalación limpia | €50 |
| | | **Subtotal** | **~€800 – 1.100** |

**Checklist**
- [ ] Nube de puntos llegando a la Kria por Ethernet
- [ ] ROS2 + driver del LiDAR corriendo
- [ ] SLAM básico funcionando parado
- [ ] SLAM con odometría del vehículo (necesita la etapa 2)
- [ ] Segmentación suelo/obstáculo **en el DPU**
- [ ] Render 3D del terreno por delante y "memoria" de lo que pasa bajo los bajos

---

## Etapa 2 — OBD2 / CAN

| | Artículo | Notas | Precio `[E]` |
|---|---|---|---|
| ☑ | **Scanmatik 3** | **Solo para el portátil, en el taller.** No tiene soporte Linux/aarch64 | *ya lo tienes* |
| ☐ | **Adaptador USB-CAN con SocketCAN** (CANable 2.0, PCAN-USB) | Lo que va a bordo, permanentemente | €30 – 250 |
| ☐ | Latiguillo OBD2 a DB9/CAN | Conexión al puerto | €20 |
| | | **Subtotal** | **~€50 – 270** |

**Checklist**
- [ ] `can0` levantado con SocketCAN en la Kria
- [ ] Tramas capturadas con `candump`
- [ ] Confirmado que el V80 usa ISO 15765-4 sobre CAN
- [ ] Identificados los PID de velocidad de rueda, RPM, temperaturas
- [ ] **Odometría publicada hacia el SLAM del LiDAR**
- [ ] Registro persistente en el SSD

---

## Etapa 3 — Comunicación de verdad (⚑ y ☐)

> Independiente del proyecto, a propósito. Ver [PLATAFORMA_4X4.md](PLATAFORMA_4X4.md) §2.3.

| | Artículo | Notas | Precio `[E]` |
|---|---|---|---|
| ⚑ | **Licencia de radioaficionado** | **Empieza ya**: el trámite tarda meses. Estudio + examen + indicativo | €100 – 200 |
| ⚑ | Alta en **REMER** (Protección Civil) | Red de emergencia de voluntarios; encaja con tu caso de uso | gratis |
| ☐ | Transceptor HF móvil (p. ej. Yaesu FT-891) | Comunicación a larga distancia sin infraestructura | €700 – 900 |
| ☐ | Bibanda VHF/UHF móvil | Comunicación local, repetidores | €150 – 300 |
| ☐ | Antena HF móvil + acoplador | Lo que más determina el alcance real | €300 – 500 |
| ☐ | Antena bibanda + masa/plano de tierra | | €100 |
| | | **Subtotal** | **~€1.400 – 2.000** |

**Checklist**
- [ ] Licencia obtenida
- [ ] Equipos instalados con alimentación directa a batería y fusible
- [ ] Antenas ajustadas (ROE medida, no supuesta)
- [ ] **Prueba de contacto real** desde una zona sin cobertura móvil
- [ ] Verificado que transmitir no perturba la electrónica del vehículo

---

## Etapa 4 — Adaptador SDR RX (◆ primera placa a medida)

> Placa sencilla, sin FPGA. Valida la interfaz IAS1, que es el cimiento de todo lo demás.

| | Artículo | Notas | Precio `[E]` |
|---|---|---|---|
| ◆ | **Diseño y fabricación de la placa** | 6 capas, tirada corta con montaje | €400 – 800 |
| ☐ | ADC **AD9253BCPZ-125** | 14 b, 2 de 4 canales a 62.5 MSPS, 1-lane | €40 |
| ☐ | Fan-out de reloj **ADCLK944BCPZ-R2** + TCXO | Con acoplo AC y red de bias | €30 |
| ☐ | Drivers diferenciales **AD8352ACPZ** ×2 | Los usa AERIS | €30 |
| ☐ | Conmutadores **M3SWA2-34DR+** ×4 | Control positivo 3.3 V, confirmado | €80 |
| ☐ | Alimentación: bucks, LDO, protección de polaridad | Ver §9 del documento maestro | €40 |
| ☐ | Conectores: Hirose BM20B(0.8)-34DP ×2, SMA, Pmod | | €60 |
| ☐ | Cable FFC/Pmod hacia la KV260 | | €20 |
| | | **Subtotal** | **~€700 – 1.100** |

**Prerrequisitos antes de encargar nada**
- [ ] `VCCO` real del banco HPA de la KV260 (esquemático de la carrier)
- [ ] Envolvente mecánica medida sobre la placa física
- [ ] Stackup de 6 capas cerrado con el fabricante, con impedancias calculadas
- [ ] ERC sin errores y warnings justificados uno a uno

**Checklist de puesta en marcha** (en este orden, cada paso valida el anterior)
- [ ] Tensiones y rizado de todos los raíles, sin conversores montados
- [ ] Salidas del ADCLK944 en el osciloscopio: niveles, jitter, terminación
- [ ] **Senoide conocida por la entrada del ADC, recuperada en el PL** ← la prueba crítica
- [ ] Los 3 modos de conmutación

---

## Etapa 5 — Front-end SDR y transmisión (◆)

| | Artículo | Notas | Precio `[E]` |
|---|---|---|---|
| ◆ | Diseño y fabricación de la placa de RF | 4–6 capas | €400 – 800 |
| ☐ | Sintetizador **ADF4351** | LO de 35 MHz a 4.4 GHz | €25 |
| ☐ | Mezclador **ADL5801ACPZ** | Aquí sí está en su rango (10 MHz – 6 GHz) | €20 |
| ☐ | LNA (SPF5189Z / PGA-103+) | | €20 |
| ☐ | Filtros: LPF 30 MHz + 3 BPF conmutados | **Diseño a medida** — no los subestimes | €100 |
| ☐ | DAC **AD9767ASTZ** o **AD9709** + filtro de reconstrucción | Transmisión | €40 |
| ☐ | Limitador de entrada, conmutación T/R, driver de TX | | €80 |
| ☐ | **Cargas de 50 Ω conmutables** | Validar en *loopback* sin radiar | €30 |
| | | **Subtotal** | **~€700 – 1.100** |

---

## Etapa 6 — Radar de obstáculos, 77 GHz (☐, sin diseñar)

> **Si el objetivo del radar es ver obstáculos y niebla, esta etapa sustituye a AERIS.**
> 76–77 GHz está atribuido a radar vehicular: **sin licencia**.

| | Artículo | Notas | Precio `[E]` |
|---|---|---|---|
| ☐ | Módulo **TI AWR1843AOP** o similar (antena en encapsulado) | Un chip. Salida por USB/serie | €250 – 400 |
| ☐ | Caja estanca y soporte frontal | | €80 |
| | | **Subtotal** | **~€350 – 500** |

**Checklist**
- [ ] Detecciones llegando a la Kria
- [ ] Fusión radar + LiDAR (el radar atraviesa la niebla; el LiDAR da la resolución)

---

## Etapa 7 — FPGA de front-end (◆ decisión mayor pendiente)

> Necesaria para radiogoniometría de 4 canales y para AERIS. Ver
> [ROADMAP.md](ROADMAP.md) §4.3.

| | Artículo | Notas | Precio `[E]` |
|---|---|---|---|
| ◆ | Rediseño de la placa con FPGA | Arranque QSPI, secuencia de alimentación, JTAG | €800 – 1.500 |
| ☐ | **XC7A50T-2FTG256I** | La misma que AERIS: su firmware corre sin portar | €80 |
| ☐ | Flash QSPI + PMIC de secuencia + JTAG | | €40 |
| ☐ | ADC **AD9484BCPZ-500** (8 b, 400 MSPS) | El de AERIS | €120 |
| ☐ | Licencia/instalación de Vivado | Gratuita para estos dispositivos | — |
| | | **Subtotal** | **~€1.000 – 1.800** |

---

## Etapa 8 — AERIS-10 (☐ + ◆, el proyecto grande)

> Solo si el objetivo es **vigilancia a distancia**. Requiere autorización experimental.

| | Artículo | Notas | Precio `[E]` |
|---|---|---|---|
| ⚑ | Autorización de uso temporal y experimental (10.45–10.5 GHz) | Aficionado a título **secundario** | trámite |
| ◆ | Main Board de AERIS | 4 u 8× ADAR1000, 16× ADTR1107, 2× LTC5552, XC7A50T, STM32 | €1.500 – 3.000 |
| ◆ | Placa de síntesis de frecuencia | AD9523 + 2× ADF4382 | €400 – 700 |
| ◆ | Placa de alimentación | Con secuenciado | €300 |
| ◆ | Array de antenas | Rogers, 8×16 parches | €500 – 1.500 |
| ◆ | 16× placas de amplificador GaN | **Solo variante Extended** | €2.000+ |
| ☐ | Instrumentación de calibración | **El coste oculto**: cámara anecoica o montaje de campo cercano | ??? |
| | | **Subtotal** | **€3.000 – 8.000+** |

---

## Transversal — instalación en el vehículo

Aplica desde la etapa 1. **Esto no es accesorio: es lo que hace que el resto funcione.**

| | Artículo | Por qué | Precio `[E]` |
|---|---|---|---|
| ☑ | LiFePO4 + alternador secundario | | *ya lo tienes* |
| ☐ | **Protección ISO 7637-2** en la entrada de 12 V | *Load dump* y *cold crank*. Un TVS de banco no basta | €50 |
| ☐ | DC/DC 12 V estabilizado, con filtro de entrada | El rizado del alternador **te va a arruinar la HF** | €80 |
| ☐ | Caja con IP y ventilación filtrada | El fansink de la KV260 necesita aire limpio | €150 |
| ☐ | Distribución con fusibles y corte general | Seguridad | €60 |
| ☐ | Cable apantallado, ferritas, trenza de masa | **Problema práctico nº 1 de la radio en vehículo** | €100 |
| ☐ | Pantalla táctil o tablet como interfaz | | €150 |
| ☐ | Bancada antivibración | | €80 |
| | | **Subtotal** | **~€700** |

---

## Resumen económico `[E]`

| Etapa | Coste | Acumulado | Hardware a medida |
|---|---|---|---|
| 0 — SDR comercial | €1.200 | €1.200 | No |
| 1 — LiDAR | €950 | €2.150 | No |
| 2 — OBD/CAN | €150 | €2.300 | No |
| 3 — Radio homologada | €1.700 | €4.000 | No |
| Transversal — instalación | €700 | €4.700 | No |
| 4 — Adaptador SDR RX | €900 | €5.600 | **Sí** |
| 5 — Front-end SDR + TX | €900 | €6.500 | **Sí** |
| 6 — Radar 77 GHz | €430 | €6.900 | No |
| 7 — FPGA de front-end | €1.400 | €8.300 | **Sí** |
| 8 — AERIS-10 | €3.000 – 8.000+ | **€11.000 – 16.000+** | **Sí** |

**Las etapas 0 a 3, más la instalación, suman ~€4.700 y no requieren diseñar ni una placa.** Ahí
está la mayor parte de la utilidad real en el 4×4: escuchar, localizar, ver en la oscuridad,
mapear, registrar el vehículo y poder pedir ayuda.

Todo lo que viene después es ingeniería de RF a medida, y cuesta más que todo lo anterior junto.

---

## Lo que puedes pedir esta semana

Si quieres empezar mañana, este es el pedido mínimo con el que la KV260 deja de estar en un
cajón:

- [ ] microSD A2 + SSD USB — **€55**
- [ ] HackRF One + upconverter HF — **€360**
- [ ] Antena discono + látigo HF — **€150**
- [ ] GPS USB u-blox — **€40**
- [ ] Adaptador USB-CAN con SocketCAN — **€50**

**~€655**, y tienes escucha de banda ancha, detección de drones en 5.8 GHz, posición y
telemetría del vehículo. Y sobre todo, seis meses de datos reales con los que decidir si la
placa a medida tiene que ser como creemos hoy.
