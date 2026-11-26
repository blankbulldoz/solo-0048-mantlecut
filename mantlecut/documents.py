import json

from .errors import Rejected


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"JSON 键重复：{key}")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError(f"不支持 JSON 数值 {value}")


def parse(text):
    try:
        value = json.loads(text, object_pairs_hook=_unique, parse_constant=_reject_constant)
        canonical(value).encode("utf-8")
        return value
    except (ValueError, RecursionError, UnicodeError) as exc:
        raise Rejected("invalid_json", "JSON 必须使用唯一键、有限数值和有效的 UTF-8 字符") from exc


def object_body(data):
    if not isinstance(data, dict):
        raise Rejected("object_required", "请求必须是 JSON 对象")
    return data
