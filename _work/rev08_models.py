#!/usr/bin/env python3
"""
3-D models for the Rev08 parts (17 Nov 2026), written into the board as text (never through pcbnew).

The LCSC land patterns of _work/footprints_rev08 came from easyeda2kicad with their EasyEDA models; when
_work/rev08_footprints.py copied them into the library it dropped the model references. This script puts them
back on the placed footprints of KV260-IAS2RF.kicad_pcb, with the offset, scale and rotation of the
source footprint, pointing at _work/mech/cache/models3d (outside git: EasyEDA's models are not redistributed,
docs/3D_MODELS.md section 2), with pure white turned to an off-white ceramic tone. The model files are copied there from --models (the directory easyeda2kicad
wrote them to).

Not covered, and why: J1501 (HX-TYPE-C 16P 180 LT H10.0), for which EasyEDA has no model and KiCad's library
has no vertical receptacle; SH1, SH2, which are the shield frames' copper walls, not parts.

Usage:  py _work/rev08_models.py --models <dir with the .wrl/.step files>
"""
import argparse
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PCB = os.path.join(ROOT, "KV260-IAS2RF.kicad_pcb")
SRC = os.path.join(ROOT, "_work", "footprints_rev08")
CACHE = os.path.join(ROOT, "_work", "mech", "cache", "models3d")
sys.path.insert(0, os.path.join(ROOT, "_work", "manual"))
import board_parts                                   # noqa: E402


def source_model(fp_name):
    """The (model ...) block of the source footprint, its file name and the block text."""
    p = os.path.join(SRC, fp_name + ".kicad_mod")
    if not os.path.exists(p):
        return None
    t = open(p, encoding="utf-8").read()
    i = t.find("(model ")
    if i < 0:
        return None
    depth, j = 0, i
    while True:
        if t[j] == "(":
            depth += 1
        elif t[j] == ")":
            depth -= 1
            if depth == 0:
                break
        j += 1
    block = t[i:j + 1]
    path = re.match(r'\(model "([^"]+)"', block).group(1)
    return os.path.basename(path), block


WHITE = "diffuseColor 1.0 1.0 1.0"
CERAMIC = "diffuseColor 0.62 0.60 0.55"     # the owner's render rule: nothing pure white (it burns out)


LIGHT_GREY = "diffuseColor 0.7529411764705882 0.7529411764705882 0.7529411764705882"


def tone(path):
    """EasyEDA paints ceramic bodies pure white, and the filters' bodies a light grey that the top view's light
    burns out to white; give both an off-white ceramic tone. Only those two colours are touched."""
    t = open(path, encoding="utf-8", errors="replace").read()
    n = t.replace(WHITE, CERAMIC)
    if os.path.basename(path).startswith("FILTER-"):
        n = n.replace(LIGHT_GREY, CERAMIC)
    if n != t:
        open(path, "w", encoding="utf-8").write(n)
        return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", required=True)
    args = ap.parse_args()
    toned = [f for f in os.listdir(args.models) if f.endswith(".wrl") and os.path.exists(os.path.join(CACHE, f))
             and tone(os.path.join(CACHE, f))]
    if toned:
        print("toned:", " ".join(toned))
    text = open(PCB, encoding="utf-8").read()
    os.makedirs(CACHE, exist_ok=True)
    out, done, skipped, pos = [], [], [], 0
    for b in board_parts._blocks(text, "footprint "):
        start = text.index(b, pos)
        end = start + len(b)
        name = re.match(r'\(footprint "([^"]+)"', b).group(1).split(":")[-1]
        ref = board_parts._prop(b, "Reference")
        src = source_model(name) if "(model " not in b else None
        if src:
            fname, block = src
            stem = os.path.splitext(fname)[0]
            for ext in (".wrl", ".step"):
                f = os.path.join(args.models, stem + ext)
                if not os.path.exists(f):
                    sys.exit(f"missing {f}")
                shutil.copy2(f, CACHE)
            tone(os.path.join(CACHE, stem + ".wrl"))
            block = re.sub(r'\(model "[^"]+"', f'(model "${{KIPRJMOD}}/_work/mech/cache/models3d/{fname}"', block, count=1)
            block = "\n".join(("\t" + ln if k else ln) for k, ln in enumerate(block.splitlines()))
            nb = b[:-1].rstrip() + "\n\t\t" + block + "\n\t)"
            out.append(text[pos:start] + nb)
            done.append(ref)
        else:
            out.append(text[pos:end])
            if "(model " not in b:
                skipped.append(ref)
        pos = end
    out.append(text[pos:])
    open(PCB, "w", encoding="utf-8", newline="").write("".join(out))
    print(f"models added to {len(done)} footprints: {' '.join(sorted(done))}")
    print(f"still without a model: {' '.join(sorted(skipped))}")


if __name__ == "__main__":
    main()
