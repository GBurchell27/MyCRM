"""Tasks tab: active task input on the left, completed history on the right."""

import tkinter as tk
from tkinter import ttk, messagebox

import help_text
from dialogs.email_dialog import EmailDialog
from dialogs.outsource_dialog import OutsourceDialog
from dialogs.progress_report_dialog import ProgressReportDialog
from dialogs.task_dialog import TaskDialog
from helpers import truncate
from hover_preview import TreeHoverPreview
from task_group_collapse import CollapsedTaskGroups
from task_manager import TaskManager
from widgets.dictation_button import DictationButton
from widgets.quick_tag_picker import QuickTagPicker
from widgets.tag_field import TagField
from widgets.task_group_heading import TaskGroupHeading
from widgets.tooltip import attach_all


class TasksTab(ttk.Frame):
    HISTORY_COLUMNS = ("completed_at", "tag", "title", "notes", "created_at")
    HISTORY_HEADINGS = ["Completed", "Tag", "Title", "Notes", "Created"]
    ALL_TAGS = "All tags"
    UNTAGGED_HEADING = "Needs a tag"
    COLLAPSE_ALL_LABEL = "⊟ Collapse all"
    EXPAND_ALL_LABEL = "⊞ Expand all"

    def __init__(self, master):
        super().__init__(master, padding=8)
        self.active_rows = []
        self.history_rows = []
        self.selected_active_id = None
        self._check_vars = {}
        self._known_tags = []
        # The tag most recently filed from the list, offered as a one-click
        # repeat on the next untagged row — untagged work arrives in batches.
        self._last_quick_tag = ""
        # Which projects are rolled up. Persisted, so the list opens tomorrow
        # the way you left it today.
        self._collapsed_groups = CollapsedTaskGroups()

        style = ttk.Style(self)
        style.configure("Trash.TButton", foreground="#B71C1C", padding=(2, 0))

        paned = ttk.Panedwindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True)

        left = ttk.Frame(paned, padding=(0, 0, 8, 0))
        right = ttk.Frame(paned, padding=(8, 0, 0, 0))
        paned.add(left, weight=1)
        paned.add(right, weight=1)

        self._build_active_panel(left)
        self._build_history_panel(right)
        self.refresh()

    def _build_active_panel(self, parent):
        ttk.Label(parent, text="Active tasks", font=("Segoe UI", 11, "bold")).pack(
            anchor="w", pady=(0, 6)
        )

        form = ttk.LabelFrame(parent, text="New task", padding=8)
        form.pack(fill="x", pady=(0, 8))

        ttk.Label(form, text="Title").grid(row=0, column=0, sticky="w")
        self.title_var = tk.StringVar()
        title_entry = ttk.Entry(form, textvariable=self.title_var)
        title_entry.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        title_entry.bind("<Return>", lambda e: self.add_task())
        DictationButton(form, title_entry, single_line=True).grid(
            row=1, column=1, padx=(4, 0), pady=(0, 6)
        )

        ttk.Label(form, text="Notes (optional)").grid(row=2, column=0, sticky="w")
        self.notes_var = tk.StringVar()
        notes_entry = ttk.Entry(form, textvariable=self.notes_var)
        notes_entry.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        notes_entry.bind("<Return>", lambda e: self.add_task())
        DictationButton(form, notes_entry, single_line=True).grid(
            row=3, column=1, padx=(4, 0), pady=(0, 8)
        )

        ttk.Label(form, text="Project / tag (optional)").grid(row=4, column=0, sticky="w")
        self.tag_field = TagField(form)
        self.tag_field.grid(row=5, column=0, sticky="ew", pady=(0, 8))
        self.tag_field.bind("<Return>", lambda e: self.add_task())
        attach_all([(self.tag_field, help_text.TASK_TAG)])

        form.columnconfigure(0, weight=1)
        ttk.Button(form, text="Add Task", command=self.add_task).grid(
            row=6, column=0, columnspan=2, sticky="e"
        )

        toolbar = ttk.Frame(parent)
        toolbar.pack(fill="x", pady=(0, 6))
        ttk.Label(
            toolbar,
            text="Check a box to complete · click a task to edit · 🗑 to delete",
            foreground="#555555",
        ).pack(side="left")

        self.filter_var = tk.StringVar(value=self.ALL_TAGS)
        self.filter_combo = ttk.Combobox(
            toolbar,
            textvariable=self.filter_var,
            state="readonly",
            width=18,
            values=[self.ALL_TAGS],
        )
        self.filter_combo.pack(side="right")
        self.filter_combo.bind(
            "<<ComboboxSelected>>", lambda e: self._rebuild_active_list()
        )
        ttk.Label(toolbar, text="Show:", foreground="#555555").pack(
            side="right", padx=(0, 4)
        )
        self.collapse_all_button = ttk.Button(
            toolbar, text=self.COLLAPSE_ALL_LABEL, command=self._toggle_all_groups
        )
        self.collapse_all_button.pack(side="right", padx=(0, 10))
        attach_all([
            (self.filter_combo, help_text.TASK_TAG_FILTER),
            (self.collapse_all_button, help_text.TASK_COLLAPSE_ALL),
        ])

        list_wrap = ttk.Frame(parent)
        list_wrap.pack(fill="both", expand=True)
        self.active_canvas = tk.Canvas(list_wrap, highlightthickness=0)
        scrollbar = ttk.Scrollbar(
            list_wrap, orient="vertical", command=self.active_canvas.yview
        )
        self.active_list = ttk.Frame(self.active_canvas)
        self.active_list.bind(
            "<Configure>",
            lambda e: self.active_canvas.configure(
                scrollregion=self.active_canvas.bbox("all")
            ),
        )
        self._list_window = self.active_canvas.create_window(
            (0, 0), window=self.active_list, anchor="nw"
        )
        self.active_canvas.configure(yscrollcommand=scrollbar.set)
        self.active_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.active_canvas.bind("<Configure>", self._on_canvas_configure)
        self.active_canvas.bind("<Enter>", self._bind_mousewheel)
        self.active_canvas.bind("<Leave>", self._unbind_mousewheel)

    def _build_history_panel(self, parent):
        header = ttk.Frame(parent)
        header.pack(fill="x", pady=(0, 6))
        ttk.Label(header, text="History", font=("Segoe UI", 11, "bold")).pack(side="left")
        ttk.Label(
            header,
            text="Click a row to edit · select + ↩ to put it back · 🗑 to delete",
            foreground="#555555",
        ).pack(side="left", padx=(10, 0))
        delete_btn = ttk.Button(
            header,
            text="🗑 Delete",
            style="Trash.TButton",
            command=self.delete_history_task,
        )
        delete_btn.pack(side="right")
        reopen_btn = ttk.Button(
            header,
            text="↩ Reopen",
            command=self.reopen_history_task,
        )
        reopen_btn.pack(side="right", padx=(0, 6))
        summarise_btn = ttk.Button(
            header,
            text="✦ AI summarise",
            command=self.open_progress_report,
        )
        summarise_btn.pack(side="right", padx=(0, 6))
        attach_all([
            (delete_btn, help_text.TASK_DELETE),
            (reopen_btn, help_text.TASK_REOPEN),
            (summarise_btn, help_text.PROGRESS_OPEN),
        ])

        self.history_tree = ttk.Treeview(
            parent,
            columns=self.HISTORY_COLUMNS,
            show="headings",
            selectmode="browse",
        )
        for col, heading in zip(self.HISTORY_COLUMNS, self.HISTORY_HEADINGS):
            self.history_tree.heading(col, text=heading)
            width = 120 if col in ("completed_at", "created_at") else 160
            if col == "notes":
                width = 180
            if col == "tag":
                width = 110
            self.history_tree.column(col, width=width, anchor="w")
        self.history_tree.pack(fill="both", expand=True)
        self.history_tree.bind("<ButtonRelease-1>", self._on_history_clicked)
        self.history_tree.bind("<Delete>", self.delete_history_task)
        self.history_tree.bind("<Button-3>", self._on_history_right_click)
        self.history_menu = tk.Menu(self, tearoff=0)
        self.history_menu.add_command(
            label="↩ Reopen task", command=self.reopen_history_task
        )
        self.history_menu.add_separator()
        self.history_menu.add_command(
            label="Delete task", command=self.delete_history_task
        )
        self.history_hover = TreeHoverPreview(
            self.history_tree, self.history_preview_fields
        )

    def _on_canvas_configure(self, event):
        self.active_canvas.itemconfigure(self._list_window, width=event.width)

    def _bind_mousewheel(self, _event=None):
        self.active_canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _unbind_mousewheel(self, _event=None):
        self.active_canvas.unbind_all("<MouseWheel>")

    def _on_mousewheel(self, event):
        self.active_canvas.yview_scroll(int(-event.delta / 120), "units")

    def refresh(self):
        self.active_rows = TaskManager.list_active()
        self.history_rows = TaskManager.list_history()
        self._refresh_tag_choices()
        self._rebuild_active_list()

        for i in self.history_tree.get_children():
            self.history_tree.delete(i)
        for row in self.history_rows:
            self.history_tree.insert(
                "",
                "end",
                iid=str(row["id"]),
                values=(
                    row["completed_at"],
                    row["tag"] or "",
                    row["title"],
                    truncate(row["notes"]),
                    row["created_at"],
                ),
            )

    def _refresh_tag_choices(self):
        """Keep the new-task picker and the filter in step with the tags in use."""
        self.tag_field.refresh_choices()
        tags = TaskManager.list_tags()
        self._known_tags = tags
        self.filter_combo.configure(values=[self.ALL_TAGS] + tags)
        if self.filter_var.get() not in tags:
            self.filter_var.set(self.ALL_TAGS)

    def _rebuild_active_list(self):
        for child in self.active_list.winfo_children():
            child.destroy()
        self._check_vars = {}
        if self.selected_active_id and not any(
            row["id"] == self.selected_active_id for row in self.active_rows
        ):
            self.selected_active_id = None

        visible_rows = self._visible_active_rows()
        if not visible_rows:
            ttk.Label(
                self.active_list,
                text=self._empty_list_message(),
                foreground="#777777",
            ).pack(anchor="w", pady=8)
            return

        # Once any project exists the headings stay on, so a list that happens to
        # be all-untagged still reads as "these need filing" rather than as normal.
        groups = TaskManager.group_by_tag(visible_rows)
        show_headings = len(groups) > 1 or bool(self._known_tags)
        self._update_collapse_all_button([tag for tag, _ in groups], show_headings)
        for tag, rows in groups:
            collapsed = show_headings and self._is_group_collapsed(tag)
            if show_headings:
                self._add_group_heading(tag, len(rows), collapsed)
            if collapsed:
                continue
            for row in rows:
                self._add_active_row(row)

    def _visible_active_rows(self):
        chosen_tag = self.filter_var.get()
        if chosen_tag == self.ALL_TAGS:
            return list(self.active_rows)
        return [row for row in self.active_rows if (row["tag"] or "") == chosen_tag]

    def _empty_list_message(self):
        chosen_tag = self.filter_var.get()
        if chosen_tag != self.ALL_TAGS:
            return f"No active tasks tagged “{chosen_tag}”."
        return "No active tasks yet."

    def _add_group_heading(self, tag, task_count, collapsed):
        """One heading per project, so the list reads as groups not one long run."""
        heading = TaskGroupHeading(
            self.active_list,
            tag=tag,
            task_count=task_count,
            collapsed=collapsed,
            on_toggle=self._toggle_group,
        )
        heading.pack(fill="x", pady=(8, 0))
        ttk.Separator(self.active_list, orient="horizontal").pack(fill="x", pady=(1, 2))

    def _is_group_collapsed(self, tag):
        """Filtering to one project always shows it: you asked for that group."""
        if self.filter_var.get() != self.ALL_TAGS:
            return False
        return self._collapsed_groups.is_collapsed(tag)

    def _toggle_group(self, tag):
        self._collapsed_groups.toggle(tag)
        self._rebuild_keeping_scroll()

    def _toggle_all_groups(self):
        """One button for "show me the projects" and "show me the work"."""
        tags = [tag for tag, _ in TaskManager.group_by_tag(self._visible_active_rows())]
        if self._collapsed_groups.all_collapsed(tags):
            self._collapsed_groups.expand_all(tags)
        else:
            self._collapsed_groups.collapse_all(tags)
        self._rebuild_keeping_scroll()

    def _update_collapse_all_button(self, tags, show_headings):
        collapsible = show_headings and bool(tags)
        self.collapse_all_button.configure(
            state="normal" if collapsible else "disabled",
            text=(
                self.EXPAND_ALL_LABEL
                if collapsible and self._collapsed_groups.all_collapsed(tags)
                else self.COLLAPSE_ALL_LABEL
            ),
        )

    def _rebuild_keeping_scroll(self):
        """Redraw in place; Tk clamps the offset when the list gets shorter."""
        position = self.active_canvas.yview()[0]
        self._rebuild_active_list()
        self.active_canvas.after_idle(lambda: self.active_canvas.yview_moveto(position))

    def _add_active_row(self, row):
        task_id = row["id"]
        row_frame = ttk.Frame(self.active_list, padding=(4, 4))
        row_frame.pack(fill="x", pady=1)

        var = tk.BooleanVar(value=False)
        self._check_vars[task_id] = var
        tick = ttk.Checkbutton(
            row_frame,
            variable=var,
            command=lambda tid=task_id: self._on_checkbox_toggled(tid),
        )
        tick.pack(side="left", padx=(0, 6))

        trash = ttk.Button(
            row_frame,
            text="🗑",
            width=3,
            style="Trash.TButton",
            command=lambda tid=task_id: self.delete_active_task(tid),
        )
        trash.pack(side="right", padx=(6, 0))

        outsource = ttk.Button(
            row_frame,
            text="→ Claude",
            width=9,
            command=lambda tid=task_id: self._outsource_task(tid),
        )
        outsource.pack(side="right", padx=(6, 0))

        email = ttk.Button(
            row_frame,
            text="✉ Email",
            width=8,
            command=lambda tid=task_id: self._email_task(tid),
        )
        email.pack(side="right", padx=(6, 0))

        tips = [
            (tick, help_text.TASK_COMPLETE),
            (trash, help_text.TASK_DELETE),
            (outsource, help_text.TASK_OUTSOURCE),
            (email, help_text.TASK_EMAIL),
        ]
        if not (row["tag"] or ""):
            picker = self._add_quick_tag_picker(row_frame, task_id)
            tips.append((picker, help_text.TASK_QUICK_TAG))
        attach_all(tips)

        text_frame = ttk.Frame(row_frame)
        text_frame.pack(side="left", fill="x", expand=True)

        title = ttk.Label(
            text_frame,
            text=row["title"] or "",
            font=("Segoe UI", 10),
            cursor="hand2",
        )
        title.pack(anchor="w")
        meta_bits = [row["created_at"] or ""]
        if row["notes"]:
            meta_bits.append(truncate(row["notes"], 80))
        meta = ttk.Label(
            text_frame,
            text=" · ".join(bit for bit in meta_bits if bit),
            foreground="#666666",
            cursor="hand2",
        )
        meta.pack(anchor="w")

        for widget in (text_frame, title, meta):
            widget.bind("<Button-1>", lambda e, tid=task_id: self._on_task_clicked(tid))

    def _add_quick_tag_picker(self, row_frame, task_id):
        """Untagged rows carry their own filing control, so filing costs no dialog."""
        picker = QuickTagPicker(
            row_frame,
            choices=self._known_tags,
            on_assign=lambda tag, tid=task_id: self._quick_tag_task(tid, tag),
            repeat_tag=self._last_quick_tag,
        )
        picker.pack(side="right", padx=(6, 0))
        return picker

    def _quick_tag_task(self, task_id, tag):
        """File one task from the list and leave the list where it was."""
        TaskManager.set_tag(task_id, tag)
        self._last_quick_tag = TaskManager.canonical_tag(tag)
        self._refresh_keeping_scroll()

    def _refresh_keeping_scroll(self):
        """Refresh without throwing you back to the top mid-way down a batch."""
        position = self.active_canvas.yview()[0]
        self.refresh()
        self.active_canvas.after_idle(lambda: self.active_canvas.yview_moveto(position))

    def open_progress_report(self):
        ProgressReportDialog(self)

    def _outsource_task(self, task_id):
        task = self._row_by_id(self.active_rows, task_id)
        if task:
            OutsourceDialog(self, task)

    def _email_task(self, task_id):
        task = self._row_by_id(self.active_rows, task_id)
        if task:
            EmailDialog(self, task)

    def _on_task_clicked(self, task_id):
        self.selected_active_id = task_id
        task = self._row_by_id(self.active_rows, task_id)
        if task:
            TaskDialog(self, on_save=self.save_task, task=task)

    def _on_history_clicked(self, event):
        if self.history_tree.identify_region(event.x, event.y) != "cell":
            return
        iid = self.history_tree.identify_row(event.y)
        if not iid:
            return
        task = self._row_by_id(self.history_rows, iid)
        if task:
            TaskDialog(self, on_save=self.save_task, task=task)

    def _on_history_right_click(self, event):
        iid = self.history_tree.identify_row(event.y)
        if not iid:
            return
        self.history_tree.selection_set(iid)
        self.history_tree.focus(iid)
        try:
            self.history_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.history_menu.grab_release()

    def _on_checkbox_toggled(self, task_id):
        var = self._check_vars.get(task_id)
        if not var or not var.get():
            return
        self.complete_task(task_id)

    def _row_by_id(self, rows, task_id):
        try:
            tid = int(task_id)
        except (TypeError, ValueError):
            return None
        for row in rows:
            if row["id"] == tid:
                return row
        return None

    def get_selected_active(self):
        if self.selected_active_id is None:
            return None
        return self._row_by_id(self.active_rows, self.selected_active_id)

    def get_selected_history(self):
        sel = self.history_tree.selection()
        if not sel:
            return None
        return self._row_by_id(self.history_rows, sel[0])

    def history_preview_fields(self, iid):
        row = self._row_by_id(self.history_rows, iid)
        if not row:
            return None
        return [
            (heading, row[col])
            for col, heading in zip(self.HISTORY_COLUMNS, self.HISTORY_HEADINGS)
        ]

    def add_task(self):
        title = self.title_var.get().strip()
        if not title:
            messagebox.showinfo("Missing title", "Enter a task title first.")
            return
        TaskManager.create_task(
            title,
            notes=self.notes_var.get().strip(),
            tag=self.tag_field.tag(),
        )
        self.title_var.set("")
        self.notes_var.set("")
        # The tag stays put: tasks for one project usually arrive in a batch.
        self.refresh()

    def save_task(self, data, task_id):
        TaskManager.update_task(
            task_id, data["title"], notes=data["notes"], tag=data.get("tag", "")
        )
        self.refresh()

    def complete_task(self, task_id):
        TaskManager.complete_task(task_id)
        if self.selected_active_id == task_id:
            self.selected_active_id = None
        self.refresh()

    def reopen_history_task(self, _event=None):
        task = self.get_selected_history()
        if not task:
            messagebox.showinfo(
                "No selection",
                "Select the completed task you want back on the active list.",
            )
            return
        self.reopen_task(task["id"])

    def reopen_task(self, task_id):
        """Put a completed task back. No confirmation: ticking it again undoes it."""
        TaskManager.reopen_task(task_id)
        self.selected_active_id = task_id
        self.refresh()

    def _confirm_delete(self, task, what="task"):
        return messagebox.askyesno(
            f"Delete {what}",
            f"Delete this {what}?\n\n{truncate(task['title'], 80)}\n\n"
            "This cannot be undone.",
            icon="warning",
            default="no",
            parent=self.winfo_toplevel(),
        )

    def delete_active_task(self, task_id=None):
        if task_id is None:
            task = self.get_selected_active()
        else:
            task = self._row_by_id(self.active_rows, task_id)
        if not task:
            messagebox.showinfo("No selection", "Click a task to select it, then delete.")
            return
        if not self._confirm_delete(task):
            return
        self._delete_task(task["id"])

    def delete_history_task(self, _event=None):
        task = self.get_selected_history()
        if not task:
            messagebox.showinfo(
                "No selection", "Select a completed task in the list first."
            )
            return
        if not self._confirm_delete(task, what="completed task"):
            return
        self._delete_task(task["id"])

    def _delete_task(self, task_id):
        TaskManager.delete_task(task_id)
        if self.selected_active_id == task_id:
            self.selected_active_id = None
        self.refresh()
