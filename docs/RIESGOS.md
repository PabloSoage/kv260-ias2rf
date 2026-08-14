# Bloqueantes y riesgos

*Actualizado: 14 de agosto de 2026 · **Los 5 bloqueantes están cerrados***

Dos de ellos se cerraron **en contra** de lo que suponía la arquitectura Rev02. El resultado
obliga a replantear la interfaz con la Kria. Este documento recoge la evidencia; las
consecuencias están en [ARCHITECTURE_draft_es.md](../ARCHITECTURE_draft_es.md).

| ID | Cuestión | Resultado |
|---|---|---|
| **B-01** | ¿Pueden los pines IAS ser salidas? ¿A qué banco van? | ⛔ **Cierra en contra.** IAS0 no llega a la FPGA |
| **B-02** | ¿Admite el AD9253 1-lane a 125 MSPS? | ⛔ **Cierra en contra.** 1-lane ≤ 62.5 MSPS |
| **B-03** | ¿Control negativo en los conmutadores? | ✅ **Cierra a favor.** Control positivo, 3.3 V |
| **B-04** | ¿Cuál es la IF de AERIS-10? | ✅ **Cierra a favor.** 120 MHz, filtros sin especificar |
| **B-05** | ¿Cómo es la variante Extended? | ⚠️ **Parcial.** No publicada; 8 ADAR1000 según tu información |

---

## B-01 — Interfaz con la Kria ⛔ CIERRA EN CONTRA

### Lo que dice la documentación oficial

Tabla de conectores de **UG1089** (v1.0 de abril de 2021 y v1.3 de mayo de 2024, idénticas en
este punto):

| Conector | Descripción según UG1089 |
|---|---|
| **CC J7 — IAS0** | *"OnSemi image access system (IAS) camera module interface supporting four MIPI lanes. **Connects to OnSemi AP1302 ISP device sensor 0 interface**"* |
| **CC J8 — IAS1** | *"OnSemi IAS camera module interface supporting four MIPI lanes. **Connected directly to the Zynq UltraScale+ MPSoC HPA bank**"* |
| **CC J9 — RPi camera** | *"Raspberry Pi camera module interface. **15-pin variant supporting two MIPI lanes** directly connected to the Zynq UltraScale+ MPSoC HPA bank"* |
| **CC J2 — Pmod** | *"Digilent Pmod 2x6 expansion header"* — 3.3 V, 100 mA |

Más adelante la misma guía las nombra explícitamente como *"IAS camera sensor **ISP** interface
(J7)"* frente a *"IAS camera sensor **direct** interface (J8)"*.

Corroborado de forma independiente: *"the first IAS MIPI connector is connected to an external
ISP AP1302 from ONSemi, while the second is connected directly to the SOM pins"*.

### Las tres consecuencias

**1. IAS0 (J7) no llega a la lógica programable.** Sus cuatro carriles MIPI entran en un ISP
AP1302 soldado en la carrier card. Un ISP es un procesador de imagen: no deja pasar datos
arbitrarios y desde luego no puede ser un camino de salida. **La arquitectura "IAS0 = RX,
IAS1 = TX" no es realizable.**

**2. No existe ninguna cabecera Raspberry Pi de 40 pines en la KV260.** La lista completa de
conectores de la carrier es J2 (Pmod 2×6), J3 (JTAG), J4 (UART/JTAG por USB), J5 (HDMI),
J6 (DisplayPort), J7 (IAS0), J8 (IAS1), J9 (cámara RPi de 15 pines), J10 (Ethernet),
J11 (microSD), J12 (12 V), J13 (ventilador). **J9 es un conector de cámara, no la cabecera GPIO
de una Raspberry Pi.** El informe Rev01 basaba todo el bus paralelo del DAC en *"el cabezal RPi
40-pin de la Kria (28 GPIO disponibles)"*: ese conector no existe.

