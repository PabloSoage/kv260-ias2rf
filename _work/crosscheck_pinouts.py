#!/usr/bin/env python3
"""
Cross-check every datasheet-transcribed pin table against a second source.

A pin table typed by hand from a datasheet can be wrong in exactly the ways
that are invisible later: two pins swapped, a complement on the wrong side of
a pair, a supply pin read as a signal. The defence is a second, independent
source. Three exist:

  * the AERIS-10 Eagle libraries (fabricated, measured boards);
  * _work/pinouts.txt, pin names scraped from EasyEDA/LCSC symbols during
    the Rev01 work - names only, no types;
  * KiCad's own stock symbol libraries, where a pin-compatible part exists
    (the Si549 in pinout code C is a drop-in for the Si570, which KiCad
    ships).

None is authoritative - that is the datasheet - but an INDEPENDENT source
that agrees pin for pin is strong evidence the transcription is right, and
any disagreement is worth a second look at the datasheet page.

What is normalised away before comparing (all cosmetic):
  * case, en-dash vs hyphen, "(MSB)"/"(LSB)" annotations;
  * overbars: "~{CLK}" vs "CLK" - EasyEDA sometimes drops them. Reported
    separately, since a missing overbar is information lost, not a conflict;
  * Eagle's uniquifying suffixes: Eagle cannot have two pins with the same
    name, so repeated supplies become AVDD_1, AVDD@2 and so on;
  * the exposed pad: every source names it differently (EP, EPAD, AGND,
    GND_EP), and the datasheet calls it pin 0 where KiCad uses N+1.

Usage:  py _work/crosscheck_pinouts.py
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_symbols as ms          # noqa: E402

PINOUTS = os.path.join(HERE, "pinouts.txt")

# our symbol -> (source kind, name in that source)
SECOND_SOURCE = {
    "AD9484BCPZ-500": ("eagle",  "AD9484BCPZ-500"),
    "AD8352ACPZ":     ("eagle",  "AD8352ACPZ-R7"),
    "AD9523BCPZ":     ("eagle",  "AD9523BCPZ"),
    "M3SWA2-34DR":    ("eagle",  "M3SWA2-34DR+"),
    "LTC5552":        ("eagle",  "LTC5552IUDBTRMPBF"),
    "AD9253BCPZ-125": ("easyeda", "AD9253BCPZ-125"),
    "AD9767ASTZ":     ("easyeda", "AD9767ASTZ"),
    "ADCLK944BCPZ":   ("easyeda", "ADCLK944BCPZ-R2"),
    "Si549_PinoutC":  ("kicad",   "Oscillator:Si570"),
    "AD9708AR":       ("kicad",   "Video:AD9708AR"),
    # Power (25 Sep): pin-compatible family members in KiCad's own library
    "TPS562201":      ("kicad",   "Regulator_Switching:TPS562200"),
    "LMR33630ADDA":   ("kicad",   "Regulator_Switching:LMR33640ADDA"),
    # CONTROL (25 Sep): the 1.8 V member of the same family, W-PDFN package,
    # same eight-pin assignment
    "MT25QL128ABA1ESE": ("kicad", "Memory_Flash:MT25QUxxxxxx1xW7"),
}

# Datasheet symbols for which no independent source exists. Listed so the
# gap is visible in the output instead of silently skipped.
NO_SECOND_SOURCE = {
    "TPS7A8300RGR": "not in Eagle, EasyEDA or KiCad's libraries. Checked only against its "
                    "datasheet's pin drawing and Pin Functions table, which agree",
    "LM2663M": "KiCad has only the LM2665 (SOT-23-6), a different part. Checked only "
               "against the datasheet's pin drawing and Pin Functions table",
    "ADCLK948BCPZ": "not in Eagle, EasyEDA or KiCad's libraries. Checked only "
                    "against itself: Figure 2 and Table 7 of the datasheet agree",
}

KICAD_SYMBOLS = "E:/Program Files/KiCad/10.0/share/kicad/symbols"

EP_WORDS = re.compile(r"(?i)^(ep|epad|pad|exp|gnd_ep|agnd_ep|vee_ep|thermal.*|.*_ep)$")


def is_ep(name):
    return bool(EP_WORDS.match(name))


# U+FFFD is what the en-dash in "VIN–A" became when pinouts.txt was scraped:
# the character was lost, but it was a minus.
DASHES = ("–", "−", "�")


def norm(name):
    """Name with every cosmetic difference removed."""
    n = name.strip().upper()
    for d in DASHES:
        n = n.replace(d, "-")
    n = re.sub(r"\((MSB|LSB)\)", "", n)
    n = re.sub(r"~\{([^}]*)\}", r"\1", n)          # KiCad overbar ~{X}
    n = n.lstrip("~")                              # Eagle overbar ~X
    n = re.sub(r"(@\d+|_\d+)$", "", n)             # Eagle uniquifier AVDD_3
    # ...and the bare-digit form, but only on names that are never numbered
    # for real (OUT13 must stay OUT13).
    n = re.sub(r"^(GND|AGND|DGND|DRGND|NC|VCC|VDD)\d+$", r"\1", n)
    return n.strip()


def has_bar(name):
    return name.startswith("~")


# Disagreements that were looked up and settled against the datasheet. They
# stay visible in the output, marked as settled, so the reasoning is on record
# rather than silently normalised away. (symbol, pad) -> reason
ADJUDICATED = {
    ("AD9523BCPZ", "55"):
        "Eagle 'STATUS1/SPI' is a typo: SP1 is I2C address bit 1, beside "
        "STATUS0/SP0 on pad 56. Datasheet Table 19: STATUS1/SP1",
    ("AD9523BCPZ", "69"):
        "Eagle 'VDD1.8_PLL2' predates Rev. D, which calls pin 69 NC; its "
        "Note 1 says 'on existing PCB designs, it is acceptable to leave pin "
        "69 connected to 1.8 V'. Typed passive so either choice passes ERC",
    ("AD9523BCPZ", "72"):
        "Eagle '~PLL_OUT' is wrong twice over: the pin is PLL1_OUT, a "
        "single-ended CMOS output with no complement (Table 19, Figure 2)",
    ("LTC5552", "3"):
        "Eagle 'IF' lost the superscript minus: pin 3 is IF- (PIN "
        "CONFIGURATION). The datasheet's own GND list also names pin 3 - an "
        "erratum, see make_symbols.py",
    ("LTC5552", "EP"):
        "Eagle has no exposed pad; the datasheet does: 'EXPOSED PAD (PIN 13) "
        "IS GND, MUST BE SOLDERED TO PCB'",
    ("AD9253BCPZ-125", "37"): "EasyEDA typo 'VNI' for VIN (datasheet Table 8)",
    ("AD9253BCPZ-125", "38"): "EasyEDA typo 'VNI' for VIN (datasheet Table 8)",
    ("AD9253BCPZ-125", "47"): "EasyEDA typo 'VNI' for VIN (datasheet Table 8)",
    ("AD9253BCPZ-125", "48"): "EasyEDA typo 'VNI' for VIN (datasheet Table 8)",
    ("AD9253BCPZ-125", "40"): "EasyEDA typo 'RBAIS' for RBIAS (datasheet Table 8)",
    ("AD9708AR", "9"):
        "KiCad's Video:AD9708AR leaves out the NC pins; the datasheet lists "
        "9-14 and 25 as 'No Internal Connection'. Kept, typed no_connect",
    ("AD9708AR", "10"):
        "KiCad's Video:AD9708AR leaves out the NC pins; the datasheet lists "
        "9-14 and 25 as 'No Internal Connection'. Kept, typed no_connect",
    ("AD9708AR", "11"):
        "KiCad's Video:AD9708AR leaves out the NC pins; the datasheet lists "
        "9-14 and 25 as 'No Internal Connection'. Kept, typed no_connect",
    ("AD9708AR", "12"):
        "KiCad's Video:AD9708AR leaves out the NC pins; the datasheet lists "
        "9-14 and 25 as 'No Internal Connection'. Kept, typed no_connect",
    ("AD9708AR", "13"):
        "KiCad's Video:AD9708AR leaves out the NC pins; the datasheet lists "
        "9-14 and 25 as 'No Internal Connection'. Kept, typed no_connect",
    ("AD9708AR", "14"):
        "KiCad's Video:AD9708AR leaves out the NC pins; the datasheet lists "
        "9-14 and 25 as 'No Internal Connection'. Kept, typed no_connect",
    ("AD9708AR", "25"):
        "KiCad's Video:AD9708AR leaves out the NC pins; the datasheet lists "
        "9-14 and 25 as 'No Internal Connection'. Kept, typed no_connect",
    ("LMR33630ADDA", "1"):
        "Naming only: KiCad's LMR33640ADDA calls pad 1 'GND', the LMR33630 datasheet "
        "'PGND' (power ground). Same pad",
    ("LMR33630ADDA", "9"):
        "The thermal pad: the datasheet names it AGND, KiCad 'GND', so the script does "
        "not match it by name. Same pad 9 on both",
    ("LMR33630ADDA", "EP"):
        "See pad 9: one exposed pad on each side, named differently",
    ("MT25QL128ABA1ESE", "7"):
        "Pin 7 is DQ3/HOLD# or DQ3/RESET# by part number (datasheet Figure 6); KiCad's "
        "symbol is drawn for a RESET# variant. The HOLD# part is the one Figure 2-14 of "
        "UG470 draws. Same pad either way",
    ("MT25QL128ABA1ESE", "EP"):
        "KiCad's symbol is for the W-PDFN package, which has an exposed pad; the SO8W "
        "chosen here has none",
    ("Si549_PinoutC", "6"):
        "Naming only: KiCad's Si570 calls the supply 'Vcc', the Si549 "
        "datasheet 'VDD'. Same pin, same function",
}


def load_easyeda():
    """{part: {pad: name}} from _work/pinouts.txt."""
    parts, cur = {}, None
    for line in open(PINOUTS, encoding="utf-8"):
        m = re.match(r"^=== (.+?) ===", line)
        if m:
            cur = m.group(1).strip()
            parts[cur] = {}
            continue
        m = re.match(r"^\s+(\S+)\s+(\S+)\s+\?\s+\(", line)
        if cur and m and m.group(1) != "Pin":
            parts[cur][m.group(1)] = m.group(2)
    return parts


def load_kicad(ref):
    """{pad: name} of a stock KiCad symbol, 'Library:Symbol'."""
    lib, name = ref.split(":")
    text = open(os.path.join(KICAD_SYMBOLS, lib + ".kicad_sym"), encoding="utf-8").read()
    i = text.find(f'(symbol "{name}"')
    j = text.find('\n\t(symbol "', i + 10)
    body = text[i:j if j > 0 else len(text)]
    return {num: nm for nm, num in re.findall(
        r'\(pin \w+ \w+.*?\(name "([^"]*)".*?\(number "([^"]*)"', body, re.S)}


def load_eagle():
    out = {}
    for src in ms.EAGLE_SOURCES:
        if os.path.exists(src):
            for ds, pins in ms.load_libraries(src).items():
                out.setdefault(ds, {p: n for p, n, _ in pins})
    return out


def compare(ours, theirs):
    """Return (matched, conflicts, bar_only, only_ours, only_theirs)."""
    # The exposed pad is matched by role, not by number.
    ep_ours = {p for p, n in ours.items() if is_ep(n)}
    ep_theirs = {p for p, n in theirs.items() if is_ep(n) or p in ("0", "EP")}
    a = {p: n for p, n in ours.items() if p not in ep_ours}
    b = {p: n for p, n in theirs.items() if p not in ep_theirs}

    matched, conflicts, bar_only = 0, [], []
    for p in sorted(set(a) & set(b), key=ms.sort_key):
        if norm(a[p]) == norm(b[p]):
            matched += 1
            if has_bar(a[p]) != has_bar(b[p]):
                bar_only.append((p, a[p], b[p]))
        else:
            conflicts.append((p, a[p], b[p]))
    ep_ok = len(ep_ours) == len(ep_theirs)
    return (matched, conflicts, bar_only,
            sorted(set(a) - set(b), key=ms.sort_key),
            sorted(set(b) - set(a), key=ms.sort_key),
            ep_ok, len(ep_ours), len(ep_theirs))


def main():
    easy = load_easyeda()
    eagle = load_eagle()
    total_conf = 0
    print(f"{'symbol':16s} {'2nd source':9s} {'pins':>5s} {'agree':>6s}  result")
    print("-" * 64)
    for sym, (kind, key) in SECOND_SOURCE.items():
        ours = {p: n for p, n, _ in ms.DATASHEET_PINS[sym]}
        if kind == "kicad":
            src = load_kicad(key)
        else:
            src = (eagle if kind == "eagle" else easy).get(key)
        if src is None:
            print(f"{sym:16s} {kind:9s}  -- second source has no '{key}'")
            continue
        m, conf, bar, only_a, only_b, ep_ok, ne_a, ne_b = compare(ours, src)
        settled = [c for c in conf if (sym, c[0]) in ADJUDICATED]
        conf = [c for c in conf if (sym, c[0]) not in ADJUDICATED]
        # a pad only one side has can be adjudicated too (e.g. NC pins a
        # second source leaves out)
        settled += [(p, ours[p], None) for p in only_a if (sym, p) in ADJUDICATED]
        only_a = [p for p in only_a if (sym, p) not in ADJUDICATED]
        settled += [(p, None, src[p]) for p in only_b if (sym, p) in ADJUDICATED]
        only_b = [p for p in only_b if (sym, p) not in ADJUDICATED]
        ep_settled = not ep_ok and (sym, "EP") in ADJUDICATED
        open_ep = not ep_ok and not ep_settled
        if conf or only_a or only_b or open_ep:
            verdict = "CHECK"
        elif settled or ep_settled:
            verdict = f"AGREE, {len(settled) + ep_settled} settled"
        else:
            verdict = "AGREE"
        total_conf += len(conf) + len(only_a) + len(only_b) + open_ep
        print(f"{sym:16s} {kind:9s} {len(ours):5d} {m:6d}  {verdict}")
        for p, x, y in conf:
            print(f"      pad {p:>3s}: ours {x!r:22s} theirs {y!r}")
        for p, x, y in settled:
            print(f"      settled pad {p}: ours {x!r}, theirs {y!r}")
            print(f"          {ADJUDICATED[(sym, p)]}")
        if only_a:
            print(f"      pads only in ours:   {only_a}")
        if only_b:
            print(f"      pads only in theirs: {only_b}")
        if open_ep:
            print(f"      exposed pad: ours {ne_a}, theirs {ne_b}")
        if ep_settled:
            print(f"      settled exposed pad: ours {ne_a}, theirs {ne_b}")
            print(f"          {ADJUDICATED[(sym, 'EP')]}")
        if bar:
            print(f"      overbar present on one side only: {len(bar)} pins "
                  f"(e.g. pad {bar[0][0]}: {bar[0][1]!r} vs {bar[0][2]!r})")
    for sym, why in NO_SECOND_SOURCE.items():
        print(f"{sym:16s} {'-':9s} {len(ms.DATASHEET_PINS[sym]):5d} {'-':>6s}  NO SECOND SOURCE: {why}")
    print()
    print("No conflicts." if not total_conf else f"{total_conf} conflict(s) to resolve.")
    return 1 if total_conf else 0


if __name__ == "__main__":
    sys.exit(main())
