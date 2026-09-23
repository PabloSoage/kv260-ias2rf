# Negative result: the IAS connector positions cannot be read from the .brd

*21 September 2026*

**Do not retry this.** Recorded so the next person does not spend the same effort.

## What was attempted

XTP681 ships the KV260 carrier layout as binary Allegro `.brd`
(`BRD-05058-03_A1.brd`, 32 MB). The goal was the X/Y of connectors `J7` and `J8`
— the two IAS connectors — to register the adapter's coordinate frame against
the KV260's, closing R-04.

The approach exploited a strong signature: on the adapter the two mating Hirose
connectors are **50.040 mm apart on one axis, with identical Y**
`[V, measured from CSI2-KRIA-KV260_Rev01.kicad_pcb]`. The carrier pair must
match. So:

1. Find `J7` / `J8` as NUL-terminated, delimited refdes strings. **Worked**:
   19 and 15 delimited occurrences.
2. Scan int32 values at matching relative offsets from each string, looking for
   a pair separated by 50.040 mm in plausible Allegro units.
3. Require a second pair at a contiguous offset with **equal** values — the
   shared Y.

## Why it failed

Step 2 alone produced a tempting hit: `J7 = 34,098` and `J8 = 14,396` in units
of 0.1 mil, giving 86.609 mm and 36.566 mm, separated by **50.043 mm** against
the 50.040 expected — a 3 µm discrepancy, well inside one unit of quantisation.

Step 3 killed it. **Zero** candidates had both the correct X separation and a
matching Y at contiguous offsets. The X hit was coincidence: with 19 × 15 string
sites and ~250 offsets each, a 4-unit window produces false positives.

Without the Y confirmation there is no way to tell a real coordinate from a
lucky integer, and a wrong registration is worse than none — it would put the
board outline in the wrong place with false confidence.

## What does work

The Cadence PCB Editor Viewer 25.1 is installed at
`C:\Cadence\PCBEditorViewer_25.1\tools\bin\allegro_free_viewer.exe`.

It must be given the board as a command-line argument. Launched from its
shortcut it starts in **APD+ mode**, which only opens `.mcm`, and the Open
dialog then offers no `.brd` — which looks like a missing filter but is a mode
difference:

```
"C:\Cadence\PCBEditorViewer_25.1\tools\bin\allegro_free_viewer.exe" "<path>\BRD-05058-03_A1.brd"
```

From there, `Display → Element` and a click on the component reports its
location. Four numbers (J7 X/Y, J8 X/Y) plus the outline extents are enough.

`extracta.exe`, the Allegro command-line database dump, is **not** included in
the free viewer, so there is no headless route.

## Postscript — 23 September 2026: closed by another route

The question this probe tried to answer is closed, **from the STEP model rather than the `.brd`**:
`_work/kv260_step_locate.py` finds the IAS connectors by part name (J7 at Y 62.024, J8 at Y 11.986),
and `_work/kv260_register_adapter.py` registers the adapter with three independent checks. See
`docs/INTERFACE_SPEC.md` §5.3.

For the record, the rejected `.brd` candidate above (J7 86.609, J8 36.566 mm) has the same
ordering as the STEP result, and the same separation to within 5 µm. That is **not** new evidence
that it was right: the separation is what it was selected on, and the ordering is a coin toss. The
advice stands. There is no reason to go back to the `.brd`.
