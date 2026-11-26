"""Toolbar icons drawn with QPainter (own simple designs, no external image files)."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

INK = QColor(40, 52, 68)
ACC = QColor(31, 111, 235)
RED = QColor(220, 60, 60)


def _icon(draw) -> QIcon:
    pm = QPixmap(32, 32)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    draw(p)
    p.end()
    return QIcon(pm)


def _pen(p, c=INK, w=2.2):
    p.setPen(QPen(c, w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)


def folder():
    def d(p):
        _pen(p); p.setBrush(QColor(255, 205, 90))
        path = QPainterPath(); path.moveTo(4, 9); path.lineTo(13, 9); path.lineTo(15, 12); path.lineTo(28, 12)
        path.lineTo(28, 26); path.lineTo(4, 26); path.closeSubpath(); p.drawPath(path)
    return _icon(d)


def phantom():
    def d(p):
        _pen(p); p.setBrush(QColor(230, 236, 244))
        p.drawEllipse(QRectF(5, 8, 22, 16)); p.setBrush(QColor(120, 170, 230))
        p.drawEllipse(QRectF(9, 12, 6, 8)); p.drawEllipse(QRectF(17, 12, 6, 8))
    return _icon(d)


def save():
    def d(p):
        _pen(p); p.setBrush(QColor(200, 214, 232)); p.drawRoundedRect(QRectF(5, 5, 22, 22), 2, 2)
        p.setBrush(QColor(255, 255, 255)); p.drawRect(QRectF(10, 5, 12, 8)); p.drawRect(QRectF(9, 17, 14, 10))
    return _icon(d)


def layout(kind):
    def d(p):
        _pen(p, INK, 1.8)
        if kind == "1":
            p.drawRect(QRectF(5, 6, 22, 20))
        elif kind == "4":
            p.drawRect(QRectF(5, 6, 22, 20)); p.drawLine(16, 6, 16, 26); p.drawLine(5, 16, 27, 16)
        else:
            p.drawRect(QRectF(5, 6, 22, 20)); p.drawLine(19, 6, 19, 26); p.drawLine(19, 12.7, 27, 12.7); p.drawLine(19, 19.3, 27, 19.3)
    return _icon(d)


def cross():
    def d(p):
        _pen(p, ACC); p.drawLine(16, 4, 16, 28); p.drawLine(4, 16, 28, 16); _pen(p); p.drawEllipse(QRectF(11, 11, 10, 10))
    return _icon(d)


def pan():
    def d(p):
        _pen(p)
        for a, b, c, e in ((16, 4, 16, 28), (4, 16, 28, 16)):
            p.drawLine(a, b, c, e)
        for pts in (((16, 3), (12, 8), (20, 8)), ((16, 29), (12, 24), (20, 24)), ((3, 16), (8, 12), (8, 20)), ((29, 16), (24, 12), (24, 20))):
            p.setBrush(INK); p.drawPolygon(QPolygonF([QPointF(*q) for q in pts]))
    return _icon(d)


def zoom():
    def d(p):
        _pen(p, INK, 2.6); p.drawEllipse(QRectF(5, 5, 15, 15)); p.drawLine(18, 18, 27, 27)
        _pen(p, ACC, 2); p.drawLine(9, 12.5, 16, 12.5); p.drawLine(12.5, 9, 12.5, 16)
    return _icon(d)


def contrast():
    def d(p):
        _pen(p); p.drawEllipse(QRectF(5, 5, 22, 22)); p.setBrush(INK)
        path = QPainterPath(); path.moveTo(16, 5); path.arcTo(QRectF(5, 5, 22, 22), 90, 180); path.closeSubpath(); p.drawPath(path)
    return _icon(d)


def ruler():
    def d(p):
        _pen(p); p.setBrush(QColor(255, 225, 140))
        p.drawPolygon(QPolygonF([QPointF(4, 22), QPointF(22, 4), QPointF(28, 10), QPointF(10, 28)]))
        for t in range(4):
            p.drawLine(9 + 4 * t, 17 - 4 * t, 12 + 4 * t, 20 - 4 * t)
    return _icon(d)


def brush(erase=False):
    def d(p):
        if erase:
            _pen(p); p.setBrush(QColor(255, 170, 170))
            p.drawPolygon(QPolygonF([QPointF(6, 20), QPointF(17, 9), QPointF(26, 18), QPointF(15, 29)]))
            p.setBrush(QColor(240, 240, 240)); p.drawPolygon(QPolygonF([QPointF(6, 20), QPointF(11, 15), QPointF(20, 24), QPointF(15, 29)]))
        else:
            _pen(p); p.setBrush(QColor(200, 160, 110)); p.drawLine(26, 4, 15, 17)
            p.setBrush(ACC); p.drawEllipse(QRectF(6, 16, 11, 11))
    return _icon(d)


def polygon():
    def d(p):
        _pen(p, ACC, 2); pts = [QPointF(6, 22), QPointF(10, 7), QPointF(24, 6), QPointF(27, 20), QPointF(15, 27)]
        p.drawPolygon(QPolygonF(pts)); p.setBrush(INK)
        for q in pts:
            p.drawEllipse(q, 2.2, 2.2)
    return _icon(d)


def undo(redo=False):
    def d(p):
        _pen(p, INK, 2.4)
        path = QPainterPath()
        if redo:
            path.moveTo(8, 24); path.cubicTo(6, 12, 18, 8, 25, 13); p.drawPath(path)
            p.setBrush(INK); p.drawPolygon(QPolygonF([QPointF(27, 6), QPointF(28, 16), QPointF(19, 14)]))
        else:
            path.moveTo(24, 24); path.cubicTo(26, 12, 14, 8, 7, 13); p.drawPath(path)
            p.setBrush(INK); p.drawPolygon(QPolygonF([QPointF(5, 6), QPointF(4, 16), QPointF(13, 14)]))
    return _icon(d)


def camera():
    def d(p):
        _pen(p); p.setBrush(QColor(200, 214, 232)); p.drawRoundedRect(QRectF(4, 10, 24, 16), 3, 3)
        p.drawRect(QRectF(11, 6, 10, 4)); p.setBrush(QColor(255, 255, 255)); p.drawEllipse(QRectF(11, 12, 10, 10))
    return _icon(d)


def beam():
    def d(p):
        _pen(p); p.setBrush(QColor(255, 190, 110))
        p.drawPolygon(QPolygonF([QPointF(16, 3), QPointF(8, 27), QPointF(24, 27)]))
        _pen(p, RED, 2); p.drawLine(16, 3, 16, 27)
    return _icon(d)


def calc():
    def d(p):
        _pen(p); p.setBrush(QColor(120, 200, 140)); p.drawPolygon(QPolygonF([QPointF(9, 6), QPointF(26, 16), QPointF(9, 26)]))
    return _icon(d)
