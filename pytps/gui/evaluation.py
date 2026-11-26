"""DVH plot and the Evaluation workspace: statistics, plan comparison, point doses, clinical goals and the PDF report."""
from __future__ import annotations

import datetime

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (QApplication, QComboBox, QFileDialog, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
                               QMenu, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from ..core.plan import dose_at, dvh


def render_image(draw, w=900, h=520, scale=2):
    """Render a plot (draw(painter, QRectF)) to a white high-resolution image for reports and theses."""
    img = QImage(int(w * scale), int(h * scale), QImage.Format_ARGB32)
    img.fill(QColor(255, 255, 255))
    p = QPainter(img); p.setRenderHint(QPainter.Antialiasing); p.scale(scale, scale)
    draw(p, QRectF(0, 0, w, h))
    p.end()
    img.setDotsPerMeterX(int(96 * scale / 0.0254)); img.setDotsPerMeterY(int(96 * scale / 0.0254))
    return img


class _PlotMenu:
    """Right-click menu of the DVH and profile plots: save image, copy image, export data."""

    def contextMenuEvent(self, ev):
        m = QMenu(self)
        m.addAction("Save image (PNG)…", self.save_image)
        m.addAction("Copy image", lambda: QApplication.clipboard().setImage(self.image()))
        m.addAction("Export data (CSV)…", self.save_csv)
        m.exec(ev.globalPos())

    def save_image(self, path=None):
        if not self.has_data():
            QMessageBox.information(self, self.KIND, "Calculate the dose first."); return
        if not path:
            path, _ = QFileDialog.getSaveFileName(self, f"Save {self.KIND} image", f"{self.FILE}_{self.state.plan.name}.png",
                                                  "PNG (*.png);;JPEG (*.jpg)")
        if path:
            self.image().save(path)
            self.state.message.emit(f"{self.KIND} image written: {path}")

    def save_csv(self, path=None):
        if not self.has_data():
            QMessageBox.information(self, self.KIND, "Calculate the dose first."); return
        if not path:
            path, _ = QFileDialog.getSaveFileName(self, f"Export {self.KIND} data", f"{self.FILE}_{self.state.plan.name}.csv", "CSV (*.csv)")
        if path:
            head, rows = self.table()
            import csv
            with open(path, "w", newline="", encoding="utf-8") as fh:
                wr = csv.writer(fh); wr.writerow(head); wr.writerows(rows)
            self.state.message.emit(f"{self.KIND} data written: {path} ({len(rows)} rows)")


def _cmp(state):
    c = state.compare
    return c if (c is not None and c is not state.plan and c.dose is not None and state.engine is not None
                 and len(c.dose) == len(state.engine.grid.pts)) else None


class DVHWidget(_PlotMenu, QWidget):
    KIND, FILE = "DVH", "DVH"

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.curves, self.cmp_curves = {}, {}
        self.setMinimumHeight(120)
        state.changed.connect(self._changed)

    def _changed(self, w):
        if w in ("dose", "structures", "image", "plans", "compare"):
            self.recompute()

    def recompute(self):
        st = self.state
        self.curves, self.cmp_curves = {}, {}
        if st.plan is not None and st.plan.dose is not None and st.engine is not None and len(st.plan.dose) == len(st.engine.grid.pts):
            cmp = _cmp(st)
            for s in st.ss.structures:
                if s.visible:
                    d = dvh(st.plan, st.engine, s.name)
                    if d:
                        self.curves[s.name] = (s.color, d)
                    if cmp is not None:
                        d2 = dvh(cmp, st.engine, s.name)
                        if d2:
                            self.cmp_curves[s.name] = (s.color, d2)
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self); p.fillRect(self.rect(), QColor(250, 251, 252)); p.setRenderHint(QPainter.Antialiasing)
        draw_dvh(p, QRectF(self.rect()), self.state, self.curves, self.cmp_curves)
        p.end()

    def has_data(self):
        return bool(self.curves)

    def image(self, w=900, h=520):
        st = self.state

        def draw(p, r):
            p.setPen(QColor(20, 24, 32)); f = QFont(); f.setPointSizeF(10); f.setBold(True); p.setFont(f)
            title = f"DVH · {st.plan.name} · Rx {st.plan.rx.dose:g} Gy / {st.plan.rx.fractions} fx"
            p.drawText(QPointF(r.left() + 48, r.top() + 16), title)
            draw_dvh(p, r.adjusted(0, 24, 0, 0), st, self.curves, self.cmp_curves)
        return render_image(draw, w, h)

    def table(self):
        """Cumulative DVH on a common dose axis: dose (Gy) and volume (%) of every shown structure (and compared plan)."""
        st = self.state
        cols = [(n, d) for n, (_, d) in self.curves.items()]
        if self.cmp_curves and st.compare is not None:
            cols += [(f"{n} [{st.compare.name}]", d) for n, (_, d) in self.cmp_curves.items()]
        dmax = max(float(d["dose"][-1]) for _, d in cols)
        step = 0.1 if st.plan.rx.dose >= 10 else 0.02
        axis = np.arange(0, dmax + step / 2, step)
        vols = [np.interp(axis, d["dose"], d["volume"], right=0.0) for _, d in cols]
        head = ["Dose (Gy)"] + [f"{n} volume (%)" for n, _ in cols]
        rows = [[f"{x:.2f}"] + [f"{v[i]:.3f}" for v in vols] for i, x in enumerate(axis)]
        return head, rows


