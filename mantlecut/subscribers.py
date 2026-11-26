import hmac
import json
import secrets

from . import channels, events, wire
from .documents import canonical
from .errors import Rejected, conflict, missing
from .inputs import identifier, integer, labels


def get(db, slug, node):
    row = db.execute("SELECT * FROM subscribers WHERE slug = ? AND node = ?", (slug, node)).fetchone()
    if row is None:
        raise missing("订阅端")
    return dict(row, tags=json.loads(row["tags"]), paused=bool(row["paused"]))


def public(subscriber):
    return {k: v for k, v in subscriber.items() if k != "key_sha256"}


def list_subscribers(db, slug, *, active_only=False):
    rows = db.execute("SELECT * FROM subscribers WHERE slug = ? AND (? = 0 OR paused = 0) ORDER BY node", (slug, active_only))
    return [public(dict(row, tags=json.loads(row["tags"]), paused=bool(row["paused"]))) for row in rows]


def _check_current_versions(db, slug, node, tags, protocol):
    rows = db.execute(
        """SELECT v.base, v.layers, v.id FROM releases r JOIN revisions v ON v.id = r.revision
           JOIN channels c ON c.slug = r.slug WHERE r.slug = ?
           AND (r.id = c.stable_release OR r.stage IN ('trial', 'wide')) ORDER BY r.id""",
        (slug,),
    )
    for row in rows:
        try:
            wire.compile_for(json.loads(row["base"]), json.loads(row["layers"]), tags, protocol)
        except Rejected as exc:
            raise conflict("subscriber_incompatible", f"订阅端 {node} 无法使用现行版本 #{row['id']}：{exc}") from exc


def register(db, now, slug, node, tags, protocol, *, demo_key=None):
    channels.get(db, slug)
    identifier(node, "订阅端 ID")
    tags = labels(tags)
    protocol = integer(protocol, 1, 2, "协议代际")
    if db.execute("SELECT 1 FROM subscribers WHERE slug = ? AND node = ?", (slug, node)).fetchone():
        raise conflict("duplicate_subscriber", "同一配置线已有该订阅端")
    _check_current_versions(db, slug, node, tags, protocol)
    key = demo_key or secrets.token_urlsafe(30)
    db.execute(
        "INSERT INTO subscribers(slug, node, tags, wire, key_sha256) VALUES (?, ?, ?, ?, ?)",
        (slug, node, canonical(tags), protocol, wire.digest(key.encode())),
    )
    events.record(db, slug, now, "subscriber_registered", node=node, wire=protocol, tags=tags)
    return dict(public(get(db, slug, node)), key=key)


def change_pause(db, now, slug, node, paused):
    subscriber = get(db, slug, node)
    if not isinstance(paused, bool):
        raise Rejected("invalid_pause", "paused 使用布尔值")
    if subscriber["paused"] != paused:
        db.execute("UPDATE subscribers SET paused = ? WHERE slug = ? AND node = ?", (paused, slug, node))
        if paused:
            db.execute("UPDATE offers SET state = 'superseded' WHERE slug = ? AND node = ? AND state = 'open'", (slug, node))
        events.record(db, slug, now, "subscriber_paused" if paused else "subscriber_resumed", node=node)
    return public(get(db, slug, node))


def authenticate(db, slug, node, key):
    try:
        subscriber = get(db, slug, node)
    except Rejected as exc:
        if exc.status != 404:
            raise
        subscriber = None
    key_hash = wire.digest(key.encode("utf-8"))
    expected = subscriber["key_sha256"] if subscriber else "0" * 64
    known = hmac.compare_digest(key_hash, expected)
    if not key or subscriber is None or not known:
        raise Rejected("invalid_key", "订阅端凭据无效", 401)
    return subscriber
