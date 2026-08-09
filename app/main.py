"""Windows desktop UI for human-like keyboard typing."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk
import pyperclip

try:
    import winsound
except ImportError:  # pragma: no cover
    winsound = None  # type: ignore

from .typer_engine import BREAK_PRESETS, HumanTypingEngine, TypingSettings, parse_events
from .typing_sounds import TypingSoundPlayer

ACCENT = "#6C63FF"
ACCENT_HOVER = "#5A52E0"
SURFACE = "#1E1E22"
SURFACE_2 = "#2A2A30"
BORDER = "#3A3A42"
TEXT = "#E8E8EC"
MUTED = "#9A9AA3"


class SliderRow(ctk.CTkFrame):
    def __init__(
        self,
        master,
        label: str,
        from_: float,
        to: float,
        default: float,
        is_int: bool = True,
        on_change=None,
        **kwargs,
    ):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.is_int = is_int
        self.on_change = on_change
        self.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            self,
            text=label,
            text_color=TEXT,
            anchor="w",
            font=ctk.CTkFont(size=12),
        ).grid(row=0, column=0, sticky="w", padx=(0, 8))

        self.var = ctk.DoubleVar(value=float(default))
        self.slider = ctk.CTkSlider(
            self,
            from_=from_,
            to=to,
            variable=self.var,
            height=16,
            progress_color=ACCENT,
            button_color=ACCENT,
            button_hover_color=ACCENT_HOVER,
            command=self._on_slide,
        )
        self.slider.grid(row=0, column=1, sticky="ew", padx=(0, 8))

        self.entry = ctk.CTkEntry(
            self,
            width=48,
            height=24,
            justify="center",
            fg_color=SURFACE_2,
            border_color=BORDER,
            font=ctk.CTkFont(size=12),
        )
        self.entry.grid(row=0, column=2, sticky="e")
        self.entry.insert(0, self._fmt(default))
        self.entry.bind("<Return>", self._on_entry)
        self.entry.bind("<FocusOut>", self._on_entry)

    def _fmt(self, value: float) -> str:
        return str(int(round(value))) if self.is_int else f"{value:.1f}"

    def _on_slide(self, value: float) -> None:
        self.entry.delete(0, tk.END)
        self.entry.insert(0, self._fmt(float(value)))
        if self.on_change:
            self.on_change(float(value))

    def _on_entry(self, _event=None) -> None:
        try:
            value = float(self.entry.get().strip())
        except ValueError:
            value = float(self.var.get())
        value = max(self.slider.cget("from_"), min(self.slider.cget("to"), value))
        self.var.set(value)
        self._on_slide(value)

    def get(self) -> float:
        self._on_entry()
        return float(self.var.get())


class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("")
        self.geometry("480x420")
        self.minsize(360, 340)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")
        self.configure(fg_color="#141416")

        self.engine = HumanTypingEngine()
        self.key_sounds = TypingSoundPlayer()
        self._was_stopped = False

        self._build()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build(self) -> None:
        btn_font = ctk.CTkFont(size=11)
        small_font = ctk.CTkFont(size=11)

        root = ctk.CTkFrame(self, fg_color="transparent")
        root.pack(fill="both", expand=True, padx=10, pady=8)
        root.grid_columnconfigure(0, weight=1)
        root.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(root, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        header.grid_columnconfigure(0, weight=1)

        switches = ctk.CTkFrame(header, fg_color="transparent")
        switches.grid(row=0, column=0, sticky="e")

        self.keysound_switch = ctk.CTkSwitch(
            switches,
            text="Keys",
            width=36,
            height=18,
            font=small_font,
            progress_color=ACCENT,
            button_color="#D0D0D8",
            button_hover_color="#FFFFFF",
            command=self._on_keysound_toggle,
        )
        # On by default so keystroke sounds are audible without hunting for the switch.
        self.keysound_switch.select()
        self.key_sounds.set_enabled(True)
        self.keysound_switch.pack(side="left", padx=(0, 10))

        self.alert_switch = ctk.CTkSwitch(
            switches,
            text="Alert",
            width=36,
            height=18,
            font=small_font,
            progress_color=ACCENT,
            button_color="#D0D0D8",
            button_hover_color="#FFFFFF",
        )
        self.alert_switch.select()
        self.alert_switch.pack(side="left", padx=(0, 10))

        self.topmost_switch = ctk.CTkSwitch(
            switches,
            text="On top",
            width=36,
            height=18,
            font=small_font,
            progress_color=ACCENT,
            button_color="#D0D0D8",
            button_hover_color="#FFFFFF",
            command=self._on_topmost_toggle,
        )
        self.topmost_switch.pack(side="left")

        text_wrap = ctk.CTkFrame(root, fg_color=SURFACE, corner_radius=8)
        text_wrap.grid(row=1, column=0, sticky="nsew")
        text_wrap.grid_columnconfigure(0, weight=1)
        text_wrap.grid_rowconfigure(0, weight=1)

        self.text = ctk.CTkTextbox(
            text_wrap,
            fg_color=SURFACE,
            text_color=TEXT,
            border_width=0,
            font=ctk.CTkFont(family="Consolas", size=12),
            wrap="word",
            activate_scrollbars=True,
        )
        self.text.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        self.text.bind("<KeyRelease>", self._update_counts)
        self.text.bind("<<Paste>>", lambda _e: self.after(10, self._update_counts))
        # Insert a real tab instead of moving focus out of the editor.
        self.text.bind("<Tab>", self._insert_tab)
        try:
            self.text._textbox.bind("<Tab>", self._insert_tab)
        except Exception:
            pass

        self.count_label = ctk.CTkLabel(
            root,
            text="0 chars — 0 words",
            text_color=MUTED,
            font=small_font,
            anchor="w",
        )
        self.count_label.grid(row=2, column=0, sticky="w", pady=(4, 6))

        settings = ctk.CTkFrame(root, fg_color="transparent")
        settings.grid(row=3, column=0, sticky="ew")
        settings.grid_columnconfigure(0, weight=1)
        settings.grid_columnconfigure(1, weight=1)

        self.opacity = SliderRow(
            settings,
            "Opacity %",
            30,
            100,
            100,
            on_change=self._on_opacity_change,
        )
        self.opacity.grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=2)

        self.cpm = SliderRow(settings, "CPM", 80, 900, 400)
        self.cpm.grid(row=0, column=1, sticky="ew", padx=(6, 0), pady=2)

        self.jitter = SliderRow(settings, "Jitter (±)", 0, 200, 40)
        self.jitter.grid(row=1, column=0, sticky="ew", padx=(0, 6), pady=2)

        self.mistakes = SliderRow(settings, "Mistakes %", 0, 15, 0)
        self.mistakes.grid(row=1, column=1, sticky="ew", padx=(6, 0), pady=2)

        corr = ctk.CTkFrame(settings, fg_color="transparent")
        corr.grid(row=2, column=0, columnspan=2, sticky="ew", pady=2)
        corr.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            corr,
            text="Fix delay (ms)",
            text_color=TEXT,
            font=ctk.CTkFont(size=12),
        ).grid(row=0, column=0, sticky="w", padx=(0, 8))
        delay_box = ctk.CTkFrame(corr, fg_color="transparent")
        delay_box.grid(row=0, column=1, sticky="e")

        self.corr_lo = ctk.CTkEntry(
            delay_box,
            width=48,
            height=24,
            justify="center",
            fg_color=SURFACE_2,
            border_color=BORDER,
            font=ctk.CTkFont(size=12),
        )
        self.corr_lo.insert(0, "500")
        self.corr_lo.pack(side="left")
        ctk.CTkLabel(delay_box, text="→", text_color=MUTED, font=small_font).pack(
            side="left", padx=4
        )
        self.corr_hi = ctk.CTkEntry(
            delay_box,
            width=48,
            height=24,
            justify="center",
            fg_color=SURFACE_2,
            border_color=BORDER,
            font=ctk.CTkFont(size=12),
        )
        self.corr_hi.insert(0, "1000")
        self.corr_hi.pack(side="left")

        actions = ctk.CTkFrame(root, fg_color="transparent")
        actions.grid(row=4, column=0, sticky="ew", pady=(8, 0))

        ctk.CTkButton(
            actions,
            text="Paste",
            width=52,
            height=24,
            font=btn_font,
            fg_color=SURFACE_2,
            hover_color=BORDER,
            border_width=1,
            border_color=BORDER,
            corner_radius=6,
            command=self._paste_clipboard,
        ).pack(side="left", padx=(0, 4))

        ctk.CTkButton(
            actions,
            text="Clear",
            width=48,
            height=24,
            font=btn_font,
            fg_color=SURFACE_2,
            hover_color=BORDER,
            border_width=1,
            border_color=BORDER,
            corner_radius=6,
            command=self._clear_text,
        ).pack(side="left", padx=(0, 4))

        # Insert special-key tokens into the text (for forms: Tab between fields, arrows, …).
        self.keys_menu = ctk.CTkOptionMenu(
            actions,
            values=[
                "Insert key…",
                "{TAB}",
                "{ENTER}",
                "{LEFT}",
                "{RIGHT}",
                "{UP}",
                "{DOWN}",
                "{BACKSPACE}",
                "{DELETE}",
                "{HOME}",
                "{END}",
                "{ESC}",
                "{SPACE}",
            ],
            width=100,
            height=24,
            font=btn_font,
            fg_color=SURFACE_2,
            button_color=SURFACE_2,
            button_hover_color=BORDER,
            dropdown_fg_color=SURFACE,
            dropdown_font=btn_font,
            command=self._on_insert_key_menu,
        )
        self.keys_menu.set("Insert key…")
        self.keys_menu.pack(side="left", padx=(0, 4))

        self.breaks_btn = ctk.CTkOptionMenu(
            actions,
            values=list(BREAK_PRESETS.keys()),
            width=78,
            height=24,
            font=btn_font,
            fg_color=SURFACE_2,
            button_color=SURFACE_2,
            button_hover_color=BORDER,
            dropdown_fg_color=SURFACE,
            dropdown_font=btn_font,
        )
        self.breaks_btn.set("Natural")
        self.breaks_btn.pack(side="left", padx=(0, 4))

        self.stop_switch = ctk.CTkSwitch(
            actions,
            text="Stop",
            width=36,
            height=18,
            font=small_font,
            progress_color=ACCENT,
            button_color="#D0D0D8",
            button_hover_color="#FFFFFF",
            command=self._on_stop_toggle,
        )
        self.stop_switch.pack(side="left", padx=(4, 4))

        self.start_btn = ctk.CTkButton(
            actions,
            text="▶ Start",
            width=64,
            height=24,
            font=btn_font,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            corner_radius=6,
            command=self._start_typing,
        )
        self.start_btn.pack(side="left", padx=(4, 0))

        footer = ctk.CTkFrame(root, fg_color="transparent")
        footer.grid(row=5, column=0, sticky="ew", pady=(6, 0))
        footer.grid_columnconfigure(0, weight=1)

        self.status = ctk.CTkLabel(
            footer, text="", text_color=MUTED, font=small_font, anchor="w"
        )
        self.status.grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            footer,
            text="CPM varies",
            text_color=MUTED,
            font=small_font,
            anchor="e",
        ).grid(row=0, column=1, sticky="e")

    def _break_preset(self) -> str:
        return self.breaks_btn.get()

    def _update_counts(self, _event=None) -> None:
        content = self.text.get("1.0", "end-1c")
        chars = len(content)
        words = len(content.split()) if content.strip() else 0
        self.count_label.configure(text=f"{chars} chars — {words} words")

    def _paste_clipboard(self) -> None:
        try:
            clip = pyperclip.paste()
        except Exception:
            clip = ""
        if not clip:
            return
        self.text.insert("insert", clip)
        self._update_counts()

    def _insert_tab(self, _event=None):
        # Prefer visible token so multi-field scripts are easy to read/edit.
        self.text.insert("insert", "{TAB}")
        self._update_counts()
        return "break"

    def _insert_special(self, token: str) -> None:
        self.text.insert("insert", token)
        self._update_counts()

    def _on_insert_key_menu(self, choice: str) -> None:
        if choice and choice != "Insert key…":
            self._insert_special(choice)
        self.keys_menu.set("Insert key…")

    def _clear_text(self) -> None:
        self.text.delete("1.0", "end")
        self._update_counts()

    def _on_topmost_toggle(self) -> None:
        self.attributes("-topmost", bool(self.topmost_switch.get()))

    def _on_keysound_toggle(self) -> None:
        self.key_sounds.set_enabled(bool(self.keysound_switch.get()))

    def _play_done_sound(self, *, success: bool) -> None:
        if not self.alert_switch.get() or winsound is None:
            return
        try:
            flag = winsound.MB_OK if success else winsound.MB_ICONHAND
            winsound.MessageBeep(flag)
        except Exception:
            pass

    def _on_opacity_change(self, percent: float) -> None:
        # Keep a usable minimum so the window can't vanish.
        alpha = max(0.30, min(1.0, percent / 100.0))
        self.attributes("-alpha", alpha)

    def _on_stop_toggle(self) -> None:
        if self.stop_switch.get() == 1:
            self._was_stopped = True
            self.engine.stop()
            self.status.configure(text="Stopping…")

    def _gather_settings(self) -> TypingSettings | None:
        try:
            lo = int(self.corr_lo.get().strip())
            hi = int(self.corr_hi.get().strip())
        except ValueError:
            messagebox.showerror("Invalid delay", "Correction delay must be whole numbers.")
            return None
        if lo < 0 or hi < 0:
            messagebox.showerror("Invalid delay", "Correction delay cannot be negative.")
            return None
        if hi < lo:
            lo, hi = hi, lo
        return TypingSettings(
            cpm=self.cpm.get(),
            jitter=self.jitter.get(),
            mistake_chance_pct=self.mistakes.get(),
            correction_delay_ms=(lo, hi),
            breaks=self._break_preset(),
        )

    def _start_typing(self) -> None:
        if self.engine.is_running:
            return

        content = self.text.get("1.0", "end-1c")
        if not parse_events(content):
            messagebox.showinfo("Nothing to type", "Paste or type some text first.")
            return

        settings = self._gather_settings()
        if settings is None:
            return

        self._was_stopped = False
        self.stop_switch.deselect()
        self.start_btn.configure(state="disabled")
        self.status.configure(text="Starting in 2 seconds — click the text field…")

        def begin() -> None:
            self.key_sounds.set_enabled(bool(self.keysound_switch.get()))
            self.status.configure(text="Typing…")
            self.engine.type_text(
                content,
                settings,
                on_progress=lambda done, total: self.after(
                    0, lambda d=done, t=total: self._on_progress(d, t)
                ),
                on_done=lambda err: self.after(0, lambda e=err: self._on_done(e)),
                on_keystroke=self.key_sounds.play,
            )

        self.after(2000, begin)

    def _on_progress(self, done: int, total: int) -> None:
        pct = int((done / total) * 100) if total else 100
        self.status.configure(text=f"Typing… {done}/{total} ({pct}%)")

    def _on_done(self, error: str | None) -> None:
        self.start_btn.configure(state="normal")
        self.stop_switch.deselect()
        if error:
            self.status.configure(text=f"Error: {error}")
            self._play_done_sound(success=False)
            messagebox.showerror("Typing failed", error)
        elif self._was_stopped:
            self.status.configure(text="Stopped.")
        else:
            self.status.configure(text="Done.")
            self._play_done_sound(success=True)

    def _on_close(self) -> None:
        self.engine.stop()
        try:
            self.key_sounds.close()
        except Exception:
            pass
        self.destroy()


def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
