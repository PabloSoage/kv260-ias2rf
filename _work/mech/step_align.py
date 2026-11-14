"""Re-places EasyEDA STEP models in their VRML's frame (14 Nov), so kicad-cli pcb export glb --subst-models
puts them where KiCad's own 3-D view puts the VRML: EasyEDA centres the STEP, not the VRML (J1001 was 2.1 / 3.5 mm
off in the Blender renders, J1201 2.2 mm, the SRP7028A inductors 0.5 mm deep in the board). Colours kept
(XDE). The originals are kept as <name>.easyeda.step. Shifts measured by comparing both files' bounds.

    micromamba run -n cq python _work/mech/step_align.py      # WSL, cadquery/OCP env
"""
import os, shutil, sys
from OCP.STEPCAFControl import STEPCAFControl_Reader, STEPCAFControl_Writer
from OCP.TDocStd import TDocStd_Document
from OCP.TCollection import TCollection_ExtendedString
from OCP.XCAFDoc import XCAFDoc_DocumentTool
from OCP.TDF import TDF_LabelSequence
from OCP.gp import gp_Trsf, gp_Vec
from OCP.TopLoc import TopLoc_Location
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPControl import STEPControl_AsIs

D = "/mnt/d/Repos/kv260-ias2rf/_work/mech/cache/models3d"
SHIFT = {"DC-IN-TH_PJ-102AH": (2.115, 3.5, 0.0), "RJ45-TH_HR911130C": (0.0, 2.2, 0.0),
         "IND-SMD_SRP7028A-8R2M": (0.2, -0.092, 0.545), "SMD-6_L7.9-W5.6-P2.54-LS7.0-BL": (0.0, 0.0, 0.14)}
for name, d in SHIFT.items():
    src = f"{D}/{name}.easyeda.step"
    if not os.path.exists(src):
        shutil.copy(f"{D}/{name}.step", src)
    doc = TDocStd_Document(TCollection_ExtendedString("XmlOcaf"))
    r = STEPCAFControl_Reader(); r.SetColorMode(True); r.SetNameMode(True); r.SetLayerMode(True)
    assert r.ReadFile(src) == IFSelect_RetDone
    r.Transfer(doc)
    st = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    roots = TDF_LabelSequence(); st.GetFreeShapes(roots)
    t = gp_Trsf(); t.SetTranslation(gp_Vec(*d))
    asm = st.NewShape()
    for i in range(1, roots.Length() + 1):
        st.AddComponent(asm, roots.Value(i), TopLoc_Location(t))
    st.UpdateAssemblies()
    w = STEPCAFControl_Writer(); w.SetColorMode(True); w.SetNameMode(True)
    w.Transfer(asm, STEPControl_AsIs)
    assert w.Write(f"{D}/{name}.step") == IFSelect_RetDone
    print("aligned", name, d)
