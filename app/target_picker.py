"""Pick a target window by screen position (crosshair click)."""

from __future__ import annotations

import time
import tkinter as tk
from dataclasses import dataclass
from typing import Callable

try:
    import win32api
    import win32con
    import win32gui
    import win32process
except ImportError:  # pragma: no cover
    win32api = None  # type: ignore
    win32con = None  # type: ignore
    win32gui = None  # type: ignore
    win32process = None  # type: ignore


@dataclass
class TargetWindow:
    hwnd: int
    title: str
    click_x: int | None = None
    click_y: int | None = None

    @property
    def label(self) -> str:
        title = self.title.strip() or "Untitled"
        if len(title) > 42:
            title = title[:39] + "..."
        if self.click_x is not None and self.click_y is not None:
            return f"{title} @ ({self.click_x}, {self.click_y})"
        return title


def _is_obscured_tool_window(hwnd: int) -> bool:
    assert win32gui is not None and win32con is not None
    try:
        ex = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        if ex & win32con.WS_EX_TOOLWINDOW and not (ex & win32con.WS_EX_APPWINDOW):
            title = win32gui.GetWindowText(hwnd)
            # Keep named tool windows; skip nameless chrome.
            if not title.strip():
                return True
    except Exception:
        return True
    return False


def window_at_point(
    x: int,
    y: int,
    exclude_hwnds: set[int] | None = None,
) -> TargetWindow | None:
    """Find the topmost visible top-level window under a screen point.

    Uses Z-order enumeration so a transparent picker overlay can be excluded
    without temporarily hiding it (WindowFromPoint would hit the overlay).
    """
    if win32gui is None:
        return None

    exclude = set(exclude_hwnds or ())
    hit: int | None = None

    def enum_handler(hwnd: int, _: object) -> bool:
        nonlocal hit
        if hwnd in exclude:
            return True
        try:
            if not win32gui.IsWindowVisible(hwnd):
                return True
            if win32gui.IsIconic(hwnd):
                return True
            if _is_obscured_tool_window(hwnd):
                return True
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        except Exception:
            return True
        if left <= x < right and top <= y < bottom:
            hit = hwnd
            return False  # stop enum — EnumWindows is top-to-bottom Z-order
        return True

    try:
        win32gui.EnumWindows(enum_handler, None)
    except Exception:
        return None

    if not hit:
        return None

    try:
        title = win32gui.GetWindowText(hit)
    except Exception:
        title = ""

    return TargetWindow(hwnd=hit, title=title, click_x=x, click_y=y)


def _window_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    if win32gui is None:
        return None
    try:
        return win32gui.GetWindowRect(hwnd)
    except Exception:
        return None


def click_screen(x: int, y: int) -> None:
    """Left-click a screen position to focus the field under the cursor."""
    if win32api is None or win32con is None:
        return
    win32api.SetCursorPos((int(x), int(y)))
    time.sleep(0.05)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.02)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


def focus_target(target: TargetWindow | None, settle_seconds: float = 0.35) -> bool:
    """Foreground the chosen window and re-click the picked position."""
    if target is None or win32gui is None:
        return False
    hwnd = target.hwnd
    if not win32gui.IsWindow(hwnd):
        return False

    try:
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)

        foreground = win32gui.GetForegroundWindow()
        current_thread = win32process.GetCurrentThreadId()
        fg_thread, _ = (
            win32process.GetWindowThreadProcessId(foreground) if foreground else (0, 0)
        )
        target_thread, _ = win32process.GetWindowThreadProcessId(hwnd)

        attached_fg = False
        attached_target = False
        if fg_thread and fg_thread != current_thread:
            attached_fg = bool(win32process.AttachThreadInput(current_thread, fg_thread, True))
        if target_thread and target_thread != current_thread and target_thread != fg_thread:
            attached_target = bool(
                win32process.AttachThreadInput(current_thread, target_thread, True)
            )

        try:
            win32gui.BringWindowToTop(hwnd)
            win32gui.SetForegroundWindow(hwnd)
        finally:
            if attached_target:
                win32process.AttachThreadInput(current_thread, target_thread, False)
            if attached_fg:
                win32process.AttachThreadInput(current_thread, fg_thread, False)

        time.sleep(settle_seconds)

        if target.click_x is not None and target.click_y is not None:
            click_screen(target.click_x, target.click_y)
            time.sleep(0.15)

        return True
    except Exception:
        return False


