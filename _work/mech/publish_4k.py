"""Publish the 4K Blender renders: PNG masters in _work/mech/cache/renders4k (git-ignored) -> JPEG q90 in
docs/img/highres/renders. A 4K PNG of a render is 7-9 MB; the JPEG keeps the resolution at about a tenth of that.

    python _work/mech/publish_4k.py
"""
import glob
import os
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "_work", "mech", "cache", "renders4k")
DST = os.path.join(ROOT, "docs", "img", "highres", "renders")
os.makedirs(DST, exist_ok=True)
for p in sorted(glob.glob(os.path.join(SRC, "*_4k.png"))):
    out = os.path.join(DST, os.path.basename(p)[:-4] + ".jpg")
    Image.open(p).convert("RGB").save(out, quality=90, optimize=True)
    print(f"{os.path.basename(out)}: {os.path.getsize(out) / 1e6:.1f} MB")
