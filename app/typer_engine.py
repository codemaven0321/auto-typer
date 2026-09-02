"""High-quality human-like typing engine built on human_typer."""

from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass
from typing import Callable

from keyboard import send

from .human_typer_loader import Human_typer
from .keyboard_input import type_char_with_fallback


BREAK_PRESETS = {
    "Off": {
        "word_pause": (0.0, 0.0),
        "sentence_pause": (0.0, 0.0),
        "line_pause": (0.0, 0.0),
        "paragraph_pause": (0.0, 0.0),
        "think_chance": 0.0,
        "think_pause": (0.0, 0.0),
    },
    "Light": {
        "word_pause": (0.03, 0.10),
        "sentence_pause": (0.18, 0.45),
        "line_pause": (0.22, 0.55),
        "paragraph_pause": (0.45, 0.95),
        "think_chance": 0.012,
        "think_pause": (0.3, 0.75),
    },
    "Natural": {
        "word_pause": (0.05, 0.16),
        "sentence_pause": (0.35, 0.85),
        "line_pause": (0.4, 1.0),
        "paragraph_pause": (0.75, 1.8),
        "think_chance": 0.03,
        "think_pause": (0.5, 1.4),
    },
    "Heavy": {
        "word_pause": (0.1, 0.28),
        "sentence_pause": (0.55, 1.35),
        "line_pause": (0.7, 1.6),
        "paragraph_pause": (1.2, 2.8),
        "think_chance": 0.055,
        "think_pause": (0.9, 2.2),
    },
}

# Fast same-hand / common digraphs typed a bit quicker.
_FAST_DIGRAPHS = {
    "th",
    "he",
    "in",
    "er",
    "an",
    "re",
    "on",
    "at",
    "en",
    "nd",
    "ti",
    "es",
    "or",
    "te",
    "of",
    "ed",
    "is",
    "it",
    "al",
    "ar",
    "st",
    "to",
    "nt",
    "ng",
    "se",
    "ha",
    "as",
    "ou",
    "io",
    "le",
    "ve",
    "co",
    "me",
    "de",
    "hi",
    "ri",
    "ro",
    "ic",
    "ne",
}


# Named special keys users can embed as {TAB}, {ENTER}, …
SPECIAL_TOKENS: dict[str, str] = {
    "TAB": "tab",
    "ENTER": "enter",
    "RETURN": "enter",
    "RET": "enter",
    "ESC": "esc",
    "ESCAPE": "esc",
    "BACKSPACE": "backspace",
    "BS": "backspace",
    "DELETE": "delete",
    "DEL": "delete",
    "SPACE": "space",
    "HOME": "home",
    "END": "end",
    "UP": "up",
    "DOWN": "down",
    "LEFT": "left",
    "RIGHT": "right",
    "PAGEUP": "page up",
    "PGUP": "page up",
    "PAGEDOWN": "page down",
    "PGDN": "page down",
    "INSERT": "insert",
    "INS": "insert",
}

_ESCAPE_CHARS = {
    "t": "\t",
    "n": "\n",
    "r": "\n",
    "\\": "\\",
}


