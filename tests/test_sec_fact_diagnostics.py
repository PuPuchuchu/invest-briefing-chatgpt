import json
import gzip
import zlib
from pathlib import Path
from urllib.request import Request, urlopen
from datetime import datetime, date


# ============================================================
# CONFIGURATION
# ============================================================

USER_AGENT = "invest-briefing-chatgpt/0.1 chks7788@gmail.com"

TICKERS = {
    "NVDA": "0001045810",
    "LLY": "0000059478",
    "PLTR": "0001321655",
}


RAW_DIR = Path("data/raw/sec")


# ============================================================
# TARGET CONCEPTS
# ============================================================

TARGET_CONCEPTS = {

    # --------------------------------------------------------
    # NVDA
    # --------------------------------------------------------

    "NVDA": [

        "RevenueFromContractWithCustomerExcludingAssessedTax",

        "Revenues",

        "SalesRevenueNet",

        "NetIncomeLoss",

        "ProfitLoss",

        "OperatingIncomeLoss",

        "NetCashProvidedByUsedInOperatingActivities",

        "PaymentsToAcquirePropertyPlantAndEquipment",

        "PaymentsToAcquireOtherPropertyPlantAndEquipment",

        "CashAndCashEquivalentsAtCarryingValue",

        "LongTermDebtCurrent",

        "LongTermDebtNoncurrent",

        "LongTermDebt",

        "DebtCurrent",

        "ShortTermBorrowings",

        "ShortTermDebt",

        "DebtLongtermAndShorttermCombinedAmount",

        "EntityCommonStockSharesOutstanding",

        "CommonStockSharesOutstanding",
    ],


    # --------------------------------------------------------
    # LLY
    # --------------------------------------------------------

    "LLY": [

        "RevenueFromContractWithCustomerExcludingAssessedTax",

        "Revenues",

        "SalesRevenueNet",

        "NetIncomeLoss",

        "ProfitLoss",

        "OperatingIncomeLoss",

        "NetCashProvidedByUsedInOperatingActivities",

        "PaymentsToAcquirePropertyPlantAndEquipment",

        "PaymentsToAcquireOtherPropertyPlantAndEquipment",

        "CashAndCashEquivalentsAtCarryingValue",

        "LongTermDebtCurrent",

        "LongTermDebtNoncurrent",

        "LongTermDebt",

        "DebtCurrent",

        "ShortTermBorrowings",

        "ShortTermDebt",

        "DebtLongtermAndShorttermCombinedAmount",

        "EntityCommonStockSharesOutstanding",

        "CommonStockSharesOutstanding",
    ],


    # --------------------------------------------------------
    # PLTR
    # --------------------------------------------------------

    "PLTR": [

        "RevenueFromContractWithCustomerExcludingAssessedTax",

        "Revenues",

        "SalesRevenueNet",

        "NetIncomeLoss",

        "ProfitLoss",

        "OperatingIncomeLoss",

        "NetCashProvidedByUsedInOperatingActivities",

        "PaymentsToAcquirePropertyPlantAndEquipment",

        "PaymentsToAcquireOtherPropertyPlantAndEquipment",

        "CashAndCashEquivalentsAtCarryingValue",

        "LongTermDebtCurrent",

        "LongTermDebtNoncurrent",

        "LongTermDebt",

        "DebtCurrent",

        "ShortTermBorrowings",

        "ShortTermDebt",

        "DebtLongtermAndShorttermCombinedAmount",

        "EntityCommonStockSharesOutstanding",

        "CommonStockSharesOutstanding",
    ],
}


# ============================================================
# FETCH
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

    with urlopen(
        request,
        timeout=30
    ) as response:

        status = response.status

        content_encoding = (
            response.headers.get(
                "Content-Encoding",
                ""
            ).lower()
        )

        raw_data = response.read()

        print(
            f"HTTP status: {status}"
        )

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

        return json.loads(
            raw_data.decode(
                "utf-8"
            )
        )


# ============================================================
# DATE HELPERS
# ============================================================

def parse_date(
    value
):

    if not value:

        return None

    try:

        return datetime.strptime(
            value,
            "%Y-%m-%d"
        ).date()

    except ValueError:

        return None


def duration_days(
    observation
):

    start = parse_date(
        observation.get("start")
    )

    end = parse_date(
        observation.get("end")
    )

    if not start or not end:

        return None

    return (
        end - start
    ).days + 1


# ============================================================
# OBSERVATION DISPLAY
# ============================================================

def print_observation(
    observation,
    index=None
):

    if index is not None:

        print(
            f"  Observation #{index}"
        )

    print(
        f"    value      = "
        f"{observation.get('val')}"
    )

    print(
        f"    unit       = "
        f"{observation.get('unit')}"
    )

    print(
        f"    start      = "
        f"{observation.get('start')}"
    )

    print(
        f"    end        = "
        f"{observation.get('end')}"
    )

    print(
        f"    duration   = "
        f"{duration_days(observation)} days"
    )

    print(
        f"    filed      = "
        f"{observation.get('filed')}"
    )

    print(
        f"    form       = "
        f"{observation.get('form')}"
    )

    print(
        f"    fy         = "
        f"{observation.get('fy')}"
    )

    print(
        f"    fp         = "
        f"{observation.get('fp')}"
    )

    print(
        f"    frame      = "
        f"{observation.get('frame')}"
    )

    print(
        f"    accession  = "
        f"{observation.get('accn')}"
    )


