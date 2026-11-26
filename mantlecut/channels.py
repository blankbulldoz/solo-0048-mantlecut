from . import events
from .errors import conflict, missing
from .inputs import identifier, short_text


def get(db, slug):
    row = db.execute("SELECT * FROM channels WHERE slug = ?", (slug,)).fetchone()
    if row is None:
        raise missing("配置线")
    return dict(row)


def list_channels(db):
    return [dict(row) for row in db.execute("SELECT * FROM channels ORDER BY slug")]


def create(db, now, slug, title):
    identifier(slug, "配置线 ID")
    title = short_text(title, "配置线名称", 60)
    cursor = db.execute("INSERT OR IGNORE INTO channels(slug, title) VALUES (?, ?)", (slug, title))
    if cursor.rowcount != 1:
        raise conflict("duplicate_channel", "配置线 ID 已存在")
    events.record(db, slug, now, "channel_created")
    return get(db, slug)
