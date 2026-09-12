import json
import gzip
import zlib
from pathlib import Path
from urllib.request import Request, urlopen
from datetime import datetime, timezone


USER_AGENT = "invest-briefing-chatgpt/0.1 chks7788@gmail.com"

TICKERS = {
    "MSFT": "0000789019",
    "NVDA": "0001045810",
    "JPM": "0000019617",
    "LLY": "0000059478",
    "PLTR": "0001321655",
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

            raw_data = gzip.decompress(raw_data)

        elif content_encoding == "deflate":

            raw_data = zlib.decompress(raw_data)

        text = raw_data.decode("utf-8")

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

    if not isinstance(data["facts"], dict):

        raise ValueError(
            "facts is not a dictionary"
        )


# ============================================================
# HELPERS
# ============================================================

def get_all_concepts(data: dict):

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


def get_observations(concept_data: dict):

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


def is_recent_observation(obs: dict) -> bool:

    return bool(
        obs.get("filed")
        or obs.get("end")
    )


def get_latest_observation(concept_data: dict):

    observations = get_observations(concept_data)

    valid = [
        obs
        for obs in observations
        if is_recent_observation(obs)
    ]

    if not valid:
        return None

    valid.sort(
        key=lambda x: (
            x.get("filed", ""),
            x.get("end", ""),
            x.get("start", ""),
        ),
        reverse=True,
    )

    return valid[0]


# ============================================================
# CONCEPT SEARCH / RANKING
# ============================================================

def concept_matches(concept_name: str, keywords):

    name = concept_name.lower()

    return all(
        keyword.lower() in name
        for keyword in keywords
    )


def find_candidate_concepts(
    data: dict,
    keywords,
    namespaces=("us-gaap",),
    limit=10,
):

    candidates = []

    for item in get_all_concepts(data):

        if item["namespace"] not in namespaces:
            continue

        concept_name = item["concept"]

        if not concept_matches(
            concept_name,
            keywords,
        ):
            continue

        latest = get_latest_observation(
            item["data"]
        )

        if latest is None:
            continue

        candidates.append(
            {
                "namespace": item["namespace"],
                "concept": concept_name,
                "latest": latest,
            }
        )

    candidates.sort(
        key=lambda x: (
            x["latest"].get("filed", ""),
            x["latest"].get("end", ""),
        ),
        reverse=True,
    )

    return candidates[:limit]


def print_candidates(
    data: dict,
    metric_name: str,
    keywords,
    namespaces=("us-gaap",),
):

    print()
    print(
        f"=== Concept candidates: {metric_name} ==="
    )

    candidates = find_candidate_concepts(
        data,
        keywords,
        namespaces,
    )

    if not candidates:

        print("[WARN] No candidates found")
        return candidates

    for candidate in candidates:

        latest = candidate["latest"]

        print(
            f"- {candidate['namespace']}:"
            f"{candidate['concept']}"
        )

        print(
            f"  latest end="
            f"{latest.get('end')}"
            f", filed="
            f"{latest.get('filed')}"
            f", form="
            f"{latest.get('form')}"
            f", fp="
            f"{latest.get('fp')}"
            f", value="
            f"{latest.get('val')}"
        )

    return candidates


# ============================================================
# EXTRACT LATEST FY OBSERVATION
# ============================================================

def select_latest_annual_observation(
    concept_data: dict,
):

    observations = get_observations(
        concept_data
    )

    annual = []

    for obs in observations:

        form = obs.get("form")
        fp = obs.get("fp")

        if form != "10-K":
            continue

        if fp != "FY":
            continue

        if "start" not in obs:
            continue

        annual.append(obs)

    if not annual:
        return None

    annual.sort(
        key=lambda x: (
            x.get("filed", ""),
            x.get("end", ""),
        ),
        reverse=True,
    )

    return annual[0]


def find_best_annual_concept(
    data: dict,
    concept_names,
    namespaces=("us-gaap",),
):

    candidates = []

    for item in get_all_concepts(data):

        if item["namespace"] not in namespaces:
            continue

        if item["concept"] not in concept_names:
            continue

        latest = select_latest_annual_observation(
            item["data"]
        )

        if latest is None:
            continue

        candidates.append(
            {
                "namespace": item["namespace"],
                "concept": item["concept"],
                "observation": latest,
            }
        )

    if not candidates:
        return None

    candidates.sort(
        key=lambda x: (
            x["observation"].get("filed", ""),
            x["observation"].get("end", ""),
        ),
        reverse=True,
    )

    return candidates[0]


# ============================================================
# METRIC EXTRACTION
# ============================================================

def extract_metric(
    data: dict,
    metric_name: str,
    concept_candidates,
    namespaces=("us-gaap",),
    annual=True,
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

        return {
            "metric": metric_name,
            "status": "MISSING",
            "value": None,
        }

    obs = result["observation"]

    return {
        "metric": metric_name,
        "status": "OK",
        "namespace": result["namespace"],
        "concept": result["concept"],
        "unit": obs.get("unit"),
        "value": obs.get("val"),
        "period_start": obs.get("start"),
        "period_end": obs.get("end"),
        "filing_date": obs.get("filed"),
        "form": obs.get("form"),
        "fy": obs.get("fy"),
        "fp": obs.get("fp"),
        "frame": obs.get("frame"),
        "accession": obs.get("accn"),
    }


# ============================================================
# INSTANT FACT EXTRACTION
# ============================================================

def select_latest_instant_observation(
    concept_data: dict,
):

    observations = get_observations(
        concept_data
    )

    instant = []

    for obs in observations:

        if "end" not in obs:
            continue

        if "start" in obs:
            continue

        instant.append(obs)

    if not instant:
        return None

    instant.sort(
        key=lambda x: (
            x.get("filed", ""),
            x.get("end", ""),
        ),
        reverse=True,
    )

    return instant[0]


def find_best_instant_concept(
    data: dict,
    concept_names,
    namespaces=("us-gaap", "dei"),
):

    candidates = []

    for item in get_all_concepts(data):

        if item["namespace"] not in namespaces:
            continue

        if item["concept"] not in concept_names:
            continue

        latest = select_latest_instant_observation(
            item["data"]
        )

        if latest is None:
            continue

        candidates.append(
            {
                "namespace": item["namespace"],
                "concept": item["concept"],
                "observation": latest,
            }
        )

    if not candidates:
        return None

    candidates.sort(
        key=lambda x: (
            x["observation"].get("filed", ""),
            x["observation"].get("end", ""),
        ),
        reverse=True,
    )

    return candidates[0]


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

        return {
            "metric": metric_name,
            "status": "MISSING",
            "value": None,
        }

    obs = result["observation"]

    return {
        "metric": metric_name,
        "status": "OK",
        "namespace": result["namespace"],
        "concept": result["concept"],
        "unit": obs.get("unit"),
        "value": obs.get("val"),
        "period_end": obs.get("end"),
        "filing_date": obs.get("filed"),
        "form": obs.get("form"),
        "fy": obs.get("fy"),
        "fp": obs.get("fp"),
        "frame": obs.get("frame"),
        "accession": obs.get("accn"),
    }


# ============================================================
# COMPANY NORMALIZATION
# ============================================================

def normalize_company(
    ticker: str,
    data: dict,
):

    print()
    print("=" * 70)
    print(f"NORMALIZING {ticker}")
    print("=" * 70)

    # --------------------------------------------------------
    # Revenue
    # --------------------------------------------------------

    revenue = extract_metric(
        data,
        "revenue",
        [
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "Revenues",
            "SalesRevenueNet",
        ],
    )

    # --------------------------------------------------------
    # Net Income
    # --------------------------------------------------------

    net_income = extract_metric(
        data,
        "net_income",
        [
            "NetIncomeLoss",
            "ProfitLoss",
        ],
    )

    # --------------------------------------------------------
    # EPS
    # --------------------------------------------------------

    diluted_eps = extract_metric(
        data,
        "diluted_eps",
        [
            "EarningsPerShareDiluted",
        ],
    )

    # --------------------------------------------------------
    # Operating Income
    # --------------------------------------------------------

    operating_income = extract_metric(
        data,
        "operating_income",
        [
            "OperatingIncomeLoss",
        ],
    )

    # --------------------------------------------------------
    # CFO
    # --------------------------------------------------------

    cfo = extract_metric(
        data,
        "cfo",
        [
            "NetCashProvidedByUsedInOperatingActivities",
        ],
    )

    # --------------------------------------------------------
    # CapEx
    # --------------------------------------------------------

    capex = extract_metric(
        data,
        "capex",
        [
            "PaymentsToAcquirePropertyPlantAndEquipment",
        ],
    )

    # --------------------------------------------------------
    # Cash
    # --------------------------------------------------------

    cash = extract_instant_metric(
        data,
        "cash",
        [
            "CashAndCashEquivalentsAtCarryingValue",
        ],
    )

    # --------------------------------------------------------
    # Debt
    # --------------------------------------------------------

    current_debt = extract_instant_metric(
        data,
        "current_debt",
        [
            "LongTermDebtCurrent",
            "ShortTermBorrowings",
            "ShortTermDebt",
        ],
    )

    noncurrent_debt = extract_instant_metric(
        data,
        "noncurrent_debt",
        [
            "LongTermDebtNoncurrent",
            "LongTermDebt",
        ],
    )

    # --------------------------------------------------------
    # Shares
    # --------------------------------------------------------

    shares = extract_instant_metric(
        data,
        "shares_outstanding",
        [
            "EntityCommonStockSharesOutstanding",
        ],
        namespaces=("dei",),
    )

    # --------------------------------------------------------
    # Construct total debt
    # --------------------------------------------------------

    total_debt = {
        "metric": "total_debt",
        "status": "OK",
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
    ):

        total_debt["value"] = (
            current_value +
            noncurrent_value
        )

    else:

        total_debt["status"] = "INCOMPLETE"

    # --------------------------------------------------------
    # Result
    # --------------------------------------------------------

    normalized = {

        "ticker": ticker,

        "entity_name": data.get(
            "entityName"
        ),

        "cik": data.get("cik"),

        "retrieved_at": datetime.now(
            timezone.utc
        ).isoformat(),

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

            "shares_outstanding": shares,
        },
    }

    return normalized


# ============================================================
# VALIDATION
# ============================================================

def validate_normalized_data(
    normalized: dict,
):

    ticker = normalized["ticker"]

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

    print()
    print(
        f"=== Validation: {ticker} ==="
    )

    failures = []

    for metric in required_metrics:

        data = normalized["metrics"][metric]

        status = data.get("status")

        if status == "OK":

            print(
                f"[PASS] {metric}: "
                f"{data.get('value')}"
            )

        else:

            print(
                f"[WARN] {metric}: "
                f"{status}"
            )

            failures.append(metric)

    total_debt = normalized["metrics"]["total_debt"]

    if total_debt.get("status") == "OK":

        print(
            f"[PASS] total_debt: "
            f"{total_debt.get('value')}"
        )

    else:

        print(
            "[WARN] total_debt: "
            f"{total_debt.get('status')}"
        )

    return failures


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

    print("=== SEC Company Facts Test ===")
    print()

    for ticker, cik in TICKERS.items():

        print(
            f"Ticker: {ticker}"
        )

        url = (
            "https://data.sec.gov/api/xbrl/"
            f"companyfacts/CIK{cik}.json"
        )

        print(
            f"CIK: {cik}"
        )

        print(
            f"URL: {url}"
        )

        try:

            # ------------------------------------------------
            # 1. Fetch
            # ------------------------------------------------

            data = fetch_json(url)

            # ------------------------------------------------
            # 2. Validate raw response
            # ------------------------------------------------

            validate_companyfacts(data)

            # ------------------------------------------------
            # 3. Save raw cache
            # ------------------------------------------------

            raw_file = (
                RAW_DIR /
                f"{ticker}_companyfacts.json"
            )

            with raw_file.open(
                "w",
                encoding="utf-8"
            ) as f:

                json.dump(
                    data,
                    f,
                    ensure_ascii=False,
                    indent=2
                )

            print(
                f"[PASS] Raw cache written: "
                f"{raw_file}"
            )

            # ------------------------------------------------
            # 4. Normalize
            # ------------------------------------------------

            normalized = normalize_company(
                ticker,
                data,
            )

            # ------------------------------------------------
            # 5. Validate normalized data
            # ------------------------------------------------

            failures = validate_normalized_data(
                normalized
            )

            # ------------------------------------------------
            # 6. Save normalized data
            # ------------------------------------------------

            processed_file = (
                PROCESSED_DIR /
                f"{ticker}_fundamentals.json"
            )

            with processed_file.open(
                "w",
                encoding="utf-8"
            ) as f:

                json.dump(
                    normalized,
                    f,
                    ensure_ascii=False,
                    indent=2
                )

            print(
                f"[PASS] Normalized data written: "
                f"{processed_file}"
            )

            if not failures:

                print(
                    f"[PASS] Fundamental validation: "
                    f"{ticker}"
                )

                success_count += 1

            else:

                print(
                    f"[WARN] {ticker} has missing metrics: "
                    f"{', '.join(failures)}"
                )

        except Exception as e:

            print(
                f"[FAIL] {ticker}: "
                f"{type(e).__name__}: {e}"
            )

        print("-" * 70)

    print()
    print(
        f"Result: "
        f"{success_count}/{len(TICKERS)} "
        f"tickers fully normalized"
    )

    if success_count != len(TICKERS):

        raise RuntimeError(
            "SEC fundamental normalization "
            "test failed"
        )

    print()
    print(
        "[PASS] All SEC fundamental normalization tests passed."
    )


if __name__ == "__main__":
    main()