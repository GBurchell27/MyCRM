"""Turns a progress pack into the update you send someone who has been away.

Close cousin of the catch-up brief, but written for the opposite direction: a
catch-up prepares you to walk into a meeting, this one is read by someone who
missed the fortnight and wants to know what moved, what slipped, and what needs
them. It is written to be pasted into an email, so it leads with the summary.
"""

from ai_client import chat_completion, client, parse_json_reply, string_list
from config.ai_models import CATCHUP, chat_completion_kwargs, supports_custom_temperature

PROGRESS_SYSTEM = """You write a progress update for a manager who has been away.

The user reports to this person and is telling them what happened while they
were out. You are given every meeting logged in the period, the tasks the user
completed, the action items ticked off, and the ones still open.

Return ONLY valid JSON with this shape:
{
  "headline": "3-5 sentences summarising the period, readable on its own",
  "highlights": [
    {"headline": "Short subject line",
     "detail": "One or two sentences of substance",
     "source": "Person, YYYY-MM-DD"}
  ],
  "delivered": ["Something finished in this period, one line each"],
  "in_flight": [
    {"item": "The piece of work, worded as it appears in the input",
     "status": "on track | slipping | blocked | not started",
     "detail": "What the input says about where it stands"}
  ],
  "risks": ["Slipping commitments, repeated blockers, things that went quiet"],
  "needs_you": ["Something only the manager can decide, unblock or approve"]
}

Rules:
- Every entry in "highlights" MUST carry a source naming the person and the date
  it came from. If you cannot attribute it, leave it out.
- Never state anything the input does not support. An empty list is always better
  than an invented item. A thin update is fine; a wrong one is not.
- Group by theme or workstream, not by meeting. The manager cares what moved,
  not which day it was discussed on.
- "delivered" is for work that is actually done — completed tasks and ticked-off
  action items. Anything still in progress belongs in "in_flight".
- An item that appears in several meetings without moving is a risk, not a
  highlight.
- Write for someone who knows the projects. No throat-clearing, no explaining
  what a project is, no filler, no sign-off.
- Notes may be dictated and ramble. Condense; never quote the rambling.
"""


def summarize_progress(pack_text):
    """Generate the update. Returns the parsed dict. Raises RuntimeError on failure."""
    if not (pack_text or "").strip():
        raise RuntimeError("Nothing to summarise — no meetings or tasks in this range.")
    kwargs = chat_completion_kwargs(CATCHUP)
    if supports_custom_temperature(kwargs["model"]):
        kwargs["temperature"] = 0.2
    response = chat_completion(
        client(),
        messages=[
            {"role": "system", "content": PROGRESS_SYSTEM},
            {"role": "user", "content": pack_text},
        ],
        response_format={"type": "json_object"},
        **kwargs,
    )
    return normalise(parse_json_reply(response))


def normalise(data):
    """Coerce whatever came back into the shape the renderer expects."""
    return {
        "headline": str(data.get("headline") or "").strip(),
        "highlights": _objects(data.get("highlights"), ("headline", "detail", "source")),
        "delivered": string_list(data.get("delivered")),
        "in_flight": _objects(data.get("in_flight"), ("item", "status", "detail")),
        "risks": string_list(data.get("risks")),
        "needs_you": string_list(data.get("needs_you")),
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


def render(update, start_date="", end_date=""):
    """The update as shown in the panel and copied to the clipboard."""
    blocks = []
    if start_date and end_date:
        blocks.append(f"Progress update — {start_date} to {end_date}")
    if update["headline"]:
        blocks.append(update["headline"])
    if update["highlights"]:
        lines = []
        for highlight in update["highlights"]:
            line = f"• {highlight['headline']}"
            if highlight["detail"]:
                line += f"\n  {highlight['detail']}"
            if highlight["source"]:
                line += f"\n  ({highlight['source']})"
            lines.append(line)
        blocks.append("HIGHLIGHTS\n" + "\n".join(lines))
    if update["delivered"]:
        blocks.append("DONE\n" + "\n".join(f"• {item}" for item in update["delivered"]))
    if update["in_flight"]:
        lines = [
            f"• [{row['status'] or 'unknown'}] {row['item']}"
            + (f"\n  {row['detail']}" if row["detail"] else "")
            for row in update["in_flight"]
        ]
        blocks.append("IN FLIGHT\n" + "\n".join(lines))
    if update["risks"]:
        blocks.append("RISKS\n" + "\n".join(f"• {item}" for item in update["risks"]))
    if update["needs_you"]:
        blocks.append("WHAT I NEED FROM YOU\n"
                      + "\n".join(f"• {item}" for item in update["needs_you"]))
    return "\n\n".join(blocks).strip()
