import json
from pathlib import Path
from datetime import datetime

from src.sec.fetcher import fetch_json as _shared_fetch_json
from src.sec.fetcher import get_user_agent as _get_user_agent


# ============================================================
# CONFIGURATION
# ============================================================
# Reads SEC_USER_AGENT from the environment now (matching the
# GitHub Actions workflow that invokes this script), falling back to
# this literal only when the env var isn't set (e.g. local ad-hoc runs).
# Resolved once at import time via a safe default, so it cannot crash
# pytest collection when the env var is unset.

USER_AGENT = _get_user_agent(default="invest-briefing-claude/0.1 chks7788@gmail.com")

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

    "PLTR": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
        "NetIncomeLoss",
        "ProfitLoss",
        "OperatingIncomeLoss",
        "NetCashProvidedByUsedInOperatingActivities",
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireOtherPropertyPlantAndPropertyPlantEquipment",
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
# DIAGNOSTIC SEARCH KEYWORDS
# ============================================================

SEARCH_GROUPS = {

    "Operating Income": [
        "operating",
        "income",
    ],

    "Operating": [
        "operating",
    ],

    "Income": [
        "income",
    ],

    "Debt": [
        "debt",
    ],

    "Borrowing": [
        "borrow",
    ],

    "Long Term Debt": [
        "long",
        "term",
        "debt",
    ],

    "Current Debt": [
        "current",
        "debt",
    ],

    "Cash": [
        "cash",
    ],

    "Revenue": [
        "revenue",
    ],

    "Property Plant Equipment": [
        "property",
        "plant",
    ],
}


# ============================================================
# FETCH
# ============================================================

def fetch_json(url: str) -> dict:
    # Delegates to src/sec/fetcher.py, which now owns the HTTP +
    # gzip/deflate handling previously duplicated in this file (and in
    # tests/test_sec_companyfacts.py, tests/test_sec_fundamentals_pipeline.py).
    # Kept as a thin local wrapper, still called as fetch_json(url), so the
    # one call site below (line ~1015) did not need to change.
    return _shared_fetch_json(url, user_agent=USER_AGENT, timeout=30)


# ============================================================
# DATE HELPERS
# ============================================================

def parse_date(value):

    if not value:
        return None

    try:

        return datetime.strptime(
            value,
            "%Y-%m-%d",
        ).date()

    except ValueError:

        return None


def duration_days(observation):

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
# OBSERVATION HELPERS
# ============================================================

def observation_value(observation):

    if "val" in observation:
        return observation.get("val")

    return observation.get("value")


def is_numeric(value):

    if isinstance(
        value,
        bool,
    ):
        return False

    return isinstance(
        value,
        (int, float),
    )


def is_annual_observation(
    observation,
):

    return (
        observation.get("form") == "10-K"
        and observation.get("fp") == "FY"
        and bool(
            observation.get("start")
        )
        and bool(
            observation.get("end")
        )
    )


def is_instant_observation(
    observation,
):

    return (
        not observation.get("start")
        and bool(
            observation.get("end")
        )
    )


# ============================================================
# OBSERVATION DISPLAY
# ============================================================

