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
