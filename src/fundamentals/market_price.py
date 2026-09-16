import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


# ============================================================
# CONFIGURATION
# ============================================================

SCHEMA_VERSION = "market_price_v0.1"

PROCESSED_DIR = Path(
    "data/processed/market_price"
)

TIINGO_BASE_URL = (
    "https://api.tiingo.com/tiingo/daily"
)

ALPHA_VANTAGE_BASE_URL = (
    "https://www.alphavantage.co/query"
)

DEFAULT_MAX_PRICE_AGE_DAYS = 5

USER_AGENT = (
    "invest-briefing-chatgpt/0.1 "
    "chks7788@gmail.com"
)


# ============================================================
# BASIC HELPERS
# ============================================================

def _is_number(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
    )


def _date_string(value):
    if value is None:
        return None

    if isinstance(value, str):
        return value[:10]

    if isinstance(value, date):
        return value.isoformat()

    return str(value)[:10]


def _parse_date(value):
    value = _date_string(value)

    if not value:
        return None

    try:
        return datetime.strptime(
            value,
            "%Y-%m-%d",
        ).date()
    except ValueError:
        return None


def _today_utc():
    return datetime.now(
        timezone.utc
    ).date()


# ============================================================
# RESULT BUILDERS
# ============================================================

def build_unavailable_price(
    ticker,
    reason,
    attempts=None,
):
    return {
        "schema_version": SCHEMA_VERSION,
        "ticker": ticker,
        "status": "UNAVAILABLE",
        "price": None,
        "price_date": None,
        "currency": "USD",
        "source": None,
        "reason": reason,
        "attempts": attempts or [],
    }


def build_ok_price(
    ticker,
    price,
    price_date,
    source,
    currency="USD",
    open_price=None,
    high=None,
    low=None,
    close=None,
    volume=None,
):
    return {
        "schema_version": SCHEMA_VERSION,
        "ticker": ticker,
        "status": "OK",
        "price": float(price),
        "price_date": _date_string(price_date),
        "currency": currency,
        "source": source,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


# ============================================================
# HTTP
# ============================================================

def _http_get_json(
    url,
    headers=None,
    timeout=30,
):
    request_headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }

    if headers:
        request_headers.update(headers)

    request = Request(
        url,
        headers=request_headers,
        method="GET",
    )

    with urlopen(
        request,
        timeout=timeout,
    ) as response:

        status_code = response.getcode()

        raw = response.read()

    if status_code != 200:
        raise RuntimeError(
            f"HTTP status {status_code}"
        )

    try:
        return json.loads(
            raw.decode("utf-8")
        )
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "Response is not valid JSON."
        ) from exc


# ============================================================
# PRICE VALIDATION
# ============================================================

def validate_price_record(
    record,
    max_age_days=DEFAULT_MAX_PRICE_AGE_DAYS,
    reference_date=None,
):
    failures = []

    if not isinstance(record, dict):
        return [
            "record_not_dict"
        ]

    if record.get("status") != "OK":
        failures.append("status_not_ok")
        return failures

    price = record.get("price")

    if not _is_number(price):
        failures.append(
            "price_not_numeric"
        )
    elif price <= 0:
        failures.append(
            "price_not_positive"
        )

    price_date = _parse_date(
        record.get("price_date")
    )

    if price_date is None:
        failures.append(
            "price_date_invalid"
        )

    if price_date is not None:

        if reference_date is None:
            reference_date = _today_utc()

        age_days = (
            reference_date - price_date
        ).days

        if age_days < 0:
            failures.append(
                "price_date_in_future"
            )

        if age_days > max_age_days:
            failures.append(
                "price_too_old"
            )

    open_price = record.get("open")
    high = record.get("high")
    low = record.get("low")
    close = record.get("close")

    numeric_ohlc = [
        value
        for value in (
            open_price,
            high,
            low,
            close,
        )
        if value is not None
    ]

    for value in numeric_ohlc:

        if not _is_number(value):
            failures.append(
                "ohlc_non_numeric"
            )
            break

        if value < 0:
            failures.append(
                "ohlc_negative"
            )
            break

    if (
        _is_number(high)
        and _is_number(low)
        and high < low
    ):
        failures.append(
            "high_below_low"
        )

    return sorted(
        set(failures)
    )


