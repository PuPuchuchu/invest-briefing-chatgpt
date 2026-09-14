from __future__ import annotations

from datetime import date, datetime
from typing import Any


# ============================================================
# CONFIGURATION
# ============================================================

SCHEMA_VERSION = "sec_history_v0.1"

ANNUAL_FORM = "10-K"
QUARTERLY_FORM = "10-Q"

# Approximate duration ranges used only for classification.
# SEC reporting periods are not required to be exactly these lengths.
Q1_MIN_DAYS = 70
Q1_MAX_DAYS = 110

YTD_6M_MIN_DAYS = 150
YTD_6M_MAX_DAYS = 210

YTD_9M_MIN_DAYS = 240
YTD_9M_MAX_DAYS = 300

FY_MIN_DAYS = 300
FY_MAX_DAYS = 400


# ============================================================
# BASIC HELPERS
# ============================================================

def _parse_date(value: Any) -> date | None:
    """
    Parse YYYY-MM-DD into datetime.date.

    Returns None for invalid/missing values.
    """
    if not isinstance(value, str):
        return None

    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _duration_days(observation: dict) -> int | None:
    """
    Return inclusive duration in days based on start/end.
    """
    start = _parse_date(observation.get("start"))
    end = _parse_date(observation.get("end"))

    if start is None or end is None:
        return None

    if end < start:
        return None

    return (end - start).days + 1


def _is_numeric(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
    )


def _filing_sort_key(observation: dict) -> tuple:
    """
    Sort by filing date first.

    This is deliberate.

    For historical investment analysis, information availability
    at filing time matters more than simply choosing the latest
    period_end.
    """
    return (
        observation.get("filed") or "",
        observation.get("end") or "",
        observation.get("start") or "",
        observation.get("accession") or "",
    )


# ============================================================
# OBSERVATION CLASSIFICATION
# ============================================================

def is_duration_observation(observation: dict) -> bool:
    """
    True when both start and end are present.
    """
    return (
        isinstance(observation, dict)
        and observation.get("start") is not None
        and observation.get("end") is not None
    )


def is_annual_observation(observation: dict) -> bool:
    """
    True for 10-K FY duration observations.
    """
    if not is_duration_observation(observation):
        return False

    return (
        observation.get("form") == ANNUAL_FORM
        and observation.get("fp") == "FY"
    )


def is_quarterly_form_observation(observation: dict) -> bool:
    """
    True for 10-Q observations.
    """
    return (
        isinstance(observation, dict)
        and observation.get("form") == QUARTERLY_FORM
        and is_duration_observation(observation)
    )


def classify_duration_observation(observation: dict) -> str:
    """
    Classify a duration observation.

    Possible results:
        annual
        q1
        ytd_6m
        ytd_9m
        unknown
    """

    if not isinstance(observation, dict):
        return "unknown"

    if is_annual_observation(observation):
        return "annual"

    if not is_quarterly_form_observation(observation):
        return "unknown"

    fp = observation.get("fp")
    days = _duration_days(observation)

    if days is None:
        return "unknown"

    # Q1 is usually the only 10-Q period that represents a
    # standalone quarter in duration form.
    if fp == "Q1" and Q1_MIN_DAYS <= days <= Q1_MAX_DAYS:
        return "q1"

    # Q2 filing commonly contains 6-month YTD data.
    if fp == "Q2" and YTD_6M_MIN_DAYS <= days <= YTD_6M_MAX_DAYS:
        return "ytd_6m"

    # Q3 filing commonly contains 9-month YTD data.
    if fp == "Q3" and YTD_9M_MIN_DAYS <= days <= YTD_9M_MAX_DAYS:
        return "ytd_9m"

    return "unknown"


# ============================================================
# OBSERVATION FILTERING
# ============================================================

def filter_valid_duration_observations(
    observations: list[dict],
) -> list[dict]:
    """
    Keep observations with valid start/end dates and numeric values.

    No deduplication is performed here.
    """
    result = []

    for observation in observations:
        if not isinstance(observation, dict):
            continue

        if not is_duration_observation(observation):
            continue

        if _parse_date(observation.get("start")) is None:
            continue

        if _parse_date(observation.get("end")) is None:
            continue

        if not _is_numeric(observation.get("value")):
            continue

        result.append(observation)

    return result


def sort_by_filing_date(
    observations: list[dict],
    newest_first: bool = False,
) -> list[dict]:
    """
    Sort observations by filing date.

    Default:
        oldest filing first

    newest_first=True:
        newest filing first
    """
    return sorted(
        observations,
        key=_filing_sort_key,
        reverse=newest_first,
    )


# ============================================================
# ANNUAL HISTORY
# ============================================================

