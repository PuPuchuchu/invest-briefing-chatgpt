"""
Unified SEC EDGAR raw-data fetch layer.

Why this module exists
-----------------------
Three scripts in this repository each implemented their own, functionally
identical, copy of "GET a JSON URL from SEC EDGAR, handle gzip/deflate
Content-Encoding by hand (urllib does not auto-decompress), check the HTTP
status, and parse the body":

    - tests/test_sec_companyfacts.py       (fetch_json)
    - tests/test_sec_fact_diagnostics.py   (fetch_json)
    - tests/test_sec_fundamentals_pipeline.py (fetch_json + download_companyfacts)

This module is the single place that logic now lives. It owns exactly one
responsibility: getting raw bytes off data.sec.gov onto disk / into memory,
correctly. It intentionally does NOT know anything about XBRL concepts,
economic-priority concept selection, or normalization -- that logic already
lives in src/fundamentals/sec_normalizer.py and must not be duplicated here.

Behavioral notes carried over from the three original implementations
(preserved deliberately, not incidentally):
    - Non-200 HTTP status raises RuntimeError("HTTP status: {status}").
    - gzip / deflate Content-Encoding is decompressed explicitly.
    - Network-level failures (HTTPError, URLError, socket.timeout) are left
      to propagate unchanged -- none of the three originals caught them.

One deliberate behavioral FIX relative to the originals:
    - tests/test_sec_fundamentals_pipeline.py read `SEC_USER_AGENT` and
      raised RuntimeError at *module import time* if it was unset. That
      breaks `pytest` collection for the entire test suite (not just that
      file) whenever the env var isn't exported first -- confirmed via a
      clean `pytest -q` run in this environment, which aborts with
      "Interrupted: 1 error during collection, no tests collected" before a
      single test runs. `get_user_agent()` below performs the same check,
      but only when a caller actually calls it, never on import.
"""

from __future__ import annotations

import gzip
import json
import os
import zlib
from pathlib import Path
from urllib.request import Request, urlopen

SEC_COMPANYFACTS_BASE_URL = "https://data.sec.gov/api/xbrl/companyfacts"
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_RAW_FILENAME_TEMPLATE = "{ticker}_companyfacts.json"


class SECUserAgentNotConfigured(RuntimeError):
    """Raised by get_user_agent() when SEC_USER_AGENT is unset and no
    default was supplied. Never raised at import time."""


def get_user_agent(default: str | None = None) -> str:
    """
    Resolve the User-Agent string SEC EDGAR requires
    (https://www.sec.gov/os/webmaster-faq#developers).

    Reads SEC_USER_AGENT from the environment first; falls back to
    `default` if provided; otherwise raises. This check happens only when
    this function is called, not at module import time.
    """
    value = os.environ.get("SEC_USER_AGENT")
    if value:
        return value
    if default:
        return default
    raise SECUserAgentNotConfigured(
        "SEC_USER_AGENT environment variable is not set, and no default "
        "User-Agent was provided."
    )


def build_companyfacts_url(cik: str) -> str:
    """Build the SEC XBRL Company Facts API URL for a given CIK."""
    return f"{SEC_COMPANYFACTS_BASE_URL}/CIK{cik}.json"


def fetch_json(
    url: str,
    user_agent: str,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    verbose: bool = True,
) -> dict:
    """
    GET `url` with a compliant User-Agent / Accept-Encoding header set and
    return the parsed JSON body.

    Raises RuntimeError on a non-200 HTTP status. Explicitly decompresses
    gzip/deflate bodies (urllib does not do this automatically). Does not
    catch urllib.error.HTTPError / URLError / socket.timeout -- those
    propagate to the caller, matching all three original implementations.
    """
    request = Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate",
        },
        method="GET",
    )

    with urlopen(request, timeout=timeout) as response:
        status = response.status
        content_encoding = response.headers.get("Content-Encoding", "").lower()
        raw_data = response.read()

        if verbose:
            print(f"HTTP status: {status}")
            print(f"Content-Encoding: {content_encoding or 'none'}")
            print(f"Response bytes: {len(raw_data)}")

        if status != 200:
            raise RuntimeError(f"HTTP status: {status}")

        if content_encoding == "gzip":
            raw_data = gzip.decompress(raw_data)
        elif content_encoding == "deflate":
            raw_data = zlib.decompress(raw_data)

        return json.loads(raw_data.decode("utf-8"))


def fetch_companyfacts(
    cik: str,
    user_agent: str,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    verbose: bool = True,
) -> dict:
    """Fetch the raw XBRL Company Facts JSON for a CIK. No validation,
    no normalization -- just the fetch."""
    url = build_companyfacts_url(cik)
    return fetch_json(url, user_agent=user_agent, timeout=timeout, verbose=verbose)


def save_raw_json(path: Path, data: dict) -> Path:
    """
    Write `data` as UTF-8 JSON (indent=2, ensure_ascii=False), creating
    parent directories as needed. Matches the write pattern that was
    duplicated across the legacy scripts. Returns the path written.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def fetch_and_cache_companyfacts(
    ticker: str,
    cik: str,
    raw_dir: Path,
    user_agent: str,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    filename_template: str = DEFAULT_RAW_FILENAME_TEMPLATE,
    required_keys: tuple[str, ...] = ("cik", "entityName", "facts"),
    verbose: bool = True,
) -> tuple[dict, Path]:
    """
    Fetch a company's raw XBRL Company Facts JSON from SEC EDGAR, check
    that the required top-level keys are present, and write it to
    `raw_dir`. This is the fetch -> validate-keys -> save sequence shared
    by tests/test_sec_companyfacts.py, tests/test_sec_fact_diagnostics.py
    and tests/test_sec_fundamentals_pipeline.py.

    Returns (data, path_written). Deliberately does NOT perform XBRL-level
    validation or normalization -- callers needing that continue to use
    src/fundamentals/sec_normalizer.py.
    """
    data = fetch_companyfacts(cik, user_agent=user_agent, timeout=timeout, verbose=verbose)

    for key in required_keys:
        if key not in data:
            raise ValueError(f"{ticker}: missing required key '{key}' in SEC response")

    raw_path = Path(raw_dir) / filename_template.format(ticker=ticker)
    save_raw_json(raw_path, data)

    if verbose:
        print(f"[PASS] Raw cache written: {raw_path}")

    return data, raw_path
