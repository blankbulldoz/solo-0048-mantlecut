import hmac
import json
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import agent_api, control_api, forms, http_input, pages
from .errors import Rejected, missing
from .view import page, render, text


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port, storage, *, ttl_ms=45000):
        self.storage = storage
        self.token = secrets.token_hex(24)
        self.ttl_ms = ttl_ms
        super().__init__(("127.0.0.1", port), Handler)
        self.hosts = {f"127.0.0.1:{self.server_port}", f"localhost:{self.server_port}"}


class Handler(BaseHTTPRequestHandler):
    server_version = "Mantlecut"
    sys_version = ""
    timeout = 8

    def _send(self, code, body, content_type):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, value, code=200):
        data = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self._send(code, data, "application/json; charset=utf-8")

    def _html(self, value, code=200):
        self._send(code, value.encode("utf-8"), "text/html; charset=utf-8")

    def _redirect(self, url):
        self.send_response(303)
        self.send_header("Location", url)
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def _enforce_local(self, write):
        hosts = self.headers.get_all("Host", [])
        if len(hosts) != 1 or hosts[0] not in self.server.hosts:
            raise Rejected("invalid_host", "请通过本机地址访问层签", 403)
        if write:
            origins = self.headers.get_all("Origin", [])
            if len(origins) > 1 or (origins and origins[0] != "http://" + hosts[0]):
                raise Rejected("invalid_origin", "写入请求来自不同页面来源", 403)

    def _handle_request(self, write):
        path = []
        try:
            self._enforce_local(write)
            path, query = http_input.request_target(self.path)
            if not write and path == ["health"]:
                with self.server.storage.transaction() as (db, _):
                    db.execute("SELECT 1 FROM channels LIMIT 1").fetchone()
                return self._json({"status": "ready"})
            if not write and path == ["assets", "console.css"]:
                css = Path(__file__).with_name("static") / "console.css"
                return self._send(200, css.read_bytes(), "text/css; charset=utf-8")
            if path and path[0] in {"api", "agents"}:
                reply = self._api(path, query, write)
                return self._json(reply)
            if write:
                return self._form(path)
            with self.server.storage.transaction() as (db, now):
                content = pages.read(db, now, path, query, self.server.token)
            return self._html(content)
        except Rejected as exc:
            if self.path.startswith(("/api/", "/agents/", "/health")):
                return self._json({"error": exc.code, "message": str(exc)}, exc.status)
            content = render("error", message=text(str(exc)))
            return self._html(page("操作未完成", content), exc.status)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            self.close_connection = True
            return None

    def _api(self, path, query, write):
        if not write and path[0] != "api":
            raise missing("接口")
        body = http_input.read_data(self, "application/json") if write else None
        with self.server.storage.transaction(write=write) as (db, now):
            if path[0] == "agents":
                scheme, _, key = self.headers.get("Authorization", "").partition(" ")
                return agent_api.change(db, now, path[1:], key if scheme.lower() == "bearer" else "", body, self.server.ttl_ms)
            if write:
                return control_api.change(db, now, path[1:], body)
            return control_api.read(db, now, path[1:], query)

    def _form(self, path):
        if not path or path[0] != "lines":
            raise missing("表单")
        body = http_input.read_data(self, "application/x-www-form-urlencoded")
        if not hmac.compare_digest(body.get("_token", "").encode("utf-8"), self.server.token.encode("ascii")):
            raise Rejected("invalid_form_token", "页面凭据已失效，请重新打开表单", 403)
        route, data = forms.to_control(["channels", *path[1:]], body)
        with self.server.storage.transaction(write=True) as (db, now):
            result = control_api.change(db, now, route, data)
        url, message = pages.form_result(route, result)
        return self._html(message) if message else self._redirect(url)

    def do_GET(self):
        self._handle_request(False)

    def do_POST(self):
        self._handle_request(True)
