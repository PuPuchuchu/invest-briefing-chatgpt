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
    normalize_company,
    validate_normalized_data,
    save_json,
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
                                "frame": "CY2024"
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
                                "frame": "CY2025"
                            }
                        ]
                    }
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
                                "frame": "CY2025"
                            }
                        ]
                    }
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
                                "frame": "CY2025"
                            }
                        ]
                    }
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
                                "frame": "CY2025"
                            }
                        ]
                    }
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
                                "frame": "CY2025"
                            }
                        ]
                    }
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
                                "frame": "CY2025"
                            }
                        ]
                    }
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
                                "frame": "CY2025"
                            }
                        ]
                    }
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
                                "frame": "CY2025"
                            }
                        ]
                    }
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
                                "frame": "CY2025"
                            }
                        ]
                    }
                }
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
                                "filed": "2026-02-15"
                            }
                        ]
                    }
                }
            }
        }
    }


# ============================================================
# BASIC VALIDATION
# ============================================================

def test_validate_companyfacts():
    data = make_companyfacts_fixture()

    assert validate_companyfacts(data) is True


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
    assert ("dei", "EntityCommonStockSharesOutstanding") in names


def test_find_concept():
    data = make_companyfacts_fixture()

    concept = find_concept(
        data,
        "us-gaap",
        "Revenues",
    )

    assert concept is not None
    assert "units" in concept


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


# ============================================================
# SORT / LATEST OBSERVATION
# ============================================================

def test_sort_observations():
    data = make_companyfacts_fixture()

    revenue = find_concept(
        data,
        "us-gaap",
        "Revenues",
    )

    observations = get_observations(revenue)
    sorted_obs = sort_observations(observations)

    assert sorted_obs[-1]["end"] == "2025-12-31"


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
# CONCEPT PRIORITY SEARCH
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
    assert result["concept_name"] == "Revenues"


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
    assert result["concept_name"] == (
        "CashAndCashEquivalentsAtCarryingValue"
    )


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

    assert normalized["ticker"] == "TEST"
    assert normalized["entity_name"] == "Test Company"
    assert normalized["cik"] == "0000000000"
    assert normalized["company_type"] == "NON_FINANCIAL"

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
   