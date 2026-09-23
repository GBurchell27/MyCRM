"""Relationship board data: people/note nodes and the links between them.

The board is a free-form canvas layer over the CRM. Every contact can appear
as a node, node positions are remembered between sessions, and links record
how people relate to each other (who reports to whom, who shares a team, ...).
Contact details are never copied here - they are read live from `contacts`.
"""

from collections import defaultdict
from datetime import date

import attendees
from db import get_conn

# How long since you last spoke before a card starts fading.
FRESH_DAYS = 30
STALE_DAYS = 90
FADED_DAYS = 180
MAX_FADE = 0.75  # never fade so far that the card stops being readable

CONTACT_NODE = "contact"
NOTE_NODE = "note"

# kind -> (display text, directed?)
RELATIONSHIP_KINDS = {
    "reports_to": ("reports to", True),
    "manages": ("manages", True),
    "same_team": ("same team", False),
    "works_with": ("works with", False),
    "introduced_by": ("introduced by", True),
    "custom": ("linked to", False),
}
KIND_ORDER = [
    "reports_to", "manages", "same_team", "works_with", "introduced_by", "custom",
]

NOTE_COLORS = {
    "Yellow": "#fff3bf",
    "Blue": "#e3f0fd",
    "Green": "#e2f5e6",
    "Pink": "#fbe4ef",
    "Grey": "#eceef0",
}

_NODE_QUERY = """
    SELECT n.id, n.kind, n.contact_id, n.label, n.x, n.y, n.notes, n.color,
           c.name AS contact_name, c.team, c.office, c.role, c.manager,
           c.met_on, c.how_we_met, c.notes AS crm_notes
    FROM board_nodes n
    LEFT JOIN contacts c ON c.id = n.contact_id
    ORDER BY n.id
"""


# --- reading ---------------------------------------------------------------

def load_board(today=None):
    """Return (nodes, edges) with CRM details merged into the contact nodes."""
    conn = get_conn()
    nodes = [dict(row) for row in conn.execute(_NODE_QUERY)]
    edges = [dict(row) for row in conn.execute("SELECT * FROM board_edges ORDER BY id")]
    conn.close()
    node_ids = {n["id"] for n in nodes}
    edges = [e for e in edges if e["from_node"] in node_ids and e["to_node"] in node_ids]
    history = meeting_history()
    today = today or date.today()
    for node in nodes:
        _attach_history(node, history, today)
    return nodes, edges


# --- contact history, derived from the meetings you already record ----------

def meeting_history():
    """Per-person meeting counts and dates, keyed by casefolded name."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT TRIM(person) AS person, date FROM meetings "
        "WHERE person IS NOT NULL AND TRIM(person) != ''"
    ).fetchall()
    conn.close()
    today = date.today().isoformat()
    history = {}
    for row in rows:
        day = (row["date"] or "").strip()
        # A group meeting counts as a meeting with every person who was in it.
        for person in attendees.parse(row["person"]):
            entry = history.setdefault(
                person.casefold(),
                {"last_met": "", "next_meeting": "", "meeting_count": 0},
            )
            if not day:
                continue
            if day <= today:
                entry["meeting_count"] += 1
                entry["last_met"] = max(entry["last_met"], day)
            elif not entry["next_meeting"] or day < entry["next_meeting"]:
                entry["next_meeting"] = day
    return history


def _attach_history(node, history, today):
    node.update(
        last_met="", next_meeting="", meeting_count=0,
        last_contact="", days_since=None, staleness=0.0,
    )
    if node["kind"] != CONTACT_NODE:
        return
    entry = history.get((node["contact_name"] or "").strip().casefold())
    if entry:
        node.update(entry)
    # Contacts predate meeting records, so fall back to when you first met.
    dates = [d for d in (node["last_met"], (node["met_on"] or "").strip()) if d]
    node["last_contact"] = max(dates) if dates else ""
    node["days_since"] = days_since(node["last_contact"], today)
    node["staleness"] = staleness(node["days_since"])


def days_since(iso_date, today=None):
    """Whole days between an ISO date and today, or None if unusable."""
    try:
        day = date.fromisoformat((iso_date or "").strip())
    except ValueError:
        return None
    return max(0, ((today or date.today()) - day).days)


def staleness(days):
    """0.0 (spoke recently) to MAX_FADE (long time), for fading cards."""
    if days is None:
        return 0.0
    if days <= FRESH_DAYS:
        return 0.0
    if days <= STALE_DAYS:
        return 0.45 * (days - FRESH_DAYS) / (STALE_DAYS - FRESH_DAYS)
    if days <= FADED_DAYS:
        return 0.45 + (MAX_FADE - 0.45) * (days - STALE_DAYS) / (FADED_DAYS - STALE_DAYS)
    return MAX_FADE


def age_label(days):
    """Compact 'how long ago' badge: 3d, 5w, 4mo, 2y."""
    if days is None:
        return ""
    if days == 0:
        return "today"
    if days < 14:
        return f"{days}d"
    if days < 60:
        return f"{days // 7}w"
    if days < 365:
        return f"{days // 30}mo"
    return f"{days // 365}y"


def last_contact_label(node):
    """Inspector wording for when you last spoke to someone."""
    if not node["last_contact"]:
        return "—"
    days = node["days_since"]
    if days is None:
        return node["last_contact"]
    if days == 0:
        return f"{node['last_contact']} (today)"
    return f"{node['last_contact']} ({days} days ago)"


def node_title(node):
    if node["kind"] == NOTE_NODE:
        return node["label"] or "Note"
    return node["contact_name"] or node["label"] or "(removed from CRM)"


def node_is_orphan(node):
    """A person node whose CRM contact has since been deleted."""
    return (
        node["kind"] == CONTACT_NODE
        and node["contact_id"] is not None
        and not node["contact_name"]
    )


def kind_label(kind, label=""):
    label = (label or "").strip()
    if label:
        return label
    return RELATIONSHIP_KINDS.get(kind, RELATIONSHIP_KINDS["custom"])[0]


def kind_is_directed(kind):
    return RELATIONSHIP_KINDS.get(kind, RELATIONSHIP_KINDS["custom"])[1]


def describe_edge(edge, node, other):
    """One-line description of an edge as seen from `node`."""
    outgoing = edge["from_node"] == node["id"]
    text = kind_label(edge["kind"], edge["label"])
    arrow = "→" if outgoing else "←"
    if not kind_is_directed(edge["kind"]):
        arrow = "—"
    return f"{arrow} {text}: {node_title(other)}"


def contacts_off_board():
    """CRM contacts that have no node yet, as (id, name, team, role) rows."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT c.id, c.name, c.team, c.role FROM contacts c
        WHERE c.id NOT IN (
            SELECT contact_id FROM board_nodes WHERE contact_id IS NOT NULL
        )
        ORDER BY c.name COLLATE NOCASE
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# --- writing ---------------------------------------------------------------

def add_contact_node(contact_id, x, y):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO board_nodes (kind, contact_id, x, y) VALUES (?, ?, ?, ?)",
        (CONTACT_NODE, contact_id, x, y),
    )
    conn.commit()
    node_id = cur.lastrowid
    conn.close()
    return node_id


def add_note_node(x, y, label="New note", notes=""):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO board_nodes (kind, label, x, y, notes, color) VALUES (?, ?, ?, ?, ?, ?)",
        (NOTE_NODE, label, x, y, notes, NOTE_COLORS["Yellow"]),
    )
    conn.commit()
    node_id = cur.lastrowid
    conn.close()
    return node_id


def move_node(node_id, x, y):
    conn = get_conn()
    conn.execute("UPDATE board_nodes SET x=?, y=? WHERE id=?", (x, y, node_id))
    conn.commit()
    conn.close()


def move_nodes(positions):
    """Bulk position update: {node_id: (x, y)}."""
    conn = get_conn()
    conn.executemany(
        "UPDATE board_nodes SET x=?, y=? WHERE id=?",
        [(x, y, nid) for nid, (x, y) in positions.items()],
    )
    conn.commit()
    conn.close()


def update_node(node_id, **fields):
    allowed = {k: v for k, v in fields.items() if k in ("label", "notes", "color")}
    if not allowed:
        return
    assignments = ", ".join(f"{key}=?" for key in allowed)
    conn = get_conn()
    conn.execute(
        f"UPDATE board_nodes SET {assignments} WHERE id=?",
        (*allowed.values(), node_id),
    )
    conn.commit()
    conn.close()


def delete_node(node_id):
    conn = get_conn()
    conn.execute("DELETE FROM board_edges WHERE from_node=? OR to_node=?", (node_id, node_id))
    conn.execute("DELETE FROM board_nodes WHERE id=?", (node_id,))
    conn.commit()
    conn.close()


def add_edge(from_node, to_node, kind="works_with", label=""):
    if from_node == to_node:
        return None
    conn = get_conn()
    existing = conn.execute(
        "SELECT id FROM board_edges WHERE (from_node=? AND to_node=?) OR (from_node=? AND to_node=?)",
        (from_node, to_node, to_node, from_node),
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE board_edges SET from_node=?, to_node=?, kind=?, label=? WHERE id=?",
            (from_node, to_node, kind, label, existing[0]),
        )
        edge_id = existing[0]
    else:
        cur = conn.execute(
            "INSERT INTO board_edges (from_node, to_node, kind, label) VALUES (?, ?, ?, ?)",
            (from_node, to_node, kind, label),
        )
        edge_id = cur.lastrowid
    conn.commit()
    conn.close()
    return edge_id


def update_edge(edge_id, kind=None, label=None):
    conn = get_conn()
    if kind is not None:
        conn.execute("UPDATE board_edges SET kind=? WHERE id=?", (kind, edge_id))
    if label is not None:
        conn.execute("UPDATE board_edges SET label=? WHERE id=?", (label, edge_id))
    conn.commit()
    conn.close()


def delete_edge(edge_id):
    conn = get_conn()
    conn.execute("DELETE FROM board_edges WHERE id=?", (edge_id,))
    conn.commit()
    conn.close()


# --- syncing with the CRM --------------------------------------------------

def sync_from_crm():
    """Add nodes for new contacts and links for filled-in manager fields.

    Returns (nodes_added, links_added). Existing nodes, positions and links
    are left untouched, so a sync never disturbs a board you have arranged.
    """
    nodes, edges = load_board()
    missing = contacts_off_board()
    start_x, start_y = _free_area(nodes)
    added_nodes = 0
    for index, contact in enumerate(missing):
        add_contact_node(
            contact["id"],
            start_x + (index % 4) * 240,
            start_y + (index // 4) * 150,
        )
        added_nodes += 1

    nodes, edges = load_board()
    by_name = {
        (n["contact_name"] or "").strip().casefold(): n
        for n in nodes
        if n["kind"] == CONTACT_NODE and n["contact_name"]
    }
    linked = {
        frozenset((e["from_node"], e["to_node"])) for e in edges
    }
    added_links = 0
    for node in nodes:
        manager = (node["manager"] or "").strip().casefold()
        boss = by_name.get(manager)
        if not boss or boss["id"] == node["id"]:
            continue
        if frozenset((node["id"], boss["id"])) in linked:
            continue
        add_edge(node["id"], boss["id"], "reports_to")
        linked.add(frozenset((node["id"], boss["id"])))
        added_links += 1
    return added_nodes, added_links


def _free_area(nodes, margin=160):
    """Top-left corner of empty space below the current content."""
    if not nodes:
        return 60.0, 60.0
    return 60.0, max(n["y"] for n in nodes) + margin


# --- automatic layout ------------------------------------------------------

def auto_layout(nodes, edges, x_gap=240.0, y_gap=170.0):
    """Tidy the board into org-chart trees, with the rest grouped by team.

    Returns {node_id: (x, y)}; the caller decides whether to persist it.
    """
    by_id = {n["id"]: n for n in nodes}
    parent, children = _hierarchy(by_id, edges)

    positions = {}
    slot = [0]

    def place(node_id, depth):
        kids = sorted(children.get(node_id, []), key=lambda i: node_title(by_id[i]).casefold())
        if kids:
            xs = [place(kid, depth + 1) for kid in kids]
            x = sum(xs) / len(xs)
        else:
            x = slot[0] * x_gap
            slot[0] += 1
        positions[node_id] = (x, depth * y_gap)
        return x

    in_tree = set(parent) | set(children)
    roots = sorted(
        (nid for nid in in_tree if nid not in parent),
        key=lambda i: node_title(by_id[i]).casefold(),
    )
    for root in roots:
        place(root, 0)
        slot[0] += 1  # blank column between separate trees

    _place_loose_nodes(nodes, positions, x_gap, y_gap)
    return _normalise(positions)


def _hierarchy(by_id, edges):
    """Parent/children maps built from the directed reporting links."""
    parent, children = {}, defaultdict(list)
    for edge in edges:
        if edge["kind"] == "reports_to":
            boss, report = edge["to_node"], edge["from_node"]
        elif edge["kind"] == "manages":
            boss, report = edge["from_node"], edge["to_node"]
        else:
            continue
        if boss not in by_id or report not in by_id or report in parent:
            continue
        if _would_cycle(parent, boss, report):
            continue
        parent[report] = boss
        children[boss].append(report)
    return parent, children


def _would_cycle(parent, boss, report):
    seen = set()
    while boss is not None and boss not in seen:
        if boss == report:
            return True
        seen.add(boss)
        boss = parent.get(boss)
    return False


def _place_loose_nodes(nodes, positions, x_gap, y_gap):
    """Everyone without a reporting link, columned by team; notes last."""
    loose = [n for n in nodes if n["id"] not in positions]
    if not loose:
        return
    baseline = max((y for _, y in positions.values()), default=-y_gap * 1.5) + y_gap * 1.5
    groups = defaultdict(list)
    for node in loose:
        if node["kind"] == NOTE_NODE:
            key = "￿Notes"  # sorts last
        else:
            key = (node["team"] or "").strip() or (node["office"] or "").strip() or "No team"
        groups[key].append(node)
    for column, key in enumerate(sorted(groups, key=str.casefold)):
        members = sorted(groups[key], key=lambda n: node_title(n).casefold())
        for row, node in enumerate(members):
            positions[node["id"]] = (column * x_gap, baseline + row * y_gap * 0.8)


def _normalise(positions, margin=60.0):
    if not positions:
        return positions
    min_x = min(x for x, _ in positions.values())
    min_y = min(y for _, y in positions.values())
    return {
        nid: (x - min_x + margin, y - min_y + margin)
        for nid, (x, y) in positions.items()
    }
