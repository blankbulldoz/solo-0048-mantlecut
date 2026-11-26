# 配置分发 HTTP 样例

用 `python3 -m mantlecut --seed` 启动本机实例，从下列 URL 读取演示对象。通过 `python3 -m examples.walkthrough` 可在临时端口和数据目录走完整交互。

## 配置线与版本

`GET /api/channels/carbon-ridge` 返回当前稳态、在途发布、订阅端和版本索引。

`POST /api/channels/carbon-ridge/revisions` 创建一份草稿。以下草稿在西区先放宽时间窗口，再对边缘端降低采样比例。

```json
{
  "title": "西区窗口",
  "base": {"poll_ms": 2000, "flush_ms": 8000, "inflight": 64, "burst": 24, "upstream": "collector-main", "sampling": 100},
  "layers": [
    {"id": "west-window", "priority": 10, "when": {"site": "west"}, "patch": {"flush_ms": 12000}},
    {"id": "west-edge", "priority": 20, "when": {"site": "west", "tier": "edge"}, "patch": {"sampling": 70}}
  ]
}
```

`GET /api/channels/carbon-ridge/revisions/2/preview?node=reed-aux` 预览种子版本和订阅端。压缩层只命中北区订阅端。查询 `preflight` 可获取版本在当前登记人群中的所有兼容问题。

`POST /api/channels/carbon-ridge/revisions/3/seal` 检查并封存演示草稿。传 `{"generation":1}`。复制封存版则在创建草稿的入口使用 `{"title":"复核副本","source_id":1}`。

## 代理取件

`POST /agents/carbon-ridge/agate-west/pull`，使用 JSON 主体 `{}` 和头 `Authorization: Bearer mantlecut-demo-agate-west`。`agate-west` 是代际 1，`fir-remote` 是代际 2。两个端均可使用各自的演示密钥 `mantlecut-demo-<订阅端ID>`。已有端可能直接收到 `current`，可先创建新发布或注册新端体验领取。若收到 `offer`，解码制品并比对摘要。

`POST /agents/carbon-ridge/agate-west/receipts` 使用同一凭据。主体中 `seq` 和 `sha256` 从自己的取件响应取值。提交 `result: "applied"` 表示已应用。提交 `result: "rejected"` 时附带 `reason`。

代理单路处理领取件。应用前应校验摘要，验证尚在到期窗口内并防止旧领取件覆盖本地较高序号的应用结果。收到目标变化或过期的拒绝后，重新查询下发目标。

## 发布决策

`GET /api/channels/carbon-ridge/releases/2` 查看试发席位以及当前门槛。控制面发往同一路径的 `widen`、`settle` 或 `withdraw` 子路径，使用空对象 `{}`。创建新的发布向发布集合 POST `{"revision":1,"fraction":40}`，需先结束当前在途发布。

`GET /api/channels/carbon-ridge/events` 查看新到旧的事件号。下一页带 `?before=<next_before>`。
