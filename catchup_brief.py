"""Stores a generated catch-up brief and knows when it has gone out of date.

A brief written on Sunday for Tuesday's meeting is missing Monday. Recording
which meetings it was built from turns that from a silent wrong answer into a
banner offering to regenerate.
"""

import json
from datetime import datetime

from config.ai_models import catchup_model
from meeting_store import update_catchup
from meeting_window import field


class CatchupBriefManager:
    @staticmethod
    def load(meeting_row):
        """Return (brief_text, meta) for a saved meeting row."""
        if meeting_row is None:
            return "", {}
        brief = str(field(meeting_row, "catchup_brief")).strip()
        try:
            meta = json.loads(field(meeting_row, "catchup_meta") or "{}")
        except (json.JSONDecodeError, TypeError):
            meta = {}
        return brief, meta if isinstance(meta, dict) else {}

    @staticmethod
    def save(meeting_id, brief_text, window):
        """Persist the brief alongside a record of exactly what it covered."""
        meta = {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "anchor_meeting_id": window.anchor_id,
            "anchor_meeting_ids": window.anchor_ids,
            "source_meeting_ids": window.source_meeting_ids,
            "window": [window.start_date, window.meeting_date],
            "model": catchup_model(),
        }
        update_catchup(meeting_id, brief_text, meta)
        return meta

    @staticmethod
    def staleness_notice(meta, window):
        """A line to show above the brief when it no longer matches reality."""
        if not meta:
            return ""
        covered = set(meta.get("source_meeting_ids") or [])
        current = set(window.source_meeting_ids)
        if CatchupBriefManager._anchors_moved(meta, window):
            return "You've met since this brief was written — regenerate it."
        new = current - covered
        if new:
            count = len(new)
            return (f"{count} new meeting{'s' if count != 1 else ''} logged since this "
                    "brief was written — regenerate it.")
        if covered - current:
            return "A meeting this brief covered has been deleted — regenerate it."
        return ""

    @staticmethod
    def _anchors_moved(meta, window):
        """Has anyone in this meeting been seen since the brief was written?

        Briefs saved before group meetings existed only recorded one anchor id;
        fall back to it so an old brief isn't declared stale on a technicality.
        """
        if "anchor_meeting_ids" in meta:
            return set(meta.get("anchor_meeting_ids") or []) != set(window.anchor_ids)
        return meta.get("anchor_meeting_id") != window.anchor_id

    @staticmethod
    def describe_generation(meta):
        if not meta.get("generated_at"):
            return ""
        model = meta.get("model") or ""
        suffix = f" · {model}" if model else ""
        return f"Brief written {meta['generated_at']}{suffix}"
