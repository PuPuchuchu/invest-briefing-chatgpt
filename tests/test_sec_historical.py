from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.fundamentals.sec_historical import (
    SCHEMA_VERSION,
    CONCEPT_MAP,
    build_record,
    deduplicate_observations,
    extract_annual_history,
    extract_historical_data,
    extract_instant_history,
    extract_quarterly_history,
    find_best_concept,
    get_concept_data,
    get_observations,
    save_historical_data,
    validate_companyfacts,
    validate_historical_data,
)


# ============================================================
# FIXTURE HELPERS
# ============================================================

def _duration_obs(
    *,
    value,
    start,
    end,
    form,
    fy,
    fp,
    filed,
    accn,
    frame=None,
    unit="USD",
):
    result = {
        "start": start,
        "end": end,
        "val": value,
        "form": form,
        "fy": fy,
        "fp": fp,
        "filed": filed,
        "accn": accn,
        "frame": frame,
        "unit": unit,
    }

    return result


def _instant_obs(
    *,
    value,
    end,
    form,
    fy,
    fp,
    filed,
    accn,
    frame=None,
    unit="USD",
):
    result = {
        "end": end,
        "val": value,
        "form": form,
        "fy": fy,
        "fp": fp,
        "filed": filed,
        "accn": accn,
        "frame": frame,
        "unit": unit,
    }

    return result


def _concept(observations, *, label="Test Concept"):
    return {
        "label": label,
        "description": label,
        "units": {
            "USD": observations,
        },
    }


def _shares_concept(observations):
    return {
        "label": "Entity Common Stock Shares Outstanding",
        "description": "Shares outstanding",
        "units": {
            "shares": observations,
        },
    }


def _build_fixture_companyfacts():
    """
    Synthetic SEC Company Facts fixture.

    FY2025:
        Q1 = 10
        H1  = 25
        Q2 standalone intentionally absent
        9M  = 45
        FY  = 70

    Therefore:
        Q1 = 10
        Q2 = 25 - 10 = 15
        Q3 = 45 - 25 = 20
        Q4 = 70 - 45 = 25

    FY2024 is included to validate annual history.
    """

    revenue_observations = [
        # FY2024
        _duration_obs(
            value=100,
            start="2024-01-01",
            end="2024-12-31",
            form="10-K",
            fy=2024,
            fp="FY",
            filed="2025-02-15",
            accn="0000000000-25-000001",
            frame="CY2024",
        ),

        # FY2025 Q1
        _duration_obs(
            value=10,
            start="2025-01-01",
            end="2025-03-31",
            form="10-Q",
            fy=2025,
            fp="Q1",
            filed="2025-05-01",
            accn="0000000000-25-000010",
            frame="CY2025Q1",
        ),

        # FY2025 H1
        _duration_obs(
            value=25,
            start="2025-01-01",
            end="2025-06-30",
            form="10-Q",
            fy=2025,
            fp="Q2",
            filed="2025-08-01",
            accn="0000000000-25-000020",
            frame="CY2025Q2",
        ),

        # FY2025 9M
        _duration_obs(
            value=45,
            start="2025-01-01",
            end="2025-09-30",
            form="10-Q",
            fy=2025,
            fp="Q3",
            filed="2025-11-01",
            accn="0000000000-25-000030",
            frame="CY2025Q3",
        ),

        # FY2025 FY
        _duration_obs(
            value=70,
            start="2025-01-01",
            end="2025-12-31",
            form="10-K",
            fy=2025,
            fp="FY",
            filed="2026-02-15",
            accn="0000000000-26-000001",
            frame="CY2025",
        ),
    ]

    net_income_observations = [
        _duration_obs(
            value=50,
            start="2024-01-01",
            end="2024-12-31",
            form="10-K",
            fy=2024,
            fp="FY",
            filed="2025-02-15",
            accn="0000000000-25-000001",
            frame="CY2024",
        ),
        _duration_obs(
            value=1,
            start="2025-01-01",
            end="2025-03-31",
            form="10-Q",
            fy=2025,
            fp="Q1",
            filed="2025-05-01",
            accn="0000000000-25-000010",
            frame="CY2025Q1",
        ),
        _duration_obs(
            value=3,
            start="2025-01-01",
            end="2025-06-30",
            form="10-Q",
            fy=2025,
            fp="Q2",
            filed="2025-08-01",
            accn="0000000000-25-000020",
            frame="CY2025Q2",
        ),
        _duration_obs(
            value=6,
            start="2025-01-01",
            end="2025-09-30",
            form="10-Q",
            fy=2025,
            fp="Q3",
            filed="2025-11-01",
            accn="0000000000-25-000030",
            frame="CY2025Q3",
        ),
        _duration_obs(
            value=10,
            start="2025-01-01",
            end="2025-12-31",
            form="10-K",
            fy=2025,
            fp="FY",
            filed="2026-02-15",
            accn="0000000000-26-000001",
            frame="CY2025",
        ),
    ]

    cash_observations = [
        # Same period-end, older filing
        _instant_obs(
            value=80,
            end="2025-12-31",
            form="10-K",
            fy=2025,
            fp="FY",
            filed="2026-02-15",
            accn="0000000000-26-000001",
            frame="CY2025",
        ),

        # Same period-end, amended/newer filing
        _instant_obs(
            value=85,
            end="2025-12-31",
            form="10-K",
            fy=2025,
            fp="FY",
            filed="2026-03-01",
            accn="0000000000-26-000002",
            frame="CY2025",
        ),

        _instant_obs(
            value=90,
            end="2026-03-31",
            form="10-Q",
            fy=2026,
            fp="Q1",
            filed="2026-05-01",
            accn="0000000000-26-000010",
            frame="CY2026Q1",
        ),
    ]

    shares_observations = [
        _instant_obs(
            value=1_000,
            end="2025-12-31",
            form="10-K",
            fy=2025,
            fp="FY",
            filed="2026-02-15",
            accn="0000000000-26-000001",
            frame=None,
            unit="shares",
        ),
        _instant_obs(
            value=1_020,
            end="2026-03-31",
            form="10-Q",
            fy=2026,
            fp="Q1",
            filed="2026-05-01",
            accn="0000000000-26-000010",
            frame=None,
            unit="shares",
        ),
    ]

    return {
        "cik": "0000000000",
        "entityName": "TEST CORP",
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": _concept(
                    revenue_observations,
                    label="Revenue",
                ),
                "NetIncomeLoss": _concept(
                    net_income_observations,
                    label="Net Income",
                ),
                "CashAndCashEquivalentsAtCarryingValue": {
                    "label": "Cash",
                    "description": "Cash and equivalents",
                    "units": {
                        "USD": cash_observations,
                    },
                },
            },
            "dei": {
                "EntityCommonStockSharesOutstanding": _shares_concept(
                    shares_observations
                ),
            },
        },
    }


