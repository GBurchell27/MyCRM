"""Meeting notes tab."""

import csv
import tkinter as tk
from tkinter import ttk, messagebox

import attendees
from db import get_conn
import help_text
from dialogs.meeting_dialog import MeetingDialog
from dialogs.recurring_meetings_manager import RecurringMeetingsManager
from excel_export import format_agenda_text, write_meetings_workbook
from helpers import (
    truncate,
    agenda_item_line,
    agenda_progress_label,
    parse_agenda_items,
    meeting_schedule_tag,
    format_meeting_date_label,
)
from hover_preview import TreeHoverPreview
from meeting_window import field
from widgets.tooltip import attach_all


class MeetingsTab(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=8)
        self.all_rows = []

        top = ttk.Frame(self)
        top.pack(fill="x", pady=(0, 6))

        ttk.Style(self).configure(
            "Primary.TButton",
            font=("Segoe UI", 9, "bold"),
            padding=(12, 6),
        )
        add_btn = ttk.Button(
            top,
            text="Add Meeting Note",
            command=self.add_meeting,
            style="Primary.TButton",
        )
        add_btn.pack(side="left")
        recurring_btn = ttk.Button(
            top, text="Recurring meetings…", command=self.manage_recurring_meetings
        )
        recurring_btn.pack(side="left", padx=(8, 4))
        edit_btn = ttk.Button(top, text="Edit", command=self.edit_meeting)
        edit_btn.pack(side="left", padx=(0, 4))
        delete_btn = ttk.Button(top, text="Delete", command=self.delete_meeting)
        delete_btn.pack(side="left")
        attach_all([
            (add_btn, help_text.MEETINGS_ADD),
            (recurring_btn, help_text.MEETINGS_RECURRING),
            (edit_btn, help_text.MEETINGS_EDIT),
            (delete_btn, help_text.MEETINGS_DELETE),
        ])

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *a: self.refresh())
        ttk.Entry(top, textvariable=self.search_var, width=30).pack(side="right")
        ttk.Label(top, text="Search:").pack(side="right", padx=(0, 4))

        columns = ("date", "person", "agenda", "summary", "notes")
        headings = ["Date", "People", "Agenda progress", "AI summary", "My notes"]
        self.tree = ttk.Treeview(self, columns=columns, show="headings", selectmode="browse")
        widths = [150, 140, 120, 240, 240]
        for col, heading, w in zip(columns, headings, widths):
            self.tree.heading(col, text=heading)
            self.tree.column(col, width=w, anchor="w")
        self.tree.tag_configure(
            "future",
            foreground="#0B5FFF",
            font=("Segoe UI", 9, "bold"),
        )
        self.tree.tag_configure(
            "today",
            foreground="#0A7A3E",
            font=("Segoe UI", 9, "bold"),
        )
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda e: self.edit_meeting())
        self.hover_preview = TreeHoverPreview(self.tree, self.preview_fields)

        self.refresh()

    def load_rows(self):
        conn = get_conn()
        rows = conn.execute("SELECT * FROM meetings ORDER BY date DESC, id DESC").fetchall()
        conn.close()
        return rows

    def refresh(self):
        self.all_rows = self.load_rows()
        query = self.search_var.get().strip().lower()
        for i in self.tree.get_children():
            self.tree.delete(i)
        for row in self.all_rows:
            if query and not self._matches_person(row, query):
                continue
            schedule_tag = meeting_schedule_tag(row["date"])
            tags = (schedule_tag,) if schedule_tag else ()
            self.tree.insert(
                "",
                "end",
                iid=str(row["id"]),
                tags=tags,
                values=(
                    format_meeting_date_label(row["date"]),
                    attendees.describe(row["person"]),
                    agenda_progress_label(row["agenda_items"]),
                    truncate(row["ai_summary"]),
                    truncate(row["notes"]),
                ),
            )

    @staticmethod
    def _matches_person(row, query):
        """Search hits a group meeting through any one of its people."""
        return any(query in name.lower() for name in attendees.parse(row["person"]))

    def preview_fields(self, iid):
        try:
            mid = int(iid)
        except ValueError:
            return None
        for row in self.all_rows:
            if row["id"] == mid:
                items = parse_agenda_items(row["agenda_items"])
                agenda = "\n".join(agenda_item_line(it) for it in items)
                return [
                    ("Date", row["date"]),
                    ("People", attendees.describe(row["person"])),
                    ("Agenda", agenda),
                    ("AI summary", row["ai_summary"]),
                    ("My notes", row["notes"]),
                ]
        return None

    def get_selected_meeting(self):
        sel = self.tree.selection()
        if not sel:
            focused = self.tree.focus()
            if not focused:
                return None
            sel = (focused,)
        mid = int(sel[0])
        for row in self.all_rows:
            if row["id"] == mid:
                return row
        return None

    def add_meeting(self):
        MeetingDialog(self, on_save=self.save_meeting)

    def manage_recurring_meetings(self):
        RecurringMeetingsManager(self, on_changed=self.refresh)

    def edit_meeting(self):
        meeting = self.get_selected_meeting()
        if not meeting:
            messagebox.showinfo(
                "No selection",
                "Select a meeting note to edit first.",
                parent=self,
            )
            return
        existing = self._find_open_editor(meeting["id"])
        if existing is not None:
            existing.deiconify()
            existing.lift()
            existing.focus_force()
            return
        MeetingDialog(self, on_save=self.save_meeting, meeting=meeting)

    def _find_open_editor(self, meeting_id):
        """The already-open MeetingDialog editing this meeting, if any."""
        finder = getattr(self.winfo_toplevel(), "open_meeting_dialogs", None)
        if finder is None:
            return None
        for dialog in finder():
            try:
                if (
                    dialog.winfo_exists()
                    and dialog.meeting is not None
                    and dialog.meeting["id"] == meeting_id
                ):
                    return dialog
            except tk.TclError:
                continue
        return None

    def delete_meeting(self):
        meeting = self.get_selected_meeting()
        if not meeting:
            messagebox.showinfo(
                "No selection",
                "Select a meeting note to delete first.",
                parent=self,
            )
            return
        person = attendees.describe(meeting["person"]) or "(no person)"
        meeting_date = meeting["date"] or "(no date)"
        confirmed = messagebox.askyesno(
            "Delete meeting note",
            f"Delete the meeting with {person} on {meeting_date}?\n\nThis cannot be undone.",
            parent=self,
            icon="warning",
        )
        if not confirmed:
            return
        conn = get_conn()
        conn.execute("DELETE FROM meetings WHERE id=?", (meeting["id"],))
        conn.commit()
        conn.close()
        self.refresh()

    def save_meeting(self, data, meeting_id):
        conn = get_conn()
        if meeting_id:
            conn.execute("""UPDATE meetings
                            SET date=?, person=?, agenda_items=?, ai_summary=?, notes=?,
                                transcript=?, media_paths=?
                             WHERE id=?""",
                         (
                             data["date"],
                             data["person"],
                             data["agenda_items"],
                             data["ai_summary"],
                             data["notes"],
                             data.get("transcript", ""),
                             data.get("media_paths", ""),
                             meeting_id,
                         ))
        else:
            conn.execute("""INSERT INTO meetings
                            (date, person, agenda_items, ai_summary, notes,
                             transcript, media_paths)
                            VALUES (?, ?, ?, ?, ?, ?, ?)""",
                         (
                             data["date"],
                             data["person"],
                             data["agenda_items"],
                             data["ai_summary"],
                             data["notes"],
                             data.get("transcript", ""),
                             data.get("media_paths", ""),
                         ))
        conn.commit()
        conn.close()
        self.refresh()

    def export_csv(self, path):
        rows = self.load_rows()
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Date", "People", "Agenda items", "Catch-up brief", "AI summary", "My notes",
            ])
            for row in rows:
                writer.writerow([
                    row["date"],
                    attendees.describe(row["person"]),
                    format_agenda_text(row["agenda_items"]),
                    field(row, "catchup_brief"),
                    row["ai_summary"],
                    row["notes"],
                ])

    def export_excel(self, path):
        write_meetings_workbook(path, self.load_rows())
