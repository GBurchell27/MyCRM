"""Which task groups are rolled up in the active list, remembered between runs.

Collapsing is a view preference rather than task data, so the set of collapsed
project headings lives in the app_settings key/value store as one JSON row — no
schema change, and it survives a restart so a long project you are not working
on today stays out of the way tomorrow too.

The untagged group is stored under the empty string, the same key the tasks
themselves use for "no project".
"""

import json

from db import get_setting, set_setting

UNTAGGED = ""


class CollapsedTaskGroups:
    """The set of collapsed headings, saved the moment one is toggled."""

    SETTING_KEY = "tasks_collapsed_groups"

    def __init__(self, key=SETTING_KEY):
        self._key = key
        self._collapsed = self._load()

    def is_collapsed(self, tag):
        return (tag or UNTAGGED) in self._collapsed

    def toggle(self, tag):
        """Flip one heading and return its new collapsed state."""
        tag = tag or UNTAGGED
        if tag in self._collapsed:
            self._collapsed.discard(tag)
        else:
            self._collapsed.add(tag)
        self._save()
        return tag in self._collapsed

    def all_collapsed(self, tags):
        """True when every heading on screen is already rolled up."""
        tags = list(tags)
        return bool(tags) and all(self.is_collapsed(tag) for tag in tags)

    def collapse_all(self, tags):
        self._collapsed.update(tag or UNTAGGED for tag in tags)
        self._save()

    def expand_all(self, tags):
        self._collapsed.difference_update(tag or UNTAGGED for tag in tags)
        self._save()

    def _load(self):
        raw = get_setting(self._key, "")
        if not str(raw).strip():
            return set()
        try:
            stored = json.loads(raw)
        except (TypeError, ValueError):
            return set()
        if not isinstance(stored, list):
            return set()
        return {str(tag) for tag in stored}

    def _save(self):
        set_setting(self._key, json.dumps(sorted(self._collapsed)))
