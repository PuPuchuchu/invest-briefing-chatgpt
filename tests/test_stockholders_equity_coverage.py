import json
from pathlib import Path

import pytest

from src.fundamentals.sec_normalizer import normalize_company


RAW_DIR = Path("data/raw/sec")

TARGET_TICKERS = [
    "MSFT", "AAPL", "NVDA", "AVGO", "INTC", "MU",
    "AMD", "PLTR", "ORCL", "SMCI", "CRWV",
]


# ============================================================
# ALLOWED SEC CONCEPTS
# ============================================================

ALLOWED_STOCKHOLDERS_EQUITY_CONCEPTS = {
    "StockholdersEquity",
    "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
}


# ============================================================
# HELPERS
# ============================================================

def load_companyfacts(ticker: str) -> dict:
    path = RAW_DIR / f"{ticker}_companyfacts.json"

    if not path.exists():
        raise FileNotFoundError(
            f"SEC raw file not found: {path}"
        )

    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def normalize_target(ticker: str) -> dict:
    return normalize_company(
        ticker=ticker,
        data=load_companyfacts(ticker),
        company_type="NON_FINANCIAL",
    )


# ============================================================
# TEST: REAL COMPANY SEC COVERAGE
# ============================================================

@pytest.mark.parametrize("ticker", TARGET_TICKERS)
def test_stockholders_equity_real_company(ticker):
    """
    Verify real SEC CompanyFacts coverage for StockholdersEquity.

    This test validates:
    - Successful extraction
    - Numeric value
    - Period end
    - Filing date
    - SEC namespace
    - Accepted SEC Concept provenance

    This tests extraction/provenance,
    not valuation quality.
    """

    try:
        normalized = normalize_target(ticker)

    except FileNotFoundError as exc:
        pytest.fail(str(exc))

    metric = normalized["metrics"]["stockholders_equity"]

    assert metric["status"] == "OK", (
        f"{ticker}: status={metric.get('status')}, "
        f"reason={metric.get('reason')}"
    )

    assert isinstance(metric.get("value"), (int, float)), (
        f"{ticker}: non-numeric value={metric.get('value')!r}"
    )

    assert metric.get("period_end"), (
        f"{ticker}: missing period_end"
    )

    assert metric.get("filing_date"), (
        f"{ticker}: missing filing_date"
    )

    assert metric.get("namespace") == "us-gaap", (
        f"{ticker}: namespace={metric.get('namespace')}"
    )

    assert metric.get("concept") in (
        ALLOWED_STOCKHOLDERS_EQUITY_CONCEPTS
    ), (
        f"{ticker}: concept={metric.get('concept')}"
    )


# ============================================================
# TEST: PRINT COVERAGE RESULTS
# ============================================================

def test_print_stockholders_equity_coverage():
    print()
    print("=" * 100)
    print("REAL SEC STOCKHOLDERS' EQUITY COVERAGE")
    print("=" * 100)

    print(
        f"{'Ticker':<8}"
        f"{'Status':<12}"
        f"{'Value':>20}"
        f"{'Period End':<14}"
        f"{'Filed':<14}"
        f"{'Concept':<28}"
    )

    print("-" * 100)

    for ticker in TARGET_TICKERS:
        normalized = normalize_target(ticker)
        metric = normalized["metrics"]["stockholders_equity"]

        value = metric.get("value")

        value_text = (
            f"{value:,.0f}"
            if isinstance(value, (int, float))
            else str(value)
        )

        print(
            f"{ticker:<8}"
            f"{metric.get('status', ''):<12}"
            f"{value_text:>20}"
            f"{str(metric.get('period_end', '')):<14}"
            f"{str(metric.get('filing_date', '')):<14}"
            f"{str(metric.get('concept', '')):<28}"
        )

    print("=" * 100)
    print()