import pathlib, re
for fname in ["FRONTEND.kicad_sch", "CSI2-KRIA-KV260_Rev01.kicad_pcb"]:
    f = pathlib.Path(fname)
    t = f.read_text(encoding="utf-8")
    before = len(t)
    t = re.sub(r'C_BP(\d+)', r'CF\1', t)
    f.write_text(t, encoding="utf-8")
    c1 = t.count('CF1"') + t.count('CF1 ')
    print(f'{fname}: {c1} CF1 refs, C_BP remaining: {"C_BP" in t}')
