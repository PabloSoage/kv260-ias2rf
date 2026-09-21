# Sensing and communications platform for an expedition vehicle

*21 September 2026 · System view*

---

## 1. Goal

Turn an **AMD Kria KV260** into the brain of a platform carried in an expedition 4×4, able to
operate far from coverage and infrastructure:

| Subsystem | Function |
|---|---|
| **LiDAR** | See in fog and at night, and know the terrain under the vehicle. 3D render and route mapping |
| **SDR RX** | Listen to HF, AM, FM, airband and walkies, and detect emissions (drones at 5.8 GHz, control links at 2.4 GHz) |
| **SDR — location finding** | Work out where a signal comes from, by interferometry and by triangulating as the vehicle moves |
| **SDR TX** | Communicate on amateur bands when there is no coverage |
| **Radar** | Detection and location of targets at range (AERIS-10, 10.5 GHz, beamforming) |
| **OBD2 / CAN** | Vehicle telemetry, and **odometry for LiDAR fusion** |

**Vehicle:** Mitsubishi Montero V80 3.2 DiD 4M41, Intense, manual, long wheelbase, 7 seats, Euro 4,
no DPF, EGR and swirl flaps deleted, Stage 1 at 200 hp. Secondary alternator and LiFePO4 battery.

Framed this way, **the KV260 makes complete sense**: the DPU is exactly what is needed for point
cloud segmentation, target classification and sensor fusion. This is the first framing in which the
board is on home ground.

---

## 2. Overall assessment

The vision is coherent and the pieces fit. Three observations before the detail.

### 2.1 This is five projects, not one

Each subsystem carries its own risk, schedule and learning curve. Attempting them in parallel is
the most reliable way to finish none of them. §6 proposes an order, and it is not the order they
appear in on the wish list.

### 2.2 The LiDAR needs no custom hardware — it can start today

It connects over USB or Ethernet. The KV260 has 4× USB 3.0 and Gigabit Ethernet. **No boards
designed, no soldering.** By a distance it has the best value-to-effort ratio in the whole project,
and it is probably what gets used most day to day.

### 2.3 Do not mix the instrument with the lifeline

This is the observation that matters most.

For **listening, scanning and locating**, an SDR driven by the KV260 is the right tool. For
**talking to someone when you are genuinely in trouble**, the right tool is a commercial
type-approved transceiver, with physical controls, its own battery and no computer in the path.

If the day you need to call for help you are depending on a prototype — a serial link you wrote, a
Linux that boots, an FPGA that configures — you have a single point of failure exactly where you
cannot afford one. **In a safety context, redundancy is worth more than integration.** An FT-891 or
a dual-band mobile costs less than the board being designed here, and works with the engine off and
the laptop shut.

That does not diminish the SDR. It gives it its real role, which is as an instrument.

---

## 3. Subsystems

### 3.1 LiDAR

**The under-vehicle problem, and its solution.** A LiDAR cannot see beneath the vehicle: there is no
line of sight. The correct way to solve it is to **look ahead and remember**:

```
Forward LiDAR (sweeps 2–10 m ahead)
        |
        v
   SLAM + odometry  <-- wheel speed over CAN + IMU
        |
        v
  Persistent local 3D map
        |
        v
  "What is under you now, you scanned three metres back"
```

This makes odometry a functional requirement rather than a luxury — and it is what **ties the
OBD/CAN subsystem to the LiDAR one**. The two things that looked independent are not.

**Candidates:** Livox Mid-360 (360° × 59°, Ethernet, official ROS2 driver, widely used in mobile
robotics) or Unitree L2 (360° × 96°, cheaper). Both have open SLAM available (FAST-LIO2 and
similar).

**Where the DPU comes in:** point cloud segmentation (drivable ground against obstacle),
classification, and detection of ruts and rocks. That is inference, and it is what the board was
bought for.

**Caveat `[E]`:** LiDAR degrades in thick fog and heavy rain — droplets scatter the infrared. It is
far better than human night vision, but it is not magic. The sensor that genuinely penetrates fog is
radar, specifically at 77 GHz (§3.4).

