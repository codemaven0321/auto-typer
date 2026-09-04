"""Done-alarm loop — rings up to 1 minute; call stop() to silence."""

from __future__ import annotations

import math
import struct
import threading
import time
import wave
from pathlib import Path

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
ALARM_WAV = ASSETS_DIR / "alarm.wav"


def _ensure_wav() -> None:
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    if ALARM_WAV.exists() and ALARM_WAV.stat().st_size >= 100:
        return
    rate = 22050
    ms = 280
    n = int(rate * ms / 1000)
    freqs = (1400.0, 1800.0, 1400.0)
    samples: list[int] = []
    for i in range(n):
        t = i / rate
        env = min(1.0, t * 40) * math.exp(-t * 6)
        phase_t = t * len(freqs) / max(ms / 1000, 0.01)
        idx = min(int(phase_t), len(freqs) - 1)
        val = math.sin(2 * math.pi * freqs[idx] * t)
        samples.append(int(max(-1.0, min(1.0, val * env * 0.9)) * 32767))
    with wave.open(str(ALARM_WAV), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(struct.pack("<" + "h" * n, *samples))


class AlarmLoop:
    """Repeat an alarm for a duration; call stop() to silence."""

    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    def start(self, seconds: float = 60.0) -> None:
        if self._running:
            return
        self._stop.clear()
        self._running = True
        ring = min(60.0, max(1.0, float(seconds)))
        self._thread = threading.Thread(
            target=self._run, args=(ring,), daemon=True, name="AlarmLoop"
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._running = False
        self._purge()

    def _purge(self) -> None:
        try:
            import winsound

            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass

    def _play_one(self) -> None:
        try:
            _ensure_wav()
            import winsound

            winsound.PlaySound(
                str(ALARM_WAV),
                winsound.SND_FILENAME | winsound.SND_NODEFAULT,
            )
        except Exception:
            try:
                import winsound

                winsound.Beep(1500, 120)
            except Exception:
                pass

    def _run(self, seconds: float) -> None:
        end = time.monotonic() + seconds
        try:
            while not self._stop.is_set() and time.monotonic() < end:
                self._play_one()
                if self._stop.wait(0.12):
                    break
        finally:
            self._purge()
            self._running = False
