"""
Unit tests for src/sec/fetcher.py.

These are pure Unit Tests in the taxonomy sense: no network access, no
real SEC data. HTTP responses are mocked via unittest.mock.patch on
urllib.request.urlopen. Anything requiring a real SEC EDGAR round trip
belongs in an Integration Test elsewhere, not here.
"""

import gzip
import json
import zlib
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from src.sec.fetcher import (
    DEFAULT_RAW_FILENAME_TEMPLATE,
    SECUserAgentNotConfigured,
    build_companyfacts_url,
    fetch_and_cache_companyfacts,
    fetch_companyfacts,
    fetch_json,
    get_user_agent,
    save_raw_json,
)


# ============================================================
# Fake urlopen response helper
# ============================================================

class _FakeResponse:
    """Minimal stand-in for the object urlopen() returns, supporting the
    subset of the interface fetch_json() actually uses (status, headers,
    read, and the context-manager protocol)."""

    def __init__(self, body_bytes: bytes, status: int = 200, content_encoding: str = ""):
        self._body = body_bytes
        self.status = status
        self._headers = {}
        if content_encoding:
            self._headers["Content-Encoding"] = content_encoding

    @property
    def headers(self):
        mock_headers = MagicMock()
        mock_headers.get = lambda key, default="": self._headers.get(key, default)
        return mock_headers

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


# ============================================================
# build_companyfacts_url
# ============================================================

def test_build_companyfacts_url():
    url = build_companyfacts_url("0000789019")
    assert url == "https://data.sec.gov/api/xbrl/companyfacts/CIK0000789019.json"


# ============================================================
# get_user_agent
# ============================================================

def test_get_user_agent_from_env(monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "test-agent/1.0 test@example.com")
    assert get_user_agent() == "test-agent/1.0 test@example.com"


def test_get_user_agent_falls_back_to_default(monkeypatch):
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    assert get_user_agent(default="fallback-agent/1.0") == "fallback-agent/1.0"


def test_get_user_agent_env_takes_priority_over_default(monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "from-env/1.0")
    assert get_user_agent(default="fallback/1.0") == "from-env/1.0"


def test_get_user_agent_raises_when_unset_and_no_default(monkeypatch):
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    with pytest.raises(SECUserAgentNotConfigured):
        get_user_agent()


def test_get_user_agent_does_not_raise_at_import_time(monkeypatch):
    """Regression test for the collection-breaking bug in the legacy
    tests/test_sec_fundamentals_pipeline.py, which raised at module import
    time if SEC_USER_AGENT was unset -- aborting pytest collection for the
    ENTIRE suite, not just that file. Importing this fetcher module must
    never raise regardless of env state."""
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    import importlib
    import src.sec.fetcher as fetcher_module
    importlib.reload(fetcher_module)  # must not raise


# ============================================================
# fetch_json
# ============================================================

def test_fetch_json_plain_response():
    payload = {"cik": "789019", "entityName": "MICROSOFT CORP", "facts": {}}
    body = json.dumps(payload).encode("utf-8")

    with patch("src.sec.fetcher.urlopen", return_value=_FakeResponse(body, status=200)):
        result = fetch_json("https://data.sec.gov/fake", user_agent="ua/1.0", verbose=False)

    assert result == payload


def test_fetch_json_gzip_response():
    payload = {"cik": "320193", "entityName": "APPLE INC", "facts": {}}
    body = gzip.compress(json.dumps(payload).encode("utf-8"))

    with patch(
        "src.sec.fetcher.urlopen",
        return_value=_FakeResponse(body, status=200, content_encoding="gzip"),
    ):
        result = fetch_json("https://data.sec.gov/fake", user_agent="ua/1.0", verbose=False)

    assert result == payload


def test_fetch_json_deflate_response():
    payload = {"cik": "1045810", "entityName": "NVIDIA CORP", "facts": {}}
    body = zlib.compress(json.dumps(payload).encode("utf-8"))

    with patch(
        "src.sec.fetcher.urlopen",
        return_value=_FakeResponse(body, status=200, content_encoding="deflate"),
    ):
        result = fetch_json("https://data.sec.gov/fake", user_agent="ua/1.0", verbose=False)

    assert result == payload


def test_fetch_json_raises_on_non_200_status():
    body = b"{}"
    with patch("src.sec.fetcher.urlopen", return_value=_FakeResponse(body, status=500)):
        with pytest.raises(RuntimeError, match="HTTP status: 500"):
            fetch_json("https://data.sec.gov/fake", user_agent="ua/1.0", verbose=False)


