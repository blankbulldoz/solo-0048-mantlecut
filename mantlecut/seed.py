from . import channels, offers, receipts, revisions, rollout, subscribers

SLUG = "carbon-ridge"
DEFAULT_CONFIG = {"poll_ms": 2000, "flush_ms": 8000, "inflight": 64, "burst": 24, "upstream": "collector-main", "sampling": 100}
NODES = {
    "agate-west": ({"site": "west", "tier": "edge"}, 1),
    "fir-remote": ({"site": "west", "tier": "edge"}, 2),
    "ember-fan": ({"site": "south", "tier": "core"}, 2),
    "moraine-hub": ({"site": "south", "tier": "core"}, 1),
    "reed-aux": ({"site": "north", "tier": "edge"}, 2),
}


def key(node):
    return f"mantlecut-demo-{node}"


def seed(storage):
    with storage.transaction(write=True) as (db, now):
        if db.execute("SELECT 1 FROM channels LIMIT 1").fetchone():
            return False
        channels.create(db, now, SLUG, "脊线采集")
        for node, (tags, protocol) in NODES.items():
            subscribers.register(db, now, SLUG, node, tags, protocol, demo_key=key(node))
        layers = [{"id": "west-colder", "priority": 10, "when": {"site": "west"}, "patch": {"sampling": 70}}]
        initial = revisions.create(db, now, SLUG, "稳态 · 主采集窗口", DEFAULT_CONFIG, layers)
        revisions.seal(db, now, SLUG, initial["id"], initial["generation"])
        first = rollout.start(db, now, SLUG, initial["id"], 100)
        for node in NODES:
            subscriber = subscribers.get(db, SLUG, node)
            offer = offers.pull(db, now, subscriber, 45000)
            receipts.accept(db, now, subscriber, offer["seq"], offer["sha256"], "applied", None)
        rollout.advance(db, now, SLUG, first["id"], "widen")
        rollout.advance(db, now, SLUG, first["id"], "settle")
        north_layer = {"id": "north-batch", "priority": 20, "when": {"site": "north"}, "patch": {"burst": 32, "compression": "gzip"}}
        candidate = revisions.create(db, now, SLUG, "北区压缩试发", DEFAULT_CONFIG, layers + [north_layer])
        revisions.seal(db, now, SLUG, candidate["id"], candidate["generation"])
        second = rollout.start(db, now, SLUG, candidate["id"], 40)
        first_trial = next(seat for seat in second["seats"] if seat["trial"])
        subscriber = subscribers.get(db, SLUG, first_trial["node"])
        offer = offers.pull(db, now, subscriber, 45000)
        receipts.accept(db, now, subscriber, offer["seq"], offer["sha256"], "applied", None)
        draft_layer = {"id": "south-window", "priority": 30, "when": {"site": "south"}, "patch": {"flush_ms": 12000}}
        revisions.create(db, now, SLUG, "南区延长批量窗口", DEFAULT_CONFIG, layers + [draft_layer])
        return True
