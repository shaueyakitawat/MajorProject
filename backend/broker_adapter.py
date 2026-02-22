# Broker Adapter
# Lightweight adapter scaffold for market data fetching and normalization.
# No quantitative logic. Fetch + normalize + validate only.
# Not wired into run_pipeline() yet.

import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
import yfinance as yf


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _utc_iso_timestamp() -> str:
    """Return current UTC time as ISO 8601 string with Z suffix."""
    return datetime.utcnow().isoformat() + "Z"


def _parse_ist_datetime(value: str) -> datetime:
    """Parse IST datetime string in supported formats."""
    supported_formats = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"]
    for date_format in supported_formats:
        try:
            dt = datetime.strptime(value, date_format)
            return dt.replace(tzinfo=ZoneInfo("Asia/Kolkata"))
        except ValueError:
            continue
    raise ValueError(
        f"Invalid IST datetime format: '{value}'. Use 'YYYY-MM-DD HH:MM:SS'."
    )


def _normalize_dhan_candles(payload: dict) -> list[dict]:
    """
    Convert Dhan OHLC arrays to normalized candle dicts.

    Returns:
        list[dict]:
            {"timestamp": "<IST ISO>", "open": float, "high": float,
             "low": float, "close": float, "volume": int}
    """
    open_values = payload.get("open", [])
    high_values = payload.get("high", [])
    low_values = payload.get("low", [])
    close_values = payload.get("close", [])
    volume_values = payload.get("volume", [])
    ts_values = payload.get("timestamp", [])

    series_lengths = [
        len(open_values), len(high_values), len(low_values),
        len(close_values), len(volume_values), len(ts_values)
    ]

    if min(series_lengths, default=0) == 0:
        raise ValueError("Dhan intraday API returned empty candle arrays")

    if len(set(series_lengths)) != 1:
        raise ValueError(
            f"Dhan intraday arrays have inconsistent lengths: {series_lengths}"
        )

    candles = []
    ist_tz = ZoneInfo("Asia/Kolkata")
    for timestamp, open_px, high_px, low_px, close_px, volume in zip(
        ts_values, open_values, high_values, low_values, close_values, volume_values
    ):
        dt_ist = datetime.fromtimestamp(int(timestamp), tz=ist_tz)
        candles.append(
            {
                "timestamp": dt_ist.isoformat(),
                "open": _to_float_safe(open_px),
                "high": _to_float_safe(high_px),
                "low": _to_float_safe(low_px),
                "close": _to_float_safe(close_px),
                "volume": int(float(volume)),
            }
        )

    return candles


def fetch_intraday_candles_dhan(
    *,
    security_id: str,
    exchange_segment: str,
    instrument: str,
    interval_min: int,
    from_dt_ist: str,
    to_dt_ist: str,
    oi: bool = False,
) -> dict:
    """
    Fetch intraday candles from DhanHQ historical data API.
    """
    allowed_intervals = {1, 5, 15, 25, 60}
    if interval_min not in allowed_intervals:
        raise ValueError(
            f"Invalid interval_min={interval_min}. Allowed: {sorted(allowed_intervals)}"
        )

    from_dt = _parse_ist_datetime(from_dt_ist)
    to_dt = _parse_ist_datetime(to_dt_ist)
    if to_dt <= from_dt:
        raise ValueError("to_dt_ist must be greater than from_dt_ist")

    if (to_dt - from_dt) > timedelta(days=90):
        raise ValueError("Dhan intraday date range cannot exceed 90 days")

    access_token = os.getenv("DHAN_ACCESS_TOKEN", "").strip()
    if not access_token:
        raise ValueError("Missing DHAN_ACCESS_TOKEN environment variable")

    url = "https://api.dhan.co/v2/charts/intraday"
    headers = {
        "access-token": access_token,
        "Content-Type": "application/json",
    }
    request_body = {
        "securityId": str(security_id),
        "exchangeSegment": exchange_segment,
        "instrument": instrument,
        "interval": int(interval_min),
        "oi": bool(oi),
        "fromDate": from_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "toDate": to_dt.strftime("%Y-%m-%d %H:%M:%S"),
    }

    response = requests.post(url, headers=headers, json=request_body, timeout=30)
    try:
        response_json = response.json()
    except ValueError as e:
        raise ValueError(
            f"Dhan intraday API returned non-JSON response (status={response.status_code})"
        ) from e

    if response.status_code >= 400:
        raise ValueError(
            f"Dhan intraday API error (status={response.status_code}): {response_json}"
        )

    # Validate arrays are present and non-empty as required
    if not response_json.get("timestamp") or not response_json.get("close"):
        raise ValueError("Dhan intraday API returned empty arrays for requested range")

    return response_json


def _to_float_safe(value) -> float:
    """
    Safely convert a value to float.

    Args:
        value: Any scalar value to convert.

    Returns:
        float: Converted value.

    Raises:
        ValueError: If conversion fails or result is not finite.
    """
    try:
        result = float(value)
    except (TypeError, ValueError) as e:
        raise ValueError(f"Cannot convert value to float: {value!r}") from e

    if result != result:  # NaN check without importing math
        raise ValueError(f"Value converted to NaN: {value!r}")

    return result


# ---------------------------------------------------------------------------
# Fetch functions
# ---------------------------------------------------------------------------

