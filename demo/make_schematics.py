#!/usr/bin/env python3
"""Author-drawn schematic figures for the VMAT-TBI thesis.

These replace the figure slots that would otherwise need a published figure
(and copyright permission) or a photograph, and redraw Figures 3.2 and 3.5 for
the final film plan.  All drawings are original schematics; nothing is copied
from a published figure.  Run from the repository root:

    python demo/make_schematics.py
"""

import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import (Arc, Circle, Ellipse, FancyArrowPatch, Polygon,  # noqa: E402
                                Rectangle, RegularPolygon)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_demo as bd  # noqa: E402

FIG = bd.FIG
C1, C2, C3, C4, INK, INK2 = bd.C1, bd.C2, bd.C3, bd.C4, bd.INK, bd.INK2
BODY, EDGE, LUNG = "#f2f1ee", "#bdbab4", "#e8f1fb"
plt.rcParams.update({"axes.grid": False})


def clean(ax):
    ax.set_axis_off()
    ax.set_aspect("equal")


def outline_xy(z0=0, z1=90, scale=1.0, horizontal=True):
    z = np.linspace(z0, z1, 400)
    a, _ = bd.half_axes(z)
    if horizontal:
        return np.r_[z, z[::-1]] * scale, np.r_[a, -a[::-1]] * scale
    return np.r_[a, -a[::-1]] * scale, np.r_[z, z[::-1]] * scale


def body(ax, z0=0, z1=90, lungs=True, **kw):
    x, y = outline_xy(z0, z1)
    ax.add_patch(Polygon(np.c_[x, y], closed=True, fc=BODY, ec=EDGE, lw=1.6, **kw))
    if lungs:
        for s in (-1, 1):
            ax.add_patch(Ellipse((41, s * 7.0), 24, 11, fc=LUNG, ec=C1, lw=1, ls="--"))


def arrow(ax, p, q, col=INK2, lw=1.2, style="-|>", ms=10):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle=style, mutation_scale=ms, color=col, lw=lw))


def arc_arrows(ax, x, y, r, col):
    ax.add_patch(Arc((x, y), 2 * r, 2 * r, theta1=20, theta2=330, color=col, lw=1.3))
    arrow(ax, (x + r * np.cos(np.radians(320)), y + r * np.sin(np.radians(320))),
          (x + r * np.cos(np.radians(335)), y + r * np.sin(np.radians(335))), col=col, ms=9)


