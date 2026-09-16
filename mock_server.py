"""Tiny stand-in for fuel-api: accepts the poller's requests and prints them.

    python3 mock_server.py                          # listens on http://127.0.0.1:8000
    python3 main.py --api-url http://127.0.0.1:8000

Answers with the same envelope shapes as the real API:
    POST /api/v1/devices                     -> 201 {"success": true, "data": {...}}
    POST /api/v1/devices/<site>/heartbeat    -> 200 {"success": true, "data": {"online": true}}
    POST /api/v1/logs                        -> 201 {"success": true, "data": {"id": n}}
"""

import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000


class Handler(BaseHTTPRequestHandler):
    next_id = 1

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""
        print(f"POST {self.path}", flush=True)
        if body:
            try:
                print(json.dumps(json.loads(body), indent=2), flush=True)
            except json.JSONDecodeError:
                print("non-JSON body:", body[:200], flush=True)

        if self.path == "/api/v1/logs":
            Handler.next_id += 1
            self._reply(201, {"success": True, "data": {"id": Handler.next_id - 1}})
        elif self.path.startswith("/api/v1/devices/") and self.path.endswith("/heartbeat"):
            site = self.path[len("/api/v1/devices/") : -len("/heartbeat")]
            self._reply(200, {"success": True, "data": {"site_id": site, "online": True}})
        elif self.path == "/api/v1/devices":
            self._reply(201, {"success": True, "data": json.loads(body or b"{}")})
        else:
            self._reply(404, {"success": False, "data": None, "error": {"message": f"no route for POST {self.path}"}})

    def _reply(self, status, payload):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())


if __name__ == "__main__":
    print(f"mock fuel-api listening on http://127.0.0.1:{PORT}  (use: --api-url http://127.0.0.1:{PORT})")
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
