"""Low-level keyboard injection using scan codes (RDP / remote-desktop safe).

The ``keyboard`` library's ``write()`` sends KEYEVENTF_UNICODE, which many remote
tools (RDP, Parsec, TeamViewer, etc.) drop. ``send('space')`` uses scan codes
and works — this module types printable characters the same way.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008

ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong

VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12  # Alt


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


def _vk_to_scan(vk: int) -> int:
    return int(user32.MapVirtualKeyW(vk, 0))


def _scan_down(scan: int) -> None:
    inp = INPUT(
        type=INPUT_KEYBOARD,
        ki=KEYBDINPUT(0, scan, KEYEVENTF_SCANCODE, 0, 0),
    )
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def _scan_up(scan: int) -> None:
    inp = INPUT(
        type=INPUT_KEYBOARD,
        ki=KEYBDINPUT(0, scan, KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP, 0, 0),
    )
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def _tap_scan(scan: int) -> None:
    _scan_down(scan)
    _scan_up(scan)


def _modifier_vks(shift_state: int) -> list[int]:
    mods: list[int] = []
    if shift_state & 1:
        mods.append(VK_SHIFT)
    if shift_state & 2:
        mods.append(VK_CONTROL)
    if shift_state & 4:
        mods.append(VK_MENU)
    if shift_state & 8:
        # Hankaku / special — rarely needed for Latin typing
        pass
    return mods


def type_char(char: str) -> bool:
    """
    Type one character via hardware scan codes + current keyboard layout.
    Returns True if sent, False if the character cannot be mapped (caller may fallback).
    """
    if not char or len(char) != 1:
        return False

    mapped = user32.VkKeyScanW(ord(char))
    if mapped == -1:
        return False

    vk = mapped & 0xFF
    shift_state = (mapped >> 8) & 0xFF
    main_scan = _vk_to_scan(vk)
    if main_scan == 0:
        return False

    mod_scans = [_vk_to_scan(vk_mod) for vk_mod in _modifier_vks(shift_state)]
    mod_scans = [s for s in mod_scans if s]

    for scan in mod_scans:
        _scan_down(scan)
    _scan_down(main_scan)
    _scan_up(main_scan)
    for scan in reversed(mod_scans):
        _scan_up(scan)
    return True


def type_char_with_fallback(char: str) -> None:
    """Scan-code typing with Unicode fallback for unmappable glyphs."""
    if type_char(char):
        return
    try:
        from keyboard import write

        write(char, delay=0)
    except Exception:
        try:
            from keyboard import send

            send(char)
        except Exception:
            pass