---

### 3.2 SDR — reception and location finding

This is the highest-value subsystem among those that do depend on the custom board.

**Intended coverage and how it is achieved:**

| Band | Content | Route |
|---|---|---|
| 0.1 – 30 MHz | AM, shortwave, **amateur HF**, CB | Direct sampling |
| 88 – 108 MHz | FM broadcast | Conversion |
| 118 – 137 MHz | Airband | Conversion |
| 144 – 148 / 430 – 440 MHz | Amateur (2 m / 70 cm) | Conversion |
| 446 MHz | **PMR446 walkies** | Conversion |
| 2.4 GHz | Drone control links | **Additional converter** (§3.3) |
| 5.8 GHz | **Drone FPV video** | **Additional converter** (§3.3) |

**Direction finding needs more than two channels.** This matters and it drives the design:

| Coherent channels | What it allows |
|---|---|
| 1 | Listening only |
| 2 | One interferometric baseline → bearing **with ambiguity** |
| 4 – 5 | Real direction finding, unambiguous (what a KrakenSDR does with 5) |

The AD9253 is a **quad** ADC. Using all four coherently is the natural direction-finding
configuration — but it does not fit through IAS1: four channels in 1-lane mode are 4 data lanes +
`DCO` + `FCO` = **6 pairs**, and IAS1 has 5.

→ **Direction finding is a second argument for the front-end FPGA**, alongside the radar.

**Triangulating by moving the vehicle:** this works, and it is a classic technique. You take
bearings from different positions and cross them. It needs accurate position and heading at each
bearing → **GPS + IMU**, another dependency shared with the LiDAR.

---

### 3.3 Drone detection (2.4 / 5.8 GHz)

This falls **outside** the specified SDR front end, which reaches about 500 MHz. An additional block
is needed: a downconverter from 2.4 and 5.8 GHz to the receiver's IF.

It is a relatively simple module (LNA + mixer + synthesiser + filter), and low-cost commercial
options exist. **Detecting** drone emissions is passive reception: legal anywhere.

---

### 3.4 Radar — the important correction

**I believe the radar being built is the wrong one for the job described.**

AERIS-10 is a 10.5 GHz surveillance radar with a beamforming array, meant to detect targets at
**3 – 20 km**. It is a superb and very ambitious instrument. But for *"seeing an obstacle under the
vehicle"* or *"seeing in fog"*, the tool industry builds for exactly that is **automotive radar at
76 – 81 GHz**:

| | AERIS-10 (10.5 GHz) | Automotive radar (77 GHz) |
|---|---|---|
| Designed for | Surveillance, targets at kilometres | **Obstacles in front of a vehicle** |
| Legality in the EU | Amateur **secondary** in 10.45–10.5, special authorisation | **76–77 GHz allocated to vehicular radar, no licence** |
| Hardware | 3 boards + array + front-end FPGA | **One chip with antenna on package** (TI AWR1843AOP and similar) |
| Cost and effort | Very high | Affordable evaluation module |
| Fog, dust, rain | Good | Good — it is its reason for existing |

**These are two different radars for two different jobs.** The question to answer before going
further is: *is the radar for seeing obstacles while driving, or for detecting things far away
(drones, aircraft, vehicles at kilometres)?*

- **Obstacles and driving in fog** → 77 GHz. Cheap, legal, solved.
- **Surveillance at range** → AERIS-10. That is the big project, and then the front-end FPGA is
  justified.
- **Both** → they are separate subsystems, and the 77 GHz one should come first because it is
  trivial by comparison.

On the legality of AERIS, piece by piece: in Spain the 10.45 – 10.5 GHz segment is allocated to the
amateur service on a **secondary** basis, and use of 10.0 – 10.5 GHz requires **special
authorisation**. A formal mechanism for *temporary and experimental use* exists. So **there is a
legal route** — it is not a dead end, but it is paperwork, it is secondary (you may not cause
interference to primary services) and it leaves **50 MHz** of room, which limits the sweep and
therefore range resolution to about 3 m.

---

### 3.5 SDR — transmission

Two things that look alike need separating here.