def draw_dvh(p, rect, state, curves, cmp_curves):
    if not curves:
        p.setPen(QColor(120, 130, 145)); p.drawText(rect, Qt.AlignCenter, "DVH: calculate the dose (Planning ▸ Prescription ▸ Calculate dose)")
        return
    rx = state.plan.rx.dose
    allc = list(curves.values()) + list(cmp_curves.values())
    dmax = max(max(d["max"] for _, d in allc), rx) * 1.08
    L, R, T, B = rect.left() + 48, rect.right() - 175, rect.top() + 10, rect.bottom() - 26
    f = QFont(); f.setPointSizeF(8.5); p.setFont(f)
    step = 10 if dmax > 60 else 5 if dmax > 25 else 2
    for d in np.arange(0, dmax + 1e-6, step):
        x = L + (R - L) * d / dmax; p.setPen(QColor(222, 227, 233)); p.drawLine(QPointF(x, T), QPointF(x, B))
        p.setPen(QColor(90, 100, 115)); p.drawText(QPointF(x - 8, B + 14), f"{d:g}")
    for v in range(0, 101, 20):
        y = B - (B - T) * v / 100; p.setPen(QColor(222, 227, 233)); p.drawLine(QPointF(L, y), QPointF(R, y))
        p.setPen(QColor(90, 100, 115)); p.drawText(QPointF(L - 26, y + 4), f"{v}")
    p.setPen(QPen(QColor(200, 150, 0), 1, Qt.DashLine)); xr = L + (R - L) * rx / dmax; p.drawLine(QPointF(xr, T), QPointF(xr, B))
    p.setPen(QColor(90, 100, 115)); p.drawText(QPointF((L + R) / 2 - 25, rect.bottom() - 2), "Dose (Gy)")
    p.save(); p.translate(rect.left() + 12, (T + B) / 2 + 25); p.rotate(-90); p.drawText(0, 0, "Volume (%)"); p.restore()

    def curve(col, d, dash):
        c = QColor(*col)
        if sum(col) > 600:
            c = c.darker(140)
        p.setPen(QPen(c, 1.4 if dash else 2, Qt.DashLine if dash else Qt.SolidLine))
        xs = L + (R - L) * d["dose"] / dmax; ys = B - (B - T) * d["volume"] / 100
        p.drawPolyline(QPolygonF([QPointF(x, y) for x, y in zip(xs, ys)]))
        return c
    for _, (col, d) in cmp_curves.items():
        curve(col, d, True)
    ly = T + 12
    for name, (col, d) in curves.items():
        c = curve(col, d, False)
        p.setPen(c); p.drawText(QPointF(R + 10, ly), f"{name}  {d['mean']:.1f} Gy"); ly += 15
    if cmp_curves and state.compare is not None:
        p.setPen(QColor(90, 100, 115)); p.drawText(QPointF(R + 10, ly + 6), f"dashed: {state.compare.name}")


