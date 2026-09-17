import json

from src.fundamentals.sec_normalizer import (
    validate_companyfacts,
    get_all_concepts,
    get_observations,
    is_annual_observation,
    is_instant_observation,
    is_duration_observation,
    sort_observations,
    select_latest_annual_observation,
    select_latest_instant_observation,
    find_concept,
    find_best_annual_concept,
    find_best_instant_concept,
    calculate_total_debt,
    normalize_company,
    validate_normalized_data,
    save_normalized_data,
    load_raw_companyfacts,
    normalize_from_cache,
)


# ============================================================
# SYNTHETIC COMPANY FACTS FIXTURE
# ============================================================

def make_companyfacts_fixture():
    return {
        "cik": "0000000000",
        "entityName": "Test Company",
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "label": "Revenue",
                    "description": "Test revenue",
                    "units": {
                        "USD": [
                            {
                                "start": "2024-01-01",
                                "end": "2024-12-31",
                                "val": 100000,
                                "accn": "0000000000-25-000001",
                                "fy": 2024,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2025-02-15",
                                "frame": "CY2024",
                            },
                            {
                                "start": "2025-01-01",
                                "end": "2025-12-31",
                                "val": 120000,
                                "accn": "0000000000-26-000001",
                                "fy": 2025,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2026-02-15",
                                "frame": "CY2025",
                            },
                        ]
                    },
                },
                "NetIncomeLoss": {
                    "label": "Net Income",
                    "description": "Test net income",
                    "units": {
                        "USD": [
                            {
                                "start": "2025-01-01",
                                "end": "2025-12-31",
                                "val": 20000,
                                "accn": "0000000000-26-000001",
                                "fy": 2025,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2026-02-15",
                                "frame": "CY2025",
                            }
                        ]
                    },
                },
                "EarningsPerShareDiluted": {
                    "label": "Diluted EPS",
                    "description": "Test diluted EPS",
                    "units": {
                        "USD/shares": [
                            {
                                "start": "2025-01-01",
                                "end": "2025-12-31",
                                "val": 2.50,
                                "accn": "0000000000-26-000001",
                                "fy": 2025,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2026-02-15",
                                "frame": "CY2025",
                            }
                        ]
                    },
                },
                "OperatingIncomeLoss": {
                    "label": "Operating Income",
                    "description": "Test operating income",
                    "units": {
                        "USD": [
                            {
                                "start": "2025-01-01",
                                "end": "2025-12-31",
                                "val": 30000,
                                "accn": "0000000000-26-000001",
                                "fy": 2025,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2026-02-15",
                                "frame": "CY2025",
                            }
                        ]
                    },
                },
                "NetCashProvidedByUsedInOperatingActivities": {
                    "label": "Operating Cash Flow",
                    "description": "Test CFO",
                    "units": {
                        "USD": [
                            {
                                "start": "2025-01-01",
                                "end": "2025-12-31",
                                "val": 25000,
                                "accn": "0000000000-26-000001",
                                "fy": 2025,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2026-02-15",
                                "frame": "CY2025",
                            }
                        ]
                    },
                },
                "PaymentsToAcquirePropertyPlantAndEquipment": {
                    "label": "Capital Expenditures",
                    "description": "Test capex",
                    "units": {
                        "USD": [
                            {
                                "start": "2025-01-01",
                                "end": "2025-12-31",
                                "val": -5000,
                                "accn": "0000000000-26-000001",
                                "fy": 2025,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2026-02-15",
                                "frame": "CY2025",
                            }
                        ]
                    },
                },
                "CashAndCashEquivalentsAtCarryingValue": {
                    "label": "Cash",
                    "description": "Test cash",
                    "units": {
                        "USD": [
                            {
                                "end": "2025-12-31",
                                "val": 50000,
                                "accn": "0000000000-26-000001",
                                "fy": 2025,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2026-02-15",
                                "frame": "CY2025",
                            }
                        ]
                    },
                },
                "ShortTermBorrowings": {
                    "label": "Current Debt",
                    "description": "Test current debt",
                    "units": {
                        "USD": [
                            {
                                "end": "2025-12-31",
                                "val": 10000,
                                "accn": "0000000000-26-000001",
                                "fy": 2025,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2026-02-15",
                                "frame": "CY2025",
                            }
                        ]
                    },
                },
                "LongTermDebtNoncurrent": {
                    "label": "Noncurrent Debt",
                    "description": "Test noncurrent debt",
                    "units": {
                        "USD": [
                            {
                                "end": "2025-12-31",
                                "val": 30000,
                                "accn": "0000000000-26-000001",
                                "fy": 2025,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2026-02-15",
                                "frame": "CY2025",
                            }
                        ]
                    },
                },
                # P/B valuation input.
                "StockholdersEquity": {
                    "label": "Stockholders' Equity",
                    "description": "Test stockholders' equity",
                    "units": {
                        "USD": [
                            {
                                "end": "2025-12-31",
                                "val": 80000,
                                "accn": "0000000000-26-000001",
                                "fy": 2025,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2026-02-15",
                                "frame": "CY2025",
                            }
                        ]
                    },
                },
            },
            "dei": {
                "EntityCommonStockSharesOutstanding": {
                    "label": "Shares Outstanding",
                    "description": "Test shares outstanding",
                    "units": {
                        "shares": [
                            {
                                "end": "2025-12-31",
                                "val": 10000,
                                "accn": "0000000000-26-000001",
                                "fy": 2025,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2026-02-15",
                            }
                        ]
                    },
                }
            },
        },
    }