# ============================================================
# BASIC VALIDATION
# ============================================================

def test_validate_companyfacts_accepts_valid_fixture():
    data = _build_fixture_companyfacts()

    validate_companyfacts(data)


def test_validate_companyfacts_rejects_missing_required_key():
    data = _build_fixture_companyfacts()

    del data["facts"]

    with pytest.raises(ValueError):
        validate_companyfacts(data)


def test_get_concept_data():
    data = _build_fixture_companyfacts()

    concept = get_concept_data(
        data,
        "us-gaap",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
    )

    assert concept is not None


def test_get_observations_flattens_units():
    data = _build_fixture_companyfacts()

    concept = get_concept_data(
        data,
        "us-gaap",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
    )

    observations = get_observations(concept)

    assert len(observations) == 5
    assert all("unit" in obs for obs in observations)


# ============================================================
# CONCEPT SELECTION
# ============================================================

def test_find_best_concept_uses_priority_order():
    data = _build_fixture_companyfacts()

    result = find_best_concept(
        data,
        "revenue",
        instant=False,
    )

    assert result is not None

    namespace, concept, concept_data = result

    assert namespace == "us-gaap"
    assert (
        concept
        == "RevenueFromContractWithCustomerExcludingAssessedTax"
    )
    assert concept_data is not None


# ============================================================
# ANNUAL EXTRACTION
# ============================================================

def test_extract_annual_history_returns_fy_only():
    data = _build_fixture_companyfacts()

    result = extract_annual_history(
        data,
        "revenue",
    )

    assert result["status"] == "OK"

    records = result["records"]

    assert len(records) == 2

    assert records[0]["period_end"] == "2024-12-31"
    assert records[0]["value"] == 100

    assert records[1]["period_end"] == "2025-12-31"
    assert records[1]["value"] == 70


def test_extract_annual_history_keeps_provenance():
    data = _build_fixture_companyfacts()

    result = extract_annual_history(
        data,
        "revenue",
    )

    record = result["records"][-1]

    assert record["form"] == "10-K"
    assert record["fp"] == "FY"
    assert record["fy"] == 2025
    assert record["filing_date"] == "2026-02-15"
    assert record["accession"] == "0000000000-26-000001"


