"""Tests for config.py — ETF loader and constants."""

from pathlib import Path

import pytest

import config
from config import load_etfs


def test_load_etfs_valid_csv(sample_etf_csv):
    result = load_etfs(sample_etf_csv)
    assert result == ["SPY", "QQQ", "DIA"]


def test_load_etfs_skips_blank(tmp_path):
    csv = tmp_path / "etfs.csv"
    csv.write_text("Symbol,Description\nSPY,S&P 500\n,blank row\nDIA,Dow Jones\n")
    result = load_etfs(csv)
    assert result == ["SPY", "DIA"]


def test_load_etfs_strips_whitespace(tmp_path):
    csv = tmp_path / "etfs.csv"
    csv.write_text("Symbol,Description\n  SPY  ,S&P 500\n QQQ ,Nasdaq\n")
    result = load_etfs(csv)
    assert result == ["SPY", "QQQ"]


def test_load_etfs_file_not_found():
    with pytest.raises(FileNotFoundError):
        load_etfs(Path("/nonexistent/path/ETFs.csv"))


def test_constants():
    assert config.TRADE_RATE == 165.0
    assert config.NLV_BASE == 10_000.0
    assert config.MIN_TRADE_SIZE == 5.00


def test_sandbox_true():
    assert config.SANDBOX is True


# --- validate_credentials ---


def test_validate_credentials_valid(monkeypatch):
    monkeypatch.setattr(config, "TASTYTRADE_PROVIDER_SECRET", "real_secret_abc123")
    monkeypatch.setattr(config, "TASTYTRADE_REFRESH_TOKEN", "real_token_xyz789")
    config.validate_credentials()  # Should not raise


def test_validate_credentials_empty_secret(monkeypatch):
    monkeypatch.setattr(config, "TASTYTRADE_PROVIDER_SECRET", "")
    monkeypatch.setattr(config, "TASTYTRADE_REFRESH_TOKEN", "real_token_xyz789")
    with pytest.raises(SystemExit, match="PROVIDER_SECRET"):
        config.validate_credentials()


def test_validate_credentials_empty_token(monkeypatch):
    monkeypatch.setattr(config, "TASTYTRADE_PROVIDER_SECRET", "real_secret_abc123")
    monkeypatch.setattr(config, "TASTYTRADE_REFRESH_TOKEN", "")
    with pytest.raises(SystemExit, match="REFRESH_TOKEN"):
        config.validate_credentials()


def test_validate_credentials_both_empty(monkeypatch):
    monkeypatch.setattr(config, "TASTYTRADE_PROVIDER_SECRET", "")
    monkeypatch.setattr(config, "TASTYTRADE_REFRESH_TOKEN", "")
    with pytest.raises(SystemExit, match="PROVIDER_SECRET"):
        config.validate_credentials()


def test_validate_credentials_placeholder_secret(monkeypatch):
    monkeypatch.setattr(config, "TASTYTRADE_PROVIDER_SECRET", "your_oauth_client_secret")
    monkeypatch.setattr(config, "TASTYTRADE_REFRESH_TOKEN", "real_token_xyz789")
    with pytest.raises(SystemExit, match="placeholder"):
        config.validate_credentials()


def test_validate_credentials_placeholder_token(monkeypatch):
    monkeypatch.setattr(config, "TASTYTRADE_PROVIDER_SECRET", "real_secret_abc123")
    monkeypatch.setattr(config, "TASTYTRADE_REFRESH_TOKEN", "your_refresh_token")
    with pytest.raises(SystemExit, match="placeholder"):
        config.validate_credentials()