# ============================================================
# CONCEPT EXTRACTION
# ============================================================

def get_target_concepts(
    data: dict,
    target_names
):

    found = []

    facts = data.get(
        "facts",
        {}
    )

    for namespace, namespace_data in facts.items():

        if not isinstance(
            namespace_data,
            dict
        ):
            continue

        for concept_name, concept_data in namespace_data.items():

            if concept_name not in target_names:
                continue

            found.append(
                {
                    "namespace": namespace,
                    "concept": concept_name,
                    "data": concept_data,
                }
            )

    return found


# ============================================================
# PRINT CONCEPT
# ============================================================

def print_concept(
    item
):

    namespace = item[
        "namespace"
    ]

    concept = item[
        "concept"
    ]

    concept_data = item[
        "data"
    ]

    print()
    print(
        "-" * 80
    )

    print(
        f"CONCEPT: "
        f"{namespace}:{concept}"
    )

    units = concept_data.get(
        "units",
        {}
    )

    if not units:

        print(
            "  [NO UNITS]"
        )

        return


    for unit, observations in units.items():

        if not isinstance(
            observations,
            list
        ):
            continue

        print()
        print(
            f"  UNIT: {unit}"
        )

        # ----------------------------------------------------
        # Sort newest filing first
        # ----------------------------------------------------

        sorted_observations = sorted(
            observations,
            key=lambda x: (
                x.get("filed", ""),
                x.get("end", ""),
                x.get("start", ""),
            ),
            reverse=True,
        )


        # ----------------------------------------------------
        # Show recent observations
        # ----------------------------------------------------

        max_rows = 20

        for index, observation in enumerate(
            sorted_observations[
                :max_rows
            ],
            start=1
        ):

            print_observation(
                observation,
                index
            )


# ============================================================
# SEARCH CUSTOM TAXONOMY
# ============================================================

def search_custom_taxonomy(
    data: dict,
    keywords
):

    """
    us-gaap / dei 이외 namespace까지 검색한다.

    LLY처럼 회사별 custom taxonomy를 사용하는 경우
    Operating Income 후보를 찾기 위한 진단용 함수.
    """

    facts = data.get(
        "facts",
        {}
    )

    results = []

    for namespace, namespace_data in facts.items():

        if namespace in (
            "us-gaap",
            "dei",
        ):
            continue

        if not isinstance(
            namespace_data,
            dict
        ):
            continue

        for concept_name, concept_data in namespace_data.items():

            concept_lower = (
                concept_name.lower()
            )

            if all(
                keyword.lower()
                in concept_lower
                for keyword in keywords
            ):

                results.append(
                    {
                        "namespace": namespace,
                        "concept": concept_name,
                        "data": concept_data,
                    }
                )

    return results


# ============================================================
# CUSTOM TAXONOMY DISPLAY
# ============================================================

def print_custom_candidates(
    data: dict,
    keywords,
    label
):

    print()
    print(
        "=" * 80
    )

    print(
        f"CUSTOM TAXONOMY SEARCH: "
        f"{label}"
    )

    print(
        f"Keywords: {keywords}"
    )

    candidates = search_custom_taxonomy(
        data,
        keywords
    )

    if not candidates:

        print(
            "[WARN] No custom taxonomy candidates found."
        )

        return


    print(
        f"[FOUND] "
        f"{len(candidates)} candidate(s)"
    )


    for item in candidates:

        print()
        print(
            f"- {item['namespace']}:"
            f"{item['concept']}"
        )

        units = item[
            "data"
        ].get(
            "units",
            {}
        )

        for unit, observations in units.items():

            if not isinstance(
                observations,
                list
            ):
                continue

            sorted_observations = sorted(
                observations,
                key=lambda x: (
                    x.get("filed", ""),
                    x.get("end", ""),
                    x.get("start", ""),
                ),
                reverse=True,
            )

            for observation in sorted_observations[:5]:

                print(
                    f"  {unit} | "
                    f"value={observation.get('val')} | "
                    f"start={observation.get('start')} | "
                    f"end={observation.get('end')} | "
                    f"filed={observation.get('filed')} | "
                    f"form={observation.get('form')} | "
                    f"fp={observation.get('fp')} | "
                    f"fy={observation.get('fy')} | "
                    f"frame={observation.get('frame')} | "
                    f"accn={observation.get('accn')}"
                )


# ============================================================
# PERIOD DIAGNOSTICS
# ============================================================

