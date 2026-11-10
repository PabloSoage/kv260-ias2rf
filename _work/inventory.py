#!/usr/bin/env python3
"""Inventory of CSI2-KRIA-KV260_Rev01-2.kicad_sch (multi-channel IAS0/IAS1).

Approach: a MINIMAL, tolerant S-expression parser. All it has to do is find
the instantiated top-level `(symbol ...)` blocks (NOT those of the
`(lib_symbols ...)` block, which are the definitions) and extract their properties.

Output: _work/inventory.txt, in numbered sections.
"""
from __future__ import annotations
import re, sys, json, collections, pathlib, uuid

ROOT = pathlib.Path(r"E:\PCB\adapter_AMD_Xilinx_KRIA-KV260")
SCH  = ROOT / "CSI2-KRIA-KV260_Rev01-2.kicad_sch"
OUT  = ROOT / "_work" / "inventory.txt"

text = SCH.read_text(encoding="utf-8")
lines = text.splitlines()

# ---------------------------------------------------------------
# 1) Find the range of the `(lib_symbols ...)` block, to exclude it
# ---------------------------------------------------------------
def find_block(start_keyword: str) -> tuple[int,int] | None:
    """Find a top-level parenthesis opened with keyword=start_keyword.
    Return (line_open_idx_0based, line_close_idx_0based)."""
    pat = re.compile(r"^\s*\(" + re.escape(start_keyword) + r"\b")
    for i, ln in enumerate(lines):
        if pat.match(ln):
            depth = 0
            for j in range(i, len(lines)):
                # count the non-string parentheses, roughly
                # (enough for KiCad, which has no '(' inside strings bar rare cases)
                s = lines[j]
                # drop strings so as not to count parentheses inside "..."
                cleaned = re.sub(r'"[^"]*"', '""', s)
                depth += cleaned.count("(") - cleaned.count(")")
                if depth == 0 and j > i:
                    return (i, j)
    return None

libsyms = find_block("lib_symbols")
print(f"[i] (lib_symbols ...) 1-based line range: "
      f"{libsyms[0]+1 if libsyms else '-'}..{libsyms[1]+1 if libsyms else '-'}")

# ---------------------------------------------------------------
# 2) Find every top-level `(symbol` block  (instances, not definitions)
#    A top-level `(symbol` has its lib_id right on the next line.
# ---------------------------------------------------------------
def find_top_level_blocks(keyword: str) -> list[tuple[int,int]]:
    """Return a list of 0-based (start_idx,end_idx) of top-level blocks
    whose first line is ` (keyword ...`. Uses the parentheses balance and
    dropping those nested in (lib_symbols ...)."""
    pat = re.compile(r"^\s*\(" + re.escape(keyword) + r"\b")
    res = []
    for i, ln in enumerate(lines):
        if not pat.match(ln):
            continue
        # drop it if it falls inside (lib_symbols ...)
        if libsyms and libsyms[0] <= i <= libsyms[1]:
            continue
        depth = 0
        for j in range(i, len(lines)):
            s = lines[j]
            cleaned = re.sub(r'"[^"]*"', '""', s)
            depth += cleaned.count("(") - cleaned.count(")")
            if depth == 0:
                res.append((i, j))
                break
    return res

sym_blocks = find_top_level_blocks("symbol")
print(f"[i] {len(sym_blocks)} top-level (symbol ...) blocks found")

# ---------------------------------------------------------------
# 3) Extract the properties of each symbol block
# ---------------------------------------------------------------
def get_line_text(idx: int) -> str:
    return lines[idx].strip()

def extract_props(start: int, end: int) -> dict:
    block = "\n".join(lines[start:end+1])
    props = {}
    # (lib_id "X")  -> always on the block's first line or shortly after
    m = re.search(r"\(lib_id\s+"+'"([^"]+)"', block)
    props["lib_id"] = m.group(1) if m else ""
    # (at X Y [rot])
    m = re.search(r"\(at\s+([-0-9.]+)\s+([-0-9.]+)(?:\s+([-0-9.]+))?", block)
    props["at"] = f"{m.group(1)},{m.group(2)}" + (f",{m.group(3)}" if m and m.group(3) else "") if m else ""
    # (uuid "...")
    m = re.search(r'\(uuid\s+"([^"]+)"', block)
    props["uuid"] = m.group(1) if m else ""
    # properties: Reference, Value, Footprint, Datasheet, Description, MANUFACTURER PART NUMBER...
    for field in ("Reference","Value","Footprint","Datasheet","Description",
                  "MANUFACTURER PART NUMBER","KHK PART NUMBER","MANUFACTURER"):
        m = re.search(r'\(property\s+"' + re.escape(field) + r'"\s+"((?:[^"\\]|\\.)*)"', block)
        if m:
            props[field] = m.group(1)
    return props

components = []
for (s,e) in sym_blocks:
    p = extract_props(s,e)
    p["line_start"] = s+1
    p["line_end"]   = e+1
    p["line_count"] = e-s+1
    components.append(p)

