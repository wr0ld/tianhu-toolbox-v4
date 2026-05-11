import os
import sys
import time
import logging
from typing import Optional, List

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QPushButton, QMenu, QMessageBox, QFileDialog,
    QSizePolicy, QLabel,
)

from views.terminal_widget import TerminalWidget
from config import SETTINGS

logger = logging.getLogger(__name__)


class TerminalTabWidget(QWidget):

    terminal_count_changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tab_counter = 0
        self._setup_ui()


    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        tb = QHBoxLayout()
        tb.setContentsMargins(4, 4, 4, 2)
        tb.setSpacing(4)

        self._btn_new = QPushButton("+ 新建终端")
        self._btn_new.setFixedHeight(28)
        self._btn_new.setObjectName("noHoverBtn")
        self._btn_new.setMenu(self._create_new_menu())
        self._btn_new.setStyleSheet(
            "QPushButton { padding: 2px 12px; }"
            "QPushButton::menu-indicator { image: none; }"
        )
        tb.addWidget(self._btn_new)

        self._btn_save_all = QPushButton("保存全部")
        self._btn_save_all.setFixedHeight(28)
        self._btn_save_all.setObjectName("noHoverBtn")
        self._btn_save_all.clicked.connect(self.save_all_tabs)
        tb.addWidget(self._btn_save_all)

        self._btn_close_current = QPushButton("关闭当前")
        self._btn_close_current.setFixedHeight(28)
        self._btn_close_current.setObjectName("noHoverBtn")
        self._btn_close_current.clicked.connect(self._close_current_tab)
        tb.addWidget(self._btn_close_current)

        tb.addStretch()

        self._status_label = QLabel("就绪")
        self._status_label.setStyleSheet("color: #888; font-size: 11px;")
        tb.addWidget(self._status_label)

        layout.addLayout(tb)

        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(False)
        self._tabs.currentChanged.connect(self._on_tab_changed)
        self._tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #333;
                background: #1a1a2e;
            }
            QTabBar::tab {
                background: #2d2d44;
                color: #aaa;
                padding: 6px 16px;
                border: 1px solid #333;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background: #1a1a2e;
                color: #38BDF8;
                border-bottom: 2px solid #38BDF8;
            }
            QTabBar::tab:hover:!selected {
                background: #3a3a55;
                color: #ddd;
            }
        """)
        layout.addWidget(self._tabs)

    def _create_new_menu(self) -> QMenu:
        menu = QMenu(self)
        menu.setObjectName("terminalNewMenu")

        act_cmd = menu.addAction("CMD 命令行")
        act_cmd.triggered.connect(lambda: self.add_terminal("cmd"))

        act_ps = menu.addAction("PowerShell")
        act_ps.triggered.connect(lambda: self.add_terminal("powershell"))

        menu.addSeparator()

        act_admin_cmd = menu.addAction("CMD (管理员)")
        act_admin_cmd.triggered.connect(lambda: self.add_terminal("cmd", admin_mode=True))

        act_admin_ps = menu.addAction("PowerShell (管理员)")
        act_admin_ps.triggered.connect(lambda: self.add_terminal("powershell", admin_mode=True))

        return menu


    def add_terminal(
        self,
        shell_type: str = "cmd",
        admin_mode: bool = False,
        working_dir: str = None,
    ) -> str:
        if working_dir is None:
            working_dir = os.path.dirname(os.path.abspath(sys.argv[0]))

        if admin_mode:
            self._launch_admin_external(shell_type, working_dir)
            return ""

        self._tab_counter += 1
        tab_id = f"term_{self._tab_counter}"

        terminal = TerminalWidget(
            self._tabs,
            shell_type=shell_type,
            working_dir=working_dir,
            admin_mode=False,
            tab_id=tab_id,
        )

        shell_name = "PowerShell" if shell_type == "powershell" else "CMD"
        title = f"{shell_name} #{self._tab_counter}"

        idx = self._tabs.addTab(terminal, title)
        self._tabs.setCurrentIndex(idx)

        terminal._input.setFocus()

        self.terminal_count_changed.emit(self._tabs.count())
        self._update_status()
        return tab_id

    def _launch_admin_external(self, shell_type: str, working_dir: str):
        import ctypes
        from PyQt6.QtWidgets import QMessageBox

        try:
            if shell_type == "powershell":
                ps_path = self._find_powershell()
                exe = ps_path
                params = (
                    f'-NoLogo -NoExit -Command "'
                    f"[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
                    f"[Console]::InputEncoding = [System.Text.Encoding]::UTF8; "
                    f"Set-Location '{working_dir}'\""
                )
            else:
                exe = "cmd.exe"
                params = f'/k "chcp 65001 >nul & cd /d {working_dir}"'

            ret = ctypes.windll.shell32.ShellExecuteW(
                None, "runas", exe, params, working_dir, 1
            )
            if ret <= 32:
                QMessageBox.warning(
                    self, "错误",
                    "管理员权限请求被拒绝或失败。"
                )
            else:
                self._status_label.setText("管理员终端已在外部打开")
        except Exception as e:
            QMessageBox.warning(self, "错误", f"启动管理员终端失败: {e}")

    @staticmethod
    def _find_powershell() -> str:
        for path in [
            r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
            r"C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe",
        ]:
            if os.path.isfile(path):
                return path
        return "powershell.exe"

    def close_terminal(self, index: int) -> bool:
        if index < 0 or index >= self._tabs.count():
            return True

        terminal = self._tabs.widget(index)
        if not isinstance(terminal, TerminalWidget):
            return True

        action = self._get_save_action(terminal)

        if action == "cancel":
            return False
        elif action == "save":
            if not terminal.save_session_to_file():
                return False


        terminal.cleanup()
        self._tabs.removeTab(index)
        terminal.deleteLater()

        self.terminal_count_changed.emit(self._tabs.count())
        self._update_status()
        return True

    def close_all_terminals(self) -> bool:
        if self._tabs.count() == 0:
            return True

        terminals_with_content = []
        for i in range(self._tabs.count()):
            tw = self._tabs.widget(i)
            if isinstance(tw, TerminalWidget) and tw.has_content():
                terminals_with_content.append((i, tw))

        if not terminals_with_content:
            self.cleanup_all()
            return True

        save_prompt = SETTINGS.get("terminal_save_prompt", "prompt_if_content")

        if save_prompt == "always_discard":
            self.cleanup_all()
            return True

        if save_prompt == "always_save":
            return self._auto_save_all()

        return self._prompt_save_on_exit(terminals_with_content)

    def _prompt_save_on_exit(self, terminals: list) -> bool:
        if not terminals:
            return True

        names = []
        for i, tw in terminals:
            title = self._tabs.tabText(i)
            names.append(title)

        msg = QMessageBox(self)
        msg.setWindowTitle("保存终端会话")
        msg.setIcon(QMessageBox.Icon.Question)
        msg.setText(f"有 {len(terminals)} 个终端标签包含内容。")

        btn_save_all = msg.addButton("保存全部", QMessageBox.ButtonRole.AcceptRole)
        btn_select = msg.addButton("选择保存", QMessageBox.ButtonRole.ActionRole)
        btn_discard = msg.addButton("全部丢弃", QMessageBox.ButtonRole.DestructiveRole)
        btn_cancel = msg.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        msg.setDefaultButton(btn_save_all)

        msg.exec()
        clicked = msg.clickedButton()

        if clicked == btn_cancel:
            return False

        if clicked == btn_discard:
            self.cleanup_all()
            return True

        if clicked == btn_save_all:
            return self._auto_save_all()

        if clicked == btn_select:
            return self._select_and_save(terminals)

        return True

    def _select_and_save(self, terminals: list) -> bool:
        from PyQt6.QtWidgets import QInputDialog

        names = [self._tabs.tabText(i) for i, _ in terminals]
        items = names + ["全部"]

        item, ok = QInputDialog.getItem(
            self, "选择要保存的标签",
            "请选择要保存的终端会话：",
            items, 0, False
        )
        if not ok:
            self.cleanup_all()
            return True

        if item == "全部":
            return self._auto_save_all()

        idx = names.index(item) if item in names else -1
        if idx >= 0:
            _, tw = terminals[idx]
            tw.save_session_to_file()

        self.cleanup_all()
        return True

    def _auto_save_all(self) -> bool:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        save_dir = os.path.join("config", "sessions")
        os.makedirs(save_dir, exist_ok=True)

        for i in range(self._tabs.count()):
            tw = self._tabs.widget(i)
            if isinstance(tw, TerminalWidget) and tw.has_content():
                title = self._tabs.tabText(i).replace("/", "_").replace("\\", "_")
                filepath = os.path.join(save_dir, f"{title}_{timestamp}.txt")
                try:
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(tw.get_session_text())
                except Exception as e:
                    logger.warning(f"自动保存终端会话失败: {e}")

        self.cleanup_all()
        return True

    def _get_save_action(self, terminal: TerminalWidget) -> str:
        save_prompt = SETTINGS.get("terminal_save_prompt", "prompt_if_content")

        if save_prompt == "always_discard":
            return "discard"
        if save_prompt == "always_save":
            return "save"

        if save_prompt == "prompt_if_content" and not terminal.has_content():
            return "discard"

        msg = QMessageBox(self)
        msg.setWindowTitle("保存会话")
        msg.setIcon(QMessageBox.Icon.Question)
        msg.setText(f"标签 \"{self._tabs.tabText(self._tabs.indexOf(terminal))}\" 包含会话内容。")

        btn_save = msg.addButton("保存", QMessageBox.ButtonRole.AcceptRole)
        btn_discard = msg.addButton("丢弃", QMessageBox.ButtonRole.DestructiveRole)
        btn_cancel = msg.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        msg.setDefaultButton(btn_save)
        msg.exec()

        clicked = msg.clickedButton()
        if clicked == btn_save:
            return "save"
        elif clicked == btn_discard:
            return "discard"
        return "cancel"


    def save_all_tabs(self):
        dir_path = QFileDialog.getExistingDirectory(self, "选择保存目录")
        if not dir_path:
            return

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        saved = 0
        for i in range(self._tabs.count()):
            tw = self._tabs.widget(i)
            if isinstance(tw, TerminalWidget) and tw.has_content():
                title = self._tabs.tabText(i).replace("/", "_").replace("\\", "_")
                filepath = os.path.join(dir_path, f"{title}_{timestamp}.txt")
                try:
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(tw.get_session_text())
                    saved += 1
                except Exception as e:
                    logger.warning(f"保存会话失败: {e}")

        self._status_label.setText(f"已保存 {saved} 个会话")

    def current_terminal(self) -> Optional[TerminalWidget]:
        tw = self._tabs.currentWidget()
        if isinstance(tw, TerminalWidget):
            return tw
        return None

    def get_terminal(self, tab_id: str) -> Optional[TerminalWidget]:
        for i in range(self._tabs.count()):
            tw = self._tabs.widget(i)
            if isinstance(tw, TerminalWidget) and tw.tab_id == tab_id:
                return tw
        return None

    def run_in_current(self, cmd: str):
        tw = self.current_terminal()
        if tw:
            tw.run_command(cmd)

    def terminal_count(self) -> int:
        return self._tabs.count()

    def cleanup_all(self):
        for i in range(self._tabs.count()):
            tw = self._tabs.widget(i)
            if isinstance(tw, TerminalWidget):
                tw.cleanup()
        self._tabs.clear()
        self.terminal_count_changed.emit(0)
        self._update_status()


    def _handle_tab_close_requested(self, index: int):
        self.close_terminal(index)

    def _close_current_tab(self):
        self.close_terminal(self._tabs.currentIndex())

    def _on_tab_changed(self, index: int):
        if index >= 0:
            tw = self._tabs.widget(index)
            if isinstance(tw, TerminalWidget):
                tw._input.setFocus()
        self._update_status()

    def _update_status(self):
        count = self._tabs.count()
        running = sum(
            1 for i in range(count)
            if isinstance(self._tabs.widget(i), TerminalWidget)
            and self._tabs.widget(i).is_running()
        )
        if count == 0:
            self._status_label.setText("无终端 — 点击「+ 新建终端」开始")
        else:
            self._status_label.setText(f"{count} 个标签 / {running} 个运行中")
