#!/usr/bin/env python3
"""
Price the JLCPCB order: today's stock and price of every part in the BOM.

Reads _work/fab/lcsc_parts.csv (one LCSC code per BOM line, chosen by
lcsc_select.py), asks JLCPCB's parts search for each code, and writes
_work/fab/quote.csv: per code, the quantity per board, the quantity JLCPCB
would buy for N assembled boards (need + its attrition, at least its minimum),
the price tier that quantity falls in, the line cost, stock and links.

The board, stencil and assembly fees are not in the parts search: they are
entered by hand in docs/JLCPCB_QUOTE.md from jlcpcb.com's quote page.

Usage:  python _work/fab/quote.py [--boards 2,5]
"""

import argparse
import csv
import datetime
import json
import os
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PARTS = os.path.join(ROOT, "_work", "fab", "lcsc_parts.csv")
OUT = os.path.join(ROOT, "_work", "fab", "quote.csv")
DOC = os.path.join(ROOT, "docs", "JLCPCB_QUOTE.md")
API = ("https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/"
       "selectSmtComponentList")
FEEDER_FEE = 1.53       # USD per unique part, basic or extended: Standard PCBA loads every part
                        # (stack 2116A rules out Economic PCBA; JLCPCB price page, 22 Oct 2026)


def lookup(code):
    body = json.dumps({"keyword": code, "currentPage": 1, "pageSize": 10}).encode()
    req = urllib.request.Request(API, data=body, headers={
        "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
    for attempt in range(4):
        try:
            d = json.load(urllib.request.urlopen(req, timeout=60))
            break
        except Exception:                           # noqa: BLE001
            if attempt == 3:
                raise
            time.sleep(5 * (attempt + 1))
    for c in ((d.get("data") or {}).get("componentPageInfo") or {}).get("list") or []:
        if c.get("componentCode") == code:
            return c
    return None


def unit_price(c, qty):
    tiers = sorted(c.get("componentPrices") or [], key=lambda t: t["startNumber"])
    p = None
    for t in tiers:
        if qty >= t["startNumber"]:
            p = t["productPrice"]
    return p if p is not None else (tiers[0]["productPrice"] if tiers else None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--boards", default="2,5", help="assembled-board counts to price")
    a = ap.parse_args()
    ns = [int(x) for x in a.boards.split(",")]

    lines = {}
    for r in csv.DictReader(open(PARTS, encoding="utf-8")):
        code = r["LCSC"].strip()
        key = code or r["Comment"]
        e = lines.setdefault(key, dict(code=code, qty=0, mpn=r["MPN"], mfr=r["Manufacturer"],
                                       comment=[], footprint=r["Footprint"], note=r["Note"]))
        e["qty"] += int(r["Qty"])
        e["comment"].append(r["Comment"])

    rows = []
    for key, e in lines.items():
        row = dict(LCSC=e["code"], MPN=e["mpn"], Manufacturer=e["mfr"],
                   Value=" / ".join(dict.fromkeys(e["comment"])), Footprint=e["footprint"],
                   PerBoard=e["qty"], Note=e["note"])
        c = lookup(e["code"]) if e["code"] else None
        if c:
            lib = c.get("componentLibraryType")
            row.update(Library="basic" if lib == "base" else ("preferred" if c.get("preferredComponentFlag") else "extended"),
                       Stock=c.get("stockCount") or 0, Attrition=c.get("lossNumber") or 0,
                       MinQty=max(c.get("leastPatchNumber") or 1, c.get("minPurchaseNum") or 1),
                       JLCPCB=f"https://jlcpcb.com/partdetail/{c.get('urlSuffix')}" if c.get("urlSuffix") else "",
                       LCSCurl=c.get("lcscGoodsUrl") or "",
                       Tiers=" ".join(f"{t['startNumber']}+:{t['productPrice']}" for t in
                                      sorted(c.get("componentPrices") or [], key=lambda t: t["startNumber"])))
            for n in ns:
                buy = max(e["qty"] * n + row["Attrition"], row["MinQty"])
                p = unit_price(c, buy)
                row[f"Buy{n}"] = buy
                row[f"Unit{n}"] = p
                row[f"Cost{n}"] = round(buy * p, 2) if p is not None else ""
        else:
            row.update(Library="", Stock="", Attrition="", MinQty="", JLCPCB="", LCSCurl="", Tiers="")
            for n in ns:
                row[f"Buy{n}"] = e["qty"] * n
                row[f"Unit{n}"] = row[f"Cost{n}"] = ""
        rows.append(row)
        time.sleep(0.3)

    cols = (["LCSC", "MPN", "Manufacturer", "Value", "Footprint", "Library", "PerBoard", "Stock",
             "Attrition", "MinQty"] + [f"{k}{n}" for n in ns for k in ("Buy", "Unit", "Cost")]
            + ["Tiers", "JLCPCB", "LCSCurl", "Note"])
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, cols)
        w.writeheader()
        w.writerows(rows)

    today = datetime.date.today().isoformat()
    print(f"{len(rows)} codes, searched {today} -> {os.path.relpath(OUT, ROOT)}")
    uniq = sum(1 for r in rows if r["LCSC"])
    for n in ns:
        tot = sum(r[f"Cost{n}"] for r in rows if r[f"Cost{n}"] != "")
        print(f"{n} boards: parts ${tot:.2f}; feeder loading {uniq} x ${FEEDER_FEE} = ${uniq * FEEDER_FEE:.2f}")
    write_doc(rows, ns, today)
    short = [r for r in rows if r["Stock"] != "" and r["Stock"] < r[f"Buy{ns[0]}"]]
    print("short of stock:", ", ".join(f"{r['MPN']} ({r['Stock']})" for r in short) or "none")


def write_doc(rows, ns, today):
    """Replace the parts table between the markers in docs/JLCPCB_QUOTE.md."""
    if not os.path.exists(DOC):
        return
    b, e = "<!-- parts:begin -->", "<!-- parts:end -->"
    d = open(DOC, encoding="utf-8").read()
    if b not in d or e not in d:
        return
    rs = sorted(rows, key=lambda r: -(r[f"Cost{ns[0]}"] or 0))
    head = ("| LCSC | Part | Maker | Value | Lib | Per board | Stock | "
            + " | ".join(f"Buy {n} / unit / cost" for n in ns) + " |")
    out = [f"*Searched {today} by `_work/fab/quote.py`; prices in USD, JLCPCB's tier for the quantity bought.*",
           "", head, "|" + "---|" * (7 + len(ns))]
    for r in rs:
        code = f"[{r['LCSC']}]({r['JLCPCB']})" if r["JLCPCB"] else (r["LCSC"] or "none")
        mpn = f"[{r['MPN']}]({r['LCSCurl']})" if r["LCSCurl"] else r["MPN"]
        stock = r["Stock"]
        if stock != "" and stock < r[f"Buy{ns[0]}"]:
            stock = f"**{stock}**"
        cells = []
        for n in ns:
            if r[f"Cost{n}"] == "":
                cells.append(f"{r[f'Buy{n}']} / — / —")
            else:
                cells.append(f"{r[f'Buy{n}']} / {r[f'Unit{n}']:.4g} / {r[f'Cost{n}']:.2f}")
        out.append(f"| {code} | {mpn} | {r['Manufacturer']} | {r['Value']} | {r['Library']} | "
                   f"{r['PerBoard']} | {stock} | " + " | ".join(cells) + " |")
    tot = [sum(r[f"Cost{n}"] for r in rows if r[f"Cost{n}"] != "") for n in ns]
    out.append("| | **Total** | | | | | | " + " | ".join(f"**{t:.2f}**" for t in tot) + " |")
    nl = chr(10)
    d = d[:d.index(b) + len(b)] + nl + nl.join(out) + nl + d[d.index(e):]
    open(DOC, "w", encoding="utf-8", newline=nl).write(d)


if __name__ == "__main__":
    main()
