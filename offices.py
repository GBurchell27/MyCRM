"""Company offices: the known list, their colour coding, and text matching.

Office is a separate axis from team: `team` says what someone does (Sales,
Marketing), `office` says where they sit. Keeping them apart means the
relationship board can colour by country and still group by function.
"""

import re

OFFICES = ["Netherlands", "Sweden", "Norway", "Germany", "Denmark"]

# office -> (card fill, card outline)
OFFICE_COLORS = {
    "Netherlands": ("#ffe9c9", "#d9a55a"),
    "Sweden": ("#dbe9fa", "#6d9bd1"),
    "Norway": ("#d5f0ec", "#59a99e"),
    "Germany": ("#e5e2f5", "#8c86c4"),
    "Denmark": ("#fbdfe8", "#cf8aa5"),
}
UNKNOWN_COLORS = ("#eef0f2", "#a8b2bd")

# Handed out to offices opened later, so new sites still read as distinct
# instead of every one of them falling back to grey.
_SPARE_COLORS = [
    ("#e3f1d8", "#93b573"),
    ("#f6e3f7", "#bd8fc4"),
    ("#fdf0d0", "#c9ab5f"),
    ("#e8e4dc", "#ab9d86"),
]

# Cities and codes people actually say, mapped to the office they mean.
_ALIASES = {
    "Netherlands": [
        "nl", "netherlands", "the netherlands", "holland", "dutch",
        "amsterdam", "rotterdam", "utrecht", "eindhoven", "the hague", "den haag",
    ],
    "Sweden": [
        "se", "sweden", "swedish", "stockholm", "gothenburg", "goteborg",
        "göteborg", "malmo", "malmö",
    ],
    "Norway": ["no", "norway", "norwegian", "oslo", "bergen", "trondheim", "stavanger"],
    "Germany": [
        "de", "germany", "german", "deutschland", "berlin", "munich", "munchen",
        "münchen", "hamburg", "cologne", "koln", "köln", "frankfurt",
        "dusseldorf", "düsseldorf",
    ],
    "Denmark": [
        "dk", "denmark", "danish", "copenhagen", "kobenhavn", "københavn",
        "aarhus", "arhus", "århus", "odense",
    ],
}
_BY_ALIAS = {
    alias: office for office, aliases in _ALIASES.items() for alias in aliases
}


def match_office(text):
    """Return the known office this text refers to, or '' if it names none.

    Strict: used when deciding whether a value is a location at all, such as
    the backfill that splits places out of the old free-text team column.
    """
    cleaned = (text or "").strip().casefold()
    if not cleaned:
        return ""
    if cleaned in _BY_ALIAS:
        return _BY_ALIAS[cleaned]
    # "Stockholm office", "based in Copenhagen" - look for a known word.
    for word in re.findall(r"[\wÀ-ɏ]+", cleaned):
        if word in _BY_ALIAS:
            return _BY_ALIAS[word]
    return ""


def normalise_office(text):
    """Tidy an office value, mapping known cities/codes onto the office name.

    Lenient: unrecognised text is kept as typed, so offices we open next month
    work before anyone updates this file.
    """
    cleaned = " ".join((text or "").split())
    return match_office(cleaned) or cleaned


def office_colors(office):
    """(fill, outline) for a card, including offices not in the known list."""
    name = (office or "").strip()
    if not name:
        return UNKNOWN_COLORS
    if name in OFFICE_COLORS:
        return OFFICE_COLORS[name]
    # Deterministic across runs, unlike hash().
    seed = sum(ord(ch) for ch in name.casefold())
    return _SPARE_COLORS[seed % len(_SPARE_COLORS)]
