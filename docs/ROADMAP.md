# Plan de trabajo

*14 de agosto de 2026 · Arquitectura Rev02*

Cada fase tiene un **criterio de salida verificable**. Una fase no está terminada porque se hayan
tocado ficheros, sino porque se cumple su criterio. El Rev01 se declaró completo sin criterios
de salida, y de ahí vino todo.

---

## Fase 0 — Cerrar los bloqueantes ✅ COMPLETADA

| Bloqueante | Resultado |
|---|---|
| **B-01** — Interfaz con la Kria | ⛔ **En contra.** IAS0 termina en el ISP AP1302; no existe cabecera RPi de 40 pines; los GTH no son accesibles. Presupuesto real: **8 pares + ~14 señales sueltas** |
| **B-02** — Modo 1-lane del AD9253 | ⛔ **En contra.** Limitado a **62.5 MSPS** |
| **B-03** — Conmutadores de RF | ✅ **A favor.** M3SWA2-34DR+ con driver interno, control positivo 3.3 V |
| **B-04** — IF de AERIS-10 | ✅ **A favor.** 120 MHz; los filtros `BPF2` son placeholders sin especificar |
| **B-05** — Variante Extended | ⚠️ **Parcial.** No publicada. Se dimensiona para 8 chips |

Evidencia y fuentes en [RIESGOS.md](RIESGOS.md). Consecuencia: la arquitectura Rev02 no era
realizable y se ha sustituido por la **Rev03, con FPGA de front-end**.

Queda pendiente, no bloqueante para decidir pero sí para cerrar el esquemático:

| Tarea | Fuente |
|---|---|
| `VCCO` exacta del banco HPA tal como la configura la KV260 | Esquemático de la carrier card |
| Confirmar la variante Extended de AERIS (B-05) | Autor del proyecto |
| Medir la envolvente mecánica sobre la KV260 | La placa física |

---

## Fase 0.5 — Decisión de arquitectura ⬅ **AQUÍ ESTAMOS**

**Una sola pregunta, y de ella depende todo lo demás:** ¿se acepta poner una FPGA de front-end
en la placa adaptadora?

| | Con FPGA de front-end | Sin FPGA |
|---|---|---|
| Resolución de radar | **0.75 m** | 3.0 – 6.0 m |
| Canales de RX | 2 a 400 MSPS + 2 de SDR | 2 a 62.5 MSPS |
| Transmisión | 14 bits, bus local | 8 bits repartidos entre 2 conectores |
| Control de los ADAR1000 | Trivial, con estrobo síncrono | Sin resolver para 8 chips |
| Firmware de AERIS | **Corre casi sin portar** | Hay que reescribirlo |
| Conectores usados | J8 + Pmod | J8 + J9 (FFC) + Pmod |
| Complejidad de la placa | **Placa FPGA**: arranque, secuencia, JTAG | Placa pasiva |
| Segundo flujo de herramientas | Sí (Vivado para la FPGA de front-end) | No |

**Criterio de salida:** decisión tomada y registrada. Sin ella, cualquier esquemático es trabajo
tirado.

---

## Fase 1 — Especificación congelada

| Tarea | Entregable |
|---|---|
| Fijar frecuencia de muestreo y modo de lanes del ADC | Actualizar §4.1 del documento maestro |
| Fijar ancho de bus, tasa y componente del DAC | Actualizar §5.1 |
| Congelar el mapa pin a pin de IAS0, IAS1 y la cabecera RPi | Tabla de asignación completa, con pines físicos |
| Congelar el conector de control hacia AERIS-10 | Pinout del IDC 2×20, con niveles y direcciones |
| Presupuesto de corriente por raíl con datos de datasheet | Sustituir las estimaciones `[E]` de §10.1 |
| Definir el stackup de 6 capas con impedancias calculadas | Ficha de stackup para el fabricante |

**Criterio de salida:** el documento maestro sin ninguna marca `[?]` en las secciones 4, 5, 6
y 10, y con las `[E]` de alimentación sustituidas por valores de datasheet.

---

## Fase 2 — Esquemático

Se parte de `CSI2-KRIA-KV260_Rev01-2.kicad_sch` (la purga, que es trabajo válido) y se
**descartan** `FRONTEND.kicad_sch` y `PHASED_ARRAY.kicad_sch`.

