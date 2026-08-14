# Plataforma de sensores y comunicaciones para vehículo de expedición

*14 de agosto de 2026 · Visión de sistema*

---

## 1. Objetivo

Convertir una **Kria KV260** en el cerebro de una plataforma embarcada en un 4×4 de expedición,
capaz de operar lejos de cobertura y de infraestructura:

| Subsistema | Función |
|---|---|
| **LiDAR** | Ver en niebla, de noche, y conocer el terreno bajo los bajos. Render 3D y mapeo de rutas |
| **SDR RX** | Escuchar HF, AM, FM, aeronáutica, walkies, y detectar emisiones (drones en 5.8 GHz, enlaces en 2.4 GHz) |
| **SDR — localización** | Determinar de dónde viene una señal, por interferometría y por triangulación desplazando el vehículo |
| **SDR TX** | Comunicar en bandas de aficionado cuando no hay cobertura |
| **Radar** | Detección y localización de blancos a distancia (AERIS-10, 10.5 GHz, beamforming) |
| **OBD2 / CAN** | Telemetría del vehículo, y **odometría para la fusión con el LiDAR** |

**Vehículo:** Mitsubishi Montero V80 3.2 DiD 4M41, Intense, manual, largo, 7 plazas, Euro 4, sin
DPF, EGR y palometas anuladas, Stage 1 a 200 CV. Alternador secundario y batería LiFePO4.

Con este encuadre, **la KV260 pasa a tener todo el sentido del mundo**: el DPU es exactamente lo
que hace falta para segmentación de nubes de puntos, clasificación de blancos y fusión de
sensores. Es la primera vez en este proyecto que la placa está en su terreno.

---

## 2. Valoración general

La visión es coherente y las piezas encajan. Tres observaciones antes de entrar en detalle.

### 2.1 Son cinco proyectos, no uno

Cada subsistema es un proyecto con su propio riesgo, su propio calendario y su propia curva de
aprendizaje. Intentarlos en paralelo es la forma más fiable de no terminar ninguno. En §6 hay un
orden propuesto, y no es el orden en el que aparecen en la lista de deseos.

### 2.2 El LiDAR no necesita hardware a medida — se puede empezar hoy

Conecta por USB o Ethernet. La KV260 tiene 4× USB 3.0 y Gigabit Ethernet. **Cero placas
diseñadas, cero soldadura.** Es, con diferencia, el mejor ratio valor/esfuerzo de todo el
proyecto, y probablemente lo que más vas a usar en el día a día.

### 2.3 No mezcles el instrumento con el salvavidas

Esta es la observación que más me importa transmitir.

Para **escuchar, escanear y localizar**, un SDR gobernado por la KV260 es la herramienta
adecuada. Para **hablar con alguien cuando estás en un apuro de verdad**, lo adecuado es un
transceptor comercial homologado, con sus mandos físicos, su batería y ningún ordenador de por
medio.

Si el día que necesitas pedir ayuda dependes de un prototipo —un enlace serie que escribiste tú,
un Linux que arranca, una FPGA que se configura—, tienes un único punto de fallo justo donde no
te lo puedes permitir. **En un contexto de seguridad, la redundancia vale más que la
integración.** Un FT-891 o un bibanda móvil cuestan menos que la placa que estás diseñando, y
funcionan con el motor parado y el portátil apagado.

Eso no resta valor al SDR: le da su papel real, que es el de instrumento.

---

## 3. Subsistemas

### 3.1 LiDAR

**El problema de los bajos, y su solución.** Un LiDAR no puede ver debajo del vehículo: no hay
línea de visión. La forma correcta de resolverlo es **mirar hacia delante y recordar**:

```
LiDAR frontal (barre 2–10 m por delante)
        │
        ▼
   SLAM + odometría  ◄── velocidad de ruedas por CAN + IMU
        │
        ▼
  Mapa 3D local persistente
        │
        ▼
  "Lo que ahora tienes bajo los bajos lo escaneaste hace 3 metros"
```

