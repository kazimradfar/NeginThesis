"""Workspace panels: Patient (import, phantoms, CT-to-density) and Contouring (structure set and tools)."""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QColorDialog, QComboBox, QDoubleSpinBox, QFileDialog,
                               QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QMessageBox,
                               QProgressDialog, QPushButton, QTableWidget, QTableWidgetItem, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget, QApplication)

from ..core import dicomio
from ..core.phantoms import PHANTOMS
from ..core.structures import STRUCT_TYPES, StructureSet


def _btn(text, slot, tip=""):
    b = QPushButton(text)
    b.clicked.connect(slot)
    if tip:
        b.setToolTip(tip)
    return b


class PatientPanel(QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.series = []
        lay = QVBoxLayout(self)
        g = QGroupBox("Import DICOM")
        gl = QVBoxLayout(g)
        gl.addWidget(_btn("Select folder…", self.choose_folder, "Read a folder with CT, RT Structure Set (and RT Plan / RT Dose) files"))
        self.tree = QTreeWidget(); self.tree.setHeaderLabels(["Series", "Files"]); self.tree.setRootIsDecorated(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch); self.tree.setMinimumHeight(120)
        gl.addWidget(self.tree)
        gl.addWidget(_btn("Load selected CT + structures", self.load_selected))
        note = QLabel("Files are read on this computer only. Names and IDs are replaced by an anonymous code. "
                      "Use de-identified data and follow your hospital's rules.")
        note.setWordWrap(True); note.setStyleSheet("color:#6b7785;font-size:11px")
        gl.addWidget(note)
        lay.addWidget(g)
        g2 = QGroupBox("Practice phantoms")
        g2l = QHBoxLayout(g2)
        self.ph = QComboBox(); self.ph.addItems(list(PHANTOMS))
        g2l.addWidget(self.ph, 1); g2l.addWidget(_btn("Load", lambda: self.load_phantom(self.ph.currentText())))
        lay.addWidget(g2)
        g3 = QGroupBox("Patient and image")
        g3l = QVBoxLayout(g3)
        self.info = QLabel("—"); self.info.setWordWrap(True); self.info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        g3l.addWidget(self.info)
        lay.addWidget(g3)
        g4 = QGroupBox("CT number to relative electron density")
        g4l = QVBoxLayout(g4)
        self.ctab = QTableWidget(0, 2); self.ctab.setHorizontalHeaderLabels(["HU", "ρe (rel.)"])
        self.ctab.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch); self.ctab.verticalHeader().hide(); self.ctab.setMaximumHeight(200)
        g4l.addWidget(self.ctab)
        g4l.addWidget(_btn("Apply table", self.apply_ct_table, "Used by the dose calculation"))
        lay.addWidget(g4)
        lay.addStretch(1)
        state.changed.connect(lambda w: self.refresh() if w == "image" else None)

    # ------------------------------------------------------------------ actions
    def choose_folder(self, folder=None):
        folder = folder or QFileDialog.getExistingDirectory(self, "Folder with DICOM files")
        if not folder:
            return
        dlg = QProgressDialog("Scanning DICOM files…", None, 0, 100, self); dlg.setWindowModality(Qt.WindowModal); dlg.show()
        try:
            self.series = dicomio.scan_folder(folder, lambda n, t: (dlg.setMaximum(t), dlg.setValue(n), QApplication.processEvents()))
        except Exception as e:
            QMessageBox.warning(self, "Import", str(e)); return
        finally:
            dlg.close()
        self.tree.clear()
        for s in self.series:
            it = QTreeWidgetItem([f"{s.modality} · {s.description or '(no description)'} · {s.patient_code}", str(len(s.files))])
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(0, Qt.Checked if s.modality in ("CT", "RTSTRUCT") else Qt.Unchecked)
            self.tree.addTopLevelItem(it)
        if not self.series:
            QMessageBox.information(self, "Import", "No CT, RT Structure Set, RT Plan or RT Dose files were found.")

    def load_selected(self):
        chosen = [s for i, s in enumerate(self.series) if self.tree.topLevelItem(i).checkState(0) == Qt.Checked]
        cts = [s for s in chosen if s.modality == "CT"]
        if len(cts) != 1:
            QMessageBox.warning(self, "Import", "Select exactly one CT series."); return
        dlg = QProgressDialog("Loading CT…", None, 0, 100, self); dlg.setWindowModality(Qt.WindowModal); dlg.show()
        try:
            img = dicomio.load_ct(cts[0].files, progress=lambda n, t: (dlg.setMaximum(t), dlg.setValue(n), QApplication.processEvents()))
            ss = StructureSet(img)
            for s in chosen:
                if s.modality == "RTSTRUCT":
                    dlg.setLabelText("Converting contours…")
                    dicomio.load_rtstruct(s.files[0], ss, lambda n, t: (dlg.setMaximum(t), dlg.setValue(n), QApplication.processEvents()))
            if ss.external() is None:
                body = ss.add("BODY", ss.external_from_threshold(), (127, 220, 127), "EXTERNAL")
                ss.structures.remove(body); ss.structures.insert(0, body)
                self.state.message.emit("No external contour in the structure set: BODY was created from the CT (threshold −350 HU)")
        except Exception as e:
            QMessageBox.warning(self, "Import", f"Could not load the data:\n{e}"); return
        finally:
            dlg.close()
        self.state.set_case(img, ss, "DICOM")

    def load_phantom(self, name):
        img, ss = PHANTOMS[name]()
        self.state.set_case(img, ss, f"phantom: {name}")

    def refresh(self):
        st = self.state
        if st.image is None:
            return
        img = st.image
        e = img.extent()
        self.info.setText(f"<b>{img.patient.get('id', 'ANON')}</b> · {st.source}<br>{img.patient.get('description', '')}<br>"
                          f"Patient position {img.orientation}<br>Grid {img.shape[2]} × {img.shape[1]} × {img.shape[0]} voxels, "
                          f"{img.spacing[0]:.2f} × {img.spacing[1]:.2f} × {img.spacing[2]:.2f} mm<br>"
                          f"Extent {(e[0][1] - e[0][0]) / 10:.1f} × {(e[1][1] - e[1][0]) / 10:.1f} × {(e[2][1] - e[2][0]) / 10:.1f} cm")
        self.ctab.setRowCount(len(img.ct_to_red))
        for r, (hu, d) in enumerate(sorted(img.ct_to_red)):
            self.ctab.setItem(r, 0, QTableWidgetItem(f"{hu:g}")); self.ctab.setItem(r, 1, QTableWidgetItem(f"{d:g}"))

    def apply_ct_table(self):
        st = self.state
        if st.image is None:
            return
        try:
            rows = [(float(self.ctab.item(r, 0).text()), float(self.ctab.item(r, 1).text())) for r in range(self.ctab.rowCount())]
        except Exception:
            QMessageBox.warning(self, "CT to density", "All cells must be numbers."); return
        st.image.ct_to_red = sorted(rows)
        st.changed.emit("density")
        st.message.emit("CT-to-density table applied")


