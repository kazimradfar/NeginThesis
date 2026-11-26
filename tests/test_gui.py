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


def test_plans_compare_sum_report(tmp_path):
    from PySide6.QtWidgets import QApplication
    from pytps.gui.main_window import MainWindow
    from pytps.gui.planning import demo_beams
    from pytps.core.plan import plan_sum
    app = QApplication.instance() or QApplication([])
    w = MainWindow(); w.resize(1366, 768); w.show()
    w.patient.load_phantom("Thorax (lung tumour)")
    demo_beams(w.state, [0, 180])
    w.rx_panel.refresh(); w.rx_panel.calculate()
    first = w.state.plan
    w.copy_plan(); second = w.state.plan
    assert second is not first and len(w.state.plans) == 2
    second.beams[0].gantry = 60; second.beams[1].gantry = 240; second.beam_dose.clear()
    w.rx_panel.calculate()
    w.state.compare = first; w.state.changed.emit("compare")
    w.set_dose_mode("difference"); app.processEvents()
    s = plan_sum(first, second)
    assert abs(float(s.dose.max()) - float((first.dose + second.dose).max())) < 1e-3
    w.state.points.append(("P1", w.state.plan.beams[0].iso.copy())); w.evaluation.refresh()
    w.evaluation.goal_list.append(("PTV", "D", 95.0, ">=", 57.0)); w.evaluation.refresh()
    w.evaluation.report(str(tmp_path / "r.pdf"), w)
    assert (tmp_path / "r.pdf").stat().st_size > 20000
    from pytps.gui.beamdata_dialog import BeamDataDialog
    d = BeamDataDialog(w.state, w); d.fit(); d.close()
    w.close()


def test_guide_tbi_steps_and_field_drag():
    import numpy as np
    from PySide6.QtCore import QPointF
    from PySide6.QtWidgets import QApplication
    from pytps.gui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    w = MainWindow(); w.resize(1600, 900); w.show()
    w.show_guide()
    for k in range(5):
        w.guide.run(k)
        assert w.guide.status[k].text().startswith("✔"), (k, w.guide.status[k].text())
    p = w.state.plan
    assert len(p.beams) == 6 and {round(b.iso[2]) for b in p.beams} == {-155, -425, -720}
    # drag the Y2 jaw of the first beam in the coronal view
    cor = w.views[1]; app.processEvents()
    b = p.beams[0]; y2 = b.y2
    w.state.cur_beam = b.name
    s, S, _ = cor.mapping()
    edge = S(0.0, b.iso[2] + b.y2)          # coronal: u = x, v = z (Y towards the head for HFS)
    hit = cor._field_hit(edge)
    assert hit is not None and hit[0] == "jaw" and hit[2] == "y2"
    cor._drag_field(("field",) + hit, S(0.0, b.iso[2] + b.y2 + 20))
    assert abs(b.y2 - (y2 + 20)) < 2
    w.beamviews.setCurrentIndex(2); app.processEvents()
    w.lower.setCurrentWidget(w.profile); app.processEvents()
    w.close()


def test_legend_exports_main_view_manual(tmp_path):
    import csv
    from PySide6.QtWidgets import QApplication
    from pytps.gui.main_window import MainWindow
    from pytps.gui.manual import ManualDialog, chapters, manual_path
    from pytps.gui.planning import demo_beams
    app = QApplication.instance() or QApplication([])
    w = MainWindow(); w.resize(1400, 850); w.show()
    w.patient.load_phantom("Pelvis (prostate)")
    demo_beams(w.state, [0, 90, 180, 270])
    w.rx_panel.refresh(); w.rx_panel.calculate()
    # colour bar in the wash mode: the top-right corner of the transverse view is no longer black
    w.grid.set_mode("1"); w.grid.show_view("Transverse"); app.processEvents()
    v = w.views[0]
    def corner():
        img = v.grab().toImage()
        return [img.pixelColor(x, y).name() for x in range(v.width() - 140, v.width() - 10, 3) for y in range(20, 180, 3)]
    for mode in ("wash", "lines"):
        w.set_dose_mode(mode); w.show_legend(True); app.processEvents(); a = corner()
        w.show_legend(False); app.processEvents(); b = corner()
        assert sum(p != q for p, q in zip(a, b)) > 100, mode
        w.show_legend(True)
    # DVH and profile: images and CSV
    w.dvh.recompute()
    w.dvh.save_image(str(tmp_path / "dvh.png")); w.dvh.save_csv(str(tmp_path / "dvh.csv"))
    w.profile.save_image(str(tmp_path / "prof.png")); w.profile.save_csv(str(tmp_path / "prof.csv"))
    rows = list(csv.reader(open(tmp_path / "dvh.csv")))
    assert rows[0][0] == "Dose (Gy)" and any(h.startswith("PTV") for h in rows[0])
    i = next(k for k, h in enumerate(rows[0]) if h.startswith("PTV"))
    assert float(rows[1][i]) == 100.0 and float(rows[-1][i]) < 1.0
    assert (tmp_path / "dvh.png").stat().st_size > 10000 and (tmp_path / "prof.png").stat().st_size > 5000
    # BEV, 3D and room view as the single view
    for n in ("BEV", "3D", "Room"):
        w.grid.show_view(n); app.processEvents()
        assert w.grid.focus is w.beamviews and w.beamviews.isVisible() and w.grid.current_name() == n
        assert w.mainview.currentText() == n
        assert not w.views[0].isVisible()
    w.save_view_image(str(tmp_path / "room.png"))
    assert (tmp_path / "room.png").exists()
    # manual and about text
    assert os.path.exists(manual_path())
    parts = chapters(open(manual_path(), encoding="utf-8").read())
    assert len(parts) > 10
    dlg = ManualDialog(w); dlg.show(); app.processEvents()
    assert dlg.toc.count() == len(parts) and len(dlg.view.toPlainText()) > 50
    w.close()


def test_rtdose_export_import_compare(tmp_path):
    pytest.importorskip("pydicom")
    import numpy as np
    from PySide6.QtWidgets import QApplication
    from pytps.gui.main_window import MainWindow
    from pytps.gui.planning import demo_beams
    app = QApplication.instance() or QApplication([])
    w = MainWindow(); w.resize(1200, 800); w.show()
    w.patient.load_phantom("Pelvis (prostate)")
    demo_beams(w.state, [0, 90, 180, 270]); w.rx_panel.refresh(); w.rx_panel.calculate()
    ref = w.state.plan
    w.export_rtdose(str(tmp_path / "RD.dcm"))
    n = len(w.state.plans)
    w.import_rtdose(str(tmp_path / "RD.dcm"))          # used to fail: numpy was not imported in the main window
    assert len(w.state.plans) == n + 1
    imp = w.state.plans[-1]
    inner = w.state.engine.grid.pts[:, 0] ** 2 < 1e4            # away from the grid edges
    rel = np.abs(imp.dose[inner] - ref.dose[inner]).max() / ref.dose.max()
    assert rel < 0.02, rel
    w.close()
