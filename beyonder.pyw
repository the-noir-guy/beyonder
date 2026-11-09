# -*- coding: utf-8 -*-
"""Beyonder - Windows browser/profile launcher.

Native pywebview window (WebView2) with an HTML/CSS/JS interface and all logic in Python.
Double-click this file to run it (no console window).
"""
import os
import sys
import io
import re
import json
import time
import shutil
import base64
import hashlib
import struct
import configparser
import ctypes
import logging
import functools
import queue
import zipfile
import threading
import subprocess
from ctypes import wintypes
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))
APP_DIR = os.path.dirname(sys.executable) if FROZEN else os.path.dirname(os.path.abspath(__file__))
RES_DIR = getattr(sys, "_MEIPASS", APP_DIR)

UI_INDEX = os.path.join(RES_DIR, "ui", "index.html")
ICON_PATH = os.path.join(RES_DIR, "assets", "favicon.ico")
DATA_DIR = os.path.join(APP_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "launcher.json")
STATS_PATH = os.path.join(DATA_DIR, "stats.json")
LOG_PATH = os.path.join(DATA_DIR, "error.log")
SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")

APP_TITLE = "Beyonder"
APP_ID = "Beyonder.Launcher"
TITLE_H = 38                    # height of the HTML title bar in CSS px (must match --title-h in style.css)
ASPECT = 1280.0 / 800.0         # the design canvas proportions
MIN_STAGE_W = 640               # smallest window width
WEBVIEW2_URL = "https://developer.microsoft.com/microsoft-edge/webview2/"
BACKGROUND = "--background" in sys.argv     # started by Windows at sign-in: stay in the tray until asked
MUTEX_NAME = "Local\\Beyonder.Launcher.Instance"
EVENT_NAME = "Local\\Beyonder.Launcher.Show"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "Beyonder"
THEME_BG = {"dark": "#000000", "light": "#f4f4f4"}     # window background before the page paints (match --bg in style.css)
SETTING_CHOICES = {                                         # settings the page may change through set_setting
    "autostart": (True, False),
    "hotkey_enabled": (True, False),
    "minimize_after_launch": (True, False),
    "close_action": ("tray", "quit"),
    "sort": ("manual", "most_used", "recent"),
}

Image = None                    # Pillow, imported in main() once it is installed

log = logging.getLogger("beyonder")


# ───────────────────────────── logging, message boxes, dependencies ─────────────────────────────
def setup_logging():
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        if os.path.isfile(LOG_PATH) and os.path.getsize(LOG_PATH) > 1000000:
            os.replace(LOG_PATH, LOG_PATH + ".1")
    except OSError:
        pass
    try:
        logging.basicConfig(filename=LOG_PATH, level=logging.INFO, encoding="utf-8",
                            format="%(asctime)s [%(levelname)s] %(message)s")
    except Exception:
        logging.basicConfig(level=logging.INFO)
    log.info("---- Beyonder starting (Python %s, frozen=%s) ----", sys.version.split()[0], FROZEN)


def message_box(title, text, flags=0x10):
    try:
        return ctypes.windll.user32.MessageBoxW(0, text, title, flags)
    except Exception:
        return 0


def have_module(name):
    try:
        __import__(name)
        return True
    except Exception:
        return False


def ensure_dependencies():
    """Installs pywebview, Pillow and pystray on first run, like the old app did."""
    needed = [(m, p) for m, p in (("webview", "pywebview"), ("PIL", "Pillow"), ("pystray", "pystray")) if not have_module(m)]
    if not needed:
        return True
    packages = [p for _, p in needed]
    if not FROZEN:
        py = sys.executable
        if os.path.basename(py).lower() == "pythonw.exe":
            py = os.path.join(os.path.dirname(py), "python.exe")
        log.info("Installing missing packages: %s", packages)
        try:
            result = subprocess.run([py, "-m", "pip", "install", *packages], creationflags=0x08000000,
                                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, errors="replace")
            log.info("pip output (tail):\n%s", (result.stdout or "")[-3000:])
        except Exception:
            log.exception("pip install failed to start")
        try:
            import importlib
            importlib.invalidate_caches()
        except Exception:
            pass
    missing = [p for m, p in needed if not have_module(m)]
    if missing:
        log.error("Still missing after install: %s", missing)
        message_box("Beyonder", "Beyonder could not install: %s\n\nRun this in a command prompt, then start Beyonder "
                                "again:\n\npip install %s\n\nDetails: %s" % (", ".join(missing), " ".join(missing), LOG_PATH))
        return False
    return True


def setup_windows_identity():
    """Own process identity: sharp rendering on scaled displays and the Beyonder name/icon in the taskbar."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:
        log.exception("SetCurrentProcessExplicitAppUserModelID failed")


def webview2_installed():
    try:
        import winreg
    except Exception:
        return True
    guid = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
    spots = [
        (winreg.HKEY_LOCAL_MACHINE, "SOFTWARE\\WOW6432Node\\Microsoft\\EdgeUpdate\\Clients\\" + guid),
        (winreg.HKEY_LOCAL_MACHINE, "SOFTWARE\\Microsoft\\EdgeUpdate\\Clients\\" + guid),
        (winreg.HKEY_CURRENT_USER, "Software\\Microsoft\\EdgeUpdate\\Clients\\" + guid),
    ]
    for root, key in spots:
        try:
            with winreg.OpenKey(root, key) as k:
                version, _ = winreg.QueryValueEx(k, "pv")
                if version and version != "0.0.0.0":
                    return True
        except OSError:
            continue
    return False


# ───────────────────────────── Win32 window helpers ─────────────────────────────
user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
try:
    dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
    dwmapi.DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
    dwmapi.DwmSetWindowAttribute.restype = ctypes.c_long
except Exception:
    dwmapi = None
_instance_handles = []


def claim_instance():
    """Returns None when Beyonder is already running (that copy is asked to show its window),
    otherwise the handle of the event a second launch will signal (0 if it could not be created)."""
    try:
        mutex = kernel32.CreateMutexW(None, False, MUTEX_NAME)
        if ctypes.get_last_error() == 183:          # ERROR_ALREADY_EXISTS
            ev = kernel32.OpenEventW(0x0002, False, EVENT_NAME)     # EVENT_MODIFY_STATE
            if ev:
                kernel32.SetEvent(ev)
                kernel32.CloseHandle(ev)
            return None
        event = kernel32.CreateEventW(None, False, False, EVENT_NAME)
        _instance_handles.extend([mutex, event])
        return event or 0
    except Exception:
        log.exception("Single-instance check failed")
        return 0


def listen_for_second_launch(event, show):
    """A second launch signals the event; this brings the running window back."""
    if not event:
        return

    def work():
        while True:
            try:
                if kernel32.WaitForSingleObject(event, 0xFFFFFFFF) == 0:
                    show()
                else:
                    time.sleep(1)
            except Exception:
                time.sleep(1)
    threading.Thread(target=work, daemon=True).start()


HOTKEY_MODS = {"Ctrl": 0x0002, "Alt": 0x0001, "Shift": 0x0004, "Win": 0x0008}
HOTKEY_ORDER = ("Ctrl", "Alt", "Shift", "Win")


def parse_hotkey(text):
    """'Ctrl+Alt+B' -> (canonical text, modifier flags, virtual key code), or None when it can't be used."""
    parts = [p.strip() for p in str(text or "").split("+") if p.strip()]
    if len(parts) < 2:
        return None
    aliases = {"ctrl": "Ctrl", "control": "Ctrl", "alt": "Alt", "shift": "Shift", "win": "Win", "windows": "Win"}
    names = []
    for part in parts[:-1]:
        name = aliases.get(part.lower())
        if not name or name in names:
            return None
        names.append(name)
    if not any(n in names for n in ("Ctrl", "Alt", "Win")):
        return None                                     # Shift alone would take over normal typing
    key = parts[-1].upper()
    if len(key) == 1 and ("A" <= key <= "Z" or "0" <= key <= "9"):
        vk, shown = ord(key), key
    elif key.startswith("F") and key[1:].isdigit() and 1 <= int(key[1:]) <= 12:
        vk, shown = 0x70 + int(key[1:]) - 1, key
    elif key == "SPACE":
        vk, shown = 0x20, "Space"
    else:
        return None
    mods = 0
    for n in names:
        mods |= HOTKEY_MODS[n]
    return "+".join([n for n in HOTKEY_ORDER if n in names] + [shown]), mods, vk


class Hotkey:
    """One global shortcut. RegisterHotKey belongs to the thread that called it, so it gets a thread of its own
    with a message loop; changes are handed over through a queue and a wake-up message."""
    WM_HOTKEY = 0x0312
    WM_WAKE = 0x8001                    # WM_APP + 1
    HOTKEY_ID = 0x0B1D

    def __init__(self, on_press):
        self.on_press = on_press
        self._cmds = queue.Queue()
        self._ready = threading.Event()
        self._tid = 0
        self._thread = None

    def _ensure_thread(self):
        if self._thread is not None and self._thread.is_alive():
            return True
        self._ready.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self._ready.wait(3)

    def _loop(self):
        try:
            msg = wintypes.MSG()
            user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)         # creates this thread's message queue
            self._tid = kernel32.GetCurrentThreadId()
            self._ready.set()
            while True:
                got = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if got <= 0:
                    break
                if msg.message == self.WM_HOTKEY and msg.wParam == self.HOTKEY_ID:
                    try:
                        self.on_press()
                    except Exception:
                        log.exception("Hotkey action failed")
                elif msg.message == self.WM_WAKE:
                    self._drain()
        except Exception:
            log.exception("The hotkey thread stopped")
        finally:
            try:
                user32.UnregisterHotKey(None, self.HOTKEY_ID)
            except Exception:
                pass

    def _drain(self):
        while True:
            try:
                mods, vk, done, out = self._cmds.get_nowait()
            except queue.Empty:
                return
            user32.UnregisterHotKey(None, self.HOTKEY_ID)
            result = None
            if vk is not None:
                if not user32.RegisterHotKey(None, self.HOTKEY_ID, mods | 0x4000, vk):     # MOD_NOREPEAT
                    result = "already" if ctypes.get_last_error() == 1409 else "failed"
            out.append(result)
            done.set()

    def apply(self, mods, vk):
        """Registers the shortcut, or removes it when vk is None. Returns None on success, else 'already'/'failed'."""
        if vk is None and not (self._thread is not None and self._thread.is_alive()):
            return None
        if not self._ensure_thread():
            return "failed"
        done, out = threading.Event(), []
        self._cmds.put((mods, vk, done, out))
        user32.PostThreadMessageW(self._tid, self.WM_WAKE, 0, 0)
        if not done.wait(3):
            return "failed"
        return out[0] if out else None


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", RECT), ("rcWork", RECT), ("dwFlags", wintypes.DWORD)]


def _declare_win32():
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, wintypes.UINT]
    user32.SetWindowPos.restype = wintypes.BOOL
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
    user32.GetCursorPos.restype = wintypes.BOOL
    user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    user32.GetAsyncKeyState.restype = ctypes.c_short
    user32.GetSystemMetrics.argtypes = [ctypes.c_int]
    user32.GetSystemMetrics.restype = ctypes.c_int
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ShowWindow.restype = wintypes.BOOL
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.IsWindow.restype = wintypes.BOOL
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowW.restype = wintypes.HWND
    user32.SetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPCWSTR]
    user32.SetWindowTextW.restype = wintypes.BOOL
    user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.SendMessageW.restype = ctypes.c_ssize_t
    user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int, ctypes.c_int,
                                  wintypes.UINT]
    user32.LoadImageW.restype = wintypes.HANDLE
    user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.MonitorFromWindow.restype = wintypes.HMONITOR
    user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFO)]
    user32.GetMonitorInfoW.restype = wintypes.BOOL
    user32.SystemParametersInfoW.argtypes = [wintypes.UINT, wintypes.UINT, ctypes.c_void_p, wintypes.UINT]
    user32.SystemParametersInfoW.restype = wintypes.BOOL
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.IsIconic.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateEventW.restype = wintypes.HANDLE
    kernel32.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.OpenEventW.restype = wintypes.HANDLE
    kernel32.SetEvent.argtypes = [wintypes.HANDLE]
    kernel32.SetEvent.restype = wintypes.BOOL
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    user32.GetForegroundWindow.argtypes = []
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
    user32.RegisterHotKey.restype = wintypes.BOOL
    user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.UnregisterHotKey.restype = wintypes.BOOL
    user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
    user32.GetMessageW.restype = ctypes.c_int
    user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT,
                                    wintypes.UINT]
    user32.PeekMessageW.restype = wintypes.BOOL
    user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.PostThreadMessageW.restype = wintypes.BOOL
    kernel32.GetCurrentThreadId.argtypes = []
    kernel32.GetCurrentThreadId.restype = wintypes.DWORD


try:
    _declare_win32()
except Exception:
    pass

SWP_FLAGS = 0x0004 | 0x0010     # SWP_NOZORDER | SWP_NOACTIVATE


def dpi_scale():
    try:
        return max(1.0, user32.GetDpiForSystem() / 96.0)
    except Exception:
        try:
            return max(1.0, ctypes.windll.shcore.GetScaleFactorForDevice(0) / 100.0)
        except Exception:
            return 1.0


def work_area():
    wa = RECT()
    try:
        user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(wa), 0)     # SPI_GETWORKAREA
        if wa.right > wa.left and wa.bottom > wa.top:
            return wa.left, wa.top, wa.right, wa.bottom
    except Exception:
        pass
    return 0, 0, 1366, 768


def initial_geometry():
    """The largest window with 1280x800 proportions that fits about 90% of the screen: x, y, w, h (physical px)."""
    left, top, right, bottom = work_area()
    ww, wh = right - left, bottom - top
    scale = dpi_scale()
    title = TITLE_H * scale
    stage_w = min(ww * 0.9, (wh * 0.9 - title) * ASPECT)
    w = int(stage_w)
    h = int(stage_w / ASPECT + title)
    return left + (ww - w) // 2, top + (wh - h) // 2, w, h, scale


