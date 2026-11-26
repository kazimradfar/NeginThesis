"""Shared application state (patient, structures, cursor, tools) with change notifications."""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QObject, Signal

WL_PRESETS = {"Soft tissue": (40, 400), "Lung": (-600, 1500), "Bone": (300, 1500), "Brain": (40, 80),
              "Mediastinum": (50, 350), "Abdomen": (40, 350)}


class AppState(QObject):
    changed = Signal(str)        # "image", "structures", "cursor", "window", "tool", "view", "plan", "dose"
    message = Signal(str)

    def __init__(self):
        super().__init__()
        self.image = None
        self.ss = None
        self.cursor = np.zeros(3)            # patient coordinates (mm) of the crosshair
        self.window = (40.0, 400.0)          # level, width
        self.tool = "select"
        self.active = None                   # name of the structure being edited
        self.brush_mm = 10.0
        self.undo_stack: list = []
        self.redo_stack: list = []
        self.plan = None
        self.engine = None                   # dose engine (built on the first calculation)
        self.engine_version = None
        self.density_version = 0
        self.cur_beam = None
        self.cp_index = 0
        self.source = ""                     # "phantom: ..." or "DICOM"
        self._models = None
        self.changed.connect(self._density_watch)

    @property
    def models(self):
        if self._models is None:
            from ..core.beamdata import default_models
            self._models = default_models()
        return self._models

    def _density_watch(self, what):
        if what == "density":
            self.density_version += 1

    # ------------------------------------------------------------------ data
    def set_case(self, image, ss, source=""):
        self.image, self.ss, self.source = image, ss, source
        ext = image.extent()
        tgt = next((s for s in ss.structures if s.is_target and s.mask.any()), None)
        if tgt is not None:
            k, j, i = [float(np.mean(a)) for a in np.nonzero(tgt.mask)]
            self.cursor = image.index_to_world((i, j, k))
        else:
            self.cursor = np.array([(a + b) / 2 for a, b in ext])
        self.active = tgt.name if tgt else (ss.structures[0].name if ss.structures else None)
        self.undo_stack.clear(); self.redo_stack.clear()
        self.plan = None; self.engine = None; self.engine_version = None; self.cur_beam = None; self.cp_index = 0
        self.changed.emit("image")

    def set_cursor(self, p):
        if self.image is None:
            return
        ext = self.image.extent()
        self.cursor = np.array([min(max(p[i], ext[i][0]), ext[i][1]) for i in range(3)])
        self.changed.emit("cursor")

    def set_window(self, level, width):
        self.window = (float(level), max(1.0, float(width)))
        self.changed.emit("window")

    def set_tool(self, tool):
        self.tool = tool
        self.changed.emit("tool")

    # ------------------------------------------------------------------ editing with undo
    def begin_edit(self, name, label="edit"):
        s = self.ss.get(name) if self.ss else None
        if s is None:
            return None
        self.undo_stack.append((label, name, s.mask.copy()))
        del self.undo_stack[:-20]
        self.redo_stack.clear()
        return s

    def end_edit(self):
        self.ss.version += 1
        self.changed.emit("structures")

    def undo(self):
        if not self.undo_stack:
            return
        label, name, mask = self.undo_stack.pop()
        s = self.ss.get(name)
        if s is not None:
            self.redo_stack.append((label, name, s.mask.copy()))
            s.mask = mask
            self.end_edit()
            self.message.emit(f"Undo: {label} ({name})")

    def redo(self):
        if not self.redo_stack:
            return
        label, name, mask = self.redo_stack.pop()
        s = self.ss.get(name)
        if s is not None:
            self.undo_stack.append((label, name, s.mask.copy()))
            s.mask = mask
            self.end_edit()
            self.message.emit(f"Redo: {label} ({name})")
