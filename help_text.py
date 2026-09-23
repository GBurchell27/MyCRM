"""Every tooltip's wording, in one place.

Kept out of the UI files so the explanations can be read and reworded as a set,
rather than hunted down one widget at a time.
"""

# --- Main window ------------------------------------------------------------

SETTINGS_COG = (
    "Settings (Ctrl+,) — the AI model and reasoning effort behind each job, how far "
    "back catch-ups look, and how a new meeting note starts out."
)

# --- Meeting note window: capture and AI -----------------------------------

RECORD = (
    "Record the meeting — microphone, optionally your screen and system audio, plus a "
    "log of which windows you were in.\n\nEverything is written to disk as it is captured, "
    "so a long meeting is safe even if the app closes unexpectedly, and the audio is kept "
    "as its own file afterwards.\n\nStop and start again to add more clips to the same "
    "note. Shortcut: F9."
)
AI_SUMMARIZE = (
    "Send your notes and any transcript to the AI, which writes the summary and pulls "
    "out action items onto the agenda below.\n\nRuns automatically after a recording is "
    "transcribed."
)
RETRY_TRANSCRIPTION = (
    "Transcribe the last recording again. Enabled when transcription failed or there was "
    "no API key at the time — the note can't be saved until it succeeds, or you discard "
    "it.\n\nLong recordings are transcribed in parts, so a failure never costs more than "
    "the part it happened in, and the audio stays on disk to try again."
)
INCLUDE_VIDEO = (
    "Also record your screen. The audio is folded into the video for playback and also "
    "kept as a separate file, so the recording never depends on the video surviving."
)
RECOVER_RECORDING = (
    "Appears when a recording was interrupted — the app closed while it was still "
    "running. Repairs what was captured and attaches it to this meeting note."
)
INCLUDE_SYSTEM_AUDIO = (
    "Also record what comes out of your speakers, so the other side of a call is captured "
    "and not just your microphone."
)
MEETING_DATE = (
    "Pick a day, or type one as YYYY-MM-DD. Future dates are fine — that's how you write "
    "an agenda before the meeting happens."
)
MEETING_PERSON = (
    "Who this standing meeting is with. One person per series — a series books their "
    "slot in your week."
)
MEETING_PEOPLE = (
    "Who the meeting is with. Pick or type a name and press Enter (or + Add) for each "
    "person — a group meeting can hold as many as you like.\n\nThis drives the catch-up "
    "panel: it's how the app knows when you last saw each of them. Saving a name that "
    "isn't in your CRM offers to add them."
)
MEETING_PEOPLE_ADD = (
    "Add this name to the meeting. Enter does the same.\n\nEveryone added shows as a chip "
    "below — click the x on one to take them out.\n\nA later 1:1 with any of them opens "
    "with what this meeting agreed, and its open items carry forward to each of them."
)
SAVE_MEETING = "Save the note and close the window. Shortcut: Ctrl+S."

# --- Agenda / action items --------------------------------------------------

AGENDA_TICK = (
    "Tick when it's done.\n\nTicked items are reported as closed in your next catch-up "
    "brief instead of rolling onto the next agenda."
)
AGENDA_TO_TASKS = (
    "Create a task from this item, linked to it.\n\nComplete it in the Tasks tab and it "
    "counts as done here too — it won't be asked about again next time."
)
AGENDA_IN_TASKS = "Already a task. Completing it in the Tasks tab closes it here as well."
AGENDA_REMOVE = "Remove this row from the agenda."
AGENDA_ADD = "Add an empty row. Pressing Enter in a filled row does the same."
AGENDA_BULK_TO_TASKS = (
    "Turn every unticked item into a linked task in one go."
)


def agenda_carried(count, first_raised):
    """Tooltip for the ↻ badge on an item that keeps rolling forward."""
    times = "time" if count == 1 else "times"
    since = f", first raised {first_raised}" if first_raised else ""
    return (
        f"Carried forward {count} {times}{since}.\n\n"
        "It came off your last agenda unfinished. The longer this number gets, the more "
        "it's worth either doing or dropping."
    )


# --- Catch-up panel ---------------------------------------------------------

