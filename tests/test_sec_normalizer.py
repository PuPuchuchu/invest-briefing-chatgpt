import json
from pathlib import Path

import pytest

from src.fundamentals.sec_normalizer import (
    MISSING,
    NOT_APPLICABLE,
    validate_companyfacts,
    get_all_concepts,
    get_observations,
    is_annual_observation,
    is_instant_observation,
    calculate_total_debt,
    normalize_company,
    validate_normalized_data,
    save_normalized_data,
    load_raw_companyfacts,
    normalize_from_cache,
)


# ============================================================
# TEST FIXTURE
# ============================================================

def make_companyfacts():
    """
    Minimal synthetic SEC Company Facts fixture.

    This fixture is intentionally small.
    It is used to test the normalizer logic without:
    - SEC API access
    - real SEC files
    - internet connection
    """

    return {
        "cik": 789019,
        "entityName": "TEST CORPORATION",
        "facts": {
            "us-gaap": {

                # ------------------------------------------------
                # Revenue
                # ------------------------------------------------
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
                                "start": "2023-01-01",
                                "end": "2023-12-31",
                                "val": 90000,
                                "accn": "0000000000-24-000001",
                                "fy": 2023,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2024-02-15",
                                "frame": "CY2023",
                            },
                            {
                                "start": "2024-01-01",
                                "end": "2024-09-30",
                                "val": 75000,
                                "accn": "0000000000-24-000002",
                                "fy": 2024,
                                "fp": "Q3",
                                "form": "10-Q",
                                "filed": "2024-11-01",
                            },
                        ]
                    },
                },

                # ------------------------------------------------
                # Net income
                # ------------------------------------------------
                "NetIncomeLoss": {
                    "label": "Net Income",
                    "description": "Test net income",
                    "units": {
                        "USD": [
                            {
                                "start": "2024-01-01",
                                "end": "2024-12-31",
                                "val": 12000,
                                "accn": "0000000000-25-000001",
                                "fy": 2024,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2025-02-15",
                                "frame": "CY2024",
                            },
                            {
                                "start": "2023-01-01",
                                "end": "2023-12-31",
                                "val": 10000,
                                "accn": "0000000000-24-000001",
                                "fy": 2023,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2024-02-15",
                                "frame": "CY2023",
                            },
                        ]
                    },
                },

                # ------------------------------------------------
                # Cash
                # ------------------------------------------------
                "CashAndCashEquivalentsAtCarryingValue": {
                    "label": "Cash and Cash Equivalents",
                    "description": "Test cash",
                    "units": {
                        "USD": [
                            {
                                "end": "2024-12-31",
                                "val": 50000,
                                "accn": "0000000000-25-000001",
                                "fy": 2024,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2025-02-15",
                                "frame": "CY2024",
                            },
                            {
                                "end": "2023-12-31",
                                "val": 45000,
                                "accn": "0000000000-24-000001",
                                "fy": 2023,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2024-02-15",
                                "frame": "CY2023",
                            },
                        ]
                    },
                },

                # ------------------------------------------------
                # Current debt
                # ------------------------------------------------
                "ShortTermBorrowings": {
                    "label": "Short Term Borrowings",
                    "description": "Test current debt",
                    "units": {
                        "USD": [
                            {
                                "end": "2024-12-31",
                                "val": 10000,
                                "accn": "0000000000-25-000001",
                                "fy": 2024,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2025-02-15",
                                "frame": "CY2024",
                            }
                        ]
                    },
                },

                # ------------------------------------------------
                # Long-term debt
                # ------------------------------------------------
                "LongTermDebtNoncurrent": {
                    "label": "Long Term Debt",
                    "description": "Test long term debt",
                    "units": {
                        "USD": [
                            {
                                "end": "2024-12-31",
                                "val": 30000,
                                "accn": "0000000000-25-000001",
                                "fy": 2024,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2025-02-15",
                                "frame": "CY2024",
                            }
                        ]
                    },
                },

                # ------------------------------------------------
                # Assets
                # ------------------------------------------------
                "Assets": {
                    "label": "Assets",
                    "description": "Test assets",
                    "units": {
                        "USD": [
                            {
                                "end": "2024-12-31",
                                "val": 200000,
                                "accn": "0000000000-25-000001",
                                "fy": 2024,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2025-02-15",
                                "frame": "CY2024",
                            }
                        ]
                    },
                },

                # ------------------------------------------------
                # Liabilities
                # ------------------------------------------------
                "Liabilities": {
                    "label": "Liabilities",
                    "description": "Test liabilities",
                    "units": {
                        "USD": [
                            {
                                "end": "2024-12-31",
                                "val": 80000,
                                "accn": "0000000000-25-000001",
                                "fy": 2024,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2025-02-15",
                                "frame": "CY2024",
                            }
                        ]
                    },
                },

                # ------------------------------------------------
                # Operating cash flow
                # ------------------------------------------------
                "NetCashProvidedByUsedInOperatingActivities": {
                    "label": "Operating Cash Flow",
                    "description": "Test operating cash flow",
                    "units": {
                        "USD": [
                            {
                                "start": "2024-01-01",
                                "end": "2024-12-31",
                                "val": 18000,
                                "accn": "0000000000-25-000001",
                                "fy": 2024,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2025-02-15",
                                "frame": "CY2024",
                            }
                        ]
                    },
                },

                # ------------------------------------------------
                # Capital expenditures
                # ------------------------------------------------
                "PaymentsToAcquirePropertyPlantAndEquipment": {
                    "label": "Capital Expenditures",
                    "description": "Test CapEx",
                    "units": {
                        "USD": [
                            {
                                "start": "2024-01-01",
                                "end": "2024-12-31",
                                "val": 7000,
                                "accn": "0000000000-25-000001",
                                "fy": 2024,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2025-02-15",
                                "frame": "CY2024",
                            }
                        ]
                    },
                },

                # ------------------------------------------------
                # Shares
                # ------------------------------------------------
                "CommonStockSharesOutstanding": {
                    "label": "Common Stock Shares Outstanding",
                    "description": "Test shares",
                    "units": {
                        "shares": [
                            {
                                "end": "2024-12-31",
                                "val": 1000000,
                                "accn": "0000000000-25-000001",
                                "fy": 2024,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2025-02-15",
                                "frame": "CY2024",
                            }
                        ]
                    },
                },
            },

            # ====================================================
            # DEI
            # ====================================================
            "dei": {
                "EntityCommonStockSharesOutstanding": {
                    "label": "Entity Common Stock Shares Outstanding",
                    "description": "Test DEI shares",
                    "units": {
                        "shares": [
                            {
                                "end": "2024-12-31",
                                "val": 1100000,
                                "accn": "0000000000-25-000001",
                                "fy": 2024,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2025-02-15",
                                "frame": "CY2024",
                            }
                        ]
                    },
                }
            },
        },
    }


