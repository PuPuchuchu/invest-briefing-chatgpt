from __future__ import annotations

from datetime import date
from math import isfinite
from typing import Any


# ============================================================
# CONFIGURATION
# ============================================================

SCHEMA_VERSION = "growth_v0.1"

VALID_STATUSES = {
    "OK",
    "MISSING",
    "INVALID",
    "NOT_APPLICABLE",
}

GROWTH_METRICS = [
    "revenue_yoy",
    "operating_income_yoy",
    "eps_yoy",
    "fcf_yoy",
    "revenue_cagr_3y",
]

GROWTH_WEIGHTS = {
    "revenue_yoy": 0.25,
    "operating_income_yoy": 0.20,
    "eps_yoy": 0.25,
    "fcf_yoy": 0.20,
    "revenue_cagr_3y": 0.10,
}

MIN_VALID_COMPONENTS = 3


# ============================================================
# BASIC HELPERS
# ============================================================

def _is_number(value: Any) -> bool:
    """
    Return True only for finite int/float values.
    bool is intentionally excluded.
    """
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and isfinite(float(value))
    )


def _build_ok_metric(
    metric_name: str,
    value: float,
    *,
    reason: str | None = None,
    source: list[str] | None = None,
) -> dict:
    result = {
        "metric": metric_name,
        "status": "OK",
        "value": float(value),
    }

    if reason is not None:
        result["reason"] = reason

    if source is not None:
        result["source"] = source

    return result


def _build_missing_metric(
    metric_name: str,
    reason: str,
    *,
    source: list[str] | None = None,
) -> dict:
    result = {
        "metric": metric_name,
        "status": "MISSING",
        "value": None,
        "reason": reason,
    }

    if source is not None:
        result["source"] = source

    return result


def _build_invalid_metric(
    metric_name: str,
    reason: str,
    *,
    source: list[str] | None = None,
) -> dict:
    result = {
        "metric": metric_name,
        "status": "INVALID",
        "value": None,
        "reason": reason,
    }

    if source is not None:
        result["source"] = source

    return result


def _build_not_applicable_metric(
    metric_name: str,
    reason: str,
) -> dict:
    return {
        "metric": metric_name,
        "status": "NOT_APPLICABLE",
        "value": None,
        "reason": reason,
    }


def _date_string(value: Any) -> str | None:
    if value is None:
        return None

    if isinstance(value, str):
        return value[:10]

    if isinstance(value, date):
        return value.isoformat()

    return str(value)[:10]


def _year_value(record: dict) -> int | None:
    """
    Extract fiscal year from a historical record.

    SEC historical records normally contain:
        fy

    We keep period_end as a fallback.
    """
    fy = record.get("fy")

    if isinstance(fy, int) and not isinstance(fy, bool):
        return fy

    if isinstance(fy, str):
        try:
            return int(fy)
        except ValueError:
            pass

    period_end = _date_string(record.get("period_end"))

    if period_end:
        try:
            return int(period_end[:4])
        except ValueError:
            return None

    return None


def _quarter_value(record: dict) -> str | None:
    quarter = record.get("quarter")

    if quarter in {"Q1", "Q2", "Q3", "Q4"}:
        return quarter

    return None


def _record_period_end(record: dict) -> str:
    return (
        _date_string(record.get("period_end"))
        or ""
    )


# ============================================================
# GROWTH CALCULATIONS
# ============================================================

