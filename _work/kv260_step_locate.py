#!/usr/bin/env python3
"""
Locate named parts of the KV260 in the official STEP assembly.

WHY THIS EXISTS
---------------
docs/INTERFACE_SPEC.md §5.3 left one thing open: the registration between the
adapter's coordinate frame and the KV260 model's, which decides which way the
adapter board may grow. The STL could not settle it - triangles carry no
names, and the IAS connectors did not come out as separable bodies
(_work/kv260_locate_ias.py). The .brd could not be parsed
(_work/brd_probe_NEGATIVE.md).

The STEP the STL was made from CAN settle it. It is a Creo assembly (AP203):
every part is a named PRODUCT, and every placement of a part is a
NEXT_ASSEMBLY_USAGE_OCCURRENCE with a rigid transform relative to its parent.
Walking the tree from the root and composing the transforms gives the world
position of every instance of every part, by name.

HOW AN INSTANCE'S TRANSFORM IS READ (AP203 / AP214)
---------------------------------------------------
    NAUO(parent_pd, child_pd)
    PRODUCT_DEFINITION_SHAPE(definition = NAUO)                    -> pds
    CONTEXT_DEPENDENT_SHAPE_REPRESENTATION(rel, pds)
    rel = (REPRESENTATION_RELATIONSHIP(rep_1, rep_2)
           REPRESENTATION_RELATIONSHIP_WITH_TRANSFORMATION(idt) ...)
    ITEM_DEFINED_TRANSFORMATION(item_1 in rep_1, item_2 in rep_2)

One of rep_1/rep_2 is the child's shape representation (found through
SHAPE_DEFINITION_REPRESENTATION of the child's product definition). The
placement belonging to the child's rep is the child frame, the other the
parent frame, and  parent <- child  =  M(parent item) . inverse(M(child item)).

The geometry of a part - for its bounding box - is every B-rep VERTEX_POINT
reachable from its shape representation(s). Not every CARTESIAN_POINT: the
first version did that, and surface placements (a plane's origin can be
anywhere on the plane) put the heatsink 20 mm BELOW the carrier. The check
that the fix is right: the fan cover's top now comes out at Z 28.75 mm, the
STL's maximum to the hundredth, and the rubber feet at Z -7.085.

Units: the file's length unit is the millimetre (Creo default; checked below).

Usage:
    py _work/kv260_step_locate.py <model.stp> [name-substring ...]
    (default substrings: the IAS connector candidate, fansink, board outline)
"""

import math
import re
import sys
from collections import defaultdict

DEFAULT_TARGETS = ["CONN_928X90X80_38P", "FANSINK", "BOARD_OUTLINE",
                   "128-05058", "CON_SAMTEC"]

IAS_SEPARATION_MM = 50.040       # [V] adapter layout, docs/INTERFACE_SPEC.md §2


# --------------------------------------------------------------------------
# Part 21 parsing
# --------------------------------------------------------------------------

def load(path):
    """{id: (TYPE or None for complex entities, raw argument text)}."""
    raw = open(path, "rb").read().decode("latin-1")
    data = raw[raw.index("DATA;") + 5: raw.rindex("ENDSEC;")]
    data = data.replace("\r", "").replace("\n", "")
    ents = {}
    for m in re.finditer(r"#(\d+)\s*=\s*(.*?);(?=\s*#\d+\s*=|\s*$)", data):
        body = m.group(2).strip()
        t = re.match(r"([A-Z0-9_]+)\s*\((.*)\)$", body)
        if t:
            ents[int(m.group(1))] = (t.group(1), t.group(2))
        else:
            ents[int(m.group(1))] = (None, body)       # complex entity
    return ents, raw


def refs(text):
    # Strings first: Creo names placements 'Placement #2847', and that '#2847'
    # is text, not a reference. Missing this silently resolves every
    # occurrence to the wrong entity and every transform to the identity.
    return [int(x) for x in re.findall(r"#(\d+)", re.sub(r"'[^']*'", "''", text))]


def floats(text):
    return [float(x) for x in re.findall(r"[-+]?\d+\.?\d*(?:[Ee][-+]?\d+)?", text)]


def point(ents, i):
    return floats(ents[i][1].split(",", 1)[1])[:3]


def direction(ents, i):
    return floats(ents[i][1].split(",", 1)[1])[:3]


# --------------------------------------------------------------------------
# 4x4 rigid transforms as nested lists
# --------------------------------------------------------------------------