# ============================================================
# BASIC VALIDATION TESTS
# ============================================================

def test_validate_companyfacts_accepts_valid_fixture():
    data = make_companyfacts()

    result = validate_companyfacts(data)

    assert result is True


def test_validate_companyfacts_rejects_non_dict():
    with pytest.raises(Exception):
        validate_companyfacts([])


def test_validate_companyfacts_rejects_missing_facts():
    bad_data = {
        "cik": 789019,
        "entityName": "TEST CORPORATION",
    }

    with pytest.raises(Exception):
        validate_companyfacts(bad_data)


# ============================================================
# CONCEPT TESTS
# ============================================================

def test_get_all_concepts_returns_concepts():
    data = make_companyfacts()

    concepts = get_all_concepts(data)

    assert isinstance(concepts, dict)
    assert "us-gaap:Revenues" in concepts
    assert "us-gaap:NetIncomeLoss" in concepts
    assert "dei:EntityCommonStockSharesOutstanding" in concepts


def test_get_observations_returns_observations():
    data = make_companyfacts()

    observations = get_observations(
        data,
        "us-gaap:Revenues",
    )

    assert isinstance(observations, list)
    assert len(observations) >= 1


def test_get_observations_unknown_concept_returns_empty():
    data = make_companyfacts()

    observations = get_observations(
        data,
        "us-gaap:DoesNotExist",
    )

    assert observations == []