**3. Los transceptores GTH no son accesibles.** El SoM K26 tiene un quad GTH a 12.5 Gb/s, pero
en la KV260 no sale a ningún conector de usuario. **JESD204B queda descartado**, que era la vía
natural para un conversor rápido con pocos pines.

### Presupuesto real de E/S de una KV260 hacia una placa externa

| Conector | Pares diferenciales | Single-ended | Banco |
|---|---|---|---|
| **J8 / IAS1** | **5** (4 datos + 1 reloj) | ~4 (I2C, PWDN, GPIO) | HPA, directo al SoM |
| **J9 / cámara RPi** | **3** (2 datos + 1 reloj) | ~2 | HPA, directo al SoM |
| **J2 / Pmod** | — | **8** a 3.3 V, 100 mA | HD |
| ~~J7 / IAS0~~ | ~~4~~ | — | **Termina en el ISP AP1302** |
| **Total utilizable** | **8 pares** | **~14** | |

Ocho pares diferenciales. Eso es todo lo que hay.

### Lo que sí quedó confirmado a favor

- Los pines de J8 y J9 van **directamente al SoM**, sin buffers ni traductores intercalados. Son
  E/S de FPGA normales sobre un banco HP: **bidireccionales**, configurables como LVDS o LVCMOS.
- La carrier ofrece raíles de **2.75 V, 1.8 V y 1.2 V** en los pines de alimentación de los
  conectores IAS, coherente con el pinout leído del `.kicad_pcb` de este repositorio.

`[?]` **Queda por confirmar** la tensión `VCCO` exacta del banco HPA tal como la configura la
KV260 (los bancos HP de Zynq UltraScale+ admiten de 1.0 V a 1.8 V; MIPI D-PHY suele implicar
1.2 V). Determina el estándar de E/S utilizable y si hace falta acoplo en AC. **No es
bloqueante para decidir la arquitectura**, pero sí para cerrar el esquemático.

---

## B-02 — Modo 1-lane del AD9253 ⛔ CIERRA EN CONTRA

Dos especificaciones del datasheet del AD9253:

1. *"the data rate for each serial stream is equal to **16 bits** times the sample clock rate
   divided by the number of lanes"* (16 y no 14: hay 2 bits de trama).
2. *"a maximum of **1000 Mbps/lane** at 125 MSPS in **two-lane** mode. The maximum conversion
   rate is based on two-lane output mode."*

Comprobación: 16 × 125 MSPS ÷ 2 carriles = 1000 Mbps/carril ✓

Despejando para 1 carril: **f_s ≤ 1000 Mbps ÷ 16 bits = 62.5 MSPS**.

### Consecuencia sobre el presupuesto de pares

| Configuración | Canales | f_s | Nyquist | Pares (datos + DCO + FCO) |
|---|---|---|---|---|
| 1-lane | 2 | **62.5 MSPS** | 31.25 MHz | 2 + 2 = **4** |
| 2-lane | 2 | 125 MSPS | 62.5 MHz | 4 + 2 = **6** |
| 2-lane | 1 | 125 MSPS | 62.5 MHz | 2 + 2 = **4** |

Con 5 pares en IAS1, **2 canales a 125 MSPS no caben** (harían falta 6). Las únicas opciones
directas son 2 canales a 62.5 MSPS, o 1 canal a 125 MSPS.

`[?]` Convendría ver la línea explícita de la tabla de modos del datasheet. La aritmética es
determinante a partir de las dos especificaciones citadas, pero es una deducción, no una cita
directa del límite de 1-lane.

---

## B-03 — Conmutadores de RF ✅ CIERRA A FAVOR

El **M3SWA2-34DR+** (el que usa AERIS-10, 17 unidades) es un conmutador SPDT absortivo GaAs
MMIC **con driver interno**, DC – 30 GHz, alimentación de **3.3 – 3.6 V**, encapsulado QFN de
3×3 mm, soporta +27 dBm.

