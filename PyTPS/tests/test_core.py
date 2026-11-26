import numpy as np
import pytest

from pytps.core import phantoms
from pytps.core.structures import StructureSet, fill_polygon


def test_phantoms_build():
    for name, f in phantoms.PHANTOMS.items():
        img, ss = f()
        assert ss.external() is not None, name
        assert img.array.shape == ss.structures[0].mask.shape


def test_square_polygon_area():
    img, ss = phantoms.water_box()
    sq = np.array([[-60, -60], [60, -60], [60, 60], [-60, 60]], float)
    m = ss.rasterise({0.0: [sq]})
    assert abs(m.sum() * img.spacing[0] * img.spacing[1] - 120 * 120) < 0.05 * 120 * 120


def test_margin_sphere_volume():
    img, ss = phantoms.water_box(sp=(2.0, 2.0, 2.0))
    x, y, z = img.axis("x"), img.axis("y"), img.axis("z")
    Z, Y, X = np.meshgrid(z, y, x, indexing="ij")
    ball = X ** 2 + Y ** 2 + Z ** 2 <= 30 ** 2
    grown = ss.margin(ball, 10)
    v = grown.sum() * 8 / 1000.0
    assert abs(v - 4 / 3 * np.pi * 4.0 ** 3) / (4 / 3 * np.pi * 4.0 ** 3) < 0.05
    shrunk = ss.margin(ball, -10)
    assert abs(shrunk.sum() * 8 / 1000.0 - 4 / 3 * np.pi * 2.0 ** 3) < 0.15 * 4 / 3 * np.pi * 2.0 ** 3


def test_boolean_and_interpolate():
    img, ss = phantoms.water_box()
    a = np.zeros(img.shape, bool); a[10, 40:60, 40:60] = True; a[20, 40:60, 40:60] = True
    full = ss.interpolate(a)
    assert full[15].sum() > 300
    b = np.zeros_like(a); b[10, 50:70, 50:70] = True
    assert StructureSet.boolean(a, "intersect", b).sum() == 100


def test_fill_polygon_triangle():
    m = fill_polygon((20, 20), [0, 19, 0], [0, 0, 19])
    assert 150 < m.sum() < 230
