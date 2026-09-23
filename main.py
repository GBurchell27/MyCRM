"""
Personal CRM + Meeting Notes desktop app
-----------------------------------------
- Three tabs: CRM (contacts), Meeting Notes, and Tasks
- People memory: Person/Name/Manager dropdowns from CRM + past meetings
- Meeting capture: mic recording + active-window activity log
- AI Summarize in the meeting editor: summary, highlights, action items
- Saving a meeting with someone new opens a pre-filled Add Contact dialog,
  with their team/role/manager read out of the transcript by AI
- Tasks: active list with input, completed items move to history
- Meeting agenda items can be sent to the Tasks list
- Data stored locally in crm_data.db (SQLite), next to this script

Requirements: Python 3.8+ (tkinter included on Windows)
Optional AI/recording: pip install -r requirements.txt
Run with:  python main.py
"""

import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox, filedialog

from dotenv import load_dotenv

import help_text
from config.app_settings import STARTUP_TAB, TAB_CRM, TAB_MEETINGS, TAB_TASKS
from db import init_db, APP_DIR
from recurring_meetings import RecurringMeetingManager
from tabs.crm_tab import CRMTab
from tabs.meetings_tab import MeetingsTab
from tabs.tasks_tab import TasksTab
from dialogs.meeting_dialog import MeetingDialog
from dialogs.settings import SettingsDialog
from widgets.settings_cog import SettingsCog

load_dotenv()

APP_ICON_PATH = Path(__file__).resolve().parent / "assets" / "app.ico"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MyCRM")
        self.geometry("1100x650")
        self._set_app_icon()

        self._configure_main_tabs_style()

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True)

        self.crm_tab = CRMTab(notebook)
        self.meetings_tab = MeetingsTab(notebook)
        self.tasks_tab = TasksTab(notebook)
        notebook.add(self.crm_tab, text="CRM")
        notebook.add(self.meetings_tab, text="Meeting Notes")
        notebook.add(self.tasks_tab, text="Tasks")
        notebook.select(self.startup_tab())

        self.settings_cog = SettingsCog(
            self, command=self.open_settings, help_text=help_text.SETTINGS_COG
        )
        self.settings_cog.attach_to(notebook, self.crm_tab)

        menubar = tk.Menu(self)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Export CRM to CSV...", command=self.export_crm)
        file_menu.add_command(label="Export Meeting Notes to CSV...", command=self.export_meetings)
        file_menu.add_command(label="Export CRM to Excel...", command=self.export_crm_excel)
        file_menu.add_command(
            label="Export Meeting Notes to Excel...",
            command=self.export_meetings_excel,
        )
        file_menu.add_separator()
        file_menu.add_command(
            label="Settings...", accelerator="Ctrl+,", command=self.open_settings
        )
        file_menu.add_command(label="Open data folder", command=self.open_data_folder)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.request_quit)
        menubar.add_cascade(label="File", menu=file_menu)
        self.config(menu=menubar)
        self.bind_all("<Control-comma>", lambda _event: self.open_settings())
        self.protocol("WM_DELETE_WINDOW", self.request_quit)

    def startup_tab(self):
        tabs = {
            TAB_CRM: self.crm_tab,
            TAB_MEETINGS: self.meetings_tab,
            TAB_TASKS: self.tasks_tab,
        }
        return tabs.get(STARTUP_TAB.get(), self.meetings_tab)

    def _set_app_icon(self):
        if not APP_ICON_PATH.exists():
            return
        try:
            # Windows: .ico covers title bar and taskbar for pythonw/python runs
            self.iconbitmap(default=str(APP_ICON_PATH))
        except tk.TclError:
            pass
        if sys.platform == "win32":
            try:
                import ctypes

                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                    "MyCRM.App"
                )
            except Exception:
                pass

    def _configure_main_tabs_style(self):
        style = ttk.Style(self)
        style.configure(
            "TNotebook",
            tabmargins=(6, 6, 6, 0),
        )
        style.configure(
            "TNotebook.Tab",
            font=("Segoe UI", 11, "bold"),
            padding=(22, 10),
        )
        style.map(
            "TNotebook.Tab",
            expand=[("selected", (1, 1, 1, 0))],
        )

    def open_meeting_dialogs(self):
        found = []
        stack = [self]
        while stack:
            widget = stack.pop()
            try:
                children = widget.winfo_children()
            except tk.TclError:
                continue
            for child in children:
                if isinstance(child, MeetingDialog):
                    found.append(child)
                else:
                    stack.append(child)
        return found

    def request_quit(self):
        for dialog in list(self.open_meeting_dialogs()):
            try:
                if dialog.winfo_exists() and not dialog.try_close():
                    return
            except tk.TclError:
                continue
        self.destroy()

    def export_crm(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            initialfile="crm_export.csv",
        )
        if path:
            self.crm_tab.export_csv(path)
            messagebox.showinfo("Exported", f"CRM exported to:\n{path}")

    def export_meetings(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            initialfile="meeting_notes_export.csv",
        )
        if path:
            self.meetings_tab.export_csv(path)
            messagebox.showinfo("Exported", f"Meeting notes exported to:\n{path}")

    def export_crm_excel(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel workbook", "*.xlsx")],
            initialfile="crm_export.xlsx",
        )
        if not path:
            return
        try:
            self.crm_tab.export_excel(path)
        except RuntimeError as exc:
            messagebox.showerror("Export failed", str(exc))
            return
        messagebox.showinfo("Exported", f"CRM exported to:\n{path}")

    def export_meetings_excel(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel workbook", "*.xlsx")],
            initialfile="meeting_notes_export.xlsx",
        )
        if not path:
            return
        try:
            self.meetings_tab.export_excel(path)
        except RuntimeError as exc:
            messagebox.showerror("Export failed", str(exc))
            return
        messagebox.showinfo("Exported", f"Meeting notes exported to:\n{path}")

    def open_settings(self):
        SettingsDialog(self)

    def open_data_folder(self):
        os.startfile(APP_DIR)


if __name__ == "__main__":
    init_db()
    RecurringMeetingManager.top_up_all()
    app = App()
    app.mainloop()
