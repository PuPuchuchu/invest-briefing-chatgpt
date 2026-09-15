import sys
from pathlib import Path


# ============================================================
# TEST PATH CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


from fundamentals.quality import (
    QUALITY_METRICS,
    QUALITY_WEIGHTS,
    calculate_quality,
    rate_operating_margin,
    rate_net_margin,
    rate_fcf_margin,
    rate_fcf_conversion,
    rate_net_debt_to_fcf,
    rate_debt_to_cash,
    rate_profit_to_cash_consistency,
    validate_quality,
)


# ============================================================
# HELPERS
# ============================================================

def _ok_metric(value):
    return {
        "status": "OK",
        "value": value,
    }


def _build_derived(
    *,
    operating_margin=0.20,
    net_margin=0.15,
    fcf_margin=0.18,
    fcf=18.0,
    net_debt=0.0,
    debt_to_cash=0.0,
):
    return {
        "schema_version": "derived_metrics_v0.1",
        "ticker": "TEST",
        "derived_metrics": {
            "operating_margin": _ok_metric(operating_margin),
            "net_margin": _ok_metric(net_margin),
            "fcf_margin": _ok_metric(fcf_margin),
            "fcf": _ok_metric(fcf),
            "net_debt": _ok_metric(net_debt),
            "debt_to_cash": _ok_metric(debt_to_cash),
        },
    }


def _build_normalized(
    *,
    company_type="NON_FINANCIAL",
    net_income=15.0,
):
    return {
        "schema_version": "sec_normalized_v0.1",
        "ticker": "TEST",
        "company_type": company_type,
        "metrics": {
            "net_income": _ok_metric(net_income),
        },
    }


# ============================================================
# CONFIGURATION TESTS
# ============================================================

def test_quality_metrics_configuration():
    expected_metrics = {
        "operating_margin",
        "net_margin",
        "fcf_margin",
        "fcf_conversion",
        "net_debt_to_fcf",
        "debt_to_cash",
        "profit_to_cash_consistency",
    }

    assert set(QUALITY_METRICS) == expected_metrics


def test_quality_weights_sum_to_one():
    assert abs(sum(QUALITY_WEIGHTS.values()) - 1.0) < 1e-9


def test_quality_weights_cover_all_metrics():
    assert set(QUALITY_WEIGHTS.keys()) == set(QUALITY_METRICS)


# ============================================================
# STAR THRESHOLD TESTS
# ============================================================

def test_operating_margin_thresholds():
    assert rate_operating_margin(0.049) == 1
    assert rate_operating_margin(0.05) == 2
    assert rate_operating_margin(0.099) == 2
    assert rate_operating_margin(0.10) == 3
    assert rate_operating_margin(0.199) == 3
    assert rate_operating_margin(0.20) == 4
    assert rate_operating_margin(0.299) == 4
    assert rate_operating_margin(0.30) == 5


def test_net_margin_thresholds():
    assert rate_net_margin(0.019) == 1
    assert rate_net_margin(0.02) == 2
    assert rate_net_margin(0.059) == 2
    assert rate_net_margin(0.06) == 3
    assert rate_net_margin(0.119) == 3
    assert rate_net_margin(0.12) == 4
    assert rate_net_margin(0.199) == 4
    assert rate_net_margin(0.20) == 5


def test_fcf_margin_thresholds():
    assert rate_fcf_margin(0.019) == 1
    assert rate_fcf_margin(0.02) == 2
    assert rate_fcf_margin(0.059) == 2
    assert rate_fcf_margin(0.06) == 3
    assert rate_fcf_margin(0.119) == 3
    assert rate_fcf_margin(0.12) == 4
    assert rate_fcf_margin(0.199) == 4
    assert rate_fcf_margin(0.20) == 5


def test_fcf_conversion_thresholds():
    assert rate_fcf_conversion(0.399) == 1
    assert rate_fcf_conversion(0.40) == 2
    assert rate_fcf_conversion(0.599) == 2
    assert rate_fcf_conversion(0.60) == 3
    assert rate_fcf_conversion(0.799) == 3
    assert rate_fcf_conversion(0.80) == 4
    assert rate_fcf_conversion(0.999) == 4
    assert rate_fcf_conversion(1.00) == 5


def test_net_debt_to_fcf_thresholds():
    assert rate_net_debt_to_fcf(1.0) == 5
    assert rate_net_debt_to_fcf(1.5) == 4
    assert rate_net_debt_to_fcf(2.0) == 4
    assert rate_net_debt_to_fcf(2.5) == 3
    assert rate_net_debt_to_fcf(3.0) == 3
    assert rate_net_debt_to_fcf(3.5) == 2
    assert rate_net_debt_to_fcf(4.0) == 2
    assert rate_net_debt_to_fcf(4.1) == 1


def test_debt_to_cash_thresholds():
    assert rate_debt_to_cash(0.5) == 5
    assert rate_debt_to_cash(0.75) == 4
    assert rate_debt_to_cash(1.0) == 4
    assert rate_debt_to_cash(1.5) == 3
    assert rate_debt_to_cash(2.0) == 3
    assert rate_debt_to_cash(3.0) == 2
    assert rate_debt_to_cash(4.0) == 2
    assert rate_debt_to_cash(4.1) == 1


