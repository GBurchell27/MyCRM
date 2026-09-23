"""Relationship board window: an org-chart / sticky-note canvas over the CRM."""

import tkinter as tk
from tkinter import ttk, messagebox
from tkinter.scrolledtext import ScrolledText

import relationship_board as board
from db import get_conn
from dialogs.contact_dialog import ContactDialog
from offices import OFFICES, office_colors
from relationship_board import CONTACT_NODE, NOTE_NODE, NOTE_COLORS
from widgets.board_canvas import NODE_H, NODE_W, NOTE_H, NOTE_W, BoardCanvas

DETAIL_FIELDS = [
    ("role", "Role"),
    ("team", "Team"),
    ("office", "Office"),
    ("manager", "Manager (CRM)"),
    ("met_on", "First met"),
    ("how_we_met", "How we met"),
]
# Worked out from the meetings you already record - nothing to type in.
HISTORY_FIELDS = [
    ("last_contact", "Last spoken"),
    ("meeting_count", "Times met"),
    ("next_meeting", "Next meeting"),
]
HINT = "Drag a card to move it · drag the background to pan · wheel to zoom · double-click to edit"


def _count(number, singular, plural=None):
    return f"{number} {singular if number == 1 else plural or singular + 's'}"


class RelationshipBoardDialog(tk.Toplevel):
    def __init__(self, master, save_contact=None, on_contacts_changed=None):
        super().__init__(master)
        self.title("Relationships")
        self.geometry("1280x780")
        self.minsize(900, 560)
        self.save_contact = save_contact
        self.on_contacts_changed = on_contacts_changed
        self.nodes = []
        self.edges = []
        self._notes_dirty = False
        self._notes_node_id = None
        self._title_node_id = None

        self._build_toolbar()
        self.legend = ttk.Frame(self, padding=(10, 0, 10, 6))
        self.legend.pack(fill="x")
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)
        self.canvas = BoardCanvas(
            body,
            on_select=self._on_select,
            on_move=self._on_node_moved,
            on_open=self._on_node_opened,
            on_link=self._on_link_drawn,
            on_context=self._on_context,
        )
        self.canvas.pack(side="left", fill="both", expand=True)
        self._build_inspector(body)

        self.status = ttk.Label(self, text=HINT, anchor="w", padding=(10, 4))
        self.status.pack(fill="x")

        self.bind("<Delete>", lambda e: self._delete_selection())
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._first_load()
        self.transient(master)

    # --- layout -------------------------------------------------------------

    def _build_toolbar(self):
        bar = ttk.Frame(self, padding=(8, 8, 8, 4))
        bar.pack(fill="x")
        ttk.Button(bar, text="Add people…", command=self._add_people).pack(side="left")
        ttk.Button(bar, text="Add note", command=self._add_note).pack(side="left", padx=4)
        self.link_button = ttk.Button(bar, text="Draw link", command=self._toggle_link_mode)
        self.link_button.pack(side="left", padx=(12, 4))
        ttk.Button(bar, text="Tidy layout", command=self._auto_layout).pack(side="left", padx=4)
        ttk.Button(bar, text="Sync from CRM", command=self._sync).pack(side="left", padx=4)

        ttk.Button(bar, text="Fit", width=5,
                   command=self.canvas_fit).pack(side="right")
        ttk.Button(bar, text="+", width=3,
                   command=lambda: self.canvas.zoom_by(1.2)).pack(side="right", padx=2)
        ttk.Button(bar, text="−", width=3,
                   command=lambda: self.canvas.zoom_by(1 / 1.2)).pack(side="right")

    def canvas_fit(self):
        self.canvas.fit_to_content()

    def _build_inspector(self, master):
        panel = ttk.Frame(master, padding=10, width=300)
        panel.pack(side="right", fill="y")
        panel.pack_propagate(False)

        self.inspector_title = ttk.Label(
            panel, text="Nothing selected", font=("Segoe UI", 11, "bold"), wraplength=270
        )
        self.inspector_title.pack(anchor="w")
        self.inspector_subtitle = ttk.Label(
            panel, text="Click a card to see its CRM details.",
            wraplength=270, foreground="#5d6773",
        )
        self.inspector_subtitle.pack(anchor="w", pady=(2, 8))

        # One slot swapped between contact details and the note title editor,
        # so the panel keeps its order whichever kind of card is selected.
        self.detail_slot = ttk.Frame(panel)
        self.detail_slot.pack(fill="x")
        self.detail_frame = ttk.Frame(self.detail_slot)
        self.detail_frame.pack(fill="x")
        self.detail_values = {}
        rows = [*DETAIL_FIELDS, (None, None), *HISTORY_FIELDS]
        for row, (field, label) in enumerate(rows):
            if field is None:
                ttk.Separator(self.detail_frame, orient="horizontal").grid(
                    row=row, column=0, columnspan=2, sticky="ew", pady=6
                )
                continue
            ttk.Label(self.detail_frame, text=f"{label}:", foreground="#5d6773").grid(
                row=row, column=0, sticky="nw", pady=1
            )
            value = ttk.Label(self.detail_frame, text="", wraplength=180, justify="left")
            value.grid(row=row, column=1, sticky="w", padx=(6, 0), pady=1)
            self.detail_values[field] = value
        self.detail_frame.columnconfigure(1, weight=1)

        self.title_frame = ttk.Frame(self.detail_slot)
        ttk.Label(self.title_frame, text="Note title:").pack(anchor="w")
        self.note_title_var = tk.StringVar()
        entry = ttk.Entry(self.title_frame, textvariable=self.note_title_var)
        entry.pack(fill="x", pady=(2, 0))
        entry.bind("<FocusOut>", lambda e: self._save_note_title())
        entry.bind("<Return>", lambda e: self._save_note_title())

        colour_row = ttk.Frame(panel)
        colour_row.pack(fill="x", pady=(8, 0))
        ttk.Label(colour_row, text="Colour:").pack(side="left")
        self.colour_var = tk.StringVar()
        self.colour_box = ttk.Combobox(
            colour_row, textvariable=self.colour_var, state="readonly",
            values=["Default"] + list(NOTE_COLORS), width=12,
        )
        self.colour_box.pack(side="left", padx=6)
        self.colour_box.bind("<<ComboboxSelected>>", lambda e: self._apply_colour())

        ttk.Label(panel, text="Board notes:").pack(anchor="w", pady=(10, 2))
        self.notes_box = ScrolledText(panel, height=7, wrap="word", width=28)
        self.notes_box.pack(fill="both", expand=False)
        self.notes_box.bind("<<Modified>>", self._on_notes_modified)
        ttk.Button(panel, text="Save note", command=self._save_notes).pack(
            anchor="e", pady=(4, 0)
        )

        ttk.Label(panel, text="Relationships:").pack(anchor="w", pady=(12, 2))
        self.links_list = tk.Listbox(panel, height=6, exportselection=False)
        self.links_list.pack(fill="both", expand=True)
        self.link_rows = []
        link_buttons = ttk.Frame(panel)
        link_buttons.pack(fill="x", pady=(4, 0))
        ttk.Button(link_buttons, text="Edit link…", command=self._edit_selected_link).pack(side="left")
        ttk.Button(link_buttons, text="Remove link", command=self._remove_selected_link).pack(
            side="left", padx=4
        )

        actions = ttk.Frame(panel)
        actions.pack(fill="x", pady=(12, 0))
        self.edit_contact_button = ttk.Button(
            actions, text="Edit in CRM…", command=self._edit_selected_contact
        )
        self.edit_contact_button.pack(side="left")
        ttk.Button(actions, text="Remove from board", command=self._delete_selection).pack(
            side="right"
        )

    # --- data ---------------------------------------------------------------

    def _first_load(self):
        nodes, _ = board.load_board()
        if not nodes:
            added, _ = board.sync_from_crm()
            if added:
                nodes, edges = board.load_board()
                board.move_nodes(board.auto_layout(nodes, edges))
        self.reload(keep_view=False)

    def reload(self, keep_view=True):
        self.nodes, self.edges = board.load_board()
        self.canvas.set_data(self.nodes, self.edges, keep_view=keep_view)
        self._refresh_inspector()
        self._refresh_legend()
        self._refresh_status()

    def _refresh_legend(self):
        """Colour key for the offices actually present on the board."""
        for child in self.legend.winfo_children():
            child.destroy()
        present = {
            (n["office"] or "").strip()
            for n in self.nodes
            if n["kind"] == CONTACT_NODE and not board.node_is_orphan(n)
        }
        if not present:
            return
        known = [office for office in OFFICES if office in present]
        extra = sorted(present - set(OFFICES) - {""})
        for office in known + extra + ([""] if "" in present else []):
            fill, outline = office_colors(office)
            swatch = tk.Frame(
                self.legend, width=12, height=12, background=fill,
                highlightbackground=outline, highlightthickness=1,
            )
            swatch.pack(side="left", padx=(0, 4))
            swatch.pack_propagate(False)
            ttk.Label(self.legend, text=office or "No office").pack(
                side="left", padx=(0, 14)
            )
        ttk.Label(
            self.legend, text="faded = a while since you spoke", foreground="#7c8797"
        ).pack(side="right")

    def _refresh_status(self):
        people = sum(1 for n in self.nodes if n["kind"] == CONTACT_NODE)
        notes = sum(1 for n in self.nodes if n["kind"] == NOTE_NODE)
        counts = " · ".join([
            _count(people, "person", "people"),
            _count(notes, "note"),
            _count(len(self.edges), "link"),
        ])
        self.status.configure(text=f"{counts}    |    {HINT}")

    def _node(self, node_id):
        for node in self.nodes:
            if node["id"] == node_id:
                return node
        return None

    def _selected_node(self):
        return self.canvas.selected_node()

    # --- toolbar actions ----------------------------------------------------

    def _add_people(self):
        available = board.contacts_off_board()
        if not available:
            messagebox.showinfo(
                "Everyone is here",
                "Every CRM contact already has a card on the board.",
                parent=self,
            )
            return
        AddPeopleDialog(self, available, self._place_contacts)

    def _place_contacts(self, contact_ids):
        center_x, center_y = self.canvas.view_center_world()
        placed = list(self.nodes)
        for index, contact_id in enumerate(contact_ids):
            x, y = self._free_spot(
                center_x - 100 + (index % 3) * 230,
                center_y - 40 + (index // 3) * 130,
                (NODE_W, NODE_H), placed,
            )
            board.add_contact_node(contact_id, x, y)
            placed.append({"x": x, "y": y, "kind": CONTACT_NODE})
        self.reload()

    def _add_note(self, world=None):
        x, y = world or self.canvas.view_center_world()
        x, y = self._free_spot(x - 95, y - 60, (NOTE_W, NOTE_H), self.nodes)
        node_id = board.add_note_node(x, y)
        self.reload()
        self.canvas.select("node", node_id)
        self.notes_box.focus_set()

    @staticmethod
    def _free_spot(x, y, size, taken, step=28.0, tries=40):
        """Nudge a new card diagonally until it no longer covers another one."""
        width, height = size
        for _ in range(tries):
            clashes = any(
                x < other["x"] + BoardCanvas.node_size(other)[0]
                and other["x"] < x + width
                and y < other["y"] + BoardCanvas.node_size(other)[1]
                and other["y"] < y + height
                for other in taken
            )
            if not clashes:
                break
            x += step
            y += step
        return x, y

    def _toggle_link_mode(self):
        enabled = not self.canvas.link_mode
        self.canvas.set_link_mode(enabled)
        self.link_button.configure(text="Cancel link" if enabled else "Draw link")
        if enabled:
            self.status.configure(text="Click the first person, then the person they relate to.")
        else:
            self._refresh_status()

    def _auto_layout(self):
        if not self.nodes:
            return
        board.move_nodes(board.auto_layout(self.nodes, self.edges))
        self.reload(keep_view=False)

    def _sync(self):
        added_nodes, added_links = board.sync_from_crm()
        self.reload()
        messagebox.showinfo(
            "Synced with CRM",
            f"Added {added_nodes} new card(s) and {added_links} manager link(s).",
            parent=self,
        )

    # --- canvas callbacks ---------------------------------------------------

    def _on_select(self, _kind, _item_id):
        self._flush_notes()
        self._refresh_inspector()

    def _on_node_moved(self, node_id, x, y):
        board.move_node(node_id, x, y)

    def _on_node_opened(self, node_id):
        node = self._node(node_id)
        if node and node["kind"] == CONTACT_NODE and node["contact_id"]:
            self._edit_contact(node)
        else:
            self.notes_box.focus_set()

    def _on_link_drawn(self, source_id, target_id):
        source, target = self._node(source_id), self._node(target_id)
        if not source or not target:
            return
        LinkDialog(
            self, board.node_title(source), board.node_title(target),
            on_save=lambda kind, label: self._create_link(source_id, target_id, kind, label),
        )

    def _create_link(self, source_id, target_id, kind, label):
        board.add_edge(source_id, target_id, kind, label)
        self.canvas.set_link_mode(False)
        self.link_button.configure(text="Draw link")
        self.reload()

    def _on_context(self, kind, item_id, event):
        menu = tk.Menu(self, tearoff=0)
        if kind == "node":
            node = self._node(item_id)
            menu.add_command(label="Draw link from here",
                             command=lambda: self._start_link_from(item_id))
            if node and node["kind"] == CONTACT_NODE and node["contact_id"]:
                menu.add_command(label="Edit in CRM…", command=lambda: self._edit_contact(node))
            menu.add_separator()
            menu.add_command(label="Remove from board", command=self._delete_selection)
        elif kind == "edge":
            menu.add_command(label="Edit link…", command=lambda: self._edit_link(item_id))
            menu.add_command(label="Delete link", command=self._delete_selection)
        else:
            world = self.canvas.event_world(event)
            menu.add_command(label="Add note here", command=lambda: self._add_note(world))
            menu.add_command(label="Add people…", command=self._add_people)
            menu.add_separator()
            menu.add_command(label="Fit to view", command=self.canvas_fit)
        menu.tk_popup(event.x_root, event.y_root)

    def _start_link_from(self, node_id):
        if not self.canvas.link_mode:
            self._toggle_link_mode()
        self.canvas.link_source_id = node_id
        self.canvas.redraw()

    # --- inspector ----------------------------------------------------------

    def _refresh_inspector(self):
        node = self._selected_node()
        if node is None:
            self._show_edge_or_empty()
            return
        is_note = node["kind"] == NOTE_NODE
        self.inspector_title.configure(text=board.node_title(node))
        if is_note:
            self.inspector_subtitle.configure(text="Sticky note")
            self.detail_frame.pack_forget()
            self.title_frame.pack(fill="x")
            self._title_node_id = node["id"]
            self.note_title_var.set(node["label"] or "")
            self.edit_contact_button.state(["disabled"])
        else:
            self.title_frame.pack_forget()
            self.detail_frame.pack(fill="x")
            self._title_node_id = None
            if board.node_is_orphan(node):
                self.inspector_subtitle.configure(
                    text="This contact was deleted from the CRM."
                )
            else:
                self.inspector_subtitle.configure(text="From the CRM tab")
            for field, value_label in self.detail_values.items():
                value_label.configure(text=self._detail_text(node, field))
            self.edit_contact_button.state(
                ["!disabled"] if node["contact_id"] else ["disabled"]
            )
        colours = {v: k for k, v in NOTE_COLORS.items()}
        self.colour_var.set(colours.get(node["color"], "Default"))
        self._set_notes_text(node["notes"] or "", node["id"])
        self._fill_links(node)

    @staticmethod
    def _detail_text(node, field):
        if field == "last_contact":
            return board.last_contact_label(node)
        if field == "meeting_count":
            return str(node["meeting_count"]) if node["meeting_count"] else "—"
        return (node[field] or "").strip() or "—"

    def _show_edge_or_empty(self):
        self.detail_frame.pack_forget()
        self.title_frame.pack_forget()
        self._set_notes_text("", None)
        self.links_list.delete(0, "end")
        self.link_rows = []
        self.edit_contact_button.state(["disabled"])
        if self.canvas.selected_kind == "edge":
            edge = next((e for e in self.edges if e["id"] == self.canvas.selected_id), None)
            if edge:
                source, target = self._node(edge["from_node"]), self._node(edge["to_node"])
                self.inspector_title.configure(text=board.kind_label(edge["kind"], edge["label"]))
                self.inspector_subtitle.configure(
                    text=f"{board.node_title(source)} → {board.node_title(target)}"
                )
                return
        self.inspector_title.configure(text="Nothing selected")
        self.inspector_subtitle.configure(text="Click a card to see its CRM details.")

    def _fill_links(self, node):
        self.links_list.delete(0, "end")
        self.link_rows = []
        for edge in self.edges:
            if node["id"] not in (edge["from_node"], edge["to_node"]):
                continue
            other_id = edge["to_node"] if edge["from_node"] == node["id"] else edge["from_node"]
            other = self._node(other_id)
            if not other:
                continue
            self.links_list.insert("end", board.describe_edge(edge, node, other))
            self.link_rows.append(edge["id"])

    def _selected_link_id(self):
        selection = self.links_list.curselection()
        if selection:
            return self.link_rows[selection[0]]
        if self.canvas.selected_kind == "edge":
            return self.canvas.selected_id
        return None

    def _edit_selected_link(self):
        edge_id = self._selected_link_id()
        if edge_id is None:
            messagebox.showinfo("No link selected", "Pick a relationship first.", parent=self)
            return
        self._edit_link(edge_id)

    def _edit_link(self, edge_id):
        edge = next((e for e in self.edges if e["id"] == edge_id), None)
        if not edge:
            return
        source, target = self._node(edge["from_node"]), self._node(edge["to_node"])
        LinkDialog(
            self, board.node_title(source), board.node_title(target),
            kind=edge["kind"], label=edge["label"],
            on_save=lambda kind, label: self._update_link(edge_id, kind, label),
        )

    def _update_link(self, edge_id, kind, label):
        board.update_edge(edge_id, kind=kind, label=label)
        self.reload()

    def _remove_selected_link(self):
        edge_id = self._selected_link_id()
        if edge_id is None:
            messagebox.showinfo("No link selected", "Pick a relationship first.", parent=self)
            return
        board.delete_edge(edge_id)
        self.reload()

    def _on_notes_modified(self, _event=None):
        if self.notes_box.edit_modified():
            self._notes_dirty = True
            self.notes_box.edit_modified(False)

    def _set_notes_text(self, text, node_id):
        self._notes_node_id = node_id
        self.notes_box.delete("1.0", "end")
        self.notes_box.insert("1.0", text)
        self.notes_box.edit_modified(False)
        self._notes_dirty = False

    def _save_notes(self):
        # Always write back to the node the text came from: the selection may
        # already have moved on by the time this runs.
        node = self._node(self._notes_node_id) if self._notes_node_id else None
        if not node:
            return
        text = self.notes_box.get("1.0", "end").strip()
        if text != (node["notes"] or ""):
            board.update_node(node["id"], notes=text)
            node["notes"] = text
            self.canvas.redraw()
        self._notes_dirty = False

    def _flush_notes(self):
        """Persist pending note edits before the selection changes."""
        if self._notes_dirty:
            self._save_notes()

    def _save_note_title(self):
        node = self._node(self._title_node_id) if self._title_node_id else None
        if not node or node["kind"] != NOTE_NODE:
            return
        title = self.note_title_var.get().strip()
        if title != (node["label"] or ""):
            board.update_node(node["id"], label=title)
            node["label"] = title
            self.canvas.redraw()
            if self._selected_node() is node:
                self.inspector_title.configure(text=board.node_title(node))

    def _apply_colour(self):
        node = self._selected_node()
        if not node:
            return
        colour = NOTE_COLORS.get(self.colour_var.get(), "")
        board.update_node(node["id"], color=colour)
        node["color"] = colour
        self.canvas.redraw()

    # --- contacts -----------------------------------------------------------

    def _edit_selected_contact(self):
        node = self._selected_node()
        if node and node["kind"] == CONTACT_NODE and node["contact_id"]:
            self._edit_contact(node)

    def _edit_contact(self, node):
        conn = get_conn()
        contact = conn.execute(
            "SELECT * FROM contacts WHERE id=?", (node["contact_id"],)
        ).fetchone()
        conn.close()
        if not contact:
            messagebox.showinfo(
                "Contact missing",
                "This person is no longer in the CRM. Remove the card from the board.",
                parent=self,
            )
            return
        ContactDialog(self, on_save=self._store_contact, contact=contact)

    def _store_contact(self, data, contact_id):
        if self.save_contact:
            self.save_contact(data, contact_id)
        if self.on_contacts_changed:
            self.on_contacts_changed()
        self.reload()

    # --- deletion / closing -------------------------------------------------

    def _delete_selection(self):
        if self.canvas.selected_kind == "edge":
            board.delete_edge(self.canvas.selected_id)
            self.reload()
            return
        node = self._selected_node()
        if not node:
            return
        if node["kind"] == NOTE_NODE:
            if not messagebox.askyesno(
                "Delete note", "Delete this note? This cannot be undone.", parent=self
            ):
                return
        board.delete_node(node["id"])
        self._notes_dirty = False
        self.reload()

    def _close(self):
        self._flush_notes()
        self.destroy()


class AddPeopleDialog(tk.Toplevel):
    """Pick CRM contacts that are not on the board yet."""

    def __init__(self, master, contacts, on_add):
        super().__init__(master)
        self.title("Add people to the board")
        self.geometry("380x420")
        self.contacts = contacts
        self.on_add = on_add

        ttk.Label(self, text="Select the people to add:", padding=(10, 10, 10, 4)).pack(anchor="w")
        frame = ttk.Frame(self, padding=(10, 0))
        frame.pack(fill="both", expand=True)
        self.listbox = tk.Listbox(frame, selectmode="extended")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scroll.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        for contact in contacts:
            detail = " · ".join(p for p in (contact["role"], contact["team"]) if p)
            self.listbox.insert("end", f"{contact['name']}{'  —  ' + detail if detail else ''}")

        buttons = ttk.Frame(self, padding=10)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Add", command=self._add).pack(side="right", padx=4)
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        self.transient(master)
        self.grab_set()
        self.listbox.focus_set()

    def _add(self):
        chosen = [self.contacts[i]["id"] for i in self.listbox.curselection()]
        if chosen:
            self.on_add(chosen)
        self.destroy()


class LinkDialog(tk.Toplevel):
    """Choose the relationship type between two cards."""

    def __init__(self, master, source_name, target_name, kind="reports_to", label="", on_save=None):
        super().__init__(master)
        self.title("Relationship")
        self.resizable(False, False)
        self.on_save = on_save
        self.kind_names = {
            key: board.RELATIONSHIP_KINDS[key][0] for key in board.KIND_ORDER
        }

        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        ttk.Label(
            body, text=f"{source_name}  →  {target_name}",
            font=("Segoe UI", 10, "bold"), wraplength=320,
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

        ttk.Label(body, text="Relationship:").grid(row=1, column=0, sticky="w")
        self.kind_var = tk.StringVar(value=self.kind_names.get(kind, "works with"))
        ttk.Combobox(
            body, textvariable=self.kind_var, state="readonly",
            values=list(self.kind_names.values()), width=24,
        ).grid(row=1, column=1, sticky="ew", padx=(8, 0))

        ttk.Label(body, text="Own wording:").grid(row=2, column=0, sticky="w", pady=(8, 0))
        self.label_var = tk.StringVar(value=label or "")
        entry = ttk.Entry(body, textvariable=self.label_var, width=26)
        entry.grid(row=2, column=1, sticky="ew", padx=(8, 0), pady=(8, 0))
        ttk.Label(
            body, text="Optional — replaces the wording on the line.",
            foreground="#6b7684",
        ).grid(row=3, column=1, sticky="w", padx=(8, 0))

        buttons = ttk.Frame(body)
        buttons.grid(row=4, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="Save", command=self._save).pack(side="right", padx=4)
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        body.columnconfigure(1, weight=1)

        entry.bind("<Return>", lambda e: self._save())
        self.transient(master)
        self.grab_set()

    def _save(self):
        chosen = self.kind_var.get()
        kind = next(
            (key for key, name in self.kind_names.items() if name == chosen), "custom"
        )
        if self.on_save:
            self.on_save(kind, self.label_var.get().strip())
        self.destroy()