# ============================================================
# BASIC VALIDATION
# ============================================================

def test_validate_companyfacts():
    data = make_companyfacts_fixture()
    assert validate_companyfacts(data) is None


def test_validate_companyfacts_missing_key():
    data = make_companyfacts_fixture()
    del data["facts"]

    try:
        validate_companyfacts(data)
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "facts" in str(exc)


# ============================================================
# CONCEPT DISCOVERY
# ============================================================

def test_get_all_concepts():
    data = make_companyfacts_fixture()
    concepts = get_all_concepts(data)

    assert len(concepts) > 0

    names = {
        (item["namespace"], item["concept"])
        for item in concepts
    }

    assert ("us-gaap", "Revenues") in names
    assert ("us-gaap", "NetIncomeLoss") in names
    assert ("us-gaap", "StockholdersEquity") in names
    assert (
        "dei",
        "EntityCommonStockSharesOutstanding",
    ) in names


def test_find_concept():
    data = make_companyfacts_fixture()

    concept = find_concept(
        data,
        "us-gaap",
        "Revenues",
    )

    assert concept is not None
    assert "units" in concept


def test_find_concept_missing():
    data = make_companyfacts_fixture()

    concept = find_concept(
        data,
        "us-gaap",
        "DoesNotExist",
    )

    assert concept is None


# ============================================================
# OBSERVATION HANDLING
# ============================================================

def test_get_observations():
    data = make_companyfacts_fixture()

    concept = find_concept(
        data,
        "us-gaap",
        "Revenues",
    )

    observations = get_observations(concept)

    assert len(observations) == 2
    assert observations[0]["val"] == 100000
    assert observations[1]["val"] == 120000
    assert observations[0]["unit"] == "USD"


def test_observation_classification():
    data = make_companyfacts_fixture()

    revenue = find_concept(
        data,
        "us-gaap",
        "Revenues",
    )

    observations = get_observations(revenue)

    for obs in observations:
        assert is_duration_observation(obs)
        assert is_annual_observation(obs)
        assert not is_instant_observation(obs)


def test_instant_observation_classification():
    data = make_companyfacts_fixture()

    cash = find_concept(
        data,
        "us-gaap",
        "CashAndCashEquivalentsAtCarryingValue",
    )

    observations = get_observations(cash)

    assert len(observations) == 1
    assert is_instant_observation(observations[0])
    assert not is_duration_observation(observations[0])
    assert not is_annual_observation(observations[0])


