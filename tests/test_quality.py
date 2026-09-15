from future import annotations

import pytest

from src.fundamentals.quality import (
QUALITY_METRICS,
calculate_fcf_conversion,
calculate_net_debt_to_fcf,
calculate_profit_to_cash_consistency,
calculate_quality,
rate_debt_to_cash,
rate_fcf_conversion,
rate_fcf_margin,
rate_net_debt_to_fcf,
rate_net_margin,
rate_operating_margin,
rate_profit_to_cash_consistency,
validate_quality,
)

============================================================

TEST HELPERS

============================================================

def _ok_metric(value: float) -> dict:
return {
"status": "OK",
"value": value,
}

def _build_derived(
*,
operating_margin: float | None = 0.20,
net_margin: float | None = 0.12,
fcf_margin: float | None = 0.10,
fcf: float | None = 100.0,
net_debt: float | None = 100.0,
debt_to_cash: float | None = 1.0,
) -> dict:

values = {
    "operating_margin": operating_margin,
    "net_margin": net_margin,
    "fcf_margin": fcf_margin,
    "fcf": fcf,
    "net_debt": net_debt,
    "debt_to_cash": debt_to_cash,
}

derived_metrics = {}

for name, value in values.items():

    if value is None:
        derived_metrics[name] = {
            "status": "MISSING",
            "value": None,
        }

    else:
        derived_metrics[name] = _ok_metric(value)

return {
    "schema_version": "derived_metrics_v0.1",
    "ticker": "TEST",
    "derived_metrics": derived_metrics,
}

def _build_normalized(
*,
ticker: str = "TEST",
company_type: str = "NON_FINANCIAL",
net_income: float | None = 100.0,
) -> dict:

if net_income is None:
    net_income_metric = {
        "status": "MISSING",
        "value": None,
    }

else:
    net_income_metric = {
        "status": "OK",
        "value": net_income,
    }

return {
    "schema_version": "sec_normalized_v0.1",
    "ticker": ticker,
    "company_type": company_type,
    "metrics": {
        "net_income": net_income_metric,
    },
}

============================================================

BASIC CONFIGURATION

============================================================

def test_quality_metric_configuration():

assert QUALITY_METRICS == [
    "operating_margin",
    "net_margin",
    "fcf_margin",
    "fcf_conversion",
    "net_debt_to_fcf",
    "debt_to_cash",
    "profit_to_cash_consistency",
]

============================================================

OPERATING MARGIN

============================================================

@pytest.mark.parametrize(
"value, expected_stars",
[
(0.30, 5),
(0.20, 4),
(0.10, 3),
(0.05, 2),
(0.0499, 1),
(-0.10, 1),
],
)
def test_rate_operating_margin_thresholds(
value,
expected_stars,
):

result = rate_operating_margin(value)

assert result["status"] == "OK"
assert result["value"] == pytest.approx(value)
assert result["stars"] == expected_stars

def test_rate_operating_margin_missing():

result = rate_operating_margin(None)

assert result["status"] == "MISSING"
assert result["value"] is None
assert result["stars"] is None

============================================================

NET MARGIN

============================================================

@pytest.mark.parametrize(
"value, expected_stars",
[
(0.20, 5),
(0.12, 4),
(0.06, 3),
(0.02, 2),
(0.0199, 1),
(-0.10, 1),
],
)
def test_rate_net_margin_thresholds(
value,
expected_stars,
):

result = rate_net_margin(value)

assert result["status"] == "OK"
assert result["value"] == pytest.approx(value)
assert result["stars"] == expected_stars

def test_rate_net_margin_missing():

result = rate_net_margin(None)

assert result["status"] == "MISSING"
assert result["value"] is None
assert result["stars"] is None

============================================================

FCF MARGIN

============================================================

@pytest.mark.parametrize(
"value, expected_stars",
[
(0.20, 5),
(0.12, 4),
(0.06, 3),
(0.02, 2),
(0.0199, 1),
(0.00, 1),
(-0.10, 1),
],
)
def test_rate_fcf_margin_thresholds(
value,
expected_stars,
):

result = rate_fcf_margin(value)

