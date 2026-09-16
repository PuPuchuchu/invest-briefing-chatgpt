import json
from datetime import datetime, timezone
from pathlib import Path


# ============================================================
# CONFIGURATION
# ============================================================

RAW_DIR = Path("data/raw/sec")
PROCESSED_DIR = Path("data/processed/fundamentals")

SCHEMA_VERSION = "sec_fundamentals_v0.1"


# ============================================================
# BASIC VALIDATION
# ============================================================

def validate_companyfacts(data: dict) -> None:
    """
    Validate minimum SEC Company Facts structure.
    """

    required_keys = [
        "cik",
        "entityName",
        "facts",
    ]

    for key in required_keys:
        if key not in data:
            raise ValueError(
                f"Missing required key: {key}"
            )

    if not isinstance(data["facts"], dict):
        raise ValueError(
            "facts is not a dictionary"
        )


# ============================================================
# SEC FACT HELPERS
# ============================================================

def get_all_concepts(data: dict) -> list:
    """
    Return all concepts from all SEC namespaces.
    """

    validate_companyfacts(data)

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


def get_observations(
    concept_data: dict,
) -> list:
    """
    Flatten SEC concept units into observation rows.
    """

    if not isinstance(concept_data, dict):
        return []

    units = concept_data.get(
        "units",
        {},
    )

    if not isinstance(units, dict):
        return []

    observations = []

    for unit, values in units.items():

        if not isinstance(values, list):
            continue

        for obs in values:

            if not isinstance(obs, dict):
                continue

            row = dict(obs)
            row["unit"] = unit

            observations.append(row)

    return observations


# ============================================================
# OBSERVATION CLASSIFICATION
# ============================================================

def is_instant_observation(
    obs: dict,
) -> bool:
    """
    Balance-sheet style observation.

    Example:
        Cash at 2026-06-30
    """

    return (
        "end" in obs
        and "start" not in obs
    )


def is_duration_observation(
    obs: dict,
) -> bool:
    """
    Income-statement / cash-flow style observation.

    Example:
        Revenue from 2025-07-01 to 2026-06-30
    """

    return (
        "start" in obs
        and "end" in obs
    )


def is_annual_observation(
    obs: dict,
) -> bool:
    """
    Current v0.1 annual definition.

    Only:
        form = 10-K
        fp   = FY
        duration observation
    """

    if obs.get("form") != "10-K":
        return False

    if obs.get("fp") != "FY":
        return False

    return is_duration_observation(obs)


# ============================================================
# BASIC VALUE / DATE HELPERS
# ============================================================

def _is_number(value) -> bool:
    return (
        isinstance(
            value,
            (int, float),
        )
        and not isinstance(
            value,
            bool,
        )
    )


def _date_string(value):
    if value is None:
        return None

    if isinstance(value, str):
        return value[:10]

    return str(value)[:10]


def _observation_sort_key(
    observation: dict,
    concept_priority: int = 0,
):
    """
    Common observation sorting key.

    Ordering:
        1. Economic period end
        2. Filing date
        3. Concept priority
        4. Accession number

    Dates are represented as YYYY-MM-DD strings,
    allowing lexicographical sorting.
    """

    return (
        _date_string(
            observation.get("end")
        )
        or "",
        _date_string(
            observation.get("filed")
        )
        or "",
        -concept_priority,
        observation.get("accn")
        or "",
    )


# ============================================================
# OBSERVATION SELECTION
# ============================================================

def sort_observations(
    observations: list,
) -> list:
    """
    Sort duration observations newest-first.

    For duration metrics, filing date remains the primary
    information-availability ordering because the same
    economic period may be reported or revised in later filings.

    Ordering:
        1. Filing date
        2. Period end
        3. Period start
        4. Accession
    """

    return sorted(
        observations,
        key=lambda x: (
            _date_string(
                x.get("filed")
            )
            or "",
            _date_string(
                x.get("end")
            )
            or "",
            _date_string(
                x.get("start")
            )
            or "",
            x.get("accn")
            or "",
        ),
        reverse=True,
    )


def sort_instant_observations(
    observations: list,
) -> list:
    """
    Sort balance-sheet / instant observations.

    Economic period end is prioritized over filing date.

    Ordering:
        1. Period end
        2. Filing date
        3. Accession
    """

    return sorted(
        observations,
        key=lambda x: (
            _date_string(
                x.get("end")
            )
            or "",
            _date_string(
                x.get("filed")
            )
            or "",
            x.get("accn")
            or "",
        ),
        reverse=True,
    )


def select_latest_annual_observation(
    concept_data: dict,
):
    """
    Select latest valid annual observation.
    """

    observations = get_observations(
        concept_data
    )

    annual = [
        obs
        for obs in observations
        if is_annual_observation(obs)
    ]

    if not annual:
        return None

    annual = sort_observations(
        annual
    )

    return annual[0]


