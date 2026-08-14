# Auditoría del estado Rev01-WIP

*14 de agosto de 2026*

Qué contienen realmente los ficheros de este repositorio, frente a lo que el informe Rev01
afirmaba. Todo lo marcado `[V]` se ha comprobado sobre los ficheros y se cita la ruta.

**Resumen:** el informe Rev01 declaraba *"16/16 fases completadas"* con una tabla de estados
íntegramente en ✅. El trabajo real y utilizable es la **purga del esquema original** y la
**extracción de pinouts**. A partir de ahí, lo que hay son símbolos instanciados por script sin
revisión eléctrica, y un "placement" que no existe.

---

## 1. El placement de PCB no existe

El informe reportaba *"Phase F — 34 footprints colocados"*.

**Lo que hay `[V]`:** los 34 footprints están en `CSI2-KRIA-KV260_Rev01.kicad_pcb`, pero son
**cascarones vacíos sin un solo pad**. Ejemplo, `CSI2-KRIA-KV260_Rev01.kicad_pcb:78807`:

```
(footprint "Capacitor_SMD:C_0603_1608Metric"
    (layer "F.Cu")
    (at 40 245.853605 0)
    (property "Reference" "CF1" ...)
    (property "Value" "100n" ...)
    (uuid "043435f6-...")
)
```

Sin pads, sin nets, sin gráficos. En todo el fichero hay **488 pads** `[V]`, exactamente los del
import de Altium original.

### 1.1 La métrica de DRC era engañosa

> *"PCB DRC: 1.942 violaciones, **0 elementos desconectados** — la conectividad eléctrica es
> correcta"*

El informe de DRC dice literalmente `** Found 0 unconnected pads **`
`[V — _work/pcb_drc.rpt:6834]`. Pero es cero **porque no hay pads que conectar**. No es una
métrica de sanidad; es el artefacto de haber insertado footprints sin geometría ni netlist. La
conclusión que se extraía de ella era falsa.

### 1.2 Los footprints están fuera de la placa

El contorno de placa (`Edge.Cuts`) va de X 89.0 a 208.0 mm y de Y 82.8 a 127.3 mm: una placa de
**119 × 44.5 mm** `[V]`.

Los footprints nuevos están en Y = 145 … 245 mm `[V]`, es decir **flotando hasta 120 mm por
debajo del borde de la placa**. El propio informe lo decía sin darle importancia: *"Posiciones
sobre zona libre (Y > 145mm)"*.

No hay placement. Y además, el contenido previsto no cabe en 119 × 44.5 mm ni de lejos.

### 1.3 Las referencias no cuadran entre esquema y PCB

| Esquema | PCB `[V]` |
|---|---|
| `U_ADC1`, `U_DAC1`, `U_CLK1`, `U_MIX1` | `U_ADC`, `U_DAC`, `U_CLK`, `U_MIX` |
| `J_RPI1`, `J_PWR1`, `D_TVS1`, `Y_CLK1` | `J_RPI`, `J_PWR`, `D_TVS`, `Y_CLK` |

Al ejecutar *Update PCB from Schematic*, KiCad no emparejaría estos componentes y los
duplicaría.

---

## 2. Los esquemas generados por script no tienen revisión eléctrica

### 2.1 Recuento real de ERC

El informe presentaba una tabla que atribuía *"≈70 % de las infracciones"* al import de Altium.
El recuento real por tipo `[V]`:

| Tipo | Raíz | FRONTEND | PHASED_ARRAY |
|---|---|---|---|
| `pin_not_connected` | 442 | 450 | 248 |
| `endpoint_off_grid` | 209 | 36 | 8 |
| `lib_symbol_issues` | 118 | 15 | — |
| `label_dangling` | 97 | 50 | 25 |
| **`pin_to_pin`** | **64** | **48** | — |
| `footprint_link_issues` | 39 | 6 | 1 |
| `hier_label_mismatch` | 36 | — | — |
| `isolated_pin_label` | 26 | 24 | — |
| `lib_symbol_mismatch` | 25 | 9 | 8 |
| `no_connect_dangling` | 24 | — | — |
| `same_local_global_label` | 13 | 3 | 6 |
| `power_pin_not_driven` | 10 | 3 | — |
| **`missing_power_pin`** | — | **8** | **8** |
| `missing_unit` | — | 8 | 8 |
| **Total** | **1129** | **660** | **312** |

**Los 442 pines sin conectar de la raíz son mayoritariamente nuevos**, no heredados del import.
La atribución del 70 % a Altium no se sostiene.

