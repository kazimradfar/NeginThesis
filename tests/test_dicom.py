import numpy as np
import pytest

pydicom = pytest.importorskip("pydicom")

from pytps.core import dicomio, phantoms
from pytps.core.structures import StructureSet


def test_roundtrip_ct_and_rtstruct(tmp_path):
    img, ss = phantoms.thorax()
    dicomio.write_ct_series(str(tmp_path / "ct"), img)
    dicomio.save_rtstruct(str(tmp_path / "ct" / "RS.dcm"), ss)
    series = dicomio.scan_folder(str(tmp_path))
    mods = sorted(s.modality for s in series)
    assert mods == ["CT", "RTSTRUCT"]
    ct = next(s for s in series if s.modality == "CT")
    img2 = dicomio.load_ct(ct.files)
    assert img2.shape == img.shape
    assert np.allclose(img2.origin, img.origin, atol=0.01)
    assert abs(float(img2.array.mean()) - float(np.round(img.array).mean())) < 1
    assert img2.patient["id"].startswith("ANON")
    ss2 = StructureSet(img2)
    names = dicomio.load_rtstruct(next(s for s in series if s.modality == "RTSTRUCT").files[0], ss2)
    assert "PTV" in names and "BODY" in names
    for n in ("PTV", "Lung_R", "BODY"):
        v1, v2 = ss.get(n).volume_cc(img), ss2.get(n).volume_cc(img2)
        assert abs(v1 - v2) / v1 < 0.08, (n, v1, v2)


def test_rtplan_and_rtdose_roundtrip(tmp_path):
    from pytps.core.beamdata import default_models
    from pytps.core.beams import Beam, Wedge
    from pytps.core.dose_pb import DoseEngine
    from pytps.core.plan import Plan, calculate
    img, ss = phantoms.pelvis()
    eng = DoseEngine(ss, default_models(), 6.0)
    p = Plan("RT"); p.rx.target = "PTV"
    iso = np.array([0.0, 10.0, 0.0])
    b1 = Beam("AP", iso.copy(), x1=-40, x2=40, y1=-35, y2=35); b1.mlc_mode = "conformal"
    b2 = Beam("LAT", iso.copy(), gantry=90, energy="10X", wedge=Wedge(30, "-X")); b2.mlc_mode = "conformal"
    b3 = Beam("ARC", iso.copy(), kind="ARC", gantry=181, arc_stop=179, cp_spacing=20)
    p.beams = [b1, b2, b3]
    calculate(p, eng)
    dicomio.save_rtplan(str(tmp_path / "rp.dcm"), p, img)
    beams, rx = dicomio.load_rtplan(str(tmp_path / "rp.dcm"))
    assert [b.name for b in beams] == ["AP", "LAT", "ARC"]
    assert abs(beams[1].gantry - 90) < 1e-3 and beams[1].energy == "10X" and beams[1].wedge.angle == 30
    assert beams[2].kind == "ARC" and len(beams[2].cps) == len(b3.control_points())
    for a, b in zip(p.beams, beams):
        assert abs(a.mu - b.mu) < 0.01
    assert np.allclose(beams[0].cps[0].left, b1.left, atol=0.1)
    vol = eng.grid.to_volume(p.dose)
    dicomio.save_rtdose(str(tmp_path / "rd.dcm"), vol, eng.grid.spacing, eng.grid.origin, img)
    arr, sp, org = dicomio.load_rtdose(str(tmp_path / "rd.dcm"))
    assert arr.shape == vol.shape and abs(float(arr.max()) - float(vol.max())) < 0.01 * float(vol.max())
    assert np.allclose(org, eng.grid.origin, atol=0.01)
