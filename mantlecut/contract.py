from .errors import Rejected
from .inputs import identifier, integer

RANGES = {"poll_ms": (100, 60000), "flush_ms": (100, 600000), "inflight": (1, 16384), "burst": (1, 16384)}
REQUIRED = set(RANGES) | {"upstream", "sampling"}
OPTIONAL = {"compression"}


def fields(value, *, patch=False):
    if not isinstance(value, dict) or not value or set(value) - (REQUIRED | OPTIONAL):
        raise Rejected("invalid_fields", "配置对象为空或含未知字段")
    if not patch and not REQUIRED <= set(value):
        raise Rejected("missing_fields", "基底缺少必要字段：" + "、".join(sorted(REQUIRED - set(value))))
    for key, raw in value.items():
        if patch and key in OPTIONAL and raw is None:
            continue
        if key in RANGES:
            integer(raw, *RANGES[key], key)
        elif key == "upstream":
            identifier(raw, "上游名称")
        elif key == "sampling":
            integer(raw, 1, 100, "采样百分比")
        elif raw not in ("off", "gzip"):
            raise Rejected("invalid_compression", "compression 使用 off 或 gzip")
    return value.copy()


def enforce(value):
    fields(value)
    if value["flush_ms"] % value["poll_ms"]:
        raise Rejected("unaligned_window", "批量窗口须为采集间隔的整数倍")
    if value["burst"] > value["inflight"]:
        raise Rejected("batch_exceeds_inflight", "批量上限不能超过在途上限")
    return value
