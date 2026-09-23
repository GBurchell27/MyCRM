"""Read-only window showing the raw transcript for one meeting note."""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText


class TranscriptWindow(tk.Toplevel):
    """Separate window so the transcript can sit alongside the meeting note."""

    def __init__(self, master, text, title="Raw transcript"):
        super().__init__(master)
        self.title(title)
        self.geometry("720x640")
        self.minsize(420, 320)
        self._text = text or ""

        body = ttk.Frame(self, padding=10)
        body.pack(fill="both", expand=True)
        self.text_box = ScrolledText(body, wrap="word", font=("Segoe UI", 10))
        self.text_box.pack(fill="both", expand=True)
        self.text_box.insert("1.0", self._text)
        self.text_box.configure(state="disabled")

        footer = ttk.Frame(self, padding=(10, 0, 10, 10))
        footer.pack(fill="x")
        ttk.Button(footer, text="Copy all", command=self.copy_all).pack(side="left")
        ttk.Button(footer, text="Save as…", command=self.save_as).pack(side="left", padx=6)
        ttk.Button(footer, text="Close", command=self.destroy).pack(side="right")
        self.bind("<Escape>", lambda _e: self.destroy())

    def copy_all(self):
        self.clipboard_clear()
        self.clipboard_append(self._text)

    def save_as(self):
        path = filedialog.asksaveasfilename(
            parent=self,
            defaultextension=".txt",
            filetypes=[("Text file", "*.txt"), ("All files", "*.*")],
            initialfile="transcript.txt",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(self._text)
        except OSError as exc:
            messagebox.showerror("Could not save", str(exc), parent=self)
