"""Treatment plan: beams, prescription, MU normalisation, total dose and DVH."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .beams import Beam, conformal_leaves, Frame
from .dose_pb import DoseEngine


@dataclass
class Prescription:
    dose: float = 60.0              # Gy (total)
    fractions: int = 30
    target: str = "PTV"
    method: str = "isocentre"       # isocentre, mean, D95, D50, point
    point: np.ndarray | None = None
    percent: float = 100.0          # prescription isodose (%)

    @property
    def per_fraction(self):
        return self.dose / max(1, self.fractions)


@dataclass
class Plan:
    name: str = "Plan 1"
    beams: list = field(default_factory=list)
    rx: Prescription = field(default_factory=Prescription)
    beam_dose: dict = field(default_factory=dict)      # beam name -> dose per MU (cGy) on the dose grid
    dose: np.ndarray | None = None                     # total dose (Gy) on the dose grid inside points
    version: int = 0

    def beam(self, name):
        return next((b for b in self.beams if b.name == name), None)

    def new_name(self, base="B"):
        n = 1
        names = {b.name for b in self.beams}
        while f"{base}{n}" in names:
            n += 1
        return f"{base}{n}"

    def isocentre(self):
        return self.beams[0].iso.copy() if self.beams else None


def prepare_mlc(plan: Plan, eng: DoseEngine):
    """Fit the leaves of 'conformal' beams to their structure (projection of the structure voxels)."""
    ss = eng.ss
    for b in plan.beams:
        if b.mlc_mode != "conformal":
            continue
        s = ss.get(b.mlc_target or plan.rx.target)
        if s is None or not s.mask.any():
            continue
        k, j, i = np.nonzero(s.mask)
        step = max(1, len(k) // 40000)
        pts = ss.image.index_to_world(np.column_stack([i[::step], j[::step], k[::step]]))
        cp = b.control_points()[0]
        b.left, b.right = conformal_leaves(Frame(cp, b.iso, b.orientation), pts, b.mlc_margin, b.x1, b.x2, b.y1, b.y2)


def calculate(plan: Plan, eng: DoseEngine, progress=None, only=None):
    """Dose per MU of each (changed) beam on the dose grid."""
    prepare_mlc(plan, eng)
    todo = [b for b in plan.beams if (only is None or b.name in only)]
    for n, b in enumerate(todo):
        plan.beam_dose[b.name] = eng.beam_dose_per_mu(b)
        if progress:
            progress(n + 1, len(todo), b.name)
    for k in list(plan.beam_dose):
        if plan.beam(k) is None:
            del plan.beam_dose[k]
    normalise(plan, eng)


def _target_points(plan: Plan, eng: DoseEngine):
    s = eng.ss.get(plan.rx.target)
    if s is None:
        return None
    img = eng.ss.image
    ijk = np.round(img.world_to_index(eng.grid.pts)).astype(int)
    ok = (ijk >= 0).all(1) & (ijk[:, 0] < img.shape[2]) & (ijk[:, 1] < img.shape[1]) & (ijk[:, 2] < img.shape[0])
    sel = np.zeros(len(ijk), bool)
    sel[ok] = s.mask[ijk[ok, 2], ijk[ok, 1], ijk[ok, 0]]
    return sel


def normalise(plan: Plan, eng: DoseEngine):
    """MU of each beam: relative weights are kept, the sum is scaled to meet the prescription."""
    beams = [b for b in plan.beams if b.name in plan.beam_dose and b.weight > 0]
    if not beams:
        plan.dose = None; return
    rx = plan.rx
    want_cgy = rx.per_fraction * 100 * 100.0 / rx.percent
    # dose per unit weight at the normalisation point / volume
    if rx.method in ("isocentre", "point"):
        p = rx.point if (rx.method == "point" and rx.point is not None) else beams[0].iso
        per = {b.name: eng.point_dose_per_mu(b, p) for b in beams}
        ref = sum(b.weight * per[b.name] for b in beams)
        scale = want_cgy / ref if ref > 0 else 0
    else:
        unit = sum(b.weight * plan.beam_dose[b.name] for b in beams)
        sel = _target_points(plan, eng)
        if sel is None or not sel.any():
            scale = 0
        else:
            v = unit[sel]
            ref = {"mean": v.mean(), "D95": np.percentile(v, 5), "D50": np.median(v)}.get(rx.method, v.mean())
            scale = want_cgy / ref if ref > 0 else 0
    for b in plan.beams:
        b.mu = float(b.weight * scale) if b in beams else 0.0
    # total plan dose in Gy (all fractions)
    tot = np.zeros(len(eng.grid.pts), np.float32)
    for b in beams:
        tot += plan.beam_dose[b.name] * b.mu
    plan.dose = tot * rx.fractions / 100.0
    plan.version += 1


def dvh(plan: Plan, eng: DoseEngine, name: str, bins=400):
    """Cumulative DVH of a structure: (dose axis Gy, volume %) and statistics."""
    if plan.dose is None:
        return None
    s = eng.ss.get(name)
    if s is None or not s.mask.any():
        return None
    img = eng.ss.image
    # sample the structure voxels (CT grid) with the dose (trilinear from the dose grid)
    from scipy import ndimage
    k, j, i = np.nonzero(s.mask)
    step = max(1, len(k) // 200000)
    w = img.index_to_world(np.column_stack([i[::step], j[::step], k[::step]]))
    g = eng.grid
    vol = g.to_volume(plan.dose)
    c = (w - g.origin) / g.spacing
    d = ndimage.map_coordinates(vol, [c[:, 2], c[:, 1], c[:, 0]], order=1, mode="nearest")
    d.sort()
    dmax = max(float(d[-1]), plan.rx.dose * 1.1)
    axis = np.linspace(0, dmax * 1.05, bins)
    vol_pct = 100.0 * (len(d) - np.searchsorted(d, axis)) / len(d)
    pct = lambda p: float(d[min(len(d) - 1, max(0, int((1 - p / 100) * len(d))))])
    return {"dose": axis, "volume": vol_pct, "mean": float(d.mean()), "min": float(d[0]), "max": float(d[-1]),
            "D": pct, "V": lambda x: float(100.0 * (len(d) - np.searchsorted(d, x)) / len(d)), "cc": s.volume_cc(img)}
