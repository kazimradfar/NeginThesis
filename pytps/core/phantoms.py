"""Synthetic CT phantoms with structure sets (for teaching without patient data).

Coordinates follow DICOM LPS in mm: +x patient left, +y posterior, +z superior.
All anatomy is analytic (ellipses / ellipsoids) and only roughly anatomical.
"""
from __future__ import annotations

import numpy as np

from .image import Image3D
from .structures import StructureSet

HU = {"air": -1000, "lung": -820, "fat": -90, "soft": 40, "muscle": 50, "organ": 35, "bladder": 10,
      "bone": 1100, "marrow": 250, "brain": 30}


def _grid(xr, yr, zr, sp):
    x = np.arange(xr[0] + sp[0] / 2, xr[1], sp[0])
    y = np.arange(yr[0] + sp[1] / 2, yr[1], sp[1])
    z = np.arange(zr[0] + sp[2] / 2, zr[1], sp[2])
    return x, y, z


def _ell(X, Y, cx, cy, a, b):
    return ((X - cx) / a) ** 2 + ((Y - cy) / b) ** 2 <= 1.0


def _ellz(X, Y, z, cx, cy, cz, a, b, c):
    t = (z - cz) / c
    if abs(t) >= 1:
        return np.zeros_like(X, bool)
    s = np.sqrt(1 - t * t)
    return _ell(X, Y, cx, cy, a * s, b * s)


class _Builder:
    def __init__(self, x, y, z, name, desc):
        self.x, self.y, self.z = x, y, z
        self.ct = np.full((len(z), len(y), len(x)), HU["air"], np.float32)
        self.masks: dict[str, tuple] = {}
        self.name, self.desc = name, desc
        self.X, self.Y = np.meshgrid(x, y)

    def mask(self, name, k, m, color=None, type="ORGAN"):
        if name not in self.masks:
            self.masks[name] = (np.zeros(self.ct.shape, bool), color, type)
        self.masks[name][0][k] |= m

    def image(self, sp):
        org = (float(self.x[0]), float(self.y[0]), float(self.z[0]))
        img = Image3D(self.ct, sp, org, {"name": "PHANTOM", "id": self.name, "description": self.desc})
        ss = StructureSet(img)
        order = sorted(self.masks.items(), key=lambda kv: 0 if kv[1][2] == "EXTERNAL" else 1)
        for n, (m, c, t) in order:
            ss.add(n, m, c, t)
        return img, ss


def water_box(size=300.0, sp=(3.0, 3.0, 3.0)):
    h = size / 2
    x, y, z = _grid((-h - 30, h + 30), (-h - 30, h + 30), (-h, h), sp)
    B = _Builder(x, y, z, "WATER", f"Water phantom {size / 10:.0f} x {size / 10:.0f} x {size / 10:.0f} cm")
    box = (np.abs(B.X) <= h) & (np.abs(B.Y) <= h)
    for k in range(len(z)):
        B.ct[k][box] = 0
        B.mask("Water", k, box, (127, 220, 127), "EXTERNAL")
    return B.image(sp)


