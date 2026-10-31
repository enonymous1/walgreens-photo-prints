"""Freeze tests: demo-only output, disabled forms, no secrets.

Flask is an optional ``[web]`` extra, so these tests skip (rather
than error) on a library-only install. CI installs ``.[dev,web]``,
so they run there; see README Local Development.
"""

import sys
from pathlib import Path

import pytest

pytest.importorskip("flask")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from freeze import build_freeze


def test_freeze_builds_all_pages_with_banner_and_disabled_forms(tmp_path, monkeypatch):
    monkeypatch.setenv("WALGREENS_API_KEY", "real-secret-should-not-appear")
    monkeypatch.setenv("WALGREENS_AFF_ID", "real-aff-should-not-appear")
    out = tmp_path / "freeze-site"
    written = build_freeze(out)
    expected = {
        "index.html",
        "products.html",
        "stores.html",
        "coupon.html",
        "upload.html",
        "submit.html",
        "status.html",
        "static/style.css",
        ".nojekyll",
    }
    assert set(written) == expected
    products = (out / "products.html").read_text(encoding="utf-8")
    assert "Demo 4x6 Print" in products
    assert "Static demo" in products
    assert "disabled" in products
    assert 'href="stores.html"' in products
    assert 'href="static/style.css"' in products
    assert "real-secret-should-not-appear" not in products
    assert "real-aff-should-not-appear" not in products
    for name in expected - {"static/style.css", ".nojekyll"}:
        text = (out / name).read_text(encoding="utf-8")
        assert "Static demo" in text
        assert "real-secret-should-not-appear" not in text
        # No absolute Flask paths may survive: Pages serves a subpath.
        assert 'href="/' not in text
        assert 'action="/' not in text


def test_freeze_submit_page_is_prefilled_not_submitted(tmp_path):
    out = tmp_path / "freeze-site"
    build_freeze(out)
    submit = (out / "submit.html").read_text(encoding="utf-8")
    assert "8420005" in submit
    assert "nothing has been submitted yet" not in submit
    assert "DEMO-0001" not in submit