# ---------------------------------------------------------------
# 4) Clasificar por lib_id
# ---------------------------------------------------------------
def lib_bucket(lib_id: str) -> str:
    L = lib_id.lower()
    if "bm20b" in L or "df40" in L or "hirose" in L:
        return "HIROSE_IAS"
    if "ffc" in L or "fh55" in L or "fh12" in L or "fpc" in L:
        return "FFC_FPC_CAMERA"
    if "tps25200" in L or "ina260" in L or "tps" in L or "adp" in L or "ltc" in L or "tlv" in L:
        return "POWER"
    if "ntb0104" in L or "txs" in L or "pca" in L or "fxma" in L or "level" in L:
        return "LEVEL_SHIFTER"
    if "con 1x" in L:
        return "PIN_HEADER"
    if "pcb hole" in L or "hole" in L:
        return "MOUNT_HOLE"
    if "tp_16" in L or "_tp" in L:
        return "TESTPOINT"
    if "led" in L:
        return "LED"
    if "r x" in L or re.search(r"r \d", L) or "r 0r0" in L or "r 2k0" in L or "r 3k3" in L or "r 51k" in L or "r 270k" in L:
        return "RESISTOR"
    if " c " in L or "c " in L and ("u" in L or "n " in L):
        return "CAPACITOR"
    if "gnd_bar" in L or "_circle" in L or "c-gnd" in L or "power_ground" in L:
        return "POWER_SYMBOL"
    if "pcb text" in L or "pcb label" in L or "pcb marker" in L or "pcb$" in L:
        return "PCB_REMARK"
    return "OTHER"

for c in components:
    c["bucket"] = lib_bucket(c["lib_id"])

# ---------------------------------------------------------------
# 5) Etiquetas globales/jerarquicas/locales
# ---------------------------------------------------------------
glabels = []
hlabels = []
labels  = []
for i, ln in enumerate(lines):
    if libsyms and libsyms[0] <= i <= libsyms[1]:
        continue
    m = re.match(r"\s*\(global_label\s+\"([^\"]+)\"", ln)
    if m: glabels.append((i+1, m.group(1)))
    m = re.match(r"\s*\(hierarchical_label\s+\"([^\"]+)\"", ln)
    if m: hlabels.append((i+1, m.group(1)))
    m = re.match(r"\s*\(label\s+\"([^\"]+)\"", ln)
    if m: labels.append((i+1, m.group(1)))

# ---------------------------------------------------------------
# 6) Libraries used in (lib_symbols ...): list of the symbols defined
# ---------------------------------------------------------------
lib_defs = []
if libsyms:
    inner = "\n".join(lines[libsyms[0]+1:libsyms[1]])
    # each definition starts with (symbol "LIB:NAME" ... but note: there are
    # sub-symbols (symbol "NAME_1_0" ...) nested inside. Only those
    # holding ':' are taken (they include the library).
    for m in re.finditer(r'\(symbol\s+"([^"]*:?[^"]+)"', inner):
        name = m.group(1)
        if ":" in name and name not in [d for _,d in lib_defs]:
            lib_defs.append((0,name))
    # also those WITHOUT ':' that are roots (rare)
    for m in re.finditer(r'\(symbol\s+"([^"]+)"', inner):
        name = m.group(1)
        if ":" not in name and not re.match(r"^.+(_\d+_\d+|_1_0|_0_0)$", name):
            if name not in [d for _,d in lib_defs]:
                lib_defs.append((0,name))

# ---------------------------------------------------------------
# 7) Symbols of the lib_symbols block: look for our ICs
# ---------------------------------------------------------------
needed = ["AD9268","AD9779","ADAR1000","HMC547","ADL5801","8132H","ADCLK944"]
lib_block_text = "\n".join(lines[libsyms[0]:libsyms[1]+1]) if libsyms else ""
needed_present = {}
for n in needed:
    needed_present[n] = bool(re.search(r'\(symbol\s+"[^"]*' + n + r'[^"]*"', lib_block_text, re.I))

# ---------------------------------------------------------------
# 8) Pins of the Hirose BM20B(0.8)-34DP (definition in lib_symbols)
# ---------------------------------------------------------------
# Find the Hirose symbol inside lib_symbols and list its pins
hirose_pins = []
if libsyms:
    # the Hirose's definition block:
    m = re.search(r'\(symbol\s+"AVT_KHK_Lib:IAS1_0_CON BM20B\(0\.8\)-34DP[^"]*"\s*\n(.+?)(?=\n\t\t\(symbol\s+"AVT_KHK_Lib:|\n\t\(symbol\s+"|^\t\)$|$)',
                  lib_block_text, re.S)
    # if it does not fit, fall back
    if not m:
        m = re.search(r'\(symbol\s+"AVT_KHK_Lib:IAS1_0_CON BM20B\(0\.8\)-34DP[^"]*"[^)]*?(?=\n\t\t\(symbol\s+"|$)',
                      lib_block_text, re.S)
    hirose_block = m.group(0) if m else ""
    # extract (pin "name" ...) in the definition
    for pm in re.finditer(r'\(pin\s+"?([A-Za-z0-9_\-+()./]+)"?\s+(input|output|bidirectional|passive|power_in|power_out|unspecified)\s+\(at\s+[-0-9.]+\s+[-0-9.]+\)', hirose_block):
        hirose_pins.append(pm.group(1))

