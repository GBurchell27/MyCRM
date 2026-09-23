"""Turns a catch-up pack into the update you actually give your manager.

Separate from the meeting summarizer because the job is different: that one
condenses one conversation, this one reads several and works out what the other
person needs to hear, what has stalled, and what you need from them.
"""

from ai_client import chat_completion, client, parse_json_reply, string_list
from config.ai_models import CATCHUP, chat_completion_kwargs, supports_custom_temperature

CATCHUP_SYSTEM = """You prepare a briefing for a meeting the user is about to walk into.

The user is about to meet {person} — one person for a standing one-to-one,
several for a group meeting. You are given: what they agreed with {person} last
time, which of those items have since been closed, which are still open, and
notes from every other meeting the user has had in between.

Where several people are meeting, "last time" may be a different meeting for
each of them. Attribute accordingly and never imply someone was in a
conversation the input does not put them in.

Return ONLY valid JSON with this shape:
{
  "since_last_time": "2-4 sentences the user can say out loud to open the meeting",
  "updates": [
    {"headline": "Short subject line",
     "detail": "One or two sentences of substance",
     "source": "Person, YYYY-MM-DD"}
  ],
  "open_items_status": [
    {"item": "The open item, worded as it appears in the input",
     "status": "done | progressed | blocked | no movement",
     "evidence": "What in the input supports that status, or why nothing does"}
  ],
  "decisions_needed": ["Something only {person} can decide, unblock or approve"],
  "risks": ["Slipping commitments, repeated blockers, things going quiet"],
  "suggested_agenda": [{"text": "Short agenda title", "detail": "Why it's on the list"}]
}

Rules:
- Every entry in "updates" MUST carry a source naming the person and date it came
  from. If you cannot attribute it, leave it out.
- Never state anything the input does not support. An empty list is always better
  than an invented item. A thin briefing is fine; a wrong one is not.
- "open_items_status" must cover every item listed as still open, in the same
  order, even when the answer is "no movement" — that absence is the point.
- Flag an item carried across several meetings as a risk, not just an update.
- Write for someone who was in all these meetings. No throat-clearing, no
  recaps of what a project is, no filler.
- Notes may be dictated and ramble. Condense; never quote the rambling.
"""


def _system_prompt(person):
    return CATCHUP_SYSTEM.replace("{person}", person or "your manager")


def summarize_catchup(pack_text, person):
    """Generate the briefing. Returns the parsed dict. Raises RuntimeError on failure."""
    if not (pack_text or "").strip():
        raise RuntimeError("Nothing to brief on yet — no meetings since you last met.")
    kwargs = chat_completion_kwargs(CATCHUP)
    if supports_custom_temperature(kwargs["model"]):
        kwargs["temperature"] = 0.2
    response = chat_completion(
        client(),
        messages=[
            {"role": "system", "content": _system_prompt(person)},
            {"role": "user", "content": pack_text},
        ],
        response_format={"type": "json_object"},
        **kwargs,
    )
    return normalise(parse_json_reply(response))


def normalise(data):
    """Coerce whatever came back into the shape the renderer expects."""
    return {
        "since_last_time": str(data.get("since_last_time") or "").strip(),
        "updates": _objects(data.get("updates"), ("headline", "detail", "source")),
        "open_items_status": _objects(
            data.get("open_items_status"), ("item", "status", "evidence")
        ),
        "decisions_needed": string_list(data.get("decisions_needed")),
        "risks": string_list(data.get("risks")),
        "suggested_agenda": _objects(data.get("suggested_agenda"), ("text", "detail")),
    }


def _objects(value, fields):
    """Keep well-formed dicts, tolerate a bare string, drop anything empty."""
    if not isinstance(value, list):
        return []
    cleaned = []
    for entry in value:
        if isinstance(entry, str):
            entry = {fields[0]: entry}
        if not isinstance(entry, dict):
            continue
        row = {field: str(entry.get(field) or "").strip() for field in fields}
        if row[fields[0]]:
            cleaned.append(row)
    return cleaned


def render(brief):
    """The briefing as the text shown in the panel and copied to the clipboard."""
    blocks = []
    if brief["since_last_time"]:
        blocks.append(brief["since_last_time"])
    if brief["updates"]:
        lines = []
        for update in brief["updates"]:
            line = f"• {update['headline']}"
            if update["detail"]:
                line += f"\n  {update['detail']}"
            if update["source"]:
                line += f"\n  ({update['source']})"
            lines.append(line)
        blocks.append("WHAT'S HAPPENED\n" + "\n".join(lines))
    if brief["open_items_status"]:
        lines = [
            f"• [{row['status'] or 'unknown'}] {row['item']}"
            + (f"\n  {row['evidence']}" if row["evidence"] else "")
            for row in brief["open_items_status"]
        ]
        blocks.append("WHERE LAST TIME'S ITEMS STAND\n" + "\n".join(lines))
    if brief["decisions_needed"]:
        blocks.append("WHAT I NEED FROM YOU\n"
                      + "\n".join(f"• {item}" for item in brief["decisions_needed"]))
    if brief["risks"]:
        blocks.append("RISKS\n" + "\n".join(f"• {item}" for item in brief["risks"]))
    if brief["suggested_agenda"]:
        lines = [
            f"• {row['text']}" + (f" — {row['detail']}" if row["detail"] else "")
            for row in brief["suggested_agenda"]
        ]
        blocks.append("SUGGESTED AGENDA\n" + "\n".join(lines))
    return "\n\n".join(blocks).strip()
