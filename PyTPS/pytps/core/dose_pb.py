"""Pencil-beam dose calculation (educational).

For each control point:
1. fluence at the isocentre plane from jaws, MLC (with leaf transmission) and wedge;
2. the fluence is convolved with a narrow Gaussian (penumbra) and a broad exponential scatter kernel;
3. the radiological depth along each divergent ray is traced through the electron-density volume;
4. dose = k * MU * Sc * ISF * [ P(d) * F_primary + S(d) * F_scatter ].
P(d) and S(d) are the depth functions of the beam model fitted to the beam data (see beamdata.py).
Heterogeneities change the depth only (no lateral scatter scaling): good enough to teach, not for clinical use.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage
from scipy.signal import fftconvolve

from .beamdata import BeamModel
from .beams import LEAF_EDGES, SAD, Beam, ControlPoint, Frame
from .structures import StructureSet


@dataclass
class DoseGrid:
    spacing: float
    origin: np.ndarray            # (x0, y0, z0) of voxel [0,0,0]
    shape: tuple                  # (nz, ny, nx)
    inside: np.ndarray            # bool, voxel inside the body
    pts: np.ndarray               # (N, 3) patient coordinates of the inside voxels

    @classmethod
    def from_structures(cls, ss: StructureSet, spacing=4.0):
        img = ss.image
        ext = ss.external()
        body = ext.mask if ext is not None else np.ones(img.shape, bool)
        ks, js, is_ = [np.where(body.any(axis=ax))[0] for ax in ((1, 2), (0, 2), (0, 1))]
        lo = img.index_to_world((is_[0], js[0], ks[0])) - spacing
        hi = img.index_to_world((is_[-1], js[-1], ks[-1])) + spacing
        n = np.maximum(1, np.ceil((hi - lo) / spacing).astype(int) + 1)
        xs, ys, zs = (lo[i] + spacing * np.arange(n[i]) for i in range(3))
        Z, Y, X = np.meshgrid(zs, ys, xs, indexing="ij")
        ijk = img.world_to_index(np.stack([X, Y, Z], -1).reshape(-1, 3))
        inside = ndimage.map_coordinates(body.astype(np.float32), [ijk[:, 2], ijk[:, 1], ijk[:, 0]], order=0, cval=0).reshape(Z.shape) > 0.5
        pts = np.stack([X[inside], Y[inside], Z[inside]], -1)
        return cls(spacing, lo, Z.shape, inside, pts)

    def to_volume(self, values, extend=False):
        """Dose volume on the grid; extend=True fills the voxels outside the body with the nearest inside value,
        so that interpolation near the skin is not pulled down by the zeros outside."""
        v = np.zeros(self.shape, np.float32); v[self.inside] = values
        if extend:
            if getattr(self, "_nearest", None) is None:
                self._nearest = ndimage.distance_transform_edt(~self.inside, return_distances=False, return_indices=True)
            k, j, i = self._nearest
            v = v[k, j, i]
        return v

    def axis(self, i):
        return self.origin[i] + self.spacing * np.arange(self.shape[2 - i])


def equivalent_square(cp: ControlPoint):
    X, Y = cp.x2 - cp.x1, cp.y2 - cp.y1
    return 2 * X * Y / max(X + Y, 1e-6)


def fluence_map(cp: ControlPoint, beam: Beam, model: BeamModel, h=2.5, pad=40.0):
    """Relative fluence at the isocentre plane. Returns (F, u axis, v axis)."""
    u = np.arange(cp.x1 - pad, cp.x2 + pad + h / 2, h)
    v = np.arange(cp.y1 - pad, cp.y2 + pad + h / 2, h)
    U, V = np.meshgrid(u, v, indexing="ij")
    jaw = ((U >= cp.x1) & (U <= cp.x2) & (V >= cp.y1) & (V <= cp.y2)).astype(np.float32)
    F = jaw + model.jaw_t * (1 - jaw)
    if cp.left is not None and cp.right is not None:
        leaf = np.clip(np.searchsorted(LEAF_EDGES, V, side="right") - 1, 0, len(LEAF_EDGES) - 2)
        inbank = (V >= LEAF_EDGES[0]) & (V < LEAF_EDGES[-1])
        L, R = np.asarray(cp.left)[leaf], np.asarray(cp.right)[leaf]
        mopen = ((U >= L) & (U <= R)) | ~inbank
        F = F * np.where(mopen, 1.0, model.leaf_t)
    w = beam.wedge
    if w.angle:
        s = {"+X": U, "-X": -U, "+Y": V, "-Y": -V}[w.direction]
        k = 1.9 * model.mu_p * np.tan(np.radians(w.angle))
        F = F * model.wedge_factors.get(int(w.angle), w.factor) * np.exp(-k * s)
    return F.astype(np.float32), u, v


def _scatter_kernel(h, lam):
    r = np.arange(-5 * lam, 5 * lam + h / 2, h)
    X, Y = np.meshgrid(r, r, indexing="ij")
    k = np.exp(-np.hypot(X, Y) / lam)
    return (k / k.sum()).astype(np.float32)


def convolved(F, h, model: BeamModel):
    Fp = ndimage.gaussian_filter(F, model.sigma / h, mode="constant", cval=model.jaw_t)
    Fs = fftconvolve(F, _scatter_kernel(h, model.lam), mode="same")
    return Fp, Fs


class DoseEngine:
    def __init__(self, ss: StructureSet, models: dict, grid_mm=4.0):
        self.ss = ss
        self.models = models
        self.grid = DoseGrid.from_structures(ss, grid_mm)
        self.refresh_density()

    def refresh_density(self):
        self.density = self.ss.density()
        img = self.ss.image
        self._lo = np.array([e[0] for e in img.extent()]); self._hi = np.array([e[1] for e in img.extent()])

    # ------------------------------------------------------------------ calibration
    def k_cal(self, model: BeamModel):
        """cGy per MU per unit fluence, so that 10 x 10 cm at SSD 100 gives the calibration dose at dmax."""
        if getattr(model, "_k", None) is not None and model._kkey == (model.lam, model.sigma, model.s_max, model.calibration):
            return model._k
        cp = ControlPoint(0, 0, 0, -50, 50, -50, 50)
        F, u, v = fluence_map(cp, Beam("cal", np.zeros(3)), model)
        Fp, Fs = convolved(F, u[1] - u[0], model)
        c = (len(u) // 2, len(v) // 2)
        d = model.dmax
        val = (model.P(d) * Fp[c] + model.S(d) * Fs[c]) * (SAD / (SAD + d)) ** 2
        model._k = float(model.calibration / val); model._kkey = (model.lam, model.sigma, model.s_max, model.calibration)
        return model._k

    # ------------------------------------------------------------------ ray tracing
    def depth_table(self, fr: Frame, ulim, vlim, ray_step=None):
        img = self.ss.image
        corners = np.array([[x, y, z] for x in (self._lo[0], self._hi[0]) for y in (self._lo[1], self._hi[1]) for z in (self._lo[2], self._hi[2])])
        _, _, a = fr.project(corners)
        a0, a1 = max(1.0, a.min() - 10), a.max() + 10
        span = max(ulim[1] - ulim[0], vlim[1] - vlim[0])
        rs = ray_step or max(4.0, span / 90)
        us = np.arange(ulim[0], ulim[1] + rs, rs, dtype=np.float32)
        vs = np.arange(vlim[0], vlim[1] + rs, rs, dtype=np.float32)
        da = min(img.spacing) * 0.9
        As = np.arange(a0, a1 + da, da, dtype=np.float32)
        U, V = np.meshgrid(us, vs, indexing="ij")
        cum = np.zeros((len(us), len(vs), len(As)), np.float32)
        acc = np.zeros(U.shape, np.float32)
        path = np.sqrt(1 + (U ** 2 + V ** 2) / SAD ** 2) * da        # true path length per axial step
        org, sp = np.asarray(img.origin), np.asarray(img.spacing)
        for n, a in enumerate(As):
            p = fr.ray_point(U, V, np.full(U.shape, a))
            ijk = (p - org) / sp
            rho = ndimage.map_coordinates(self.density, [ijk[..., 2].ravel(), ijk[..., 1].ravel(), ijk[..., 0].ravel()], order=1, cval=0.0).reshape(U.shape)
            acc += rho * path
            cum[:, :, n] = acc - 0.5 * rho * path
        return cum, us, vs, As

    # ------------------------------------------------------------------ dose of one control point (cGy per MU)
    def cp_dose_per_mu(self, beam: Beam, cp: ControlPoint, model: BeamModel, pts=None):
        pts = self.grid.pts if pts is None else pts
        fr = Frame(cp, beam.iso, beam.orientation)
        h = 2.5 if max(cp.x2 - cp.x1, cp.y2 - cp.y1) < 250 else 5.0
        F, fu, fv = fluence_map(cp, beam, model, h=h, pad=min(5 * model.lam, 120))
        Fp, Fs = convolved(F, h, model)
        u, v, a = fr.project(pts)
        sel = (u >= fu[0]) & (u <= fu[-1]) & (v >= fv[0]) & (v <= fv[-1]) & (a > 1)
        out = np.zeros(len(pts), np.float32)
        if not sel.any():
            return out
        cum, us, vs, As = self.depth_table(fr, (fu[0], fu[-1]), (fv[0], fv[-1]))
        uu, vv, aa = u[sel], v[sel], a[sel]
        d = ndimage.map_coordinates(cum, [(uu - us[0]) / (us[1] - us[0]), (vv - vs[0]) / (vs[1] - vs[0]), (aa - As[0]) / (As[1] - As[0])], order=1, mode="nearest")
        ci = [(uu - fu[0]) / h, (vv - fv[0]) / h]
        fp = ndimage.map_coordinates(Fp, ci, order=1, mode="nearest"); fs = ndimage.map_coordinates(Fs, ci, order=1, mode="nearest")
        isf = (SAD / aa) ** 2
        out[sel] = self.k_cal(model) * model.sc(equivalent_square(cp)) * isf * (model.P(d) * fp + model.S(d) * fs)
        return out

    def beam_dose_per_mu(self, beam: Beam, pts=None, progress=None):
        """Dose (cGy) per beam MU, summed over the control points with their MU weights."""
        model = self.models[beam.energy]
        cps = beam.control_points()
        tot = None
        wsum = sum(c.weight for c in cps) or 1.0
        for n, cp in enumerate(cps):
            d = self.cp_dose_per_mu(beam, cp, model, pts) * (cp.weight / wsum)
            tot = d if tot is None else tot + d
            if progress:
                progress(n + 1, len(cps))
        return tot

    def point_dose_per_mu(self, beam: Beam, p):
        return float(self.beam_dose_per_mu(beam, np.asarray(p, float)[None])[0])

    def ssd(self, beam: Beam, cp: ControlPoint | None = None):
        """Source-skin distance on the central axis (mm), from the body outline."""
        cp = cp or beam.control_points()[0]
        fr = Frame(cp, beam.iso, beam.orientation)
        ext = self.ss.external()
        if ext is None:
            return float("nan")
        img = self.ss.image
        a = np.arange(SAD - 600, SAD + 600, 1.0)
        p = fr.ray_point(np.zeros_like(a), np.zeros_like(a), a)
        ijk = np.round(img.world_to_index(p)).astype(int)
        ok = (ijk[:, 0] >= 0) & (ijk[:, 1] >= 0) & (ijk[:, 2] >= 0) & (ijk[:, 0] < img.shape[2]) & (ijk[:, 1] < img.shape[1]) & (ijk[:, 2] < img.shape[0])
        hit = np.zeros(len(a), bool)
        hit[ok] = ext.mask[ijk[ok, 2], ijk[ok, 1], ijk[ok, 0]]
        return float(a[np.argmax(hit)]) if hit.any() else float("nan")
