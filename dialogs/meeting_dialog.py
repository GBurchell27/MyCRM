"""Meeting note dialog with checklist, recording, and AI summarize."""

import json
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from tkinter.scrolledtext import ScrolledText
from datetime import date

import help_text
from contact_capture import capture_contacts_from_meeting
from dialogs.meeting_attachment_transcriber import MeetingAttachmentTranscriber
from dialogs.recording_recovery_dialog import RecordingRecoveryFlow
from dialogs.meeting_catchup_section import MeetingCatchupSection
from dialogs.meeting_close_guard import MeetingCloseGuard
from dialogs.meeting_recording_section import MeetingRecordingSection
from helpers import parse_agenda_items, split_action_item
from people_memory import is_known_contact, list_known_people
from ai_summarizer import summarize_meeting
from meeting_artifacts import MeetingArtifacts, encode_media_paths
from widgets.agenda_checklist import AgendaChecklist
from widgets.attendees_field import AttendeesField
from widgets.meeting_artifacts_bar import MeetingArtifactsBar
from widgets.dictation_button import DictationButton
from widgets.busy_spinner import BusySpinner
from widgets.meeting_date_field import MeetingDateField
from widgets.tooltip import attach, attach_all


def _saved_field(meeting, key):
    """Value of `key` on a meetings row, tolerant of rows saved before it existed."""
    if not meeting:
        return ""
    try:
        return meeting[key] or ""
    except (IndexError, KeyError):
        return ""


