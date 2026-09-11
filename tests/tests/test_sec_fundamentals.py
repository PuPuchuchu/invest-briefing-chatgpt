import json
import os
from pathlib import Path


RAW_DIR = Path("data/raw/sec")
PROCESSED_DIR = Path("data/processed/fundamentals")

TICKERS = [
    "MSFT",
    "NVDA",
    "JPM",
    "LLY",
    "PLTR",
]


# ---------------------------------------------------------
# SEC XBRL concept candidates
# ---------------------------------------------------------

METRIC_CANDIDATES = {

    "revenue": [
        "Revenue",
        "Revenues",
        "SalesRevenueNet",
        "SalesRevenueGoodsNet",
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


# ---------------------------------------------------------
# Utility functions
# ---------------------------------------------------------

def load_companyfacts(ticker: str) -> dict:

    path = RAW_DIR / f"{ticker}_companyfacts.json"

    if not path.exists():
        raise FileNotFoundError(
            f"Raw SEC file not found: {path}"
        )

    with path.open(
        "r",
        encoding="utf-8"
    ) as f:

        return json.load(f)


def get_fact(
    data: dict,
    concept: str
):

    for namespace in [
        "us-gaap",
        "dei",
        "invest",
        "srt",
        "ecd",
        "ffd",
    ]:

        facts = data.get("facts", {})

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


def normalize_unit(
    unit: str
) -> str:

    return unit


def select_latest_observation(
    observations: list
):

    valid = []

    for obs in observations:

        if not obs.get("filed"):
            continue

        if "val" not in obs:
            continue

        valid.append(obs)

    if not valid:
        return None

    valid.sort(
        key=lambda x: x["filed"]
    )

    return valid[-1]


def extract_metric(
    data: dict,
    metric: str
):

    candidates = METRIC_CANDIDATES[
        metric
    ]

    for concept in candidates:

        namespace, fact = get_fact(
            data,
            concept
        )

        if fact is None:
            continue

        units = fact.get(
            "units",
            {}
        )

        if not units:
            continue

        # Try every unit available.
        for unit, observations in units.items():

            latest = select_latest_observation(
                observations
            )

            if latest is None:
                continue

            return {
                "metric": metric,
                "concept": concept,
                "namespace": namespace,
                "unit": normalize_unit(unit),
                "value": latest["val"],
                "period_end": latest.get("end"),
                "period_start": latest.get("start"),
                "fiscal_year": latest.get("fy"),
                "fiscal_period": latest.get("fp"),
                "form": latest.get("form"),
                "filed": latest.get("filed"),
                "frame": latest.get("frame"),
                "accn": latest.get("accn"),
            }

    return None


# ---------------------------------------------------------
# Main extraction
# ---------------------------------------------------------

def main():

    PROCESSED_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    total_pass = 0
    total_fail = 0

    print(
        "=== SEC Fundamental Extraction Test ==="
    )
    print()

    for ticker in TICKERS:

        print("=" * 70)
        print(
            f"Ticker: {ticker}"
        )
        print("=" * 70)

        try:

            data = load_companyfacts(
                ticker
            )

            entity_name = data.get(
                "entityName"
            )

            print(
                f"Entity: {entity_name}"
            )

            extracted = {}

            for metric in METRIC_CANDIDATES:

                result = extract_metric(
                    data,
                    metric
                )

                if result is None:

                    print(
                        f"[FAIL] "
                        f"{metric}: "
                        f"not found"
                    )

                    total_fail += 1

                else:

                    extracted[metric] = result

                    print(
                        f"[PASS] "
                        f"{metric}: "
                        f"{result['value']} "
                        f"{result['unit']} "
                        f"| "
                        f"{result['concept']} "
                        f"| filed "
                        f"{result['filed']}"
                    )

                    total_pass += 1

            output = {
                "ticker": ticker,
                "entity_name": entity_name,
                "source": "SEC Company Facts",
                "extracted_metrics": extracted,
            }

            output_file = (
                PROCESSED_DIR /
                f"{ticker}_fundamentals.json"
            )

            with output_file.open(
                "w",
                encoding="utf-8"
            ) as f:

                json.dump(
                    output,
                    f,
                    ensure_ascii=False,
                    indent=2
                )

            print()
            print(
                f"[PASS] "
                f"Processed file written: "
                f"{output_file}"
            )

        except Exception as e:

            print(
                f"[FAIL] {ticker}: "
                f"{type(e).__name__}: {e}"
            )

            total_fail += 1

        print()

    print("=" * 70)
    print(
        f"Metric extraction result: "
        f"{total_pass} PASS / "
        f"{total_fail} FAIL"
    )
    print("=" * 70)

    if total_fail > 0:

        raise RuntimeError(
            "SEC fundamental extraction test "
            "has failures."
        )

    print()
    print(
        "[PASS] All fundamental extraction "
        "tests passed."
    )


if __name__ == "__main__":
    main()