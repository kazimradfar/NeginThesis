"""Inverse planning: cost functions, Stage 1 fluence optimisation and Stage 2 segmentation (IMRT and VMAT).

The dose of each control point is linear in its fluence map F (MU-weighted, at the isocentre plane):
    dose(voxel) = Pw(voxel) * (G * F)(u, v) + Sw(voxel) * (K * F)(u, v)
with G the penumbra Gaussian, K the scatter kernel and Pw / Sw the depth, inverse-square and calibration terms of
the pencil-beam model (dose_pb.py). The gradient of the cost with respect to F is obtained with the transposed
operations (splatting the voxel gradients into the map and convolving with the same symmetric kernels).
Educational model: no tongue-and-groove, no exact leaf-sequencing physics.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import ndimage
from scipy.signal import fftconvolve

from .beams import LEAF_EDGES, Beam, ControlPoint, Frame
from .dose_pb import DoseEngine, equivalent_square
from .plan import Plan, _target_points, calculate

COST_TYPES = ["Target Penalty", "Target EUD", "Quadratic Underdose", "Underdose DVH", "Quadratic Overdose",
              "Overdose DVH", "Maximum Dose", "Serial", "Parallel", "Conformality"]
COST_HELP = {
    "Target Penalty": ("Prescription (Gy)", "Min. volume (%)"), "Target EUD": ("EUD (Gy)", "Cell sensitivity α (1/Gy)"),
    "Quadratic Underdose": ("Dose (Gy)", "RMS (Gy)"), "Underdose DVH": ("Dose (Gy)", "Min. volume (%)"),
    "Quadratic Overdose": ("Dose (Gy)", "RMS (Gy)"), "Overdose DVH": ("Dose (Gy)", "Max. volume (%)"),
    "Maximum Dose": ("Max. dose (Gy)", "–"), "Serial": ("EUD limit (Gy)", "Power k"),
    "Parallel": ("Reference dose (Gy)", "Mean organ damage (%)"), "Conformality": ("Reference dose (Gy)", "Fall-off (mm)"),
}
K = {"tpE": 43, "tpU": 864, "qod": 576, "max": 2880, "par": 400, "eud": 3000, "ser": 3000, "dvh": 576, "conf": 150}


@dataclass
class Cost:
    structure: str
    type: str
    dose: float
    param: float = 0.0
    weight: float = 1.0
    mode: str = "objective"          # objective or constraint
    on: bool = True
    achieved: str = ""
    value: float = 0.0
    _mult: float = 5.0


@dataclass
class OptSettings:
    iterations: int = 120
    stage2_iterations: int = 40
    smoothing: float = 0.5           # 0 = off .. 2 = high (fluence smoothness)
    levels: int = 7                  # IMRT intensity levels
    max_segments: int = 12           # per beam
    min_area: float = 4.0            # cm^2
    min_mu: float = 2.0              # MU per segment
    vmat_apertures: int = 3          # apertures per optimisation control point
    arc_spacing: float = 8.0         # control point spacing used to optimise arcs (deg)
    leaf_speed: float = 25.0         # mm / s
    gantry_speed: float = 6.0        # deg / s
    dose_rate: float = 600.0         # MU / min
    layering: bool = False
    history: list = field(default_factory=list)


# ---------------------------------------------------------------------------------------------- voxel set
class VoxelSet:
    """Dose-grid voxels used by the optimiser: all voxels of the cost-function structures, the rest of the body sparsely."""

    def __init__(self, eng: DoseEngine, costs: list[Cost], target: str, layering: bool):
        ss, img, g = eng.ss, eng.ss.image, eng.grid
        ijk = np.round(img.world_to_index(g.pts)).astype(int)
        ok = (ijk >= 0).all(1) & (ijk[:, 0] < img.shape[2]) & (ijk[:, 1] < img.shape[1]) & (ijk[:, 2] < img.shape[0])
        names = []
        for c in costs:
            if c.on and c.structure not in names and ss.get(c.structure) is not None:
                names.append(c.structure)
        if target and target not in names and ss.get(target) is not None:
            names.append(target)
        member = {}
        anyorg = np.zeros(len(g.pts), bool)
        for n in names:
            s = ss.get(n)
            m = np.zeros(len(g.pts), bool)
            m[ok] = s.mask[ijk[ok, 2], ijk[ok, 1], ijk[ok, 0]]
            member[n] = m
            if s.type != "EXTERNAL":
                anyorg |= m
        gi = np.round((g.pts - g.origin) / g.spacing).astype(int)
        sparse = (gi[:, 0] % 2 == 0) & (gi[:, 1] % 2 == 0) & (gi[:, 2] % 2 == 0)
        keep = anyorg | sparse
        self.index = np.where(keep)[0]                   # into the dose-grid points
        self.pts = g.pts[self.index]
        # weights: sparse body voxels represent 8 voxels
        self.w = np.where(anyorg[self.index], 1.0, 8.0).astype(np.float32)
        self.member = {n: m[self.index] for n, m in member.items()}
        if layering:
            # a voxel belongs only to the highest structure in the list (target structures first in ties)
            order = [s.name for s in ss.structures if s.name in self.member and s.type != "EXTERNAL"]
            taken = np.zeros(len(self.index), bool)
            for n in order:
                self.member[n] = self.member[n] & ~taken
                taken |= self.member[n]
        self.dist = None
        self._eng = eng
        self._target = target

    def target_distance(self):
        if self.dist is None:
            ss = self._eng.ss
            s = ss.get(self._target)
            img = ss.image
            if s is None or not s.mask.any():
                self.dist = np.full(len(self.pts), 1e3, np.float32)
            else:
                dt = ndimage.distance_transform_edt(~s.mask, sampling=(img.spacing[2], img.spacing[1], img.spacing[0]))
                c = img.world_to_index(self.pts)
                self.dist = ndimage.map_coordinates(dt, [c[:, 2], c[:, 1], c[:, 0]], order=1, mode="nearest").astype(np.float32)
        return self.dist


# ---------------------------------------------------------------------------------------------- linear operator per control point
class CPOp:
    def __init__(self, eng: DoseEngine, beam: Beam, cp: ControlPoint, vox: VoxelSet, hu=2.5):
        model = eng.models[beam.energy]
        self.beam, self.cp, self.model = beam, cp, model
        self.hu, self.hv = hu, 5.0
        # fluence grid inside the jaws: u columns, v rows aligned with the leaf pairs
        self.u = np.arange(cp.x1 + hu / 2, cp.x2, hu)
        lo = np.searchsorted(LEAF_EDGES, cp.y1, side="right") - 1
        hi = np.searchsorted(LEAF_EDGES, cp.y2, side="left")
        self.leaf0 = int(max(0, lo)); self.leaf1 = int(min(len(LEAF_EDGES) - 1, hi))
        self.v = 0.5 * (LEAF_EDGES[self.leaf0:self.leaf1] + LEAF_EDGES[self.leaf0 + 1:self.leaf1 + 1])
        self.shape = (len(self.u), len(self.v))
        pad_u, pad_v = int(np.ceil(3 * model.lam / hu)), int(np.ceil(3 * model.lam / self.hv))
        self.pad = (pad_u, pad_v)
        # scatter kernel on the anisotropic grid
        ru = np.arange(-pad_u, pad_u + 1) * hu; rv = np.arange(-pad_v, pad_v + 1) * self.hv
        RU, RV = np.meshgrid(ru, rv, indexing="ij")
        ks = np.exp(-np.hypot(RU, RV) / model.lam); self.ks = (ks / ks.sum()).astype(np.float32)
        self.sig = (model.sigma / hu, model.sigma / self.hv)
        fr = Frame(cp, beam.iso, beam.orientation)
        u, v, a = fr.project(vox.pts)
        U0, V0 = self.u[0] - pad_u * hu, self.v[0] - pad_v * self.hv
        PU, PV = self.shape[0] + 2 * pad_u, self.shape[1] + 2 * pad_v
        gu, gv = (u - U0) / hu, (v - V0) / self.hv
        sel = (gu >= 0) & (gu <= PU - 1.001) & (gv >= 0) & (gv <= PV - 1.001) & (a > 1)
        self.vi = np.where(sel)[0]
        self.gu, self.gv = gu[sel].astype(np.float32), gv[sel].astype(np.float32)
        self.P = (PU, PV)
        if len(self.vi):
            cum, us, vs, As = eng.depth_table(fr, (u[sel].min(), u[sel].max()), (v[sel].min(), v[sel].max()))
            d = ndimage.map_coordinates(cum, [(u[sel] - us[0]) / (us[1] - us[0]) if len(us) > 1 else np.zeros(sel.sum()),
                                              (v[sel] - vs[0]) / (vs[1] - vs[0]) if len(vs) > 1 else np.zeros(sel.sum()),
                                              (a[sel] - As[0]) / (As[1] - As[0])], order=1, mode="nearest")
            k = eng.k_cal(model) * model.sc(equivalent_square(cp)) * (1000.0 / a[sel]) ** 2
            self.Pw = (k * model.P(d)).astype(np.float32); self.Sw = (k * model.S(d)).astype(np.float32)
        else:
            self.Pw = self.Sw = np.zeros(0, np.float32)
        i0 = np.floor(self.gu).astype(int); j0 = np.floor(self.gv).astype(int)
        self.i0, self.j0 = i0, j0
        self.fu, self.fv = self.gu - i0, self.gv - j0

    def _padded(self, F):
        out = np.zeros(self.P, np.float32)
        out[self.pad[0]:self.pad[0] + self.shape[0], self.pad[1]:self.pad[1] + self.shape[1]] = F
        return out

    def _gather(self, M):
        i0, j0, fu, fv = self.i0, self.j0, self.fu, self.fv
        return (M[i0, j0] * (1 - fu) * (1 - fv) + M[i0 + 1, j0] * fu * (1 - fv) + M[i0, j0 + 1] * (1 - fu) * fv + M[i0 + 1, j0 + 1] * fu * fv)

    def _splat(self, val):
        if not hasattr(self, "_flat"):
            PV = self.P[1]
            self._flat = (self.i0 * PV + self.j0, (self.i0 + 1) * PV + self.j0, self.i0 * PV + self.j0 + 1, (self.i0 + 1) * PV + self.j0 + 1)
            fu, fv = self.fu, self.fv
            self._wts = ((1 - fu) * (1 - fv), fu * (1 - fv), (1 - fu) * fv, fu * fv)
        n = self.P[0] * self.P[1]
        M = np.zeros(n)
        for idx, w in zip(self._flat, self._wts):
            M += np.bincount(idx, val * w, minlength=n)
        return M.reshape(self.P)

    def forward(self, F, out):
        """Add this control point's dose (cGy, for fluence F in MU) to out (voxel array)."""
        if not len(self.vi):
            return
        Fp = self._padded(F)
        gp = ndimage.gaussian_filter(Fp, self.sig, mode="constant")
        gs = fftconvolve(Fp, self.ks, mode="same")
        out[self.vi] += self.Pw * self._gather(gp) + self.Sw * self._gather(gs)

    def backward(self, g):
        """Gradient with respect to F of sum(g * dose)."""
        if not len(self.vi):
            return np.zeros(self.shape, np.float32)
        gv = g[self.vi]
        Mp, Ms = self._splat(gv * self.Pw), self._splat(gv * self.Sw)
        G = ndimage.gaussian_filter(Mp, self.sig, mode="constant") + fftconvolve(Ms, self.ks, mode="same")
        return G[self.pad[0]:self.pad[0] + self.shape[0], self.pad[1]:self.pad[1] + self.shape[1]].astype(np.float32)

    def aperture_map(self, left, right, leaf_t):
        """Relative fluence of an MLC aperture on this grid (with leaf transmission)."""
        A = np.full(self.shape, leaf_t, np.float32)
        for j in range(self.shape[1]):
            li = self.leaf0 + j
            l, r = left[li], right[li]
            cov = np.clip((np.minimum(r, self.u + self.hu / 2) - np.maximum(l, self.u - self.hu / 2)) / self.hu, 0, 1)
            A[:, j] = cov + leaf_t * (1 - cov)
        return A