def calculate_positive_yoy(
    metric_name: str,
    current_value: Any,
    previous_value: Any,
) -> dict:
    """
    Calculate YoY only when both current and previous values
    are strictly positive.

    This is intentionally used for EPS and FCF.

    Negative/zero prior values do not produce a conventional
    percentage-growth figure because the result would be
    economically misleading.
    """
    if not _is_number(current_value):
        return _build_missing_metric(
            f"{metric_name}_yoy",
            "Current value is missing or non-numeric.",
            source=[metric_name],
        )

    if not _is_number(previous_value):
        return _build_missing_metric(
            f"{metric_name}_yoy",
            "Previous value is missing or non-numeric.",
            source=[metric_name],
        )

    current = float(current_value)
    previous = float(previous_value)

    if previous <= 0:
        return _build_invalid_metric(
            f"{metric_name}_yoy",
            (
                "Conventional YoY growth is not calculated "
                "when the prior-period value is zero or negative."
            ),
            source=[metric_name],
        )

    if current <= 0:
        return _build_invalid_metric(
            f"{metric_name}_yoy",
            (
                "Conventional YoY growth is not calculated "
                "when the current-period value is zero or negative."
            ),
            source=[metric_name],
        )

    return _build_ok_metric(
        f"{metric_name}_yoy",
        current / previous - 1.0,
        source=[metric_name],
    )


def calculate_standard_yoy(
    metric_name: str,
    current_value: Any,
    previous_value: Any,
) -> dict:
    """
    Calculate conventional YoY.

    Used for Revenue and Operating Income.

    Zero prior value is invalid because percentage growth
    cannot be defined.
    """
    if not _is_number(current_value):
        return _build_missing_metric(
            f"{metric_name}_yoy",
            "Current value is missing or non-numeric.",
            source=[metric_name],
        )

    if not _is_number(previous_value):
        return _build_missing_metric(
            f"{metric_name}_yoy",
            "Previous value is missing or non-numeric.",
            source=[metric_name],
        )

    previous = float(previous_value)

    if previous == 0:
        return _build_invalid_metric(
            f"{metric_name}_yoy",
            "Previous value is zero; YoY cannot be calculated.",
            source=[metric_name],
        )

    current = float(current_value)

    return _build_ok_metric(
        f"{metric_name}_yoy",
        current / previous - 1.0,
        source=[metric_name],
    )


def calculate_cagr_3y(
    metric_name: str,
    start_value: Any,
    end_value: Any,
    years: Any = 3,
) -> dict:
    """
    Calculate 3-year CAGR.

    CAGR is calculated only when:
        start > 0
        end >= 0
        years > 0
    """
    result_name = f"{metric_name}_cagr_3y"

    if not _is_number(start_value):
        return _build_missing_metric(
            result_name,
            "Start value is missing or non-numeric.",
            source=[metric_name],
        )

    if not _is_number(end_value):
        return _build_missing_metric(
            result_name,
            "End value is missing or non-numeric.",
            source=[metric_name],
        )

    if not _is_number(years):
        return _build_missing_metric(
            result_name,
            "Years is missing or non-numeric.",
            source=[metric_name],
        )

    start = float(start_value)
    end = float(end_value)
    years_float = float(years)

    if years_float <= 0:
        return _build_invalid_metric(
            result_name,
            "Years must be greater than zero.",
            source=[metric_name],
        )

    if start <= 0:
        return _build_invalid_metric(
            result_name,
            (
                "CAGR requires a strictly positive "
                "starting value."
            ),
            source=[metric_name],
        )

    if end < 0:
        return _build_invalid_metric(
            result_name,
            (
                "CAGR requires a non-negative "
                "ending value."
            ),
            source=[metric_name],
        )

    value = (end / start) ** (1.0 / years_float) - 1.0

    return _build_ok_metric(
        result_name,
        value,
        source=[metric_name],
    )


# ============================================================
# HISTORICAL RECORD SELECTION
# ============================================================

def _valid_history_records(
    history: Any,
) -> list[dict]:
    if not isinstance(history, list):
        return []

    result = []

    for record in history:
        if not isinstance(record, dict):
            continue

        value = record.get("value")
        period_end = record.get("period_end")

        if not _is_number(value):
            continue

        if not period_end:
            continue

        result.append(record)

    return result


