"""CT image volume on a regular, axis-aligned grid (DICOM patient coordinates, millimetres).

Patient coordinate system (DICOM LPS): +x towards the patient's left, +y towards the patient's
posterior, +z towards the patient's head. Arrays are indexed [k, j, i] = [slice, row, column].
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


# piecewise-linear CT-number to relative electron density curve (generic, editable in the GUI)
DEFAULT_CT_TO_RED = [(-1000.0, 0.001), (-800.0, 0.19), (-100.0, 0.93), (0.0, 1.0), (100.0, 1.06),
                     (300.0, 1.16), (1000.0, 1.53), (3000.0, 2.5)]


@dataclass
class Image3D:
    array: np.ndarray                      # CT numbers (HU), shape (nz, ny, nx), float32
    spacing: tuple[float, float, float]    # (dx, dy, dz) in mm
    origin: tuple[float, float, float]     # patient position of voxel [0, 0, 0] centre (mm)
    patient: dict = field(default_factory=dict)   # anonymised identifiers and description
    orientation: str = "HFS"               # patient position at CT (HFS, FFS, HFP, FFP)
    ct_to_red: list = field(default_factory=lambda: list(DEFAULT_CT_TO_RED))

    @property
    def shape(self):
        return self.array.shape

    def axis(self, a: str) -> np.ndarray:
        """Voxel centre coordinates along x, y or z (mm)."""
        n = {"x": self.shape[2], "y": self.shape[1], "z": self.shape[0]}[a]
        i = "xyz".index(a)
        return self.origin[i] + self.spacing[i] * np.arange(n)

    def extent(self):
        """(min, max) patient coordinates of the voxel edges for x, y, z."""
        out = []
        for i, a in enumerate("xyz"):
            ax = self.axis(a)
            out.append((ax[0] - self.spacing[i] / 2, ax[-1] + self.spacing[i] / 2))
        return out

    def world_to_index(self, p):
        p = np.asarray(p, float)
        return (p - np.asarray(self.origin)) / np.asarray(self.spacing)   # (i, j, k) as floats

    def index_to_world(self, ijk):
        return np.asarray(self.origin) + np.asarray(ijk, float) * np.asarray(self.spacing)

    def value_at(self, p) -> float:
        i, j, k = np.round(self.world_to_index(p)).astype(int)
        if 0 <= k < self.shape[0] and 0 <= j < self.shape[1] and 0 <= i < self.shape[2]:
            return float(self.array[k, j, i])
        return float("nan")

    def density(self) -> np.ndarray:
        """Relative electron density from the CT-to-density table."""
        hu, red = zip(*sorted(self.ct_to_red))
        return np.interp(self.array, hu, red).astype(np.float32)

    def slice(self, view: str, pos_mm: float) -> tuple[np.ndarray, int]:
        """2D slice through the volume. view: 'axial' (pos = z), 'coronal' (pos = y), 'sagittal' (pos = x)."""
        a = {"axial": "z", "coronal": "y", "sagittal": "x"}[view]
        i = "xyz".index(a)
        idx = int(np.clip(np.round((pos_mm - self.origin[i]) / self.spacing[i]), 0, self.shape[2 - i] - 1))
        if view == "axial":
            return self.array[idx], idx
        if view == "coronal":
            return self.array[:, idx, :], idx
        return self.array[:, :, idx], idx

    def resampled(self, spacing) -> "Image3D":
        """Resample to a new spacing (linear), e.g. to keep whole-body CTs small."""
        from scipy.ndimage import zoom
        f = [self.spacing[2] / spacing[2], self.spacing[1] / spacing[1], self.spacing[0] / spacing[0]]
        arr = zoom(self.array, f, order=1).astype(np.float32)
        new_sp = tuple(self.spacing[i] * self.shape[2 - i] / arr.shape[2 - i] for i in range(3))
        org = tuple(self.origin[i] - self.spacing[i] / 2 + new_sp[i] / 2 for i in range(3))
        return Image3D(arr, new_sp, org, dict(self.patient), self.orientation, list(self.ct_to_red))
