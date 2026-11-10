import pathlib, re
ROOT = pathlib.Path(r"E:\PCB\adapter_AMD_Xilinx_KRIA-KV260")
ERC = ROOT / "CSI2-KRIA-KV260_Rev01-erc.rpt"
SCH = ROOT / "CSI2-KRIA-KV260_Rev01-2.kicad_sch"
erctxt = ERC.read_text(encoding="utf-8")
els = erctxt.splitlines()
coord_set = []
headers = ("[unconnected_wire_endpoint]", "[wire_dangling]")
i = 0
while i < len(els):
    if any(h in els[i] for h in headers):
        j = i + 1
        while j < len(els) and (els[j].strip()=="" or els[j].strip().startswith(";")):
            j += 1
        while j < len(els) and not els[j].lstrip().startswith("["):
            m = re.match(r"\s*@\(([-0-9.]+)\s*mm,\s*([-0-9.]+)\s*mm\)", els[j])
            if m: coord_set.append((m.group(1), m.group(2)))
            j += 1
        i = j
    else:
        i += 1
print(f"orphan coords: {len(coord_set)}")
print("first 8:", coord_set[:8])
sch = SCH.read_text(encoding="utf-8")
for raw in coord_set[:8]:
    nn, mm = raw
    # match con 3 decimales
    pat = re.compile(r"\(xy\s+("+re.escape(nn)+r"|"+re.escape(nn)+r"\d+)\s+("+re.escape(mm)+r"|"+re.escape(mm)+r"\d+)\)")
    n = len(pat.findall(sch))
    print(f"  ({nn},{mm}) -> ocurrencias tolerantes (xy): {n}")
# now with float parsing
fset = {(round(float(a),3), round(float(b),3)) for a,b in coord_set}
print("fset size:", len(fset))
# scan every (xy X Y)
allxy = re.findall(r"\(xy\s+([-0-9.]+)\s+([-0-9.]+)\)", sch)
allxy_r = [(round(float(a),3), round(float(b),3)) for a,b in allxy]
print("total (xy) en sch:", len(allxy_r))
match = sum(1 for c in allxy_r if c in fset)
print("(xy) found in fset:", match)