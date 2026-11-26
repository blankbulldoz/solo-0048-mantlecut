from urllib.parse import parse_qs, urlsplit

from .documents import object_body, parse
from .errors import Rejected

MAX_BODY = 192 * 1024


def flatten(raw):
    try:
        pairs = parse_qs(raw, keep_blank_values=True, max_num_fields=32, errors="strict")
    except (ValueError, UnicodeError) as exc:
        raise Rejected("invalid_parameters", "表单或查询参数无效", 400) from exc
    if any(len(values) != 1 for values in pairs.values()):
        raise Rejected("duplicate_parameters", "不支持重复参数", 400)
    return {key: values[0] for key, values in pairs.items()}


def request_target(raw):
    try:
        url = urlsplit(raw)
    except ValueError as exc:
        raise Rejected("invalid_path", "请求路径无效", 400) from exc
    if url.scheme or url.netloc or not url.path.startswith("/") or len(url.path) > 1024:
        raise Rejected("invalid_path", "请求路径无效", 400)
    path = url.path[1:].split("/") if len(url.path) > 1 else []
    return path, flatten(url.query)


def read_data(handler, content_type):
    if handler.headers.get("Transfer-Encoding") is not None:
        raise Rejected("invalid_length", "请求需要明确的主体长度", 400)
    if handler.headers.get_content_type() != content_type:
        raise Rejected("invalid_content_type", f"请求需要 {content_type}", 415)
    sizes = handler.headers.get_all("Content-Length", [])
    if len(sizes) != 1 or not sizes[0].isascii() or not sizes[0].isdigit() or len(sizes[0]) > 8:
        raise Rejected("invalid_length", "请求需要明确的主体长度", 400)
    length = int(sizes[0])
    if length > MAX_BODY:
        raise Rejected("body_too_large", "请求主体超过 192 KiB", 413)
    body = handler.rfile.read(length)
    if len(body) != length:
        raise Rejected("incomplete_body", "请求主体未完整到达", 400)
    try:
        decoded = body.decode("utf-8")
    except UnicodeError as exc:
        raise Rejected("invalid_encoding", "请求应使用 UTF-8 编码", 400) from exc
    return object_body(parse(decoded)) if content_type == "application/json" else flatten(decoded)
