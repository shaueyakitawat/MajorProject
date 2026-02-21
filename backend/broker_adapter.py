# Broker Adapter
# Lightweight adapter scaffold for market data fetching and normalization.
# No quantitative logic. Fetch + normalize + validate only.
# Not wired into run_pipeline() yet.

from datetime import datetime
import yfinance as yf


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _utc_iso_timestamp() -> str:
    """Return current UTC time as ISO 8601 string with Z suffix."""
    return datetime.utcnow().isoformat() + "Z"


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

    raise ValueError(
        f"fetch_spot: Unsupported provider '{provider}'. Supported: ['yfinance']."
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

    raise ValueError(
        f"fetch_option_chain: Unsupported provider '{provider}'. Supported: ['yfinance']."
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
