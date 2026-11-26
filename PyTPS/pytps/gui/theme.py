"""Application look: light desktop panels with dark image views (own design)."""
from PySide6.QtGui import QColor, QPalette


def apply_theme(app):
    app.setStyle("Fusion")
    p = QPalette()
    p.setColor(QPalette.Window, QColor(233, 236, 240))
    p.setColor(QPalette.WindowText, QColor(30, 36, 48))
    p.setColor(QPalette.Base, QColor(255, 255, 255))
    p.setColor(QPalette.AlternateBase, QColor(244, 246, 249))
    p.setColor(QPalette.Button, QColor(240, 242, 245))
    p.setColor(QPalette.ButtonText, QColor(30, 36, 48))
    p.setColor(QPalette.Highlight, QColor(31, 111, 235))
    p.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    p.setColor(QPalette.ToolTipBase, QColor(255, 255, 230))
    app.setPalette(p)
    app.setStyleSheet("""
        QToolBar { background: #dfe4ea; border-bottom: 1px solid #c3cbd5; spacing: 3px; padding: 2px; }
        QToolButton:checked { background: #c6d8f5; border: 1px solid #7aa3e0; border-radius: 3px; }
        QTabWidget::pane { border: 1px solid #c3cbd5; }
        QTabBar::tab { padding: 5px 12px; background: #dde2e8; border: 1px solid #c3cbd5; border-bottom: none; }
        QTabBar::tab:selected { background: #ffffff; font-weight: 600; }
        QGroupBox { font-weight: 600; border: 1px solid #c8d0da; border-radius: 4px; margin-top: 10px; padding-top: 6px; }
        QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 3px; }
        QStatusBar { background: #dfe4ea; }
    """)