def print_observation(
    observation,
    index=None,
):

    if index is not None:

        print(
            f"  Observation #{index}"
        )

    print(
        f"    value      = "
        f"{observation_value(observation)}"
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
    target_names,
):

    found = []

    facts = data.get(
        "facts",
        {},
    )

    for namespace, namespace_data in facts.items():

        if not isinstance(
            namespace_data,
            dict,
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
# CONCEPT SUMMARY
# ============================================================

def get_concept_statistics(
    concept_data,
):

    units = concept_data.get(
        "units",
        {},
    )

    observation_count = 0
    annual_count = 0
    instant_count = 0

    latest_filed = None
    latest_end = None

    for unit, observations in units.items():

        if not isinstance(
            observations,
            list,
        ):
            continue

        for observation in observations:

            observation_count += 1

            filed = observation.get(
                "filed"
            )

            end = observation.get(
                "end"
            )

            if filed:

                if (
                    latest_filed is None
                    or filed > latest_filed
                ):
                    latest_filed = filed

            if end:

                if (
                    latest_end is None
                    or end > latest_end
                ):
                    latest_end = end

            if is_annual_observation(
                observation
            ):

                annual_count += 1

            if is_instant_observation(
                observation
            ):

                instant_count += 1

    return {
        "observation_count": observation_count,
        "annual_count": annual_count,
        "instant_count": instant_count,
        "latest_filed": latest_filed,
        "latest_end": latest_end,
    }


# ============================================================
# PRINT CONCEPT
# ============================================================

def print_concept(
    item,
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
        "-" * 90
    )

    print(
        f"CONCEPT: "
        f"{namespace}:{concept}"
    )

    print(
        f"LABEL: "
        f"{concept_data.get('label')}"
    )

    print(
        f"DESCRIPTION: "
        f"{concept_data.get('description')}"
    )

    stats = get_concept_statistics(
        concept_data
    )

    print(
        f"OBSERVATIONS: "
        f"{stats['observation_count']}"
    )

    print(
        f"ANNUAL 10-K/FY: "
        f"{stats['annual_count']}"
    )

    print(
        f"INSTANT: "
        f"{stats['instant_count']}"
    )

    print(
        f"LATEST FILED: "
        f"{stats['latest_filed']}"
    )

    print(
        f"LATEST END: "
        f"{stats['latest_end']}"
    )

    units = concept_data.get(
        "units",
        {},
    )

    if not units:

        print(
            "  [NO UNITS]"
        )

        return

    for unit, observations in units.items():

        if not isinstance(
            observations,
            list,
        ):
            continue

        print()
        print(
            f"  UNIT: {unit}"
        )

        sorted_observations = sorted(
            observations,
            key=lambda x: (
                x.get("filed", ""),
                x.get("end", ""),
                x.get("start", ""),
            ),
            reverse=True,
        )

        for index, observation in enumerate(
            sorted_observations[:10],
            start=1,
        ):

            print_observation(
                observation,
                index,
            )


# ============================================================
# SEARCH ALL TAXONOMIES
# ============================================================

def search_taxonomy(
    data: dict,
    keywords,
):

    facts = data.get(
        "facts",
        {},
    )

    results = []

    for namespace, namespace_data in facts.items():

        if not isinstance(
            namespace_data,
            dict,
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
# SEARCH RESULT SCORING
# ============================================================

def candidate_score(
    item,
):

    concept = item[
        "concept"
    ].lower()

    namespace = item[
        "namespace"
    ].lower()

    score = 0

    # Prefer us-gaap.
    if namespace == "us-gaap":
        score += 50

    # Prefer exact/strong economic terminology.
    priority_terms = [
        "operatingincomeloss",
        "operatingincome",
        "debtcurrent",
        "longtermdebtcurrent",
        "longtermdebtnoncurrent",
        "shorttermdebt",
        "shorttermborrowings",
        "debtlongtermandshorttermcombinedamount",
    ]

    for rank, term in enumerate(
        priority_terms
    ):

        if term in concept:
            score += (
                100
                - rank * 5
            )

    stats = get_concept_statistics(
        item["data"]
    )

    score += min(
        stats["annual_count"],
        20,
    )

    score += min(
        stats["instant_count"],
        20,
    )

    return score


# ============================================================
# PRINT SEARCH RESULTS
# ============================================================

def print_search_results(
    data: dict,
    keywords,
    label,
    max_candidates=30,
):

    print()
    print(
        "=" * 90
    )

    print(
        f"CONCEPT SEARCH: {label}"
    )

    print(
        f"Keywords: {keywords}"
    )

    candidates = search_taxonomy(
        data,
        keywords,
    )

    if not candidates:

        print(
            "[WARN] No candidates found."
        )

        return

    candidates.sort(
        key=candidate_score,
        reverse=True,
    )

    print(
        f"[FOUND] "
        f"{len(candidates)} candidate(s)"
    )

    for rank, item in enumerate(
        candidates[:max_candidates],
        start=1,
    ):

        concept_data = item[
            "data"
        ]

        stats = get_concept_statistics(
            concept_data
        )

        print()
        print(
            f"[{rank}] "
            f"{item['namespace']}:"
            f"{item['concept']}"
        )

        print(
            f"    label       = "
            f"{concept_data.get('label')}"
        )

        print(
            f"    description = "
            f"{concept_data.get('description')}"
        )

        print(
            f"    observations= "
            f"{stats['observation_count']}"
        )

        print(
            f"    annual      = "
            f"{stats['annual_count']}"
        )

        print(
            f"    instant     = "
            f"{stats['instant_count']}"
        )

        print(
            f"    latest filed= "
            f"{stats['latest_filed']}"
        )

        print(
            f"    latest end  = "
            f"{stats['latest_end']}"
        )


# ============================================================
# PERIOD DIAGNOSTICS
# ============================================================

def print_period_summary(
    item,
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
        {},
    ).items():

        if not isinstance(
            values,
            list,
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
                f"    value={observation_value(observation)} | "
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
    cik,
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
        exist_ok=True,
    )

    with raw_file.open(
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2,
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
        "=" * 90
    )

    print(
        "TARGET CONCEPT INSPECTION"
    )

    target_names = TARGET_CONCEPTS[
        ticker
    ]

    concepts = get_target_concepts(
        data,
        target_names,
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
    # ALL TAXONOMY SEARCH
    # ========================================================

    for label, keywords in SEARCH_GROUPS.items():

        print_search_results(
            data,
            keywords,
            label,
        )

    # ========================================================
    # COMPANY-SPECIFIC FOCUS
    # ========================================================

    if ticker == "LLY":

        print()
        print(
            "=" * 90
        )

        print(
            "LLY OPERATING INCOME FOCUS"
        )

        print_search_results(
            data,
            [
                "operating",
                "income",
            ],
            "LLY Operating Income",
            max_candidates=50,
        )

    if ticker == "PLTR":

        print()
        print(
            "=" * 90
        )

        print(
            "PLTR DEBT FOCUS"
        )

        print_search_results(
            data,
            [
                "debt",
            ],
            "PLTR Debt",
            max_candidates=50,
        )

        print_search_results(
            data,
            [
                "borrow",
            ],
            "PLTR Borrowing",
            max_candidates=50,
        )

        print_search_results(
            data,
            [
                "current",
                "debt",
            ],
            "PLTR Current Debt",
            max_candidates=50,
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
                cik,
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