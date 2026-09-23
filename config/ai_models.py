"""Central registry of the AI models used across the app.

Each purpose (summaries, email drafting, transcription) has a settings key
stored in crm_data.db, a default model, and suggested choices. The settings
dialog renders one row per entry in MODEL_SETTINGS, so making a new model
configurable is just adding an entry here and reading it via its accessor.

A chat model is stored as "model" or "model:effort" in a single setting —
"gpt-5.6-terra:max" is the model id with reasoning_effort "max". The dialog
shows those two halves as separate controls; storage keeps them together so no
existing value needs migrating. gpt-5.6-luna is the default everywhere: reach
for terra/sol (":max" for the hardest jobs) when deeper reasoning is worth the
cost.
"""

from db import get_setting

CHAT_MODEL_CHOICES = [
    "gpt-5-mini",
    "gpt-5",
    "gpt-5.6-luna",
    "gpt-5.6-terra",
    "gpt-5.6-sol",
    "gpt-4o-mini",
    "gpt-4o",
]

TRANSCRIPTION_MODEL_CHOICES = [
    "whisper-1",
    "gpt-4o-mini-transcribe",
    "gpt-4o-transcribe",
]

# "" means send no reasoning_effort at all and let the API pick.
DEFAULT_EFFORT_LABEL = "Model default"

REASONING_EFFORT_CHOICES = [
    ("", DEFAULT_EFFORT_LABEL),
    ("minimal", "minimal — fastest, cheapest"),
    ("low", "low"),
    ("medium", "medium"),
    ("high", "high"),
    ("xhigh", "xhigh"),
    ("max", "max — slowest, most thorough"),
]

CHAT = "chat"
TRANSCRIPTION_KIND = "transcription"

SUMMARY = {
    "label": "Meeting summaries",
    "key": "openai_model",
    "default": "gpt-5.6-luna",
    "choices": CHAT_MODEL_CHOICES,
    "kind": CHAT,
    "help": (
        "Turns your notes, the transcript and the activity log into the meeting "
        "summary, highlights, and the action items that land on the agenda."
    ),
}

CATCHUP = {
    "label": "Catch-up briefs",
    "key": "openai_catchup_model",
    "default": "gpt-5.6-terra",
    "choices": CHAT_MODEL_CHOICES,
    "kind": CHAT,
    "help": (
        "Reads every meeting since you last saw someone and writes the update you "
        "talk from. The job with the most to read — worth a stronger model."
    ),
}

CONTACT = {
    "label": "New contact details",
    "key": "openai_contact_model",
    "default": "gpt-5.6-luna",
    "choices": CHAT_MODEL_CHOICES,
    "kind": CHAT,
    "help": (
        "Reads a meeting for the team, office, role and manager of someone who "
        "isn't in your CRM yet, to pre-fill the Add Contact dialog."
    ),
}

EMAIL = {
    "label": "Email drafting",
    "key": "openai_email_model",
    "default": "gpt-5.6-luna",
    "choices": CHAT_MODEL_CHOICES,
    "kind": CHAT,
    "help": "Drafts the email behind the ✉ button on a task. Short, one-shot work.",
}

TRANSCRIPTION = {
    "label": "Audio transcription",
    "key": "openai_transcribe_model",
    "default": "whisper-1",
    "choices": TRANSCRIPTION_MODEL_CHOICES,
    "kind": TRANSCRIPTION_KIND,
    "help": (
        "Turns recordings and dictation into text. Transcription models take no "
        "reasoning effort."
    ),
}

MODEL_SETTINGS = [SUMMARY, CATCHUP, CONTACT, EMAIL, TRANSCRIPTION]


def _model(setting):
    value = get_setting(setting["key"], setting["default"])
    return (value or "").strip() or setting["default"]


def summary_model():
    return _model(SUMMARY)


def catchup_model():
    return _model(CATCHUP)


def contact_model():
    return _model(CONTACT)


def email_model():
    return _model(EMAIL)


def transcription_model():
    return resolve_chat_model(_model(TRANSCRIPTION))[0]


def stored_value(setting):
    """The raw "model" or "model:effort" string this purpose is set to."""
    return _model(setting)


def resolve_chat_model(value):
    """Split "model:effort" (e.g. "gpt-5.6-terra:max") into (model_id, effort or "")."""
    model, _, effort = (value or "").partition(":")
    return model.strip(), effort.strip().lower()


def combine_chat_model(model, effort):
    """The inverse of resolve_chat_model — what gets written to the settings row."""
    model = (model or "").strip()
    effort = (effort or "").strip().lower()
    if not model:
        return ""
    if not effort or not supports_reasoning_effort(model):
        return model
    return f"{model}:{effort}"


def is_reasoning_model(model):
    """True for the model families that take a reasoning_effort instead of a temperature."""
    return (model or "").strip().lower().startswith(("gpt-5", "o1", "o3", "o4"))


def supports_reasoning_effort(model):
    return is_reasoning_model(model)


def supports_custom_temperature(model):
    """The gpt-5 family and o-series reasoning models reject non-default temperature."""
    return not is_reasoning_model(model)


def chat_completion_kwargs(setting):
    """Model kwargs for client.chat.completions.create(), incl. reasoning effort."""
    model, effort = resolve_chat_model(_model(setting))
    kwargs = {"model": model}
    if effort and supports_reasoning_effort(model):
        kwargs["reasoning_effort"] = effort
    return kwargs