> **Captura manual en la GUI de KiCad, no generación por script.** Ver la nota metodológica de
> [AUDITORIA_Rev01.md](AUDITORIA_Rev01.md#7-nota-metodológica). Los scripts sirven para purgar y
> para extraer datos; no para dibujar circuitos que nadie va a poder revisar.

| Hoja | Contenido |
|---|---|
| Raíz | Jerarquía y conectores Hirose |
| `IAS_RX` | Hirose IAS0, ADC, acondicionamiento de entrada, terminaciones |
| `IAS_TX` | Hirose IAS1, traductores de nivel, DAC, filtro de reconstrucción |
| `CLOCK` | Selector de referencia, TCXO, ADCLK944 con acoplo y polarización |
| `ROUTING` | 4 conmutadores SPDT, SMA de IF, SMA de reloj |
| `CONTROL` | Cabecera RPi, decodificador 3→8, traductores a 1.8 V, IDC hacia AERIS y placa B |
| `POWER` | Árbol completo con protección de polaridad y separación analógico/digital |

**Requisitos de calidad, no negociables:**

- Símbolos con **tipos eléctricos correctos** en todos los pines. Si un símbolo de EasyEDA viene
  con todo marcado `Unspecified`, se corrige antes de usarlo: si no, el ERC no comprueba nada.
- Conexiones con **wires**, no solo con etiquetas. Las etiquetas son válidas para buses y raíles;
  la topología de RF y de alimentación tiene que verse.
- Un `no_connect` explícito en cada pin deliberadamente sin usar.

**Criterio de salida:**

1. ERC con **cero errores** y warnings justificados uno a uno en un fichero de excepciones.
2. Revisión visual hoja por hoja contra el documento maestro.
3. Cada componente del BOM con su parte real, encapsulado y disponibilidad comprobada.

---

## Fase 3 — Layout

| Tarea | Nota |
|---|---|
| Ampliar el contorno de placa | Manteniendo fijas las posiciones de los dos Hirose |
| Definir el stackup de 6 capas en KiCad | Con dieléctricos y espesores reales del fabricante |
| Placement | Conversores y reloj lo más cerca posible de los Hirose |
| Rutado de los pares de los IAS | 100 Ω diferenciales, apareados en longitud, plano de referencia continuo |
| Rutado del bus del DAC | Terminación serie en origen, retorno próximo |
| Planos de alimentación | Separación real entre analógico y digital, ferritas en los puntos de unión |
| Rutado de las líneas de IF | 50 Ω hasta los SMA |

**Criterio de salida:**

1. DRC con cero errores **con las reglas correctas activadas** (no heredando las del import).
2. Cero pads sin conectar — y esta vez con pads de verdad.
3. Impedancias verificadas con la calculadora del stackup del fabricante.
4. Revisión de fabricabilidad con el fabricante elegido antes de pedir.

---

## Fase 4 — Prototipo y puesta en marcha

Orden deliberado: cada paso valida el anterior y no depende del siguiente.

| Paso | Qué se valida | Cómo |
|---|---|---|
| 1 | Alimentación | Tensiones y rizado en todos los raíles, sin conversores montados |
| 2 | Reloj | Salidas del ADCLK944 con osciloscopio: niveles, jitter, terminaciones |
| 3 | **Enlace IAS0 → PL** | Inyectar una senoide conocida en la entrada del ADC y recuperarla en el PL. **Es la validación crítica de todo el proyecto** (cierra B-01 en la práctica) |
| 4 | **Enlace PL → IAS1** | Generar una senoide desde el PL y verla en la salida del DAC |
| 5 | Diafonía del bus del DAC | Barrido de frecuencia de muestreo hasta encontrar el límite real (cierra R-01) |
| 6 | Conmutadores y encaminado | Los 3 modos de operación de §7.2 |
| 7 | Integración con AERIS-10 | Reloj común, IF en ambos sentidos, control de haz |

**Criterio de salida:** lazo cerrado DAC → conmutador → conmutador → ADC funcionando, con la
señal generada por el PL recuperada por el PL.

---

## Fase 5 — Gateware

Se puede solapar con las fases 2 y 3.

| Tarea | Nota |
|---|---|
| Receptor serie LVDS del ADC | `ISERDESE3` + alineación de trama |
| Generador del bus del DAC | |
| Maestro SPI y control de haz | |
| Portar el procesado de radar de AERIS-10 | Adaptar reloj (400 → 80/125 MHz), bits (8 → 14), host (USB → AXI/DMA) |
| Cadena SDR | DDC, decimación, demodulación |
| Aplicación de host | |

**Criterio de salida:** captura de ADC y generación de DAC funcionando sobre hardware real, con
las regresiones del firmware de AERIS pasando en el nuevo dominio de reloj.

---

## Fases posteriores

- **Placa B — front-end SDR.** Independiente. Puede empezar en cuanto la Fase 1 congele la
  interfaz de IF.
- **Integración con AERIS-10X.** Depende de que el autor publique la variante extendida (B-05).

---

## Estado actual

**Fase 0 completada. Bloqueado en la Fase 0.5**, a la espera de la decisión sobre la FPGA de
front-end.

### Trabajo hecho sobre los ficheros KiCad

| Acción | Estado |
|---|---|
| Eliminados los **34 footprints vacíos** que el Rev01 había insertado en el `.kicad_pcb` | ✅ Hecho. Copia previa en `_backup_original/CSI2-KRIA-KV260_Rev01_preRev02cleanup.kicad_pcb` |
| Verificada la integridad del fichero tras la edición | ✅ Paréntesis balanceados; **488 pads intactos**, ninguno era de los footprints borrados |
| Conservados los 5 footprints sin pads que **sí** son originales del import (`LA1`, `T1`, `T2`, `J5_IAS0`, `J5_IAS1`) | ✅ |

**Lo que deliberadamente no se ha hecho, y por qué:**

- **No se ha dibujado esquemático nuevo.** La arquitectura cambió al cerrar B-01 y la decisión de
  la Fase 0.5 está abierta. Dibujar ahora sería trabajo tirado.
- **No se ha hecho placement ni rutado.** Por lo mismo, y porque hacerlo escribiendo
  S-expressions a mano produciría exactamente el tipo de artefacto irrevisable que causó los
  problemas del Rev01 (ver la [nota metodológica](AUDITORIA_Rev01.md#7-nota-metodológica)).
- **No se ha ampliado el contorno de placa** ni definido el stackup de 6 capas: ambos dependen de
  la decisión de arquitectura y de la envolvente mecánica, aún sin medir.
- **No se han inventado pinouts.** Los símbolos de las piezas nuevas (XC7A50T, AD9484, AD9708) se
  crearán a partir de sus datasheets, con tipos eléctricos correctos, no por copia de librerías
  de terceros sin tipar.

`FRONTEND.kicad_sch` y `PHASED_ARRAY.kicad_sch` siguen registrados en el proyecto pero
**implementan una arquitectura muerta**. Conviene sacarlos del `.kicad_pro` y del esquemático
raíz al empezar la Fase 2; no se ha hecho ahora para no dejar el proyecto en un estado que no
puedas abrir y comprobar.
