"""Wires the catch-up panel into a meeting note window.

Watches the person and date fields, rebuilds the pack when they change, and
moves open items forward into the agenda. Carried items are written straight to
the meetings row rather than routed through the editor's unsaved-changes
tracking: derived data shouldn't make a note you only opened look edited.
"""

import threading
from tkinter import messagebox

from ai_catchup import render as render_brief, summarize_catchup
from ai_client import has_api_key
import attendees
from carry_over import CarryOverManager
from catchup_brief import CatchupBriefManager
from catchup_pack import build_pack
from config.app_settings import CATCHUP_AUTO_BRIEF, CATCHUP_AUTO_PULL
from dialogs.recurring_meeting_dialog import RecurringMeetingDialog
from meeting_cadence import load_cadence
from meeting_store import update_agenda_items
from meeting_window import field
from recurring_meetings import RecurringMeetingManager
from widgets.catchup_panel import CatchupPanel

POLL_MS = 700

NO_KEY_NOTICE = "Set an API key (⚙ settings) to generate a written brief."


class MeetingCatchupSection:
    def __init__(self, dialog, parent):
        self._dialog = dialog
        self.pack = None
        self._context = None
        self._auto_pull_done = False
        self._generating = False
        self._brief_meta = {}
        self._cadence = None
        self.panel = CatchupPanel(
            parent,
            on_refresh=self.refresh,
            on_pull_items=self.pull_items,
            on_generate=self.generate_brief,
            on_copy=self.copy_to_clipboard,
            on_make_recurring=self.make_recurring,
        )
        self.panel.set_pull_enabled(False)
        self._load_saved_brief()
        dialog.after(0, self._first_look)
        dialog.after(POLL_MS, self._watch_context)

    # ------------------------------------------------------------------ input

    def _current_context(self):
        """(people, date) as they stand in the editor, or None when incomplete.

        `people` is the canonical person column, so adding someone to the
        meeting counts as a change and rebuilds the pack around them too.
        """
        dialog = self._dialog
        people = dialog.people_field.get()
        meeting_date = dialog.date_field.get_iso()
        if not people or not meeting_date:
            return None
        return people, meeting_date

    def _watch_context(self):
        dialog = self._dialog
        if not dialog.winfo_exists():
            return
        context = self._current_context()
        if context != self._context:
            self.refresh()
        dialog.after(POLL_MS, self._watch_context)

    def _first_look(self):
        self.refresh()
        self._maybe_auto_pull()
        self._maybe_auto_generate()

    def _maybe_auto_generate(self):
        """Write the brief unprompted for a standing meeting, once.

        Guarded hard: only with the setting on, only a saved occurrence of a
        series that asked for briefs, only when none has been written yet, and
        only when there is something to brief on. The result is cached, so
        opening the note again costs nothing.
        """
        meeting = self._dialog.meeting
        if not CATCHUP_AUTO_BRIEF.get():
            return
        if meeting is None or self._brief_meta or not has_api_key():
            return
        if not self.pack or not self.pack.window.has_anchor or not self.pack.has_anything:
            return
        if not RecurringMeetingManager.catchup_enabled(field(meeting, "recurring_id") or None):
            return
        self.generate_brief()

    # ---------------------------------------------------------------- display

    def refresh(self):
        context = self._current_context()
        self._context = context
        if context is None:
            self.pack = None
            self.panel.show_headline(
                "Add someone and pick a date to see what has happened since you last met."
            )
            self.panel.show_pack("")
            self.panel.set_pull_enabled(False)
            self.panel.show_suggestion("")
            return
        people, meeting_date = context
        self.pack = build_pack(people, meeting_date, exclude_meeting_id=self._meeting_id())
        self.panel.show_headline(self.pack.headline())
        self.panel.show_pack(self.pack.render())
        self._update_pull_button()
        self._update_brief_controls()
        self._update_suggestion(people)

    # ------------------------------------------------- becoming a regular

    def _update_suggestion(self, people):
        """Offer to formalise a pattern the notes already show.

        Only when there's no series yet — someone you've started seeing weekly
        shouldn't have to know the feature exists to benefit from it.
        """
        self._cadence = None
        # A series books one person's standing slot, so this only speaks up
        # about a 1:1.
        person = attendees.first(people)
        if attendees.count(people) != 1:
            self.panel.show_suggestion("")
            return
        if RecurringMeetingManager.series_for_person(person) is not None:
            self.panel.show_suggestion("")
            return
        cadence = load_cadence(person)
        if not cadence.looks_regular:
            self.panel.show_suggestion("")
            return
        self._cadence = cadence
        self.panel.show_suggestion(
            f"{cadence.describe()} Set this up as a recurring meeting?"
        )

    def make_recurring(self):
        """Open the recurring dialog, pre-filled with the pattern we detected."""
        if self._cadence is None:
            return
        RecurringMeetingDialog(
            self._dialog,
            on_saved=self._on_series_created,
            person=self._cadence.person,
            weekdays=self._cadence.weekday_pattern,
        )

    def _on_series_created(self):
        self._dialog.status_var.set(
            "Recurring meeting set up — future notes are created ahead of time, "
            "and each one briefs itself."
        )
        self.refresh()

    def _load_saved_brief(self):
        brief, self._brief_meta = CatchupBriefManager.load(self._dialog.meeting)
        if brief:
            self.panel.show_brief(brief)
            self.panel.select_brief_tab()
        else:
            self.panel.show_brief(
                "No brief yet.\n\nPress “Generate brief” to have the meetings in the "
                "“What happened” tab turned into an update you can talk from."
            )
            self.panel.select_pack_tab()

    def _update_brief_controls(self):
        """Keep the generate button and the notice line honest."""
        if self._generating:
            return
        if not has_api_key():
            self.panel.set_generate_enabled(False, "Generate brief")
            self.panel.show_notice(NO_KEY_NOTICE)
            return
        has_brief = bool(self._brief_meta)
        self.panel.set_generate_enabled(
            self.pack is not None, "Regenerate brief" if has_brief else "Generate brief"
        )
        notice = ""
        if has_brief and self.pack:
            notice = CatchupBriefManager.staleness_notice(self._brief_meta, self.pack.window)
        self.panel.show_notice(notice or CatchupBriefManager.describe_generation(self._brief_meta))

    def _update_pull_button(self):
        carried = self.pack.carried if self.pack else []
        if not carried:
            self.panel.set_pull_enabled(False, "No open items")
            return
        already = {
            self._key(item) for item in self._dialog.agenda.get_filled_items()
        }
        outstanding = [c for c in carried if self._key(c.as_agenda_item()) not in already]
        if not outstanding:
            self.panel.set_pull_enabled(False, "Open items pulled in")
        else:
            self.panel.set_pull_enabled(
                True, f"Pull in {len(outstanding)} open item{'s' if len(outstanding) != 1 else ''}"
            )

    @staticmethod
    def _key(item):
        return " ".join(str(item.get("text", "")).split()).casefold()

    def _meeting_id(self):
        meeting = self._dialog.meeting
        return meeting["id"] if meeting else None

    # ------------------------------------------------------------ carry items

    def pull_items(self):
        if not self.pack or not self.pack.carried:
            messagebox.showinfo(
                "Nothing to carry forward",
                "Nothing came off the last meeting unfinished.",
                parent=self._dialog,
            )
            return
        added = self._merge_carried()
        if added:
            self._dialog.status_var.set(
                f"Pulled {added} open item(s) forward from {self._source_meetings()}."
            )
        else:
            self._dialog.status_var.set("Every open item is already on this agenda.")
        self._update_pull_button()

    def _merge_carried(self):
        dialog = self._dialog
        merged, added = CarryOverManager.merge_into(
            dialog.agenda.get_filled_items(), self.pack.carried
        )
        if added:
            dialog.agenda.set_items(merged)
        return added

    def _maybe_auto_pull(self):
        """Roll open items into a freshly generated, still-empty meeting note.

        Only for a saved note with nothing on its agenda yet, so this can never
        tread on something already written. The result is persisted immediately
        and the editor's baseline moved with it — opening a note should not, by
        itself, leave it looking unsaved.
        """
        dialog = self._dialog
        meeting_id = self._meeting_id()
        if not CATCHUP_AUTO_PULL.get():
            return
        if (self._auto_pull_done or meeting_id is None or not self.pack
                or not self.pack.carried or dialog.agenda.get_filled_items()):
            return
        if dialog.has_unsaved_changes():
            return  # something is already being typed; don't move their baseline
        self._auto_pull_done = True
        added = self._merge_carried()
        if not added:
            return
        items = dialog.agenda.get_filled_items()
        update_agenda_items(meeting_id, items)
        dialog.reset_baseline()
        dialog.status_var.set(
            f"Carried {added} open item(s) forward from {self._source_meetings()} "
            "— already saved."
        )
        self._update_pull_button()

    def _source_meetings(self):
        """Where the carried items came from, named honestly for one or many."""
        anchors = self.pack.window.anchors
        if len(anchors) == 1:
            return f"your {anchors.latest_date} meeting"
        return f"the {len(anchors)} meetings these people were last in"

    # ------------------------------------------------------------------ brief

    def generate_brief(self):
        dialog = self._dialog
        if self._generating or self.pack is None:
            return
        if dialog.is_busy():
            messagebox.showinfo(
                "Please wait", "Another AI job is already running.", parent=dialog
            )
            return
        if not self.pack.has_anything:
            messagebox.showinfo(
                "Nothing to brief on",
                "There are no meetings logged since you last saw them.",
                parent=dialog,
            )
            return
        self._generating = True
        self.panel.set_generate_enabled(False, "Working…")
        self.panel.show_notice("Reading your meetings since last time…")
        dialog.status_var.set("Writing the catch-up brief…")
        pack_text = self.pack.render()
        person = self.pack.window.person
        window = self.pack.window

        def worker():
            try:
                brief = summarize_catchup(pack_text, person)
                dialog.after(0, lambda: self._apply_brief(brief, None, window))
            except Exception as exc:
                dialog.after(0, lambda: self._apply_brief(None, exc, window))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_brief(self, brief, error, window):
        dialog = self._dialog
        self._generating = False
        if not dialog.winfo_exists():
            return
        if error:
            self.panel.show_notice(f"Brief failed: {error}")
            self.panel.set_generate_enabled(True, "Try again")
            dialog.status_var.set("Catch-up brief failed.")
            return
        text = render_brief(brief)
        if not text:
            self.panel.show_notice("The model returned nothing usable. Try again.")
            self.panel.set_generate_enabled(True, "Try again")
            return
        self.panel.show_brief(text)
        self.panel.select_brief_tab()
        meeting_id = self._meeting_id()
        if meeting_id is not None:
            # Written to its own column, so it never touches what the editor is
            # tracking as unsaved — no baseline reset here, or typing in progress
            # would be quietly marked as saved.
            self._brief_meta = CatchupBriefManager.save(meeting_id, text, window)
            dialog.status_var.set("Catch-up brief ready — saved on this note.")
        else:
            self._brief_meta = {}
            dialog.status_var.set("Catch-up brief ready — save the note to keep it.")
        self._update_brief_controls()

    # ----------------------------------------------------------------- export

    def copy_to_clipboard(self):
        text = self.panel.visible_text()
        if not text:
            return
        dialog = self._dialog
        dialog.clipboard_clear()
        dialog.clipboard_append(text)
        dialog.status_var.set("Copied to the clipboard.")
