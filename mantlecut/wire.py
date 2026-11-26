import base64
import hashlib

from .documents import canonical
from .errors import Rejected
from .rules import resolve


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def encode(value, protocol):
    if protocol == 1:
        if value["compression"] != "off":
            raise Rejected("legacy_compression", "代际 1 无法表达配置指定的压缩方式")
        if value["poll_ms"] % 1000 or value["flush_ms"] % 1000:
            raise Rejected("legacy_precision", "代际 1 只支持整数秒的间隔与窗口")
        data = {k: v for k, v in value.items() if k not in {"poll_ms", "flush_ms", "compression"}}
        data.update(poll_s=value["poll_ms"] // 1000, flush_s=value["flush_ms"] // 1000)
    elif protocol == 2:
        data = value
    else:
        raise Rejected("unknown_protocol", "代际使用 1 或 2")
    return canonical(data).encode("utf-8")


def compile_for(base, layers, tags, protocol):
    value, matched = resolve(base, layers, tags)
    payload = encode(value, protocol)
    return value, matched, payload


def pack(payload):
    return {"body_b64": base64.b64encode(payload).decode("ascii"), "sha256": digest(payload)}
