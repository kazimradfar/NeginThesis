"""Slice view (transverse, coronal, sagittal): CT, structures, dose and beams, with navigation and contouring tools."""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from ..core.structures import disc_on_slice, fill_polygon

TITLES = {"axial": "Transverse", "coronal": "Coronal", "sagittal": "Sagittal"}
# (u axis, v axis, normal axis) as indices into (x, y, z); v_sign = +1 draws v downwards (axial y), -1 upwards (z)
AXES = {"axial": (0, 1, 2, 1), "coronal": (0, 2, 1, -1), "sagittal": (1, 2, 0, -1)}
LABELS = {"axial": ("R", "L", "A", "P"), "coronal": ("R", "L", "H", "F"), "sagittal": ("A", "P", "H", "F")}


class SliceView(QWidget):
    activated = Signal(object)          # emitted on mouse press (to make this the focused view)

    def __init__(self, state, view, parent=None):
        super().__init__(parent)
        self.state, self.view = state, view
        self.zoom, self.pan = 1.0, QPointF(0, 0)
        self._img_cache = None
        self._ct_key = None
        self._ct_qimage = None
        self._contour_cache = {}
        self._drag = None
        self._poly: list = []
        self._ruler = None
        self._mouse = None
        self.overlays = []              # callables (painter, view) for dose / beams
        self.setMouseTracking(True)
        self.setMinimumSize(160, 140)
        self.setFocusPolicy(Qt.ClickFocus)
        state.changed.connect(self._on_change)

    # ------------------------------------------------------------------ geometry
    def _on_change(self, what):
        if what in ("image",):
            self.zoom, self.pan = 1.0, QPointF(0, 0)
            self._contour_cache.clear(); self._ct_key = None
        if what == "structures":
            self._contour_cache.clear()
        self.update()

    def _ax(self):
        return AXES[self.view]

    def _bounds(self):
        ext = self.state.image.extent()
        u, v, _, _ = self._ax()
        return ext[u], ext[v]

    def mapping(self):
        """(scale px/mm, function world (u, v) -> screen QPointF, inverse)."""
        (u0, u1), (v0, v1) = self._bounds()
        W, H = self.width(), self.height() - 4
        s = min(W / (u1 - u0), H / (v1 - v0)) * 0.94 * self.zoom
        sgn = self._ax()[3]
        cx, cy = W / 2 + self.pan.x(), H / 2 + 2 + self.pan.y()
        um, vm = (u0 + u1) / 2, (v0 + v1) / 2

        def to_screen(u, v):
            return QPointF(cx + (u - um) * s, cy + sgn * (v - vm) * s)

        def to_world(px, py):
            return um + (px - cx) / s, vm + sgn * (py - cy) / s
        return s, to_screen, to_world

    def slice_index(self):
        img = self.state.image
        n = self._ax()[2]
        idx = int(round((self.state.cursor[n] - img.origin[n]) / img.spacing[n]))
        return int(np.clip(idx, 0, img.shape[2 - n] - 1))

    def world_point(self, px, py):
        _, _, inv = self.mapping()
        u, v = inv(px, py)
        p = np.array(self.state.cursor, float)
        a = self._ax()
        p[a[0]], p[a[1]] = u, v
        return p

    # ------------------------------------------------------------------ painting
    def _ct_image(self):
        st = self.state
        idx = self.slice_index()
        key = (id(st.image), self.view, idx, st.window)
        if key == self._ct_key:
            return self._ct_qimage
        arr, _ = st.image.slice(self.view, st.cursor[self._ax()[2]])
        if self.view != "axial":
            arr = arr[::-1]                       # superior at the top
        lev, wid = st.window
        g = np.clip((arr - (lev - wid / 2)) / wid * 255.0, 0, 255).astype(np.uint8)
        g = np.ascontiguousarray(g)
        q = QImage(g.data, g.shape[1], g.shape[0], g.strides[0], QImage.Format_Grayscale8).copy()
        self._ct_key, self._ct_qimage = key, q
        return q

    def paintEvent(self, ev):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0))
        st = self.state
        if st.image is None:
            p.setPen(QColor(150, 160, 175))
            p.drawText(self.rect(), Qt.AlignCenter, "No patient loaded\nFile ▸ Import DICOM…  or  File ▸ Load phantom")
            p.end(); return
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.setRenderHint(QPainter.Antialiasing)
        s, S, _ = self.mapping()
        (u0, u1), (v0, v1) = self._bounds()
        a, b = S(u0, v0), S(u1, v1)
        target = QRectF(min(a.x(), b.x()), min(a.y(), b.y()), abs(b.x() - a.x()), abs(b.y() - a.y()))
        p.drawImage(target, self._ct_image())
        for ov in self.overlays:
            ov(p, self)
        self._draw_structures(p, S)
        self._draw_cursor(p, S)
        self._draw_tools(p, S, s)
        self._draw_labels(p, s)
        p.end()

    def _draw_structures(self, p, S):
        st = self.state
        if st.ss is None:
            return
        idx = self.slice_index()
        for s in st.ss.structures:
            if not s.visible:
                continue
            key = (st.ss.version, s.name, idx)
            cs = self._contour_cache.get(key)
            if cs is None:
                cs = st.ss.contours(s.name, self.view, idx)
                self._contour_cache[key] = cs
            if not cs:
                continue
            w = 2.4 if s.name == st.active else 1.4
            p.setPen(QPen(QColor(*s.color), w))
            p.setBrush(Qt.NoBrush)
            for c in cs:
                if len(c) < 2:
                    continue
                p.drawPolyline(QPolygonF([S(float(u), float(v)) for u, v in c[::1 if len(c) < 400 else 2]]))

    def _draw_cursor(self, p, S):
        c = self.state.cursor
        a = self._ax()
        pt = S(c[a[0]], c[a[1]])
        p.setPen(QPen(QColor(255, 225, 90, 140), 1, Qt.DashLine))
        p.drawLine(QPointF(pt.x(), 0), QPointF(pt.x(), self.height()))
        p.drawLine(QPointF(0, pt.y()), QPointF(self.width(), pt.y()))

    def _draw_tools(self, p, S, s):
        st = self.state
        if st.tool in ("brush", "eraser") and self._mouse is not None:
            r = st.brush_mm * s
            p.setPen(QPen(QColor(255, 120, 120) if st.tool == "eraser" else QColor(120, 255, 140), 1.2))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(self._mouse, r, r)
        if self._poly:
            p.setPen(QPen(QColor(120, 255, 140), 1.5))
            pts = [S(u, v) for u, v in self._poly]
            if self._mouse is not None:
                pts.append(self._mouse)
            p.drawPolyline(QPolygonF(pts))
            for q in pts[:-1]:
                p.drawEllipse(q, 2.5, 2.5)
        if self._ruler:
            (ua, va), (ub, vb) = self._ruler
            A, B = S(ua, va), S(ub, vb)
            p.setPen(QPen(QColor(255, 230, 120), 1.6)); p.drawLine(A, B)
            d = float(np.hypot(ub - ua, vb - va))
            p.drawText(B + QPointF(6, -6), f"{d / 10:.2f} cm")

    def _draw_labels(self, p, s):
        st = self.state
        f = QFont(self.font()); f.setPointSizeF(9); p.setFont(f)
        a = self._ax()
        n = a[2]
        pos = st.cursor[n]
        axis = "xyz"[n]
        idx = self.slice_index()
        p.setPen(QColor(232, 238, 245))
        fb = QFont(f); fb.setBold(True); p.setFont(fb)
        p.drawText(8, 16, f"{TITLES[self.view]}")
        p.setFont(f)
        p.drawText(8, 31, f"{axis} = {pos / 10:.2f} cm   slice {idx + 1}/{st.image.shape[2 - n]}")
        lev, wid = st.window
        p.setPen(QColor(160, 176, 194))
        p.drawText(8, self.height() - 8, f"W {wid:.0f}  L {lev:.0f}   zoom {self.zoom:.1f}×")
        L = LABELS[self.view]
        p.setPen(QColor(255, 215, 94))
        p.drawText(4, self.height() // 2, L[0]); p.drawText(self.width() - 12, self.height() // 2, L[1])
        p.drawText(self.width() // 2 - 3, 14, L[2]); p.drawText(self.width() // 2 - 3, self.height() - 22, L[3])
        # 5 cm scale bar
        x1 = self.width() - 12; x0 = x1 - 50 * s; y = self.height() - 12
        p.setPen(QPen(QColor(220, 228, 236), 2)); p.drawLine(QPointF(x0, y), QPointF(x1, y))
        p.drawText(QPointF((x0 + x1) / 2 - 12, y - 4), "5 cm")

    # ------------------------------------------------------------------ interaction
    def wheelEvent(self, ev):
        if self.state.image is None:
            return
        if ev.modifiers() & Qt.ControlModifier:
            f = 1.15 if ev.angleDelta().y() > 0 else 1 / 1.15
            self.zoom = float(np.clip(self.zoom * f, 0.3, 20))
            self.update(); return
        n = self._ax()[2]
        step = self.state.image.spacing[n] * (5 if ev.modifiers() & Qt.ShiftModifier else 1)
        c = np.array(self.state.cursor); c[n] += step * (1 if ev.angleDelta().y() > 0 else -1)
        self.state.set_cursor(c)

    def mousePressEvent(self, ev):
        if self.state.image is None:
            return
        self.activated.emit(self)
        pos = ev.position()
        tool = self.state.tool
        if ev.button() == Qt.MiddleButton or (ev.button() == Qt.LeftButton and tool == "pan"):
            self._drag = ("pan", pos, QPointF(self.pan)); return
        if ev.button() == Qt.RightButton and tool not in ("polygon",):
            self._drag = ("window", pos, self.state.window); return
        if ev.button() == Qt.RightButton and tool == "polygon":
            self._finish_polygon(subtract=bool(ev.modifiers() & Qt.ShiftModifier)); return
        if ev.button() != Qt.LeftButton:
            return
        if tool == "zoom":
            self._drag = ("zoom", pos, self.zoom)
        elif tool == "window":
            self._drag = ("window", pos, self.state.window)
        elif tool == "ruler":
            _, _, inv = self.mapping(); u, v = inv(pos.x(), pos.y()); self._ruler = [(u, v), (u, v)]; self._drag = ("ruler",)
        elif tool in ("brush", "eraser"):
            if self._start_brush():
                self._drag = ("brush",); self._paint(pos)
        elif tool == "polygon":
            _, _, inv = self.mapping(); self._poly.append(inv(pos.x(), pos.y())); self.update()
        else:
            self._drag = ("cursor",); self.state.set_cursor(self.world_point(pos.x(), pos.y()))

    def mouseDoubleClickEvent(self, ev):
        if self.state.tool == "polygon" and len(self._poly) >= 3:
            self._finish_polygon(subtract=bool(ev.modifiers() & Qt.ShiftModifier))

    def mouseMoveEvent(self, ev):
        pos = ev.position()
        self._mouse = pos
        st = self.state
        if st.image is not None:
            wp = self.world_point(pos.x(), pos.y())
            hu = st.image.value_at(wp)
            under = [s.name for s in (st.ss.structures if st.ss else []) if _inside(s.mask, st.image, wp)]
            st.message.emit(f"x {wp[0] / 10:.2f}  y {wp[1] / 10:.2f}  z {wp[2] / 10:.2f} cm   HU {hu:.0f}   {', '.join(under)}")
        d = self._drag
        if d is None:
            if st.tool in ("brush", "eraser", "polygon"):
                self.update()
            return
        if d[0] == "pan":
            self.pan = d[2] + (pos - d[1]); self.update()
        elif d[0] == "zoom":
            self.zoom = float(np.clip(d[2] * np.exp(-(pos.y() - d[1].y()) / 150), 0.3, 20)); self.update()
        elif d[0] == "window":
            lev, wid = d[2]
            st.set_window(lev + (pos.y() - d[1].y()) * 2, wid + (pos.x() - d[1].x()) * 4)
        elif d[0] == "ruler":
            _, _, inv = self.mapping(); self._ruler[1] = inv(pos.x(), pos.y()); self.update()
        elif d[0] == "brush":
            self._paint(pos)
        elif d[0] == "cursor":
            st.set_cursor(self.world_point(pos.x(), pos.y()))

    def mouseReleaseEvent(self, ev):
        if self._drag and self._drag[0] == "brush":
            self.state.end_edit()
        self._drag = None

    def leaveEvent(self, ev):
        self._mouse = None; self.update()

    def keyPressEvent(self, ev):
        n = self._ax()[2]
        if self.state.image is None:
            return
        if ev.key() in (Qt.Key_Up, Qt.Key_PageUp, Qt.Key_Down, Qt.Key_PageDown):
            sgn = 1 if ev.key() in (Qt.Key_Up, Qt.Key_PageUp) else -1
            c = np.array(self.state.cursor); c[n] += sgn * self.state.image.spacing[n]; self.state.set_cursor(c)
        elif ev.key() == Qt.Key_Escape:
            self._poly.clear(); self._ruler = None; self.update()

    # ------------------------------------------------------------------ contouring on this slice
    def _start_brush(self):
        st = self.state
        if not st.active or st.ss.get(st.active) is None:
            st.message.emit("Select the structure to edit in the Contouring panel first")
            return False
        st.begin_edit(st.active, "eraser" if st.tool == "eraser" else "brush")
        return True

    def _slice_view_of(self, mask):
        idx = self.slice_index()
        if self.view == "axial":
            return mask[idx]
        if self.view == "coronal":
            return mask[:, idx, :]
        return mask[:, :, idx]

    def _pix(self, u, v):
        """(row, col) in the slice array for world (u, v) of this view."""
        img = self.state.image
        a = self._ax()
        col = (u - img.origin[a[0]]) / img.spacing[a[0]]
        row = (v - img.origin[a[1]]) / img.spacing[a[1]]
        return row, col

    def _paint(self, pos):
        st = self.state
        s = st.ss.get(st.active)
        if s is None:
            return
        _, _, inv = self.mapping()
        u, v = inv(pos.x(), pos.y())
        row, col = self._pix(u, v)
        a = self._ax()
        img = st.image
        sl = self._slice_view_of(s.mask)
        disc = disc_on_slice(sl.shape, (row, col), (st.brush_mm / img.spacing[a[1]], st.brush_mm / img.spacing[a[0]]))
        if st.tool == "eraser":
            sl[disc] = False
        else:
            ext = st.ss.external()
            limit = self._slice_view_of(ext.mask) if (ext is not None and ext is not s) else None
            sl[disc if limit is None else (disc & limit)] = True
        st.ss.version += 1
        self._contour_cache.clear()
        self.update()

    def _finish_polygon(self, subtract=False):
        st = self.state
        if len(self._poly) < 3 or not self._start_brush():
            self._poly.clear(); self.update(); return
        s = st.ss.get(st.active)
        sl = self._slice_view_of(s.mask)
        rc = np.array([self._pix(u, v) for u, v in self._poly])
        inside = fill_polygon(sl.shape, rc[:, 1], rc[:, 0])
        if subtract:
            sl[inside] = False
        else:
            sl[inside] = True
        self._poly.clear()
        st.end_edit()


def _inside(mask, img, p):
    i, j, k = np.round(img.world_to_index(p)).astype(int)
    return 0 <= k < mask.shape[0] and 0 <= j < mask.shape[1] and 0 <= i < mask.shape[2] and bool(mask[k, j, i])
