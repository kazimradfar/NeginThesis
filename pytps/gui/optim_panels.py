"""IMRT Constraints and Optimisation tabs."""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout,
                               QHeaderView, QLabel, QMessageBox, QProgressDialog, QPushButton, QSpinBox, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from ..core.dose_pb import DoseEngine
from ..core.optimise import COST_HELP, COST_TYPES, Cost, Optimiser, OptSettings, default_costs
from ..core.plan import calculate
from .planning import ensure_plan

COLS = ["On", "Structure", "Cost function", "Dose (Gy)", "Parameter", "Weight", "Mode", "Achieved"]


class ConstraintsPanel(QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self._filling = False
        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        for t, f, tip in (("Add", self.add, "Add a cost function"), ("Delete", self.delete, "Delete the selected row"),
                          ("Defaults", self.defaults, "Replace with a starting set for the target and organs")):
            b = QPushButton(t); b.setToolTip(tip); b.clicked.connect(f); row.addWidget(b)
        lay.addLayout(row)
        self.table = QTableWidget(0, len(COLS)); self.table.setHorizontalHeaderLabels(COLS); self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemChanged.connect(self._edited); self.table.currentCellChanged.connect(lambda r, *_: self._help(r))
        lay.addWidget(self.table, 1)
        self.help = QLabel(""); self.help.setWordWrap(True); self.help.setStyleSheet("color:#4a5568"); lay.addWidget(self.help)
        note = QLabel("<b>Objective</b>: traded off against the others. <b>Constraint</b>: its weight grows while it is not met.<br>"
                      "Target Penalty / Target EUD / Underdose keep the target dose up; Overdose and Maximum Dose limit hot spots; "
                      "Serial (EUD with power k) for organs like the spinal cord; Parallel (mean organ damage) for organs like the lungs "
                      "or parotids; DVH points; Conformality for a steep dose fall-off around the target.")
        note.setWordWrap(True); note.setStyleSheet("color:#6b7785;font-size:11px"); lay.addWidget(note)
        state.changed.connect(lambda w: self.refresh() if w in ("image", "structures", "costs", "plans") else None)

    def costs(self):
        st = self.state
        if st.ss is None:
            return []
        p = ensure_plan(st)
        if not p.costs:
            p.costs = default_costs(p, st.ss)
        return p.costs

    def refresh(self):
        st = self.state
        if st.ss is None:
            return
        C = self.costs()
        self._filling = True
        self.table.setRowCount(len(C))
        names = st.ss.names()
        for r, c in enumerate(C):
            on = QTableWidgetItem(); on.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled); on.setCheckState(Qt.Checked if c.on else Qt.Unchecked)
            self.table.setItem(r, 0, on)
            cb = QComboBox(); cb.addItems(names); cb.setCurrentText(c.structure); cb.currentTextChanged.connect(lambda t, c=c: setattr(c, "structure", t))
            self.table.setCellWidget(r, 1, cb)
            tb = QComboBox(); tb.addItems(COST_TYPES); tb.setCurrentText(c.type)
            tb.currentTextChanged.connect(lambda t, c=c, r=r: (setattr(c, "type", t), self._help(r)))
            self.table.setCellWidget(r, 2, tb)
            for col, v in ((3, c.dose), (4, c.param), (5, c.weight)):
                it = QTableWidgetItem(f"{v:g}"); it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter); self.table.setItem(r, col, it)
            mb = QComboBox(); mb.addItems(["objective", "constraint"]); mb.setCurrentText(c.mode)
            mb.currentTextChanged.connect(lambda t, c=c: (setattr(c, "mode", t), setattr(c, "_mult", 5.0)))
            self.table.setCellWidget(r, 6, mb)
            a = QTableWidgetItem(c.achieved or "–"); a.setFlags(Qt.ItemIsEnabled); self.table.setItem(r, 7, a)
        self._filling = False

    def _help(self, r):
        C = self.costs()
        if 0 <= r < len(C):
            h = COST_HELP.get(C[r].type, ("", ""))
            self.help.setText(f"<b>{C[r].type}</b>: Dose = {h[0]}, Parameter = {h[1]}")

    def _edited(self, it):
        if self._filling:
            return
        c = self.costs()[it.row()]
        if it.column() == 0:
            c.on = it.checkState() == Qt.Checked
            return
        try:
            v = float(it.text().replace(",", "."))
        except ValueError:
            self.refresh(); return
        setattr(c, {3: "dose", 4: "param", 5: "weight"}[it.column()], v)

    def add(self):
        st = self.state
        if st.ss is None:
            return
        p = ensure_plan(st)
        self.costs().append(Cost(p.rx.target, "Quadratic Overdose", round(p.rx.dose * 1.05, 1), 0.5))
        self.refresh()

    def delete(self):
        r = self.table.currentRow()
        if 0 <= r < len(self.costs()):
            del self.costs()[r]; self.refresh()

    def defaults(self):
        st = self.state
        if st.ss is None:
            return
        ensure_plan(st).costs = default_costs(ensure_plan(st), st.ss); self.refresh()


