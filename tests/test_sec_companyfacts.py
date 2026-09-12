import json
import gzip
import zlib
from pathlib import Path
from urllib.request import Request, urlopen
from datetime import datetime, timezone


# ============================================================
# CONFIGURATION
# ============================================================

USER_AGENT = "invest-briefing-chatgpt/0.1 chks7788@gmail.com"

TICKERS = {
    "MSFT": {
        "cik": "0000789019",
        "company_type": "NON_FINANCIAL",
    },
    "NVDA": {
        "cik": "0001045810",
        "company_type": "NON_FINANCIAL",
    },
    "JPM": {
        "cik": "0000019617",
        "company_type": "FINANCIAL",
    },
    "LLY": {
        "cik": "0000059478",
        "company_type": "NON_FINANCIAL",
    },
    "PLTR": {
        "cik": "0001321655",
        "company_type": "NON_FINANCIAL",
    },
}


RAW_DIR = Path("data/raw/sec")
PROCESSED_DIR = Path("data/processed/fundamentals")


# ============================================================
# SEC FETCH
# ============================================================

def fetch_json(url: str) -> dict:

    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate",
        },
        method="GET",
    )

    with urlopen(request, timeout=30) as response:

        status = response.status

        content_encoding = (
            response.headers.get(
                "Content-Encoding",
                ""
            ).lower()
        )

        raw_data = response.read()

        print(f"HTTP status: {status}")

        print(
            f"Content-Encoding: "
            f"{content_encoding or 'none'}"
        )

        print(
            f"Response bytes: "
            f"{len(raw_data)}"
        )

        if status != 200:

            raise RuntimeError(
                f"HTTP status: {status}"
            )

        if content_encoding == "gzip":

            raw_data = gzip.decompress(
                raw_data
            )

        elif content_encoding == "deflate":

            raw_data = zlib.decompress(
                raw_data
            )

        text = raw_data.decode(
            "utf-8"
        )

        return json.loads(text)


# ============================================================
# BASIC VALIDATION
# ============================================================

def validate_companyfacts(data: dict) -> None:

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

    if not isinstance(
        data["facts"],
        dict
    ):

        raise ValueError(
            "facts is not a dictionary"
        )


# ============================================================
# SEC FACT HELPERS
# ============================================================

def get_all_concepts(data: dict):

    concepts = []

    for namespace, namespace_data in data["facts"].items():

        if not isinstance(
            namespace_data,
            dict
        ):
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
    concept_data: dict
):

    units = concept_data.get(
        "units",
        {}
    )

    observations = []

    for unit, values in units.items():

        if not isinstance(
            values,
            list
        ):
            continue

        for obs in values:

            row = dict(obs)

            row["unit"] = unit

            observations.append(
                row
            )

    return observations


# ============================================================
# OBSERVATION CLASSIFICATION
# ============================================================

def is_instant_observation(
    obs: dict
) -> bool:

    return (
        "end" in obs
        and "start" not in obs
    )


def is_duration_observation(
    obs: dict
) -> bool:

    return (
        "start" in obs
        and "end" in obs
    )


def is_annual_observation(
    obs: dict
) -> bool:

    if obs.get("form") != "10-K":
        return False

    if obs.get("fp") != "FY":
        return False

    return is_duration_observation(
        obs
    )


# ============================================================
# OBSERVATION SELECTION
# ============================================================

def sort_observations(
    observations
):

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


