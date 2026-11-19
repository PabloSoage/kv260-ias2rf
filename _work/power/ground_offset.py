#!/usr/bin/env python3
"""
Ground offset and ground loops between the adapter and the KV260 (BOARD_MANUAL section 6).

The two boards share their ground through the board-to-board connectors (J101 on IAS1, J102 on IAS0:
11 ground contacts each), the FFC to the KV260's J9 (2 ground conductors) and the Pmod cable (2). Each board
also has its own 12 V input. Whenever both inputs return to different points (two places on a car body, or
two earthed supplies at home), those inter-board grounds close a loop, and any voltage between the two
return points drives a current through them.

This script solves that network as resistors (DC, and 50 Hz, where the cords are still resistive) for:
  1. today's wiring, the two grounds on different points of the car (ISO 16750-2 section 4.8: +-1 V offset);
  2. today's wiring, both grounds to the same point;
  3. the loss of one board's ground wire (the other board's return then crosses the connectors);
  4. the single power entry as built (sheet KVPWR): the KV260 fed from the adapter's J1004 by a jumper, one
     ground wire to the vehicle; also with the jumper's ground contact open, with the contacts at their maximum,
     and with one contact at half the others' resistance (uneven sharing: that contact carries about twice its
     share);
  5. at home, two earthed supplies with a 50 Hz voltage between their protective earths (the old wiring);
  6. at home with the single entry: one earthed supply, and an earthed monitor on the KV260's DisplayPort, the
     loop that remains.
It reports the current in each BM20 ground contact against its 0.3 A rating, and the voltage the loop
current leaves across the adapter's ground.

[V] verified against a data sheet or standard, [E] estimated. Values:
  BM20 contact: 0.3 A rated, 100 mOhm maximum [V] (Hirose BM20 catalogue D47513); 30 mOhm typical [E].
  Harness wire FLRY 0.5 mm^2: 37.1 mOhm/m at 20 C [V] (ISO 6722-1 maximum for 0.5 mm^2).
  Barrel jack contact (PJ-102AH on the adapter, PJ-202BH on the KV260): 20 mOhm [E].
  FFC, 1.0 mm pitch, 100 mm: 0.6 x 0.035 mm conductor, 82 mOhm, plus 2 x 20 mOhm contacts [E].
  Pmod ribbon, 28 AWG, 150 mm: 32 mOhm, plus 2 x 20 mOhm contacts [V/E].
  Adapter: 0.97 A typical, 1.12 A worst at 12 V [V] (AUDIT_Rev08 section 2.1).
  KV260: 0.92 A (11 W, the thermal model's K26 + carrier) [E]; 3 A, its brick's rating, as the worst case.
  KV260 input: MP5016 eFuse, OVP 13.2 V, current limit 5 A, SMAJ16A [V] (XTP682 rev 2, page 3).
  Single entry as built: U1010 limits the KV260 to 3.0 A +-7 %, so 3.19 A worst [V] (TPS26631, R1043 6.04 k);
  jumper 0.15 m of 18 AWG, 20.9 mOhm/m [V]; JST VH contact 10 mOhm maximum [V] (JST VH catalogue); the
  barrel plug in the KV260's J12, 20 mOhm [E]; L1004's ground winding 8 mOhm maximum [V] (SMM9070-501).
  Home loop, single entry: DisplayPort cable shield 2 m, 60 mOhm [E]; the monitor's mains cord PE 1.5 m of
  0.75 mm^2, 36 mOhm [V]; 10 m of 2.5 mm^2 PE between the outlets, 74 mOhm [V].

Usage:  py _work/power/ground_offset.py      (writes docs/sim/ground_offset.png and docs/sim/ground_offset.json)
"""
import json
import os

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_PNG = os.path.join(ROOT, "docs", "sim", "ground_offset.png")
OUT_JSON = os.path.join(ROOT, "docs", "sim", "ground_offset.json")

