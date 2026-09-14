from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any


# ============================================================
# CONFIGURATION
# ============================================================

SCHEMA_VERSION = "sec_historical_v0.1"

RAW_DIR = Path("data/raw/sec")
PROCESSED_DIR = Path("data/processed/fundamentals")


# ============================================================
# CONCEPT MAP
# ============================================================

CONCEPT_MAP = {
    "revenue": [
        ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax"),
        ("us-gaap", "Revenues"),
    ],
    "net_income": [
        ("us-gaap", "NetIncomeLoss"),
        ("us-gaap", "ProfitLoss"),
    ],
    "diluted_eps": [
        ("us-gaap", "EarningsPerShareDiluted"),
    ],
    "operating_income": [
        ("us-gaap", "OperatingIncomeLoss"),
    ],
    "cfo": [
        ("us-gaap", "NetCashProvidedByUsedInOperatingActivities"),
    ],
    "capex": [
        ("us-gaap", "PaymentsToAcquirePropertyPlantAndEquipment"),
        ("us-gaap", "PaymentsToAcquireOtherPropertyPlantAndEquipment"),
    ],
    "cash": [
        ("us-gaap", "CashAndCashEquivalentsAtCarryingValue"),
    ],
    "current_debt": [
        ("us-gaap", "DebtCurrent"),
        ("us-gaap", "LongTermDebtCurrent"),
        ("us-gaap", "ShortTermBorrowings"),
        ("us-gaap", "ShortTermDebt"),
        ("us-gaap", "CurrentDebt"),
    ],
    "noncurrent_debt": [
        ("us-gaap", "LongTermDebtNoncurrent"),
    ],
    "shares_outstanding": [
        ("dei", "EntityCommonStockSharesOutstanding"),
        ("us-gaap", "CommonStockSharesOutstanding"),
    ],
}


# ============================================================
# BASIC HELPERS
# ============================================================

def _is_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and value == value
    )


def _safe_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _date_string(value: Any) -> str | None:
    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    return value


def _date_key(value: Any) -> str:
    if value is None:
        return ""

    return str(value)


def _parse_date(value: Any) -> datetime | None:
    if value is None:
        return None

    try:
        return datetime.strptime(str(value), "%Y-%m-%d")
    except (TypeError, ValueError):
        return None


def _duration_days(observation: dict) -> int | None:
    start = _parse_date(observation.get("start"))
    end = _parse_date(observation.get("end"))

    if start is None or end is None:
        return None

    return (end - start).days + 1


def _is_duration(observation: dict) -> bool:
    return (
        observation.get("start") is not None
        and observation.get("end") is not None
    )


def _is_instant(observation: dict) -> bool:
    return (
        observation.get("end") is not None
        and observation.get("start") is None
    )


# ============================================================
# SEC RAW DATA HELPERS
# ============================================================

def validate_companyfacts(data: dict) -> None:
    if not isinstance(data, dict):
        raise ValueError("Company Facts root must be a dict.")

    required = ["cik", "entityName", "facts"]

    for key in required:
        if key not in data:
            raise ValueError(f"Missing required Company Facts key: {key}")

    if not isinstance(data["facts"], dict):
        raise ValueError("Company Facts 'facts' must be a dict.")


def get_concept_data(
    data: dict,
    namespace: str,
    concept_name: str,
) -> dict | None:
    validate_companyfacts(data)

    namespace_data = data["facts"].get(namespace)

    if not isinstance(namespace_data, dict):
        return None

    concepts = namespace_data.get("facts")

    if not isinstance(concepts, dict):
        return None

    concept_data = concepts.get(concept_name)

    if not isinstance(concept_data, dict):
        return None

    return concept_data


def get_observations(concept_data: dict) -> list[dict]:
    """
    Flatten SEC Company Facts units into a single observation list.
    """

    units = concept_data.get("units", {})

    if not isinstance(units, dict):
        return []

    observations = []

    for unit, records in units.items():
        if not isinstance(records, list):
            continue

        for record in records:
            if not isinstance(record, dict):
                continue

            observation = dict(record)
            observation["unit"] = unit
            observations.append(observation)

    return observations


# ============================================================
# OBSERVATION FILTERING
# ============================================================

def _is_fy_observation(obs: dict) -> bool:
    return (
        obs.get("form") == "10-K"
        and obs.get("fp") == "FY"
        and _is_duration(obs)
    )


def _is_quarter_form(obs: dict) -> bool:
    return obs.get("form") in {"10-Q", "10-K"}