# ============================================================
# PERIOD CLASSIFICATION TESTS
# ============================================================

def test_is_annual_observation_true_for_10k_fy():
    observation = {
        "start": "2024-01-01",
        "end": "2024-12-31",
        "form": "10-K",
        "fp": "FY",
    }

    assert is_annual_observation(observation) is True


def test_is_annual_observation_false_for_10q():
    observation = {
        "start": "2024-01-01",
        "end": "2024-09-30",
        "form": "10-Q",
        "fp": "Q3",
    }

    assert is_annual_observation(observation) is False


def test_is_annual_observation_false_for_missing_fp():
    observation = {
        "start": "2024-01-01",
        "end": "2024-12-31",
        "form": "10-K",
    }

    assert is_annual_observation(observation) is False


def test_is_instant_observation_true():
    observation = {
        "end": "2024-12-31",
        "val": 100,
        "form": "10-K",
    }

    assert is_instant_observation(observation) is True


def test_is_instant_observation_false_for_duration():
    observation = {
        "start": "2024-01-01",
        "end": "2024-12-31",
        "val": 100,
        "form": "10-K",
    }

    assert is_instant_observation(observation) is False


# ============================================================
# DEBT TESTS
# ============================================================

def test_calculate_total_debt():
    data = make_companyfacts()

    total_debt = calculate_total_debt(data)

    assert total_debt is not None
    assert total_debt["value"] == 40000


def test_calculate_total_debt_is_not_zero_when_debt_exists():
    data = make_companyfacts()

    total_debt = calculate_total_debt(data)

    assert total_debt["value"] > 0


# ============================================================
# NORMALIZATION TESTS
# ============================================================

def test_normalize_company_returns_dict():
    data = make_companyfacts()

    normalized = normalize_company(
        data,
        ticker="TEST",
    )

    assert isinstance(normalized, dict)


def test_normalize_company_contains_ticker():
    data = make_companyfacts()

    normalized = normalize_company(
        data,
        ticker="TEST",
    )

    assert normalized["ticker"] == "TEST"


def test_normalize_company_contains_company_name():
    data = make_companyfacts()

    normalized = normalize_company(
        data,
        ticker="TEST",
    )

    assert normalized["company_name"] == "TEST CORPORATION"


def test_normalize_company_contains_schema_version():
    data = make_companyfacts()

    normalized = normalize_company(
        data,
        ticker="TEST",
    )

    assert normalized["schema_version"] == "sec_fundamentals_v0.1"


def test_normalize_company_has_metrics():
    data = make_companyfacts()

    normalized = normalize_company(
        data,
        ticker="TEST",
    )

    assert "metrics" in normalized
    assert isinstance(normalized["metrics"], dict)


def test_normalized_revenue_is_present():
    data = make_companyfacts()

    normalized = normalize_company(
        data,
        ticker="TEST",
    )

    revenue = normalized["metrics"]["revenue"]

    assert revenue["value"] == 100000


def test_normalized_net_income_is_present():
    data = make_companyfacts()

    normalized = normalize_company(
        data,
        ticker="TEST",
    )

    net_income = normalized["metrics"]["net_income"]

    assert net_income["value"] == 12000


def test_normalized_cash_is_present():
    data = make_companyfacts()

    normalized = normalize_company(
        data,
        ticker="TEST",
    )

    cash = normalized["metrics"]["cash"]

    assert cash["value"] == 50000


def test_normalized_total_debt_is_present():
    data = make_companyfacts()

    normalized = normalize_company(
        data,
        ticker="TEST",
    )

    total_debt = normalized["metrics"]["total_debt"]

    assert total_debt["value"] == 40000


# ============================================================
# MISSING / NOT_APPLICABLE TESTS
# ============================================================

def test_missing_metric_is_explicitly_marked():
    data = make_companyfacts()

    normalized = normalize_company(
        data,
        ticker="TEST",
    )

    # This concept intentionally does not exist in the fixture.
    # The normalizer must not silently convert it to zero.
    possible_missing_metrics = [
        value
        for value in normalized["metrics"].values()
        if isinstance(value, dict)
        and value.get("status") == MISSING
    ]

    assert len(possible_missing_metrics) >= 1


