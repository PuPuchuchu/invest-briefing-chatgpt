import json
from pathlib import Path
from datetime import date


TICKER = "AVGO"

RAW_FILE = Path(
    f"data/raw/sec/{TICKER}_companyfacts.json"
)

TARGET_CONCEPTS = {
    "StockholdersEquity",
    "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
}


def load_companyfacts():
    if not RAW_FILE.exists():
        raise FileNotFoundError(
            f"SEC raw file not found: {RAW_FILE}"
        )

    with RAW_FILE.open("r", encoding="utf-8") as file:
        return json.load(file)


def main():
    data = load_companyfacts()

    facts = data.get("facts", {})

    print("=" * 120)
    print("AVGO STOCKHOLDERS EQUITY DIAGNOSTIC")
    print("=" * 120)

    print(f"Entity: {data.get('entityName')}")
    print(f"CIK: {data.get('cik')}")
    print(f"Raw file: {RAW_FILE}")

    print("=" * 120)

    found_count = 0

    for namespace, namespace_facts in facts.items():

        for concept_name, concept_data in namespace_facts.items():

            if concept_name not in TARGET_CONCEPTS:
                continue

            found_count += 1

            print()
            print("-" * 120)
            print(f"Namespace: {namespace}")
            print(f"Concept: {concept_name}")
            print(f"Label: {concept_data.get('label')}")
            print(f"Description: {concept_data.get('description')}")

            units = concept_data.get("units", {})

            for unit_name, observations in units.items():

                print()
                print(f"Unit: {unit_name}")
                print(f"Observation count: {len(observations)}")

                sorted_observations = sorted(
                    observations,
                    key=lambda item: (
                        item.get("filed", ""),
                        item.get("end", ""),
                    ),
                    reverse=True,
                )

                for index, observation in enumerate(
                    sorted_observations,
                    start=1,
                ):

                    print(
                        f"{index:03d} | "
                        f"start={observation.get('start')} | "
                        f"end={observation.get('end')} | "
                        f"filed={observation.get('filed')} | "
                        f"form={observation.get('form')} | "
                        f"fy={observation.get('fy')} | "
                        f"fp={observation.get('fp')} | "
                        f"frame={observation.get('frame')} | "
                        f"accn={observation.get('accn')} | "
                        f"value={observation.get('val')}"
                    )

    print()
    print("=" * 120)
    print(f"Matching concepts found: {found_count}")
    print("=" * 120)


if __name__ == "__main__":
    main()