def select_latest_instant_observation(
    concept_data: dict,
):
    """
    Select latest valid instant observation.

    The latest economic period end is prioritized
    over filing date.
    """

    observations = get_observations(
        concept_data
    )

    instant = [
        obs
        for obs in observations
        if is_instant_observation(obs)
    ]

    if not instant:
        return None

    instant = sort_instant_observations(
        instant
    )

    return instant[0]


# ============================================================
# CONCEPT LOOKUP
# ============================================================

def find_concept(
    data: dict,
    namespace: str,
    concept_name: str,
):
    """
    Find an exact SEC concept.
    """

    facts = data.get(
        "facts",
        {},
    )

    namespace_data = facts.get(
        namespace
    )

    if not isinstance(namespace_data, dict):
        return None

    return namespace_data.get(
        concept_name
    )


# ============================================================
# PRIORITY-BASED ANNUAL CONCEPT SELECTION
# ============================================================

def find_best_annual_concept(
    data: dict,
    concept_candidates: list,
    namespaces=("us-gaap",),
):
    """
    Select the best annual observation across all
    candidate concepts and namespaces.

    Selection priority:
        1. Latest filing date
        2. Latest period end
        3. Candidate concept priority
        4. Accession number

    This avoids blindly selecting the first concept
    that happens to contain a valid observation.
    """

    candidates = []

    for concept_priority, concept_name in enumerate(
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

            observation = (
                select_latest_annual_observation(
                    concept_data
                )
            )

            if observation is None:
                continue

            candidates.append(
                {
                    "namespace": namespace,
                    "concept": concept_name,
                    "observation": observation,
                    "concept_priority": concept_priority,
                }
            )

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: (
            _date_string(
                item["observation"].get("filed")
            )
            or "",
            _date_string(
                item["observation"].get("end")
            )
            or "",
            -item["concept_priority"],
            item["observation"].get("accn")
            or "",
        ),
        reverse=True,
    )

    return candidates[0]


# ============================================================
# PRIORITY-BASED INSTANT CONCEPT SELECTION
# ============================================================

def find_best_instant_concept(
    data: dict,
    concept_candidates: list,
    namespaces=("us-gaap", "dei"),
):
    """
    Select the best instant observation across all
    candidate concepts and namespaces.

    Selection priority:
        1. Latest economic period end
        2. Latest filing date
        3. Candidate concept priority
        4. Accession number

    IMPORTANT:
        All candidate concepts are evaluated before selection.

        This prevents an old observation from a high-priority
        concept from blocking a newer observation available
        in another candidate concept.
    """

    candidates = []

    for concept_priority, concept_name in enumerate(
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

            observation = (
                select_latest_instant_observation(
                    concept_data
                )
            )

            if observation is None:
                continue

            candidates.append(
                {
                    "namespace": namespace,
                    "concept": concept_name,
                    "observation": observation,
                    "concept_priority": concept_priority,
                }
            )

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: (
            _date_string(
                item["observation"].get("end")
            )
            or "",
            _date_string(
                item["observation"].get("filed")
            )
            or "",
            -item["concept_priority"],
            item["observation"].get("accn")
            or "",
        ),
        reverse=True,
    )

    return candidates[0]


# ============================================================
# RESULT BUILDERS
# ============================================================

def build_missing_metric(
    metric_name: str,
    reason: str = None,
):
    """
    Missing data is explicitly represented.

    Missing is NOT converted to zero.
    """

    result = {
        "metric": metric_name,
        "status": "MISSING",
        "value": None,
    }

    if reason:
        result["reason"] = reason

    return result


