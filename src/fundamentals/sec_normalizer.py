import json
from datetime import datetime, timezone
from pathlib import Path


# ============================================================
# CONFIGURATION
# ============================================================

RAW_DIR = Path("data/raw/sec")
PROCESSED_DIR = Path("data/processed/fundamentals")


# ============================================================
# BASIC VALIDATION
# ============================================================

def validate_companyfacts(data: dict) -> None:
    required_keys = ["cik", "entityName", "facts"]

    for key in required_keys:
        if key not in data:
            raise ValueError(f"Missing required key: {key}")

    if not isinstance(data["facts"], dict):
        raise ValueError("facts is not a dictionary")


# ============================================================
# SEC FACT HELPERS
# ============================================================

def get_all_concepts(data: dict) -> list:
    concepts = []

    for namespace, namespace_data in data["facts"].items():
        if not isinstance(namespace_data, dict):
            continue

        for concept_name, concept_data in namespace_data.items():
            concepts.append(
                {
                    "namespace": namespace,
                    "concept": concept_name,
                    "data": concept_data,
                }
            )

    return concepts


def get_observations(concept_data: dict) -> list:
    units = concept_data.get("units", {})
    observations = []

    for unit, values in units.items():
        if not isinstance(values, list):
            continue

        for obs in values:
            row = dict(obs)
            row["unit"] = unit
            observations.append(row)

    return observations


# ============================================================
# OBSERVATION CLASSIFICATION
# ============================================================

def is_instant_observation(obs: dict) -> bool:
    return "end" in obs and "start" not in obs


def is_duration_observation(obs: dict) -> bool:
    return "start" in obs and "end" in obs


def is_annual_observation(obs: dict) -> bool:
    return (
        obs.get("form") == "10-K"
        and obs.get("fp") == "FY"
        and is_duration_observation(obs)
    )


# ============================================================
# OBSERVATION SELECTION
# ============================================================

def sort_observations(observations: list) -> list:
    return sorted(
        observations,
        key=lambda x: (
            x.get("filed", ""),
            x.get("end", ""),
            x.get("start", ""),
            x.get("accn", ""),
        ),
        reverse=True,
    )


def select_latest_annual_observation(concept_data: dict):
    annual = [
        obs
        for obs in get_observations(concept_data)
        if is_annual_observation(obs)
    ]

    if not annual:
        return None

    return sort_observations(annual)[0]


def select_latest_instant_observation(concept_data: dict):
    instant = [
        obs
        for obs in get_observations(concept_data)
        if is_instant_observation(obs)
    ]

    if not instant:
        return None

    return sort_observations(instant)[0]


# ============================================================
# CONCEPT LOOKUP
# ============================================================

def find_concept(data: dict, namespace: str, concept_name: str):
    facts = data.get("facts", {})
    namespace_data = facts.get(namespace)

    if not isinstance(namespace_data, dict):
        return None

    return namespace_data.get(concept_name)


def find_best_annual_concept(
    data: dict,
    concept_candidates: list,
    namespaces=("us-gaap",),
):
    for concept_name in concept_candidates:
        for namespace in namespaces:
            concept_data = find_concept(
                data,
                namespace,
                concept_name,
            )

            if concept_data is None:
                continue

            observation = select_latest_annual_observation(concept_data)

            if observation is None:
                continue

            return {
                "namespace": namespace,
                "concept": concept_name,
                "observation": observation,
            }

    return None


def find_best_instant_concept(
    data: dict,
    concept_candidates: list,
    namespaces=("us-gaap", "dei"),
):
    for concept_name in concept_candidates:
        for namespace in namespaces:
            concept_data = find_concept(
                data,
                namespace,
                concept_name,
            )

            if concept_data is None:
                continue

            observation = select_latest_instant_observation(concept_data)

            if observation is None:
                continue

            return {
                "namespace": namespace,
                "concept": concept_name,
                "observation": observation,
            }

    return None


# ============================================================
# RESULT BUILDERS
# ============================================================

def build_missing_metric(metric_name: str, reason: str = None):
    result = {
        "metric": metric_name,
        "status": "MISSING",
        "value": None,
    }

    if reason:
        result["reason"] = reason

    return result


def build_not_applicable_metric(metric_name: str, reason: str):
    return {
        "metric": metric_name,
        "status": "NOT_APPLICABLE",
        "value": None,
        "reason": reason,
    }


def build_metric_result(
    metric_name: str,
    namespace: str,
    concept: str,
    observation: dict,
):
    return {
        "metric": metric_name,
        "status": "OK",
        "namespace": namespace,
        "concept": concept,
        "unit": observation.get("unit"),
        "value": observation.get("val"),
        "period_start": observation.get("start"),
        "period_end": observation.get("end"),
        "filing_date": observation.get("filed"),
        "form": observation.get("form"),
        "fy": observation.get("fy"),
        "fp": observation.get("fp"),
        "frame": observation.get("frame"),
        "accession": observation.get("accn"),
    }


