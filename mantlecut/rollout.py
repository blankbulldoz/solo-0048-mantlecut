from . import channels, cohorts, events, revisions, subscribers, targets
from .errors import conflict, missing
from .inputs import integer


def get(db, slug, number):
    row = db.execute("SELECT * FROM releases WHERE slug = ? AND id = ?", (slug, number)).fetchone()
    if row is None:
        raise missing("发布")
    return dict(row)


def listing(db, slug):
    return [dict(row) for row in db.execute("SELECT * FROM releases WHERE slug = ? ORDER BY id DESC", (slug,))]


def status(db, slug, number):
    release = get(db, slug, number)
    seats = cohorts.status(db, number)
    required = [seat for seat in seats if release["widened_ms"] is not None or seat["trial"]]
    blockers = [seat["node"] for seat in required if seat["applied_seq"] is None]
    return dict(release, seats=seats, required=len(required), confirmed=len(required) - len(blockers), blockers=blockers)


def _invalidate_wrong_offers(db, slug):
    for row in db.execute("SELECT seq, node, release FROM offers WHERE slug = ? AND state = 'open'", (slug,)).fetchall():
        desired = targets.for_node(db, slug, row["node"])
        if desired is None or row["release"] != desired["id"]:
            db.execute("UPDATE offers SET state = 'superseded' WHERE seq = ?", (row["seq"],))


def start(db, now, slug, revision, fraction):
    channels.get(db, slug)
    integer(revision, 1, 2**63 - 1, "版本号")
    fraction = integer(fraction, 1, 100, "试发百分比")
    if targets.active(db, slug):
        raise conflict("release_in_progress", "该配置线已有在途发布")
    candidate = revisions.get(db, slug, revision)
    if candidate["signature"] is None:
        raise conflict("draft_not_sealed", "发布前请封存版本")
    report = revisions.preflight(db, candidate)
    if report["failures"]:
        first = report["failures"][0]
        raise conflict("audience_incompatible", f"{first['node'] or '基底'}无法使用该版本：{first['message']}")
    number = db.execute(
        "INSERT INTO releases(slug, revision, fraction, stage, started_ms) VALUES (?, ?, ?, 'trial', ?)",
        (slug, revision, fraction, now),
    ).lastrowid
    endpoints = subscribers.list_subscribers(db, slug, active_only=True)
    count = cohorts.freeze(db, slug, number, fraction, endpoints)
    _invalidate_wrong_offers(db, slug)
    events.record(db, slug, now, "release_started", release=number, revision=revision, total=len(endpoints), trial=count)
    return status(db, slug, number)


def advance(db, now, slug, number, action):
    current = status(db, slug, number)
    stage = current["stage"]
    if action == "withdraw" and stage in ("trial", "wide"):
        target = "withdrawn"
    elif (stage, action) in (("trial", "widen"), ("wide", "settle")):
        if current["blockers"]:
            raise conflict("receipts_pending", "待确认订阅端：" + "、".join(current["blockers"][:10]))
        target = "wide" if stage == "trial" else "stable"
    else:
        raise conflict("release_stage", "当前阶段无法执行该操作")
    ended = now if target in ("stable", "withdrawn") else None
    widened = now if target == "wide" else current["widened_ms"]
    db.execute(
        "UPDATE releases SET stage = ?, widened_ms = ?, ended_ms = ? WHERE id = ?",
        (target, widened, ended, number),
    )
    if target == "stable":
        db.execute("UPDATE channels SET stable_release = ? WHERE slug = ?", (number, slug))
    _invalidate_wrong_offers(db, slug)
    events.record(db, slug, now, f"release_{target}", release=number, confirmed=current["confirmed"], required=current["required"])
    return status(db, slug, number)
