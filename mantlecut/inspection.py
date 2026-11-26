from . import channels, events, offers, revisions, rollout, subscribers, targets


def overview(db, slug):
    return {
        "channel": channels.get(db, slug), "active": targets.active(db, slug),
        "revisions": revisions.list_revisions(db, slug), "releases": rollout.listing(db, slug),
        "subscribers": subscribers.list_subscribers(db, slug),
    }


def subscriber_state(db, now, slug, node):
    subscriber = subscribers.get(db, slug, node)
    target = targets.for_node(db, slug, node) if not subscriber["paused"] else None
    return {"subscriber": subscribers.public(subscriber), "target": target, "offers": offers.list_offers(db, slug, node, now)}


def audit_page(db, slug, before):
    channels.get(db, slug)
    return events.list_events(db, slug, before)
