import json
from pathlib import Path


RAW_DIR = Path("data/raw/sec")

TICKERS = [
    "MSFT",
    "NVDA",
    "JPM",
    "LLY",
    "PLTR",
]


SEARCH_TERMS = {
    "operating_income": [
        "operating",
        "income",
    ],
    "capex": [
        "property",
        "plant",
        "equipment",
    ],
    "shares": [
        "shares",
        "outstanding",
    ],
    "debt": [
        "debt",
    ],
}


def load_companyfacts(ticker):

    path = RAW_DIR / f"{ticker}_companyfacts.json"

    if not path.exists():

        raise FileNotFoundError(
            f"Missing raw file: {path}"
        )

    with path.open(
        "r",
        encoding="utf-8"
    ) as f:

        return json.load(f)


def get_latest_observation(concept_data):

    observations = []

    for unit, values in concept_data.get(
        "units",
        {}
    ).items():

        if not isinstance(values, list):
            continue

        for obs in values:

            row = dict(obs)
            row["unit"] = unit

            observations.append(row)

    if not observations:
        return None

    observations.sort(
        key=lambda x: (
            x.get("filed", ""),
            x.get("end", ""),
            x.get("start", ""),
        ),
        reverse=True,
    )

    return observations[0]


def concept_contains_terms(
    concept_name,
    terms
):

    name = concept_name.lower()

    return all(
        term.lower() in name
        for term in terms
    )


def inspect_ticker(
    ticker,
    data
):

    print()
    print("=" * 80)
    print(f"{ticker} / {data.get('entityName')}")
    print("=" * 80)

    for metric, terms in SEARCH_TERMS.items():

        print()
        print(
            f"### {metric.upper()}"
        )

        candidates = []

        for namespace, facts in data.get(
            "facts",
            {}
        ).items():

            if not isinstance(facts, dict):
                continue

            for concept_name, concept_data in facts.items():

                if not concept_contains_terms(
                    concept_name,
                    terms
                ):
                    continue

                latest = get_latest_observation(
                    concept_data
                )

                if latest is None:
                    continue

                candidates.append(
                    {
                        "namespace": namespace,
                        "concept": concept_name,
                        "latest": latest,
                    }
                )

        candidates.sort(
            key=lambda x: (
                x["latest"].get(
                    "filed",
                    ""
                ),
                x["latest"].get(
                    "end",
                    ""
                ),
            ),
            reverse=True,
        )

        if not candidates:

            print(
                "[NONE]"
            )
            continue

        for candidate in candidates[:15]:

            obs = candidate["latest"]

            print(
                f"{candidate['namespace']}:"
                f"{candidate['concept']}"
            )

            print(
                f"  unit={obs.get('unit')}"
            )

            print(
                f"  start={obs.get('start')}"
            )

            print(
                f"  end={obs.get('end')}"
            )

            print(
                f"  filed={obs.get('filed')}"
            )

            print(
                f"  form={obs.get('form')}"
            )

            print(
                f"  fp={obs.get('fp')}"
            )

            print(
                f"  fy={obs.get('fy')}"
            )

            print(
                f"  frame={obs.get('frame')}"
            )

            print(
                f"  value={obs.get('val')}"
            )

            print()


def main():

    print(
        "=== SEC Concept Inspection ==="
    )

    for ticker in TICKERS:

        data = load_companyfacts(
            ticker
        )

        inspect_ticker(
            ticker,
            data
        )


if __name__ == "__main__":
    main()