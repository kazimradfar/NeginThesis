"""Beam data and the parameters of the pencil-beam model.

The default data are GENERIC teaching values with the typical shape of 6 MV and 10 MV beams.
They do not describe any real treatment machine. Students can edit the measured-style data
(PDD for several field sizes, output factors, wedge factors) and refit the model ("commissioning").
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import least_squares

DEPTHS = np.array([0, 2, 5, 10, 15, 20, 30, 40, 50, 75, 100, 150, 200, 250, 300], float)  # mm


@dataclass
class BeamModel:
    name: str
    # measured-style data (SSD 100 cm)
    pdd: dict                                   # field size (mm, square) -> PDD (%) at DEPTHS
    output: dict                                # field size (mm) -> total output factor Scp (10x10 = 1)
    head_scatter: dict                          # field size (mm) -> collimator scatter factor Sc
    wedge_factors: dict = field(default_factory=lambda: {15: 0.78, 30: 0.65, 45: 0.52, 60: 0.40})
    calibration: float = 1.0                    # cGy / MU at dmax, 10 x 10, SSD 100
    # fitted model parameters
    mu_p: float = 0.005                         # primary attenuation (1/mm)
    dmax: float = 15.0
    surf: float = 0.45                          # relative surface dose of the primary part
    bu: float = 4.5                             # build-up length (mm)
    s_max: float = 0.25                         # scatter amplitude
    s_grow: float = 60.0                        # scatter build-up with depth (mm)
    mu_s: float = 0.004                         # scatter attenuation (1/mm)
    lam: float = 30.0                           # scatter kernel radius (mm)
    sigma: float = 3.5                          # penumbra (mm) at the isocentre
    leaf_t: float = 0.015                       # MLC transmission
    jaw_t: float = 0.002
    fit_rms: float = float("nan")

    # ------------------------------------------------------------------ model functions (depth d in mm water-equivalent)
    def P(self, d):
        d = np.maximum(np.asarray(d, float), 0)
        bu = 1 - (1 - self.surf) * np.exp(-d / self.bu)
        return bu * np.exp(-self.mu_p * np.maximum(d - self.dmax, 0)) / (1 - (1 - self.surf) * np.exp(-self.dmax / self.bu))

    def S(self, d):
        d = np.maximum(np.asarray(d, float), 0)
        return self.s_max * (1 - np.exp(-d / self.s_grow)) * np.exp(-self.mu_s * d)

    def scatter_fraction(self, side):
        """Fraction of the (normalised) scatter kernel inside a square field of the given side (mm), on axis."""
        r_eq = side * 0.5642                                 # circle of equal area
        return 1 - (1 + r_eq / self.lam) * np.exp(-r_eq / self.lam)   # 2D exponential kernel, radial integral

    def pdd_model(self, side, depths=DEPTHS, ssd=1000.0):
        """PDD of an open square field (side at the surface) in water from the model, normalised to the maximum."""
        d = np.asarray(depths, float)
        side_d = side * (ssd + d) / ssd                      # divergence
        dose = (self.P(d) + self.S(d) * self.scatter_fraction(side_d)) * ((ssd + self.dmax) / (ssd + d)) ** 2
        return 100 * dose / dose.max()

    def sc(self, side):
        fs = sorted(self.head_scatter)
        return float(np.interp(side, fs, [self.head_scatter[f] for f in fs]))

    def fit(self):
        """Fit the model parameters to the PDD data (all field sizes) and output factors."""
        sizes = sorted(self.pdd)

        def res(q):
            m = copy.copy(self)
            m.mu_p, m.surf, m.bu, m.s_max, m.s_grow, m.mu_s, m.lam = q
            r = []
            for s in sizes:
                r.extend((m.pdd_model(s) - np.asarray(self.pdd[s])) / 2.0)
            # phantom scatter part of the output factors: Sp = Scp / Sc, relative to 10 x 10 at dmax
            ref = m.P(m.dmax) + m.S(m.dmax) * m.scatter_fraction(100)
            for s, of in self.output.items():
                sp = of / self.sc(s)
                r.append(((m.P(m.dmax) + m.S(m.dmax) * m.scatter_fraction(s)) / ref - sp) * 50)
            return np.asarray(r)
        q0 = [self.mu_p, self.surf, self.bu, self.s_max, self.s_grow, self.mu_s, self.lam]
        lo = [0.001, 0.1, 1.0, 0.0, 5.0, 0.0, 5.0]; hi = [0.02, 0.95, 15.0, 1.0, 300.0, 0.02, 120.0]
        out = least_squares(res, q0, bounds=(lo, hi))
        self.mu_p, self.surf, self.bu, self.s_max, self.s_grow, self.mu_s, self.lam = out.x
        self.fit_rms = float(np.sqrt(np.mean((res(out.x)[:len(sizes) * len(DEPTHS)] * 2.0) ** 2)))
        return self.fit_rms

    def mu_per_gy_note(self):
        return f"{self.calibration:.3f} cGy/MU at dmax ({self.dmax:.0f} mm), 10 × 10 cm, SSD 100 cm"


def _pdd_generic(dmax, mu_eff, surf, side_gain):
    """Generic PDD table (% at DEPTHS) for a few field sizes, from a smooth analytic shape."""
    out = {}
    for side in (50, 100, 200, 300):
        d = DEPTHS
        bu = 1 - (1 - surf - 0.05 * (side - 100) / 100) * np.exp(-d / (dmax / 3.2))
        att = np.exp(-(mu_eff - side_gain * np.log(side / 100.0)) * np.maximum(d - dmax, 0))
        isq = ((1000 + dmax) / (1000 + d)) ** 2
        v = bu * att * isq
        out[side] = list(np.round(100 * v / v.max(), 1))
    return out


def default_models():
    m6 = BeamModel("6X", _pdd_generic(15, 0.0032, 0.45, 0.0008),
                   {30: 0.86, 50: 0.92, 100: 1.0, 150: 1.04, 200: 1.065, 300: 1.09, 400: 1.10},
                   {30: 0.93, 50: 0.955, 100: 1.0, 150: 1.02, 200: 1.035, 300: 1.05, 400: 1.06}, dmax=15.0, sigma=3.5)
    m10 = BeamModel("10X", _pdd_generic(23, 0.0026, 0.33, 0.0005),
                    {30: 0.87, 50: 0.93, 100: 1.0, 150: 1.035, 200: 1.055, 300: 1.075, 400: 1.085},
                    {30: 0.935, 50: 0.96, 100: 1.0, 150: 1.018, 200: 1.03, 300: 1.045, 400: 1.05}, dmax=23.0, sigma=4.2,
                    wedge_factors={15: 0.81, 30: 0.69, 45: 0.57, 60: 0.46})
    for m in (m6, m10):
        m.fit()
    return {"6X": m6, "10X": m10}
