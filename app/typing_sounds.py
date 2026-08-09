"""Per-key sounds from app/sounds — exactly one click per keystroke, in sync."""

from __future__ import annotations

import struct
import tempfile
import wave
from pathlib import Path

try:
    import winsound
except ImportError:  # pragma: no cover
    winsound = None  # type: ignore

SOUNDS_DIR = Path(__file__).resolve().parent / "sounds"

# Keep clicks shorter than typical inter-key delay so each key is audible.
_CLICK_MS = 48

_KEY_FILES = {
    "space": "space.wav",
    "enter": "enter.wav",
    "tab": "tab.wav",
    "backspace": "backspace.wav",
    "delete": "backspace.wav",
    "shift": "shift.wav",
    "caps lock": "caps lock.wav",
    "esc": "tab.wav",
    "escape": "tab.wav",
    "left": "c.wav",
    "right": "b.wav",
    "up": "g.wav",
    "down": "v.wav",
    "home": "n.wav",
    "end": "m.wav",
    "page up": "h.wav",
    "page down": "k.wav",
    "insert": "shift.wav",
}

_CHAR_ALIASES = {
    "1": "q.wav",
    "2": "w.wav",
    "3": "e.wav",
    "4": "r.wav",
    "5": "t.wav",
    "6": "y.wav",
    "7": "u.wav",
    "8": "i.wav",
    "9": "o.wav",
    "0": "p.wav",
    "-": "[.wav",
    "=": "].wav",
    "`": "q.wav",
    ";": "l.wav",
    "'": "[.wav",
    ",": "m.wav",
    ".": "[.wav",
    "/": "].wav",
    "\\": "].wav",
    "[": "[.wav",
    "]": "].wav",
}

_PLAY_FLAGS = 0
if winsound is not None:
    # No SND_NOSTOP: each new key stops the previous click so you hear 1:1 attacks
    # at the same cadence as typing (guessable speed from sound alone).
    _PLAY_FLAGS = (
        winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT
    )


def _to_short_mono(src: Path, dest: Path, click_ms: float = _CLICK_MS) -> None:
    """Convert pack WAV → short mono click for reliable winsound + clear rhythm."""
    with wave.open(str(src), "rb") as w:
        channels = w.getnchannels()
        width = w.getsampwidth()
        rate = w.getframerate()
        frames = w.readframes(w.getnframes())

    if width != 2:
        # Fallback: copy as-is if unexpected format.
        dest.write_bytes(src.read_bytes())
        return

    sample_count = len(frames) // width
    samples = struct.unpack("<" + "h" * sample_count, frames)
    if channels == 2:
        mono = [
            int((samples[i] + samples[i + 1]) / 2)
            for i in range(0, len(samples) - 1, 2)
        ]
    else:
        mono = list(samples)

    keep = min(len(mono), max(8, int(rate * click_ms / 1000.0)))
    mono = mono[:keep]

    # Short fade-out so the click doesn't click-pop when cut by the next key.
    fade = min(len(mono), max(1, int(rate * 0.008)))
    for i in range(fade):
        idx = len(mono) - fade + i
        mono[idx] = int(mono[idx] * (1.0 - (i + 1) / fade))

    data = struct.pack("<" + "h" * len(mono), *mono)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(dest), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(data)


class TypingSoundPlayer:
    """One sound attack per keystroke, started on the typing thread at key time."""

    def __init__(self, sounds_dir: Path | None = None) -> None:
        self._enabled = False
        self._dir = Path(sounds_dir) if sounds_dir else SOUNDS_DIR
        self._cache_dir = Path(tempfile.mkdtemp(prefix="autotyper_clicks_"))
        self._files: dict[str, str] = {}
        self._prepare_cache()
        self._fallback = self._pick_fallback()

    def _prepare_cache(self) -> None:
        for src in sorted(self._dir.glob("*.wav")):
            if not src.is_file():
                continue
            dest = self._cache_dir / src.name
            try:
                _to_short_mono(src, dest)
                self._files[src.name.lower()] = str(dest)
            except Exception:
                # Last resort: use original file.
                self._files[src.name.lower()] = str(src)

    def _pick_fallback(self) -> str | None:
        for name in ("a.wav", "space.wav", "g.wav"):
            if name in self._files:
                return self._files[name]
        return next(iter(self._files.values()), None)

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)

    def resolve_path(self, kind: str, value: str) -> str | None:
        if kind == "key":
            filename = _KEY_FILES.get(value.lower())
            if filename and filename.lower() in self._files:
                return self._files[filename.lower()]
            return self._fallback

        ch = value
        if not ch:
            return self._fallback

        if ch.isalpha() and len(ch) == 1:
            return self._files.get(f"{ch.lower()}.wav", self._fallback)

        alias = _CHAR_ALIASES.get(ch)
        if alias and alias.lower() in self._files:
            return self._files[alias.lower()]

        exact = f"{ch}.wav"
        if exact.lower() in self._files:
            return self._files[exact.lower()]

        return self._fallback

    def play(self, kind: str, value: str) -> None:
        """Play exactly one click for this key, at this moment (non-blocking)."""
        if not self._enabled or winsound is None:
            return
        path = self.resolve_path(kind, value)
        if not path:
            return
        try:
            # Called on the typing thread right as the key fires — no queue lag,
            # no extra threads racing PlaySound. ASYNC returns immediately.
            winsound.PlaySound(path, _PLAY_FLAGS)
        except Exception:
            pass

    def close(self) -> None:
        self._enabled = False
        try:
            if winsound is not None:
                winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass
