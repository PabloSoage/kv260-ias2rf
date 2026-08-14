import pathlib, re, collections
t = pathlib.Path(r"E:\PCB\adapter_AMD_Xilinx_KRIA-KV260\CSI2-KRIA-KV260_Rev01-erc.rpt").read_text(encoding='utf-8').splitlines()
hits = []
headers = ('[pin_not_connected]','[label_dangling]','[wire_dangling]','[unconnected_wire_endpoint]','[no_connect_dangling]','[isolated_pin_label]')
i = 0
while i < len(t):
    if any(h in t[i] for h in headers):
        j = i + 1
        while j < len(t) and (t[j].strip()=='' or t[j].strip().startswith(';')): j += 1
        block = []
        while j < len(t) and not t[j].lstrip().startswith('['):
            block.append(t[j].strip()); j += 1
        hits.append((t[i].split(']:')[0]+']', block))
        i = j
    else: i += 1
print('Total entradas:', len(hits))
print()
import collections
cnt = collections.Counter(h[0] for h in hits)
for k,n in cnt.most_common(): print(f'{k}: {n}')
print()
# pin_not_connected refs
sym_re = re.compile(r'Symbol\s+(\S+)\s+(?:\[([^]]*)\])?')
refs = collections.Counter()
samples = []
for cat, blk in hits:
    if 'pin_not_connected' in cat:
        for L in blk:
            m = sym_re.search(L)
            if m: refs[m.group(1)] += 1
        samples.append(blk[0] if blk else '')
print()
print('Refs con pin_not_connected (top 30):')
for r,n in refs.most_common(30): print(f'  {r}: {n}')
print()
print('Sample first 15 pin_not_connected lines:')
for s in samples[:15]: print(' '+s[:200])