Esto convierte la odometría en un requisito funcional, no en un lujo — y es lo que **ata el
subsistema OBD/CAN al del LiDAR**. Las dos cosas que parecían independientes no lo son.

**Candidatos:** Livox Mid-360 (360° × 59°, Ethernet, driver ROS2 oficial, muy usado en robótica
móvil) o Unitree L2 (360° × 96°, más barato). Ambos con SLAM abierto disponible (FAST-LIO2 y
similares).

**Dónde entra el DPU:** segmentación de la nube de puntos (suelo transitable frente a obstáculo),
clasificación, y detección de badenes y rocas. Eso es inferencia, y es para lo que compraste la
placa.

**Aviso `[E]`:** el LiDAR en niebla cerrada y lluvia intensa se degrada — las gotas dispersan el
infrarrojo. Es mucho mejor que la vista humana de noche, pero no es mágico. El sensor que de
verdad atraviesa la niebla es el radar, y en concreto el de 77 GHz (§3.4).

---

### 3.2 SDR — recepción y localización

Es el subsistema con más valor de los que sí dependen de la placa a medida.

**Cobertura pretendida y cómo se consigue:**

| Banda | Contenido | Vía |
|---|---|---|
| 0.1 – 30 MHz | AM, onda corta, **HF de aficionado**, CB | Muestreo directo |
| 88 – 108 MHz | FM comercial | Conversión |
| 118 – 137 MHz | Aeronáutica | Conversión |
| 144 – 148 / 430 – 440 MHz | Aficionado (2 m / 70 cm) | Conversión |
| 446 MHz | **Walkies PMR446** | Conversión |
| 2.4 GHz | Enlaces de control de drones | **Convertidor adicional** (§3.3) |
| 5.8 GHz | **Vídeo FPV de drones** | **Convertidor adicional** (§3.3) |

**La localización necesita más de dos canales.** Esto es importante y condiciona el diseño:

| Canales coherentes | Qué permite |
|---|---|
| 1 | Solo escuchar |
| 2 | Una línea de base interferométrica → dirección **con ambigüedad** |
| 4 – 5 | Radiogoniometría real, sin ambigüedad (es lo que hace un KrakenSDR con 5) |

El AD9253 es un ADC **cuádruple**. Usar sus 4 canales de forma coherente es la configuración
natural para radiogoniometría — pero no cabe por IAS1: 4 canales en modo 1-lane son 4 carriles de
datos + `DCO` + `FCO` = **6 pares**, y en IAS1 solo hay 5.

→ **La radiogoniometría es otro argumento a favor de la FPGA de front-end**, junto con el radar.

**Triangulación desplazando el vehículo:** funciona, y es una técnica clásica. Tomas marcaciones
desde posiciones distintas y cruzas los rumbos. Requiere posición y orientación precisas en cada
marcación → **GPS + IMU**, otra dependencia compartida con el LiDAR.

---

### 3.3 Detección de drones (2.4 / 5.8 GHz)

Queda **fuera** del front-end SDR especificado, que llega a ~500 MHz. Hace falta un bloque
adicional: un convertidor de bajada de 2.4 y 5.8 GHz hacia la IF del receptor.

Es un módulo relativamente sencillo (LNA + mezclador + sintetizador + filtro), y existen soluciones
comerciales de bajo coste. **Detectar** emisiones de drones es recepción pasiva: legal en
cualquier sitio.

---

### 3.4 Radar — la corrección importante

**Creo que estás construyendo el radar equivocado para el trabajo que describes.**

AERIS-10 es un radar de vigilancia de 10.5 GHz con array de beamforming, pensado para detectar
blancos a **3 – 20 km**. Es un instrumento magnífico y muy ambicioso. Pero para *"ver un obstáculo
en los bajos"* o *"ver en niebla"*, la herramienta que la industria fabrica para exactamente eso
es el **radar de automoción de 76 – 81 GHz**:

| | AERIS-10 (10.5 GHz) | Radar de automoción (77 GHz) |
|---|---|---|
| Diseñado para | Vigilancia, blancos a kilómetros | **Obstáculos delante de un vehículo** |
| Legalidad en la UE | Aficionado **secundario** en 10.45–10.5, con autorización especial | **76–77 GHz atribuido a radar vehicular, sin licencia** |
| Hardware | 3 placas + array + FPGA de front-end | **Un chip con antena en el encapsulado** (TI AWR1843AOP y similares) |
| Coste y esfuerzo | Muy alto | Módulo de evaluación asequible |
| Niebla, polvo, lluvia | Bien | Bien — es su razón de existir |

**Son dos radares distintos para dos trabajos distintos.** La pregunta que hay que responder
antes de seguir es: *¿el radar es para ver obstáculos mientras conduces, o para detectar cosas
lejos (drones, aeronaves, vehículos a kilómetros)?*

- **Obstáculos y conducción en niebla** → 77 GHz. Barato, legal, resuelto.
- **Vigilancia a distancia** → AERIS-10. Es el proyecto grande, y entonces la FPGA de front-end
  está justificada.
- **Ambas** → son dos subsistemas separados, y el de 77 GHz debería ir primero porque es
  trivial en comparación.

Sobre la legalidad de AERIS, y por partes: en España el tramo **10.45 – 10.5 GHz está atribuido
al servicio de aficionados a título secundario**, y el uso de 10.0 – 10.5 GHz requiere
**autorización especial**. Existe un mecanismo formal de *autorización de uso temporal y
experimental*. O sea, **hay una vía legal** — no es un callejón sin salida, pero es papeleo, es a
título secundario (no puedes causar interferencia a los servicios primarios) y te deja **50 MHz**
de margen, lo que limita el barrido y por tanto la resolución en distancia a ~3 m.

---

### 3.5 SDR — transmisión

Aquí conviene separar dos cosas que se parecen pero no lo son.

**Bandas donde puedes transmitir legalmente, con licencia de radioaficionado:**
HF (todas las bandas de aficionado), 2 m (144–146), 70 cm (430–440).

**Bandas donde no puedes transmitir con equipo casero:** PMR446 exige equipo homologado; FM
comercial y aeronáutica están fuera de discusión. **Recibir en ellas es libre.**

Detalle práctico: el 70 cm de aficionado (430–440) está pegado a PMR446 (446). Con licencia
tienes comunicación legal en la misma zona del espectro y con la misma antena.

**En emergencia real**, la normativa (Reglamento de Radiocomunicaciones de la UIT, art. 25, y la
regulación española) permite usar cualquier medio para pedir auxilio. Eso es un derecho en una
situación de peligro, no una excusa para operar fuera de banda el resto del tiempo.

**Vía recomendada:** sácate la licencia — el examen no es difícil y el trámite tarda meses, así
que **empieza ya, en paralelo con el hardware**. Y mira la **REMER** (Red Radio de Emergencia de
Protección Civil): es una red de voluntarios que encaja exactamente con tu caso de uso y te da
contexto, formación y una comunidad.

---

### 3.6 OBD2 / CAN

**El Scanmatik 3 no te sirve a bordo.** Es un interfaz J2534/RP1210 con software para **Windows y
Android**; no hay soporte Linux, y menos en aarch64. Es una herramienta de diagnóstico
excelente — para el portátil, en el taller.

**Para registro permanente en la Kria:** un adaptador **USB-CAN compatible con SocketCAN**
(CANable, PCAN-USB o similar). SocketCAN está en el kernel de Linux, es estable, y `can-utils`
te da captura y decodificación inmediatas. El V80 Euro 4 lleva CAN en el OBD (ISO 15765-4)
`[E — confirmar en el vehículo]`.

