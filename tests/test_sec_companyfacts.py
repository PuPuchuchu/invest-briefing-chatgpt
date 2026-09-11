import json
import gzip
import zlib
from pathlib import Path
from urllib.request import Request, urlopen


USER_AGENT = "stock-master-sec-test/0.1 chks7788@gmail.com"

TICKERS = {
    "MSFT": "0000789019",
    "NVDA": "0001045810",
    "JPM": "0000019617",
    "LLY": "0000059478",
    "PLTR": "0001321655",
}

RAW_DIR = Path("data/raw/sec")


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

        text = raw_data.decode("utf-8")

        return json.loads(text)


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


def main():

    RAW_DIR.mkdir(
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

            data = fetch_json(url)

            validate_companyfacts(data)

            output_file = (
                RAW_DIR /
                f"{ticker}_companyfacts.json"
            )

            with output_file.open(
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
                f"[PASS] HTTP request: {ticker}"
            )

            print(
                f"[PASS] JSON structure: {ticker}"
            )

            print(
                f"[PASS] Raw cache written: "
                f"{output_file}"
            )

            print(
                f"Entity: "
                f"{data.get('entityName')}"
            )

            print(
                f"Facts namespaces: "
                f"{list(data['facts'].keys())}"
            )

            success_count += 1

        except Exception as e:

            print(
                f"[FAIL] {ticker}: "
                f"{type(e).__name__}: {e}"
            )

        print("-" * 60)

    print()
    print(
        f"Result: "
        f"{success_count}/{len(TICKERS)} tickers passed"
    )

    if success_count != len(TICKERS):

        raise RuntimeError(
            "SEC Company Facts test failed"
        )

    print()
    print(
        "[PASS] All SEC Company Facts tests passed."
    )


if __name__ == "__main__":
    main()