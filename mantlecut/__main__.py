import argparse
from pathlib import Path

from .seed import seed
from .server import Server
from .storage import Storage


def main():
    parser = argparse.ArgumentParser(description="启动层签配置分发服务")
    parser.add_argument("--port", type=int, default=8794, help="本机 HTTP 端口")
    parser.add_argument("--state", type=Path, default=Path(".mantlecut/state.sqlite3"), help="SQLite 状态文件")
    parser.add_argument("--seed", action="store_true", help="在空实例写入演示配置线")
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("端口必须介于 0 和 65535")
    storage = Storage(args.state)
    with Server(args.port, storage) as server:
        if args.seed:
            seed(storage)
        print(f"层签运行于 http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