class EvaluationPanel(QWidget):
    COLS = ["Structure", "cc", "Min", "Mean", "Max", "D98", "D95", "D50", "D2", "V95% Rx"]

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        lay = QVBoxLayout(self)
        self.summary = QLabel("No dose yet."); self.summary.setWordWrap(True); lay.addWidget(self.summary)
        row = QHBoxLayout(); row.addWidget(QLabel("Compare with"))
        self.cmpbox = QComboBox(); self.cmpbox.currentIndexChanged.connect(self._set_compare); row.addWidget(self.cmpbox, 1)
        lay.addLayout(row)
        self.table = QTableWidget(0, len(self.COLS)); self.table.setHorizontalHeaderLabels(self.COLS)
        self.table.verticalHeader().hide(); self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        lay.addWidget(self.table, 2)
        lay.addWidget(QLabel("Clinical goals"))
        self.goals = QTableWidget(0, 5); self.goals.setHorizontalHeaderLabels(["Structure", "Goal", "Limit", "Plan", "Compared"])
        self.goals.verticalHeader().hide(); self.goals.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.goals.horizontalHeader().setStretchLastSection(True); lay.addWidget(self.goals, 1)
        r2 = QHBoxLayout()
        for t, f in (("Add goal", self.add_goal), ("Delete goal", self.del_goal)):
            b = QPushButton(t); b.clicked.connect(f); r2.addWidget(b)
        lay.addLayout(r2)
        lay.addWidget(QLabel("Point doses"))
        self.points = QTableWidget(0, 4); self.points.setHorizontalHeaderLabels(["Point", "x, y, z (cm)", "Plan (Gy)", "Compared (Gy)"])
        self.points.verticalHeader().hide(); self.points.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch); self.points.setMaximumHeight(130)
        lay.addWidget(self.points)
        r3 = QHBoxLayout()
        for t, f in (("Point at crosshair", self.add_point), ("Clear points", self.clear_points), ("PDF report…", self.report)):
            b = QPushButton(t); b.clicked.connect(f); r3.addWidget(b)
        lay.addLayout(r3)
        r4 = QHBoxLayout(); r4.addWidget(QLabel("Export"))
        self.dvh_widget = None       # set by the main window
        for t, f, tip in (("Statistics CSV…", self.export, "Dose statistics table as CSV"),
                          ("DVH image…", lambda: self.dvh_widget and self.dvh_widget.save_image(), "DVH as a PNG image (white background, for reports)"),
                          ("DVH data…", lambda: self.dvh_widget and self.dvh_widget.save_csv(), "Cumulative DVH curves as CSV (dose in Gy, volume in %)")):
            b = QPushButton(t); b.setToolTip(tip); b.clicked.connect(f); r4.addWidget(b)
        lay.addLayout(r4)
        note = QLabel("Doses come from the educational pencil-beam model and generic beam data."); note.setWordWrap(True)
        note.setStyleSheet("color:#6b7785;font-size:11px"); lay.addWidget(note)
        self.goal_list = []          # (structure, metric, x, op, limit)
        state.changed.connect(lambda w: self.refresh() if w in ("dose", "structures", "plans", "compare", "image") else None)

    # ------------------------------------------------------------------ comparison
    def _fill_compare(self):
        st = self.state
        self.cmpbox.blockSignals(True); self.cmpbox.clear(); self.cmpbox.addItem("(none)")
        for p in st.plans:
            if p is not st.plan:
                self.cmpbox.addItem(p.name)
        self.cmpbox.setCurrentText(st.compare.name if (st.compare is not None and st.compare in st.plans) else "(none)")
        self.cmpbox.blockSignals(False)

    def _set_compare(self, i):
        st = self.state
        name = self.cmpbox.currentText()
        st.compare = next((p for p in st.plans if p.name == name and p is not st.plan), None)
        st.changed.emit("compare")

    # ------------------------------------------------------------------ statistics
    def rows(self, plan=None):
        st = self.state
        plan = plan or st.plan
        out = []
        if plan is None or plan.dose is None or st.engine is None or len(plan.dose) != len(st.engine.grid.pts):
            return out
        rx = plan.rx.dose
        for s in st.ss.structures:
            d = dvh(plan, st.engine, s.name)
            if d:
                out.append([s.name, d["cc"], d["min"], d["mean"], d["max"], d["D"](98), d["D"](95), d["D"](50), d["D"](2), d["V"](0.95 * rx)])
        return out

    def goal_value(self, plan, g):
        st = self.state
        if plan is None or plan.dose is None:
            return None
        d = dvh(plan, st.engine, g[0])
        if d is None:
            return None
        metric, x = g[1], g[2]
        return {"Dmean": d["mean"], "Dmax": d["max"], "Dmin": d["min"]}.get(metric) if metric in ("Dmean", "Dmax", "Dmin") else d["D"](x) if metric == "D" else d["V"](x)

    def refresh(self):
        st = self.state
        self._fill_compare()
        rows = self.rows()
        cmp = _cmp(st)
        crow = {r[0]: r for r in self.rows(cmp)} if cmp is not None else {}
        cols = self.COLS + (["Mean (cmp)", "D95 (cmp)", "Max (cmp)"] if cmp is not None else [])
        self.table.setColumnCount(len(cols)); self.table.setHorizontalHeaderLabels(cols)
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            vals = row + ([crow[row[0]][3], crow[row[0]][6], crow[row[0]][4]] if row[0] in crow else ([None] * 3 if cmp is not None else []))
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v if c == 0 else "–" if v is None else f"{v:.1f}" if c == 1 else f"{v:.2f}")
                if c:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if c >= len(self.COLS):
                    it.setForeground(QColor(110, 80, 200))
                self.table.setItem(r, c, it)
        p = st.plan
        if p is None or p.dose is None:
            self.summary.setText("No dose yet.")
        else:
            tot = sum(b.mu for b in p.beams)
            kind = {"sum": " (plan sum)", "imported": " (imported RT Dose)"}.get(p.kind, "")
            self.summary.setText(f"<b>{p.name}</b>{kind} · {p.rx.dose:g} Gy in {p.rx.fractions} fractions to {p.rx.target}"
                                 + (f" (normalised to {p.rx.method}) · {tot:.0f} MU per fraction" if p.beams else ""))
        # goals
        self.goals.setRowCount(len(self.goal_list))
        for r, g in enumerate(self.goal_list):
            v, vc = self.goal_value(p, g), self.goal_value(cmp, g) if cmp is not None else None
            txt = {"Dmean": "Dmean", "Dmax": "Dmax", "Dmin": "Dmin", "D": f"D{g[2]:g}%", "V": f"V{g[2]:g}Gy"}[g[1]]
            ok = None if v is None else (v <= g[4] if g[3] == "<=" else v >= g[4])
            unit = "%" if g[1] == "V" else "Gy"
            for c, t in enumerate([g[0], txt, f"{g[3]} {g[4]:g} {unit}", "–" if v is None else f"{v:.2f}", "–" if vc is None else f"{vc:.2f}"]):
                it = QTableWidgetItem(t)
                if c == 3 and ok is not None:
                    it.setForeground(QColor(20, 140, 70) if ok else QColor(200, 40, 40))
                self.goals.setItem(r, c, it)
        # points
        self.points.setRowCount(len(st.points))
        for r, (n, xyz) in enumerate(st.points):
            a = dose_at(p, st.engine, xyz) if (p is not None and p.dose is not None and st.engine is not None) else float("nan")
            b = dose_at(cmp, st.engine, xyz) if cmp is not None else float("nan")
            for c, t in enumerate([n, ", ".join(f"{v / 10:.1f}" for v in xyz), f"{a:.2f}", "–" if np.isnan(b) else f"{b:.2f}"]):
                self.points.setItem(r, c, QTableWidgetItem(t))

    # ------------------------------------------------------------------ actions
    def add_goal(self):
        st = self.state
        if st.ss is None:
            return
        s, ok = QInputDialog.getItem(self, "Clinical goal", "Structure", st.ss.names(), 0, False)
        if not ok:
            return
        m, ok = QInputDialog.getItem(self, "Clinical goal", "Metric", ["Dmean", "Dmax", "Dmin", "D (dose to x % volume)", "V (volume % above x Gy)"], 0, False)
        if not ok:
            return
        m = m.split()[0]
        x = 0.0
        if m in ("D", "V"):
            x, ok = QInputDialog.getDouble(self, "Clinical goal", "x (% for D, Gy for V)", 95 if m == "D" else 20, 0, 500, 1)
            if not ok:
                return
        op, ok = QInputDialog.getItem(self, "Clinical goal", "Condition", ["<=", ">="], 0 if m != "D" else 1, False)
        if not ok:
            return
        lim, ok = QInputDialog.getDouble(self, "Clinical goal", "Limit", 20, 0, 1000, 2)
        if ok:
            self.goal_list.append((s, m, x, op, lim)); self.refresh()

    def del_goal(self):
        r = self.goals.currentRow()
        if 0 <= r < len(self.goal_list):
            del self.goal_list[r]; self.refresh()

    def add_point(self):
        st = self.state
        if st.image is None:
            return
        st.points.append((f"P{len(st.points) + 1}", np.array(st.cursor, float)))
        st.changed.emit("points"); self.refresh()

    def clear_points(self):
        self.state.points.clear(); self.state.changed.emit("points"); self.refresh()

    def export(self):
        rows = self.rows()
        if not rows:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export statistics", "dose_statistics.csv", "CSV (*.csv)")
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(",".join(self.COLS) + "\n")
                for r in rows:
                    fh.write(",".join([r[0]] + [f"{v:.3f}" for v in r[1:]]) + "\n")

    def report(self, path=None, window=None):
        """PDF plan report: summary, beams, statistics, goals, views and DVH. Every page says 'not for clinical use'."""
        st = self.state
        if st.plan is None or st.plan.dose is None:
            QMessageBox.information(self, "Report", "Calculate the dose first."); return
        if not path:
            path, _ = QFileDialog.getSaveFileName(self, "Plan report", f"{st.plan.name}.pdf", "PDF (*.pdf)")
            if not path:
                return
        write_report(path, st, self, window)
        st.message.emit(f"Report written: {path}")


