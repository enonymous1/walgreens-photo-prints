"""Web front-end tests, all in demo mode (fictional data, no network).

Flask is an optional ``[web]`` extra, so these tests skip (rather
than error) on a library-only install. CI installs ``.[dev,web]``,
so they run there; see README Local Development.
"""

import io
import re

import pytest

pytest.importorskip("flask")

from walgreens_photo_prints.demo import SAMPLE_ORDER_JSON
from walgreens_photo_prints.webapp import create_app


@pytest.fixture
def demo_client():
    app = create_app(demo=True, secret_key="test-secret")
    app.config["TESTING"] = True
    return app.test_client()


def _csrf(html):
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match, "CSRF token missing from form"
    return match.group(1)


def test_index_and_products_demo(demo_client):
    assert demo_client.get("/").status_code == 200
    html = demo_client.get("/products").get_data(as_text=True)
    assert "Demo 4x6 Print" in html
    assert "Demo mode" in html


def test_stores_demo_shows_no_promise_warning(demo_client):
    html = demo_client.get("/stores").get_data(as_text=True)
    assert "Demo Walgreens" in html
    assert "cannot promise a pickup time" in html


def test_coupon_and_status_demo(demo_client):
    html = demo_client.get("/coupon").get_data(as_text=True)
    assert "DEMO10" in html
    assert "8.0" in html  # 10.00 total - 2.00 discount
    html = demo_client.get("/status").get_data(as_text=True)
    assert "DEMO-0001" in html
    assert "Ready for Pickup" in html


def test_upload_demo_discards_file_and_shows_fictional_url(demo_client):
    html = demo_client.get("/upload").get_data(as_text=True)
    token = _csrf(html)
    response = demo_client.post(
        "/upload",
        data={"csrf_token": token, "image": (io.BytesIO(b"fake-image"), "photo.jpg")},
        content_type="multipart/form-data",
    )
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "https://example.test/blob/photo.jpg?sig=DEMO" in html
    assert "Demo mode" in html


def test_submit_preview_redacts_and_confirm_returns_demo_order(demo_client):
    html = demo_client.get("/submit").get_data(as_text=True)
    token = _csrf(html)
    form = {
        "csrf_token": token,
        "first_name": "Jane",
        "last_name": "Doe",
        "phone": "5555555555",
        "email": "jane@example.test",
        "store_num": "211",
        "promise_time": "03-02-2020 5:15 PM",
        "coupon_code": "",
        "publisher_id": "",
        "aff_notes": "",
        "product_details": SAMPLE_ORDER_JSON,
    }
    preview = demo_client.post("/submit", data=form)
    html = preview.get_data(as_text=True)
    assert "nothing has been submitted yet" in html
    assert '"apiKey": "***"' in html
    assert "demo-api-key" not in html
    # Confirming without the terms checkbox must not submit.
    confirm_form = {**form, "csrf_token": _csrf(html), "confirm": "1"}
    preview2 = demo_client.post("/submit", data=confirm_form)
    assert "nothing has been submitted yet" in preview2.get_data(as_text=True)
    # Both boxes checked: demo order, no real order.
    confirm_form["accept_terms"] = "1"
    result = demo_client.post("/submit", data=confirm_form)
    html = result.get_data(as_text=True)
    assert "DEMO-0001" in html
    assert "fictional order" in html


def test_post_without_csrf_is_rejected(demo_client):
    response = demo_client.post("/products", data={"product_group_id": ""}, follow_redirects=False)
    assert response.status_code == 400
    assert "CSRF" in response.get_data(as_text=True)


def test_invalid_json_shows_error_page(demo_client):
    html = demo_client.get("/coupon").get_data(as_text=True)
    response = demo_client.post(
        "/coupon",
        data={"csrf_token": _csrf(html), "code": "X", "product_details": "not json"},
    )
    assert response.status_code == 400
    assert "Invalid JSON" in response.get_data(as_text=True)
