import ctypes
from ctypes import c_int, byref, sizeof
from ctypes.wintypes import HWND, DWORD
import sys

DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_SYSTEMBACKDROP_TYPE = 38

DWMSBT_NONE = 1
DWMSBT_TRANSIENTWINDOW = 3


class WindowEffect:
    def __init__(self):
        self.dwmapi = ctypes.WinDLL("dwmapi")
        self.user32 = ctypes.WinDLL("user32")

    def set_acrylic_effect(self, hwnd: int, is_dark: bool = True):
        if sys.platform != "win32":
            return False
        try:
            dark_mode = c_int(1 if is_dark else 0)
            self.dwmapi.DwmSetWindowAttribute(
                HWND(hwnd),
                DWORD(DWMWA_USE_IMMERSIVE_DARK_MODE),
                byref(dark_mode),
                sizeof(dark_mode),
            )
            backdrop_type = c_int(DWMSBT_TRANSIENTWINDOW)
            self.dwmapi.DwmSetWindowAttribute(
                HWND(hwnd),
                DWORD(DWMWA_SYSTEMBACKDROP_TYPE),
                byref(backdrop_type),
                sizeof(backdrop_type),
            )
            return True
        except Exception as e:
            print(f"Failed to set Acrylic effect: {e}")
            return False

    def remove_background_effect(self, hwnd: int):
        if sys.platform != "win32":
            return
        try:
            backdrop_type = c_int(DWMSBT_NONE)
            self.dwmapi.DwmSetWindowAttribute(
                HWND(hwnd),
                DWORD(DWMWA_SYSTEMBACKDROP_TYPE),
                byref(backdrop_type),
                sizeof(backdrop_type),
            )
        except:
            pass
