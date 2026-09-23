"""Typed, self-describing preferences — the pieces a settings registry is built from.

A Setting owns its storage key, its default, and the rules for turning what the
database holds (always text) into a usable Python value. Everything the settings
dialog needs to draw a control lives on the object, so adding a preference means
adding one entry to a registry — no dialog code changes, no new save path.

Reads go straight to the database each time rather than through a cache, so a
setting changed in the dialog takes effect on the next use without a restart.
"""

from db import get_setting, set_setting


class Setting:
    """One persisted preference. Subclasses define the value type."""

    kind = "text"

    def __init__(self, key, label, default, help_text=""):
        self.key = key
        self.label = label
        self.default = default
        self.help_text = help_text

    def get(self):
        """The stored value, coerced — falling back to the default if unusable."""
        raw = get_setting(self.key, None)
        if raw is None or not str(raw).strip():
            return self.default
        try:
            return self.coerce(str(raw))
        except (TypeError, ValueError):
            return self.default

    def save(self, value):
        set_setting(self.key, self.to_storage(value))

    def coerce(self, raw):
        return raw.strip()

    def to_storage(self, value):
        return str(value)


class BoolSetting(Setting):
    """A checkbox. Stored as "1"/"0"."""

    kind = "bool"

    TRUTHY = ("1", "true", "yes", "on")

    def coerce(self, raw):
        return raw.strip().lower() in self.TRUTHY

    def to_storage(self, value):
        return "1" if value else "0"


class IntSetting(Setting):
    """A whole number within a range. Out-of-range values are clamped, not rejected.

    Clamping matters because these are read on hot paths (every catch-up, every
    recording): a typo in the dialog should narrow the window, never raise deep
    inside a feature that has nothing to do with settings.
    """

    kind = "int"

    def __init__(self, key, label, default, minimum, maximum, unit="", help_text=""):
        super().__init__(key, label, default, help_text)
        self.minimum = minimum
        self.maximum = maximum
        self.unit = unit

    def coerce(self, raw):
        return self.clamp(int(float(raw.strip())))

    def clamp(self, value):
        return max(self.minimum, min(self.maximum, value))

    def to_storage(self, value):
        return str(self.clamp(int(value)))


class ChoiceSetting(Setting):
    """A fixed set of values, shown by their labels.

    `options` is a list of (value, label) pairs: the value is what gets stored
    and what callers switch on, the label is only ever seen on screen.
    """

    kind = "choice"

    def __init__(self, key, label, default, options, help_text=""):
        super().__init__(key, label, default, help_text)
        self.options = list(options)

    @property
    def values(self):
        return [value for value, _ in self.options]

    @property
    def labels(self):
        return [text for _, text in self.options]

    def label_for(self, value):
        for candidate, text in self.options:
            if candidate == value:
                return text
        return str(value)

    def value_for(self, label):
        for value, text in self.options:
            if text == label:
                return value
        return self.default

    def coerce(self, raw):
        value = raw.strip()
        return value if value in self.values else self.default


class SettingsSection:
    """A named group of settings — one page of the settings dialog."""

    def __init__(self, title, blurb, settings):
        self.title = title
        self.blurb = blurb
        self.settings = list(settings)

    def __iter__(self):
        return iter(self.settings)
