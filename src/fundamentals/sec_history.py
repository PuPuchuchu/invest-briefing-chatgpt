from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


# ============================================================
# CONFIGURATION
# ============================================================

SCHEMA_VERSION = "sec_history_v0.1"

BASE_DIR = Path(__file__).resolve().parents[2]

RAW_DIR = BASE_DIR / "data" / "raw" / "sec"
PROCESSED_DIR = BASE_DIR / "data" / "processed" / "fundamentals"


# Approximate duration ranges.
#
# These are intentionally broad because fiscal calendars differ
# between companies and some companies use 52/53-week calendars.
#
# The ranges are NOT used as the sole source of truth.
# Form/fp/fy/end/start information is also considered.
DURATION_RANGES = {
    "q1": (70, 110),
    "ytd_6m": (150, 210),
    "ytd_9m": (240, 300),
    "annual": (300, 400),
}


# ============================================================
# BASIC HELPERS
# ============================================================

def _parse_date(value: Any) -> date | None:
    """
    Parse an ISO date string into datetime.date.

    Returns None for invalid or missing values.
    """
    if not isinstance(value, str):
        return None

    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _duration_days(observation: dict) -> int | None:
    """
    Return inclusive duration in days.

    Example:
        2025-01-01 -> 2025-03-31
        = 90 days
    """
    start = _parse_date(observation.get("start"))
    end = _parse_date(observation.get("end"))

    if start is None or end is None:
        return None

    if end < start:
        return None

    return (end - start).days + 1


def _is_numeric(value: Any) -> bool:
    """
    Return True for finite int/float values.

    bool is intentionally excluded because bool is a subclass of int.
    """
    if isinstance(value, bool):
        return False

    if not isinstance(value, (int, float)):
        return False

    return value == value and value not in (
        float("inf"),
        float("-inf"),
    )


def _filing_sort_key(observation: dict) -> tuple:
    """
    Sort observations by information availability.

    Earlier filing date = information became public earlier.

    Secondary keys are included for deterministic ordering.
    """
    filed = _parse_date(observation.get("filed"))
    end = _parse_date(observation.get("end"))
    start = _parse_date(observation.get("start"))

    return (
        filed or date.max,
        end or date.max,
        start or date.max,
        str(observation.get("accession", "")),
    )


# ============================================================
# OBSERVATION CLASSIFICATION
# ============================================================

def is_duration_observation(observation: dict) -> bool:
    """
    Return True if observation contains a valid duration.

    Duration observations require both start and end dates.
    """
    return (
        _parse_date(observation.get("start")) is not None
        and _parse_date(observation.get("end")) is not None
    )


def is_annual_observation(observation: dict) -> bool:
    """
    Return True for annual 10-K / FY observations.

    SEC Company Facts annual observations are normally represented
    by form=10-K and fp=FY.
    """
    if not is_duration_observation(observation):
        return False

    form = observation.get("form")
    fp = observation.get("fp")

    if form != "10-K":
        return False

    if fp != "FY":
        return False

    duration = _duration_days(observation)

    if duration is None:
        return False

    min_days, max_days = DURATION_RANGES["annual"]

    return min_days <= duration <= max_days


