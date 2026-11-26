#!/usr/bin/env python3
"""Build the demonstration (literature-based) results of the VMAT-TBI thesis.

Every number written into the demo thesis comes from this script.  The inputs
are the values reported by the studies cited in the thesis
(``literature_values.csv``, with the thesis reference number of each study);
the script averages them, distributes them over the geometry of the planned
phantom study and writes

    demo/demo_values.json   all numbers used in Chapters 4-6 and the Abstract
    demo/figures/*.png      Figures 4.1-4.9 (demonstration data)

The results are NOT measurements.  They show what the study is expected to
find if it behaves like the published VMAT-TBI studies, so that the supervisors
can judge the expected outcome before the measurements are made.

Run from the repository root:   python demo/build_demo.py
Needs: numpy, scipy, matplotlib.
"""

import csv
import json
from pathlib import Path

import numpy as np
from scipy import ndimage, optimize, stats
from scipy.interpolate import PchipInterpolator

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Ellipse, Rectangle  # noqa: E402

HERE = Path(__file__).resolve().parent
FIG = HERE / "figures"
FIG.mkdir(exist_ok=True)
RNG = np.random.default_rng(20251126)

# Colours: fixed categorical order (validated palette), text in neutral inks.
C1, C2, C3, C4 = "#257de0", "#f47230", "#00b894", "#f2a600"
INK, INK2, GRID = "#191919", "#666666", "#e6e6e6"
FAIL = "#dc3c3d"
plt.rcParams.update({
    "font.family": "DejaVu Serif", "font.size": 10, "axes.edgecolor": INK2,
    "axes.labelcolor": INK, "xtick.color": INK2, "ytick.color": INK2,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
    "grid.color": GRID, "grid.linewidth": 0.6, "lines.linewidth": 2,
    "legend.frameon": False, "savefig.dpi": 200, "savefig.bbox": "tight",
})

PRESCRIPTION = 12.0       # Gy in 6 fractions, normalised to the PTV mean dose
FRACTION = 2.0


def r(x, n=1):
    return float(round(float(x), n))


# ---------------------------------------------------------------------------
# 1. Literature values
# ---------------------------------------------------------------------------
def load_literature():
    rows = list(csv.DictReader(open(HERE / "literature_values.csv", encoding="utf-8")))
    lit = {}
    for row in rows:
        try:
            v = float(row["value"])
        except ValueError:
            continue
        lit.setdefault(row["quantity"], []).append((row["study"], int(row["thesis_ref"]), v))
    return lit


def mean_of(lit, key):
    vals = [v for _, _, v in lit[key]]
    return float(np.mean(vals)), sorted({ref for _, ref, _ in lit[key]})


# Curto (thesis ref 13), Appendix Table A2: mean (of two measurements) percentage
# difference TLD - Monaco per location, and Table A1 Monaco dose (mean of two
# plans, Gy per fraction).  Used for the spatial pattern of the point doses.
CURTO = {
    4: {"C": (-0.8, 2.006), "A-DX": (-0.5, 2.069), "A-SX": (-1.2, 2.032), "P-DX": (1.3, 2.004), "P-SX": (-1.1, 2.017)},
    5: {"C": (1.4, 2.060), "A-DX": (-1.0, 2.041), "A-SX": (0.3, 2.057), "P-DX": (-3.4, 2.012), "P-SX": (0.5, 1.994)},
    8: {"A": (4.3, 2.039), "P": (1.1, 2.004), "DX": (2.8, 1.981), "SX": (1.0, 2.026), "C": (0.5, 1.993)},
    9: {"A": (4.4, 2.046), "SX": (2.3, 2.027), "P-DX": (0.8, 2.044), "A-SX": (1.6, 2.041)},
    12: {"C": (-4.3, 1.983), "A-DX": (-1.0, 2.049), "A-SX": (-4.5, 2.027), "P-DX LUNG": (-5.5, 1.281), "P-SX LUNG": (-5.5, 1.334)},
    13: {"C": (-0.3, 1.989), "DX LUNG": (7.9, 1.466), "SX LUNG": (-0.1, 1.099), "A": (3.5, 2.027), "P": (-1.6, 2.100)},
    16: {"C": (2.2, 2.001), "A-DX LUNG": (3.7, 1.801), "A-SX": (1.9, 2.023), "P-DX LUNG": (-2.5, 1.025), "P-SX LUNG": (1.1, 1.006)},
    17: {"A": (0.4, 2.045), "P": (-0.4, 2.091), "DX LUNG": (3.3, 0.916), "SX LUNG": (0.5, 1.375)},
    20: {"A": (0.0, 2.025), "P-DX": (-1.1, 2.025), "P-SX": (-1.1, 2.062)},
    21: {"A-DX": (-0.9, 2.018), "P": (1.1, 2.032), "A-SX": (0.0, 2.072)},
    24: {"C": (-1.7, 2.029), "P-SX": (-1.3, 2.026), "A": (1.3, 2.050), "P-DX": (-2.4, 2.040)},
    25: {"P": (-0.4, 2.055), "C": (-4.7, 2.061), "A-SX": (0.8, 2.045), "A-DX": (-1.4, 2.043)},
    29: {"C": (-4.4, 2.038), "P-DX": (-1.7, 2.048), "P-SX": (-2.8, 2.005), "A-DX": (-3.2, 2.040), "A-SX": (-3.3, 2.005)},
}

# Film levels of the planned study (Rando slices 0-35, 2.5 cm each; z = cm from vertex)
LEVELS = [
    # name, slices, z, type, Curto slices used for the pattern, evaluation points
    ("Head", "5/6", 15.0, "iso", [4, 5], ["C", "L", "R", "A", "P"]),
    ("Neck", "8/9", 22.5, "iso", [8, 9], ["C", "L", "R"]),
    ("Junction A–B", "11/12", 30.0, "junction", [12], ["C", "L", "R"]),
    ("Upper thorax", "13/14", 35.0, "iso", [13], ["C", "RL", "LL", "CWR", "CWL"]),
    ("Mid-thorax", "16/17", 42.5, "iso", [16, 17], ["C", "RL", "LL", "CWR", "CWL"]),
    ("Lower thorax", "19/20", 50.0, "iso", [20], ["C", "RL", "LL"]),
    ("Junction B–C", "21/22", 55.0, "junction", [21], ["C", "L", "R"]),
    ("Umbilicus (reference)", "26/27", 67.5, "iso", [24, 25], ["C", "L", "R", "A", "P"]),
    ("Pelvis", "30/31", 77.5, "iso", [29], ["C", "L", "R"]),
]
ISO = {"A": 15.5, "B": 42.5, "C": 72.0}
FIELDS = {"A": (0.0, 31.0), "B": (29.0, 56.0), "C": (54.0, 90.0)}
JUNCTIONS = {"A–B": 30.0, "B–C": 55.0}