def _select_latest_quarter_pair(
    history: Any,
) -> tuple[dict | None, dict | None]:
    """
    Select the latest quarter and the comparable prior-year
    quarter.

    Matching logic:
        current quarter = prior quarter
        current fiscal year - prior fiscal year = 1

    The latest current-period record is selected by period_end.
    """
    records = _valid_history_records(history)

    if not records:
        return None, None

    records.sort(
        key=lambda x: (
            _record_period_end(x),
            _date_string(x.get("filing_date")) or "",
        ),
        reverse=True,
    )

    current = records[0]

    current_quarter = _quarter_value(current)
    current_year = _year_value(current)

    if current_quarter is None or current_year is None:
        return None, None

    candidates = []

    for record in records[1:]:
        if _quarter_value(record) != current_quarter:
            continue

        year = _year_value(record)

        if year != current_year - 1:
            continue

        candidates.append(record)

    if not candidates:
        return current, None

    candidates.sort(
        key=lambda x: (
            _record_period_end(x),
            _date_string(x.get("filing_date")) or "",
        ),
        reverse=True,
    )

    return current, candidates[0]


def _select_three_year_revenue_pair(
    history: Any,
) -> tuple[dict | None, dict | None, int | None]:
    """
    Select the latest annual revenue record and the closest
    record exactly three fiscal years earlier.

    A valid CAGR requires a positive starting value.
    """
    records = _valid_history_records(history)

    if not records:
        return None, None, None

    annual_records = []

    for record in records:
        period_type = record.get("period_type")

        if period_type != "annual":
            continue

        year = _year_value(record)

        if year is None:
            continue

        annual_records.append(record)

    if len(annual_records) < 2:
        return None, None, None

    annual_records.sort(
        key=lambda x: (
            _year_value(x) or -1,
            _record_period_end(x),
        ),
        reverse=True,
    )

    current = annual_records[0]
    current_year = _year_value(current)

    if current_year is None:
        return None, None, None

    target_year = current_year - 3

    exact_candidates = [
        record
        for record in annual_records[1:]
        if _year_value(record) == target_year
    ]

    if exact_candidates:
        exact_candidates.sort(
            key=lambda x: (
                _record_period_end(x),
                _date_string(x.get("filing_date")) or "",
            ),
            reverse=True,
        )

        return current, exact_candidates[0], 3

    # If an exact 3-year observation is unavailable,
    # do not silently use 4+ years. v0.1 requires an exact
    # three-fiscal-year comparison.
    return current, None, None


# ============================================================
# FCF HISTORY
# ============================================================

def _build_fcf_history(
    cfo_history: Any,
    capex_history: Any,
) -> list[dict]:
    """
    Construct quarterly FCF history from:

        FCF = CFO + CapEx

    Both histories must refer to the same period.
    """
    cfo_records = _valid_history_records(cfo_history)
    capex_records = _valid_history_records(capex_history)

    if not cfo_records or not capex_records:
        return []

    capex_by_key = {}

    for record in capex_records:
        key = (
            _record_period_end(record),
            _quarter_value(record),
            _year_value(record),
        )

        existing = capex_by_key.get(key)

        if existing is None:
            capex_by_key[key] = record
            continue

        current_filed = (
            _date_string(record.get("filing_date"))
            or ""
        )

        existing_filed = (
            _date_string(existing.get("filing_date"))
            or ""
        )

        if current_filed > existing_filed:
            capex_by_key[key] = record

    result = []

    for cfo in cfo_records:
        key = (
            _record_period_end(cfo),
            _quarter_value(cfo),
            _year_value(cfo),
        )

        capex = capex_by_key.get(key)

        if capex is None:
            continue

        cfo_value = cfo.get("value")
        capex_value = capex.get("value")

        if not _is_number(cfo_value):
            continue

        if not _is_number(capex_value):
            continue

        result.append(
            {
                "period_type": cfo.get("period_type"),
                "quarter": _quarter_value(cfo),
                "fy": _year_value(cfo),
                "period_start": cfo.get("period_start"),
                "period_end": cfo.get("period_end"),
                "value": float(cfo_value)
                + float(capex_value),
                "unit": cfo.get("unit"),
                "derived": True,
            }
        )

    result.sort(
        key=lambda x: (
            x.get("period_end") or "",
            x.get("fy") or 0,
        )
    )

    return result


# ============================================================
# COMPONENT CALCULATIONS
# ============================================================

