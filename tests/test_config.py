import pytest

from lyceum.config import PAPER_TRADING_URL, ConfigurationError, Settings, load_settings
from lyceum.models import ExecutionMode


def test_defaults_are_read_only_paper(monkeypatch, tmp_path):
    monkeypatch.delenv("LYCEUM_EXECUTION_MODE", raising=False)
    monkeypatch.delenv("ALPACA_PAPER", raising=False)
    settings = load_settings(tmp_path / "missing")
    assert settings.paper and settings.execution_mode is ExecutionMode.READ_ONLY
    assert settings.trading_base_url == PAPER_TRADING_URL


def test_live_endpoint_rejected():
    with pytest.raises(ValueError, match="only permits"):
        Settings(trading_base_url="https://api.alpaca.markets")


def test_autonomous_requires_second_flag():
    with pytest.raises(ValueError, match="requires"):
        Settings(execution_mode=ExecutionMode.PAPER_AUTONOMOUS)


def test_false_paper_environment_rejected(monkeypatch, tmp_path):
    monkeypatch.setenv("ALPACA_PAPER", "false")
    with pytest.raises(ConfigurationError, match="no live mode"):
        load_settings(tmp_path / "missing")