El driver interno acepta control lógico positivo: **no hace falta raíl negativo**. Se elimina el
inversor de carga del árbol de alimentación.

Los raíles `-5V0_ADAR12` / `-5V0_ADAR34` que tiene AERIS son para los **ADAR1000**, no para los
conmutadores, y están en su placa. No afectan al adaptador.

---

## B-04 — Frecuencia intermedia de AERIS-10 ✅ CIERRA A FAVOR

**La IF de AERIS-10 es 120 MHz**, muestreada a 400 MSPS. Verificado en su propio RTL:

```
9_Firmware/9_2_FPGA/ddc_400m.v            "120MHz IF"
9_Firmware/9_2_FPGA/tb/cosim/radar_scene.py   F_IF = 120
   parámetro RTL:  IF_FREQ = 120_000_000
```

**Y los filtros de IF no están especificados.** En el BOM de la Main Board, el componente `BPF2`
(cantidad 2, designadores `U$2, U$3`) tiene como número de fabricante literalmente
**"Not a component"**: son huecos sin definir.

### Consecuencias, todas favorables

- No hay hardware de filtrado que sustituir en la placa de AERIS. El temor de tener que modificar
  una placa ajena desaparece.
- La IF es un **parámetro libre**: se puede acordar el valor que convenga al conversor elegido.
- Si se conserva la IF de 120 MHz, se puede **submuestrear**: a 125 MSPS, 120 MHz cae en la
  segunda zona de Nyquist y se repliega a 5 MHz. Es muestreo paso banda clásico, y exige que el
  filtro anti-alias sea **paso banda centrado en 120 MHz**, no paso bajo.

---

## B-05 — Variante AERIS-10X Extended ⚠️ PARCIAL

No hay evidencia publicada de la configuración de 8 ADAR1000. Lo que sí está verificado:

- La Main Board publicada lleva **4× ADAR1000ACCZN** y 16× ADTR1107.
- El README de AERIS describe la variante Extended como array de guía de onda ranurada 32×16 con
  16 placas de amplificador GaN de 10 W. Dieciséis placas de PA encajan con 16 canales, no con 32.
- El control es **por chip**: `ADAR_n_CS`, `ADAR_TX_LOAD_n`, `ADAR_RX_LOAD_n`, `ADAR_TR_n`.

**Se adopta tu dato (8 chips, 32 canales) como requisito de dimensionado**, porque
sobredimensionar el control es barato y quedarse corto no tiene arreglo. Conviene confirmarlo con
el autor del proyecto antes de congelar el conector.

---

# Riesgos abiertos

### R-01 — La KV260 es una plataforma pobre en E/S para este proyecto

**Es el riesgo estructural.** Ocho pares diferenciales y catorce señales sueltas es muy poco para
un front-end de RF con dos cadenas, dos conversores y hasta 32 canales de beamforming.

**Alternativas si llegara a ser insalvable:**

| Opción | E/S disponible | Coste |
|---|---|---|
| KV260 + FPGA embudo | 8 pares (enlace serie propio) | Una FPGA más en el adaptador |
| **KR260** (Robotics Starter Kit) | 4× Pmod + Ethernet PL + más E/S | Cambiar de placa |
| **Carrier propia para el SoM K26** | ~180 E/S de usuario + 4 carriles GTH a 12.5 Gb/s | Diseñar una carrier de 240 pines |

La tercera es la que hace un diseño serio de radar, y habilita JESD204B. También es, con
diferencia, la más cara en trabajo.

---

### R-02 — Resolución en distancia limitada por el conversor

| Configuración | Ancho de banda útil | Resolución ΔR = c/2B |
|---|---|---|
| AERIS-10 original (AD9484, 400 MSPS) | 200 MHz | 0.75 m |
| Con FPGA embudo (AD9484 a 400 MSPS) | 200 MHz | **0.75 m** |
| Sin embudo, AD9253 1 canal a 125 MSPS | ~50 MHz | 3.0 m |
| Sin embudo, AD9253 2 canales a 62.5 MSPS | ~25 MHz | 6.0 m |

