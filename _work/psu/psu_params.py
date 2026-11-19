#!/usr/bin/env python3
"""
The PSU board (vehicle and bench power for both boards): every component value and every data-sheet figure the
design and the simulations use, in one place, with its source. [V] verified against the data sheet named, [E]
estimated, [C] chosen (a design decision, derived in psu_design.py).

The board takes the battery (or a bench supply) on J1 and feeds the two boards by their own cables from one ground:
  J1 -> D1 + D2 (two unidirectional TVS in series, opposed: +111 V / -27 V) -> U1 LTC4364 surge stopper with ideal
  diode: M1 (150 V pass FET, clamps the bus side at 48 V during a load dump) and M2 (100 V, reverse input and
  back-feed) -> C bulk -> L2 input filter -> R_ISNS (input current limit) -> U2 LM5177 four-switch buck-boost
  (Q2..Q5, L1, R_CS) -> +12V bus -> U3 TPS26631 (adapter output, J2) and U4 TPS26631 (KV260 output, J3).
"""

# ---------------------------------------------------------------- operating requirements
VOUT = 12.0                 # [C] regulated output; under the KV260's 13.2 V MP5016 cut-off (XTP682 p. 3) [V]
VIN_START = 6.0             # [C] about where the converter starts (EN/UVLO divider)
VIN_STOP = 3.0              # [C] about where it stops (ISO 16750-2 Level III: Us = 3.0 V, TIDUC53 Table 8) [V]
VIN_MIN_FULL = 4.3          # [C] full load down to 4.3 V at the board: Level II (Us = 4.5 V) less the harness drop
VIN_MAX_RUN = 36.0          # [C] continuous: jump start (24 V), Load Dump B (35 V suppressed) [V] ISO 16750-2
VIN_CLAMP = 50.0            # [C] the load dump clamp's worst level (D2 at its maximum, below), still running
FSW = 400e3                 # [C] switching frequency; DRSS spreads it by +-7.8 % (LM5177 SNVSBU4F 7.3.17) [V]

# loads (constant power; each board's own data)
P_ADAPTER = {"typ": 11.7, "max": 13.4}      # W [V] AUDIT_Rev08 2.1
I_ADAPTER_MAX = 1.12                        # A at 12 V [V]
P_KV260 = {"typ": 11.0}                     # W [E] the thermal model's K26 + carrier
I_KV_LIMIT = 3.0 * 1.07                     # A, U4's current limit at its tolerance [V] (R = 6.04 k, below)

# ---------------------------------------------------------------- LM5177 (U2), SNVSBU4F, January 2025 [V]
LM5177 = dict(
    vin_min=2.9, vin_max=60.0, vin_abs=85.0,        # ROC / abs max; 2.8 V needs V(BIAS) > 3.5 V (features)
    vref=1.0, vref_tol=0.01,
    gm_ea=600e-6, a_cs=10.0,                         # EA transconductance; current-sense gain (eq. 3)
    vcs_min=38.5e-3, vcs_typ=50e-3, vcs_max=58.5e-3, # positive peak current limit threshold
    visns=50e-3, visns_min=49e-3, visns_max=51.7e-3, # average current limiter threshold
    uvlo_r=1.25, uvlo_r_min=1.22, uvlo_r_max=1.28,   # EN/UVLO rising
    uvlo_f=1.20, uvlo_f_min=1.17, uvlo_f_max=1.23,   # EN/UVLO falling
    i_hyst=5e-6, i_hyst_min=4e-6, i_hyst_max=6e-6,   # UVLO hysteresis sink (below the threshold)
    vdet_f=2.7, vdet_f_max=2.85,                     # VIN falling detector
    i_ss=10e-6, vcc=5.0,
    ton_min_buck=197e-9, toff_min_boost=207e-9,      # at 600 kHz; used for the mode boundaries
    r_drv_up=1.3, r_drv_dn=0.6, r_drv_hi_up=1.3, r_drv_hi_dn=0.7,
    t_dead=21e-9, qg_max=42e-9,                      # per driver at 600 kHz, V(BIAS) = 12 V
    rth_ja=33.6, rth_jb=15.2,                         # HTSSOP-38
    ovp2=83.5,                                        # VOUT OVP2
)

# ---------------------------------------------------------------- MOSFETs [V]
# Q2/Q3: input half-bridge (sees VIN up to the clamp), Infineon BSC0805LS (100 V, logic level), LCSC C534374
BSC0805LS = dict(vds=100.0, rds_45=8.5e-3, rds_10=7.0e-3, rds_45_typ=7.7e-3, tc=1.6,   # tc: RDS(150 C)/RDS(25 C) [E] from fig. "RDS(on)=f(Tj)"
                 qg_45=16e-9, qgd=6e-9, qgs2=3.0e-9, qoss=41e-9, qrr=12e-9, rg=1.0, vplat=3.0,
                 rth_jc=1.5, rth_ja=50.0)
