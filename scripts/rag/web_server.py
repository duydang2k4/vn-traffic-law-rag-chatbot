"""Serve the local Vietnamese traffic-law interface using the existing RAG index."""

import argparse
import json
import sqlite3
from contextlib import closing
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from scripts import ROOT
from scripts.rag.baseline_rag import answer
from scripts.rag.llm import load_llm
from scripts.rag.rag_index import INDEX, fingerprint

ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
}


class Handler(BaseHTTPRequestHandler):
    def __init__(self, *args, llm=None):
        self.llm = llm
        super().__init__(*args)

    def respond(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def respond_json(self, status, result):
        self.respond(status, json.dumps(result, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def do_GET(self):
        asset = ASSETS.get(urlsplit(self.path).path)
        if asset is None:
            self.send_error(404)
            return
        name, content_type = asset
        self.respond(200, (ROOT / "web" / name).read_bytes(), content_type)

    def do_POST(self):
        if self.path != "/api/ask":
            self.send_error(404)
            return
        if self.headers.get_content_type() != "application/json":
            self.respond_json(415, {"error": "Yêu cầu phải dùng JSON."})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 1 <= size <= 8192:
                raise ValueError
            payload = json.loads(self.rfile.read(size))
            question = payload.get("question") if isinstance(payload, dict) else None
            if not isinstance(question, str) or not 1 <= len(question.strip()) <= 1000:
                raise ValueError
        except (ValueError, UnicodeError):
            self.respond_json(400, {"error": "Nhập câu hỏi dài từ 1 đến 1.000 ký tự."})
            return
        try:
            with closing(sqlite3.connect(f"{INDEX.as_uri()}?mode=ro", uri=True)) as db:
                snapshot = db.execute("SELECT value FROM metadata WHERE key='snapshot'").fetchone()
                if snapshot != (fingerprint(),):
                    self.respond_json(503, {"error": "Dữ liệu đã đổi. Hãy cập nhật dữ liệu và xây lại chỉ mục."})
                    return
                result = answer(db, question.strip(), llm=self.llm)
        except (OSError, sqlite3.Error, ValueError, KeyError):
            self.respond_json(503, {"error": "Chỉ mục chưa sẵn sàng. Hãy chạy lệnh build trong README."})
            return
        self.respond_json(200, result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    try:
        llm = load_llm()
    except (OSError, ValueError) as error:
        parser.error(str(error))
    with ThreadingHTTPServer(("127.0.0.1", args.port), partial(Handler, llm=llm)) as server:
        print(f"Local: http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