# ---------------------------------------------------------------------------
# 2. Synthetic phantom and dose model (for the figures and plane values)
# ---------------------------------------------------------------------------
DX = 0.25                      # cm
xs = np.arange(-20, 20 + DX, DX)          # lateral (patient left = +x)
ys = np.arange(-14, 14 + DX, DX)          # AP (anterior = -y)
zs = np.arange(0, 90 + DX, DX)            # longitudinal


def half_axes(z):
    """Lateral and AP half-axes (cm) of the Rando outline at height z."""
    zp = [0, 3, 11, 19, 22, 24, 27, 30, 40, 52, 56, 66, 72, 82, 90]
    ax = [2, 6.5, 7.8, 6.8, 5.6, 5.5, 8.5, 15.0, 16.0, 15.5, 14.5, 14.8, 16.2, 16.6, 16.0]
    ay = [2, 7.5, 9.5, 8.5, 5.8, 5.6, 7.0, 9.5, 10.8, 11.0, 10.4, 10.6, 10.8, 11.0, 10.5]
    return np.interp(z, zp, ax), np.interp(z, zp, ay)


def lung_masks(z, X, Y):
    """Right and left lung masks in an axial plane at height z."""
    out = []
    zc, hz = 41.0, 12.0
    t = (z - zc) / hz
    if abs(t) >= 1:
        return [np.zeros_like(X, bool)] * 2
    s = np.sqrt(1 - t ** 2)
    for side in (-1, 1):
        cx = side * 7.0
        a, b = 5.6 * s, 6.8 * s
        out.append(((X - cx) / a) ** 2 + ((Y - 0.8) / b) ** 2 <= 1)
    return out


def distance_inside(mask):
    return ndimage.distance_transform_edt(mask) * DX


def junction_ripple(z, amp):
    out = np.zeros_like(np.asarray(z, float))
    for (name, zj), a in zip(JUNCTIONS.items(), amp):
        out = out + a * np.exp(-0.5 * ((np.asarray(z) - zj) / 1.2) ** 2)
    return out


def axial_dose(z, lung_core=0.50, ripple=(-0.012, -0.010)):
    """Course dose (Gy) in an axial plane: uniform body dose, build-up rim,
    lung sparing (core receives lung_core x prescription), small junction ripple."""
    X, Y = np.meshgrid(xs, ys)
    a, b = half_axes(z)
    body = (X / a) ** 2 + (Y / b) ** 2 <= 1
    d = np.zeros_like(X)
    if not body.any():
        return d, body, [np.zeros_like(body)] * 2
    depth = distance_inside(body)
    base = PRESCRIPTION * (1 + junction_ripple(z, ripple))
    # slight heterogeneity: higher at the neck and thin regions, lower at the edges
    d[body] = base * (1 + 0.012 * np.cos(X[body] / 6.0) - 0.006)
    rim = np.clip(depth / 0.6, 0, 1)
    d = d * np.where(body, 0.86 + 0.14 * rim, 0)
    lungs = lung_masks(z, X, Y)
    for lm in lungs:
        if lm.any():
            dl = distance_inside(lm)
            f = lung_core + (1 - lung_core) * np.exp(-dl / 1.6)
            d[lm] = d[lm] * f[lm]
    # scatter tail outside the body
    out = ~body
    dist_out = ndimage.distance_transform_edt(out) * DX
    d[out] = PRESCRIPTION * 0.35 * np.exp(-dist_out[out] / 1.5)
    d = ndimage.gaussian_filter(d, 0.8)
    return d, body, lungs


def calibrate_lung_model(target_mean):
    """Find the lung-core factor that gives the target whole-lung mean dose."""
    zl = np.arange(29.5, 53.0, 0.5)

    def lung_mean(core):
        tot, n = 0.0, 0
        for z in zl:
            d, _, lungs = axial_dose(z, lung_core=core)
            m = lungs[0] | lungs[1]
            tot += d[m].sum(); n += m.sum()
        return tot / n
    core = optimize.brentq(lambda c: lung_mean(c) - target_mean, 0.2, 0.95, xtol=1e-3)
    return core


# ---------------------------------------------------------------------------
# 3. Gamma index (global, 2D)
# ---------------------------------------------------------------------------
def gamma_2d(ref, ev, spacing, dd=0.03, dta=0.3, threshold=0.10, search=0.6):
    """Global 2D gamma of evaluated vs reference (both on the same grid)."""
    dmax = ref.max()
    n = int(np.ceil(search / spacing))
    best = np.full(ref.shape, np.inf)
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            dist2 = ((i * spacing) ** 2 + (j * spacing) ** 2) / dta ** 2
            if dist2 > (search / dta) ** 2:
                continue
            sh = np.roll(np.roll(ev, i, 0), j, 1)
            g2 = ((sh - ref) / (dd * dmax)) ** 2 + dist2
            best = np.minimum(best, g2)
    g = np.sqrt(best)
    mask = ref >= threshold * dmax
    return g, mask, float((g[mask] <= 1).mean() * 100)


# ---------------------------------------------------------------------------
# 4. Results
# ---------------------------------------------------------------------------
def plan_results(lit, V):
    mu = {k: mean_of(lit, f"plan_MU_{k}")[0] for k in ("head", "chest", "abdomen", "pelvis")}
    rate = {k: mean_of(lit, f"dose_rate_{k}")[0] for k in ("head", "chest", "abdomen", "pelvis")}
    total_mu = sum(mu.values())
    # Curto's four fields (25 cm long, isocentres 21 cm apart) mapped onto our
    # three fields: MU per cm of each Curto field, integrated over our field.
    curto_fields = {"head": (0, 25), "chest": (21, 46), "abdomen": (42, 67), "pelvis": (63, 88)}
    z = np.linspace(0, 90, 9001)
    dens = np.zeros_like(z); drate_num = np.zeros_like(z)
    for k, (a, b) in curto_fields.items():
        inside = (z >= a) & (z <= b)
        dens += inside * mu[k] / (b - a)
        drate_num += inside * mu[k] / (b - a) * rate[k]
    share, rate_ours = {}, {}
    # each overlap is shared half/half between the two adjacent fields
    edges = {"A": (0, 30), "B": (30, 55), "C": (55, 90)}
    for f, (a, b) in edges.items():
        m = (z >= a) & (z < b)
        share[f] = np.trapezoid(dens[m], z[m])
        rate_ours[f] = np.trapezoid(drate_num[m], z[m]) / share[f]
    scale = total_mu / sum(share.values())
    plan = {}
    for f in "ABC":
        m = share[f] * scale
        dr = min(rate_ours[f], 250.0)
        plan[f] = {"MU": int(round(m)), "dose_rate": int(round(dr)), "beam_on": r(m / dr, 1)}
    plan["total"] = {"MU": int(sum(plan[f]["MU"] for f in "ABC")),
                     "beam_on": r(sum(m / min(rate_ours[f], 250) for f, m in
                                      ((f, share[f] * scale) for f in "ABC")), 1)}
    V["plan"] = plan
    V["planning_time_h"] = r(mean_of(lit, "planning_time")[0], 1)
    V["iso_distance"] = {"A–B": r(ISO["B"] - ISO["A"]), "B–C": r(ISO["C"] - ISO["B"])}
    return plan