def is_quarterly_form_observation(observation: dict) -> bool:
    """
    Return True for 10-Q duration observations.

    This intentionally checks the SEC form rather than assuming
    every duration observation is quarterly.
    """
    return (
        is_duration_observation(observation)
        and observation.get("form") == "10-Q"
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

    Classification is based primarily on form/fp and duration.
    """
    if not is_duration_observation(observation):
        return "unknown"

    # --------------------------------------------------------
    # Annual
    # --------------------------------------------------------

    if is_annual_observation(observation):
        return "annual"

    # --------------------------------------------------------
    # Quarterly 10-Q observations
    # --------------------------------------------------------

    if observation.get("form") != "10-Q":
        return "unknown"

    duration = _duration_days(observation)

    if duration is None:
        return "unknown"

    q1_min, q1_max = DURATION_RANGES["q1"]
    h1_min, h1_max = DURATION_RANGES["ytd_6m"]
    ytd9_min, ytd9_max = DURATION_RANGES["ytd_9m"]

    if q1_min <= duration <= q1_max:
        return "q1"

    if h1_min <= duration <= h1_max:
        return "ytd_6m"

    if ytd9_min <= duration <= ytd9_max:
        return "ytd_9m"

    return "unknown"


# ============================================================
# FILTERING
# ============================================================

def filter_valid_duration_observations(
    observations: list[dict],
) -> list[dict]:
    """
    Keep observations that:

    1. are dictionaries
    2. contain valid start/end dates
    3. have end >= start
    4. contain a numeric value
    """
    result = []

    for observation in observations:
        if not isinstance(observation, dict):
            continue

        if not is_duration_observation(observation):
            continue

        if not _is_numeric(observation.get("val")):
            continue

        result.append(observation)

    return result


# ============================================================
# SORTING
# ============================================================

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
    Extract annual 10-K / FY observations.

    One observation is retained per fiscal year.

    If multiple observations exist for the same FY, the earliest
    filing is preferred because it represents the earliest point
    at which the information became publicly available.
    """
    valid = filter_valid_duration_observations(observations)

    annual = [
        observation
        for observation in valid
        if is_annual_observation(observation)
    ]

    grouped: dict[Any, list[dict]] = defaultdict(list)

    for observation in annual:
        fy = observation.get("fy")

        if fy is None:
            # Without FY information we cannot safely perform
            # one-record-per-fiscal-year deduplication.
            continue

        grouped[fy].append(observation)

    result = []

    for fy, records in grouped.items():
        records = sort_by_filing_date(records)

        selected = records[0].copy()

        result.append(selected)

    result.sort(
        key=lambda observation: (
            observation.get("fy", 0),
            observation.get("end", ""),
        )
    )

    return result


# ============================================================
# QUARTERLY HISTORY
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

    Annual observations are intentionally excluded because
    they belong to annual history extraction.

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
        # ----------------------------------------------------
        # IMPORTANT:
        # Quarterly history must only contain 10-Q records.
        #
        # This prevents an annual 10-K/FY observation from
        # producing:
        #
        #     KeyError: 'annual'
        #
        # inside the quarterly result dictionary.
        # ----------------------------------------------------
        if not is_quarterly_form_observation(observation):
            continue

        classification = classify_duration_observation(
            observation
        )

        # Defensive guard.
        #
        # Even if a future classification is added to
        # classify_duration_observation(), it must not break
        # this function.
        if classification not in result:
            continue

        result[classification].append(observation)

    for key in result:
        result[key] = sort_by_filing_date(result[key])

    return result


# ============================================================
# FISCAL YEAR HELPERS
# ============================================================

def _same_fiscal_year(
    observation_a: dict,
    observation_b: dict,
) -> bool:
    """
    Return True if two observations belong to the same fiscal year.

    Prefer SEC fy when available.

    Fall back to calendar year of the end date when fy is absent.
    """
    fy_a = observation_a.get("fy")
    fy_b = observation_b.get("fy")

    if fy_a is not None and fy_b is not None:
        return fy_a == fy_b

    end_a = _parse_date(observation_a.get("end"))
    end_b = _parse_date(observation_b.get("end"))

    if end_a is None or end_b is None:
        return False

    return end_a.year == end_b.year


# ============================================================
# QUARTER RECONSTRUCTION
# ============================================================

def _make_reconstructed_quarter(
    *,
    quarter: str,
    current_observation: dict,
    previous_observation: dict | None,
) -> dict | None:
    """
    Reconstruct a standalone quarter from SEC YTD observations.

    Examples:

        Q1 = Q1

        Q2 = H1 - Q1

        Q3 = 9M - H1

        Q4 = FY - 9M

    The returned record preserves provenance.
    """
    if not _is_numeric(current_observation.get("val")):
        return None

    current_value = current_observation["val"]

    # --------------------------------------------------------
    # Q1 is already a standalone quarter.
    # --------------------------------------------------------

    if quarter == "Q1":
        return {
            "quarter": "Q1",
            "value": current_value,
            "period_start": current_observation.get("start"),
            "period_end": current_observation.get("end"),
            "filed": current_observation.get("filed"),
            "form": current_observation.get("form"),
            "fy": current_observation.get("fy"),
            "accession": current_observation.get("accession"),
            "reconstructed": False,
            "source": {
                "current": current_observation.copy(),
                "previous": None,
            },
        }

    # --------------------------------------------------------
    # Q2 / Q3 / Q4 require a previous cumulative period.
    # --------------------------------------------------------

    if previous_observation is None:
        return None

    if not _is_numeric(previous_observation.get("val")):
        return None

    previous_value = previous_observation["val"]

    value = current_value - previous_value

    previous_end = _parse_date(
        previous_observation.get("end")
    )

    current_end = _parse_date(
        current_observation.get("end")
    )

    if previous_end is None or current_end is None:
        return None

    # --------------------------------------------------------
    # The standalone quarter starts the day after the
    # previous cumulative period ended.
    #
    # Example:
    # H1 ends 2025-06-30
    # Q2 starts 2025-07-01
    # --------------------------------------------------------

    period_start = previous_end + timedelta(days=1)

    return {
        "quarter": quarter,
        "value": value,
        "period_start": period_start.isoformat(),
        "period_end": current_observation.get("end"),
        "filed": current_observation.get("filed"),
        "form": current_observation.get("form"),
        "fy": current_observation.get("fy"),
        "accession": current_observation.get("accession"),
        "reconstructed": True,
        "source": {
            "current": current_observation.copy(),
            "previous": previous_observation.copy(),
        },
    }


def _select_one_observation(
    observations: list[dict],
    fy: Any,
) -> dict | None:
    """
    Select one observation for a fiscal year.

    The earliest filing is preferred.

    This is important because SEC Company Facts can contain
    duplicate observations caused by amended filings or repeated
    disclosures.
    """
    candidates = [
        observation
        for observation in observations
        if observation.get("fy") == fy
    ]

    if not candidates:
        return None

    candidates = sort_by_filing_date(candidates)

    return candidates[0]


def reconstruct_standalone_quarters(
    observations: list[dict],
) -> list[dict]:
    """
    Reconstruct standalone quarterly values.

    Logic:

        Q1 = Q1

        Q2 = H1 - Q1

        Q3 = 9M - H1

        Q4 = FY - 9M

    The reconstruction is performed separately for each fiscal year.

    Q4 filing provenance uses the FY / 10-K filing date because
    Q4 results are only known publicly when the annual filing is
    released.
    """
    valid = filter_valid_duration_observations(observations)

    # --------------------------------------------------------
    # Separate annual and quarterly observations.
    # --------------------------------------------------------

    annual = [
        observation
        for observation in valid
        if is_annual_observation(observation)
    ]

    quarterly = [
        observation
        for observation in valid
        if is_quarterly_form_observation(observation)
    ]

    classified = extract_quarterly_history(quarterly)

    # --------------------------------------------------------
    # Build fiscal-year universe.
    # --------------------------------------------------------

    fiscal_years = set()

    for observation in annual:
        if observation.get("fy") is not None:
            fiscal_years.add(observation.get("fy"))

    for records in classified.values():
        for observation in records:
            if observation.get("fy") is not None:
                fiscal_years.add(observation.get("fy"))

    result = []

    # --------------------------------------------------------
    # Process each fiscal year independently.
    # --------------------------------------------------------

    for fy in sorted(fiscal_years):
        q1 = _select_one_observation(
            classified["q1"],
            fy,
        )

        h1 = _select_one_observation(
            classified["ytd_6m"],
            fy,
        )

        ytd9 = _select_one_observation(
            classified["ytd_9m"],
            fy,
        )

        fy_observation = _select_one_observation(
            annual,
            fy,
        )

        # ----------------------------------------------------
        # Q1
        # ----------------------------------------------------

        if q1 is not None:
            reconstructed_q1 = _make_reconstructed_quarter(
                quarter="Q1",
                current_observation=q1,
                previous_observation=None,
            )

            if reconstructed_q1 is not None:
                result.append(reconstructed_q1)

        # ----------------------------------------------------
        # Q2 = H1 - Q1
        # ----------------------------------------------------

        if (
            h1 is not None
            and q1 is not None
            and _same_fiscal_year(h1, q1)
        ):
            reconstructed_q2 = _make_reconstructed_quarter(
                quarter="Q2",
                current_observation=h1,
                previous_observation=q1,
            )

            if reconstructed_q2 is not None:
                result.append(reconstructed_q2)

        # ----------------------------------------------------
        # Q3 = 9M - H1
        # ----------------------------------------------------

        if (
            ytd9 is not None
            and h1 is not None
            and _same_fiscal_year(ytd9, h1)
        ):
            reconstructed_q3 = _make_reconstructed_quarter(
                quarter="Q3",
                current_observation=ytd9,
                previous_observation=h1,
            )

            if reconstructed_q3 is not None:
                result.append(reconstructed_q3)

        # ----------------------------------------------------
        # Q4 = FY - 9M
        #
        # Q4 uses the annual filing date.
        # ----------------------------------------------------

        if (
            fy_observation is not None
            and ytd9 is not None
            and _same_fiscal_year(fy_observation, ytd9)
        ):
            reconstructed_q4 = _make_reconstructed_quarter(
                quarter="Q4",
                current_observation=fy_observation,
                previous_observation=ytd9,
            )

            if reconstructed_q4 is not None:
                result.append(reconstructed_q4)

    # --------------------------------------------------------
    # Sort chronologically.
    # --------------------------------------------------------

    result.sort(
        key=lambda observation: (
            observation.get("period_end", ""),
            observation.get("quarter", ""),
        )
    )

    return result


# ============================================================
# CONCEPT HISTORY
# ============================================================

def extract_concept_history(
    concept_data: dict,
) -> dict:
    """
    Extract annual, quarterly and standalone-quarter history
    from one SEC Company Facts concept.

    Expected structure:

        {
            "label": "...",
            "description": "...",
            "units": {
                "USD": [...],
                ...
            }
        }

    v0.1 behavior:
        All units are flattened into one observation list.

    Production hardening for unit selection will be added after
    real SEC validation confirms actual Company Facts behavior.
    """
    if not isinstance(concept_data, dict):
        raise ValueError(
            "concept_data must be a dictionary"
        )

    units = concept_data.get("units")

    if not isinstance(units, dict):
        raise ValueError(
            "concept_data.units must be a dictionary"
        )

    observations = []

    for unit_name, unit_observations in units.items():
        if not isinstance(unit_observations, list):
            continue

        for observation in unit_observations:
            if not isinstance(observation, dict):
                continue

            copied = observation.copy()

            # Preserve the original SEC unit explicitly.
            copied["_unit"] = unit_name

            observations.append(copied)

    annual = extract_annual_history(observations)

    quarterly = extract_quarterly_history(observations)

    standalone_quarters = reconstruct_standalone_quarters(
        observations
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "label": concept_data.get("label"),
        "description": concept_data.get("description"),
        "annual": annual,
        "quarterly": quarterly,
        "standalone_quarters": standalone_quarters,
    }


# ============================================================
# VALIDATION
# ============================================================

def validate_history(
    history: dict,
) -> list[str]:
    """
    Validate extracted history structure.

    Returns a list of validation errors.

    Empty list means validation passed.
    """
    errors = []

    if not isinstance(history, dict):
        return ["history must be a dictionary"]

    required_keys = {
        "schema_version",
        "annual",
        "quarterly",
        "standalone_quarters",
    }

    for key in required_keys:
        if key not in history:
            errors.append(
                f"missing required key: {key}"
            )

    if errors:
        return errors

    if history.get("schema_version") != SCHEMA_VERSION:
        errors.append(
            "invalid schema_version"
        )

    if not isinstance(history.get("annual"), list):
        errors.append(
            "annual must be a list"
        )

    quarterly = history.get("quarterly")

    if not isinstance(quarterly, dict):
        errors.append(
            "quarterly must be a dictionary"
        )
    else:
        required_quarterly_keys = {
            "q1",
            "ytd_6m",
            "ytd_9m",
            "unknown",
        }

        for key in required_quarterly_keys:
            if key not in quarterly:
                errors.append(
                    f"missing quarterly key: {key}"
                )

            elif not isinstance(quarterly[key], list):
                errors.append(
                    f"quarterly.{key} must be a list"
                )

    if not isinstance(
        history.get("standalone_quarters"),
        list,
    ):
        errors.append(
            "standalone_quarters must be a list"
        )

    # --------------------------------------------------------
    # Validate annual records.
    # --------------------------------------------------------

    for index, observation in enumerate(
        history.get("annual", [])
    ):
        if not isinstance(observation, dict):
            errors.append(
                f"annual[{index}] must be a dictionary"
            )
            continue

        if not _is_numeric(observation.get("val")):
            errors.append(
                f"annual[{index}] has invalid val"
            )

        if not is_duration_observation(observation):
            errors.append(
                f"annual[{index}] has invalid duration"
            )

    # --------------------------------------------------------
    # Validate quarterly records.
    # --------------------------------------------------------

    quarterly = history.get("quarterly", {})

    if isinstance(quarterly, dict):
        for key, records in quarterly.items():
            if not isinstance(records, list):
                continue

            for index, observation in enumerate(records):
                if not isinstance(observation, dict):
                    errors.append(
                        f"quarterly.{key}[{index}] "
                        "must be a dictionary"
                    )
                    continue

                if not _is_numeric(
                    observation.get("val")
                ):
                    errors.append(
                        f"quarterly.{key}[{index}] "
                        "has invalid val"
                    )

                if not is_duration_observation(
                    observation
                ):
                    errors.append(
                        f"quarterly.{key}[{index}] "
                        "has invalid duration"
                    )

    # --------------------------------------------------------
    # Validate standalone quarters.
    # --------------------------------------------------------

    standalone = history.get(
        "standalone_quarters",
        [],
    )

    for index, quarter in enumerate(standalone):
        if not isinstance(quarter, dict):
            errors.append(
                f"standalone_quarters[{index}] "
                "must be a dictionary"
            )
            continue

        if quarter.get("quarter") not in {
            "Q1",
            "Q2",
            "Q3",
            "Q4",
        }:
            errors.append(
                f"standalone_quarters[{index}] "
                "has invalid quarter"
            )

        if not _is_numeric(
            quarter.get("value")
        ):
            errors.append(
                f"standalone_quarters[{index}] "
                "has invalid value"
            )

        if _parse_date(
            quarter.get("period_start")
        ) is None:
            errors.append(
                f"standalone_quarters[{index}] "
                "has invalid period_start"
            )

        if _parse_date(
            quarter.get("period_end")
        ) is None:
            errors.append(
                f"standalone_quarters[{index}] "
                "has invalid period_end"
            )

    return errors


# ============================================================
# PUBLIC EXPORTS
# ============================================================

__all__ = [
    "SCHEMA_VERSION",
    "DURATION_RANGES",
    "is_duration_observation",
    "is_annual_observation",
    "is_quarterly_form_observation",
    "classify_duration_observation",
    "filter_valid_duration_observations",
    "sort_by_filing_date",
    "extract_annual_history",
    "extract_quarterly_history",
    "reconstruct_standalone_quarters",
    "extract_concept_history",
    "validate_history",
]