"""Agenda / action-item checklist with optional send-to-tasks actions."""

import tkinter as tk
from tkinter import ttk, messagebox

import help_text
from helpers import parse_meeting_date
from task_manager import TaskManager
from widgets.tooltip import attach, attach_all

TITLE_WIDTH = 30
MAX_VISIBLE_ROWS = 5

# Keys this widget owns. Anything else on a saved item (carry-forward
# provenance, for instance) is held untouched and written back out on snapshot,
# so metadata survives a round trip through the UI.
WIDGET_OWNED_KEYS = frozenset({"text", "detail", "checked", "in_tasks", "task_id"})


def carried_badge(item):
    """"↻3 since 24 Jul" for an item that keeps rolling forward, else ""."""
    count = int((item or {}).get("carried_count") or 0)
    if count < 1:
        return ""
    first_raised = str((item or {}).get("first_raised") or "").strip()
    label = f"↻{count}"
    day = parse_meeting_date(first_raised)
    return f"{label} since {day.strftime('%d %b')}" if day else label


class AgendaChecklist(ttk.LabelFrame):
    def __init__(self, master, get_meeting_context=None, on_task_added=None, **kwargs):
        kwargs.setdefault("text", "Agenda / action items (tick when done)")
        kwargs.setdefault("padding", 8)
        super().__init__(master, **kwargs)
        self.get_meeting_context = get_meeting_context or (lambda: {})
        self.on_task_added = on_task_added
        self.item_rows = []

        header = ttk.Frame(self)
        header.pack(fill="x")
        ttk.Label(header, text="", width=3).pack(side="left")
        ttk.Label(header, text="Title", width=TITLE_WIDTH).pack(side="left", padx=4)
        ttk.Label(header, text="Note / detail").pack(side="left", padx=4)

        scroll_area = ttk.Frame(self)
        scroll_area.pack(fill="x", expand=True)
        bg = ttk.Style(self).lookup("TFrame", "background") or self.cget("background")
        self._canvas = tk.Canvas(
            scroll_area, highlightthickness=0, borderwidth=0, background=bg, height=1
        )
        self._scrollbar = ttk.Scrollbar(
            scroll_area, orient="vertical", command=self._canvas.yview
        )
        self._canvas.configure(yscrollcommand=self._scrollbar.set)
        self._canvas.pack(side="left", fill="both", expand=True)

        self.items_container = ttk.Frame(self._canvas)
        self._items_window = self._canvas.create_window(
            (0, 0), window=self.items_container, anchor="nw"
        )
        self.items_container.bind("<Configure>", self._on_items_configure)
        self._canvas.bind(
            "<Configure>",
            lambda e: self._canvas.itemconfigure(self._items_window, width=e.width),
        )
        self._canvas.bind("<MouseWheel>", self._on_mousewheel)

        actions = ttk.Frame(self)
        actions.pack(fill="x", pady=(6, 0))
        add_btn = ttk.Button(actions, text="+ Add item", command=lambda: self.add_item_row())
        add_btn.pack(side="left")
        bulk_btn = ttk.Button(
            actions,
            text="Add unchecked to Tasks",
            command=self.add_unchecked_to_tasks,
        )
        bulk_btn.pack(side="left", padx=(8, 0))
        attach_all([
            (add_btn, help_text.AGENDA_ADD),
            (bulk_btn, help_text.AGENDA_BULK_TO_TASKS),
        ])

    def _on_items_configure(self, _event=None):
        """Grow the canvas with the rows, but cap it at MAX_VISIBLE_ROWS."""
        total = self.items_container.winfo_reqheight()
        rows = len(self.item_rows)
        if rows > MAX_VISIBLE_ROWS:
            visible = int(total * MAX_VISIBLE_ROWS / rows)
            if not self._scrollbar.winfo_ismapped():
                self._scrollbar.pack(side="right", fill="y")
        else:
            visible = total
            if self._scrollbar.winfo_ismapped():
                self._scrollbar.pack_forget()
            self._canvas.yview_moveto(0)
        self._canvas.configure(
            height=max(visible, 1),
            yscrollincrement=max(total // rows, 1) if rows else 1,
            scrollregion=(0, 0, self.items_container.winfo_reqwidth(), total),
        )

    def _on_mousewheel(self, event):
        if len(self.item_rows) > MAX_VISIBLE_ROWS:
            step = -1 if event.delta > 0 else 1
            self._canvas.yview_scroll(step, "units")
        return "break"

    def _bind_wheel(self, widget):
        widget.bind("<MouseWheel>", self._on_mousewheel)
        for child in widget.winfo_children():
            self._bind_wheel(child)

    def _scroll_row_into_view(self, frame):
        self.update_idletasks()
        total = max(self.items_container.winfo_reqheight(), 1)
        top = frame.winfo_y() / total
        bottom = (frame.winfo_y() + frame.winfo_reqheight()) / total
        view_top, view_bottom = self._canvas.yview()
        if top < view_top:
            self._canvas.yview_moveto(top)
        elif bottom > view_bottom:
            self._canvas.yview_moveto(bottom - (view_bottom - view_top))

    @staticmethod
    def _style_tasks_button(button, in_tasks):
        if in_tasks:
            button.configure(
                text="In Tasks",
                state="disabled",
                bg="#2E7D32",
                fg="white",
                disabledforeground="white",
                relief="flat",
            )
        else:
            button.configure(
                text="To Tasks",
                state="normal",
                bg="SystemButtonFace",
                fg="black",
                disabledforeground="black",
                relief="raised",
            )

    def add_item_row(self, text="", checked=False, focus=False, detail="", in_tasks=False,
                     task_id=None, extra=None):
        row = ttk.Frame(self.items_container)
        row.pack(fill="x", pady=1)
        var = tk.BooleanVar(value=checked)
        tick = ttk.Checkbutton(row, variable=var)
        tick.pack(side="left")
        attach(tick, help_text.AGENDA_TICK)
        entry = ttk.Entry(row, width=TITLE_WIDTH)
        entry.insert(0, text)
        entry.pack(side="left", padx=4)
        entry.bind("<Return>", self._on_item_enter)
        detail_entry = ttk.Entry(row)
        detail_entry.insert(0, detail)
        detail_entry.pack(side="left", fill="x", expand=True, padx=4)
        detail_entry.bind("<Return>", self._on_item_enter)
        badge = carried_badge(extra)
        if badge:
            badge_label = tk.Label(row, text=badge, fg="#B36B00", font=("Segoe UI", 8))
            badge_label.pack(side="left", padx=(0, 4))
            attach(badge_label, help_text.agenda_carried(
                int((extra or {}).get("carried_count") or 0),
                str((extra or {}).get("first_raised") or ""),
            ))
        tasks_btn = tk.Button(
            row,
            width=9,
            relief="raised",
            command=lambda r=row: self.add_row_to_tasks(r),
        )
        tasks_btn.pack(side="left", padx=(0, 2))
        attach(tasks_btn, lambda b=tasks_btn: (
            help_text.AGENDA_IN_TASKS if str(b.cget("text")) == "In Tasks"
            else help_text.AGENDA_TO_TASKS
        ))
        remove_btn = ttk.Button(row, text="✕", width=3,
                                command=lambda: self.remove_item_row(row))
        remove_btn.pack(side="left")
        attach(remove_btn, help_text.AGENDA_REMOVE)
        self._bind_wheel(row)
        self.item_rows.append(
            {
                "frame": row,
                "var": var,
                "entry": entry,
                "detail": detail_entry,
                "tasks_btn": tasks_btn,
                "in_tasks": in_tasks,
                "task_id": task_id,
                "extra": dict(extra or {}),
            }
        )
        self._style_tasks_button(tasks_btn, in_tasks)
        if focus:
            entry.focus_set()
            self._scroll_row_into_view(row)
        return entry

    def _on_item_enter(self, event):
        current = event.widget
        idx = next(
            (
                i
                for i, r in enumerate(self.item_rows)
                if current in (r["entry"], r["detail"])
            ),
            None,
        )
        if idx is None or not self.item_rows[idx]["entry"].get().strip():
            return "break"
        if idx + 1 < len(self.item_rows):
            nxt = self.item_rows[idx + 1]["entry"]
            if not nxt.get().strip():
                nxt.focus_set()
                self._scroll_row_into_view(self.item_rows[idx + 1]["frame"])
                return "break"
        self.add_item_row(focus=True)
        return "break"

    def remove_item_row(self, row):
        self.item_rows = [r for r in self.item_rows if r["frame"] is not row]
        row.destroy()

    def clear_item_rows(self):
        for r in list(self.item_rows):
            r["frame"].destroy()
        self.item_rows = []

    def set_items(self, items):
        self.clear_item_rows()
        if not items:
            items = [{"text": "", "detail": "", "checked": False}]
        for it in items:
            self.add_item_row(
                it.get("text", ""),
                it.get("checked", False),
                detail=it.get("detail", ""),
                in_tasks=it.get("in_tasks", False),
                task_id=it.get("task_id"),
                extra={k: v for k, v in it.items() if k not in WIDGET_OWNED_KEYS},
            )
        self._canvas.yview_moveto(0)

    def get_snapshot_items(self):
        items = []
        for r in self.item_rows:
            item = dict(r["extra"])
            item.update({
                "text": r["entry"].get().strip(),
                "detail": r["detail"].get().strip(),
                "checked": bool(r["var"].get()),
                "in_tasks": bool(r["in_tasks"]),
            })
            if r["task_id"] is not None:
                item["task_id"] = r["task_id"]
            items.append(item)
        return items

    def get_filled_items(self):
        return [item for item in self.get_snapshot_items() if item["text"]]

    def _task_notes(self, detail=""):
        context = self.get_meeting_context() or {}
        person = (context.get("person") or "").strip()
        meeting_date = (context.get("date") or "").strip()
        bits = []
        if person:
            bits.append(f"From meeting with {person}")
        if meeting_date:
            bits.append(f"on {meeting_date}")
        source = " ".join(bits)
        detail = (detail or "").strip()
        return "\n\n".join(part for part in (detail, source) if part)

    def add_row_to_tasks(self, row):
        item = next((r for r in self.item_rows if r["frame"] is row), None)
        if item is None or item["in_tasks"]:
            return
        title = item["entry"].get().strip()
        if not title:
            messagebox.showinfo(
                "Empty item",
                "Give the agenda item a title before adding it to Tasks.",
                parent=self.winfo_toplevel(),
            )
            return
        item["task_id"] = TaskManager.create_task(
            title, notes=self._task_notes(item["detail"].get())
        )
        item["in_tasks"] = True
        self._style_tasks_button(item["tasks_btn"], True)
        if self.on_task_added:
            self.on_task_added(title)

    def add_unchecked_to_tasks(self):
        candidates = [
            r
            for r in self.item_rows
            if r["entry"].get().strip() and not r["var"].get() and not r["in_tasks"]
        ]
        if not candidates:
            messagebox.showinfo(
                "Nothing to add",
                "No unchecked agenda items to send to Tasks.",
                parent=self.winfo_toplevel(),
            )
            return
        for r in candidates:
            r["task_id"] = TaskManager.create_task(
                r["entry"].get().strip(), notes=self._task_notes(r["detail"].get())
            )
            r["in_tasks"] = True
            self._style_tasks_button(r["tasks_btn"], True)
        if self.on_task_added:
            self.on_task_added(f"{len(candidates)} item(s)")
        messagebox.showinfo(
            "Added to Tasks",
            f"Added {len(candidates)} item(s) to your Tasks list.",
            parent=self.winfo_toplevel(),
        )