class CostPlot(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.hist = []
        self.setMinimumHeight(110)

    def set(self, h):
        self.hist = list(h); self.update()

    def paintEvent(self, ev):
        p = QPainter(self); p.fillRect(self.rect(), QColor(250, 251, 252)); p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QColor(200, 206, 214)); p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        h = [v for v in self.hist if v > 0]
        p.setPen(QColor(90, 100, 115)); p.drawText(8, 14, f"Total cost (log scale) · {len(self.hist)} iterations" + (f" · {self.hist[-1]:.4g}" if self.hist else ""))
        if len(h) < 2:
            p.end(); return
        lo, hi = np.log(min(h)), np.log(max(h))
        W, H = self.width() - 16, self.height() - 28
        pts = [QPointF(8 + W * i / (len(h) - 1), 20 + H * (1 - (np.log(v) - lo) / max(hi - lo, 1e-9))) for i, v in enumerate(h)]
        p.setPen(QPen(QColor(110, 80, 220), 1.6)); p.drawPolyline(QPolygonF(pts))
        p.end()


class OptimisationPanel(QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.opt = None
        lay = QVBoxLayout(self)
        g = QGroupBox("Settings"); f = QFormLayout(g)
        self.it1 = QSpinBox(); self.it1.setRange(10, 1000); self.it1.setValue(120)
        self.it2 = QSpinBox(); self.it2.setRange(0, 500); self.it2.setValue(40)
        self.smooth = QComboBox(); self.smooth.addItems(["Off", "Low", "Medium", "High"]); self.smooth.setCurrentText("Medium")
        self.levels = QSpinBox(); self.levels.setRange(2, 20); self.levels.setValue(7)
        self.maxseg = QSpinBox(); self.maxseg.setRange(1, 60); self.maxseg.setValue(12)
        self.minarea = QDoubleSpinBox(); self.minarea.setRange(0.5, 50); self.minarea.setValue(4); self.minarea.setSuffix(" cm²")
        self.minmu = QDoubleSpinBox(); self.minmu.setRange(0, 20); self.minmu.setValue(2); self.minmu.setSuffix(" MU")
        self.aps = QSpinBox(); self.aps.setRange(1, 6); self.aps.setValue(3)
        self.arcsp = QDoubleSpinBox(); self.arcsp.setRange(2, 30); self.arcsp.setValue(8); self.arcsp.setSuffix(" °")
        self.rate = QDoubleSpinBox(); self.rate.setRange(100, 2400); self.rate.setValue(600); self.rate.setSuffix(" MU/min")
        self.layer = QCheckBox("Layering (overlaps belong to the structure higher in the list)")
        for lab, w in (("Stage 1 iterations", self.it1), ("Stage 2 iterations", self.it2), ("Fluence smoothing", self.smooth),
                       ("IMRT intensity levels", self.levels), ("Max. segments / beam", self.maxseg), ("Min. segment area", self.minarea),
                       ("Min. MU / segment", self.minmu), ("VMAT apertures / sector", self.aps), ("VMAT sector (optimisation)", self.arcsp),
                       ("Max. dose rate", self.rate)):
            f.addRow(lab, w)
        f.addRow(self.layer)
        lay.addWidget(g)
        row = QHBoxLayout()
        self.b1 = QPushButton("Stage 1 · fluence"); self.b2 = QPushButton("Stage 2 · segments"); self.ball = QPushButton("Optimise (1 + 2)")
        self.ball.setStyleSheet("font-weight:600")
        for b, fn in ((self.b1, self.stage1), (self.b2, self.stage2), (self.ball, self.both)):
            b.clicked.connect(fn); row.addWidget(b)
        lay.addLayout(row)
        self.plot = CostPlot(); lay.addWidget(self.plot)
        self.info = QLabel("Beams with MLC = optimised are optimised; the other beams count as a fixed (bias) dose.")
        self.info.setWordWrap(True); lay.addWidget(self.info)
        self.deliv = QTableWidget(0, 4); self.deliv.setHorizontalHeaderLabels(["Beam", "MU / fx", "Segments / CPs", "Time (min)"])
        self.deliv.verticalHeader().hide(); self.deliv.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch); self.deliv.setMaximumHeight(170)
        lay.addWidget(self.deliv)
        lay.addStretch(1)
        state.changed.connect(lambda w: setattr(self, "opt", None) if w in ("plans", "image") else None)

    def settings(self):
        st = OptSettings(iterations=self.it1.value(), stage2_iterations=self.it2.value(),
                         smoothing={"Off": 0, "Low": 0.3, "Medium": 0.6, "High": 1.5}[self.smooth.currentText()],
                         levels=self.levels.value(), max_segments=self.maxseg.value(), min_area=self.minarea.value(),
                         min_mu=self.minmu.value(), vmat_apertures=self.aps.value(), arc_spacing=self.arcsp.value(),
                         dose_rate=self.rate.value(), layering=self.layer.isChecked())
        return st

    def _prepare(self):
        st = self.state
        if st.ss is None:
            return None
        p = ensure_plan(st)
        if not any(b.mlc_mode == "optimised" for b in p.beams):
            QMessageBox.information(self, "Optimisation", "Set MLC = optimised for the beams to optimise (Planning ▸ Beams)."); return None
        if not p.costs:
            p.costs = default_costs(p, st.ss)
        costs = p.costs
        if not any(c.on for c in costs):
            QMessageBox.information(self, "Optimisation", "Add cost functions in IMRT Constraints."); return None
        grid = 4.0 if max(b - a for a, b in st.image.extent()) < 600 else 6.0
        if st.engine is None or st.engine_version != (st.ss.version, st.density_version):
            st.engine = DoseEngine(st.ss, st.models, grid); st.engine_version = (st.ss.version, st.density_version); p.beam_dose.clear()
        # fixed beams need their dose first (bias)
        fixed = [b.name for b in p.beams if b.mlc_mode != "optimised" and b.name not in p.beam_dose]
        if fixed:
            calculate(p, st.engine, only=fixed)
        return p, costs

    def _run(self, stages):
        st = self.state
        prep = self._prepare()
        if prep is None:
            return
        p, costs = prep
        sett = self.settings()
        for c in costs:
            c._mult = 5.0
        dlg = QProgressDialog("Optimising…", "Stop", 0, 100, self); dlg.setWindowModality(Qt.WindowModal); dlg.setMinimumDuration(0); dlg.show()

        def prog(text, n, tot):
            dlg.setLabelText(text)
            if tot:
                dlg.setMaximum(tot); dlg.setValue(min(n, tot))
            if n % 5 == 0 and sett.history:
                self.plot.set(sett.history)
            QApplication.processEvents()
            return not dlg.wasCanceled()
        try:
            if "1" in stages or self.opt is None:
                self.opt = Optimiser(p, st.engine, costs, sett, prog)
                self.opt.stage1()
            else:
                self.opt.st = sett; self.opt.progress = prog
                sett.history = list(self.opt.st.history) if self.opt.st.history else []
            if "2" in stages:
                dlg.setLabelText("Stage 2 · sequencing…")
                if not self.opt.stage2():
                    QMessageBox.information(self, "Optimisation", "Run Stage 1 first."); return
                dlg.setLabelText("Final dose calculation…"); QApplication.processEvents()
                self.opt.finish()
            else:
                # show the Stage 1 (ideal fluence) dose estimate on the optimisation voxels
                pass
        except Exception as e:
            QMessageBox.warning(self, "Optimisation", f"Optimisation failed: {e}"); return
        finally:
            dlg.close()
        self.plot.set(sett.history)
        st.changed.emit("costs"); st.changed.emit("plan"); st.changed.emit("dose")
        self.fill_delivery()
        st.message.emit("Optimisation finished" + (" (Stage 1: ideal fluence; run Stage 2 for deliverable segments)" if "2" not in stages else ""))

    def fill_delivery(self):
        if self.opt is None:
            return
        rows = self.opt.delivery()
        self.deliv.setRowCount(len(rows))
        for r, (n, mu, segs, t) in enumerate(rows):
            for c, v in enumerate([n, f"{mu:.1f}", str(segs), f"{t / 60:.1f}"]):
                self.deliv.setItem(r, c, QTableWidgetItem(v))

    def stage1(self):
        self._run("1")

    def stage2(self):
        self._run("2")

    def both(self):
        self._run("12")
