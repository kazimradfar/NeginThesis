"""Help ▸ User manual: shows docs/USER_MANUAL.md inside the program, one chapter at a time, with search."""
from __future__ import annotations

import os
import re

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLineEdit, QListWidget, QPushButton, QSplitter, QTextBrowser,
                               QVBoxLayout)

MANUAL_URL = "https://github.com/kazimradfar/NeginThesis/blob/pytps/PyTPS/docs/USER_MANUAL.md"


def manual_path():
    """docs/USER_MANUAL.md next to the pytps package (source tree and the built program)."""
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, "docs", "USER_MANUAL.md")


def chapters(text):
    """Split the manual at level-2 headings: [(title, markdown)]. Text before the first heading is the title page."""
    parts = re.split(r"(?m)^## ", text)
    out = [("Title page", parts[0])] if parts[0].strip() else []
    for p in parts[1:]:
        title = p.splitlines()[0].strip()
        out.append((title, "## " + p))
    return out


class ManualDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PyTPS user manual")
        self.resize(1100, 760)
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.search = QLineEdit(); self.search.setPlaceholderText("Search the manual (Enter = next match)")
        self.search.returnPressed.connect(self.find); top.addWidget(self.search, 1)
        b = QPushButton("Open on GitHub"); b.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(MANUAL_URL))); top.addWidget(b)
        lay.addLayout(top)
        sp = QSplitter(Qt.Horizontal)
        self.toc = QListWidget(); self.toc.setMaximumWidth(330)
        self.view = QTextBrowser(); self.view.setOpenExternalLinks(True)
        self.view.setStyleSheet("QTextBrowser{background:#ffffff;color:#1e2430;padding:10px}")
        sp.addWidget(self.toc); sp.addWidget(self.view); sp.setStretchFactor(1, 1)
        lay.addWidget(sp, 1)
        self.parts = []
        path = manual_path()
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                self.parts = chapters(fh.read())
            self.base = QUrl.fromLocalFile(os.path.dirname(path) + os.sep)
        for t, _ in self.parts:
            self.toc.addItem(t)
        self.toc.currentRowChanged.connect(self.show_chapter)
        if self.parts:
            self.toc.setCurrentRow(0)
        else:
            self.view.setHtml(f"<p>The manual file was not found ({path}).</p><p>Read it online: <a href='{MANUAL_URL}'>{MANUAL_URL}</a></p>")

    def show_chapter(self, i):
        if not (0 <= i < len(self.parts)):
            return
        doc = self.view.document()
        doc.setBaseUrl(self.base)
        self.view.setMarkdown(self.parts[i][1])
        self.view.verticalScrollBar().setValue(0)

    def find(self):
        """Find the next match in this chapter, then in the following chapters."""
        q = self.search.text().strip()
        if not q:
            return
        if self.view.find(q):
            return
        n = len(self.parts)
        start = self.toc.currentRow()
        for k in range(1, n + 1):
            i = (start + k) % n
            if q.lower() in self.parts[i][1].lower():
                self.toc.setCurrentRow(i)
                self.view.moveCursor(self.view.textCursor().MoveOperation.Start)
                self.view.find(q)
                return
