"""Beam's eye view (DRR, structures, jaws and MLC, with drag editing) and a 3D model view of patient and beams."""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QImage, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QTabWidget, QWidget
from scipy import ndimage

from ..core.beams import LEAF_EDGES, SAD, Frame
from .overlays import BEAM_COLORS


def _density(state):
    key = (id(state.ss), state.ss.version, state.density_version)
    if getattr(state, "_dens_key", None) != key:
        state._dens = state.ss.density(); state._dens_key = key
    return state._dens


class BEVView(QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.setMouseTracking(True); self.setMinimumSize(160, 140)
        self._cache = {}
        self._drag = None
        self.show_drr = True
        state.changed.connect(lambda w: self.update())

    def _beam(self):
        st = self.state
        if st.plan is None or not st.plan.beams:
            return None, None
        b = st.plan.beam(st.cur_beam) or st.plan.beams[0]
        cps = b.control_points()
        return b, cps[min(st.cp_index, len(cps) - 1)] if b.kind == "ARC" else cps[0]

    def _extent(self, cp):
        half = max(150.0, max(abs(cp.x1), abs(cp.x2), abs(cp.y1), abs(cp.y2)) + 60)
        return float(np.ceil(half / 50.0) * 50.0)

    def mapping(self, cp):
        half = self._extent(cp)
        W, H = self.width(), self.height() - 40
        s = min(W, H) / (2 * half)
        cx, cy = W / 2, 34 + H / 2
        return s, (lambda u, v: QPointF(cx + u * s, cy - v * s)), (lambda px, py: ((px - cx) / s, (cy - py) / s))

    def _drr_and_outlines(self, b, cp):
        st = self.state
        half = self._extent(cp)
        key = (st.ss.version, st.density_version, tuple(np.round(b.iso, 1)), cp.gantry, cp.collimator, cp.couch, b.orientation, round(half))
        if key in self._cache:
            return self._cache[key]
        if len(self._cache) > 12:
            self._cache.clear()
        fr = Frame(cp, b.iso, b.orientation)
        n = 180
        us = np.linspace(-half, half, n, dtype=np.float32)
        U, V = np.meshgrid(us, us, indexing="xy")      # rows = v
        img = st.image
        dens = _density(st)
        corners = np.array([[e0, e1, e2] for e0 in img.extent()[0] for e1 in img.extent()[1] for e2 in img.extent()[2]])
        _, _, a = fr.project(corners)
        acc = np.zeros(U.shape, np.float32)
        org, sp = np.asarray(img.origin), np.asarray(img.spacing)
        step = max(3.0, (a.max() - a.min()) / 160)
        for aa in np.arange(max(1, a.min()), a.max(), step):
            p = fr.ray_point(U, V, np.full(U.shape, aa))
            ijk = (p - org) / sp
            acc += ndimage.map_coordinates(dens, [ijk[..., 2].ravel(), ijk[..., 1].ravel(), ijk[..., 0].ravel()], order=1, cval=0.0).reshape(U.shape)
        acc *= step
        # emphasise bone and air contrast like a radiograph
        if (acc > 0).any():
            lo, hi = np.percentile(acc[acc > 0], [2, 99.5])
            g = np.clip((acc - lo) / max(hi - lo, 1e-3), 0, 1) ** 0.8 * (acc > 0)
        else:
            g = acc
        g8 = np.clip(g * 255, 0, 255).astype(np.uint8)[::-1].copy()      # row 0 = top = +v
        qi = QImage(g8.data, n, n, n, QImage.Format_Grayscale8).copy()
        outlines = {}
        from skimage import measure
        for s in st.ss.structures:
            if not s.visible or not s.mask.any():
                continue
            k, j, i = np.nonzero(s.mask)
            stepv = max(1, len(k) // 60000)
            pts = img.index_to_world(np.column_stack([i[::stepv], j[::stepv], k[::stepv]]))
            pu, pv, _ = fr.project(pts)
            occ = np.zeros((n, n), np.float32)
            hh = 2 * half / (n - 1)
            ci = np.clip(np.round((pu + half) / hh).astype(int), 0, n - 1); ri = np.clip(np.round((pv + half) / hh).astype(int), 0, n - 1)
            occ[ri, ci] = 1
            occ = ndimage.binary_closing(ndimage.binary_dilation(occ > 0, iterations=1), iterations=2).astype(np.float32)
            outlines[s.name] = [np.column_stack([-half + c[:, 1] * hh, -half + c[:, 0] * hh]) for c in measure.find_contours(np.pad(occ, 1), 0.5)]
            outlines[s.name] = [o - hh for o in outlines[s.name]]
        res = (qi, outlines, half)
        self._cache[key] = res
        return res

    def paintEvent(self, ev):
        p = QPainter(self); p.fillRect(self.rect(), QColor(0, 0, 0)); p.setRenderHint(QPainter.Antialiasing)
        st = self.state
        b, cp = self._beam() if st.image is not None else (None, None)
        if b is None:
            p.setPen(QColor(150, 160, 175)); p.drawText(self.rect(), Qt.AlignCenter, "Beam's eye view\n\nAdd a beam in Planning ▸ Beams")
            p.end(); return
        s, S, _ = self.mapping(cp)
        qi, outlines, half = self._drr_and_outlines(b, cp)
        if self.show_drr:
            a, c = S(-half, half), S(half, -half)
            p.drawImage(QRectF(a, c), qi)
        for st_ in st.ss.structures:
            if st_.name in outlines:
                p.setPen(QPen(QColor(*st_.color), 1.6 if st_.is_target else 1.1))
                for o in outlines[st_.name]:
                    p.drawPolyline(QPolygonF([S(u, v) for u, v in o]))
        # MLC
        if cp.left is not None and cp.right is not None:
            p.setPen(QPen(QColor(25, 30, 38), 0.6)); p.setBrush(QBrush(QColor(120, 132, 150, 190)))
            for i, (e0, e1) in enumerate(zip(LEAF_EDGES[:-1], LEAF_EDGES[1:])):
                if e1 < -half or e0 > half:
                    continue
                l, r = float(cp.left[i]), float(cp.right[i])
                p.drawRect(QRectF(S(-half, e1), S(l, e0))); p.drawRect(QRectF(S(r, e1), S(half, e0)))
            p.setBrush(Qt.NoBrush)
        # jaws
        p.setPen(QPen(QColor(255, 215, 94), 2)); p.drawRect(QRectF(S(cp.x1, cp.y2), S(cp.x2, cp.y1)))
        # graticule
        p.setPen(QPen(QColor(255, 255, 255, 140), 1))
        p.drawLine(S(-half, 0), S(half, 0)); p.drawLine(S(0, -half), S(0, half))
        for t in np.arange(-np.floor(half / 10) * 10, half, 10):
            q = S(t, 0); p.drawLine(q + QPointF(0, -3 if t % 50 else -6), q + QPointF(0, 3 if t % 50 else 6))
            q = S(0, t); p.drawLine(q + QPointF(-3 if t % 50 else -6, 0), q + QPointF(3 if t % 50 else 6, 0))
        f = QFont(self.font()); f.setPointSizeF(9); f.setBold(True); p.setFont(f); p.setPen(QColor(232, 238, 245))
        p.drawText(8, 16, f"Beam's eye view · {b.name}")
        f.setBold(False); p.setFont(f); p.setPen(QColor(255, 179, 92))
        p.drawText(8, 31, f"Gantry {cp.gantry:.1f}°  Coll {cp.collimator:.1f}°  Couch {cp.couch:.1f}°  {b.energy}  {b.orientation}")
        p.setPen(QColor(160, 176, 194))
        p.drawText(8, self.height() - 8, f"X {cp.x1 / 10:.1f} / {cp.x2 / 10:.1f}  Y {cp.y1 / 10:.1f} / {cp.y2 / 10:.1f} cm · MLC {b.mlc_mode}"
                   + (f" · {b.mu:.0f} MU" if b.mu else "") + ("   drag jaws" + (" / leaves" if b.mlc_mode == "manual" else "")))
        p.end()

    # ------------------------------------------------------------------ dragging jaws and leaves
    def mousePressEvent(self, ev):
        b, cp = self._beam()
        if b is None or ev.button() != Qt.LeftButton:
            return
        s, S, inv = self.mapping(cp)
        u, v = inv(ev.position().x(), ev.position().y())
        tol = 6 / s
        for name, val, coord in (("x1", cp.x1, u), ("x2", cp.x2, u), ("y1", cp.y1, v), ("y2", cp.y2, v)):
            if abs(coord - val) < tol:
                self._drag = ("jaw", name); return
        if b.mlc_mode == "manual" and b.left is not None:
            self._drag = ("leaf",); self._leaf(b, u, v)

    def _leaf(self, b, u, v):
        i = int(np.searchsorted(LEAF_EDGES, v) - 1)
        if 0 <= i < len(b.left):
            if abs(u - b.left[i]) <= abs(u - b.right[i]):
                b.left[i] = min(round(u), b.right[i])
            else:
                b.right[i] = max(round(u), b.left[i])

    def mouseMoveEvent(self, ev):
        b, cp = self._beam()
        if b is None:
            return
        s, S, inv = self.mapping(cp)
        u, v = inv(ev.position().x(), ev.position().y())
        if self._drag is None:
            tol = 6 / s
            near = any(abs(c - val) < tol for c, val in ((u, cp.x1), (u, cp.x2), (v, cp.y1), (v, cp.y2)))
            self.setCursor(Qt.SizeAllCursor if near else Qt.ArrowCursor); return
        if self._drag[0] == "jaw":
            name = self._drag[1]; val = float(round(u if name[0] == "x" else v))
            lo, hi = (-200, getattr(b, name[0] + "2")) if name.endswith("1") else (getattr(b, name[0] + "1"), 200)
            setattr(b, name, float(np.clip(val, lo, hi)))
        else:
            self._leaf(b, u, v)
        b.cps = []
        if self.state.plan:
            self.state.plan.beam_dose.pop(b.name, None)
        self.update()

    def mouseReleaseEvent(self, ev):
        if self._drag is not None:
            self._drag = None
            self.state.changed.emit("plan")


class Model3DView(QWidget):
    """Simple 3D model: patient outline rings, structures and divergent beams (software rendering)."""

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.yaw, self.pitch, self.zoom = -0.6, 0.35, 1.0
        self._drag = None
        self._rings = None
        self.setMinimumSize(160, 140)
        state.changed.connect(self._changed)

    def _changed(self, w):
        if w in ("image", "structures"):
            self._rings = None
        self.update()

    def _build_rings(self):
        st = self.state
        from skimage import measure
        img = st.image
        rings = []
        nz = img.shape[0]
        step = max(1, nz // 40)
        for s in st.ss.structures:
            if not s.visible or not s.mask.any():
                continue
            ks = np.where(s.mask.any(axis=(1, 2)))[0]
            st_k = step if s.type == "EXTERNAL" else max(1, step // 2)
            for k in ks[::st_k]:
                for c in measure.find_contours(np.pad(s.mask[k].astype(np.float32), 1), 0.5):
                    c = c[::max(1, len(c) // 60)] - 1
                    pts = np.column_stack([img.origin[0] + c[:, 1] * img.spacing[0], img.origin[1] + c[:, 0] * img.spacing[1], np.full(len(c), img.origin[2] + k * img.spacing[2])])
                    rings.append((s, pts))
        self._rings = rings

    def _proj(self):
        st = self.state
        e = st.image.extent()
        centre = np.array([(a + b) / 2 for a, b in e])
        if st.plan and st.plan.beams:
            centre = st.plan.beams[0].iso
        R = max(b - a for a, b in e)
        cy, sy, cp_, sp_ = np.cos(self.yaw), np.sin(self.yaw), np.cos(self.pitch), np.sin(self.pitch)
        # view: patient x right, patient z up (head), y into the screen, then rotate
        M = np.array([[cy, sy, 0], [0, 0, 1], [sy, -cy, 0]], float)
        P = np.array([[1, 0, 0], [0, cp_, -sp_], [0, sp_, cp_]]) @ M
        s = min(self.width(), self.height()) / (R * 1.9) * self.zoom
        W2, H2 = self.width() / 2, self.height() / 2

        def f(pts):
            q = (np.atleast_2d(pts) - centre) @ P.T
            return np.column_stack([W2 + q[:, 0] * s, H2 - q[:, 1] * s]), q[:, 2]
        return f

    def paintEvent(self, ev):
        p = QPainter(self); p.fillRect(self.rect(), QColor(14, 18, 24)); p.setRenderHint(QPainter.Antialiasing)
        st = self.state
        if st.image is None:
            p.end(); return
        if self._rings is None:
            self._build_rings()
        f = self._proj()
        for s, pts in self._rings:
            xy, _ = f(pts)
            col = QColor(*s.color); col.setAlpha(70 if s.type == "EXTERNAL" else 170)
            p.setPen(QPen(col, 1.0))
            p.drawPolyline(QPolygonF([QPointF(*q) for q in xy] + [QPointF(*xy[0])]))
        if st.plan:
            for bi, b in enumerate(st.plan.beams):
                if not b.visible:
                    continue
                col = QColor(*BEAM_COLORS[bi % len(BEAM_COLORS)]); cur = b.name == st.cur_beam
                cps = b.control_points()
                if b.kind == "ARC":
                    path = [b.iso + Frame(c, b.iso, b.orientation).source for c in cps]
                    xy, _ = f(np.array(path)); c2 = QColor(col); c2.setAlpha(160); p.setPen(QPen(c2, 1.2))
                    p.drawPolyline(QPolygonF([QPointF(*q) for q in xy]))
                    cps = [cps[min(st.cp_index, len(cps) - 1)]] if cur else [cps[0]]
                for cp in cps:
                    fr = Frame(cp, b.iso, b.orientation)
                    src = b.iso + fr.source
                    far = SAD + 150
                    corners = [fr.ray_point(np.array(u), np.array(v), np.array(far)) for u, v in ((cp.x1, cp.y1), (cp.x2, cp.y1), (cp.x2, cp.y2), (cp.x1, cp.y2))]
                    xs, _ = f(np.array([src] + corners))
                    fill = QColor(col); fill.setAlpha(55 if cur else 25)
                    p.setPen(QPen(QColor(col.red(), col.green(), col.blue(), 220 if cur else 120), 1.3 if cur else 0.8))
                    for i in range(4):
                        p.setBrush(QBrush(fill))
                        p.drawPolygon(QPolygonF([QPointF(*xs[0]), QPointF(*xs[1 + i]), QPointF(*xs[1 + (i + 1) % 4])]))
                    p.setBrush(Qt.NoBrush)
                    p.drawPolygon(QPolygonF([QPointF(*xs[k]) for k in range(1, 5)]))
                    iso_xy, _ = f(b.iso)
                    p.setPen(QPen(col, 1, Qt.DashLine)); p.drawLine(QPointF(*xs[0]), QPointF(*iso_xy[0]))
                    p.setPen(col); p.drawText(QPointF(*xs[0]) + QPointF(4, -4), b.name)
            if st.plan.beams:
                q, _ = f(st.plan.beams[0].iso)
                p.setPen(QPen(QColor(255, 80, 80), 2)); p.drawEllipse(QPointF(*q[0]), 3, 3)
        p.setPen(QColor(232, 238, 245)); fnt = QFont(self.font()); fnt.setBold(True); fnt.setPointSizeF(9); p.setFont(fnt)
        p.drawText(8, 16, "3D model"); fnt.setBold(False); p.setFont(fnt); p.setPen(QColor(150, 162, 178))
        p.drawText(8, self.height() - 8, "drag = rotate, wheel = zoom")
        p.end()

    def mousePressEvent(self, ev):
        self._drag = ev.position()

    def mouseMoveEvent(self, ev):
        if self._drag is None:
            return
        d = ev.position() - self._drag; self._drag = ev.position()
        self.yaw += d.x() * 0.01; self.pitch = float(np.clip(self.pitch + d.y() * 0.01, -1.5, 1.5)); self.update()

    def mouseReleaseEvent(self, ev):
        self._drag = None

    def wheelEvent(self, ev):
        self.zoom = float(np.clip(self.zoom * (1.12 if ev.angleDelta().y() > 0 else 1 / 1.12), 0.3, 8)); self.update()


def _box(c, size, R=np.eye(3)):
    """8 corners and 6 faces (index lists) of a box centred at c with edge lengths size, rotated by R."""
    hx, hy, hz = np.asarray(size) / 2
    corners = np.array([[sx * hx, sy * hy, sz * hz] for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]) @ R.T + c
    faces = [[0, 1, 3, 2], [4, 5, 7, 6], [0, 1, 5, 4], [2, 3, 7, 6], [0, 2, 6, 4], [1, 3, 7, 5]]
    return corners, faces


def _cyl(c, r, length, axis, n=28, R=np.eye(3)):
    """Corners and faces of a cylinder (axis 0/1/2 = X/Y/Z of the room)."""
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    ring = np.zeros((n, 3)); o = [i for i in range(3) if i != axis]
    ring[:, o[0]] = r * np.cos(t); ring[:, o[1]] = r * np.sin(t)
    a = np.zeros(3); a[axis] = length / 2
    pts = np.vstack([ring - a, ring + a]) @ R.T + c
    faces = [[k, (k + 1) % n, n + (k + 1) % n, n + k] for k in range(n)] + [list(range(n)), list(range(2 * n - 1, n - 1, -1))]
    return pts, faces


class RoomView(QWidget):
    """Treatment room in IEC fixed coordinates (X right, Y towards the gantry, Z up; isocentre at the origin):
    linac with rotating gantry and collimator, couch with its rotation, the patient and the current beam."""

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.yaw, self.pitch, self.zoom = 0.75, 0.32, 1.9
        self._drag = None
        self._body = None
        self.setMinimumSize(160, 140)
        state.changed.connect(self._changed)

    def _changed(self, w):
        if w in ("image", "structures"):
            self._body = None
        self.update()

    def _body_rings(self):
        st = self.state
        from skimage import measure
        img = st.image
        rings = []
        for s in st.ss.structures:
            if not s.mask.any() or not (s.type == "EXTERNAL" or s.is_target or "lung" in s.name.lower()):
                continue
            ks = np.where(s.mask.any(axis=(1, 2)))[0]
            for k in ks[::max(1, len(ks) // (30 if s.type == "EXTERNAL" else 14))]:
                for c in measure.find_contours(np.pad(s.mask[k].astype(np.float32), 1), 0.5):
                    c = c[::max(1, len(c) // 48)] - 1
                    rings.append((s, np.column_stack([img.origin[0] + c[:, 1] * img.spacing[0], img.origin[1] + c[:, 0] * img.spacing[1],
                                                      np.full(len(c), img.origin[2] + k * img.spacing[2])])))
        self._body = rings

    def _proj(self):
        cy, sy, cp_, sp_ = np.cos(self.yaw), np.sin(self.yaw), np.cos(self.pitch), np.sin(self.pitch)
        # camera: rotate about Z (yaw), then tilt (pitch); screen x right, screen y up, depth = third row
        Rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]])
        Rx = np.array([[1, 0, 0], [0, cp_, sp_], [0, -sp_, cp_]])
        M = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]]) @ Rx @ Rz      # (x, y, z) -> (screen x, screen y, depth)
        s = min(self.width(), self.height()) / 4200.0 * self.zoom
        W2, H2 = self.width() / 2, self.height() * 0.55

        def f(pts):
            q = np.atleast_2d(pts) @ M.T
            return np.column_stack([W2 + q[:, 0] * s, H2 - q[:, 1] * s]), q[:, 2]
        return f

    def paintEvent(self, ev):
        from ..core.beams import ORIENT, SAD, Frame, _rz
        p = QPainter(self); p.fillRect(self.rect(), QColor(22, 27, 34)); p.setRenderHint(QPainter.Antialiasing)
        st = self.state
        f = self._proj()
        b = cp = None
        if st.plan and st.plan.beams:
            b = st.plan.beam(st.cur_beam) or st.plan.beams[0]
            cps = b.control_points(); cp = cps[min(st.cp_index, len(cps) - 1)] if b.kind == "ARC" else cps[0]
        g = cp.gantry if cp else 0.0; coll = cp.collimator if cp else 0.0; couch = cp.couch if cp else 0.0
        G = np.array([[np.cos(np.radians(g)), 0, np.sin(np.radians(g))], [0, 1, 0], [-np.sin(np.radians(g)), 0, np.cos(np.radians(g))]])
        polys = []        # (depth, points2d, colour)

        def add(corners, faces, col, alpha=255):
            xy, z = f(corners)
            for fc in faces:
                c = QColor(*col); c.setAlpha(alpha)
                # simple shading from the face normal
                v = corners[fc]
                nrm = np.cross(v[1] - v[0], v[2] - v[0]); nrm /= (np.linalg.norm(nrm) + 1e-9)
                c = c.lighter(int(100 + 25 * abs(nrm[2]) + 10 * abs(nrm[0])))
                polys.append((float(z[fc].mean()), xy[fc], c))
        # floor, gantry stand, drum, arm, head and imager
        add(*_box(np.array([0, -400, -1310]), (4000, 5000, 20)), (52, 58, 68))
        add(*_box(np.array([0, 1750, -100]), (2200, 700, 2400)), (205, 210, 218))
        add(*_cyl(np.array([0, 1350, 0]), 950, 120, 1, 36, G), (190, 196, 205))
        add(*_box(np.array([0, 850, 0]) + G @ np.array([0, 0, 1120]), (560, 900, 300), G), (225, 228, 233))
        Hc = G @ np.array([0, 0, 1180])
        add(*_box(Hc, (620, 620, 420), G), (235, 237, 240))
        Rc = G @ _rz(-coll)
        add(*_cyl(G @ np.array([0, 0, 900]), 260, 160, 2, 28, Rc), (170, 178, 190))
        add(*_box(G @ np.array([0, 0, -560]), (430, 430, 40), G), (70, 80, 96))
        add(*_box(G @ np.array([0, 450, -560]), (90, 600, 60), G), (150, 156, 166))
        # couch (rotates about the vertical axis through the isocentre)
        Rcouch = _rz(couch)
        iso = b.iso if b is not None else (np.array(st.cursor) if st.image is not None else np.zeros(3))
        back = 0.0
        if st.image is not None and st.ss is not None and st.ss.external() is not None:
            ext = st.ss.external().mask
            js = np.where(ext.any(axis=(0, 2)))[0]
            back = st.image.origin[1] + js[-1] * st.image.spacing[1] - iso[1]
        top = -back - 30
        add(*_box(Rcouch @ np.array([0, -700, top]), (530, 2100, 50), Rcouch), (40, 44, 52))
        add(*_box(np.array([0, -1300, (top - 1310) / 2]), (450, 600, max(50, top + 1290))), (180, 186, 196))
        polys.sort(key=lambda t: t[0])
        for _, xy, c in polys:
            p.setPen(QPen(QColor(30, 34, 40, 160), 0.6)); p.setBrush(c)
            p.drawPolygon(QPolygonF([QPointF(*q) for q in xy]))
        # patient (rings), transformed patient -> room
        if st.image is not None:
            if self._body is None:
                self._body_rings()
            orient = b.orientation if b is not None else "HFS"
            P = Rcouch @ ORIENT.get(orient, ORIENT["HFS"])
            for s, pts in self._body:
                xy, _ = f((pts - iso) @ P.T)
                c = QColor(*s.color); c.setAlpha(230)
                if s.type == "EXTERNAL":
                    c = QColor(245, 210, 185, 210)
                fill = QColor(c); fill.setAlpha(28 if s.type == "EXTERNAL" else 60)
                p.setPen(QPen(c, 1.4)); p.setBrush(fill)
                p.drawPolygon(QPolygonF([QPointF(*q) for q in xy]))
                p.setBrush(Qt.NoBrush)
        # beam from the source through the jaws
        if cp is not None:
            fr = Frame(cp, b.iso, b.orientation)
            P = Rcouch @ ORIENT.get(b.orientation, ORIENT["HFS"])
            src = fr.source @ P.T
            far = SAD + 250
            corners = [(fr.ray_point(np.array(u), np.array(v), np.array(far)) - b.iso) @ P.T for u, v in ((cp.x1, cp.y1), (cp.x2, cp.y1), (cp.x2, cp.y2), (cp.x1, cp.y2))]
            xs, _ = f(np.array([src] + corners))
            p.setPen(QPen(QColor(255, 170, 60, 220), 1.2))
            for i in range(4):
                p.setBrush(QColor(255, 160, 50, 45))
                p.drawPolygon(QPolygonF([QPointF(*xs[0]), QPointF(*xs[1 + i]), QPointF(*xs[1 + (i + 1) % 4])]))
            o, _ = f(np.zeros(3))
            p.setPen(QPen(QColor(255, 80, 80), 2)); p.drawEllipse(QPointF(*o[0]), 3, 3)
        # lasers through the isocentre
        p.setPen(QPen(QColor(60, 220, 90, 150), 1))
        for a_, b_ in (([-1800, 0, 0], [1800, 0, 0]), ([0, -2500, 0], [0, 1300, 0]), ([0, 0, -1300], [0, 0, 1300])):
            xy, _ = f(np.array([a_, b_])); p.drawLine(QPointF(*xy[0]), QPointF(*xy[1]))
        fnt = QFont(self.font()); fnt.setBold(True); fnt.setPointSizeF(9); p.setFont(fnt); p.setPen(QColor(232, 238, 245))
        p.drawText(8, 16, "Room view")
        fnt.setBold(False); p.setFont(fnt); p.setPen(QColor(255, 179, 92))
        p.drawText(8, 31, f"Gantry {g:.1f}°  Collimator {coll:.1f}°  Couch {couch:.1f}°" + (f"  ·  {b.name} ({b.orientation})" if b else ""))
        p.setPen(QColor(150, 162, 178)); p.drawText(8, self.height() - 8, "drag = rotate, wheel = zoom · generic linac, not a real machine")
        p.end()

    def mousePressEvent(self, ev):
        self._drag = ev.position()

    def mouseMoveEvent(self, ev):
        if self._drag is None:
            return
        d = ev.position() - self._drag; self._drag = ev.position()
        self.yaw += d.x() * 0.01; self.pitch = float(np.clip(self.pitch + d.y() * 0.01, -0.2, 1.5)); self.update()

    def mouseReleaseEvent(self, ev):
        self._drag = None

    def wheelEvent(self, ev):
        self.zoom = float(np.clip(self.zoom * (1.12 if ev.angleDelta().y() > 0 else 1 / 1.12), 0.4, 6)); self.update()


class BeamViews(QTabWidget):
    """Fourth image area: beam's eye view and 3D model."""

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.bev = BEVView(state); self.model = Model3DView(state); self.room = RoomView(state)
        self.addTab(self.bev, "BEV"); self.addTab(self.model, "3D"); self.addTab(self.room, "Room")
        self.setTabPosition(QTabWidget.South)
        self.setDocumentMode(True)
        self.setMinimumSize(160, 140)
