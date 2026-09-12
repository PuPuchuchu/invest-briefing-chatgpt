import gzip
import json
import os
import zlib
from pathlib import Path
from urllib.request import Request, urlopen


# =========================================================
# Configuration
# =========================================================

USER_AGENT = os.environ.get("SEC_USER_AGENT")

if not USER_AGENT:
    raise RuntimeError(
        "SEC_USER_AGENT environment variable is not set."
    )


TICKERS = {
    "MSFT": "0000789019",
    "NVDA": "0001045810",
    "JPM": "0000019617",
    "LLY": "0000059478",
    "PLTR": "0001321655",
}


RAW_DIR = Path("data/raw/sec")
PROCESSED_DIR = Path("data/processed/fundamentals")


# =========================================================
# XBRL concept candidates
# =========================================================

METRIC_CANDIDATES = {

    "revenue": [
        "Revenue",
        "Revenues",
        "SalesRevenueNet",
        "SalesRevenueGoodsNet",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
    ],

    "net_income": [
        "NetIncomeLoss",
        "ProfitLoss",
    ],

    "diluted_eps": [
        "EarningsPerShareDiluted",
    ],

    "operating_income": [
        "OperatingIncomeLoss",
    ],

    "cfo": [
        "NetCashProvidedByUsedInOperatingActivities",
    ],

    "capex": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
    ],

    "cash": [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ],

    "debt": [
        "LongTermDebtCurrent",
        "LongTermDebtNoncurrent",
        "LongTermDebt",
        "ShortTermBorrowings",
        "ShortTermDebt",
    ],

    "shares_outstanding": [
        "EntityCommonStockSharesOutstanding",
    ],
}


# =========================================================
# SEC API
# =========================================================

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
            "Content-Encoding: "
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

        return json.loads(
            raw_data.decode("utf-8")
        )


# =========================================================
# Raw SEC acquisition
# =========================================================

def download_companyfacts(
    ticker: str,
    cik: str
) -> dict:

    url = (
        "https://data.sec.gov/api/xbrl/"
        f"companyfacts/CIK{cik}.json"
    )

    print()
    print("=" * 70)
    print(f"Downloading: {ticker}")
    print(f"CIK: {cik}")
    print("=" * 70)

    data = fetch_json(url)

    required_keys = [
        "cik",
        "entityName",
        "facts",
    ]

    for key in required_keys:

        if key not in data:
            raise ValueError(
                f"{ticker}: missing key '{key}'"
            )

    RAW_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

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

    return data


# =========================================================
# XBRL concept search
# =========================================================

def find_concept(
    data: dict,
    concept: str
):

    facts = data.get(
        "facts",
        {}
    )

    # Prefer us-gaap first.
    namespace_order = [
        "us-gaap",
        "dei",
        "invest",
        "srt",
        "ecd",
        "ffd",
    ]

    for namespace in namespace_order:

        namespace_facts = facts.get(
            namespace,
            {}
        )

        if concept in namespace_facts:

            return (
                namespace,
                namespace_facts[concept]
            )

    return None, None


# =========================================================
# Observation helpers
# =========================================================

def get_observations(
    fact: dict
):

    units = fact.get(
        "units",
        {}
    )

    observations = []

    for unit, rows in units.items():

        for row in rows:

            if "val" not in row:
                continue

            item = dict(row)

            item["unit"] = unit

            observations.append(item)

    return observations


def sort_observations(
    observations: list
):

    return sorted(
        observations,
        key=lambda x: (
            x.get("filed", ""),
            x.get("end", ""),
            x.get("accn", ""),
        )
    )


# =========================================================
# Metric extraction
# =========================================================

