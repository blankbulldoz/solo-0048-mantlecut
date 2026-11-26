# 层签 Mantlecut

层签是一个采集代理配置分发服务。运维人员在浏览器里编辑配置并跟进灰度。代理通过 HTTP 领取自己的配置制品，应用后提交回执。

## 启动

需要 Python 3.11 或更新版本及其标准库中的 SQLite。在项目根目录执行以下命令。

```sh
python3 -m mantlecut --seed
```

在浏览器打开 `http://127.0.0.1:8794`。示例包含「脊线采集」的稳态版本、一个未完成的试发和两种协议订阅端。示例端的凭据仅用于本机演示。省略 `--seed` 可使用空实例。默认状态路径为 `.mantlecut/state.sqlite3`，可用 `--state` 和 `--port` 启动独立实例。HTTP 仅监听回环地址，供本机受信运维与代理演练使用。请在受控目录保存状态库。

## 动手操作

在「配置线」创建草稿，粘贴基础 JSON 和标签叠层数组，选择已登记订阅端预览。可从封存版复制草稿。封存后可启动指定比例的试发。「发布」显示端是否属于试发席位、是否已成功应用，以及扩大和切稳门槛。「订阅端」可以暂停或恢复取件。「审计记录」按持久事件号列出实际发生的操作。

## HTTP 接口

控制面接受 `application/json`，GET 返回 JSON。业务错误包含 `error` 和 `message`，状态冲突使用 409。配置参数约束见 [项目规格](PROJECT_SPEC.md)。完整的请求样本见 [API 样例](examples/requests.md)，演示脚本可在临时实例完成完整交付和撤回。

```sh
python3 -m examples.walkthrough
```

代理调用 `/agents/<slug>/<node>/pull` 和 `/agents/<slug>/<node>/receipts`，请求携带 `Authorization: Bearer <领取密钥>`。领取响应包含 `seq`、`revision`、`release`、`expires_ms`、`sha256` 及 Base64 制品 `body_b64`。代理核验 Base64 解码后 UTF-8 字节的摘要，应用后以 `seq`、`sha256` 和 `applied` 提交回执，也可提交 `rejected` 和原因。`idle` 表示当前无待应用领取件。

自动化测试延后。`python3 -m compileall -q mantlecut examples` 执行离线构建检查，场景复走启动真实 HTTP 服务并使用临时 SQLite 状态。