# ============================================================
# OBSERVATION SELECTION
# ============================================================

def test_sort_observations():
    data = make_companyfacts_fixture()

    revenue = find_concept(
        data,
        "us-gaap",
        "Revenues",
    )

    sorted_obs = sort_observations(
        get_observations(revenue)
    )

    assert sorted_obs[0]["end"] == "2025-12-31"
    assert sorted_obs[0]["filed"] == "2026-02-15"


def test_select_latest_annual_observation():
    data = make_companyfacts_fixture()

    revenue = find_concept(
        data,
        "us-gaap",
        "Revenues",
    )

    latest = select_latest_annual_observation(revenue)

    assert latest is not None
    assert latest["val"] == 120000
    assert latest["end"] == "2025-12-31"
    assert latest["filed"] == "2026-02-15"


def test_select_latest_instant_observation():
    data = make_companyfacts_fixture()

    cash = find_concept(
        data,
        "us-gaap",
        "CashAndCashEquivalentsAtCarryingValue",
    )

    latest = select_latest_instant_observation(cash)

    assert latest is not None
    assert latest["val"] == 50000
    assert latest["end"] == "2025-12-31"


# ============================================================
# CONCEPT PRIORITY
# ============================================================

def test_find_best_annual_concept():
    data = make_companyfacts_fixture()

    result = find_best_annual_concept(
        data,
        [
            "NonExistingRevenueConcept",
            "Revenues",
        ],
    )

    assert result is not None
    assert result["namespace"] == "us-gaap"
    assert result["concept"] == "Revenues"
    assert result["observation"]["val"] == 120000


def test_find_best_instant_concept():
    data = make_companyfacts_fixture()

    result = find_best_instant_concept(
        data,
        [
            "NonExistingCashConcept",
            "CashAndCashEquivalentsAtCarryingValue",
        ],
    )

    assert result is not None
    assert result["namespace"] == "us-gaap"
    assert (
        result["concept"]
        == "CashAndCashEquivalentsAtCarryingValue"
    )
    assert result["observation"]["val"] == 50000


def test_find_best_instant_equity_concept():
    data = make_companyfacts_fixture()

    result = find_best_instant_concept(
        data,
        ["StockholdersEquity"],
    )

    assert result is not None
    assert result["namespace"] == "us-gaap"
    assert result["concept"] == "StockholdersEquity"
    assert result["observation"]["val"] == 80000


# ============================================================
# TOTAL DEBT
# ============================================================

def test_calculate_total_debt_nonfinancial():
    current_debt = {
        "metric": "current_debt",
        "status": "OK",
        "value": 10000,
    }

    noncurrent_debt = {
        "metric": "noncurrent_debt",
        "status": "OK",
        "value": 30000,
    }

    result = calculate_total_debt(
        current_debt,
        noncurrent_debt,
        "NON_FINANCIAL",
    )

    assert result["status"] == "OK"
    assert result["value"] == 40000


def test_calculate_total_debt_incomplete():
    current_debt = {
        "metric": "current_debt",
        "status": "OK",
        "value": 10000,
    }

    noncurrent_debt = {
        "metric": "noncurrent_debt",
        "status": "MISSING",
        "value": None,
    }

    result = calculate_total_debt(
        current_debt,
        noncurrent_debt,
        "NON_FINANCIAL",
    )

    assert result["status"] == "INCOMPLETE"
    assert result["value"] is None


def test_calculate_total_debt_financial():
    current_debt = {
        "metric": "current_debt",
        "status": "NOT_APPLICABLE",
        "value": None,
    }

    noncurrent_debt = {
        "metric": "noncurrent_debt",
        "status": "NOT_APPLICABLE",
        "value": None,
    }

    result = calculate_total_debt(
        current_debt,
        noncurrent_debt,
        "FINANCIAL",
    )

    assert result["status"] == "NOT_APPLICABLE"
    assert result["value"] is None
    assert "components" in result


# ============================================================
# NORMALIZATION
# ============================================================