def _calculate_history_yoy(
    metric_name: str,
    history: Any,
    *,
    positive_only: bool = False,
) -> dict:
    current, previous = _select_latest_quarter_pair(history)

    if current is None:
        return _build_missing_metric(
            metric_name,
            (
                "No valid quarterly historical "
                "observation was found."
            ),
            source=[metric_name],
        )

    if previous is None:
        return _build_missing_metric(
            metric_name,
            (
                "No comparable prior-year quarter "
                "was found."
            ),
            source=[metric_name],
        )

    current_value = current.get("value")
    previous_value = previous.get("value")

    if positive_only:
        result = calculate_positive_yoy(
            metric_name,
            current_value,
            previous_value,
        )
    else:
        result = calculate_standard_yoy(
            metric_name,
            current_value,
            previous_value,
        )

    result["current_period"] = {
        "period_end": current.get("period_end"),
        "quarter": current.get("quarter"),
        "fy": current.get("fy"),
        "value": current_value,
    }

    result["previous_period"] = {
        "period_end": previous.get("period_end"),
        "quarter": previous.get("quarter"),
        "fy": previous.get("fy"),
        "value": previous_value,
    }

    return result


def _calculate_revenue_cagr(
    history: Any,
) -> dict:
    current, previous, years = (
        _select_three_year_revenue_pair(history)
    )

    if current is None:
        return _build_missing_metric(
            "revenue_cagr_3y",
            "No valid annual revenue history was found.",
            source=["revenue"],
        )

    if previous is None or years is None:
        return _build_missing_metric(
            "revenue_cagr_3y",
            (
                "An exact three-fiscal-year annual "
                "revenue comparison was not available."
            ),
            source=["revenue"],
        )

    result = calculate_cagr_3y(
        "revenue",
        previous.get("value"),
        current.get("value"),
        years,
    )

    result["current_period"] = {
        "period_end": current.get("period_end"),
        "fy": current.get("fy"),
        "value": current.get("value"),
    }

    result["previous_period"] = {
        "period_end": previous.get("period_end"),
        "fy": previous.get("fy"),
        "value": previous.get("value"),
    }

    return result


# ============================================================
# STAR RATING
# ============================================================

def _rate_growth_value(
    metric_name: str,
    value: Any,
    thresholds: list[tuple[float, int]],
) -> dict:
    """
    Generic ascending threshold rating.

    thresholds example:
        [
            (0.00, 2),
            (0.05, 3),
            (0.10, 4),
            (0.20, 5),
        ]

    Values below the first threshold receive 1 star.
    """
    if not _is_number(value):
        return _build_missing_metric(
            metric_name,
            "Value is missing or non-numeric.",
        )

    numeric_value = float(value)

    stars = 1

    for threshold, rating in thresholds:
        if numeric_value >= threshold:
            stars = rating
        else:
            break

    return {
        "metric": metric_name,
        "status": "OK",
        "value": numeric_value,
        "stars": stars,
    }


def rate_revenue_yoy(value: Any) -> dict:
    return _rate_growth_value(
        "revenue_yoy",
        value,
        [
            (0.00, 2),
            (0.05, 3),
            (0.10, 4),
            (0.20, 5),
        ],
    )


def rate_operating_income_yoy(value: Any) -> dict:
    return _rate_growth_value(
        "operating_income_yoy",
        value,
        [
            (0.00, 2),
            (0.05, 3),
            (0.15, 4),
            (0.30, 5),
        ],
    )


def rate_eps_yoy(value: Any) -> dict:
    return _rate_growth_value(
        "eps_yoy",
        value,
        [
            (0.00, 2),
            (0.05, 3),
            (0.15, 4),
            (0.30, 5),
        ],
    )


def rate_fcf_yoy(value: Any) -> dict:
    return _rate_growth_value(
        "fcf_yoy",
        value,
        [
            (0.00, 2),
            (0.05, 3),
            (0.15, 4),
            (0.30, 5),
        ],
    )


