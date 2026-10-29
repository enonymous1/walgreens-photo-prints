"""Upload URL invariants and upload-image behavior (mocked PUT)."""

import pytest

from conftest import FakeResponse, FakeSession
from walgreens_photo_prints.errors import WalgreensApiError
from walgreens_photo_prints.upload import (
    build_upload_url,
    upload_image,
    upload_image_for_credentials,
)


def test_build_upload_url_happy_path():
    url = build_upload_url(
        "https://example.test/c?sig=abc&se=2030-01-01",
        "test-aff",
        image_name="Image-test-aff-fixed.jpg",
    )
    assert url == "https://example.test/c/Image-test-aff-fixed.jpg?sig=abc&se=2030-01-01"


def test_build_upload_url_generates_uuid_name():
    url = build_upload_url("https://example.test/c?sig=abc", "test-aff")
    assert url.startswith("https://example.test/c/Image-test-aff-")
    assert url.endswith(".jpg?sig=abc")


def test_build_upload_url_rejects_bad_tokens():
    with pytest.raises(ValueError, match="must contain a"):
        build_upload_url("https://example.test/c", "test-aff")
    with pytest.raises(ValueError, match="must contain a"):
        build_upload_url("https://example.test/c?", "test-aff")
    with pytest.raises(ValueError, match="exactly one"):
        build_upload_url("https://example.test/c?sig=a?sig=b", "test-aff")
    with pytest.raises(ValueError, match="sas_key_token is required"):
        build_upload_url("", "test-aff")
    with pytest.raises(ValueError, match="aff_id is required"):
        build_upload_url("https://example.test/c?sig=abc", "")


def test_upload_image_headers_and_body(tmp_path):
    image = tmp_path / "photo.jpg"
    image.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg")
    session = FakeSession([])
    status = upload_image(
        "https://example.test/c/x.jpg?sig=abc", str(image), request_id="req-1", session=session
    )
    assert status == 201
    put = session.puts[0]
    assert put["headers"]["Content-Length"] == str(len(b"\xff\xd8\xff\xe0fake-jpeg"))
    assert put["headers"]["Content-Type"] == "image/jpeg"
    assert put["headers"]["x-ms-blob-type"] == "BlockBlob"
    assert put["headers"]["x-ms-client-request-id"] == "req-1"
    assert put["body"] == b"\xff\xd8\xff\xe0fake-jpeg"


def test_upload_image_default_request_id_is_uuid():
    import uuid

    session = FakeSession([])
    import tempfile
    import os

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as handle:
        handle.write(b"data")
        path = handle.name
    try:
        upload_image("https://example.test/c/x.jpg?sig=abc", path, session=session)
    finally:
        os.unlink(path)
    uuid.UUID(session.puts[0]["headers"]["x-ms-client-request-id"])


def test_upload_image_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        upload_image("https://example.test/c/x.jpg?sig=abc", str(tmp_path / "nope.jpg"))


def test_upload_image_http_error_raises(tmp_path):
    class ErrorSession(FakeSession):
        def put(self, url, headers=None, data=None, timeout=None):
            return FakeResponse(None, status_code=403)

    image = tmp_path / "photo.jpg"
    image.write_bytes(b"data")
    with pytest.raises(WalgreensApiError) as excinfo:
        upload_image("https://example.test/c/x.jpg?sig=abc", str(image), session=ErrorSession([]))
    assert excinfo.value.status_code == 403


def test_upload_flow_fetches_credentials_once(make_client, tmp_path, monkeypatch):
    client, session = make_client(
        [FakeResponse({"cloud": [{"sasKeyToken": "https://example.test/c?sig=abc"}]})]
    )
    image = tmp_path / "photo.jpg"
    image.write_bytes(b"data")

    captured = {}

    import walgreens_photo_prints.upload as upload_mod

    real_session_class = upload_mod.requests.Session

    class CapturingSession(real_session_class):
        def put(self, url, headers=None, data=None, timeout=None):
            captured["url"] = url
            captured["headers"] = headers
            return FakeResponse(None, status_code=201)

    monkeypatch.setattr(upload_mod.requests, "Session", CapturingSession)
    url, status = upload_image_for_credentials(client, str(image))
    assert status == 201
    assert url == captured["url"]
    assert len(session.posts) == 1  # credentials fetched exactly once
    assert captured["headers"]["x-ms-blob-type"] == "BlockBlob"


def test_upload_flow_without_sas_token_raises(make_client, tmp_path):
    client, _ = make_client([FakeResponse({"cloud": []})])
    image = tmp_path / "photo.jpg"
    image.write_bytes(b"data")
    with pytest.raises(WalgreensApiError, match="no sasKeyToken"):
        upload_image_for_credentials(client, str(image))