def _has_valid_period(obs: dict) -> bool:
    return (
        obs.get("start") is not None
        and obs.get("end") is not None
    )


def _observation_sort_key(obs: dict) -> tuple:
    return (
        _date_key(obs.get("filed")),
        _date_key(obs.get("end")),
        _date_key(obs.get("start")),
        _date_key(obs.get("accn")),
    )


def sort_observations(observations: list[dict]) -> list[dict]:
    return sorted(
        observations,
        key=_observation_sort_key,
        reverse=True,
    )


# ============================================================
# DUPLICATE CONTROL
# ============================================================

def _period_identity(obs: dict) -> tuple:
    return (
        obs.get("start"),
        obs.get("end"),
        obs.get("fy"),
        obs.get("fp"),
    )


def deduplicate_observations(
    observations: list[dict],
) -> list[dict]:
    """
    Keep the latest filed observation for the same SEC period identity.

    This is important because the same fiscal period may appear
    in multiple filings.
    """

    selected: dict[tuple, dict] = {}

    for obs in observations:
        identity = _period_identity(obs)

        current = selected.get(identity)

        if current is None:
            selected[identity] = obs
            continue

        if _observation_sort_key(obs) > _observation_sort_key(current):
            selected[identity] = obs

    return sort_observations(list(selected.values()))


# ============================================================
# CONCEPT SELECTION
# ============================================================

def find_best_concept(
    data: dict,
    metric_name: str,
    *,
    instant: bool = False,
) -> tuple[str, str, dict] | None:
    """
    Select the first concept in economic-priority order that has
    usable observations.

    Returns:
        (namespace, concept_name, concept_data)
    """

    candidates = CONCEPT_MAP.get(metric_name, [])

    for namespace, concept_name in candidates:
        concept_data = get_concept_data(
            data,
            namespace,
            concept_name,
        )

        if not concept_data:
            continue

        observations = get_observations(concept_data)

        if instant:
            usable = [
                obs
                for obs in observations
                if _is_instant(obs)
            ]
        else:
            usable = [
                obs
                for obs in observations
                if _is_duration(obs)
            ]

        if usable:
            return namespace, concept_name, concept_data

    return None


# ============================================================
# RECORD BUILDER
# ============================================================

def build_record(
    observation: dict,
    *,
    namespace: str,
    concept: str,
    period_type: str,
    quarter: str | None = None,
) -> dict:
    """
    Convert a raw SEC observation into a normalized historical record.
    """

    record = {
        "period_type": period_type,
        "period_start": observation.get("start"),
        "period_end": observation.get("end"),
        "value": observation.get("val"),
        "unit": observation.get("unit"),
        "namespace": namespace,
        "concept": concept,
        "filing_date": observation.get("filed"),
        "form": observation.get("form"),
        "fy": observation.get("fy"),
        "fp": observation.get("fp"),
        "frame": observation.get("frame"),
        "accession": observation.get("accn"),
    }

    if quarter is not None:
        record["quarter"] = quarter

    return record


# ============================================================
# ANNUAL EXTRACTION
# ============================================================

def extract_annual_history(
    data: dict,
    metric_name: str,
) -> dict:
    """
    Extract annual SEC observations.

    Annual policy:
        form == 10-K
        fp == FY
        duration observation
    """

    selected = find_best_concept(
        data,
        metric_name,
        instant=False,
    )

    if selected is None:
        return {
            "status": "MISSING",
            "metric": metric_name,
            "records": [],
            "reason": "No usable SEC concept found.",
        }

    namespace, concept, concept_data = selected

    observations = get_observations(concept_data)

    annual = [
        obs
        for obs in observations
        if _is_fy_observation(obs)
        and _has_valid_period(obs)
        and _is_number(obs.get("val"))
    ]

    annual = deduplicate_observations(annual)

    annual.sort(
        key=lambda x: (
            _safe_int(x.get("fy")) or 0,
            _date_key(x.get("end")),
            _date_key(x.get("filed")),
        )
    )

    records = [
        build_record(
            obs,
            namespace=namespace,
            concept=concept,
            period_type="annual",
        )
        for obs in annual
    ]

    return {
        "status": "OK" if records else "MISSING",
        "metric": metric_name,
        "namespace": namespace,
        "concept": concept,
        "records": records,
    }


# ============================================================
# INSTANT HISTORY
# ============================================================

