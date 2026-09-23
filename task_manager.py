"""Business logic for personal tasks."""

from datetime import date, datetime, timedelta

from db import get_conn


def clean_tag(tag):
    """A tag as typed, tidied: no stray whitespace, no double spaces."""
    return " ".join((tag or "").split())


class TaskManager:
    @staticmethod
    def now_stamp():
        return datetime.now().strftime("%Y-%m-%d %H:%M")

    @classmethod
    def create_task(cls, title, notes="", tag=""):
        cleaned_title = (title or "").strip()
        if not cleaned_title:
            raise ValueError("Task title is required")
        conn = get_conn()
        cursor = conn.execute(
            "INSERT INTO tasks (title, notes, tag, created_at, completed_at) "
            "VALUES (?, ?, ?, ?, NULL)",
            (
                cleaned_title,
                (notes or "").strip(),
                cls.canonical_tag(tag),
                cls.now_stamp(),
            ),
        )
        conn.commit()
        task_id = cursor.lastrowid
        conn.close()
        return task_id

    @classmethod
    def update_task(cls, task_id, title, notes="", tag=""):
        cleaned_title = (title or "").strip()
        if not cleaned_title:
            raise ValueError("Task title is required")
        conn = get_conn()
        conn.execute(
            "UPDATE tasks SET title=?, notes=?, tag=? WHERE id=?",
            (
                cleaned_title,
                (notes or "").strip(),
                cls.canonical_tag(tag),
                task_id,
            ),
        )
        conn.commit()
        conn.close()

    @classmethod
    def canonical_tag(cls, tag):
        """Match an existing tag's spelling so "alpha" joins "Alpha", not splits it."""
        cleaned = clean_tag(tag)
        if not cleaned:
            return ""
        for known in cls.list_tags():
            if known.casefold() == cleaned.casefold():
                return known
        return cleaned

    @staticmethod
    def list_tags():
        """Every tag in use, active or completed, alphabetical and case-insensitive."""
        conn = get_conn()
        rows = conn.execute(
            "SELECT DISTINCT tag FROM tasks WHERE tag IS NOT NULL AND tag != '' "
            "ORDER BY tag COLLATE NOCASE"
        ).fetchall()
        conn.close()
        return [row["tag"] for row in rows]

    @staticmethod
    def group_by_tag(rows):
        """[(tag, rows)] with the untagged group ("") first, then tags A-Z.

        Untagged leads because that is where work lands — an item sent over from
        a meeting note arrives without a tag, and it should be sitting in front
        of you to file or finish, not buried under the projects already sorted.

        Order inside each group is the order the rows arrived in, so whatever
        sorting the caller's query applied survives the grouping.
        """
        groups = {}
        for row in rows:
            groups.setdefault(row["tag"] or "", []).append(row)
        ordered = [("", groups[""])] if "" in groups else []
        for tag in sorted((tag for tag in groups if tag), key=lambda t: t.casefold()):
            ordered.append((tag, groups[tag]))
        return ordered

    @classmethod
    def complete_task(cls, task_id):
        conn = get_conn()
        conn.execute(
            "UPDATE tasks SET completed_at=? WHERE id=? AND completed_at IS NULL",
            (cls.now_stamp(), task_id),
        )
        conn.commit()
        conn.close()

    @classmethod
    def reopen_task(cls, task_id):
        """Undo a completion: the task goes back to the active list unchanged.

        A tick box is one slip of the mouse away from wrong, so finishing a task
        has to be reversible. Clearing completed_at is the whole job — carry-over
        and the progress packs read that column rather than a separate flag, so
        the agenda item the task came from reopens with it.
        """
        conn = get_conn()
        conn.execute("UPDATE tasks SET completed_at=NULL WHERE id=?", (task_id,))
        conn.commit()
        conn.close()

    @classmethod
    def set_tag(cls, task_id, tag):
        """File a task under a project, leaving its title and notes alone.

        Kept apart from update_task so the list can tag a task in place without
        having to hand back the fields it is not editing.
        """
        conn = get_conn()
        conn.execute(
            "UPDATE tasks SET tag=? WHERE id=?", (cls.canonical_tag(tag), task_id)
        )
        conn.commit()
        conn.close()

    @staticmethod
    def delete_task(task_id):
        conn = get_conn()
        conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))
        conn.commit()
        conn.close()

    @staticmethod
    def list_active():
        conn = get_conn()
        rows = conn.execute(
            "SELECT * FROM tasks WHERE completed_at IS NULL ORDER BY created_at DESC, id DESC"
        ).fetchall()
        conn.close()
        return rows

    @staticmethod
    def list_history():
        conn = get_conn()
        rows = conn.execute(
            "SELECT * FROM tasks WHERE completed_at IS NOT NULL "
            "ORDER BY completed_at DESC, id DESC"
        ).fetchall()
        conn.close()
        return rows

    @staticmethod
    def states_for(task_ids):
        """Map {task_id: row} for the ids that still exist.

        Ids missing from the result have been deleted, which callers must treat
        differently from "still open" — a deleted task is not a done task.
        """
        wanted = [int(task_id) for task_id in task_ids if task_id is not None]
        if not wanted:
            return {}
        conn = get_conn()
        placeholders = ",".join("?" * len(wanted))
        rows = conn.execute(
            f"SELECT * FROM tasks WHERE id IN ({placeholders})", wanted
        ).fetchall()
        conn.close()
        return {row["id"]: row for row in rows}

    @staticmethod
    def completed_between(start_date, end_date):
        """Tasks completed on any day in [start_date, end_date], both inclusive.

        completed_at is "YYYY-MM-DD HH:MM", so the upper bound compares against
        the following day — "<= end_date" would drop everything finished after
        midnight on the last day.
        """
        day_after_end = (date.fromisoformat(end_date) + timedelta(days=1)).isoformat()
        conn = get_conn()
        rows = conn.execute(
            "SELECT * FROM tasks WHERE completed_at IS NOT NULL "
            "AND completed_at >= ? AND completed_at < ? "
            "ORDER BY completed_at, id",
            (start_date, day_after_end),
        ).fetchall()
        conn.close()
        return rows