# ---------------------------------------------------------------------------
def fig_2_4():
    fig, axs = plt.subplots(1, 2, figsize=(9.6, 3.9))
    # (a) standing, AP/PA, extended SSD
    ax = axs[0]; clean(ax)
    ax.add_patch(Rectangle((0, 4.2), 1.2, 1.6, fc="#d9d9d9", ec=INK2))
    ax.text(0.6, 6.2, "Linac\n(gantry 90°)", ha="center", fontsize=8)
    ax.plot([1.2, 8.6], [5.0, 9.4], color=C2, lw=0.8, ls="--")
    ax.plot([1.2, 8.6], [5.0, 0.6], color=C2, lw=0.8, ls="--")
    ax.add_patch(Rectangle((7.2, 0.7), 0.12, 8.6, fc="#c9c9c9", ec=INK2))
    ax.text(7.26, 9.6, "spoiler", ha="center", fontsize=8)
    ax.add_patch(Rectangle((6.8, 5.6), 0.2, 1.3, fc="#7f7f7f", ec=INK))
    ax.text(6.4, 7.2, "lung block\non tray", ha="right", fontsize=8)
    # standing figure
    ax.add_patch(Circle((8.1, 8.4), 0.45, fc=BODY, ec=EDGE, lw=1.4))
    ax.add_patch(Rectangle((7.75, 4.6), 0.7, 3.4, fc=BODY, ec=EDGE, lw=1.4))
    ax.add_patch(Rectangle((7.8, 0.8), 0.28, 3.8, fc=BODY, ec=EDGE, lw=1.4))
    ax.add_patch(Rectangle((8.12, 0.8), 0.28, 3.8, fc=BODY, ec=EDGE, lw=1.4))
    ax.add_patch(Rectangle((8.6, 3.0), 0.5, 2.6, fc="none", ec=INK2, lw=1))
    ax.text(9.3, 3.2, "support\nframe", fontsize=8)
    arrow(ax, (1.2, 0.2), (8.0, 0.2), style="<|-|>")
    ax.text(4.6, -0.3, "SSD ≈ 3–5 m", ha="center", va="top", fontsize=8)
    ax.set_xlim(-0.3, 10.6); ax.set_ylim(-1.2, 10.4)
    ax.set_title("(a) Standing, AP/PA fields", fontsize=10)
    # (b) lying, lateral fields
    ax = axs[1]; clean(ax)
    ax.add_patch(Rectangle((0, 4.2), 1.2, 1.6, fc="#d9d9d9", ec=INK2))
    ax.text(0.6, 6.2, "Linac", ha="center", fontsize=8)
    ax.plot([1.2, 9.2], [5.0, 8.8], color=C2, lw=0.8, ls="--")
    ax.plot([1.2, 9.2], [5.0, 1.2], color=C2, lw=0.8, ls="--")
    ax.add_patch(Rectangle((7.2, 1.3), 0.12, 7.4, fc="#c9c9c9", ec=INK2))
    ax.text(7.26, 8.9, "spoiler", ha="center", fontsize=8)
    # patient lying on side view (supine, legs bent) seen from the beam
    ax.add_patch(Rectangle((7.6, 2.6), 2.4, 0.25, fc="#d9d9d9", ec=INK2))
    ax.add_patch(Polygon([[7.7, 2.85], [9.6, 2.85], [9.9, 3.6], [7.9, 3.7]], fc=BODY, ec=EDGE, lw=1.4))
    ax.add_patch(Circle((8.0, 4.0), 0.35, fc=BODY, ec=EDGE, lw=1.4))
    ax.add_patch(Polygon([[9.6, 3.5], [9.0, 4.6], [9.25, 4.75], [9.9, 3.6]], fc=BODY, ec=EDGE, lw=1.4))
    ax.text(8.8, 2.3, "couch / stretcher", ha="center", va="top", fontsize=8)
    ax.text(8.6, 5.3, "arms along the body\nshield the lungs", ha="center", fontsize=8)
    arrow(ax, (1.2, 0.6), (8.6, 0.6), style="<|-|>")
    ax.text(4.9, 0.1, "SSD ≈ 3–5 m (lateral fields, both sides)", ha="center", va="top", fontsize=8)
    ax.set_xlim(-0.3, 10.6); ax.set_ylim(-1.2, 10.4)
    ax.set_title("(b) Lying, lateral fields", fontsize=10)
    fig.savefig(FIG / "fig2_4_extended_ssd.png"); plt.close(fig)


