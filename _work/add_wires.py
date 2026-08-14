#!/usr/bin/env python3
"""Anade wires visuales entre componentes clave del FRONTEND."""
import pathlib, re, uuid

DST = pathlib.Path(r"E:\PCB\adapter_AMD_Xilinx_KRIA-KV260\FRONTEND.kicad_sch")
text = DST.read_text(encoding="utf-8")

def make_wire(x1, y1, x2, y2):
    u = uuid.uuid4()
    return f"""	(wire
		(pts
			(xy {x1} {y1}) (xy {x2} {y2})
		)
		(stroke (width 0) (type default))
		(uuid "{u}")
	)"""

wires = []

# Power chain: J_PWR(1) → D_TVS(1) → TPS54202(VIN) → TPS82140(VIN) → ADP151(VIN)
# Barrel pin1 at (46.35, 41.27) → TVS pin1 at (54.92, 40.0)
wires.append(make_wire(46.35, 41.27, 46.35, 40.0))      # vertical
wires.append(make_wire(46.35, 40.0, 54.92, 40.0))        # horizontal
# TVS pin2 at (65.08, 40.0) → TPS54202 VIN(3) at (77.30, 37.46)
wires.append(make_wire(65.08, 40.0, 77.30, 40.0))
wires.append(make_wire(77.30, 40.0, 77.30, 37.46))
# TPS54202 SW(2) at (77.30, 40.0) → TPS82140 VIN(2) at (118.57, 40.0)
wires.append(make_wire(77.30, 40.0, 118.57, 40.0))
# TPS82140 VOUT(4) at (118.57, 34.92) → ADP151 VIN(1) at (159.84, 42.54)
wires.append(make_wire(118.57, 34.92, 118.57, 25.0))
wires.append(make_wire(118.57, 25.0, 159.84, 25.0))
wires.append(make_wire(159.84, 25.0, 159.84, 42.54))

# Clock chain: Y_CLK OUTPUT(3) at (57.78, 108.73) → U_CLK CLK(1) at (79.84, 117.62)
wires.append(make_wire(57.78, 108.73, 65.0, 108.73))
wires.append(make_wire(65.0, 108.73, 65.0, 117.62))
wires.append(make_wire(65.0, 117.62, 79.84, 117.62))

# U_CLK Q0+(15) at (100.16, 115.08) → U_ADC CLK+(6) at (143.49, 130.32)
wires.append(make_wire(100.16, 115.08, 100.16, 100.0))
wires.append(make_wire(100.16, 100.0, 143.49, 100.0))
wires.append(make_wire(143.49, 100.0, 143.49, 130.32))

# U_CLK Q1+(13) at (100.16, 104.92) → U_DAC CLK1(18) at (222.22, 96.03)
wires.append(make_wire(100.16, 104.92, 100.16, 90.0))
wires.append(make_wire(100.16, 90.0, 222.22, 90.0))
wires.append(make_wire(222.22, 90.0, 222.22, 96.03))

# Insert wires before sheet_instances
insert = text.rfind("(sheet_instances")
new_text = text[:insert] + "\n".join(wires) + "\n" + text[insert:]

cleaned = re.sub(r'"[^"]*"', '""', new_text)
delta = cleaned.count("(") - cleaned.count(")")
print(f"Wires: {len(wires)}, delta: {delta}")

if delta == 0:
    DST.write_text(new_text, encoding="utf-8")
    print("[ok] Wires visuales añadidos a FRONTEND")
else:
    print(f"[!!] delta={delta}")