**Y recuerda que esto no es solo telemetría:** la velocidad de ruedas por CAN es la odometría que
necesita el SLAM del LiDAR (§3.1). Es un sensor, no un adorno.

---

## 4. Alimentación y entorno — lo que un diseño de banco ignora

Un vehículo es un entorno eléctrico hostil y esto afecta a **todas** las placas del proyecto.

| Fenómeno | Consecuencia de diseño |
|---|---|
| **Load dump** (desconexión de batería con alternador cargando): picos de decenas de voltios | Protección de entrada según **ISO 7637-2**. Un TVS de banco no basta |
| **Cold crank**: la tensión cae a 6–7 V al arrancar | O el sistema tolera la caída, o se inhibe durante el arranque |
| Rizado del alternador y ruido de conmutación | Filtrado de entrada serio. Y es ruido **justo en las bandas de HF que quieres escuchar** |
| Vibración | Conectores con retención, nada de headers de 2.54 mm sueltos, tornillería con freno |
| Temperatura: −10 a +70 °C en habitáculo, peor en vano motor | Rango industrial en los componentes críticos |
| Polvo y agua | Caja con IP adecuado; el fansink de la KV260 necesita aire filtrado |

**Presupuesto de potencia `[E]`, a afinar:**

| Consumidor | Potencia |
|---|---|
| KV260 | 36 W (12 V / 3 A) |
| LiDAR | 10 – 20 W |
| SDR (RX) | 10 – 15 W |
| Radar AERIS Extended | **Muy alto**: 16 amplificadores GaN de 10 W. Pulsado, pero el pico manda en el dimensionado |
| **Total sin radar** | **~60 – 70 W** |

Sesenta o setenta vatios continuos con el motor parado son unos 6 A a 12 V: una LiFePO4 de 100 Ah
te da muchas horas. **Con el radar Extended, el orden de magnitud cambia por completo** y hay que
hacer las cuentas en serio antes de comprar nada.

**El ruido del alternador secundario y de los convertidores DC/DC va a ser tu peor enemigo en
HF.** Es el problema práctico número uno de cualquier instalación de radio en vehículo, y merece
tanta atención de diseño como el propio receptor.

---

## 5. Arquitectura de sistema

```
                    ┌──────────────────────────────────────────┐
   LiDAR ═══Eth═════│                                          │
                    │            Kria KV260                    │
   USB-CAN ══USB════│                                          │
     │              │  PS: Linux, SLAM, fusión, GUI, registro  │
     └─ OBD2        │  PL: DSP de SDR y radar                  │
                    │  DPU: segmentación, clasificación        │
   GPS+IMU ══USB════│                                          │
                    └────┬────────────────────────┬────────────┘
                    J8/IAS1 (5 pares)        J2/Pmod (8 señales)
                         │                        │
                    ┌────┴────────────────────────┴────────────┐
                    │      PLACA ADAPTADORA + FPGA front-end   │
                    │   ADC · DAC · reloj común · conmutación  │
                    └────┬──────────────┬──────────────┬───────┘
                         │              │              │
              ┌──────────┴───┐  ┌───────┴──────┐  ┌────┴─────────┐
              │ Front-end SDR│  │ Convertidor  │  │  AERIS-10    │
              │ HF/VHF/UHF   │  │ 2.4 / 5.8GHz │  │  (radar)     │
              │ RX + TX      │  │ (drones)     │  │              │
              └──────────────┘  └──────────────┘  └──────────────┘

   ── FUERA DEL SISTEMA, A PROPÓSITO ──
   Transceptor comercial homologado (HF y/o bibanda) para comunicación de emergencia
```

---

## 6. Orden recomendado

No es el orden de la lista de deseos. Está ordenado por **valor entregado dividido por riesgo**,
y cada etapa deja algo utilizable aunque abandones la siguiente.

