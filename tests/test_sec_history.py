from __future__ import annotations

import pytest

from src.fundamentals.sec_history import (
    SCHEMA_VERSION,
    classify_duration_observation,
    extract_annual_history,
    extract_concept_history,
    extract_quarterly_history,
    is_annual_observation,
    is_duration_observation,
    reconstruct_standalone_quarters,
    sort_by_filing_date,
    validate_history,
)


# ============================================================
# FIXTURES
# ============================================================

def make_q1(
    fy=2025,
    value=25,
    filed="2025-05-01",
    accession="0000000000-25-000001",
):
    return {
        "start": f"{fy}-01-01",
        "end": f"{fy}-03-31",
        "filed": filed,
        "form": "10-Q",
        "fy": fy,
        "fp": "Q1",
        "frame": f"CY{fy}Q1",
        "value": value,
        "accession": accession,
    }


def make_h1(
    fy=2025,
    value=55,
    filed="2025-08-01",
    accession="0000000000-25-000002",
):
    return {
        "start": f"{fy}-01-01",
        "end": f"{fy}-06-30",
        "filed": filed,
        "form": "10-Q",
        "fy": fy,
        "fp": "Q2",
        "frame": f"CY{fy}H1",
        "value": value,
        "accession": accession,
    }


def make_9m(
    fy=2025,
    value=90,
    filed="2025-11-01",
    accession="0000000000-25-000003",
):
    return {
        "start": f"{fy}-01-01",
        "end": f"{fy}-09-30",
        "filed": filed,
        "form": "10-Q",
        "fy": fy,
        "fp": "Q3",
        "frame": f"CY{fy}Q1Q2Q3",
        "value": value,
        "accession": accession,
    }


def make_fy(
    fy=2025,
    value=120,
    filed="2026-02-15",
    accession="0000000000-26-000001",
):
    return {
        "start": f"{fy}-01-01",
        "end": f"{fy}-12-31",
        "filed": filed,
        "form": "10-K",
        "fy": fy,
        "fp": "FY",
        "frame": f"CY{fy}",
        "value": value,
        "accession": accession,
    }


# ============================================================
# BASIC CLASSIFICATION
# ============================================================

def test_duration_observation():
    assert is_duration_observation(make_q1())


def test_annual_observation():
    assert is_annual_observation(make_fy())


def test_classify_q1():
    assert classify_duration_observation(make_q1()) == "q1"


def test_classify_h1():
    assert classify_duration_observation(make_h1()) == "ytd_6m"


def test_classify_9m():
    assert classify_duration_observation(make_9m()) == "ytd_9m"


def test_classify_fy():
    assert classify_duration_observation(make_fy()) == "annual"


def test_classify_instant_as_unknown():
    observation = {
        "end": "2025-03-31",
        "filed": "2025-05-01",
        "form": "10-Q",
        "fy": 2025,
        "fp": "Q1",
        "value": 100,
    }

    assert classify_duration_observation(observation) == "unknown"


# ============================================================
# ANNUAL HISTORY
# ============================================================

def test_extract_annual_history():
    observations = [
        make_fy(
            fy=2024,
            value=100,
            filed="2025-02-15",
        ),
        make_fy(
            fy=2025,
            value=120,
            filed="2026-02-15",
        ),
    ]

    result = extract_annual_history(observations)

    assert len(result) == 2
    assert result[0]["fy"] == 2024
    assert result[1]["fy"] == 2025


def test_extract_annual_history_ignores_10q():
    observations = [
        make_q1(value=25),
        make_h1(value=55),
        make_9m(value=90),
        make_fy(value=120),
    ]

    result = extract_annual_history(observations)

    assert len(result) == 1
    assert result[0]["fy"] == 2025