# ---------------------------------------------------------------
# 9) Escribir informe
# ---------------------------------------------------------------
def fmt_comp(c):
    ref = c.get("Reference","?")
    val = c.get("Value","")
    fp  = c.get("Footprint","")
    return (f"  L{c['line_start']:>6}-L{c['line_end']:<6} ({c['line_count']:>4} ln) | "
            f"{ref:<8} | {val:<32} | fp='{fp}' | lib={c['lib_id']}")

buckets = collections.defaultdict(list)
for c in components:
    buckets[c["bucket"]].append(c)

order = ["HIROSE_IAS","FFC_FPC_CAMERA","POWER","LEVEL_SHIFTER","PIN_HEADER",
         "MOUNT_HOLE","TESTPOINT","LED","RESISTOR","CAPACITOR","POWER_SYMBOL",
         "PCB_REMARK","OTHER"]

with OUT.open("w", encoding="utf-8") as f:
    f.write("===== INVENTORY OF CSI2-KRIA-KV260_Rev01-2.kicad_sch =====\n")
    f.write(f"File: {SCH}\n")
    f.write(f"Total lines: {len(lines)}\n")
    f.write(f"Rango (lib_symbols ...): "
            f"{libsyms[0]+1 if libsyms else '-'}..{libsyms[1]+1 if libsyms else '-'}\n")
    f.write(f"Top-level (symbol) instances: {len(sym_blocks)}\n\n")

    f.write("----- 1. PARTS BY BUCKET -----\n")
    for k in order:
        items = buckets.get(k, [])
        if not items: continue
        f.write(f"\n== {k}  (n={len(items)}) ==\n")
        for c in sorted(items, key=lambda x: x["line_start"]):
            f.write(fmt_comp(c) + "\n")

    f.write("\n\n----- 2. ETIQUETAS -----\n")
    f.write(f"\n[global_label] n={len(glabels)}\n")
    for ln,name in glabels: f.write(f"  L{ln}: {name}\n")
    f.write(f"\n[hierarchical_label] n={len(hlabels)}\n")
    for ln,name in hlabels: f.write(f"  L{ln}: {name}\n")
    f.write(f"\n[label locales] n={len(labels)}\n")
    for ln,name in labels[:300]: f.write(f"  L{ln}: {name}\n")
    if len(labels) > 300:
        f.write(f"  ... and {len(labels)-300} more (left out for brevity)\n")

    f.write("\n\n----- 3. LIBRARIES DEFINED IN (lib_symbols) -----\n")
    f.write(f"Symbols defined: {len(lib_defs)}\n")
    libs = collections.Counter()
    for _,name in lib_defs:
        lib = name.split(":")[0] if ":" in name else "(sin lib)"
        libs[lib] += 1
    for lib,n in libs.most_common():
        f.write(f"  {lib}: {n} symbols\n")

    f.write("\n\n----- 4. CHIPS NUEVOS: presentes en lib_symbols? -----\n")
    for n in needed:
        f.write(f"  {n}: {'YES' if needed_present[n] else 'NO (still to import)'}\n")

    f.write("\n\n----- 5. PINS OF THE HIROSE BM20B(0.8)-34DP -----\n")
    f.write(f"Pins found in the definition: {len(hirose_pins)}\n")
    for p in hirose_pins:
        f.write(f"  {p}\n")

    f.write("\n\n----- 6. OTROS DATOS UTILES -----\n")
    # Find lines with 'MIPI','CSI','Camera','Sensor','TCAM','Focus','Actuator','EEPROM'
    keywords = ["MIPI","CSI","MIPI","Camera","Sensor","TCAM","Focus","Actuator","EEPROM",
                "XCLK","FSIN","AUTOM","PWM","RESET","XSHUT","TRIGGER","SCL","SDA","I2C","SPI",
                "FPGA","LVDS","VCC1V8","VCC1V2","VCC3V3","VCC5V","VCC2V75","VCC5V-CAM","VCC-EXT"]
    f.write("Keyword mentions in the file (lib_symbols excluded):\n")
    for kw in keywords:
        cnt = 0
        for i,ln in enumerate(lines):
            if libsyms and libsyms[0] <= i <= libsyms[1]: continue
            if kw.lower() in ln.lower(): cnt += 1
        f.write(f"  {kw:<14} : {cnt}\n")

print(f"[i] Escrito: {OUT}")
print(f"[i] {len(components)} componentes inventariados")
print(f"[i] {len(glabels)} glabel, {len(hlabels)} hlabel, {len(labels)} label local, "
      f"{len(hirose_pins)} pins hirose, {len(lib_defs)} lib_defs")