| # | Etapa | Hardware a medida | Qué te llevas |
|---|---|---|---|
| **0** | **SDR comercial por USB** (HackRF, KrakenSDR) | **Ninguno** | Escuchas y localizas **ya**. Y descubres qué necesitas de verdad |
| **1** | **LiDAR** por Ethernet + SLAM | **Ninguno** | Visión en niebla y de noche, mapeo 3D |
| **2** | **OBD/CAN** con adaptador SocketCAN | **Ninguno** | Telemetría + odometría para el SLAM |
| **3** | **Licencia de radioaficionado** + transceptor comercial | **Ninguno** | Comunicación legal y fiable en medio de la nada |
| **4** | **Adaptador SDR RX simple** (AD9253 en IAS1) | Placa sencilla | Valida la interfaz IAS1. Receptor integrado |
| **5** | **Front-end SDR** (filtros, LNA, mezclador, sintetizador) + TX | Placa de RF | Cobertura completa y transmisión |
| **6** | **Radar de 77 GHz** (si el objetivo son obstáculos) | Módulo comercial | Ver en niebla de verdad |
| **7** | **FPGA de front-end** + radiogoniometría de 4 canales | Placa FPGA | Localización sin ambigüedad |
| **8** | **AERIS-10** (si el objetivo es vigilancia a distancia) | 3 placas + array | El proyecto grande |

### Por qué la etapa 0 es la más importante

**No diseñes una placa para averiguar qué necesitas.** Un HackRF cubre de 1 MHz a 6 GHz —
incluidos los 5.8 GHz de los drones— y cuesta menos que una tirada de prototipos. Un KrakenSDR
hace radiogoniometría de 5 canales lista para usar. Ambos van por USB a la KV260 y funcionan hoy.

Conduce con eso seis meses. Vas a descubrir que la mitad de tus requisitos eran equivocados y que
hay tres que no habías previsto. **Entonces** diseña la placa, para resolver lo que realmente te
limita — que es lo que justifica una placa a medida: integración, reloj común con el radar y
potencia de transmisión, no capacidad básica.

---

## 7. Riesgos propios de esta plataforma

| ID | Riesgo | Mitigación |
|---|---|---|
| **V-01** | Cinco proyectos en paralelo → ninguno terminado | El orden de §6. Cada etapa entrega algo usable |
| **V-02** | Depender de un prototipo para pedir auxilio | Transceptor comercial independiente (§2.3) |
| **V-03** | El radar elegido no sirve para el uso descrito | Decidir §3.4 antes de gastar |
| **V-04** | Ruido eléctrico del vehículo arruinando la recepción en HF | Filtrado, apantallamiento, masas. Presupuestarlo como trabajo real |
| **V-05** | Entorno automovilístico (load dump, vibración, temperatura) | ISO 7637-2, rango industrial, conectores con retención |
| **V-06** | Consumo del radar Extended desbordando la instalación | Cuentas antes de comprar |
| **V-07** | Legalidad de la emisión | Licencia de aficionado; autorización experimental para 10 GHz; 76–77 GHz exento |
| **V-08** | Scanmatik 3 sin soporte Linux | USB-CAN + SocketCAN para a bordo; SM3 para el taller |
| **V-09** | LiDAR degradado en niebla y lluvia densas | Fusión con radar; no depender de un único sensor |

---

## 8. Qué hay que decidir

1. **¿Para qué es el radar?** Obstáculos (→ 77 GHz) o vigilancia a distancia (→ AERIS). De esto
   depende si la FPGA de front-end es necesaria por el radar, o solo por la radiogoniometría.
2. **¿Se acepta la FPGA de front-end?** (§4.3 de [ROADMAP.md](ROADMAP.md))
3. **¿Transmisión integrada en la placa, o transceptor comercial aparte?** Mi recomendación:
   las dos cosas, con papeles distintos.
4. **¿Empezamos por la etapa 0?** Es la que más te enseña y la única que no tiene riesgo.

---

Ver también: [LISTA_COMPRA.md](LISTA_COMPRA.md) para el detalle de material por etapa.
