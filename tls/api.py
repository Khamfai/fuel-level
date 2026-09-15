"""Push parsed reports to a REST endpoint as JSON (standard library only)."""

from __future__ import annotations

import dataclasses
import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Optional

from tls.protocol import Delivery, DeliveryReport, InventoryReport, StatusReport

DEFAULT_TIMEOUT_S = 10.0
FLOAT_DECIMALS = 3  # gauge floats are single precision; more digits is noise


class ApiError(Exception):
    """The server rejected the request or could not be reached."""


class ApiClient:
    def __init__(self, url: str, api_key: Optional[str] = None, timeout: float = DEFAULT_TIMEOUT_S):
        self._url = url
        self._api_key = api_key
        self._timeout = timeout

    def post(self, payload: dict[str, Any]) -> int:
        """POST the payload as JSON. Returns the HTTP status code."""
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        request = urllib.request.Request(
            self._url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                return response.status
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:200]
            raise ApiError(f"HTTP {exc.code} from {self._url}: {body}") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise ApiError(f"cannot reach {self._url}: {exc}") from exc


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
