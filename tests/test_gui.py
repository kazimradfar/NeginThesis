import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_main_window_loads_phantom_and_contours(tmp_path):
    from PySide6.QtWidgets import QApplication
    from pytps.gui.main_window import MainWindow
    from pytps.gui.theme import apply_theme
    app = QApplication.instance() or QApplication([])
    apply_theme(app)
    w = MainWindow(); w.resize(1366, 768); w.show()
    w.patient.load_phantom("Thorax (lung tumour)")
    app.processEvents()
    st = w.state
    assert st.image is not None and st.active == "GTV" or st.active == "PTV"
    # margin into a new structure, then undo
    st.ss.add("PTV_ring")
    w.contour.refresh()
    w.contour.target.setCurrentText("PTV_ring"); w.contour.msrc.setCurrentText("PTV"); w.contour.mmm.setValue(10); w.contour.mmz.setValue(10)
    w.contour.margin()
    v = st.ss.get("PTV_ring").volume_cc(st.image)
    assert v > st.ss.get("PTV").volume_cc(st.image)
    st.undo()
    assert st.ss.get("PTV_ring").volume_cc(st.image) == 0
    for mode in ("1", "1+3", "4"):
        w.grid.set_mode(mode); app.processEvents()
    w.save_screenshot(str(tmp_path / "w.png"))
    assert (tmp_path / "w.png").stat().st_size > 10000
    w.close()


def test_plan_beams_and_dose():
    from PySide6.QtWidgets import QApplication
    from pytps.gui.main_window import MainWindow
    from pytps.gui.planning import demo_beams
    app = QApplication.instance() or QApplication([])
    w = MainWindow(); w.resize(1366, 768); w.show()
    w.patient.load_phantom("Pelvis (prostate)")
    demo_beams(w.state, [0, 90, 180, 270])
    w.rx_panel.refresh(); w.rx_panel.dose.setValue(70); w.rx_panel.fx.setValue(35); w.rx_panel.method.setCurrentText("mean")
    w.rx_panel.target.setCurrentText("PTV")
    w.rx_panel.calculate()
    app.processEvents()
    p = w.state.plan
    assert p.dose is not None and all(b.mu > 0 for b in p.beams)
    from pytps.core.plan import dvh
    d = dvh(p, w.state.engine, "PTV")
    print("rx", p.rx, "PTV mean", d["mean"], "MU", [b.mu for b in p.beams])
    assert p.rx.target == "PTV" and p.rx.method == "mean"
    assert abs(d["mean"] - 70) < 1.5
    w.beams_panel.add_arc(); app.processEvents()
    w.views[3].setCurrentIndex(1); app.processEvents(); w.views[3].setCurrentIndex(0); app.processEvents()
    w.close()
