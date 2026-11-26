"""在独立的临时 HTTP 实例复走配置分发。"""

import argparse
import base64
import hashlib
import json
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from mantlecut.seed import DEFAULT_CONFIG, NODES, SLUG, key, seed
from mantlecut.server import Handler, Server
from mantlecut.storage import Storage

LINE = "/api/channels/" + SLUG
LEGACY = "agate-west"
MODERN = "fir-remote"


class DemoTime:
    now = 1760000000000

    def __call__(self):
        return self.now


class Demo:
    def __init__(self, url, demo_time):
        self.url = url
        self.demo_time = demo_time

    def request(self, path, data=None, *, token=None, status=200):
        headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
        body = None
        if isinstance(data, dict):
            body = json.dumps(data).encode("utf-8")
            headers["Content-Type"] = "application/json"
        elif data is not None:
            body = data.encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        try:
            response = urlopen(Request(self.url + path, data=body, headers=headers), timeout=6)
        except HTTPError as exc:
            response = exc
        with response:
            content = response.read().decode("utf-8")
            if response.status != status:
                raise RuntimeError(f"{path} 应返回 {status}，实际 {response.status} {content[:160]}")
            return json.loads(content) if response.headers.get_content_type() == "application/json" else content

    def draft(self, *, base=None, layers=None, source=None):
        data = {"title": "走查用配置", "source_id": source} if source else {
            "title": "走查用配置", "base": base or DEFAULT_CONFIG, "layers": layers or [],
        }
        return self.request(LINE + "/revisions", data)

    def seal(self, revision, status=200):
        return self.request(f"{LINE}/revisions/{revision['id']}/seal", {"generation": revision["generation"]}, status=status)

    def start(self, revision, fraction=100, status=200):
        return self.request(LINE + "/releases", {"revision": revision, "fraction": fraction}, status=status)

    def advance(self, release, action, status=200):
        return self.request(f"{LINE}/releases/{release}/{action}", {}, status=status)

    def pull(self, node, *, token=None, status=200):
        return self.request(f"/agents/{SLUG}/{node}/pull", {}, token=token or key(node), status=status)

    def receipt(self, node, offer, result="applied", *, reason=None, token=None, status=200):
        return self.request(f"/agents/{SLUG}/{node}/receipts", {
            "seq": offer["seq"], "sha256": offer["sha256"], "result": result, "reason": reason,
        }, token=token or key(node), status=status)

    def status(self, release=2):
        return self.request(f"{LINE}/releases/{release}")


@contextmanager
def serve(path, demo_time, *, initialize=True):
    storage = Storage(path, demo_time)
    if initialize:
        seed(storage)
    with Server(0, storage, ttl_ms=1000) as server:
        worker = Thread(target=server.serve_forever, kwargs={"poll_interval": .02}, daemon=True)
        worker.start()
        try:
            yield Demo(f"http://127.0.0.1:{server.server_port}", demo_time)
        finally:
            server.shutdown()
            worker.join(timeout=2)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def payload(offer):
    raw = base64.b64decode(offer["body_b64"], validate=True)
    require(hashlib.sha256(raw).hexdigest() == offer["sha256"], "制品摘要应与收到的 UTF-8 字节一致")
    return json.loads(raw)


def complete(demo, release):
    trial = demo.status(release)
    for seat in trial["seats"]:
        if seat["trial"] and not seat["applied_seq"]:
            node = seat["node"]
            demo.receipt(node, demo.pull(node))
    wide = demo.advance(release, "widen")
    for seat in wide["seats"]:
        if not seat["applied_seq"]:
            node = seat["node"]
            demo.receipt(node, demo.pull(node))
    return demo.advance(release, "settle")


def agent_enroll(demo):
    registered = demo.request(LINE + "/subscribers", {"node": "late-east", "wire": 2, "tags": {"site": "east"}})
    offer = demo.pull("late-east", token=registered["key"])
    require(offer["release"] == 1, "在途期间登记的端应先取稳态")
    result = demo.request(LINE + "/subscribers", {"node": "legacy-north", "wire": 1, "tags": {"site": "north"}}, status=409)
    require(result["error"] == "subscriber_incompatible", "晚登记端须兼容未来稳态")
    overview = demo.request(LINE)
    require(all("key" not in item and "key_sha256" not in item for item in overview["subscribers"]), "密钥应只在登记时显示")


def draft_edit(demo):
    clone = demo.draft(source=1)
    proposed = dict(clone["base"], burst=30)
    path = f"{LINE}/revisions/{clone['id']}/edit"
    body = {"title": "缩短等待", "base": proposed, "layers": clone["layers"], "generation": clone["generation"]}
    revised = demo.request(path, body)
    stale = demo.request(path, body, status=409)
    require(revised["generation"] == 2 and revised["source_id"] == 1 and stale["error"] == "stale_generation", "代数及来源应持久保留")
    require(demo.request(f"{LINE}/revisions/1")["base"]["burst"] == 24, "复制编辑不得更改来源")


