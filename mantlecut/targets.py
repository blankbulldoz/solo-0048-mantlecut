from . import channels


def active(db, slug):
    row = db.execute("SELECT * FROM releases WHERE slug = ? AND stage IN ('trial', 'wide')", (slug,)).fetchone()
    return dict(row) if row else None


def for_node(db, slug, node):
    current = active(db, slug)
    if current:
        seat = db.execute("SELECT trial FROM seats WHERE release = ? AND node = ?", (current["id"], node)).fetchone()
        if seat and (seat["trial"] or current["stage"] == "wide"):
            return current
    stable = channels.get(db, slug)["stable_release"]
    if stable is None:
        return None
    return dict(db.execute("SELECT * FROM releases WHERE id = ?", (stable,)).fetchone())
