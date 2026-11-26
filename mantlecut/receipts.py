import hmac
import re

from . import events, offers, targets
from .errors import Rejected, conflict
from .inputs import integer, short_text

HEX = re.compile(r"[0-9a-f]{64}\Z")


def accept(db, now, subscriber, seq, fingerprint, result, reason):
    slug, node = subscriber["slug"], subscriber["node"]
    seq = integer(seq, 1, 2**63 - 1, "领取序号")
    if not isinstance(fingerprint, str) or not HEX.fullmatch(fingerprint):
        raise Rejected("invalid_digest", "sha256 应为 64 位小写十六进制摘要")
    if result == "rejected":
        reason = short_text(reason, "拒绝原因", 280)
    elif result != "applied" or reason is not None:
        raise Rejected("invalid_receipt", "回执状态使用 applied 或 rejected，只有拒绝需要原因")
    offer = offers.get_owned(db, slug, node, seq)
    if not hmac.compare_digest(offer["sha256"], fingerprint):
        raise conflict("digest_mismatch", "回执摘要与领取字节不一致")
    existing = db.execute("SELECT * FROM receipts WHERE seq = ?", (seq,)).fetchone()
    if existing:
        if (existing["result"], existing["reason"]) != (result, reason):
            raise conflict("receipt_conflict", "领取件已有不同终态回执")
        return dict(existing, replayed=True)
    if subscriber["paused"]:
        raise conflict("paused_subscriber", "订阅端处于暂停状态")
    if offer["state"] == "expired" or (offer["state"] == "open" and offer["expires_ms"] <= now):
        raise conflict("offer_expired", "领取件已过期，请重新领取")
    desired = targets.for_node(db, slug, node)
    if offer["state"] != "open" or desired is None or desired["id"] != offer["release"]:
        raise conflict("superseded_offer", "领取件的发布目标已改变")
    db.execute("INSERT INTO receipts(seq, sha256, result, reason, received_ms) VALUES (?, ?, ?, ?, ?)", (seq, fingerprint, result, reason, now))
    db.execute("UPDATE offers SET state = ? WHERE seq = ?", (result, seq))
    events.record(db, slug, now, "receipt_recorded", node=node, seq=seq, release=offer["release"], result=result)
    return {"seq": seq, "sha256": fingerprint, "result": result, "reason": reason, "received_ms": now, "replayed": False}