def axis_matrix(ents, i):
    """AXIS2_PLACEMENT_3D -> 4x4 matrix mapping local -> containing frame."""
    r = refs(ents[i][1])
    o = point(ents, r[0])
    z = direction(ents, r[1]) if len(r) > 1 else [0, 0, 1]
    x = direction(ents, r[2]) if len(r) > 2 else [1, 0, 0]
    nz = math.sqrt(sum(c * c for c in z))
    z = [c / nz for c in z]
    d = sum(a * b for a, b in zip(x, z))
    x = [a - d * b for a, b in zip(x, z)]
    nx = math.sqrt(sum(c * c for c in x))
    x = [c / nx for c in x]
    y = [z[1] * x[2] - z[2] * x[1], z[2] * x[0] - z[0] * x[2], z[0] * x[1] - z[1] * x[0]]
    return [[x[0], y[0], z[0], o[0]],
            [x[1], y[1], z[1], o[1]],
            [x[2], y[2], z[2], o[2]],
            [0, 0, 0, 1]]


def mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def inv(m):
    r = [[m[j][i] for j in range(3)] for i in range(3)]        # R transposed
    t = [-sum(r[i][k] * m[k][3] for k in range(3)) for i in range(3)]
    return [r[0] + [t[0]], r[1] + [t[1]], r[2] + [t[2]], [0, 0, 0, 1]]


def apply(m, p):
    return [sum(m[i][k] * p[k] for k in range(3)) + m[i][3] for i in range(3)]


IDENTITY = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]


# --------------------------------------------------------------------------
# Assembly structure
# --------------------------------------------------------------------------

def build(ents):
    by_type = defaultdict(list)
    for i, (t, _) in ents.items():
        by_type[t].append(i)

    # product definition -> product name
    prod_name = {i: re.match(r"'([^']*)'", a).group(1)
                 for i in by_type["PRODUCT"] for a in [ents[i][1]]}
    pdf_prod = {}
    for t in ("PRODUCT_DEFINITION_FORMATION",
              "PRODUCT_DEFINITION_FORMATION_WITH_SPECIFIED_SOURCE"):
        for i in by_type[t]:
            pdf_prod[i] = refs(ents[i][1])[0]
    pd_name = {}
    for i in by_type["PRODUCT_DEFINITION"]:
        r = refs(ents[i][1])
        pd_name[i] = prod_name.get(pdf_prod.get(r[0]), "?")

    # product definition -> its shape representation(s)
    pds_def = {i: refs(ents[i][1])[0] for i in by_type["PRODUCT_DEFINITION_SHAPE"]}
    pd_reps = defaultdict(list)
    for i in by_type["SHAPE_DEFINITION_REPRESENTATION"]:
        pds, rep = refs(ents[i][1])[:2]
        pd_reps[pds_def.get(pds)].append(rep)

    # NAUO -> transform, via the pds whose definition is the NAUO
    nauo_pds = {pds_def[p]: p for p in pds_def}
    cdsr = {}
    for i in by_type["CONTEXT_DEPENDENT_SHAPE_REPRESENTATION"]:
        rel, pds = refs(ents[i][1])[:2]
        cdsr[pds] = rel

    children = defaultdict(list)       # parent pd -> [(child pd, parent<-child, occurrence name)]
    is_child = set()
    unresolved = 0
    for i in by_type["NEXT_ASSEMBLY_USAGE_OCCURRENCE"]:
        a = ents[i][1]
        name = re.findall(r"'([^']*)'", a)
        r = refs(a)
        parent, child = r[0], r[1]
        m = IDENTITY
        rel = cdsr.get(nauo_pds.get(i))
        if rel is not None:
            body = ents[rel][1]
            rr = re.search(r"REPRESENTATION_RELATIONSHIP\('[^']*','[^']*',#(\d+),#(\d+)\)", body)
            idt = re.search(r"WITH_TRANSFORMATION\(#(\d+)\)", body)
            if rr and idt:
                r1, r2 = int(rr.group(1)), int(rr.group(2))
                a1, a2 = refs(ents[int(idt.group(1))][1])[:2]
                child_reps = set(pd_reps.get(child, []))
                if r1 in child_reps:
                    m = mul(axis_matrix(ents, a2), inv(axis_matrix(ents, a1)))
                elif r2 in child_reps:
                    m = mul(axis_matrix(ents, a1), inv(axis_matrix(ents, a2)))
                else:
                    # Convention (rep_1 = child) as the fallback.
                    m = mul(axis_matrix(ents, a2), inv(axis_matrix(ents, a1)))
                    unresolved += 1
        children[parent].append((child, m, name[1] if len(name) > 1 else ""))
        is_child.add(child)

    roots = [p for p in pd_name if p not in is_child and children.get(p)]
    return pd_name, pd_reps, children, roots, unresolved