# ============================================================
# TIINGO PROVIDER
# ============================================================

def fetch_tiingo_price(
    ticker,
    api_key=None,
    timeout=30,
):
    ticker = ticker.upper().strip()

    api_key = (
        api_key
        or os.getenv("TIINGO_API_KEY")
    )

    if not api_key:
        return {
            "status": "UNAVAILABLE",
            "source": "tiingo",
            "reason": (
                "TIINGO_API_KEY is not configured."
            ),
        }

    url = (
        f"{TIINGO_BASE_URL}/"
        f"{ticker}/prices?"
        + urlencode(
            {
                "token": api_key,
            }
        )
    )

    try:
        payload = _http_get_json(
            url,
            timeout=timeout,
        )

    except (
        HTTPError,
        URLError,
        TimeoutError,
        RuntimeError,
    ) as exc:

        return {
            "status": "UNAVAILABLE",
            "source": "tiingo",
            "reason": str(exc),
        }

    if not isinstance(
        payload,
        list,
    ):
        return {
            "status": "UNAVAILABLE",
            "source": "tiingo",
            "reason": (
                "Unexpected Tiingo "
                "response format."
            ),
        }

    if not payload:
        return {
            "status": "UNAVAILABLE",
            "source": "tiingo",
            "reason": (
                "Tiingo returned "
                "no price records."
            ),
        }

    latest = sorted(
        payload,
        key=lambda x: (
            _date_string(
                x.get("date")
            )
            or ""
        ),
        reverse=True,
    )[0]

    price = latest.get("close")

    if not _is_number(price):
        return {
            "status": "UNAVAILABLE",
            "source": "tiingo",
            "reason": (
                "Tiingo close price "
                "is missing or invalid."
            ),
        }

    record = build_ok_price(
        ticker=ticker,
        price=price,
        price_date=latest.get("date"),
        source="tiingo",
        currency="USD",
        open_price=latest.get("open"),
        high=latest.get("high"),
        low=latest.get("low"),
        close=latest.get("close"),
        volume=latest.get("volume"),
    )

    failures = validate_price_record(
        record
    )

    if failures:
        return {
            "status": "UNAVAILABLE",
            "source": "tiingo",
            "reason": (
                "Tiingo price "
                "failed validation."
            ),
            "validation_failures": failures,
        }

    return record


# ============================================================
# ALPHA VANTAGE PROVIDER
# ============================================================

