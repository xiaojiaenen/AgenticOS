"""
cdg-gateway —— 把本机管道桥包装成 HTTP 服务，供任何语言/任何主机的服务调用。

零依赖（只用标准库），可直接跑在装有亿赛通客户端的 Windows 机器上：

    python gateway.py --port 8765 --token CHANGE_ME

之后任何地方都能这样用：

    curl -H "X-Token: CHANGE_ME" "http://WIN_HOST:8765/file?path=D:/Data/a.xlsx" -o a.xlsx

接口：
    GET  /health                          服务与桥状态
    GET  /file?path=...                   下载明文原始字节（octet-stream）
    PUT  /file?path=...                   上传并写回（body 为字节）
    GET  /head?path=...&n=16              读文件头 hex，用于判定明文/密文
    GET  /classify?path=...               plain / cipher / unknown
    GET  /stat?path=...                   大小、时间、属性
    GET  /list?dir=...&pattern=*.xlsx     目录列表（JSON）
    POST /copy?src=...&dst=...            服务端复制（明文字节直通）
    DELETE /file?path=...                 删除
    POST /mkdir?path=...                  建目录
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "python"))

import cdgfs

TOKEN = ""


def _norm(p: str) -> str:
    """把 URL 里的 / 或 \\ 统一成 Windows 本地路径。"""
    if not p:
        raise ValueError("missing path")
    p = p.replace("/", os.sep).replace("\\", os.sep)
    return os.path.abspath(p)


class Handler(BaseHTTPRequestHandler):
    server_version = "cdg-gateway/1.0"
    protocol_version = "HTTP/1.1"

    # ---------------------------------------------------------------- 工具
    def _auth(self) -> bool:
        if not TOKEN:
            return True
        got = self.headers.get("X-Token") or ""
        if not got:
            q = urllib.parse.urlparse(self.path).query
            qs = urllib.parse.parse_qs(q)
            got = (qs.get("token") or [""])[0]
        if got != TOKEN:
            self._json(401, {"error": "unauthorized"})
            return False
        return True

    def _json(self, code: int, obj) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _bytes(self, code: int, data: bytes, ctype="application/octet-stream") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _query(self) -> dict:
        q = urllib.parse.urlparse(self.path).query
        return {k: v[0] for k, v in urllib.parse.parse_qs(q).items()}

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    # ---------------------------------------------------------------- 路由
    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/health":
            try:
                host = cdgfs.ping()
                return self._json(200, {"ok": True, "bridge": host})
            except cdgfs.BridgeError as e:
                return self._json(503, {"ok": False, "error": str(e)})

        if not self._auth():
            return
        q = self._query()

        try:
            if path == "/file":
                data = cdgfs.read_bytes(_norm(q.get("path", "")))
                return self._bytes(200, data)

            if path == "/head":
                n = int(q.get("n", 16))
                h = cdgfs.head(_norm(q.get("path", "")), n)
                return self._json(200, {"hex": h})

            if path == "/classify":
                kind, detail = cdgfs.classify(_norm(q.get("path", "")))
                return self._json(200, {"kind": kind, "detail": detail})

            if path == "/stat":
                return self._json(200, cdgfs.stat(_norm(q.get("path", ""))))

            if path == "/list":
                rows = cdgfs.listdir(_norm(q.get("dir", "")), q.get("pattern", "*"))
                return self._json(200, {"items": rows})

        except cdgfs.BridgeError as e:
            return self._json(502, {"error": "bridge", "detail": str(e)})
        except (OSError, ValueError) as e:
            return self._json(400, {"error": "bad request", "detail": str(e)})

        self._json(404, {"error": "not found", "path": path})

    def do_PUT(self):
        if not self._auth():
            return
        q = self._query()
        try:
            n = int(self.headers.get("Content-Length", "0"))
            data = self.rfile.read(n) if n else b""
            target = _norm(q.get("path", ""))
            cdgfs.write_bytes(target, data)
            return self._json(200, {"ok": True, "path": target, "size": len(data)})
        except cdgfs.BridgeError as e:
            return self._json(502, {"error": "bridge", "detail": str(e)})
        except (OSError, ValueError) as e:
            return self._json(400, {"error": "bad request", "detail": str(e)})

    def do_POST(self):
        if not self._auth():
            return
        path = urllib.parse.urlparse(self.path).path
        q = self._query()
        try:
            if path == "/copy":
                cdgfs.copy(_norm(q.get("src", "")), _norm(q.get("dst", "")))
                return self._json(200, {"ok": True})
            if path == "/mkdir":
                cdgfs.mkdir(_norm(q.get("path", "")))
                return self._json(200, {"ok": True})
        except cdgfs.BridgeError as e:
            return self._json(502, {"error": "bridge", "detail": str(e)})
        except (OSError, ValueError) as e:
            return self._json(400, {"error": "bad request", "detail": str(e)})
        self._json(404, {"error": "not found", "path": path})

    def do_DELETE(self):
        if not self._auth():
            return
        q = self._query()
        try:
            cdgfs.remove(_norm(q.get("path", "")))
            return self._json(200, {"ok": True})
        except cdgfs.BridgeError as e:
            return self._json(502, {"error": "bridge", "detail": str(e)})
        except (OSError, ValueError) as e:
            return self._json(400, {"error": "bad request", "detail": str(e)})


def main():
    global TOKEN
    ap = argparse.ArgumentParser(description="cdg-bridge HTTP gateway")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--bind", default="127.0.0.1",
                    help="对外提供服务用 0.0.0.0，仅本机用 127.0.0.1")
    ap.add_argument("--token", default="", help="访问令牌，空则不校验")
    ap.add_argument("--pipe", default="cdgbridge", help="管道名")
    ap.add_argument("--auto-start", action="store_true",
                    help="桥未运行时自动拉起（需给 --dll）")
    ap.add_argument("--dll", default="", help="bridge.dll 路径")
    args = ap.parse_args()

    TOKEN = args.token
    cdgfs.PIPE_NAME = args.pipe

    try:
        cdgfs.ping()
    except cdgfs.BridgeError:
        if args.auto_start and args.dll:
            print(f"[..] 桥未运行，自动启动 {args.dll}")
            cdgfs.start(args.dll, args.pipe)
        else:
            print("[!] 桥未运行：先执行 start-bridge.cmd，或加 --auto-start --dll <path>")

    srv = ThreadingHTTPServer((args.bind, args.port), Handler)
    print(f"[OK] cdg-gateway listening on http://{args.bind}:{args.port}  pipe={args.pipe}")
    print(f"     health: curl http://{args.bind}:{args.port}/health")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[..] shutting down")
        srv.shutdown()


if __name__ == "__main__":
    main()