def test_fetch_json_sets_required_headers():
    payload = {"ok": True}
    body = json.dumps(payload).encode("utf-8")
    captured_request = {}

    def fake_urlopen(request, timeout=None):
        captured_request["headers"] = dict(request.headers)
        captured_request["timeout"] = timeout
        return _FakeResponse(body, status=200)

    with patch("src.sec.fetcher.urlopen", side_effect=fake_urlopen):
        fetch_json("https://data.sec.gov/fake", user_agent="my-agent/2.0", timeout=15, verbose=False)

    # urllib title-cases header keys internally
    assert captured_request["headers"]["User-agent"] == "my-agent/2.0"
    assert captured_request["headers"]["Accept-encoding"] == "gzip, deflate"
    assert captured_request["timeout"] == 15


# ============================================================
# fetch_companyfacts
# ============================================================

def test_fetch_companyfacts_builds_correct_url():
    payload = {"cik": "789019", "entityName": "MICROSOFT CORP", "facts": {}}
    body = json.dumps(payload).encode("utf-8")
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        return _FakeResponse(body, status=200)

    with patch("src.sec.fetcher.urlopen", side_effect=fake_urlopen):
        result = fetch_companyfacts("0000789019", user_agent="ua/1.0", verbose=False)

    assert captured["url"] == "https://data.sec.gov/api/xbrl/companyfacts/CIK0000789019.json"
    assert result == payload


# ============================================================
# save_raw_json
# ============================================================

def test_save_raw_json_writes_file_and_creates_parents(tmp_path):
    target = tmp_path / "nested" / "dir" / "MSFT_companyfacts.json"
    data = {"cik": "789019", "entityName": "MICROSOFT CORP", "facts": {"us-gaap": {}}}

    returned_path = save_raw_json(target, data)

    assert returned_path == target
    assert target.exists()
    with target.open("r", encoding="utf-8") as f:
        loaded = json.load(f)
    assert loaded == data


# ============================================================
# fetch_and_cache_companyfacts
# ============================================================

def test_fetch_and_cache_companyfacts_happy_path(tmp_path):
    payload = {"cik": "789019", "entityName": "MICROSOFT CORP", "facts": {}}
    body = json.dumps(payload).encode("utf-8")

    with patch("src.sec.fetcher.urlopen", return_value=_FakeResponse(body, status=200)):
        data, path_written = fetch_and_cache_companyfacts(
            ticker="MSFT",
            cik="0000789019",
            raw_dir=tmp_path,
            user_agent="ua/1.0",
            verbose=False,
        )

    assert data == payload
    assert path_written == tmp_path / "MSFT_companyfacts.json"
    assert path_written.exists()


def test_fetch_and_cache_companyfacts_custom_filename_template(tmp_path):
    payload = {"cik": "1045810", "entityName": "NVIDIA CORP", "facts": {}}
    body = json.dumps(payload).encode("utf-8")

    with patch("src.sec.fetcher.urlopen", return_value=_FakeResponse(body, status=200)):
        _, path_written = fetch_and_cache_companyfacts(
            ticker="NVDA",
            cik="0001045810",
            raw_dir=tmp_path,
            user_agent="ua/1.0",
            filename_template="{ticker}_companyfacts_diagnostic.json",
            verbose=False,
        )

    assert path_written == tmp_path / "NVDA_companyfacts_diagnostic.json"


def test_fetch_and_cache_companyfacts_raises_on_missing_required_key(tmp_path):
    # Missing "facts" key entirely.
    payload = {"cik": "789019", "entityName": "MICROSOFT CORP"}
    body = json.dumps(payload).encode("utf-8")

    with patch("src.sec.fetcher.urlopen", return_value=_FakeResponse(body, status=200)):
        with pytest.raises(ValueError, match="missing required key 'facts'"):
            fetch_and_cache_companyfacts(
                ticker="MSFT",
                cik="0000789019",
                raw_dir=tmp_path,
                user_agent="ua/1.0",
                verbose=False,
            )

    # No file should have been written when validation fails.
    assert not (tmp_path / "MSFT_companyfacts.json").exists()


def test_default_raw_filename_template_matches_legacy_pattern():
    assert DEFAULT_RAW_FILENAME_TEMPLATE.format(ticker="AAPL") == "AAPL_companyfacts.json"
