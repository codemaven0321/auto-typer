"""Smoke tests for line-break normalization and key dispatch."""

from __future__ import annotations

import time
import unittest
from unittest.mock import patch

from app.typer_engine import (
    HumanTypingEngine,
    TypingSettings,
    normalize_text,
    parse_events,
)


class NormalizeTests(unittest.TestCase):
    def test_crlf_becomes_single_lf(self) -> None:
        self.assertEqual(normalize_text("a\r\nb\r\nc"), "a\nb\nc")

    def test_bare_cr_becomes_lf(self) -> None:
        self.assertEqual(normalize_text("a\rb"), "a\nb")

    def test_keeps_blank_lines(self) -> None:
        self.assertEqual(normalize_text("a\n\nb"), "a\n\nb")
        self.assertEqual(normalize_text("a\r\n\r\nb"), "a\n\nb")


class ParseEventsTests(unittest.TestCase):
    def test_tab_token_and_escape(self) -> None:
        self.assertEqual(
            parse_events("a{TAB}b\\tc"),
            [("char", "a"), ("key", "tab"), ("char", "b"), ("key", "tab"), ("char", "c")],
        )

    def test_enter_token(self) -> None:
        self.assertEqual(
            parse_events("x{ENTER}y"),
            [("char", "x"), ("key", "enter"), ("char", "y")],
        )

    def test_raw_tab_and_newline(self) -> None:
        self.assertEqual(
            parse_events("a\tb\nc"),
            [
                ("char", "a"),
                ("key", "tab"),
                ("char", "b"),
                ("key", "enter"),
                ("char", "c"),
            ],
        )


class TypingDispatchTests(unittest.TestCase):
    def test_newlines_send_enter_not_press_hold(self) -> None:
        engine = HumanTypingEngine()
        settings = TypingSettings(cpm=900, jitter=0, mistake_chance_pct=0, breaks="Off")
        taps: list[str] = []
        writes: list[str] = []

        with (
            patch.object(HumanTypingEngine, "_tap", side_effect=lambda k: taps.append(k)),
            patch("app.typer_engine.type_char_with_fallback", side_effect=lambda c: writes.append(c)),
            patch.object(HumanTypingEngine, "_interruptible_sleep", return_value=False),
        ):
            done = {"ok": False}

            def on_done(err: str | None) -> None:
                done["ok"] = err is None
                done["err"] = err

            engine.type_text("Hi\r\nthere\n\nEnd", settings, on_done=on_done)
            for _ in range(50):
                if not engine.is_running:
                    break
                time.sleep(0.02)

        self.assertTrue(done["ok"], done.get("err"))
        # "Hi\nthere\n\nEnd" → Enter after Hi, after there, blank line Enter
        self.assertEqual(taps.count("enter"), 3)
        self.assertEqual(writes, list("HithereEnd"))
        self.assertNotIn("space", taps)

    def test_space_and_tab_use_tap(self) -> None:
        engine = HumanTypingEngine()
        settings = TypingSettings(cpm=900, jitter=0, mistake_chance_pct=0, breaks="Off")
        taps: list[str] = []

        with (
            patch.object(HumanTypingEngine, "_tap", side_effect=lambda k: taps.append(k)),
            patch("app.typer_engine.type_char_with_fallback"),
            patch.object(HumanTypingEngine, "_interruptible_sleep", return_value=False),
        ):
            done = {"ok": False}
            engine.type_text("a b\tc", settings, on_done=lambda e: done.update(ok=e is None))
            for _ in range(50):
                if not engine.is_running:
                    break
                time.sleep(0.02)

        self.assertTrue(done["ok"])
        self.assertEqual(taps, ["space", "tab"])

    def test_special_tokens_dispatch_keys(self) -> None:
        engine = HumanTypingEngine()
        settings = TypingSettings(cpm=900, jitter=0, mistake_chance_pct=0, breaks="Off")
        taps: list[str] = []

        with (
            patch.object(HumanTypingEngine, "_tap", side_effect=lambda k: taps.append(k)),
            patch("app.typer_engine.type_char_with_fallback"),
            patch.object(HumanTypingEngine, "_interruptible_sleep", return_value=False),
        ):
            done = {"ok": False}
            engine.type_text(
                "a{TAB}b{ENTER}c{ESC}",
                settings,
                on_done=lambda e: done.update(ok=e is None),
            )
            for _ in range(50):
                if not engine.is_running:
                    break
                time.sleep(0.02)

        self.assertTrue(done["ok"])
        self.assertEqual(taps, ["tab", "enter", "esc"])


class HumanPacingTests(unittest.TestCase):
    def test_delays_are_variable_not_metronomic(self) -> None:
        engine = HumanTypingEngine()
        samples: list[float] = []

        def fake_sleep(seconds: float) -> bool:
            if seconds > 0.01:
                samples.append(seconds)
            return False

        with (
            patch.object(HumanTypingEngine, "_tap"),
            patch("app.typer_engine.type_char_with_fallback"),
            patch.object(HumanTypingEngine, "_interruptible_sleep", side_effect=fake_sleep),
        ):
            settings = TypingSettings(
                cpm=300, jitter=80, mistake_chance_pct=0, breaks="Natural"
            )
            done = {"ok": False}
            text = "Hello world. Next line.\nNew paragraph follows soon."
            engine.type_text(text, settings, on_done=lambda e: done.update(ok=e is None))
            for _ in range(100):
                if not engine.is_running:
                    break
                time.sleep(0.02)

        self.assertTrue(done["ok"])
        self.assertGreater(len(samples), 10)
        # Coefficient of variation should be noticeable (not flat robot timing).
        mean = sum(samples) / len(samples)
        var = sum((s - mean) ** 2 for s in samples) / len(samples)
        cv = (var**0.5) / mean
        self.assertGreater(cv, 0.15, f"timing too flat: cv={cv:.3f}")


if __name__ == "__main__":
    unittest.main()