def extract_instant_history(
    data: dict,
    metric_name: str,
) -> dict:
    """
    Extract historical balance-sheet / instant observations.

    Unlike duration metrics, these are keyed primarily by period_end.
    """

    selected = find_best_concept(
        data,
        metric_name,
        instant=True,
    )

    if selected is None:
        return {
            "status": "MISSING",
            "metric": metric_name,
            "records": [],
            "reason": "No usable SEC instant concept found.",
        }

    namespace, concept, concept_data = selected

    observations = get_observations(concept_data)

    instant = [
        obs
        for obs in observations
        if _is_instant(obs)
        and obs.get("end") is not None
        and _is_number(obs.get("val"))
    ]

    # For instant metrics, same period-end may appear in multiple filings.
    # Keep latest filed observation.
    selected_by_end: dict[str, dict] = {}

    for obs in instant:
        end = obs.get("end")

        current = selected_by_end.get(end)

        if current is None:
            selected_by_end[end] = obs
            continue

        if _observation_sort_key(obs) > _observation_sort_key(current):
            selected_by_end[end] = obs

    instant = sorted(
        selected_by_end.values(),
        key=lambda x: (
            _date_key(x.get("end")),
            _date_key(x.get("filed")),
        )
    )

    records = [
        build_record(
            obs,
            namespace=namespace,
            concept=concept,
            period_type="instant",
        )
        for obs in instant
    ]

    return {
        "status": "OK" if records else "MISSING",
        "metric": metric_name,
        "namespace": namespace,
        "concept": concept,
        "records": records,
    }


# ============================================================
# QUARTER IDENTIFICATION
# ============================================================

def _quarter_duration_days(
    observation: dict,
) -> int | None:
    return _duration_days(observation)


def _looks_like_standalone_quarter(
    observation: dict,
) -> bool:
    """
    Identify a likely standalone quarter by duration.

    Approximate policy:
        70 <= days <= 120

    This accommodates normal 13-week quarters and most
    52/53-week fiscal calendars.

    The duration test is intentionally conservative.
    """

    days = _quarter_duration_days(observation)

    if days is None:
        return False

    return 70 <= days <= 120


def _looks_like_ytd(
    observation: dict,
) -> bool:
    """
    Identify a cumulative fiscal-year observation.

    Approximate ranges:
        Q2 YTD: ~140-210 days
        Q3 YTD: ~210-310 days

    A broad range is used because fiscal calendars differ.
    """

    days = _quarter_duration_days(observation)

    if days is None:
        return False

    return 120 < days < 320


def _fy_value(observation: dict) -> int | None:
    return _safe_int(observation.get("fy"))


def _fp(observation: dict) -> str:
    value = observation.get("fp")

    if value is None:
        return ""

    return str(value).upper()


# ============================================================
# PERIOD MATCHING
# ============================================================

def _select_latest_matching(
    observations: list[dict],
    predicate,
) -> dict | None:
    candidates = [
        obs
        for obs in observations
        if predicate(obs)
        and _is_number(obs.get("val"))
    ]

    if not candidates:
        return None

    candidates = sort_observations(candidates)

    return candidates[0]


def _select_q1_standalone(
    observations: list[dict],
    fy: int,
) -> dict | None:
    candidates = [
        obs
        for obs in observations
        if _fy_value(obs) == fy
        and _fp(obs) == "Q1"
        and _is_duration(obs)
        and _looks_like_standalone_quarter(obs)
    ]

    if not candidates:
        return None

    return sort_observations(candidates)[0]


def _select_q2_standalone(
    observations: list[dict],
    fy: int,
) -> dict | None:
    candidates = [
        obs
        for obs in observations
        if _fy_value(obs) == fy
        and _fp(obs) == "Q2"
        and _is_duration(obs)
        and _looks_like_standalone_quarter(obs)
    ]

    if not candidates:
        return None

    return sort_observations(candidates)[0]


def _select_q3_standalone(
    observations: list[dict],
    fy: int,
) -> dict | None:
    candidates = [
        obs
        for obs in observations
        if _fy_value(obs) == fy
        and _fp(obs) == "Q3"
        and _is_duration(obs)
        and _looks_like_standalone_quarter(obs)
    ]

    if not candidates:
        return None

    return sort_observations(candidates)[0]


# ============================================================
# CUMULATIVE PERIOD SELECTION
# ============================================================

def _select_q1_cumulative(
    observations: list[dict],
    fy: int,
) -> dict | None:
    """
    Q1 cumulative is normally also the standalone Q1 value.
    """

    return _select_q1_standalone(observations, fy)


