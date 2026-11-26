import json

from .documents import canonical


def record(db, slug, at_ms, kind, **detail):
    db.execute("INSERT INTO events(slug, at_ms, kind, detail) VALUES (?, ?, ?, ?)", (slug, at_ms, kind, canonical(detail)))


def list_events(db, slug, before, limit=32):
    rows = db.execute(
        "SELECT * FROM events WHERE slug = ? AND id < ? ORDER BY id DESC LIMIT ?",
        (slug, before, limit + 1),
    ).fetchall()
    selected = rows[:limit]
    result = [dict(row, detail=json.loads(row["detail"])) for row in selected]
    return {"events": result, "next_before": selected[-1]["id"] if len(rows) > limit else None}
