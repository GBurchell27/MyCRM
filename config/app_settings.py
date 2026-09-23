"""Every preference the app exposes that isn't a choice of AI model.

One object per setting, grouped into the sections the settings dialog shows as
pages. Callers read a setting where they use it — `CATCHUP_LOOKBACK_DAYS.get()`
— rather than caching it at import time, so changing a setting takes effect
without restarting the app.

Model choices live in config/ai_models.py; they need a registry of their own
because a model carries a reasoning effort alongside it.
"""

from config.setting_types import BoolSetting, ChoiceSetting, IntSetting, SettingsSection

# --- General ----------------------------------------------------------------

TAB_CRM = "crm"
TAB_MEETINGS = "meetings"
TAB_TASKS = "tasks"

STARTUP_TAB = ChoiceSetting(
    key="startup_tab",
    label="Open on startup",
    default=TAB_MEETINGS,
    options=[(TAB_CRM, "CRM"), (TAB_MEETINGS, "Meeting Notes"), (TAB_TASKS, "Tasks")],
    help_text="Which tab is selected when the app opens.",
)

HOVER_PREVIEWS = BoolSetting(
    key="hover_previews_enabled",
    label="Show row previews on hover",
    default=True,
    help_text="The yellow popup with a row's full details when you rest the mouse on it.",
)

# --- Catch-up ---------------------------------------------------------------

CATCHUP_LOOKBACK_DAYS = IntSetting(
    key="catchup_lookback_days",
    label="Look back at most",
    default=14,
    minimum=1,
    maximum=180,
    unit="days",
    help_text=(
        "How far back “what has happened since” reaches when you last saw someone a "
        "long time ago. Open items still carry forward from further back than this — "
        "only the sweep of other meetings is bounded."
    ),
)

CATCHUP_FALLBACK_DAYS = IntSetting(
    key="catchup_fallback_days",
    label="First meeting covers",
    default=7,
    minimum=1,
    maximum=180,
    unit="days",
    help_text="The window used when there is no previous meeting with this person at all.",
)

CATCHUP_MEETING_CHARS = IntSetting(
    key="catchup_meeting_chars",
    label="Characters kept per meeting",
    default=3000,
    minimum=500,
    maximum=20000,
    unit="chars",
    help_text=(
        "Each meeting is trimmed to this length before the AI sees it, so one long "
        "transcript can't crowd out four other meetings. Raising it costs more per brief."
    ),
)

CATCHUP_AUTO_PULL = BoolSetting(
    key="catchup_auto_pull",
    label="Carry open items forward automatically",
    default=True,
    help_text=(
        "When you open a saved note with an empty agenda, last meeting's unfinished "
        "items are added and saved. Turn off to pull them in yourself."
    ),
)

CATCHUP_AUTO_BRIEF = BoolSetting(
    key="catchup_auto_brief",
    label="Write briefs for recurring meetings automatically",
    default=True,
    help_text=(
        "The master switch for the per-series setting: with this off, no meeting "
        "writes its brief on open no matter how its series is configured. One AI call "
        "per meeting, cached afterwards."
    ),
)

# --- Meetings and recording -------------------------------------------------

RECURRING_HORIZON_DAYS = IntSetting(
    key="recurring_horizon_days",
    label="Create recurring notes",
    default=7,
    minimum=1,
    maximum=120,
    unit="days ahead",
    help_text=(
        "How far ahead placeholder notes are generated for standing meetings. "
        "Topped up each time the app starts."
    ),
)

RECORD_INCLUDE_VIDEO = BoolSetting(
    key="record_include_video",
    label="Include screen video by default",
    default=True,
    help_text="How the “Include screen video” box starts in a new meeting note.",
)

RECORD_INCLUDE_SYSTEM_AUDIO = BoolSetting(
    key="record_include_system_audio",
    label="Include system audio by default",
    default=True,
    help_text=(
        "How the “Include system audio” box starts — the other side of a call rather "
        "than just your microphone. Ignored on machines with no system-audio device."
    ),
)

DICTATION_MAX_MINUTES = IntSetting(
    key="dictation_max_minutes",
    label="Stop dictation after",
    default=10,
    minimum=1,
    maximum=13,
    unit="minutes",
    help_text=(
        "A safety net for a mic left running. 16 kHz mono audio hits the 25 MB "
        "transcription upload limit at about 13 minutes, so this cannot go higher."
    ),
)

# --- Sections, in the order the dialog shows them ---------------------------

GENERAL_SECTION = SettingsSection(
    "General",
    "How the app opens and behaves.",
    [STARTUP_TAB, HOVER_PREVIEWS],
)

CATCHUP_SECTION = SettingsSection(
    "Catch-up",
    "What “since you last met” covers, and how much of it the AI is given.",
    [
        CATCHUP_LOOKBACK_DAYS,
        CATCHUP_FALLBACK_DAYS,
        CATCHUP_MEETING_CHARS,
        CATCHUP_AUTO_PULL,
        CATCHUP_AUTO_BRIEF,
    ],
)

MEETINGS_SECTION = SettingsSection(
    "Meetings",
    "Standing meetings, and how a new note starts out.",
    [
        RECURRING_HORIZON_DAYS,
        RECORD_INCLUDE_VIDEO,
        RECORD_INCLUDE_SYSTEM_AUDIO,
        DICTATION_MAX_MINUTES,
    ],
)

SETTING_SECTIONS = [GENERAL_SECTION, CATCHUP_SECTION, MEETINGS_SECTION]