BM20_RATED = 0.3
R_BM20_TYP, R_BM20_MAX = 0.030, 0.100
N_BM20 = 22                       # 11 on J101 + 11 on J102
R_WIRE = 0.0371                   # ohm/m, 0.5 mm^2
R_JACK = 0.020
R_FFC = 0.082 + 2 * 0.020
R_PMOD = 0.032 + 2 * 0.020
I_ADAPTER_TYP, I_ADAPTER_MAX = 0.97, 1.12
I_KV_TYP, I_KV_MAX = 0.92, 3.0
I_KV_LIMIT = 3.0 * 1.07           # U1010's current limit at its tolerance: the KV260 cannot draw more
R_JUMPER = 0.15 * 0.0209 + 0.010 + R_JACK     # J1004 contact + 18 AWG + barrel plug, one conductor
R_L1004 = 0.008


def par(*rs):
    return 1.0 / sum(1.0 / r for r in rs)


def link(r_contact):
    """The inter-board ground: 22 BM20 contacts, 2 FFC conductors, 2 Pmod conductors, in parallel."""
    r_bm = r_contact / N_BM20
    r = par(r_bm, R_FFC / 2, R_PMOD / 2)
    return r, r / r_bm            # total, and the share of the current that the BM20 contacts carry


def solve(dv, l_a, l_k, i_a, i_k, r_contact, lose=None, single=False, r_pig=None):
    """Return the inter-board current (A, adapter -> KV260 positive) and the two ground node voltages.

    Nodes: a (adapter ground), k (KV260 ground). Return points: adapter's at 0 V, KV260's at dv.
    Each board's supply current returns into its own node. lose='a' or 'k' removes that board's wire.
    single=True: the KV260 is fed from the adapter, its return goes back to node a through the pigtail
    (r_pig) in parallel with the link, and there is no KV260 wire to the vehicle."""
    r_link, _ = link(r_contact)
    g_link = 1.0 / r_link
    if single:
        g_ka = g_link + 1.0 / r_pig
        g_a = 1.0 / (l_a * R_WIRE + R_JACK)
        # node a carries both returns to the vehicle; node k only to node a
        v_a = (i_a + i_k) / g_a
        v_k = v_a + i_k / g_ka
        return (v_a - v_k) * g_link, v_a, v_k
    g_a = 0.0 if lose == "a" else 1.0 / (l_a * R_WIRE + R_JACK)
    g_k = 0.0 if lose == "k" else 1.0 / (l_k * R_WIRE + R_JACK)
    G = np.array([[g_a + g_link, -g_link], [-g_link, g_k + g_link]])
    b = np.array([i_a, i_k + g_k * dv])
    v_a, v_k = np.linalg.solve(G, b)
    return (v_a - v_k) * g_link, v_a, v_k


def per_contact(i_link, r_contact):
    _, share = link(r_contact)
    return abs(i_link) * share / N_BM20


