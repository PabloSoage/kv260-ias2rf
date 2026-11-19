#!/usr/bin/env python3
"""
Keep the site's deep links into the documentation book in step with the book: reads the book's table of contents
(docs/KV260-IAS2RF_Documentation.pdf, built by export_documentation.py), rewrites DOC_PDF_PAGE_MAP in site/app.js
and every "#page=N" / "(p.N)" in site/index.html and site/sim_mode.js that pointed at the old start of a document,
and the book's page count in site/index.html. Run it after every rebuild of the book.

Usage:  py _work/site_pdf_pages.py
"""
import os
import re
import sys

import fitz

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import export_documentation as E                                     # noqa: E402

BOOK = os.path.join(ROOT, "docs", "KV260-IAS2RF_Documentation.pdf")
APP = os.path.join(ROOT, "site", "app.js")
PAGES = [os.path.join(ROOT, "site", "index.html"), os.path.join(ROOT, "site", "sim_mode.js"),
         os.path.join(ROOT, "site", "psu.html")]
ALIASES = {"docs/SYSTEM_SIM.md": "fpga/SYSTEM_SIM.md", "docs/LINK_PROTOCOL.md": "fpga/link/LINK_PROTOCOL.md",
           "docs/PINMAP.md": "fpga/link/PINMAP.md", "docs/POWER_AND_STACKUP.md": "docs/POWER_SPEC.md"}


def main():
    doc = fitz.open(BOOK)
    toc = doc.get_toc()
    total = len(doc)
    title_to_md = {t: md for _, docs in E.PARTS for t, md in docs}
    new = {}
    for lvl, title, page in toc:
        if lvl == 2 and title in title_to_md:
            new[title_to_md[title]] = page
    app = open(APP, encoding="utf-8").read()
    m = re.search(r"const DOC_PDF_PAGE_MAP = \{(.*?)\};", app, re.S)
    old = {k: int(v) for k, v in re.findall(r'"([^"]+)":\s*(\d+)', m.group(1))}
    remap = {}
    for k, v in old.items():
        md = ALIASES.get(k, k)
        if md in new:
            remap[v] = new[md]
    keys = list(old) + [md for md in new if md not in old and md not in ALIASES.values()]
    body = "\n".join(f'  "{k}": {new[ALIASES.get(k, k)]},' for k in keys if ALIASES.get(k, k) in new)
    app = app[:m.start(1)] + "\n" + body + "\n" + app[m.end(1):]
    open(APP, "w", encoding="utf-8", newline="\n").write(app)
    for p in PAGES:
        t = open(p, encoding="utf-8").read()
        t = re.sub(r"(#page=)(\d+)", lambda x: x.group(1) + str(remap.get(int(x.group(2)), int(x.group(2)))), t)
        t = re.sub(r"(\(p\.)(\d+)(\))", lambda x: x.group(1) + str(remap.get(int(x.group(2)), int(x.group(2))))
                   + x.group(3), t)
        t = t.replace("PSUPAGE", str(new["docs/PSU_SPEC.md"]))
        t = re.sub(r"\b\d{3}-page compiled reference", f"{total}-page compiled reference", t)
        open(p, "w", encoding="utf-8", newline="\n").write(t)
    print(f"book {total} pages; {len(new)} documents; moved: "
          + ", ".join(f"{a}->{b}" for a, b in sorted(remap.items()) if a != b))
    print("PSU_SPEC at page", new.get("docs/PSU_SPEC.md"))


if __name__ == "__main__":
    main()