def rate_revenue_cagr_3y(value: Any) -> dict:
    return _rate_growth_value(
        "revenue_cagr_3y",
        value,
        [
            (0.00, 2),
            (0.05, 3),
            (0.10, 4),
            (0.20, 5),
        ],
    )


# ============================================================
# WARNING DETECTION
# ============================================================

def _build_warning(
    status: str,
    reason: str,
    *,
    metrics: dict[str, Any] | None = None,
) -> dict:
    result = {
        "status": status,
        "reason": reason,
    }

    if metrics is not None:
        result["metrics"] = metrics

    return result


def detect_growth_warnings(
    components: dict,
) -> dict:
    """
    Detect divergence between growth dimensions.

    Warnings do not directly change the Growth score in v0.1.
    They are informational risk flags for later Investment State
    integration.
    """
    warnings = {}

    revenue = components.get("revenue_yoy", {})
    operating_income = components.get(
        "operating_income_yoy",
        {},
    )
    fcf = components.get("fcf_yoy", {})
    eps = components.get("eps_yoy", {})

    revenue_value = revenue.get("value")
    operating_value = operating_income.get("value")
    fcf_value = fcf.get("value")
    eps_value = eps.get("value")

    # --------------------------------------------------------
    # Revenue vs Operating Income
    # --------------------------------------------------------

    if (
        _is_number(revenue_value)
        and _is_number(operating_value)
        and float(revenue_value) >= 0.10
        and float(operating_value) < 0.0
    ):
        warnings[
            "revenue_operating_income_divergence"
        ] = _build_warning(
            "WARNING",
            (
                "Revenue is growing by at least 10%, "
                "while operating income is declining."
            ),
            metrics={
                "revenue_yoy": revenue_value,
                "operating_income_yoy": operating_value,
            },
        )

    # --------------------------------------------------------
    # Revenue vs FCF
    # --------------------------------------------------------

    if (
        _is_number(revenue_value)
        and _is_number(fcf_value)
        and float(revenue_value) >= 0.10
        and float(fcf_value) < 0.0
    ):
        warnings[
            "revenue_fcf_divergence"
        ] = _build_warning(
            "WARNING",
            (
                "Revenue is growing by at least 10%, "
                "while FCF is declining."
            ),
            metrics={
                "revenue_yoy": revenue_value,
                "fcf_yoy": fcf_value,
            },
        )

    # --------------------------------------------------------
    # EPS vs Revenue
    # --------------------------------------------------------

    if (
        _is_number(eps_value)
        and _is_number(revenue_value)
        and float(eps_value) >= 0.30
        and float(revenue_value) < 0.05
    ):
        warnings[
            "eps_revenue_divergence"
        ] = _build_warning(
            "WARNING",
            (
                "EPS is growing by at least 30% while "
                "Revenue growth is below 5%. "
                "EPS growth quality requires additional review."
            ),
            metrics={
                "eps_yoy": eps_value,
                "revenue_yoy": revenue_value,
            },
        )

    return warnings


# ============================================================
# SCORE CALCULATION
# ============================================================

def _calculate_weighted_score(
    components: dict,
) -> dict:
    weighted_sum = 0.0
    available_weight = 0.0
    available_components = 0

    for metric_name in GROWTH_METRICS:
        component = components.get(
            metric_name,
            {},
        )

        if component.get("status") != "OK":
            continue

        stars = component.get("stars")

        if not _is_number(stars):
            continue

        weight = GROWTH_WEIGHTS[metric_name]

        weighted_sum += float(stars) * weight
        available_weight += weight
        available_components += 1

    if available_components < MIN_VALID_COMPONENTS:
        return {
            "status": "MISSING",
            "score": None,
            "stars": None,
            "available_components": available_components,
            "available_weight": available_weight,
        }

    if available_weight <= 0:
        return {
            "status": "MISSING",
            "score": None,
            "stars": None,
            "available_components": available_components,
            "available_weight": available_weight,
        }

    score = weighted_sum / available_weight

    stars = max(
        1,
        min(
            5,
            int(score + 0.5),
        ),
    )

    return {
        "status": "OK",
        "score": score,
        "stars": stars,
        "available_components": available_components,
        "available_weight": available_weight,
    }


