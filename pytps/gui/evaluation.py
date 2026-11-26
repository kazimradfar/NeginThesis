"""DVH plot and the Evaluation workspace (dose statistics per structure, plan summary)."""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (QHeaderView, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
                               QFileDialog)

from ..core.plan import dvh


class DVHWidget(QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.curves = {}
        self.setMinimumHeight(120)
        state.changed.connect(self._changed)

    def _changed(self, w):
        if w in ("dose", "structures", "image"):
            self.recompute()

    def recompute(self):
        st = self.state
        self.curves = {}
        if st.plan is not None and st.plan.dose is not None and st.engine is not None:
            for s in st.ss.structures:
                if s.visible:
                    d = dvh(st.plan, st.engine, s.name)
                    if d:
                        self.curves[s.name] = (s.color, d)
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self); p.fillRect(self.rect(), QColor(250, 251, 252)); p.setRenderHint(QPainter.Antialiasing)
        if not self.curves:
            p.setPen(QColor(120, 130, 145)); p.drawText(self.rect(), Qt.AlignCenter, "DVH: calculate the dose (Planning ▸ Prescription ▸ Calculate dose)")
            p.end(); return
        rx = self.state.plan.rx.dose
        dmax = max(max(d["max"] for _, d in self.curves.values()), rx) * 1.08
        L, R, T, B = 48, self.width() - 170, 10, self.height() - 26
        p.setPen(QPen(QColor(220, 226, 233), 1))
        step = 10 if dmax > 60 else 5 if dmax > 25 else 2
        f = QFont(self.font()); f.setPointSizeF(8.5); p.setFont(f)
        for d in np.arange(0, dmax + 1e-6, step):
            x = L + (R - L) * d / dmax; p.setPen(QColor(222, 227, 233)); p.drawLine(QPointF(x, T), QPointF(x, B))
            p.setPen(QColor(90, 100, 115)); p.drawText(QPointF(x - 8, B + 14), f"{d:g}")
        for v in range(0, 101, 20):
            y = B - (B - T) * v / 100; p.setPen(QColor(222, 227, 233)); p.drawLine(QPointF(L, y), QPointF(R, y))
            p.setPen(QColor(90, 100, 115)); p.drawText(QPointF(L - 26, y + 4), f"{v}")
        p.setPen(QPen(QColor(200, 150, 0), 1, Qt.DashLine)); xr = L + (R - L) * rx / dmax; p.drawLine(QPointF(xr, T), QPointF(xr, B))
        p.setPen(QColor(90, 100, 115)); p.drawText(QPointF((L + R) / 2 - 25, self.height() - 2), "Dose (Gy)")
        p.save(); p.translate(12, (T + B) / 2 + 25); p.rotate(-90); p.drawText(0, 0, "Volume (%)"); p.restore()
        ly = T + 12
        for name, (col, d) in self.curves.items():
            c = QColor(*col)
            if sum(col) > 600:
                c = c.darker(140)
            p.setPen(QPen(c, 2))
            xs = L + (R - L) * d["dose"] / dmax; ys = B - (B - T) * d["volume"] / 100
            p.drawPolyline(QPolygonF([QPointF(x, y) for x, y in zip(xs, ys)]))
            p.drawText(QPointF(R + 10, ly), f"{name}  {d['mean']:.1f} Gy"); ly += 15
        p.end()


class EvaluationPanel(QWidget):
    COLS = ["Structure", "cc", "Min", "Mean", "Max", "D98", "D95", "D50", "D2", "V95% Rx"]

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        lay = QVBoxLayout(self)
        self.summary = QLabel("No dose yet."); self.summary.setWordWrap(True); lay.addWidget(self.summary)
        self.table = QTableWidget(0, len(self.COLS)); self.table.setHorizontalHeaderLabels(self.COLS)
        self.table.verticalHeader().hide(); self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        lay.addWidget(self.table, 1)
        self.beams = QTableWidget(0, 4); self.beams.setHorizontalHeaderLabels(["Beam", "MU / fx", "Weight", "SSD (cm)"])
        self.beams.verticalHeader().hide(); self.beams.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch); self.beams.setMaximumHeight(180)
        lay.addWidget(QLabel("Beams")); lay.addWidget(self.beams)
        b = QPushButton("Export statistics (CSV)…"); b.clicked.connect(self.export); lay.addWidget(b)
        note = QLabel("Dose values come from the educational pencil-beam model and generic beam data."); note.setWordWrap(True)
        note.setStyleSheet("color:#6b7785;font-size:11px"); lay.addWidget(note)
        state.changed.connect(lambda w: self.refresh() if w in ("dose", "structures") else None)

    def rows(self):
        st = self.state
        out = []
        if st.plan is None or st.plan.dose is None:
            return out
        rx = st.plan.rx.dose
        for s in st.ss.structures:
            d = dvh(st.plan, st.engine, s.name)
            if d:
                out.append([s.name, d["cc"], d["min"], d["mean"], d["max"], d["D"](98), d["D"](95), d["D"](50), d["D"](2), d["V"](0.95 * rx)])
        return out

    def refresh(self):
        st = self.state
        rows = self.rows()
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, v in enumerate(row):
                it = QTableWidgetItem(v if c == 0 else f"{v:.1f}" if c == 1 else f"{v:.2f}")
                if c:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(r, c, it)
        p = st.plan
        if p is None or p.dose is None:
            self.summary.setText("No dose yet."); self.beams.setRowCount(0); return
        tot = sum(b.mu for b in p.beams)
        self.summary.setText(f"<b>{p.name}</b> · {p.rx.dose:g} Gy in {p.rx.fractions} fractions to {p.rx.target} "
                             f"(normalised to {p.rx.method}, {p.rx.percent:g} %) · {tot:.0f} MU per fraction")
        self.beams.setRowCount(len(p.beams))
        for r, b in enumerate(p.beams):
            ssd = st.engine.ssd(b) if st.engine else float("nan")
            for c, v in enumerate([b.name, f"{b.mu:.1f}", f"{b.weight:.3f}", "–" if not np.isfinite(ssd) else f"{ssd / 10:.1f}"]):
                self.beams.setItem(r, c, QTableWidgetItem(v))

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