def build_instant_result(
    metric_name: str,
    namespace: str,
    concept: str,
    observation: dict,
):
    return {
        "metric": metric_name,
        "status": "OK",
        "namespace": namespace,
        "concept": concept,
        "unit": observation.get("unit"),
        "value": observation.get("val"),
        "period_end": observation.get("end"),
        "filing_date": observation.get("filed"),
        "form": observation.get("form"),
        "fy": observation.get("fy"),
        "fp": observation.get("fp"),
        "frame": observation.get("frame"),
        "accession": observation.get("accn"),
    }


# ============================================================
# METRIC EXTRACTION
# ============================================================

def extract_metric(
    data: dict,
    metric_name: str,
    concept_candidates: list,
    namespaces=("us-gaap",),
):
    result = find_best_annual_concept(
        data,
        concept_candidates,
        namespaces,
    )

    if result is None:
        return build_missing_metric(metric_name)

    return build_metric_result(
        metric_name,
        result["namespace"],
        result["concept"],
        result["observation"],
    )


def extract_instant_metric(
    data: dict,
    metric_name: str,
    concept_candidates: list,
    namespaces=("us-gaap", "dei"),
):
    result = find_best_instant_concept(
        data,
        concept_candidates,
        namespaces,
    )

    if result is None:
        return build_missing_metric(metric_name)

    return build_instant_result(
        metric_name,
        result["namespace"],
        result["concept"],
        result["observation"],
    )


# ============================================================
# TOTAL DEBT
# ============================================================

def calculate_total_debt(
    current_debt: dict,
    noncurrent_debt: dict,
    company_type: str,
):
    if company_type == "FINANCIAL":
        return {
            "metric": "total_debt",
            "status": "NOT_APPLICABLE",
            "value": None,
            "reason": (
                "Generic EV debt calculation is not "
                "appropriate for financial companies."
            ),
            "components": {
                "current_debt": current_debt,
                "noncurrent_debt": noncurrent_debt,
            },
        }

    result = {
        "metric": "total_debt",
        "status": "INCOMPLETE",
        "value": None,
        "components": {
            "current_debt": current_debt,
            "noncurrent_debt": noncurrent_debt,
        },
    }

    current_value = current_debt.get("value")
    noncurrent_value = noncurrent_debt.get("value")

    if (
        current_debt.get("status") == "OK"
        and noncurrent_debt.get("status") == "OK"
        and isinstance(current_value, (int, float))
        and isinstance(noncurrent_value, (int, float))
    ):
        result["value"] = current_value + noncurrent_value
        result["status"] = "OK"

    return result


# ============================================================
# COMPANY NORMALIZATION
# ============================================================

def normalize_company(
    ticker: str,
    data: dict,
    company_type: str,
):
    validate_companyfacts(data)

    revenue = extract_metric(
        data,
        "revenue",
        [
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "SalesRevenueNet",
            "Revenues",
        ],
    )

    net_income = extract_metric(
        data,
        "net_income",
        [
            "NetIncomeLoss",
            "ProfitLoss",
        ],
    )

    diluted_eps = extract_metric(
        data,
        "diluted_eps",
        [
            "EarningsPerShareDiluted",
        ],
    )

    if company_type == "FINANCIAL":
        operating_income = build_not_applicable_metric(
            "operating_income",
            "Generic operating income framework is not used for financial companies.",
        )
    else:
        operating_income = extract_metric(
            data,
            "operating_income",
            ["OperatingIncomeLoss"],
        )

    if company_type == "FINANCIAL":
        cfo = build_not_applicable_metric(
            "cfo",
            "Generic CFO/FCF framework is not used for financial companies.",
        )
    else:
        cfo = extract_metric(
            data,
            "cfo",
            ["NetCashProvidedByUsedInOperatingActivities"],
        )

    if company_type == "FINANCIAL":
        capex = build_not_applicable_metric(
            "capex",
            "Generic CapEx/FCF framework is not used for financial companies.",
        )
    else:
        capex = extract_metric(
            data,
            "capex",
            [
                "PaymentsToAcquirePropertyPlantAndEquipment",
                "PaymentsToAcquireOtherPropertyPlantAndEquipment",
            ],
        )

    cash = extract_instant_metric(
        data,
        "cash",
        ["CashAndCashEquivalentsAtCarryingValue"],
    )

    if company_type == "FINANCIAL":
        current_debt = build_not_applicable_metric(
            "current_debt",
            "Generic industrial debt framework is not used for financial companies.",
        )
    else:
        current_debt = extract_instant_metric(
            data,
            "current_debt",
            [
                "LongTermDebtCurrent",
                "ShortTermBorrowings",
                "ShortTermDebt",
                "CurrentDebt",
            ],
        )

    if company_type == "FINANCIAL":
        noncurrent_debt = build_not_applicable_metric(
            "noncurrent_debt",
            "Generic industrial debt framework is not used for financial companies.",
        )
    else:
        noncurrent_debt = extract_instant_metric(
            data,
            "noncurrent_debt",
            ["LongTermDebtNoncurrent"],
        )

    # ========================================================
    # STOCKHOLDERS' EQUITY
    # ========================================================
    # Optional in v0.1 validation, but normalized now because
    # P/B valuation requires book equity.
    stockholders_equity = extract_instant_metric(
        data,
        "stockholders_equity",
        ["StockholdersEquity"],
    )

    shares = extract_instant_metric(
        data,
        "shares_outstanding",
        [
            "EntityCommonStockSharesOutstanding",
            "CommonStockSharesOutstanding",
        ],
        namespaces=("dei", "us-gaap"),
    )

    total_debt = calculate_total_debt(
        current_debt,
        noncurrent_debt,
        company_type,
    )

    return {
        "schema_version": "sec_fundamentals_v0.1",
        "ticker": ticker,
        "entity_name": data.get("entityName"),
        "cik": data.get("cik"),
        "company_type": company_type,
        "source": {
            "provider": "SEC",
            "dataset": "Company Facts",
        },
        "normalized_at": datetime.now(timezone.utc).isoformat(),
        "metrics": {
            "revenue": revenue,
            "net_income": net_income,
            "diluted_eps": diluted_eps,
            "operating_income": operating_income,
            "cfo": cfo,
            "capex": capex,
            "cash": cash,
            "current_debt": current_debt,
            "noncurrent_debt": noncurrent_debt,
            "total_debt": total_debt,
            "stockholders_equity": stockholders_equity,
            "shares_outstanding": shares,
        },
    }


