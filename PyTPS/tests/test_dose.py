import numpy as np

from pytps.core import phantoms
from pytps.core.beamdata import DEPTHS, default_models
from pytps.core.beams import Beam, Frame, ControlPoint
from pytps.core.dose_pb import DoseEngine


def _engine():
    img, ss = phantoms.water_box(sp=(2.0, 2.0, 2.0))
    return DoseEngine(ss, default_models(), 4.0)


def test_calibration_and_pdd_in_water():
    eng = _engine()
    for e in ("6X", "10X"):
        m = eng.models[e]
        b = Beam("t", np.array([0.0, -150.0, 0.0]), energy=e)      # 10 x 10 cm, SSD 100 cm
        d = DEPTHS[(DEPTHS >= m.dmax) & (DEPTHS <= 250)]
        pts = np.column_stack([np.zeros_like(d), -150 + d, np.zeros_like(d)])
        D = eng.beam_dose_per_mu(b, pts)
        assert abs(D.max() - 1.0) < 0.03
        pdd = 100 * D / D.max()
        assert np.max(np.abs(pdd - np.interp(d, DEPTHS, m.pdd[100]))) < 2.0


def test_gantry_90_points_to_patient_left():
    fr = Frame(ControlPoint(90, 0, 0, -50, 50, -50, 50), np.zeros(3), "HFS")
    assert fr.source[0] > 999          # source on the patient's left (+x)
    fr = Frame(ControlPoint(0, 0, 0, -50, 50, -50, 50), np.zeros(3), "HFS")
    assert fr.source[1] < -999         # gantry 0: anterior (-y)


def test_lung_increases_dose_behind_it():
    img, ss = phantoms.water_box(sp=(2.0, 2.0, 2.0))
    lung = ss.add("Lung", np.zeros(img.shape, bool))
    Z, Y, X = np.meshgrid(img.axis("z"), img.axis("y"), img.axis("x"), indexing="ij")
    lung.mask[(Y > -100) & (Y < 0)] = True
    lung.density = 0.25
    eng = DoseEngine(ss, default_models(), 4.0)
    b = Beam("t", np.array([0.0, 0.0, 0.0]))
    p = np.array([[0.0, 60.0, 0.0]])
    with_lung = eng.beam_dose_per_mu(b, p)[0]
    lung.density = None; eng.refresh_density()
    assert with_lung > 1.2 * eng.beam_dose_per_mu(b, p)[0]


def test_optimiser_spares_rectum():
    from pytps.core.optimise import Optimiser, OptSettings, default_costs
    from pytps.core.plan import Plan, dvh
    img, ss = phantoms.pelvis()
    eng = DoseEngine(ss, default_models(), 5.0)
    p = Plan(); p.rx.target = "PTV"; p.rx.method = "mean"; p.rx.dose, p.rx.fractions = 78, 39
    k, j, i = [np.mean(a) for a in np.nonzero(ss.get("PTV").mask)]
    iso = img.index_to_world((i, j, k))
    for g in (0, 72, 144, 216, 288):
        b = Beam(f"G{g}", iso.copy(), gantry=g, x1=-50, x2=50, y1=-45, y2=45); b.mlc_mode = "optimised"; p.beams.append(b)
    costs = default_costs(p, ss)
    opt = Optimiser(p, eng, costs, OptSettings(iterations=40, stage2_iterations=15))
    opt.stage1(); opt.stage2(); opt.finish()
    assert all(b.cps for b in p.beams)
    ptv, rect = dvh(p, eng, "PTV"), dvh(p, eng, "Rectum")
    assert abs(ptv["mean"] - 78) < 2
    assert rect["mean"] < 30            # open 5-field plan: about 37 Gy
