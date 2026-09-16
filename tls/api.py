"""Talk to the fuel-api REST service (standard library only).

Endpoints used, relative to the API base URL:
    POST /v1/devices                       register this site's device (once)
    POST /v1/devices/{site_id}/heartbeat   "still alive", sent every poll cycle
    POST /v1/logs                          one gauge report

Every response is an envelope: {"success": true, "data": ...} or
{"success": false, "data": null, "error": {"message": "...", "details": [...]}}.
"""

from __future__ import annotations

import dataclasses
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Optional

from tls.protocol import Delivery, DeliveryReport, InventoryReport, StatusReport

DEFAULT_TIMEOUT_S = 10.0
FLOAT_DECIMALS = 3  # gauge floats are single precision; more digits is noise

# Older configs pointed --api-url at the full endpoint; accept them and strip the path.
LEGACY_ENDPOINT_SUFFIXES = ("/v1/logs", "/readings")


class ApiError(Exception):
    """The server rejected the request or could not be reached.

    `status` is the HTTP status code, or None when the server was unreachable.
    """

    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


def normalise_base_url(url: str) -> str:
    """Trim a trailing slash and any legacy endpoint path, leaving the API base URL."""
    base = url.strip().rstrip("/")
    for suffix in LEGACY_ENDPOINT_SUFFIXES:
        if base.endswith(suffix):
            base = base[: -len(suffix)].rstrip("/")
            break
    return base


class ApiClient:
    def __init__(self, base_url: str, site_id: str, api_key: Optional[str] = None, timeout: float = DEFAULT_TIMEOUT_S):
        self.base_url = normalise_base_url(base_url)
        self._site_id = site_id
        self._api_key = api_key
        self._timeout = timeout

    @property
    def logs_url(self) -> str:
        return f"{self.base_url}/v1/logs"

    @property
    def devices_url(self) -> str:
        return f"{self.base_url}/v1/devices"

    @property
    def heartbeat_url(self) -> str:
        return f"{self.devices_url}/{urllib.parse.quote(self._site_id, safe='')}/heartbeat"

    def post_log(self, payload: dict[str, Any]) -> int:
        """POST one gauge report. Returns the HTTP status code (201 when stored)."""
        status, _ = self._request("POST", self.logs_url, payload)
        return status

    def heartbeat(self) -> bool:
        """Tell the server this device is alive. Returns the server's `online` verdict."""
        _, body = self._request("POST", self.heartbeat_url, None)
        data = body.get("data") if isinstance(body, dict) else None
        return bool(data.get("online")) if isinstance(data, dict) else True

    def register_device(self, name: str, lat: float, lng: float) -> str:
        """Create this site's device. Returns "created", or "exists" when it was already registered."""
        try:
            self._request("POST", self.devices_url, {"site_id": self._site_id, "name": name, "lat": lat, "lng": lng})
        except ApiError as exc:
            if exc.status == 409:
                return "exists"
            raise
        return "created"

    def _request(self, method: str, url: str, payload: Optional[dict[str, Any]]) -> tuple[int, Any]:
        headers = {"Accept": "application/json"}
        data = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload).encode("utf-8")
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                return response.status, _parse_json(response.read())
        except urllib.error.HTTPError as exc:
            raise ApiError(f"HTTP {exc.code} from {url}: {_describe_error(exc.read())}", status=exc.code) from exc
        except (urllib.error.URLError, OSError) as exc:
            raise ApiError(f"cannot reach {url}: {exc}") from exc


def _parse_json(raw: bytes) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def _describe_error(raw: bytes) -> str:
    """Prefer the envelope's error message and details over a raw body dump."""
    body = _parse_json(raw)
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict) and error.get("message"):
        details = error.get("details")
        if isinstance(details, list) and details:
            return f"{error['message']} ({'; '.join(str(d) for d in details)})"
        return str(error["message"])
    return raw.decode("utf-8", errors="replace")[:200]


def build_payload(
    site_id: str,
    inventory: Optional[InventoryReport] = None,
    status: Optional[StatusReport] = None,
    delivery: Optional[DeliveryReport] = None,
) -> dict[str, Any]:
    """Assemble one JSON-serialisable document from whichever reports were read."""
    payload: dict[str, Any] = {
        "site_id": site_id,
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }
    if inventory is not None:
        payload["inventory"] = _to_json(inventory)
    if status is not None:
        payload["status"] = _to_json(status)
    if delivery is not None:
        payload["delivery"] = _to_json(delivery)
    return payload


def _to_json(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Delivery):
        return {**_to_json(dataclasses.asdict(value)), "amount": value.amount}
    if dataclasses.is_dataclass(value):
        return {f.name: _to_json(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, dict):
        return {k: _to_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_json(v) for v in value]
    if isinstance(value, float):
        return round(value, FLOAT_DECIMALS)
    return value