def dvh_results(lit, V):
    v90 = mean_of(lit, "V90_PTV")[0]
    v95 = mean_of(lit, "V95_PTV")[0]
    d98 = mean_of(lit, "D98_rel")[0] * PRESCRIPTION
    d2 = mean_of(lit, "D2_rel")[0] * PRESCRIPTION
    dmax_rel = float(np.mean([mean_of(lit, "Dmax_rel")[0]]))
    lung = mean_of(lit, "lung_mean")[0]
    v12 = mean_of(lit, "lung_V12")[0]

    # PTV quantile function through the literature points, D50 tuned so that
    # the mean equals the prescription (plan normalised to mean PTV dose).
    def ptv_q(d50):
        p = [0, 1 - v90 / 100, 0.02, 1 - v95 / 100, 0.5, 0.98, 0.999]
        q = [9.2, 0.9 * PRESCRIPTION, d98, 0.95 * PRESCRIPTION, d50, d2, 13.6]
        order = np.argsort(p)
        return PchipInterpolator(np.array(p)[order], np.array(q)[order])
    u = np.linspace(0, 0.999, 20000)
    d50 = optimize.brentq(lambda x: ptv_q(x)(u).mean() - PRESCRIPTION, 11.6, 12.4)
    ptv = ptv_q(d50)(u)

    def lung_q(mid):
        p = [0, 0.1, 0.3, 0.5, 0.7, 0.9, 1 - v12 / 100, 0.999]
        q = [4.6, 5.8, 7.0, mid, mid + 1.7, 11.3, 12.0, 13.0]
        return PchipInterpolator(p, q)
    mid = optimize.brentq(lambda x: lung_q(x)(u).mean() - lung, 7.0, 10.0)
    lungd = lung_q(mid)(u)
    rl = lungd * 0.9955; ll = lungd * 1.0045       # Curto right/left ratio

    hi = (d2 - d98) / d50
    V["dvh"] = {
        "PTV_V90": r(v90), "PTV_V95": r(v95), "PTV_D98": r(d98), "PTV_D50": r(d50),
        "PTV_D2": r(d2), "PTV_Dmean": r(ptv.mean()), "HI": r(hi, 2),
        "body_Dmax": r(dmax_rel * PRESCRIPTION),
        "lung_mean": r(lung), "lung_R_mean": r(rl.mean()), "lung_L_mean": r(ll.mean()),
        "lung_V8": r((lungd >= 8).mean() * 100, 0), "lung_V10": r((lungd >= 10).mean() * 100, 0),
        "lung_V12": r(v12), "lung_V12_check": r((lungd >= 12).mean() * 100),
        "lung_refs": mean_of(lit, "lung_mean")[1], "lung_n": len(lit["lung_mean"]),
        "D2_rel": r(d2 / PRESCRIPTION * 100), "D98_rel": r(d98 / PRESCRIPTION * 100),
        "Dmax_rel": r(dmax_rel * 100),
    }

    # Figure 4.2: DVHs
    fig, ax = plt.subplots(figsize=(6.4, 4.0))
    grid = np.linspace(0, 15, 601)

    def cum(d):
        return [(d >= g).mean() * 100 for g in grid]
    ax.plot(grid, cum(ptv), color=C1, label="PTV")
    ax.plot(grid, cum(rl), color=C2, label="Right lung")
    ax.plot(grid, cum(ll), color=C3, label="Left lung", linestyle=(0, (4, 2)))
    ax.plot(grid, cum(lungd), color=C4, label="Total lung", linestyle=(0, (1, 1.5)))
    ax.axvline(10.8, color=INK2, lw=0.8, ls="--")
    ax.text(10.75, 4, "90% of\nprescription", ha="right", va="bottom", fontsize=8, color=INK2)
    ax.set_xlabel("Dose (Gy)"); ax.set_ylabel("Volume (%)")
    ax.set_xlim(0, 15); ax.set_ylim(0, 102)
    ax.legend(loc="lower left")
    ax.set_title("Demo DVH, 12 Gy in 6 fractions (literature-mean values)", fontsize=10, color=INK2)
    fig.savefig(FIG / "fig4_2_dvh.png"); plt.close(fig)
    return ptv, lungd


