from __future__ import annotations

from math import isfinite
from typing import Any


# ============================================================
# CONFIGURATION
# ============================================================

SCHEMA_VERSION = "derived_metrics_v0.1"


# ============================================================
# BASIC HELPERS
# ============================================================

def _is_number(value: Any) -> bool:
    """
    Return True only for finite int/float values.
    bool is intentionally excluded because bool is a subclass of int.
    """
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and isfinite(float(value))
    )


def _build_ok_metric(
    metric_name: str,
    value: float | int,
    source_metrics: list[str] | None = None,
    reason: str | None = None,
) -> dict:
    result = {
        "metric": metric_name,
        "status": "OK",
        "value": value,
    }

    if source_metrics is not None:
        result["source_metrics"] = source_metrics

    if reason is not None:
        result["reason"] = reason

    return result


def _build_missing_metric(
    metric_name: str,
    reason: str,
    source_metrics: list[str] | None = None,
) -> dict:
    result = {
        "metric": metric_name,
        "status": "MISSING",
        "value": None,
        "reason": reason,
    }

    if source_metrics is not None:
        result["source_metrics"] = source_metrics

    return result


def _build_invalid_metric(
    metric_name: str,
    reason: str,
    source_metrics: list[str] | None = None,
) -> dict:
    result = {
        "metric": metric_name,
        "status": "INVALID",
        "value": None,
        "reason": reason,
    }

    if source_metrics is not None:
        result["source_metrics"] = source_metrics

    return result


# ============================================================
# GROWTH
# ============================================================

def calculate_yoy(
    metric_name: str,
    current_value: Any,
    previous_value: Any,
) -> dict:
    """
    Calculate year-over-year growth.

    Formula:
        (current / previous) - 1

    Returned value is decimal form.
    Example:
        120 / 100 - 1 = 0.20
    """

    if not _is_number(current_value):
        return _build_missing_metric(
            metric_name=f"{metric_name}_yoy",
            reason="Current value is missing or non-numeric.",
            source_metrics=[metric_name],
        )

    if not _is_number(previous_value):
        return _build_missing_metric(
            metric_name=f"{metric_name}_yoy",
            reason="Previous value is missing or non-numeric.",
            source_metrics=[metric_name],
        )

    if float(previous_value) == 0:
        return _build_invalid_metric(
            metric_name=f"{metric_name}_yoy",
            reason="Previous value is zero; YoY cannot be calculated.",
            source_metrics=[metric_name],
        )

    value = float(current_value) / float(previous_value) - 1.0

    return _build_ok_metric(
        metric_name=f"{metric_name}_yoy",
        value=value,
        source_metrics=[metric_name],
    )


# ============================================================
# CAGR
# ============================================================

def calculate_cagr(
    metric_name: str,
    start_value: Any,
    end_value: Any,
    years: Any,
) -> dict:
    """
    Calculate CAGR.

    Formula:
        (end / start) ** (1 / years) - 1

    Policy:
    - years must be positive.
    - start must be strictly positive.
    - end must be non-negative.
    - CAGR is not calculated when the starting value is <= 0.
    """

    result_name = f"{metric_name}_cagr"

    if not _is_number(start_value):
        return _build_missing_metric(
            result_name,
            "Start value is missing or non-numeric.",
            [metric_name],
        )

    if not _is_number(end_value):
        return _build_missing_metric(
            result_name,
            "End value is missing or non-numeric.",
            [metric_name],
        )

    if not _is_number(years):
        return _build_missing_metric(
            result_name,
            "Years is missing or non-numeric.",
            [metric_name],
        )

    years_float = float(years)

    if years_float <= 0:
        return _build_invalid_metric(
            result_name,
            "Years must be greater than zero.",
            [metric_name],
        )

    start_float = float(start_value)
    end_float = float(end_value)

    if start_float <= 0:
        return _build_invalid_metric(
            result_name,
            "CAGR requires a strictly positive starting value.",
            [metric_name],
        )

    if end_float < 0:
        return _build_invalid_metric(
            result_name,
            "CAGR requires a non-negative ending value.",
            [metric_name],
        )

    value = (end_float / start_float) ** (1.0 / years_float) - 1.0

    return _build_ok_metric(
        result_name,
        value,
        [metric_name],
    )


