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
# SEC request
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

        encoding = (
            response.headers.get(
                "Content-Encoding",
                ""
            ).lower()
        )

        raw_data = response.read()

        if status != 200:
            raise RuntimeError(
                f"HTTP status: {status}"
            )

        if encoding == "gzip":
            raw_data = gzip.decompress(raw_data)

        elif encoding == "deflate":
            raw_data = zlib.decompress(raw_data)

        return json.loads(
            raw_data.decode("utf-8")
        )


# =========================================================
# Find concepts
# =========================================================

def find_concept(
    data: dict,
    concept: str
):

    facts = data.get(
        "facts",
        {}
    )

    for namespace in [
        "us-gaap",
        "dei",
        "invest",
        "srt",
        "ecd",
        "ffd",
    ]:

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
# Print observation diagnostics
# =========================================================

def diagnose_concept(
    ticker: str,
    metric: str,
    concept: str,
    namespace: str,
    fact: dict
):

    print()
    print(
        f"### {ticker} | {metric}"
    )

    print(
        f"namespace = {namespace}"
    )

    print(
        f"concept   = {concept}"
    )

    print(
        f"label     = "
        f"{fact.get('label', '')}"
    )

    print(
        f"description = "
        f"{fact.get('description', '')[:180]}"
    )

    units = fact.get(
        "units",
        {}
    )

    for unit, rows in units.items():

        print()
        print(
            f"UNIT: {unit}"
        )

        # Sort primarily by filing date.
        rows_sorted = sorted(
            rows,
            key=lambda x: (
                x.get("filed", ""),
                x.get("end", ""),
                x.get("start", ""),
            ),
            reverse=True,
        )

        # Show only the most recent 12
        # observations for diagnosis.
        for row in rows_sorted[:12]:

            print(
                "  "
                f"value={row.get('val')} | "
                f"start={row.get('start', '-')} | "
                f"end={row.get('end', '-')} | "
                f"filed={row.get('filed', '-')} | "
                f"form={row.get('form', '-')} | "
                f"fy={row.get('fy', '-')} | "
                f"fp={row.get('fp', '-')} | "
                f"frame={row.get('frame', '-')} | "
                f"accn={row.get('accn', '-')}"
            )


# =========================================================
# Diagnose one ticker
# =========================================================

def diagnose_ticker(
    ticker: str,
    cik: str
):

    print()
    print(
        "=" * 80
    )

    print(
        f"TICKER: {ticker}"
    )

    print(
        f"CIK: {cik}"
    )

    print(
        "=" * 80
    )

    raw_file = (
        RAW_DIR /
        f"{ticker}_companyfacts.json"
    )

    # Use the raw file if it exists.
    # Otherwise download it.
    if raw_file.exists():

        print(
            f"[INFO] Using existing raw file: "
            f"{raw_file}"
        )

        with raw_file.open(
            "r",
            encoding="utf-8"
        ) as f:

            data = json.load(f)

    else:

        print(
            "[INFO] Raw file not found. "
            "Downloading from SEC..."
        )

        url = (
            "https://data.sec.gov/api/xbrl/"
            f"companyfacts/CIK{cik}.json"
        )

        data = fetch_json(url)

        RAW_DIR.mkdir(
            parents=True,
            exist_ok=True
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
        f"Entity: {data.get('entityName')}"
    )

    facts = data.get(
        "facts",
        {}
    )

    print(
        "Namespaces: "
        f"{list(facts.keys())}"
    )

    # -----------------------------------------------------
    # Each metric
    # -----------------------------------------------------

    for metric, candidates in (
        METRIC_CANDIDATES.items()
    ):

        found = False

        print()
        print(
            "-" * 80
        )

        print(
            f"SEARCH METRIC: {metric}"
        )

        for concept in candidates:

            namespace, fact = find_concept(
                data,
                concept
            )

            if fact is None:
                continue

            found = True

            diagnose_concept(
                ticker,
                metric,
                concept,
                namespace,
                fact
            )

            # Only the first matching concept
            # is diagnosed in this test.
            break

        if not found:

            print(
                f"[NOT FOUND] {metric}"
            )


# =========================================================
# Main
# =========================================================

def main():

    print(
        "================================================"
    )

    print(
        "SEC FACT DIAGNOSTIC TEST"
    )

    print(
        "================================================"
    )

    print(
        "Purpose:"
    )

    print(
        "Inspect actual SEC XBRL observations "
        "before designing the production extraction logic."
    )

    for ticker, cik in TICKERS.items():

        try:

            diagnose_ticker(
                ticker,
                cik
            )

        except Exception as e:

            print(
                f"[FAIL] {ticker}: "
                f"{type(e).__name__}: {e}"
            )

    print()
    print(
        "================================================"
    )

    print(
        "DIAGNOSTIC TEST COMPLETE"
    )

    print(
        "================================================"
    )


if __name__ == "__main__":
    main()