def build_not_applicable_metric(
    metric_name: str,
    reason: str,
):
    """
    Metric is structurally inappropriate for
    the company's business model.
    """

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
    """
    Build duration-based normalized metric.
    """

    return {
        "metric": metric_name,
        "status": "OK",

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


def build_instant_result(
    metric_name: str,
    namespace: str,
    concept: str,
    observation: dict,
):
    """
    Build instant / balance-sheet normalized metric.
    """

    return {
        "metric": metric_name,
        "status": "OK",

        "namespace": namespace,
        "concept": concept,

        "unit": observation.get(
            "unit"
        ),
        "value": observation.get(
            "val"
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


# ============================================================
# METRIC EXTRACTION
# ============================================================

def extract_metric(
    data: dict,
    metric_name: str,
    concept_candidates: list,
    namespaces=("us-gaap",),
):
    """
    Extract annual duration metric.
    """

    result = find_best_annual_concept(
        data,
        concept_candidates,
        namespaces,
    )

    if result is None:

        return build_missing_metric(
            metric_name
        )

    observation = result[
        "observation"
    ]

    return build_metric_result(
        metric_name,
        result["namespace"],
        result["concept"],
        observation,
    )


def extract_instant_metric(
    data: dict,
    metric_name: str,
    concept_candidates: list,
    namespaces=("us-gaap", "dei"),
):
    """
    Extract latest instant metric.
    """

    result = find_best_instant_concept(
        data,
        concept_candidates,
        namespaces,
    )

    if result is None:

        return build_missing_metric(
            metric_name
        )

    observation = result[
        "observation"
    ]

    return build_instant_result(
        metric_name,
        result["namespace"],
        result["concept"],
        observation,
    )


# ============================================================
# TOTAL DEBT
# ============================================================

def calculate_total_debt(
    current_debt: dict,
    noncurrent_debt: dict,
    company_type: str,
):
    """
    Calculate total debt only when both components
    are independently valid.

    Missing debt is NOT interpreted as zero.
    """

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

    current_value = current_debt.get(
        "value"
    )

    noncurrent_value = noncurrent_debt.get(
        "value"
    )

    if (
        current_debt.get("status") == "OK"
        and
        noncurrent_debt.get("status") == "OK"
        and
        _is_number(current_value)
        and
        _is_number(noncurrent_value)
    ):

        result["value"] = (
            current_value
            +
            noncurrent_value
        )

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
    """
    Convert raw SEC Company Facts into
    the v0.1 normalized fundamental schema.
    """

    validate_companyfacts(
        data
    )

    # ========================================================
    # REVENUE
    # ========================================================

    revenue = extract_metric(
        data,
        "revenue",
        [
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "SalesRevenueNet",
            "Revenues",
        ],
    )

    # ========================================================
    # NET INCOME
    # ========================================================

    net_income = extract_metric(
        data,
        "net_income",
        [
            "NetIncomeLoss",
            "ProfitLoss",
        ],
    )

    # ========================================================
    # DILUTED EPS
    # ========================================================

    diluted_eps = extract_metric(
        data,
        "diluted_eps",
        [
            "EarningsPerShareDiluted",
        ],
    )

    # ========================================================
    # OPERATING INCOME
    # ========================================================

    if company_type == "FINANCIAL":

        operating_income = (
            build_not_applicable_metric(
                "operating_income",
                (
                    "Generic operating income framework "
                    "is not used for financial companies."
                ),
            )
        )

    else:

        operating_income = extract_metric(
            data,
            "operating_income",
            [
                "OperatingIncomeLoss",
            ],
        )

    # ========================================================
    # CFO
    # ========================================================

    if company_type == "FINANCIAL":

        cfo = build_not_applicable_metric(
            "cfo",
            (
                "Generic CFO/FCF framework "
                "is not used for financial companies."
            ),
        )

    else:

        cfo = extract_metric(
            data,
            "cfo",
            [
                "NetCashProvidedByUsedInOperatingActivities",
            ],
        )

    # ========================================================
    # CAPEX
    # ========================================================

    if company_type == "FINANCIAL":

        capex = build_not_applicable_metric(
            "capex",
            (
                "Generic CapEx/FCF framework "
                "is not used for financial companies."
            ),
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

    # ========================================================
    # CASH
    # ========================================================

    cash = extract_instant_metric(
        data,
        "cash",
        [
            "CashAndCashEquivalentsAtCarryingValue",
        ],
    )

    # ========================================================
    # CURRENT DEBT
    # ========================================================

    if company_type == "FINANCIAL":

        current_debt = (
            build_not_applicable_metric(
                "current_debt",
                (
                    "Generic industrial debt framework "
                    "is not used for financial companies."
                ),
            )
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

    # ========================================================
    # NONCURRENT DEBT
    # ========================================================

    if company_type == "FINANCIAL":

        noncurrent_debt = (
            build_not_applicable_metric(
                "noncurrent_debt",
                (
                    "Generic industrial debt framework "
                    "is not used for financial companies."
                ),
            )
        )

    else:

        noncurrent_debt = extract_instant_metric(
            data,
            "noncurrent_debt",
            [
                "LongTermDebtNoncurrent",
            ],
        )

    # ========================================================
    # SHARES OUTSTANDING
    # ========================================================

    shares = extract_instant_metric(
        data,
        "shares_outstanding",
        [
            "EntityCommonStockSharesOutstanding",
            "CommonStockSharesOutstanding",
        ],
        namespaces=(
            "dei",
            "us-gaap",
        ),
    )

    # ========================================================
    # STOCKHOLDERS' EQUITY
    # ========================================================

    stockholders_equity = (
        extract_instant_metric(
            data,
            "stockholders_equity",
            [
                "StockholdersEquity",
            ],
            namespaces=(
                "us-gaap",
            ),
        )
    )

    # ========================================================
    # TOTAL DEBT
    # ========================================================

    total_debt = calculate_total_debt(
        current_debt,
        noncurrent_debt,
        company_type,
    )

    # ========================================================
    # NORMALIZED RESULT
    # ========================================================

    return {

        "schema_version":
            SCHEMA_VERSION,

        "ticker":
            ticker,

        "entity_name":
            data.get("entityName"),

        "cik":
            data.get("cik"),

        "company_type":
            company_type,

        "source": {
            "provider": "SEC",
            "dataset": "Company Facts",
        },

        "normalized_at":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "metrics": {

            "revenue":
                revenue,

            "net_income":
                net_income,

            "diluted_eps":
                diluted_eps,

            "operating_income":
                operating_income,

            "cfo":
                cfo,

            "capex":
                capex,

            "cash":
                cash,

            "current_debt":
                current_debt,

            "noncurrent_debt":
                noncurrent_debt,

            "total_debt":
                total_debt,

            "shares_outstanding":
                shares,

            "stockholders_equity":
                stockholders_equity,
        },
    }


# ============================================================
# NORMALIZED DATA VALIDATION
# ============================================================

def validate_normalized_data(
    normalized: dict,
) -> list:
    """
    Validate normalized fundamental dataset.

    Returns:
        list[str] of failed metric names.

    IMPORTANT:
        stockholders_equity is intentionally NOT required
        for v0.1 core validation.

    Reason:
        Some issuers may not expose a directly usable equity
        concept even though the metric is useful for valuation.

        Valuation should treat unavailable equity as MISSING,
        not as zero.
    """

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

            raise ValueError(
                f"Missing normalized key: {key}"
            )

    company_type = normalized[
        "company_type"
    ]

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

        raise ValueError(
            f"Unknown company_type: {company_type}"
        )

    failures = []

    for metric in required_metrics:

        metric_data = normalized[
            "metrics"
        ].get(
            metric
        )

        if not isinstance(
            metric_data,
            dict,
        ):

            failures.append(
                metric
            )

            continue

        if metric_data.get(
            "status"
        ) != "OK":

            failures.append(
                metric
            )

    # ========================================================
    # TOTAL DEBT
    # ========================================================

    total_debt = normalized[
        "metrics"
    ].get(
        "total_debt"
    )

    if not isinstance(
        total_debt,
        dict,
    ):

        failures.append(
            "total_debt"
        )

    elif company_type == "NON_FINANCIAL":

        if total_debt.get(
            "status"
        ) != "OK":

            failures.append(
                "total_debt"
            )

    elif company_type == "FINANCIAL":

        if total_debt.get(
            "status"
        ) != "NOT_APPLICABLE":

            failures.append(
                "total_debt"
            )

    return failures


# ============================================================
# FILE HELPERS
# ============================================================

def load_raw_companyfacts(
    ticker: str,
    raw_dir: Path = RAW_DIR,
) -> dict:
    """
    Load previously cached SEC Company Facts.
    """

    path = (
        raw_dir
        /
        f"{ticker}_companyfacts.json"
    )

    if not path.exists():

        raise FileNotFoundError(
            f"Raw SEC file not found: {path}"
        )

    with path.open(
        "r",
        encoding="utf-8",
    ) as f:

        data = json.load(
            f
        )

    return data


def save_normalized_data(
    ticker: str,
    normalized: dict,
    processed_dir: Path = PROCESSED_DIR,
) -> Path:
    """
    Save normalized fundamental JSON.
    """

    processed_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    path = (
        processed_dir
        /
        f"{ticker}_fundamentals.json"
    )

    with path.open(
        "w",
        encoding="utf-8",
    ) as f:

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
    """
    Main reusable normalization entry point.

    Important:
        This function does NOT access the SEC API.

        It only operates on raw cached Company Facts.
    """

    data = load_raw_companyfacts(
        ticker,
        raw_dir,
    )

    normalized = normalize_company(
        ticker,
        data,
        company_type,
    )

    failures = validate_normalized_data(
        normalized
    )

    output_path = save_normalized_data(
        ticker,
        normalized,
        processed_dir,
    )

    return {
        "ticker":
            ticker,

        "output_path":
            str(output_path),

        "failures":
            failures,

        "normalized":
            normalized,
    }


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":

    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Normalize SEC Company Facts "
            "into the Stock Master "
            "fundamental schema."
        )
    )

    parser.add_argument(
        "--ticker",
        required=True,
        help="Ticker symbol, e.g. NVDA",
    )

    parser.add_argument(
        "--company-type",
        default="NON_FINANCIAL",
        choices=[
            "NON_FINANCIAL",
            "FINANCIAL",
        ],
    )

    args = parser.parse_args()

    result = normalize_from_cache(
        ticker=args.ticker,
        company_type=args.company_type,
    )

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        )
    )