def test_normalize_nonfinancial_company():
    data = make_companyfacts_fixture()

    normalized = normalize_company(
        "TEST",
        data,
        "NON_FINANCIAL",
    )

    assert normalized["schema_version"] == "sec_fundamentals_v0.2"
    assert normalized["ticker"] == "TEST"
    assert normalized["entity_name"] == "Test Company"
    assert normalized["cik"] == "0000000000"
    assert normalized["company_type"] == "NON_FINANCIAL"

    assert normalized["source"]["provider"] == "SEC"
    assert normalized["source"]["dataset"] == "Company Facts"
    assert "normalized_at" in normalized

    metrics = normalized["metrics"]

    assert metrics["revenue"]["status"] == "OK"
    assert metrics["revenue"]["value"] == 120000

    assert metrics["net_income"]["status"] == "OK"
    assert metrics["net_income"]["value"] == 20000

    assert metrics["diluted_eps"]["status"] == "OK"
    assert metrics["diluted_eps"]["value"] == 2.50

    assert metrics["operating_income"]["status"] == "OK"
    assert metrics["operating_income"]["value"] == 30000

    assert metrics["cfo"]["status"] == "OK"
    assert metrics["cfo"]["value"] == 25000

    assert metrics["capex"]["status"] == "OK"
    assert metrics["capex"]["value"] == -5000

    assert metrics["cash"]["status"] == "OK"
    assert metrics["cash"]["value"] == 50000

    assert metrics["current_debt"]["status"] == "OK"
    assert metrics["current_debt"]["value"] == 10000

    assert metrics["noncurrent_debt"]["status"] == "OK"
    assert metrics["noncurrent_debt"]["value"] == 30000

    assert metrics["total_debt"]["status"] == "OK"
    assert metrics["total_debt"]["value"] == 40000

    assert metrics["stockholders_equity"]["status"] == "OK"
    assert metrics["stockholders_equity"]["value"] == 80000

    assert metrics["shares_outstanding"]["status"] == "OK"
    assert metrics["shares_outstanding"]["value"] == 10000


def test_normalize_financial_company():
    data = make_companyfacts_fixture()

    normalized = normalize_company(
        "TEST",
        data,
        "FINANCIAL",
    )

    metrics = normalized["metrics"]

    assert metrics["revenue"]["status"] == "OK"
    assert metrics["net_income"]["status"] == "OK"
    assert metrics["diluted_eps"]["status"] == "OK"
    assert metrics["cash"]["status"] == "OK"
    assert metrics["shares_outstanding"]["status"] == "OK"

    assert metrics["operating_income"]["status"] == "NOT_APPLICABLE"
    assert metrics["cfo"]["status"] == "NOT_APPLICABLE"
    assert metrics["capex"]["status"] == "NOT_APPLICABLE"
    assert metrics["current_debt"]["status"] == "NOT_APPLICABLE"
    assert metrics["noncurrent_debt"]["status"] == "NOT_APPLICABLE"
    assert metrics["total_debt"]["status"] == "NOT_APPLICABLE"

    # Equity remains independently extractable for P/B.
    assert metrics["stockholders_equity"]["status"] == "OK"
    assert metrics["stockholders_equity"]["value"] == 80000


# ============================================================
# NORMALIZED VALIDATION
# ============================================================

def test_validate_normalized_nonfinancial():
    data = make_companyfacts_fixture()

    normalized = normalize_company(
        "TEST",
        data,
        "NON_FINANCIAL",
    )

    failures = validate_normalized_data(normalized)

    assert failures == []


def test_validate_normalized_financial():
    data = make_companyfacts_fixture()

    normalized = normalize_company(
        "TEST",
        data,
        "FINANCIAL",
    )

    failures = validate_normalized_data(normalized)

    assert failures == []


def test_missing_equity_does_not_fail_v01_validation():
    data = make_companyfacts_fixture()
    del data["facts"]["us-gaap"]["StockholdersEquity"]

    normalized = normalize_company(
        "TEST",
        data,
        "NON_FINANCIAL",
    )

    assert (
        normalized["metrics"]["stockholders_equity"]["status"]
        == "MISSING"
    )

    failures = validate_normalized_data(normalized)
    assert failures == []


