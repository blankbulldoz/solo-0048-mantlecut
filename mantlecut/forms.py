from .control_api import number
from .documents import parse
from .errors import missing, Rejected
from .view import render, text


def button(path, label, token, css="", **hidden):
    fields = "".join(f'<input type="hidden" name="{text(k)}" value="{text(v)}">' for k, v in hidden.items())
    return render("button", path=text(path), label=text(label), token=text(token), css=text(css), fields=fields)


def revision_fields(form):
    return {"title": form.get("title"), "base": parse(form.get("base", "")), "layers": parse(form.get("layers", ""))}


def to_control(path, form):
    value = form.get
    match path:
        case ["channels"]:
            return path, {"slug": value("slug"), "title": value("title")}
        case ["channels", _, "subscribers"]:
            return path, {"node": value("node"), "wire": number(value("wire", "")), "tags": parse(value("tags", "{}"))}
        case ["channels", _, "subscribers", _, "pause"]:
            if value("paused") not in {"true", "false"}:
                raise Rejected("invalid_pause", "订阅端操作无效")
            return path, {"paused": value("paused") == "true"}
        case ["channels", _, "revisions"]:
            if "source_id" in form:
                return path, {"title": value("title"), "source_id": number(value("source_id", ""))}
            return path, revision_fields(form)
        case ["channels", _, "revisions", _, "edit"]:
            return path, dict(revision_fields(form), generation=number(value("generation", "")))
        case ["channels", _, "revisions", _, "seal"]:
            return path, {"generation": number(value("generation", ""))}
        case ["channels", _, "releases"]:
            return path, {"revision": number(value("revision", "")), "fraction": number(value("fraction", ""))}
        case ["channels", _, "releases", _, "widen" | "settle" | "withdraw"]:
            return path, {}
        case _:
            raise missing("表单")