def write_report(path, st, panel, window=None):
    from PySide6.QtCore import QMarginsF, QSizeF
    from PySide6.QtGui import QPageLayout, QPageSize, QPdfWriter
    p = st.plan
    w = QPdfWriter(path); w.setPageSize(QPageSize(QPageSize.A4)); w.setResolution(150)
    w.setPageMargins(QMarginsF(14, 14, 14, 14), QPageLayout.Millimeter)
    pa = QPainter(w)
    W, H = w.width(), w.height()
    y = [0]
    f = QFont("Helvetica");

    def text(t, size=10, bold=False, col=QColor(20, 24, 32), dy=None):
        f.setPointSizeF(size); f.setBold(bold); pa.setFont(f); pa.setPen(col)
        h = pa.fontMetrics().height()
        pa.drawText(QRectF(0, y[0], W, h * 1.3), Qt.AlignLeft | Qt.TextWordWrap, t)
        y[0] += (dy if dy is not None else h * 1.35)

    def footer():
        f.setPointSizeF(7.5); f.setBold(False); pa.setFont(f); pa.setPen(QColor(160, 80, 0))
        pa.drawText(QRectF(0, H - 40, W, 40), Qt.AlignCenter, "PyTPS · educational treatment planning · NOT FOR CLINICAL USE · generic beam data")

    def table(head, rows, widths):
        f.setPointSizeF(8); pa.setFont(f)
        rh = pa.fontMetrics().height() * 1.35
        x0 = 0
        pa.setPen(QColor(255, 255, 255))
        pa.fillRect(QRectF(0, y[0], W, rh), QColor(31, 56, 100))
        for t, cw in zip(head, widths):
            pa.drawText(QRectF(x0 + 4, y[0], cw * W - 8, rh), Qt.AlignVCenter, t); x0 += cw * W
        y[0] += rh
        for i, r in enumerate(rows):
            if y[0] + rh > H - 60:
                footer(); w.newPage(); y[0] = 0
            if i % 2:
                pa.fillRect(QRectF(0, y[0], W, rh), QColor(238, 242, 248))
            pa.setPen(QColor(20, 24, 32)); x0 = 0
            for t, cw in zip(r, widths):
                pa.drawText(QRectF(x0 + 4, y[0], cw * W - 8, rh), Qt.AlignVCenter, t); x0 += cw * W
            y[0] += rh
        y[0] += rh * 0.6

    text("PyTPS plan report", 16, True)
    text(f"{p.name} · {st.image.patient.get('id', '')} · {st.source} · {datetime.datetime.now():%Y-%m-%d %H:%M}", 9, col=QColor(80, 90, 105))
    text("Educational report. The doses come from a simplified pencil-beam model with generic beam data; "
         "they must not be used for any clinical purpose.", 9, col=QColor(160, 80, 0))
    text(f"Prescription: {p.rx.dose:g} Gy in {p.rx.fractions} fractions ({p.rx.per_fraction:.2f} Gy/fx) to {p.rx.target}, "
         f"normalised to {p.rx.method} at {p.rx.percent:g} %.", 10)
    if p.beams:
        text("Beams", 11, True)
        rows = [[b.name, b.energy, b.kind, f"{b.gantry:.1f}" + (f"→{b.arc_stop:.1f}" if b.kind == "ARC" else ""), f"{b.collimator:.1f}",
                 f"{b.couch:.1f}", f"{b.x1 / 10:.1f}/{b.x2 / 10:.1f}", f"{b.y1 / 10:.1f}/{b.y2 / 10:.1f}", b.mlc_mode,
                 f"{b.wedge.angle:g}", f"{len(b.cps) if b.cps else 1}", f"{b.mu:.1f}"] for b in p.beams]
        table(["Beam", "E", "Type", "Gantry", "Coll", "Couch", "X (cm)", "Y (cm)", "MLC", "Wedge", "CP/seg", "MU/fx"], rows,
              [0.1, 0.06, 0.08, 0.12, 0.06, 0.06, 0.1, 0.1, 0.1, 0.06, 0.07, 0.09])
    text("Dose statistics (Gy)", 11, True)
    rows = [[r[0]] + [f"{r[1]:.1f}"] + [f"{v:.2f}" for v in r[2:]] for r in panel.rows()]
    table(EvaluationPanel.COLS, rows, [0.16, 0.08, 0.08, 0.09, 0.09, 0.09, 0.09, 0.09, 0.09, 0.14])
    if panel.goal_list:
        text("Clinical goals", 11, True)
        gr = []
        for g in panel.goal_list:
            v = panel.goal_value(p, g)
            ok = "–" if v is None else ("met" if (v <= g[4] if g[3] == "<=" else v >= g[4]) else "NOT met")
            gr.append([g[0], {"D": f"D{g[2]:g}%", "V": f"V{g[2]:g}Gy"}.get(g[1], g[1]), f"{g[3]} {g[4]:g}", "–" if v is None else f"{v:.2f}", ok])
        table(["Structure", "Goal", "Limit", "Value", "Result"], gr, [0.25, 0.2, 0.2, 0.15, 0.2])
    # DVH
    if y[0] + H * 0.33 > H - 60:
        footer(); w.newPage(); y[0] = 0
    text("Dose-volume histogram", 11, True)
    dv = DVHWidget(st); dv.recompute()
    rect = QRectF(0, y[0], W, H * 0.3)
    pa.fillRect(rect, QColor(250, 251, 252)); draw_dvh(pa, rect, st, dv.curves, dv.cmp_curves); y[0] += H * 0.31
    if window is not None:
        footer(); w.newPage(); y[0] = 0
        text("Views", 11, True)
        img = window.grid.grab().toImage()
        sc = min(W / img.width(), (H - 120 - y[0]) / img.height())
        pa.drawImage(QRectF(0, y[0], img.width() * sc, img.height() * sc), img)
    footer()
    pa.end()