def fetch_spot(*, provider: str = "yfinance", symbol: str) -> dict:
    """
    Fetch the latest spot price for a given symbol.

    Args:
        provider: Data provider identifier. Currently supports "yfinance".
        symbol: Ticker symbol (e.g. "^NSEI").

    Returns:
        dict: Raw spot payload with at minimum a "spot_price" key (float).

    Raises:
        ValueError: If provider is unsupported or spot price cannot be retrieved.
    """
    if provider == "yfinance":
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="1d")

        if hist.empty:
            raise ValueError(
                f"fetch_spot: No data returned from yfinance for symbol '{symbol}'."
            )

        spot_price = _to_float_safe(hist["Close"].iloc[-1])

        return {
            "spot_price": spot_price,
            "symbol": symbol,
            "provider": provider,
            "timestamp": _utc_iso_timestamp(),
        }

    if provider == "dhan":
        security_id = os.getenv("DHAN_SECURITY_ID", "13")
        exchange_segment = os.getenv("DHAN_EXCHANGE_SEGMENT", "IDX_I")
        instrument = os.getenv("DHAN_INSTRUMENT", "INDEX")
        interval_min = int(os.getenv("DHAN_INTERVAL_MIN", "1"))

        now_ist = datetime.now(ZoneInfo("Asia/Kolkata"))
        from_ist = now_ist - timedelta(days=5)
        raw = fetch_intraday_candles_dhan(
            security_id=security_id,
            exchange_segment=exchange_segment,
            instrument=instrument,
            interval_min=interval_min,
            from_dt_ist=from_ist.strftime("%Y-%m-%d %H:%M:%S"),
            to_dt_ist=now_ist.strftime("%Y-%m-%d %H:%M:%S"),
            oi=False,
        )
        candles = _normalize_dhan_candles(raw)
        latest_close = candles[-1]["close"]

        return {
            "spot_price": _to_float_safe(latest_close),
            "symbol": symbol,
            "provider": provider,
            "timestamp": _utc_iso_timestamp(),
            "candles": candles,
        }

    raise ValueError(
        f"fetch_spot: Unsupported provider '{provider}'. Supported: ['yfinance', 'dhan']."
    )


def fetch_option_chain(*, provider: str = "yfinance", symbol: str) -> dict:
    """
    Fetch the option chain for a given symbol.

    Args:
        provider: Data provider identifier. Currently supports "yfinance".
        symbol: Ticker symbol (e.g. "^NSEI").

    Returns:
        dict: Raw chain payload with an "option_chain" key (list of dicts).
              Returns an empty list if no option chain is available for the symbol.

    Raises:
        ValueError: If provider is unsupported.
    """
    if provider == "yfinance":
        ticker = yf.Ticker(symbol)

        try:
            expirations = ticker.options  # tuple of expiry date strings
        except Exception:
            expirations = ()

        chain_records = []

        if expirations:
            # Fetch only nearest expiry to keep payload minimal
            nearest_expiry = expirations[0]
            try:
                chain = ticker.option_chain(nearest_expiry)
                calls = chain.calls.to_dict(orient="records") if chain.calls is not None else []
                puts = chain.puts.to_dict(orient="records") if chain.puts is not None else []
                chain_records = calls + puts
            except Exception:
                chain_records = []

        return {
            "option_chain": chain_records,
            "symbol": symbol,
            "provider": provider,
            "timestamp": _utc_iso_timestamp(),
        }

    if provider == "dhan":
        # Placeholder for future strike-wise integration.
        # Keep schema stable for normalize_broker_payload.
        return {
            "option_chain": [],
            "symbol": symbol,
            "provider": provider,
            "timestamp": _utc_iso_timestamp(),
        }

    raise ValueError(
        f"fetch_option_chain: Unsupported provider '{provider}'. Supported: ['yfinance', 'dhan']."
    )


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

def normalize_broker_payload(*, spot_payload: dict, chain_payload: dict) -> dict:
    """
    Normalize raw broker payloads into a standardized market data dict.

    Args:
        spot_payload: Output from fetch_spot (must contain "spot_price").
        chain_payload: Output from fetch_option_chain (must contain "option_chain").

    Returns:
        dict: Normalized payload with exact schema:
            {
                "spot_price": float,
                "option_chain": list,
                "timestamp": str   # UTC ISO with Z suffix
            }

    Raises:
        ValueError: If required fields are missing or cannot be normalized.
    """
    # --- Normalize spot_price ---
    if "spot_price" not in spot_payload:
        raise ValueError(
            "normalize_broker_payload: 'spot_price' key missing from spot_payload."
        )

    spot_price = _to_float_safe(spot_payload["spot_price"])

    if spot_price <= 0:
        raise ValueError(
            f"normalize_broker_payload: spot_price must be positive, got {spot_price}."
        )

    # --- Normalize option_chain ---
    raw_chain = chain_payload.get("option_chain", None)

    if raw_chain is None:
        option_chain = []
    elif not isinstance(raw_chain, list):
        # Attempt coercion — if it's iterable, convert; otherwise default to empty
        try:
            option_chain = list(raw_chain)
        except TypeError:
            option_chain = []
    else:
        option_chain = raw_chain

    # Ensure every element is JSON-serializable (drop non-dict or unconvertible entries)
    sanitized_chain = []
    for entry in option_chain:
        if isinstance(entry, dict):
            sanitized_chain.append(entry)

    # --- Timestamp ---
    timestamp = _utc_iso_timestamp()

    return {
        "spot_price": spot_price,
        "option_chain": sanitized_chain,
        "timestamp": timestamp,
    }