def test_missing_is_not_zero():
    data = make_companyfacts()

    normalized = normalize_company(
        data,
        ticker="TEST",
    )

    for metric in normalized["metrics"].values():
        if isinstance(metric, dict):
            if metric.get("status") == MISSING:
                assert metric.get("value") != 0


# ============================================================
# NORMALIZED DATA VALIDATION
# ============================================================

def test_validate_normalized_data_accepts_normalized_result():
    data = make_companyfacts()

    normalized = normalize_company(
        data,
        ticker="TEST",
    )

    result = validate_normalized_data(normalized)

    assert result is True


def test_validate_normalized_data_rejects_non_dict():
    with pytest.raises(Exception):
        validate_normalized_data([])


# ============================================================
# SAVE / LOAD TESTS
# ============================================================

def test_save_normalized_data_creates_file(tmp_path):
    data = make_companyfacts()

    normalized = normalize_company(
        data,
        ticker="TEST",
    )

    output_path = tmp_path / "TEST_fundamentals.json"

    save_normalized_data(
        normalized,
        output_path,
    )

    assert output_path.exists()


def test_saved_normalized_data_is_valid_json(tmp_path):
    data = make_companyfacts()

    normalized = normalize_company(
        data,
        ticker="TEST",
    )

    output_path = tmp_path / "TEST_fundamentals.json"

    save_normalized_data(
        normalized,
        output_path,
    )

    with output_path.open("r", encoding="utf-8") as f:
        loaded = json.load(f)

    assert isinstance(loaded, dict)
    assert loaded["ticker"] == "TEST"


# ============================================================
# CACHE TESTS
# ============================================================

def test_load_raw_companyfacts(tmp_path):
    data = make_companyfacts()

    raw_path = tmp_path / "TEST_companyfacts.json"

    with raw_path.open("w", encoding="utf-8") as f:
        json.dump(data, f)

    loaded = load_raw_companyfacts(raw_path)

    assert loaded == data


def test_normalize_from_cache(tmp_path):
    data = make_companyfacts()

    raw_path = tmp_path / "TEST_companyfacts.json"

    with raw_path.open("w", encoding="utf-8") as f:
        json.dump(data, f)

    normalized = normalize_from_cache(
        raw_path,
        ticker="TEST",
    )

    assert isinstance(normalized, dict)
    assert normalized["ticker"] == "TEST"
    assert normalized["company_name"] == "TEST CORPORATION"


# ============================================================
# NO NETWORK TEST
# ============================================================

def test_normalizer_does_not_require_network(monkeypatch):
    """
    The normalizer must work entirely from Company Facts data.
    This test intentionally blocks common network functions.
    """

    import urllib.request

    def blocked(*args, **kwargs):
        raise AssertionError(
            "Network access was attempted by sec_normalizer.py"
        )

    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        blocked,
    )

    data = make_companyfacts()

    normalized = normalize_company(
        data,
        ticker="TEST",
    )

    assert normalized["ticker"] == "TEST"


# ============================================================
# END-TO-END NORMALIZER TEST
# ============================================================

def test_full_normalization_pipeline(tmp_path):
    """
    Full local pipeline:

    synthetic Company Facts
        ↓
    save raw JSON
        ↓
    load raw JSON
        ↓
    normalize
        ↓
    validate normalized data
        ↓
    save normalized JSON
        ↓
    reload JSON
    """

    data = make_companyfacts()

    raw_path = tmp_path / "TEST_companyfacts.json"

    with raw_path.open("w", encoding="utf-8") as f:
        json.dump(data, f)

    loaded_raw = load_raw_companyfacts(raw_path)

    normalized = normalize_company(
        loaded_raw,
        ticker="TEST",
    )

    assert validate_normalized_data(normalized) is True

    processed_path = tmp_path / "TEST_fundamentals.json"

    save_normalized_data(
        normalized,
        processed_path,
    )

    assert processed_path.exists()

    with processed_path.open("r", encoding="utf-8") as f:
        reloaded = json.load(f)

    assert reloaded["ticker"] == "TEST"
    assert reloaded["company_name"] == "TEST CORPORATION"
    assert reloaded["schema_version"] == "sec_fundamentals_v0.1"