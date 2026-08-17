import os
import sys

from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QFrame, QGridLayout, QMenu, QSizePolicy
)

from utils import is_tool_favorited, add_favorite_tool, remove_favorite_tool


class _ToolButton(QPushButton):
    right_clicked = pyqtSignal(dict, QPoint)

    def __init__(self, tool, parent=None):
        super().__init__(parent)
        self.tool = tool
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("classicToolBtn")
        self.setToolTip(str(tool.get("description", "") or tool.get("name", "")))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(32)
        self.refresh_state(False, False)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.right_clicked.emit(self.tool, self.mapToGlobal(event.pos()))
            event.accept()
            return
        super().mousePressEvent(event)

    def refresh_state(self, batch_mode, selected):
        self.setProperty("batchMode", batch_mode)
        self.setProperty("selectedBtn", selected)
        self.setProperty("favoriteBtn", is_tool_favorited(self.tool))
        self.setText(str(self.tool.get("name", "")))
        style = self.style()
        style.unpolish(self)
        style.polish(self)
        self.update()


class ClassicToolBoxView(QScrollArea):
    tool_run = pyqtSignal(dict)
    tool_edit = pyqtSignal(dict)
    tool_delete = pyqtSignal(dict)
    favorite_changed = pyqtSignal(dict, bool)
    batch_run_requested = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("classicToolScroll")
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.Shape.NoFrame)

        self.container = QWidget()
        self.container.setObjectName("classicToolContainer")
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(6, 6, 6, 10)
        self.container_layout.setSpacing(12)
        self.setWidget(self.container)

        self.final_tools = []
        self.show_select_box = False
        self._selected_keys = set()
        self._empty_label = None
        self._last_cols = -1
        self._last_signature = ()
        self._rebuild_timer = QTimer(self)
        self._rebuild_timer.setSingleShot(True)
        self._rebuild_timer.timeout.connect(self._rebuild)

    def set_final_tools(self, tools):
        self.final_tools = list(tools or [])
        self._schedule_rebuild(force=True)

    def enable_batch_mode(self, enable):
        self.show_select_box = bool(enable)
        if not self.show_select_box:
            self._selected_keys.clear()
        self._refresh_buttons_state()

    def get_selected_tools(self):
        out = []
        for tool in self.final_tools:
            if self._tool_key(tool) in self._selected_keys:
                out.append(tool)
        return out

    def adjust_card_size(self):
        self._schedule_rebuild()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._schedule_rebuild()

    def _tool_key(self, tool):
        return (str(tool.get("name", "")), str(tool.get("category", "")))

    def _clear_layout(self):
        while self.container_layout.count():
            item = self.container_layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.deleteLater()
            elif child_layout is not None:
                self._delete_layout(child_layout)

    def _delete_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            sub = item.layout()
            if widget is not None:
                widget.deleteLater()
            elif sub is not None:
                self._delete_layout(sub)

    def _group_tools(self):
        grouped = {}
        order = []
        for tool in self.final_tools:
            cat = str(tool.get("category", "") or "其他工具")
            if cat not in grouped:
                grouped[cat] = []
                order.append(cat)
            grouped[cat].append(tool)
        return order, grouped

    def _calc_columns(self):
        width = max(720, self.viewport().width())
        button_w = 210
        gap = 10
        return max(1, min(8, width // (button_w + gap)))

    def _build_signature(self):
        return tuple(
            (
                str(tool.get("name", "")),
                str(tool.get("category", "")),
                float(tool.get("weight", 0) or 0),
            )
            for tool in self.final_tools
        )

    def _schedule_rebuild(self, force=False):
        cols = self._calc_columns()
        sig = self._build_signature()
        if (not force) and cols == self._last_cols and sig == self._last_signature:
            return
        self._last_cols = cols
        self._last_signature = sig
        self._rebuild_timer.start(30)

    def _rebuild(self):
        self._clear_layout()
        self._empty_label = None

        if not self.final_tools:
            self._empty_label = QLabel("当前没有可显示的工具", self.container)
            self._empty_label.setObjectName("classicEmptyLabel")
            self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.container_layout.addWidget(self._empty_label)
            self.container_layout.addStretch(1)
            return

        cols = self._calc_columns()
        order, grouped = self._group_tools()
        for cat in order:
            section = QFrame(self.container)
            section.setObjectName("classicSection")
            section_lay = QVBoxLayout(section)
            section_lay.setContentsMargins(8, 8, 8, 8)
            section_lay.setSpacing(8)

            title = QLabel(cat, section)
            title.setObjectName("classicSectionTitle")
            section_lay.addWidget(title)

            grid_wrap = QWidget(section)
            grid_wrap.setObjectName("classicSectionBody")
            grid = QGridLayout(grid_wrap)
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setHorizontalSpacing(8)
            grid.setVerticalSpacing(8)

            for i, tool in enumerate(grouped.get(cat, [])):
                btn = _ToolButton(tool, grid_wrap)
                btn.clicked.connect(lambda checked=False, t=tool: self._on_tool_clicked(t))
                btn.right_clicked.connect(self._show_context_menu)
                btn.refresh_state(self.show_select_box, self._tool_key(tool) in self._selected_keys)
                grid.addWidget(btn, i // cols, i % cols)

            section_lay.addWidget(grid_wrap)
            self.container_layout.addWidget(section)

        self.container_layout.addStretch(1)

    def _refresh_buttons_state(self):
        for btn in self.container.findChildren(_ToolButton):
            btn.refresh_state(self.show_select_box, self._tool_key(btn.tool) in self._selected_keys)

    def _on_tool_clicked(self, tool):
        key = self._tool_key(tool)
        if self.show_select_box:
            if key in self._selected_keys:
                self._selected_keys.remove(key)
            else:
                self._selected_keys.add(key)
            self._refresh_buttons_state()
            return
        self.tool_run.emit(tool)

    def _show_context_menu(self, tool, global_pos):
        menu = QMenu(self)
        act_run = menu.addAction("运行")
        menu.addSeparator()
        act_edit = menu.addAction("编辑")
        act_del = menu.addAction("删除")
        menu.addSeparator()
        act_fav = menu.addAction("取消收藏" if is_tool_favorited(tool) else "加入收藏")
        menu.addSeparator()
        act_folder = menu.addAction("打开程序文件夹")
        chosen = menu.exec(global_pos)
        if chosen is None:
            return
        if chosen == act_run:
            self.tool_run.emit(tool)
        elif chosen == act_edit:
            self.tool_edit.emit(tool)
        elif chosen == act_del:
            self.tool_delete.emit(tool)
        elif chosen == act_fav:
            self._toggle_favorite(tool)
        elif chosen == act_folder:
            self._handle_context_action(tool)

    def _toggle_favorite(self, tool):
        is_fav = is_tool_favorited(tool)
        if is_fav:
            remove_favorite_tool(tool)
            self.favorite_changed.emit(tool, False)
        else:
            add_favorite_tool(tool)
            self.favorite_changed.emit(tool, True)
        self._refresh_buttons_state()

    def _handle_context_action(self, tool):
        path = tool.get("path", "")
        base_path = os.path.abspath("tools")
        if not os.path.isabs(path):
            abs_path = os.path.join(base_path, path)
        else:
            abs_path = os.path.abspath(path)

        folder_path = ""
        if os.path.isfile(abs_path):
            folder_path = os.path.dirname(abs_path)
        elif os.path.isdir(abs_path):
            folder_path = abs_path

        if not folder_path or not os.path.exists(folder_path):
            return

        if sys.platform.startswith("win"):
            os.startfile(folder_path)