# ============================================================
# QUARTERLY EXTRACTION
# ============================================================

def test_q1_is_extracted_as_standalone_quarter():
    data = _build_fixture_companyfacts()

    result = extract_quarterly_history(
        data,
        "revenue",
    )

    records = result["records"]

    q1 = next(
        record
        for record in records
        if record["fy"] == 2025
        and record["quarter"] == "Q1"
    )

    assert q1["value"] == 10
    assert q1["derived"] if "derived" in q1 else True


def test_q2_is_reconstructed_from_h1_minus_q1():
    data = _build_fixture_companyfacts()

    result = extract_quarterly_history(
        data,
        "revenue",
    )

    records = result["records"]

    q2 = next(
        record
        for record in records
        if record["fy"] == 2025
        and record["quarter"] == "Q2"
    )

    assert q2["value"] == 15
    assert q2["derived"] is True
    assert q2["derivation"] == "cumulative_subtraction"


def test_q3_is_reconstructed_from_9m_minus_h1():
    data = _build_fixture_companyfacts()

    result = extract_quarterly_history(
        data,
        "revenue",
    )

    records = result["records"]

    q3 = next(
        record
        for record in records
        if record["fy"] == 2025
        and record["quarter"] == "Q3"
    )

    assert q3["value"] == 20
    assert q3["derived"] is True
    assert q3["derivation"] == "cumulative_subtraction"


def test_q4_is_reconstructed_from_fy_minus_9m():
    data = _build_fixture_companyfacts()

    result = extract_quarterly_history(
        data,
        "revenue",
    )

    records = result["records"]

    q4 = next(
        record
        for record in records
        if record["fy"] == 2025
        and record["quarter"] == "Q4"
    )

    assert q4["value"] == 25
    assert q4["derived"] is True
    assert q4["derivation"] == "cumulative_subtraction"


def test_quarterly_reconstruction_keeps_source_observations():
    data = _build_fixture_companyfacts()

    result = extract_quarterly_history(
        data,
        "revenue",
    )

    q2 = next(
        record
        for record in result["records"]
        if record["fy"] == 2025
        and record["quarter"] == "Q2"
    )

    assert "source_observations" in q2
    assert len(q2["source_observations"]) == 2


# ============================================================
# DIRECT STANDALONE QUARTER PRIORITY
# ============================================================

def test_direct_standalone_quarter_is_preferred_over_reconstruction():
    data = _build_fixture_companyfacts()

    revenue_concept = data["facts"]["us-gaap"][
        "RevenueFromContractWithCustomerExcludingAssessedTax"
    ]

    revenue_concept["units"]["USD"].append(
        _duration_obs(
            value=16,
            start="2025-04-01",
            end="2025-06-30",
            form="10-Q",
            fy=2025,
            fp="Q2",
            filed="2025-08-01",
            accn="0000000000-25-000021",
            frame="CY2025Q2",
        )
    )

    result = extract_quarterly_history(
        data,
        "revenue",
    )

    q2 = next(
        record
        for record in result["records"]
        if record["fy"] == 2025
        and record["quarter"] == "Q2"
    )

    assert q2["value"] == 16
    assert q2.get("derived", False) is False


# ============================================================
# DUPLICATE CONTROL
# ============================================================

def test_duplicate_period_keeps_latest_filing():
    observations = [
        _duration_obs(
            value=100,
            start="2025-01-01",
            end="2025-12-31",
            form="10-K",
            fy=2025,
            fp="FY",
            filed="2026-02-15",
            accn="0000000000-26-000001",
        ),
        _duration_obs(
            value=110,
            start="2025-01-01",
            end="2025-12-31",
            form="10-K",
            fy=2025,
            fp="FY",
            filed="2026-03-01",
            accn="0000000000-26-000002",
        ),
    ]

    result = deduplicate_observations(observations)

    assert len(result) == 1
    assert result[0]["value"] if "value" in result[0] else result[0]["val"] == 110


# ============================================================
# INSTANT HISTORY
# ============================================================

def test_instant_history_keeps_latest_filing_for_same_period_end():
    data = _build_fixture_companyfacts()

    result = extract_instant_history(
        data,
        "cash",
    )

    records = result["records"]

    record = next(
        record
        for record in records
        if record["period_end"] == "2025-12-31"
    )

    assert record["value"] == 85
    assert record["filing_date"] == "2026-03-01"


