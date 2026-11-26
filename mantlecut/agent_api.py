from . import offers, receipts, subscribers
from .errors import missing


def change(db, now, path, key, data, ttl_ms):
    match path:
        case [slug, node, "pull"]:
            subscriber = subscribers.authenticate(db, slug, node, key)
            return offers.pull(db, now, subscriber, ttl_ms)
        case [slug, node, "receipts"]:
            subscriber = subscribers.authenticate(db, slug, node, key)
            return receipts.accept(db, now, subscriber, data.get("seq"), data.get("sha256"), data.get("result"), data.get("reason"))
        case _:
            raise missing("代理接口")
