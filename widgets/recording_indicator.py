"""Large pulsing red REC light for active meeting capture."""

import tkinter as tk


class RecordingIndicator(tk.Frame):
    """Shows a big blinking red light while recording is in progress."""

    _BG = "#FFEBEE"
    _LIGHT_ON = "#E53935"
    _LIGHT_OFF = "#8B1E1E"
    _LABEL_ON = "#B71C1C"
    _LABEL_OFF = "#8B1E1E"
    _WARNING_FG = "#7F4200"
    _PULSE_MS = 500
    _SUBTITLE_IDLE = "Mic / screen capture in progress"

    def __init__(self, master, stop_command=None, **kwargs):
        super().__init__(master, bg=self._BG, padx=10, pady=8, **kwargs)
        self._active = False
        self._lit = True
        self._pulse_job = None
        self._warning = ""

        self._canvas = tk.Canvas(
            self,
            width=40,
            height=40,
            bg=self._BG,
            highlightthickness=0,
            bd=0,
        )
        self._canvas.pack(side="left")
        self._light = self._canvas.create_oval(
            4, 4, 36, 36, fill=self._LIGHT_ON, outline="#B71C1C", width=2
        )

        text_col = tk.Frame(self, bg=self._BG)
        text_col.pack(side="left", padx=(10, 0))
        self._label = tk.Label(
            text_col,
            text="RECORDING",
            font=("Segoe UI", 16, "bold"),
            fg=self._LABEL_ON,
            bg=self._BG,
        )
        self._label.pack(anchor="w")
        self._subtitle = tk.Label(
            text_col,
            text=self._SUBTITLE_IDLE,
            font=("Segoe UI", 9),
            fg=self._LABEL_ON,
            bg=self._BG,
        )
        self._subtitle.pack(anchor="w")

        self._stop_button = tk.Button(
            self,
            text="■  STOP RECORDING",
            command=stop_command,
            font=("Segoe UI", 11, "bold"),
            fg="white",
            bg="#C62828",
            activeforeground="white",
            activebackground="#8E0000",
            padx=16,
            pady=10,
            cursor="hand2",
        )
        self._stop_button.pack(side="right", padx=(12, 0))

        self.pack_forget()

    def start(self):
        if self._active:
            return
        self._active = True
        self._lit = True
        self._stop_button.configure(state="normal", text="■  STOP RECORDING")
        self.clear_warning()
        self.pack(fill="x", pady=(8, 0))
        self._paint_light(True)
        self._schedule_pulse()

    def set_warning(self, message):
        """Show a capture problem on the indicator itself while recording.

        The status line scrolls past and the activity log is only read
        afterwards; this is the part of the window the user is already
        watching, so a device that dropped out belongs here. It stays put once
        set — a problem should not scroll away behind the running clock.
        """
        self._warning = message
        self._subtitle.configure(text=message, fg=self._WARNING_FG)

    def set_elapsed(self, seconds):
        """Show how long this recording has been running, unless warning."""
        if self._warning:
            return
        self._subtitle.configure(text=self._elapsed_text(seconds), fg=self._LABEL_ON)

    @staticmethod
    def _elapsed_text(seconds):
        total = int(max(0, seconds))
        clock = f"{total // 3600}:{total // 60 % 60:02d}:{total % 60:02d}"
        return f"{clock} recorded — saved to disk as it goes"

    def clear_warning(self):
        self._warning = ""
        self._subtitle.configure(text=self._SUBTITLE_IDLE, fg=self._LABEL_ON)

    def set_stopping(self):
        """Keep the control visible while the recording is finalized."""
        self._stop_button.configure(state="disabled", text="Stopping…")
        self._subtitle.configure(text="Finalizing the recording…")

    def stop(self):
        self._active = False
        if self._pulse_job is not None:
            self.after_cancel(self._pulse_job)
            self._pulse_job = None
        self.clear_warning()
        self.pack_forget()

    def _schedule_pulse(self):
        if not self._active:
            return
        self._pulse_job = self.after(self._PULSE_MS, self._pulse)

    def _pulse(self):
        if not self._active:
            return
        self._lit = not self._lit
        self._paint_light(self._lit)
        self._schedule_pulse()

    def _paint_light(self, lit):
        self._canvas.itemconfigure(self._light, fill=self._LIGHT_ON if lit else self._LIGHT_OFF)
        self._label.configure(fg=self._LABEL_ON if lit else self._LABEL_OFF)