def extract_metric(
    data: dict,
    metric: str
):

    candidates = METRIC_CANDIDATES[
        metric
    ]

    for concept in candidates:

        namespace, fact = find_concept(
            data,
            concept
        )

        if fact is None:
            continue

        observations = get_observations(
            fact
        )

        observations = sort_observations(
            observations
        )

        if not observations:
            continue

        # Keep the latest filed observation
        # only for this acquisition test.
        latest = observations[-1]

        return {
            "metric": metric,
            "namespace": namespace,
            "concept": concept,
            "value": latest.get("val"),
            "unit": latest.get("unit"),
            "period_start": latest.get("start"),
            "period_end": latest.get("end"),
            "fiscal_year": latest.get("fy"),
            "fiscal_period": latest.get("fp"),
            "form": latest.get("form"),
            "filed": latest.get("filed"),
            "frame": latest.get("frame"),
            "accn": latest.get("accn"),
        }

    return None


# =========================================================
# Fundamental extraction
# =========================================================

def extract_fundamentals(
    ticker: str,
    data: dict
) -> dict:

    print()
    print(
        f"--- Fundamental extraction: "
        f"{ticker} ---"
    )

    entity_name = data.get(
        "entityName"
    )

    extracted = {}
    missing = []

    for metric in METRIC_CANDIDATES:

        result = extract_metric(
            data,
            metric
        )

        if result is None:

            print(
                f"[WARN] {metric}: NOT FOUND"
            )

            missing.append(metric)

        else:

            extracted[metric] = result

            print(
                f"[PASS] {metric}: "
                f"value={result['value']} "
                f"unit={result['unit']} "
                f"concept={result['concept']} "
                f"period_end={result['period_end']} "
                f"form={result['form']} "
                f"filed={result['filed']}"
            )

    return {
        "ticker": ticker,
        "entity_name": entity_name,
        "source": "SEC Company Facts",
        "extracted_metrics": extracted,
        "missing_metrics": missing,
    }


# =========================================================
# Main pipeline
# =========================================================

def main():

    print(
        "=============================================="
    )
    print(
        "SEC Fundamental Pipeline Test"
    )
    print(
        "=============================================="
    )

    PROCESSED_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    pipeline_results = {}

    api_success = 0
    extraction_success = 0

    for ticker, cik in TICKERS.items():

        try:

            data = download_companyfacts(
                ticker,
                cik
            )

            api_success += 1

            result = extract_fundamentals(
                ticker,
                data
            )

            pipeline_results[ticker] = result

            output_file = (
                PROCESSED_DIR /
                f"{ticker}_fundamentals.json"
            )

            with output_file.open(
                "w",
                encoding="utf-8"
            ) as f:

                json.dump(
                    result,
                    f,
                    ensure_ascii=False,
                    indent=2
                )

            print(
                f"[PASS] Processed file written: "
                f"{output_file}"
            )

            extraction_success += 1

        except Exception as e:

            print(
                f"[FAIL] {ticker}: "
                f"{type(e).__name__}: {e}"
            )

    # -----------------------------------------------------
    # Summary
    # -----------------------------------------------------

    print()
    print(
        "=============================================="
    )
    print(
        "FINAL RESULT"
    )
    print(
        "=============================================="
    )

    print(
        f"API acquisition: "
        f"{api_success}/{len(TICKERS)}"
    )

    print(
        f"Fundamental extraction: "
        f"{extraction_success}/{len(TICKERS)}"
    )

    total_metrics = 0
    found_metrics = 0

    for ticker, result in pipeline_results.items():

        found = len(
            result["extracted_metrics"]
        )

        missing = len(
            result["missing_metrics"]
        )

        total = found + missing

        total_metrics += total
        found_metrics += found

        print(
            f"{ticker}: "
            f"{found}/{total} metrics found"
        )

        if missing:

            print(
                f"  Missing: "
                f"{', '.join(result['missing_metrics'])}"
            )

    print()
    print(
        f"Metric availability: "
        f"{found_metrics}/{total_metrics}"
    )

    print(
        "=============================================="
    )

    # API acquisition failure is a hard failure.
    if api_success != len(TICKERS):

        raise RuntimeError(
            "SEC API acquisition test failed."
        )

    # Extraction itself should not fail for all companies.
    if extraction_success != len(TICKERS):

        raise RuntimeError(
            "Fundamental extraction pipeline failed."
        )

    print(
        "[PASS] SEC Fundamental Pipeline completed."
    )


if __name__ == "__main__":
    main()