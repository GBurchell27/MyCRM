"""CRM contacts tab."""

import csv
import tkinter as tk
from tkinter import ttk, messagebox

from db import get_conn
from dialogs.contact_dialog import ContactDialog
from dialogs.relationship_board_dialog import RelationshipBoardDialog
from excel_export import write_crm_workbook
from helpers import truncate
from hover_preview import TreeHoverPreview


class CRMTab(ttk.Frame):
    COLUMNS = ("met_on", "name", "team", "office", "role", "manager", "how_we_met", "notes")
    HEADINGS = [
        "Met On", "Name", "Team", "Office", "Role", "Manager", "How We Met", "Notes",
    ]

    def __init__(self, master):
        super().__init__(master, padding=8)
        self.all_rows = []

        top = ttk.Frame(self)
        top.pack(fill="x", pady=(0, 6))
        ttk.Label(top, text="Search:").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *a: self.refresh())
        ttk.Entry(top, textvariable=self.search_var, width=30).pack(side="left", padx=4)
        ttk.Button(top, text="Add Contact", command=self.add_contact).pack(side="right")
        ttk.Button(top, text="Delete", command=self.delete_contact).pack(side="right", padx=4)
        ttk.Button(top, text="Edit", command=self.edit_contact).pack(side="right")
        ttk.Button(top, text="Relationships", command=self.open_relationships).pack(
            side="right", padx=(0, 12)
        )

        self.tree = ttk.Treeview(self, columns=self.COLUMNS, show="headings", selectmode="browse")
        for col, heading in zip(self.COLUMNS, self.HEADINGS):
            self.tree.heading(col, text=heading)
            width = 90 if col in ("met_on", "team", "office", "role") else 140
            if col in ("how_we_met",):
                width = 100
            if col == "notes":
                width = 260
            self.tree.column(col, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda e: self.edit_contact())
        self.hover_preview = TreeHoverPreview(self.tree, self.preview_fields)

        self.refresh()

    def load_rows(self):
        conn = get_conn()
        rows = conn.execute("SELECT * FROM contacts ORDER BY met_on DESC, id DESC").fetchall()
        conn.close()
        return rows

    def refresh(self):
        self.all_rows = self.load_rows()
        query = self.search_var.get().strip().lower()
        for i in self.tree.get_children():
            self.tree.delete(i)
        for row in self.all_rows:
            if query and not any(
                query in (row[field] or "").lower()
                for field in ("name", "team", "office")
            ):
                continue
            self.tree.insert("", "end", iid=str(row["id"]), values=(
                row["met_on"], row["name"], row["team"], row["office"], row["role"],
                row["manager"], row["how_we_met"], truncate(row["notes"])
            ))

    def preview_fields(self, iid):
        try:
            cid = int(iid)
        except ValueError:
            return None
        for row in self.all_rows:
            if row["id"] == cid:
                return [
                    (heading, row[col])
                    for col, heading in zip(self.COLUMNS, self.HEADINGS)
                ]
        return None

    def get_selected_contact(self):
        sel = self.tree.selection()
        if not sel:
            return None
        cid = int(sel[0])
        for row in self.all_rows:
            if row["id"] == cid:
                return row
        return None

    def add_contact(self):
        ContactDialog(self, on_save=self.save_contact)

    def open_relationships(self):
        # save_contact already refreshes this tab, so edits made on the board
        # show up in the list behind it.
        RelationshipBoardDialog(self, save_contact=self.save_contact)

    def edit_contact(self):
        contact = self.get_selected_contact()
        if not contact:
            messagebox.showinfo("No selection", "Select a contact to edit first.")
            return
        ContactDialog(self, on_save=self.save_contact, contact=contact)

    def delete_contact(self):
        contact = self.get_selected_contact()
        if not contact:
            messagebox.showinfo("No selection", "Select a contact to delete first.")
            return
        if messagebox.askyesno("Delete contact", f"Delete '{contact['name']}'? This cannot be undone."):
            conn = get_conn()
            conn.execute("DELETE FROM contacts WHERE id=?", (contact["id"],))
            conn.commit()
            conn.close()
            self.refresh()

    def save_contact(self, data, contact_id):
        conn = get_conn()
        if contact_id:
            conn.execute("""UPDATE contacts SET met_on=?, name=?, team=?, office=?, role=?,
                             manager=?, how_we_met=?, notes=? WHERE id=?""",
                         (data["met_on"], data["name"], data["team"], data["office"],
                          data["role"], data["manager"], data["how_we_met"],
                          data["notes"], contact_id))
        else:
            conn.execute("""INSERT INTO contacts
                            (met_on, name, team, office, role, manager, how_we_met, notes)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                         (data["met_on"], data["name"], data["team"], data["office"],
                          data["role"], data["manager"], data["how_we_met"],
                          data["notes"]))
        conn.commit()
        conn.close()
        self.refresh()

    def export_csv(self, path):
        rows = self.load_rows()
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(self.HEADINGS)
            for row in rows:
                writer.writerow([row[c] for c in self.COLUMNS])

    def export_excel(self, path):
        write_crm_workbook(path, self.load_rows())
