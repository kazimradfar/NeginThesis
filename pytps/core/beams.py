"""Beams and control points with IEC 61217-style geometry (gantry, collimator, couch), jaws and MLC.

Conventions used in PyTPS (shown in the program):
* Patient coordinates are DICOM LPS (mm). For a head-first supine (HFS) patient, IEC fixed X = patient left,
  Y = towards the gantry (head), Z = up (anterior).
* Gantry 0 = beam from above (anterior for HFS); gantry 90 = source on the IEC +X side (patient's left for HFS).
* Collimator rotates the beam-limiting device about the beam axis; couch rotates the patient about the vertical axis.
* Field coordinates (X, Y) are at the isocentre plane, in mm; the MLC leaves move along X, leaf pairs are stacked along Y.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field

import numpy as np

SAD = 1000.0
# 80 leaf pairs of 5 mm (40 cm field), a common modern MLC layout
LEAF_EDGES = np.linspace(-200.0, 200.0, 81)
LEAF_CENTRES = 0.5 * (LEAF_EDGES[1:] + LEAF_EDGES[:-1])

ORIENT = {   # patient LPS -> IEC fixed (couch at 0)
    "HFS": np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]], float),
    "FFS": np.array([[-1, 0, 0], [0, 0, -1], [0, -1, 0]], float),
    "HFP": np.array([[-1, 0, 0], [0, 0, 1], [0, 1, 0]], float),
    "FFP": np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]], float),
}


def _rz(deg):
    a = np.radians(deg); c, s = np.cos(a), np.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


@dataclass
class Wedge:
    angle: float = 0.0          # nominal wedge angle (deg); 0 = none
    direction: str = "+X"       # thick end towards +X, -X, +Y or -Y of the field
    factor: float = 1.0         # wedge transmission on the central axis


@dataclass
class ControlPoint:
    gantry: float
    collimator: float
    couch: float
    x1: float; x2: float; y1: float; y2: float          # jaws at the isocentre (mm)
    left: np.ndarray | None = None                      # MLC bank positions (mm), 80 values each
    right: np.ndarray | None = None
    weight: float = 1.0                                 # share of the beam MU


@dataclass
class Beam:
    name: str
    iso: np.ndarray                                     # isocentre (patient coordinates, mm)
    energy: str = "6X"
    kind: str = "STATIC"                                # STATIC, ARC
    gantry: float = 0.0
    collimator: float = 0.0
    couch: float = 0.0
    x1: float = -50.0; x2: float = 50.0; y1: float = -50.0; y2: float = 50.0
    mlc_mode: str = "open"                              # open, conformal, manual, optimised
    mlc_target: str = ""                                # structure for conformal MLC
    mlc_margin: float = 5.0
    left: np.ndarray | None = None                      # manual / conformal leaf positions
    right: np.ndarray | None = None
    wedge: Wedge = field(default_factory=Wedge)
    arc_stop: float = 0.0
    arc_dir: str = "CW"
    cp_spacing: float = 4.0
    weight: float = 1.0                                 # relative weight (forward planning)
    mu: float = 0.0
    orientation: str = "HFS"
    visible: bool = True
    cps: list = field(default_factory=list)            # optimised / sequenced control points

    # ------------------------------------------------------------------ geometry
    def arc_span(self):
        d = (self.arc_stop - self.gantry) % 360 if self.arc_dir == "CW" else (self.gantry - self.arc_stop) % 360
        return 360.0 if d < 1e-6 else d

    def angles(self):
        if self.kind != "ARC":
            return [self.gantry]
        span = self.arc_span(); n = max(2, int(round(span / self.cp_spacing)))
        sg = 1 if self.arc_dir == "CW" else -1
        return [(self.gantry + sg * span * (k + 0.5) / n) % 360 for k in range(n)]

    def control_points(self):
        """Control points used for display and dose (sequenced ones if present)."""
        if self.cps:
            return self.cps
        ang = self.angles()
        return [ControlPoint(g, self.collimator, self.couch, self.x1, self.x2, self.y1, self.y2, self.left, self.right, 1.0 / len(ang)) for g in ang]

    def copy(self, name=None):
        b = copy.deepcopy(self)
        if name:
            b.name = name
        return b


class Frame:
    """Beam frame of one control point: source position and field axes in patient coordinates (relative to the isocentre)."""

    def __init__(self, cp: ControlPoint, iso, orientation="HFS"):
        g, c = np.radians(cp.gantry), np.radians(cp.collimator)
        P = _rz(cp.couch) @ ORIENT.get(orientation, ORIENT["HFS"])   # patient -> fixed
        Pinv = P.T
        s_f = SAD * np.array([np.sin(g), 0.0, np.cos(g)])
        xb = np.array([np.cos(g), 0.0, -np.sin(g)]); yb = np.array([0.0, 1.0, 0.0])
        xc = np.cos(c) * xb + np.sin(c) * yb; yc = -np.sin(c) * xb + np.cos(c) * yb
        self.iso = np.asarray(iso, float)
        self.source = Pinv @ s_f                      # relative to the isocentre
        self.axis = -self.source / SAD                # unit vector source -> isocentre
        self.X = Pinv @ xc
        self.Y = Pinv @ yc
        self.cp = cp

    def project(self, pts):
        """Patient points (N, 3) -> field coordinates at the isocentre plane (u, v), distance along the axis a, magnification."""
        d = np.asarray(pts, float) - self.iso - self.source
        a = d @ self.axis
        mag = SAD / np.maximum(a, 1e-3)
        return (d @ self.X) * mag, (d @ self.Y) * mag, a

    def ray_point(self, u, v, a):
        """Patient point at field position (u, v) (isocentre plane) and axial distance a from the source."""
        f = np.asarray(a, float)[..., None] / SAD
        return self.iso + self.source + f * (self.axis * SAD + np.asarray(u, float)[..., None] * self.X + np.asarray(v, float)[..., None] * self.Y)


def conformal_leaves(frame: Frame, mask_points: np.ndarray, margin: float, x1, x2, y1, y2):
    """Leaf positions that follow the projection of a structure (points in patient mm) with a margin."""
    left = np.full(len(LEAF_CENTRES), 0.0); right = np.full(len(LEAF_CENTRES), 0.0)
    if len(mask_points) == 0:
        return left, right
    u, v, _ = frame.project(mask_points)
    for i, (e0, e1) in enumerate(zip(LEAF_EDGES[:-1], LEAF_EDGES[1:])):
        sel = (v >= e0 - margin) & (v <= e1 + margin)
        if sel.any():
            left[i] = max(x1, u[sel].min() - margin); right[i] = min(x2, u[sel].max() + margin)
            if right[i] < left[i]:
                left[i] = right[i] = 0.0
    return left, right


def opposing(beam: Beam) -> Beam:
    """Parallel-opposed copy (gantry + 180, collimator mirrored)."""
    b = beam.copy(beam.name + "_opp")
    b.gantry = (beam.gantry + 180) % 360
    b.collimator = (360 - beam.collimator) % 360
    b.x1, b.x2 = -beam.x2, -beam.x1
    if beam.left is not None:
        b.left, b.right = -beam.right.copy(), -beam.left.copy()
    if beam.wedge.angle:
        b.wedge = Wedge(beam.wedge.angle, {"+X": "-X", "-X": "+X"}.get(beam.wedge.direction, beam.wedge.direction), beam.wedge.factor)
    return b
