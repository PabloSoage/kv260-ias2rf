"""STEP assembly (with its colours and names) -> glTF binary, for Blender.
    python _work/mech/step2glb.py in.step out.glb [linear_deflection_mm, default 0.05]
Needs OpenCascade's Python bindings: pip install cadquery-ocp (in a venv)."""
import sys, time
from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.TDocStd import TDocStd_Document
from OCP.TCollection import TCollection_ExtendedString, TCollection_AsciiString
from OCP.XCAFDoc import XCAFDoc_DocumentTool
from OCP.TDF import TDF_ChildIterator
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.RWGltf import RWGltf_CafWriter
from OCP.OCP.collections import IndexedDataMap_TCollection_AsciiString_TCollection_AsciiString as InfoMap
from OCP.Message import Message_ProgressRange
from OCP.IFSelect import IFSelect_RetDone
from OCP.RWMesh import RWMesh_CoordinateSystem

inp, out = sys.argv[1], sys.argv[2]
defl = float(sys.argv[3]) if len(sys.argv) > 3 else 0.05
t0 = time.time()
doc = TDocStd_Document(TCollection_ExtendedString("doc"))
r = STEPCAFControl_Reader(); r.SetColorMode(True); r.SetNameMode(True); r.SetLayerMode(True)
assert r.ReadFile(inp) == IFSelect_RetDone
r.Transfer(doc)
print("read", round(time.time() - t0), "s", flush=True)
st = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
it = TDF_ChildIterator(st.Label(), False); n = 0
while it.More():
    lab = it.Value(); it.Next()
    if st.IsSimpleShape_s(lab):
        BRepMesh_IncrementalMesh(st.GetShape_s(lab), defl, False, 0.3, True); n += 1
print(n, "parts")
print("meshed", round(time.time() - t0), "s", flush=True)
w = RWGltf_CafWriter(TCollection_AsciiString(out), True)
w.ChangeCoordinateSystemConverter().SetInputLengthUnit(0.001)      # mm in, metres out
w.ChangeCoordinateSystemConverter().SetInputCoordinateSystem(RWMesh_CoordinateSystem.RWMesh_CoordinateSystem_Zup)
w.Perform(doc, InfoMap(), Message_ProgressRange())
print("wrote", out, round(time.time() - t0), "s")
