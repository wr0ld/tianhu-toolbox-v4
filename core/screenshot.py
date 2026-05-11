import os
import math
import logging
from datetime import datetime

from PyQt6.QtCore import Qt, QRect, QRectF, QPoint, QPointF
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QFont, QPixmap, QPainterPath,
)
from PyQt6.QtWidgets import (
    QWidget, QApplication, QHBoxLayout, QPushButton, QLabel,
    QFileDialog, QTextEdit,
)

logger = logging.getLogger(__name__)

_MIN_SEL = 10
_HANDLE_SIZE = 8

_TOOL_COLORS = [
    QColor("#FF4444"),
    QColor("#FF8C00"),
    QColor("#FFCC00"),
    QColor("#4CAF50"),
    QColor("#FFFFFF"),
    QColor("#000000"),
]

_TOOL_LABELS = [
    ("画笔", "draw"),
    ("箭头", "arrow"),
    ("文字", "text"),
    ("马赛克", "mosaic"),
    ("橡皮", "eraser"),
]

_H_TL, _H_TR, _H_BL, _H_BR = 0, 1, 2, 3
_H_T, _H_B, _H_L, _H_R = 4, 5, 6, 7


class ScreenshotOverlay(QWidget):

    def __init__(self, parent=None, callback=None):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setWindowOpacity(1.0)
        self._callback = callback

        self._screen_fullres = None

        self._screen_fullres_img = None

        self._dpr = 1.0

        self._sel_start = None
        self._sel_end = None
        self._phase = "idle"
        self._active_handle = -1
        self._move_origin = None
        self._move_rect_origin = None

        self._tool = None
        self._color = QColor("#FF0000")
        self._color_index = 0
        self._pen_size = 3
        self._annotations = []
        self._undo_stack = []
        self._current_stroke = None
        self._current_points = []

        self._text_edit = None
        self._toolbar = None
        self._tool_btns = {}
        self._status_label = None
        self._undo_btn = None
        self._color_btn = None

        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)


    def show_and_capture(self):
        screen = QApplication.primaryScreen()
        if not screen:
            logger.error("No primary screen found")
            return
        geo = screen.geometry()
        dpr = screen.devicePixelRatio()
        full = screen.grabWindow(0)

        full.setDevicePixelRatio(1.0)
        full_img = full.toImage()
        full_img.setDevicePixelRatio(1.0)
        cap_w, cap_h = full_img.width(), full_img.height()

        px = int(geo.x() * dpr)
        py = int(geo.y() * dpr)
        pw = int(geo.width() * dpr)
        ph = int(geo.height() * dpr)

        if (0 <= px < cap_w and 0 <= py < cap_h
                and pw > 0 and ph > 0
                and px + pw <= cap_w and py + ph <= cap_h):
            fullres_img = full_img.copy(px, py, pw, ph)
        else:
            lx, ly = geo.x(), geo.y()
            lw2, lh2 = geo.width(), geo.height()
            if (0 <= lx < cap_w and 0 <= ly < cap_h
                    and lw2 > 0 and lh2 > 0
                    and lx + lw2 <= cap_w and ly + lh2 <= cap_h):
                fullres_img = full_img.copy(lx, ly, lw2, lh2)
            else:
                fullres_img = full_img.copy(
                    max(0, min(lx, cap_w - 1)),
                    max(0, min(ly, cap_h - 1)),
                    min(lw2, cap_w),
                    min(lh2, cap_h),
                )

        fw, fh = fullres_img.width(), fullres_img.height()
        lw, lh = geo.width(), geo.height()
        self._dpr = (fw / lw + fh / lh) / 2.0 if lw > 0 and lh > 0 else 1.0

        self._screen_fullres = QPixmap.fromImage(fullres_img.copy())
        self._screen_fullres_img = fullres_img

        logger.info(
            f"截图: 捕获 {cap_w}×{cap_h}, 区域 {fw}×{fh}, "
            f"逻辑 {lw}×{lh}, DPR={self._dpr:.2f}"
        )

        self.setGeometry(geo)
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()


    def _selection_rect(self):
        if self._sel_start is None or self._sel_end is None:
            return QRect()
        x1, y1 = self._sel_start.x(), self._sel_start.y()
        x2, y2 = self._sel_end.x(), self._sel_end.y()
        return QRect(min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))

    def _set_selection_rect(self, rect):
        self._sel_start = rect.topLeft()
        self._sel_end = rect.bottomRight()

    def _handle_rects(self):
        r = self._selection_rect()
        if r.width() < 1 or r.height() < 1:
            return {}
        hs = _HANDLE_SIZE
        hh = hs // 2
        cx, cy = r.center().x(), r.center().y()
        return {
            _H_TL: QRect(r.left() - hh, r.top() - hh, hs, hs),
            _H_TR: QRect(r.right() - hh, r.top() - hh, hs, hs),
            _H_BL: QRect(r.left() - hh, r.bottom() - hh, hs, hs),
            _H_BR: QRect(r.right() - hh, r.bottom() - hh, hs, hs),
            _H_T:  QRect(cx - hh, r.top() - hh, hs, hs),
            _H_B:  QRect(cx - hh, r.bottom() - hh, hs, hs),
            _H_L:  QRect(r.left() - hh, cy - hh, hs, hs),
            _H_R:  QRect(r.right() - hh, cy - hh, hs, hs),
        }

    _HC = {
        _H_TL: Qt.CursorShape.SizeFDiagCursor, _H_BR: Qt.CursorShape.SizeFDiagCursor,
        _H_TR: Qt.CursorShape.SizeBDiagCursor, _H_BL: Qt.CursorShape.SizeBDiagCursor,
        _H_T:  Qt.CursorShape.SizeVerCursor,   _H_B:  Qt.CursorShape.SizeVerCursor,
        _H_L:  Qt.CursorShape.SizeHorCursor,   _H_R:  Qt.CursorShape.SizeHorCursor,
    }

    def _hit_test(self, pos):
        for idx, hr in self._handle_rects().items():
            if hr.adjusted(-4, -4, 4, 4).contains(pos):
                return idx, "handle"
        if self._selection_rect().contains(pos):
            return -1, "inside"
        return -1, "outside"


    def paintEvent(self, event):
        if self._screen_fullres_img is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        img = self._screen_fullres_img
        dpr = self._dpr
        w, h = self.width(), self.height()

        painter.drawImage(
            QRectF(0, 0, w, h),
            img,
            QRectF(0, 0, img.width(), img.height()),
        )

        painter.fillRect(self.rect(), QColor(0, 0, 0, 100))

        sel = self._selection_rect()
        if sel.isValid() and sel.width() > 1 and sel.height() > 1:
            painter.save()
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            painter.fillRect(sel, Qt.GlobalColor.transparent)
            painter.restore()
            src = QRectF(
                sel.x() * dpr, sel.y() * dpr,
                sel.width() * dpr, sel.height() * dpr,
            )
            painter.drawImage(QRectF(sel), img, src)

        if sel.isValid():
            painter.save()
            painter.setClipRect(sel.adjusted(0, 0, 1, 1))
            for ann in self._annotations:
                self._draw_annotation(painter, ann, hires=False)
            if self._current_stroke:
                self._draw_annotation(painter, self._current_stroke, hires=False)
            painter.restore()

        if sel.isValid() and sel.width() > 1 and sel.height() > 1:
            painter.setPen(QPen(QColor("#38BDF8"), 1.5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(sel)
            for hr in self._handle_rects().values():
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor("#38BDF8"))
                painter.drawRoundedRect(hr, 2, 2)
            self._draw_size_label(painter, sel)

        painter.end()

    def _draw_size_label(self, painter, sel):
        w, h = sel.width(), sel.height()
        txt = f"{w} × {h}"
        font = QFont("Microsoft YaHei", 9)
        painter.setFont(font)
        fm = painter.fontMetrics()
        tw = fm.horizontalAdvance(txt) + 14
        th = fm.height() + 6
        tx = sel.left()
        ty = sel.top() - th - 4
        if ty < 0:
            ty = sel.bottom() + 4
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 170))
        painter.drawRoundedRect(QRect(tx, ty, tw, th), 4, 4)
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(QRect(tx, ty, tw, th), Qt.AlignmentFlag.AlignCenter, txt)


    def _draw_annotation(self, painter, ann, hires=False):
        atype = ann.get("type", "")

        if atype in ("draw", "eraser"):
            pts = ann.get("points", [])
            if len(pts) < 2:
                return
            if atype == "eraser":
                pen_w = ann.get("size", 14)
                img = self._screen_fullres_img
                dpr = self._dpr
                for pt in pts:
                    half = pen_w // 2
                    dest = QRectF(pt.x() - half, pt.y() - half, pen_w, pen_w)
                    src = QRectF(
                        (pt.x() - half) * dpr, (pt.y() - half) * dpr,
                        pen_w * dpr, pen_w * dpr,
                    )
                    painter.drawImage(dest, img, src)
            else:
                color = ann.get("color", QColor("#FF0000"))
                pen = QPen(color, ann.get("size", 3))
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                painter.setPen(pen)
                for i in range(1, len(pts)):
                    painter.drawLine(pts[i - 1], pts[i])

        elif atype == "arrow":
            start = ann.get("start")
            end = ann.get("end")
            if not start or not end:
                return
            color = ann.get("color", QColor("#FF0000"))
            pen = QPen(color, ann.get("size", 3))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawLine(start, end)
            dx = end.x() - start.x()
            dy = end.y() - start.y()
            length = math.sqrt(dx * dx + dy * dy)
            if length < 2:
                return
            ux, uy = dx / length, dy / length
            hl = min(18, length * 0.3)
            p1x = end.x() - hl * (ux * 0.866 + uy * 0.5)
            p1y = end.y() - hl * (uy * 0.866 - ux * 0.5)
            p2x = end.x() - hl * (ux * 0.866 - uy * 0.5)
            p2y = end.y() - hl * (uy * 0.866 + ux * 0.5)
            path = QPainterPath()
            path.moveTo(QPointF(float(end.x()), float(end.y())))
            path.lineTo(QPointF(p1x, p1y))
            path.lineTo(QPointF(p2x, p2y))
            path.closeSubpath()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.fillPath(path, color)

        elif atype == "mosaic":
            pts = ann.get("points", [])
            size = ann.get("size", 12)
            img = self._screen_fullres_img
            dpr = self._dpr
            for pt in pts:
                self._draw_mosaic(painter, pt, size, img, dpr)

        elif atype == "text":
            pos = ann.get("pos")
            text = ann.get("text", "")
            if not pos or not text:
                return
            font = QFont("Microsoft YaHei", ann.get("size", 14))
            painter.setFont(font)
            painter.setPen(ann.get("color", QColor("#FF0000")))
            y = pos.y()
            for line in text.split("\n"):
                painter.drawText(QPointF(float(pos.x()), float(y)), line)
                y += painter.fontMetrics().height()

    def _draw_mosaic(self, painter, center, size, image, dpr):
        if image is None:
            return
        half = size // 2
        r = QRect(center.x() - half, center.y() - half, size, size)
        block = max(6, size // 3)
        x = r.left()
        while x < r.right():
            y = r.top()
            while y < r.bottom():
                sx = max(0, min(int((x + block // 2) * dpr), image.width() - 1))
                sy = max(0, min(int((y + block // 2) * dpr), image.height() - 1))
                try:
                    color = QColor.fromRgb(image.pixel(sx, sy))
                except Exception:
                    color = QColor(128, 128, 128)
                painter.fillRect(QRect(x, y, block, block), color)
                y += block
            x += block


    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = event.pos()
        if self._phase == "idle":
            self._sel_start = pos
            self._sel_end = pos
            self._phase = "selecting"
            self.update()
            return
        if self._phase == "selected":
            hidx, region = self._hit_test(pos)
            if region == "handle":
                self._phase = "resizing"
                self._active_handle = hidx
                return
            if region == "inside":
                if self._tool:
                    self._start_drawing(pos)
                    return
                self._phase = "moving"
                self._move_origin = pos
                self._move_rect_origin = self._selection_rect()
                self.setCursor(Qt.CursorShape.SizeAllCursor)
                return
            self._reset_selection()
            self._sel_start = pos
            self._sel_end = pos
            self._phase = "selecting"
            self.update()

    def mouseMoveEvent(self, event):
        pos = event.pos()
        if self._phase == "selecting":
            self._sel_end = pos
            self.update()
            return
        if self._phase == "resizing":
            self._do_resize(pos)
            self.update()
            return
        if self._phase == "moving":
            delta = pos - self._move_origin
            nr = self._move_rect_origin.translated(delta).intersected(self.rect())
            if nr.isValid() and nr.width() > 2 and nr.height() > 2:
                self._set_selection_rect(nr)
            self.update()
            return
        if self._phase == "drawing" and self._current_stroke:
            self._continue_drawing(pos)
            self.update()
            return
        if self._phase == "selected":
            hidx, region = self._hit_test(pos)
            if region == "handle":
                self.setCursor(self._HC.get(hidx, Qt.CursorShape.ArrowCursor))
            elif region == "inside":
                self.setCursor(Qt.CursorShape.CrossCursor if self._tool
                               else Qt.CursorShape.SizeAllCursor)
            else:
                self.setCursor(Qt.CursorShape.CrossCursor)

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._phase == "selecting":
            sel = self._selection_rect()
            if sel.width() >= _MIN_SEL and sel.height() >= _MIN_SEL:
                self._phase = "selected"
                self._build_toolbar()
            else:
                self._phase = "idle"
                self._sel_start = self._sel_end = None
            self.update()
            return
        if self._phase == "resizing":
            self._phase = "selected"
            self._reposition_toolbar()
            self._update_status()
            self.update()
            return
        if self._phase == "moving":
            self._phase = "selected"
            self._reposition_toolbar()
            self._update_status()
            self.setCursor(Qt.CursorShape.SizeAllCursor)
            self.update()
            return
        if self._phase == "drawing":
            self._finish_drawing()

    def _do_resize(self, pos):
        h = self._active_handle
        s, e = self._sel_start, self._sel_end
        if s is None or e is None:
            return
        x1, y1, x2, y2 = s.x(), s.y(), e.x(), e.y()
        if h == _H_TL:   x1, y1 = pos.x(), pos.y()
        elif h == _H_TR: x2, y1 = pos.x(), pos.y()
        elif h == _H_BL: x1, y2 = pos.x(), pos.y()
        elif h == _H_BR: x2, y2 = pos.x(), pos.y()
        elif h == _H_T:  y1 = pos.y()
        elif h == _H_B:  y2 = pos.y()
        elif h == _H_L:  x1 = pos.x()
        elif h == _H_R:  x2 = pos.x()
        self._sel_start = QPoint(min(x1, x2), min(y1, y2))
        self._sel_end = QPoint(max(x1, x2), max(y1, y2))


    def _start_drawing(self, pos):
        if self._tool == "text":
            self._start_text_input(pos)
            return
        self._phase = "drawing"
        self._current_points = [pos]
        if self._tool in ("draw", "eraser", "mosaic"):
            self._current_stroke = {
                "type": self._tool, "points": [pos],
                "color": self._color,
                "size": self._pen_size if self._tool != "eraser" else 14,
            }
        elif self._tool == "arrow":
            self._current_stroke = {
                "type": "arrow", "start": pos, "end": pos,
                "color": self._color, "size": self._pen_size,
            }

    def _continue_drawing(self, pos):
        if not self._current_stroke:
            return
        if self._current_stroke["type"] in ("draw", "eraser", "mosaic"):
            self._current_points.append(pos)
            self._current_stroke["points"] = self._current_points
        elif self._current_stroke["type"] == "arrow":
            self._current_stroke["end"] = pos

    def _finish_drawing(self):
        if self._current_stroke:
            atype = self._current_stroke.get("type", "")
            if atype in ("draw", "eraser", "mosaic") and len(self._current_points) >= 2:
                self._annotations.append(self._current_stroke)
                self._undo_stack.append(self._current_stroke)
            elif atype == "arrow":
                s, e = self._current_stroke.get("start"), self._current_stroke.get("end")
                if s and e and (s - e).manhattanLength() > 3:
                    self._annotations.append(self._current_stroke)
                    self._undo_stack.append(self._current_stroke)
        self._current_stroke = None
        self._current_points = []
        self._phase = "selected"
        self._update_undo_btn()
        self.update()


    def _start_text_input(self, pos):
        if self._text_edit is not None:
            self._finalize_text()
        self._text_edit = QTextEdit(self)
        self._text_edit.setFrameStyle(0)
        self._text_edit.setStyleSheet(
            "QTextEdit{background:rgba(0,0,0,0.5);color:%s;"
            "font-size:14px;border:1px dashed #38BDF8;border-radius:3px;padding:2px;}"
            % self._color.name()
        )
        self._text_edit.setFont(QFont("Microsoft YaHei", 14))
        self._text_edit.setFixedSize(220, 64)
        self._text_edit.move(pos)
        self._text_edit.show()
        self._text_edit.setFocus()

    def _finalize_text(self):
        if self._text_edit is None:
            return
        text = self._text_edit.toPlainText().strip()
        if text:
            ann = {
                "type": "text", "pos": self._text_edit.pos(),
                "text": text, "color": self._color, "size": 14,
            }
            self._annotations.append(ann)
            self._undo_stack.append(ann)
            self._update_undo_btn()
        self._text_edit.deleteLater()
        self._text_edit = None
        self.update()


    def _reset_selection(self):
        self._remove_toolbar()
        self._annotations.clear()
        self._undo_stack.clear()
        self._current_stroke = None
        self._current_points = []
        self._tool = None
        self._tool_btns.clear()
        if self._text_edit:
            self._text_edit.deleteLater()
            self._text_edit = None
        self._sel_start = self._sel_end = None


    def _build_toolbar(self):
        if self._toolbar is not None:
            self._remove_toolbar()
        self._toolbar = QWidget(self)
        self._toolbar.setObjectName("ssTB")
        self._toolbar.setStyleSheet(
            "QWidget#ssTB{background:rgba(24,24,30,240);border-radius:8px;}"
            "QPushButton{background:rgba(255,255,255,0.08);color:#ddd;border:none;"
            "border-radius:5px;padding:4px 10px;font-size:12px;font-weight:500;}"
            "QPushButton:hover{background:rgba(255,255,255,0.18);color:#fff;}"
            "QPushButton:checked{background:rgba(56,189,248,0.3);color:#38BDF8;"
            "border:1px solid #38BDF8;}"
            "QLabel{color:#888;font-size:11px;background:transparent;}"
        )
        lay = QHBoxLayout(self._toolbar)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(2)

        self._tool_btns = {}
        for label, name in _TOOL_LABELS:
            btn = QPushButton(label)
            btn.setFixedHeight(28)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, n=name: self._set_tool(n))
            lay.addWidget(btn)
            self._tool_btns[name] = btn

        lay.addSpacing(6)
        self._color_btn = QPushButton("颜色")
        self._color_btn.setFixedHeight(28)
        self._color_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._color_btn.clicked.connect(self._cycle_color)
        lay.addWidget(self._color_btn)
        self._update_color_btn()

        self._undo_btn = QPushButton("撤销")
        self._undo_btn.setFixedHeight(28)
        self._undo_btn.setEnabled(False)
        self._undo_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._undo_btn.clicked.connect(self._undo)
        lay.addWidget(self._undo_btn)

        lay.addSpacing(6)
        self._status_label = QLabel()
        lay.addWidget(self._status_label)
        self._update_status()

        lay.addSpacing(8)
        save_btn = QPushButton("保存")
        save_btn.setStyleSheet(
            "QPushButton{background:#38BDF8;color:#000;font-weight:bold;border-radius:5px;}"
            "QPushButton:hover{background:#60CCFF;}"
        )
        save_btn.setFixedHeight(28)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.clicked.connect(self._save_to_clipboard_and_close)
        lay.addWidget(save_btn)

        save_as_btn = QPushButton("另存为")
        save_as_btn.setFixedHeight(28)
        save_as_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_as_btn.clicked.connect(self._save_as_file)
        lay.addWidget(save_as_btn)

        cancel_btn = QPushButton("取消")
        cancel_btn.setStyleSheet(
            "QPushButton{background:#EF4444;color:#fff;border-radius:5px;}"
            "QPushButton:hover{background:#FF6B6B;}"
        )
        cancel_btn.setFixedHeight(28)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.clicked.connect(self._cleanup)
        lay.addWidget(cancel_btn)
        self._position_toolbar()

    def _position_toolbar(self):
        if not self._toolbar:
            return
        sel = self._selection_rect()
        self._toolbar.adjustSize()
        tw = self._toolbar.sizeHint().width()
        th = self._toolbar.sizeHint().height()
        tx = max(0, min(sel.left() + (sel.width() - tw) // 2, self.width() - tw - 4))
        ty = sel.bottom() + 6
        if ty + th > self.height():
            ty = sel.top() - th - 6
        ty = max(0, min(ty, self.height() - th - 4))
        self._toolbar.move(tx, ty)
        self._toolbar.show()

    def _reposition_toolbar(self):
        if self._toolbar:
            self._position_toolbar()

    def _remove_toolbar(self):
        if self._toolbar is not None:
            try:
                self._toolbar.close()
                self._toolbar.deleteLater()
            except Exception:
                pass
            self._toolbar = None
            self._tool_btns = {}
            self._undo_btn = None
            self._status_label = None
            self._color_btn = None

    def _update_undo_btn(self):
        if self._undo_btn:
            self._undo_btn.setEnabled(len(self._undo_stack) > 0)

    def _update_status(self):
        if self._status_label:
            sel = self._selection_rect()
            self._status_label.setText(
                f"{sel.width()}×{sel.height()}" if sel.isValid() else ""
            )

    def _update_color_btn(self):
        if self._color_btn:
            c = self._color.name()
            fg = "#fff" if self._color.lightness() < 128 else "#000"
            self._color_btn.setStyleSheet(
                f"QPushButton{{background:{c};color:{fg};font-weight:bold;"
                f"border-radius:5px;padding:4px 10px;}}"
                f"QPushButton:hover{{background:{c};}}"
            )


    def _set_tool(self, name):
        self._tool = name
        for n, btn in self._tool_btns.items():
            btn.setChecked(n == name)
        if name != "text" and self._text_edit:
            self._finalize_text()
        self.setCursor(Qt.CursorShape.CrossCursor)

    def _cycle_color(self):
        self._color_index = (self._color_index + 1) % len(_TOOL_COLORS)
        self._color = _TOOL_COLORS[self._color_index]
        self._update_color_btn()

    def _undo(self):
        if self._undo_stack:
            last = self._undo_stack.pop()
            if last in self._annotations:
                self._annotations.remove(last)
            self._update_undo_btn()
            self.update()


    def _get_result_pixmap(self):
        sel = self._selection_rect()
        if not sel.isValid() or sel.width() < 1 or sel.height() < 1:
            return None

        dpr = self._dpr
        img = self._screen_fullres_img
        if img is None or img.width() < 1 or img.height() < 1:
            return None

        px = max(0, int(sel.x() * dpr))
        py = max(0, int(sel.y() * dpr))
        pw = max(1, min(int(sel.width() * dpr), img.width() - px))
        ph = max(1, min(int(sel.height() * dpr), img.height() - py))

        result = QPixmap(pw, ph)
        result.setDevicePixelRatio(1.0)
        result.fill(Qt.GlobalColor.transparent)
        painter = QPainter(result)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.drawImage(QPoint(0, 0), img, QRect(px, py, pw, ph))

        painter.scale(dpr, dpr)
        painter.translate(-sel.topLeft())

        for ann in self._annotations:
            self._draw_annotation(painter, ann, hires=True)

        painter.end()
        return result

    def _save_to_clipboard_and_close(self):
        try:
            if self._text_edit:
                self._finalize_text()
            pixmap = self._get_result_pixmap()
            if pixmap:
                QApplication.clipboard().setPixmap(pixmap)
                logger.info("截图已保存到剪贴板")
                if self._callback:
                    self._callback(None)
        except Exception as e:
            logger.error(f"保存到剪贴板失败: {e}")
        self._cleanup()

    def _save_as_file(self):
        try:
            if self._text_edit:
                self._finalize_text()
            pixmap = self._get_result_pixmap()
            if not pixmap:
                return
            name = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            path, _ = QFileDialog.getSaveFileName(
                self, "另存为", name, "PNG (*.png);;JPEG (*.jpg)"
            )
            if path:
                ext = os.path.splitext(path)[1].lower()
                pixmap.save(path, "JPG" if ext in (".jpg", ".jpeg") else "PNG")
                logger.info(f"截图另存为: {path}")
                if self._callback:
                    self._callback(path)
                self._cleanup()
        except Exception as e:
            logger.error(f"另存为失败: {e}")

    def _cleanup(self):
        try:
            if self._text_edit:
                self._text_edit.deleteLater()
                self._text_edit = None
        except Exception:
            pass
        self._remove_toolbar()
        self.close()
        self.deleteLater()


    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self._cleanup()
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self._phase == "selected":
                self._save_to_clipboard_and_close()
        elif key == Qt.Key.Key_Z and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._undo()
        elif key == Qt.Key.Key_S and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if self._phase == "selected":
                self._save_as_file()
        else:
            super().keyPressEvent(event)