def fig_2_6():
    fig, axs = plt.subplots(1, 2, figsize=(11.5, 3.8), gridspec_kw={"width_ratios": [1, 1.1]})
    ax = axs[0]; clean(ax)
    ax.add_patch(Rectangle((0, -3), 20, 6, fc="#e6e6e6", ec=INK2))
    ax.add_patch(Circle((10, 0), 0.5, fc=INK2))
    ax.add_patch(Arc((10, 0), 9, 9, theta1=200, theta2=340, color=C2, lw=1.5))
    arrow(ax, (14.2, -1.7), (14.5, -1.2), col=C2)
    ax.text(10, -5.1, "rotation by 180° about a vertical axis", ha="center", fontsize=8, color=INK)
    ax.text(10, 3.6, "rotatable tabletop on the couch", ha="center", fontsize=8)
    for x0, lab, col in ((1, "head-first\n(upper body)", C1), (13, "feet-first\n(legs)", C2)):
        ax.add_patch(Rectangle((x0, -2), 6, 4, fc="none", ec=col, lw=1.2, ls="--"))
        ax.text(x0 + 3, 0, lab, ha="center", va="center", fontsize=8, color=INK)
    ax.set_xlim(-1, 21); ax.set_ylim(-6, 5)
    ax.set_title("(a) Patient rotation between the two plans", fontsize=10)
    ax = axs[1]
    z = np.linspace(0, 170, 800)
    hfs = 1 / (1 + np.exp((z - 100) / 3.0))
    ffs_plain = 1 / (1 + np.exp(-(z - 96) / 3.0))
    ffs_bias = 1 - hfs
    ax.plot(z, hfs * 100, color=C1, label="HFS plan")
    ax.plot(z, ffs_plain * 100, color=C2, ls=":", label="FFS plan without bias dose")
    ax.plot(z, (hfs + ffs_plain) * 100, color=INK2, ls=":", lw=1.2, label="Sum without bias dose")
    ax.plot(z, (ffs_bias) * 100, color=C2, label="FFS plan optimised on HFS bias dose")
    ax.plot(z, (hfs + ffs_bias) * 100, color=INK, lw=1.4, label="Sum with bias dose")
    ax.axvspan(92, 104, color="#efefef", zorder=0)
    ax.set_xlabel("Position along the body (cm)"); ax.set_ylabel("Relative dose (%)")
    ax.set_ylim(0, 135); ax.grid(True)
    ax.legend(fontsize=7.5, loc="upper left", bbox_to_anchor=(1.01, 1.0))
    ax.set_title("(b) Junction dose with and without the bias dose", fontsize=10)
    fig.tight_layout(); fig.savefig(FIG / "fig2_6_rotatable_tabletop.png"); plt.close(fig)


def fig_2_7():
    xs, zs = bd.xs, np.arange(0, 90.25, 0.5)
    vm = np.zeros((len(zs), len(xs))); cv = np.zeros_like(vm)
    yi = np.argmin(abs(bd.ys - 0.8))
    for k, z in enumerate(zs):
        d, body_m, lungs = bd.axial_dose(z, lung_core=0.55)
        vm[k] = d[yi]
        a, b = bd.half_axes(z)
        # conventional extended-SSD AP/PA: dose follows the separation
        sep_factor = 1 + 0.12 * (10.8 - b) / 10.8 * (b > 2)
        row = np.where(body_m[yi], bd.PRESCRIPTION * sep_factor, 0)
        lm = lungs[0][yi] | lungs[1][yi]
        row = np.where(lm, row * 0.86, row)          # partial-transmission lung blocks
        cv[k] = row
    from scipy import ndimage
    cv = ndimage.gaussian_filter(cv, 1.2)
    fig = plt.figure(figsize=(9.2, 4.6))
    for i, (img, lab) in enumerate(((cv, "Conventional (extended SSD, AP/PA,\nlung blocks)"),
                                    (vm, "VMAT (three isocentres,\nlungs as avoidance structure)"))):
        ax = fig.add_axes([0.02 + i * 0.25, 0.08, 0.22, 0.80])
        im = ax.imshow(img, extent=[xs[0], xs[-1], zs[-1], zs[0]], cmap="inferno", vmin=0, vmax=14)
        ax.set_title(lab, fontsize=9); ax.set_xticks([]); ax.set_yticks([])
    cax = fig.add_axes([0.49, 0.12, 0.012, 0.7]); fig.colorbar(im, cax=cax).set_label("Dose (Gy)", fontsize=8)
    ax = fig.add_axes([0.63, 0.15, 0.35, 0.7])
    grid = np.linspace(0, 15, 301)
    for img, ls, name in ((cv, ":", "Conventional"), (vm, "-", "VMAT")):
        lungmask = np.zeros_like(img, bool); bodymask = img > 6
        for k, z in enumerate(zs):
            _, _, lungs = bd.axial_dose(z) if 29 < z < 53 else (None, None, [np.zeros(len(bd.ys), bool)] * 0)
            if lungs:
                lungmask[k] = lungs[0][yi] | lungs[1][yi]
        lv = img[lungmask]; bv = img[bodymask & ~lungmask]
        ax.plot(grid, [(bv >= g).mean() * 100 for g in grid], color=C1, ls=ls, label=f"Body, {name}")
        ax.plot(grid, [(lv >= g).mean() * 100 for g in grid], color=C2, ls=ls, label=f"Lungs, {name}")
    ax.set_xlabel("Dose (Gy)"); ax.set_ylabel("Volume (%)"); ax.grid(True)
    ax.legend(fontsize=7.5, loc="lower left")
    ax.set_title("Coronal-plane DVH (illustrative)", fontsize=9)
    fig.savefig(FIG / "fig2_7_conventional_vs_vmat.png"); plt.close(fig)