# Q4/Q5: output half-bridge (sees VOUT), Infineon BSC026N04LS, LCSC C3039672
BSC026N04LS = dict(vds=40.0, rds_45=3.6e-3, rds_45_typ=2.6e-3, tc=1.6,
                   qg_45=16e-9, qgd=5.2e-9, qgs2=3.0e-9, qoss=28e-9, qrr=57e-9, rg=0.9, vplat=3.0,
                   rth_jc=2.0, rth_ja=50.0)
# Q1: ideal-diode FET (reverse battery, back-feed), Infineon BSC040N10NS5, LCSC C534334; LM74700 drives it from
# its charge pump (V(VCAP) - V(ANODE) up to 15 V)
BSC040N10NS5 = dict(vds=100.0, rds_10=4.0e-3, tc=1.7, rth_ja=50.0)

# ---------------------------------------------------------------- magnetics and sense [V]
L1 = dict(part="KOHERelec MDA1870-2R2M", lcsc="C3015590", l=2.2e-6, tol=0.20, isat=35.0, irms=32.0,
          dcr=1.8e-3, dcr_max=2.2e-3, size=(17.8, 16.9, 6.7))
L1_ALT = dict(part="KOHERelec MDA1870-3R3M", lcsc="C3015591", l=3.3e-6, isat=32.0, irms=30.0, dcr_max=3.3e-3)
R_CS = 2.0e-3                # [C] peak current sense (between SW1 and L1), 2512, 1 %
R_ISNS = 3.0e-3              # [C] input average current sense, 2512, 1 %
R_DIFF, C_DIFF = 10.0, 150e-12  # [C] CSA/CSB filter, from eq. 15 with the 197 ns minimum on-time

# ---------------------------------------------------------------- protection [V]
# D1 + D2: the input clamp, two unidirectional SMC TVS in series and opposed (as TI TIDA-01179 does): positive
# pulses break D1 down through D2 forward, negative pulses break D2 down through D1 forward. 1500 W 10/1000 us.
SMCJ100A = dict(vbr_min=111.0, vbr_max=123.0, vc=162.0, ipp=9.3, p_1ms=1500.0)   # Littelfuse SMCJ series
SMCJ24A = dict(vbr_min=26.7, vbr_max=29.5, vc=38.9, ipp=38.6, p_1ms=1500.0)
# U1: Analog Devices LTC4364-2 (auto-retry), rev. B data sheet: VCC 4 to 80 V, -40 to 100 V abs; SOURCE -40 V;
# output clamp by FB (1.25 V); OV fault timer I = 2 uA + 0.644 uA/V (VCC - OUT - 0.5 V), FLT at 1.25 V, off at 1.35 V
LTC4364 = dict(vcc_min=4.0, vcc_max=80.0, vcc_abs=100.0, v_rev=-40.0, vfb=1.25, vtmr_f=1.25, vtmr_g=1.35,
               i_tmr0=2e-6, k_tmr=0.644e-6)
V_CLAMP = 48.0               # [C] the surge stopper's output clamp (LM5177 runs to 60 V; 63 V bulk capacitor)
C_TMR = 4.7e-6               # [C] fault timer: lets a whole Load Dump A pass (simulated in psu_transient.py)
# M1: Infineon IPB048N15N5 (150 V, 4.8 mOhm, D2PAK), rev. 2.1: SOA diagram 3 (DC at 40 V about 2.5 A at TC 25 C),
# Zth single pulse about 0.3 K/W at 0.1 s; M2: BSC040N10NS5 (above)
IPB048N15N5 = dict(vds=150.0, rds_10=4.8e-3, tc=1.8, rth_jc=0.5, soa_dc_40v=2.5)
TPS26631 = dict(r_on=31e-3, ilim_k=18e3, ilim_tol=0.07, vin_max=60.0, vin_abs=67.0, rth_ja=31.4)  # SLVSE94G

# ---------------------------------------------------------------- harness (vehicle side) [V]/[E]
# 1 m of 16 AWG each way (13.2 mOhm/m [V]) and the XT30 pair (about 1 mOhm a contact [E]). The battery's own
# resistance is part of the ISO 16750-2 profile (the profile is the voltage at the harness).
R_HARNESS = 2 * 1.0 * 0.0132 + 2 * 0.001
R_FILTER = 1.0e-3                       # input filter inductor L2 DCR [C] (below)
FUSE_BATTERY = 20.0                     # A, at the battery [C]