**Bands you may transmit on legally, with an amateur licence:** HF (all amateur bands), 2 m
(144–146), 70 cm (430–440).

**Bands you may not transmit on with home-built equipment:** PMR446 requires type-approved
equipment; FM broadcast and airband are out of the question. **Receiving on them is free.**

A practical detail: amateur 70 cm (430–440) sits right next to PMR446 (446). With a licence you get
legal communication in the same part of the spectrum and with the same antenna.

**In a genuine emergency**, the regulations (ITU Radio Regulations Article 25, and Spanish
regulation) permit using any means to call for help. That is a right in a distress situation, not a
licence to operate out of band the rest of the time.

**Recommended route:** get the licence — the exam is not hard and the paperwork takes months, so
**start now, in parallel with the hardware**. And look at **REMER** (the Spanish civil protection
emergency radio network): it is a volunteer network that fits this use case exactly and brings
context, training and a community.

---

### 3.6 OBD2 / CAN

**The Scanmatik 3 is no use on board.** It is a J2534/RP1210 interface with software for **Windows
and Android**; there is no Linux support, let alone aarch64. It is an excellent diagnostic tool —
for the laptop, in the garage.

**For permanent logging on the Kria:** a **SocketCAN-compatible USB-CAN adapter** (CANable,
PCAN-USB or similar). SocketCAN is in the Linux kernel, it is stable, and `can-utils` gives you
capture and decoding immediately. The Euro 4 V80 carries CAN on the OBD port (ISO 15765-4)
`[E — confirm on the vehicle]`.

**And remember this is not just telemetry:** wheel speed over CAN is the odometry the LiDAR SLAM
needs (§3.1). It is a sensor, not an ornament.

---

## 4. Power and environment — what a bench design ignores

A vehicle is a hostile electrical environment and this affects **every** board in the project.

| Phenomenon | Design consequence |
|---|---|
| **Load dump** (battery disconnected while the alternator charges): tens of volts | Input protection to **ISO 7637-2**. A bench TVS is not enough |
| **Cold crank**: the rail drops to 6–7 V on starting | Either the system tolerates the dip, or it inhibits during cranking |
| Alternator ripple and switching noise | Serious input filtering. And it is noise **right in the HF bands you want to listen to** |
| Vibration | Connectors with retention, no loose 2.54 mm headers, threadlocked fasteners |
| Temperature: −10 to +70 °C in the cabin, worse in the engine bay | Industrial grade on the critical parts |
| Dust and water | Suitable IP enclosure; the KV260's fansink needs filtered air |

**Power budget `[E]`, to be refined:**

| Consumer | Power |
|---|---|
| KV260 | 36 W (12 V / 3 A) |
| LiDAR | 10 – 20 W |
| SDR (RX) | 10 – 15 W |
| AERIS Extended radar | **Very high**: 16 GaN amplifiers of 10 W. Pulsed, but the peak drives the sizing |
| **Total without radar** | **~60 – 70 W** |

Sixty or seventy watts continuous with the engine off is about 6 A at 12 V: a 100 Ah LiFePO4 gives
many hours. **With the Extended radar the order of magnitude changes entirely** and the sums have to
be done properly before buying anything.

**Noise from the secondary alternator and the DC/DC converters will be your worst enemy on HF.** It
is the number one practical problem of any vehicle radio installation, and it deserves as much
design attention as the receiver itself.

---

## 5. System architecture

```
                    +------------------------------------------+
   LiDAR ====Eth====|                                          |
                    |            Kria KV260                    |
   USB-CAN ==USB====|                                          |
     |              |  PS: Linux, SLAM, fusion, GUI, logging   |
     +- OBD2        |  PL: SDR and radar DSP                   |
                    |  DPU: segmentation, classification       |
   GPS+IMU ==USB====|                                          |
                    +----+--------------------------+----------+
                    J8/IAS1 (5 pairs)          J2/Pmod (8 signals)
                         |                          |
                    +----+--------------------------+----------+
                    |     ADAPTER BOARD + FRONT-END FPGA       |
                    |   ADC · DAC · common clock · switching   |
                    +----+--------------+--------------+-------+
                         |              |              |
              +----------+---+  +-------+------+  +----+---------+
              | SDR front end|  | 2.4 / 5.8GHz |  |  AERIS-10    |
              | HF/VHF/UHF   |  | converter    |  |  (radar)     |
              | RX + TX      |  | (drones)     |  |              |
              +--------------+  +--------------+  +--------------+

   -- DELIBERATELY OUTSIDE THE SYSTEM --
   Commercial type-approved transceiver (HF and/or dual-band) for emergency comms
```