def test_extract_annual_history_prefers_earliest_filing():
    early = make_fy(
        fy=2025,
        value=120,
        filed="2026-02-15",
        accession="EARLY",
    )

    later = make_fy(
        fy=2025,
        value=125,
        filed="2026-05-01",
        accession="LATE",
    )

    result = extract_annual_history(
        [later, early]
    )

    assert len(result) == 1
    assert result[0]["value"] == 120
    assert result[0]["accession"] == "EARLY"


# ============================================================
# QUARTERLY CLASSIFICATION
# ============================================================

def test_extract_quarterly_history():
    observations = [
        make_q1(),
        make_h1(),
        make_9m(),
        make_fy(),
    ]

    result = extract_quarterly_history(observations)

    assert len(result["q1"]) == 1
    assert len(result["ytd_6m"]) == 1
    assert len(result["ytd_9m"]) == 1
    assert len(result["unknown"]) == 0


# ============================================================
# STANDALONE QUARTER RECONSTRUCTION
# ============================================================

def test_reconstruct_standalone_quarters():
    observations = [
        make_q1(value=25),
        make_h1(value=55),
        make_9m(value=90),
        make_fy(value=120),
    ]

    result = reconstruct_standalone_quarters(
        observations
    )

    assert len(result) == 4

    values = {
        item["quarter"]: item["value"]
        for item in result
    }

    assert values["Q1"] == pytest.approx(25)
    assert values["Q2"] == pytest.approx(30)
    assert values["Q3"] == pytest.approx(35)
    assert values["Q4"] == pytest.approx(30)


def test_reconstruct_q2():
    observations = [
        make_q1(value=25),
        make_h1(value=55),
    ]

    result = reconstruct_standalone_quarters(
        observations
    )

    q2 = [
        item
        for item in result
        if item["quarter"] == "Q2"
    ]

    assert len(q2) == 1
    assert q2[0]["value"] == pytest.approx(30)


def test_reconstruct_q3():
    observations = [
        make_q1(value=25),
        make_h1(value=55),
        make_9m(value=90),
    ]

    result = reconstruct_standalone_quarters(
        observations
    )

    q3 = [
        item
        for item in result
        if item["quarter"] == "Q3"
    ]

    assert len(q3) == 1
    assert q3[0]["value"] == pytest.approx(35)


def test_reconstruct_q4():
    observations = [
        make_q1(value=25),
        make_h1(value=55),
        make_9m(value=90),
        make_fy(value=120),
    ]

    result = reconstruct_standalone_quarters(
        observations
    )

    q4 = [
        item
        for item in result
        if item["quarter"] == "Q4"
    ]

    assert len(q4) == 1
    assert q4[0]["value"] == pytest.approx(30)


def test_q4_uses_fy_filing_date():
    observations = [
        make_q1(value=25),
        make_h1(value=55),
        make_9m(value=90),
        make_fy(
            value=120,
            filed="2026-02-15",
        ),
    ]

    result = reconstruct_standalone_quarters(
        observations
    )

    q4 = [
        item
        for item in result
        if item["quarter"] == "Q4"
    ][0]

    assert q4["filed"] == "2026-02-15"


def test_missing_h1_prevents_q2():
    observations = [
        make_q1(value=25),
        make_9m(value=90),
        make_fy(value=120),
    ]

    result = reconstruct_standalone_quarters(
        observations
    )

    quarters = {
        item["quarter"]
        for item in result
    }

    assert "Q2" not in quarters


def test_missing_9m_prevents_q3_and_q4():
    observations = [
        make_q1(value=25),
        make_h1(value=55),
        make_fy(value=120),
    ]

    result = reconstruct_standalone_quarters(
        observations
    )

    quarters = {
        item["quarter"]
        for item in result
    }

    assert "Q3" not in quarters
    assert "Q4" not in quarters


# ============================================================
# MULTI-YEAR HISTORY
# ============================================================