La FPGA embudo es lo que recupera las prestaciones originales de AERIS.

---

### R-03 — Diafonía si se usan pares acoplados como líneas single-ended

Los pares de J8 y J9 son líneas acopladas de 100 Ω. Usar sus dos conductores como señales
independientes implica acoplamiento fuerte. **Con la FPGA embudo el problema desaparece**: los
pares se usan como pares LVDS, que es para lo que están.

---

### R-04 — Envolvente mecánica sin verificar

El contorno actual mide 119 × 44.5 mm. Hay que medir sobre la placa física hasta dónde puede
crecer sin chocar con el disipador, los conectores frontales o la carcasa. Las posiciones de los
Hirose son fijas.

Añadido ahora: si se usa **J9 (cámara RPi, FFC de 15 pines)** además de J8, el adaptador necesita
un cable FFC hasta ese conector, que está en otra zona de la placa. Es una complicación mecánica
real.

---

### R-05 — Calibración del array

32 canales exigen calibración de fase y amplitud por canal: cámara anecoica o montaje de campo
cercano. Es el coste oculto mayor del proyecto de radar. No lo introduce el adaptador, pero hay
que tenerlo en el plan.

---

### R-06 — Regulación de la emisión en 10.5 GHz

`[?]` No es banda ISM libre en todos los países. Con amplificadores GaN de 10 W por canal, la
variante Extended no es un equipo que se encienda sin más. **Mitigación:** cargas de 50 Ω
conmutables en las salidas de TX para validar todo en *loopback* conducido, sin radiar.

---

### R-07 — Secuenciado de alimentación de los amplificadores

Un fallo de secuencia destruye los GaN. **Mitigación:** conservar el STM32 de AERIS como
controlador de housekeeping en lugar de replicar su lógica probada.

---

### R-08 — Portar el firmware de AERIS-10

Reutilizable y bien probado, pero no es copiar y pegar: hay que adaptar dominios de reloj,
profundidades de bit e interfaz de host. **Con la FPGA embudo, `ddc_400m.v` se puede portar casi
tal cual**, porque trabajaría en su dominio nativo de 400 MSPS.

---

### R-09 — Añadir una FPGA al adaptador es un salto de complejidad

Deja de ser una placa adaptadora y pasa a ser una placa FPGA: configuración, memoria de arranque,
alimentación multi-raíl con secuencia, JTAG, y un segundo flujo de herramientas. Es la decisión
de proyecto más importante que queda por tomar.

---

## Fuentes

- [Kria KV260 Vision AI Starter Kit User Guide UG1089 v1.0](https://fpga.eetrend.com/files/2021-11/wen_zhang_/100554954-225561-ug1089-kv260-starter-kit.pdf)
- [Kria KV260 Vision AI Starter Kit User Guide UG1089 v1.3](https://docs.xibif.ch/_downloads/480ec1217d1ac2bd520e695148cfe86f/KV260_Userguide.pdf)
- [Hardware Architecture of the Platform — Kria KV260 docs](https://xilinx.github.io/kria-apps-docs/kv260/2022.1/build/html/docs/nlp-smartvision/docs/hw_arch_platform_nlp.html)
- [Kria K26 SOM Data Sheet DS987 — GTH Transceivers](https://docs.amd.com/r/en-US/ds987-k26-som/GTH-Transceivers)
- [AD9253 Data Sheet — Analog Devices](https://www.analog.com/media/en/technical-documentation/data-sheets/ad9253.pdf)
- [M3SWA2-34DR+ SPDT RF Switch — Mini-Circuits](https://www.minicircuits.com/pdfs/M3SWA2-34DR+.pdf)
- [tomverbeure/kv260_bringup](https://github.com/tomverbeure/kv260_bringup)