def normalize_text(text: str) -> str:
    """Normalize clipboard / editor line endings so Enter is typed once per line."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def parse_events(text: str) -> list[tuple[str, str]]:
    """Parse text into typing events: ("char", ch) or ("key", key_name).

    Supports:
    - real control chars (tab / newline)
    - backslash escapes: \\t \\n \\r \\\\
    - brace tokens: {TAB} {ENTER} {ESC} …
    """
    text = normalize_text(text)
    events: list[tuple[str, str]] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "{" :
            close = text.find("}", i + 1)
            if close != -1:
                token = text[i + 1 : close].strip().upper()
                if token in SPECIAL_TOKENS:
                    events.append(("key", SPECIAL_TOKENS[token]))
                    i = close + 1
                    continue
        if ch == "\\" and i + 1 < n:
            esc = text[i + 1]
            if esc in _ESCAPE_CHARS:
                mapped = _ESCAPE_CHARS[esc]
                if mapped == "\t":
                    events.append(("key", "tab"))
                elif mapped == "\n":
                    events.append(("key", "enter"))
                else:
                    events.append(("char", mapped))
                i += 2
                continue
        if ch == "\t":
            events.append(("key", "tab"))
        elif ch == "\n":
            events.append(("key", "enter"))
        elif ch == " ":
            events.append(("key", "space"))
        else:
            events.append(("char", ch))
        i += 1
    return events


@dataclass
class TypingSettings:
    cpm: float = 450.0
    jitter: float = 40.0
    mistake_chance_pct: float = 3.0
    correction_delay_ms: tuple[int, int] = (500, 1000)
    breaks: str = "Natural"
    layout: str = "qwerty"


class HumanTypingEngine:
    """Wraps human_typer layouts/typo logic with richer pacing and cancellation."""

    def __init__(self) -> None:
        self._stop = threading.Event()
        self._busy = threading.Event()

    @property
    def is_running(self) -> bool:
        return self._busy.is_set()

    def stop(self) -> None:
        self._stop.set()

    def type_text(
        self,
        text: str,
        settings: TypingSettings,
        on_progress: Callable[[int, int], None] | None = None,
        on_done: Callable[[str | None], None] | None = None,
        on_keystroke: Callable[[str, str], None] | None = None,
    ) -> None:
        if self._busy.is_set():
            if on_done:
                on_done("Already typing")
            return

        self._stop.clear()
        self._busy.set()

        def worker() -> None:
            error: str | None = None
            try:
                self._run(text, settings, on_progress, on_keystroke)
            except Exception as exc:  # noqa: BLE001 - surface to UI
                error = str(exc)
            finally:
                self._busy.clear()
                if on_done:
                    on_done(error)

        threading.Thread(target=worker, daemon=True).start()

    def _emit_keystroke(
        self,
        on_keystroke: Callable[[str, str], None] | None,
        kind: str,
        value: str,
    ) -> None:
        """Fire keystroke side-effects without letting them slow typing."""
        if on_keystroke is None:
            return
        try:
            on_keystroke(kind, value)
        except Exception:
            pass

    def _run(
        self,
        text: str,
        settings: TypingSettings,
        on_progress: Callable[[int, int], None] | None,
        on_keystroke: Callable[[str, str], None] | None = None,
    ) -> None:
        events = parse_events(text)
        if not events:
            return

        error_rate = max(0.0, min(1.0, settings.mistake_chance_pct / 100.0))
        base = Human_typer(
            keyboard_layout=settings.layout,
            average_cpm=max(40.0, settings.cpm),
            error_rate=error_rate,
        )

        cpm = max(40.0, settings.cpm)
        jitter = max(0.0, settings.jitter)
        low_cpm = max(30.0, cpm - jitter)
        high_cpm = max(low_cpm + 1.0, cpm + jitter)

        corr_lo = max(50, min(settings.correction_delay_ms)) / 1000.0
        corr_hi = max(corr_lo, max(settings.correction_delay_ms) / 1000.0)

        breaks = BREAK_PRESETS.get(settings.breaks, BREAK_PRESETS["Natural"])

        # Local rhythm state — speed drifts in waves like a real typist.
        rhythm = 1.0
        burst_left = 0
        prev = ""

        total = len(events)
        i = 0
        while i < total:
            if self._stop.is_set():
                return

            kind, value = events[i]
            if on_progress:
                on_progress(i, total)

            if kind == "key":
                # Sound thread first, then key — keeps audio locked to the event.
                self._emit_keystroke(on_keystroke, "key", value)
                self._tap(value)
                # Map special keys to pacing stand-ins.
                pace_char = {
                    "enter": "\n",
                    "tab": "\t",
                    "space": " ",
                }.get(value, "\t")
                self._sleep_char(pace_char, prev, low_cpm, high_cpm, rhythm)
                self._maybe_break_event(pace_char, events, i, breaks)
                prev = pace_char
            else:
                char = value
                if (
                    error_rate > 0
                    and char not in " \t\n"
                    and random.random() < error_rate
                ):
                    self._type_with_mistake(
                        base,
                        char,
                        corr_lo,
                        corr_hi,
                        low_cpm,
                        high_cpm,
                        rhythm,
                        on_keystroke,
                    )
                else:
                    self._emit_keystroke(on_keystroke, "char", char)
                    self._type_char(char)
                    self._sleep_char(char, prev, low_cpm, high_cpm, rhythm)
                self._maybe_break_event(char, events, i, breaks)
                prev = char

            # Drift rhythm slowly; occasional short bursts of faster keys.
            if burst_left > 0:
                burst_left -= 1
                if burst_left == 0:
                    rhythm = random.uniform(0.92, 1.08)
            elif random.random() < 0.04:
                burst_left = random.randint(3, 9)
                rhythm = random.uniform(0.72, 0.88)
            else:
                rhythm = max(0.7, min(1.35, rhythm + random.uniform(-0.04, 0.04)))

            if self._stop.is_set():
                return
            i += 1

        if on_progress:
            on_progress(total, total)

    def _type_with_mistake(
        self,
        base: Human_typer,
        char: str,
        corr_lo: float,
        corr_hi: float,
        low_cpm: float,
        high_cpm: float,
        rhythm: float,
        on_keystroke: Callable[[str, str], None] | None = None,
    ) -> None:
        layout = base.find_layout(char)
        if layout is None:
            self._emit_keystroke(on_keystroke, "char", char)
            self._type_char(char)
            self._sleep_char(char, "", low_cpm, high_cpm, rhythm)
            return

        wrong = base.get_random_close_neighbor(char, layout)
        if random.random() < 0.65:
            self._emit_keystroke(on_keystroke, "char", wrong)
            self._type_char(wrong)
            if self._interruptible_sleep(self._uniform(corr_lo, corr_hi)):
                return
            self._emit_keystroke(on_keystroke, "key", "backspace")
            self._tap("backspace")
            if self._interruptible_sleep(self._uniform(corr_lo * 0.45, corr_hi * 0.55)):
                return
            self._emit_keystroke(on_keystroke, "char", char)
            self._type_char(char)
        else:
            self._emit_keystroke(on_keystroke, "char", char)
            self._type_char(char)
            self._sleep_char(char, "", low_cpm, high_cpm, rhythm)
            if self._stop.is_set():
                return
            self._emit_keystroke(on_keystroke, "char", wrong)
            self._type_char(wrong)
            if self._interruptible_sleep(self._uniform(corr_lo, corr_hi)):
                return
            self._emit_keystroke(on_keystroke, "key", "backspace")
            self._tap("backspace")

        self._sleep_char(char, "", low_cpm, high_cpm, rhythm)

    @staticmethod
    def _tap(key: str) -> None:
        """Press and release a named key (Enter, Tab, Backspace, …)."""
        send(key)

    def _type_char(self, char: str) -> None:
        if char == "\n":
            # Must use send/press_and_release — keyboard.press() holds without release.
            self._tap("enter")
        elif char == "\t":
            self._tap("tab")
        elif char == " ":
            self._tap("space")
        else:
            # Scan-code path works over RDP / remote desktop; keyboard.write() does not.
            type_char_with_fallback(char)

    def _sleep_char(
        self,
        char: str,
        prev: str,
        low_cpm: float,
        high_cpm: float,
        rhythm: float,
    ) -> None:
        instant_cpm = random.uniform(low_cpm, high_cpm)
        base = 60.0 / instant_cpm
        # Heavier log-normal so gaps aren't metronomic.
        delay = base * random.lognormvariate(0.0, 0.28) * rhythm

        digraph = (prev + char).lower()
        if digraph in _FAST_DIGRAPHS:
            delay *= random.uniform(0.72, 0.9)
        elif prev and prev.isalpha() and char.isalpha():
            # Awkward reach / case change slows a bit.
            if prev.islower() != char.islower() and char.isupper():
                delay *= random.uniform(1.15, 1.45)

        if char in ",:;":
            delay *= random.uniform(1.45, 2.3)
        elif char in ".!?":
            delay *= random.uniform(1.9, 3.2)
        elif char == " ":
            delay *= random.uniform(0.7, 1.2)
        elif char == "\t":
            delay *= random.uniform(1.1, 1.6)
        elif char == "\n":
            # Line break: human hesitation before continuing.
            delay *= random.uniform(1.6, 2.8)
        elif char.isupper():
            delay *= random.uniform(1.08, 1.3)
        elif char.isdigit():
            delay *= random.uniform(1.05, 1.35)

        # Tiny micro-stutter (~3%) — looks human, not perfect.
        if random.random() < 0.03:
            delay += random.uniform(0.08, 0.28)

        self._interruptible_sleep(max(0.015, delay))

    def _maybe_break_event(
        self,
        char: str,
        events: list[tuple[str, str]],
        index: int,
        breaks: dict,
    ) -> None:
        if breaks["think_chance"] > 0 and random.random() < breaks["think_chance"]:
            self._interruptible_sleep(self._uniform(*breaks["think_pause"]))
            return

        nxt = ""
        if index + 1 < len(events):
            nkind, nval = events[index + 1]
            if nkind == "key":
                nxt = {"enter": "\n", "tab": "\t", "space": " "}.get(nval, "")
            else:
                nxt = nval

        if char == "\n":
            # Blank line (paragraph) vs single line break.
            if nxt == "\n":
                self._interruptible_sleep(self._uniform(*breaks["paragraph_pause"]))
            else:
                self._interruptible_sleep(self._uniform(*breaks["line_pause"]))
        elif char in ".!?" and (nxt in " \n\t" or nxt == ""):
            self._interruptible_sleep(self._uniform(*breaks["sentence_pause"]))
        elif char == " " and nxt and nxt not in " \n\t":
            self._interruptible_sleep(self._uniform(*breaks["word_pause"]))

    @staticmethod
    def _uniform(lo: float, hi: float) -> float:
        """random.uniform that never errors when bounds are equal or swapped."""
        a, b = float(lo), float(hi)
        if b < a:
            a, b = b, a
        if a == b:
            return a
        return random.uniform(a, b)

    def _interruptible_sleep(self, seconds: float) -> bool:
        """Sleep in slices so Stop reacts quickly. Returns True if stopped."""
        remaining = max(0.0, float(seconds))
        if remaining <= 0:
            return self._stop.is_set()
        end = time.perf_counter() + remaining
        while True:
            if self._stop.is_set():
                return True
            left = end - time.perf_counter()
            if left <= 0:
                break
            time.sleep(min(0.05, left))
        return self._stop.is_set()