def extract_annual_history(
    observations: list[dict],
) -> list[dict]:
    """
    Extract annual 10-K/FY observations.

    One observation per fiscal year is retained.

    When duplicate observations exist for the same FY,
    the earliest filing is preferred.

    This prevents later filings/restatements from silently
    replacing what was originally known at the time.
    """

    valid = filter_valid_duration_observations(observations)

    annual = [
        obs
        for obs in valid
        if is_annual_observation(obs)
    ]

    annual.sort(
        key=lambda obs: (
            obs.get("fy") if isinstance(obs.get("fy"), int) else -1,
            obs.get("filed") or "",
            obs.get("end") or "",
        )
    )

    selected: dict[int, dict] = {}

    for observation in annual:
        fy = observation.get("fy")

        if not isinstance(fy, int):
            continue

        if fy not in selected:
            selected[fy] = observation

    return [
        selected[fy]
        for fy in sorted(selected.keys())
    ]


# ============================================================
# QUARTERLY / YTD HISTORY
# ============================================================

def extract_quarterly_history(
    observations: list[dict],
) -> dict[str, list[dict]]:
    """
    Classify 10-Q duration observations into:

        q1
        ytd_6m
        ytd_9m
        unknown

    The original observations are preserved.
    """

    valid = filter_valid_duration_observations(observations)

    result = {
        "q1": [],
        "ytd_6m": [],
        "ytd_9m": [],
        "unknown": [],
    }

    for observation in valid:
        classification = classify_duration_observation(
            observation
        )

        result[classification].append(observation)

    for key in result:
        result[key] = sort_by_filing_date(
            result[key],
            newest_first=False,
        )

    return result


# ============================================================
# YTD → STANDALONE QUARTER
# ============================================================

def _same_fiscal_year(
    left: dict,
    right: dict,
) -> bool:
    """
    Compare fiscal year using FY when available.
    """
    left_fy = left.get("fy")
    right_fy = right.get("fy")

    if isinstance(left_fy, int) and isinstance(right_fy, int):
        return left_fy == right_fy

    left_end = _parse_date(left.get("end"))
    right_end = _parse_date(right.get("end"))

    if left_end is None or right_end is None:
        return False

    return left_end.year == right_end.year


def _make_reconstructed_quarter(
    source_observation: dict,
    previous_observation: dict,
    quarter: str,
) -> dict:
    """
    Construct a standalone quarter by subtracting the previous
    YTD observation from the current YTD observation.

    Example:
        H1 = 55
        Q1 = 25

        Q2 = 55 - 25 = 30
    """

    value = (
        float(source_observation["value"])
        - float(previous_observation["value"])
    )

    source_start = source_observation.get("start")
    source_end = source_observation.get("end")

    previous_end = previous_observation.get("end")

    return {
        "status": "OK",
        "value": value,
        "period_type": "standalone_quarter",
        "quarter": quarter,
        "period_start": previous_end,
        "period_end": source_end,
        "filed": source_observation.get("filed"),
        "form": source_observation.get("form"),
        "fy": source_observation.get("fy"),
        "fp": source_observation.get("fp"),
        "frame": source_observation.get("frame"),
        "accession": source_observation.get("accession"),
        "source": {
            "current_observation": {
                "start": source_observation.get("start"),
                "end": source_observation.get("end"),
                "value": source_observation.get("value"),
                "filed": source_observation.get("filed"),
                "accession": source_observation.get("accession"),
            },
            "previous_observation": {
                "start": previous_observation.get("start"),
                "end": previous_observation.get("end"),
                "value": previous_observation.get("value"),
                "filed": previous_observation.get("filed"),
                "accession": previous_observation.get("accession"),
            },
        },
    }


