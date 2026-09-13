"""
SEC Company Facts Financial Normalizer v0.1

Purpose
-------
Convert SEC Company Facts raw JSON into an auditable normalized
financial series suitable for later valuation / scoring engines.

Design principles
-----------------
1. SEC filing date ("filed") is the information-availability date.
2. Instant and duration observations are handled separately.
3. 10-K / 10-Q financial statements have priority over unrelated forms.
4. FY / quarterly / YTD observations are never mixed blindly.
5. Quarterly values are reconstructed from YTD when necessary.
6. TTM is calculated only for additive duration metrics.
7. EPS is NOT summed into TTM.
8. Debt concepts must not be double-counted.
9. Old observations are marked STALE rather than interpreted as zero.
10. Every normalized value keeps source metadata for auditability.

Python
------
Designed for Python 3.12+.
Standard library only.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo


# ============================================================
# CONFIGURATION
# ============================================================

RAW_DIR = Path("data/raw/sec")
PROCESSED_DIR = Path("data/processed/fundamentals")

NY_TZ = ZoneInfo("America/New_York")


DEFAULT_TICKERS = {
    "MSFT": {
        "cik": "0000789019",
        "company_type": "NON_FINANCIAL",
    },
    "NVDA": {
        "cik": "0001045810",
        "company_type": "NON_FINANCIAL",
    },
    "JPM": {
        "cik": "0000019617",
        "company_type": "FINANCIAL",
    },
    "LLY": {
        "cik": "0000059478",
        "company_type": "NON_FINANCIAL",
    },
    "PLTR": {
        "cik": "0001321655",
        "company_type": "NON_FINANCIAL",
    },
}


# ============================================================
# FORM PRIORITY
# ============================================================

# Higher number = stronger preference.
#
# Important:
# DEF 14A may contain financial information, but it must NOT
# displace the actual 10-K financial statement for core metrics.

ANNUAL_FORM_PRIORITY = {
    "10-K": 100,
    "20-F": 100,
    "40-F": 100,
    "10-K/A": 95,
    "20-F/A": 95,
    "40-F/A": 95,
    "10-Q": 60,
    "10-Q/A": 55,
    "8-K": 20,
    "6-K": 20,
    "DEF 14A": 5,
}

QUARTER_FORM_PRIORITY = {
    "10-Q": 100,
    "10-Q/A": 95,
    "6-K": 80,
    "8-K": 20,
    "10-K": 10,
}

INSTANT_FORM_PRIORITY = {
    "10-Q": 100,
    "10-Q/A": 95,
    "10-K": 90,
    "10-K/A": 85,
    "20-F": 90,
    "20-F/A": 85,
    "40-F": 90,
    "40-F/A": 85,
    "DEF 14A": 20,
    "8-K": 20,
    "6-K": 20,
}


# ============================================================
# CONCEPT CANDIDATES
# ============================================================

CONCEPTS = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueNet",
        "Revenues",
    ],

    "net_income": [
        "NetIncomeLoss",
        "ProfitLoss",
    ],

    "diluted_eps": [
        "EarningsPerShareDiluted",
    ],

    "operating_income": [
        "OperatingIncomeLoss",
    ],

    "cfo": [
        "NetCashProvidedByUsedInOperatingActivities",
    ],

    "capex": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireOtherPropertyPlantAndEquipment",
    ],

    "cash": [
        "CashAndCashEquivalentsAtCarryingValue",
    ],

    # Current debt:
    #
    # DebtCurrent is preferred because it can represent the total
    # current debt bucket. Older concepts are fallback only.
    "current_debt": [
        "DebtCurrent",
        "ShortTermBorrowings",
        "ShortTermDebt",
        "CurrentDebt",
        "LongTermDebtCurrent",
    ],

    # Non-current debt:
    "noncurrent_debt": [
        "LongTermDebtNoncurrent",
        "LongTermDebt",
    ],

    # Combined debt:
    "combined_debt": [
        "DebtLongtermAndShorttermCombinedAmount",
    ],

    "shares_outstanding": [
        "EntityCommonStockSharesOutstanding",
        "CommonStockSharesOutstanding",
    ],
}


# ============================================================
# EXPECTED UNITS
# ============================================================

EXPECTED_UNITS = {
    "revenue": {"USD"},
    "net_income": {"USD"},
    "operating_income": {"USD"},
    "cfo": {"USD"},
    "capex": {"USD"},
    "cash": {"USD"},
    "current_debt": {"USD"},
    "noncurrent_debt": {"USD"},
    "combined_debt": {"USD"},
    "diluted_eps": {
        "USD/shares",
        "USD / shares",
    },
    "shares_outstanding": {
        "shares",
    },
}


# ============================================================
# DATE HELPERS
# ============================================================

def today_new_york() -> date:
    """
    Return current New York calendar date.

    This is intentional because the project uses NY market dates.
    """
    return datetime.now(NY_TZ).date()


def parse_date(value: Any) -> date | None:
    if value is None:
        return None

    if isinstance(value, date):
        return value

    if not isinstance(value, str):
        return None

    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def normalize_as_of_date(
    as_of_date: str | date | None,
) -> date:

    if as_of_date is None:
        return today_new_york()

    if isinstance(as_of_date, date):
        return as_of_date

    parsed = parse_date(as_of_date)

    if parsed is None:
        raise ValueError(
            f"Invalid as_of_date: {as_of_date}"
        )

    return parsed


def days_between(
    start: str | None,
    end: str | None,
) -> int | None:

    start_date = parse_date(start)
    end_date = parse_date(end)

    if start_date is None or end_date is None:
        return None

    return (end_date - start_date).days + 1


# ============================================================
# BASIC SEC HELPERS
# ============================================================

def get_all_concepts(
    data: dict,
) -> list[dict]:

    concepts = []

    facts = data.get("facts", {})

    if not isinstance(facts, dict):
        return concepts

    for namespace, namespace_data in facts.items():

        if not isinstance(namespace_data, dict):
            continue

        for concept_name, concept_data in namespace_data.items():

            if not isinstance(concept_data, dict):
                continue

            concepts.append(
                {
                    "namespace": namespace,
                    "concept": concept_name,
                    "data": concept_data,
                }
            )

    return concepts


def find_concept(
    data: dict,
    namespace: str,
    concept_name: str,
) -> dict | None:

    facts = data.get("facts", {})

    namespace_data = facts.get(namespace)

    if not isinstance(namespace_data, dict):
        return None

    concept_data = namespace_data.get(
        concept_name
    )

    if not isinstance(concept_data, dict):
        return None

    return concept_data


def get_observations(
    concept_data: dict,
) -> list[dict]:

    units = concept_data.get("units", {})

    if not isinstance(units, dict):
        return []

    observations = []

    for unit, values in units.items():

        if not isinstance(values, list):
            continue

        for observation in values:

            if not isinstance(observation, dict):
                continue

            row = dict(observation)

            row["unit"] = unit

            observations.append(row)

    return observations


# ============================================================
# OBSERVATION TYPE
# ============================================================

def is_instant_observation(
    observation: dict,
) -> bool:

    return (
        "end" in observation
        and "start" not in observation
    )


def is_duration_observation(
    observation: dict,
) -> bool:

    return (
        "start" in observation
        and "end" in observation
    )


# ============================================================
# UNIT VALIDATION
# ============================================================

def normalize_unit_name(
    unit: str | None,
) -> str | None:

    if unit is None:
        return None

    return (
        unit.strip()
        .replace(" ", "")
        .lower()
    )


def unit_matches(
    metric_name: str,
    unit: str | None,
) -> bool:

    if unit is None:
        return False

    expected = EXPECTED_UNITS.get(
        metric_name,
        set(),
    )

    if not expected:
        return True

    normalized_actual = normalize_unit_name(
        unit
    )

    normalized_expected = {
        normalize_unit_name(x)
        for x in expected
    }

    return normalized_actual in normalized_expected


# ============================================================
# FILING / OBSERVATION ELIGIBILITY
# ============================================================

def is_filed_by(
    observation: dict,
    as_of_date: date,
) -> bool:

    filed = parse_date(
        observation.get("filed")
    )

    if filed is None:
        return False

    return filed <= as_of_date


def get_form_priority(
    observation: dict,
    form_priority: dict[str, int],
) -> int:

    form = observation.get("form")

    return form_priority.get(
        form,
        0,
    )


def observation_sort_key(
    observation: dict,
    form_priority: dict[str, int],
):

    filed = observation.get(
        "filed",
        "",
    )

    end = observation.get(
        "end",
        "",
    )

    return (
        get_form_priority(
            observation,
            form_priority,
        ),
        filed,
        end,
        observation.get(
            "accn",
            "",
        ),
    )


def filter_eligible_observations(
    observations: Iterable[dict],
    as_of_date: date,
    metric_name: str | None = None,
    instant: bool | None = None,
) -> list[dict]:

    result = []

    for observation in observations:

        if not is_filed_by(
            observation,
            as_of_date,
        ):
            continue

        if instant is True:
            if not is_instant_observation(
                observation
            ):
                continue

        elif instant is False:
            if not is_duration_observation(
                observation
            ):
                continue

        if metric_name is not None:

            if not unit_matches(
                metric_name,
                observation.get("unit"),
            ):
                continue

        result.append(observation)

    return result


# ============================================================
# STALE CHECK
# ============================================================

def is_stale_instant(
    observation: dict,
    as_of_date: date,
    max_age_days: int,
) -> bool:

    end_date = parse_date(
        observation.get("end")
    )

    if end_date is None:
        return True

    age = (
        as_of_date - end_date
    ).days

    return age > max_age_days


# ============================================================
# ANNUAL / QUARTER / YTD CLASSIFICATION
# ============================================================

def is_annual_observation(
    observation: dict,
) -> bool:

    if not is_duration_observation(
        observation
    ):
        return False

    form = observation.get("form")

    fp = observation.get("fp")

    if form not in {
        "10-K",
        "10-K/A",
        "20-F",
        "20-F/A",
        "40-F",
        "40-F/A",
    }:
        return False

    return fp == "FY"


def get_quarter_from_frame(
    observation: dict,
) -> int | None:

    frame = observation.get(
        "frame"
    )

    if not isinstance(frame, str):
        return None

    match = re.search(
        r"Q([1-4])",
        frame,
    )

    if not match:
        return None

    return int(
        match.group(1)
    )


def get_quarter_from_fp(
    observation: dict,
) -> int | None:

    fp = observation.get("fp")

    if fp not in {
        "Q1",
        "Q2",
        "Q3",
    }:
        return None

    return int(
        fp[-1]
    )


def get_observation_fiscal_year(
    observation: dict,
) -> int | None:

    fy = observation.get("fy")

    if isinstance(fy, int):
        return fy

    try:
        return int(fy)
    except (TypeError, ValueError):
        return None


def is_direct_quarter_observation(
    observation: dict,
) -> bool:

    if not is_duration_observation(
        observation
    ):
        return False

    form = observation.get("form")

    if form not in {
        "10-Q",
        "10-Q/A",
        "6-K",
    }:
        return False

    duration = days_between(
        observation.get("start"),
        observation.get("end"),
    )

    if duration is None:
        return False

    # Typical fiscal quarter duration:
    # approximately 80-100 days.
    #
    # Wider bounds allow 52/53-week fiscal calendars.
    return 70 <= duration <= 120


def is_ytd_observation(
    observation: dict,
) -> bool:

    if not is_duration_observation(
        observation
    ):
        return False

    form = observation.get("form")

    if form not in {
        "10-Q",
        "10-Q/A",
        "6-K",
    }:
        return False

    fp = observation.get("fp")

    if fp not in {
        "Q1",
        "Q2",
        "Q3",
    }:
        return False

    duration = days_between(
        observation.get("start"),
        observation.get("end"),
    )

    if duration is None:
        return False

    # Q1 can be both quarter and YTD.
    #
    # Q2 YTD: roughly 150-210 days
    # Q3 YTD: roughly 230-300 days
    #
    # Q1 is handled as the quarter itself.
    if fp == "Q1":
        return False

    if fp == "Q2":
        return 120 <= duration <= 230

    if fp == "Q3":
        return 200 <= duration <= 330

    return False


# ============================================================
# SOURCE METADATA
# ============================================================

def compact_source(
    observation: dict,
) -> dict:

    return {
        "value": observation.get(
            "val"
        ),

        "unit": observation.get(
            "unit"
        ),

        "period_start": observation.get(
            "start"
        ),

        "period_end": observation.get(
            "end"
        ),

        "filing_date": observation.get(
            "filed"
        ),

        "form": observation.get(
            "form"
        ),

        "fy": observation.get(
            "fy"
        ),

        "fp": observation.get(
            "fp"
        ),

        "frame": observation.get(
            "frame"
        ),

        "accession": observation.get(
            "accn"
        ),
    }


def build_source_result(
    metric_name: str,
    namespace: str,
    concept: str,
    observation: dict,
    *,
    source_type: str = "DIRECT",
    components: list[dict] | None = None,
) -> dict:

    result = {
        "metric": metric_name,
        "status": "OK",
        "source_type": source_type,

        "namespace": namespace,
        "concept": concept,

        "unit": observation.get(
            "unit"
        ),

        "value": observation.get(
            "val"
        ),

        "period_start": observation.get(
            "start"
        ),

        "period_end": observation.get(
            "end"
        ),

        "filing_date": observation.get(
            "filed"
        ),

        "form": observation.get(
            "form"
        ),

        "fy": observation.get(
            "fy"
        ),

        "fp": observation.get(
            "fp"
        ),

        "frame": observation.get(
            "frame"
        ),

        "accession": observation.get(
            "accn"
        ),
    }

    if components:
        result["components"] = components

    return result


def build_derived_result(
    metric_name: str,
    value: float,
    unit: str | None,
    period_start: str | None,
    period_end: str | None,
    *,
    source_type: str,
    components: list[dict],
    reason: str | None = None,
) -> dict:

    result = {
        "metric": metric_name,
        "status": "OK",
        "source_type": source_type,

        "namespace": None,
        "concept": None,

        "unit": unit,
        "value": value,

        "period_start": period_start,
        "period_end": period_end,

        "filing_date": max(
            (
                x.get("filing_date")
                for x in components
                if x.get("filing_date")
            ),
            default=None,
        ),

        "form": None,
        "fy": None,
        "fp": None,
        "frame": None,
        "accession": None,

        "components": components,
    }

    if reason:
        result["reason"] = reason

    return result


def build_missing_result(
    metric_name: str,
    reason: str,
) -> dict:

    return {
        "metric": metric_name,
        "status": "MISSING",
        "source_type": None,
        "namespace": None,
        "concept": None,
        "unit": None,
        "value": None,
        "period_start": None,
        "period_end": None,
        "filing_date": None,
        "form": None,
        "fy": None,
        "fp": None,
        "frame": None,
        "accession": None,
        "reason": reason,
    }


def build_stale_result(
    metric_name: str,
    observation: dict,
    reason: str,
) -> dict:

    result = build_source_result(
        metric_name,
        observation.get(
            "_namespace",
            "",
        ),
        observation.get(
            "_concept",
            "",
        ),
        observation,
        source_type="STALE",
    )

    result["status"] = "STALE"
    result["reason"] = reason

    return result


def build_not_applicable_result(
    metric_name: str,
    reason: str,
) -> dict:

    return {
        "metric": metric_name,
        "status": "NOT_APPLICABLE",
        "source_type": None,
        "namespace": None,
        "concept": None,
        "unit": None,
        "value": None,
        "period_start": None,
        "period_end": None,
        "filing_date": None,
        "form": None,
        "fy": None,
        "fp": None,
        "frame": None,
        "accession": None,
        "reason": reason,
    }


# ============================================================
# CONCEPT OBSERVATION COLLECTION
# ============================================================

def collect_candidate_observations(
    data: dict,
    concept_candidates: list[str],
    namespaces: tuple[str, ...],
    as_of_date: date,
    metric_name: str,
    *,
    instant: bool,
) -> list[dict]:

    candidates = []

    for candidate_rank, concept_name in enumerate(
        concept_candidates
    ):

        for namespace in namespaces:

            concept_data = find_concept(
                data,
                namespace,
                concept_name,
            )

            if concept_data is None:
                continue

            observations = get_observations(
                concept_data
            )

            observations = filter_eligible_observations(
                observations,
                as_of_date,
                metric_name,
                instant=instant,
            )

            for observation in observations:

                row = dict(observation)

                row["_namespace"] = namespace
                row["_concept"] = concept_name
                row["_candidate_rank"] = candidate_rank

                candidates.append(row)

    return candidates


# ============================================================
# BEST INSTANT CONCEPT
# ============================================================

def select_best_instant_observation(
    data: dict,
    metric_name: str,
    concept_candidates: list[str],
    namespaces: tuple[str, ...],
    as_of_date: date,
    *,
    max_age_days: int = 400,
) -> dict:

    candidates = collect_candidate_observations(
        data,
        concept_candidates,
        namespaces,
        as_of_date,
        metric_name,
        instant=True,
    )

    if not candidates:

        return {
            "status": "MISSING",
            "observation": None,
        }

    # Sort by:
    #
    # 1. concept priority
    # 2. end date descending
    # 3. filing date descending
    # 4. form priority
    #
    # This preserves economic concept priority while still
    # preferring the latest observation within that concept.

    candidates.sort(
        key=lambda x: (
            x.get(
                "_candidate_rank",
                999,
            ),
            x.get(
                "end",
                "",
            ),
            x.get(
                "filed",
                "",
            ),
            get_form_priority(
                x,
                INSTANT_FORM_PRIORITY,
            ),
        ),
        reverse=False,
    )

    # Candidate rank must dominate.
    best_rank = min(
        x.get(
            "_candidate_rank",
            999,
        )
        for x in candidates
    )

    same_rank = [
        x
        for x in candidates
        if x.get(
            "_candidate_rank",
            999,
        ) == best_rank
    ]

    same_rank.sort(
        key=lambda x: (
            x.get(
                "end",
                "",
            ),
            get_form_priority(
                x,
                INSTANT_FORM_PRIORITY,
            ),
            x.get(
                "filed",
                "",
            ),
        ),
        reverse=True,
    )

    best = same_rank[0]

    if is_stale_instant(
        best,
        as_of_date,
        max_age_days,
    ):

        return {
            "status": "STALE",
            "observation": best,
        }

    return {
        "status": "OK",
        "observation": best,
    }


# ============================================================
# BEST ANNUAL OBSERVATION
# ============================================================

def select_best_annual_observation(
    data: dict,
    metric_name: str,
    concept_candidates: list[str],
    namespaces: tuple[str, ...],
    as_of_date: date,
    fiscal_year: int | None = None,
) -> dict | None:

    all_candidates = []

    for candidate_rank, concept_name in enumerate(
        concept_candidates
    ):

        for namespace in namespaces:

            concept_data = find_concept(
                data,
                namespace,
                concept_name,
            )

            if concept_data is None:
                continue

            observations = get_observations(
                concept_data
            )

            for observation in observations:

                if not is_annual_observation(
                    observation
                ):
                    continue

                if not is_filed_by(
                    observation,
                    as_of_date,
                ):
                    continue

                if not unit_matches(
                    metric_name,
                    observation.get("unit"),
                ):
                    continue

                if fiscal_year is not None:

                    if get_observation_fiscal_year(
                        observation
                    ) != fiscal_year:
                        continue

                row = dict(observation)

                row["_namespace"] = namespace
                row["_concept"] = concept_name
                row["_candidate_rank"] = candidate_rank

                all_candidates.append(row)

    if not all_candidates:
        return None

    # Concept priority dominates.
    best_rank = min(
        x["_candidate_rank"]
        for x in all_candidates
    )

    candidates = [
        x
        for x in all_candidates
        if x["_candidate_rank"] == best_rank
    ]

    candidates.sort(
        key=lambda x: (
            get_form_priority(
                x,
                ANNUAL_FORM_PRIORITY,
            ),
            x.get(
                "filed",
                "",
            ),
            x.get(
                "end",
                "",
            ),
        ),
        reverse=True,
    )

    return candidates[0]


# ============================================================
# DIRECT QUARTER OBSERVATION
# ============================================================

def select_direct_quarter(
    data: dict,
    metric_name: str,
    concept_candidates: list[str],
    namespaces: tuple[str, ...],
    fiscal_year: int,
    quarter: int,
    as_of_date: date,
) -> dict | None:

    all_candidates = []

    for candidate_rank, concept_name in enumerate(
        concept_candidates
    ):

        for namespace in namespaces:

            concept_data = find_concept(
                data,
                namespace,
                concept_name,
            )

            if concept_data is None:
                continue

            observations = get_observations(
                concept_data
            )

            for observation in observations:

                if not is_direct_quarter_observation(
                    observation
                ):
                    continue

                if not is_filed_by(
                    observation,
                    as_of_date,
                ):
                    continue

                if not unit_matches(
                    metric_name,
                    observation.get("unit"),
                ):
                    continue

                obs_fy = get_observation_fiscal_year(
                    observation
                )

                if obs_fy != fiscal_year:
                    continue

                obs_quarter = (
                    get_quarter_from_frame(
                        observation
                    )
                    or
                    get_quarter_from_fp(
                        observation
                    )
                )

                if obs_quarter != quarter:
                    continue

                row = dict(observation)

                row["_namespace"] = namespace
                row["_concept"] = concept_name
                row["_candidate_rank"] = candidate_rank

                all_candidates.append(row)

    if not all_candidates:
        return None

    best_rank = min(
        x["_candidate_rank"]
        for x in all_candidates
    )

    candidates = [
        x
        for x in all_candidates
        if x["_candidate_rank"] == best_rank
    ]

    candidates.sort(
        key=lambda x: (
            get_form_priority(
                x,
                QUARTER_FORM_PRIORITY,
            ),
            x.get(
                "filed",
                "",
            ),
            x.get(
                "end",
                "",
            ),
        ),
        reverse=True,
    )

    return candidates[0]


# ============================================================
# YTD OBSERVATION
# ============================================================

def select_ytd_observation(
    data: dict,
    metric_name: str,
    concept_candidates: list[str],
    namespaces: tuple[str, ...],
    fiscal_year: int,
    quarter: int,
    as_of_date: date,
) -> dict | None:

    all_candidates = []

    for candidate_rank, concept_name in enumerate(
        concept_candidates
    ):

        for namespace in namespaces:

            concept_data = find_concept(
                data,
                namespace,
                concept_name,
            )

            if concept_data is None:
                continue

            observations = get_observations(
                concept_data
            )

            for observation in observations:

                if not is_ytd_observation(
                    observation
                ):
                    continue

                if not is_filed_by(
                    observation,
                    as_of_date,
                ):
                    continue

                if not unit_matches(
                    metric_name,
                    observation.get("unit"),
                ):
                    continue

                if get_observation_fiscal_year(
                    observation
                ) != fiscal_year:
                    continue

                obs_quarter = get_quarter_from_fp(
                    observation
                )

                if obs_quarter != quarter:
                    continue

                row = dict(observation)

                row["_namespace"] = namespace
                row["_concept"] = concept_name
                row["_candidate_rank"] = candidate_rank

                all_candidates.append(row)

    if not all_candidates:
        return None

    best_rank = min(
        x["_candidate_rank"]
        for x in all_candidates
    )

    candidates = [
        x
        for x in all_candidates
        if x["_candidate_rank"] == best_rank
    ]

    candidates.sort(
        key=lambda x: (
            get_form_priority(
                x,
                QUARTER_FORM_PRIORITY,
            ),
            x.get(
                "filed",
                "",
            ),
            x.get(
                "end",
                "",
            ),
        ),
        reverse=True,
    )

    return candidates[0]


# ============================================================
# PERIOD RESULT HELPERS
# ============================================================

def observation_to_result(
    metric_name: str,
    observation: dict,
    *,
    source_type: str = "DIRECT",
) -> dict:

    return build_source_result(
        metric_name,
        observation.get(
            "_namespace",
            "",
        ),
        observation.get(
            "_concept",
            "",
        ),
        observation,
        source_type=source_type,
    )


# ============================================================
# QUARTER RECONSTRUCTION
# ============================================================

def build_quarter_series(
    data: dict,
    metric_name: str,
    concept_candidates: list[str],
    namespaces: tuple[str, ...],
    fiscal_year: int,
    as_of_date: date,
) -> dict:

    quarters: dict[str, dict] = {}

    # --------------------------------------------------------
    # Q1
    # --------------------------------------------------------

    q1_direct = select_direct_quarter(
        data,
        metric_name,
        concept_candidates,
        namespaces,
        fiscal_year,
        1,
        as_of_date,
    )

    if q1_direct is not None:

        quarters["Q1"] = observation_to_result(
            metric_name,
            q1_direct,
            source_type="DIRECT",
        )

    else:

        q1_ytd = select_ytd_observation(
            data,
            metric_name,
            concept_candidates,
            namespaces,
            fiscal_year,
            1,
            as_of_date,
        )

        if q1_ytd is not None:

            quarters["Q1"] = observation_to_result(
                metric_name,
                q1_ytd,
                source_type="YTD_Q1",
            )

    # --------------------------------------------------------
    # Q2
    # --------------------------------------------------------

    q2_direct = select_direct_quarter(
        data,
        metric_name,
        concept_candidates,
        namespaces,
        fiscal_year,
        2,
        as_of_date,
    )

    if q2_direct is not None:

        quarters["Q2"] = observation_to_result(
            metric_name,
            q2_direct,
            source_type="DIRECT",
        )

    else:

        q2_ytd = select_ytd_observation(
            data,
            metric_name,
            concept_candidates,
            namespaces,
            fiscal_year,
            2,
            as_of_date,
        )

        if (
            q2_ytd is not None
            and "Q1" in quarters
        ):

            q1_value = quarters["Q1"].get(
                "value"
            )

            q2_ytd_value = q2_ytd.get(
                "val"
            )

            if (
                isinstance(
                    q1_value,
                    (int, float),
                )
                and
                isinstance(
                    q2_ytd_value,
                    (int, float),
                )
            ):

                value = (
                    q2_ytd_value
                    - q1_value
                )

                quarters["Q2"] = build_derived_result(
                    metric_name,
                    value,
                    q2_ytd.get(
                        "unit"
                    ),
                    q2_ytd.get(
                        "start"
                    ),
                    q2_ytd.get(
                        "end"
                    ),
                    source_type="YTD_MINUS_Q1",
                    components=[
                        quarters["Q1"],
                        compact_source(
                            q2_ytd
                        ),
                    ],
                )

    # --------------------------------------------------------
    # Q3
    # --------------------------------------------------------

    q3_direct = select_direct_quarter(
        data,
        metric_name,
        concept_candidates,
        namespaces,
        fiscal_year,
        3,
        as_of_date,
    )

    if q3_direct is not None:

        quarters["Q3"] = observation_to_result(
            metric_name,
            q3_direct,
            source_type="DIRECT",
        )

    else:

        q3_ytd = select_ytd_observation(
            data,
            metric_name,
            concept_candidates,
            namespaces,
            fiscal_year,
            3,
            as_of_date,
        )

        if (
            q3_ytd is not None
            and "Q1" in quarters
            and "Q2" in quarters
        ):

            q1_value = quarters["Q1"].get(
                "value"
            )

            q2_value = quarters["Q2"].get(
                "value"
            )

            q3_ytd_value = q3_ytd.get(
                "val"
            )

            if all(
                isinstance(
                    x,
                    (int, float),
                )
                for x in [
                    q1_value,
                    q2_value,
                    q3_ytd_value,
                ]
            ):

                value = (
                    q3_ytd_value
                    - q1_value
                    - q2_value
                )

                quarters["Q3"] = build_derived_result(
                    metric_name,
                    value,
                    q3_ytd.get(
                        "unit"
                    ),
                    q3_ytd.get(
                        "start"
                    ),
                    q3_ytd.get(
                        "end"
                    ),
                    source_type="YTD_MINUS_Q1_Q2",
                    components=[
                        quarters["Q1"],
                        quarters["Q2"],
                        compact_source(
                            q3_ytd
                        ),
                    ],
                )

    # --------------------------------------------------------
    # Q4
    # --------------------------------------------------------

    annual = select_best_annual_observation(
        data,
        metric_name,
        concept_candidates,
        namespaces,
        as_of_date,
        fiscal_year=fiscal_year,
    )

    if (
        annual is not None
        and
        all(
            q in quarters
            for q in [
                "Q1",
                "Q2",
                "Q3",
            ]
        )
    ):

        annual_value = annual.get(
            "val"
        )

        q1_value = quarters["Q1"].get(
            "value"
        )

        q2_value = quarters["Q2"].get(
            "value"
        )

        q3_value = quarters["Q3"].get(
            "value"
        )

        if all(
            isinstance(
                x,
                (int, float),
            )
            for x in [
                annual_value,
                q1_value,
                q2_value,
                q3_value,
            ]
        ):

            q4_value = (
                annual_value
                - q1_value
                - q2_value
                - q3_value
            )

            quarters["Q4"] = build_derived_result(
                metric_name,
                q4_value,
                annual.get(
                    "unit"
                ),
                annual.get(
                    "start"
                ),
                annual.get(
                    "end"
                ),
                source_type="FY_MINUS_Q1_Q2_Q3",
                components=[
                    quarters["Q1"],
                    quarters["Q2"],
                    quarters["Q3"],
                    compact_source(
                        annual
                    ),
                ],
            )

    return quarters


# ============================================================
# ANNUAL SERIES
# ============================================================

def build_annual_series(
    data: dict,
    metric_name: str,
    concept_candidates: list[str],
    namespaces: tuple[str, ...],
    as_of_date: date,
) -> dict:

    fiscal_years = set()

    for concept_name in concept_candidates:

        for namespace in namespaces:

            concept_data = find_concept(
                data,
                namespace,
                concept_name,
            )

            if concept_data is None:
                continue

            for observation in get_observations(
                concept_data
            ):

                if not is_annual_observation(
                    observation
                ):
                    continue

                if not is_filed_by(
                    observation,
                    as_of_date,
                ):
                    continue

                if not unit_matches(
                    metric_name,
                    observation.get("unit"),
                ):
                    continue

                fy = get_observation_fiscal_year(
                    observation
                )

                if fy is not None:
                    fiscal_years.add(fy)

    annual = {}

    for fiscal_year in sorted(
        fiscal_years
    ):

        observation = select_best_annual_observation(
            data,
            metric_name,
            concept_candidates,
            namespaces,
            as_of_date,
            fiscal_year=fiscal_year,
        )

        if observation is None:
            continue

        annual[str(fiscal_year)] = (
            observation_to_result(
                metric_name,
                observation,
                source_type="ANNUAL",
            )
        )

    return annual


# ============================================================
# TTM
# ============================================================

ADDITIVE_TTM_METRICS = {
    "revenue",
    "net_income",
    "operating_income",
    "cfo",
    "capex",
}


def build_ttm(
    data: dict,
    metric_name: str,
    concept_candidates: list[str],
    namespaces: tuple[str, ...],
    as_of_date: date,
    annual_series: dict,
    quarter_series: dict,
) -> dict | None:

    # EPS must never be mechanically summed.
    if metric_name not in ADDITIVE_TTM_METRICS:
        return None

    if not annual_series:
        return None

    # --------------------------------------------------------
    # Determine latest annual fiscal year.
    # --------------------------------------------------------

    annual_years = sorted(
        int(x)
        for x in annual_series.keys()
    )

    latest_fy = annual_years[-1]

    # --------------------------------------------------------
    # Find current YTD after latest FY.
    #
    # Example:
    # FY2025 + H1 2026 - H1 2025
    # --------------------------------------------------------

    current_fy = latest_fy + 1

    current_ytd_candidates = []

    for quarter in [1, 2, 3]:

        ytd = select_ytd_observation(
            data,
            metric_name,
            concept_candidates,
            namespaces,
            current_fy,
            quarter,
            as_of_date,
        )

        if ytd is not None:
            current_ytd_candidates.append(
                ytd
            )

    if current_ytd_candidates:

        # Use the longest YTD period available:
        # Q3 > Q2 > Q1.
        current_ytd_candidates.sort(
            key=lambda x: (
                days_between(
                    x.get("start"),
                    x.get("end"),
                )
                or 0
            ),
            reverse=True,
        )

        current_ytd = (
            current_ytd_candidates[0]
        )

        current_q = get_quarter_from_fp(
            current_ytd
        )

        if current_q is not None:

            prior_ytd = select_ytd_observation(
                data,
                metric_name,
                concept_candidates,
                namespaces,
                latest_fy,
                current_q,
                as_of_date,
            )

            annual_result = annual_series.get(
                str(latest_fy)
            )

            if (
                prior_ytd is not None
                and annual_result is not None
            ):

                annual_value = annual_result.get(
                    "value"
                )

                current_ytd_value = (
                    current_ytd.get("val")
                )

                prior_ytd_value = (
                    prior_ytd.get("val")
                )

                if all(
                    isinstance(
                        x,
                        (int, float),
                    )
                    for x in [
                        annual_value,
                        current_ytd_value,
                        prior_ytd_value,
                    ]
                ):

                    ttm_value = (
                        annual_value
                        + current_ytd_value
                        - prior_ytd_value
                    )

                    return build_derived_result(
                        metric_name,
                        ttm_value,
                        current_ytd.get(
                            "unit"
                        ),
                        current_ytd.get(
                            "start"
                        ),
                        current_ytd.get(
                            "end"
                        ),
                        source_type="TTM_FY_PLUS_YTD_MINUS_PRIOR_YTD",
                        components=[
                            annual_result,
                            compact_source(
                                current_ytd
                            ),
                            compact_source(
                                prior_ytd
                            ),
                        ],
                    )

    # --------------------------------------------------------
    # Fallback:
    # sum latest four reconstructed quarters.
    # --------------------------------------------------------

    available_quarters = []

    for fiscal_year, periods in quarter_series.items():

        for quarter, result in periods.items():

            if result.get("status") != "OK":
                continue

            value = result.get(
                "value"
            )

            if not isinstance(
                value,
                (int, float),
            ):
                continue

            available_quarters.append(
                (
                    int(fiscal_year),
                    int(quarter[1]),
                    result,
                )
            )

    available_quarters.sort(
        key=lambda x: (
            x[0],
            x[1],
        ),
        reverse=True,
    )

    latest_four = available_quarters[:4]

    if len(latest_four) != 4:
        return None

    values = [
        item[2]["value"]
        for item in latest_four
    ]

    if not all(
        isinstance(
            x,
            (int, float),
        )
        for x in values
    ):
        return None

    ttm_value = sum(values)

    components = [
        item[2]
        for item in reversed(
            latest_four
        )
    ]

    period_start = components[0].get(
        "period_start"
    )

    period_end = components[-1].get(
        "period_end"
    )

    return build_derived_result(
        metric_name,
        ttm_value,
        components[-1].get(
            "unit"
        ),
        period_start,
        period_end,
        source_type="TTM_SUM_LAST_FOUR_QUARTERS",
        components=components,
    )


# ============================================================
# DURATION METRIC NORMALIZATION
# ============================================================

def normalize_duration_metric(
    data: dict,
    metric_name: str,
    concept_candidates: list[str],
    namespaces: tuple[str, ...],
    as_of_date: date,
) -> dict:

    annual = build_annual_series(
        data,
        metric_name,
        concept_candidates,
        namespaces,
        as_of_date,
    )

    # Determine fiscal years from annual series and current
    # YTD observations.
    fiscal_years = set(
        int(x)
        for x in annual.keys()
    )

    for concept_name in concept_candidates:

        for namespace in namespaces:

            concept_data = find_concept(
                data,
                namespace,
                concept_name,
            )

            if concept_data is None:
                continue

            for observation in get_observations(
                concept_data
            ):

                if not is_duration_observation(
                    observation
                ):
                    continue

                if not is_filed_by(
                    observation,
                    as_of_date,
                ):
                    continue

                if not unit_matches(
                    metric_name,
                    observation.get("unit"),
                ):
                    continue

                fy = get_observation_fiscal_year(
                    observation
                )

                if fy is not None:
                    fiscal_years.add(fy)

    fiscal_years = sorted(
        fiscal_years
    )

    quarters = {}

    for fiscal_year in fiscal_years:

        quarter_result = build_quarter_series(
            data,
            metric_name,
            concept_candidates,
            namespaces,
            fiscal_year,
            as_of_date,
        )

        if quarter_result:
            quarters[str(fiscal_year)] = (
                quarter_result
            )

    ttm = build_ttm(
        data,
        metric_name,
        concept_candidates,
        namespaces,
        as_of_date,
        annual,
        quarters,
    )

    status = "OK"

    if not annual and not quarters:
        status = "MISSING"

    return {
        "metric": metric_name,
        "status": status,
        "annual": annual,
        "quarters": quarters,
        "ttm": ttm,
    }


# ============================================================
# INSTANT METRIC NORMALIZATION
# ============================================================

def normalize_instant_metric(
    data: dict,
    metric_name: str,
    concept_candidates: list[str],
    namespaces: tuple[str, ...],
    as_of_date: date,
    *,
    max_age_days: int = 400,
) -> dict:

    result = select_best_instant_observation(
        data,
        metric_name,
        concept_candidates,
        namespaces,
        as_of_date,
        max_age_days=max_age_days,
    )

    status = result.get(
        "status"
    )

    observation = result.get(
        "observation"
    )

    if status == "MISSING":

        return build_missing_result(
            metric_name,
            "No valid instant observation found.",
        )

    if observation is None:

        return build_missing_result(
            metric_name,
            "Observation selection returned no data.",
        )

    if status == "STALE":

        return build_stale_result(
            metric_name,
            observation,
            (
                f"Latest observation is older than "
                f"{max_age_days} days as of "
                f"{as_of_date.isoformat()}."
            ),
        )

    return observation_to_result(
        metric_name,
        observation,
        source_type="INSTANT",
    )


# ============================================================
# DEBT NORMALIZATION
# ============================================================

def select_latest_candidate_observation(
    data: dict,
    metric_name: str,
    concept_candidates: list[str],
    namespaces: tuple[str, ...],
    as_of_date: date,
    max_age_days: int,
) -> dict | None:

    candidates = collect_candidate_observations(
        data,
        concept_candidates,
        namespaces,
        as_of_date,
        metric_name,
        instant=True,
    )

    if not candidates:
        return None

    # For debt components we prioritize freshness within
    # the concept candidate hierarchy.
    #
    # First find the best candidate concept rank that has a
    # non-stale observation.

    for candidate_rank in sorted(
        set(
            x.get(
                "_candidate_rank",
                999,
            )
            for x in candidates
        )
    ):

        same_rank = [
            x
            for x in candidates
            if x.get(
                "_candidate_rank",
                999,
            ) == candidate_rank
        ]

        same_rank = [
            x
            for x in same_rank
            if not is_stale_instant(
                x,
                as_of_date,
                max_age_days,
            )
        ]

        if not same_rank:
            continue

        same_rank.sort(
            key=lambda x: (
                x.get(
                    "end",
                    "",
                ),
                x.get(
                    "filed",
                    "",
                ),
                get_form_priority(
                    x,
                    INSTANT_FORM_PRIORITY,
                ),
            ),
            reverse=True,
        )

        return same_rank[0]

    return None


def normalize_debt(
    data: dict,
    as_of_date: date,
    *,
    max_age_days: int = 400,
) -> dict:

    combined = select_latest_candidate_observation(
        data,
        "combined_debt",
        CONCEPTS["combined_debt"],
        ("us-gaap",),
        as_of_date,
        max_age_days,
    )

    current = select_latest_candidate_observation(
        data,
        "current_debt",
        CONCEPTS["current_debt"],
        ("us-gaap",),
        as_of_date,
        max_age_days,
    )

    noncurrent = select_latest_candidate_observation(
        data,
        "noncurrent_debt",
        CONCEPTS["noncurrent_debt"],
        ("us-gaap",),
        as_of_date,
        max_age_days,
    )

    current_result = (
        observation_to_result(
            "current_debt",
            current,
            source_type="INSTANT",
        )
        if current is not None
        else build_missing_result(
            "current_debt",
            "No recent current debt observation found.",
        )
    )

    noncurrent_result = (
        observation_to_result(
            "noncurrent_debt",
            noncurrent,
            source_type="INSTANT",
        )
        if noncurrent is not None
        else build_missing_result(
            "noncurrent_debt",
            "No recent non-current debt observation found.",
        )
    )

    # --------------------------------------------------------
    # Case 1: no combined debt and no components.
    # --------------------------------------------------------

    if (
        combined is None
        and current is None
        and noncurrent is None
    ):

        return {
            "metric": "total_debt",
            "status": "MISSING",
            "source_type": None,
            "value": None,
            "unit": "USD",
            "components": {
                "current_debt": current_result,
                "noncurrent_debt": noncurrent_result,
            },
            "reason": (
                "No recent debt observation found."
            ),
        }

    # --------------------------------------------------------
    # Case 2: combined debt exists.
    #
    # If combined debt is materially older than both current
    # and non-current components, prefer the fresher components.
    #
    # This is important for cases such as LLY where an older
    # combined debt concept may coexist with newer components.
    # --------------------------------------------------------

    if combined is not None:

        combined_end = parse_date(
            combined.get("end")
        )

        component_ends = []

        for component in [
            current,
            noncurrent,
        ]:

            if component is None:
                continue

            component_end = parse_date(
                component.get("end")
            )

            if component_end is not None:
                component_ends.append(
                    component_end
                )

        latest_component_end = (
            max(component_ends)
            if component_ends
            else None
        )

        combined_is_materially_older = False

        if (
            combined_end is not None
            and latest_component_end is not None
        ):

            gap = (
                latest_component_end
                - combined_end
            ).days

            if gap > 45:
                combined_is_materially_older = True

        if not combined_is_materially_older:

            combined_result = (
                observation_to_result(
                    "total_debt",
                    combined,
                    source_type="COMBINED_DEBT",
                )
            )

            combined_result["components"] = {
                "combined_debt": compact_source(
                    combined
                ),
                "current_debt": current_result,
                "noncurrent_debt": noncurrent_result,
            }

            return combined_result

    # --------------------------------------------------------
    # Case 3: use current + non-current.
    # --------------------------------------------------------

    if (
        current is not None
        and noncurrent is not None
    ):

        current_value = current.get(
            "val"
        )

        noncurrent_value = noncurrent.get(
            "val"
        )

        if (
            isinstance(
                current_value,
                (int, float),
            )
            and
            isinstance(
                noncurrent_value,
                (int, float),
            )
        ):

            total_value = (
                current_value
                + noncurrent_value
            )

            latest_end = max(
                current.get(
                    "end",
                    "",
                ),
                noncurrent.get(
                    "end",
                    "",
                ),
            )

            result = {
                "metric": "total_debt",
                "status": "OK",
                "source_type": (
                    "CURRENT_PLUS_NONCURRENT"
                ),
                "namespace": None,
                "concept": None,
                "unit": "USD",
                "value": total_value,
                "period_start": None,
                "period_end": latest_end,
                "filing_date": max(
                    current.get(
                        "filed",
                        "",
                    ),
                    noncurrent.get(
                        "filed",
                        "",
                    ),
                ),
                "form": None,
                "fy": None,
                "fp": None,
                "frame": None,
                "accession": None,
                "components": {
                    "current_debt": current_result,
                    "noncurrent_debt": noncurrent_result,
                },
            }

            return result

    # --------------------------------------------------------
    # Case 4: only one component exists.
    #
    # Never interpret one component as total debt.
    # --------------------------------------------------------

    return {
        "metric": "total_debt",
        "status": "INCOMPLETE",
        "source_type": None,
        "namespace": None,
        "concept": None,
        "unit": "USD",
        "value": None,
        "period_start": None,
        "period_end": None,
        "filing_date": None,
        "form": None,
        "fy": None,
        "fp": None,
        "frame": None,
        "accession": None,
        "components": {
            "combined_debt": (
                compact_source(combined)
                if combined is not None
                else None
            ),
            "current_debt": current_result,
            "noncurrent_debt": noncurrent_result,
        },
        "reason": (
            "Only one debt component is available; "
            "total debt is not inferred."
        ),
    }


# ============================================================
# NORMALIZE COMPANY
# ============================================================

def normalize_company(
    ticker: str,
    data: dict,
    company_type: str,
    *,
    as_of_date: str | date | None = None,
    max_instant_age_days: int = 400,
) -> dict:

    as_of = normalize_as_of_date(
        as_of_date
    )

    print()
    print("=" * 70)
    print(
        f"NORMALIZING {ticker}"
    )
    print(
        f"Company type: {company_type}"
    )
    print(
        f"As-of date: {as_of.isoformat()}"
    )
    print("=" * 70)

    # --------------------------------------------------------
    # Duration metrics
    # --------------------------------------------------------

    duration_metrics = {}

    for metric_name in [
        "revenue",
        "net_income",
        "diluted_eps",
    ]:

        duration_metrics[metric_name] = (
            normalize_duration_metric(
                data,
                metric_name,
                CONCEPTS[metric_name],
                ("us-gaap",),
                as_of,
            )
        )

    # --------------------------------------------------------
    # Non-financial duration metrics
    # --------------------------------------------------------

    if company_type == "NON_FINANCIAL":

        for metric_name in [
            "operating_income",
            "cfo",
            "capex",
        ]:

            duration_metrics[metric_name] = (
                normalize_duration_metric(
                    data,
                    metric_name,
                    CONCEPTS[metric_name],
                    ("us-gaap",),
                    as_of,
                )
            )

    else:

        duration_metrics[
            "operating_income"
        ] = build_not_applicable_result(
            "operating_income",
            (
                "Generic operating income framework "
                "is not used for financial companies."
            ),
        )

        duration_metrics[
            "cfo"
        ] = build_not_applicable_result(
            "cfo",
            (
                "Generic CFO/FCF framework "
                "is not used for financial companies."
            ),
        )

        duration_metrics[
            "capex"
        ] = build_not_applicable_result(
            "capex",
            (
                "Generic CapEx/FCF framework "
                "is not used for financial companies."
            ),
        )

    # --------------------------------------------------------
    # Instant metrics
    # --------------------------------------------------------

    cash = normalize_instant_metric(
        data,
        "cash",
        CONCEPTS["cash"],
        ("us-gaap",),
        as_of,
        max_age_days=max_instant_age_days,
    )

    shares = normalize_instant_metric(
        data,
        "shares_outstanding",
        CONCEPTS["shares_outstanding"],
        ("dei", "us-gaap"),
        as_of,
        max_age_days=max_instant_age_days,
    )

    # --------------------------------------------------------
    # Debt
    # --------------------------------------------------------

    if company_type == "NON_FINANCIAL":

        debt = normalize_debt(
            data,
            as_of,
            max_age_days=max_instant_age_days,
        )

    else:

        debt = build_not_applicable_result(
            "total_debt",
            (
                "Generic EV debt framework is not "
                "used for financial companies."
            ),
        )

        debt["components"] = {
            "current_debt": build_not_applicable_result(
                "current_debt",
                (
                    "Generic industrial debt framework "
                    "is not used for financial companies."
                ),
            ),
            "noncurrent_debt": build_not_applicable_result(
                "noncurrent_debt",
                (
                    "Generic industrial debt framework "
                    "is not used for financial companies."
                ),
            ),
        }

    # --------------------------------------------------------
    # Result
    # --------------------------------------------------------

    normalized = {
        "normalizer_version": "0.1",

        "ticker": ticker,

        "entity_name": data.get(
            "entityName"
        ),

        "cik": data.get(
            "cik"
        ),

        "company_type": company_type,

        "as_of_date": as_of.isoformat(),

        "retrieved_at": datetime.now(
            timezone.utc
        ).isoformat(),

        "metrics": {
            "revenue": duration_metrics[
                "revenue"
            ],

            "net_income": duration_metrics[
                "net_income"
            ],

            "diluted_eps": duration_metrics[
                "diluted_eps"
            ],

            "operating_income": duration_metrics[
                "operating_income"
            ],

            "cfo": duration_metrics[
                "cfo"
            ],

            "capex": duration_metrics[
                "capex"
            ],

            "cash": cash,

            "total_debt": debt,

            "shares_outstanding": shares,
        },
    }

    return normalized


# ============================================================
# VALIDATION
# ============================================================

def validate_metric_structure(
    metric_name: str,
    metric_data: dict,
) -> list[str]:

    failures = []

    status = metric_data.get(
        "status"
    )

    if status not in {
        "OK",
        "MISSING",
        "STALE",
        "INCOMPLETE",
        "NOT_APPLICABLE",
    }:

        failures.append(
            f"{metric_name}: invalid status {status}"
        )

    if "annual" in metric_data:

        if not isinstance(
            metric_data["annual"],
            dict,
        ):

            failures.append(
                f"{metric_name}: annual is not dict"
            )

    if "quarters" in metric_data:

        if not isinstance(
            metric_data["quarters"],
            dict,
        ):

            failures.append(
                f"{metric_name}: quarters is not dict"
            )

    return failures


def validate_normalized_data(
    normalized: dict,
) -> list[str]:

    failures = []

    ticker = normalized.get(
        "ticker"
    )

    company_type = normalized.get(
        "company_type"
    )

    print()
    print(
        f"=== Normalization Validation: {ticker} ==="
    )

    print(
        f"Company type: {company_type}"
    )

    print(
        f"As-of date: "
        f"{normalized.get('as_of_date')}"
    )

    # --------------------------------------------------------
    # Required metrics
    # --------------------------------------------------------

    required_metrics = [
        "revenue",
        "net_income",
        "diluted_eps",
        "cash",
        "shares_outstanding",
        "total_debt",
    ]

    if company_type == "NON_FINANCIAL":

        required_metrics.extend(
            [
                "operating_income",
                "cfo",
                "capex",
            ]
        )

    # --------------------------------------------------------
    # Validate each metric
    # --------------------------------------------------------

    for metric_name in required_metrics:

        metric_data = normalized[
            "metrics"
        ].get(
            metric_name
        )

        if metric_data is None:

            print(
                f"[FAIL] {metric_name}: missing object"
            )

            failures.append(
                metric_name
            )

            continue

        metric_failures = (
            validate_metric_structure(
                metric_name,
                metric_data,
            )
        )

        if metric_failures:

            for failure in metric_failures:
                print(
                    f"[FAIL] {failure}"
                )

            failures.extend(
                metric_failures
            )

        else:

            print(
                f"[PASS] {metric_name}: "
                f"{metric_data.get('status')}"
            )

    # --------------------------------------------------------
    # Important warning checks
    # --------------------------------------------------------

    # EPS TTM should not be mechanically generated.
    eps = normalized[
        "metrics"
    ].get(
        "diluted_eps"
    )

    if eps is not None:

        if eps.get("ttm") is not None:

            print(
                "[FAIL] diluted_eps: "
                "TTM must not be mechanically summed."
            )

            failures.append(
                "diluted_eps_ttm"
            )

        else:

            print(
                "[PASS] diluted_eps: "
                "TTM not mechanically summed"
            )

    # --------------------------------------------------------
    # Total debt
    # --------------------------------------------------------

    total_debt = normalized[
        "metrics"
    ].get(
        "total_debt"
    )

    if total_debt is not None:

        debt_status = total_debt.get(
            "status"
        )

        if (
            company_type == "FINANCIAL"
            and
            debt_status == "NOT_APPLICABLE"
        ):

            print(
                "[PASS] total_debt: "
                "NOT_APPLICABLE for financial company"
            )

        elif debt_status == "OK":

            print(
                f"[PASS] total_debt: "
                f"{total_debt.get('value')}"
            )

        elif debt_status in {
            "MISSING",
            "INCOMPLETE",
        }:

            print(
                f"[WARN] total_debt: "
                f"{debt_status}"
            )

        else:

            print(
                f"[FAIL] total_debt: "
                f"unexpected status {debt_status}"
            )

            failures.append(
                "total_debt"
            )

    # --------------------------------------------------------
    # Final
    # --------------------------------------------------------

    if failures:

        print()
        print(
            f"[FAIL] {ticker} "
            f"normalization validation "
            f"issues: {', '.join(failures)}"
        )

    else:

        print()
        print(
            f"[PASS] {ticker} "
            f"normalization validation complete."
        )

    return failures


# ============================================================
# JSON I/O
# ============================================================

def load_json(
    path: Path,
) -> dict:

    with path.open(
        "r",
        encoding="utf-8",
    ) as f:

        return json.load(f)


def save_json(
    path: Path,
    data: dict,
) -> None:

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2,
        )


# ============================================================
# FILE NORMALIZATION
# ============================================================

def normalize_raw_file(
    ticker: str,
    raw_path: Path,
    *,
    company_type: str,
    as_of_date: str | date | None = None,
    output_path: Path | None = None,
) -> dict:

    print()
    print(
        f"Loading raw SEC file: {raw_path}"
    )

    data = load_json(
        raw_path
    )

    normalized = normalize_company(
        ticker,
        data,
        company_type,
        as_of_date=as_of_date,
    )

    failures = validate_normalized_data(
        normalized
    )

    if output_path is None:

        output_path = (
            PROCESSED_DIR
            /
            f"{ticker}_fundamentals.json"
        )

    save_json(
        output_path,
        normalized,
    )

    print(
        f"[PASS] Normalized file written: "
        f"{output_path}"
    )

    if failures:

        print(
            f"[WARN] {ticker} has "
            f"{len(failures)} validation issue(s)."
        )

    else:

        print(
            f"[PASS] {ticker} normalization complete."
        )

    return normalized


# ============================================================
# MAIN
# ============================================================

def main():

    RAW_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    PROCESSED_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    as_of = today_new_york()

    print(
        "=== SEC Financial Normalizer v0.1 ==="
    )

    print(
        f"As-of date: {as_of.isoformat()}"
    )

    print()

    success_count = 0
    processed_count = 0

    for ticker, config in DEFAULT_TICKERS.items():

        raw_file = (
            RAW_DIR
            /
            f"{ticker}_companyfacts.json"
        )

        if not raw_file.exists():

            print(
                f"[WARN] {ticker}: "
                f"raw file not found: {raw_file}"
            )

            continue

        processed_count += 1

        try:

            output_file = (
                PROCESSED_DIR
                /
                f"{ticker}_fundamentals.json"
            )

            normalized = normalize_raw_file(
                ticker,
                raw_file,
                company_type=config[
                    "company_type"
                ],
                as_of_date=as_of,
                output_path=output_file,
            )

            failures = (
                validate_normalized_data(
                    normalized
                )
            )

            if not failures:
                success_count += 1

        except Exception as exc:

            print(
                f"[FAIL] {ticker}: "
                f"{type(exc).__name__}: {exc}"
            )

        print(
            "-" * 70
        )

    print()

    print(
        f"Result: "
        f"{success_count}/{processed_count} "
        f"processed tickers passed validation."
    )

    if processed_count == 0:

        raise RuntimeError(
            "No raw SEC Company Facts files found."
        )

    if success_count != processed_count:

        raise RuntimeError(
            "SEC normalization validation failed."
        )

    print()
    print(
        "[PASS] SEC Financial Normalizer v0.1 complete."
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()