def print_period_summary(
    item
):

    concept = (
        f"{item['namespace']}:"
        f"{item['concept']}"
    )

    observations = []

    for unit, values in item[
        "data"
    ].get(
        "units",
        {}
    ).items():

        if not isinstance(
            values,
            list
        ):
            continue

        for observation in values:

            row = dict(
                observation
            )

            row["unit"] = unit

            observations.append(
                row
            )


    print()
    print(
        f"PERIOD SUMMARY: {concept}"
    )


    annual = []

    ytd = []

    quarterly = []

    instant = []


    for observation in observations:

        if not observation.get(
            "start"
        ):

            instant.append(
                observation
            )

            continue


        days = duration_days(
            observation
        )

        if days is None:
            continue


        if (
            observation.get("form")
            == "10-K"
            and
            observation.get("fp")
            == "FY"
        ):

            annual.append(
                observation
            )


        if (
            150 <= days <= 220
        ):

            ytd.append(
                observation
            )


        if (
            70 <= days <= 110
        ):

            quarterly.append(
                observation
            )


    print(
        f"  Annual 10-K FY observations : "
        f"{len(annual)}"
    )

    print(
        f"  YTD-like observations        : "
        f"{len(ytd)}"
    )

    print(
        f"  Quarterly-like observations  : "
        f"{len(quarterly)}"
    )

    print(
        f"  Instant observations         : "
        f"{len(instant)}"
    )


    if annual:

        print()
        print(
            "  Latest annual observations:"
        )

        annual = sorted(
            annual,
            key=lambda x: (
                x.get("filed", ""),
                x.get("end", ""),
            ),
            reverse=True,
        )

        for observation in annual[:5]:

            print(
                f"    value={observation.get('val')} | "
                f"start={observation.get('start')} | "
                f"end={observation.get('end')} | "
                f"days={duration_days(observation)} | "
                f"filed={observation.get('filed')} | "
                f"fy={observation.get('fy')} | "
                f"fp={observation.get('fp')} | "
                f"frame={observation.get('frame')} | "
                f"accn={observation.get('accn')}"
            )


# ============================================================
# COMPANY DIAGNOSTIC
# ============================================================

def diagnose_company(
    ticker,
    cik
):

    print()
    print()
    print(
        "#" * 90
    )

    print(
        f"DIAGNOSTIC: {ticker}"
    )

    print(
        "#" * 90
    )


    url = (
        "https://data.sec.gov/api/xbrl/"
        f"companyfacts/CIK{cik}.json"
    )


    print(
        f"URL: {url}"
    )


    # --------------------------------------------------------
    # Fetch
    # --------------------------------------------------------

    data = fetch_json(
        url
    )


    print(
        f"Entity: "
        f"{data.get('entityName')}"
    )

    print(
        f"CIK: "
        f"{data.get('cik')}"
    )


    # --------------------------------------------------------
    # Save raw
    # --------------------------------------------------------

    raw_file = (
        RAW_DIR
        /
        f"{ticker}_companyfacts_diagnostic.json"
    )

    raw_file.parent.mkdir(
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
        f"[PASS] Diagnostic raw cache: "
        f"{raw_file}"
    )


    # ========================================================
    # TARGET CONCEPTS
    # ========================================================

    print()
    print(
        "=" * 80
    )

    print(
        "TARGET CONCEPT INSPECTION"
    )

    target_names = TARGET_CONCEPTS[
        ticker
    ]


    concepts = get_target_concepts(
        data,
        target_names
    )


    print(
        f"Found "
        f"{len(concepts)} target concept(s)"
    )


    for item in concepts:

        print_concept(
            item
        )

        print_period_summary(
            item
        )


    # ========================================================
    # CUSTOM TAXONOMY
    # ========================================================

    # --------------------------------------------------------
    # Operating income
    # --------------------------------------------------------

    print_custom_candidates(
        data,
        [
            "operating",
            "income",
        ],
        "Operating Income"
    )


    # --------------------------------------------------------
    # Revenue
    # --------------------------------------------------------

    print_custom_candidates(
        data,
        [
            "revenue",
        ],
        "Revenue"
    )


    # --------------------------------------------------------
    # Debt
    # --------------------------------------------------------

    print_custom_candidates(
        data,
        [
            "debt",
        ],
        "Debt"
    )


    # --------------------------------------------------------
    # CapEx
    # --------------------------------------------------------

    print_custom_candidates(
        data,
        [
            "property",
            "plant",
        ],
        "Property Plant Equipment / CapEx"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "=== SEC FACT DIAGNOSTIC TEST ==="
    )

    print()

    for ticker, cik in TICKERS.items():

        try:

            diagnose_company(
                ticker,
                cik
            )

        except Exception as e:

            print()
            print(
                f"[FAIL] {ticker}: "
                f"{type(e).__name__}: {e}"
            )

        print()
        print(
            "=" * 90
        )


    print()
    print(
        "=== DIAGNOSTIC COMPLETE ==="
    )

    print(
        "No normalization result is modified by this test."
    )

    print(
        "Use the output to determine production Concept mappings."
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()