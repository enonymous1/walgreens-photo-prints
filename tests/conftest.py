"""Shared fixtures for mocked (never live) Walgreens API tests."""

import pytest

from walgreens_photo_prints.client import WalgreensClient
from walgreens_photo_prints.config import Config


class FakeResponse:
    def __init__(self, json_data=None, status_code=200, headers=None, json_error=False, text=""):
        self._json_data = json_data
        self.status_code = status_code
        self.headers = headers or {}
        self._json_error = json_error
        self.text = text

    def json(self):
        if self._json_error:
            raise ValueError("No JSON object could be decoded")
        return self._json_data


class FakeSession:
    """Records requests and returns scripted responses."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.posts = []
        self.puts = []
        self.closed = False

    def post(self, url, headers=None, json=None, timeout=None):
        self.posts.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        if not self.responses:
            raise AssertionError("Unexpected POST: no scripted response left")
        return self.responses.pop(0)

    def put(self, url, headers=None, data=None, timeout=None):
        body = data.read() if hasattr(data, "read") else data
        self.puts.append({"url": url, "headers": headers, "body": body, "timeout": timeout})
        return FakeResponse({"ok": True}, status_code=201)

    def close(self):
        self.closed = True


@pytest.fixture
def config():
    return Config(
        api_key="test-api-key",
        aff_id="test-aff",
        app_ver="1.0",
        dev_inf="TestDevice,1.0",
    )


@pytest.fixture
def make_client(config):
    def _make(responses):
        session = FakeSession(responses)
        client = WalgreensClient(config, session=session)
        return client, session

    return _make
