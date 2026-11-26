import json
from functools import lru_cache
from html import escape
from pathlib import Path
from string import Template

from . import VERSION

LABELS = {
    "trial": "试发中", "wide": "全量验证", "stable": "已切稳", "withdrawn": "已撤回",
    "draft": "草稿", "sealed": "已封存", "open": "已领取", "expired": "已过期",
    "superseded": "目标已变", "applied": "已应用", "rejected": "已拒绝", "paused": "已暂停",
    "enabled": "可取件", "unissued": "未领取",
}

EVENTS = {
    "channel_created": "创建配置线", "subscriber_registered": "登记订阅端", "subscriber_paused": "暂停订阅端",
    "subscriber_resumed": "恢复订阅端", "draft_created": "创建草稿", "draft_edited": "编辑草稿",
    "revision_sealed": "封存版本", "release_started": "启动试发", "release_wide": "扩大受众",
    "release_stable": "切为稳态", "release_withdrawn": "撤回发布", "offer_issued": "代理领取制品",
    "offer_expired": "领取超时", "offer_superseded": "领取目标变更", "receipt_recorded": "记录应用回执",
}


def text(value):
    return escape(str(value), quote=True)


def pretty(value):
    return text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


@lru_cache(maxsize=20)
def load(name):
    path = Path(__file__).with_name("templates") / f"{name}.html"
    return Template(path.read_text(encoding="utf-8"))


def render(name, **values):
    return load(name).substitute(values)


def badge(status):
    return f'<span class="badge {text(status)}">{text(LABELS[status])}</span>'


def link(url, label, css=""):
    return f'<a class="{text(css)}" href="{text(url)}">{text(label)}</a>'


def table(headings, rows, empty="暂无记录"):
    header = "".join(f"<th scope=\"col\">{text(cell)}</th>" for cell in headings)
    content = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    if not content:
        content = f'<tr><td colspan="{len(headings)}" class="muted">{text(empty)}</td></tr>'
    return f'<div class="table-wrap"><table><thead><tr>{header}</tr></thead><tbody>{content}</tbody></table></div>'


def page(title, content, slug=None):
    navigation = link("/", "配置线")
    if slug:
        navigation += link(f"/lines/{slug}", slug, "current") + link(f"/lines/{slug}/events", "审计记录")
    return render("layout", title=text(title), navigation=navigation, content=content, version=text(VERSION))
