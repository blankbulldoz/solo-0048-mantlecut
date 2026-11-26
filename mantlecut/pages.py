from datetime import datetime, timezone

from . import channels, control_api, forms, inspection, revisions, rollout
from .errors import Rejected, missing
from .seed import DEFAULT_CONFIG
from .view import EVENTS, badge, link, page, pretty, render, table, text


def _at(value):
    if value is None:
        return "—"
    return datetime.fromtimestamp(value / 1000, timezone.utc).strftime("%m-%d %H:%M:%S UTC")


def _channel_index(db, token):
    tiles = "".join(render(
        "line_tile", title=text(line["title"]), slug=text(line["slug"]),
        stability=text(f"发布 #{line['stable_release']}" if line["stable_release"] else "尚无稳态"),
    ) for line in channels.list_channels(db))
    return page("配置线", render("index", tiles=tiles or '<p class="muted">建一条配置线，开始登记代理。</p>', token=text(token)))


def _overview(db, slug, token):
    board = inspection.overview(db, slug)
    path = f"/lines/{slug}"
    active = board["active"]
    steady = board["channel"]["stable_release"]
    if active:
        status = rollout.status(db, slug, active["id"])
        work = render("active", label=badge(active["stage"]), release=link(f'{path}/releases/{active["id"]}', f'发布 #{active["id"]}'),
                      done=status["confirmed"], required=status["required"],
                      meter=status["confirmed"] * 100 // max(status["required"], 1), revision=active["revision"])
    else:
        work = '<p class="muted">当前没有在途发布。</p>'
    table_revisions = table(("版本", "阶段", "来源", "封存时间"), (
        (link(f"{path}/revisions/{r['id']}", f"#{r['id']} {r['title']}"), badge("sealed" if r["signature"] else "draft"),
         text(f"#{r['source_id']}" if r["source_id"] else "—"), text(_at(r["sealed_ms"])))
        for r in board["revisions"]
    ))
    table_nodes = table(("订阅端", "状态", "协议", "标签"), (
        (link(f"{path}/subscribers/{s['node']}", s["node"]), badge("paused" if s["paused"] else "enabled"),
         f"v{s['wire']}", text(" · ".join(f"{key}={value}" for key, value in s["tags"].items()) or "—"))
        for s in board["subscribers"]
    ))
    table_releases = table(("发布", "阶段", "版本", "起始时间"), (
        (link(f"{path}/releases/{r['id']}", f"#{r['id']}"), badge(r["stage"]), f"#{r['revision']}", text(_at(r["started_ms"])))
        for r in board["releases"]
    ))
    editor = render("revision_fields", title="", base=pretty(DEFAULT_CONFIG), layers="[]")
    return page(board["channel"]["title"], render(
        "line", title=text(board["channel"]["title"]), slug=text(slug), path=text(path), token=text(token), active=work,
        stable=link(f"{path}/releases/{steady}", f"发布 #{steady}") if steady else '尚无稳态',
        revisions=table_revisions, nodes=table_nodes, releases=table_releases, editor=editor,
    ), slug)


def _revision(db, now, slug, raw, token, query):
    number = control_api.number(raw)
    data = revisions.get(db, slug, number)
    board = inspection.overview(db, slug)
    line = f"/lines/{slug}"
    path = f"{line}/revisions/{number}"
    generation = data["generation"]
    options = ''.join(f'<option value="{text(s["node"])}"{" selected" if s["node"] == query.get("node") else ""}>{text(s["node"])}</option>'
                      for s in board["subscribers"])
    preview_box = ""
    if query.get("node"):
        try:
            outcome = control_api.read(db, now, ["channels", slug, "revisions", raw, "preview"], query)
        except Rejected as exc:
            if exc.status != 422:
                raise
            preview_box = f'<p class="waiting" role="status">{text(str(exc))}</p>'
        else:
            preview_box = render("preview", node=text(outcome["node"]), effective=pretty(outcome["effective"]),
                                 hits=text(" → ".join(outcome["matched"]) or "仅使用基底"),
                                 message=text(outcome.get("message", "协议可表达")), payload=text(outcome.get("payload", "—")))
    report = revisions.preflight(db, data)
    compatibility = table(("来源", "阻挡原因"), (
        (text(item["node"] or "基底"), text(item["message"])) for item in report["failures"]
    ), "全部已登记端可用")
    if data["signature"]:
        editor = render("sealed", base=pretty(data["base"]), layers=pretty(data["layers"]), signature=text(data["signature"]))
        actions = render("sealed_actions", line=text(line), token=text(token), revision=number, fork=text(f"{data['title'][:75]} · 副本"))
    else:
        fields = render("revision_fields", title=text(data["title"]), base=pretty(data["base"]), layers=pretty(data["layers"]))
        editor = render("edit", path=path, fields=fields, generation=generation, token=text(token))
        actions = forms.button(f"{path}/seal", "封存版本", token, "primary", generation=generation)
    return page(data["title"], render(
        "revision", title=text(data["title"]), revision=number, state=badge("sealed" if data["signature"] else "draft"),
        generation=generation, editor=editor, actions=actions, options=options,
        preview_form=render("preview_form", path=path, options=options) if options else '<p class="muted">登记订阅端后可试算。</p>',
        preview=preview_box, compatibility=compatibility, checked=report["checked"],
    ), slug)


def _release(db, slug, raw, token):
    number = control_api.number(raw)
    data = rollout.status(db, slug, number)
    path = f"/lines/{slug}/releases/{number}"
    roster = table(("席位", "订阅端", "试发", "领取情况", "应用回执"), (
        (str(seat["rank"]), link(f"/lines/{slug}/subscribers/{seat['node']}", seat["node"]),
         "是" if seat["trial"] else "—", badge("paused" if seat["paused"] else seat["latest"] or "unissued"),
         f"#{seat['applied_seq']}" if seat["applied_seq"] else "—") for seat in data["seats"]
    ))
    actions = ""
    if data["stage"] in {"trial", "wide"}:
        action, label = ("widen", "扩大到冻结全量") if data["stage"] == "trial" else ("settle", "切为稳态")
        if not data["blockers"]:
            actions += forms.button(f"{path}/{action}", label, token, "primary")
        actions += forms.button(f"{path}/withdraw", "撤回发布", token, "danger")
        waiting = "、".join(data["blockers"]) or "本阶段已满足应用门槛"
    else:
        waiting = "本轮已结束，席位保留供复核。"
    return page(f"发布 #{number}", render(
        "release", revision=link(f"/lines/{slug}/revisions/{data['revision']}", f"版本 #{data['revision']}"),
        release=number, badge=badge(data["stage"]), done=data["confirmed"], needed=data["required"], fraction=data["fraction"],
        waiting=text(waiting), seats=roster, actions=actions,
    ), slug)


def _node(db, now, slug, node, token):
    status = inspection.subscriber_state(db, now, slug, node)
    subscriber = status["subscriber"]
    target = status["target"]
    entries = table(("领取件", "发布／版本", "状态", "摘要", "签收时间", "原因"), (
        (f"#{offer['seq']}", f"#{offer['release']} / #{offer['revision']}", badge(offer["state"]),
         f'<code title="{text(offer["sha256"])}">{text(offer["sha256"][:12])}</code>', text(_at(offer["received_ms"])),
         text(offer["reason"] or "—")) for offer in status["offers"]
    ))
    paused = subscriber["paused"]
    action = forms.button(f"/lines/{slug}/subscribers/{node}/pause", "恢复取件" if paused else "暂停取件", token,
                          paused="false" if paused else "true")
    return page(node, render("subscriber", node=text(node), state=badge("paused" if paused else "enabled"),
                wire=subscriber["wire"], tags=pretty(subscriber["tags"]),
                target=link(f"/lines/{slug}/releases/{target['id']}", f"发布 #{target['id']}") if target else "暂无适用发布",
                offers=entries, action=action), slug)


def _events(db, slug, query):
    result = inspection.audit_page(db, slug, control_api.number(query["before"]) if "before" in query else control_api.MAX_NUMBER)
    rows = table(("事件号", "时间", "操作", "事实"), (
        (str(e["id"]), text(_at(e["at_ms"])), text(EVENTS.get(e["kind"], e["kind"])), f'<pre class="event">{pretty(e["detail"])}</pre>')
        for e in result["events"]
    ))
    more = link(f"/lines/{slug}/events?before={result['next_before']}", "较早事件", "button") if result["next_before"] else ""
    return page("审计记录", render("events", events=rows, more=more), slug)


def read(db, now, path, query, token):
    match path:
        case []:
            return _channel_index(db, token)
        case ["lines", slug]:
            return _overview(db, slug, token)
        case ["lines", slug, "revisions", number]:
            return _revision(db, now, slug, number, token, query)
        case ["lines", slug, "releases", number]:
            return _release(db, slug, number, token)
        case ["lines", slug, "subscribers", node]:
            return _node(db, now, slug, node, token)
        case ["lines", slug, "events"]:
            return _events(db, slug, query)
        case _:
            raise missing("页面")


def form_result(path, result):
    match path:
        case ["channels"]:
            return f"/lines/{result['slug']}", None
        case ["channels", slug, "subscribers"]:
            back = f"/lines/{slug}/subscribers/{result['node']}"
            return back, page("领取密钥", render("key", key=text(result["key"]), back=text(back)), slug)
        case ["channels", slug, "subscribers", node, "pause"]:
            return f"/lines/{slug}/subscribers/{node}", None
        case ["channels", slug, ("revisions" | "releases") as section, *_]:
            return f"/lines/{slug}/{section}/{result['id']}", None
        case _:
            raise missing("页面")
