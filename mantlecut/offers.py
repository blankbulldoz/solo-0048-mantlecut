from . import events, revisions, targets, wire
from .errors import missing


def get_owned(db, slug, node, seq):
    row = db.execute("SELECT * FROM offers WHERE slug = ? AND node = ? AND seq = ?", (slug, node, seq)).fetchone()
    if row is None:
        raise missing("领取件")
    return row


def list_offers(db, slug, node, now):
    rows = db.execute(
        """SELECT o.seq, o.release, o.sha256, o.state, o.issued_ms, o.expires_ms, r.revision,
                  a.received_ms, a.reason
           FROM offers o JOIN releases r ON r.id = o.release LEFT JOIN receipts a ON o.seq = a.seq
           WHERE o.slug = ? AND o.node = ? ORDER BY o.seq DESC LIMIT 40""", (slug, node),
    )
    return [dict(row, state="expired" if row["state"] == "open" and row["expires_ms"] <= now else row["state"]) for row in rows]


def _envelope(row, revision):
    return {
        "kind": "offer", "seq": row["seq"], "revision": revision,
        "release": row["release"], "expires_ms": row["expires_ms"], **wire.pack(row["payload"]),
    }


def pull(db, now, subscriber, ttl_ms):
    slug, node = subscriber["slug"], subscriber["node"]
    if subscriber["paused"]:
        return {"kind": "idle", "reason": "paused"}
    target = targets.for_node(db, slug, node)
    pending = db.execute("SELECT * FROM offers WHERE slug = ? AND node = ? AND state = 'open'", (slug, node)).fetchone()
    if pending:
        if target and pending["release"] == target["id"] and pending["expires_ms"] > now:
            return _envelope(pending, target["revision"])
        state = "expired" if pending["expires_ms"] <= now else "superseded"
        db.execute("UPDATE offers SET state = ? WHERE seq = ?", (state, pending["seq"]))
        events.record(db, slug, now, f"offer_{state}", node=node, seq=pending["seq"])
    if target is None:
        return {"kind": "idle", "reason": "no_target"}
    latest = db.execute(
        """SELECT release, seq FROM offers WHERE slug = ? AND node = ? AND state = 'applied' ORDER BY seq DESC LIMIT 1""",
        (slug, node),
    ).fetchone()
    if latest and latest["release"] == target["id"]:
        uncertain = db.execute(
            """SELECT 1 FROM offers WHERE slug = ? AND node = ? AND seq > ?
               AND release != ? AND state IN ('expired', 'superseded') LIMIT 1""",
            (slug, node, latest["seq"], target["id"]),
        ).fetchone()
        if uncertain is None:
            return {"kind": "idle", "reason": "current", "release": target["id"]}
    rejected = db.execute(
        "SELECT 1 FROM offers WHERE slug = ? AND node = ? AND release = ? AND state = 'rejected'",
        (slug, node, target["id"]),
    ).fetchone()
    if rejected:
        return {"kind": "idle", "reason": "rejected", "release": target["id"]}
    revision = revisions.get(db, slug, target["revision"])
    _, _, payload = wire.compile_for(revision["base"], revision["layers"], subscriber["tags"], subscriber["wire"])
    seq = db.execute(
        """INSERT INTO offers(slug, node, release, sha256, payload, issued_ms, expires_ms, state)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'open')""",
        (slug, node, target["id"], wire.digest(payload), payload, now, now + ttl_ms),
    ).lastrowid
    events.record(db, slug, now, "offer_issued", node=node, seq=seq, release=target["id"], revision=target["revision"])
    return _envelope(get_owned(db, slug, node, seq), revision["id"])
