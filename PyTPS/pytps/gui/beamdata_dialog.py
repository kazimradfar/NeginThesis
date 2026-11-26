"""Beam data editor: PDD, output factors, head scatter, wedge factors and calibration; refit the pencil-beam model."""
from __future__ import annotations

import copy

import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QHeaderView,
                               QLabel, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from ..core.beamdata import DEPTHS


class PDDPlot(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.model = None
        self.setMinimumSize(360, 220)

    def paintEvent(self, ev):
        p = QPainter(self); p.fillRect(self.rect(), QColor(250, 251, 252)); p.setRenderHint(QPainter.Antialiasing)
        m = self.model
        if m is None:
            p.end(); return
        L, R, T, B = 40, self.width() - 10, 10, self.height() - 24
        X = lambda d: L + (R - L) * d / DEPTHS[-1]
        Y = lambda v: B - (B - T) * v / 105
        p.setPen(QColor(220, 226, 233))
        for d in range(0, int(DEPTHS[-1]) + 1, 50):
            p.drawLine(QPointF(X(d), T), QPointF(X(d), B))
        for v in range(0, 101, 20):
            p.drawLine(QPointF(L, Y(v)), QPointF(R, Y(v)))
        p.setPen(QColor(90, 100, 115))
        for d in range(0, int(DEPTHS[-1]) + 1, 50):
            p.drawText(QPointF(X(d) - 8, B + 14), f"{d // 10}")
        for v in range(0, 101, 20):
            p.drawText(QPointF(L - 26, Y(v) + 4), f"{v}")
        cols = [QColor(31, 111, 235), QColor(220, 90, 40), QColor(40, 160, 90), QColor(150, 80, 200), QColor(120, 120, 120)]
        dd = np.linspace(0, DEPTHS[-1], 120)
        for k, (side, data) in enumerate(sorted(m.pdd.items())):
            c = cols[k % len(cols)]
            p.setPen(QPen(c, 1.6)); p.drawPolyline(QPolygonF([QPointF(X(d), Y(v)) for d, v in zip(dd, m.pdd_model(side, dd))]))
            p.setPen(Qt.NoPen); p.setBrush(c)
            for d, v in zip(DEPTHS, data):
                p.drawEllipse(QPointF(X(d), Y(v)), 2.6, 2.6)
            p.setPen(c); p.drawText(QPointF(R - 120, T + 14 + 14 * k), f"{side / 10:g} × {side / 10:g} cm")
        p.setPen(QColor(90, 100, 115)); p.drawText(QPointF(L + 4, T + 12), "PDD (%) · dots = data, lines = model · depth (cm)")
        p.end()


class BeamDataDialog(QDialog):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Beam data and model (generic teaching data)")
        self.state = state
        self.models = copy.deepcopy(state.models)
        lay = QVBoxLayout(self)
        top = QHBoxLayout(); top.addWidget(QLabel("Energy")); self.energy = QComboBox(); self.energy.addItems(list(self.models))
        self.energy.currentTextChanged.connect(self.load); top.addWidget(self.energy); top.addStretch(1); lay.addLayout(top)
        warn = QLabel("These are generic values with a typical shape. Change them to see how the model and the dose follow the data "
                      "(beam commissioning). They describe no real machine.")
        warn.setWordWrap(True); warn.setStyleSheet("color:#a05a00"); lay.addWidget(warn)
        tabs = QTabWidget()
        self.pdd = QTableWidget(); self.of = QTableWidget(); self.wf = QTableWidget()
        w1 = QWidget(); l1 = QHBoxLayout(w1); l1.addWidget(self.pdd, 1); self.plot = PDDPlot(); l1.addWidget(self.plot, 1)
        tabs.addTab(w1, "Depth dose (PDD, SSD 100 cm)"); tabs.addTab(self.of, "Output and head scatter"); tabs.addTab(self.wf, "Wedge factors")
        w4 = QWidget(); f4 = QFormLayout(w4)
        self.cal = QDoubleSpinBox(); self.cal.setRange(0.5, 2); self.cal.setDecimals(3); self.cal.setSuffix(" cGy/MU")
        self.sigma = QDoubleSpinBox(); self.sigma.setRange(1, 10); self.sigma.setDecimals(2); self.sigma.setSuffix(" mm")
        self.leaf = QDoubleSpinBox(); self.leaf.setRange(0, 0.1); self.leaf.setDecimals(3)
        f4.addRow("Calibration (dmax, 10 × 10 cm, SSD 100 cm)", self.cal); f4.addRow("Penumbra σ at the isocentre", self.sigma)
        f4.addRow("MLC transmission", self.leaf)
        self.params = QLabel(""); self.params.setWordWrap(True); f4.addRow("Fitted model", self.params)
        tabs.addTab(w4, "Calibration and model")
        lay.addWidget(tabs, 1)
        row = QHBoxLayout()
        fit = QPushButton("Fit model to the data"); fit.clicked.connect(self.fit); row.addWidget(fit)
        self.rms = QLabel(""); row.addWidget(self.rms, 1); lay.addLayout(row)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel); bb.accepted.connect(self.accept_models); bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.resize(980, 560)
        self.load(self.energy.currentText())

    def m(self):
        return self.models[self.energy.currentText()]

    def load(self, e):
        m = self.models[e]
        sizes = sorted(m.pdd)
        self.pdd.setColumnCount(len(sizes) + 1); self.pdd.setRowCount(len(DEPTHS))
        self.pdd.setHorizontalHeaderLabels(["Depth (cm)"] + [f"{s / 10:g}×{s / 10:g}" for s in sizes]); self.pdd.verticalHeader().hide()
        for r, d in enumerate(DEPTHS):
            it = QTableWidgetItem(f"{d / 10:g}"); it.setFlags(Qt.ItemIsEnabled); self.pdd.setItem(r, 0, it)
            for c, s in enumerate(sizes):
                self.pdd.setItem(r, c + 1, QTableWidgetItem(f"{m.pdd[s][r]:g}"))
        fs = sorted(set(m.output) | set(m.head_scatter))
        self.of.setColumnCount(3); self.of.setRowCount(len(fs)); self.of.setHorizontalHeaderLabels(["Field (cm)", "Total output Scp", "Head scatter Sc"])
        self.of.verticalHeader().hide(); self.of.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        for r, s in enumerate(fs):
            it = QTableWidgetItem(f"{s / 10:g}"); it.setFlags(Qt.ItemIsEnabled); self.of.setItem(r, 0, it)
            self.of.setItem(r, 1, QTableWidgetItem(f"{m.output.get(s, np.nan):g}")); self.of.setItem(r, 2, QTableWidgetItem(f"{m.head_scatter.get(s, np.nan):g}"))
        ws = sorted(m.wedge_factors)
        self.wf.setColumnCount(2); self.wf.setRowCount(len(ws)); self.wf.setHorizontalHeaderLabels(["Wedge (°)", "Factor"])
        self.wf.verticalHeader().hide(); self.wf.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        for r, a in enumerate(ws):
            it = QTableWidgetItem(f"{a}"); it.setFlags(Qt.ItemIsEnabled); self.wf.setItem(r, 0, it); self.wf.setItem(r, 1, QTableWidgetItem(f"{m.wedge_factors[a]:g}"))
        self.cal.setValue(m.calibration); self.sigma.setValue(m.sigma); self.leaf.setValue(m.leaf_t)
        self.plot.model = m; self.plot.update(); self.show_params()

    def read(self):
        m = self.m()
        sizes = sorted(m.pdd)
        try:
            for c, s in enumerate(sizes):
                m.pdd[s] = [float(self.pdd.item(r, c + 1).text()) for r in range(len(DEPTHS))]
            for r in range(self.of.rowCount()):
                s = int(round(float(self.of.item(r, 0).text()) * 10))
                m.output[s] = float(self.of.item(r, 1).text()); m.head_scatter[s] = float(self.of.item(r, 2).text())
            for r in range(self.wf.rowCount()):
                m.wedge_factors[int(self.wf.item(r, 0).text())] = float(self.wf.item(r, 1).text())
        except (ValueError, AttributeError):
            QMessageBox.warning(self, "Beam data", "All cells must be numbers."); return False
        m.calibration, m.sigma, m.leaf_t = self.cal.value(), self.sigma.value(), self.leaf.value()
        m._k = None
        return True

    def show_params(self):
        m = self.m()
        self.params.setText(f"μ primary {m.mu_p * 10:.3f} /cm · surface {m.surf:.2f} · build-up {m.bu:.1f} mm · scatter amplitude {m.s_max:.2f} · "
                            f"scatter growth {m.s_grow:.0f} mm · scatter μ {m.mu_s * 10:.3f} /cm · kernel radius {m.lam:.0f} mm")
        self.rms.setText(f"PDD fit: RMS difference {m.fit_rms:.2f} % (should be below about 2 %)")

    def fit(self):
        if not self.read():
            return
        self.m().fit(); self.plot.update(); self.show_params()

    def accept_models(self):
        if not self.read():
            return
        self.m().fit()
        self.state._models = self.models
        self.accept()
