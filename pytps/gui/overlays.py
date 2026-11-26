"""Overlays on the slice views: isodose lines / colour wash and divergent beam outlines."""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QPen, QPolygonF

from ..core.beams import SAD, Frame

ISODOSE = [(107, (255, 45, 85)), (105, (255, 140, 26)), (100, (255, 225, 77)), (95, (76, 217, 100)), (90, (46, 197, 255)),
           (80, (61, 123, 255)), (70, (130, 110, 255)), (50, (180, 107, 255)), (30, (120, 130, 150))]
BEAM_COLORS = [(255, 159, 67), (88, 166, 255), (61, 220, 151), (255, 107, 154), (201, 160, 255), (255, 215, 94), (92, 225, 230)]


class DoseOverlay:
    def __init__(self, state):
        self.state = state
        self.mode = "lines"         # lines, wash, off
        self.levels = {lv: True for lv, _ in ISODOSE}
        self._cache = {}

    def _plane(self, view):
        st = self.state
        plan, eng = st.plan, st.engine
        g = eng.grid
        key = (plan.version, view.view, round(float(st.cursor[view._ax()[2]]), 2))
        if key in self._cache:
            return self._cache[key]
        if len(self._cache) > 30:
            self._cache.clear()
        vol = g.to_volume(plan.dose)
        n = view._ax()[2]
        f = (st.cursor[n] - g.origin[n]) / g.spacing
        k0 = int(np.clip(np.floor(f), 0, vol.shape[2 - n] - 1)); k1 = min(k0 + 1, vol.shape[2 - n] - 1); t = float(np.clip(f - k0, 0, 1))
        take = (lambda k: vol[k]) if n == 2 else (lambda k: vol[:, k, :]) if n == 1 else (lambda k: vol[:, :, k])
        sl = take(k0) * (1 - t) + take(k1) * t
        u, v = view._ax()[0], view._ax()[1]
        res = (sl, g.origin[u], g.origin[v], g.spacing)
        self._cache[key] = res
        return res

    def __call__(self, p, view):
        st = self.state
        if self.mode == "off" or st.plan is None or st.plan.dose is None or st.engine is None:
            return
        sl, u0, v0, h = self._plane(view)
        rx = st.plan.rx.dose
        if rx <= 0 or not sl.any():
            return
        _, S, _ = view.mapping()
        if self.mode == "wash":
            from PySide6.QtGui import QImage
            f = sl / rx
            rgba = np.zeros(sl.shape + (4,), np.uint8)
            for lv, col in sorted(ISODOSE):
                m = f >= lv / 100
                rgba[m] = (*col, 110)
            img = QImage(rgba.data, sl.shape[1], sl.shape[0], sl.shape[1] * 4, QImage.Format_RGBA8888).copy()
            a = S(u0 - h / 2, v0 - h / 2); b = S(u0 + (sl.shape[1] - 0.5) * h, v0 + (sl.shape[0] - 0.5) * h)
            from PySide6.QtCore import QRectF
            tgt = QRectF(min(a.x(), b.x()), min(a.y(), b.y()), abs(b.x() - a.x()), abs(b.y() - a.y()))
            if view._ax()[3] < 0:
                img = img.mirrored(False, True)
            p.drawImage(tgt, img)
            return
        from skimage import measure
        for lv, col in ISODOSE:
            if not self.levels.get(lv, True):
                continue
            p.setPen(QPen(QColor(*col), 1.4))
            for c in measure.find_contours(sl, rx * lv / 100):
                pts = [S(u0 + q[1] * h, v0 + q[0] * h) for q in c[::1 if len(c) < 300 else 2]]
                p.drawPolyline(QPolygonF(pts))


def _pyramid_section(fr: Frame, cp, axis_n, c):
    """Intersection of the divergent field pyramid with the plane coordinate[axis_n] = c (patient coordinates)."""
    S = fr.iso + fr.source
    far = SAD + 700
    corners = [fr.ray_point(np.array(u), np.array(v), np.array(far)) for u, v in ((cp.x1, cp.y1), (cp.x2, cp.y1), (cp.x2, cp.y2), (cp.x1, cp.y2))]
    edges = [(S, q) for q in corners] + [(corners[i], corners[(i + 1) % 4]) for i in range(4)]
    pts = []
    for a, b in edges:
        da, db = a[axis_n] - c, b[axis_n] - c
        if da == db:
            continue
        if da * db <= 0:
            t = da / (da - db)
            pts.append(a + t * (b - a))
    return pts


class BeamOverlay:
    def __init__(self, state):
        self.state = state
        self.show = True

    def __call__(self, p, view):
        st = self.state
        if not self.show or st.plan is None or not st.plan.beams:
            return
        _, S, _ = view.mapping()
        ax = view._ax()
        n, c = ax[2], float(st.cursor[ax[2]])
        for bi, b in enumerate(st.plan.beams):
            if not b.visible:
                continue
            col = QColor(*BEAM_COLORS[bi % len(BEAM_COLORS)])
            cur = b.name == st.cur_beam
            cps = b.control_points()
            show = cps if b.kind != "ARC" else [cps[min(st.cp_index, len(cps) - 1)]] if cur else []
            if b.kind == "ARC":           # arc: central axes of all control points, faint
                col2 = QColor(col); col2.setAlpha(70 if cur else 40)
                p.setPen(QPen(col2, 1))
                for cp in cps[::max(1, len(cps) // 45)]:
                    fr = Frame(cp, b.iso, b.orientation)
                    s3 = b.iso + fr.source * 0.32
                    if abs(s3[n] - c) < 30 and abs(b.iso[n] - c) < 30:
                        p.drawLine(S(s3[ax[0]], s3[ax[1]]), S(b.iso[ax[0]], b.iso[ax[1]]))
            for cp in show:
                fr = Frame(cp, b.iso, b.orientation)
                pts = _pyramid_section(fr, cp, n, c)
                if len(pts) >= 3:
                    q = np.array([[pt[ax[0]], pt[ax[1]]] for pt in pts])
                    cen = q.mean(0); order = np.argsort(np.arctan2(q[:, 1] - cen[1], q[:, 0] - cen[0]))
                    poly = QPolygonF([S(*q[i]) for i in order])
                    fill = QColor(col); fill.setAlpha(38 if cur else 18)
                    p.setBrush(QBrush(fill)); edge = QColor(col); edge.setAlpha(230 if cur else 140)
                    p.setPen(QPen(edge, 2.0 if cur else 1.2)); p.drawPolygon(poly)
                    p.setBrush(Qt.NoBrush)
                # central axis (dashed) when it lies close to this plane
                src = b.iso + fr.source
                if abs(fr.axis[n]) < 0.2 and abs(b.iso[n] - c) < 40:
                    end = b.iso + fr.axis * 400
                    p.setPen(QPen(col, 1.2, Qt.DashLine))
                    p.drawLine(S(src[ax[0]], src[ax[1]]), S(end[ax[0]], end[ax[1]]))
                    lab = b.iso + fr.source * 0.2
                    p.setPen(col); p.drawText(S(lab[ax[0]], lab[ax[1]]) + QPointF(4, -4), f"{b.name}  G{cp.gantry:.0f}")
            # isocentre marker
            if abs(b.iso[n] - c) < 3:
                q = S(b.iso[ax[0]], b.iso[ax[1]])
                p.setPen(QPen(QColor(255, 80, 80), 2)); p.drawLine(q + QPointF(-7, 0), q + QPointF(7, 0)); p.drawLine(q + QPointF(0, -7), q + QPointF(0, 7))
