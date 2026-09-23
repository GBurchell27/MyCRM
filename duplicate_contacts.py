"""Fuzzy matching to catch duplicate contact rows for the same person."""

import difflib

from db import get_conn

SIMILARITY_THRESHOLD = 0.82


def normalize_name(name):
    """Strip, casefold, and collapse whitespace for comparison."""
    return " ".join((name or "").strip().casefold().split())


def _similarity(name_a, name_b):
    norm_a, norm_b = normalize_name(name_a), normalize_name(name_b)
    if not norm_a or not norm_b:
        return 0.0
    if norm_a == norm_b or sorted(norm_a.split()) == sorted(norm_b.split()):
        return 1.0
    return difflib.SequenceMatcher(None, norm_a, norm_b).ratio()


def find_possible_duplicates(name, exclude_id=None, threshold=SIMILARITY_THRESHOLD):
    """Return existing contacts whose name closely matches `name`, best match first."""
    if not (name or "").strip():
        return []
    conn = get_conn()
    rows = conn.execute("SELECT * FROM contacts").fetchall()
    conn.close()

    scored = []
    for row in rows:
        if exclude_id is not None and row["id"] == exclude_id:
            continue
        score = _similarity(name, row["name"])
        if score >= threshold:
            scored.append((score, row))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [row for _, row in scored]