def main():
    res = {"params": {
        "bm20_rated_A": BM20_RATED, "bm20_contact_ohm_typ": R_BM20_TYP, "bm20_contact_ohm_max": R_BM20_MAX,
        "wire_ohm_per_m": R_WIRE, "jack_ohm": R_JACK, "ffc_ohm": R_FFC, "pmod_ohm": R_PMOD,
        "i_adapter_A": [I_ADAPTER_TYP, I_ADAPTER_MAX], "i_kv260_A": [I_KV_TYP, I_KV_MAX]}}
    r_link_typ, share_typ = link(R_BM20_TYP)
    r_link_max, share_max = link(R_BM20_MAX)
    res["link_ohm"] = {"typ": r_link_typ, "max": r_link_max, "bm20_share_typ": share_typ, "bm20_share_max": share_max}

    dv = np.linspace(-2.0, 2.0, 81)
    cases = {}
    # 1. different points, 1 m each, worst currents, typical (low) contact resistance: the most current
    for name, (la, lk, rc) in {"separate_1m_typ": (1.0, 1.0, R_BM20_TYP),
                              "separate_1m_max": (1.0, 1.0, R_BM20_MAX),
                              "separate_0p3m_typ": (0.3, 0.3, R_BM20_TYP),
                              "separate_3m_typ": (3.0, 3.0, R_BM20_TYP)}.items():
        ic = [per_contact(solve(d, la, lk, I_ADAPTER_MAX, I_KV_MAX, rc)[0], rc) for d in dv]
        cases[name] = ic
    # 2. same point (dv = 0), sweep the KV260 current and the wire lengths
    same = {}
    for la, lk in ((1.0, 1.0), (0.3, 2.0), (2.0, 0.3)):
        i_l = solve(0.0, la, lk, I_ADAPTER_MAX, I_KV_MAX, R_BM20_TYP)[0]
        same[f"{la}m/{lk}m"] = {"link_A": i_l, "per_contact_A": per_contact(i_l, R_BM20_TYP)}
    res["same_point"] = same
    # 3. ground loss
    loss = {}
    for lose, ia, ik in (("k", I_ADAPTER_MAX, I_KV_MAX), ("a", I_ADAPTER_MAX, I_KV_MAX)):
        i_l, v_a, v_k = solve(0.0, 1.0, 1.0, ia, ik, R_BM20_TYP, lose=lose)
        loss["KV260 wire lost" if lose == "k" else "adapter wire lost"] = {
            "link_A": abs(i_l), "per_contact_A": per_contact(i_l, R_BM20_TYP),
            "surviving_jack_A": ia + ik}
    res["ground_loss"] = loss
    # 4. single entry as built: the KV260's return splits between the jumper's ground and the link; the offset
    # between the vehicle points no longer matters (there is no second wire). Worst current: U1010's limit.
    r_pig = R_JUMPER
    ic_single = []
    for d in dv:
        i_l = solve(d, 1.0, 1.0, I_ADAPTER_MAX, I_KV_LIMIT, R_BM20_TYP, single=True, r_pig=r_pig)[0]
        ic_single.append(per_contact(i_l, R_BM20_TYP))
    cases["single_entry"] = ic_single

    def single(r_pig_, r_c, i_k):
        i_l = solve(0, 1, 1, I_ADAPTER_MAX, i_k, r_c, single=True, r_pig=r_pig_)[0]
        return {"link_A": i_l, "per_contact_A": per_contact(i_l, r_c)}
    res["single_entry"] = {"jumper_ohm": r_pig, "per_contact_A": ic_single[0], "input_A": I_ADAPTER_MAX + I_KV_LIMIT,
                           "link_A": single(r_pig, R_BM20_TYP, I_KV_LIMIT)["link_A"],
                           "typical_load": single(r_pig, R_BM20_TYP, I_KV_TYP),
                           "contacts_at_max": single(r_pig, R_BM20_MAX, I_KV_LIMIT),
                           "jumper_ground_open": single(1e6, R_BM20_TYP, I_KV_LIMIT),
                           "jumper_ground_open_contacts_at_max": single(1e6, R_BM20_MAX, I_KV_LIMIT)}

    def one_low(i_k, r_others, r_low):
        """One BM20 contact at r_low, the other 21 at r_others: the current in that one contact."""
        r = 1.0 / ((N_BM20 - 1) / r_others + 1.0 / r_low + 2 / R_FFC + 2 / R_PMOD)
        i_link = i_k * R_JUMPER / (r + R_JUMPER)
        return i_link * r / r_low
    res["single_entry"]["uneven"] = {
        "limit_one_at_half": one_low(I_KV_LIMIT, R_BM20_TYP, R_BM20_TYP / 2),
        "limit_one_at_third": one_low(I_KV_LIMIT, 1.5 * R_BM20_TYP, R_BM20_TYP / 2),
        "typical_one_at_half": one_low(I_KV_TYP, R_BM20_TYP, R_BM20_TYP / 2),
        "load_2A_one_at_third": one_low(2.0, 1.5 * R_BM20_TYP, R_BM20_TYP / 2)}
    # offsets at which the contacts reach their rating, today
    lim = {}
    for name in ("separate_0p3m_typ", "separate_1m_typ", "separate_3m_typ", "separate_1m_max"):
        arr = np.array(cases[name])
        over = dv[arr >= BM20_RATED]
        lim[name] = float(min(abs(over))) if over.size else None
    res["offset_at_rating_V"] = lim
    res["per_contact_at_1V"] = {k: float(np.interp(1.0, dv, v)) for k, v in cases.items()}

    # 5. home: two earthed supplies, a 50 Hz voltage between their earths (0.1 V typical, 1 V poor) [E].
    # Loop: 2 x 1.8 m DC cords (0.5 mm^2 return), 10 m of 2.5 mm^2 PE between the outlets (7.4 mOhm/m [V]),
    # 2 x 20 mOhm plug contacts, the inter-board link. Cords are resistive at 50 Hz (X = 2 pi 50 L, L about
    # 2 uH, 0.6 mOhm).
    r_loop = 2 * (1.8 * R_WIRE + R_JACK) + 10 * 0.0074 + 2 * 0.020 + r_link_typ
    home = {}
    for v in (0.1, 1.0):
        i = v / r_loop
        home[f"{v} V"] = {"loop_A": i, "per_contact_A": per_contact(i, R_BM20_TYP),
                          "adapter_ground_drop_uV": i * 0.5e-3 * 1e6}   # about 0.5 mOhm of plane across the board [E]
    res["home_50Hz"] = {"loop_ohm": r_loop, "cases": home}

    # 6. home, single entry: the supply's cord, L1004's ground winding, the link in parallel with the jumper's
    # ground, the DisplayPort shield, the monitor's PE, the PE between the outlets. The share of the loop current
    # in the link adds (as rms, 50 Hz on DC) to the KV260's own return.
    r_jl = par(r_link_typ, R_JUMPER)
    r_loop1 = (1.8 * R_WIRE + R_JACK) + R_L1004 + r_jl + 0.060 + 0.036 + 10 * 0.0074 + 2 * 0.020
    dc = single(R_JUMPER, R_BM20_TYP, I_KV_LIMIT)["link_A"]
    home1 = {}
    for v in (0.1, 1.0):
        i = v / r_loop1
        i_link_ac = i * R_JUMPER / (r_link_typ + R_JUMPER)
        rms = (dc ** 2 + i_link_ac ** 2) ** 0.5
        home1[f"{v} V"] = {"loop_A": i, "link_ac_A": i_link_ac, "per_contact_A": per_contact(rms, R_BM20_TYP),
                           "adapter_ground_drop_uV": i_link_ac * r_link_typ * 1e6}
    res["home_single_entry_50Hz"] = {"loop_ohm": r_loop1, "cases": home1}

    os.makedirs(os.path.dirname(OUT_PNG), exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(res, f, indent=1)

    fig, ax = plt.subplots(1, 2, figsize=(13, 5.4))
    labels = {"separate_0p3m_typ": "today, grounds on 2 points, 0.3 m wires",
              "separate_1m_typ": "today, grounds on 2 points, 1 m wires",
              "separate_3m_typ": "today, grounds on 2 points, 3 m wires",
              "separate_1m_max": "today, 2 points, 1 m, contacts at 100 mOhm",
              "single_entry": "single entry (as built): KV260 fed from J1004, 3.19 A"}
    colors = {"separate_0p3m_typ": "#b2182b", "separate_1m_typ": "#d6604d", "separate_3m_typ": "#f4a582",
              "separate_1m_max": "#92c5de", "single_entry": "#2166ac"}
    for k in labels:
        ax[0].plot(dv, np.array(cases[k]) * 1000, color=colors[k], lw=2, label=labels[k])
    ax[0].axhline(BM20_RATED * 1000, color="k", ls="--", lw=1)
    ax[0].text(-1.95, BM20_RATED * 1000 + 15, "BM20 rating, 0.3 A a contact", fontsize=8)
    ax[0].axvspan(-1, 1, color="#eeeeee", zorder=0)
    ax[0].text(0, 30, "ISO 16750-2 4.8: +-1 V", ha="center", fontsize=8)
    ax[0].set_xlabel("Voltage between the two ground points (V)")
    ax[0].set_ylabel("Current in each BM20 ground contact (mA)")
    ax[0].set_title("Car: ground offset, adapter 1.12 A + KV260 3 A (3.19 A single entry)")
    ax[0].set_ylim(0, 1200)
    ax[0].grid(alpha=0.3)
    ax[0].legend(fontsize=7.5, loc="upper center")

    se = res["single_entry"]
    names = ["same point\n1 m / 1 m", "KV260 wire\nlost", "adapter wire\nlost", "home, 2 supplies\n1 V",
             "single entry", "single, one\ncontact at half", "single, jumper\nGND open", "single + earthed\nmonitor, 1 V"]
    vals = [same["1.0m/1.0m"]["per_contact_A"], loss["KV260 wire lost"]["per_contact_A"],
            loss["adapter wire lost"]["per_contact_A"], home["1.0 V"]["per_contact_A"],
            se["per_contact_A"], se["uneven"]["limit_one_at_half"], se["jumper_ground_open"]["per_contact_A"],
            home1["1.0 V"]["per_contact_A"]]
    bars = ax[1].bar(names, np.array(vals) * 1000,
                     color=["#999999", "#d6604d", "#d6604d", "#d6604d", "#2166ac", "#2166ac", "#2166ac", "#2166ac"])
    for b_, v in zip(bars, vals):
        ax[1].text(b_.get_x() + b_.get_width() / 2, v * 1000 + 8, f"{v*1000:.0f}", ha="center", fontsize=8)
    ax[1].axhline(BM20_RATED * 1000, color="k", ls="--", lw=1)
    ax[1].set_ylabel("Current in each BM20 ground contact (mA)")
    ax[1].set_title("Other cases (worst currents; red: today, blue: single entry)")
    ax[1].tick_params(axis="x", labelsize=7.5)
    plt.setp(ax[1].get_xticklabels(), rotation=35, ha="right", rotation_mode="anchor")
    ax[1].grid(alpha=0.3, axis="y")
    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=150)

    print(f"link: {r_link_typ*1000:.2f} mOhm typical ({share_typ*100:.0f} % in the BM20s), {r_link_max*1000:.2f} mOhm with contacts at max")
    print("per BM20 contact at a 1 V offset:")
    for k, v in res["per_contact_at_1V"].items():
        print(f"  {k:22s} {v*1000:7.0f} mA")
    print("offset at which a contact reaches 0.3 A:", {k: (None if v is None else round(v, 2)) for k, v in lim.items()})
    print("same point:", {k: round(v['per_contact_A'] * 1000) for k, v in same.items()}, "mA a contact")
    print("ground loss:", {k: (round(v['per_contact_A'] * 1000), round(v['surviving_jack_A'], 2)) for k, v in loss.items()}, "(mA a contact, A in the other jack)")
    print(f"single entry: {se['per_contact_A']*1000:.0f} mA a contact at any offset, input {se['input_A']:.2f} A; "
          f"contacts at max {se['contacts_at_max']['per_contact_A']*1000:.0f} mA; jumper ground open "
          f"{se['jumper_ground_open']['per_contact_A']*1000:.0f} mA "
          f"({se['jumper_ground_open_contacts_at_max']['per_contact_A']*1000:.0f} mA at max); typical load "
          f"{se['typical_load']['per_contact_A']*1000:.0f} mA")
    print("single entry, uneven contacts (mA in the low one):", {k: round(v * 1000) for k, v in se["uneven"].items()})
    print("home single entry 50 Hz:", {k: (round(v['loop_A'], 2), round(v['per_contact_A'] * 1000), round(v['adapter_ground_drop_uV']))
                                       for k, v in home1.items()}, "(A loop, mA a contact, uV)")
    print("home 50 Hz:", {k: (round(v['loop_A'], 2), round(v['per_contact_A'] * 1000), round(v['adapter_ground_drop_uV'])) for k, v in home.items()}, "(A loop, mA a contact, uV)")
    print("wrote", OUT_PNG)


if __name__ == "__main__":
    main()