def thorax(sp=(2.5, 2.5, 3.0)):
    x, y, z = _grid((-200, 200), (-140, 140), (-150, 150), sp)
    B = _Builder(x, y, z, "THORAX", "Thorax with a right upper-lobe tumour")
    X, Y = B.X, B.Y
    for k, zz in enumerate(z):
        body = _ell(X, Y, 0, 0, 165, 108)
        B.ct[k][body] = HU["fat"]
        B.ct[k][_ell(X, Y, 0, 0, 155, 98)] = HU["muscle"]
        t = (zz - 20) / 140
        lr = ll = np.zeros_like(body)
        if abs(t) < 1:
            g = np.sqrt(1 - t * t)
            lr, ll = _ell(X, Y, -72, 5, 52 * g, 68 * g), _ell(X, Y, 72, 5, 52 * g, 68 * g)
            B.ct[k][lr | ll] = HU["lung"]
        heart = _ellz(X, Y, zz, 25, -20, -40, 50, 44, 60)
        B.ct[k][heart] = HU["organ"]
        vert = _ell(X, Y, 0, 55, 19, 16)
        cord = _ell(X, Y, 0, 57, 6, 5.5)
        B.ct[k][vert] = HU["bone"]; B.ct[k][_ell(X, Y, 0, 57, 8, 7)] = HU["marrow"]; B.ct[k][cord] = HU["soft"]
        stern = (np.abs(X) < 15) & (Y > -102) & (Y < -92)
        B.ct[k][stern] = HU["bone"]
        oes = _ell(X, Y, 6, 28, 9, 8)
        B.ct[k][oes] = HU["soft"]
        gtv = _ellz(X, Y, zz, -70, 5, 60, 16, 16, 18)
        B.ct[k][gtv] = HU["organ"]
        ptv = _ellz(X, Y, zz, -70, 5, 60, 26, 26, 28)
        B.mask("BODY", k, body, (127, 220, 127), "EXTERNAL")
        B.mask("Lung_R", k, lr, (64, 160, 255)); B.mask("Lung_L", k, ll, (160, 120, 255))
        B.mask("Heart", k, heart, (255, 107, 214)); B.mask("SpinalCord", k, cord, (255, 210, 77))
        B.mask("Esophagus", k, oes, (255, 159, 67))
        B.mask("GTV", k, gtv, (255, 45, 85), "GTV"); B.mask("PTV", k, ptv, (255, 64, 64), "PTV")
    return B.image(sp)


def pelvis(sp=(2.5, 2.5, 3.0)):
    x, y, z = _grid((-210, 210), (-140, 140), (-120, 120), sp)
    B = _Builder(x, y, z, "PELVIS", "Pelvis with prostate, rectum and bladder")
    X, Y = B.X, B.Y
    for k, zz in enumerate(z):
        body = _ell(X, Y, 0, 0, 175, 112)
        B.ct[k][body] = HU["fat"]; B.ct[k][_ell(X, Y, 0, 0, 165, 102)] = HU["muscle"]
        fh_r = _ellz(X, Y, zz, -92, 5, 0, 23, 23, 23); fh_l = _ellz(X, Y, zz, 92, 5, 0, 23, 23, 23)
        if zz > 0:
            for s in (-1, 1):
                ring = _ell(X, Y, s * 105, 15, 30, 60) & ~_ell(X, Y, s * 105, 15, 18, 46)
                B.ct[k][ring] = HU["bone"]
            B.ct[k][_ell(X, Y, 0, 75, 26, 16)] = HU["bone"]
        else:
            for s in (-1, 1):
                B.ct[k][_ell(X, Y, s * 95, 5, 16, 16)] = HU["bone"]
        B.ct[k][fh_r | fh_l] = HU["bone"]
        bladder = _ellz(X, Y, zz, 0, -15, 45, 42, 36, 32)
        B.ct[k][bladder] = HU["bladder"]
        rect = _ell(X, Y, 0, 44, 14, 13) & (zz > -100) & (zz < 100)
        B.ct[k][rect] = HU["soft"]; B.ct[k][_ell(X, Y, 0, 44, 6, 5) & rect] = -600
        pros = _ellz(X, Y, zz, 0, 10, 0, 23, 19, 23)
        B.ct[k][pros] = HU["organ"]
        ptv = _ellz(X, Y, zz, 0, 10, 0, 31, 26, 31) & ~rect
        B.mask("BODY", k, body, (127, 220, 127), "EXTERNAL")
        B.mask("Bladder", k, bladder, (255, 210, 77)); B.mask("Rectum", k, rect, (196, 154, 108))
        B.mask("FemHead_R", k, fh_r, (64, 160, 255)); B.mask("FemHead_L", k, fh_l, (160, 120, 255))
        B.mask("CTV_Prostate", k, pros, (255, 45, 85), "CTV"); B.mask("PTV", k, ptv, (255, 64, 64), "PTV")
    return B.image(sp)


