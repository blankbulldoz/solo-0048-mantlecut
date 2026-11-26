from . import channels, inspection, revisions, rollout, subscribers
from .errors import missing, Rejected

MAX_NUMBER = 2**63 - 1


def number(text):
    if len(text) > 19 or not text.isascii() or not text.isdecimal() or not 1 <= int(text) <= MAX_NUMBER:
        raise Rejected("invalid_number", "编号须为有效的正整数", 400)
    return int(text)


def read(db, now, path, query):
    match path:
        case ["channels"]:
            return {"channels": channels.list_channels(db)}
        case ["channels", slug]:
            return inspection.overview(db, slug)
        case ["channels", slug, "subscribers", node]:
            return inspection.subscriber_state(db, now, slug, node)
        case ["channels", slug, "revisions", value]:
            return revisions.get(db, slug, number(value))
        case ["channels", slug, "revisions", value, "preview"]:
            return revisions.preview(db, slug, number(value), query.get("node", ""))
        case ["channels", slug, "revisions", value, "preflight"]:
            return revisions.preflight(db, revisions.get(db, slug, number(value)))
        case ["channels", slug, "releases", value]:
            return rollout.status(db, slug, number(value))
        case ["channels", slug, "events"]:
            return inspection.audit_page(db, slug, number(query["before"]) if "before" in query else MAX_NUMBER)
        case _:
            raise missing("接口")


def change(db, now, path, data):
    value = data.get
    match path:
        case ["channels"]:
            return channels.create(db, now, value("slug"), value("title"))
        case ["channels", slug, "subscribers"]:
            return subscribers.register(db, now, slug, value("node"), value("tags"), value("wire"))
        case ["channels", slug, "subscribers", node, "pause"]:
            return subscribers.change_pause(db, now, slug, node, value("paused"))
        case ["channels", slug, "revisions"]:
            return revisions.create(db, now, slug, value("title"), value("base"), value("layers"), value("source_id"))
        case ["channels", slug, "revisions", revision, "edit"]:
            return revisions.update(db, now, slug, number(revision), value("generation"), value("title"), value("base"), value("layers"))
        case ["channels", slug, "revisions", revision, "seal"]:
            return revisions.seal(db, now, slug, number(revision), value("generation"))
        case ["channels", slug, "releases"]:
            return rollout.start(db, now, slug, value("revision"), value("fraction"))
        case ["channels", slug, "releases", release, ("widen" | "settle" | "withdraw") as action]:
            return rollout.advance(db, now, slug, number(release), action)
        case _:
            raise missing("接口")
