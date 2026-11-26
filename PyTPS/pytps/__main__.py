"""Start PyTPS:  python -m pytps  [--phantom NAME] [--dicom FOLDER] [--layout 4|1+3|1] [--screenshot FILE]"""
from __future__ import annotations

import argparse
import sys


def main(argv=None):
    ap = argparse.ArgumentParser(prog="pytps", description="PyTPS - educational treatment planning (not for clinical use)")
    ap.add_argument("--phantom", help="load a practice phantom at start, e.g. 'Thorax (lung tumour)'")
    ap.add_argument("--dicom", help="folder with DICOM CT (and RT Structure Set) to load at start")
    ap.add_argument("--layout", choices=["4", "1+3", "1"], default="4")
    ap.add_argument("--workspace", default="", help="workspace tab to show (Patient, Contouring, Planning, Evaluation)")
    ap.add_argument("--tool", default="", help="toolbar tool to select")
    ap.add_argument("--size", default="1500x900", help="window size WxH")
    ap.add_argument("--demo-plan", default="", help="add demo beams and calculate, e.g. '0,90,180,270' (gantry angles)")
    ap.add_argument("--dose-mode", default="lines", choices=["lines", "wash", "off"])
    ap.add_argument("--optimise", type=int, default=0, help="with --demo-plan: optimise the beams (Stage 1 iterations)")
    ap.add_argument("--arc", action="store_true", help="with --demo-plan: use one arc instead of static fields")
    ap.add_argument("--screenshot", help="save a screenshot after start and quit (for tests)")
    ap.add_argument("--self-test", dest="self_test", help="run a short check of the installed program and write the result (JSON)")
    a = ap.parse_args(argv)
    if a.self_test:
        return self_test(a.self_test)

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from .gui.main_window import MainWindow
    from .gui.theme import apply_theme

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("PyTPS")
    apply_theme(app)
    _set_icon(app)
    w = MainWindow()
    W, H = (int(v) for v in a.size.lower().split("x"))
    w.resize(W, H)
    w.show()
    if a.phantom:
        w.patient.load_phantom(a.phantom)
    if a.dicom:
        w.patient.choose_folder(a.dicom)
        w.patient.load_selected()
    if a.demo_plan and w.state.image is not None:
        from .gui.planning import demo_beams
        demo_beams(w.state, [float(g) for g in a.demo_plan.split(",")])
        if a.arc:
            b = w.state.plan.beams[0]; b.kind = "ARC"; b.gantry, b.arc_stop = 181.0, 179.0
            del w.state.plan.beams[1:]
        if a.optimise:
            for b in w.state.plan.beams:
                b.mlc_mode = "optimised"; b.x1 -= 5; b.x2 += 5; b.y1 -= 5; b.y2 += 5
            w.rx_panel.refresh(); w.rx_panel.store()
            w.opt_panel.it1.setValue(a.optimise); w.opt_panel.it2.setValue(max(10, a.optimise // 3))
            w.opt_panel.both()
        else:
            w.rx_panel.refresh(); w.rx_panel.calculate()
        w.set_dose_mode(a.dose_mode)
    w.grid.set_mode(a.layout)
    if a.workspace:
        for i in range(w.work.count()):
            if w.work.tabText(i).lower() == a.workspace.lower():
                w.work.setCurrentIndex(i)
    if a.tool:
        w.set_tool(a.tool)
    if a.screenshot:
        def shot():
            w.save_screenshot(a.screenshot)
            app.quit()
        QTimer.singleShot(1500, shot)
    return app.exec()


def _set_icon(app):
    import os
    from PySide6.QtGui import QIcon
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "pytps.png")
    if os.path.exists(p):
        app.setWindowIcon(QIcon(p))


def self_test(out_path):
    """Load a phantom, add two beams, calculate, optimise briefly, write a JSON report. Exit code 0 = passed."""
    import json
    import os
    import time
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from .gui.main_window import MainWindow
    from .gui.planning import demo_beams
    from . import __version__
    t0 = time.time()
    res = {"version": __version__, "ok": False}
    try:
        app = QApplication.instance() or QApplication([])
        w = MainWindow(); w.resize(1366, 768); w.show()
        w.patient.load_phantom("Pelvis (prostate)")
        demo_beams(w.state, [0, 120, 240])
        for b in w.state.plan.beams:
            b.mlc_mode = "optimised"
        w.rx_panel.refresh(); w.rx_panel.method.setCurrentText("mean"); w.rx_panel.store()
        w.opt_panel.it1.setValue(15); w.opt_panel.it2.setValue(5)
        w.opt_panel.both()
        p = w.state.plan
        from .core.plan import dvh
        d = dvh(p, w.state.engine, "PTV")
        res.update(mu=[round(b.mu, 1) for b in p.beams], ptv_mean=round(d["mean"], 2), seconds=round(time.time() - t0, 1))
        res["ok"] = bool(abs(d["mean"] - p.rx.dose) < 0.05 * p.rx.dose and all(b.mu > 0 for b in p.beams))
        w.close()
    except Exception as e:  # pragma: no cover
        import traceback
        res["error"] = repr(e); res["trace"] = traceback.format_exc()
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1)
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
