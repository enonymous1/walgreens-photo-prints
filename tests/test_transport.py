"""Stage 3 tests: transport boundary, typed inputs, endpoints.

All Walgreens-side responses are mocked; the local HTTP-server
test exercises only the transport against a real ``requests``
session on localhost, because Config intentionally requires HTTPS.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from conftest import FakeResponse, FakeSession
from walgreens_photo_prints.client import (
    API_VERSION,
    DOCUMENTED_RATE_LIMITS_PER_MINUTE,
    ENDPOINTS,
    RATE_LIMITS_PER_MINUTE,
    WalgreensClient,
)
from walgreens_photo_prints.models import ProductQty
from walgreens_photo_prints.transport import RequestsTransport


class RecordingTransport:
    def __init__(self, responses):
        self._responses = list(responses)
        self.posts = []
        self.closed = False

    def post(self, url, headers, json, timeout):
        self.posts.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return self._responses.pop(0)

    def close(self):
        self.closed = True


def test_client_accepts_transport_and_closes_it(config):
    transport = RecordingTransport([FakeResponse({"products": []})])
    with WalgreensClient(config, transport=transport) as client:
        client.list_products()
    assert transport.closed
    assert transport.posts[0]["headers"]["User-Agent"].startswith("walgreens-photo-prints/")
    assert transport.posts[0]["url"].endswith(ENDPOINTS["products"])


def test_transport_takes_precedence_over_session(config):
    transport = RecordingTransport([FakeResponse({"products": []})])
    session = FakeSession([])
    client = WalgreensClient(config, session=session, transport=transport)
    client.list_products()
    assert transport.posts and session.posts == []


def test_requests_transport_wraps_session_without_closing_it():
    session = FakeSession([FakeResponse({"products": []})])
    transport = RequestsTransport(session)
    transport.post("https://example.test/api", headers={}, json={}, timeout=30)
    transport.close()
    assert session.posts and not session.closed


def test_product_qty_inputs_accepted(make_client):
    client, session = make_client(
        [FakeResponse({"status": "success", "orderTotalPrice": 1.0, "orderDiscountPrice": 0.0})]
    )
    result = client.validate_coupon("X", [ProductQty("1", "2")])
    assert session.posts[0]["json"]["productDetails"] == [{"productId": "1", "qty": "2"}]
    assert result.status == "success"


def test_product_qty_requires_product_id():
    with pytest.raises(ValueError):
        ProductQty("", "1")


def test_endpoints_built_from_single_version():
    assert API_VERSION == "v3"
    assert set(ENDPOINTS) == {"creds", "products", "coupon", "stores", "submit", "status"}
    assert all(path.endswith(f"/{API_VERSION}") for path in ENDPOINTS.values())
    assert ENDPOINTS["creds"] == "/api/photo/creds/v3"


def test_rate_limit_rename_keeps_alias():
    assert DOCUMENTED_RATE_LIMITS_PER_MINUTE["coupon"] == 100
    assert RATE_LIMITS_PER_MINUTE is DOCUMENTED_RATE_LIMITS_PER_MINUTE


def test_requests_transport_against_local_http_server():
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            assert json.loads(body)["ping"] == "pong"
            payload = json.dumps({"status": "ok"}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):  # keep test output clean
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/api"
        response = RequestsTransport().post(
            url, headers={"Content-Type": "application/json"}, json={"ping": "pong"}, timeout=5
        )
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
    finally:
        server.shutdown()
        server.server_close()
