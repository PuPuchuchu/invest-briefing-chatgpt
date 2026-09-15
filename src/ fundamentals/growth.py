from __future__ import annotations

from datetime import date, datetime
from typing import Any


# ============================================================
# CONFIGURATION
# ============================================================

SCHEMA_VERSION = "growth_v0.1"

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
# GENERIC HELPERS
# ============================================================

def _is_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
    )


def _build_ok_metric(
    metric: str,
    value: float,
    source: list[str] | None = None,
) -> dict[str, Any]:
    result = {
        "status": "OK",
        "metric": metric,
        "value": value,
    }

    if source:
        result["source"] = source

    return result


def _build_missing_metric(
    metric: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "status": "MISSING",
        "metric": metric,
        "value": None,
        "reason": reason,
    }


def _build_invalid_metric(
    metric: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "status": "INVALID",
        "metric": metric,
        "value": None,
        "reason": reason,
    }


def _round_growth(value: float) -> float:
    """
    Normalize floating-point noise in growth calculations.

    Example:
        120 / 100 - 1
        -> 0.19999999999999996

    becomes:
        0.2

    This is important because rating thresholds include exact
    boundaries such as 20%.
    """
    return round(float(value), 10)


def _date_string(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.date().isoformat()

    if isinstance(value, date):
        return value.isoformat()

    if isinstance(value, str):
        return value

    return None


def _year_value(record: dict[str, Any]) -> int | None:
    value = record.get("fy")

    if isinstance(value, int):
        return value

    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None

    return None


def _quarter_value(record: dict[str, Any]) -> str | None:
    value = record.get("quarter")

    if value is None:
        return None

    return str(value)


def _record_period_end(record: dict[str, Any]) -> str | None:
    for key in ("period_end", "end", "date"):
        value = _date_string(record.get(key))

        if value:
            return value

    return None


# ============================================================
# GROWTH CALCULATIONS
# ============================================================

def calculate_positive_yoy(
    metric_name: str,
    current: Any,
    previous: Any,
) -> dict[str, Any]:
    """
    Calculate YoY growth for metrics where conventional growth
    requires both periods to be positive.

    Used for:
        - EPS
        - FCF

    If either period is <= 0, the result is INVALID rather than
    fabricating a misleading growth rate.
    """

    if not _is_number(current) or not _is_number(previous):
        return _build_invalid_metric(
            metric_name,
            "Current and previous values must be numeric.",
        )

    if previous <= 0:
        return _build_invalid_metric(
            metric_name,
            "Previous value must be greater than zero "
            "for conventional YoY calculation.",
        )

    if current <= 0:
        return _build_invalid_metric(
            metric_name,
            "Current value must be greater than zero "
            "for conventional YoY calculation.",
        )

    growth = _round_growth((current / previous) - 1.0)

    return _build_ok_metric(
        metric_name,
        growth,
    )


def calculate_standard_yoy(
    metric_name: str,
    current: Any,
    previous: Any,
) -> dict[str, Any]:
    """
    Calculate standard YoY growth.

    Used for:
        - Revenue
        - Operating Income

    Negative growth is allowed.

    Previous value of zero is invalid because division by zero
    would make the conventional YoY calculation undefined.
    """

    if not _is_number(current) or not _is_number(previous):
        return _build_invalid_metric(
            metric_name,
            "Current and previous values must be numeric.",
        )

    if previous == 0:
        return _build_invalid_metric(
            metric_name,
            "Previous value cannot be zero.",
        )

    growth = _round_growth((current / previous) - 1.0)

    return _build_ok_metric(
        metric_name,
        growth,
    )


def calculate_cagr_3y(
    metric_name: str,
    start_value: Any,
    end_value: Any,
    years: int = 3,
) -> dict[str, Any]:
    """
    Calculate CAGR.

    Requirements:
        - start value > 0
        - end value >= 0
        - years > 0
    """

    if not _is_number(start_value) or not _is_number(end_value):
        return _build_invalid_metric(
            metric_name,
            "Start and end values must be numeric.",
        )

    if start_value <= 0:
        return _build_invalid_metric(
            metric_name,
            "Starting value must be greater than zero.",
        )

    if end_value < 0:
        return _build_invalid_metric(
            metric_name,
            "Ending value cannot be negative.",
        )

    if years <= 0:
        return _build_invalid_metric(
            metric_name,
            "Years must be greater than zero.",
        )

    cagr = (end_value / start_value) ** (1.0 / years) - 1.0

    return _build_ok_metric(
        metric_name,
        _round_growth(cagr),
    )


# ============================================================
# HISTORY HELPERS
# ============================================================

def _valid_history_records(
    history: Any,
) -> list[dict[str, Any]]:
    if not isinstance(history, list):
        return []

    records = []

    for record in history:
        if not isinstance(record, dict):
            continue

        if record.get("status") not in (None, "OK"):
            continue

        if not _is_number(record.get("value")):
            continue

        if _record_period_end(record) is None:
            continue

        records.append(record)

    return records


def _select_latest_quarter_pair(
    history: Any,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """
    Select the latest quarterly observation and its prior-year
    comparable quarter.

    Priority:
        1. Same quarter label + prior FY
        2. Same quarter label + one-year-earlier period_end
    """

    records = _valid_history_records(history)

    if not records:
        return None, None

    records = sorted(
        records,
        key=lambda x: _record_period_end(x) or "",
    )

    latest = records[-1]

    latest_quarter = _quarter_value(latest)
    latest_fy = _year_value(latest)

    candidates: list[dict[str, Any]] = []

    for record in records[:-1]:
        record_quarter = _quarter_value(record)
        record_fy = _year_value(record)

        if (
            latest_quarter is not None
            and record_quarter == latest_quarter
            and latest_fy is not None
            and record_fy == latest_fy - 1
        ):
            candidates.append(record)

    if candidates:
        previous = sorted(
            candidates,
            key=lambda x: _record_period_end(x) or "",
        )[-1]

        return latest, previous

    latest_end = _record_period_end(latest)

    if latest_end:
        try:
            latest_date = date.fromisoformat(latest_end)
        except ValueError:
            latest_date = None

        if latest_date:
            target_year = latest_date.year - 1

            year_candidates = []

            for record in records[:-1]:
                period_end = _record_period_end(record)

                if not period_end:
                    continue

                try:
                    record_date = date.fromisoformat(period_end)
                except ValueError:
                    continue

                if record_date.year == target_year:
                    year_candidates.append(record)

            if year_candidates:
                previous = min(
                    year_candidates,
                    key=lambda x: abs(
                        (
                            date.fromisoformat(
                                _record_period_end(x)
                            )
                            - latest_date
                        ).days
                    ),
                )

                return latest, previous

    return latest, None


def _select_three_year_revenue_pair(
    history: Any,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """
    Select annual revenue observations exactly three fiscal years
    apart.

    No 4-year or 5-year fallback is used because the framework
    explicitly requires a 3-year CAGR.
    """

    records = _valid_history_records(history)

    annual_records = [
        record
        for record in records
        if str(record.get("period_type", "")).lower() == "annual"
    ]

    if not annual_records:
        return None, None

    annual_records = sorted(
        annual_records,
        key=lambda x: _year_value(x) or 0,
    )

    latest = annual_records[-1]
    latest_fy = _year_value(latest)

    if latest_fy is None:
        return None, None

    target_fy = latest_fy - 3

    candidates = [
        record
        for record in annual_records
        if _year_value(record) == target_fy
    ]

    if not candidates:
        return latest, None

    previous = sorted(
        candidates,
        key=lambda x: _record_period_end(x) or "",
    )[-1]

    return latest, previous


def _build_fcf_history(
    cfo_history: Any,
    capex_history: Any,
) -> list[dict[str, Any]]:
    """
    Build historical FCF records by matching CFO and CapEx
    observations on period metadata.

    FCF = CFO + CapEx

    CapEx is expected to be represented as a negative cash-flow
    amount in the historical data.
    """

    cfo_records = _valid_history_records(cfo_history)
    capex_records = _valid_history_records(capex_history)

    if not cfo_records or not capex_records:
        return []

    capex_map: dict[tuple[Any, Any, Any, Any], dict[str, Any]] = {}

    for record in capex_records:
        key = (
            _record_period_end(record),
            _quarter_value(record),
            _year_value(record),
            record.get("period_type"),
        )

        capex_map[key] = record

    result = []

    for cfo in cfo_records:
        key = (
            _record_period_end(cfo),
            _quarter_value(cfo),
            _year_value(cfo),
            cfo.get("period_type"),
        )

        capex = capex_map.get(key)

        if capex is None:
            continue

        fcf = cfo["value"] + capex["value"]

        result.append(
            {
                "status": "OK",
                "period_end": _record_period_end(cfo),
                "quarter": _quarter_value(cfo),
                "fy": _year_value(cfo),
                "period_type": cfo.get("period_type"),
                "value": fcf,
            }
        )

    return result


# ============================================================
# COMPONENT CALCULATIONS
# ============================================================

def _calculate_history_yoy(
    metric_name: str,
    history: Any,
    positive_only: bool,
) -> dict[str, Any]:
    latest, previous = _select_latest_quarter_pair(history)

    if latest is None:
        return _build_missing_metric(
            metric_name,
            "No usable quarterly history found.",
        )

    if previous is None:
        return _build_missing_metric(
            metric_name,
            "No prior-year comparable quarter found.",
        )

    if positive_only:
        result = calculate_positive_yoy(
            metric_name,
            latest["value"],
            previous["value"],
        )
    else:
        result = calculate_standard_yoy(
            metric_name,
            latest["value"],
            previous["value"],
        )

    if result["status"] == "OK":
        result["source"] = [
            "historical",
            "quarterly",
        ]

        result["current_period_end"] = _record_period_end(latest)
        result["previous_period_end"] = _record_period_end(previous)

    return result


def _calculate_revenue_cagr(
    revenue_history: Any,
) -> dict[str, Any]:
    latest, previous = _select_three_year_revenue_pair(
        revenue_history
    )

    if latest is None:
        return _build_missing_metric(
            "revenue_cagr_3y",
            "No usable annual revenue history found.",
        )

    if previous is None:
        return _build_missing_metric(
            "revenue_cagr_3y",
            "Exact three-year annual revenue history "
            "is not available.",
        )

    result = calculate_cagr_3y(
        "revenue_cagr_3y",
        previous["value"],
        latest["value"],
        years=3,
    )

    if result["status"] == "OK":
        result["source"] = [
            "historical",
            "annual",
        ]

        result["start_period_end"] = _record_period_end(previous)
        result["end_period_end"] = _record_period_end(latest)

    return result


# ============================================================
# GROWTH RATING
# ============================================================

def _rate_growth_value(
    metric_name: str,
    value: Any,
) -> dict[str, Any]:
    """
    Convert growth rate into a 1-5 star rating.

    Thresholds:

        Revenue YoY
            < 0%   -> 1★
            >= 0%  -> 2★
            >= 5%  -> 3★
            >= 10% -> 4★
            >= 20% -> 5★

        Operating Income YoY
            < 0%   -> 1★
            >= 0%  -> 2★
            >= 5%  -> 3★
            >= 15% -> 4★
            >= 30% -> 5★

        EPS YoY
            < 0%   -> 1★
            >= 0%  -> 2★
            >= 5%  -> 3★
            >= 15% -> 4★
            >= 30% -> 5★

        FCF YoY
            < 0%   -> 1★
            >= 0%  -> 2★
            >= 5%  -> 3★
            >= 15% -> 4★
            >= 30% -> 5★

        Revenue 3Y CAGR
            < 0%   -> 1★
            >= 0%  -> 2★
            >= 5%  -> 3★
            >= 10% -> 4★
            >= 20% -> 5★
    """

    if not _is_number(value):
        return {
            "status": "INVALID",
            "metric": metric_name,
            "stars": None,
            "value": None,
        }

    value = _round_growth(value)

    if metric_name == "revenue_yoy":
        thresholds = (0.00, 0.05, 0.10, 0.20)

    elif metric_name == "operating_income_yoy":
        thresholds = (0.00, 0.05, 0.15, 0.30)

    elif metric_name == "eps_yoy":
        thresholds = (0.00, 0.05, 0.15, 0.30)

    elif metric_name == "fcf_yoy":
        thresholds = (0.00, 0.05, 0.15, 0.30)

    elif metric_name == "revenue_cagr_3y":
        thresholds = (0.00, 0.05, 0.10, 0.20)

    else:
        return {
            "status": "INVALID",
            "metric": metric_name,
            "stars": None,
            "value": value,
            "reason": "Unknown growth metric.",
        }

    if value < thresholds[0]:
        stars = 1
    elif value < thresholds[1]:
        stars = 2
    elif value < thresholds[2]:
        stars = 3
    elif value < thresholds[3]:
        stars = 4
    else:
        stars = 5

    return {
        "status": "OK",
        "metric": metric_name,
        "value": value,
        "stars": stars,
    }


# ============================================================
# WARNINGS
# ============================================================

def detect_growth_warnings(
    components: dict[str, dict[str, Any]],
) -> list[str]:
    warnings: list[str] = []

    revenue = components.get("revenue_yoy", {})
    operating_income = components.get(
        "operating_income_yoy",
        {},
    )
    eps = components.get("eps_yoy", {})
    fcf = components.get("fcf_yoy", {})

    revenue_value = revenue.get("value")
    operating_income_value = operating_income.get("value")
    eps_value = eps.get("value")
    fcf_value = fcf.get("value")

    if (
        _is_number(revenue_value)
        and _is_number(operating_income_value)
        and revenue_value >= 0.10
        and operating_income_value < 0
    ):
        warnings.append(
            "Revenue growth is >=10% while operating income "
            "growth is negative."
        )

    if (
        _is_number(revenue_value)
        and _is_number(fcf_value)
        and revenue_value >= 0.10
        and fcf_value < 0
    ):
        warnings.append(
            "Revenue growth is >=10% while FCF growth is negative."
        )

    if (
        _is_number(eps_value)
        and _is_number(revenue_value)
        and eps_value >= 0.30
        and revenue_value < 0.05
    ):
        warnings.append(
            "EPS growth is >=30% while revenue growth is <5%."
        )

    return warnings


# ============================================================
# WEIGHTED SCORE
# ============================================================

def _calculate_weighted_score(
    components: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    weighted_sum = 0.0
    weight_sum = 0.0
    valid_components = 0

    for metric_name, weight in GROWTH_WEIGHTS.items():
        component = components.get(metric_name, {})

        if (
            component.get("status") != "OK"
            or not _is_number(component.get("stars"))
        ):
            continue

        stars = component["stars"]

        weighted_sum += stars * weight
        weight_sum += weight
        valid_components += 1

    if valid_components < MIN_VALID_COMPONENTS:
        return {
            "status": "INSUFFICIENT_DATA",
            "score": None,
            "stars": None,
            "valid_components": valid_components,
            "total_components": len(GROWTH_METRICS),
            "coverage": (
                valid_components / len(GROWTH_METRICS)
                if GROWTH_METRICS
                else 0.0
            ),
        }

    score = weighted_sum / weight_sum

    # Convert weighted 1-5 score to integer star rating.
    stars = int(score + 0.5)
    stars = max(1, min(5, stars))

    return {
        "status": "OK",
        "score": round(score, 4),
        "stars": stars,
        "valid_components": valid_components,
        "total_components": len(GROWTH_METRICS),
        "coverage": round(
            valid_components / len(GROWTH_METRICS),
            4,
        ),
    }


# ============================================================
# MAIN CALCULATION
# ============================================================

def calculate_growth(
    normalized: dict[str, Any],
    derived: dict[str, Any],
    historical: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Calculate Growth Factor v0.1.

    Historical Extraction is the source of truth for quarterly
    YoY calculations.

    Components:
        - Revenue YoY              25%
        - Operating Income YoY     20%
        - EPS YoY                  25%
        - FCF YoY                  20%
        - Revenue 3Y CAGR          10%

    Minimum valid components:
        3 / 5
    """

    if not isinstance(normalized, dict):
        raise TypeError("normalized must be a dictionary.")

    if not isinstance(derived, dict):
        raise TypeError("derived must be a dictionary.")

    ticker = normalized.get("ticker")

    components: dict[str, dict[str, Any]] = {}

    if not isinstance(historical, dict):
        historical = {}

    revenue_history = historical.get("revenue", [])
    operating_income_history = historical.get(
        "operating_income",
        [],
    )
    eps_history = historical.get(
        "diluted_eps",
        [],
    )
    cfo_history = historical.get(
        "cfo",
        [],
    )
    capex_history = historical.get(
        "capex",
        [],
    )

    # --------------------------------------------------------
    # Revenue YoY
    # --------------------------------------------------------

    components["revenue_yoy"] = _calculate_history_yoy(
        "revenue_yoy",
        revenue_history,
        positive_only=False,
    )

    # --------------------------------------------------------
    # Operating Income YoY
    # --------------------------------------------------------

    components["operating_income_yoy"] = _calculate_history_yoy(
        "operating_income_yoy",
        operating_income_history,
        positive_only=False,
    )

    # --------------------------------------------------------
    # EPS YoY
    # --------------------------------------------------------

    components["eps_yoy"] = _calculate_history_yoy(
        "eps_yoy",
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
        "fcf_yoy",
        fcf_history,
        positive_only=True,
    )

    # --------------------------------------------------------
    # Revenue 3Y CAGR
    # --------------------------------------------------------

    components["revenue_cagr_3y"] = _calculate_revenue_cagr(
        revenue_history,
    )

    # --------------------------------------------------------
    # Apply ratings
    # --------------------------------------------------------

    for metric_name in GROWTH_METRICS:
        component = components[metric_name]

        if component.get("status") != "OK":
            component["stars"] = None
            continue

        rated = _rate_growth_value(
            metric_name,
            component.get("value"),
        )

        component["stars"] = rated.get("stars")

    # --------------------------------------------------------
    # Warnings
    # --------------------------------------------------------

    warnings = detect_growth_warnings(components)

    # --------------------------------------------------------
    # Score
    # --------------------------------------------------------

    score_result = _calculate_weighted_score(
        components,
    )

    # --------------------------------------------------------
    # Limitations
    # --------------------------------------------------------

    limitations: dict[str, Any] = {}

    if components["eps_yoy"].get("status") != "OK":
        limitations["eps_yoy"] = (
            "EPS growth requires positive current and "
            "prior-year comparable-quarter values."
        )

    if components["fcf_yoy"].get("status") != "OK":
        limitations["fcf_yoy"] = (
            "FCF growth requires positive current and "
            "prior-year comparable-quarter values."
        )

    if components["revenue_cagr_3y"].get("status") != "OK":
        limitations["revenue_cagr_3y"] = (
            "Revenue CAGR requires exact three-fiscal-year "
            "annual history."
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "ticker": ticker,
        "growth": score_result,
        "components": components,
        "warnings": warnings,
        "limitations": limitations,
    }


# ============================================================
# VALIDATION
# ============================================================

def validate_growth(
    data: dict[str, Any],
) -> list[str]:
    """
    Validate Growth Factor output.

    Returns:
        [] when valid
        list[str] when invalid
    """

    errors: list[str] = []

    if not isinstance(data, dict):
        return ["Growth output must be a dictionary."]

    if data.get("schema_version") != SCHEMA_VERSION:
        errors.append(
            "Invalid or missing schema_version."
        )

    if "ticker" not in data:
        errors.append(
            "Missing ticker."
        )

    growth = data.get("growth")

    if not isinstance(growth, dict):
        errors.append(
            "Missing or invalid growth result."
        )
    else:
        status = growth.get("status")

        if status not in (
            "OK",
            "INSUFFICIENT_DATA",
        ):
            errors.append(
                "Invalid growth status."
            )

        if status == "OK":
            if not _is_number(growth.get("score")):
                errors.append(
                    "Growth score must be numeric."
                )

            if not isinstance(
                growth.get("stars"),
                int,
            ):
                errors.append(
                    "Growth stars must be an integer."
                )

            if not isinstance(
                growth.get("valid_components"),
                int,
            ):
                errors.append(
                    "valid_components must be an integer."
                )

        if status == "INSUFFICIENT_DATA":
            if growth.get("score") is not None:
                errors.append(
                    "Insufficient-data score must be None."
                )

            if growth.get("stars") is not None:
                errors.append(
                    "Insufficient-data stars must be None."
                )

    components = data.get("components")

    if not isinstance(components, dict):
        errors.append(
            "Missing or invalid components."
        )
    else:
        for metric_name in GROWTH_METRICS:
            if metric_name not in components:
                errors.append(
                    f"Missing component: {metric_name}"
                )
                continue

            component = components[metric_name]

            if not isinstance(component, dict):
                errors.append(
                    f"Invalid component: {metric_name}"
                )
                continue

            status = component.get("status")

            if status not in (
                "OK",
                "MISSING",
                "INVALID",
            ):
                errors.append(
                    f"Invalid status for {metric_name}."
                )

            if status == "OK":
                if not _is_number(
                    component.get("value")
                ):
                    errors.append(
                        f"OK component {metric_name} "
                        "must have numeric value."
                    )

                stars = component.get("stars")

                if not isinstance(stars, int):
                    errors.append(
                        f"OK component {metric_name} "
                        "must have integer stars."
                    )
                elif stars < 1 or stars > 5:
                    errors.append(
                        f"Invalid stars for {metric_name}."
                    )

    warnings = data.get("warnings")

    if not isinstance(warnings, list):
        errors.append(
            "Warnings must be a list."
        )

    limitations = data.get("limitations")

    if not isinstance(limitations, dict):
        errors.append(
            "Limitations must be a dictionary."
        )

    return errors