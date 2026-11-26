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
    ap.add_argument("--screenshot", help="save a screenshot after start and quit (for tests)")
    a = ap.parse_args(argv)

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from .gui.main_window import MainWindow
    from .gui.theme import apply_theme

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("PyTPS")
    apply_theme(app)
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


if __name__ == "__main__":
    sys.exit(main())