CATCHUP_HEADLINE = (
    "Everything logged since the last meeting with these people — including the whole of "
    "that day, since meeting notes have no time on them.\n\nWith several people, the "
    "window opens at the oldest of their last meetings, so nobody's open items are left "
    "behind.\n\nOpen items are the ones that came off those agendas unfinished."
)
CATCHUP_GENERATE = (
    "Read every meeting in the “What happened” tab and write the update you can talk "
    "from: what's moved, where last time's items stand, what you need from them.\n\n"
    "Uses the catch-up model from Settings (⚙)."
)
CATCHUP_REGENERATE = (
    "Write the brief again from the notes as they stand now. The old one is replaced."
)
CATCHUP_COPY = "Copy whichever tab you're reading to the clipboard."
CATCHUP_REFRESH = (
    "Rebuild from the notes as they stand now — after editing another meeting, or "
    "changing the person or date above."
)
CATCHUP_PULL = (
    "Add the unfinished items from your last meeting with each of these people to this "
    "agenda, keeping how long each has been rolling. An item raised with two of them "
    "lands once.\n\nHappens by itself when you open a note with an empty agenda."
)
CATCHUP_BRIEF_TAB = "The written update. Generate it with the button below."
CATCHUP_PACK_TAB = (
    "Every meeting since you last saw these people, exactly as the AI receives it. Always "
    "available, with or without an API key."
)
CATCHUP_SUGGEST = (
    "You seem to be meeting this person on a regular pattern. Setting it up as a "
    "recurring meeting creates the notes ahead of time and writes each catch-up brief "
    "without being asked."
)

# --- Recurring meetings -----------------------------------------------------

RECURRING_DAYS = "Which days of the week you meet. A blank note is created for each one."
RECURRING_CATCHUP = (
    "Write the catch-up brief automatically when you open each meeting.\n\nOne AI call "
    "per meeting, cached afterwards. Leave it off to press Generate yourself."
)
RECURRING_STOP = (
    "Stop creating new notes for this series. Notes already written are kept."
)
RECURRING_TOGGLE_BRIEF = "Turn automatic catch-up briefs on or off for this series."

# --- Tasks ------------------------------------------------------------------

TASK_OUTSOURCE = "Hand this task to Claude Code as a prompt."
TASK_EMAIL = "Draft an email about this task with the AI."
TASK_DELETE = "Delete this task permanently."
TASK_TAG = (
    "The project this task belongs to. Type a new one or pick a tag you have used "
    "before — the list groups tasks under their tag, so one project reads as one "
    "block."
)
TASK_TAG_FILTER = "Show only the tasks tagged with one project."
TASK_COMPLETE = (
    "Mark it done. It moves to History — and closes the agenda item it came from, if it "
    "came from one."
)
TASK_REOPEN = (
    "Ticked something off by mistake? This puts the task back on the active list, "
    "notes and tag intact, and reopens the agenda item it closed."
)
TASK_QUICK_TAG = (
    "File this task under a project without opening it: pick a tag or type a new one "
    "and it is saved straight away. The ⤵ button reuses the tag you filed last, so a "
    "batch of untagged tasks is one click each."
)
TASK_GROUP_TOGGLE = (
    "Click the heading to roll this project up or down. Collapsed projects stay "
    "collapsed next time you open the app, so you scroll past the work you are not "
    "doing today."
)
TASK_COLLAPSE_ALL = (
    "Roll every project up so only the headings show — then open the one you are "
    "working on. Click again to expand them all."
)


# --- Progress summary -------------------------------------------------------

PROGRESS_OPEN = (
    "Summarise a stretch of time — every meeting and completed task in it — into the "
    "update you send someone who has been away. Defaults to the last two weeks."
)
PROGRESS_HEADLINE = "What the chosen range covers: meetings, people, work closed."
PROGRESS_SUMMARISE = (
    "Read everything in the “What happened” tab and write the update: what moved, what "
    "is still in flight, what's at risk, what needs them.\n\n"
    "Uses the catch-up model from Settings (⚙)."
)
PROGRESS_COPY = "Copy whichever tab you're reading to the clipboard."
PROGRESS_UPDATE_TAB = "The written update. Generate it with the button below."
PROGRESS_PACK_TAB = (
    "Every meeting and completed task in the range, exactly as the AI receives it. "
    "Always available, with or without an API key."
)

# --- Meetings tab -----------------------------------------------------------

MEETINGS_ADD = "Write a new meeting note."
MEETINGS_RECURRING = (
    "Set up and manage standing meetings — the people you see on a repeating pattern."
)
MEETINGS_EDIT = "Open the selected note."
MEETINGS_DELETE = "Delete the selected note permanently."