def fig_2_8():
    fig, axs = plt.subplots(1, 2, figsize=(9.4, 4.2), gridspec_kw={"width_ratios": [2.2, 1]})
    ax = axs[0]; clean(ax)
    body(ax)
    for k in range(37):
        z = k * 2.5
        a, _ = bd.half_axes(min(z, 89.9))
        ax.plot([z, z], [-a, a], color=EDGE, lw=0.6)
    for k in range(0, 36, 5):
        ax.text(k * 2.5 + 1.25, -19.5, str(k), ha="center", fontsize=7, color=INK2)
    ax.text(45, -23, "slice number (2.5 cm slices, numbered from the vertex)", ha="center", fontsize=8)
    ax.text(41, 0, "lungs", ha="center", va="center", fontsize=8, color=C1)
    ax.set_xlim(-2, 92); ax.set_ylim(-25, 20)
    ax.set_title("Alderson Rando phantom, frontal outline (schematic)", fontsize=10)
    ax = axs[1]; clean(ax)
    ax.add_patch(Ellipse((0, 0), 32, 22, fc=BODY, ec=EDGE, lw=1.6))
    for s in (-1, 1):
        ax.add_patch(Ellipse((s * 7, 0.8), 11, 13.5, fc=LUNG, ec=C1, lw=1, ls="--"))
    ax.add_patch(Circle((0, 7.5), 1.5, fc="#dcd7cf", ec=EDGE))
    for x in np.arange(-13.5, 14, 3):
        for y in np.arange(-9, 10, 3):
            if (x / 15.5) ** 2 + (y / 10.5) ** 2 < 0.92:
                ax.add_patch(Circle((x, y), 0.32, fc="#ffffff", ec=INK2, lw=0.6))
    ax.text(0, -13.5, "transverse slice with 3 cm grid\nof dosimeter holes", ha="center", va="top", fontsize=8)
    ax.set_xlim(-17, 17); ax.set_ylim(-17, 13)
    fig.savefig(FIG / "fig2_8_rando_phantom.png"); plt.close(fig)


def fig_2_10():
    fig, ax = plt.subplots(figsize=(8.8, 3.6)); clean(ax)
    ax.add_patch(Rectangle((-2, -3.2), 64, 0.8, fc="#e6e6e6", ec=INK2))
    for x0, lab, col, ls in ((8, "Position 1:\narray centred on isocentre 1", C1, "-"),
                             (30, "Position 2: couch translated\nby the isocentre distance", C2, "--")):
        ax.add_patch(Rectangle((x0, -2.4), 21, 4.8, fc="#f7f7f7", ec=col, lw=1.4, ls=ls))
        for xx in np.arange(x0 + 1, x0 + 21, 1.0):
            ax.plot([xx, xx], [-2.0, 2.0], color=col, lw=0.4, alpha=0.6)
        ax.text(x0 + 10.5, 3.1, lab, ha="center", fontsize=8)
    for x, lab in ((18.5, "iso 1"), (40.5, "iso 2")):
        ax.plot(x, 0, "x", color=INK, ms=8, mew=2); ax.text(x, -4.3, lab, ha="center", fontsize=8)
    ax.axvspan(28.5, 31.0, ymin=0.2, ymax=0.8, color="#d9d9d9", zorder=0)
    ax.text(29.75, -5.8, "junction (overlap)\nmeasured in both positions", ha="center", fontsize=8)
    arrow(ax, (18.5, -7.4), (40.5, -7.4), style="<|-|>")
    ax.text(29.5, -8.0, "longitudinal couch shift", ha="center", va="top", fontsize=8)
    ax.text(-1, 5.6, "Cylindrical diode array (helical detector layout), side view", fontsize=9)
    ax.set_xlim(-3, 63); ax.set_ylim(-10, 7)
    fig.savefig(FIG / "fig2_10_arccheck_junction.png"); plt.close(fig)


