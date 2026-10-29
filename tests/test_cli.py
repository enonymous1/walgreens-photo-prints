"""CLI tests: mocked client, submit gating, dotenv and flag overrides."""

import json

import pytest

import walgreens_photo_prints.cli as cli_mod
from conftest import FakeResponse, FakeSession
from walgreens_photo_prints.cli import main
from walgreens_photo_prints.client import WalgreensClient
from walgreens_photo_prints.config import Config


def _set_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("WALGREENS_API_KEY", "test-key")
    monkeypatch.setenv("WALGREENS_AFF_ID", "test-aff")
    monkeypatch.delenv("WALGREENS_APP_VER", raising=False)
    monkeypatch.delenv("WALGREENS_DEV_INF", raising=False)


def _patch_client(monkeypatch, session):
    def factory(config):
        assert isinstance(config, Config)
        return WalgreensClient(config, session=session)

    monkeypatch.setattr(cli_mod, "WalgreensClient", factory)


def test_cli_creds_redacts_token(monkeypatch, tmp_path, capsys):
    _set_env(monkeypatch, tmp_path)
    session = FakeSession(
        [
            FakeResponse(
                {
                    "uploadLimit": 5,
                    "template": "default",
                    "cloud": [{"sasKeyToken": "https://example.test/c?sig=SECRET"}],
                }
            )
        ]
    )
    _patch_client(monkeypatch, session)
    assert main(["creds"]) == 0
    out = capsys.readouterr().out
    assert "SECRET" not in out
    assert '"cloud_entries": 1' in out


def test_cli_products_json(monkeypatch, tmp_path, capsys):
    _set_env(monkeypatch, tmp_path)
    session = FakeSession(
        [
            FakeResponse(
                {"products": [{"productId": "1", "productDesc": "4x6", "productPrice": "0.10"}]}
            )
        ]
    )
    _patch_client(monkeypatch, session)
    assert main(["products"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data[0]["product_id"] == "1"


def test_cli_missing_credentials_exits_1(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("WALGREENS_API_KEY", raising=False)
    monkeypatch.delenv("WALGREENS_AFF_ID", raising=False)
    assert main(["creds"]) == 1
    assert "error" in capsys.readouterr().err


def test_cli_flag_overrides_env(monkeypatch, tmp_path, capsys):
    _set_env(monkeypatch, tmp_path)
    session = FakeSession([FakeResponse({"products": []})])
    _patch_client(monkeypatch, session)
    assert main(["products", "--api-key", "flag-key", "--aff-id", "flag-aff"]) == 0
    assert session.posts[0]["json"]["apiKey"] == "flag-key"


def test_cli_dotenv_file(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("WALGREENS_API_KEY", raising=False)
    monkeypatch.delenv("WALGREENS_AFF_ID", raising=False)
    env_file = tmp_path / "test.env"
    env_file.write_text(
        "WALGREENS_API_KEY=dotenv-key\nWALGREENS_AFF_ID=dotenv-aff\n", encoding="utf-8"
    )
    session = FakeSession([FakeResponse({"products": []})])
    _patch_client(monkeypatch, session)
    assert main(["products", "--env-file", str(env_file)]) == 0
    assert session.posts[0]["json"]["apiKey"] == "dotenv-key"


def test_cli_submit_without_confirm_prints_redacted_payload_and_sends_nothing(
    monkeypatch, tmp_path, capsys
):
    _set_env(monkeypatch, tmp_path)
    session = FakeSession([])
    _patch_client(monkeypatch, session)
    details = tmp_path / "order.json"
    details.write_text(
        json.dumps(
            [
                {
                    "productId": "1",
                    "imageDetails": [{"url": "https://example.test/x.jpg", "qty": "1"}],
                }
            ]
        ),
        encoding="utf-8",
    )
    code = main(
        [
            "submit",
            "--first-name",
            "A",
            "--last-name",
            "B",
            "--phone",
            "5555555555",
            "--email",
            "a@example.test",
            "--store-num",
            "211",
            "--promise-time",
            "03-02-2020 5:15 PM",
            "--product-details",
            str(details),
        ]
    )
    assert code == 2
    out = capsys.readouterr().out
    assert "test-key" not in out
    assert '"apiKey": "***"' in out
    assert session.posts == []


def test_cli_submit_with_confirm_sends_order(monkeypatch, tmp_path, capsys):
    _set_env(monkeypatch, tmp_path)
    session = FakeSession([FakeResponse({"vendorOrderId": "9", "status": "success"})])
    _patch_client(monkeypatch, session)
    details = tmp_path / "order.json"
    details.write_text(
        json.dumps(
            [
                {
                    "productId": "1",
                    "imageDetails": [{"url": "https://example.test/x.jpg", "qty": "1"}],
                }
            ]
        ),
        encoding="utf-8",
    )
    code = main(
        [
            "submit",
            "--first-name",
            "A",
            "--last-name",
            "B",
            "--phone",
            "5555555555",
            "--email",
            "a@example.test",
            "--store-num",
            "211",
            "--promise-time",
            "03-02-2020 5:15 PM",
            "--product-details",
            str(details),
            "--confirm",
            "--accept-terms",
        ]
    )
    assert code == 0
    assert len(session.posts) == 1
    assert json.loads(capsys.readouterr().out)["vendor_order_id"] == "9"


def test_cli_submit_confirm_without_accept_terms_exits_2(monkeypatch, tmp_path, capsys):
    _set_env(monkeypatch, tmp_path)
    session = FakeSession([])
    _patch_client(monkeypatch, session)
    details = tmp_path / "order.json"
    details.write_text(
        json.dumps(
            [
                {
                    "productId": "1",
                    "imageDetails": [{"url": "https://example.test/x.jpg", "qty": "1"}],
                }
            ]
        ),
        encoding="utf-8",
    )
    code = main(
        [
            "submit",
            "--first-name",
            "A",
            "--last-name",
            "B",
            "--phone",
            "5555555555",
            "--email",
            "a@example.test",
            "--store-num",
            "211",
            "--promise-time",
            "03-02-2020 5:15 PM",
            "--product-details",
            str(details),
            "--confirm",
        ]
    )
    assert code == 2
    assert session.posts == []


def test_cli_version(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    assert "1.0.0" in capsys.readouterr().out


def test_cli_bad_product_details_file(monkeypatch, tmp_path, capsys):
    _set_env(monkeypatch, tmp_path)
    session = FakeSession([])
    _patch_client(monkeypatch, session)
    assert main(["coupon", "--code", "X", "--product-details", str(tmp_path / "missing.json")]) == 1
    assert session.posts == []
