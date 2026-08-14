# KV260-IAS2RF — Front-End RF unificado (SDR + Radar FMCW banda X) para AMD Kria KV260

**Estado: diseño en curso (Rev02, fase de arquitectura). No fabricable. No hay hardware validado.**

Este repositorio contiene el desarrollo de una placa adaptadora para la **AMD Kria KV260 Vision
AI Starter Kit** que se acopla por los conectores Hirose de las interfaces IAS y aloja los
conversores, el reloj común y una **FPGA de front-end**, dando servicio a dos cadenas:

- **Canal 1 — SDR multibanda:** walkie, HF, AM, FM, VHF/UHF. Recepción y transmisión
- **Canal 2 — radar 10.5 GHz:** IF de la cadena de banda X del proyecto abierto
  [AERIS-10 / PLFM_RADAR](https://github.com/NawfalMotii79/PLFM_RADAR), con beamforming sobre
  ADAR1000

La cadena de 10.5 GHz **no se rediseña aquí**: se reutiliza AERIS-10. La placa se dimensiona para
**8 ADAR1000 (32 canales)**, de modo que soporte tanto la variante Nexus (4 chips) como la
Extended (8 chips).

> ### Hallazgo que condiciona todo el proyecto
>
> El conector **IAS0 (J7) de la KV260 no llega a la lógica programable**: sus carriles MIPI
> entran en un ISP AP1302 soldado en la carrier card. Solo **IAS1 (J8)** está cableado
> directamente al SoM. Además, **la KV260 no tiene ninguna cabecera Raspberry Pi de 40 pines**
> (J9 es un conector de cámara de 15 pines) y **los transceptores GTH no son accesibles**.
>
> El presupuesto real de E/S entre la KV260 y una placa externa es de **8 pares diferenciales y
> ~14 señales sueltas**. De ahí la FPGA de front-end. Ver [docs/RIESGOS.md](docs/RIESGOS.md).

## Origen del proyecto y atribución

Este proyecto es un **fork** del diseño de hardware abierto
[Allied Vision Adapter Board CSI-2 for Kria KV260](https://github.com/alliedvision), publicado
bajo licencia MIT (ver [LICENSE](LICENSE)). De aquel diseño se conserva:

- La geometría de la placa y su acoplamiento mecánico a la KV260
- Los dos conectores Hirose BM20B(0.8)-34DP (IAS0 / IAS1) y su cableado a la SoM
- El stackup y las reglas de fabricación originales

Todo lo demás (electrónica de cámara MIPI, level shifters, alimentación USB) se ha eliminado y
se sustituye por la cadena de RF descrita en la documentación. **Este repositorio ya no produce
una placa adaptadora de cámaras Allied Vision.** Si buscas eso, usa el proyecto original.

## Documentación

| Documento | Contenido |
|---|---|
| **[HANDOFF.md](HANDOFF.md)** | **Empieza aquí si retomas el proyecto.** Resumen autocontenido: estado, hallazgos, decisiones pendientes y reglas de trabajo |
| **[docs/PLATAFORMA_4X4.md](docs/PLATAFORMA_4X4.md)** | **Visión de sistema.** Esta placa es un subsistema de una plataforma de sensores y comunicaciones para un 4×4 de expedición: LiDAR, SDR, radar, OBD2 |
| **[docs/LISTA_COMPRA.md](docs/LISTA_COMPRA.md)** | Lista de material y checklist por etapas, con costes orientativos |
| **[ARCHITECTURE_draft_es.md](ARCHITECTURE_draft_es.md)** | **Documento maestro.** Arquitectura Rev03: FPGA de front-end, enlace con la Kria, conversores, plan de frecuencias, integración con AERIS-10, BOM |
| [docs/AUDITORIA_Rev01.md](docs/AUDITORIA_Rev01.md) | Auditoría de los ficheros actuales: qué hay realmente en el repo frente a lo que la documentación anterior afirmaba |
| [docs/RIESGOS.md](docs/RIESGOS.md) | Bloqueantes y riesgos abiertos, priorizados, con acción concreta para cerrar cada uno |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Plan de trabajo por fases con criterios de salida verificables |
| [docs/HISTORIAL_Rev01.md](docs/HISTORIAL_Rev01.md) | Registro del trabajo hecho sobre el Rev01 (purga del esquema original y generación por script), con su valoración |

**Empieza por [docs/RIESGOS.md](docs/RIESGOS.md)** si vas a retomar el proyecto: hay tres
incógnitas bloqueantes que condicionan la arquitectura y deben resolverse antes de tocar
un esquemático.

## Estado real de los ficheros de diseño

Los ficheros KiCad del repositorio corresponden al **Rev01-WIP**, un estado intermedio que
**no refleja la arquitectura Rev02** documentada aquí y que contiene errores de selección de
componentes ya identificados. En concreto:

| Fichero | Estado real |
|---|---|
| `CSI2-KRIA-KV260_Rev01-2.kicad_sch` | Esquema original purgado de electrónica de cámara. **Utilizable como base.** |
| `FRONTEND.kicad_sch` | Generado por script, sin revisión eléctrica. Contiene componentes descartados. **A rehacer.** |
| `PHASED_ARRAY.kicad_sch` | Generado por script. Los ADAR1000 no tienen alimentación conectada. **A rehacer.** |
| `CSI2-KRIA-KV260_Rev01.kicad_pcb` | Layout original + 34 footprints vacíos (sin pads ni nets) situados fuera del contorno de placa. **El placement no existe.** |
| `PCB/`, `Documents/` | Fuentes Altium y salidas de fabricación del diseño Allied Vision original, intactas. |

Detalle y evidencia en [docs/AUDITORIA_Rev01.md](docs/AUDITORIA_Rev01.md).

## Entorno

- **KiCad 10** para esquemático y layout (el proyecto se migró desde Altium Designer 22)
- Los ficheros Altium originales se conservan en `PCB/` como referencia histórica
- Los scripts de manipulación del Rev01 están en `_work/`; ver la nota metodológica en
  [docs/HISTORIAL_Rev01.md](docs/HISTORIAL_Rev01.md) antes de reutilizarlos

## Aviso legal

Este diseño transmite en bandas cuyo uso está regulado. La operación del transmisor SDR
requiere licencia de radioaficionado o autorización equivalente, y la emisión en 10.4–10.6 GHz
está sujeta a asignaciones nacionales que **no** son de uso libre en todos los países. Ver la
sección de cumplimiento normativo del documento maestro. La responsabilidad de operar dentro
de la legalidad aplicable es de quien construya y use el equipo.

## Licencia

MIT — ver [LICENSE](LICENSE). Se mantiene la licencia y la atribución del proyecto original de
Allied Vision.
