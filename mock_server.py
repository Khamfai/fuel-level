"""Tiny stand-in for the real REST API: accepts POSTs and prints the JSON.

    python3 mock_server.py            # listens on http://127.0.0.1:8000/readings
    python3 main.py --api-url http://127.0.0.1:8000/readings
"""

import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            print(json.dumps(json.loads(body), indent=2), flush=True)
        except json.JSONDecodeError:
            print("non-JSON body:", body[:200], flush=True)
        self.send_response(201)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok": true}')


if __name__ == "__main__":
    print(f"mock API listening on http://127.0.0.1:{PORT}/readings")
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