# ============================================================
# NORMALIZED DATA VALIDATION
# ============================================================

def validate_normalized_data(normalized: dict) -> list:
    required_top_level = [
        "schema_version",
        "ticker",
        "entity_name",
        "cik",
        "company_type",
        "metrics",
    ]

    for key in required_top_level:
        if key not in normalized:
            raise ValueError(f"Missing normalized key: {key}")

    company_type = normalized["company_type"]

    if company_type == "NON_FINANCIAL":
        required_metrics = [
            "revenue",
            "net_income",
            "diluted_eps",
            "operating_income",
            "cfo",
            "capex",
            "cash",
            "shares_outstanding",
        ]
    elif company_type == "FINANCIAL":
        required_metrics = [
            "revenue",
            "net_income",
            "diluted_eps",
            "cash",
            "shares_outstanding",
        ]
    else:
        raise ValueError(f"Unknown company_type: {company_type}")

    failures = []

    for metric in required_metrics:
        metric_data = normalized["metrics"].get(metric)

        if not isinstance(metric_data, dict):
            failures.append(metric)
            continue

        if metric_data.get("status") != "OK":
            failures.append(metric)

    total_debt = normalized["metrics"]["total_debt"]

    if company_type == "NON_FINANCIAL":
        if total_debt.get("status") != "OK":
            failures.append("total_debt")
    else:
        if total_debt.get("status") != "NOT_APPLICABLE":
            failures.append("total_debt")

    # stockholders_equity is intentionally optional in v0.1.
    # Missing equity must not invalidate the whole SEC normalization.
    return failures


# ============================================================
# FILE HELPERS
# ============================================================

def load_raw_companyfacts(
    ticker: str,
    raw_dir: Path = RAW_DIR,
) -> dict:
    path = raw_dir / f"{ticker}_companyfacts.json"

    if not path.exists():
        raise FileNotFoundError(
            f"Raw SEC file not found: {path}"
        )

    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_normalized_data(
    ticker: str,
    normalized: dict,
    processed_dir: Path = PROCESSED_DIR,
) -> Path:
    processed_dir.mkdir(parents=True, exist_ok=True)

    path = processed_dir / f"{ticker}_fundamentals.json"

    with path.open("w", encoding="utf-8") as f:
        json.dump(
            normalized,
            f,
            ensure_ascii=False,
            indent=2,
        )

    return path


# ============================================================
# NORMALIZE FROM CACHE
# ============================================================

def normalize_from_cache(
    ticker: str,
    company_type: str,
    raw_dir: Path = RAW_DIR,
    processed_dir: Path = PROCESSED_DIR,
):
    data = load_raw_companyfacts(ticker, raw_dir)

    normalized = normalize_company(
        ticker,
        data,
        company_type,
    )

    failures = validate_normalized_data(normalized)

    output_path = save_normalized_data(
        ticker,
        normalized,
        processed_dir,
    )

    return {
        "ticker": ticker,
        "output_path": str(output_path),
        "failures": failures,
        "normalized": normalized,
    }
