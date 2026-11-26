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