def _select_q2_ytd(
    observations: list[dict],
    fy: int,
) -> dict | None:
    candidates = [
        obs
        for obs in observations
        if _fy_value(obs) == fy
        and _fp(obs) == "Q2"
        and _is_duration(obs)
        and _looks_like_ytd(obs)
    ]

    if not candidates:
        return None

    return sort_observations(candidates)[0]


def _select_q3_ytd(
    observations: list[dict],
    fy: int,
) -> dict | None:
    candidates = [
        obs
        for obs in observations
        if _fy_value(obs) == fy
        and _fp(obs) == "Q3"
        and _is_duration(obs)
        and _looks_like_ytd(obs)
    ]

    if not candidates:
        return None

    return sort_observations(candidates)[0]


def _select_fy(
    observations: list[dict],
    fy: int,
) -> dict | None:
    candidates = [
        obs
        for obs in observations
        if _fy_value(obs) == fy
        and _is_fy_observation(obs)
        and _is_number(obs.get("val"))
    ]

    if not candidates:
        return None

    return sort_observations(candidates)[0]


# ============================================================
# DERIVED QUARTER RECORD
# ============================================================

def _build_derived_quarter(
    *,
    metric_name: str,
    quarter: str,
    fy: int,
    value: float,
    current_observation: dict,
    source_observations: list[dict],
    namespace: str,
    concept: str,
) -> dict:
    """
    Build a standalone-quarter record reconstructed from SEC
    cumulative observations.

    Provenance retains all source observations.
    """

    source_records = []

    for obs in source_observations:
        source_records.append(
            {
                "period_start": obs.get("start"),
                "period_end": obs.get("end"),
                "value": obs.get("val"),
                "form": obs.get("form"),
                "fy": obs.get("fy"),
                "fp": obs.get("fp"),
                "frame": obs.get("frame"),
                "filing_date": obs.get("filed"),
                "accession": obs.get("accn"),
            }
        )

    return {
        "period_type": "quarterly",
        "quarter": quarter,
        "fy": fy,
        "period_start": current_observation.get("start"),
        "period_end": current_observation.get("end"),
        "value": value,
        "unit": current_observation.get("unit"),
        "namespace": namespace,
        "concept": concept,
        "filing_date": current_observation.get("filed"),
        "form": current_observation.get("form"),
        "fp": current_observation.get("fp"),
        "frame": current_observation.get("frame"),
        "accession": current_observation.get("accn"),
        "derived": True,
        "derivation": "cumulative_subtraction",
        "source_observations": source_records,
    }


def _subtract_observations(
    current: dict,
    previous: dict,
) -> float | None:
    current_value = current.get("val")
    previous_value = previous.get("val")

    if not _is_number(current_value):
        return None

    if not _is_number(previous_value):
        return None

    return float(current_value) - float(previous_value)


# ============================================================
# QUARTERLY EXTRACTION
# ============================================================