---

## 6. Recommended order

This is not the order of the wish list. It is sorted by **value delivered divided by risk**, and
every stage leaves something usable even if you abandon the next one.

| # | Stage | Custom hardware | What you get |
|---|---|---|---|
| **0** | **Commercial SDR over USB** (HackRF, KrakenSDR) | **None** | You listen and locate **now**. And you find out what you actually need |
| **1** | **LiDAR** over Ethernet + SLAM | **None** | Vision in fog and at night, 3D mapping |
| **2** | **OBD/CAN** with a SocketCAN adapter | **None** | Telemetry + odometry for the SLAM |
| **3** | **Amateur licence** + commercial transceiver | **None** | Legal, reliable communication in the middle of nowhere |
| **4** | **Simple SDR RX adapter** (AD9253 on IAS1) | Simple board | Validates the IAS1 interface. Integrated receiver |
| **5** | **SDR front end** (filters, LNA, mixer, synthesiser) + TX | RF board | Full coverage and transmission |
| **6** | **77 GHz radar** (if the goal is obstacles) | Commercial module | Genuinely seeing in fog |
| **7** | **Front-end FPGA** + 4-channel direction finding | FPGA board | Unambiguous location finding |
| **8** | **AERIS-10** (if the goal is surveillance at range) | 3 boards + array | The big project |

### Why stage 0 is the most important

**Do not design a board to find out what you need.** A HackRF covers 1 MHz to 6 GHz — including the
5.8 GHz of drones — and costs less than a prototype run. A KrakenSDR does 5-channel direction
finding out of the box. Both go over USB to the KV260 and work today.

Drive with that for six months. You will discover that half your requirements were wrong and that
there are three you had not anticipated. **Then** design the board, to solve what actually limits
you — which is what justifies a custom board: integration, a clock shared with the radar, and
transmit power, not basic capability.

---

## 7. Risks specific to this platform

| ID | Risk | Mitigation |
|---|---|---|
| **V-01** | Five projects in parallel → none finished | The order in §6. Every stage delivers something usable |
| **V-02** | Depending on a prototype to call for help | Independent commercial transceiver (§2.3) |
| **V-03** | The chosen radar does not serve the described use | Decide §3.4 before spending |
| **V-04** | Vehicle electrical noise wrecking HF reception | Filtering, shielding, grounding. Budget it as real work |
| **V-05** | Automotive environment (load dump, vibration, temperature) | ISO 7637-2, industrial grade, retained connectors |
| **V-06** | Extended radar power exceeding the installation | Do the sums before buying |
| **V-07** | Legality of transmission | Amateur licence; experimental authorisation for 10 GHz; 76–77 GHz exempt |
| **V-08** | Scanmatik 3 has no Linux support | USB-CAN + SocketCAN on board; SM3 for the garage |
| **V-09** | LiDAR degraded in dense fog and rain | Fuse with radar; do not depend on a single sensor |

---

## 8. What has to be decided

1. **What is the radar for?** Obstacles (→ 77 GHz) or surveillance at range (→ AERIS). This
   determines whether the front-end FPGA is needed for the radar, or only for direction finding.
2. **Is the front-end FPGA accepted?** (§4.3 of [ROADMAP.md](ROADMAP.md))
3. **Transmission integrated on the board, or a separate commercial transceiver?** My
   recommendation: both, with different roles.
4. **Do we start with stage 0?** It teaches the most and it is the only one with no risk.

---

See also: [SHOPPING_LIST.md](SHOPPING_LIST.md) for the parts breakdown per stage.