def layered_preview(demo):
    base = dict(DEFAULT_CONFIG, compression="gzip")
    layers = [
        {"id": "edge-clear", "priority": 20, "when": {"tier": "edge"}, "patch": {"compression": None}},
        {"id": "west-window", "priority": 10, "when": {"site": "west"}, "patch": {"flush_ms": 12000}},
        {"id": "west-restore", "priority": 30, "when": {"site": "west"}, "patch": {"compression": "gzip"}},
    ]
    revision = demo.draft(base=base, layers=layers)
    path = f"{LINE}/revisions/{revision['id']}/preview?node="
    old, modern, north = (demo.request(path + node) for node in (LEGACY, MODERN, "reed-aux"))
    require(old["matched"] == ["west-window", "edge-clear", "west-restore"] and not old["compatible"], "后续命中会恢复压缩")
    require(modern["effective"]["flush_ms"] == 12000 and modern["compatible"], "代际 2 应保留有效值")
    require(north["effective"]["compression"] == "off", "没有恢复层时应采用关闭语义")


def seal_check(demo):
    incompatible = demo.draft(base=dict(DEFAULT_CONFIG, poll_ms=1500, flush_ms=6000))
    report = demo.request(f"{LINE}/revisions/{incompatible['id']}/preflight")
    require({f["node"] for f in report["failures"]} == {LEGACY, "moraine-hub"}, "精度拒绝范围应匹配实际旧端")
    require(demo.seal(incompatible, 409)["error"] == "compatibility_blocked", "旧代际不允许近似转换")
    sealed = demo.seal(demo.draft())
    path = f"{LINE}/revisions/{sealed['id']}/edit"
    immutable = demo.request(path, {}, status=409)
    require(bool(sealed["signature"]) and immutable["error"] == "sealed_revision", "封存不可原位修改")


def trial_roster(demo):
    demo.advance(2, "withdraw")
    draft = demo.draft()
    require(demo.start(draft["id"], status=409)["error"] == "draft_not_sealed", "草稿不可直接发布")
    trial = demo.start(demo.seal(draft)["id"], 25)
    require(len(trial["seats"]) == 5 and trial["required"] == 2, "试发席位向上取整")
    require(demo.start(1, status=409)["error"] == "release_in_progress", "同线不得同时发布")
    chosen = [seat["node"] for seat in trial["seats"] if seat["trial"]]
    require(chosen == sorted(NODES, key=lambda node: hashlib.sha256(f"{SLUG}/{trial['id']}/{node}".encode()).digest())[:2], "试发席位应可复算")


def wire_pull(demo):
    demo.advance(2, "withdraw")
    for node, interval in ((LEGACY, "poll_s"), (MODERN, "poll_ms")):
        release = demo.start(1, 100) if node == LEGACY else demo.request(LINE)["active"]
        item = demo.pull(node)
        require(item["release"] == release["id"] and interval in payload(item), "同稿须按协议代际下发")
        require(demo.pull(node) == item, "同目标且未过期的领取件应重送")
    require(demo.pull(LEGACY, token="wrong", status=401)["error"] == "invalid_key", "订阅端凭据应绑定身份")


def pause_resume(demo):
    node = demo.status()["blockers"][0]
    offer = demo.pull(node)
    path = f"{LINE}/subscribers/{node}/pause"
    demo.request(path, {"paused": True})
    require(demo.pull(node)["reason"] == "paused", "暂停端不可取件")
    require(demo.receipt(node, offer, status=409)["error"] == "paused_subscriber", "暂停端不可提交新回执")
    require(node in demo.status()["blockers"], "暂停不重写试发冻结名单")
    demo.request(path, {"paused": False})
    require(demo.pull(node)["seq"] > offer["seq"], "恢复后旧领取件不得复活")


def signed_receipt(demo):
    node = demo.status()["blockers"][0]
    offer = demo.pull(node)
    altered = dict(offer, sha256="0" * 64)
    require(demo.receipt(node, altered, status=409)["error"] == "digest_mismatch", "不匹配的字节摘要不得落账")
    first = demo.receipt(node, offer)
    replay = demo.receipt(node, offer)
    require(not first["replayed"] and replay["replayed"] and replay["received_ms"] == first["received_ms"], "重送不应改写回执")
    require(demo.receipt(node, offer, "rejected", reason="执行拒绝", status=409)["error"] == "receipt_conflict", "重送不得改写终态")


def widen_and_settle(demo):
    require(demo.advance(2, "widen", 409)["error"] == "receipts_pending", "试发未确认应阻挡扩大")
    result = complete(demo, 2)
    require(result["stage"] == "stable" and result["confirmed"] == 5, "全体席位确认后才切稳")
    require(demo.request(LINE)["channel"]["stable_release"] == 2, "新稳态应与发布终态一致")