def dose_figures(V, core):
    """Figure 4.1: coronal and axial dose distributions of the demo plan."""
    # coronal plane through y = 0.8 (centre of the lungs)
    X = xs
    cor = np.zeros((len(zs), len(xs)))
    yi = np.argmin(abs(ys - 0.8))
    for k, z in enumerate(zs[::2]):
        d, _, _ = axial_dose(z, lung_core=core)
        cor[2 * k] = d[yi]
        if 2 * k + 1 < len(zs):
            cor[2 * k + 1] = d[yi]
    fig = plt.figure(figsize=(7.2, 6.2))
    ax = fig.add_axes([0.04, 0.06, 0.40, 0.88])
    im = ax.imshow(cor, extent=[X[0], X[-1], zs[-1], zs[0]], cmap="inferno", vmin=0, vmax=13.2,
                   aspect="equal", interpolation="bilinear")
    for k, (f, (a, b)) in enumerate(FIELDS.items()):
        ax.add_patch(Rectangle((-19.5 + k * 0.3, a), 39 - k * 0.6, b - a, fill=False,
                               ec=[C1, "#ffffff", C1][k], lw=1.0, ls=["-", "--", "-"][k]))
        ax.plot(0, ISO[f], marker="x", color="#ffffff", ms=8, mew=2)
        ax.text(17.5, ISO[f], f, color="#ffffff", fontsize=10, va="center", ha="right")
    for zj in JUNCTIONS.values():
        ax.axhline(zj, color="#9dc8f7", lw=0.6, ls=":")
    ax.set_xlabel("Lateral (cm)"); ax.set_ylabel("Distance from vertex (cm)")
    ax.set_title("Coronal plane", fontsize=10); ax.grid(False)
    for spec, zz in ((0, 42.5), (1, 67.5)):
        a2 = fig.add_axes([0.52, 0.55 - spec * 0.47, 0.40, 0.38])
        d, body, lungs = axial_dose(zz, lung_core=core)
        a2.imshow(d, extent=[xs[0], xs[-1], ys[-1], ys[0]], cmap="inferno", vmin=0, vmax=13.2,
                  interpolation="bilinear")
        for lm in lungs:
            if lm.any():
                a2.contour(xs, ys, lm.astype(float), [0.5], colors="#9dc8f7", linewidths=0.8)
        a2.set_title(f"Axial, z = {zz:g} cm ({'mid-thorax' if spec == 0 else 'umbilicus'})", fontsize=10)
        a2.grid(False); a2.set_xlabel("Lateral (cm)")
    cax = fig.add_axes([0.94, 0.08, 0.018, 0.84])
    cb = fig.colorbar(im, cax=cax); cb.set_label("Dose per course (Gy)")
    fig.savefig(FIG / "fig4_1_dose_distribution.png"); plt.close(fig)


def octavius_results(lit, V):
    s33 = [v for _, _, v in lit["gamma_single_3_3"]]
    single33 = float(np.mean(s33))
    single32 = mean_of(lit, "gamma_single_3_2")[0]
    # junctions: pooled individual measurements (Curto 6 after correction, Uehara 5)
    curto_j = [97.1, 99.2, 94.2, 91.0, 90.8, 93.5]
    uehara_j33 = [97.9, 93.3, 97.8, 98.2, 98.6]
    uehara_j32 = [94.8, 92.9, 96.0, 96.2, 98.3]
    j33 = float(np.mean(curto_j + uehara_j33))
    ratio = np.mean(uehara_j32) / np.mean(uehara_j33)
    j32 = j33 * ratio
    spread_s33 = {"A": +0.2, "B": -0.3, "C": +0.1}
    spread_s32 = {"A": +0.3, "B": -0.5, "C": +0.2}
    g = {}
    for f in "ABC":
        g[f"Isocentre {f}"] = (r(single33 + spread_s33[f]), r(single32 + spread_s32[f]))
    g["Junction A–B"] = (r(j33 + 0.3), r(j32 + 0.3))
    g["Junction B–C"] = (r(j33 - 0.3), r(j32 - 0.3))
    V["gamma"] = {k: {"g33": a, "g32": b} for k, (a, b) in g.items()}
    V["gamma_means"] = {"single33": r(single33), "single32": r(single32), "junction33": r(j33),
                        "junction32": r(j32), "n_junction": len(curto_j) + len(uehara_j33)}

    # Figure 4.3: illustrative planes (array plane 27 x 27 cm, 2.5 mm grid)
    sp = 0.25
    x = np.arange(-13.5, 13.5 + sp, sp)
    Xg, Zg = np.meshgrid(x, x)

    def arc_plane(zc, length):
        prof_z = 0.5 * (1 + np.tanh((length / 2 - abs(Zg - zc)) / 0.45))
        prof_x = 0.5 * (1 + np.tanh((12 - abs(Xg)) / 0.5))
        mod = 1 + 0.05 * np.sin(Xg / 2.3) * np.cos(Zg / 3.1) + 0.03 * np.cos(Xg / 1.4 + Zg / 4)
        return 2.0 * prof_z * prof_x * mod

    def measured(calc, shift_mm, noise, seed):
        rng = np.random.default_rng(seed)
        m = ndimage.shift(calc, (shift_mm / 10 / sp, 0), order=1, mode="nearest")
        return m * (1 + rng.normal(0, noise, m.shape))

    iso_calc = arc_plane(0, 40)
    cases = {}
    target = {"iso": g["Isocentre B"][0], "jun": g["Junction A–B"][0]}
    # junction: two arc pairs whose feathered edges meet at z = 0 (2 cm overlap)
    f1, f2 = arc_plane(-14, 28.0), arc_plane(14, 28.0)
    calc_j = f1 + f2

    def measured_j(noise, seed, s_mm=1.0):
        rng = np.random.default_rng(seed)
        m1 = ndimage.shift(f1, (s_mm / 10 / sp, 0), order=1, mode="nearest")
        m2 = ndimage.shift(f2, (-s_mm / 10 / sp, 0), order=1, mode="nearest")
        m = m1 + m2
        return m * (1 + rng.normal(0, noise, m.shape))
    for key, calc in (("iso", iso_calc), ("jun", calc_j)):
        best = None
        for noise in np.linspace(0.002, 0.03, 57):
            meas = measured(calc, 0.5, noise, 7) if key == "iso" else measured_j(noise, 7)
            gm, mask, pr = gamma_2d(calc, meas, sp)
            if best is None or abs(pr - target[key]) < abs(best[0] - target[key]):
                best = (pr, meas, gm, mask)
        cases[key] = (calc,) + best[1:] + (best[0],)
    fig, axs = plt.subplots(2, 3, figsize=(9.0, 6.4), constrained_layout=True)
    for row, (key, title) in enumerate((("iso", "Isocentre B"), ("jun", "Junction A–B"))):
        calc, meas, gm, mask, pr = cases[key]
        for col, (img, lab) in enumerate(((calc, "Calculated (TPS)"), (meas, "Measured (array)"))):
            im = axs[row, col].imshow(img, extent=[x[0], x[-1], x[-1], x[0]], cmap="inferno",
                                      vmin=0, vmax=2.3)
            axs[row, col].set_title(lab, fontsize=9)
        gshow = np.where(mask, gm, np.nan)
        cmap = matplotlib.colors.ListedColormap(["#b6d5f8", "#6aabf1", FAIL])
        norm = matplotlib.colors.BoundaryNorm([0, 0.5, 1.0, 10], 3)
        axs[row, 2].imshow(gshow, extent=[x[0], x[-1], x[-1], x[0]], cmap=cmap, norm=norm)
        axs[row, 2].set_title(f"γ map 3%/3 mm: {pr:.1f}% pass", fontsize=9)
        for a in axs[row]:
            a.grid(False); a.set_xlabel("Lateral (cm)", fontsize=8); a.tick_params(labelsize=7)
        axs[row, 0].set_ylabel(f"{title}\nlongitudinal (cm)", fontsize=9)
    cb = fig.colorbar(im, ax=axs[:, 1], shrink=0.7); cb.set_label("Dose (Gy)")
    handles = [Rectangle((0, 0), 1, 1, color=c) for c in ("#b6d5f8", "#6aabf1", FAIL)]
    fig.legend(handles, ["γ ≤ 0.5", "0.5 < γ ≤ 1", "γ > 1 (fail)"], loc="lower right",
               ncol=3, fontsize=8, bbox_to_anchor=(1.0, -0.04))
    fig.savefig(FIG / "fig4_3_octavius_gamma.png"); plt.close(fig)