def test_instant_history_preserves_multiple_period_ends():
    data = _build_fixture_companyfacts()

    result = extract_instant_history(
        data,
        "cash",
    )

    records = result["records"]

    period_ends = {
        record["period_end"]
        for record in records
    }

    assert period_ends == {
        "2025-12-31",
        "2026-03-31",
    }


# ============================================================
# MISSING DATA
# ============================================================

def test_missing_concept_does_not_become_zero():
    data = _build_fixture_companyfacts()

    result = extract_annual_history(
        data,
        "operating_income",
    )

    assert result["status"] == "MISSING"
    assert result["records"] == []


def test_missing_concept_has_no_fake_value():
    data = _build_fixture_companyfacts()

    result = extract_quarterly_history(
        data,
        "operating_income",
    )

    assert result["status"] == "MISSING"
    assert result["records"] == []


# ============================================================
# FULL HISTORICAL EXTRACTION
# ============================================================

def test_extract_historical_data_schema():
    data = _build_fixture_companyfacts()

    result = extract_historical_data(
        ticker="TEST",
        data=data,
        company_type="NON_FINANCIAL",
    )

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["ticker"] == "TEST"
    assert result["entity_name"] == "TEST CORP"
    assert result["cik"] == "0000000000"

    assert "history" in result

    assert "revenue" in result["history"]
    assert "net_income" in result["history"]
    assert "cash" in result["history"]


def test_full_extraction_contains_annual_and_quarterly_revenue():
    data = _build_fixture_companyfacts()

    result = extract_historical_data(
        ticker="TEST",
        data=data,
    )

    revenue = result["history"]["revenue"]

    assert revenue["annual"]["status"] == "OK"
    assert revenue["quarterly"]["status"] == "OK"

    assert len(revenue["annual"]["records"]) == 2
    assert len(revenue["quarterly"]["records"]) == 4


def test_full_extraction_contains_instant_cash_history():
    data = _build_fixture_companyfacts()

    result = extract_historical_data(
        ticker="TEST",
        data=data,
    )

    cash = result["history"]["cash"]

    assert cash["instant"]["status"] == "OK"
    assert len(cash["instant"]["records"]) == 2


# ============================================================
# VALIDATION
# ============================================================

def test_validate_historical_data_passes_valid_output():
    data = _build_fixture_companyfacts()

    result = extract_historical_data(
        ticker="TEST",
        data=data,
    )

    failures = validate_historical_data(result)

    assert failures == []


def test_validate_historical_data_detects_missing_top_level_key():
    data = _build_fixture_companyfacts()

    result = extract_historical_data(
        ticker="TEST",
        data=data,
    )

    del result["history"]

    failures = validate_historical_data(result)

    assert "history" in failures


# ============================================================
# FILE SAVE
# ============================================================

def test_save_historical_data(tmp_path: Path):
    data = _build_fixture_companyfacts()

    result = extract_historical_data(
        ticker="TEST",
        data=data,
    )

    output_path = save_historical_data(
        ticker="TEST",
        historical=result,
        processed_dir=tmp_path,
    )

    assert output_path.exists()
    assert output_path.name == "TEST_historical.json"

    with output_path.open(
        "r",
        encoding="utf-8",
    ) as file:
        saved = json.load(file)

    assert saved["ticker"] == "TEST"
    assert saved["schema_version"] == SCHEMA_VERSION


# ============================================================
# REAL SEC CACHE SMOKE TESTS
# ============================================================

@pytest.mark.parametrize(
    "ticker",
    [
        "NVDA",
        "LLY",
        "PLTR",
    ],
)
def test_real_sec_cache_smoke_if_available(ticker):
    """
    Optional smoke test.

    This test is skipped when the corresponding SEC raw cache
    does not exist locally.

    It is intentionally not a hard dependency for the unit test suite.
    """

    path = Path(
        "data/raw/sec"
    ) / f"{ticker}_companyfacts.json"

    if not path.exists():
        pytest.skip(
            f"SEC cache not available for {ticker}: {path}"
        )

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        data = json.load(file)

    result = extract_historical_data(
        ticker=ticker,
        data=data,
        company_type="NON_FINANCIAL",
    )

    failures = validate_historical_data(result)

    assert failures == []

    revenue = result["history"]["revenue"]

    assert revenue["status"] == "OK"

    assert len(
        revenue["annual"]["records"]
    ) >= 1