class ContourPanel(QWidget):
    COLS = ["", "", "Name", "Type", "cc", "ρe"]

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self._filling = False
        lay = QVBoxLayout(self)
        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        h = self.table.horizontalHeader()
        for c, m in enumerate([QHeaderView.ResizeToContents, QHeaderView.ResizeToContents, QHeaderView.Stretch,
                               QHeaderView.ResizeToContents, QHeaderView.ResizeToContents, QHeaderView.ResizeToContents]):
            h.setSectionResizeMode(c, m)
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows); self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.itemChanged.connect(self._item_changed)
        self.table.cellClicked.connect(self._cell_clicked)
        self.table.itemSelectionChanged.connect(self._selected)
        lay.addWidget(self.table, 1)
        row = QHBoxLayout()
        for t, f in (("New", self.new), ("Delete", self.delete), ("▲", lambda: self.move(-1)), ("▼", lambda: self.move(1))):
            row.addWidget(_btn(t, f))
        lay.addLayout(row)
        tip = QLabel("Brush, eraser and polygon are in the toolbar. Polygon: click points, double-click to close "
                     "(Shift = subtract). Right-drag = window/level, wheel = slice, Ctrl+wheel = zoom.")
        tip.setWordWrap(True); tip.setStyleSheet("color:#6b7785;font-size:11px"); lay.addWidget(tip)

        g = QGroupBox("Operations (result goes into the target structure)")
        gl = QGridLayout(g)
        self.target = QComboBox(); gl.addWidget(QLabel("Target"), 0, 0); gl.addWidget(self.target, 0, 1, 1, 3)
        self.msrc = QComboBox(); self.mmm = _spin(-50, 50, 1, 5); self.mmz = _spin(-50, 50, 1, 5)
        gl.addWidget(QLabel("Margin"), 1, 0); gl.addWidget(self.msrc, 1, 1); gl.addWidget(self.mmm, 1, 2); gl.addWidget(self.mmz, 1, 3)
        gl.addWidget(_btn("Apply margin (mm, lateral / head-foot)", self.margin), 2, 0, 1, 4)
        self.ba, self.bop, self.bb = QComboBox(), QComboBox(), QComboBox()
        self.bop.addItems(["union", "intersect", "subtract", "xor"])
        gl.addWidget(QLabel("Boolean"), 3, 0); gl.addWidget(self.ba, 3, 1); gl.addWidget(self.bop, 3, 2); gl.addWidget(self.bb, 3, 3)
        gl.addWidget(_btn("Apply Boolean", self.boolean), 4, 0, 1, 4)
        self.tlo, self.thi = _spin(-1000, 3000, 0, -1000), _spin(-1000, 3000, 0, -400); self.twithin = QComboBox()
        gl.addWidget(QLabel("Threshold"), 5, 0); gl.addWidget(self.tlo, 5, 1); gl.addWidget(self.thi, 5, 2); gl.addWidget(self.twithin, 5, 3)
        gl.addWidget(_btn("Apply threshold (HU, within)", self.threshold), 6, 0, 1, 4)
        r2 = QHBoxLayout()
        for t, f, tp in (("Interpolate", self.interpolate, "Fill empty slices between contoured slices"),
                         ("Fill holes", self.fill_holes, "Fill holes slice by slice"),
                         ("Keep largest", self.largest, "Keep the largest connected part"),
                         ("Clear", self.clear, "Empty the target structure")):
            r2.addWidget(_btn(t, f, tp))
        gl.addLayout(r2, 7, 0, 1, 4)
        gl.addWidget(_btn("Body outline from CT (−350 HU)", self.auto_body), 8, 0, 1, 4)
        lay.addWidget(g)
        state.changed.connect(lambda w: self.refresh() if w in ("image", "structures") else None)

    # ------------------------------------------------------------------ table
    def refresh(self):
        st = self.state
        if st.ss is None:
            return
        self._filling = True
        ss = st.ss
        self.table.setRowCount(len(ss.structures))
        for r, s in enumerate(ss.structures):
            vis = QTableWidgetItem(); vis.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            vis.setCheckState(Qt.Checked if s.visible else Qt.Unchecked); self.table.setItem(r, 0, vis)
            col = QTableWidgetItem("  "); col.setBackground(QColor(*s.color)); col.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            col.setToolTip("Click to change the colour"); self.table.setItem(r, 1, col)
            nm = QTableWidgetItem(s.name); self.table.setItem(r, 2, nm)
            cb = QComboBox(); cb.addItems(STRUCT_TYPES); cb.setCurrentText(s.type)
            cb.currentTextChanged.connect(lambda t, s=s: (setattr(s, "type", t), st.changed.emit("structures")))
            self.table.setCellWidget(r, 3, cb)
            v = QTableWidgetItem(f"{s.volume_cc(st.image):.1f}"); v.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable); self.table.setItem(r, 4, v)
            self.table.setItem(r, 5, QTableWidgetItem("" if s.density is None else f"{s.density:g}"))
            if s.name == st.active:
                self.table.selectRow(r)
        names = ss.names()
        for cb in (self.target, self.msrc, self.ba, self.bb, self.twithin):
            keep = cb.currentText(); cb.blockSignals(True); cb.clear()
            if cb is self.twithin:
                cb.addItem("(whole image)")
            cb.addItems(names)
            if keep in names or (cb is self.twithin and keep == "(whole image)"):
                cb.setCurrentText(keep)
            elif cb is self.target and st.active:
                cb.setCurrentText(st.active)
            cb.blockSignals(False)
        self._filling = False

    def _item_changed(self, it):
        if self._filling:
            return
        st = self.state
        s = st.ss.structures[it.row()]
        if it.column() == 0:
            s.visible = it.checkState() == Qt.Checked
        elif it.column() == 2:
            new = it.text().strip()
            if new and new != s.name and st.ss.get(new) is None:
                if st.active == s.name:
                    st.active = new
                s.name = new
        elif it.column() == 5:
            t = it.text().strip()
            try:
                s.density = None if t == "" else float(t)
            except ValueError:
                s.density = None
            st.changed.emit("density")
        st.ss.version += 1
        st.changed.emit("structures")

    def _cell_clicked(self, r, c):
        if c != 1:
            return
        s = self.state.ss.structures[r]
        col = QColorDialog.getColor(QColor(*s.color), self, f"Colour of {s.name}")
        if col.isValid():
            s.color = (col.red(), col.green(), col.blue()); self.state.ss.version += 1; self.state.changed.emit("structures")

    def _selected(self):
        if self._filling:
            return
        rows = self.table.selectionModel().selectedRows()
        if rows:
            self.state.active = self.state.ss.structures[rows[0].row()].name
            self.target.setCurrentText(self.state.active)
            self.state.changed.emit("active")

    def new(self):
        st = self.state
        if st.ss is None:
            return
        name, ok = QInputDialog.getText(self, "New structure", "Name:")
        if ok and name.strip():
            try:
                st.ss.add(name.strip())
            except ValueError as e:
                QMessageBox.warning(self, "New structure", str(e)); return
            st.active = name.strip(); st.changed.emit("structures")

    def delete(self):
        st = self.state
        if not st.active:
            return
        if QMessageBox.question(self, "Delete", f"Delete {st.active}?") == QMessageBox.Yes:
            st.ss.remove(st.active); st.active = st.ss.structures[0].name if st.ss.structures else None
            st.changed.emit("structures")

    def move(self, d):
        st = self.state
        L = st.ss.structures
        i = next((k for k, s in enumerate(L) if s.name == st.active), None)
        if i is None or not (0 <= i + d < len(L)):
            return
        L[i], L[i + d] = L[i + d], L[i]
        st.ss.version += 1; st.changed.emit("structures")

    # ------------------------------------------------------------------ operations
    def _apply(self, label, fn):
        st = self.state
        name = self.target.currentText()
        s = st.begin_edit(name, label)
        if s is None:
            QMessageBox.information(self, label, "Choose a target structure."); return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            s.mask = fn(s).astype(bool)
        finally:
            QApplication.restoreOverrideCursor()
        st.end_edit()
        st.message.emit(f"{label} → {name}: {s.volume_cc(st.image):.1f} cc")

    def _mask(self, name):
        s = self.state.ss.get(name)
        return s.mask if s is not None else None

    def margin(self):
        src = self._mask(self.msrc.currentText())
        if src is None:
            return
        mz = self.mmz.value()
        self._apply("margin", lambda s: self.state.ss.margin(src.copy(), self.mmm.value(), None if mz == self.mmm.value() else mz))

    def boolean(self):
        a, b = self._mask(self.ba.currentText()), self._mask(self.bb.currentText())
        if a is None or b is None:
            return
        self._apply("Boolean", lambda s: StructureSet.boolean(a.copy(), self.bop.currentText(), b.copy()))

    def threshold(self):
        w = None if self.twithin.currentText() == "(whole image)" else self._mask(self.twithin.currentText())
        self._apply("threshold", lambda s: self.state.ss.threshold(self.tlo.value(), self.thi.value(), w))

    def interpolate(self):
        self._apply("interpolate", lambda s: self.state.ss.interpolate(s.mask))

    def fill_holes(self):
        self._apply("fill holes", lambda s: StructureSet.fill_holes(s.mask))

    def largest(self):
        self._apply("keep largest", lambda s: StructureSet.largest_component(s.mask))

    def clear(self):
        self._apply("clear", lambda s: np.zeros_like(s.mask))

    def auto_body(self):
        self._apply("body outline", lambda s: self.state.ss.external_from_threshold())


def _spin(lo, hi, dec, val=0.0):
    s = QDoubleSpinBox(); s.setRange(lo, hi); s.setDecimals(dec); s.setValue(val); s.setMaximumWidth(80)
    return s

