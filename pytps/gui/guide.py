"""Guided exercise: VMAT total body irradiation (TBI) following the planning steps of the thesis.

Each step explains what is done and why, how it is done in a clinical planning system, and offers
"Show me" (PyTPS does the step) and "Check" (PyTPS checks what the student did)."""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDockWidget, QGroupBox, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget)

from ..core.beams import Beam
from ..core.optimise import Cost

RX, FX = 12.0, 6
THESIS_ISO = [("A", -155.0, -155.0, 175.0), ("B", -425.0, -135.0, 135.0), ("C", -720.0, -200.0, 180.0)]   # z, Y1, Y2 (mm)


def _body_z(st):
    ext = st.ss.external()
    ks = np.where(ext.mask.any(axis=(1, 2)))[0]
    z = st.image.origin[2] + ks * st.image.spacing[2]
    return float(z.min()), float(z.max())


def iso_layout(st, overlap=20.0, flash=20.0, max_len=400.0):
    """Isocentres along the body: thesis layout for the 90 cm phantom, otherwise equal fields with the overlap."""
    z0, z1 = _body_z(st)
    L = z1 - z0
    if 870 <= L <= 930 and abs(z1) < 30:
        return THESIS_ISO
    span = L + 2 * flash
    n = int(np.ceil((span - overlap) / (max_len - overlap)))
    seg = (span + overlap * (n - 1)) / n
    out = []
    top = z1 + flash
    for k in range(n):
        hi = top - k * (seg - overlap); lo = hi - seg; c = round((hi + lo) / 2)
        out.append((chr(65 + k), float(c), float(lo - c), float(hi - c)))
    return out


def iso_groups(plan):
    G = {}
    for b in plan.beams:
        G.setdefault(tuple(np.round(b.iso, 1)), []).append(b)
    return sorted(G.items(), key=lambda kv: -kv[0][2])


STEPS = [
    ("1 · Patient and CT",
     "TBI is planned on a whole-body CT, head first supine. A body this long is often scanned in two parts (head-first and "
     "feet-first); here the 90 cm phantom of the thesis is used.<br><i>Clinical system:</i> create the patient, import the CT, "
     "check the patient position (HFS) and the image orientation."),
    ("2 · Contours",
     "Body outline (EXTERNAL), right and left lung, kidneys. Lungs = Lung_R ∪ Lung_L. "
     "PTV_TBI = BODY contracted by 3 mm (skin build-up) minus the lungs contracted by 2 mm, so the optimiser can lower the lung dose.<br>"
     "<i>Clinical system:</i> contouring workspace, Boolean and margin tools; give the PTV the type PTV."),
    ("3 · Isocentres and arcs",
     "One field of the linac is at most 40 cm long, so the body is split into several isocentres along the patient. "
     "Neighbouring fields overlap by about 2 cm (thesis) so that the junctions are not cold; the first and last fields "
     "extend about 2 cm beyond the body. Each isocentre gets two full arcs (clockwise 181→179°, counter-clockwise 179→181°), "
     "6 MV, jaws X ±20 cm, MLC optimised.<br><i>Clinical system:</i> new VMAT plan, add isocentres (couch shifts between them), "
     "add two arcs per isocentre, set the Y jaws per isocentre. Drag the field edges or the isocentre in the slice views to adjust."),
    ("4 · Prescription",
     "12 Gy in 6 fractions (2 Gy twice daily) to PTV_TBI, normalised so that the mean PTV dose equals the prescription."),
    ("5 · IMRT constraints",
     "Thesis cost functions: PTV target penalty 12 Gy, PTV quadratic overdose 13.2 Gy, lungs parallel 8 Gy with 55 % mean organ "
     "damage (keeps the mean lung dose below about 10 Gy), lungs quadratic overdose 10 Gy, body maximum dose 14.4 Gy (120 %)."),
    ("6 · Optimisation",
     "Stage 1 optimises the fluence of every arc sector; Stage 2 converts it into MLC apertures and optimises their weights. "
     "Whole-body plans take about two to three minutes here (much longer in a clinical system)."),
    ("7 · Evaluation and junctions",
     "Goals: PTV V90% ≥ 95 %, D2% ≤ 110 % (13.2 Gy), mean lung dose ≤ 10 Gy, body near-maximum D0.1% ≤ 120 %. "
     "Look at the dose profile along the body (lower area ▸ Profile) at each junction: no cold or hot band should appear where "
     "the fields of two isocentres overlap."),
    ("8 · Robustness of the junctions",
     "Plans ▸ Copy plan. In the copy, drag isocentre B 5 mm up or down in the coronal view (the arcs keep their MLC), "
     "press F5 to recalculate, then Evaluation ▸ Compare with the original. The profile shows how sensitive the junction is to a "
     "set-up error; a wider overlap makes it less sensitive."),
]


