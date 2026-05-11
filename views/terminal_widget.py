import os
import re
import sys
import time
import logging
from typing import Optional, List

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QEvent
from PyQt6.QtGui import QFont, QFontMetrics, QPainter, QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QSizePolicy, QFileDialog, QMessageBox,
    QApplication, QMenu, QScrollBar,
)

import pyte
from winpty import PTY
from core.env_manager import EnvManager

logger = logging.getLogger(__name__)

_TERMINAL_FONT = "Consolas"
_DEFAULT_FG = "#cccccc"
_DEFAULT_BG = "#0c0c0c"
_CURSOR_COLOR = "#cccccc"

_RE_ANSI = re.compile(
    r'\x1b\[[^A-Za-z]*[A-Za-z]'
    r'|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)'
    r'|\x1b[^[\]]?'
)

_ANSI_COLORS = {
    "black": "#0c0c0c",
    "red": "#c50f1f",
    "green": "#13a10e",
    "brown": "#c19c00",
    "blue": "#0037da",
    "magenta": "#881798",
    "cyan": "#3a96dd",
    "white": "#cccccc",
    "brightblack": "#767676",
    "brightred": "#e74856",
    "brightgreen": "#16c60c",
    "brightyellow": "#f9f1a5",
    "brightblue": "#3b78ff",
    "brightmagenta": "#b4009e",
    "brightcyan": "#61d6d6",
    "brightwhite": "#f2f2f2",
    "default": _DEFAULT_FG,
}

_QCOLOR_CACHE: dict = {}
_QCOLOR_BG_CACHE: dict = {}


def _get_fg_qcolor(color) -> QColor:
    key = (color, False) if isinstance(color, str) else ("rgb", color.rgb) if hasattr(color, "rgb") and color.rgb else ("default", None)
    qc = _QCOLOR_CACHE.get(key)
    if qc is not None:
        return qc
    if color is None or color == "default":
        qc = QColor(_DEFAULT_FG)
    elif isinstance(color, str):
        qc = QColor(_ANSI_COLORS.get(color, _DEFAULT_FG))
    elif hasattr(color, "rgb") and color.rgb:
        r, g, b = color.rgb
        qc = QColor(r, g, b)
    else:
        qc = QColor(_DEFAULT_FG)
    _QCOLOR_CACHE[key] = qc
    return qc


def _get_bg_qcolor(color) -> QColor:
    key = (color, True) if isinstance(color, str) else ("rgb", color.rgb) if hasattr(color, "rgb") and color.rgb else ("default", None)
    qc = _QCOLOR_BG_CACHE.get(key)
    if qc is not None:
        return qc
    if color is None or color == "default":
        qc = QColor(_DEFAULT_BG)
    elif isinstance(color, str):
        qc = QColor(_ANSI_COLORS.get(color, _DEFAULT_BG))
    elif hasattr(color, "rgb") and color.rgb:
        r, g, b = color.rgb
        qc = QColor(r, g, b)
    else:
        qc = QColor(_DEFAULT_BG)
    _QCOLOR_BG_CACHE[key] = qc
    return qc


_QC_DEFAULT_FG = QColor(_DEFAULT_FG)
_QC_DEFAULT_BG = QColor(_DEFAULT_BG)
_QC_CURSOR = QColor(_CURSOR_COLOR)


def _build_env_str(env_dict: dict) -> str:
    return '\0'.join(f'{k}={v}' for k, v in env_dict.items()) + '\0'


_SCROLLBAR_STYLE = """
    QScrollBar:vertical {
        background: #1a1a2e;
        width: 10px;
        margin: 0;
        border: none;
    }
    QScrollBar::handle:vertical {
        background: #444;
        min-height: 30px;
        border-radius: 5px;
    }
    QScrollBar::handle:vertical:hover {
        background: #666;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0;
    }
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
        background: none;
    }
"""