assert result["status"] == "OK"
assert result["value"] == pytest.approx(value)
assert result["stars"] == expected_stars

def test_rate_fcf_margin_missing():

result = rate_fcf_margin(None)

assert result["status"] == "MISSING"
assert result["value"] is None
assert result["stars"] is None

============================================================

FCF CONVERSION

============================================================

def test_calculate_fcf_conversion():

result = calculate_fcf_conversion(
    net_income_value=100.0,
    fcf_value=80.0,
)

assert result["status"] == "OK"
assert result["value"] == pytest.approx(0.80)

def test_calculate_fcf_conversion_above_100_percent():

result = calculate_fcf_conversion(
    net_income_value=100.0,
    fcf_value=120.0,
)

assert result["status"] == "OK"
assert result["value"] == pytest.approx(1.20)

def test_calculate_fcf_conversion_negative_fcf():

result = calculate_fcf_conversion(
    net_income_value=100.0,
    fcf_value=-20.0,
)

assert result["status"] == "OK"
assert result["value"] == pytest.approx(-0.20)

def test_calculate_fcf_conversion_zero_net_income():

result = calculate_fcf_conversion(
    net_income_value=0.0,
    fcf_value=100.0,
)

assert result["status"] == "INVALID"
assert result["value"] is None

def test_calculate_fcf_conversion_negative_net_income():

result = calculate_fcf_conversion(
    net_income_value=-100.0,
    fcf_value=50.0,
)

assert result["status"] == "INVALID"
assert result["value"] is None

def test_calculate_fcf_conversion_missing_net_income():

result = calculate_fcf_conversion(
    net_income_value=None,
    fcf_value=50.0,
)

assert result["status"] == "MISSING"

def test_calculate_fcf_conversion_missing_fcf():

result = calculate_fcf_conversion(
    net_income_value=100.0,
    fcf_value=None,
)

assert result["status"] == "MISSING"

@pytest.mark.parametrize(
"value, expected_stars",
[
(1.00, 5),
(0.80, 4),
(0.60, 3),
(0.40, 2),
(0.3999, 1),
(-0.20, 1),
],
)
def test_rate_fcf_conversion_thresholds(
value,
expected_stars,
):

result = rate_fcf_conversion(value)

assert result["status"] == "OK"
assert result["stars"] == expected_stars

============================================================

NET DEBT / FCF

============================================================

def test_calculate_net_debt_to_fcf():

result = calculate_net_debt_to_fcf(
    net_debt_value=200.0,
    fcf_value=100.0,
)

assert result["status"] == "OK"
assert result["value"] == pytest.approx(2.0)

def test_calculate_net_debt_to_fcf_net_cash():

result = calculate_net_debt_to_fcf(
    net_debt_value=-200.0,
    fcf_value=100.0,
)

assert result["status"] == "OK"
assert result["value"] == pytest.approx(-2.0)

def test_calculate_net_debt_to_fcf_zero_fcf():

result = calculate_net_debt_to_fcf(
    net_debt_value=100.0,
    fcf_value=0.0,
)

assert result["status"] == "INVALID"
assert result["value"] is None

def test_calculate_net_debt_to_fcf_negative_fcf():

result = calculate_net_debt_to_fcf(
    net_debt_value=100.0,
    fcf_value=-50.0,
)

assert result["status"] == "INVALID"
assert result["value"] is None

@pytest.mark.parametrize(
"value, expected_stars",
[
(-2.0, 5),
(-1.0, 5),
(0.0, 5),
(1.0, 5),
(1.0001, 4),
(2.0, 4),
(2.0001, 3),
(3.0, 3),
(3.0001, 2),
(4.0, 2),
(4.0001, 1),
],
)
def test_rate_net_debt_to_fcf_thresholds(
value,
expected_stars,
):

result = rate_net_debt_to_fcf(value)

assert result["status"] == "OK"
assert result["stars"] == expected_stars

============================================================

DEBT / CASH

============================================================

@pytest.mark.parametrize(
"value, expected_stars",
[
(0.0, 5),
(0.5, 5),
(0.5001, 4),
(1.0, 4),
(1.0001, 3),
(2.0, 3),
(2.0001, 2),
(4.0, 2),
(4.0001, 1),
],
)
def test_rate_debt_to_cash_thresholds(
value,
expected_stars,
):

