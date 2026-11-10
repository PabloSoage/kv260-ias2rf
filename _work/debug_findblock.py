import pathlib, re
text = pathlib.Path(r"C:\Users\pablo\KiCad\EasyEDA.kicad_sym").read_text(encoding="utf-8")
lines = text.splitlines()
name = "AD9268BCPZ-125"
pat = re.compile(r'^\s*\(symbol\s+"' + re.escape(name) + r'"', re.M)
ms = list(pat.finditer(text))
print(f"matches: {len(ms)}")
for m in ms:
    start = text.count("\n", 0, m.start())
    print(f"  match at char {m.start()} = line 0idx {start} (1idx {start+1}); {start} newlines before it")
    print(f"    first 80 chars of match: {m.group(0)[:80]!r}")
# Try find_block (as the script does)
m = pat.search(text)
start = text.count("\n", 0, m.start())
print(f"\nfind_block: search returns a match at char {m.start()} = 0-idx line {start}, 1-idx {start+1}")
depth = 0
last_j = -1
for j in range(start, min(start+5, len(lines))):
    s = re.sub(r'"[^"]*"', '""', lines[j])
    delta = s.count("(") - s.count(")")
    depth += delta
    print(f"  L{j+1} (1idx): depth += {delta} -> {depth}. line: {lines[j][:80]!r}")