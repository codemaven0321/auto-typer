"""Tests for scan-code keyboard input."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from app.keyboard_input import type_char


class KeyboardInputTests(unittest.TestCase):
    def test_type_char_maps_letter(self) -> None:
        with patch("app.keyboard_input.user32") as user32:
            user32.VkKeyScanW.return_value = ord("a")  # vk='a', no modifiers
            user32.MapVirtualKeyW.return_value = 0x1E
            user32.SendInput.return_value = 1
            self.assertTrue(type_char("a"))
            self.assertGreater(user32.SendInput.call_count, 0)

    def test_type_char_uses_shift_for_uppercase(self) -> None:
        with patch("app.keyboard_input.user32") as user32:
            # vk for 'A' with shift bit set
            user32.VkKeyScanW.return_value = ord("A") | (1 << 8)
            user32.MapVirtualKeyW.side_effect = lambda vk, _: {
                0x10: 0x2A,  # shift
                ord("A") & 0xFF: 0x1E,
            }.get(vk, 0x1E)
            user32.SendInput.return_value = 1
            self.assertTrue(type_char("A"))
            # down: shift, key, up: key, shift
            self.assertGreaterEqual(user32.SendInput.call_count, 4)

    def test_unmappable_returns_false(self) -> None:
        with patch("app.keyboard_input.user32") as user32:
            user32.VkKeyScanW.return_value = -1
            self.assertFalse(type_char("\u2603"))


if __name__ == "__main__":
    unittest.main()