def calibration_results(V):
    """Simulated EBT3 calibration (red, green, blue) with the typical response."""
    doses = np.arange(0, 251, 25) / 100.0          # Gy
    true = {"red": (6.9, 42.0, 2.70), "green": (10.6, 70.0, 2.45), "blue": (26.0, 400.0, 2.6)}

    def dose_of(netod, a, b, n):
        return a * netod + b * np.power(np.clip(netod, 0, None), n)

    def netod_of(D, p):
        return np.array([optimize.brentq(lambda x: dose_of(x, *p) - d, 0, 2) if d > 0 else 0.0 for d in D])
    data = {}
    for ch, p in true.items():
        nod = netod_of(doses, p)
        reps = np.array([nod * (1 + RNG.normal(0, 0.009, nod.shape)) + RNG.normal(0, 0.0012, nod.shape)
                         for _ in range(3)])
        reps[:, 0] = np.abs(RNG.normal(0, 0.0008, 3))
        data[ch] = reps
    fits = {}
    for ch, reps in data.items():
        xx = reps.flatten(); yy = np.tile(doses, 3)
        popt, _ = optimize.curve_fit(dose_of, xx, yy, p0=true[ch], maxfev=20000)
        pred = dose_of(xx, *popt)
        ss = ((yy - pred) ** 2).sum(); st = ((yy - yy.mean()) ** 2).sum()
        fits[ch] = (popt, 1 - ss / st)
    a, b, n = fits["red"][0]
    mean_nod = data["red"].mean(0)
    pred = dose_of(mean_nod, a, b, n)
    resid = (pred[1:] - doses[1:]) / doses[1:] * 100
    rep_sd = (dose_of(data["red"], a, b, n).std(0, ddof=1)[1:] / doses[1:] * 100)
    ver_nod = netod_of(np.array([1.6]), true["red"])[0] * (1 + 0.004)
    ver = dose_of(ver_nod, a, b, n)
    V["calibration"] = {
        "a": r(a, 2), "b": r(b, 1), "n": r(n, 2), "R2": r(fits["red"][1], 4),
        "max_resid_ge50": r(np.abs(resid[1:]).max(), 1), "resid_25": r(abs(resid[0]), 1),
        "max_sd_ge50": r(rep_sd[1:].max(), 1), "netod_200": r(mean_nod[8], 3),
        "netod_250": r(mean_nod[10], 3), "verification_160": r(ver * 100, 1),
        "verification_diff": r((ver - 1.6) / 1.6 * 100, 1),
        "R2_green": r(fits["green"][1], 4), "R2_blue": r(fits["blue"][1], 4),
    }
    fig, (ax, axr) = plt.subplots(2, 1, figsize=(6.2, 5.6), sharex=False,
                                  gridspec_kw={"height_ratios": [3, 1.2]})
    for ch, col in (("red", C2), ("green", C3), ("blue", C1)):
        reps = data[ch]; p = fits[ch][0]
        ax.errorbar(reps.mean(0), doses * 100, xerr=reps.std(0, ddof=1), fmt="o", ms=4.5,
                    color=col, capsize=2, label=f"{ch.capitalize()} channel")
        xx = np.linspace(0, reps.max() * 1.02, 200)
        ax.plot(xx, dose_of(xx, *p) * 100, color=col, lw=1.4)
    ax.set_xlabel("netOD"); ax.set_ylabel("Dose (cGy)")
    ax.legend(loc="lower right")
    ax.text(0.02, 0.95, f"Red: D = {a:.2f}·netOD + {b:.1f}·netOD^{n:.2f}  (Gy)",
            transform=ax.transAxes, va="top", fontsize=9, color=INK)
    axr.bar(doses[1:] * 100, resid, width=12, color=C2)
    axr.axhline(0, color=INK2, lw=0.8)
    for lim in (-2, 2):
        axr.axhline(lim, color=INK2, lw=0.6, ls="--")
    axr.set_xlabel("Dose (cGy)"); axr.set_ylabel("Residual (%)", fontsize=9)
    fig.tight_layout(); fig.savefig(FIG / "fig4_4_calibration.png"); plt.close(fig)