class MeetingDialog(tk.Toplevel):
    def __init__(self, master, on_save, meeting=None, default_person=""):
        super().__init__(master)
        self.base_title = "Edit Meeting Note" if meeting else "Add Meeting Note"
        self.title(self.base_title)
        self.on_save = on_save
        self.meeting = meeting
        self.geometry("1040x760")
        self.minsize(800, 600)
        self.recording = MeetingRecordingSection(self)
        self.artifacts = MeetingArtifacts(
            self.recording.session,
            saved_transcript=_saved_field(meeting, "transcript"),
            saved_media_json=_saved_field(meeting, "media_paths"),
        )
        self._attachment_transcriber = MeetingAttachmentTranscriber(self)
        self._recovery = RecordingRecoveryFlow(self)
        self._close_guard = MeetingCloseGuard(self)
        self._pipeline_busy = False
        self._saved = False
        self._closing = False
        self._contact_capture_done = False

        top = ttk.Frame(self, padding=12)
        top.pack(fill="x")
        ttk.Label(top, text="Date:").grid(row=0, column=0, sticky="nw")
        self.date_field = MeetingDateField(top, width=22)
        self.date_field.grid(row=0, column=1, sticky="nw", padx=(4, 20))
        ttk.Label(top, text="People:").grid(row=0, column=2, sticky="nw")
        self.people_field = AttendeesField(top, known_people=list_known_people())
        self.people_field.grid(row=0, column=3, sticky="nw", padx=4)

        if meeting:
            self.date_field.set(meeting["date"] or "")
            self.people_field.set(meeting["person"] or "")
        else:
            self.date_field.set(date.today().isoformat())
            self.people_field.set(default_person)

        tools = ttk.LabelFrame(self, text="Capture & AI", padding=8)
        tools.pack(fill="x", padx=12, pady=(4, 0))
        row1 = ttk.Frame(tools)
        row1.pack(fill="x")
        record_btn = self.recording.build_record_button(row1)
        record_btn.pack(side="left")
        summarize_btn = ttk.Button(row1, text="AI Summarize", command=self.run_ai_summarize)
        summarize_btn.pack(side="left", padx=6)
        retry_btn = self.recording.build_retry_button(row1)
        retry_btn.pack(side="left", padx=2)
        self.artifacts_bar = MeetingArtifactsBar(
            row1,
            self.artifacts,
            transcript_title=self._transcript_title(),
            on_attach=self._attachment_transcriber.handle_attached,
            on_recover=self._recovery.prompt,
        )
        self.artifacts_bar.pack(side="left", padx=2)
        self.recording.build_capture_options(row1).pack(side="left")
        attach_all([
            (record_btn, help_text.RECORD),
            (summarize_btn, help_text.AI_SUMMARIZE),
            (retry_btn, help_text.RETRY_TRANSCRIPTION),
            (self.date_field.widget, help_text.MEETING_DATE),
            (self.people_field.combo, help_text.MEETING_PEOPLE),
            (self.people_field.add_button, help_text.MEETING_PEOPLE_ADD),
        ])
        self.status_var = tk.StringVar(
            value="Records mic + screen + active windows. Stop/start again to add more clips to this meeting."
        )
        ttk.Label(tools, textvariable=self.status_var, wraplength=900).pack(anchor="w", pady=(6, 0))
        self.recording.build_indicator(tools)
        self.busy_spinner = BusySpinner(tools)

        self.agenda = AgendaChecklist(
            self,
            get_meeting_context=self._meeting_task_context,
            on_task_added=self._on_agenda_task_added,
        )
        self.agenda.pack(fill="both", expand=False, padx=12, pady=(8, 4))
        existing_items = parse_agenda_items(meeting["agenda_items"]) if meeting else []
        self.agenda.set_items(existing_items)

        footer = tk.Frame(self, bg="#E8F5E9", padx=12, pady=10)
        footer.pack(fill="x", side="bottom")
        self.unsaved_var = tk.StringVar(value="")
        tk.Label(
            footer,
            textvariable=self.unsaved_var,
            font=("Segoe UI", 9),
            fg="#B71C1C",
            bg="#E8F5E9",
        ).pack(side="left")
        ttk.Button(footer, text="Cancel", command=self.on_close).pack(side="right", padx=(8, 0))
        self.save_btn = tk.Button(
            footer,
            text="SAVE MEETING NOTE  (Ctrl+S)",
            command=self.save,
            font=("Segoe UI", 12, "bold"),
            fg="white",
            bg="#2E7D32",
            activeforeground="white",
            activebackground="#1B5E20",
            disabledforeground="#A5D6A7",
            padx=22,
            pady=12,
            cursor="hand2",
            relief="raised",
            bd=2,
        )
        self.save_btn.pack(side="right")
        attach(self.save_btn, help_text.SAVE_MEETING)

        notes_container = ttk.Frame(self)
        notes_container.pack(fill="both", expand=True, padx=12, pady=4)
        for column in range(3):
            notes_container.columnconfigure(column, weight=1, uniform="meeting_notes")
        notes_container.rowconfigure(0, weight=1)

        self.catchup = MeetingCatchupSection(self, notes_container)
        self.catchup.panel.grid(row=0, column=0, sticky="nsew", padx=(0, 4))

        summary_label, summary_mic = self._label_with_mic(notes_container, "AI summary")
        summary_frame = ttk.LabelFrame(notes_container, labelwidget=summary_label, padding=8)
        summary_frame.grid(row=0, column=1, sticky="nsew", padx=4)
        self.summary_box = ScrolledText(summary_frame, wrap="word")
        self.summary_box.pack(fill="both", expand=True)
        summary_mic.target = self.summary_box

        notes_label, notes_mic = self._label_with_mic(notes_container, "My notes during meeting")
        notes_frame = ttk.LabelFrame(notes_container, labelwidget=notes_label, padding=8)
        notes_frame.grid(row=0, column=2, sticky="nsew", padx=(4, 0))
        self.notes_box = ScrolledText(notes_frame, wrap="word")
        self.notes_box.pack(fill="both", expand=True)
        notes_mic.target = self.notes_box
        if meeting:
            self.summary_box.insert("1.0", meeting["ai_summary"] or "")
            self.notes_box.insert("1.0", meeting["notes"] or "")

        self._baseline = self._snapshot()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.bind("<Escape>", lambda _e: self.on_close())
        for widget in (self, self.notes_box, self.summary_box):
            widget.bind("<F9>", self.recording.handle_shortcut)
            widget.bind("<Control-s>", self._on_save_shortcut)
            widget.bind("<Control-S>", self._on_save_shortcut)
        if default_person or (meeting and meeting["person"]):
            self.notes_box.focus_set()
        else:
            self.people_field.focus_set()
        self.after(400, self._watch_dirty)

    def _label_with_mic(self, parent, text):
        """A LabelFrame header holding the title plus a dictation mic button."""
        label = ttk.Frame(parent)
        ttk.Label(label, text=text).pack(side="left")
        mic = DictationButton(
            label,
            on_status=self.status_var.set,
            can_start=self._dictation_blocked,
        )
        mic.pack(side="left", padx=(6, 0))
        return label, mic

    def other_recording_dialog(self):
        """The other open MeetingDialog currently recording, if any."""
        root = self.master.winfo_toplevel()
        finder = getattr(root, "open_meeting_dialogs", None)
        if finder is None:
            return None
        for dialog in finder():
            try:
                if dialog is not self and dialog.winfo_exists() and dialog.recording.is_recording:
                    return dialog
            except tk.TclError:
                continue
        return None

    def _dictation_blocked(self):
        if self.recording.is_recording:
            return "Stop the meeting recording first — it is already using the microphone."
        if self.other_recording_dialog() is not None:
            return "Another meeting window is recording — stop it first (it is using the microphone)."
        return None

    def _meeting_task_context(self):
        meeting_date = self.date_field.get_iso()
        if not meeting_date:
            meeting_date = self.date_field.get_raw().strip()
        return {
            "person": self.people_field.describe(),
            "date": meeting_date or "",
        }

    def _on_agenda_task_added(self, title):
        self.status_var.set(f'Added to Tasks: "{title}"')
        root = self.master.winfo_toplevel()
        tasks_tab = getattr(root, "tasks_tab", None)
        if tasks_tab is not None:
            tasks_tab.refresh()

    def _on_save_shortcut(self, _event):
        self.save()
        return "break"

    def _snapshot(self):
        return {
            "date": self.date_field.get_raw(),
            "person": self.people_field.get(),
            "agenda_items": self.agenda.get_snapshot_items(),
            "ai_summary": self.summary_box.get("1.0", "end").strip(),
            "notes": self.notes_box.get("1.0", "end").strip(),
            "session_media": len(self.recording.session),
            "transcript": self.artifacts.transcript_text,
            "media_paths": encode_media_paths(self.artifacts.media_paths_for_saving()),
        }

    def has_unsaved_changes(self):
        if self._saved or self._closing:
            return False
        return self._snapshot() != self._baseline

    def reset_baseline(self):
        """Treat the current contents as saved.

        Used when something writes to the meetings row behind the editor's back,
        so derived data doesn't leave an untouched note looking edited.
        """
        self._baseline = self._snapshot()

    def _watch_dirty(self):
        if not self.winfo_exists() or self._closing:
            return
        dirty = self.has_unsaved_changes()
        if dirty:
            self.unsaved_var.set("● Unsaved changes — press Save before closing")
            if not self.recording.is_recording and not self._pipeline_busy:
                self.title(self.base_title + " • unsaved")
        else:
            self.unsaved_var.set("")
            if not self.recording.is_recording and not self._pipeline_busy:
                self.title(self.base_title)
        self.after(400, self._watch_dirty)

    def _set_pipeline_busy(self, busy, message=None):
        self._pipeline_busy = busy
        if busy:
            self.recording.set_record_enabled(False)
            self.save_btn.configure(state="disabled")
            if message:
                self.busy_spinner.start(message)
                self.title("⏳ " + message + " — " + self.base_title)
        else:
            if not self.recording.is_recording:
                self.recording.set_record_enabled(True)
            self.save_btn.configure(state="normal")
            self.busy_spinner.stop()
            if not self.recording.is_recording:
                self.title(self.base_title)

    def _confirm_leave(self):
        return self._close_guard.may_leave()

    def try_close(self):
        if self._closing:
            return True
        if not self._confirm_leave():
            return False
        self._closing = True
        self.destroy()
        return True

    def is_busy(self):
        """True while recording or an AI/transcription job is running."""
        return self._pipeline_busy or self.recording.is_recording

    def _transcript_title(self):
        people = self.people_field.describe()
        return f"Raw transcript — {people}" if people else "Raw transcript"

    def on_transcript_ready(self, segment_index):
        """Called by the recording section once a clip has been transcribed."""
        self._run_ai_summarize_async(auto=True, segment_index=segment_index)

    def run_ai_summarize(self):
        if self.recording.is_recording:
            messagebox.showinfo("Still recording", "Stop recording before summarizing.", parent=self)
            return
        if self._pipeline_busy:
            messagebox.showinfo("Please wait", "Another AI job is already running.", parent=self)
            return
        if self.recording.has_pending_transcription:
            messagebox.showinfo(
                "Transcription pending",
                "Finish or retry transcription for the latest recording first.",
                parent=self,
            )
            return
        self._run_ai_summarize_async(auto=False, segment_index=None)

    def _run_ai_summarize_async(self, auto, segment_index=None):
        raw = self.notes_box.get("1.0", "end").strip()
        session = self.recording.session
        if segment_index is not None:
            transcript = session.transcript_for(segment_index)
            activity = session.activity_for(segment_index)
            append = True
        else:
            transcript = session.combined_transcript
            activity = session.combined_activity
            append = False
        self._set_pipeline_busy(True, "AI summarizing…")
        self.status_var.set("AI summarizing…")

        def worker():
            try:
                result = summarize_meeting(raw, transcript, activity)
                self.after(
                    0,
                    lambda: self._apply_ai_result(
                        result, None, auto=auto, append=append, segment_index=segment_index
                    ),
                )
            except Exception as exc:
                self.after(
                    0,
                    lambda: self._apply_ai_result(
                        None, exc, auto=auto, append=append, segment_index=segment_index
                    ),
                )

        threading.Thread(target=worker, daemon=True).start()

    def _apply_ai_result(self, result, error, auto, append=False, segment_index=None):
        self._set_pipeline_busy(False)
        if error:
            self.status_var.set("AI summarize failed.")
            messagebox.showerror("AI Summarize", str(error), parent=self)
            if auto:
                self.status_var.set(
                    f"Transcript saved ({self.recording.session.describe()}). "
                    "AI Summarize failed — click AI Summarize to retry."
                )
            return

        parts = []
        if result["summary"]:
            parts.append(result["summary"])
        if result["highlights"]:
            parts.append("Things of interest:\n" + "\n".join(f"• {h}" for h in result["highlights"]))
        new_notes = "\n\n".join(parts).strip()
        if new_notes:
            if append:
                existing_summary = self.summary_box.get("1.0", "end").strip()
                clip_n = (segment_index or 0) + 1
                if existing_summary:
                    heading = f"--- Recording {clip_n} ---"
                    self.summary_box.insert("end", f"\n\n{heading}\n{new_notes}")
                else:
                    if clip_n > 1:
                        self.summary_box.delete("1.0", "end")
                        self.summary_box.insert("1.0", f"--- Recording {clip_n} ---\n{new_notes}")
                    else:
                        self.summary_box.delete("1.0", "end")
                        self.summary_box.insert("1.0", new_notes)
            else:
                self.summary_box.delete("1.0", "end")
                self.summary_box.insert("1.0", new_notes)

        existing = self.agenda.get_filled_items()
        existing_texts = {
            f"{e['text']} {e.get('detail', '')}".strip().casefold() for e in existing
        }
        for action in result["action_items"]:
            title, detail = split_action_item(action)
            if not title:
                continue
            key = f"{title} {detail}".strip().casefold()
            if key not in existing_texts:
                existing.append({"text": title, "detail": detail, "checked": False})
                existing_texts.add(key)
        self.agenda.set_items(existing)

        verb = "appended to" if append else "updated"
        self.status_var.set(
            f"AI {verb} the summary ({len(result['highlights'])} highlights) "
            f"and {len(result['action_items'])} action item(s). "
            f"{self.recording.session.describe()}. You can record another clip anytime."
        )

    def save(self, close_after=True):
        if self.recording.is_recording:
            messagebox.showinfo("Still recording", "Stop recording before saving.", parent=self)
            return False
        if self._pipeline_busy:
            messagebox.showinfo(
                "Please wait",
                "Wait for transcription / AI summary to finish before saving.",
                parent=self,
            )
            return False
        if self.recording.has_pending_transcription:
            messagebox.showinfo(
                "Transcription incomplete",
                "The latest recording must be transcribed successfully first "
                "(use Retry transcription), or discard via Cancel.",
                parent=self,
            )
            return False
        people = self.people_field.get_names()
        if not people:
            messagebox.showwarning(
                "Nobody added",
                "Add at least one person to the meeting before saving.",
                parent=self,
            )
            self.people_field.focus_set()
            return False
        meeting_date = self.date_field.get_iso()
        if meeting_date is None:
            messagebox.showwarning(
                "Invalid date",
                "Pick a date from the list, or type a date as YYYY-MM-DD "
                "(past or future).",
                parent=self,
            )
            self.date_field.focus_set()
            return False
        if not meeting_date:
            messagebox.showwarning(
                "Missing date",
                "Please choose or enter a meeting date before saving.",
                parent=self,
            )
            self.date_field.focus_set()
            return False
        data = {
            "date": meeting_date,
            "person": self.people_field.get(),
            "agenda_items": json.dumps(self.agenda.get_filled_items()),
            "ai_summary": self.summary_box.get("1.0", "end").strip(),
            "notes": self.notes_box.get("1.0", "end").strip(),
            "transcript": self.artifacts.transcript_text,
            "media_paths": encode_media_paths(self.artifacts.media_paths_for_saving()),
        }
        self.on_save(data, self.meeting["id"] if self.meeting else None)
        self._saved = True
        self._closing = True
        self._baseline = self._snapshot()
        self.unsaved_var.set("Saved")
        self._queue_new_contact_capture(people, meeting_date, data)
        if close_after:
            self.destroy()
        return True

    def _queue_new_contact_capture(self, people, meeting_date, data):
        """Offer to add anyone in the meeting who isn't a contact yet.

        A group meeting can introduce several new faces; they are offered one
        after another rather than all at once.
        """
        newcomers = [person for person in people if not is_known_contact(person)]
        if self._contact_capture_done or not newcomers:
            return
        self._contact_capture_done = True
        host = self.master
        transcript = self.recording.session.combined_transcript
        # Deferred so it runs after this dialog has closed, and on a widget
        # that outlives it.
        host.after(
            0,
            lambda: capture_contacts_from_meeting(
                host,
                people=newcomers,
                meeting_date=meeting_date,
                notes=data["notes"],
                summary=data["ai_summary"],
                transcript=transcript,
            ),
        )

    def on_close(self):
        if self._closing:
            return
        if not self._confirm_leave():
            return
        self._closing = True
        self.destroy()