class GuideDock(QDockWidget):
    def __init__(self, window):
        super().__init__("Guided exercise: VMAT-TBI", window)
        self.w = window
        self.st = window.state
        self.setObjectName("guide")
        inner = QWidget(); lay = QVBoxLayout(inner)
        intro = QLabel("<b>VMAT total body irradiation</b> (aims of the thesis): homogeneous dose to the whole body with a "
                       "lower lung dose, delivered with several isocentres and arcs. Do each step yourself and press <b>Check</b>, "
                       "or press <b>Show me</b> to let PyTPS do it.")
        intro.setWordWrap(True); lay.addWidget(intro)
        self.status = []
        for k, (title, text) in enumerate(STEPS):
            g = QGroupBox(title); gl = QVBoxLayout(g)
            lab = QLabel(text); lab.setWordWrap(True); lab.setTextFormat(Qt.RichText); gl.addWidget(lab)
            row = QHBoxLayout()
            show = QPushButton("Show me"); show.clicked.connect(lambda _=False, k=k: self.run(k)); row.addWidget(show)
            chk = QPushButton("Check"); chk.clicked.connect(lambda _=False, k=k: self.check(k)); row.addWidget(chk)
            row.addStretch(1); gl.addLayout(row)
            res = QLabel(""); res.setWordWrap(True); gl.addWidget(res); self.status.append(res)
            lay.addWidget(g)
        lay.addStretch(1)
        sc = QScrollArea(); sc.setWidget(inner); sc.setWidgetResizable(True); sc.setMinimumWidth(340)
        self.setWidget(sc)

    def _say(self, k, ok, text):
        self.status[k].setText(("✔ " if ok else "✘ ") + text)
        self.status[k].setStyleSheet("color:#1b8a4b" if ok else "color:#c0392b")

    # ------------------------------------------------------------------ show me
    def run(self, k):
        w, st = self.w, self.st
        try:
            if k == 0:
                w.patient.load_phantom("Whole body 90 cm (TBI)")
            elif k == 1:
                ss = st.ss
                lungs = None
                for n in ("Lung_R", "Lung_L"):
                    s = ss.get(n)
                    if s is not None:
                        lungs = s.mask.copy() if lungs is None else lungs | s.mask
                if lungs is None:
                    raise RuntimeError("No lung contours found")
                if ss.get("Lungs") is None:
                    ss.add("Lungs", lungs, (79, 216, 255), "ORGAN")
                else:
                    ss.get("Lungs").mask = lungs
                ptv = ss.margin(ss.external().mask, -3) & ~ss.margin(lungs, -2)
                if ss.get("PTV_TBI") is None:
                    ss.add("PTV_TBI", ptv, (255, 64, 64), "PTV")
                else:
                    ss.get("PTV_TBI").mask = ptv
                ss.version += 1; st.changed.emit("structures")
            elif k == 2:
                from .planning import ensure_plan
                p = ensure_plan(st)
                p.beams.clear(); p.beam_dose.clear()
                cx = 0.0
                for name, zc, lo, hi in iso_layout(st):
                    for d in ("CW", "CCW"):
                        b = Beam(f"{name}{1 if d == 'CW' else 2}", np.array([cx, 0.0, zc]), energy="6X", kind="ARC",
                                 gantry=181.0 if d == "CW" else 179.0, arc_stop=179.0 if d == "CW" else 181.0, arc_dir=d,
                                 x1=-200, x2=200, y1=lo, y2=hi)
                        b.mlc_mode = "optimised"; p.beams.append(b)
                st.cur_beam = p.beams[0].name; st.cp_index = 0
                st.changed.emit("plan")
                w.show_planning(0)
            elif k == 3:
                from .planning import ensure_plan
                p = ensure_plan(st)
                p.rx.dose, p.rx.fractions, p.rx.target, p.rx.method, p.rx.percent = RX, FX, "PTV_TBI", "mean", 100.0
                w.rx_panel.refresh(); w.rx_panel.grid.setValue(8.0); w.show_planning(1)
            elif k == 4:
                from .planning import ensure_plan
                ensure_plan(st).costs = [Cost("PTV_TBI", "Target Penalty", 12.0, 95, 1.5), Cost("PTV_TBI", "Quadratic Overdose", 13.2, 0.3),
                                         Cost("Lungs", "Parallel", 8.0, 55), Cost("Lungs", "Quadratic Overdose", 10.0, 0.5, 0.5),
                                         Cost("BODY", "Maximum Dose", 14.4)]
                st.changed.emit("costs"); w.show_planning(2)
            elif k == 5:
                o = w.opt_panel
                o.it1.setValue(80); o.it2.setValue(20); o.arcsp.setValue(15); o.aps.setValue(3); o.rate.setValue(600)
                w.show_planning(3)
                o.both()
            elif k == 6:
                ev = w.evaluation
                ev.goal_list = [("PTV_TBI", "V", 0.9 * RX, ">=", 95.0), ("PTV_TBI", "D", 2.0, "<=", 1.1 * RX),
                                ("Lungs", "Dmean", 0.0, "<=", 10.0), ("BODY", "D", 0.1, "<=", 1.2 * RX)]
                b = st.plan.beams[0] if st.plan and st.plan.beams else None
                if b is not None:
                    st.set_cursor(np.array([0.0, 8.0, st.cursor[2]]))
                w.work.setCurrentWidget(w.evaluation); ev.refresh()
                w.lower.setCurrentWidget(w.profile); w.profile.axis = "z"; w.profile.update()
            elif k == 7:
                w.copy_plan()
                self.status[7].setText("A copy of the plan was made. Now drag isocentre B by 5 mm in the coronal view, press F5, "
                                       "and compare with the original in Evaluation.")
                return
        except Exception as e:
            self._say(k, False, f"Could not do this step: {e}"); return
        self.check(k)

    # ------------------------------------------------------------------ checks
    def check(self, k):
        st = self.st
        if st.image is None:
            self._say(k, False, "Load the patient first (step 1)."); return
        p = st.plan
        if k == 0:
            z0, z1 = _body_z(st)
            ok = (z1 - z0) > 800
            self._say(k, ok, f"Body length {(z1 - z0) / 10:.0f} cm, patient position {st.image.orientation}." + ("" if ok else " A whole-body CT is needed."))
        elif k == 1:
            s, l = st.ss.get("PTV_TBI"), st.ss.get("Lungs")
            ok = s is not None and s.mask.any() and s.type == "PTV" and l is not None
            self._say(k, ok, f"PTV_TBI {s.volume_cc(st.image) / 1000:.1f} L, Lungs {l.volume_cc(st.image):.0f} cc." if ok
                      else "PTV_TBI (type PTV) and Lungs are needed.")
        elif k == 2:
            if p is None or not p.beams:
                self._say(k, False, "No beams yet."); return
            G = iso_groups(p)
            msgs, ok = [], len(G) >= 2
            z0, z1 = _body_z(st)
            spans = []
            for iso, beams in G:
                lo = min(b.iso[2] + b.y1 for b in beams); hi = max(b.iso[2] + b.y2 for b in beams)
                spans.append((lo, hi))
                if hi - lo > 400.5:
                    ok = False; msgs.append(f"field at z {iso[2] / 10:.1f} cm is {(hi - lo) / 10:.1f} cm long (max 40)")
                if sum(b.kind == "ARC" for b in beams) < 2:
                    msgs.append(f"isocentre at z {iso[2] / 10:.1f} cm has fewer than two arcs")
            for (lo1, hi1), (lo2, hi2) in zip(spans[:-1], spans[1:]):
                ov = hi2 - lo1
                if ov < 15:
                    ok = False; msgs.append(f"gap or small overlap at z {lo1 / 10:.1f} cm ({ov / 10:.1f} cm)")
                else:
                    msgs.append(f"overlap {ov / 10:.1f} cm at z {lo1 / 10:.1f} cm")
            if spans[0][1] < z1 or spans[-1][0] > z0:
                ok = False; msgs.append("the fields do not cover the whole body")
            self._say(k, ok, f"{len(G)} isocentres, {len(p.beams)} beams. " + "; ".join(msgs))
        elif k == 3:
            ok = p is not None and abs(p.rx.dose - RX) < 1e-6 and p.rx.fractions == FX and p.rx.target == "PTV_TBI"
            self._say(k, ok, f"{p.rx.dose:g} Gy in {p.rx.fractions} fractions to {p.rx.target}, normalised to {p.rx.method}." if p else "No plan.")
        elif k == 4:
            ok = p is not None and any(c.on and c.structure == "PTV_TBI" and c.type == "Target Penalty" for c in p.costs) and \
                any(c.on and c.structure == "Lungs" for c in p.costs)
            self._say(k, ok, f"{sum(c.on for c in p.costs)} cost functions." if ok else "A target penalty on PTV_TBI and a lung cost function are needed.")
        elif k == 5:
            ok = p is not None and p.dose is not None and all(b.cps for b in p.beams if b.mlc_mode == "optimised")
            self._say(k, ok, f"Optimised: {sum(b.mu for b in p.beams):.0f} MU per fraction." if ok else "Run Stage 1 and Stage 2.")
        elif k == 6:
            if p is None or p.dose is None:
                self._say(k, False, "No dose yet."); return
            from ..core.plan import dvh
            d, l = dvh(p, st.engine, "PTV_TBI"), dvh(p, st.engine, "Lungs")
            v90, d2, lm = d["V"](0.9 * RX), d["D"](2), l["mean"] if l else float("nan")
            ok = v90 >= 95 and d2 <= 1.1 * RX and lm <= 10
            self._say(k, ok, f"PTV V90% {v90:.1f} % (thesis literature 98.8 %), D2% {d2:.2f} Gy, mean lung dose {lm:.2f} Gy "
                             f"(literature 8.8 Gy). " + ("All goals met." if ok else "Adjust the cost functions or the overlaps and optimise again."))
        elif k == 7:
            ok = len(st.plans) >= 2 and st.compare is not None
            self._say(k, ok, "Plans compared." if ok else "Make a copy, shift an isocentre, recalculate and choose Compare with.")
