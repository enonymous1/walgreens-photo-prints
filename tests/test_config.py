"""Config tests: env vars, dotenv files, validation, no key in repr."""

import pytest

from walgreens_photo_prints.config import Config, ConfigError


def test_from_env_reads_variables(monkeypatch):
    monkeypatch.setenv("WALGREENS_API_KEY", "key-123")
    monkeypatch.setenv("WALGREENS_AFF_ID", "aff-123")
    monkeypatch.setenv("WALGREENS_BASE_URL", "https://services.walgreens.com/")
    monkeypatch.setenv("WALGREENS_TIMEOUT", "12")
    config = Config.from_env()
    assert config.api_key == "key-123"
    assert config.aff_id == "aff-123"
    assert config.base_url == "https://services.walgreens.com"
    assert config.timeout == 12.0
    assert not config.is_sandbox


def test_from_env_defaults_to_sandbox(monkeypatch):
    monkeypatch.setenv("WALGREENS_API_KEY", "k")
    monkeypatch.setenv("WALGREENS_AFF_ID", "a")
    monkeypatch.delenv("WALGREENS_BASE_URL", raising=False)
    assert Config.from_env().is_sandbox


def test_from_env_missing_key_raises(monkeypatch):
    monkeypatch.delenv("WALGREENS_API_KEY", raising=False)
    monkeypatch.setenv("WALGREENS_AFF_ID", "a")
    with pytest.raises(ConfigError):
        Config.from_env()


def test_from_env_missing_aff_id_raises(monkeypatch):
    monkeypatch.setenv("WALGREENS_API_KEY", "k")
    monkeypatch.delenv("WALGREENS_AFF_ID", raising=False)
    with pytest.raises(ConfigError):
        Config.from_env()


def test_from_env_bad_timeout_raises(monkeypatch):
    monkeypatch.setenv("WALGREENS_API_KEY", "k")
    monkeypatch.setenv("WALGREENS_AFF_ID", "a")
    monkeypatch.setenv("WALGREENS_TIMEOUT", "soon")
    with pytest.raises(ConfigError):
        Config.from_env()


def test_http_base_url_rejected():
    with pytest.raises(ConfigError):
        Config(api_key="k", aff_id="a", base_url="http://example.com")


def test_dotenv_file_is_loaded(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "WALGREENS_API_KEY=dotenv-key\nWALGREENS_AFF_ID=dotenv-aff\n", encoding="utf-8"
    )
    monkeypatch.delenv("WALGREENS_API_KEY", raising=False)
    monkeypatch.delenv("WALGREENS_AFF_ID", raising=False)
    config = Config.from_env(env_file=str(env_file))
    assert config.api_key == "dotenv-key"
    assert config.aff_id == "dotenv-aff"


def test_dotenv_does_not_override_real_environment(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("WALGREENS_API_KEY=dotenv-key\n", encoding="utf-8")
    monkeypatch.setenv("WALGREENS_API_KEY", "real-key")
    monkeypatch.setenv("WALGREENS_AFF_ID", "a")
    assert Config.from_env(env_file=str(env_file)).api_key == "real-key"


def test_api_key_not_in_repr():
    config = Config(api_key="super-secret-key", aff_id="a")
    assert "super-secret-key" not in repr(config)
