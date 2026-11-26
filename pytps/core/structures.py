"""Structure set: binary masks on the CT grid, contour conversion and contouring operations."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import ndimage

from .image import Image3D

STRUCT_TYPES = ["EXTERNAL", "PTV", "CTV", "GTV", "ORGAN", "AVOIDANCE", "SUPPORT", "MARKER", "CONTROL"]
PALETTE = [(255, 64, 64), (64, 160, 255), (160, 120, 255), (255, 210, 77), (255, 159, 67), (61, 220, 151),
           (255, 107, 214), (0, 229, 255), (184, 255, 92), (200, 200, 200), (255, 128, 128), (120, 200, 255)]


@dataclass
class Structure:
    name: str
    mask: np.ndarray                      # bool (nz, ny, nx)
    color: tuple = (255, 64, 64)
    type: str = "ORGAN"
    density: float | None = None          # relative electron density override (None = from CT)
    visible: bool = True

    def volume_cc(self, img: Image3D) -> float:
        return float(self.mask.sum()) * float(np.prod(img.spacing)) / 1000.0

    @property
    def is_target(self) -> bool:
        return self.type in ("PTV", "CTV", "GTV")


@dataclass
class StructureSet:
    image: Image3D
    structures: list[Structure] = field(default_factory=list)
    version: int = 0

    # ------------------------------------------------------------------ bookkeeping
    def names(self):
        return [s.name for s in self.structures]

    def get(self, name) -> Structure | None:
        for s in self.structures:
            if s.name == name:
                return s
        return None

    def add(self, name, mask=None, color=None, type="ORGAN") -> Structure:
        if self.get(name):
            raise ValueError(f"A structure called {name} already exists")
        if mask is None:
            mask = np.zeros(self.image.shape, bool)
        if color is None:
            color = PALETTE[len(self.structures) % len(PALETTE)]
        s = Structure(name, mask.astype(bool), tuple(color), type)
        self.structures.append(s)
        self.version += 1
        return s

    def remove(self, name):
        self.structures = [s for s in self.structures if s.name != name]
        self.version += 1

    def external(self) -> Structure | None:
        for s in self.structures:
            if s.type == "EXTERNAL":
                return s
        return None

    def density(self) -> np.ndarray:
        """Relative electron density with structure overrides (the structure lower in the list wins)."""
        d = self.image.density()
        ext = self.external()
        if ext is not None:
            d = np.where(ext.mask, d, 0.0).astype(np.float32)   # air outside the patient
        for s in self.structures:
            if s.density is not None:
                d[s.mask] = s.density
        return d

    # ------------------------------------------------------------------ contours <-> masks
    def rasterise(self, polygons_by_z: dict[float, list[np.ndarray]]) -> np.ndarray:
        """Masks from planar contours. polygons_by_z: z (mm) -> list of (N, 2) arrays of (x, y) in mm.
        Several polygons on one slice combine with the even-odd rule (holes)."""
        img = self.image
        mask = np.zeros(img.shape, bool)
        zs = img.axis("z")
        for z, polys in polygons_by_z.items():
            k = int(np.argmin(np.abs(zs - z)))
            if abs(zs[k] - z) > img.spacing[2] * 0.51:
                continue
            sl = np.zeros(img.shape[1:], bool)
            for p in polys:
                sl ^= polygon_mask(p, img)
            mask[k] |= sl
        return mask

    def contours(self, name: str, view: str, idx: int) -> list[np.ndarray]:
        """Contour lines of a structure on a slice, in mm (u, v) of that view."""
        s = self.get(name)
        if s is None:
            return []
        img = self.image
        if view == "axial":
            sl, (su, sv), (u0, v0) = s.mask[idx], (img.spacing[0], img.spacing[1]), (img.origin[0], img.origin[1])
        elif view == "coronal":
            sl, (su, sv), (u0, v0) = s.mask[:, idx, :], (img.spacing[0], img.spacing[2]), (img.origin[0], img.origin[2])
        else:
            sl, (su, sv), (u0, v0) = s.mask[:, :, idx], (img.spacing[1], img.spacing[2]), (img.origin[1], img.origin[2])
        if not sl.any():
            return []
        from skimage import measure
        out = []
        for c in measure.find_contours(np.pad(sl.astype(np.float32), 1), 0.5):
            out.append(np.column_stack([u0 + (c[:, 1] - 1) * su, v0 + (c[:, 0] - 1) * sv]))
        return out

    # ------------------------------------------------------------------ contouring operations
    def margin(self, src_mask: np.ndarray, mm: float, mm_z: float | None = None) -> np.ndarray:
        """3D margin in mm (negative contracts). mm_z: different margin in the head-foot direction."""
        sp = [self.image.spacing[2], self.image.spacing[1], self.image.spacing[0]]
        m = abs(mm)
        if mm_z is not None and m > 0:
            sp[0] *= m / max(abs(mm_z), 1e-3)        # stretch z so that one distance gives both margins
        if mm >= 0:
            return ndimage.distance_transform_edt(~src_mask, sampling=sp) <= m + 1e-6
        return ndimage.distance_transform_edt(src_mask, sampling=sp) > m + 1e-6

    @staticmethod
    def boolean(a: np.ndarray, op: str, b: np.ndarray) -> np.ndarray:
        return {"union": a | b, "intersect": a & b, "subtract": a & ~b, "xor": a ^ b}[op]

    def threshold(self, lo: float, hi: float, within: np.ndarray | None = None) -> np.ndarray:
        m = (self.image.array >= lo) & (self.image.array <= hi)
        return m & within if within is not None else m

    @staticmethod
    def fill_holes(mask: np.ndarray) -> np.ndarray:
        out = mask.copy()
        for k in range(mask.shape[0]):
            if mask[k].any():
                out[k] = ndimage.binary_fill_holes(mask[k])
        return out

    @staticmethod
    def largest_component(mask: np.ndarray) -> np.ndarray:
        lab, n = ndimage.label(mask)
        if n < 2:
            return mask
        sizes = ndimage.sum(mask, lab, range(1, n + 1))
        return lab == (1 + int(np.argmax(sizes)))

    def interpolate(self, mask: np.ndarray) -> np.ndarray:
        """Shape-based interpolation of empty axial slices between contoured slices."""
        ks = np.where(mask.any(axis=(1, 2)))[0]
        out = mask.copy()
        sp = (self.image.spacing[1], self.image.spacing[0])

        def sdf(m):
            return ndimage.distance_transform_edt(~m, sampling=sp) - ndimage.distance_transform_edt(m, sampling=sp)
        for a, b in zip(ks[:-1], ks[1:]):
            if b - a < 2:
                continue
            A, B = sdf(mask[a]), sdf(mask[b])
            for k in range(a + 1, b):
                f = (k - a) / (b - a)
                out[k] = (A * (1 - f) + B * f) <= 0
        return out

    def external_from_threshold(self, hu=-350) -> np.ndarray:
        """Body outline: threshold, keep the largest object, fill holes slice by slice."""
        m = self.image.array > hu
        m = ndimage.binary_opening(m, iterations=1)
        m = self.largest_component(m)
        return self.fill_holes(m)


def fill_polygon(shape2d, cols, rows) -> np.ndarray:
    """Even-odd scanline fill of a polygon given in pixel coordinates (column, row) on a 2D grid."""
    u, v = np.asarray(cols, float), np.asarray(rows, float)
    ny, nx = shape2d
    out = np.zeros((ny, nx), bool)
    if len(u) < 3:
        return out
    x1, y1, x2, y2 = u, v, np.roll(u, -1), np.roll(v, -1)
    for j in range(max(0, int(np.floor(v.min()))), min(ny, int(np.ceil(v.max())) + 1)):
        cross = ((y1 <= j) & (y2 > j)) | ((y2 <= j) & (y1 > j))
        if not cross.any():
            continue
        xs = np.sort(x1[cross] + (j - y1[cross]) * (x2[cross] - x1[cross]) / (y2[cross] - y1[cross]))
        for a, b in zip(xs[0::2], xs[1::2]):
            i0, i1 = int(np.ceil(a)), int(np.floor(b))
            if i1 >= i0:
                out[j, max(0, i0):min(nx, i1 + 1)] = True
    return out


def polygon_mask(poly_xy_mm: np.ndarray, img: Image3D) -> np.ndarray:
    """Fill a polygon (x, y in mm) on the axial grid of the image."""
    p = np.asarray(poly_xy_mm, float)
    return fill_polygon(img.shape[1:], (p[:, 0] - img.origin[0]) / img.spacing[0], (p[:, 1] - img.origin[1]) / img.spacing[1])


def disc_on_slice(shape2d, centre_ij, radius_px) -> np.ndarray:
    """Boolean disc on a 2D slice (for the brush). centre_ij = (row, col) in pixels; radius may differ per axis."""
    ry, rx = radius_px if isinstance(radius_px, tuple) else (radius_px, radius_px)
    jj, ii = np.ogrid[:shape2d[0], :shape2d[1]]
    return ((jj - centre_ij[0]) / max(ry, 0.5)) ** 2 + ((ii - centre_ij[1]) / max(rx, 0.5)) ** 2 <= 1.0