result = rate_debt_to_cash(value)

assert result["status"] == "OK"
assert result["stars"] == expected_stars

============================================================

PROFIT-TO-CASH CONSISTENCY

============================================================

def test_calculate_profit_to_cash_consistency():

result = calculate_profit_to_cash_consistency(
    net_margin_value=0.10,
    fcf_margin_value=0.10,
)

assert result["status"] == "OK"
assert result["value"] == pytest.approx(1.0)

def test_calculate_profit_to_cash_consistency_above_one():

result = calculate_profit_to_cash_consistency(
    net_margin_value=0.10,
    fcf_margin_value=0.15,
)

assert result["status"] == "OK"
assert result["value"] == pytest.approx(1.5)

def test_calculate_profit_to_cash_consistency_zero_net_margin():

result = calculate_profit_to_cash_consistency(
    net_margin_value=0.0,
    fcf_margin_value=0.10,
)

assert result["status"] == "INVALID"
assert result["value"] is None

def test_calculate_profit_to_cash_consistency_negative_net_margin():

result = calculate_profit_to_cash_consistency(
    net_margin_value=-0.10,
    fcf_margin_value=0.10,
)

assert result["status"] == "INVALID"
assert result["value"] is None

@pytest.mark.parametrize(
"value, expected_stars",
[
(1.20, 5),
(1.00, 4),
(0.80, 3),
(0.60, 2),
(0.5999, 1),
],
)
def test_rate_profit_to_cash_consistency_thresholds(
value,
expected_stars,
):

result = rate_profit_to_cash_consistency(value)

assert result["status"] == "OK"
assert result["stars"] == expected_stars

============================================================

MAIN QUALITY CALCULATION

============================================================

def test_calculate_quality_returns_valid_result():

normalized = _build_normalized()

derived = _build_derived(
    operating_margin=0.20,
    net_margin=0.12,
    fcf_margin=0.10,
    fcf=100.0,
    net_debt=100.0,
    debt_to_cash=1.0,
)

result = calculate_quality(
    normalized,
    derived,
)

assert result["schema_version"] == "quality_v0.1"
assert result["ticker"] == "TEST"
assert result["company_type"] == "NON_FINANCIAL"

assert "quality" in result
assert "components" in result
assert "limitations" in result

assert result["quality"]["status"] == "OK"
assert result["quality"]["score"] is not None
assert result["quality"]["stars"] in {
    1,
    2,
    3,
    4,
    5,
}

def test_calculate_quality_contains_all_components():

normalized = _build_normalized()

derived = _build_derived()

result = calculate_quality(
    normalized,
    derived,
)

assert set(result["components"].keys()) == set(
    QUALITY_METRICS
)

def test_calculate_quality_has_expected_component_statuses():

normalized = _build_normalized()

derived = _build_derived(
    operating_margin=0.20,
    net_margin=0.12,
    fcf_margin=0.10,
    fcf=100.0,
    net_debt=100.0,
    debt_to_cash=1.0,
)

result = calculate_quality(
    normalized,
    derived,
)

for metric_name in [
    "operating_margin",
    "net_margin",
    "fcf_margin",
    "fcf_conversion",
    "net_debt_to_fcf",
    "debt_to_cash",
    "profit_to_cash_consistency",
]:

    assert result["components"][metric_name]["status"] == "OK"

============================================================

MISSING DATA HANDLING

============================================================

def test_missing_components_are_not_treated_as_zero():

normalized = _build_normalized(
    net_income=100.0,
)

derived = _build_derived(
    operating_margin=0.20,
    net_margin=0.12,
    fcf_margin=0.10,
    fcf=100.0,
    net_debt=None,
    debt_to_cash=None,
)

result = calculate_quality(
    normalized,
    derived,
)

assert result["quality"]["status"] == "OK"

assert (
    result["components"]["net_debt_to_fcf"]["status"]
    == "MISSING"
)

assert (
    result["components"]["debt_to_cash"]["status"]
    == "MISSING"
)

assert result["quality"]["available_components"] == 5

