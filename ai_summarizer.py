"""AI summarization and action-item extraction for meeting notes."""

from ai_client import (
    chat_completion,
    client as _client,
    has_api_key,
    parse_json_reply,
    string_list,
    transcription as _transcription,
)
from config.ai_models import (
    CONTACT,
    SUMMARY,
    chat_completion_kwargs,
    supports_custom_temperature,
    transcription_model,
)
from offices import OFFICES, normalise_office

__all__ = [
    "has_api_key", "summarize_meeting", "extract_contact_details", "transcribe_audio",
    "DICTATION_PROMPT", "CONTACT_FIELDS",
]

SUMMARY_SYSTEM = """You are an assistant that turns raw meeting notes, transcripts,
and optional computer-activity context into clean personal CRM meeting notes.

Return ONLY valid JSON with this shape:
{
  "summary": "Clear meeting summary in a few short paragraphs",
  "action_items": ["Concrete follow-up or action point", "..."],
  "highlights": ["Notable interest or decision", "..."]
}

Rules:
- Prefer concrete, attributable action items (who/what/when when possible).
- Put decisions and interesting facts in highlights.
- Do not invent facts that are not supported by the input.
- If input is thin, keep summary short and return fewer items.
- Notes may include dictated speech that rambles, repeats itself, or contains
  filler words. Condense such passages into clean, concise notes — keep every
  piece of substance but never echo the rambling verbatim.
"""

# Style hint passed to the transcription model when the user dictates into a
# field, so short rambles come back with clean punctuation.
DICTATION_PROMPT = (
    "Dictated note for a personal CRM: meeting notes, tasks, and contact "
    "details. Clean punctuation. No filler words like um or uh."
)


def summarize_meeting(raw_notes, transcript="", activity_log=""):
    """
    Summarize meeting material via OpenAI.
    Returns dict: summary, action_items (list[str]), highlights (list[str]).
    Raises RuntimeError with a user-facing message on failure.
    """
    client = _client()
    parts = []
    if raw_notes.strip():
        parts.append("## Existing notes\n" + raw_notes.strip())
    if transcript.strip():
        parts.append("## Transcript\n" + transcript.strip())
    if activity_log.strip():
        parts.append("## Computer activity during recording\n" + activity_log.strip())
    if not parts:
        raise RuntimeError("Nothing to summarize — add notes, record audio, or paste a transcript first.")

    kwargs = chat_completion_kwargs(SUMMARY)
    if supports_custom_temperature(kwargs["model"]):
        kwargs["temperature"] = 0.2
    response = chat_completion(
        client,
        messages=[
            {"role": "system", "content": SUMMARY_SYSTEM},
            {"role": "user", "content": "\n\n".join(parts)},
        ],
        response_format={"type": "json_object"},
        **kwargs,
    )
    data = parse_json_reply(response)
    return {
        "summary": (data.get("summary") or "").strip(),
        "action_items": string_list(data.get("action_items")),
        "highlights": string_list(data.get("highlights")),
    }


CONTACT_DETAILS_SYSTEM = """You extract CRM contact details about ONE named person
from a meeting transcript and notes.

Return ONLY valid JSON with this shape:
{
  "team": "Their team or department, by function",
  "office": "The office or country they are based in",
  "role": "Their job title or role",
  "manager": "Who they report to",
  "how_we_met": "One short phrase for the context of this first meeting",
  "notes": "A few short lines of durable personal/professional background"
}

Rules:
- Extract details about the named person ONLY, not about anyone else present.
- Use "" for any field the material does not support. Never guess or infer a
  plausible-sounding value — an empty string is always better than a made-up one.
- team is what they do (Sales, Marketing, Engineering). office is where they
  sit. Never put a place in team, or a function in office.
- office: prefer one of {offices} when the material points to it. A city is
  fine ("Stockholm") — it will be mapped. Only name somewhere else if they are
  clearly based there.
- notes should hold things worth remembering next time: background, tenure,
  projects they own, stated interests or preferences. Keep it factual and skip
  anything already covered by the meeting summary.
- Keep team/office/role/manager to a few words each; they are single-line fields.
- Transcripts may misspell names or ramble. Do not repeat filler verbatim.
""".replace("{offices}", ", ".join(OFFICES))

CONTACT_FIELDS = ("team", "office", "role", "manager", "how_we_met", "notes")


def extract_contact_details(person, raw_notes="", summary="", transcript=""):
    """
    Pull CRM contact details for `person` out of meeting material via OpenAI.
    Returns a dict of CONTACT_FIELDS (all str, may be "").
    Raises RuntimeError with a user-facing message on failure.
    """
    client = _client()
    parts = [f"## Person to profile\n{person}"]
    if raw_notes.strip():
        parts.append("## Meeting notes\n" + raw_notes.strip())
    if summary.strip():
        parts.append("## Meeting summary\n" + summary.strip())
    if transcript.strip():
        parts.append("## Transcript\n" + transcript.strip())
    if len(parts) == 1:
        raise RuntimeError("Nothing to read — no notes, summary, or transcript.")

    kwargs = chat_completion_kwargs(CONTACT)
    if supports_custom_temperature(kwargs["model"]):
        kwargs["temperature"] = 0.2
    response = chat_completion(
        client,
        messages=[
            {"role": "system", "content": CONTACT_DETAILS_SYSTEM},
            {"role": "user", "content": "\n\n".join(parts)},
        ],
        response_format={"type": "json_object"},
        **kwargs,
    )
    data = parse_json_reply(response)
    details = {field: str(data.get(field) or "").strip() for field in CONTACT_FIELDS}
    # The model may answer with a city; store the office it belongs to.
    details["office"] = normalise_office(details["office"])
    return details


def transcribe_audio(audio_path, prompt=None):
    """Transcribe an audio file (WAV/M4A/…) with OpenAI Whisper. Returns transcript text."""
    client = _client()
    kwargs = {"model": transcription_model()}
    if prompt:
        kwargs["prompt"] = prompt
    with open(audio_path, "rb") as audio_file:
        result = _transcription(client, file=audio_file, **kwargs)
    return (result.text or "").strip()