def head_neck(sp=(2.0, 2.0, 3.0)):
    x, y, z = _grid((-140, 140), (-130, 130), (-210, 90), sp)
    B = _Builder(x, y, z, "HEADNECK", "Head and neck, oropharynx target with nodes")
    X, Y = B.X, B.Y
    # outline: head (z > -60), neck (-150..-60), shoulders below
    for k, zz in enumerate(z):
        if zz > -60:
            t = (zz + 10) / 95
            a, b = (78 * np.sqrt(max(0.0, 1 - t * t)) if t > 0 else 78), (95 * np.sqrt(max(0.0, 1 - t * t)) if t > 0 else 95)
        elif zz > -150:
            a, b = 58, 60
        else:
            a, b = 58 + (min(60, -150 - zz)) * 1.6, 60 + (min(60, -150 - zz)) * 0.6
        if a < 2:
            continue
        body = _ell(X, Y, 0, 0, a, b)
        B.ct[k][body] = HU["soft"]
        if zz > -60:
            skull = body & ~_ell(X, Y, 0, 0, a * 0.9, b * 0.9)
            B.ct[k][skull] = HU["bone"]; B.ct[k][_ell(X, Y, 0, 0, a * 0.9, b * 0.9)] = HU["brain"]
        if -95 < zz < -40:
            mand = _ell(X, Y, 0, -40, 45, 40) & ~_ell(X, Y, 0, -40, 37, 32) & (Y < -40)
            B.ct[k][mand] = HU["bone"]; B.mask("Mandible", k, mand, (200, 214, 229))
        if -200 < zz < -30:
            B.ct[k][_ell(X, Y, 0, -12, 9, 8)] = HU["air"]
        if zz < -20:
            B.ct[k][_ell(X, Y, 0, 36, 13, 12)] = HU["bone"]
        cord = _ell(X, Y, 0, 37, 5.5, 5) & (zz < -20)
        B.ct[k][cord] = HU["soft"]
        stem = _ellz(X, Y, zz, 0, 20, -5, 13, 13, 28)
        par_r = _ellz(X, Y, zz, -52, 8, -45, 17, 23, 26); par_l = _ellz(X, Y, zz, 52, 8, -45, 17, 23, 26)
        ptv = (_ellz(X, Y, zz, 0, -5, -70, 38, 32, 45) | _ellz(X, Y, zz, -36, 6, -120, 19, 20, 50) |
               _ellz(X, Y, zz, 36, 6, -120, 19, 20, 50)) & _ell(X, Y, 0, 0, max(a - 5, 1), max(b - 5, 1))
        B.mask("BODY", k, body, (127, 220, 127), "EXTERNAL")
        B.mask("SpinalCord", k, cord, (255, 210, 77)); B.mask("Brainstem", k, stem, (255, 159, 67))
        B.mask("Parotid_R", k, par_r, (64, 160, 255)); B.mask("Parotid_L", k, par_l, (160, 120, 255))
        B.mask("PTV", k, ptv, (255, 64, 64), "PTV")
    return B.image(sp)


def breast_left(sp=(2.5, 2.5, 3.0)):
    x, y, z = _grid((-200, 210), (-160, 130), (-120, 120), sp)
    B = _Builder(x, y, z, "BREAST", "Left breast on a thorax")
    X, Y = B.X, B.Y
    for k, zz in enumerate(z):
        thor = _ell(X, Y, 0, 0, 160, 106)
        brl = _ellz(X, Y, zz, 75, -92, 0, 70, 42, 90); brr = _ellz(X, Y, zz, -75, -92, 0, 66, 39, 86)
        body = thor | brl | brr
        B.ct[k][body] = HU["fat"]; B.ct[k][_ell(X, Y, 0, 0, 150, 96)] = HU["muscle"]
        B.ct[k][(brl | brr) & ~thor] = -60
        t = (zz + 10) / 150
        lr = ll = np.zeros_like(body)
        if abs(t) < 1:
            g = np.sqrt(1 - t * t)
            lr, ll = _ell(X, Y, -72, 8, 52 * g, 66 * g), _ell(X, Y, 72, 8, 52 * g, 66 * g)
            B.ct[k][lr | ll] = HU["lung"]
        heart = _ellz(X, Y, zz, 28, -26, -40, 50, 44, 60)
        B.ct[k][heart] = HU["organ"]
        B.ct[k][_ell(X, Y, 0, 55, 19, 16)] = HU["bone"]
        ptv = brl & ~_ell(X, Y, 0, 0, 165, 111) & _ell(X, Y, 0, -5, 175, 140)
        ptv &= ~(_ell(X, Y, 75, -92, 70, 42) & ~_ell(X, Y, 75, -92, 65, 37))   # 5 mm below the skin
        B.mask("BODY", k, body, (127, 220, 127), "EXTERNAL")
        B.mask("Lung_L", k, ll, (160, 120, 255)); B.mask("Lung_R", k, lr, (64, 160, 255))
        B.mask("Heart", k, heart, (255, 107, 214)); B.mask("Breast_R", k, brr & ~thor, (255, 210, 77))
        B.mask("PTV", k, ptv, (255, 64, 64), "PTV")
    return B.image(sp)