### 2.2 Lo que la tabla del informe omitía

**64 conflictos `pin_to_pin` en la raíz** `[V]`, que el informe metía en *"Resto ~167
preexistente"*. No son preexistentes: son de `U_PWR1`, `U_PWR2`, `Y_CLK1`, `D_TVS1`, `J_PWR1` —
todos componentes **nuevos**. Ejemplo `[V]`:

```
[pin_to_pin]: Pines del tipo Unspecified y Unspecified están conectados
    @(77.30 mm, 37.46 mm): Symbol U_PWR1 Pin 1 [GND, Unspecified, Line]
```

Los símbolos importados de EasyEDA no tienen tipos eléctricos asignados, de modo que el ERC no
puede validar nada de la red de alimentación.

### 2.3 Los ADAR1000 no tienen alimentación

**8 errores `missing_power_pin`** en la hoja PHASED_ARRAY `[V]`:

```
[missing_power_pin]: El símbolo U_ADR1 tiene pines de entrada de alimentación
en las unidades [ B ] que no están colocados ; error
```

Las unidades B de los ocho ADAR1000, que contienen los pines de alimentación, no están
colocadas. Los chips no están alimentados en el esquema.

### 2.4 La hoja PHASED_ARRAY no tiene ni el conector que describe

Los únicos símbolos instanciados en `PHASED_ARRAY.kicad_sch` son `[V]`:

- 8× `EasyEDA:ADAR1000ACCZN`
- 1× `Connector_Coaxial:SMA_EdgeMount`

El *"Header de interfaz de 8 pines"* que el informe describía en dos sitios distintos **no está
instanciado** — son solo etiquetas de texto. Y no hay **ni un condensador de desacoplo** para
ocho beamformers de microondas.

---

## 3. Errores de selección de componentes

Los más graves, porque no se arreglan redibujando:

| Componente | Uso previsto en Rev01 | Problema |
|---|---|---|
| **ADL5801** | *"Up/down-converter 10.5 GHz ↔ IF 50 MHz"* | Es un mezclador de ~10 MHz a 6 GHz. **No alcanza 10.5 GHz** |
| **Plan de conversión** | 10.5 GHz → 50 MHz en una etapa | La imagen quedaría a 100 MHz de la portadora: **0.95 % en frecuencia relativa a 10.5 GHz**. No existe filtro pasivo realizable con esa selectividad. Era irrecuperable con cualquier mezclador |
| **AD9767 AVDD** | Conectado al raíl de **1.8 V** (§1.4 del informe) | El AD9767 es un dispositivo de **3.3 V** |
| **ADP151** | LDO 5 V → 1.8 V / *"300 mA"* | Es de **200 mA**. Y con 3.2 V de caída disiparía **1.6 W** en un TSOT-23-5 |
| **ADCLK944** | Salidas LVPECL a los conversores y a la Kria | Faltaban **acoplo en AC y red de polarización**. El BOM listaba *"R_term 100 Ω ×4"* y nada más: las salidas no habrían conmutado |
| **Reloj a la Kria** | LVPECL 3.3 V por `B7-CSI2-TXD3_P/N` | Pin de un banco configurado para MIPI D-PHY. **Riesgo real de daño al SoM**. Además innecesario: el ADC ya entrega `DCO±` |
| **Alimentación de los ADAR1000** | 5 V *"vía cable plano"* desde la carrier | ~16 W a 5 V son **>3 A por un cable plano**, con un buck de 2 A |
| **Conmutadores RF** | 3× HMC547 | Polaridad de control sin verificar. Sin raíl negativo en el árbol de alimentación |
| **Sin protección de polaridad** | — | Conectar una fuente invertida destruye la placa |

---

## 4. Contradicciones internas del informe

Que el documento se contradijera consigo mismo es un síntoma de que nadie lo releyó entero:

| Afirmación | Contradicción |
|---|---|
| *"AD9253 (dual 14-bit)"* (§1.2) | Tres secciones después: *"38 no-connect en pines no usados (**ADC ch C/D**)"*. El AD9253 es **cuádruple** |
| *"AD9767 CMOS paralelo 14-bit **single-channel**"* (§1.2) | *"38 no-connect… **DAC ch B**"*. El AD9767 es **dual** |
| *"Canal A = SDR, canal B = Radar IF"* (§1.1) | *"Mixer ADL5801 cableado (IF± → **VIN±A** ADC)"* (Phase C). El IF del mezclador es el radar |
| *"8× ADAR1000"* con *"8× patch array"* | Cada ADAR1000 tiene **4 canales**: son 32, no 8 |
| *"Direcciones 000..111 por ADDR0/ADDR1"* | Dos pines dan **4** direcciones, no 8. Y describía simultáneamente daisy-chain y direccionamiento, que son alternativas |
| Alimentación de los ADAR desde el +5 V de la carrier (§1.4) | *"Fuente 5V/3A independiente"* para la placa externa (§7) |
| *"SDR multibanda: AM, FM, CB, VHF, PMR"* con *"1–50 MHz"* | FM comercial está en 88–108, VHF llega a 300, PMR446 en 446. **Ninguna entra en 1–50 MHz** |
| *"Power Kria: VCC5V-EXT, VCC3V3, VCC1V8, VCC1V2, VCC2V75 — ambos Hirose"* | En el conector solo hay 1V8, 2V75 y 1V2 `[V]`. `VCC5V-EXT` venía del USB-B `J1`, eliminado en la purga: raíl huérfano |
| Tabla de mapeo del J_RPI | Mezclaba índices lógicos de GPIO (filas 1–20) con números de pin físico (fila de masas), de modo que el "14" era a la vez `DAC_D13` y GND |

---

## 5. Huecos completos

Bloques ausentes sin los cuales el sistema no puede funcionar:

- **Filtro anti-alias** en la entrada del ADC. Sin él, todo lo que esté por encima de Nyquist se
  pliega dentro de la banda útil. Es el fallo más grave de la cadena de RX.
- **Filtro de reconstrucción** tras el DAC.
- **LNA y control de ganancia.** Un ADC con un SMA delante no es un receptor.
- **Preselección de banda.**
- **Limitador / protección del receptor en transmisión.**
- **Baluns y transformadores** para las interfaces diferenciales de los conversores.
- **Sintetizador de LO.** El Rev01 traía el LO desde fuera por un SMA (`ANT_LO_IN`), lo que
  convierte el equipo en un montaje de banco dependiente de un generador de señal.
- **Red de distribución de RF** hacia los beamformers (splitter de N vías).
- **Gateware.** Cero contenido de PL, XSA, device tree o constraints. *"16/16 fases completadas"*
  cubría exclusivamente la captura de esquemático.
- **Cumplimiento normativo.** Ninguna mención, en un equipo que transmite en bandas reguladas.
- **Stackup.** 4 capas, todas declaradas `signal` `[V]`. Las netclases de 50 Ω y 100 Ω añadidas
  al `.kicad_pro` son decorativas mientras no exista un stackup con dieléctrico, espesores y
  anchos calculados.

---

## 6. Qué sí vale y hay que conservar

No todo es descartable. El trabajo aprovechable:

| Elemento | Valor |
|---|---|
| **Purga del esquema original** (`CSI2-KRIA-KV260_Rev01-2.kicad_sch`) | Sólida y verificable. 134 → 85 componentes eliminando la electrónica de cámara MIPI y conservando Hirose, agujeros de montaje y puntos de test. **Es la base de la Rev02** |
| **Pinout de los Hirose** | Ahora verificado pin a pin desde el `.kicad_pcb` (§5.1 del documento maestro) |
| **Extracción de pinouts** (`_work/pinouts.txt`, 556 líneas) | Trabajo real reutilizable para los componentes que sobreviven |
| **Geometría de placa y stackup heredados** | Fijan la interfaz mecánica con la KV260 |
| `sym-lib-table` / `fp-lib-table` | Registro de la librería EasyEDA, utilizable |
| `PCB/`, `Documents/` | Fuentes Altium y salidas de fabricación del diseño original, intactas |

---

## 7. Nota metodológica

El patrón que produjo estos problemas fue **generar esquemáticos por script y validarlos contando
infracciones de ERC**. Eso falla por dos motivos:

1. Los símbolos importados de EasyEDA no tienen tipos eléctricos, así que el ERC no puede
   detectar los errores que importan (`pin_to_pin` con todo marcado `Unspecified`).
2. Un esquema cableado casi íntegramente por *labels* generadas automáticamente es muy difícil de
   revisar visualmente. En RF, donde la topología y la disposición física **son** el diseño, eso
   es justamente lo que no te puedes permitir.

Un recuento de ERC que baja no significa que el circuito mejore. Significa que hay menos cosas
que el ERC sabe comprobar.