def test_reconstruct_multiple_years():
    observations = [
        make_q1(fy=2024, value=20),
        make_h1(fy=2024, value=45),
        make_9m(fy=2024, value=70),
        make_fy(fy=2024, value=100),

        make_q1(fy=2025, value=25),
        make_h1(fy=2025, value=55),
        make_9m(fy=2025, value=90),
        make_fy(fy=2025, value=120),
    ]

    result = reconstruct_standalone_quarters(
        observations
    )

    assert len(result) == 8

    fy2024 = [
        item
        for item in result
        if item["fy"] == 2024
    ]

    fy2025 = [
        item
        for item in result
        if item["fy"] == 2025
    ]

    assert len(fy2024) == 4
    assert len(fy2025) == 4


# ============================================================
# CONCEPT HISTORY
# ============================================================

def test_extract_concept_history():
    concept_data = {
        "label": "Revenue",
        "description": "Revenue",
        "units": {
            "USD": [
                make_q1(value=25),
                make_h1(value=55),
                make_9m(value=90),
                make_fy(value=120),
            ]
        },
    }

    result = extract_concept_history(
        concept_data
    )

    assert result["schema_version"] == SCHEMA_VERSION
    assert len(result["annual"]) == 1
    assert len(result["standalone_quarters"]) == 4


def test_extract_concept_history_multiple_units():
    concept_data = {
        "units": {
            "USD": [
                make_q1(value=25),
                make_h1(value=55),
                make_9m(value=90),
                make_fy(value=120),
            ],
            "EUR": [
                make_q1(value=10),
            ],
        },
    }

    result = extract_concept_history(
        concept_data
    )

    # The function preserves all units as observations.
    # It does not attempt cross-currency normalization.
    assert len(result["annual"]) == 1


# ============================================================
# FILING DATE ORDER
# ============================================================

def test_sort_by_filing_date():
    observations = [
        make_q1(
            filed="2025-06-01",
            accession="LATE",
        ),
        make_q1(
            filed="2025-05-01",
            accession="EARLY",
        ),
    ]

    result = sort_by_filing_date(observations)

    assert result[0]["accession"] == "EARLY"
    assert result[1]["accession"] == "LATE"


def test_sort_by_filing_date_newest_first():
    observations = [
        make_q1(
            filed="2025-05-01",
            accession="EARLY",
        ),
        make_q1(
            filed="2025-06-01",
            accession="LATE",
        ),
    ]

    result = sort_by_filing_date(
        observations,
        newest_first=True,
    )

    assert result[0]["accession"] == "LATE"
    assert result[1]["accession"] == "EARLY"


# ============================================================
# VALIDATION
# ============================================================

def test_validate_history_valid():
    concept_data = {
        "units": {
            "USD": [
                make_q1(value=25),
                make_h1(value=55),
                make_9m(value=90),
                make_fy(value=120),
            ]
        },
    }

    result = extract_concept_history(
        concept_data
    )

    failures = validate_history(result)

    assert failures == []


def test_validate_history_missing_annual():
    data = {
        "schema_version": SCHEMA_VERSION,
        "quarterly": {
            "q1": [],
            "ytd_6m": [],
            "ytd_9m": [],
            "unknown": [],
        },
        "standalone_quarters": [],
    }

    failures = validate_history(data)

    assert "annual" in failures


# ============================================================
# INVALID DATA
# ============================================================

def test_invalid_value_is_ignored():
    observations = [
        make_q1(value="not-a-number"),
        make_h1(value=55),
    ]

    result = extract_quarterly_history(
        observations
    )

    assert len(result["q1"]) == 0
    assert len(result["ytd_6m"]) == 1


def test_invalid_date_is_ignored():
    observation = make_q1(value=25)
    observation["start"] = "invalid-date"

    result = extract_quarterly_history(
        [observation]
    )

    assert len(result["q1"]) == 0


def test_invalid_concept_data():
    with pytest.raises(ValueError):
        extract_concept_history(
            {
                "label": "Revenue",
            }
        )