def point_results(lit, V, core):
    """Film vs TPS at the evaluation points (three demo repetitions)."""
    # mean absolute film-TPS difference expected in each region type
    curto_region_iso = np.mean([np.mean([1.8, 1.0]), np.mean([3.0, 4.0]), np.mean([1.2, 0.9]),
                                np.mean([4.2, 2.0])])
    bias_studies = [v for _, _, v in lit["pointdose_bias"]]
    m_iso = float(np.mean([curto_region_iso] + bias_studies))
    curto_region_jun = np.mean([np.mean([1.7, 3.1]), np.mean([2.4, 3.3]), np.mean([2.1, 1.7])])
    m_jun = float(np.mean([curto_region_jun, mean_of(lit, "junction_film_diff")[0]]))
    # signs and relative sizes from Curto's central (or nearest) points
    pattern = []
    for name, sl, z, typ, cs, pts in LEVELS:
        vals = [CURTO[s]["C"][0] if "C" in CURTO[s] else
                np.mean([v[0] for k, v in CURTO[s].items() if "LUNG" not in k]) for s in cs]
        tps = [CURTO[s]["C"][1] if "C" in CURTO[s] else
               np.mean([v[1] for k, v in CURTO[s].items() if "LUNG" not in k]) for s in cs]
        pattern.append((np.mean(vals), np.mean(tps)))
    iso_idx = [i for i, L in enumerate(LEVELS) if L[3] == "iso"]
    k_iso = m_iso / np.mean([abs(pattern[i][0]) for i in iso_idx])
    central = []
    for i, L in enumerate(LEVELS):
        s, tps = pattern[i]
        delta = s * k_iso if L[3] == "iso" else -m_jun * (1.0 if i == 2 else 1.05)
        central.append((r(tps, 2), delta))

    # three repetitions; repeatability CV from the two Curto measurements
    cv = {"iso": 0.008, "junction": 0.014}
    # three repetitions with mean = target and SD = CV x target (order shuffled)
    target = np.array([tps * (1 + d / 100) for tps, d in central])
    reps = np.zeros((3, len(LEVELS)))
    umb_i = [i for i, L in enumerate(LEVELS) if L[0].startswith("Umbilicus")][0]
    ref_perm = np.array([-1.0, 0.0, 1.0])
    for i, L in enumerate(LEVELS):
        perm = ref_perm if i == umb_i else RNG.permutation(ref_perm)
        while i != umb_i and np.array_equal(perm, ref_perm):
            perm = RNG.permutation(ref_perm)
        reps[:, i] = target[i] * (1 + cv[L[3]] * perm)
    rows = []
    umb = [i for i, L in enumerate(LEVELS) if L[0].startswith("Umbilicus")][0]
    homog = (reps - reps[:, [umb]]) / reps[:, [umb]] * 100
    for i, L in enumerate(LEVELS):
        film_m, film_sd = reps[:, i].mean(), reps[:, i].std(ddof=1)
        tps = central[i][0]
        rows.append({
            "level": L[0], "slices": L[1], "z": L[2], "type": L[3],
            "film": r(film_m, 2), "film_sd": r(film_sd, 2), "tps": tps,
            "delta": r((film_m - tps) / tps * 100, 1),
            "homog": r(homog[:, i].mean(), 1), "homog_sd": r(homog[:, i].std(ddof=1), 1),
        })
    V["points"] = rows
    deltas = np.array([(reps[:, i].mean() - central[i][0]) / central[i][0] * 100 for i in range(len(LEVELS))])
    t_p = stats.ttest_rel(reps.mean(0), [c[0] for c in central]).pvalue
    w_p = stats.wilcoxon(reps.mean(0) - np.array([c[0] for c in central])).pvalue
    sh_p = stats.shapiro(deltas).pvalue
    V["points_summary"] = {
        "m_iso": r(m_iso, 1), "m_jun": r(m_jun, 1),
        "mean_abs_iso": r(np.mean([abs(deltas[i]) for i in iso_idx]), 1),
        "mean_abs_jun": r(np.mean([abs(deltas[i]) for i in (2, 6)]), 1),
        "mean_abs_all": r(np.mean(abs(deltas)), 1), "mean_signed": r(deltas.mean(), 1),
        "film_min": r(reps.mean(0).min(), 2), "film_max": r(reps.mean(0).max(), 2),
        "paired_t_p": r(t_p, 2), "wilcoxon_p": r(w_p, 2), "shapiro_p": r(sh_p, 2),
        "homog_min": r(min(x["homog"] for x in rows), 1), "homog_max": r(max(x["homog"] for x in rows), 1),
        "cv_max": r(max(x["film_sd"] / x["film"] * 100 for x in rows), 1),
    }

    # Figure 4.6: homogeneity along the body
    fig, ax = plt.subplots(figsize=(7.4, 3.9))
    names = ["Head", "Neck", "Junction\nA–B", "Upper\nthorax", "Mid-\nthorax", "Lower\nthorax",
             "Junction\nB–C", "Umbilicus\n(ref.)", "Pelvis"]
    xpos = np.arange(len(LEVELS))
    ax.axhspan(-10, 10, color="#efefef", zorder=0)
    ax.axhspan(-5, 5, color="#e3e3e3", zorder=0)
    for rep, (col, mk) in enumerate(((C1, "o"), (C2, "s"), (C3, "^"))):
        ax.plot(xpos + (rep - 1) * 0.12, homog[rep], mk, color=col, ms=6, ls="none",
                label=f"Measurement {rep + 1}")
    ax.plot(xpos, homog.mean(0), "_", color=INK, ms=16, mew=2, label="Mean")
    ax.axhline(0, color=INK2, lw=0.8)
    ax.set_xticks(xpos); ax.set_xticklabels(names, fontsize=8, rotation=0)
    ax.set_ylabel("Dose relative to umbilicus (%)"); ax.set_ylim(-12, 12)
    ax.text(len(LEVELS) - 0.5, 10.3, "±10% tolerance", ha="right", fontsize=8, color=INK2)
    ax.text(len(LEVELS) - 0.5, 5.3, "±5%", ha="right", fontsize=8, color=INK2)
    ax.legend(ncol=4, loc="lower center", bbox_to_anchor=(0.5, 1.0), fontsize=8)
    ax.grid(axis="x", visible=False)
    fig.savefig(FIG / "fig4_6_homogeneity.png"); plt.close(fig)

    # all evaluation points: central from above, peripheral from Curto's locations
    all_pts = []
    for i, L in enumerate(LEVELS):
        lung_vals = [v for s in L[4] for k, v in CURTO[s].items() if "LUNG" in k]
        if not lung_vals:      # lung bases: Curto had no lung TLD there, use slice 17
            lung_vals = [v for k, v in CURTO[17].items() if "LUNG" in k]
        per_vals = [v for s in L[4] for k, v in CURTO[s].items() if "LUNG" not in k and k != "C"]
        li = pi = 0
        for p in L[5]:
            if p == "C":
                tps, d = central[i][0], deltas[i]; kind = "central"
            elif p in ("RL", "LL"):
                d, tps = lung_vals[li % len(lung_vals)]; li += 1; kind = "lung"
            else:
                d, tps = per_vals[pi % len(per_vals)]; pi += 1; kind = "peripheral"
            all_pts.append((L[0], p, kind, tps, d))
    diffs = np.array([p[4] for p in all_pts])
    means = np.array([p[3] * (1 + p[4] / 200) for p in all_pts])
    low_grad = np.array([p[2] != "lung" and not LEVELS[[L[0] for L in LEVELS].index(p[0])][3] == "junction"
                         for p in all_pts])
    md, sd = diffs.mean(), diffs.std(ddof=1)
    V["agreement"] = {
        "n_points": len(all_pts), "mean_diff": r(md, 1), "sd": r(sd, 1),
        "loa_low": r(md - 1.96 * sd, 1), "loa_high": r(md + 1.96 * sd, 1),
        "pct_within3_lowgrad": r((abs(diffs[low_grad]) <= 3).mean() * 100, 0),
        "n_lowgrad": int(low_grad.sum()),
        "pct_over5": r((abs(diffs) > 5).mean() * 100, 0), "n_over5": int((abs(diffs) > 5).sum()),
        "max_abs": r(abs(diffs).max(), 1),
        "paired_all_p": r(stats.wilcoxon(diffs).pvalue, 2),
    }
    # Figure 4.9: Bland-Altman
    fig, ax = plt.subplots(figsize=(6.2, 4.0))
    for kind, col, mk, lab in (("central", C1, "o", "Central points"),
                               ("peripheral", C2, "s", "Peripheral points"),
                               ("lung", C3, "^", "Lung points")):
        m = np.array([p[2] == kind for p in all_pts])
        ax.plot(means[m], diffs[m], mk, color=col, ms=6, ls="none", label=lab)
    ax.axhline(md, color=INK, lw=1.2)
    for lim in (md - 1.96 * sd, md + 1.96 * sd):
        ax.axhline(lim, color=INK2, lw=1, ls="--")
    ax.text(1.62, md + 0.3, f"mean {md:+.1f}%", fontsize=8)
    ax.text(1.62, md + 1.96 * sd + 0.3, f"+1.96 SD = {md + 1.96 * sd:+.1f}%", fontsize=8)
    ax.text(1.62, md - 1.96 * sd + 0.3, f"−1.96 SD = {md - 1.96 * sd:+.1f}%", fontsize=8)
    ax.set_xlabel("Mean of film and TPS dose (Gy per fraction)")
    ax.set_ylabel("Film − TPS (% of TPS)")
    ax.set_xlim(0.8, 2.25)
    ax.legend(loc="upper left", fontsize=8)
    fig.savefig(FIG / "fig4_9_bland_altman.png"); plt.close(fig)
    return central, reps