class _TermDisplay(QWidget):

    _SEL_BG = QColor(38, 79, 120, 180)
    _MAX_SCROLLBACK = 9999

    def __init__(self, parent=None):
        super().__init__(parent)
        self._screen = None

        self._font = QFont(_TERMINAL_FONT, 11)
        self._fm = QFontMetrics(self._font)
        self._cell_w = self._fm.horizontalAdvance("M") or 8
        self._cell_h = self._fm.height() or 16
        self._cols = 80
        self._rows = 24
        self._scroll_offset = 0

        self._scrollbar: Optional[QScrollBar] = None
        self._sel_start = None
        self._sel_end = None
        self._selecting = False
        self.setMinimumSize(self._cell_w * 20, self._cell_h * 8)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)

    def set_scrollbar(self, sb: QScrollBar):
        self._scrollbar = sb
        sb.valueChanged.connect(self._on_scrollbar_changed)

    def set_screen(self, screen):
        self._screen = screen
        self._cols = screen.columns
        self._rows = screen.lines
        self._scroll_offset = 0
        self._update_scrollbar()
        self.update()

    def mark_dirty(self):
        self.update()

    def get_cell_size(self):
        return self._cell_w, self._cell_h

    def get_size_in_cells(self):
        w = max(self.width(), 100)
        h = max(self.height(), 100)
        cols = max(20, w // self._cell_w)
        rows = max(8, h // self._cell_h)
        return cols, rows


    def _history_count(self) -> int:
        if self._screen is None:
            return 0
        return len(self._screen.history.top)

    def _update_scrollbar(self):
        if self._scrollbar is None:
            return
        hist = self._history_count()
        sb = self._scrollbar
        sb.blockSignals(True)
        sb.setRange(0, hist)
        sb.setPageStep(self._rows)
        sb.setSingleStep(1)
        sb.setValue(hist - self._scroll_offset)
        sb.blockSignals(False)

    def _on_scrollbar_changed(self, value):
        hist = self._history_count()
        self._scroll_offset = max(0, hist - value)
        self._scroll_offset = min(self._scroll_offset, hist)
        self.update()

    def scroll_to_bottom(self):
        self._scroll_offset = 0
        self._update_scrollbar()
        self.update()

    def is_at_bottom(self) -> bool:
        return self._scroll_offset == 0

    def _scroll_up(self, lines=3):
        max_off = self._history_count()
        self._scroll_offset = min(self._scroll_offset + lines, max_off)
        self._update_scrollbar()
        self.update()

    def _scroll_down(self, lines=3):
        self._scroll_offset = max(self._scroll_offset - lines, 0)
        self._update_scrollbar()
        self.update()


    def _pos_to_cell(self, pos) -> tuple:
        col = max(0, min(int(pos.x() // self._cell_w), self._cols - 1))
        row = max(0, min(int(pos.y() // self._cell_h), self._rows - 1))
        return row, col

    def _normalized_selection(self):
        if self._sel_start is None or self._sel_end is None:
            return None
        s, e = self._sel_start, self._sel_end
        if s > e:
            s, e = e, s
        return s, e

    def _is_cell_selected(self, row: int, col: int) -> bool:
        sel = self._normalized_selection()
        if sel is None:
            return False
        s, e = sel
        if row < s[0] or row > e[0]:
            return False
        if row == s[0] and col < s[1]:
            return False
        if row == e[0] and col > e[1]:
            return False
        return True

    def _get_selected_text(self) -> str:
        sel = self._normalized_selection()
        if sel is None or self._screen is None:
            return ""
        s, e = sel
        render_lines = self._get_render_lines()
        rows = len(render_lines)
        if s[0] >= rows:
            return ""
        lines = []
        for row in range(s[0], min(e[0] + 1, rows)):
            line_dict = render_lines[row]
            text = ""
            for c in range(self._cols):
                cell = line_dict[c]
                text += cell.data if cell.data else " "
            if s[0] == e[0]:
                lines.append(text[s[1]:e[1] + 1].rstrip())
            elif row == s[0]:
                lines.append(text[s[1]:].rstrip())
            elif row == e[0]:
                lines.append(text[:e[1] + 1].rstrip())
            else:
                lines.append(text.rstrip())
        return "\n".join(lines)

    def _clear_selection(self):
        self._sel_start = None
        self._sel_end = None
        self._selecting = False


    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            self._sel_start = self._pos_to_cell(pos)
            self._sel_end = self._sel_start
            self._selecting = True
            self.update()
        elif event.button() == Qt.MouseButton.RightButton:
            text = self._get_selected_text()
            menu = QMenu(self)
            if text:
                copy_action = menu.addAction("复制 (Copy)")
                copy_action.triggered.connect(
                    lambda: QApplication.clipboard().setText(text)
                )
            else:
                self._clear_selection()
            if menu.actions():
                menu.exec(event.globalPosition().toPoint())
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._selecting and event.buttons() & Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            self._sel_end = self._pos_to_cell(pos)
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._selecting = False
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta > 0:
            self._scroll_up(max(1, abs(delta) // 40))
        elif delta < 0:
            self._scroll_down(max(1, abs(delta) // 40))
        event.accept()


    def _get_render_lines(self) -> list:
        if self._screen is None:
            return []
        hist = list(self._screen.history.top)
        n_hist = len(hist)
        offset = min(self._scroll_offset, n_hist)
        screen_lines = self._screen.lines
        cols = self._cols

        lines = []
        hist_show = offset
        for i in range(n_hist - hist_show, n_hist):
            lines.append(hist[i])
        screen_show = self._rows - hist_show
        for i in range(min(screen_show, screen_lines)):
            lines.append(self._screen.buffer[i])
        while len(lines) < self._rows:
            lines.append({})

        return lines[:self._rows]


    def paintEvent(self, event):
        if self._screen is None:
            return
        p = QPainter(self)
        p.setFont(self._font)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, False)

        cw, ch = self._cell_w, self._cell_h
        ascent = self._fm.ascent()
        cols = min(self._cols, self._screen.columns)

        p.fillRect(self.rect(), _QC_DEFAULT_BG)

        render_lines = self._get_render_lines()
        rows = len(render_lines)

        sel = self._normalized_selection()
        if sel is not None:
            s, e = sel
            for row in range(s[0], min(e[0] + 1, rows)):
                col_start = s[1] if row == s[0] else 0
                col_end = e[1] if row == e[0] else cols - 1
                if col_start <= col_end:
                    p.fillRect(col_start * cw, row * ch,
                               (col_end - col_start + 1) * cw, ch, self._SEL_BG)

        for row_idx in range(rows):
            line = render_lines[row_idx]
            y = row_idx * ch
            row_y_ascent = y + ascent

            run_text = []
            run_start_col = 0
            run_color = None
            run_bold = False

            for col_idx in range(cols):
                cell = line[col_idx] if col_idx in line else None
                if cell is None:
                    if run_text and run_color is not None:
                        qc = _get_fg_qcolor(run_color)
                        if run_bold:
                            qc = qc.lighter(130)
                        p.setPen(qc)
                        p.drawText(run_start_col * cw, row_y_ascent, "".join(run_text))
                    run_text = []
                    run_color = None
                    run_bold = False
                    continue

                if cell.bg is not None and cell.bg != "default":
                    if not self._is_cell_selected(row_idx, col_idx):
                        p.fillRect(col_idx * cw, y, cw, ch, _get_bg_qcolor(cell.bg))

                fg = cell.fg
                bold = cell.bold
                if fg != run_color or bold != run_bold or not cell.data or cell.data == " ":
                    if run_text and run_color is not None:
                        qc = _get_fg_qcolor(run_color)
                        if run_bold:
                            qc = qc.lighter(130)
                        p.setPen(qc)
                        p.drawText(run_start_col * cw, row_y_ascent, "".join(run_text))
                    if cell.data and cell.data != " ":
                        run_text = [cell.data]
                        run_start_col = col_idx
                        run_color = fg
                        run_bold = bold
                    else:
                        run_text = []
                        run_color = None
                        run_bold = False
                else:
                    run_text.append(cell.data)

            if run_text and run_color is not None:
                qc = _get_fg_qcolor(run_color)
                if run_bold:
                    qc = qc.lighter(130)
                p.setPen(qc)
                p.drawText(run_start_col * cw, row_y_ascent, "".join(run_text))

        if self._scroll_offset == 0:
            cursor = self._screen.cursor
            if not cursor.hidden and cursor.y < rows and cursor.x < cols:
                cx = cursor.x * cw
                cy = cursor.y * ch
                p.fillRect(cx, cy, cw, ch, _QC_CURSOR)
                buf = self._screen.buffer
                if cursor.y < len(buf) and cursor.x < len(buf[cursor.y]):
                    cell = buf[cursor.y][cursor.x]
                    if cell.data and cell.data != " ":
                        p.setPen(_QC_DEFAULT_BG)
                        p.drawText(cx, cy + ascent, cell.data)

        p.end()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update()


class TerminalWidget(QWidget):

    title_changed = pyqtSignal(str)

    SHELL_CMD = "cmd"
    SHELL_POWERSHELL = "powershell"

    def __init__(
        self,
        parent=None,
        *,
        shell_type: str = "cmd",
        working_dir: str = None,
        admin_mode: bool = False,
        tab_id: str = "",
    ):
        super().__init__(parent)
        self._tab_id = tab_id or f"term_{id(self)}"
        self._shell_type = shell_type
        self._working_dir = working_dir or os.path.dirname(os.path.abspath(sys.argv[0]))
        self._pty: Optional[PTY] = None
        self._pyte_screen = None
        self._pyte_stream: Optional[pyte.Stream] = None
        self._session_log: List[str] = []
        self._command_history: List[str] = []
        self._history_index: int = -1
        self._cols = 80
        self._rows = 24

        self._setup_ui()
        self._start_shell()


    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        tb = QHBoxLayout()
        tb.setContentsMargins(6, 3, 6, 3)
        tb.setSpacing(6)

        self._btn_restart = QPushButton("重启")
        self._btn_restart.setFixedHeight(30)
        self._btn_restart.setMinimumWidth(56)
        self._btn_restart.setObjectName("noHoverBtn")
        self._btn_restart.clicked.connect(self.restart)
        tb.addWidget(self._btn_restart)

        self._btn_clear = QPushButton("清屏")
        self._btn_clear.setFixedHeight(30)
        self._btn_clear.setMinimumWidth(56)
        self._btn_clear.setObjectName("noHoverBtn")
        self._btn_clear.clicked.connect(self.clear_output)
        tb.addWidget(self._btn_clear)

        self._btn_save = QPushButton("保存会话")
        self._btn_save.setFixedHeight(30)
        self._btn_save.setMinimumWidth(80)
        self._btn_save.setObjectName("noHoverBtn")
        self._btn_save.clicked.connect(lambda: self.save_session_to_file())
        tb.addWidget(self._btn_save)

        tb.addStretch()

        shell_label = "PowerShell" if self._shell_type == self.SHELL_POWERSHELL else "CMD"
        self._shell_label = QPushButton(shell_label)
        self._shell_label.setFixedHeight(30)
        self._shell_label.setMinimumWidth(70)
        self._shell_label.setEnabled(False)
        self._shell_label.setStyleSheet(
            "QPushButton { color: #38BDF8; background: transparent; "
            "border: 1px solid #38BDF8; border-radius: 4px; padding: 4px 10px; "
            "font-size: 12px; font-weight: bold; }"
        )
        tb.addWidget(self._shell_label)

        layout.addLayout(tb)

        display_row = QHBoxLayout()
        display_row.setContentsMargins(0, 0, 0, 0)
        display_row.setSpacing(0)

        self._display = _TermDisplay(self)
        display_row.addWidget(self._display, stretch=1)

        self._scrollbar = QScrollBar(Qt.Orientation.Vertical)
        self._scrollbar.setFixedWidth(10)
        self._scrollbar.setStyleSheet(_SCROLLBAR_STYLE)
        self._scrollbar.setRange(0, 0)
        display_row.addWidget(self._scrollbar)

        self._display.set_scrollbar(self._scrollbar)
        layout.addLayout(display_row, stretch=1)

        input_row = QHBoxLayout()
        input_row.setContentsMargins(6, 2, 6, 4)
        input_row.setSpacing(4)

        self._prompt_label = QPushButton(">")
        self._prompt_label.setFixedWidth(20)
        self._prompt_label.setFlat(True)
        self._prompt_label.setStyleSheet(
            "color: #38BDF8; border: none; font-weight: bold; font-size: 13px;"
        )
        input_row.addWidget(self._prompt_label)

        self._input = QLineEdit()
        self._input.setPlaceholderText("输入命令 (Enter 发送, 支持方向键历史)...")
        self._input.setFont(QFont(_TERMINAL_FONT, 11))
        self._input.setStyleSheet("""
            QLineEdit {
                background-color: #1e1e2e;
                color: #cccccc;
                border: 1px solid #444;
                padding: 4px 8px;
                border-radius: 3px;
                font-family: 'Consolas', monospace;
            }
            QLineEdit:focus {
                border: 1px solid #38BDF8;
            }
        """)
        self._input.returnPressed.connect(self._send_input)
        self._input.installEventFilter(self)
        input_row.addWidget(self._input, stretch=1)

        layout.addLayout(input_row)

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(16)
        self._poll_timer.timeout.connect(self._poll_output)

        self._resize_timer = QTimer(self)
        self._resize_timer.setInterval(200)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._do_resize)


    def _start_shell(self):
        self._kill_pty()

        cw, ch = self._display.get_cell_size()
        w = max(self._display.width(), cw * 20)
        h = max(self._display.height(), ch * 8)
        self._cols = max(20, w // cw)
        self._rows = max(8, h // ch)

        try:
            env_dict = EnvManager().get_injected_env("cli_default")
            env_str = _build_env_str(env_dict)
        except Exception:
            env_str = None

        try:
            self._pty = PTY(self._cols, self._rows)
        except Exception as e:
            self._append_text(f"创建伪终端失败: {e}\n", QColor("#ff4444"))
            return

        self._pyte_screen = pyte.HistoryScreen(
            self._cols, self._rows, history=_TermDisplay._MAX_SCROLLBACK
        )
        self._pyte_stream = pyte.Stream(self._pyte_screen)
        self._display.set_screen(self._pyte_screen)

        try:
            if self._shell_type == self.SHELL_POWERSHELL:
                exe = self._find_powershell()
                self._pty.spawn(exe, cwd=self._working_dir, env=env_str)
            else:
                self._pty.spawn(
                    r"C:\Windows\System32\cmd.exe",
                    cmdline="/k chcp 65001 >nul",
                    cwd=self._working_dir,
                    env=env_str,
                )
        except Exception as e:
            self._append_text(f"启动 Shell 失败: {e}\n", QColor("#ff4444"))
            return

        if self._shell_type == self.SHELL_POWERSHELL:
            QTimer.singleShot(500, self._setup_powershell_encoding)

        self._poll_timer.start()
        self._input.setFocus()

    def _setup_powershell_encoding(self):
        if self._pty and self._pty.isalive():
            ps_cmd = (
                "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
                "[Console]::InputEncoding = [System.Text.Encoding]::UTF8; "
                "$OutputEncoding = [System.Text.Encoding]::UTF8\r"
            )
            self._pty.write(ps_cmd)

    @staticmethod
    def _find_powershell() -> str:
        for path in [
            r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
            r"C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe",
        ]:
            if os.path.isfile(path):
                return path
        return "powershell.exe"


    def _poll_output(self):
        if self._pty is None or not self._pty.isalive():
            return
        try:
            data = self._pty.read()
            if data:
                was_at_bottom = self._display.is_at_bottom()
                self._pyte_stream.feed(data)
                plain = _RE_ANSI.sub('', data)
                if plain:
                    self._session_log.append(plain)
                if was_at_bottom:
                    self._display.scroll_to_bottom()
                else:
                    self._display._update_scrollbar()
                    self._display.update()
        except Exception:
            pass

    def _send_input(self):
        if self._pty is None:
            return
        if not self._pty.isalive():
            self._append_text("终端未运行，请点击重启\n", QColor("#ff4444"))
            return
        cmd = self._input.text()
        self._input.clear()
        if cmd:
            self._command_history.append(cmd)
            self._history_index = -1
            self._session_log.append(cmd + "\n")
        self._pty.write(cmd + "\r")
        self._display.scroll_to_bottom()

    def eventFilter(self, obj, event):
        if obj is self._input:
            if event.type() == QEvent.Type.KeyPress:
                key = event.key()
                mods = event.modifiers()
                if key == Qt.Key.Key_Up and mods == Qt.KeyboardModifier.NoModifier:
                    self._history_up()
                    return True
                elif key == Qt.Key.Key_Down and mods == Qt.KeyboardModifier.NoModifier:
                    self._history_down()
                    return True
                elif key == Qt.Key.Key_C and mods & Qt.KeyboardModifier.ControlModifier:
                    if self._pty and self._pty.isalive():
                        self._pty.write("\x03")
                    return True
                elif key == Qt.Key.Key_L and mods & Qt.KeyboardModifier.ControlModifier:
                    self.clear_output()
                    return True
                elif key == Qt.Key.Key_Tab:
                    if self._pty and self._pty.isalive():
                        self._pty.write("\t")
                    return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        if self._input.hasFocus():
            super().keyPressEvent(event)
            return
        if self._pty and self._pty.isalive():
            key = event.key()
            mods = event.modifiers()
            text = event.text()
            if key in (Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Shift,
                       Qt.Key.Key_Meta, Qt.Key.Key_CapsLock, Qt.Key.Key_NumLock,
                       Qt.Key.Key_ScrollLock):
                return
            self._display.scroll_to_bottom()
            if key == Qt.Key.Key_Return or key == Qt.Key.Key_Enter:
                self._pty.write("\r")
            elif key == Qt.Key.Key_Backspace:
                self._pty.write("\x08")
            elif key == Qt.Key.Key_Delete:
                self._pty.write("\x1b[3~")
            elif key == Qt.Key.Key_Up:
                self._pty.write("\x1b[A")
            elif key == Qt.Key.Key_Down:
                self._pty.write("\x1b[B")
            elif key == Qt.Key.Key_Right:
                self._pty.write("\x1b[C")
            elif key == Qt.Key.Key_Left:
                self._pty.write("\x1b[D")
            elif key == Qt.Key.Key_Home:
                self._pty.write("\x1b[H")
            elif key == Qt.Key.Key_End:
                self._pty.write("\x1b[F")
            elif key == Qt.Key.Key_PageUp:
                self._pty.write("\x1b[5~")
            elif key == Qt.Key.Key_PageDown:
                self._pty.write("\x1b[6~")
            elif key == Qt.Key.Key_Tab:
                self._pty.write("\t")
            elif key == Qt.Key.Key_C and mods & Qt.KeyboardModifier.ControlModifier:
                self._pty.write("\x03")
            elif key == Qt.Key.Key_D and mods & Qt.KeyboardModifier.ControlModifier:
                self._pty.write("\x04")
            elif key == Qt.Key.Key_Z and mods & Qt.KeyboardModifier.ControlModifier:
                self._pty.write("\x1a")
            elif text:
                self._pty.write(text)
        else:
            super().keyPressEvent(event)

    def _history_up(self):
        if not self._command_history:
            return
        if self._history_index == -1:
            self._history_index = len(self._command_history)
        self._history_index = max(0, self._history_index - 1)
        self._input.setText(self._command_history[self._history_index])

    def _history_down(self):
        if self._history_index == -1:
            return
        self._history_index += 1
        if self._history_index >= len(self._command_history):
            self._history_index = -1
            self._input.clear()
        else:
            self._input.setText(self._command_history[self._history_index])

    def _append_text(self, text: str, color: QColor = None):
        self._session_log.append(text)
        self.update()


    def showEvent(self, event):
        super().showEvent(event)
        if self._pty and self._pty.isalive():
            self._poll_timer.start()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._poll_timer.stop()


    def _kill_pty(self):
        self._poll_timer.stop()
        if self._pty is not None:
            try:
                pid = self._pty.pid
                if pid:
                    os.kill(pid, 9)
            except Exception:
                pass
            self._pty = None

    def restart(self):
        self.clear_output()
        self._start_shell()

    def clear_output(self):
        if self._pty and self._pty.isalive():
            if self._shell_type == self.SHELL_POWERSHELL:
                self._pty.write("Clear-Host\r")
            else:
                self._pty.write("cls\r")
        elif self._pyte_screen:
            self._pyte_screen.reset()
            self._display.scroll_to_bottom()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._resize_timer.start()

    def _do_resize(self):
        if self._pty is None or self._pyte_screen is None:
            return
        cw, ch = self._display.get_cell_size()
        w = max(self._display.width(), cw * 20)
        h = max(self._display.height(), ch * 8)
        new_cols = max(20, w // cw)
        new_rows = max(8, h // ch)
        if new_cols == self._cols and new_rows == self._rows:
            return
        self._cols = new_cols
        self._rows = new_rows
        try:
            self._pty.set_size(new_cols, new_rows)
        except Exception:
            pass
        try:
            self._pyte_screen.resize(new_rows, new_cols)
        except Exception:
            pass
        self._display._cols = new_cols
        self._display._rows = new_rows
        self._display._update_scrollbar()
        self._display.update()


    def get_session_text(self) -> str:
        if self._pyte_screen:
            lines = []
            for line_dict in self._pyte_screen.history.top:
                text = ""
                for c in range(self._pyte_screen.columns):
                    cell = line_dict[c]
                    text += cell.data if cell.data else " "
                lines.append(text.rstrip())
            for line in self._pyte_screen.display:
                lines.append(line.rstrip())
            return "\n".join(lines)
        return "".join(self._session_log)

    @property
    def session_length(self) -> int:
        if self._pyte_screen:
            total = sum(
                len("".join(cell.data for cell in line_dict.values()).rstrip())
                for line_dict in self._pyte_screen.history.top
            )
            total += sum(len(line.rstrip()) for line in self._pyte_screen.display)
            return total
        return sum(len(s) for s in self._session_log)

    def has_content(self) -> bool:
        return self.session_length > 0

    def save_session_to_file(self, filepath: str = None) -> bool:
        text = self.get_session_text()
        if not filepath:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            default_name = f"terminal_session_{timestamp}.txt"
            filepath, _ = QFileDialog.getSaveFileName(
                self, "保存会话", default_name, "文本文件 (*.txt);;所有文件 (*)"
            )
            if not filepath:
                return False
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(text)
            self._session_log.append(f"\n[会话已保存到: {filepath}]\n")
            return True
        except Exception as e:
            QMessageBox.warning(self, "保存失败", str(e))
            return False


    def run_command(self, cmd: str):
        if self._pty is None:
            return
        if self._pty.isalive():
            self._command_history.append(cmd)
            self._history_index = -1
            self._session_log.append(cmd + "\n")
            self._pty.write(cmd + "\r")
            self._display.scroll_to_bottom()
        else:
            self._append_text("终端未运行，请先重启\n", QColor("#ff4444"))

    def set_working_directory(self, path: str):
        if self._pty is None:
            return
        if self._pty.isalive():
            if self._shell_type == self.SHELL_POWERSHELL:
                self._pty.write(f"Set-Location '{path}'\r")
            else:
                self._pty.write(f'cd /d "{path}"\r')

    def switch_shell(self, shell_type: str):
        self._shell_type = shell_type
        shell_label = "PowerShell" if shell_type == self.SHELL_POWERSHELL else "CMD"
        self._shell_label.setText(shell_label)
        self.clear_output()
        self._start_shell()

    def is_running(self) -> bool:
        if self._pty is None:
            return False
        return self._pty.isalive()

    @property
    def tab_id(self) -> str:
        return self._tab_id

    @property
    def shell_type(self) -> str:
        return self._shell_type

    def cleanup(self):
        self._kill_pty()
