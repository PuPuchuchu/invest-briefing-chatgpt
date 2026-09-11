import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


TICKER = "MSFT"
CIK = "0000789019"

BASE_URL = (
    f"https://data.sec.gov/api/xbrl/companyfacts/"
    f"CIK{CIK}.json"
)

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw" / "sec"

RAW_DIR.mkdir(parents=True, exist_ok=True)


USER_AGENT = os.getenv(
    "SEC_USER_AGENT",
    "stock-master-sec-test/0.1 your-email@example.com",
)


def fetch_json(url: str) -> dict:

    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept-Encoding": "gzip, deflate",
        },
        method="GET",
    )

    with urlopen(request, timeout=30) as response:

        if response.status != 200:
            raise RuntimeError(
                f"HTTP status: {response.status}"
            )

        return json.load(response)


def main():

    retrieved_at = (
        datetime.now(timezone.utc).isoformat()
    )

    print("================================")
    print("SEC Company Facts Test v0.1")
    print("================================")

    print(f"Ticker: {TICKER}")
    print(f"CIK: {CIK}")
    print(f"URL: {BASE_URL}")

    # --------------------------------
    # 1. API request
    # --------------------------------

    try:

        payload = fetch_json(BASE_URL)

    except HTTPError as e:

        print(
            f"[FAIL] HTTPError "
            f"{e.code}: {e.reason}"
        )

        return 1

    except URLError as e:

        print(
            f"[FAIL] URLError: {e.reason}"
        )

        return 1

    except Exception as e:

        print(
            f"[FAIL] "
            f"{type(e).__name__}: {e}"
        )

        return 1

    print("[PASS] HTTP request")

    # --------------------------------
    # 2. Basic schema validation
    # --------------------------------

    required_keys = [
        "cik",
        "entityName",
        "facts",
    ]

    missing = [
        key
        for key in required_keys
        if key not in payload
    ]

    if missing:

        print(
            f"[FAIL] Missing keys: {missing}"
        )

        return 1

    print("[PASS] JSON schema")

    # --------------------------------
    # 3. CIK validation
    # --------------------------------

    if payload["cik"] != int(CIK):

        print(
            f"[FAIL] Unexpected CIK: "
            f"{payload['cik']}"
        )

        return 1

    print("[PASS] CIK validation")

    print(
        f"Entity: {payload['entityName']}"
    )

    # --------------------------------
    # 4. US-GAAP validation
    # --------------------------------

    usgaap = payload["facts"].get(
        "us-gaap",
        {}
    )

    if not usgaap:

        print(
            "[FAIL] No US-GAAP facts"
        )

        return 1

    print("[PASS] US-GAAP facts")

    # --------------------------------
    # 5. Candidate metrics
    # --------------------------------

    candidate_tags = {

        "Revenue": [
            "Revenues",
            "RevenueFromContractWithCustomerExcludingAssessedTax",
        ],

        "NetIncome": [
            "NetIncomeLoss"
        ],

        "CFO": [
            "NetCashProvidedByUsedInOperatingActivities"
        ],

        "CapEx": [
            "PaymentsToAcquirePropertyPlantAndEquipment"
        ],

        "Cash": [
            "CashAndCashEquivalentsAtCarryingValue"
        ],

        "Debt": [
            "LongTermDebtCurrent",
            "LongTermDebtNoncurrent",
            "LongTermDebtAndFinanceLeaseObligationsCurrent",
            "LongTermDebtAndFinanceLeaseObligationsNoncurrent",
        ],

        "Shares": [
            "EntityCommonStockSharesOutstanding"
        ],
    }

    results = {}

    for metric, tags in candidate_tags.items():

        found = []

        for tag in tags:

            if tag not in usgaap:
                continue

            units = usgaap[tag].get(
                "units",
                {}
            )

            observations = sum(
                len(values)
                for values in units.values()
            )

            found.append({
                "tag": tag,
                "observations": observations
            })

        results[metric] = found

    # --------------------------------
    # 6. Save raw response
    # --------------------------------

    raw_path = (
        RAW_DIR /
        f"{TICKER}_companyfacts.json"
    )

    with raw_path.open(
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            {
                "retrieved_at": retrieved_at,
                "source": "SEC data.sec.gov",
                "ticker": TICKER,
                "cik": CIK,
                "payload": payload,
            },
            file,
            ensure_ascii=False,
        )

    print()
    print("Metric detection")
    print("----------------")

    for metric, found in results.items():

        if found:

            print(
                f"[PASS] {metric}: {found}"
            )

        else:

            print(
                f"[WARN] {metric}: "
                f"no tested XBRL tag"
            )

    print()
    print(
        f"[PASS] Raw cache written: "
        f"{raw_path}"
    )

    print()
    print(
        "SEC acquisition test completed."
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())