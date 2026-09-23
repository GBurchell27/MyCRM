"""Turn a meeting with someone new into a CRM contact.

When a meeting is saved against a person who has no contact record, this reads
the meeting material with AI, then opens a pre-filled Add Contact dialog for
review. Nothing reaches the CRM until the user saves that dialog.
"""

import threading
import tkinter as tk
from tkinter import ttk, messagebox

from ai_summarizer import extract_contact_details, has_api_key
from db import get_conn
from dialogs.contact_dialog import ContactDialog
from people_memory import is_known_contact
from widgets.busy_spinner import BusySpinner


def insert_contact(data):
    """Insert a contact row from a ContactDialog data dict."""
    conn = get_conn()
    conn.execute(
        """INSERT INTO contacts
           (met_on, name, team, office, role, manager, how_we_met, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            data["met_on"], data["name"], data["team"], data["office"], data["role"],
            data["manager"], data["how_we_met"], data["notes"],
        ),
    )
    conn.commit()
    conn.close()


def update_contact(contact_id, data):
    """Update an existing contact row from a ContactDialog data dict."""
    conn = get_conn()
    conn.execute(
        """UPDATE contacts SET met_on=?, name=?, team=?, office=?, role=?,
           manager=?, how_we_met=?, notes=? WHERE id=?""",
        (
            data["met_on"], data["name"], data["team"], data["office"], data["role"],
            data["manager"], data["how_we_met"], data["notes"], contact_id,
        ),
    )
    conn.commit()
    conn.close()


class _ExtractingWindow(tk.Toplevel):
    """Small modal shown while the AI reads the meeting for contact details."""

    def __init__(self, master, person, on_cancel=None):
        super().__init__(master)
        self.title("New contact")
        self.resizable(False, False)
        self.cancelled = False
        self._on_cancel = on_cancel

        body = ttk.Frame(self, padding=14)
        body.pack(fill="both", expand=True)
        ttk.Label(
            body,
            text=f"{person} isn't in your CRM yet.",
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w")
        spinner = BusySpinner(body)
        spinner.pack(fill="x", pady=(8, 0))
        spinner.start("Reading the meeting for their details…")
        self._spinner = spinner
        ttk.Button(body, text="Skip", command=self._cancel).pack(
            anchor="e", pady=(10, 0)
        )

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.transient(master.winfo_toplevel())
        self.grab_set()
        self.update_idletasks()

    def _cancel(self):
        self.cancelled = True
        self.close()
        _call(self._on_cancel)

    def close(self):
        self._spinner.stop()
        self.grab_release()
        self.destroy()


class _CaptureQueue:
    """Offers each new face from one meeting in turn, never two at once.

    A group meeting can introduce three people you have never logged. Opening
    three extraction spinners and three contact dialogs on top of each other is
    unusable, so each one waits for the previous to be dealt with.
    """

    def __init__(self, parent, people, material):
        self._parent = parent
        self._pending = list(people)
        self._material = material

    def start(self):
        self._next()

    def _next(self):
        while self._pending:
            person = self._pending.pop(0)
            if is_known_contact(person):
                continue  # added while working through the queue
            capture_contact_from_meeting(
                self._parent, person=person, on_finished=self._next, **self._material
            )
            return


def capture_contacts_from_meeting(
    parent, people, meeting_date, notes="", summary="", transcript=""
):
    """Offer to add everyone in the meeting who has no contact record yet."""
    material = {
        "meeting_date": meeting_date,
        "notes": notes,
        "summary": summary,
        "transcript": transcript,
    }
    _CaptureQueue(parent, people, material).start()


def capture_contact_from_meeting(
    parent, person, meeting_date, notes="", summary="", transcript="", on_finished=None
):
    """Offer to add `person` to the CRM if they have no contact record yet.

    `on_finished` fires once the offer has been dealt with, however it ended —
    saved, cancelled or skipped — so a queue of new faces can move on.
    """
    person = (person or "").strip()
    if not person or is_known_contact(person):
        _call(on_finished)
        return

    prefill = {
        "met_on": meeting_date or "",
        "name": person,
        "how_we_met": f"Meeting on {meeting_date}" if meeting_date else "",
    }
    has_material = bool(notes.strip() or summary.strip() or transcript.strip())
    if not (has_material and has_api_key()):
        _open_contact_dialog(parent, person, prefill, on_closed=on_finished)
        return

    window = _ExtractingWindow(parent, person, on_cancel=on_finished)

    def worker():
        try:
            details = extract_contact_details(person, notes, summary, transcript)
            error = None
        except Exception as exc:  # surfaced as a note in the dialog, never fatal
            details, error = None, exc
        try:
            parent.after(
                0,
                lambda: _finish(
                    parent, window, person, prefill, details, error, on_finished
                ),
            )
        except tk.TclError:
            pass  # app closed while we were extracting

    threading.Thread(target=worker, daemon=True).start()


def _call(callback):
    if callback:
        callback()


def _finish(parent, window, person, prefill, details, error, on_finished=None):
    if window.cancelled or not window.winfo_exists():
        return  # the Skip button has already moved the queue on
    window.close()
    intro = f"{person} isn't in your CRM yet — here's what the meeting suggests."
    if error:
        intro = (
            f"{person} isn't in your CRM yet.\n"
            f"Couldn't read details from the meeting ({error}) — fill in what you know."
        )
    elif details:
        # Don't let a blank AI field wipe the fallback how_we_met.
        prefill.update({k: v for k, v in details.items() if v})
    _open_contact_dialog(parent, person, prefill, intro, on_closed=on_finished)


def _open_contact_dialog(parent, person, prefill, intro="", on_closed=None):
    if not intro:
        intro = f"{person} isn't in your CRM yet — add them now?"

    def on_save(data, contact_id):
        if contact_id:
            update_contact(contact_id, data)
            _refresh_crm_tab(parent)
            return
        insert_contact(data)
        _refresh_crm_tab(parent)
        messagebox.showinfo(
            "Contact added",
            f"{data['name']} has been added to the CRM tab.",
            parent=parent.winfo_toplevel(),
        )

    dialog = ContactDialog(parent, on_save=on_save, initial=prefill, intro=intro)
    if on_closed:
        # Whatever the user did with it, the next new face can be offered once
        # this window is gone. <Destroy> also fires for children, so check which.
        dialog.bind(
            "<Destroy>",
            lambda event, win=dialog: _call(on_closed) if event.widget is win else None,
        )


def _refresh_crm_tab(parent):
    crm_tab = getattr(parent.winfo_toplevel(), "crm_tab", None)
    if crm_tab is not None:
        crm_tab.refresh()
