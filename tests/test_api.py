import json
import threading
import unittest
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

from tls.api import ApiClient, ApiError, build_payload
from tls.protocol import InventoryReport, TankInventory


class _Handler(BaseHTTPRequestHandler):
    received = []

    def do_POST(self):
        length = int(self.headers["Content-Length"])
        _Handler.received.append((self.path, dict(self.headers), self.rfile.read(length)))
        self.send_response(500 if self.path.endswith("/fail") else 201)
        self.end_headers()

    def log_message(self, *args):
        pass


class ApiClientTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), _Handler)
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_posts_json_with_bearer_token(self):
        client = ApiClient(f"{self.base}/readings", api_key="secret")
        client.post({"hello": "world"})

        path, headers, body = _Handler.received[-1]
        self.assertEqual(path, "/readings")
        self.assertEqual(headers["Authorization"], "Bearer secret")
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(json.loads(body), {"hello": "world"})

    def test_raises_on_http_error(self):
        client = ApiClient(f"{self.base}/fail")
        with self.assertRaises(ApiError):
            client.post({})


class BuildPayloadTest(unittest.TestCase):
    def test_serialises_report_with_iso_timestamps(self):
        report = InventoryReport(
            function="i201",
            timestamp=datetime(2026, 9, 15, 12, 30),
            tanks=(TankInventory(1, 1000.0, 0.0, 4000.0, 48.25, 0.0, 76.1, 0.0),),
        )
        payload = build_payload("site-1", inventory=report)

        self.assertEqual(payload["site_id"], "site-1")
        self.assertEqual(payload["inventory"]["timestamp"], "2026-09-15T12:30:00")
        self.assertEqual(payload["inventory"]["tanks"][0]["tank"], 1)
        self.assertNotIn("status", payload)
        json.dumps(payload)  # must be JSON serialisable


if __name__ == "__main__":
    unittest.main()