class Chrome:
    """Frameless window behaviour: icon, drag, resize, minimize and maximize, all through Win32."""

    def __init__(self):
        self.window = None
        self.hwnd = 0
        self.maxed = False
        self.normal = None
        self._icons = None
        self._lock = threading.Lock()
        self._watching = False

    def find_hwnd(self):
        if self.hwnd and user32.IsWindow(self.hwnd):
            return self.hwnd
        handle = 0
        try:
            handle = int(self.window.native.Handle.ToInt64())
        except Exception:
            handle = 0
        if not handle:
            try:
                handle = int(user32.FindWindowW(None, APP_TITLE) or 0)
            except Exception:
                handle = 0
        self.hwnd = handle
        return handle

    def apply_icon(self):
        """WM_SETICON (big and small) from assets/favicon.ico, plus the window title."""
        hwnd = self.find_hwnd()
        if not hwnd:
            return False
        try:
            user32.SetWindowTextW(hwnd, "" if user32.IsIconic(hwnd) else APP_TITLE)
            if not os.path.isfile(ICON_PATH):
                log.warning("Icon file not found: %s", ICON_PATH)
                return False
            big = user32.GetSystemMetrics(11)       # SM_CXICON
            small = user32.GetSystemMetrics(49)     # SM_CXSMICON
            h_big = user32.LoadImageW(None, ICON_PATH, 1, big, big, 0x0010)        # IMAGE_ICON, LR_LOADFROMFILE
            h_small = user32.LoadImageW(None, ICON_PATH, 1, small, small, 0x0010)
            if h_big:
                user32.SendMessageW(hwnd, 0x0080, 1, h_big)         # WM_SETICON, ICON_BIG
            if h_small:
                user32.SendMessageW(hwnd, 0x0080, 0, h_small)       # WM_SETICON, ICON_SMALL
            self._icons = (h_big, h_small)
            return bool(h_big or h_small)
        except Exception:
            log.exception("apply_icon failed")
            return False

    def place(self, x, y, w, h):
        hwnd = self.find_hwnd()
        if hwnd:
            user32.SetWindowPos(hwnd, None, int(x), int(y), int(w), int(h), SWP_FLAGS)

    def enable_taskbar_minimize(self):
        """A frameless window has no minimize-box style, so Windows ignores a taskbar click on its focused
        button. Adding WS_MINIMIZEBOX | WS_SYSMENU makes that click minimize it like any other app."""
        hwnd = self.find_hwnd()
        if not hwnd:
            return False
        try:
            get_long = getattr(user32, "GetWindowLongPtrW", None) or user32.GetWindowLongW
            set_long = getattr(user32, "SetWindowLongPtrW", None) or user32.SetWindowLongW
            get_long.argtypes = [wintypes.HWND, ctypes.c_int]
            get_long.restype = ctypes.c_ssize_t
            set_long.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
            set_long.restype = ctypes.c_ssize_t
            style = get_long(hwnd, -16)                             # GWL_STYLE
            wanted = style | 0x00020000 | 0x00080000                # WS_MINIMIZEBOX | WS_SYSMENU
            if wanted != style:
                set_long(hwnd, -16, wanted)
                # SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED
                user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020)
            return True
        except Exception:
            log.exception("enable_taskbar_minimize failed")
            return False

    def apply_frame(self, maxed):
        """Windows 11 rounds a window's corners and draws a 1px border around it, so a window placed over the
        whole work area still shows the wallpaper in its corners and a thin line along its edges. Maximized,
        both are switched off so the window meets the screen edges like any other maximized app; restored,
        the Windows defaults come back. (Older Windows ignores these attributes.)"""
        hwnd = self.find_hwnd()
        if not hwnd or dwmapi is None:
            return
        try:
            corner = ctypes.c_uint(1 if maxed else 0)                      # DWMWCP_DONOTROUND / DWMWCP_DEFAULT
            dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(corner), 4)    # DWMWA_WINDOW_CORNER_PREFERENCE
            border = ctypes.c_uint(0xFFFFFFFE if maxed else 0xFFFFFFFF)    # DWMWA_COLOR_NONE / DWMWA_COLOR_DEFAULT
            dwmapi.DwmSetWindowAttribute(hwnd, 34, ctypes.byref(border), 4)    # DWMWA_BORDER_COLOR
        except Exception:
            log.exception("apply_frame failed")

    def minimize(self):
        hwnd = self.find_hwnd()
        if hwnd:
            user32.ShowWindow(hwnd, 6)      # SW_MINIMIZE

    def sync_title(self):
        """Minimized: the taskbar button keeps only the icon (empty title). Restored: the title comes back."""
        hwnd = self.find_hwnd()
        if not hwnd:
            return
        try:
            user32.SetWindowTextW(hwnd, "" if user32.IsIconic(hwnd) else APP_TITLE)
        except Exception:
            log.exception("sync_title failed")

    def watch_title(self):
        """Follows minimize and restore (taskbar click, buttons, launch) and updates the title to match."""
        if self._watching:
            return
        self._watching = True

        def loop():
            last = None
            while True:
                time.sleep(0.12)
                try:
                    hwnd = self.find_hwnd()
                    if not hwnd:
                        continue
                    iconic = bool(user32.IsIconic(hwnd))
                    if iconic != last:
                        last = iconic
                        self.sync_title()
                except Exception:
                    pass
        threading.Thread(target=loop, daemon=True).start()

    def show(self):
        """Brings the window back from the tray or the taskbar and to the front."""
        hwnd = self.find_hwnd()
        if not hwnd:
            return
        try:
            user32.ShowWindow(hwnd, 9 if user32.IsIconic(hwnd) else 5)     # SW_RESTORE / SW_SHOW
            flags = 0x0001 | 0x0002 | 0x0010                                # NOSIZE | NOMOVE | NOACTIVATE
            user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, flags)                # HWND_TOPMOST, then back, to win focus
            user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, flags)                # HWND_NOTOPMOST
            user32.SetForegroundWindow(hwnd)
            self.sync_title()
        except Exception:
            log.exception("show failed")

    def hide(self):
        hwnd = self.find_hwnd()
        if hwnd:
            user32.ShowWindow(hwnd, 0)      # SW_HIDE: gone from the taskbar, still running in the tray

    def toggle_maximize(self):
        hwnd = self.find_hwnd()
        if not hwnd:
            return self.maxed
        with self._lock:
            if self.maxed:
                if self.normal:
                    x, y, w, h = self.normal
                    user32.SetWindowPos(hwnd, None, x, y, w, h, SWP_FLAGS)
                self.maxed = False
            else:
                r = RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(r))
                self.normal = (r.left, r.top, r.right - r.left, r.bottom - r.top)
                mon = user32.MonitorFromWindow(hwnd, 2)         # MONITOR_DEFAULTTONEAREST
                info = MONITORINFO()
                info.cbSize = ctypes.sizeof(MONITORINFO)
                if mon and user32.GetMonitorInfoW(mon, ctypes.byref(info)):
                    wa = info.rcWork
                else:
                    wa = RECT(*work_area())
                user32.SetWindowPos(hwnd, None, wa.left, wa.top, wa.right - wa.left, wa.bottom - wa.top, SWP_FLAGS)
                self.maxed = True
        self.apply_frame(self.maxed)
        return self.maxed

    def begin(self, mode, edge=""):
        hwnd = self.find_hwnd()
        if not hwnd:
            return
        if mode == "resize" and self.maxed:
            return
        threading.Thread(target=self._loop, args=(hwnd, mode, edge), daemon=True).start()

    def _loop(self, hwnd, mode, edge):
        """Follows the mouse while its button is held and moves or resizes the window."""
        try:
            vk = 0x02 if user32.GetSystemMetrics(23) else 0x01      # swapped mouse buttons
            pt = POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            sx, sy = pt.x, pt.y
            r = RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            x0, y0, w0, h0 = r.left, r.top, r.right - r.left, r.bottom - r.top
            scale = dpi_scale()
            min_w = int(MIN_STAGE_W * scale)
            min_h = int(MIN_STAGE_W / ASPECT * scale + TITLE_H * scale)
            last = (x0, y0, w0, h0)
            restored = not self.maxed
            while user32.GetAsyncKeyState(vk) & 0x8000:
                user32.GetCursorPos(ctypes.byref(pt))
                dx, dy = pt.x - sx, pt.y - sy
                if mode == "move":
                    if not restored:
                        if abs(dx) + abs(dy) < 6:
                            time.sleep(0.01)
                            continue
                        nw, nh = (self.normal[2], self.normal[3]) if self.normal else (int(w0 * 0.8), int(h0 * 0.8))
                        frac = (sx - x0) / float(max(1, w0))
                        x0 = int(sx - frac * nw)
                        y0 = int(sy - 12 * scale)
                        w0, h0 = nw, nh
                        sx, sy = pt.x, pt.y
                        dx = dy = 0
                        self.maxed = False
                        restored = True
                        self._notify_max(False)
                    new = (x0 + dx, y0 + dy, w0, h0)
                else:
                    x, y, w, h = x0, y0, w0, h0
                    if "l" in edge:
                        w = max(min_w, w0 - dx)
                        x = x0 + (w0 - w)
                    if "r" in edge:
                        w = max(min_w, w0 + dx)
                    if "t" in edge:
                        h = max(min_h, h0 - dy)
                        y = y0 + (h0 - h)
                    if "b" in edge:
                        h = max(min_h, h0 + dy)
                    new = (x, y, w, h)
                if new != last:
                    user32.SetWindowPos(hwnd, None, new[0], new[1], new[2], new[3], SWP_FLAGS)
                    last = new
                time.sleep(0.008)
        except Exception:
            log.exception("window drag/resize loop failed")

    def _notify_max(self, state):
        self.apply_frame(state)         # runs at start-up, after a restore by dragging, and on every change
        try:
            if self.window is not None:
                self.window.evaluate_js("window.__bydMaxState && window.__bydMaxState(%s)" % ("true" if state else "false"))
        except Exception:
            pass


# ───────────────────────────── data layer ─────────────────────────────
def system_theme():
    """'light' or 'dark', following the Windows app color mode."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            value, _ = winreg.QueryValueEx(k, "AppsUseLightTheme")
        return "light" if int(value) else "dark"
    except Exception:
        return "dark"


def startup_command():
    if FROZEN:
        return '"%s" --background' % sys.executable
    py = sys.executable
    pyw = os.path.join(os.path.dirname(py), "pythonw.exe")
    if os.path.isfile(pyw):
        py = pyw
    return '"%s" "%s" --background' % (py, os.path.abspath(__file__))


def set_autostart(enabled):
    """Adds or removes Beyonder in the current user's Windows startup list."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if enabled:
                winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ, startup_command())
            else:
                try:
                    winreg.DeleteValue(k, RUN_NAME)
                except FileNotFoundError:
                    pass
        return True
    except Exception:
        log.exception("Could not update the Windows startup entry")
        return False


class Settings:
    """data/settings.json: theme, autostart, launch behaviour, Cross button, default sort and the global hotkey."""

    DEFAULTS = {"theme": "system", "autostart": True, "minimize_after_launch": True, "close_action": "tray",
                "sort": "manual", "hotkey_enabled": False, "hotkey": "Ctrl+Alt+B"}

    def __init__(self):
        self.lock = threading.RLock()
        self.data = dict(self.DEFAULTS)
        self.reload()

    def reload(self):
        """Reads settings.json again (also after a backup was restored); bad values fall back to the defaults."""
        with self.lock:
            self.data = dict(self.DEFAULTS)
            try:
                with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                if saved.get("theme") in ("light", "dark", "system"):
                    self.data["theme"] = saved["theme"]
                for key in ("autostart", "minimize_after_launch", "hotkey_enabled"):
                    if isinstance(saved.get(key), bool):
                        self.data[key] = saved[key]
                if saved.get("close_action") in ("tray", "quit"):
                    self.data["close_action"] = saved["close_action"]
                if saved.get("sort") in ("manual", "most_used", "recent"):
                    self.data["sort"] = saved["sort"]
                parsed = parse_hotkey(saved.get("hotkey"))
                if parsed:
                    self.data["hotkey"] = parsed[0]
            except FileNotFoundError:
                pass
            except Exception:
                log.exception("settings.json is unreadable; using defaults")

    def get(self, key):
        with self.lock:
            return self.data.get(key)

    def set(self, key, value):
        with self.lock:
            self.data[key] = value
            try:
                write_json_atomic(SETTINGS_PATH, self.data)
            except Exception:
                log.exception("Could not save settings.json")

    def resolved_theme(self):
        theme = self.get("theme")
        return system_theme() if theme == "system" else theme


class UserError(Exception):
    """A problem the person can fix; its text is shown in the popup."""


BAD_CHARS = '<>:"/\\|?*'
WIN_RESERVED = {"con", "prn", "aux", "nul"} | {"com%d" % i for i in range(1, 10)} | {"lpt%d" % i for i in range(1, 10)}
BROWSER_RESERVED = {"browsers.json", "launcher.json", "stats.json", "settings.json", "error.log", "error.log.1"}


def clean_text(value):
    return (value or "").strip()


def clean_path(value):
    return (value or "").strip().strip('"').strip()


def write_json_atomic(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            pass
    os.replace(tmp, path)


def file_url(path):
    """file:// address of an existing file, with a change stamp so the page never shows a stale picture."""
    try:
        if os.path.isfile(path):
            return Path(path).resolve().as_uri() + "?v=%d" % int(os.path.getmtime(path) * 1000)
    except Exception:
        log.exception("file_url failed for %s", path)
    return None



def smooth_resize(img, size):
    """Resize with premultiplied alpha so transparent edges do not darken the picture."""
    return img.convert("RGBa").resize(size, Image.LANCZOS).convert("RGBA")


def largest_ico(im):
    sizes = im.info.get("sizes")
    if sizes:
        im.size = max(sizes, key=lambda s: s[0] * s[1])
    im.load()
    return im.convert("RGBA")


def load_image_file(path):
    im = Image.open(path)
    if path.lower().endswith(".ico"):
        return largest_ico(im)
    im.load()
    return im.convert("RGBA")


def autocrop(im):
    box = im.getchannel("A").point(lambda v: 255 if v > 10 else 0).getbbox()
    return im.crop(box) if box else im


def build_icon_img(im):
    im = autocrop(im.convert("RGBA"))
    if im.height > 256:
        im = smooth_resize(im, (max(1, round(im.width * 256 / im.height)), 256))
    return im



# ───────────────────────────── profiles: identity, pictures ─────────────────────────────
PROFILE_RESERVED = {"icon.png", "browser.json", "imported.json"}      # files that live next to the profile folders
DEFAULT_KEY = "_beyonder_default"                                     # the key of the Default profile that only starts the browser
DEFAULT_NAME = "Default"                                              # its name is fixed
MAX_NAME = 80                                                         # longest profile name the Edit popup accepts
MAX_PICTURE_BYTES = 8 * 1024 * 1024                                   # biggest cropped picture the page may send


def safe_key(key):
    """The folder name for a profile key. Keys from browsers are already valid folder names; this is only a guard."""
    text = "".join("_" if (c in BAD_CHARS or ord(c) < 32) else c for c in str(key or "")).strip().rstrip(". ")
    if not text or text.lower() in WIN_RESERVED or text.lower() in PROFILE_RESERVED:
        text = "_" + text
    return text


def clean_color(value):
    """A colour as 6 hex digits in capitals (RRGGBB), or an empty text."""
    text = str(value or "").strip().lstrip("#")
    return text.upper() if re.fullmatch(r"[0-9A-Fa-f]{6}", text) else ""


def clean_profiles(items):
    """Profiles as stored: {"key", "name", "source_name", "renamed", "color", "args", "avatar_custom"}.
    The key (the browser's own folder ID) is the identity. Entries without one (older versions) are ignored."""
    out, seen = [], set()
    for p in items or []:
        if not isinstance(p, dict):
            continue
        key = p.get("key")
        if not isinstance(key, str) or not key.strip() or key in seen:
            continue
        seen.add(key)
        name = p.get("name") if isinstance(p.get("name"), str) and p["name"].strip() else key
        source = p.get("source_name") if isinstance(p.get("source_name"), str) and p["source_name"].strip() else name
        args = p.get("args")
        out.append({"key": key, "name": name, "source_name": source, "renamed": bool(p.get("renamed")),
                    "color": clean_color(p.get("color")),
                    "args": [str(a) for a in args] if isinstance(args, list) else [],
                    "avatar_custom": bool(p.get("avatar_custom"))})
    return out


def avatar_png_bytes(im):
    """A profile picture as PNG bytes, at most 256 x 256."""
    im = im.convert("RGBA")
    big = max(im.size)
    if big > 256:
        k = 256.0 / big
        im = smooth_resize(im, (max(1, round(im.width * k)), max(1, round(im.height * k))))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def write_avatar_file(folder, data):
    """Writes avatar.png from PNG bytes. Returns True when the file changed."""
    path = os.path.join(folder, "avatar.png")
    try:
        with open(path, "rb") as f:
            if f.read() == data:
                return False
    except OSError:
        pass
    os.makedirs(folder, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)
    return True


def remove_avatar_file(folder):
    """Removes Beyonder's own copy of a picture (never anything in a browser's folder)."""
    try:
        os.remove(os.path.join(folder, "avatar.png"))
        return True
    except OSError:
        return False


def thumb_data_url(im):
    """A small PNG data URL (at most 64 px) for the lists in the popups."""
    try:
        im = im.convert("RGBA")
        big = max(im.size)
        if big > 64:
            k = 64.0 / big
            im = smooth_resize(im, (max(1, round(im.width * k)), max(1, round(im.height * k))))
        buf = io.BytesIO()
        im.save(buf, "PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        log.exception("Could not make a small picture")
        return None


def decode_picture_data_url(value):
    """The cropped picture sent by the page (a data URL) as a checked RGBA image. Raises UserError when it is not a picture."""
    if not isinstance(value, str) or not value.startswith("data:image/") or "," not in value:
        raise UserError("Couldn't read the picture.")
    payload = value.split(",", 1)[1]
    if len(payload) > MAX_PICTURE_BYTES * 4 // 3 + 16:
        raise UserError("That picture is too large.")
    try:
        raw = base64.b64decode(payload)
        with Image.open(io.BytesIO(raw)) as probe:
            probe.verify()
        im = Image.open(io.BytesIO(raw))
        im.load()
    except Exception:
        log.exception("Could not decode the picture sent by the page")
        raise UserError("Couldn't read the picture.")
    if im.width < 1 or im.height < 1 or im.width > 8000 or im.height > 8000:
        raise UserError("That picture is too large.")
    return im.convert("RGBA")


def picture_data_url(path):
    """A picture file as a data URL for the crop popup (EXIF rotation applied, at most 1600 px)."""
    from PIL import ImageOps
    ext = os.path.splitext(path)[1].lower()
    if ext == ".ico":
        im = load_image_file(path)
    else:
        im = ImageOps.exif_transpose(Image.open(path))
        im.load()
    im.thumbnail((1600, 1600), Image.LANCZOS)
    has_alpha = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
    buf = io.BytesIO()
    if has_alpha:
        im.convert("RGBA").save(buf, "PNG")
        mime = "image/png"
    else:
        im.convert("RGB").save(buf, "JPEG", quality=92)
        mime = "image/jpeg"
    return "data:%s;base64,%s" % (mime, base64.b64encode(buf.getvalue()).decode("ascii")), im.width, im.height


def spawn_browser(exe, args=()):
    """Starts a program detached from Beyonder. Returns True when it started."""
    try:
        if not os.path.isfile(exe):
            raise FileNotFoundError(exe)
        subprocess.Popen([exe] + [str(a) for a in args], cwd=os.path.dirname(exe) or None, close_fds=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=0x00000008 | 0x00000200)      # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        return True
    except Exception:
        log.warning("Could not start %s", exe, exc_info=True)
        return False


def make_backup(dest):
    """Zips the data folder (without logs and temp files) into dest, as data/... entries. Returns the file count."""
    dest = os.path.abspath(dest)
    root = os.path.realpath(DATA_DIR)
    if os.path.realpath(dest).startswith(root + os.sep):
        raise UserError("Save the backup outside the data folder.")
    tmp = dest + ".tmp"
    count = 0
    try:
        os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
            for folder, dirs, files in os.walk(DATA_DIR):
                rel_folder = os.path.relpath(folder, DATA_DIR).replace(os.sep, "/")
                for d in dirs:
                    rel = d if rel_folder == "." else rel_folder + "/" + d
                    zf.write(os.path.join(folder, d), "data/" + rel)
                for name in files:
                    if name.startswith("error.log") or name.endswith(".tmp") or ".bad-" in name:
                        continue
                    rel = name if rel_folder == "." else rel_folder + "/" + name
                    zf.write(os.path.join(folder, name), "data/" + rel)
                    count += 1
        os.replace(tmp, dest)
    except Exception:
        log.exception("Backup failed")
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise UserError("Couldn't write the backup. Check the folder and try again.")
    return count


def restore_from_zip(path):
    """Replaces the contents of the data folder with a backup made by make_backup.
    A copy of the current data is saved next to the data folder first; its path is returned."""
    path = clean_path(path)
    if not os.path.isfile(path):
        raise UserError("That backup file doesn't exist.")
    try:
        zf = zipfile.ZipFile(path)
    except Exception:
        raise UserError("That isn't a valid backup (.zip) file.")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    tmp = os.path.join(APP_DIR, "data-restore-%s" % stamp)
    with zf:
        entries = []
        for info in zf.infolist():
            parts = [p for p in info.filename.replace("\\", "/").split("/") if p]
            if not parts:
                continue
            if parts[0] != "data" or any(p == ".." or ":" in p for p in parts):
                raise UserError("That zip is not a Beyonder backup.")
            if len(parts) > 1:
                entries.append((info, parts[1:]))
        top = {rel[0] for _, rel in entries}
        if not top & {"browsers.json", "launcher.json", "settings.json", "stats.json"}:
            raise UserError("That zip is not a Beyonder backup.")
        try:
            os.makedirs(tmp)
            tmp_real = os.path.realpath(tmp)
            for info, rel in entries:
                if rel[0].startswith("error.log"):
                    continue
                target = os.path.join(tmp, *rel)
                if not os.path.realpath(target).startswith(tmp_real + os.sep):
                    raise UserError("That zip is not a safe backup.")
                if info.is_dir():
                    os.makedirs(target, exist_ok=True)
                else:
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    with zf.open(info) as src_file, open(target, "wb") as out_file:
                        shutil.copyfileobj(src_file, out_file)
        except UserError:
            shutil.rmtree(tmp, ignore_errors=True)
            raise
        except Exception:
            log.exception("Could not unpack the backup")
            shutil.rmtree(tmp, ignore_errors=True)
            raise UserError("Couldn't read that backup.")
    safety = os.path.join(APP_DIR, "data-before-restore-%s.zip" % stamp)
    try:
        make_backup(safety)
    except UserError:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        for name in os.listdir(DATA_DIR):
            if name.startswith("error.log"):
                continue
            full = os.path.join(DATA_DIR, name)
            if os.path.isdir(full) and not os.path.islink(full):
                shutil.rmtree(full)
            else:
                os.remove(full)
        for name in os.listdir(tmp):
            shutil.move(os.path.join(tmp, name), os.path.join(DATA_DIR, name))
    except Exception:
        log.exception("Restore stopped half-way")
        raise UserError("The restore stopped half-way. Your previous data is saved in:\n%s" % safety)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return safety



# ───────────────────────────── installed browsers ─────────────────────────────
# Where well-known browsers live when they did not register themselves with Windows: (name, install paths).
KNOWN_BROWSERS = (
    ("Google Chrome", (r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
                       r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
                       r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")),
    ("Microsoft Edge", (r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
                        r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe")),
    ("Brave", (r"%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe",
               r"%ProgramFiles(x86)%\BraveSoftware\Brave-Browser\Application\brave.exe",
               r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe")),
    ("Mozilla Firefox", (r"%ProgramFiles%\Mozilla Firefox\firefox.exe",
                         r"%ProgramFiles(x86)%\Mozilla Firefox\firefox.exe")),
    ("Opera", (r"%LOCALAPPDATA%\Programs\Opera\opera.exe",
               r"%ProgramFiles%\Opera\opera.exe")),
    ("Opera GX", (r"%LOCALAPPDATA%\Programs\Opera GX\opera.exe",
                  r"%ProgramFiles%\Opera GX\opera.exe")),
    ("Vivaldi", (r"%LOCALAPPDATA%\Vivaldi\Application\vivaldi.exe",
                 r"%ProgramFiles%\Vivaldi\Application\vivaldi.exe")),
    ("Chromium", (r"%LOCALAPPDATA%\Chromium\Application\chrome.exe",)),
    ("Zen Browser", (r"%ProgramFiles%\Zen Browser\zen.exe",
                     r"%LOCALAPPDATA%\Zen Browser\zen.exe")),
    ("LibreWolf", (r"%ProgramFiles%\LibreWolf\librewolf.exe",)),
    ("Waterfox", (r"%ProgramFiles%\Waterfox\waterfox.exe",)),
    ("Yandex Browser", (r"%LOCALAPPDATA%\Yandex\YandexBrowser\Application\browser.exe",)),
)

# Pictures in assets/browser-icons that stand in when a program file has no icon of its own: (word in the name, part of the file name).
BUNDLED_ICON_HINTS = (("gx", "opera_gx"), ("opera", "opera_browser"), ("helium", "helium"), ("chrome", "google_chrome"),
                      ("brave", "brave"), ("arc", "arc_"), ("vivaldi", "vivaldi"), ("zen", "zen"))


# Program file name -> display name, used to name a browser picked with Add Manually.
# opera.exe and chrome.exe are refined by known_exe_name() from the folder names around them.
BROWSER_EXE_NAMES = {
    "opera.exe": "Opera", "chrome.exe": "Google Chrome", "brave.exe": "Brave", "firefox.exe": "Mozilla Firefox",
    "vivaldi.exe": "Vivaldi", "msedge.exe": "Microsoft Edge", "zen.exe": "Zen Browser", "librewolf.exe": "LibreWolf",
    "waterfox.exe": "Waterfox", "thorium.exe": "Thorium", "floorp.exe": "Floorp", "helium.exe": "Helium",
}


def exe_from_command(command):
    """The program file out of a registry command line such as: "C:\\Program Files\\X\\x.exe" --flag."""
    text = os.path.expandvars((command or "").strip())
    if text.startswith('"'):
        end = text.find('"', 1)
        path = text[1:end] if end > 0 else text[1:]
    else:
        m = re.match(r"(.+?\.exe)(?:\s|$)", text, re.IGNORECASE)
        path = m.group(1) if m else text.split(" ")[0]
    return os.path.normpath(path) if path else ""


def registry_browsers():
    """The browsers Windows itself lists as web browsers (the same list as Default apps): [(name, exe), ...]."""
    import winreg
    found = []
    spots = ((winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_64KEY), (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY),
             (winreg.HKEY_CURRENT_USER, 0))
    for hive, view in spots:
        try:
            base = winreg.OpenKey(hive, r"SOFTWARE\Clients\StartMenuInternet", 0, winreg.KEY_READ | view)
        except OSError:
            continue
        with base:
            index = 0
            while True:
                try:
                    sub = winreg.EnumKey(base, index)
                except OSError:
                    break
                index += 1
                name, command = "", ""
                try:
                    with winreg.OpenKey(base, sub, 0, winreg.KEY_READ | view) as k:
                        name = winreg.QueryValueEx(k, "")[0]
                except OSError:
                    pass
                if not (isinstance(name, str) and name.strip()) or name.startswith("@"):
                    try:
                        with winreg.OpenKey(base, sub + r"\Capabilities", 0, winreg.KEY_READ | view) as k:
                            name = winreg.QueryValueEx(k, "ApplicationName")[0]
                    except OSError:
                        name = ""
                if not isinstance(name, str) or name.startswith("@"):
                    name = ""
                try:
                    with winreg.OpenKey(base, sub + r"\shell\open\command", 0, winreg.KEY_READ | view) as k:
                        command = winreg.QueryValueEx(k, "")[0]
                except OSError:
                    continue
                exe = exe_from_command(command if isinstance(command, str) else "")
                if exe:
                    found.append((name, exe))
    return found


def clean_browser_name(name, exe):
    """A name that is safe to use as a folder name: no 'Stable' tail, no characters Windows refuses."""
    text = clean_text(name)
    if text.lower().endswith(" stable"):
        text = text[:-7].strip()
    text = "".join(c for c in text if c not in BAD_CHARS and ord(c) >= 32).strip().rstrip(".").strip()
    if not text:
        stem = os.path.splitext(os.path.basename(exe))[0]
        if stem.lower() in ("launcher", "browser", "application", "app"):
            stem = os.path.basename(os.path.dirname(exe)) or stem
        text = stem.replace("_", " ").replace("-", " ").title()
    text = text[:80].strip() or "Browser"
    if text.lower() in WIN_RESERVED or text.lower() in BROWSER_RESERVED:
        text += " Browser"
    return text


def flat_text(text):
    """Lower case without spaces, dashes and underscores, for loose comparing of names."""
    return re.sub(r"[\s_\-]+", "", (text or "").lower())


def known_exe_name(exe):
    """The display name of a well-known browser program file (looking at the folders around it), or None."""
    base = os.path.basename(exe).lower()
    name = BROWSER_EXE_NAMES.get(base)
    if name is None:
        return None
    flat = flat_text(exe)
    if base == "opera.exe":
        return "Opera GX" if "operagx" in flat else "Opera"
    if base == "chrome.exe":
        return "Chromium" if "chromium" in flat else "Google Chrome"
    return name


def known_name_from_path(exe):
    """A known browser name taken from the program file or any folder around it (for example a folder called
    'Opera GX'), or None."""
    name = known_exe_name(exe)
    if name:
        return name
    names = {flat_text(n): n for n, _ in KNOWN_BROWSERS}
    for n in BROWSER_EXE_NAMES.values():
        names[flat_text(n)] = n
    names["opera"] = "Opera"
    names["operagx"] = "Opera GX"
    parts = os.path.normpath(exe).split(os.sep)
    stem = os.path.splitext(parts[-1])[0]
    for part in [stem] + list(reversed(parts[:-1])):
        hit = names.get(flat_text(part))
        if hit:
            return hit
    return None


def exe_product_name(exe):
    """ProductName from the version info of a program file (version.dll), or an empty text."""
    try:
        ver = ctypes.WinDLL("version", use_last_error=True)
        ver.GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
        ver.GetFileVersionInfoSizeW.restype = wintypes.DWORD
        ver.GetFileVersionInfoW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
        ver.GetFileVersionInfoW.restype = wintypes.BOOL
        ver.VerQueryValueW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p),
                                       ctypes.POINTER(wintypes.UINT)]
        ver.VerQueryValueW.restype = wintypes.BOOL
        size = ver.GetFileVersionInfoSizeW(exe, None)
        if not size:
            return ""
        buf = ctypes.create_string_buffer(size)
        if not ver.GetFileVersionInfoW(exe, 0, size, buf):
            return ""
        ptr, length = ctypes.c_void_p(), wintypes.UINT(0)
        codes = []
        if ver.VerQueryValueW(buf, "\\VarFileInfo\\Translation", ctypes.byref(ptr), ctypes.byref(length)) \
                and ptr.value and length.value >= 4:
            raw = ctypes.string_at(ptr.value, length.value)
            for i in range(0, len(raw) - 3, 4):
                lang, page = struct.unpack("<HH", raw[i:i + 4])
                codes.append("%04x%04x" % (lang, page))
        codes += ["040904b0", "040904e4", "000004b0"]
        for code in codes:
            ptr, length = ctypes.c_void_p(), wintypes.UINT(0)
            if ver.VerQueryValueW(buf, "\\StringFileInfo\\%s\\ProductName" % code, ctypes.byref(ptr),
                                  ctypes.byref(length)) and ptr.value and length.value:
                text = ctypes.wstring_at(ptr.value, length.value).replace("\x00", "").strip()
                if text:
                    return text
    except Exception:
        log.exception("Could not read the version info of %s", exe)
    return ""


def guess_browser_name(exe):
    """A name for a browser program file the person picked by hand (nothing to type)."""
    name = known_name_from_path(exe)
    if not name:
        product = exe_product_name(exe)
        if product.lower().endswith(" internet browser"):
            product = product[:-len(" internet browser")].strip()
        name = product
    if not name:
        name = os.path.basename(os.path.dirname(exe))
    if not name:
        name = os.path.splitext(os.path.basename(exe))[0]
    return clean_browser_name(name, exe)


def find_installed_browsers():
    """Every browser found on this PC: [{"id", "name", "exe", "icon"}], sorted by name.
    icon is a small PNG data URL for the picker (or None); id stays the same for the same program file."""
    raw = []
    try:
        raw.extend(registry_browsers())
    except Exception:
        log.exception("Reading the browser list from the registry failed")
    listed = {clean_browser_name(n, e).lower() for n, e in raw}
    for name, templates in KNOWN_BROWSERS:
        if name.lower() in listed:
            continue
        for template in templates:
            path = os.path.expandvars(template)
            if os.path.isfile(path):
                raw.append((name, path))
                break
    mine = os.path.normcase(os.path.normpath(APP_DIR)) + os.sep
    out, seen_exe, seen_name = [], set(), set()
    for name, exe in raw:
        exe = os.path.normpath(exe)
        key = os.path.normcase(exe)
        if key in seen_exe or os.path.basename(key) == "iexplore.exe" or not os.path.isfile(exe):
            continue
        if key.startswith(mine):                        # never list Beyonder itself
            continue
        name = clean_browser_name(name, exe)
        if name.lower() == "beyonder":
            continue
        unique, n = name, 2
        while unique.lower() in seen_name:
            unique = "%s (%d)" % (name, n)
            n += 1
        seen_exe.add(key)
        seen_name.add(unique.lower())
        out.append({"id": hashlib.sha1(key.encode("utf-8")).hexdigest()[:12], "name": unique, "exe": exe})
    out.sort(key=lambda f: f["name"].lower())
    for f in out:
        try:
            f["icon"] = icon_data_url(f["name"], f["exe"])
        except Exception:
            log.exception("Could not make the picture for %s", f["name"])
            f["icon"] = None
    return out


# ── the icon inside a program file (Win32, no extra packages) ──
class _ICONINFO(ctypes.Structure):
    _fields_ = [("fIcon", wintypes.BOOL), ("xHotspot", wintypes.DWORD), ("yHotspot", wintypes.DWORD),
                ("hbmMask", ctypes.c_void_p), ("hbmColor", ctypes.c_void_p)]


class _BITMAP(ctypes.Structure):
    _fields_ = [("bmType", wintypes.LONG), ("bmWidth", wintypes.LONG), ("bmHeight", wintypes.LONG),
                ("bmWidthBytes", wintypes.LONG), ("bmPlanes", wintypes.WORD), ("bmBitsPixel", wintypes.WORD),
                ("bmBits", ctypes.c_void_p)]


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


_icon_api = None


def icon_api():
    """Private copies of user32 and gdi32 with exact argument types (so 64-bit handles are never cut short)."""
    global _icon_api
    if _icon_api is None:
        u32 = ctypes.WinDLL("user32", use_last_error=True)
        g32 = ctypes.WinDLL("gdi32", use_last_error=True)
        vp = ctypes.c_void_p
        u32.PrivateExtractIconsW.argtypes = [wintypes.LPCWSTR, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                             ctypes.POINTER(vp), ctypes.POINTER(wintypes.UINT), wintypes.UINT,
                                             wintypes.UINT]
        u32.PrivateExtractIconsW.restype = wintypes.UINT
        u32.GetIconInfo.argtypes = [vp, ctypes.POINTER(_ICONINFO)]
        u32.GetIconInfo.restype = wintypes.BOOL
        u32.DestroyIcon.argtypes = [vp]
        u32.DestroyIcon.restype = wintypes.BOOL
        u32.GetDC.argtypes = [vp]
        u32.GetDC.restype = vp
        u32.ReleaseDC.argtypes = [vp, vp]
        u32.ReleaseDC.restype = ctypes.c_int
        g32.GetObjectW.argtypes = [vp, ctypes.c_int, vp]
        g32.GetObjectW.restype = ctypes.c_int
        g32.GetDIBits.argtypes = [vp, vp, wintypes.UINT, wintypes.UINT, vp, vp, wintypes.UINT]
        g32.GetDIBits.restype = ctypes.c_int
        g32.DeleteObject.argtypes = [vp]
        g32.DeleteObject.restype = wintypes.BOOL
        _icon_api = (u32, g32)
    return _icon_api


def hicon_to_image(hicon, u32, g32):
    """An icon handle as a Pillow RGBA picture, or None."""
    info = _ICONINFO()
    if not u32.GetIconInfo(hicon, ctypes.byref(info)):
        return None
    hdc = None
    try:
        if not info.hbmColor:
            return None
        bm = _BITMAP()
        if not g32.GetObjectW(info.hbmColor, ctypes.sizeof(bm), ctypes.byref(bm)):
            return None
        w, h = int(bm.bmWidth), int(bm.bmHeight)
        if w <= 0 or h <= 0 or w > 1024 or h > 1024:
            return None
        hdc = u32.GetDC(None)

        def grab(hbm):
            head = _BITMAPINFOHEADER()
            head.biSize = ctypes.sizeof(head)
            head.biWidth = w
            head.biHeight = -h                  # top-down rows
            head.biPlanes = 1
            head.biBitCount = 32
            head.biCompression = 0              # BI_RGB
            buf = ctypes.create_string_buffer(w * h * 4)
            got = g32.GetDIBits(hdc, hbm, 0, h, buf, ctypes.byref(head), 0)
            return buf.raw if got else None

        color = grab(info.hbmColor)
        if color is None:
            return None
        im = Image.frombuffer("RGBA", (w, h), color, "raw", "BGRA", 0, 1)
        alpha = im.getchannel("A")
        if alpha.getextrema() == (0, 0):        # an old-style icon without an alpha channel: its mask says what is see-through
            mask = grab(info.hbmMask) if info.hbmMask else None
            if mask is not None:
                m = Image.frombuffer("RGBA", (w, h), mask, "raw", "BGRA", 0, 1).convert("L")
                alpha = m.point(lambda v: 0 if v > 127 else 255)
            else:
                alpha = Image.new("L", (w, h), 255)
            im.putalpha(alpha)
        return im.copy()
    finally:
        if hdc:
            u32.ReleaseDC(None, hdc)
        if info.hbmColor:
            g32.DeleteObject(info.hbmColor)
        if info.hbmMask:
            g32.DeleteObject(info.hbmMask)


def exe_icon_image(path):
    """The largest icon stored inside a program file as an RGBA picture, or None."""
    try:
        u32, g32 = icon_api()
    except Exception:
        log.exception("The Windows icon functions are not available")
        return None
    for size in (256, 128, 48):
        hicon = ctypes.c_void_p()
        icon_id = wintypes.UINT()
        try:
            count = u32.PrivateExtractIconsW(path, 0, size, size, ctypes.byref(hicon), ctypes.byref(icon_id), 1, 0)
        except Exception:
            log.exception("PrivateExtractIconsW failed for %s", path)
            return None
        if not count or count == 0xFFFFFFFF or not hicon.value:
            continue
        try:
            im = hicon_to_image(hicon, u32, g32)
        finally:
            u32.DestroyIcon(hicon)
        if im is not None:
            return im
    return None


def bundled_icon_image(name):
    """A picture from assets/browser-icons for a well-known browser, or None."""
    folder = os.path.join(RES_DIR, "assets", "browser-icons")
    try:
        files = os.listdir(folder)
    except OSError:
        return None
    lowered = (name or "").lower()
    for word, part in BUNDLED_ICON_HINTS:
        if not re.search(r"\b%s\b" % word, lowered):
            continue
        for f in files:
            if part in f.lower():
                try:
                    return load_image_file(os.path.join(folder, f))
                except Exception:
                    log.exception("Could not read the bundled icon %s", f)
    return None


def browser_icon_image(name, exe):
    """The browser's own icon (from its program file); a bundled picture if that fails. Cropped, 256 px high at most."""
    im = None
    try:
        im = exe_icon_image(exe)
    except Exception:
        log.exception("Could not read the icon of %s", exe)
    if im is None:
        im = bundled_icon_image(name)
    return build_icon_img(im) if im is not None else None


def icon_data_url(name, exe):
    """A small PNG data URL of the browser's icon for the picker, or None."""
    im = browser_icon_image(name, exe)
    if im is None:
        return None
    small = im.copy()
    small.thumbnail((96, 96), Image.LANCZOS)
    buf = io.BytesIO()
    small.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


# ───────────────────────────── profile readers ─────────────────────────────
# One small adapter per browser family. Each returns (profiles, data_dir, status):
#   profiles = [{"key", "name", "label", "color", "picture" (PIL image or None), "args"}] in the browser's own order, or None
#   data_dir = the folder the profiles were read from ("" when none was found)
#   status   = "ok", "unreadable" (a file could not be parsed, even after a retry) or "notfound" (no data folder)
# They only READ: nothing in a browser's data folder is ever written, renamed or locked.

# Opera may rename these flags in a future version; they are copied from the working shortcut of Opera GX's side profiles.
OPERA_GX_FIXED_FLAGS = ("--with-feature:side-profiles", "--with-feature:gx-profiles-revived",
                        "--no-default-browser-check", "--disable-usage-statistics-question")

# Chromium browsers: words that must all be in the browser's name -> User Data folder under %LOCALAPPDATA%.
# More specific rows (Beta, Dev, Canary) come before the plain one.
CHROMIUM_DATA_DIRS = (
    (("chrome", "beta"), r"Google\Chrome Beta\User Data"),
    (("chrome", "dev"), r"Google\Chrome Dev\User Data"),
    (("chrome", "canary"), r"Google\Chrome SxS\User Data"),
    (("chrome", "sxs"), r"Google\Chrome SxS\User Data"),
    (("chrome",), r"Google\Chrome\User Data"),
    (("edge", "beta"), r"Microsoft\Edge Beta\User Data"),
    (("edge", "dev"), r"Microsoft\Edge Dev\User Data"),
    (("edge", "canary"), r"Microsoft\Edge SxS\User Data"),
    (("edge",), r"Microsoft\Edge\User Data"),
    (("brave", "beta"), r"BraveSoftware\Brave-Browser-Beta\User Data"),
    (("brave", "nightly"), r"BraveSoftware\Brave-Browser-Nightly\User Data"),
    (("brave",), r"BraveSoftware\Brave-Browser\User Data"),
    (("vivaldi",), r"Vivaldi\User Data"),
    (("chromium",), r"Chromium\User Data"),
    (("helium",), r"imput\Helium\User Data"),          # VERIFY: found on the web for Helium on Windows
    (("helium",), r"Helium\User Data"),
)

# Firefox family: words in the browser's name -> folder under %APPDATA% that holds profiles.ini (VERIFY each)
FIREFOX_DATA_DIRS = (
    (("librewolf",), "LibreWolf"),
    (("waterfox",), "Waterfox"),
    (("waterfox",), r"Waterfox\Waterfox"),          # the older doubled layout
    (("zen",), "zen"),
    (("floorp",), "Floorp"),
    (("firefox",), r"Mozilla\Firefox"),
)

GENERIC_WORDS = {"browser", "web", "the", "internet", "software", "chrome", "launcher", "application", "app"}
UNSUPPORTED_TEXT = "Profile import isn't supported for %s yet."
READ_FAILED_TEXT = "The browser's profile list could not be read. Close the browser and try again."


def env_dir(name):
    return os.environ.get(name) or ""


def read_json_file(path):
    """A JSON file (UTF-8, a BOM is fine) as (dict, status). One retry after 200 ms: the browser may be writing it."""
    for attempt in (1, 2):
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            return (data if isinstance(data, dict) else {}), "ok"
        except FileNotFoundError:
            return None, "missing"
        except Exception:
            if attempt == 1:
                time.sleep(0.2)
                continue
            log.warning("Could not read %s", path, exc_info=True)
    return None, "unreadable"


def name_words(name, exe):
    """Words of the browser's name (and its program's name) used to recognise its folders."""
    words = set(re.findall(r"[a-z0-9]{3,}", (name or "").lower()))
    stem = os.path.splitext(os.path.basename(exe or ""))[0].lower()
    if len(stem) >= 3:
        words.add(stem)
    return {w for w in words if w not in GENERIC_WORDS}


# Browsers that have no profile system: Add Profiles opens the notice at once instead of the Add Profiles popup.
# Their only profile is the Default one that Beyonder adds (it just starts the program). To add another browser of this
# kind, give browser_kind a new kind for it and add a row here.
UNSUPPORTED_KINDS = {"opera": "Opera", "tor": "Tor Browser"}


def browser_kind(name, exe):
    """Which reader a browser needs: "opera_gx", "firefox" or "chromium"; or a kind of UNSUPPORTED_KINDS
    ("opera", "tor"): browsers without profiles."""
    low = (name or "").lower()
    path = (exe or "").lower()
    base = os.path.basename(path)
    if re.search(r"(?<![a-z0-9])tor(?![a-z0-9])", low) or "tor browser" in path or "torbrowser" in path:
        return "tor"                                    # Tor Browser's program is called firefox.exe: check it first
    if "gx" in low or "opera gx" in path or "operagx" in path:
        return "opera_gx"
    if "opera" in low or base == "opera.exe":
        return "opera"
    for word in ("firefox", "librewolf", "waterfox", "zen", "floorp"):
        if word in base or word in low:
            return "firefox"
    return "chromium"


# ── Where a browser keeps its profiles ──
# Order of the search (see locate_data_dir): the folder remembered in browser.json, then the usual places and the
# folders around the program file. A browser that sits in Program Files or in %LOCALAPPDATA% tries the usual places
# first; a standalone or portable one (anywhere else) looks around its program file first, because it keeps its data
# next to itself.
EXE_SKIP_DIRS = {"cache", "code cache", "gpucache", "service worker", "crashpad", "extensions", "node_modules", ".git",
                 "$recycle.bin", "system volume information", "windows"}
PORTABLE_DATA_NAMES = {"data", "profile", "profiles", "user data", "userdata"}   # the only folders searched beside a program folder


def chromium_has_state(folder):
    return bool(folder) and os.path.isfile(os.path.join(folder, "Local State"))


def firefox_has_ini(folder):
    return bool(folder) and os.path.isfile(os.path.join(folder, "profiles.ini"))


def firefox_has_prefs(folder):
    return bool(folder) and os.path.isfile(os.path.join(folder, "prefs.js"))


def operagx_base(folder):
    """The folder that holds _side_profiles. Older versions remembered the _side_profiles folder itself."""
    if folder and os.path.basename(os.path.normpath(folder)).lower() == "_side_profiles":
        return os.path.dirname(os.path.normpath(folder))
    return folder


def operagx_has_side(folder):
    return bool(folder) and os.path.isdir(os.path.join(operagx_base(folder), "_side_profiles"))


def valid_data_dir(kind, folder):
    if not folder or not os.path.isdir(folder):
        return False
    if kind == "chromium":
        return chromium_has_state(folder)
    if kind == "firefox":
        return firefox_has_ini(folder) or firefox_has_prefs(folder)
    if kind == "opera_gx":
        return operagx_has_side(folder)
    return False


def search_local_user_data(name, exe, claimed):
    """A 'User Data' folder (with a Local State file) up to two folders below %LOCALAPPDATA%, preferring the ones
    whose path has a word of the browser's name. Folders that belong to another well-known browser are skipped."""
    local = env_dir("LOCALAPPDATA")
    if not local or not os.path.isdir(local):
        return ""
    skip = {"packages", "temp", "crashdumps", "d3dscache", "microsoft", "programs"}

    def children(path):
        out = []
        try:
            with os.scandir(path) as it:
                for entry in it:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            out.append(entry)
                    except OSError:
                        continue
                    if len(out) >= 400:
                        break
        except OSError:
            pass
        return out

    candidates = []
    for d1 in children(local):
        if d1.name.lower() in skip:
            continue
        candidates.append(os.path.join(d1.path, "User Data"))
        for d2 in children(d1.path):
            candidates.append(os.path.join(d2.path, "User Data"))
    good = [c for c in candidates if chromium_has_state(c) and os.path.normcase(c) not in claimed]
    words = name_words(name, exe)
    matching = [c for c in good if any(w in os.path.relpath(c, local).lower() for w in words)]
    if matching:
        return sorted(matching)[0]
    return good[0] if len(good) == 1 else ""


def standard_chromium_dir(name, exe):
    """The User Data folder from the table of well-known browsers (or the one folder below %LOCALAPPDATA% that fits)."""
    flat = flat_text(name)
    local = env_dir("LOCALAPPDATA")
    claimed = set()
    for words, rel in CHROMIUM_DATA_DIRS:
        folder = os.path.join(local, rel) if local else ""
        if folder:
            claimed.add(os.path.normcase(folder))
        if folder and all(w in flat for w in words) and chromium_has_state(folder):
            return folder
    return search_local_user_data(name, exe, claimed)


def standard_firefox_dir(name, exe):
    """The folder under %APPDATA% that holds profiles.ini for this browser."""
    roaming = env_dir("APPDATA")
    if not roaming:
        return ""
    flat = flat_text(name) + flat_text(os.path.basename(exe or ""))
    for words, rel in FIREFOX_DATA_DIRS:
        folder = os.path.join(roaming, rel)
        if all(w in flat for w in words) and firefox_has_ini(folder):
            return folder
    if os.path.isdir(roaming):                          # any folder one level below %APPDATA% that looks like this browser
        words = name_words(name, exe)
        try:
            with os.scandir(roaming) as it:
                for entry in it:
                    try:
                        if entry.is_dir(follow_symlinks=False) and any(w in entry.name.lower() for w in words) \
                                and firefox_has_ini(entry.path):
                            return entry.path
                    except OSError:
                        continue
        except OSError:
            pass
    return ""


def standard_operagx_dir(exe):
    """The folder that holds _side_profiles: <program folder>\\profiles\\data, or %APPDATA%\\Opera Software\\Opera GX Stable."""
    roaming = env_dir("APPDATA")
    for base in (os.path.join(os.path.dirname(exe or ""), "profiles", "data"),
                 os.path.join(roaming, "Opera Software", "Opera GX Stable") if roaming else ""):
        if operagx_has_side(base):
            return base
    return ""


def standard_data_dir(kind, name, exe):
    if kind == "chromium":
        return standard_chromium_dir(name, exe)
    if kind == "firefox":
        return standard_firefox_dir(name, exe)
    if kind == "opera_gx":
        return standard_operagx_dir(exe)
    return ""


def exe_in_standard_place(exe):
    """True when the program file is under Program Files or %LOCALAPPDATA% (a normal install, not a portable one)."""
    path = os.path.normcase(os.path.normpath(exe or ""))
    for var in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432", "LOCALAPPDATA"):
        base = env_dir(var)
        if base:
            base = os.path.normcase(os.path.normpath(base))
            if path == base or path.startswith(base + os.sep):
                return True
    return False


def _is_reparse(entry):
    """A symlink or a junction: never followed."""
    try:
        if entry.is_symlink():
            return True
        return bool(getattr(entry.stat(follow_symlinks=False), "st_file_attributes", 0) & 0x400)
    except OSError:
        return True


def _unsafe_scan_root(path):
    """A drive root or a big system folder is never searched as a whole."""
    norm = os.path.normcase(os.path.normpath(path))
    if os.path.dirname(norm) == norm:
        return True
    for var in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432", "WINDIR", "USERPROFILE", "LOCALAPPDATA", "APPDATA"):
        value = env_dir(var)
        if value and os.path.normcase(os.path.normpath(value)) == norm:
            return True
    return False


def _scan_tree(kind, root, found, stats, skip_roots, only_names):
    """Walks root (read-only: only names are listed) and records every folder that carries a marker of this kind.
    only_names limits the first level below the root to folders with these names (None = every folder)."""
    stack = [(root, 0)]
    while stack:
        path, depth = stack.pop()
        try:
            with os.scandir(path) as it:
                entries = list(it)
        except OSError:                                 # PermissionError is an OSError too
            continue
        stats["dirs"] += 1
        stats["entries"] += len(entries)
        files, dirs = set(), {}
        for e in entries:
            try:
                if e.is_dir(follow_symlinks=False):
                    if not _is_reparse(e):
                        dirs[e.name.lower()] = e.path
                else:
                    files.add(e.name.lower())
            except OSError:
                continue
        leaf = False                                    # a folder that carries a marker is not walked any deeper
        if kind == "chromium" and "local state" in files:
            has_profile = "default" in dirs or any(re.fullmatch(r"profile \d+", d) for d in dirs)
            found.append((path, 0 if has_profile else 1))
            leaf = True
        elif kind == "firefox":
            if "profiles.ini" in files:
                found.append((path, 0))
                leaf = True
            elif "prefs.js" in files:
                here = os.path.basename(path).lower()
                above = os.path.basename(os.path.dirname(path)).lower()
                if here in ("profile", "data") or above in ("profile", "data"):
                    found.append((path, 1))
                    leaf = True
        elif kind == "opera_gx" and "_side_profiles" in dirs:
            found.append((os.path.dirname(dirs["_side_profiles"]), 0))      # the base folder, which holds _side_profiles
            leaf = True
        if leaf:
            continue
        for low, sub in dirs.items():
            if low in EXE_SKIP_DIRS or os.path.normcase(sub) in skip_roots:
                continue
            if depth == 0 and only_names is not None and low not in only_names:
                continue
            stack.append((sub, depth + 1))


def find_data_dir_near_exe(kind, exe):
    """Looks around a program file for the folder that holds its profiles (read-only: only names are listed, nothing is
    opened for writing). Returns the folder or an empty text.
      chromium: a folder with a Local State file (one that also has Default or Profile N is preferred)
      firefox:  a folder with profiles.ini, or the profile folder of a portable build (one that has prefs.js)
      opera_gx: the folder that holds _side_profiles (the base folder, which the reader appends _side_profiles to)
    The program's own folder is searched completely. Its parent and grandparent only through their Data / Profile /
    User Data folders, which is where portable builds keep their data, and only when the first search found nothing."""
    if kind not in ("chromium", "firefox", "opera_gx") or not exe:
        return ""
    started = time.time()
    exe_dir = os.path.dirname(os.path.normpath(exe))
    parent = os.path.dirname(exe_dir)
    grand = os.path.dirname(parent)
    stats = {"dirs": 0, "entries": 0}
    scanned = []
    best = ""
    for index, root in enumerate((exe_dir, parent, grand)):
        norm = os.path.normcase(root)
        if not root or norm in scanned or _unsafe_scan_root(root) or not os.path.isdir(root):
            continue
        found = []
        _scan_tree(kind, root, found, stats, set(scanned), None if index == 0 else PORTABLE_DATA_NAMES)
        scanned.append(norm)
        if found:
            found.sort(key=lambda item: (item[1], len(item[0]), item[0].lower()))
            best = found[0][0]
            break
    log.info("Looked around %s for the data folder of a %s browser: %d folders, %d entries, %.2f s -> %s",
             exe, kind, stats["dirs"], stats["entries"], time.time() - started, best or "nothing found")
    return best


NEAR_SCANS = {}                                         # normalised exe -> {"done": Event, "folder": text, "at": time}
NEAR_LOCK = threading.Lock()


def near_exe_data_dir(kind, exe, force=False):
    """find_data_dir_near_exe, run once at a time per program file: a second caller waits for the first one's result.
    A search that found nothing is repeated after 10 seconds (the browser may have made its data folder since)."""
    key = os.path.normcase(exe or "")
    with NEAR_LOCK:
        job = NEAR_SCANS.get(key)
        if job is not None and job["done"].is_set():
            if force or (not job["folder"] and time.time() - job["at"] > 10):
                job = None
        owner = job is None
        if owner:
            job = {"done": threading.Event(), "folder": "", "at": 0.0}
            NEAR_SCANS[key] = job
    if owner:
        try:
            job["folder"] = find_data_dir_near_exe(kind, exe)
        except Exception:
            log.exception("Looking around %s failed", exe)
        finally:
            job["at"] = time.time()
            job["done"].set()
    else:
        job["done"].wait()
    return job["folder"]


def locate_data_dir(kind, name, exe, cached=""):
    """The folder that holds a browser's profiles, or an empty text. Waits when the search around the program file is
    still running (the page shows its loader meanwhile)."""
    if kind == "opera_gx":
        cached = operagx_base(cached)
    if cached and valid_data_dir(kind, cached):
        return cached
    force = bool(cached)                                # the remembered folder is gone: search again
    order = (lambda: standard_data_dir(kind, name, exe), lambda: near_exe_data_dir(kind, exe, force))
    if not exe_in_standard_place(exe):
        order = order[::-1]
    for look in order:
        folder = look()
        if folder:
            return folder
    return ""


def load_picture_file(path):
    try:
        return load_image_file(path)
    except Exception:
        log.warning("Could not read the picture %s", path, exc_info=True)
        return None


# ── Chromium: Chrome, Edge, Brave, Vivaldi, Chromium, Helium and every other Chromium browser ──
def chromium_order(key):
    if key == "Default":
        return (0, 0, "")
    m = re.fullmatch(r"Profile (\d+)", key)
    if m:
        return (1, int(m.group(1)), "")
    return (2, 0, key.lower())


def read_chromium_profiles(name, exe, cached, pictures=True):
    data_dir = locate_data_dir("chromium", name, exe, cached)
    if not data_dir:
        return [], "", "notfound"
    state, status = read_json_file(os.path.join(data_dir, "Local State"))
    if status == "missing":
        return [], "", "notfound"
    if status != "ok":
        return [], data_dir, status
    profile = state.get("profile")
    cache = profile.get("info_cache") if isinstance(profile, dict) else None
    if not isinstance(cache, dict):
        return [], data_dir, "ok"
    out = []
    for key in sorted((k for k in cache if isinstance(k, str)), key=chromium_order):
        info = cache[key]
        if not isinstance(info, dict) or key in ("Guest Profile", "System Profile"):
            continue
        if info.get("is_ephemeral") or info.get("is_omitted"):
            continue
        folder = os.path.join(data_dir, key)
        if not os.path.isdir(folder):
            continue
        shown = key
        for field in ("name", "gaia_name", "user_name"):
            value = info.get(field)
            if isinstance(value, str) and value.strip():
                shown = value.strip()
                break
        picture = None
        if pictures:
            pic = os.path.join(folder, "Google Profile Picture.png")
            if os.path.isfile(pic):
                picture = load_picture_file(pic)
        color = ""
        fill = info.get("default_avatar_fill_color")
        if isinstance(fill, int) and not isinstance(fill, bool):
            color = "%06X" % (fill & 0xFFFFFF)              # a signed ARGB number: keep the RGB part
        out.append({"key": key, "name": shown, "label": key, "color": color, "picture": picture,
                    "args": ["--profile-directory=" + key]})
    return out, data_dir, "ok"


# ── Firefox, LibreWolf, Waterfox, Zen, Floorp ──
def read_ini_file(path):
    """profiles.ini as a ConfigParser (keys keep their letter case). One retry after 200 ms."""
    for attempt in (1, 2):
        cp = configparser.ConfigParser(interpolation=None, strict=False)
        cp.optionxform = str
        try:
            with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
                cp.read_file(f)
            return cp
        except FileNotFoundError:
            return None
        except Exception:
            if attempt == 1:
                time.sleep(0.2)
                continue
            log.warning("Could not read %s", path, exc_info=True)
    return None


def read_firefox_profiles(name, exe, cached, pictures=True):
    folder = locate_data_dir("firefox", name, exe, cached)
    if not folder:
        return [], "", "notfound"
    if not firefox_has_ini(folder):
        # a portable build that keeps one profile and no profiles.ini: the folder itself is the profile (VERIFY)
        key = os.path.basename(os.path.normpath(folder))
        return [{"key": key, "name": "Default", "label": key, "color": "", "picture": None,
                 "args": ["--profile", folder]}], folder, "ok"
    ini_dir = folder
    cp = read_ini_file(os.path.join(ini_dir, "profiles.ini"))
    if cp is None:
        return [], ini_dir, "unreadable"
    out, seen = [], set()
    for section in cp.sections():
        if not re.fullmatch(r"profile\d+", section, re.I):
            continue
        vals = {k.lower(): v for k, v in cp.items(section)}
        shown = (vals.get("name") or "").strip()
        path = (vals.get("path") or "").strip()
        parts = [s for s in re.split(r"[\\/]", path) if s]
        if not shown or not parts:
            continue
        if (vals.get("isrelative") or "1").strip() == "0":
            full = os.path.normpath(path)
        else:
            full = os.path.normpath(os.path.join(ini_dir, *parts))
        key = parts[-1]
        if key in seen or not os.path.isdir(full):
            continue
        seen.add(key)
        out.append({"key": key, "name": shown, "label": key, "color": "", "picture": None,
                    "args": ["-no-remote", "-P", shown]})   # VERIFY: -P selects the profile by its profiles.ini name
    return out, ini_dir, "ok"


# ── Opera GX: its own side profiles (not Chromium's Local State) ──
def read_operagx_profiles(name, exe, cached, pictures=True):
    base = locate_data_dir("opera_gx", name, exe, cached)
    if not base:
        return [], "", "notfound"
    side = os.path.join(base, "_side_profiles")         # always there; it only has no folders inside while no side profile exists
    try:
        entries = sorted(os.listdir(side), key=str.lower)
    except OSError:
        log.warning("Could not list %s", side, exc_info=True)
        return [], base, "unreadable"
    out = []
    for key in entries:
        folder = os.path.join(side, key)
        if not os.path.isdir(folder):
            continue
        try:
            files = sorted(os.listdir(folder), key=str.lower)
        except OSError:
            continue
        info = {}
        jsons = [f for f in files if f.lower().endswith(".json")]
        if jsons:
            info, status = read_json_file(os.path.join(folder, jsons[0]))
            if status == "unreadable":
                return [], base, "unreadable"          # do not guess names from a half-written file
            info = info or {}
        shown = info.get("name") if isinstance(info.get("name"), str) and info["name"].strip() else key
        theme = info.get("theme_id") if isinstance(info.get("theme_id"), str) else ""
        picture = None
        if pictures:
            icos = [f for f in files if f.lower().endswith(".ico")]
            if icos:
                picture = load_picture_file(os.path.join(folder, icos[0]))
        args = ["--side-profile-name=" + key]
        if theme:
            args.append("--side-profile-initial-theme-id=" + theme)
        args.extend(OPERA_GX_FIXED_FLAGS)
        out.append({"key": key, "name": shown.strip(), "label": key, "color": clean_color(info.get("color")),
                    "picture": picture, "args": args})
    out.sort(key=lambda p: p["name"].lower())
    return out, base, "ok"


READERS = {"chromium": read_chromium_profiles, "firefox": read_firefox_profiles, "opera_gx": read_operagx_profiles}


def unsupported_text(kind):
    return UNSUPPORTED_TEXT % UNSUPPORTED_KINDS.get(kind, "this browser")


def read_profiles(browser, pictures=True):
    """Picks the right reader for a browser {"name", "exe", "data_dir"}. Returns
    {"kind", "supported", "ok", "profiles", "data_dir", "located", "unsupported_text"}.
    supported is False only for a browser without a profile system (UNSUPPORTED_KINDS).
    ok is False only when a file exists but could not be read. located is False when no data folder was found at all:
    the list is then empty, but nothing can be said about profiles that were imported earlier."""
    name, exe = browser.get("name") or "", browser.get("exe") or ""
    kind = browser_kind(name, exe)
    res = {"kind": kind, "supported": True, "ok": True, "profiles": [], "data_dir": "", "located": False,
           "unsupported_text": ""}
    if kind in UNSUPPORTED_KINDS:
        res.update(supported=False, ok=False, unsupported_text=unsupported_text(kind))
        return res
    try:
        profiles, data_dir, status = READERS[kind](name, exe, browser.get("data_dir") or "", pictures)
    except Exception:
        log.exception("Reading the profiles of %s failed", name)
        profiles, data_dir, status = [], "", "unreadable"
    if status == "notfound":
        log.warning("No data folder found for %s (%s, %s): its profile list is empty", name, kind, exe)
        return res
    res.update(profiles=profiles or [], data_dir=data_dir, located=bool(data_dir), ok=(status == "ok"))
    return res


class Store:
    """All browsers, profiles and stats. Every public method holds the lock.

    Browsers come from the scan of this PC: each one is {"name", "exe", "profiles"}.
    On disk: data/launcher.json lists them; data/<Browser>/ holds icon.png, browser.json (the program file),
    imported.json (its profiles) and one folder per profile (its picture).
    """

    def __init__(self):
        self.lock = threading.RLock()
        os.makedirs(DATA_DIR, exist_ok=True)
        self.db = self._load_db()
        self.launches, self.usage = self._load_stats()
        self._scan = {}                 # id -> {"name", "exe", ...} from the last scan (and Add Manually picks), for add_browsers
        self._listed = set()            # ids of the tiles the popup shows right now
        self._profile_scan = {}         # browser -> {key: profile as read from the browser}, for add_profiles
        self.missing = {}               # browser -> keys of imported profiles the browser no longer has (set by the sync)

    # paths
    @staticmethod
    def folder(browser):
        return os.path.join(DATA_DIR, browser)

    @staticmethod
    def pfolder(browser, key):
        return os.path.join(DATA_DIR, browser, safe_key(key))

    @staticmethod
    def profiles_path(browser):
        return os.path.join(DATA_DIR, browser, "imported.json")

    @staticmethod
    def meta_path(browser):
        return os.path.join(DATA_DIR, browser, "browser.json")

    # loading and saving
    def _load_profiles(self, browser):
        try:
            with open(self.profiles_path(browser), "r", encoding="utf-8") as f:
                return clean_profiles(json.load(f).get("profiles", []))
        except FileNotFoundError:
            return None
        except Exception:
            log.exception("Could not read imported.json of %s", browser)
            return None

    def _save_profiles(self, browser, profiles):
        """imported.json is only created once the browser has at least one profile."""
        path = self.profiles_path(browser)
        if not profiles and not os.path.isfile(path):
            return
        write_json_atomic(path, {"profiles": clean_profiles(profiles)})

    def _load_db(self):
        try:
            with open(DB_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            return []
        except Exception:
            log.exception("launcher.json is unreadable; keeping a backup copy")
            try:
                shutil.copy2(DB_PATH, DB_PATH + ".bad-%d" % int(time.time()))
            except Exception:
                pass
            return []
        if not isinstance(data, dict):
            return []
        out = []
        for b in data.get("browsers", []):
            if not (isinstance(b, dict) and b.get("name") and b.get("exe")):
                continue
            out.append({"name": b["name"], "exe": b["exe"], "data_dir": self._data_dir_of(b["name"]),
                        "profiles": self._load_profiles(b["name"]) or []})
        return out

    def _save_db(self):
        write_json_atomic(DB_PATH, {"browsers": [{"name": b["name"], "exe": b["exe"]} for b in self.db]})

    def _load_stats(self):
        """Returns (total launches, per-profile usage {browser: {profile: {"n": count, "last": time}}})."""
        try:
            with open(STATS_PATH, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except FileNotFoundError:
            return 0, {}
        except Exception:
            log.exception("stats.json is unreadable")
            return 0, {}
        try:
            launches = max(0, int(raw.get("launches", 0)))
        except Exception:
            launches = 0
        usage = {}
        raw_usage = raw.get("usage")
        if isinstance(raw_usage, dict):
            for browser, profiles in raw_usage.items():
                if not isinstance(profiles, dict):
                    continue
                for profile, v in profiles.items():
                    try:
                        usage.setdefault(browser, {})[profile] = {"n": max(0, int(v.get("n", 0))),
                                                                  "last": float(v.get("last", 0))}
                    except Exception:
                        continue
        return launches, usage

    def _save_stats(self):
        write_json_atomic(STATS_PATH, {"launches": self.launches, "usage": self.usage})

    # lookups
    def _browser(self, name):
        for b in self.db:
            if b["name"] == name:
                return b
        raise UserError("That browser no longer exists.")

    def _profile(self, browser, key):
        for p in browser["profiles"]:
            if p["key"] == key:
                return p
        raise UserError("That profile no longer exists.")

    def _read_meta(self, browser):
        try:
            with open(self.meta_path(browser), "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except FileNotFoundError:
            return {}
        except Exception:
            log.exception("Could not read browser.json of %s", browser)
            return {}

    def _write_meta(self, browser, **fields):
        meta = self._read_meta(browser)
        meta.update(fields)
        write_json_atomic(self.meta_path(browser), meta)

    def _data_dir_of(self, browser):
        value = self._read_meta(browser).get("data_dir")
        return value if isinstance(value, str) else ""

    def _remember_data_dir(self, browser, folder):
        """Keeps the folder a reader found in browser.json, so the next read is instant."""
        if not folder:
            return
        try:
            for b in self.db:
                if b["name"] == browser and b.get("data_dir") != folder:
                    b["data_dir"] = folder
                    self._write_meta(browser, data_dir=folder)
        except Exception:
            log.exception("Could not remember the data folder of %s", browser)

    def _reader_record(self, b):
        return {"name": b["name"], "exe": b["exe"], "data_dir": b.get("data_dir", "")}

    def state(self):
        with self.lock:
            browsers, total = [], 0
            for b in self.db:
                profiles = []
                used = self.usage.get(b["name"], {})
                gone = not os.path.isfile(b["exe"])             # the browser itself was moved or uninstalled
                lost = self.missing.get(b["name"], set())       # profiles the browser no longer has
                for p in b["profiles"]:
                    use = used.get(p["key"], {})
                    profiles.append({"key": p["key"], "name": p["name"], "source_name": p["source_name"],
                                     "renamed": p["renamed"], "color": p["color"], "args": list(p["args"]),
                                     "avatar_custom": p["avatar_custom"], "locked": p["key"] == DEFAULT_KEY,
                                     "avatar_url": file_url(os.path.join(self.pfolder(b["name"], p["key"]),
                                                                         "avatar.png")),
                                     "uses": int(use.get("n", 0)), "last": float(use.get("last", 0)),
                                     "dead": gone or p["key"] in lost})
                total += len(profiles)
                kind = browser_kind(b["name"], b["exe"])
                browsers.append({"name": b["name"],
                                 "icon_url": file_url(os.path.join(self.folder(b["name"]), "icon.png")),
                                 "has_default": any(p["key"] == DEFAULT_KEY for p in b["profiles"]),
                                 "supported": kind not in UNSUPPORTED_KINDS,
                                 "unsupported_text": unsupported_text(kind) if kind in UNSUPPORTED_KINDS else "",
                                 "profiles": profiles})
            return {"browsers": browsers,
                    "stats": {"browsers": len(browsers), "profiles": total, "launches": self.launches}}

    # browsers
    def scan_browsers(self):
        """The browsers on this PC that are not in the launcher yet: {"browsers": [{"id", "name", "icon"}],
        "added_count": how many found browsers are already in it}. Remembered for add_browsers."""
        found = find_installed_browsers()               # outside the lock: the registry and the icons take a moment
        with self.lock:
            have_exe = {os.path.normcase(b["exe"]) for b in self.db}
            have_name = {b["name"].lower() for b in self.db}
            self._scan = {}
            self._listed = set()
            out, added_count = [], 0
            for f in found:
                self._scan[f["id"]] = f
                if os.path.normcase(f["exe"]) in have_exe or f["name"].lower() in have_name:
                    added_count += 1
                    continue
                self._listed.add(f["id"])
                out.append({"id": f["id"], "name": f["name"], "icon": f["icon"]})
            return {"browsers": out, "added_count": added_count}

    def inspect_browser(self, path):
        """A program file picked by hand (Add Manually): {"id", "name", "icon", "existing"}.
        existing is true when the popup already lists that browser. A new one is remembered for add_browsers."""
        path = clean_path(path)
        if not path or not path.lower().endswith(".exe") or not os.path.isfile(path):
            raise UserError("Pick a browser's .exe file.")
        exe = os.path.normpath(path)
        key = os.path.normcase(exe)
        ident = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
        with self.lock:
            if any(os.path.normcase(b["exe"]) == key for b in self.db):
                raise UserError("That browser is already in Beyonder.")
            if ident in self._listed and ident in self._scan:
                f = self._scan[ident]
                return {"id": f["id"], "name": f["name"], "icon": f["icon"], "existing": True}
        name = guess_browser_name(exe)                  # outside the lock: reads the file's version info
        with self.lock:
            taken = {b["name"].lower() for b in self.db} | {f["name"].lower() for f in self._scan.values()}
            unique, n = name, 2
            while unique.lower() in taken:
                unique = "%s (%d)" % (name, n)
                n += 1
            try:
                icon = icon_data_url(unique, exe)
            except Exception:
                log.exception("Could not make the picture for %s", unique)
                icon = None
            self._scan[ident] = {"id": ident, "name": unique, "exe": exe, "icon": icon}
            self._listed.add(ident)
            return {"id": ident, "name": unique, "icon": icon, "existing": False}

    def add_browsers(self, ids):
        """Adds the chosen browsers from the last scan. Returns their names, in the order they were added."""
        with self.lock:
            picked, seen = [], set()
            for i in ids or []:
                if i in seen:
                    continue
                f = self._scan.get(i)
                if f is None:
                    raise UserError("This list is out of date. Close the window and open it again.")
                seen.add(i)
                picked.append(f)
            if not picked:
                raise UserError("Pick at least one browser.")
            added, problem = [], None
            for f in picked:
                name, exe = f["name"], f["exe"]
                if any(b["name"].lower() == name.lower() or os.path.normcase(b["exe"]) == os.path.normcase(exe)
                       for b in self.db):
                    continue                            # already in the launcher
                if not os.path.isfile(exe):
                    problem = problem or '"%s" was moved or uninstalled.' % name
                    continue
                try:
                    os.makedirs(self.folder(name), exist_ok=True)
                    icon = browser_icon_image(name, exe)
                    if icon is not None:
                        icon.save(os.path.join(self.folder(name), "icon.png"))
                    self._write_meta(name, exe=exe)
                except OSError as ex:
                    problem = problem or "Couldn't create the folder for \"%s\": %s" % (name, ex.strerror)
                    continue
                except Exception:
                    log.exception("Could not save the icon of %s", name)
                    problem = problem or "Couldn't save the icon of \"%s\"." % name
                    continue
                profiles = self._load_profiles(name) or []      # a removed browser added again gets its profiles back
                if not any(p["key"] == DEFAULT_KEY for p in profiles):
                    profiles.insert(0, self._make_default_profile(name, icon))
                    try:
                        self._save_profiles(name, profiles)
                    except OSError as ex:
                        problem = problem or "Couldn't save the profiles of \"%s\": %s" % (name, ex.strerror)
                self.db.append({"name": name, "exe": exe, "data_dir": self._data_dir_of(name), "profiles": profiles})
                added.append(name)
            if added:
                self._save_db()
            elif problem:
                raise UserError(problem)
        for name in added:                              # find the profile folder now, so the first Add Profiles click is quick
            threading.Thread(target=self._locate_in_background, args=(name,), daemon=True).start()
        return added

    def _locate_in_background(self, name):
        """Looks for a new browser's profile folder (the whole program folder is searched) and remembers it. Never raises."""
        try:
            with self.lock:
                rec = self._reader_record(self._browser(name))
            kind = browser_kind(rec["name"], rec["exe"])
            if kind in UNSUPPORTED_KINDS:
                return
            folder = locate_data_dir(kind, rec["name"], rec["exe"], rec["data_dir"])
            if folder:
                with self.lock:
                    self._remember_data_dir(name, folder)
        except Exception:
            log.exception("Looking for the profile folder of %s failed", name)

    # the Default profile: it only starts the browser, exactly like Open
    def _make_default_profile(self, name, icon):
        """Writes the browser's icon as the Default profile's picture. Returns the profile record."""
        folder = self.pfolder(name, DEFAULT_KEY)
        try:
            os.makedirs(folder, exist_ok=True)
            if icon is not None:
                write_avatar_file(folder, avatar_png_bytes(icon))
            else:
                remove_avatar_file(folder)
        except Exception:
            log.exception("Could not save the picture of the Default profile of %s", name)
        return {"key": DEFAULT_KEY, "name": DEFAULT_NAME, "source_name": DEFAULT_NAME, "renamed": False, "color": "",
                "args": [], "avatar_custom": False}

    def _browser_icon(self, name, exe):
        """The browser's icon: the saved copy in its folder, or read again from its program file."""
        icon = load_picture_file(os.path.join(self.folder(name), "icon.png"))
        return icon if icon is not None else browser_icon_image(name, exe)

    def add_default_profile(self, name):
        """Adds the Default profile back (right-click menu of the browser). Nothing happens when it is there already."""
        with self.lock:
            b = self._browser(name)
            exe = b["exe"]
            if any(p["key"] == DEFAULT_KEY for p in b["profiles"]):
                return
        icon = self._browser_icon(name, exe)            # outside the lock: may read the program file
        with self.lock:
            b = self._browser(name)
            if any(p["key"] == DEFAULT_KEY for p in b["profiles"]):
                return
            b["profiles"].insert(0, self._make_default_profile(name, icon))
            self._save_profiles(name, b["profiles"])

    def remove_browser(self, name):
        with self.lock:
            d = self._browser(name)
            self.db = [b for b in self.db if b is not d]        # the folder stays
            self._save_db()

    # profiles
    def remove_profile(self, browser, key):
        with self.lock:
            b = self._browser(browser)
            d = self._profile(b, key)
            b["profiles"] = [p for p in b["profiles"] if p is not d]    # the folder stays
            self._save_profiles(browser, b["profiles"])
            self._note_removed_profile(browser, d)

    def reload(self):
        """Reads everything from disk again (after a backup was restored)."""
        with self.lock:
            self.db = self._load_db()
            self.launches, self.usage = self._load_stats()
            self._scan = {}
            self._listed = set()
            self._profile_scan = {}
            self.missing = {}

    def reorder_browsers(self, names):
        with self.lock:
            by_name = {b["name"]: b for b in self.db}
            ordered, seen = [], set()
            for n in names or []:
                if n in by_name and n not in seen:
                    ordered.append(by_name[n])
                    seen.add(n)
            self.db = ordered + [b for b in self.db if b["name"] not in seen]
            self._save_db()

    def reorder_profiles(self, browser, keys):
        with self.lock:
            b = self._browser(browser)
            by_key = {p["key"]: p for p in b["profiles"]}
            ordered, seen = [], set()
            for k in keys or []:
                if k in by_key and k not in seen:
                    ordered.append(by_key[k])
                    seen.add(k)
            b["profiles"] = ordered + [p for p in b["profiles"] if p["key"] not in seen]
            self._save_profiles(browser, b["profiles"])

    def recent_profiles(self, limit=5):
        """The most recently launched profiles that are still listed: [(browser, key, name), ...]."""
        with self.lock:
            found = []
            for b in self.db:
                used = self.usage.get(b["name"], {})
                for p in b["profiles"]:
                    last = used.get(p["key"], {}).get("last", 0)
                    if last > 0:
                        found.append((last, b["name"], p["key"], p["name"]))
            found.sort(reverse=True)
            return [(b, k, n) for _, b, k, n in found[:limit]]

    # importing profiles from the browsers (Add Profiles popup)
    def profile_support(self, name):
        """Whether a browser has a profile system at all. Browsers of UNSUPPORTED_KINDS (Opera, Tor Browser...) never do."""
        with self.lock:
            b = self._browser(name)
            kind = browser_kind(b["name"], b["exe"])
            if kind in UNSUPPORTED_KINDS:
                return {"supported": False, "text": unsupported_text(kind)}
            return {"supported": True, "text": ""}

    @staticmethod
    def _rows(profiles, imported):
        """Profiles as the popup lists them (small pictures, and whether they are in Beyonder already)."""
        rows = []
        for p in profiles:
            pic = thumb_data_url(p["picture"]) if p.get("picture") is not None else None
            rows.append({"key": p["key"], "name": p["name"], "label": p["label"], "color": p.get("color") or "",
                         "picture": pic, "imported": p["key"] in imported})
        return rows

    def list_browser_profiles(self, name):
        with self.lock:
            b = self._browser(name)
            rec = self._reader_record(b)
            imported = {p["key"] for p in b["profiles"]}
        res = read_profiles(rec)                        # disk reads happen outside the lock (and may wait for the folder search)
        if not res["supported"]:
            return {"supported": False, "profiles": [], "unsupported_text": res["unsupported_text"]}
        if not res["ok"]:
            raise UserError(READ_FAILED_TEXT)
        with self.lock:
            self._remember_data_dir(name, res["data_dir"])
            self._profile_scan[name] = {p["key"]: p for p in res["profiles"]}
        return {"supported": True, "profiles": self._rows(res["profiles"], imported), "unsupported_text": ""}

    def add_profiles(self, name, keys):
        """Imports the chosen profiles: a folder with the picture, and a record linking to the browser's profile."""
        keys = [k for k in dict.fromkeys(keys or []) if isinstance(k, str) and k]
        if not keys:
            raise UserError("Pick at least one profile.")
        with self.lock:
            b = self._browser(name)
            rec = self._reader_record(b)
            scan = self._profile_scan.get(name)
        if scan is None:                                # the list was not read in this session: read it again
            res = read_profiles(rec)
            if not res["supported"]:
                raise UserError(res["unsupported_text"])
            if not res["ok"]:
                raise UserError(READ_FAILED_TEXT)
            scan = {p["key"]: p for p in res["profiles"]}
            with self.lock:
                self._remember_data_dir(name, res["data_dir"])
                self._profile_scan[name] = scan
        with self.lock:
            b = self._browser(name)
            have = {p["key"] for p in b["profiles"]}
            for k in keys:
                if k not in scan:
                    raise UserError("This list is out of date. Close the window and open it again.")
            fresh, added = [], []
            for k in keys:
                if k in have:
                    continue
                src = scan[k]
                folder = self.pfolder(name, k)
                try:
                    os.makedirs(folder, exist_ok=True)
                except OSError as ex:
                    raise UserError("Couldn't create the folder for \"%s\": %s" % (src["name"], ex.strerror))
                try:
                    if src.get("picture") is not None:
                        write_avatar_file(folder, avatar_png_bytes(src["picture"]))
                    else:
                        remove_avatar_file(folder)      # a picture left behind by an older version
                except Exception:
                    log.exception("Could not save the picture of %s", src["name"])
                fresh.append({"key": k, "name": src["name"], "source_name": src["name"], "renamed": False,
                              "color": clean_color(src.get("color")), "args": list(src.get("args") or []),
                              "avatar_custom": False})
                added.append(k)
            if fresh:
                b["profiles"].extend(fresh)
                self._save_profiles(name, b["profiles"])
                lost = self.missing.get(name)
                if lost:
                    lost.difference_update(added)
            return added

    # editing a profile: only Beyonder's own copy changes, never the browser's data
    def edit_profile(self, browser, key, name, picture):
        locked = key == DEFAULT_KEY                     # the Default profile keeps its name; only its picture can change
        if locked:
            name = DEFAULT_NAME
        else:
            name = clean_text(name)
            if not name:
                raise UserError("Give the profile a name.")
            if len(name) > MAX_NAME:
                raise UserError("That name is too long (%d characters at most)." % MAX_NAME)
        data, reset, source = None, False, None
        if picture == "reset":
            reset = True
        elif picture is not None:
            data = avatar_png_bytes(decode_picture_data_url(picture))
        with self.lock:
            b = self._browser(browser)
            self._profile(b, key)
            rec = self._reader_record(b)
        if reset and locked:                            # the browser's own icon
            source = {"picture": self._browser_icon(rec["name"], rec["exe"]), "color": ""}
        elif reset:                                     # the browser's own picture, read again
            res = read_profiles(rec)
            if res["supported"] and res["ok"]:
                for x in res["profiles"]:
                    if x["key"] == key:
                        source = x
            if source is None:
                raise UserError("Beyonder can't find this profile in the browser, so its picture can't be reset.")
        with self.lock:
            b = self._browser(browser)
            p = self._profile(b, key)
            folder = self.pfolder(browser, key)
            try:
                if data is not None:
                    write_avatar_file(folder, data)
                    p["avatar_custom"] = True
                elif reset:
                    if source.get("picture") is not None:
                        write_avatar_file(folder, avatar_png_bytes(source["picture"]))
                    else:
                        remove_avatar_file(folder)
                    p["avatar_custom"] = False
                    p["color"] = clean_color(source.get("color"))
            except OSError as ex:
                raise UserError("Couldn't save the picture: %s" % ex.strerror)
            p["name"] = name
            p["renamed"] = name != p["source_name"]
            self._save_profiles(browser, b["profiles"])

    # the sync with the browsers, once per launch
    def sync_with_browsers(self):
        """Compares every imported profile with what its browser says now. Returns True when something changed."""
        with self.lock:
            records = [self._reader_record(b) for b in self.db]
        changed = False
        for rec in records:
            try:
                if self._sync_browser(rec):
                    changed = True
            except Exception:
                log.exception("Syncing %s failed", rec["name"])
        return changed

    def _sync_browser(self, rec):
        name, exe = rec["name"], rec["exe"]
        changed = False
        if not os.path.isfile(exe):                     # moved or reinstalled: look for the same browser again
            found = None
            try:
                for f in find_installed_browsers():
                    if f["name"].lower() == name.lower() and os.path.isfile(f["exe"]):
                        found = f["exe"]
                        break
            except Exception:
                log.exception("Could not look for %s again", name)
            if found and os.path.normcase(found) != os.path.normcase(exe):
                with self.lock:
                    for b in self.db:
                        if b["name"] == name:
                            b["exe"] = found
                    self._save_db()
                    try:
                        self._write_meta(name, exe=found)
                    except Exception:
                        log.exception("Could not save the new location of %s", name)
                exe = rec["exe"] = found
                changed = True
        with self.lock:
            current = next((b for b in self.db if b["name"] == name), None)
            if current is None or not any(p["key"] != DEFAULT_KEY for p in current["profiles"]):
                return changed                          # nothing imported (the Default profile is not in the browser): nothing to keep in step
        res = read_profiles(rec)
        if not res["supported"] or not res["ok"] or not res["located"]:
            return changed                              # could not read it, or its data folder was not found: cannot tell, change nothing
        by_key = {p["key"]: p for p in res["profiles"]}
        with self.lock:
            b = next((x for x in self.db if x["name"] == name), None)
            if b is None:
                return changed
            self._remember_data_dir(name, res["data_dir"])
            lost = self.missing.setdefault(name, set())
            dirty = False
            for p in b["profiles"]:
                if p["key"] == DEFAULT_KEY:
                    continue                            # the Default profile is Beyonder's own: it only starts the browser
                src = by_key.get(p["key"])
                if src is None:
                    if p["key"] not in lost:
                        lost.add(p["key"])
                        changed = True
                    continue
                if p["key"] in lost:
                    lost.discard(p["key"])
                    changed = True
                if p["source_name"] != src["name"]:
                    p["source_name"] = src["name"]
                    dirty = True
                if not p["renamed"] and p["name"] != src["name"]:
                    p["name"] = src["name"]
                    dirty = True
                color = clean_color(src.get("color"))
                if p["color"] != color:
                    p["color"] = color
                    dirty = True
                if list(src.get("args") or []) != p["args"]:
                    p["args"] = list(src.get("args") or [])
                    dirty = True
                if not p["avatar_custom"] and src.get("picture") is not None:
                    try:
                        if write_avatar_file(self.pfolder(name, p["key"]), avatar_png_bytes(src["picture"])):
                            changed = True
                    except Exception:
                        log.exception("Could not refresh the picture of %s", p["name"])
            if dirty:
                self._save_profiles(name, b["profiles"])
                changed = True
        return changed

    # removed items (Remove keeps their folders, so they can come back)
    def _note_removed_profile(self, browser, profile):
        """Remove keeps the profile's folder; the whole record is written into it so Restore brings everything back."""
        try:
            folder = self.pfolder(browser, profile["key"])
            os.makedirs(folder, exist_ok=True)
            write_json_atomic(os.path.join(folder, "profile.json"), dict(profile))
        except Exception:
            log.exception("Could not note the details of a removed profile")

    @staticmethod
    def _removed_profile_data(folder):
        try:
            with open(os.path.join(folder, "profile.json"), "r", encoding="utf-8") as f:
                data = json.load(f)
            items = clean_profiles([data])
            return items[0] if items else None
        except Exception:
            return None

    def _removed_exe(self, name):
        exe = self._read_meta(name).get("exe", "")
        return exe if isinstance(exe, str) else ""

    def list_removed(self):
        """Browsers and profiles that were removed (their folders are still on disk)."""
        with self.lock:
            active = {b["name"].lower() for b in self.db}
            browsers, profiles = [], []
            try:
                names = sorted(os.listdir(DATA_DIR), key=str.lower)
            except OSError:
                names = []
            for name in names:
                folder = os.path.join(DATA_DIR, name)
                if name.lower() in active or not os.path.isdir(folder) or not self._removed_exe(name):
                    continue
                browsers.append({"name": name, "icon_url": file_url(os.path.join(folder, "icon.png")),
                                 "profiles": len(self._load_profiles(name) or [])})
            for b in self.db:
                have = {p["key"] for p in b["profiles"]}
                try:
                    kids = sorted(os.listdir(self.folder(b["name"])), key=str.lower)
                except OSError:
                    continue
                for kid in kids:
                    folder = os.path.join(self.folder(b["name"]), kid)
                    if not os.path.isdir(folder):
                        continue
                    data = self._removed_profile_data(folder)
                    if data is None or data["key"] in have or safe_key(data["key"]).lower() != kid.lower():
                        continue
                    profiles.append({"browser": b["name"], "key": data["key"], "name": data["name"], "data": data,
                                     "avatar_url": file_url(os.path.join(folder, "avatar.png"))})
            return {"browsers": browsers, "profiles": profiles}

    def restore_browser(self, name, index):
        """Undo of Remove: the folder (icon, profiles) was kept, so the browser only has to be listed again."""
        with self.lock:
            name = clean_text(name)
            if any(b["name"] == name for b in self.db):
                raise UserError('A browser named "%s" already exists.' % name)
            exe = self._removed_exe(name)
            if not exe:
                raise UserError("That browser's folder is gone, so it can't be restored.")
            profiles = self._load_profiles(name) or []
            try:
                index = max(0, min(int(index), len(self.db)))
            except (TypeError, ValueError):
                index = len(self.db)
            self.db.insert(index, {"name": name, "exe": exe, "data_dir": self._data_dir_of(name), "profiles": profiles})
            self._save_db()

    def restore_profile(self, browser, key, data, index):
        """Undo of Remove: puts the profile back at its old position with all its fields (its folder and picture were kept)."""
        with self.lock:
            b = self._browser(browser)
            key = clean_text(key)
            if any(p["key"] == key for p in b["profiles"]):
                raise UserError("That profile is already in the list.")
            record = dict(data) if isinstance(data, dict) else {}
            record["key"] = key
            item = clean_profiles([record])
            if not item:
                raise UserError("That profile can't be restored.")
            try:
                index = max(0, min(int(index), len(b["profiles"])))
            except (TypeError, ValueError):
                index = len(b["profiles"])
            b["profiles"].insert(index, item[0])
            self._save_profiles(browser, b["profiles"])

    def dead_links(self):
        """[[browser, key], ...] whose browser program no longer exists, or that the browser no longer has."""
        with self.lock:
            items = [(b["name"], b["exe"], [p["key"] for p in b["profiles"]], set(self.missing.get(b["name"], ())))
                     for b in self.db]
        dead = []
        for browser, exe, keys, lost in items:          # file checks happen outside the lock (a network path can be slow)
            gone = not os.path.isfile(exe)
            dead.extend([browser, k] for k in keys if gone or k in lost)
        return dead

    def open_browser(self, name):
        """Starts the browser with no arguments. Launch statistics do not change. Returns True when it started."""
        with self.lock:
            exe = self._browser(name)["exe"]
        return spawn_browser(exe, [])

    def launch(self, browser, key):
        """Starts the browser with the profile's arguments. Returns the new launch count, or None when it can't start."""
        with self.lock:
            b = self._browser(browser)
            p = self._profile(b, key)
            if key in self.missing.get(browser, ()):
                raise UserError("This profile no longer exists in the browser.")
            exe, args = b["exe"], [str(a) for a in (p.get("args") or [])]
        if not spawn_browser(exe, args):
            return None
        with self.lock:
            self.launches += 1
            use = self.usage.setdefault(browser, {}).setdefault(key, {"n": 0, "last": 0.0})
            use["n"] += 1
            use["last"] = time.time()
            try:
                self._save_stats()
            except Exception:
                log.exception("Could not save stats.json")
            return self.launches


# ───────────────────────────── the JS API ─────────────────────────────
class Shell:
    """Tray icon, hide to tray, quit, start with Windows and the live Windows theme."""

    def __init__(self, chrome, settings):
        self.chrome = chrome
        self.settings = settings
        self.window = None
        self.icon = None
        self.tray_ok = False
        self.quitting = False
        self.store = None                       # set by main(); the tray menu lists recent profiles from it
        self.hotkey = Hotkey(self.hotkey_pressed)
        self.hotkey_status = "off"              # off, ok, in_use or error

    def show(self):
        self.chrome.show()

    def request_close(self):
        """The window's Cross button: hide to the tray, or really quit (setting, or no tray icon)."""
        if self.tray_ok and self.settings.get("close_action") != "quit":
            self.chrome.hide()
        else:
            self.quit()

    def on_closing(self, *_args):
        """Alt+F4 and taskbar Close also only hide the window, except when Windows is shutting down."""
        if self.quitting:
            return True
        try:
            if user32.GetSystemMetrics(0x2000):     # SM_SHUTTINGDOWN
                return True
        except Exception:
            pass
        if self.tray_ok and self.settings.get("close_action") != "quit":
            self.chrome.hide()
            return False
        return True

    def refresh_tray(self):
        """Redraws the tray menu (e.g. after Start with Windows was changed in Settings)."""
        try:
            if self.icon is not None:
                self.icon.update_menu()
        except Exception:
            pass

    def quit(self):
        self.quitting = True
        self.stop_tray()
        try:
            if self.window is not None:
                self.window.destroy()
                return
        except Exception:
            log.exception("destroy failed")
        os._exit(0)

    def push_theme(self, resolved):
        try:
            if self.window is not None:
                self.window.evaluate_js("window.__bydSystemTheme && window.__bydSystemTheme(%s)" % json.dumps(resolved))
        except Exception:
            pass

    def _tray_image(self):
        try:
            if os.path.isfile(ICON_PATH):
                im = load_image_file(ICON_PATH)
                im.thumbnail((64, 64), Image.LANCZOS)
                return im
        except Exception:
            log.exception("Could not load the tray icon image")
        from PIL import ImageDraw
        im = Image.new("RGBA", (64, 64), (0, 0, 0, 255))
        ImageDraw.Draw(im).rectangle((8, 8, 55, 55), outline=(255, 255, 255, 255), width=4)
        return im

    def _toggle_autostart(self, icon, item):
        on = not self.settings.get("autostart")
        self.settings.set("autostart", on)
        set_autostart(on)
        try:
            icon.update_menu()
        except Exception:
            pass

    @staticmethod
    def _tray_label(browser, profile):
        text = "%s \u203a %s" % (browser, profile)
        if len(text) > 60:
            text = text[:57] + "..."
        return text.replace("&", "&&")

    def _tray_launcher(self, browser, key, name):
        def run(icon, item):
            threading.Thread(target=self.launch_from_tray, args=(browser, key, name), daemon=True).start()
        return run

    def _tray_items(self):
        """Rebuilt by pystray every time the menu is updated, so Recent always follows the latest launches."""
        import pystray
        yield pystray.MenuItem("Open Beyonder", lambda icon, item: self.show(), default=True)
        yield pystray.Menu.SEPARATOR
        recents = []
        try:
            if self.store is not None:
                recents = self.store.recent_profiles(5)
        except Exception:
            log.exception("Could not read the recent profiles")
        if recents:
            for browser, key, name in recents:
                yield pystray.MenuItem(self._tray_label(browser, name), self._tray_launcher(browser, key, name))
        else:
            yield pystray.MenuItem("No recent profiles", lambda icon, item: None, enabled=False)
        yield pystray.Menu.SEPARATOR
        yield pystray.MenuItem("Start with Windows", self._toggle_autostart,
                               checked=lambda item: bool(self.settings.get("autostart")))
        yield pystray.MenuItem("Quit Beyonder", lambda icon, item: self.quit())

    def launch_from_tray(self, browser, key, name):
        count, problem = None, None
        try:
            count = self.store.launch(browser, key)
        except UserError as ex:
            problem = str(ex)
        except Exception:
            log.exception("Launch from the tray failed")
        if count is None:
            try:
                if self.icon is not None:
                    self.icon.notify(problem or '"%s" could not be opened. Its browser was moved or uninstalled.' % name,
                                     APP_TITLE)
            except Exception:
                pass
        self.refresh_tray()
        self.push_refresh()

    def push_refresh(self):
        """Asks the page to reload its data (after something changed behind its back, like a tray launch)."""
        try:
            if self.window is not None:
                self.window.evaluate_js("window.__bydRefresh && window.__bydRefresh()")
        except Exception:
            pass

    def apply_hotkey(self, enabled=None, keys=None):
        """Registers or removes the global shortcut from the saved settings (or the given values).
        Returns None, or a sentence the person can read."""
        if enabled is None:
            enabled = bool(self.settings.get("hotkey_enabled"))
        parsed = parse_hotkey(keys if keys is not None else self.settings.get("hotkey"))
        if not enabled or parsed is None:
            self.hotkey.apply(0, None)
            self.hotkey_status = "off"
            return None
        result = self.hotkey.apply(parsed[1], parsed[2])
        if result is None:
            self.hotkey_status = "ok"
            return None
        self.hotkey_status = "in_use" if result == "already" else "error"
        log.warning("Could not register the hotkey %s (%s)", parsed[0], result)
        if result == "already":
            return "That shortcut is already used by another app. Pick other keys."
        return "Windows would not register that shortcut."

    def hotkey_pressed(self):
        """Shows Beyonder, or hides it again when it is already in front."""
        hwnd = self.chrome.find_hwnd()
        front = False
        try:
            front = bool(hwnd) and bool(user32.IsWindowVisible(hwnd)) and not user32.IsIconic(hwnd) \
                and user32.GetForegroundWindow() == hwnd
        except Exception:
            front = False
        if front:
            if self.tray_ok:
                self.chrome.hide()
            else:
                self.chrome.minimize()
        else:
            self.chrome.show()

    def start_tray(self):
        try:
            import pystray
            menu = pystray.Menu(self._tray_items)
            self.icon = pystray.Icon("Beyonder", self._tray_image(), APP_TITLE, menu)
            self.icon.run_detached()
            self.tray_ok = True
        except Exception:
            self.tray_ok = False
            log.exception("The tray icon could not start; the Cross button will quit the app instead")

    def stop_tray(self):
        try:
            if self.icon is not None:
                self.icon.stop()
        except Exception:
            pass
        self.icon = None

    def watch_system_theme(self):
        def loop():
            last = system_theme()
            while not self.quitting:
                time.sleep(1.5)
                try:
                    cur = system_theme()
                    if cur != last:
                        last = cur
                        if self.settings.get("theme") == "system":
                            self.push_theme(cur)
                except Exception:
                    pass
        threading.Thread(target=loop, daemon=True).start()


def guarded(fn):
    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        try:
            return fn(self, *args, **kwargs)
        except UserError as ex:
            return {"ok": False, "error": str(ex)}
        except Exception as ex:
            log.exception("API call %s failed", fn.__name__)
            return {"ok": False, "internal": True, "error": "Python error in %s: %s" % (fn.__name__, ex)}
    return wrapper


class Api:
    """Everything the page can call. Names starting with an underscore stay private."""

    def __init__(self, store, chrome, shell, settings):
        self._store = store
        self._chrome = chrome
        self._shell = shell
        self._settings = settings
        self._window = None

    def _state_result(self):
        self._shell.refresh_tray()          # a change may have touched the recent profiles in the tray menu
        return {"ok": True, "state": self._store.state()}

    def _report(self, message):
        try:
            if self._window is not None:
                self._window.evaluate_js("window.__bydError && window.__bydError(%s)" % json.dumps(message))
        except Exception:
            pass

    # settings and theme
    def _settings_payload(self):
        s = self._settings
        return {"ok": True, "theme": s.get("theme"), "resolved": s.resolved_theme(),
                "autostart": bool(s.get("autostart")),
                "minimize_after_launch": bool(s.get("minimize_after_launch")),
                "close_action": s.get("close_action"), "sort": s.get("sort"),
                "hotkey_enabled": bool(s.get("hotkey_enabled")), "hotkey": s.get("hotkey"),
                "hotkey_status": self._shell.hotkey_status}

    @guarded
    def get_settings(self):
        return self._settings_payload()

    @guarded
    def set_setting(self, key, value):
        allowed = SETTING_CHOICES.get(key)
        if allowed is None or value not in allowed or type(value) is not type(allowed[0]):
            raise UserError("Unknown setting.")
        if key == "autostart" and not set_autostart(bool(value)):
            raise UserError("Couldn't update the Windows startup entry.")
        if key == "hotkey_enabled":
            problem = self._shell.apply_hotkey(enabled=bool(value))
            if problem:
                raise UserError(problem)
        self._settings.set(key, value)
        if key == "autostart":
            self._shell.refresh_tray()
        return self._settings_payload()

    @guarded
    def set_hotkey(self, keys):
        parsed = parse_hotkey(keys)
        if parsed is None:
            raise UserError("Use Ctrl, Alt or Win together with a letter, a number or an F key.")
        if self._settings.get("hotkey_enabled"):
            problem = self._shell.apply_hotkey(keys=parsed[0])
            if problem:
                self._shell.apply_hotkey()          # put the previous shortcut back
                raise UserError(problem)
        self._settings.set("hotkey", parsed[0])
        return self._settings_payload()

    @guarded
    def set_theme(self, mode):
        if mode not in ("light", "dark", "system"):
            raise UserError("Unknown theme.")
        self._settings.set("theme", mode)
        return {"ok": True, "theme": mode, "resolved": self._settings.resolved_theme()}

    # state
    @guarded
    def get_state(self):
        return self._state_result()

    # browsers
    @guarded
    def scan_browsers(self):
        res = self._store.scan_browsers()
        return {"ok": True, "browsers": res["browsers"], "added_count": res["added_count"]}

    @guarded
    def inspect_browser(self, path):
        res = self._store.inspect_browser(path)
        res["ok"] = True
        return res

    @guarded
    def add_browsers(self, ids):
        added = self._store.add_browsers(ids)
        out = self._state_result()
        out["added"] = added
        return out

    @guarded
    def remove_browser(self, name):
        self._store.remove_browser(name)
        return self._state_result()

    # profiles
    @guarded
    def remove_profile(self, browser, key):
        self._store.remove_profile(browser, key)
        return self._state_result()

    @guarded
    def launch_profile(self, browser, key):
        count = self._store.launch(browser, key)
        if count is None:
            return {"ok": False, "notice": {
                "title": "Couldn't open it",
                "text": "That browser was moved or uninstalled, so this profile cannot be opened."}}
        if self._settings.get("minimize_after_launch"):
            try:
                self._chrome.minimize()     # out of the way, only its icon stays in the taskbar
            except Exception:
                log.exception("Minimize after launch failed")
        self._shell.refresh_tray()          # the launched profile is now the newest entry under Recent
        return {"ok": True, "stats": self._store.state()["stats"]}

    @guarded
    def reorder_browsers(self, names):
        self._store.reorder_browsers(names)
        return {"ok": True}

    @guarded
    def reorder_profiles(self, browser, keys):
        self._store.reorder_profiles(browser, keys)
        return {"ok": True}

    @guarded
    def list_removed(self):
        out = self._store.list_removed()
        out["ok"] = True
        return out

    @guarded
    def export_backup(self):
        import webview
        dialog = getattr(getattr(webview, "FileDialog", None), "SAVE", None)
        if dialog is None:
            dialog = webview.SAVE_DIALOG
        name = "Beyonder-backup-%s.zip" % time.strftime("%Y-%m-%d")
        result = self._window.create_file_dialog(dialog, save_filename=name, file_types=("Backups (*.zip)",))
        if isinstance(result, (list, tuple)):
            result = result[0] if result else None
        if not result:
            return {"ok": True, "cancelled": True}
        dest = os.path.normpath(result)
        if not dest.lower().endswith(".zip"):
            dest += ".zip"
        with self._store.lock:
            count = make_backup(dest)
        return {"ok": True, "path": dest, "files": count}

    @guarded
    def restore_backup(self, path):
        with self._store.lock:
            safety = restore_from_zip(path)
            self._store.reload()
        self._settings.reload()
        set_autostart(bool(self._settings.get("autostart")))
        self._shell.apply_hotkey()
        out = self._state_result()
        out["settings"] = self._settings_payload()
        out["safety"] = safety
        return out

    @guarded
    def check_links(self):
        return {"ok": True, "dead": self._store.dead_links()}

    @guarded
    def restore_browser(self, name, index):
        self._store.restore_browser(name, index)
        return self._state_result()

    @guarded
    def restore_profile(self, browser, key, data, index):
        self._store.restore_profile(browser, key, data, index)
        return self._state_result()

    @guarded
    def open_browser(self, name):
        if not self._store.open_browser(name):
            return {"ok": False, "notice": {"title": "Couldn't open it", "text": "That browser was moved or uninstalled."}}
        return {"ok": True}

    # importing and editing profiles
    @guarded
    def profile_support(self, browser):
        out = self._store.profile_support(browser)
        out["ok"] = True
        return out

    @guarded
    def list_browser_profiles(self, browser):
        out = self._store.list_browser_profiles(browser)
        out["ok"] = True
        return out

    @guarded
    def add_profiles(self, browser, keys):
        added = self._store.add_profiles(browser, keys)
        out = self._state_result()
        out["added"] = added
        return out

    @guarded
    def add_default_profile(self, browser):
        self._store.add_default_profile(browser)
        return self._state_result()

    @guarded
    def edit_profile(self, browser, key, name, picture):
        self._store.edit_profile(browser, key, name, picture)
        return self._state_result()

    @guarded
    def load_picture(self, path):
        try:
            data_url, width, height = picture_data_url(clean_path(path))
        except Exception:
            log.exception("Could not open the picture %s", path)
            raise UserError("Couldn't open that picture.")
        return {"ok": True, "data_url": data_url, "width": width, "height": height}

    # files
    @guarded
    def pick_file(self, kind):
        import webview
        kinds = {"backup": ("Beyonder backups (*.zip)", "All files (*.*)"),
                 "exe": ("Programs (*.exe)", "All files (*.*)"),
                 "picture": ("Pictures (*.png;*.jpg;*.jpeg;*.webp;*.bmp;*.ico;*.gif)", "All files (*.*)")}
        types = kinds.get(kind, ("All files (*.*)",))
        dialog = getattr(getattr(webview, "FileDialog", None), "OPEN", None)
        if dialog is None:
            dialog = webview.OPEN_DIALOG
        result = self._window.create_file_dialog(dialog, allow_multiple=False, file_types=types)
        path = result[0] if result else None
        return {"ok": True, "path": os.path.normpath(path) if path else None}

    @guarded
    def get_fonts(self):
        """The four font files as base64, found by name in assets/fonts (any letter case)."""
        folder = os.path.join(RES_DIR, "assets", "fonts")
        out = {}
        try:
            names = os.listdir(folder)
        except OSError:
            log.error("Fonts folder not found: %s", folder)
            names = []
        for role in ("heading", "accent", "body", "button"):
            out[role] = None
            for n in names:
                stem, ext = os.path.splitext(n)
                if stem.lower() == role and ext.lower() in (".ttf", ".otf", ".woff", ".woff2"):
                    try:
                        with open(os.path.join(folder, n), "rb") as f:
                            out[role] = base64.b64encode(f.read()).decode("ascii")
                        log.info("Font %s loaded from %s", role, n)
                    except OSError:
                        log.exception("Could not read font %s", n)
                    break
            if out[role] is None:
                log.error("Font file for %s not found in %s", role, folder)
        return {"ok": True, "fonts": out}

    # logging from the page
    def log_js(self, level, message):
        try:
            text = "JS: %s" % message
            if level == "error":
                log.error(text)
            else:
                log.info(text)
        except Exception:
            pass
        return True

    # window controls
    @guarded
    def minimize(self):
        self._chrome.minimize()
        return {"ok": True}

    @guarded
    def toggle_maximize(self):
        return {"ok": True, "maximized": self._chrome.toggle_maximize()}

    @guarded
    def is_maximized(self):
        return {"ok": True, "maximized": self._chrome.maxed}

    @guarded
    def close(self):
        self._shell.request_close()
        return {"ok": True}

    @guarded
    def start_drag(self):
        self._chrome.begin("move")
        return {"ok": True}

    @guarded
    def start_resize(self, edge):
        if edge in ("l", "r", "t", "b", "tl", "tr", "bl", "br"):
            self._chrome.begin("resize", edge)
        return {"ok": True}


# ───────────────────────────── start ─────────────────────────────
def main():
    global Image
    setup_logging()

    def excepthook(exc_type, exc, tb):
        log.error("Unhandled exception", exc_info=(exc_type, exc, tb))

    sys.excepthook = excepthook
    try:
        threading.excepthook = lambda a: log.error("Thread exception", exc_info=(a.exc_type, a.exc_value, a.exc_traceback))
    except Exception:
        pass

    if sys.platform != "win32":
        message_box("Beyonder", "Beyonder runs on Windows only.")
        return 1
    instance_event = claim_instance()
    if instance_event is None:
        log.info("Beyonder is already running; asked it to show its window")
        return 0
    if not ensure_dependencies():
        return 1
    setup_windows_identity()

    from PIL import Image as _Image
    Image = _Image

    if not webview2_installed():
        log.error("WebView2 runtime not found")
        answer = message_box("Beyonder", "Beyonder needs the Microsoft Edge WebView2 Runtime, and it was not found on "
                                         "this PC.\n\nDownload it here:\n%s\n\nChoose Yes to open that page, or No to "
                                         "close." % WEBVIEW2_URL, 0x14)
        if answer == 6:
            try:
                os.startfile(WEBVIEW2_URL)
            except Exception:
                pass
        return 1

    if not os.path.isfile(UI_INDEX):
        log.error("UI file missing: %s", UI_INDEX)
        message_box("Beyonder", "The interface files are missing:\n%s\n\nKeep the ui folder next to beyonder.pyw." % UI_INDEX)
        return 1

    try:
        import webview
        store = Store()
        chrome = Chrome()
        settings = Settings()
        shell = Shell(chrome, settings)
        shell.store = store
        api = Api(store, chrome, shell, settings)
        if settings.get("autostart"):
            set_autostart(True)

        x, y, w, h, scale = initial_geometry()                      # the size "restore" goes back to
        left, top, right, bottom = work_area()
        mx, my, mw, mh = left, top, right - left, bottom - top      # start maximized, taskbar stays visible
        chrome.normal = (x, y, w, h)
        chrome.maxed = True
        window = webview.create_window(
            APP_TITLE, url=Path(UI_INDEX).resolve().as_uri(), js_api=api,
            width=max(640, int(mw / scale)), height=max(420, int(mh / scale)), x=int(mx / scale), y=int(my / scale),
            resizable=True, frameless=True, easy_drag=False, hidden=BACKGROUND, background_color=THEME_BG[settings.resolved_theme()],
            text_select=False,
            min_size=(320, 220))
        chrome.window = window
        api._window = window

        def on_shown():
            def work():
                try:
                    for delay in (0.0, 0.35, 1.0, 2.5):
                        time.sleep(delay)
                        if delay == 0.0 and chrome.maxed:
                            chrome.place(mx, my, mw, mh)
                        chrome.apply_icon()
                        chrome.enable_taskbar_minimize()
                        chrome.watch_title()
                        chrome._notify_max(chrome.maxed)
                except Exception:
                    log.exception("post-show setup failed")
            threading.Thread(target=work, daemon=True).start()

        window.events.shown += on_shown

        placed = []
        synced = []

        def run_sync():
            """Once per launch: keeps the imported profiles in step with their browsers (never adds new ones)."""
            try:
                time.sleep(2.0)                                 # let the window finish painting first
                if store.sync_with_browsers():
                    shell.refresh_tray()
                    shell.push_refresh()
            except Exception:
                log.exception("Syncing with the browsers failed")

        def on_loaded():
            if not synced:
                synced.append(1)
                threading.Thread(target=run_sync, daemon=True).start()

            def work():
                try:
                    if BACKGROUND and not placed and chrome.maxed:      # started hidden: put it at the maximized spot
                        chrome.place(mx, my, mw, mh)
                    placed.append(1)
                    chrome.apply_icon()
                    chrome.enable_taskbar_minimize()
                    chrome.watch_title()
                except Exception:
                    log.exception("post-load setup failed")
            threading.Thread(target=work, daemon=True).start()

        window.events.loaded += on_loaded
        window.events.closing += shell.on_closing
        shell.window = window
        shell.start_tray()
        shell.watch_system_theme()
        shell.apply_hotkey()
        listen_for_second_launch(instance_event, shell.show)
        debug = os.environ.get("BEYONDER_DEBUG") == "1"
        webview.start(gui="edgechromium", debug=debug)
        shell.quitting = True
        shell.stop_tray()
    except Exception as ex:
        log.exception("Fatal error while starting")
        message_box("Beyonder", "Beyonder could not start:\n\n%s\n\nDetails are in:\n%s" % (ex, LOG_PATH))
        return 1
    return 0


if __name__ == "__main__":
    exit_code = main()
    try:
        logging.shutdown()
    except Exception:
        pass
    os._exit(exit_code or 0)