def lung_results(lit, V, core):
    """Lung dose per film plane from the dose model; film = TPS x literature ratio."""
    ratio = mean_of(lit, "lung_film_tps")[0]
    planes = [L for L in LEVELS if L[0] in ("Upper thorax", "Mid-thorax", "Lower thorax")]
    rows, areas = [], []
    for L in planes:
        d, body, lungs = axial_dose(L[2], lung_core=core)
        m = lungs[0] | lungs[1]
        tps_course = d[m].mean()
        areas.append(m.sum() * DX * DX)
        rows.append([L[0], tps_course])
    areas = np.array(areas)
    film_reps = np.zeros((3, len(rows)))
    for j, (_, tc) in enumerate(rows):
        film_reps[:, j] = tc * (1 + ratio / 100) * (1 + 0.010 * RNG.permutation([-1.0, 0.0, 1.0]))
    out = []
    for j, (name, tc) in enumerate(rows):
        fm = film_reps[:, j].mean() / 6; fsd = film_reps[:, j].std(ddof=1) / 6
        out.append({"plane": name, "film_fx": r(fm, 2), "film_fx_sd": r(fsd, 2),
                    "film_course": r(fm * 6, 1), "tps_course": r(tc, 1),
                    "delta": r((fm * 6 - tc) / tc * 100, 1), "area_cm2": r(areas[j], 0)})
    w = areas / areas.sum()
    wf = (film_reps * w).sum(1)                         # weighted course dose per repetition
    wt = sum(w[j] * rows[j][1] for j in range(len(rows)))
    t12 = stats.ttest_1samp(wf, 12.0)
    t10 = stats.ttest_1samp(wf, 10.0, alternative="less")
    # central and peripheral lung dose in the mid-thorax plane (per fraction)
    d, body, lungs = axial_dose(42.5, lung_core=core)
    cen, per = [], []
    for lm in lungs:
        dl = distance_inside(lm)
        cen.append(d[lm & (dl > 3.0)].mean()); per.append(d[lm & (dl < 0.75)].mean())
    V["lung"] = {
        "planes": out, "weighted_film_course": r(wf.mean(), 1), "weighted_film_sd": r(wf.std(ddof=1), 2),
        "weighted_film_fx": r(wf.mean() / 6, 2), "weighted_tps_course": r(wt, 1),
        "weighted_delta": r((wf.mean() - wt) / wt * 100, 1), "film_tps_ratio_lit": r(ratio, 2),
        "p_vs_12": float(f"{t12.pvalue:.1e}"), "p_vs_10": float(f"{t10.pvalue:.1e}"),
        "central_fx": r(np.mean(cen) / 6 * (1 + ratio / 100), 2),
        "periphery_fx": r(np.mean(per) / 6 * (1 + ratio / 100), 2),
        "margin_to_9_4": r(9.4 - wf.mean(), 1),
    }

    # Figure 4.8: thoracic film map (mid-thorax)
    film = d / 6 * (1 + ratio / 100)
    film = ndimage.gaussian_filter(film * (1 + RNG.normal(0, 0.012, film.shape)), 1.0)
    film[~body] = np.nan
    fig, ax = plt.subplots(figsize=(6.0, 4.4))
    im = ax.imshow(film, extent=[xs[0], xs[-1], ys[-1], ys[0]], cmap="inferno", vmin=0.6, vmax=2.15)
    for lm in lungs:
        ax.contour(xs, ys, lm.astype(float), [0.5], colors="#9dc8f7", linewidths=1)
    ax.grid(False); ax.set_xlabel("Lateral (cm)"); ax.set_ylabel("AP (cm)")
    ax.set_title("Mid-thorax film (slices 16/17), one fraction", fontsize=10)
    cb = fig.colorbar(im, ax=ax, shrink=0.85); cb.set_label("Dose (Gy)")
    fig.savefig(FIG / "fig4_8_thorax_film.png"); plt.close(fig)