class ProfileWidget(_PlotMenu, QWidget):
    """Dose along a line through the crosshair (head-foot by default: junctions of TBI fields)."""
    KIND, FILE = "Dose profile", "profile"

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.axis = "z"
        self.setMinimumHeight(120)
        state.changed.connect(lambda w: self.update() if w in ("dose", "cursor", "plans", "compare", "image", "plan") else None)

    def mouseDoubleClickEvent(self, ev):
        self.axis = {"z": "x", "x": "y", "y": "z"}[self.axis]; self.update()

    def _line(self, plan):
        from scipy import ndimage
        st = self.state
        g = st.engine.grid
        i = "xyz".index(self.axis)
        ext = st.image.extent()[i]
        t = np.linspace(ext[0], ext[1], 400)
        pts = np.repeat(np.asarray(st.cursor, float)[None], len(t), 0); pts[:, i] = t
        vol = g.to_volume(plan.dose)
        c = (pts - g.origin) / g.spacing
        d = ndimage.map_coordinates(vol, [c[:, 2], c[:, 1], c[:, 0]], order=1, cval=0.0)
        inside = ndimage.map_coordinates(g.inside.astype(np.float32), [c[:, 2], c[:, 1], c[:, 0]], order=0, cval=0.0) > 0.5
        return t, np.where(inside, d, np.nan)

    def has_data(self):
        st = self.state
        pl = st.plan
        return not (pl is None or pl.dose is None or st.engine is None or len(pl.dose) != len(st.engine.grid.pts))

    def image(self, w=900, h=420):
        return render_image(lambda p, r: self._draw(p, r.width(), r.height(), hint=False), w, h)

    def table(self):
        st = self.state
        t, d = self._line(st.plan)
        cmp = _cmp(st)
        d2 = self._line(cmp)[1] if cmp is not None else None
        head = [f"{self.axis} (cm)", f"{st.plan.name} dose (Gy)"] + ([f"{cmp.name} dose (Gy)"] if cmp is not None else [])
        rows = []
        for i, x in enumerate(t):
            r = [f"{x / 10:.2f}", "" if not np.isfinite(d[i]) else f"{d[i]:.4f}"]
            if d2 is not None:
                r.append("" if not np.isfinite(d2[i]) else f"{d2[i]:.4f}")
            rows.append(r)
        return head, rows

    def paintEvent(self, ev):
        p = QPainter(self); p.fillRect(self.rect(), QColor(250, 251, 252)); p.setRenderHint(QPainter.Antialiasing)
        self._draw(p, self.width(), self.height())
        p.end()

    def _draw(self, p, width, height, hint=True):
        st = self.state
        pl = st.plan
        if not self.has_data():
            p.setPen(QColor(120, 130, 145)); p.drawText(QRectF(0, 0, width, height), Qt.AlignCenter, "Dose profile: calculate the dose first")
            return
        t, d = self._line(pl)
        rx = pl.rx.dose
        L, R, T, B = 48, width - 12, 22, height - 26
        dmax = max(np.nanmax(d) if np.isfinite(d).any() else rx, rx) * 1.12
        X = lambda v: L + (R - L) * (v - t[0]) / (t[-1] - t[0]); Y = lambda v: B - (B - T) * v / dmax
        # field extents along z of each isocentre
        if self.axis == "z" and pl.beams:
            cols = [QColor(88, 166, 255, 40), QColor(255, 159, 67, 40), QColor(61, 220, 151, 40), QColor(201, 160, 255, 40)]
            groups = {}
            for b in pl.beams:
                groups.setdefault(tuple(np.round(b.iso, 1)), []).append(b)
            for k, (iso, bs) in enumerate(sorted(groups.items(), key=lambda kv: kv[0][2])):
                lo = min(b.iso[2] + b.y1 for b in bs); hi = max(b.iso[2] + b.y2 for b in bs)
                p.fillRect(QRectF(X(lo), T, X(hi) - X(lo), B - T), cols[k % len(cols)])
        p.setPen(QColor(222, 227, 233))
        for f in (0.9, 1.0, 1.1):
            p.drawLine(QPointF(L, Y(f * rx)), QPointF(R, Y(f * rx)))
        p.setPen(QColor(90, 100, 115)); f = QFont(); f.setPointSizeF(8.5); p.setFont(f)
        for fr in (0.9, 1.0, 1.1):
            p.drawText(QPointF(L - 40, Y(fr * rx) + 4), f"{fr * 100:.0f}%")
        step = 100 if (t[-1] - t[0]) > 500 else 50
        for v in np.arange(np.ceil(t[0] / step) * step, t[-1], step):
            p.drawText(QPointF(X(v) - 10, B + 14), f"{v / 10:g}")

        def line(dd, col, dash):
            p.setPen(QPen(col, 1.6 if dash else 2.0, Qt.DashLine if dash else Qt.SolidLine))
            path = []
            for a, b in zip(t, dd):
                if np.isfinite(b):
                    path.append(QPointF(X(a), Y(b)))
                elif len(path) > 1:
                    p.drawPolyline(QPolygonF(path)); path = []
                else:
                    path = []
            if len(path) > 1:
                p.drawPolyline(QPolygonF(path))
        cmp = _cmp(st)
        if cmp is not None:
            line(self._line(cmp)[1], QColor(130, 90, 210), True)
        line(d, QColor(200, 120, 0), False)
        c = st.cursor
        p.setPen(QColor(40, 48, 60))
        name = {"z": "head–foot (z)", "x": "right–left (x)", "y": "anterior–posterior (y)"}[self.axis]
        p.drawText(8, 14, f"Dose profile {name} through x {c[0] / 10:.1f}, y {c[1] / 10:.1f}, z {c[2] / 10:.1f} cm · {pl.name}"
                          + (" · coloured bands = fields of each isocentre" if self.axis == "z" and pl.beams else "")
                          + (" · double-click: direction · right-click: save" if hint else "") + (f" · dashed: {cmp.name}" if cmp is not None else ""))
