# Historial del trabajo Rev01-WIP

*Registro de lo que se hizo entre el import desde Altium y agosto de 2026, conservado para
trazabilidad. La valoración de cada fase refleja la auditoría posterior; ver
[AUDITORIA_Rev01.md](AUDITORIA_Rev01.md).*

---

## Punto de partida

Proyecto KiCad importado desde Altium (`CSI2-KRIA-KV260_Rev01`): la placa adaptadora de cámaras
MIPI de Allied Vision, con 2 conectores Hirose BM20B(0.8)-34DP hacia la Kria KV260, conectores
FFC/FPC MIPI, reguladores, level shifters I2C/GPIO y alimentación USB.

---

## Fase A — Purga del esquema original

**Objetivo:** eliminar la electrónica de cámara MIPI conservando los Hirose y la alimentación.

| Acción | Detalle |
|---|---|
| Borrado directo (15 bloques) | J1 (USB-B), J7 (FFC22 MIPI), J2/J5/J6/J9/J10 (headers), U1 (INA260), U2 (TPS25200), U3 (PCA9306), U4 (NTB0104), U5 (NCP114), D1 (ESD), D2/D3 (LED) |
| Borrado en cascada (34 R/C) | 4 iteraciones de ERC → 24+7+2+1 pasivos huérfanos |
| Limpieza de wires | 133 wires y 22 junctions colgados, localizados por coordenadas del informe ERC |
| Conservado | J8 (Hirose ×2), X1, TP1-6, MRK1-6, PCB1, LA1, T1/T2, 66 símbolos de alimentación |

**Métricas:** 134 → 85 componentes · 29.298 → ~19.430 líneas · ERC 774 → 396

**Valoración: trabajo sólido y aprovechable.** Es la base de la Rev02.

**Efecto colateral no detectado en su momento:** al borrar `J1` (USB-B) desapareció el origen del
raíl `VCC5V-EXT` `[V — J1_IAS1 es el único origen de esa net en el .kicad_pcb]`, que quedó
huérfano. El informe Rev01 siguió listándolo después como si viniera de los Hirose.

---

## Fase B — Extracción de pinouts

Pinouts de 15 chips extraídos de una librería EasyEDA y documentados en `_work/pinouts.txt`
(556 líneas). Creados `sym-lib-table` y `fp-lib-table` apuntando a `${KICAD_3RD_PARTY}/EasyEDA`.

**Valoración: trabajo real y reutilizable** para los componentes que sobreviven a la revisión de
BOM.

---

## Fase C — Generación de `FRONTEND.kicad_sch` por script

Generado con `_work/phaseC_gen_frontend.py`: 14 instancias de chips con `lib_symbols` inlined,
60 etiquetas jerárquicas, árbol de alimentación, cadena de reloj, ADC, DAC, mezclador,
3 conmutadores, cabecera RPi, 4 SMA, 16 condensadores de desacoplo, 38 no-connect y 17 wires
visuales.

**Valoración: a descartar.** No por la técnica, sino por el contenido:

- El mezclador ADL5801 no alcanza los 10.5 GHz para los que se especificó.
- El AVDD del AD9767 quedó en el raíl de 1.8 V, siendo un dispositivo de 3.3 V.
- El LDO de 1.8 V (ADP151, 200 mA) es insuficiente y disipa 1.6 W en un TSOT-23-5.
- Faltan por completo filtro anti-alias, filtro de reconstrucción, LNA, baluns y sintetizador.
- Los símbolos EasyEDA no tienen tipos eléctricos: 48 conflictos `pin_to_pin` que el ERC no puede
  interpretar.

---

## Fase D — Sincronización jerárquica y netclases

54 etiquetas locales convertidas a `hierarchical_label`; 13 sheet pins añadidos; netclases
"50 Ohm" y "100 Ohm" con patrones `ANT_*`, `MIX_*`, `RF_SW*`, `CLK_*`, `B7-CSI2-*`.

**Valoración: parcialmente aprovechable.** El mecanismo es correcto. Las netclases son
decorativas mientras no exista un stackup definido: 4 capas todas declaradas `signal` no dan
control de impedancia.

---

## Fase E — Generación de `PHASED_ARRAY.kicad_sch` por script

8× ADAR1000 con daisy-chain SPI, `ADDR0`/`ADDR1` cableados, `TR_CTRL` y `TX_LOAD` comunes,
8 etiquetas `RF_ANT_1..8`, 1 SMA y —según el informe— un header de interfaz de 8 pines.

**Valoración: a descartar.**

- Las unidades B de los 8 ADAR1000, que contienen los pines de alimentación, **no están
  colocadas**: los chips no están alimentados `[V — 8 errores `missing_power_pin`]`.
- El header de interfaz **no está instanciado** `[V — los únicos símbolos son 8 ADAR1000 y 1 SMA]`.
- Cero condensadores de desacoplo.
- `ADDR0`/`ADDR1` dan 4 direcciones, no las 8 que el informe describía; y el direccionamiento y
  el daisy-chain son alternativas, no acumulables.
- Cada ADAR1000 tiene 4 canales: 8 chips son 32 elementos, no 8.

**Y sobre todo:** este bloque no hay que diseñarlo. El proyecto abierto
[AERIS-10 / PLFM_RADAR](https://github.com/NawfalMotii79/PLFM_RADAR) ya tiene resueltos los
ADAR1000, los front-ends T/R, los mezcladores, los sintetizadores y el array.

---

## Fase F — "Placement en PCB"

34 footprints insertados en el `.kicad_pcb` y anotación de símbolos de alimentación.

**Valoración: no existe como placement.**

- Los 34 footprints son **cascarones sin un solo pad** `[V]`.
- Están situados **fuera del contorno de placa**, en Y = 145…245 mm frente a un contorno que
  acaba en Y = 127.3 mm `[V]`.
- Las referencias no coinciden con las del esquemático (`U_ADC` frente a `U_ADC1`, etc.) `[V]`.
- El `0 unconnected pads` que se reportó como prueba de conectividad correcta es cero **porque no
  hay pads**.

---

## Sobre los scripts de `_work/`

Contienen trabajo válido y trabajo a no repetir:

| Script | Reutilizable |
|---|---|
| `phaseA1_purge.py`, `phaseA2_cleanup_wires.py`, `phaseA3_iterative.py` | **Sí** — purga y limpieza, bien resueltas |
| `phaseB_extract_pins.py`, `inventory.py` | **Sí** — extracción de datos |
| `debug_*.py`, `fix_*.py` | Utilidades puntuales |
| `phaseC_*.py`, `phaseD_final.py`, `phaseE_phased_array.py`, `phaseF_placement.py` | **No** — generación de esquemático y placement por script |

La lección está en la [nota metodológica de la auditoría](AUDITORIA_Rev01.md#7-nota-metodológica):
generar esquemáticos por script y validarlos contando infracciones de ERC no funciona cuando los
símbolos carecen de tipos eléctricos y el circuito es de RF. Un recuento de ERC que baja no
significa que el circuito mejore; significa que hay menos cosas que el ERC sabe comprobar.

---

## Estado final del Rev01-WIP

| Métrica | Valor `[V]` |
|---|---|
| ERC, esquema raíz | 1.129 infracciones |
| ERC, FRONTEND | 660 |
| ERC, PHASED_ARRAY | 312 |
| DRC, PCB | 1.942 violaciones |
| Pads en el PCB | 488 (todos del import original) |
| Footprints nuevos con pads | **0** |