def film_plane_figures(V, core, central):
    """Figure 4.5 (film and TPS planes) and 2D film-TPS gamma per plane;
    Figure 4.7 (junction profiles)."""
    deltas = {L[0]: (V["points"][i]["delta"]) for i, L in enumerate(LEVELS)}
    X, Y = np.meshgrid(xs, ys)
    gam = {}
    planes = {}
    for i, L in enumerate(LEVELS):
        d, body, lungs = axial_dose(L[2], lung_core=core)
        tps = d / 6
        # film: TPS with the central difference applied in the central region,
        # 1 mm registration shift and 1.2% pixel noise after the median filter
        blob = np.exp(-((X ** 2 + Y ** 2) / (2 * 5.0 ** 2)))
        rng = np.random.default_rng(100 + i)
        film = tps * (1 + deltas[L[0]] / 100 * blob)
        lungm = ndimage.binary_dilation(lungs[0] | lungs[1], iterations=2)
        if lungm.any():
            # lung: film-TPS ratio from the literature plus a smooth local
            # variation with the spread of Curto's lung TLD differences
            fld = ndimage.gaussian_filter(rng.normal(0, 1, film.shape), 1.2 / DX)
            fld = fld / fld[lungm].std() * 0.040
            film = np.where(lungm, film * (1 + V["lung"]["film_tps_ratio_lit"] / 100 + fld), film)
        film = ndimage.shift(film, (0.1 / DX, 0.1 / DX), order=1)
        film = film * (1 + ndimage.gaussian_filter(rng.normal(0, 0.035, film.shape), 1.0))
        # analysis region: inside the film outline, 1 cm from the cut edge
        inner = ndimage.binary_erosion(body, iterations=int(1.0 / DX))
        g, mask, pr = gamma_2d(tps, film, DX, threshold=0.0)
        mask = mask & inner
        pr = float((g[mask] <= 1).mean() * 100)
        gam[L[0]] = r(pr, 1)
        planes[L[0]] = (tps, film, body, lungs)
    thor = [gam[n] for n in ("Upper thorax", "Mid-thorax", "Lower thorax")]
    nonthor = [gam[n] for n in ("Head", "Umbilicus (reference)", "Pelvis")]
    V["film_gamma"] = gam
    V["film_gamma_summary"] = {"thorax_min": min(thor), "thorax_max": max(thor),
                               "nonthorax_min": min(nonthor), "nonthorax_max": max(nonthor),
                               "junction": [gam["Junction A–B"], gam["Junction B–C"]],
                               "neck": gam["Neck"]}

    fig, axs = plt.subplots(2, 2, figsize=(7.6, 5.8))
    for row, name in enumerate(("Mid-thorax", "Umbilicus (reference)")):
        tps, film, body, lungs = planes[name]
        for col, (img, lab) in enumerate(((film, "Film"), (tps, "TPS"))):
            show = np.where(body, img, np.nan)
            im = axs[row, col].imshow(show, extent=[xs[0], xs[-1], ys[-1], ys[0]], cmap="inferno",
                                      vmin=0.6, vmax=2.15)
            axs[row, col].set_title(f"{name.split(' (')[0]}: {lab}", fontsize=9)
            axs[row, col].grid(False); axs[row, col].tick_params(labelsize=7)
            pts = [(0, 0, "C")] + ([(-7, 0.8, "RL"), (7, 0.8, "LL")] if row == 0 else
                                    [(-10, 0, "R"), (10, 0, "L"), (0, -7, "A"), (0, 7, "P")])
            for px, py, lab2 in pts:
                axs[row, col].plot(px, py, "s", mfc="none", mec="#ffffff", ms=6)
    fig.colorbar(im, ax=axs, shrink=0.8).set_label("Dose per fraction (Gy)")
    fig.savefig(FIG / "fig4_5_film_maps.png"); plt.close(fig)

    # Figure 4.7: longitudinal profiles across the junctions (central axis).
    zz = np.arange(20, 65, 0.25)
    tps_prof = PRESCRIPTION / 6 * (1 + junction_ripple(zz, (-0.012, -0.010)))
    tps_prof = tps_prof * (1 + 0.004 * np.sin(zz / 3.0))
    film_planes = {"A–B": [27.5, 30.0, 32.5], "B–C": [52.5, 55.0, 57.5]}
    jd = {"A–B": deltas["Junction A–B"], "B–C": deltas["Junction B–C"]}
    fig, axs = plt.subplots(1, 2, figsize=(7.6, 3.4), sharey=True)
    prof_rows = {}
    for ax, (jn, zc) in zip(axs, JUNCTIONS.items()):
        m = (zz > zc - 8) & (zz < zc + 8)
        ax.plot(zz[m], tps_prof[m], color=C1, label="TPS")
        fz = np.array(film_planes[jn])
        tps_at = np.interp(fz, zz, tps_prof)
        film_at = tps_at * (1 + np.array([0.35, 1.0, 0.35]) * jd[jn] / 100)
        sd = film_at * 0.014
        ax.errorbar(fz, film_at, yerr=sd, fmt="s", color=C2, ms=6, capsize=3, label="Film (mean ± SD)")
        ax.axvspan(zc - 1, zc + 1, color="#efefef", zorder=0)
        ax.set_title(f"Junction {jn} (overlap {zc - 1:g}–{zc + 1:g} cm)", fontsize=9)
        ax.set_xlabel("Distance from vertex (cm)")
        prof_rows[jn] = {"tps_min_rel": r((tps_prof[m].min() / (PRESCRIPTION / 6) - 1) * 100, 1),
                         "film_centre_rel": r((film_at[1] / (PRESCRIPTION / 6) - 1) * 100, 1)}
    axs[0].set_ylabel("Dose per fraction (Gy)"); axs[0].set_ylim(1.80, 2.12)
    axs[0].legend(loc="lower left", fontsize=8)
    fig.savefig(FIG / "fig4_7_junction_profiles.png"); plt.close(fig)
    V["junction_profiles"] = prof_rows


def uncertainty(lit, V):
    comps = [
        ("Reference dose (output calibration)", mean_of(lit, "uncert_reference_dose")[0]),
        ("Depth dose / TMR data", 0.5), ("Calibration curve fit", 1.0),
        ("Film non-uniformity and film-to-film variation", 1.0), ("Scanner reproducibility", 0.3),
        ("Lateral scanner response (central region)", 0.5), ("ROI pixel variation", 0.4),
    ]
    uc = float(np.sqrt(sum(v ** 2 for _, v in comps)))
    V["uncertainty"] = {"components": [(n, r(v, 1)) for n, v in comps], "combined": r(uc, 1),
                        "expanded": r(2 * uc, 1)}


def main():
    lit = load_literature()
    V = {"note": "Demonstration values: means of the results of studies cited in the thesis. Not measurements."}
    plan_results(lit, V)
    ptv, lungd = dvh_results(lit, V)
    core = calibrate_lung_model(V["dvh"]["lung_mean"])
    V["lung_core_factor"] = r(core, 3)
    dose_figures(V, core)
    octavius_results(lit, V)
    calibration_results(V)
    central, reps = point_results(lit, V, core)
    lung_results(lit, V, core)
    film_plane_figures(V, core, central)
    uncertainty(lit, V)
    V["levels"] = [{"name": L[0], "slices": L[1], "z": L[2], "type": L[3], "points": L[5]} for L in LEVELS]
    V["geometry"] = {"isocentres": ISO, "fields": FIELDS, "junctions": JUNCTIONS}
    (HERE / "demo_values.json").write_text(json.dumps(V, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(V, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