def extract_quarterly_history(
    data: dict,
    metric_name: str,
) -> dict:
    """
    Extract standalone quarterly history.

    Priority:
        Q1:
            standalone Q1

        Q2:
            standalone Q2
            otherwise H1 - Q1

        Q3:
            standalone Q3
            otherwise 9M - H1

        Q4:
            FY - 9M

    This deliberately avoids treating H1 / 9M as standalone quarters.
    """

    selected = find_best_concept(
        data,
        metric_name,
        instant=False,
    )

    if selected is None:
        return {
            "status": "MISSING",
            "metric": metric_name,
            "records": [],
            "reason": "No usable SEC duration concept found.",
        }

    namespace, concept, concept_data = selected

    observations = get_observations(concept_data)

    observations = [
        obs
        for obs in observations
        if _is_duration(obs)
        and _is_quarter_form(obs)
        and _is_number(obs.get("val"))
    ]

    if not observations:
        return {
            "status": "MISSING",
            "metric": metric_name,
            "records": [],
            "namespace": namespace,
            "concept": concept,
            "reason": "No usable duration observations found.",
        }

    # Deduplicate exact SEC period identities.
    observations = deduplicate_observations(observations)

    fiscal_years = sorted(
        {
            _fy_value(obs)
            for obs in observations
            if _fy_value(obs) is not None
        }
    )

    quarterly_records: list[dict] = []

    for fy in fiscal_years:
        # ----------------------------------------------------
        # Q1
        # ----------------------------------------------------

        q1 = _select_q1_standalone(
            observations,
            fy,
        )

        if q1 is not None:
            quarterly_records.append(
                build_record(
                    q1,
                    namespace=namespace,
                    concept=concept,
                    period_type="quarterly",
                    quarter="Q1",
                )
                | {"fy": fy}
            )

        # ----------------------------------------------------
        # Q2
        # ----------------------------------------------------

        q2_standalone = _select_q2_standalone(
            observations,
            fy,
        )

        if q2_standalone is not None:
            quarterly_records.append(
                build_record(
                    q2_standalone,
                    namespace=namespace,
                    concept=concept,
                    period_type="quarterly",
                    quarter="Q2",
                )
                | {"fy": fy}
            )

        else:
            q1_cumulative = _select_q1_cumulative(
                observations,
                fy,
            )

            q2_ytd = _select_q2_ytd(
                observations,
                fy,
            )

            if q1_cumulative is not None and q2_ytd is not None:
                value = _subtract_observations(
                    q2_ytd,
                    q1_cumulative,
                )

                if value is not None:
                    quarterly_records.append(
                        _build_derived_quarter(
                            metric_name=metric_name,
                            quarter="Q2",
                            fy=fy,
                            value=value,
                            current_observation=q2_ytd,
                            source_observations=[
                                q2_ytd,
                                q1_cumulative,
                            ],
                            namespace=namespace,
                            concept=concept,
                        )
                    )

        # ----------------------------------------------------
        # Q3
        # ----------------------------------------------------

        q3_standalone = _select_q3_standalone(
            observations,
            fy,
        )

        if q3_standalone is not None:
            quarterly_records.append(
                build_record(
                    q3_standalone,
                    namespace=namespace,
                    concept=concept,
                    period_type="quarterly",
                    quarter="Q3",
                )
                | {"fy": fy}
            )

        else:
            q2_ytd = _select_q2_ytd(
                observations,
                fy,
            )

            q3_ytd = _select_q3_ytd(
                observations,
                fy,
            )

            if q2_ytd is not None and q3_ytd is not None:
                value = _subtract_observations(
                    q3_ytd,
                    q2_ytd,
                )

                if value is not None:
                    quarterly_records.append(
                        _build_derived_quarter(
                            metric_name=metric_name,
                            quarter="Q3",
                            fy=fy,
                            value=value,
                            current_observation=q3_ytd,
                            source_observations=[
                                q3_ytd,
                                q2_ytd,
                            ],
                            namespace=namespace,
                            concept=concept,
                        )
                    )

        # ----------------------------------------------------
        # Q4
        # ----------------------------------------------------

        fy_observation = _select_fy(
            observations,
            fy,
        )

        q3_ytd = _select_q3_ytd(
            observations,
            fy,
        )

        if fy_observation is not None and q3_ytd is not None:
            value = _subtract_observations(
                fy_observation,
                q3_ytd,
            )

            if value is not None:
                quarterly_records.append(
                    _build_derived_quarter(
                        metric_name=metric_name,
                        quarter="Q4",
                        fy=fy,
                        value=value,
                        current_observation=fy_observation,
                        source_observations=[
                            fy_observation,
                            q3_ytd,
                        ],
                        namespace=namespace,
                        concept=concept,
                    )
                )

    # --------------------------------------------------------
    # Final duplicate control
    # --------------------------------------------------------

    deduped: dict[tuple, dict] = {}

    for record in quarterly_records:
        identity = (
            record.get("fy"),
            record.get("quarter"),
        )

        current = deduped.get(identity)

        if current is None:
            deduped[identity] = record
            continue

        # Prefer directly reported standalone quarters over
        # reconstructed quarters.
        current_derived = bool(current.get("derived", False))
        new_derived = bool(record.get("derived", False))

        if current_derived and not new_derived:
            deduped[identity] = record

    quarterly_records = sorted(
        deduped.values(),
        key=lambda x: (
            _safe_int(x.get("fy")) or 0,
            x.get("quarter", ""),
        )
    )

    return {
        "status": "OK" if quarterly_records else "MISSING",
        "metric": metric_name,
        "namespace": namespace,
        "concept": concept,
        "records": quarterly_records,
    }


# ============================================================
# COMPLETE HISTORICAL EXTRACTION
# ============================================================

DURATION_METRICS = [
    "revenue",
    "net_income",
    "diluted_eps",
    "operating_income",
    "cfo",
    "capex",
]

INSTANT_METRICS = [
    "cash",
    "current_debt",
    "noncurrent_debt",
    "shares_outstanding",
]