# ============================================================
# MARGINS
# ============================================================

def calculate_margin(
    metric_name: str,
    numerator_value: Any,
    revenue_value: Any,
) -> dict:
    """
    Calculate a revenue-based margin.

    Formula:
        numerator / revenue

    Examples:
        operating income / revenue -> operating margin
        net income / revenue       -> net margin
        FCF / revenue              -> FCF margin
    """

    result_name = f"{metric_name}_margin"

    if not _is_number(numerator_value):
        return _build_missing_metric(
            result_name,
            "Numerator is missing or non-numeric.",
            [metric_name, "revenue"],
        )

    if not _is_number(revenue_value):
        return _build_missing_metric(
            result_name,
            "Revenue is missing or non-numeric.",
            [metric_name, "revenue"],
        )

    revenue_float = float(revenue_value)

    if revenue_float == 0:
        return _build_invalid_metric(
            result_name,
            "Revenue is zero; margin cannot be calculated.",
            [metric_name, "revenue"],
        )

    value = float(numerator_value) / revenue_float

    return _build_ok_metric(
        result_name,
        value,
        [metric_name, "revenue"],
    )


# ============================================================
# FREE CASH FLOW
# ============================================================

def calculate_fcf(
    cfo_value: Any,
    capex_value: Any,
) -> dict:
    """
    Calculate Free Cash Flow.

    SEC CapEx values are commonly represented as negative cash-flow
    values because they are cash outflows.

    Therefore:
        FCF = CFO + CapEx

    Example:
        CFO  = 25,000
        CapEx = -5,000
        FCF  = 20,000

    This function assumes the normalized CapEx convention used by
    sec_normalizer.py.
    """

    if not _is_number(cfo_value):
        return _build_missing_metric(
            "fcf",
            "CFO is missing or non-numeric.",
            ["cfo", "capex"],
        )

    if not _is_number(capex_value):
        return _build_missing_metric(
            "fcf",
            "CapEx is missing or non-numeric.",
            ["cfo", "capex"],
        )

    value = float(cfo_value) + float(capex_value)

    return _build_ok_metric(
        "fcf",
        value,
        ["cfo", "capex"],
    )


# ============================================================
# DEBT / CASH
# ============================================================

def calculate_net_debt(
    total_debt_value: Any,
    cash_value: Any,
) -> dict:
    """
    Calculate net debt.

    Formula:
        Net Debt = Total Debt - Cash
    """

    if not _is_number(total_debt_value):
        return _build_missing_metric(
            "net_debt",
            "Total debt is missing or non-numeric.",
            ["total_debt", "cash"],
        )

    if not _is_number(cash_value):
        return _build_missing_metric(
            "net_debt",
            "Cash is missing or non-numeric.",
            ["total_debt", "cash"],
        )

    value = float(total_debt_value) - float(cash_value)

    return _build_ok_metric(
        "net_debt",
        value,
        ["total_debt", "cash"],
    )


def calculate_debt_to_cash(
    total_debt_value: Any,
    cash_value: Any,
) -> dict:
    """
    Calculate debt-to-cash ratio.

    Formula:
        Total Debt / Cash
    """

    if not _is_number(total_debt_value):
        return _build_missing_metric(
            "debt_to_cash",
            "Total debt is missing or non-numeric.",
            ["total_debt", "cash"],
        )

    if not _is_number(cash_value):
        return _build_missing_metric(
            "debt_to_cash",
            "Cash is missing or non-numeric.",
            ["total_debt", "cash"],
        )

    cash_float = float(cash_value)

    if cash_float == 0:
        return _build_invalid_metric(
            "debt_to_cash",
            "Cash is zero; debt-to-cash ratio cannot be calculated.",
            ["total_debt", "cash"],
        )

    value = float(total_debt_value) / cash_float

    return _build_ok_metric(
        "debt_to_cash",
        value,
        ["total_debt", "cash"],
    )


# ============================================================
# TTM
# ============================================================

def calculate_ttm_from_quarters(
    metric_name: str,
    quarterly_values: list[Any],
) -> dict:
    """
    Calculate TTM from four standalone quarterly values.

    IMPORTANT:
    This function intentionally requires exactly four valid
    standalone-quarter values.

    It does NOT attempt to interpret YTD SEC observations.

    That