# ---------------------------------------------------------------------------------------------- cost functions
def evaluate_costs(costs, vox: VoxelSet, D, rx, it=-1):
    """D: dose (Gy, total) at the voxels. Returns total cost and dC/dD."""
    g = np.zeros_like(D)
    total = 0.0
    w8 = vox.w
    for c in costs:
        c.value = 0.0
        if not c.on or c.structure not in vox.member:
            continue
        m = vox.member[c.structure]
        if not m.any():
            continue
        idx = np.where(m)[0]; d = D[idx]; wv = w8[idx]; n = wv.sum()
        w = c.weight * (c._mult if c.mode == "constraint" else 1.0)
        D0 = c.dose; f = 0.0; gd = np.zeros_like(d)
        t = c.type
        if t == "Target Penalty":
            e = (d - D0) / rx; u = np.minimum(0, (d - 0.95 * D0) / rx)
            f = float((wv * (K["tpE"] * e * e + K["tpU"] * u * u)).sum() / n)
            gd = (2 * K["tpE"] * e + 2 * K["tpU"] * u) / (rx * n) * wv
            c.achieved = f"V{D0:g}Gy {100 * wv[d >= D0].sum() / n:.1f}%"
        elif t in ("Quadratic Overdose", "Quadratic Underdose"):
            e = np.maximum(0, d - D0) if t == "Quadratic Overdose" else -np.maximum(0, D0 - d)
            f = float(K["qod"] * (wv * e * e).sum() / (n * rx * rx))
            gd = 2 * K["qod"] * e * wv / (rx * rx * n)
            c.achieved = f"RMS {np.sqrt((wv * e * e).sum() / n):.2f} Gy"
        elif t == "Maximum Dose":
            e = np.maximum(0, d - D0) / rx
            f = float(K["max"] * (wv * e * e).sum() / n); gd = 2 * K["max"] * e * wv / (rx * n)
            c.achieved = f"max {d.max():.1f} Gy"
        elif t == "Parallel":
            dd = np.maximum(d, 1e-3); r = (dd / D0) ** 4
            dam = r / (1 + r); mod = float((wv * dam).sum() / n)
            ex = max(0.0, mod - c.param / 100)
            f = K["par"] * ex * ex
            if ex > 0:
                gd = 2 * K["par"] * ex * (4 * r / ((1 + r) ** 2 * dd)) * wv / n
            c.achieved = f"damage {100 * mod:.1f}%"
        elif t == "Serial":
            k = max(1.0, c.param or 12)
            M = float((wv * (np.maximum(d, 0) / D0) ** k).sum() / n); ge = M ** (1 / k); ex = max(0.0, ge - 1)
            f = K["ser"] * ex * ex
            if ex > 0:
                gd = 2 * K["ser"] * ex * M ** (1 / k - 1) * (np.maximum(d, 0) / D0) ** (k - 1) * wv / (n * D0)
            c.achieved = f"EUD {ge * D0:.1f} Gy"
        elif t == "Target EUD":
            al = max(0.01, c.param or 0.5); mn = d.min(); ex_ = np.exp(-al * (d - mn)); S = float((wv * ex_).sum() / n)
            eud = mn - np.log(S) / al; ex = max(0.0, D0 - eud) / rx
            f = K["eud"] * ex * ex
            if ex > 0:
                gd = -2 * K["eud"] * ex * ex_ * wv / (n * S * rx)
            c.achieved = f"EUD {eud:.1f} Gy"
        elif t in ("Overdose DVH", "Underdose DVH"):
            over = t == "Overdose DVH"
            order = np.argsort(d); cw = np.cumsum(wv[order]) / n
            frac = np.clip(c.param / 100, 0, 1)
            pos = np.searchsorted(cw, 1 - frac); Dv = d[order][min(pos, len(d) - 1)]
            vol = 100 * wv[d > D0].sum() / n if over else 100 * wv[d >= D0].sum() / n
            c.achieved = f"V{D0:g}Gy {vol:.1f}%"
            if over and Dv > D0:
                sel = (d > D0) & (d <= Dv); e = (d - D0) / rx
                f = float(K["dvh"] * (wv * e * e)[sel].sum() / n); gd = np.where(sel, 2 * K["dvh"] * e * wv / (rx * n), 0)
            if not over and Dv < D0:
                sel = (d < D0) & (d >= Dv); e = (D0 - d) / rx
                f = float(K["dvh"] * (wv * e * e)[sel].sum() / n); gd = np.where(sel, -2 * K["dvh"] * e * wv / (rx * n), 0)
        elif t == "Conformality":
            lam = max(2.0, c.param or 25.0)
            dist = vox.target_distance()[idx]
            tgt = dist <= 0
            allow = D0 * np.maximum(0.25, 1.05 * np.exp(-np.maximum(0, dist - 5) / lam))
            e = np.where(tgt, 0, np.maximum(0, d - allow)) / rx
            f = float(K["conf"] * (wv * e * e).sum() / n); gd = 2 * K["conf"] * e * wv / (rx * n)
            c.achieved = f"above fall-off {100 * wv[e > 0].sum() / max(1, wv[~tgt].sum()):.1f}%"
        g[idx] += w * gd
        if c.mode == "constraint" and it > 0 and it % 15 == 0 and f > 1e-4:
            c._mult = min(500.0, c._mult * 1.5)
        c.value = c.weight * f
        total += c.value
    return total, g


