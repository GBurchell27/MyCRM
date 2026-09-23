"""Decides which agenda items follow you into the next meeting.

An item that was ticked, or whose Tasks entry has been completed, is finished:
it belongs in the "here's what I got done" half of the update, not on the
agenda again. Everything else rolls forward carrying its history, so an item
raised three meetings ago is visibly an item raised three meetings ago.

The previous meeting's note is never rewritten. It records what was true on the
day; completions are reported forwards.
"""

from helpers import parse_agenda_items
from task_manager import TaskManager

CLOSED_BY_TICK = "ticked"
CLOSED_BY_TASK = "task"


def item_key(item):
    """Identity for dedupe: the title, normalised."""
    return " ".join(str(item.get("text", "")).split()).casefold()


class CarriedItem:
    """An open item on its way into the next meeting."""

    def __init__(self, item, first_raised, carried_count, source_meeting_id):
        self.item = item
        self.first_raised = first_raised
        self.carried_count = carried_count
        self.source_meeting_id = source_meeting_id

    def as_agenda_item(self):
        carried = dict(self.item)
        carried["checked"] = False
        carried["first_raised"] = self.first_raised
        carried["carried_count"] = self.carried_count
        carried["source_meeting_id"] = self.source_meeting_id
        return carried


class ClosedItem:
    """An item that got finished since the last meeting."""

    def __init__(self, item, closed_by, completed_at=""):
        self.item = item
        self.closed_by = closed_by
        self.completed_at = completed_at

    @property
    def title(self):
        return str(self.item.get("text", "")).strip()

    @property
    def detail(self):
        return str(self.item.get("detail", "") or "").strip()


class CarryOverManager:
    """Splits a previous meeting's agenda into what's done and what follows on."""

    @classmethod
    def split_anchor_items(cls, anchor_row, task_states=None):
        """Return (carried, closed) for the meeting we're catching up from."""
        if anchor_row is None:
            return [], []
        items = parse_agenda_items(anchor_row["agenda_items"])
        anchor_date = (anchor_row["date"] or "").strip()
        anchor_id = anchor_row["id"]
        if task_states is None:
            task_states = TaskManager.states_for(
                [item.get("task_id") for item in items if item.get("task_id")]
            )

        carried, closed = [], []
        for item in items:
            if not str(item.get("text", "")).strip():
                continue
            if item.get("checked"):
                closed.append(ClosedItem(item, CLOSED_BY_TICK))
                continue
            task = cls._linked_task(item, task_states)
            if task is not None and task["completed_at"]:
                closed.append(ClosedItem(item, CLOSED_BY_TASK, task["completed_at"]))
                continue
            carried.append(cls._stamp(item, task, anchor_date, anchor_id))
        return carried, closed

    @staticmethod
    def _linked_task(item, task_states):
        task_id = item.get("task_id")
        if task_id is None:
            return None
        return task_states.get(int(task_id))

    @staticmethod
    def _stamp(item, task, anchor_date, anchor_id):
        carried = dict(item)
        if item.get("task_id") is not None and task is None:
            # The task row was deleted. Not done — just no longer tracked.
            carried.pop("task_id", None)
            carried["in_tasks"] = False
        return CarriedItem(
            carried,
            first_raised=item.get("first_raised") or anchor_date,
            carried_count=int(item.get("carried_count") or 0) + 1,
            source_meeting_id=anchor_id,
        )

    @classmethod
    def split_anchors(cls, anchor_rows, task_states=None):
        """The same split across several previous meetings, folded into one pair.

        A group meeting and a 1:1 can raise the same item; carrying it twice
        would put it on the agenda twice and age it wrongly. Finished beats
        open — something ticked in Tuesday's 1:1 is done even though Monday's
        group note still shows it open — and a surviving item keeps the oldest
        first-raised date it has anywhere, so its age is the true one.
        """
        carried, closed = [], []
        for row in anchor_rows:
            row_carried, row_closed = cls.split_anchor_items(row, task_states)
            carried.extend(row_carried)
            closed.extend(row_closed)
        closed = cls._dedupe_closed(closed)
        finished = {item_key(entry.item) for entry in closed}
        return cls._dedupe_carried(carried, finished), closed

    @staticmethod
    def _dedupe_carried(entries, finished):
        merged, order = {}, []
        for entry in entries:
            key = item_key(entry.item)
            if key in finished:
                continue
            previous = merged.get(key)
            if previous is None:
                merged[key] = entry
                order.append(key)
                continue
            # Later anchors are read last, so their wording and task link win.
            merged[key] = CarriedItem(
                entry.item,
                first_raised=min(
                    [date for date in (previous.first_raised, entry.first_raised) if date],
                    default="",
                ),
                carried_count=max(previous.carried_count, entry.carried_count),
                source_meeting_id=entry.source_meeting_id,
            )
        return [merged[key] for key in order]

    @staticmethod
    def _dedupe_closed(entries):
        merged, order = {}, []
        for entry in entries:
            key = item_key(entry.item)
            if key not in merged:
                merged[key] = entry
                order.append(key)
            elif merged[key].closed_by != CLOSED_BY_TICK and entry.closed_by == CLOSED_BY_TICK:
                merged[key] = entry
        return [merged[key] for key in order]

    @staticmethod
    def merge_into(existing_items, carried):
        """Fold carried items into a meeting's agenda without duplicating.

        Existing rows win on wording — the user may have edited the text — but
        adopt the carried item's history, so re-raising something by hand (or an
        AI action item landing on the same wording) doesn't reset its age.
        """
        merged = [dict(item) for item in existing_items if str(item.get("text", "")).strip()]
        by_key = {item_key(item): item for item in merged}
        added = 0
        for carried_item in carried:
            payload = carried_item.as_agenda_item()
            existing = by_key.get(item_key(payload))
            if existing is None:
                merged.append(payload)
                by_key[item_key(payload)] = payload
                added += 1
                continue
            for key in ("first_raised", "carried_count", "source_meeting_id", "task_id"):
                if existing.get(key) is None and payload.get(key) is not None:
                    existing[key] = payload[key]
            if payload.get("in_tasks") and not existing.get("in_tasks"):
                existing["in_tasks"] = True
        return merged, added