def extract_historical_data(
    ticker: str,
    data: dict,
    *,
    company_type: str = "NON_FINANCIAL",
) -> dict:
    """
    Extract historical SEC data for one company.

    The function preserves:
    - SEC provenance
    - annual history
    - standalone quarterly history
    - instant history

    It does not calculate investment factors.
    """

    validate_companyfacts(data)

    history: dict[str, dict] = {}

    # --------------------------------------------------------
    # Duration metrics
    # --------------------------------------------------------

    for metric_name in DURATION_METRICS:
        history[metric_name] = {
            "annual": extract_annual_history(
                data,
                metric_name,
            ),
            "quarterly": extract_quarterly_history(
                data,
                metric_name,
            ),
        }

    # --------------------------------------------------------
    # Instant metrics
    # --------------------------------------------------------

    for metric_name in INSTANT_METRICS:
        history[metric_name] = {
            "instant": extract_instant_history(
                data,
                metric_name,
            ),
        }

    return {
        "schema_version": SCHEMA_VERSION,
        "ticker": ticker,
        "entity_name": data.get("entityName"),
        "cik": data.get("cik"),
        "company_type": company_type,
        "source": {
            "provider": "SEC",
            "dataset": "Company Facts",
        },
        "extracted_at": datetime.utcnow().isoformat() + "Z",
        "history": history,
    }


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
            f"SEC Company Facts file not found: {path}"
        )

    import json

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


def save_historical_data(
    ticker: str,
    historical: dict,
    processed_dir: Path = PROCESSED_DIR,
) -> Path:
    import json

    processed_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    path = processed_dir / f"{ticker}_historical.json"

    with path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            historical,
            file,
            ensure_ascii=False,
            indent=2,
        )

    return path


def extract_from_cache(
    ticker: str,
    *,
    company_type: str = "NON_FINANCIAL",
    raw_dir: Path = RAW_DIR,
    processed_dir: Path = PROCESSED_DIR,
) -> dict:
    """
    End-to-end local cached extraction.

    Raw SEC data:
        data/raw/sec/{TICKER}_companyfacts.json

    Historical output:
        data/processed/fundamentals/{TICKER}_historical.json
    """

    data = load_raw_companyfacts(
        ticker,
        raw_dir=raw_dir,
    )

    historical = extract_historical_data(
        ticker,
        data,
        company_type=company_type,
    )

    output_path = save_historical_data(
        ticker,
        historical,
        processed_dir=processed_dir,
    )

    return {
        "ticker": ticker,
        "output_path": str(output_path),
        "historical": historical,
    }


# ============================================================
# VALIDATION
# ============================================================

def validate_historical_data(
    data: dict,
) -> list[str]:
    """
    Basic structural validation for sec_historical_v0.1.
    """

    failures: list[str] = []

    if not isinstance(data, dict):
        return ["root"]

    required_top_level = [
        "schema_version",
        "ticker",
        "entity_name",
        "cik",
        "company_type",
        "source",
        "extracted_at",
        "history",
    ]

    for key in required_top_level:
        if key not in data:
            failures.append(key)

    history = data.get("history")

    if not isinstance(history, dict):
        failures.append("history")
        return failures

    for metric_name, metric_data in history.items():
        if not isinstance(metric_data, dict):
            failures.append(f"history.{metric_name}")
            continue

        for period_type, result in metric_data.items():
            if not isinstance(result, dict):
                failures.append(
                    f"history.{metric_name}.{period_type}"
                )
                continue

            if "status" not in result:
                failures.append(
                    f"history.{metric_name}.{period_type}.status"
                )

            if "records" not in result:
                failures.append(
                    f"history.{metric_name}.{period_type}.records"
                )

            records = result.get("records")

            if not isinstance(records, list):
                failures.append(
                    f"history.{metric_name}.{period_type}.records"
                )
                continue

            for index, record in enumerate(records):
                if not isinstance(record, dict):
                    failures.append(
                        f"history.{metric_name}.{period_type}"
                        f".records[{index}]"
                    )
                    continue

                if "period_end" not in record:
                    failures.append(
                        f"history.{metric_name}.{period_type}"
                        f".records[{index}].period_end"
                    )

                if "value" not in record:
                    failures.append(
                        f"history.{metric_name}.{period_type}"
                        f".records[{index}].value"
                    )

                if not _is_number(record.get("value")):
                    failures.append(
                        f"history.{metric_name}.{period_type}"
                        f".records[{index}].value"
                    )

    return failures