# ============================================================
# PROVENANCE
# ============================================================

def test_normalized_provenance():
    data = make_companyfacts_fixture()

    normalized = normalize_company(
        "TEST",
        data,
        "NON_FINANCIAL",
    )

    revenue = normalized["metrics"]["revenue"]

    assert revenue["period_start"] == "2025-01-01"
    assert revenue["period_end"] == "2025-12-31"
    assert revenue["filing_date"] == "2026-02-15"
    assert revenue["form"] == "10-K"
    assert revenue["fy"] == 2025
    assert revenue["fp"] == "FY"
    assert revenue["frame"] == "CY2025"
    assert revenue["accession"] == "0000000000-26-000001"


def test_instant_provenance():
    data = make_companyfacts_fixture()

    normalized = normalize_company(
        "TEST",
        data,
        "NON_FINANCIAL",
    )

    cash = normalized["metrics"]["cash"]

    assert cash["period_end"] == "2025-12-31"
    assert cash["filing_date"] == "2026-02-15"
    assert cash["form"] == "10-K"
    assert cash["accession"] == "0000000000-26-000001"


def test_equity_provenance():
    data = make_companyfacts_fixture()

    normalized = normalize_company(
        "TEST",
        data,
        "NON_FINANCIAL",
    )

    equity = normalized["metrics"]["stockholders_equity"]

    assert equity["namespace"] == "us-gaap"
    assert equity["concept"] == "StockholdersEquity"
    assert equity["unit"] == "USD"
    assert equity["period_end"] == "2025-12-31"
    assert equity["filing_date"] == "2026-02-15"
    assert equity["form"] == "10-K"
    assert equity["fy"] == 2025
    assert equity["fp"] == "FY"
    assert equity["frame"] == "CY2025"
    assert equity["accession"] == "0000000000-26-000001"


# ============================================================
# FILE HELPERS
# ============================================================

def test_save_and_load_raw_companyfacts(tmp_path):
    data = make_companyfacts_fixture()

    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()

    path = raw_dir / "TEST_companyfacts.json"

    with path.open("w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2,
        )

    loaded = load_raw_companyfacts(
        "TEST",
        raw_dir,
    )

    assert loaded == data


def test_save_normalized_data(tmp_path):
    data = make_companyfacts_fixture()

    normalized = normalize_company(
        "TEST",
        data,
        "NON_FINANCIAL",
    )

    processed_dir = tmp_path / "processed"

    path = save_normalized_data(
        "TEST",
        normalized,
        processed_dir,
    )

    assert path.exists()

    with path.open("r", encoding="utf-8") as f:
        loaded = json.load(f)

    assert loaded["ticker"] == "TEST"
    assert loaded["schema_version"] == "sec_fundamentals_v0.2"
    assert (
        loaded["metrics"]["stockholders_equity"]["value"]
        == 80000
    )


# ============================================================
# NORMALIZE FROM CACHE
# ============================================================

def test_normalize_from_cache(tmp_path):
    data = make_companyfacts_fixture()

    raw_dir = tmp_path / "raw"
    processed_dir = tmp_path / "processed"
    raw_dir.mkdir()

    raw_path = raw_dir / "TEST_companyfacts.json"

    with raw_path.open("w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2,
        )

    result = normalize_from_cache(
        "TEST",
        "NON_FINANCIAL",
        raw_dir,
        processed_dir,
    )

    assert result["ticker"] == "TEST"
    assert result["failures"] == []

    output_path = processed_dir / "TEST_fundamentals.json"

    assert output_path.exists()
    assert result["output_path"] == str(output_path)

    normalized = result["normalized"]

    assert normalized["ticker"] == "TEST"
    assert normalized["metrics"]["revenue"]["value"] == 120000
    assert (
        normalized["metrics"]["stockholders_equity"]["value"]
        == 80000
    )