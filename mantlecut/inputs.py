import re

from .errors import Rejected

ID = re.compile(r"[a-z][a-z0-9-]{0,47}\Z")


def identifier(value, label):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise Rejected("invalid_identifier", f"{label}使用小写字母开头，随后可用数字和连字符，最长 48 字符")
    return value


def integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise Rejected("invalid_number", f"{label}必须是 {low} 至 {high} 的整数")
    return value


def short_text(value, label, limit=120):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
        raise Rejected("invalid_text", f"{label}使用 1 至 {limit} 字符")
    return value.strip()


def labels(value):
    if not isinstance(value, dict) or len(value) > 12:
        raise Rejected("invalid_labels", "标签使用至多 12 个键值对")
    return {identifier(k, "标签键"): identifier(v, "标签值") for k, v in value.items()}