class PositionTargetPicker:
    """Fullscreen crosshair overlay: click a position to select that window."""

    def __init__(
        self,
        master: tk.Misc,
        on_picked: Callable[[TargetWindow | None], None],
        exclude_hwnds: set[int] | None = None,
    ) -> None:
        self.on_picked = on_picked
        self.exclude_hwnds: set[int] = set(exclude_hwnds or ())
        self._done = False
        self._last_hover_hwnd: int | None = None

        self.overlay = tk.Toplevel(master)
        self.overlay.withdraw()
        self.overlay.overrideredirect(True)
        self.overlay.attributes("-topmost", True)
        try:
            self.overlay.attributes("-alpha", 0.20)
        except tk.TclError:
            pass

        if win32api is not None:
            vx = win32api.GetSystemMetrics(76)  # SM_XVIRTUALSCREEN
            vy = win32api.GetSystemMetrics(77)
            vw = win32api.GetSystemMetrics(78)
            vh = win32api.GetSystemMetrics(79)
        else:
            vx, vy = 0, 0
            vw = master.winfo_screenwidth()
            vh = master.winfo_screenheight()

        self._origin = (vx, vy)
        self.overlay.geometry(f"{vw}x{vh}+{vx}+{vy}")
        self.overlay.configure(bg="#101018")
        self.overlay.config(cursor="crosshair")

        self.canvas = tk.Canvas(
            self.overlay,
            bg="#101018",
            highlightthickness=0,
            cursor="crosshair",
        )
        self.canvas.pack(fill="both", expand=True)

        self.canvas.create_text(
            vw // 2,
            36,
            text="Click the text field to type into   ·   Esc / right-click to cancel",
            fill="#F2F2F7",
            font=("Segoe UI", 14, "bold"),
            tags=("hint",),
        )

        self._rect = self.canvas.create_rectangle(
            0, 0, 0, 0, outline="#6C63FF", width=3, tags=("highlight",)
        )
        self._label = self.canvas.create_text(
            0,
            0,
            text="",
            fill="#FFFFFF",
            font=("Segoe UI", 11),
            anchor="nw",
            tags=("label",),
        )

        self.overlay.update_idletasks()
        try:
            self.exclude_hwnds.add(int(self.overlay.winfo_id()))
        except Exception:
            pass

        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Button-1>", self._on_click)
        self.overlay.bind("<Escape>", self._on_cancel)
        self.overlay.bind("<Button-3>", self._on_cancel)

        self.overlay.deiconify()
        self.overlay.lift()
        self.overlay.focus_force()
        self.overlay.grab_set()

    def _on_motion(self, event: tk.Event) -> None:
        if self._done:
            return
        x, y = int(event.x_root), int(event.y_root)
        target = window_at_point(x, y, self.exclude_hwnds)
        if target is None:
            if self._last_hover_hwnd is not None:
                self._last_hover_hwnd = None
                self.canvas.coords(self._rect, 0, 0, 0, 0)
                self.canvas.itemconfigure(self._label, text="")
            return

        if target.hwnd == self._last_hover_hwnd:
            # Still update coordinate readout.
            title = target.title.strip() or "Untitled window"
            self.canvas.itemconfigure(self._label, text=f"{title}   ({x}, {y})")
            return

        self._last_hover_hwnd = target.hwnd
        rect = _window_rect(target.hwnd)
        if not rect:
            return
        left, top, right, bottom = rect
        ox, oy = self._origin
        self.canvas.coords(
            self._rect,
            left - ox,
            top - oy,
            right - ox,
            bottom - oy,
        )
        title = target.title.strip() or "Untitled window"
        self.canvas.coords(self._label, left - ox + 8, top - oy + 8)
        self.canvas.itemconfigure(self._label, text=f"{title}   ({x}, {y})")

    def _finish(self, target: TargetWindow | None) -> None:
        if self._done:
            return
        self._done = True
        try:
            self.overlay.grab_release()
        except tk.TclError:
            pass
        try:
            self.overlay.destroy()
        except tk.TclError:
            pass
        self.on_picked(target)

    def _on_click(self, event: tk.Event) -> None:
        x, y = int(event.x_root), int(event.y_root)
        target = window_at_point(x, y, self.exclude_hwnds)
        if target is None:
            return
        target.click_x = x
        target.click_y = y
        self._finish(target)

    def _on_cancel(self, _event=None) -> None:
        self._finish(None)