def withdraw(demo):
    node = demo.status()["blockers"][0]
    in_flight = demo.pull(node)
    require(demo.advance(2, "withdraw")["stage"] == "withdrawn", "发布应结束")
    require(demo.receipt(node, in_flight, status=409)["error"] == "superseded_offer", "撤回后不可确认旧目的")
    restored = demo.pull(node)
    require(restored["release"] == 1 and restored["seq"] > in_flight["seq"], "曾领取过候选的端须重领稳态")
    demo.receipt(node, restored)
    require(demo.pull(node)["reason"] == "current", "稳态确认后不再重复发件")


def expire_and_reject(demo):
    node = demo.status()["blockers"][0]
    first = demo.pull(node)
    demo.demo_time.now = first["expires_ms"]
    require(demo.receipt(node, first, status=409)["error"] == "offer_expired", "到期点即不可提交")
    second = demo.pull(node)
    require(second["seq"] > first["seq"], "到期后需要新领取件")
    demo.receipt(node, second, "rejected", reason="端侧队列正在排空")
    require(demo.pull(node)["reason"] == "rejected", "当前目标的拒绝是终局")
    require(demo.advance(2, "widen", 409)["error"] == "receipts_pending", "拒绝不计入放量门槛")


def concurrent_receipt(demo):
    node = demo.status()["blockers"][0]
    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = pool.map(demo.pull, (node, node))
        require(first == second, "同端并发领取应得到同一个领取件")
        statuses = list(pool.map(lambda offer: demo.receipt(node, offer)["replayed"], (first, second)))
    require(sorted(statuses) == [False, True], "并发回执只应有一笔真正写入")


def audit_cursor(demo):
    for _ in range(10):
        demo.draft(source=1)
    first = demo.request(LINE + "/events")
    demo.draft(source=1)
    second = demo.request(LINE + f"/events?before={first['next_before']}")
    require(len(first["events"]) == 32 and bool(second["events"]), "审计应使用有界的持久游标")
    require(max(e["id"] for e in second["events"]) < min(e["id"] for e in first["events"]), "追加事件不应漂移旧页")
    entry = demo.request(f"{LINE}/subscribers/{LEGACY}")
    require("subscriber" in entry and "offers" in entry and "target" in entry, "端视图应关联期望目标和历史证据")


def html_console(demo):
    page = demo.request(f"/lines/{SLUG}")
    token = re.search(r'name="_token" value="([a-f0-9]+)"', page)[1]
    form = {"title": "来自网页的草稿", "base": json.dumps(DEFAULT_CONFIG), "layers": "[]", "_token": token}
    route = f"/lines/{SLUG}/revisions"
    demo.request(route, urlencode(dict(form, _token="old")), status=403)
    rendered = demo.request(route, urlencode(form))
    require("来自网页的草稿" in rendered and "协议预检" in rendered and "更新草稿" in rendered, "网页应写入真实草稿并跳转到结果")
    release = demo.request(f"/lines/{SLUG}/releases/2")
    require("冻结席位" in release and "撤回发布" in release, "网页应反映实际发布阶段")


def reopen(path, demo_time):
    with serve(path, demo_time) as demo:
        node = demo.status()["blockers"][0]
        offer = demo.pull(node)
    with serve(path, demo_time, initialize=False) as demo:
        require(demo.pull(node) == offer, "重开后仍应取到原领取件")
        require(demo.receipt(node, offer)["replayed"] is False, "重开后应可完成在途回执")
        require(demo.status()["confirmed"] == 2, "发布门槛应从持久回执恢复")


SCENARIOS = {
    "agent-enroll": agent_enroll, "draft-edit": draft_edit, "layered-preview": layered_preview, "seal-check": seal_check,
    "trial-roster": trial_roster, "wire-pull": wire_pull, "pause-resume": pause_resume, "signed-receipt": signed_receipt,
    "widen-settle": widen_and_settle, "withdraw": withdraw, "expire-reject": expire_and_reject,
    "concurrent-receipt": concurrent_receipt, "audit-cursor": audit_cursor, "html-console": html_console, "reopen": reopen,
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", nargs="?", choices=SCENARIOS)
    args = parser.parse_args()
    Handler.log_message = lambda *_: None
    for name in (args.scenario,) if args.scenario else SCENARIOS:
        with tempfile.TemporaryDirectory(prefix="mantlecut-") as directory:
            state = Path(directory) / "state.sqlite3"
            demo_time = DemoTime()
            if name == "reopen":
                reopen(state, demo_time)
            else:
                with serve(state, demo_time) as demo:
                    SCENARIOS[name](demo)
            print(f"{name}: 通过")


if __name__ == "__main__":
    main()