def local_points(ents, reps, cache={}):
    """The B-rep VERTICES reachable from these representations.

    Only VERTEX_POINTs, not every CARTESIAN_POINT: surfaces carry placements
    too, and a plane's origin can sit anywhere on the (infinite) plane - far
    outside the part. Counting those made a ~20 mm heatsink span 70 mm in Z.
    Parts with no vertices at all (a bare sphere, say) fall back to every
    point, and are then an over-estimate.
    """
    out = []
    for rep in reps:
        if rep in cache:
            out.extend(cache[rep])
            continue
        seen, stack, pts, loose = set(), [rep], [], []
        while stack:
            i = stack.pop()
            if i in seen or i not in ents:
                continue
            seen.add(i)
            t, a = ents[i]
            if t == "VERTEX_POINT":
                pts.append(point(ents, refs(a)[0]))
                continue
            if t == "CARTESIAN_POINT":
                loose.append(point(ents, i))
                continue
            # Do not climb back UP into other representations' contexts.
            if t in ("GEOMETRIC_REPRESENTATION_CONTEXT",) or t is None and "CONTEXT" in a:
                continue
            stack.extend(refs(a))
        pts = pts or loose
        cache[rep] = pts
        out.extend(pts)
    return out


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    path = sys.argv[1]
    targets = sys.argv[2:] or DEFAULT_TARGETS

    ents, raw = load(path)
    print(f"entities: {len(ents):,}")
    unit = re.search(r"SI_UNIT\(\.MILLI\.,\.METRE\.\)", raw)
    print(f"length unit: {'millimetre' if unit else 'NOT mm - check SI_UNIT!'}")

    pd_name, pd_reps, children, roots, unresolved = build(ents)
    print(f"assembly roots: {[pd_name[r] for r in roots]}")
    print(f"occurrences whose child rep could not be identified: {unresolved}")
    print()

    # Every instance path from the root(s).
    hits = defaultdict(list)            # product name -> [(world matrix, path)]
    stack = [(r, IDENTITY, pd_name[r]) for r in roots]
    while stack:
        pd, m, p = stack.pop()
        for child, t, occ in children.get(pd, []):
            wm = mul(m, t)
            name = pd_name.get(child, "?")
            cp = p + " / " + name
            if any(s.upper() in name.upper() for s in targets):
                hits[name].append((wm, cp, child))
            stack.append((child, wm, cp))

    results = {}
    for name in sorted(hits):
        for k, (wm, cp, pd) in enumerate(hits[name]):
            pts = local_points(ents, pd_reps.get(pd, []))
            if pts:
                w = [apply(wm, q) for q in pts]
                lo = [min(c[i] for c in w) for i in range(3)]
                hi = [max(c[i] for c in w) for i in range(3)]
            else:
                lo = hi = apply(wm, [0, 0, 0])
            org = apply(wm, [0, 0, 0])
            xa = [wm[0][0], wm[1][0], wm[2][0]]
            za = [wm[0][2], wm[1][2], wm[2][2]]
            results.setdefault(name, []).append((org, lo, hi))
            print(f"{name}  [{k}]")
            print(f"    origin  ({org[0]:9.3f}, {org[1]:9.3f}, {org[2]:9.3f})   "
                  f"x-axis ({xa[0]:+.2f},{xa[1]:+.2f},{xa[2]:+.2f})  "
                  f"z-axis ({za[0]:+.2f},{za[1]:+.2f},{za[2]:+.2f})")
            print(f"    bbox    X {lo[0]:9.3f} .. {hi[0]:9.3f}   Y {lo[1]:9.3f} .. {hi[1]:9.3f}"
                  f"   Z {lo[2]:8.3f} .. {hi[2]:8.3f}   ({len(pts)} pts)")
            print(f"    size    {hi[0]-lo[0]:.2f} x {hi[1]-lo[1]:.2f} x {hi[2]-lo[2]:.2f} mm")
            print(f"    path    {cp}")
        print()

    # The identity test for the IAS pair.
    for name, inst in results.items():
        if len(inst) < 2:
            continue
        for i in range(len(inst)):
            for j in range(i + 1, len(inst)):
                ca = [(inst[i][1][k] + inst[i][2][k]) / 2 for k in range(3)]
                cb = [(inst[j][1][k] + inst[j][2][k]) / 2 for k in range(3)]
                d = math.dist(ca, cb)
                flag = "  <-- IAS separation" if abs(d - IAS_SEPARATION_MM) < 0.1 else ""
                print(f"  {name} [{i}]-[{j}] centre distance {d:8.3f} mm  "
                      f"(dx {cb[0]-ca[0]:+.3f}, dy {cb[1]-ca[1]:+.3f}, dz {cb[2]-ca[2]:+.3f}){flag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