def rando_tbi(sp=(4.0, 4.0, 5.0)):
    """Whole-body phantom of 90 cm (head to upper thigh), similar to the Rando phantom of the thesis."""
    zp = np.array([0, 3, 11, 19, 22, 24, 27, 30, 40, 52, 56, 66, 72, 82, 90]) * 10.0
    ax = np.array([2, 6.5, 7.8, 6.8, 5.6, 5.5, 8.5, 15.0, 16.0, 15.5, 14.5, 14.8, 16.2, 16.6, 16.0]) * 10.0
    by = np.array([2, 7.5, 9.5, 8.5, 5.8, 5.6, 7.0, 9.5, 10.8, 11.0, 10.4, 10.6, 10.8, 11.0, 10.5]) * 10.0
    x, y, z = _grid((-185, 185), (-125, 125), (-900, 0), sp)
    B = _Builder(x, y, z, "RANDO", "Rando-like whole-body phantom, 90 cm (vertex at z = 0)")
    X, Y = B.X, B.Y
    for k, zz in enumerate(z):
        d = -zz                                  # distance from the vertex (mm)
        a, b = np.interp(d, zp, ax), np.interp(d, zp, by)
        body = _ell(X, Y, 0, 0, a, b)
        B.ct[k][body] = HU["soft"]
        if d < 210:
            B.ct[k][body & ~_ell(X, Y, 0, 0, a * 0.9, b * 0.9)] = HU["bone"]
        if 190 < d < 700:
            B.ct[k][_ell(X, Y, 0, b * 0.45, 19, 16)] = HU["bone"]
        t = (d - 410) / 120
        lr = ll = np.zeros_like(body)
        if abs(t) < 1:
            g = np.sqrt(1 - t * t) * (1 + 0.12 * t)
            lr, ll = _ell(X, Y, -76, 8, 52 * g, 66 * g), _ell(X, Y, 76, 8, 52 * g, 66 * g)
            B.ct[k][lr | ll] = HU["lung"]
        kid = _ellz(X, Y, -d, -52, 46, -570, 26, 32, 55) | _ellz(X, Y, -d, 52, 46, -570, 26, 32, 55)
        B.ct[k][kid] = HU["organ"]
        ptv = _ell(X, Y, 0, 0, max(a - 3, 1), max(b - 3, 1)) & ~lr & ~ll
        B.mask("BODY", k, body, (127, 220, 127), "EXTERNAL")
        B.mask("Lung_R", k, lr, (64, 160, 255)); B.mask("Lung_L", k, ll, (160, 120, 255))
        B.mask("Kidneys", k, kid, (255, 210, 77)); B.mask("PTV", k, ptv, (255, 64, 64), "PTV")
    return B.image(sp)


PHANTOMS = {
    "Water phantom 30 cm": water_box,
    "Thorax (lung tumour)": thorax,
    "Pelvis (prostate)": pelvis,
    "Head and neck": head_neck,
    "Breast (left)": breast_left,
    "Whole body 90 cm (TBI)": rando_tbi,
}