def fetch_alpha_vantage_price(
    ticker,
    api_key=None,
    timeout=30,
):
    ticker = ticker.upper().strip()

    api_key = (
        api_key
        or os.getenv(
            "ALPHAVANTAGE_API_KEY"
        )
    )

    if not api_key:
        return {
            "status": "UNAVAILABLE",
            "source": "alpha_vantage",
            "reason": (
                "ALPHAVANTAGE_API_KEY "
                "is not configured."
            ),
        }

    params = {
        "function": "TIME_SERIES_DAILY",
        "symbol": ticker,
        "outputsize": "compact",
        "apikey": api_key,
    }

    url = (
        ALPHA_VANTAGE_BASE_URL
        + "?"
        + urlencode(params)
    )

    try:
        payload = _http_get_json(
            url,
            timeout=timeout,
        )

    except (
        HTTPError,
        URLError,
        TimeoutError,
        RuntimeError,
    ) as exc:

        return {
            "status": "UNAVAILABLE",
            "source": "alpha_vantage",
            "reason": str(exc),
        }

    if not isinstance(
        payload,
        dict,
    ):
        return {
            "status": "UNAVAILABLE",
            "source": "alpha_vantage",
            "reason": (
                "Unexpected Alpha Vantage "
                "response."
            ),
        }

    if (
        "Note" in payload
        or "Information" in payload
        or "Error Message" in payload
    ):
        message = (
            payload.get("Note")
            or payload.get("Information")
            or payload.get("Error Message")
        )

        return {
            "status": "UNAVAILABLE",
            "source": "alpha_vantage",
            "reason": str(message),
        }

    time_series = payload.get(
        "Time Series (Daily)"
    )

    if not isinstance(
        time_series,
        dict,
    ):
        return {
            "status": "UNAVAILABLE",
            "source": "alpha_vantage",
            "reason": (
                "Daily time series "
                "is missing."
            ),
        }

    if not time_series:
        return {
            "status": "UNAVAILABLE",
            "source": "alpha_vantage",
            "reason": (
                "Alpha Vantage returned "
                "no daily records."
            ),
        }

    latest_date = sorted(
        time_series.keys(),
        reverse=True,
    )[0]

    latest = time_series[
        latest_date
    ]

    def _float_field(name):
        value = latest.get(name)

        try:
            return float(value)
        except (
            TypeError,
            ValueError,
        ):
            return None

    record = build_ok_price(
        ticker=ticker,
        price=_float_field(
            "4. close"
        ),
        price_date=latest_date,
        source="alpha_vantage",
        currency="USD",
        open_price=_float_field(
            "1. open"
        ),
        high=_float_field(
            "2. high"
        ),
        low=_float_field(
            "3. low"
        ),
        close=_float_field(
            "4. close"
        ),
        volume=_float_field(
            "5. volume"
        ),
    )

    failures = validate_price_record(
        record
    )

    if failures:
        return {
            "status": "UNAVAILABLE",
            "source": "alpha_vantage",
            "reason": (
                "Alpha Vantage price "
                "failed validation."
            ),
            "validation_failures": failures,
        }

    return record


# ============================================================
# PRICE PROVIDER MANAGER
# ============================================================

def get_latest_price(
    ticker,
    max_age_days=DEFAULT_MAX_PRICE_AGE_DAYS,
):
    ticker = ticker.upper().strip()

    attempts = []

    providers = [
        (
            "tiingo",
            fetch_tiingo_price,
        ),
        (
            "alpha_vantage",
            fetch_alpha_vantage_price,
        ),
    ]

    for provider_name, provider in providers:

        result = provider(
            ticker
        )

        if result.get("status") == "OK":

            validation_failures = (
                validate_price_record(
                    result,
                    max_age_days=max_age_days,
                )
            )

            if not validation_failures:

                return result

            attempts.append(
                {
                    "provider": provider_name,
                    "status": "INVALID",
                    "reason": validation_failures,
                }
            )

            continue

        attempts.append(
            {
                "provider": provider_name,
                "status": "UNAVAILABLE",
                "reason": result.get(
                    "reason"
                ),
            }
        )

    return build_unavailable_price(
        ticker=ticker,
        reason=(
            "All configured price "
            "providers failed or "
            "returned invalid data."
        ),
        attempts=attempts,
    )


# ============================================================
# FILE HELPERS
# ============================================================

def save_price_data(
    ticker,
    price_data,
    processed_dir=PROCESSED_DIR,
):
    processed_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    path = (
        processed_dir
        / f"{ticker.upper()}_price.json"
    )

    with path.open(
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            price_data,
            f,
            ensure_ascii=False,
            indent=2,
        )

    return path


def fetch_and_save_price(
    ticker,
    processed_dir=PROCESSED_DIR,
):
    result = get_latest_price(
        ticker
    )

    output_path = save_price_data(
        ticker,
        result,
        processed_dir,
    )

    return {
        "ticker": ticker.upper(),
        "output_path": str(
            output_path
        ),
        "price": result,
    }


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":

    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Fetch latest US stock price "
            "with automatic provider fallback."
        )
    )

    parser.add_argument(
        "--ticker",
        required=True,
        help="Ticker symbol, e.g. NVDA",
    )

    args = parser.parse_args()

    result = fetch_and_save_price(
        args.ticker
    )

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        )
    )