# ============================================================
# MAIN CALCULATION
# ============================================================

def calculate_growth(
    normalized: dict,
    derived: dict,
    historical: dict | None = None,
) -> dict:
    """
    Calculate Growth Factor v0.1.

    Expected historical structure:

        {
            "revenue": {
                "status": "OK",
                "quarterly": [...],
                "annual": [...]
            },
            "operating_income": {
                "status": "OK",
                "quarterly": [...]
            },
            "diluted_eps": {
                "status": "OK",
                "quarterly": [...]
            },
            "cfo": {
                "status": "OK",
                "quarterly": [...]
            },
            "capex": {
                "status": "OK",
                "quarterly": [...]
            }
        }

    Historical Extraction is the source of truth for
    Growth's quarterly comparisons.
    """
    if not isinstance(normalized, dict):
        raise TypeError("normalized must be a dict.")

    if not isinstance(derived, dict):
        raise TypeError("derived must be a dict.")

    if historical is None:
        historical = {}

    if not isinstance(historical, dict):
        raise TypeError("historical must be a dict.")

    ticker = normalized.get("ticker")

    components = {}

    # --------------------------------------------------------
    # Extract historical lists
    # --------------------------------------------------------

    revenue_result = historical.get(
        "revenue",
        {},
    )

    operating_result = historical.get(
        "operating_income",
        {},
    )

    eps_result = historical.get(
        "diluted_eps",
        {},
    )

    cfo_result = historical.get(
        "cfo",
        {},
    )

    capex_result = historical.get(
        "capex",
        {},
    )

    revenue_history = (
        revenue_result.get("quarterly", [])
        if isinstance(revenue_result, dict)
        else []
    )

    revenue_annual = (
        revenue_result.get("annual", [])
        if isinstance(revenue_result, dict)
        else []
    )

    operating_history = (
        operating_result.get("quarterly", [])
        if isinstance(operating_result, dict)
        else []
    )

    eps_history = (
        eps_result.get("quarterly", [])
        if isinstance(eps_result, dict)
        else []
    )

    cfo_history = (
        cfo_result.get("quarterly", [])
        if isinstance(cfo_result, dict)
        else []
    )

    capex_history = (
        capex_result.get("quarterly", [])
        if isinstance(capex_result, dict)
        else []
    )

    # --------------------------------------------------------
    # Revenue YoY
    # --------------------------------------------------------

    components["revenue_yoy"] = _calculate_history_yoy(
        "revenue",
        revenue_history,
        positive_only=False,
    )

    # --------------------------------------------------------
    # Operating Income YoY
    # --------------------------------------------------------

    components[
        "operating_income_yoy"
    ] = _calculate_history_yoy(
        "operating_income",
        operating_history,
        positive_only=False,
    )

    # --------------------------------------------------------
    # EPS YoY
    # --------------------------------------------------------

    components["eps_yoy"] = _calculate_history_yoy(
        "eps",
        eps_history,
        positive_only=True,
    )

    # --------------------------------------------------------
    # FCF YoY
    # --------------------------------------------------------

    fcf_history = _build_fcf_history(
        cfo_history,
        capex_history,
    )

    components["fcf_yoy"] = _calculate_history_yoy(
        "fcf",
        fcf_history,
        positive_only=True,
    )

    # --------------------------------------------------------
    # Revenue 3Y CAGR
    # --------------------------------------------------------

    components["revenue_cagr_3y"] = (
        _calculate_revenue_cagr(
            revenue_annual,
        )
    )

    # --------------------------------------------------------
    # Ratings
    # --------------------------------------------------------

    rating_functions = {
        "revenue_yoy": rate_revenue_yoy,
        "operating_income_yoy": rate_operating_income_yoy,
        "eps_yoy": rate_eps_yoy,
        "fcf_yoy": rate_fcf_yoy,
        "revenue_cagr_3y": rate_revenue_cagr_3y,
    }

    for metric_name, rating_function in (
        rating_functions.items()
    ):
        component = components[metric_name]

        if component.get("status") != "OK":
            continue

        rating = rating_function(
            component.get("value")
        )

        component["stars"] = rating.get("stars")

    # --------------------------------------------------------
    # Warnings
    # --------------------------------------------------------

    warnings = detect_growth_warnings(
        components,
    )

    # --------------------------------------------------------
    # Score
    # --------------------------------------------------------

    quality = _calculate_weighted_score(
        components,
    )

    result = {
        "schema_version": SCHEMA_VERSION,
        "ticker": ticker,
        "growth": quality,
        "components": components,
        "warnings": warnings,
        "limitations": {},
    }

    # --------------------------------------------------------
    # Limitations
    # --------------------------------------------------------

    if not historical:
        result["limitations"][
            "historical_data"
        ] = {
            "status": "MISSING",
            "reason": (
                "Historical Extraction data was not supplied."
            ),
        }

    if components["eps_yoy"]["status"] != "OK":
        result["limitations"][
            "eps_growth"
        ] = {
            "status": components["eps_yoy"]["status"],
            "reason": components["eps_yoy"].get(
                "reason"
            ),
        }

    if components["fcf_yoy"]["status"] != "OK":
        result["limitations"][
            "fcf_growth"
        ] = {
            "status": components["fcf_yoy"]["status"],
            "reason": components["fcf_yoy"].get(
                "reason"
            ),
        }

    return result


