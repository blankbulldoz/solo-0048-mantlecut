import json

from . import channels, events, rules, subscribers, wire
from .documents import canonical
from .errors import Rejected, conflict, missing
from .inputs import integer, short_text


def get(db, slug, number):
    row = db.execute("SELECT * FROM revisions WHERE slug = ? AND id = ?", (slug, number)).fetchone()
    if row is None:
        raise missing("版本")
    return dict(row, base=json.loads(row["base"]), layers=json.loads(row["layers"]))


def list_revisions(db, slug):
    return [dict(row) for row in db.execute(
        "SELECT id, title, generation, source_id, signature, sealed_ms FROM revisions WHERE slug = ? ORDER BY id DESC",
        (slug,),
    )]


def create(db, now, slug, title, base, layers, source_id=None):
    channels.get(db, slug)
    title = short_text(title, "版本标题", 80)
    if source_id is not None:
        integer(source_id, 1, 2**63 - 1, "来源版本")
        source = get(db, slug, source_id)
        if source["signature"] is None:
            raise conflict("unsealed_source", "只能由封存版复制草稿")
        if base is not None or layers is not None:
            raise Rejected("ambiguous_source", "复制草稿时只提供标题和来源版本")
        base, layers = source["base"], source["layers"]
    base, layers = rules.normalize(base, layers)
    number = db.execute(
        "INSERT INTO revisions(slug, title, base, layers, source_id) VALUES (?, ?, ?, ?, ?)",
        (slug, title, canonical(base), canonical(layers), source_id),
    ).lastrowid
    events.record(db, slug, now, "draft_created", revision=number, source=source_id)
    return get(db, slug, number)


def _writable(db, slug, number, generation):
    revision = get(db, slug, number)
    if revision["signature"] is not None:
        raise conflict("sealed_revision", "封存版本固定，可以复制为新草稿")
    integer(generation, 1, 2**63 - 1, "草稿代数")
    if generation != revision["generation"]:
        raise conflict("stale_generation", "草稿已有新编辑，请重新打开")
    return revision


def update(db, now, slug, number, generation, title, base, layers):
    _writable(db, slug, number, generation)
    title = short_text(title, "版本标题", 80)
    base, layers = rules.normalize(base, layers)
    db.execute(
        "UPDATE revisions SET generation = generation + 1, title = ?, base = ?, layers = ? WHERE id = ?",
        (title, canonical(base), canonical(layers), number),
    )
    events.record(db, slug, now, "draft_edited", revision=number, generation=generation + 1)
    return get(db, slug, number)


def preflight(db, revision):
    failures = []
    try:
        rules.resolve(revision["base"], revision["layers"], {})
    except Rejected as exc:
        failures.append({"node": None, "error": exc.code, "message": str(exc)})
    endpoints = subscribers.list_subscribers(db, revision["slug"])
    for endpoint in endpoints:
        try:
            wire.compile_for(revision["base"], revision["layers"], endpoint["tags"], endpoint["wire"])
        except Rejected as exc:
            failures.append({"node": endpoint["node"], "error": exc.code, "message": str(exc)})
    return {"checked": len(endpoints), "failures": failures}


def seal(db, now, slug, number, generation):
    revision = _writable(db, slug, number, generation)
    report = preflight(db, revision)
    if report["failures"]:
        first = report["failures"][0]
        raise conflict("compatibility_blocked", f"{first['node'] or '基底'}无法封存：{first['message']}")
    fingerprint = wire.digest(canonical({"base": revision["base"], "layers": revision["layers"]}).encode("utf-8"))
    db.execute("UPDATE revisions SET signature = ?, sealed_ms = ? WHERE id = ?", (fingerprint, now, number))
    events.record(db, slug, now, "revision_sealed", revision=number, signature=fingerprint, checked=report["checked"])
    return get(db, slug, number)


def preview(db, slug, number, node):
    revision = get(db, slug, number)
    subscriber = subscribers.get(db, slug, node)
    value, matches = rules.resolve(revision["base"], revision["layers"], subscriber["tags"])
    result = {"revision": number, "node": node, "wire": subscriber["wire"], "effective": value, "matched": matches}
    try:
        payload = wire.encode(value, subscriber["wire"])
    except Rejected as exc:
        return dict(result, compatible=False, error=exc.code, message=str(exc))
    return dict(result, compatible=True, payload=payload.decode("utf-8"), **wire.pack(payload))