def test_insufficient_component_coverage_returns_missing():

normalized = _build_normalized(
    net_income=100.0,
)

derived = _build_derived(
    operating_margin=0.20,
    net_margin=0.12,
    fcf_margin=None,
    fcf=None,
    net_debt=None,
    debt_to_cash=None,
)

result = calculate_quality(
    normalized,
    derived,
)

assert result["quality"]["status"] == "MISSING"
assert result["quality"]["score"] is None
assert result["quality"]["stars"] is None

assert result["quality"]["available_components"] == 2

============================================================

NEGATIVE NET INCOME

============================================================

def test_negative_net_income_makes_fcf_conversion_invalid():

normalized = _build_normalized(
    net_income=-100.0,
)

derived = _build_derived(
    operating_margin=0.10,
    net_margin=-0.05,
    fcf_margin=0.02,
    fcf=50.0,
    net_debt=100.0,
    debt_to_cash=1.0,
)

result = calculate_quality(
    normalized,
    derived,
)

assert (
    result["components"]["fcf_conversion"]["status"]
    == "INVALID"
)

assert (
    result["components"]["profit_to_cash_consistency"]["status"]
    == "INVALID"
)

============================================================

FINANCIAL COMPANY HANDLING

============================================================

def test_financial_company_is_explicitly_flagged():

normalized = _build_normalized(
    company_type="FINANCIAL",
)

derived = _build_derived()

result = calculate_quality(
    normalized,
    derived,
)

assert "financial_company" in result["limitations"]

assert (
    result["limitations"]["financial_company"]["status"]
    == "WARNING"
)

============================================================

VALIDATION

============================================================

def test_validate_quality_accepts_valid_quality_result():

normalized = _build_normalized()

derived = _build_derived()

result = calculate_quality(
    normalized,
    derived,
)

failures = validate_quality(result)

assert failures == []

def test_validate_quality_rejects_invalid_quality_status():

normalized = _build_normalized()

derived = _build_derived()

result = calculate_quality(
    normalized,
    derived,
)

result["quality"]["status"] = "INVALID_STATUS"

failures = validate_quality(result)

assert "quality.status" in failures

def test_validate_quality_rejects_invalid_component_status():

normalized = _build_normalized()

derived = _build_derived()

result = calculate_quality(
    normalized,
    derived,
)

result["components"]["net_margin"]["status"] = (
    "INVALID_STATUS"
)

failures = validate_quality(result)

assert (
    "components.net_margin.status"
    in failures
)

def test_validate_quality_rejects_non_numeric_ok_component():

normalized = _build_normalized()

derived = _build_derived()

result = calculate_quality(
    normalized,
    derived,
)

result["components"]["net_margin"]["value"] = (
    "not-a-number"
)

failures = validate_quality(result)

assert (
    "components.net_margin.value"
    in failures
)

def test_validate_quality_rejects_non_null_missing_value():

normalized = _build_normalized()

derived = _build_derived()

result = calculate_quality(
    normalized,
    derived,
)

result["components"]["net_margin"] = {
    "metric": "net_margin",
    "status": "MISSING",
    "value": 0.10,
    "rating": None,
    "stars": None,
    "reason": "test",
}

failures = validate_quality(result)

assert (
    "components.net_margin.value"
    in failures
)

============================================================

TYPE VALIDATION

============================================================

def test_calculate_quality_rejects_non_dict_normalized():

with pytest.raises(TypeError):

    calculate_quality(
        normalized=[],
        derived=_build_derived(),
    )

def test_calculate_quality_rejects_non_dict_derived():

with pytest.raises(TypeError):

    calculate_quality(
        normalized=_build_normalized(),
        derived=[],
    )

def test_calculate_quality_rejects_invalid_normalized_metrics():

normalized = _build_normalized()

normalized["metrics"] = []

with pytest.raises(ValueError):

    calculate_quality(
        normalized=normalized,
        derived=_build_derived(),
    )

def test_calculate_quality_rejects_invalid_derived_metrics():

derived = _build_derived()

derived["derived_metrics"] = []

with pytest.raises(ValueError):

    calculate_quality(
        normalized=_build_normalized(),
        derived=derived,
    )