def fig_2_11():
    fig, ax = plt.subplots(figsize=(9.6, 3.9)); clean(ax)
    body(ax, 0, 88)
    isos = {"A": 12.5, "B": 33.5, "C": 54.5, "D": 75.5}
    for k, (n, z) in enumerate(isos.items()):
        col = C1 if k % 2 == 0 else C2
        ax.add_patch(Rectangle((z - 12.5, -19 + k * 0.4), 25, 38 - k * 0.8, fill=False, ec=col, lw=1.3,
                               ls="-" if k % 2 == 0 else "--"))
        ax.plot(z, 0, "x", color=col, ms=8, mew=2)
        ax.text(z, 20.5, f"Isocentre {n}", ha="center", fontsize=9)
    for z0 in (21, 42, 63):
        ax.add_patch(Rectangle((z0, -19), 4, 38, fc="#dedede", ec="none", zorder=0.5))
    tld = [4, 5, 8, 9, 12, 13, 16, 17, 20, 21, 24, 25, 29]
    for s in tld:
        z = s * 2.5 + 1.25
        ax.plot([z, z], [-17.5, -15.8], color=INK, lw=1.4)
    ax.text(44, -21.5, "TLD slices: " + ", ".join(map(str, tld)) + " (57 locations)",
            ha="center", fontsize=8)
    ax.text(44, -25.5, "isocentres 21 cm apart, 25 cm field length, 4 cm overlap (grey)",
            ha="center", fontsize=8, color=INK2)
    ax.set_xlim(-2, 90); ax.set_ylim(-27, 22)
    fig.savefig(FIG / "fig2_11_curto_rando_plan.png"); plt.close(fig)


def fig_2_12():
    wl = np.linspace(500, 700, 600)

    def band(c, w, a):
        return a * np.exp(-0.5 * ((wl - c) / w) ** 2)
    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    for dose, alpha in ((0.5, 0.35), (1.0, 0.55), (2.0, 0.8), (4.0, 1.0)):
        spec = 0.10 + dose * (band(636, 16, 0.075) + band(585, 22, 0.045) + band(560, 40, 0.01))
        ax.plot(wl, spec, color=C1, alpha=alpha, lw=1.6, label=f"{dose:g} Gy")
    for lo, hi, lab, col in ((600, 680, "red channel", "#f8d0c0"), (520, 580, "green channel", "#cdeee5")):
        ax.axvspan(lo, hi, color=col, alpha=0.5, zorder=0)
        ax.text((lo + hi) / 2, 0.5, lab, ha="center", fontsize=8, color=INK2)
    ax.axvline(636, color=INK2, lw=0.7, ls="--"); ax.axvline(585, color=INK2, lw=0.7, ls="--")
    ax.text(636, 0.46, "636 nm", ha="center", fontsize=8, bbox=dict(fc="white", ec="none", pad=1))
    ax.text(585, 0.40, "585 nm", ha="center", fontsize=8, bbox=dict(fc="white", ec="none", pad=1))
    ax.set_xlabel("Wavelength (nm)"); ax.set_ylabel("Absorbance (a.u.)")
    ax.set_xlim(500, 700); ax.set_ylim(0, 0.55); ax.set_yticks([])
    ax.legend(title="dose", fontsize=7, title_fontsize=7, loc="upper left")
    fig.savefig(FIG / "fig2_12_ebt3_spectrum.png"); plt.close(fig)


