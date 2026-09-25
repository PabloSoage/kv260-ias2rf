"""
Drawing helpers shared by the sheet generators from ADC_SDR onwards.

The same building blocks recur: a power row (source -> ferrite -> local rail
with its decoupling), an AD8352 stage with its RG/RN/RD/CD columns, and the
AC-coupled network between a driver and an ADC. They are drawn here once, so
two sheets that use them look alike and are drawn by the same code.

(ADC_RADAR and CLOCK keep their own copies: they were drawn and reviewed
before this module existed, and are left as they are.)
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import schgen                                         # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
ROOT_UUID = "56c49378-41a8-4cbc-b1f4-3d0ea65d2366"
PROJECT = "CSI2-KRIA-KV260_Rev01"

R0402, C0402 = "Resistor_SMD:R_0402_1005Metric", "Capacitor_SMD:C_0402_1005Metric"
C0805, L0603 = "Capacitor_SMD:C_0805_2012Metric", "Inductor_SMD:L_0603_1608Metric"


def R(value, why, fp=R0402):
    return ("Device:R", value, fp, why)


def C(value, why, fp=C0402):
    return ("Device:C", value, fp, why)


def FB(value, why):
    return ("Device:FerriteBead", value, L0603, why)


def sheet_uuids(name):
    """(file uuid, block uuid) of a sheet made by rev03_build_hierarchy.py."""
    sys.path.insert(0, os.path.dirname(HERE))
    import re
    import rev03_build_hierarchy as H
    path = os.path.join(ROOT, H.SHEETS[name]["file"])
    text = open(path, encoding="utf-8").read()
    file_uuid = re.search(r'\(uuid "([^"]+)"\)', text).group(1)
    return file_uuid, H.uid("sheet", name), path


class Kit:
    def __init__(self, name, title, parts, ref_base, generator, paper="A3"):
        file_uuid, block, path = sheet_uuids(name)
        self.path = path
        self.s = schgen.Sheet(path, file_uuid, title, PROJECT, f"/{ROOT_UUID}/{block}",
                              paper=paper, generator=generator, ref_base=ref_base)
        self.s.lib("kv260-ias2rf", os.path.join(ROOT, "symbols", "kv260-ias2rf.kicad_sym"))
        self.P = parts

    # ---- placing
    def part(self, ref, at, rot=0, text_at=None, mirror=False, unit=1):
        lib_id, value, fp, _ = self.P[ref]
        return self.s.place(lib_id, ref, value, at, rot, footprint=fp, text_at=text_at,
                            mirror=mirror, unit=unit)

    def gnd(self, at):
        self.s.power("power:GND", "GND", at)

    def rail(self, name, at):
        lib = ("power:+5V" if name.startswith("+5") else
               "power:+1V8" if name.startswith("+1V8") else
               "power:+3V3" if name.startswith("+3V3") else
               "power:-3V3" if name.startswith("-3V3") else
               "power:+12V" if name.startswith("+12") else
               "power:+1V0" if name.startswith("+1V0") else
               "power:+1V2" if name.startswith("+1V2") else
               "power:+2V5" if name.startswith("+2V5") else "power:VCC")
        self.s.power(lib, name, at)

    def hpart(self, ref, x, y):
        """Horizontal two-pin part centred at (x, y): pin 1 left, pin 2 right."""
        return self.part(ref, (x, y), rot=90)

    def vpart(self, ref, x, top):
        """Vertical two-pin part, pin 1 at (x, top), pin 2 7.62 mm below."""
        return self.part(ref, (x, top + 3.81))

    def gnd_lead(self, pin, dx=5.08):
        """Ground a horizontal part's end through a short lead, so the GND
        symbol's name clears the part's value text."""
        s = self.s
        end = (pin[0] + dx, pin[1])
        s.wire(pin, end)
        self.gnd(end)

    # ---- blocks
    def power_row(self, src, fb, local, caps, x0, y):
        s = self.s
        self.rail(src, (x0, y))
        f = self.part(fb, (x0 + 7.62, y), rot=90)
        s.wire((x0, y), f.pin(1))
        s.power("power:PWR_FLAG", "PWR_FLAG", (x0 + 15.24, y))
        self.rail(local, (x0 + 19.05, y))
        x = x0 + 25.4
        for ref in caps:
            c = self.vpart(ref, x, y)
            self.gnd(c.pin(2))
            x += 10.16
        s.wire(f.pin(2), (x - 10.16, y))
        return x - 10.16

    def ad8352(self, ref, cx, cy, rg, rd, cd, vcm, rail, rn=None):
        """One AD8352 with RG, RN, RD, CD in columns 10.16 mm apart, VCM
        decoupled, ENB and VCC on one bus (ENB tied high, AD8352 eval board)."""
        s = self.s
        U = self.part(ref, (cx, cy), text_at=(cx + 13.97, cy + 17.78))
        vip, rgn, rgp, rdp, rdn = (U.pin(n) for n in (16, 3, 2, 1, 4))
        xp = vip[0]
        cols = iter(xp - 7.62 - 10.16 * k for k in range(4))
        r_g = self.vpart(rg, next(cols), rgn[1])
        s.wire(rgp, r_g.pin(2))
        if rn:
            r_n = self.vpart(rn, next(cols), vip[1])
            s.wire(rgn, r_n.pin(2))
        else:
            s.wire(rgn, r_g.pin(1))
        r_d = self.vpart(rd, next(cols), rdp[1])
        c_d = self.vpart(cd, next(cols), rdp[1])
        s.wire(rdp, c_d.pin(1))
        s.wire(r_d.pin(2), (r_d.pin(2)[0], rdn[1]))
        s.wire(c_d.pin(2), (c_d.pin(2)[0], rdn[1]))
        s.wire(rdn, (c_d.pin(2)[0], rdn[1]))
        vc = U.pin(14)
        s.wire(vc, (xp - 5.08, vc[1]))
        c = self.vpart(vcm, xp - 5.08, vc[1])
        self.gnd(c.pin(2))
        top = U.pin(8)[1] - 5.08
        for n in (8, 13, 15):
            s.wire(U.pin(n), (U.pin(n)[0], top))
        s.wire((U.pin(8)[0], top), (U.pin(15)[0], top))
        self.rail(rail, (U.pin(13)[0], top))
        bot = U.pin(6)[1] + 5.08
        for n in (6, 7, 9, 12, 17):
            s.wire(U.pin(n), (U.pin(n)[0], bot))
        s.wire((U.pin(6)[0], bot), (U.pin(17)[0], bot))
        self.gnd((cx, bot))
        return U

    def se_input(self, U, label, r_term, c_in, c_vin, r_vin, shape="input"):
        """AD8352 Figure 26: 65 ohm termination, AC coupling into VIP, VIN
        through a capacitor to 25 ohm. RN is placed by ad8352()."""
        s = self.s
        vip, vin = U.pin(16), U.pin(5)
        xp = vip[0]
        c1 = self.hpart(c_in, xp - 25.4, vip[1])
        s.wire(vip, c1.pin(2))
        r1 = self.vpart(r_term, xp - 35.56, vip[1])
        self.gnd(r1.pin(2))
        s.wire(c1.pin(1), (xp - 43.18, vip[1]))
        s.hlabel(label, shape, (xp - 43.18, vip[1]), side="left")
        c2 = self.hpart(c_vin, xp - 25.4, vin[1])
        s.wire(vin, c2.pin(2))
        r2 = self.vpart(r_vin, xp - 35.56, vin[1])
        self.gnd(r2.pin(2))
        s.wire(c2.pin(1), r2.pin(1))

    def adc_input(self, U, vinp, vinn, xa, refs, cm_label, straight="N"):
        """Driver U (AD8352) -> ADC VIN+/VIN- (pin positions vinp, vinn).

        refs: dict with keys cp, cn (coupling), rp, rn (200 ohm load legs),
        ccm (centre-tap capacitor), rcm (200 ohm to the ADC's VCM, or None),
        sp, sn (series resistors), csh (shunt across the inputs).
        The leg named by `straight` runs straight into its pin; the other
        jogs at xa - 2.54 (xa = the ADC's left pin ends)."""
        s = self.s
        vop, von = U.pin(11), U.pin(10)
        xo = vop[0]
        cp = self.hpart(refs["cp"], xo + 6.35, vop[1])
        cn = self.hpart(refs["cn"], xo + 6.35, von[1])
        s.wire(vop, cp.pin(1))
        s.wire(von, cn.pin(1))
        xch = xo + 20.32
        rp = self.vpart(refs["rp"], xch, vop[1])
        rn = self.vpart(refs["rn"], xch, von[1] - 7.62)
        s.wire(rp.pin(2), rn.pin(1))
        ym = (vop[1] + von[1]) / 2
        ym = schgen.snap(ym)
        ccm = self.hpart(refs["ccm"], xch - 3.81, ym)
        s.wire(ccm.pin(1), (ccm.pin(1)[0] - 5.08, ym))
        self.gnd((ccm.pin(1)[0] - 5.08, ym))
        if refs.get("rcm"):
            rcm = self.hpart(refs["rcm"], xch + 3.81, ym)
            s.label(cm_label, rcm.pin(2))
        else:
            s.wire((xch, ym), (xch + 2.54, ym))
            s.label(cm_label, (xch + 2.54, ym))
        sp = self.hpart(refs["sp"], xch + 12.7, vop[1])
        sn = self.hpart(refs["sn"], xch + 12.7, von[1])
        s.wire(cp.pin(2), sp.pin(1))
        s.wire(cn.pin(2), sn.pin(1))
        csh = self.vpart(refs["csh"], xch + 21.59, vop[1])
        s.wire(csh.pin(2), (csh.pin(2)[0], von[1]))
        assert xa - 2.54 > csh.pin(1)[0] + 7.62, "jog would run into the shunt's text"
        if straight == "N":
            assert vinn[1] == von[1], (vinn, von)
            s.wire(sp.pin(2), (xa - 2.54, vop[1]), (xa - 2.54, vinp[1]), vinp)
            s.wire(sn.pin(2), vinn)
        else:
            assert vinp[1] == vop[1], (vinp, vop)
            s.wire(sp.pin(2), vinp)
            s.wire(sn.pin(2), (xa - 2.54, von[1]), (xa - 2.54, vinn[1]), vinn)

    def notes(self, lines, at):
        for i, t in enumerate(lines):
            self.s.text(t, (at[0], at[1] + 3.81 * i), size=1.524 if i == 0 else 1.27)

    def write(self):
        n, w, j = self.s.write()
        print(f"wrote {os.path.relpath(self.path, ROOT)}: {n} symbols, {w} wire segments, "
              f"{j} junctions")


def dac_output(k, P, N, r, label):
    """DAC current outputs P, N (pin positions, 15.24 mm apart) -> 49.9 ohm
    loads -> AERIS-10's 5-pole differential LC filter -> 2:1 balun -> label.
    The same network as DAC_RADAR (drawn there by its own code). r: dict of
    refs rp, rn (loads), cp, cn (22 p shunts), c1, c3, c5 (across), l1p, l1n,
    l2p, l2n (series), t (balun)."""
    s = k.s
    xo = P[0]
    for ref, dx, leg in ((r["rp"], 5.08, P), (r["rn"], 5.08, N),
                         (r["cp"], 15.24, P), (r["cn"], 15.24, N)):
        c = k.vpart(ref, xo + dx, leg[1])
        k.gnd(c.pin(2))

    def across(ref, x):
        c = k.vpart(ref, x, P[1])
        s.wire(c.pin(2), (x, N[1]))

    across(r["c1"], xo + 25.4)
    l1p, l1n = k.hpart(r["l1p"], xo + 38.1, P[1]), k.hpart(r["l1n"], xo + 38.1, N[1])
    across(r["c3"], xo + 50.8)
    l2p, l2n = k.hpart(r["l2p"], xo + 63.5, P[1]), k.hpart(r["l2n"], xo + 63.5, N[1])
    across(r["c5"], xo + 76.2)
    s.wire(P, l1p.pin(1))
    s.wire(N, l1n.pin(1))
    s.wire(l1p.pin(2), l2p.pin(1))
    s.wire(l1n.pin(2), l2n.pin(1))
    T = k.part(r["t"], (xo + 99.06, P[1] + 5.08))
    aa, ab, sa, sb = T.pin(1), T.pin(2), T.pin(3), T.pin(4)
    assert aa[1] == P[1]
    s.wire(l2p.pin(2), aa)
    s.wire(l2n.pin(2), (aa[0] - 2.54, N[1]), (aa[0] - 2.54, ab[1]), ab)
    s.wire(sb, (sb[0] + 5.08, sb[1]))
    s.hlabel(label, "output", (sb[0] + 5.08, sb[1]))
    k.gnd(sa)