def reconstruct_standalone_quarters(
    observations: list[dict],
) -> list[dict]:
    """
    Reconstruct standalone quarters from SEC YTD observations.

    v0.1 policy:

        Q1:
            use standalone Q1 observation directly.

        Q2:
            H1 YTD - Q1

        Q3:
            9M YTD - H1 YTD

        Q4:
            FY - 9M YTD

    Important:
        FY is taken from 10-K and may be filed after Q3.
        The resulting Q4 carries the FY filing date because
        that is when Q4 information became publicly available.

    Records are grouped by fiscal year.

    The function requires comparable fiscal periods.
    """

    valid = filter_valid_duration_observations(observations)

    classified = extract_quarterly_history(valid)

    annual = extract_annual_history(valid)

    result: list[dict] = []

    # --------------------------------------------------------
    # Q1
    # --------------------------------------------------------

    for q1 in classified["q1"]:
        result.append(
            {
                "status": "OK",
                "value": float(q1["value"]),
                "period_type": "standalone_quarter",
                "quarter": "Q1",
                "period_start": q1.get("start"),
                "period_end": q1.get("end"),
                "filed": q1.get("filed"),
                "form": q1.get("form"),
                "fy": q1.get("fy"),
                "fp": q1.get("fp"),
                "frame": q1.get("frame"),
                "accession": q1.get("accession"),
                "source": {
                    "current_observation": {
                        "start": q1.get("start"),
                        "end": q1.get("end"),
                        "value": q1.get("value"),
                        "filed": q1.get("filed"),
                        "accession": q1.get("accession"),
                    }
                },
            }
        )

    # --------------------------------------------------------
    # Q2
    # --------------------------------------------------------

    q1_by_fy = {}

    for q1 in classified["q1"]:
        fy = q1.get("fy")

        if isinstance(fy, int):
            q1_by_fy[fy] = q1

    for h1 in classified["ytd_6m"]:
        fy = h1.get("fy")

        if not isinstance(fy, int):
            continue

        q1 = q1_by_fy.get(fy)

        if q1 is None:
            continue

        if not _same_fiscal_year(h1, q1):
            continue

        result.append(
            _make_reconstructed_quarter(
                source_observation=h1,
                previous_observation=q1,
                quarter="Q2",
            )
        )

    # --------------------------------------------------------
    # Q3
    # --------------------------------------------------------

    h1_by_fy = {}

    for h1 in classified["ytd_6m"]:
        fy = h1.get("fy")

        if isinstance(fy, int):
            h1_by_fy[fy] = h1

    for ytd_9m in classified["ytd_9m"]:
        fy = ytd_9m.get("fy")

        if not isinstance(fy, int):
            continue

        h1 = h1_by_fy.get(fy)

        if h1 is None:
            continue

        if not _same_fiscal_year(ytd_9m, h1):
            continue

        result.append(
            _make_reconstructed_quarter(
                source_observation=ytd_9m,
                previous_observation=h1,
                quarter="Q3",
            )
        )

    # --------------------------------------------------------
    # Q4
    # --------------------------------------------------------

    ytd_9m_by_fy = {}

    for ytd_9m in classified["ytd_9m"]:
        fy = ytd_9m.get("fy")

        if isinstance(fy, int):
            ytd_9m_by_fy[fy] = ytd_9m

    for fy_record in annual:
        fy = fy_record.get("fy")

        if not isinstance(fy, int):
            continue

        ytd_9m = ytd_9m_by_fy.get(fy)

        if ytd_9m is None:
            continue

        if not _same_fiscal_year(fy_record, ytd_9m):
            continue

        result.append(
            _make_reconstructed_quarter(
                source_observation=fy_record,
                previous_observation=ytd_9m,
                quarter="Q4",
            )
        )

    # --------------------------------------------------------
    # Final sorting
    # --------------------------------------------------------

    result.sort(
        key=lambda observation: (
            observation.get("period_end") or "",
            observation.get("filed") or "",
            observation.get("quarter") or "",
        )
    )

    return result


# ============================================================
# HISTORY EXTRACTION FOR ONE CONCEPT
# ============================================================

def extract_concept_history(
    concept_data: dict,
) -> dict:
    """
    Extract annual and quarterly history from one SEC concept.

    Expected input:

        {
            "label": "...",
            "description": "...",
            "units": {
                "USD": [...]
            }
        }

    Output:

        {
            "annual": [...],
            "quarterly": {
                "q1": [...],
                "ytd_6m": [...],
                "ytd_9m": [...],
                "unknown": [...]
            },
            "standalone_quarters": [...]
        }
    """

    if not isinstance(concept_data, dict):
        raise TypeError("concept_data must be a dict.")

    units = concept_data.get("units")

    if not isinstance(units, dict):
        raise ValueError("concept_data['units'] must be a dict.")

    observations = []

    for unit, records in units.items():
        if not isinstance(records, list):
            continue

        for record in records:
            if not isinstance(record, dict):
                continue

            copied = dict(record)
            copied["unit"] = unit

            observations.append(copied)

    annual = extract_annual_history(observations)
    quarterly = extract_quarterly_history(observations)
    standalone = reconstruct_standalone_quarters(observations)

    return {
        "schema_version": SCHEMA_VERSION,
        "annual": annual,
        "quarterly": quarterly,
        "standalone_quarters": standalone,
    }


# ============================================================
# HISTORY VALIDATION
# ============================================================

def validate_history(
    history: dict,
) -> list[str]:
    """
    Basic structural validation.

    Returns:
        [] when valid
        list of failure identifiers otherwise
    """

    failures = []

    if not isinstance(history, dict):
        return ["root"]

    if history.get("schema_version") != SCHEMA_VERSION:
        failures.append("schema_version")

    if "annual" not in history:
        failures.append("annual")

    if "quarterly" not in history:
        failures.append("quarterly")

    if "standalone_quarters" not in history:
        failures.append("standalone_quarters")

    annual = history.get("annual")

    if not isinstance(annual, list):
        failures.append("annual.type")

    quarterly = history.get("quarterly")

    if not isinstance(quarterly, dict):
        failures.append("quarterly.type")
    else:
        for key in [
            "q1",
            "ytd_6m",
            "ytd_9m",
            "unknown",
        ]:
            if key not in quarterly:
                failures.append(f"quarterly.{key}")

    standalone = history.get("standalone_quarters")

    if not isinstance(standalone, list):
        failures.append("standalone_quarters.type")

    return failures