def fig_3_2():
    fig, ax = plt.subplots(figsize=(10, 4.3)); clean(ax)
    body(ax)
    for k, (f, (a, b)) in enumerate(bd.FIELDS.items()):
        col = C1 if f != "B" else C2
        ax.add_patch(Rectangle((a, -19 + 0.3 * k), b - a, 38 - 0.6 * k, fill=False, ec=col, lw=1.4,
                               ls="-" if f != "B" else "--"))
        ax.plot(bd.ISO[f], 0, "x", color=col, ms=9, mew=2.2)
        ax.text((a + b) / 2, 20.5, f"Isocentre {f}", ha="center", fontsize=10)
    for zj in bd.JUNCTIONS.values():
        ax.add_patch(Rectangle((zj - 1, -19), 2, 38, fc="#d9d9d9", ec="none", alpha=0.8, zorder=0.5))
    for i, L in enumerate(bd.LEVELS):
        z = L[2]; a, _ = bd.half_axes(z)
        ax.plot([z, z], [-a - 0.5, a + 0.5], color=INK, lw=2)
        lab = L[0].replace(" (reference)", "\n(reference)").replace("Junction ", "Junction\n")
        lab = lab.replace("Upper thorax", "Upper\nthorax").replace("Mid-thorax", "Mid-\nthorax").replace(
            "Lower thorax", "Lower\nthorax")
        yy = -22.5 if i % 2 == 0 else -29.5
        ax.plot([z, z], [-19, yy + 1.5], color=EDGE, lw=0.8)
        ax.text(z, yy, f"{lab}\n[{L[1]}]", ha="center", va="top", fontsize=7.5)
    for zp in (27.5, 32.5, 52.5, 57.5):
        a, _ = bd.half_axes(zp)
        ax.plot([zp, zp], [-a, a], color=INK2, lw=1, ls=(0, (2, 1.5)))
    ax.text(45, 25.5, "Film planes (black: evaluation levels; dashed: additional junction-profile films); "
            "grey bands: 2 cm overlaps; [slices]", ha="center", fontsize=8, color=INK2)
    ax.set_xlim(-2, 92); ax.set_ylim(-40, 27)
    fig.savefig(FIG / "fig3_2_film_planes.png"); plt.close(fig)


def fig_3_3():
    fig, ax = plt.subplots(figsize=(10, 4.3)); clean(ax)
    body(ax)
    for k, (f, (a, b)) in enumerate(bd.FIELDS.items()):
        col = C1 if f != "B" else C2
        ax.add_patch(Rectangle((a, -19 + 0.3 * k), b - a, 38 - 0.6 * k, fill=False, ec=col, lw=1.4,
                               ls="-" if f != "B" else "--"))
        z = bd.ISO[f]
        ax.plot(z, 0, "x", color=col, ms=9, mew=2.2)
        arc_arrows(ax, z, 0, 3.2, col)
        ax.text(z, 21, f"Isocentre {f}", ha="center", fontsize=9.5)
        ax.text((a + b) / 2, -21.5, f"field length {b - a:g} cm", ha="center", fontsize=8, color=INK2)
    for zj in bd.JUNCTIONS.values():
        ax.add_patch(Rectangle((zj - 1, -19), 2, 38, fc="#d9d9d9", ec="none", alpha=0.8, zorder=0.5))
    arrow(ax, (bd.ISO["A"], -26), (bd.ISO["B"], -26), style="<|-|>")
    arrow(ax, (bd.ISO["B"], -26), (bd.ISO["C"], -26), style="<|-|>")
    ax.text((bd.ISO["A"] + bd.ISO["B"]) / 2, -27, "27.0 cm", ha="center", va="top", fontsize=8)
    ax.text((bd.ISO["B"] + bd.ISO["C"]) / 2, -27, "29.5 cm", ha="center", va="top", fontsize=8)
    ax.text(45, -31.5, "two full arcs (CW + CCW) per isocentre, 6 MV; overlaps 2 cm (grey); "
            "all six arcs optimised together in one plan", ha="center", va="top", fontsize=8, color=INK2)
    ax.set_xlim(-2, 92); ax.set_ylim(-35, 24)
    fig.savefig(FIG / "fig3_3_beam_arrangement.png"); plt.close(fig)