def select_latest_annual_observation(
    concept_data: dict
):

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
    concept_data: dict
):

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

    instant = sort_observations(
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

    for item in get_all_concepts(data):

        if item["namespace"] != namespace:
            continue

        if item["concept"] != concept_name:
            continue

        return item["data"]

    return None


# ============================================================
# PRIORITY-BASED ANNUAL CONCEPT SELECTION
# ============================================================

def find_best_annual_concept(
    data: dict,
    concept_candidates,
    namespaces=("us-gaap",),
):

    """
    Concept 후보를 경제적 의미의 우선순위대로 검사한다.

    중요한 원칙:
    '가장 최근 filing을 가진 Concept'를 무조건 선택하지 않는다.

    예:
        OperatingIncomeLoss
        vs
        NonoperatingIncomeExpense

    후자가 더 최근 filing을 가지고 있어도
    operating_income으로 선택하면 안 된다.

    따라서 concept_candidates의 순서를
    경제적 의미의 우선순위로 사용한다.
    """

    for concept_name in concept_candidates:

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

            return {
                "namespace": namespace,
                "concept": concept_name,
                "observation": observation,
            }

    return None


# ============================================================
# PRIORITY-BASED INSTANT CONCEPT SELECTION
# ============================================================

def find_best_instant_concept(
    data: dict,
    concept_candidates,
    namespaces=("us-gaap", "dei"),
):

    """
    Instant metric도 Concept 우선순위를 따른다.

    예:
        shares_outstanding

        1. dei:EntityCommonStockSharesOutstanding
        2. us-gaap:CommonStockSharesOutstanding

    WeightedAverageNumberOfDilutedSharesOutstanding는
    현재 시점 shares outstanding의 후보로 사용하지 않는다.
    """

    for concept_name in concept_candidates:

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

            return {
                "namespace": namespace,
                "concept": concept_name,
                "observation": observation,
            }

    return None


# ============================================================
# NORMALIZED RESULT BUILDERS
# ============================================================

def build_missing_metric(
    metric_name: str,
    reason: str = None,
):

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
# ANNUAL METRIC EXTRACTION
# ============================================================

def extract_metric(
    data: dict,
    metric_name: str,
    concept_candidates,
    namespaces=("us-gaap",),
):

    result = find_best_annual_concept(
        data,
        concept_candidates,
        namespaces,
    )

    if result is None:

        print(
            f"[WARN] {metric_name}: "
            f"no valid annual concept found"
        )

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


# ============================================================
# INSTANT METRIC EXTRACTION
# ============================================================

def extract_instant_metric(
    data: dict,
    metric_name: str,
    concept_candidates,
    namespaces=("us-gaap", "dei"),
):

    result = find_best_instant_concept(
        data,
        concept_candidates,
        namespaces,
    )

    if result is None:

        print(
            f"[WARN] {metric_name}: "
            f"no valid instant concept found"
        )

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
# COMPANY NORMALIZATION
# ============================================================

def normalize_company(
    ticker: str,
    data: dict,
    company_type: str,
):

    print()
    print("=" * 70)

    print(
        f"NORMALIZING {ticker}"
    )

    print(
        f"Company type: {company_type}"
    )

    print("=" * 70)


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
                "Generic operating income framework is not used for financial companies.",
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
            "Generic CFO/FCF framework is not used for financial companies.",
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


    # ========================================================
    # NONCURRENT DEBT
    # ========================================================

    if company_type == "FINANCIAL":

        noncurrent_debt = build_not_applicable_metric(
            "noncurrent_debt",
            "Generic industrial debt framework is not used for financial companies.",
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
    # TOTAL DEBT
    # ========================================================

    if company_type == "FINANCIAL":

        total_debt = {
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

    else:

        total_debt = {
            "metric": "total_debt",

            "status": "INCOMPLETE",

            "value": None,

            "components": {
                "current_debt": current_debt,
                "noncurrent_debt": noncurrent_debt,
            },
        }

        current_value = (
            current_debt.get("value")
        )

        noncurrent_value = (
            noncurrent_debt.get("value")
        )

        if (
            current_debt.get("status") == "OK"
            and
            noncurrent_debt.get("status") == "OK"
            and
            isinstance(
                current_value,
                (int, float)
            )
            and
            isinstance(
                noncurrent_value,
                (int, float)
            )
        ):

            total_debt["value"] = (
                current_value
                +
                noncurrent_value
            )

            total_debt["status"] = "OK"

        else:

            total_debt["status"] = (
                "INCOMPLETE"
            )


    # ========================================================
    # RESULT
    # ========================================================

    normalized = {

        "ticker": ticker,

        "entity_name": data.get(
            "entityName"
        ),

        "cik": data.get(
            "cik"
        ),

        "company_type": company_type,

        "retrieved_at": datetime.now(
            timezone.utc
        ).isoformat(),

        "metrics": {

            "revenue": revenue,

            "net_income": net_income,

            "diluted_eps": diluted_eps,

            "operating_income":
                operating_income,

            "cfo": cfo,

            "capex": capex,

            "cash": cash,

            "current_debt":
                current_debt,

            "noncurrent_debt":
                noncurrent_debt,

            "total_debt":
                total_debt,

            "shares_outstanding":
                shares,
        },
    }

    return normalized


# ============================================================
# VALIDATION
# ============================================================

def validate_normalized_data(
    normalized: dict,
):

    ticker = normalized[
        "ticker"
    ]

    company_type = normalized[
        "company_type"
    ]

    print()
    print(
        f"=== Validation: {ticker} ==="
    )

    print(
        f"Company type: {company_type}"
    )

    failures = []


    # ========================================================
    # CORE METRICS
    # ========================================================

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

    else:

        required_metrics = [

            "revenue",

            "net_income",

            "diluted_eps",

            "cash",

            "shares_outstanding",
        ]


    # ========================================================
    # VALIDATE CORE
    # ========================================================

    for metric in required_metrics:

        metric_data = (
            normalized["metrics"][metric]
        )

        status = metric_data.get(
            "status"
        )

        if status == "OK":

            print(
                f"[PASS] {metric}: "
                f"{metric_data.get('value')}"
            )

        else:

            print(
                f"[WARN] {metric}: "
                f"{status}"
            )

            failures.append(
                metric
            )


    # ========================================================
    # TOTAL DEBT
    # ========================================================

    total_debt = normalized[
        "metrics"
    ]["total_debt"]

    total_debt_status = (
        total_debt.get("status")
    )

    if (
        company_type == "FINANCIAL"
        and
        total_debt_status
        == "NOT_APPLICABLE"
    ):

        print(
            "[PASS] total_debt: "
            "NOT_APPLICABLE "
            "(financial company)"
        )

    elif (
        company_type == "NON_FINANCIAL"
        and
        total_debt_status
        == "OK"
    ):

        print(
            f"[PASS] total_debt: "
            f"{total_debt.get('value')}"
        )

    else:

        print(
            "[WARN] total_debt: "
            f"{total_debt_status}"
        )

        if company_type == "NON_FINANCIAL":

            failures.append(
                "total_debt"
            )


    # ========================================================
    # FAILURE SUMMARY
    # ========================================================

    if failures:

        print()
        print(
            f"[WARN] {ticker} "
            f"validation issues: "
            f"{', '.join(failures)}"
        )

    else:

        print()
        print(
            f"[PASS] {ticker} "
            f"validation complete."
        )

    return failures


# ============================================================
# SAVE JSON
# ============================================================

def save_json(
    path: Path,
    data: dict,
):

    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with path.open(
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )


# ============================================================
# MAIN
# ============================================================

def main():

    RAW_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    PROCESSED_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    success_count = 0

    total_count = len(
        TICKERS
    )


    print(
        "=== SEC Company Facts Test ==="
    )

    print()


    for ticker, config in TICKERS.items():

        cik = config["cik"]

        company_type = config[
            "company_type"
        ]


        print(
            f"Ticker: {ticker}"
        )

        print(
            f"CIK: {cik}"
        )

        print(
            f"Company type: "
            f"{company_type}"
        )


        url = (
            "https://data.sec.gov/api/xbrl/"
            f"companyfacts/CIK{cik}.json"
        )


        print(
            f"URL: {url}"
        )


        try:

            # =================================================
            # 1. FETCH
            # =================================================

            data = fetch_json(
                url
            )


            # =================================================
            # 2. RAW VALIDATION
            # =================================================

            validate_companyfacts(
                data
            )


            # =================================================
            # 3. SAVE RAW CACHE
            # =================================================

            raw_file = (
                RAW_DIR
                /
                f"{ticker}_companyfacts.json"
            )

            save_json(
                raw_file,
                data
            )

            print(
                f"[PASS] Raw cache written: "
                f"{raw_file}"
            )


            # =================================================
            # 4. NORMALIZE
            # =================================================

            normalized = normalize_company(
                ticker,
                data,
                company_type,
            )


            # =================================================
            # 5. VALIDATE NORMALIZED DATA
            # =================================================

            failures = (
                validate_normalized_data(
                    normalized
                )
            )


            # =================================================
            # 6. SAVE NORMALIZED DATA
            # =================================================

            processed_file = (
                PROCESSED_DIR
                /
                f"{ticker}_fundamentals.json"
            )

            save_json(
                processed_file,
                normalized
            )

            print(
                f"[PASS] Normalized data written: "
                f"{processed_file}"
            )


            # =================================================
            # 7. SUCCESS COUNT
            # =================================================

            if not failures:

                print(
                    f"[PASS] Fundamental validation: "
                    f"{ticker}"
                )

                success_count += 1

            else:

                print(
                    f"[WARN] {ticker} has validation "
                    f"issues: "
                    f"{', '.join(failures)}"
                )


        except Exception as e:

            print(
                f"[FAIL] {ticker}: "
                f"{type(e).__name__}: {e}"
            )


        print(
            "-" * 70
        )


    # ========================================================
    # FINAL RESULT
    # ========================================================

    print()

    print(
        f"Result: "
        f"{success_count}/{total_count} "
        f"tickers fully normalized"
    )


    if success_count != total_count:

        raise RuntimeError(
            "SEC fundamental normalization "
            "test failed"
        )


    print()

    print(
        "[PASS] All SEC fundamental normalization "
        "tests passed."
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()