# ---------------------------------------------------------------------------------------------- optimiser
class Optimiser:
    def __init__(self, plan: Plan, eng: DoseEngine, costs: list[Cost], st: OptSettings, progress=None):
        self.plan, self.eng, self.costs, self.st, self.progress = plan, eng, costs, st, progress
        self.vox = VoxelSet(eng, costs, plan.rx.target, st.layering)
        self.beams = [b for b in plan.beams if b.mlc_mode == "optimised" and b.weight > 0]
        self.fixed = [b for b in plan.beams if b not in self.beams and b.weight > 0]
        self.tmask = self.vox.member.get(plan.rx.target)
        self.ops = []

    def _report(self, text, n, total):
        if self.progress:
            return self.progress(text, n, total)
        return True

    def build(self):
        """Operators for the optimisation control points (arcs at st.arc_spacing)."""
        self.ops = []
        for b in self.beams:
            if b.kind == "ARC":
                span = b.arc_span(); n = max(2, int(round(span / self.st.arc_spacing))); sg = 1 if b.arc_dir == "CW" else -1
                angles = [(b.gantry + sg * span * (k + 0.5) / n) % 360 for k in range(n)]
                cps = [ControlPoint(g, b.collimator, b.couch, b.x1, b.x2, b.y1, b.y2, None, None, 1.0 / n) for g in angles]
            else:
                cps = [ControlPoint(b.gantry, b.collimator, b.couch, b.x1, b.x2, b.y1, b.y2, None, None, 1.0)]
            for cp in cps:
                self.ops.append(CPOp(self.eng, b, cp, self.vox, hu=2.5 if b.kind != "ARC" else 5.0))
                if not self._report(f"Preparing {b.name}…", len(self.ops), 0):
                    return False
        # dose of the beams that are not optimised (bias dose), in Gy total
        self.Dfix = np.zeros(len(self.vox.pts), np.float32)
        fx = self.plan.rx.fractions
        for b in self.fixed:
            if b.name in self.plan.beam_dose and b.mu > 0:
                self.Dfix += self.plan.beam_dose[b.name][self.vox.index] * b.mu * fx / 100.0
        return True

    def _dose(self, Fs):
        D = np.zeros(len(self.vox.pts), np.float32)
        for op, F in zip(self.ops, Fs):
            op.forward(F, D)
        return D * self.plan.rx.fractions / 100.0          # Gy total

    def _renorm(self, Fs, D):
        rx = self.plan.rx.dose
        if self.tmask is None or not self.tmask.any():
            return 1.0
        ma = float(D[self.tmask].mean()); mf = float(self.Dfix[self.tmask].mean())
        s = max(0.05, (rx - mf) / ma) if ma > 0 else 1.0
        for F in Fs:
            F *= s
        return s

    def _mean_gradient(self):
        """d(mean target dose)/dF for every control point (independent of F)."""
        if self.tmask is None or not self.tmask.any():
            return None
        gt = (self.tmask / self.tmask.sum()).astype(np.float32) * self.plan.rx.fractions / 100.0
        return [op.backward(gt) for op in self.ops]

    # --------------------------------------------------------------------------- Stage 1
    def stage1(self):
        if not self.ops and not self.build():
            return None
        rx = self.plan.rx.dose
        # initial fluence: open inside the target projection, roughly normalised
        Fs = []
        for op in self.ops:
            F = np.ones(op.shape, np.float32)
            Fs.append(F)
        D = self._dose(Fs)
        self._renorm(Fs, D)
        m1 = [np.zeros_like(F) for F in Fs]; m2 = [np.zeros_like(F) for F in Fs]
        lr0 = 0.06; b1, b2 = 0.9, 0.999
        H = self._mean_gradient()
        scale = [float(F.mean()) or 1.0 for F in Fs]
        self.st.history = []
        n = self.st.iterations
        for it in range(1, n + 1):
            D = self._dose(Fs)
            s = self._renorm(Fs, D); D = (D * s)
            tot, g = evaluate_costs(self.costs, self.vox, D + self.Dfix, rx, it)
            self.st.history.append(tot)
            gfac = self.plan.rx.fractions / 100.0
            lr = lr0 * (0.25 + 0.75 * max(0, 1 - it / n))
            c1, c2 = 1 / (1 - b1 ** it), 1 / (1 - b2 ** it)
            Gs = [op.backward(g) * gfac for op in self.ops]
            # the dose is renormalised to the prescription every iteration, so only the part of the gradient that
            # changes the dose distribution at fixed mean target dose matters (projection on that constraint)
            if H is not None:
                c = sum(float((G * F).sum()) for G, F in zip(Gs, Fs)) / max(1e-12, sum(float((h * F).sum()) for h, F in zip(H, Fs)))
                Gs = [G - c * h for G, h in zip(Gs, H)]
            for k, (op, F) in enumerate(zip(self.ops, Fs)):
                G = Gs[k]
                if self.st.smoothing > 0:
                    lap = 4 * F - np.roll(F, 1, 0) - np.roll(F, -1, 0) - np.roll(F, 1, 1) - np.roll(F, -1, 1)
                    G = G + self.st.smoothing * 1e-3 * lap / max(scale[k], 1e-6) * (np.abs(G).mean() + 1e-12) * 50
                m1[k] = b1 * m1[k] + (1 - b1) * G; m2[k] = b2 * m2[k] + (1 - b2) * G * G
                step = lr * scale[k] * (m1[k] * c1) / (np.sqrt(m2[k] * c2) + 1e-12)
                np.maximum(F - step, 0, out=F)
                np.minimum(F, 8 * scale[k], out=F)
            if not self._report(f"Stage 1 · iteration {it}/{n} · cost {tot:.4f}", it, n):
                break
        self.Fs = Fs
        return Fs

    # --------------------------------------------------------------------------- Stage 2
    def _segments(self, op: CPOp, F, levels, max_seg, min_area_mm2):
        """Intensity-level decomposition of a fluence map into MLC apertures (left, right leaf positions)."""
        mx = float(F.max())
        if mx <= 0:
            return []
        step = mx / levels
        q = np.round(F / step).astype(int)
        segs = []
        nleaf = len(LEAF_EDGES) - 1
        for lev in range(1, levels + 1):
            runs = []
            for j in range(op.shape[1]):
                on = q[:, j] >= lev
                rr = []; a = None
                for i in range(len(on) + 1):
                    o = i < len(on) and on[i]
                    if o and a is None:
                        a = i
                    if not o and a is not None:
                        rr.append((a, i)); a = None
                runs.append(rr)
            for s in range(max((len(r) for r in runs), default=0)):
                left = np.zeros(nleaf); right = np.zeros(nleaf); area = 0.0
                for j, rr in enumerate(runs):
                    li = op.leaf0 + j
                    if s < len(rr):
                        a, b = rr[s]
                        left[li] = op.u[a] - op.hu / 2; right[li] = op.u[b - 1] + op.hu / 2
                        area += (right[li] - left[li]) * op.hv
                if area >= min_area_mm2:
                    segs.append([left, right, step, area])
        segs.sort(key=lambda s: -s[2] * s[3])
        return segs[:max_seg]

    def stage2(self):
        if getattr(self, "Fs", None) is None:
            return False
        st = self.st
        leaf_t = {b.energy: self.eng.models[b.energy].leaf_t for b in self.beams}
        # sequence every optimisation control point
        segs_per_op = []
        for k, (op, F) in enumerate(zip(self.ops, self.Fs)):
            arc = op.beam.kind == "ARC"
            segs = self._segments(op, F, st.vmat_apertures + 2 if arc else st.levels, st.vmat_apertures if arc else st.max_segments,
                                  (1.0 if arc else st.min_area) * 100)
            segs_per_op.append(segs)
            self._report("Stage 2 · sequencing…", k + 1, len(self.ops))
        A = [[op.aperture_map(s[0], s[1], leaf_t[op.beam.energy]) for s in segs] for op, segs in zip(self.ops, segs_per_op)]
        w = [np.array([s[2] for s in segs], float) for segs in segs_per_op]
        rx = self.plan.rx.dose
        m1 = [np.zeros_like(x) for x in w]; m2 = [np.zeros_like(x) for x in w]
        H = self._mean_gradient()
        HR = [np.array([float((h * a).sum()) for a in aa]) for h, aa in zip(H, A)] if H is not None else None
        n = st.stage2_iterations
        for it in range(1, n + 1):
            Fs = [sum((wi * a for wi, a in zip(ww, aa)), np.zeros(op.shape, np.float32)) for op, ww, aa in zip(self.ops, w, A)]
            D = self._dose(Fs)
            s = 1.0
            if self.tmask is not None and self.tmask.any() and D[self.tmask].mean() > 0:
                s = max(0.05, (rx - self.Dfix[self.tmask].mean()) / D[self.tmask].mean())
            w = [x * s for x in w]; D = D * s
            tot, g = evaluate_costs(self.costs, self.vox, D + self.Dfix, rx, it)
            st.history.append(tot)
            gfac = self.plan.rx.fractions / 100.0
            grs = []
            for k, (op, aa) in enumerate(zip(self.ops, A)):
                G = op.backward(g) * gfac
                grs.append(np.array([float((G * a).sum()) for a in aa]))
            if H is not None:
                c = sum(float((gr * ww).sum()) for gr, ww in zip(grs, w)) / max(1e-12, sum(float((hr * ww).sum()) for hr, ww in zip(HR, w)))
                grs = [gr - c * hr for gr, hr in zip(grs, HR)]
            for k, (op, aa) in enumerate(zip(self.ops, A)):
                if not len(aa):
                    continue
                gr = grs[k]
                m1[k] = 0.9 * m1[k] + 0.1 * gr; m2[k] = 0.999 * m2[k] + 0.001 * gr * gr
                w0 = np.maximum(w[k], 1e-3)
                w[k] = np.maximum(0, w[k] - 0.04 * w0 * (m1[k] / (1 - 0.9 ** it)) / (np.sqrt(m2[k] / (1 - 0.999 ** it)) + 1e-12))
            if not self._report(f"Stage 2 · segment weights {it}/{n} · cost {tot:.4f}", it, n):
                break
        # write control points (MU-weighted) back to the beams
        by_beam: dict = {}
        for op, segs, ww in zip(self.ops, segs_per_op, w):
            for sgm, wi in zip(segs, ww):
                if wi <= 0:
                    continue
                by_beam.setdefault(op.beam.name, []).append((op.cp, sgm, wi))
        for b in self.beams:
            items = by_beam.get(b.name, [])
            if not items:
                b.cps = []; b.mu = 0; continue
            if b.kind != "ARC":
                items = [it_ for it_ in items if it_[2] >= st.min_mu] or items
            total = sum(i[2] for i in items)
            cps = []
            for cp, sgm, wi in items:
                cps.append(ControlPoint(cp.gantry, cp.collimator, cp.couch, cp.x1, cp.x2, cp.y1, cp.y2, sgm[0].copy(), sgm[1].copy(), wi / total))
            if b.kind == "ARC":
                # spread the apertures of each optimisation control point over its angular interval
                span = b.arc_span(); nop = max(2, int(round(span / st.arc_spacing))); sg = 1 if b.arc_dir == "CW" else -1
                groups: dict = {}
                for c in cps:
                    groups.setdefault(round(c.gantry, 3), []).append(c)
                out = []
                for g0, cl in groups.items():
                    for i, c in enumerate(cl):
                        off = (i + 0.5) / len(cl) - 0.5
                        c.gantry = (g0 + sg * off * span / nop) % 360
                        out.append(c)
                cps = out
            b.cps = cps
            b.mu = float(total)          # MU per fraction of the beam (fluence units are MU)
            b.weight = max(b.weight, 1e-3)
        return True

    def finish(self):
        """Exact dose of the sequenced beams with the full engine; MU kept (normalisation re-applied)."""
        for b in self.beams:
            self.plan.beam_dose.pop(b.name, None)
        # relative weights from the optimised MU so that normalise() reproduces them
        for b in self.beams:
            b.weight = b.mu if b.mu > 0 else 0.0
        for b in self.fixed:
            b.weight = b.mu if b.mu > 0 else b.weight
        calculate(self.plan, self.eng, only=[b.name for b in self.beams])

    def delivery(self):
        """MU per beam, number of segments / control points and a rough delivery time (s)."""
        st = self.st
        out = []
        for b in self.plan.beams:
            n = len(b.cps) if b.cps else 1
            if b.kind == "ARC":
                t = max(b.arc_span() / st.gantry_speed, b.mu / (st.dose_rate / 60))
            else:
                t = b.mu / (st.dose_rate / 60) + 1.5 * n + 10
            out.append((b.name, b.mu, n, t))
        return out


def default_costs(plan: Plan, ss):
    """Starting cost functions: target penalty and overdose on the target, parallel / serial on organs, body maximum."""
    rx = plan.rx.dose
    costs = [Cost(plan.rx.target, "Target Penalty", rx, 95, 2.0), Cost(plan.rx.target, "Quadratic Overdose", round(rx * 1.05, 1), 0.5)]
    for s in ss.structures:
        n = s.name.lower()
        if s.type == "EXTERNAL":
            costs.append(Cost(s.name, "Maximum Dose", round(rx * 1.1, 1)))
            costs.append(Cost(s.name, "Conformality", rx, 25, 0.2))
        elif s.is_target or not s.mask.any():
            continue
        elif any(k in n for k in ("cord", "stem", "chiasm", "nerve", "bowel", "rectum", "esoph")):
            costs.append(Cost(s.name, "Serial", round(min(rx * 0.7, 45), 1), 12))
        elif any(k in n for k in ("mandib", "femhead", "femoral", "bone")):
            costs.append(Cost(s.name, "Maximum Dose", round(rx * 1.05, 1)))
        else:
            costs.append(Cost(s.name, "Parallel", round(rx * 0.4, 1), 40))
    return costs