def fig_3_4():
    fig, ax = plt.subplots(figsize=(7.4, 4.6)); clean(ax)
    ax.add_patch(Circle((0, 0), 9.5, fill=False, ec=EDGE, lw=1, ls=":"))
    ax.text(6.9, 7.4, "gantry rotation", fontsize=8, color=INK2)
    ax.add_patch(Rectangle((-1.4, 9.5), 2.8, 1.8, fc="#d9d9d9", ec=INK2))
    ax.text(0, 11.9, "linac head with inclinometer", ha="center", fontsize=8)
    ax.add_patch(Rectangle((1.5, 10.0), 0.8, 0.8, fc=C2, ec=INK))
    ax.plot([-1.0, -3.2], [9.5, 3.0], color=C2, lw=0.8, ls="--")
    ax.plot([1.0, 3.2], [9.5, 3.0], color=C2, lw=0.8, ls="--")
    ax.add_patch(RegularPolygon((0, 0), 8, radius=3.4, orientation=np.pi / 8, fc=BODY, ec=EDGE, lw=1.6))
    ax.add_patch(Rectangle((-2.7, -0.15), 5.4, 0.3, fc=C1, ec=INK))
    ax.text(3.2, -0.15, "2D ionisation-\nchamber array", fontsize=8, va="center", ha="left",
            bbox=dict(fc="white", ec="none", pad=1))
    ax.add_patch(Rectangle((-6, -4.1), 12, 0.7, fc="#e6e6e6", ec=INK2))
    ax.text(0, -4.9, "treatment couch", ha="center", va="top", fontsize=8)
    ax.text(-8.6, 3.2, "Octavius phantom\n(octagonal, PMMA)", fontsize=8, ha="center")
    arrow(ax, (-7, 2.4), (-3.2, 1.2))
    ax.set_xlim(-11, 11); ax.set_ylim(-7, 13)
    fig.savefig(FIG / "fig3_4_octavius_setup.png"); plt.close(fig)


def fig_3_5():
    fig, ax = plt.subplots(figsize=(7.4, 4.8)); clean(ax)
    ax.add_patch(Polygon([[-1.0, 16], [1.0, 16], [1.2, 15], [-1.2, 15]], fc="#d9d9d9", ec=INK2))
    ax.text(0, 16.4, "Source (6 MV), SAD 100 cm", ha="center", fontsize=8.5)
    ax.plot([0, -5.0], [15, 2.0], color=C2, lw=0.8, ls="--")
    ax.plot([0, 5.0], [15, 2.0], color=C2, lw=0.8, ls="--")
    ax.text(3.6, 8, "10 × 10 cm² field\nat the film plane", fontsize=8)
    w = 14
    for k in range(5):
        ax.add_patch(Rectangle((-w / 2, 5 - k * 0.6 - 0.6), w, 0.6, fc="#e9eef5", ec=INK2, lw=0.6))
    ax.add_patch(Rectangle((-1.5, 1.95), 3.0, 0.1, fc=C2, ec=INK))
    ax.text(-w / 2 - 0.3, 3.5, "build-up:\n5 × 1 cm PMMA\n(film at 5 cm depth)", ha="right", va="center",
            fontsize=8)
    for k in range(10):
        ax.add_patch(Rectangle((-w / 2, 2 - (k + 1) * 0.6), w, 0.6, fc="#f3f3f3", ec=INK2, lw=0.6))
    ax.text(-w / 2 - 0.3, -1.0, "backscatter:\n10 × 1 cm PMMA", ha="right", va="center", fontsize=8)
    ax.text(0, 1.75, "EBT3 film, 5 × 5 cm²", fontsize=7.5, va="top", ha="center",
            bbox=dict(fc="white", ec="none", pad=0.5))
    ax.add_patch(Rectangle((-w / 2 - 0.5, -4.6), w + 1, 0.5, fc="#d9d9d9", ec=INK2))
    ax.text(0, -5.0, "treatment couch", ha="center", va="top", fontsize=8)
    ax.text(w / 2 + 0.3, -1.0, "reference dose:\nFarmer chamber\nin the same slab\ngeometry",
            fontsize=8, va="center")
    ax.set_xlim(-13.5, 13.5); ax.set_ylim(-6.2, 17.2)
    fig.savefig(FIG / "fig3_5_calibration_geometry.png"); plt.close(fig)


def main():
    for f in (fig_2_4, fig_2_6, fig_2_7, fig_2_8, fig_2_10, fig_2_11, fig_2_12, fig_3_2, fig_3_3,
              fig_3_4, fig_3_5):
        f()
        print("ok", f.__name__)


if __name__ == "__main__":
    main()
