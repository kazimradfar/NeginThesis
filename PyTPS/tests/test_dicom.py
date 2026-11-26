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
