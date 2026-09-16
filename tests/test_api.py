import json
import threading
import unittest
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

from tls.api import ApiClient, ApiError, build_payload, normalise_base_url
from tls.protocol import InventoryReport, TankInventory


class _Handler(BaseHTTPRequestHandler):
    """Fake fuel-api: answers each endpoint with the real envelope shapes."""

    received = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""
        _Handler.received.append((self.path, dict(self.headers), body))

        if self.path == "/api/v1/logs":
            self._reply(201, {"success": True, "data": {"id": 1}})
        elif self.path.endswith("/heartbeat"):
            self._reply(200, {"success": True, "data": {"site_id": "x", "online": True}})
        elif self.path == "/api/v1/devices":
            site = json.loads(body).get("site_id")
            if site == "taken":
                self._reply(409, {"success": False, "data": None, "error": {"message": "a device is already registered"}})
            else:
                self._reply(201, {"success": True, "data": {"site_id": site}})
        elif self.path == "/api/v1/unknown-site":
            self._reply(422, {"success": False, "data": None, "error": {"message": "unknown site_id", "details": ["no device for ghost"]}})
        else:
            self._reply(500, {"success": False, "data": None, "error": {"message": "boom"}})

    def _reply(self, status, body):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

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

    def test_post_log_targets_v1_logs_with_bearer_token_and_json(self):
        client = ApiClient(self.base, "station-7", api_key="secret")
        status = client.post_log({"hello": "world"})

        path, headers, body = _Handler.received[-1]
        self.assertEqual(status, 201)
        self.assertEqual(path, "/api/v1/logs")
        self.assertEqual(headers["Authorization"], "Bearer secret")
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(json.loads(body), {"hello": "world"})

    def test_heartbeat_posts_to_the_site_route_with_no_body(self):
        client = ApiClient(self.base, "site with space", api_key="secret")
        self.assertTrue(client.heartbeat())

        path, headers, body = _Handler.received[-1]
        self.assertEqual(path, "/api/v1/devices/site%20with%20space/heartbeat")
        self.assertEqual(headers["Authorization"], "Bearer secret")
        self.assertEqual(body, b"")

    def test_register_device_reports_created_or_exists(self):
        self.assertEqual(ApiClient(self.base, "fresh").register_device("Fresh", 1.5, 2.5), "created")
        _, _, body = _Handler.received[-1]
        self.assertEqual(json.loads(body), {"site_id": "fresh", "name": "Fresh", "lat": 1.5, "lng": 2.5})

        self.assertEqual(ApiClient(self.base, "taken").register_device("Taken", 0, 0), "exists")

    def test_errors_carry_the_status_and_the_envelope_message(self):
        client = ApiClient(self.base, "s")
        with self.assertRaises(ApiError) as ctx:
            client._request("POST", f"{self.base}/api/v1/unknown-site", {})
        self.assertEqual(ctx.exception.status, 422)
        self.assertIn("unknown site_id", str(ctx.exception))
        self.assertIn("no device for ghost", str(ctx.exception))

        with self.assertRaises(ApiError) as ctx:
            client._request("POST", f"{self.base}/api/v1/nope", {})
        self.assertEqual(ctx.exception.status, 500)
        self.assertIn("boom", str(ctx.exception))

    def test_unreachable_server_has_no_status(self):
        client = ApiClient("http://127.0.0.1:9", "s", timeout=0.5)
        with self.assertRaises(ApiError) as ctx:
            client.post_log({})
        self.assertIsNone(ctx.exception.status)


class NormaliseBaseUrlTest(unittest.TestCase):
    def test_strips_trailing_slash_and_legacy_endpoint_paths(self):
        self.assertEqual(normalise_base_url("https://api.example/"), "https://api.example")
        self.assertEqual(normalise_base_url("http://10.0.0.1:3000/readings"), "http://10.0.0.1:3000")
        self.assertEqual(normalise_base_url("http://10.0.0.1:3000/v1/logs/"), "http://10.0.0.1:3000")
        self.assertEqual(normalise_base_url("http://10.0.0.1:3000/api/v1/logs"), "http://10.0.0.1:3000")
        self.assertEqual(normalise_base_url("https://api.example"), "https://api.example")

    def test_client_derives_every_endpoint_from_the_base(self):
        client = ApiClient("http://h:3000/readings", "station-7")
        self.assertEqual(client.base_url, "http://h:3000")
        self.assertEqual(client.logs_url, "http://h:3000/api/v1/logs")
        self.assertEqual(client.devices_url, "http://h:3000/api/v1/devices")
        self.assertEqual(client.heartbeat_url, "http://h:3000/api/v1/devices/station-7/heartbeat")


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