# ============================================================
# VALIDATION
# ============================================================

def validate_growth(data: dict) -> list[str]:
    """
    Validate Growth Factor output.

    Returns:
        [] when valid
        list of failure paths otherwise
    """
    failures = []

    if not isinstance(data, dict):
        return ["root"]

    required_top_level = [
        "schema_version",
        "ticker",
        "growth",
        "components",
        "warnings",
        "limitations",
    ]

    for key in required_top_level:
        if key not in data:
            failures.append(key)

    growth = data.get("growth")

    if not isinstance(growth, dict):
        failures.append("growth")
    else:
        if growth.get("status") not in {
            "OK",
            "MISSING",
        }:
            failures.append("growth.status")

        score = growth.get("score")

        if growth.get("status") == "OK":
            if not _is_number(score):
                failures.append("growth.score")
            elif not 1.0 <= float(score) <= 5.0:
                failures.append("growth.score")

            stars = growth.get("stars")

            if stars not in {
                1,
                2,
                3,
                4,
                5,
            }:
                failures.append("growth.stars")

        else:
            if score is not None:
                failures.append("growth.score")

            if growth.get("stars") is not None:
                failures.append("growth.stars")

    components = data.get("components")

    if not isinstance(components, dict):
        failures.append("components")
        return failures

    for metric_name in GROWTH_METRICS:
        if metric_name not in components:
            failures.append(
                f"components.{metric_name}"
            )
            continue

        component = components[metric_name]

        if not isinstance(component, dict):
            failures.append(
                f"components.{metric_name}"
            )
            continue

        status = component.get("status")

        if status not in VALID_STATUSES:
            failures.append(
                f"components.{metric_name}.status"
            )
            continue

        if status == "OK":
            if not _is_number(component.get("value")):
                failures.append(
                    f"components.{metric_name}.value"
                )

            if component.get("stars") not in {
                1,
                2,
                3,
                4,
                5,
            }:
                failures.append(
                    f"components.{metric_name}.stars"
                )

        elif status in {
            "MISSING",
            "INVALID",
            "NOT_APPLICABLE",
        }:
            if component.get("value") is not None:
                failures.append(
                    f"components.{metric_name}.value"
                )

            if not component.get("reason"):
                failures.append(
                    f"components.{metric_name}.reason"
                )

    if not isinstance(
        data.get("warnings"),
        dict,
    ):
        failures.append("warnings")

    if not isinstance(
        data.get("limitations"),
        dict,
    ):
        failures.append("limitations")

    return failures