def test_profit_to_cash_consistency_thresholds():
    assert rate_profit_to_cash_consistency(0.599) == 1
    assert rate_profit_to_cash_consistency(0.60) == 2
    assert rate_profit_to_cash_consistency(0.799) == 2
    assert rate_profit_to_cash_consistency(0.80) == 3
    assert rate_profit_to_cash_consistency(0.999) == 3
    assert rate_profit_to_cash_consistency(1.00) == 4
    assert rate_profit_to_cash_consistency(1.199) == 4
    assert rate_profit_to_cash_consistency(1.20) == 5


# ============================================================
# MAIN QUALITY CALCULATION
# ============================================================

def test_calculate_quality_returns_expected_structure():
    normalized = _build_normalized()

    derived = _build_derived(
        operating_margin=0.25,
        net_margin=0.15,
        fcf_margin=0.18,
        fcf=18.0,
        net_debt=10.0,
        debt_to_cash=0.5,
    )

    result = calculate_quality(normalized, derived)

    assert result["status"] in {"OK", "MISSING"}
    assert result["ticker"] == "TEST"
    assert "metrics" in result
    assert "overall_score" in result
    assert "overall_stars" in result
    assert "limitations" in result


def test_calculate_quality_contains_all_quality_metrics():
    result = calculate_quality(
        _build_normalized(),
        _build_derived(),
    )

    assert set(result["metrics"].keys()) == set(QUALITY_METRICS)


def test_calculate_quality_score_is_bounded():
    result = calculate_quality(
        _build_normalized(),
        _build_derived(),
    )

    assert 0.0 <= result["overall_score"] <= 5.0
    assert 1 <= result["overall_stars"] <= 5


# ============================================================
# MISSING COMPONENT HANDLING
# ============================================================

def test_missing_components_are_excluded_from_score():
    derived = _build_derived()

    derived["derived_metrics"]["operating_margin"] = {
        "status": "MISSING",
        "value": None,
    }

    derived["derived_metrics"]["net_margin"] = {
        "status": "MISSING",
        "value": None,
    }

    result = calculate_quality(
        _build_normalized(),
        derived,
    )

    assert result["metrics"]["operating_margin"]["status"] == "MISSING"
    assert result["metrics"]["net_margin"]["status"] == "MISSING"

    assert result["status"] in {"OK", "MISSING"}


def test_quality_requires_minimum_four_valid_components():
    derived = _build_derived()

    for metric_name in [
        "operating_margin",
        "net_margin",
        "fcf_margin",
        "debt_to_cash",
    ]:
        derived["derived_metrics"][metric_name] = {
            "status": "MISSING",
            "value": None,
        }

    result = calculate_quality(
        _build_normalized(),
        derived,
    )

    assert result["status"] == "MISSING"


# ============================================================
# EDGE CASES
# ============================================================

def test_negative_net_income_does_not_create_invalid_quality_result():
    normalized = _build_normalized(net_income=-10.0)

    derived = _build_derived(
        operating_margin=-0.05,
        net_margin=-0.10,
        fcf_margin=-0.02,
        fcf=-2.0,
        net_debt=20.0,
        debt_to_cash=2.0,
    )

    result = calculate_quality(normalized, derived)

    assert result["status"] in {"OK", "MISSING"}
    assert result["overall_stars"] >= 1


def test_negative_net_debt_is_not_treated_as_bad():
    derived = _build_derived(
        fcf=20.0,
        net_debt=-20.0,
    )

    result = calculate_quality(
        _build_normalized(),
        derived,
    )

    metric = result["metrics"]["net_debt_to_fcf"]

    assert metric["status"] == "OK"
    assert metric["value"] == -1.0
    assert metric["stars"] == 5


# ============================================================
# FINANCIAL COMPANY HANDLING
# ============================================================

def test_financial_company_contains_limitation():
    normalized = _build_normalized(
        company_type="FINANCIAL",
    )

    derived = _build_derived()

    result = calculate_quality(normalized, derived)

    assert "limitations" in result
    assert len(result["limitations"]) >= 1


# ============================================================
# VALIDATION
# ============================================================

def test_validate_quality_accepts_valid_result():
    result = calculate_quality(
        _build_normalized(),
        _build_derived(),
    )

    assert validate_quality(result) is True


def test_validate_quality_rejects_invalid_result():
    result = calculate_quality(
        _build_normalized(),
        _build_derived(),
    )

    result["overall_score"] = "invalid"

    assert validate_quality(result) is False


def test_validate_quality_rejects_invalid_status():
    result = calculate_quality(
        _build_normalized(),
        _build_derived(),
    )

    result["status"] = "UNKNOWN"

    assert validate_quality(result) is False


# ============================================================
# TYPE VALIDATION
# ============================================================

def test_rate_functions_reject_non_numeric_values():
    rate_functions = [
        rate_operating_margin,
        rate_net_margin,
        rate_fcf_margin,
        rate_fcf_conversion,
        rate_net_debt_to_fcf,
        rate_debt_to_cash,
        rate_profit_to_cash_consistency,
    ]

    for rate_function in rate_functions:
        try:
            rate_function(None)
        except (TypeError, ValueError):
            pass
        else:
            raise AssertionError(
                f"{rate_function.__name__} should reject non-numeric input"
            )