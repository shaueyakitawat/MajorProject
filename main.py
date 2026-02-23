"""
================================================================================
QUANT PIPELINE FINALIZED — DO NOT MODIFY CORE LOGIC.
Future changes should focus only on API formatting or frontend integration.
================================================================================
"""

# Standard library imports
import json
import logging
import math
import re
import time
from datetime import datetime, timezone

# Third-party imports
import dateutil.parser
from fastapi import FastAPI, HTTPException, Query

# Backend module imports
from backend.services.data_service import fetch_nifty_data, compute_log_returns
from backend.services.volatility_service import forecast_volatility
from backend.services.pricing_service import black_scholes_price
from backend.services.mispricing_service import detect_mispricing
from backend.services.regime_service import classify_volatility_regime
from backend.services.strategy_service import generate_strategy
from backend.broker_adapter import fetch_spot, fetch_option_chain, normalize_broker_payload
from backend.infrastructure.timeframe_config import (
    validate_timeframe,
    get_default_timeframe_for_horizon,
    get_annualization_factor
)
from backend.infrastructure.timeframe_adapter import normalize_timeframe_dataframe
from backend.infrastructure.annualization_engine import apply_dynamic_annualization


# ========== CONFIG ==========

app = FastAPI(
    openapi_tags=[
        {
            "name": "Market Data",
            "description": "Endpoints for fetching raw market data."
        },
        {
            "name": "Pipeline",
            "description": "Quantitative pipeline stages: log returns, volatility forecast, pricing, mispricing, regime, and strategy."
        },
        {
            "name": "System",
            "description": "Health checks and operational monitoring endpoints."
        }
    ]
)

# Application identity constants (used for observability and metrics)
APP_NAME: str = "options-mispricing-backend"
APP_VERSION: str = "1.1.0"

# Configure structured logger
logger = logging.getLogger("api")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setLevel(logging.INFO)
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)


# In-memory metrics store
METRICS: dict = {
    "request_count": 0,
    "per_endpoint": {},
    "last_status": None,
    "last_error": None,
    "last_execution_time_ms": None,
    "last_timestamp": None
}


def record_request(endpoint: str) -> None:
    """Increment global and per-endpoint request counters."""
    METRICS["request_count"] += 1
    METRICS["per_endpoint"][endpoint] = METRICS["per_endpoint"].get(endpoint, 0) + 1


def record_result(
    endpoint: str,
    status: str,
    execution_time_ms: int | None,
    error_message: str | None
) -> None:
    """Update last-result fields in the metrics store."""
    METRICS["last_status"] = status
    METRICS["last_error"] = error_message
    METRICS["last_execution_time_ms"] = execution_time_ms
    METRICS["last_timestamp"] = _utc_iso_timestamp()


# ========== HELPERS ==========

def log_event(event: dict) -> None:
    """
    Emit a single structured JSON log line.

    Args:
        event: Metadata dict. Must not contain large payloads.
    """
    event.setdefault("timestamp", _utc_iso_timestamp())
    logger.info(json.dumps(event, ensure_ascii=False))


def _utc_iso_timestamp():
    """Generate UTC ISO timestamp with Z suffix."""
    return datetime.utcnow().isoformat() + "Z"


def log_endpoint_result(endpoint: str, health: str, duration_ms: int, error_message: str | None = None) -> None:
    """Log structured endpoint execution result with consistent format."""
    payload = {
        "timestamp": _utc_iso_timestamp(),
        "endpoint": endpoint,
        "pipeline_health": health,
        "execution_time_ms": duration_ms
    }
    if error_message is not None:
        payload["error_message"] = error_message
    log_event(payload)


def create_response(data):
    """Wrap data in the standard success envelope (no meta field)."""
    return {
        "status": "success",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "data": data
    }


def build_success_response(payload: dict, *, meta: dict | None = None) -> dict:
    """
    Wrap a payload dict in the standard success envelope.

    Args:
        payload: JSON-serializable endpoint data.
        meta: Optional metadata dict (e.g. execution_time_ms). Included in
              the response only when provided.

    Returns:
        dict: {"status": "success", "timestamp": str, "data": payload}
              with an additional "meta" key when meta is not None.
    """
    response = {
        "status": "success",
        "timestamp": _utc_iso_timestamp(),
        "data": payload
    }
    if meta is not None:
        response["meta"] = meta
    return response


def error_json(message: str, status_code: int = 500) -> dict:
    """
    Return a structured error envelope.

    Args:
        message: Human-readable error description.
        status_code: HTTP status code hint (not applied here; caller raises HTTPException).

    Returns:
        dict: {"status": "error", "timestamp": str, "error": message}
    """
    raise HTTPException(
        status_code=status_code,
        detail={
            "status": "error",
            "timestamp": _utc_iso_timestamp(),
            "error": message
        }
    )


def validate_symbol(symbol: str) -> str:
    """
    Validate and normalize a market symbol string.

    Args:
        symbol: Raw symbol string from query parameter.

    Returns:
        str: Uppercased, stripped symbol.

    Raises:
        ValueError: If symbol contains invalid characters.
    """
    symbol = symbol.strip().upper()
    if not re.fullmatch(r"[A-Z0-9\-\^]+", symbol):
        raise ValueError(
            f"Invalid symbol format: '{symbol}'. "
            "Only uppercase letters, digits, '-', and '^' are allowed."
        )
    return symbol


def get_live_market_data(symbol: str = "NIFTY") -> dict:
    """
    Fetch and normalize live market data via broker_adapter.

    Args:
        symbol: Ticker symbol to fetch (default: "NIFTY").

    Returns:
        dict: Normalized payload with shape:
            {"spot_price": float, "option_chain": list, "timestamp": str}
    """
    spot = fetch_spot(symbol=symbol)
    chain = fetch_option_chain(symbol=symbol)
    return normalize_broker_payload(spot_payload=spot, chain_payload=chain)


def get_live_input(symbol: str, timeframe: str) -> dict:
    """
    Fetch and return normalized live market data for pipeline input.

    Args:
        symbol: Ticker symbol (e.g., "NIFTY", "^NSEI").
        timeframe: Timeframe context for the request (e.g., "5m", "daily").
            Used for logging only; broker APIs return latest available data.

    Returns:
        dict: Normalized payload ready for ``run_pipeline`` input_data.
            Shape: {"spot_price": float, "option_chain": list, "timestamp": str}

    Raises:
        ValueError: If broker API returns invalid or malformed data.
    """
    spot = fetch_spot(symbol=symbol)
    chain = fetch_option_chain(symbol=symbol)
    return normalize_broker_payload(spot_payload=spot, chain_payload=chain)


def validate_live_input_data(input_data: dict) -> dict | None:
    """
    Validate broker input_data before feeding into pipeline.
    
    This function performs safe validation without raising exceptions.
    If validation fails, returns None to trigger fallback logic.
    
    Validations:
        1. spot_price exists and is positive
        2. option_chain exists and is a non-empty list
        3. At least one option has numeric bid and ask
        4. At least one option has parseable expiry
    
    Args:
        input_data: Broker data dict with shape:
            {"spot_price": float, "option_chain": list, "timestamp": str}
    
    Returns:
        dict: Validated input_data if all checks pass
        None: If any validation fails (triggers fallback logic)
    
    Example:
        >>> input_data = get_live_input(symbol="^NSEI", timeframe="5m")
        >>> validated = validate_live_input_data(input_data)
    """
    if not isinstance(input_data, dict):
        log_event({
            "timestamp": _utc_iso_timestamp(),
            "event": "live_input_validation_failed",
            "reason": "input_data is not a dict",
            "type": type(input_data).__name__,
            "fallback": "using historical data"
        })
        return None
    
    # Validation 1: spot_price exists and is positive
    if "spot_price" not in input_data:
        log_event({
            "timestamp": _utc_iso_timestamp(),
            "event": "live_input_validation_failed",
            "reason": "missing spot_price key",
            "keys_present": list(input_data.keys()),
            "fallback": "using historical data"
        })
        return None
    
    try:
        spot_price = float(input_data["spot_price"])
        if spot_price <= 0:
            log_event({
                "timestamp": _utc_iso_timestamp(),
                "event": "live_input_validation_failed",
                "reason": "spot_price not positive",
                "spot_price": spot_price,
                "fallback": "using historical data"
            })
            return None
    except (TypeError, ValueError) as e:
        log_event({
            "timestamp": _utc_iso_timestamp(),
            "event": "live_input_validation_failed",
            "reason": "spot_price not numeric",
            "spot_price_raw": input_data.get("spot_price"),
            "error": str(e),
            "fallback": "using historical data"
        })
        return None
    
    # Validation 2: option_chain exists and is non-empty list
    if "option_chain" not in input_data:
        log_event({
            "timestamp": _utc_iso_timestamp(),
            "event": "live_input_validation_failed",
            "reason": "missing option_chain key",
            "keys_present": list(input_data.keys()),
            "fallback": "using historical data"
        })
        return None
    
    option_chain = input_data["option_chain"]
    if not isinstance(option_chain, list):
        log_event({
            "timestamp": _utc_iso_timestamp(),
            "event": "live_input_validation_failed",
            "reason": "option_chain is not a list",
            "type": type(option_chain).__name__,
            "fallback": "using historical data"
        })
        return None
    
    if len(option_chain) == 0:
        log_event({
            "timestamp": _utc_iso_timestamp(),
            "event": "live_input_validation_failed",
            "reason": "option_chain is empty",
            "fallback": "using historical data"
        })
        return None
    
    # Validation 3: At least one option has numeric bid and ask
    has_valid_pricing = False
    for opt in option_chain:
        if not isinstance(opt, dict):
            continue
        
        # Check various field names for bid/ask
        bid = opt.get("bid") or opt.get("bidPrice")
        ask = opt.get("ask") or opt.get("askPrice")
        
        if bid is not None and ask is not None:
            try:
                if float(bid) > 0 and float(ask) > 0:
                    has_valid_pricing = True
                    break
            except (TypeError, ValueError):
                continue

    if not has_valid_pricing:
        log_event({
            "timestamp": _utc_iso_timestamp(),
            "event": "live_input_validation_failed",
            "reason": "no options with valid numeric bid/ask found",
            "option_chain_length": len(option_chain),
            "fallback": "using historical data"
        })
        return None
    
    # Validation 4: At least one option has parseable expiry
    has_parseable_expiry = False
    for opt in option_chain:
        if not isinstance(opt, dict):
            continue
        
        expiry_fields = ["expiration", "expirationDate", "expiry", "expiryDate", "lastExpiration"]
        for field in expiry_fields:
            if field in opt and opt[field] is not None:
                expiry_value = opt[field]
                if isinstance(expiry_value, (str, int, float)):
                    has_parseable_expiry = True
                    break
        
        if has_parseable_expiry:
            break
        
        # Also check contractSymbol for embedded date
        contract_symbol = opt.get("contractSymbol", "")
        if isinstance(contract_symbol, str) and re.search(r'\d{6}', contract_symbol):
            has_parseable_expiry = True
            break
    
    if not has_parseable_expiry:
        log_event({
            "timestamp": _utc_iso_timestamp(),
            "event": "live_input_validation_warning",
            "reason": "no parseable expiry found in option_chain",
            "option_chain_length": len(option_chain),
            "note": "will use fallback expiry (0.1 years)"
        })
        # Don't fail validation - expiry has fallback logic
    
    log_event({
        "timestamp": _utc_iso_timestamp(),
        "event": "live_input_validation_passed",
        "spot_price": spot_price,
        "option_chain_length": len(option_chain),
        "has_parseable_expiry": has_parseable_expiry
    })
    
    return input_data


def parse_option_expiry(raw_expiry) -> datetime | None:
    """
    Parse option expiry into UTC datetime with resilient error handling.
    
    This function uses python-dateutil parser for maximum flexibility and
    never raises exceptions. Supports multiple input formats.
    
    Args:
        raw_expiry: Expiry value in various formats:
            - str: ISO date, common date formats, or YYMMDD format
            - int/float: Unix timestamp
            - None: Returns None
    
    Returns:
        datetime: UTC timezone-aware datetime object
        None: If parsing fails or input is None
    
    Example:
        >>> expiry = parse_option_expiry("2026-03-27")
        >>> expiry = parse_option_expiry("240327")  # YYMMDD
        >>> expiry = parse_option_expiry(1711497600)  # Unix timestamp
    """
    if raw_expiry is None:
        return None
    
    try:
        if isinstance(raw_expiry, str):
            # Try python-dateutil parser (handles most formats)
            try:
                expiry_dt = dateutil.parser.parse(raw_expiry)
                # Ensure timezone-aware (assume UTC if naive)
                if expiry_dt.tzinfo is None:
                    expiry_dt = expiry_dt.replace(tzinfo=timezone.utc)
                return expiry_dt
            except (ImportError, ValueError, TypeError):
                pass
            
            # Fallback to manual parsing for common formats
            for date_format in ["%Y-%m-%d", "%Y%m%d", "%d-%m-%Y", "%m/%d/%Y", "%Y/%m/%d"]:
                try:
                    expiry_dt = datetime.strptime(raw_expiry, date_format)
                    return expiry_dt.replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
            
            # Try YYMMDD format (common in option symbols like "NIFTY240229C23000")
            if len(raw_expiry) == 6 and raw_expiry.isdigit():
                try:
                    year = int("20" + raw_expiry[0:2])
                    month = int(raw_expiry[2:4])
                    day = int(raw_expiry[4:6])
                    return datetime(year, month, day, tzinfo=timezone.utc)
                except (ValueError, TypeError):
                    pass
        
        elif isinstance(raw_expiry, (int, float)):
            try:
                return datetime.fromtimestamp(raw_expiry, tz=timezone.utc)
            except (ValueError, OSError, OverflowError):
                pass
    
    except Exception:
        pass

    return None


def sanitize_volatility(vol: float, fallback_safe_volatility: float = 0.15) -> float:
    """
    Apply sanity filters to volatility with strict bounds.
    
    This function ensures volatility is within reasonable bounds after
    EGARCH forecasting and annualization. Handles edge cases like NaN/inf.
    
    Args:
        vol: Raw volatility value from EGARCH + annualization
        fallback_safe_volatility: Fallback value if vol is NaN/infinite (default: 0.15)
    
    Returns:
        float: Sanitized volatility value within [0.01, 2.0] bounds
    
    Rules:
        - Floor: 0.01 (1%)
        - Cap: 2.0 (200%)
        - NaN/inf: Returns fallback_safe_volatility
    
    Example:
        >>> sanitize_volatility(0.25)  # Returns 0.25 (valid)
        >>> sanitize_volatility(-0.05)  # Returns 0.01 (floor)
        >>> sanitize_volatility(3.5)  # Returns 2.0 (cap)
        >>> sanitize_volatility(float('nan'))  # Returns 0.15 (fallback)
    """
    if not math.isfinite(vol):
        return fallback_safe_volatility
    if vol < 0.01:
        return 0.01
    if vol > 2.0:
        return 2.0
    return vol


def select_atm_option(option_chain: list, spot: float) -> dict | None:
    """
    Select the at-the-money (ATM) call option from option chain.
    
    This function filters and selects the best ATM call option based on:
    - Valid bid and ask prices (both must be present and numeric)
    - Non-expired contracts
    - Strike price closest to spot
    
    Args:
        option_chain: List of option contracts (dicts)
        spot: Current spot price (float)
    
    Returns:
        dict: Selected ATM option contract with keys:
            - "strike": float
            - "bid": float
            - "ask": float
            - "expiry": str | int | float | None (if available)
        None: If no valid contract found
    
    Example:
        >>> atm = select_atm_option(option_chain, spot=23500.0)
        >>> if atm:
        >>>     mid_price = (atm["bid"] + atm["ask"]) / 2.0
    """
    if not isinstance(option_chain, list) or len(option_chain) == 0:
        return None
    
    # Step 1: Filter for CALL options
    call_options = []
    
    for opt in option_chain:
        if not isinstance(opt, dict):
            continue
        
        # Method 1: Check contractSymbol for 'C' indicator (e.g., "NIFTY240229C23000")
        contract_symbol = opt.get("contractSymbol", "")
        if isinstance(contract_symbol, str) and "C" in contract_symbol.upper():
            # Additional validation: typically format is like "TICKER[DATE]C[STRIKE]"
            # The 'C' should not be part of ticker name, look for pattern with digits
            if any(char.isdigit() for char in contract_symbol):
                call_options.append(opt)
                continue
        
        # Method 2: Check explicit type field
        opt_type = opt.get("type", "").lower() or opt.get("optionType", "").lower()
        if opt_type == "call":
            call_options.append(opt)
    
    if not call_options:
        return None
    
    # Step 2: Filter for contracts with valid bid/ask and non-expired
    now_utc = datetime.now(timezone.utc)
    valid_contracts = []
    
    for opt in call_options:
        strike = opt.get("strike") or opt.get("strikePrice")
        if strike is None:
            continue
        try:
            strike = float(strike)
        except (TypeError, ValueError):
            continue

        bid = opt.get("bid") or opt.get("bidPrice")
        ask = opt.get("ask") or opt.get("askPrice")
        if bid is None or ask is None:
            continue
        try:
            bid = float(bid)
            ask = float(ask)
        except (TypeError, ValueError):
            continue

        # Validate bid/ask are positive and spread is not inverted
        if bid <= 0 or ask <= 0 or bid > ask:
            continue

        # Check if contract is expired
        is_expired = False
        expiry_value = None
        expiry_fields = ["expiration", "expirationDate", "expiry", "expiryDate", "lastExpiration"]
        for field in expiry_fields:
            if field in opt and opt[field] is not None:
                expiry_value = opt[field]
                break
        expiry_dt = parse_option_expiry(expiry_value)
        if expiry_dt is not None and expiry_dt < now_utc:
            is_expired = True
        if is_expired:
            continue

        valid_contracts.append({
            "strike": strike,
            "bid": bid,
            "ask": ask,
            "expiry": expiry_value,
            "original": opt
        })
    
    if not valid_contracts:
        return None
    
    # Step 3: Select strike closest to spot (ATM)
    # GUARDRAIL: Ensure closest strike selection is accurate
    min_distance = float('inf')
    atm_contract = None
    
    for contract in valid_contracts:
        distance = abs(contract["strike"] - spot)
        if distance < min_distance:
            min_distance = distance
            atm_contract = contract
    
    if atm_contract is None:
        return None

    # Reject if ATM strike is more than 10% from spot (data quality guard)
    strike_deviation = abs(atm_contract["strike"] - spot) / spot
    if strike_deviation > 0.10:
        return None

    return {
        "strike": atm_contract["strike"],
        "bid": atm_contract["bid"],
        "ask": atm_contract["ask"],
        "expiry": atm_contract["expiry"]
    }


# Reusable Swagger response examples
SUCCESS_EXAMPLE = {
    "status": "success",
    "timestamp": "2026-01-01T10:00:00Z",
    "data": {}
}

ERROR_EXAMPLE = {
    "status": "error",
    "message": "Internal server error",
    "timestamp": "2026-01-01T10:00:00Z"
}

_RESPONSES = {
    200: {
        "description": "Successful response",
        "content": {
            "application/json": {
                "example": SUCCESS_EXAMPLE
            }
        }
    },
    500: {
        "description": "Error response",
        "content": {
            "application/json": {
                "example": ERROR_EXAMPLE
            }
        }
    }
}


# ========== PIPELINE LOOKUP CONSTANTS ==========
# Defined at module level so they are built once, not on every run_pipeline() call.

_REGIME_SCORE: dict[str, int] = {
    "LOW_VOL": 1, "NORMAL_VOL": 2, "HIGH_VOL": 3, "EXTREME_VOL": 4
}
_STRATEGY_STRENGTH_DEGRADE: dict[str, str] = {
    "STRONG": "MODERATE", "MODERATE": "WEAK"
}
_VOL_DIRECTION: dict[str, str] = {
    "EXPANDING_VOL": "EXPANDING", "CONTRACTING_VOL": "CONTRACTING"
}
_VOLATILITY_FOCUS: dict = {
    "day_trader": "short_memory",
    "positional":  "medium_memory",
    "long_term":   "long_memory",
    None:          "standard",
}
_HORIZON_META: dict = {
    "day_trader": ("HIGH_RISK",     0.85),
    "positional":  ("MODERATE_RISK", 0.60),
    "long_term":   ("LOW_RISK",      0.35),
}
_RISK_TAG: dict[str, str] = {
    "EXTREME_VOL": "HIGH_RISK", "HIGH_VOL": "ELEVATED_RISK", "LOW_VOL": "LOW_RISK"
}
_MARKET_BIAS: dict[str, str] = {
    "overpriced": "SELL_BIAS", "underpriced": "BUY_BIAS"
}
_SIGNAL_DIR: dict[str, str] = {
    "BUY_BIAS": "LONG_SIGNAL", "SELL_BIAS": "SHORT_SIGNAL"
}
_STRATEGY_INTENT: dict[str, str] = {
    "LONG_SIGNAL": "ENTER_LONG_VOL", "SHORT_SIGNAL": "ENTER_SHORT_VOL"
}
_EXECUTION_PROFILE: dict[str, str] = {
    "HIGH": "AGGRESSIVE", "MEDIUM": "BALANCED"
}
_DASHBOARD_COLOR: dict[str, str] = {
    "BUY_BIAS": "GREEN", "SELL_BIAS": "RED"
}


# ========== PIPELINE ==========

def run_pipeline(input_data: dict = None, symbol: str = "NIFTY", trading_horizon: str = None, timeframe: str = "daily"):
    """
    Execute the complete quantitative pipeline.

    Args:
        input_data: Optional normalized market data dict from broker_adapter
            (shape: {"spot_price": float, "option_chain": list, "timestamp": str}).
            When provided, uses live spot_price and stores option_chain for later use.
            Historical candles are still fetched for EGARCH volatility forecasting.
            When None, fetches all data internally via data_service (yfinance).
        symbol: Ticker symbol hint for future symbol-aware data fetching.
            Accepted and stored for forward-compatibility; data_service currently
            defaults to NIFTY 50. Default: "NIFTY".
        trading_horizon: Optional trading horizon classification for volatility interpretation.
            Allowed values: "day_trader", "positional", "long_term".
            When None, uses default interpretation. Default: None.
        timeframe: Timeframe for analysis. Default: "daily".
            Supported: "1m", "5m", "15m", "1h", "daily", "weekly".
            When None, defaults based on trading_horizon.

    Returns:
        dict: Complete analytics results with clean structure
    """
    # Timeframe handling: default based on horizon if None
    if timeframe is None:
        timeframe = get_default_timeframe_for_horizon(trading_horizon)
    
    # Validate timeframe
    timeframe = validate_timeframe(timeframe)
    
    # Validate trading_horizon parameter
    allowed_horizons = ["day_trader", "positional", "long_term", None]
    if trading_horizon not in allowed_horizons:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid trading_horizon: '{trading_horizon}'. Allowed values: {[h for h in allowed_horizons if h is not None]}"
        )
    
    # One timestamp shared across all log_event calls in this request
    start_time = time.perf_counter()
    request_ts = _utc_iso_timestamp()

    provider_used = "live" if input_data is not None else "historical"
    data_source_live = input_data is not None
    
    # Step 1: Fetch and prepare data
    broker_spot_price = None
    broker_option_chain = None
    broker_data_healthy = True
    input_data_provided = input_data is not None

    if input_data is not None:
        validated_input = validate_live_input_data(input_data)

        if validated_input is not None:
            broker_spot_price = float(validated_input["spot_price"])
            broker_option_chain = validated_input["option_chain"]
        else:
            broker_data_healthy = False
            log_event({
                "timestamp": request_ts,
                "event": "broker_data_validation_failed",
                "action": "falling_back_to_historical_data",
                "symbol": symbol,
                "timeframe": timeframe,
                "provider_used": "historical",
                "data_source_live": False
            })
            input_data = None

    if input_data_provided and broker_data_healthy:
        live_data_health = "HEALTHY"
    elif input_data_provided and not broker_data_healthy:
        live_data_health = "DEGRADED"
    else:
        live_data_health = "NOT_APPLICABLE"
    
    # Check cache (key = symbol + timeframe) before expensive data operations
    cache_key = f"{symbol}_{timeframe}"
    current_time = time.perf_counter()

    cache_entry = run_pipeline.cache.get(cache_key)
    cache_hit = False

    if cache_entry is not None:
        cached_time = cache_entry.get("timestamp", 0)
        time_elapsed = current_time - cached_time

        if time_elapsed < run_pipeline.cache_ttl_seconds:
            data = cache_entry["data"]
            data_with_returns = cache_entry["data_with_returns"]
            cache_hit = True

    if not cache_hit:
        # Historical candles always required for EGARCH, even when live spot is available
        data = fetch_nifty_data(symbol=symbol, timeframe=timeframe)
        data = normalize_timeframe_dataframe(data, timeframe)
        data_with_returns = compute_log_returns(data)

        run_pipeline.cache[cache_key] = {
            "data": data,
            "data_with_returns": data_with_returns,
            "timestamp": current_time
        }
    
    # Validation: Ensure returns series is not empty
    if data_with_returns.empty or "log_return" not in data_with_returns.columns:
        raise HTTPException(
            status_code=500,
            detail="Data processing failed: insufficient data for volatility forecast"
        )
    
    returns_series = data_with_returns["log_return"]
    if len(returns_series) < 2:
        raise HTTPException(
            status_code=500,
            detail="Insufficient return data: need at least 2 data points for volatility forecast"
        )
    
    # EGARCH(1,1) requires ≥100 observations for stable estimation
    if len(returns_series) < 100:
        raise HTTPException(
            status_code=500,
            detail=f"Insufficient data for EGARCH: {len(returns_series)} points. Minimum 100 required for stable estimation."
        )

    if returns_series.isna().any():
        raise HTTPException(
            status_code=500,
            detail="Returns contain NaN values. Cannot compute EGARCH volatility forecast."
        )
    
    if not returns_series.apply(lambda x: math.isfinite(x)).all():
        raise HTTPException(
            status_code=500,
            detail="Returns contain infinite values. Cannot compute EGARCH volatility forecast."
        )
    
    # Step 2: Forecast volatility
    vol_forecast = forecast_volatility(returns_series)

    # Annualize to target timeframe
    vol_forecast = apply_dynamic_annualization(vol_forecast, timeframe)
    
    # Validation: Ensure volatility is valid type
    if not isinstance(vol_forecast, (int, float)):
        raise HTTPException(
            status_code=500,
            detail=f"Invalid volatility forecast type: {type(vol_forecast)}. Must be numeric."
        )

    # Guard: isinstance passes for float('nan') and float('inf') — check finiteness explicitly
    if not math.isfinite(vol_forecast):
        raise HTTPException(
            status_code=500,
            detail=f"Volatility forecast is not finite: {vol_forecast}. Cannot proceed with pipeline."
        )

    # Normalize volatility to decimal format if needed
    if vol_forecast > 1:
        vol_forecast = vol_forecast / 100
    
    # Clamp to [0.01, 2.0]; returns fallback on non-finite input
    safe_volatility = sanitize_volatility(vol_forecast, fallback_safe_volatility=0.15)

    # Horizon scale factor — does not modify EGARCH output
    horizon_multiplier = 1.0
    horizon_interpretation = "standard"

    if trading_horizon == "day_trader":
        horizon_multiplier = 1.15
        horizon_interpretation = "short_term_sensitive"
    elif trading_horizon == "positional":
        horizon_multiplier = 1.0
        horizon_interpretation = "medium_term_balanced"
    elif trading_horizon == "long_term":
        horizon_multiplier = 0.85
        horizon_interpretation = "long_term_smoothed"

    horizon_adjusted_volatility = safe_volatility * horizon_multiplier
    
    # Step 3: Extract spot price
    # Use broker live data if available, otherwise extract from historical candles
    if broker_spot_price is not None:
        spot = broker_spot_price
    else:
        spot = float(data_with_returns["Close"].iloc[-1])
    
    # Validation: Ensure spot price is a finite positive number
    # NaN comparisons always return False, so `<= 0` alone does not catch NaN
    if not math.isfinite(spot) or spot <= 0:
        raise HTTPException(
            status_code=500,
            detail=f"Invalid spot price: {spot}. Spot price must be a finite positive number."
        )
    
    # Step 4: Calculate fair price (dynamic parameters)
    strike = spot

    # Derive time-to-expiry from chain; falls back to 0.1y
    option_expiry_date = None
    
    if broker_option_chain is not None and len(broker_option_chain) > 0:
        try:
            # Strategy 1: explicit expiry field
            first_option = broker_option_chain[0]
            expiry_str = None

            for field_name in ["expiration", "expirationDate", "expiry", "expiryDate", "lastExpiration"]:
                if field_name in first_option and first_option[field_name] is not None:
                    expiry_str = first_option[field_name]
                    break

            # Strategy 2: YYMMDD embedded in contractSymbol (e.g. "NIFTY240229C23000")
            if expiry_str is None:
                contract_symbol = first_option.get("contractSymbol", "")
                if isinstance(contract_symbol, str) and len(contract_symbol) > 6:
                    date_match = re.search(r'\d{6}', contract_symbol)
                    if date_match:
                        expiry_str = date_match.group(0)

            if expiry_str is not None:
                option_expiry_date = parse_option_expiry(expiry_str)

                if option_expiry_date is not None:
                    now_utc = datetime.now(timezone.utc)
                    if option_expiry_date <= now_utc:
                        option_expiry_date = None

        except (TypeError, ValueError, KeyError, AttributeError):
            pass
    
    # Calculate time to expiry in years
    if option_expiry_date is not None:
        now_utc = datetime.now(timezone.utc)
        seconds_to_expiry = (option_expiry_date - now_utc).total_seconds()
        time_to_expiry_years = max(seconds_to_expiry, 0) / (365 * 24 * 3600)
    else:
        time_to_expiry_years = 0.1  # temporary fallback (DO NOT REMOVE)
    
    expiry_live = option_expiry_date is not None
    
    risk_free_rate = 0.06
    option_type = "call"
    
    # Scale vol by sqrt(T) for Black-Scholes input
    expiry_volatility = horizon_adjusted_volatility * (time_to_expiry_years ** 0.5)

    volatility_source = {
        "raw_forecast": vol_forecast,
        "safe_volatility": safe_volatility,
        "horizon_adjusted": horizon_adjusted_volatility,
        "expiry_adjusted": expiry_volatility,
        "model_step": timeframe,
        "annualization": "sqrt(252)",
        "trading_horizon": trading_horizon,
        "horizon_multiplier": horizon_multiplier,
        "horizon_interpretation": horizon_interpretation
    }
    
    # Guard Black-Scholes inputs
    pricing_integrity = True
    
    if expiry_volatility <= 0:
        pricing_integrity = False
    
    if time_to_expiry_years <= 0:
        pricing_integrity = False
    
    if spot <= 0:
        pricing_integrity = False
    
    if pricing_integrity:
        fair_price = black_scholes_price(
            spot=spot,
            strike=strike,
            time_to_expiry=time_to_expiry_years,
            risk_free_rate=risk_free_rate,
            volatility=expiry_volatility,
            option_type=option_type
        )
    else:
        fair_price = 0.0
    
    # Validation: Ensure fair price is valid
    if fair_price <= 0 or not isinstance(fair_price, (int, float)):
        raise HTTPException(
            status_code=500,
            detail=f"Invalid fair price calculation: {fair_price}. Price must be positive."
        )
    
    # Step 5: Determine market price from option chain or fallback
    option_mid_price = None
    atm_strike_selected = None

    if broker_option_chain is not None and len(broker_option_chain) > 0:
        # select_atm_option filters by bid/ask validity, expiry, and strike proximity
        try:
            atm_option = select_atm_option(broker_option_chain, spot)

            if atm_option is not None:
                bid = atm_option["bid"]
                ask = atm_option["ask"]
                atm_strike_selected = atm_option["strike"]
                option_mid_price = (bid + ask) / 2.0

                log_event({
                        "timestamp": request_ts,
                        "event": "atm_option_selected",
                        "strike": atm_option["strike"],
                        "bid": bid,
                        "ask": ask,
                        "mid_price": option_mid_price,
                        "spot": spot,
                        "timeframe_used": timeframe,
                        "provider_used": provider_used,
                        "data_source_live": data_source_live
                    })
            else:
                log_event({
                    "timestamp": request_ts,
                    "event": "no_valid_atm_option",
                    "reason": "no contracts passed filters (bid/ask/expiry)",
                    "option_chain_length": len(broker_option_chain),
                    "spot": spot,
                    "fallback": "using fair_price * 1.03",
                    "timeframe_used": timeframe,
                    "provider_used": provider_used,
                    "data_source_live": data_source_live
                })
        
        except (TypeError, ValueError, KeyError, AttributeError) as e:
            log_event({
                "timestamp": request_ts,
                "event": "option_chain_extraction_failed",
                "error": str(e),
                "error_type": type(e).__name__,
                "fallback": "using fair_price * 1.03",
                "timeframe_used": timeframe,
                "provider_used": provider_used,
                "data_source_live": data_source_live
            })
    
    if option_mid_price is not None:
        market_price = option_mid_price
    else:
        market_price = fair_price * 1.03  # temporary fallback ONLY
    
    market_data_live = option_mid_price is not None
    
    mispricing_result = detect_mispricing(market_price, fair_price)
    
    # Step 6: Classify volatility regime
    regime = classify_volatility_regime(vol_forecast)
    
    # Step 7: Generate strategy recommendation
    strategy_result = generate_strategy(
        mispricing_result["classification"],
        regime
    )
    regime_score = _REGIME_SCORE.get(regime, 4)

    end_time = time.perf_counter()
    execution_time_ms = round((end_time - start_time) * 1000, 2)
    
    # Unpack mispricing result; pre-compute shared derived values
    mispricing_deviation = mispricing_result["deviation"]
    mispricing_classification = mispricing_result["classification"]
    mispricing_deviation_abs = abs(mispricing_deviation)
    vol_forecast_pct = vol_forecast * 100
    sqrt_252 = 15.8745  # Pre-computed sqrt(252) for annualization
    
    signal_strength = mispricing_deviation_abs * vol_forecast
    confidence_score = min(1.0, mispricing_deviation_abs * 5)

    if confidence_score >= 0.7:
        strategy_strength = "STRONG"
    elif confidence_score >= 0.4:
        strategy_strength = "MODERATE"
    else:
        strategy_strength = "WEAK"
    
    if live_data_health == "DEGRADED":
        strategy_strength = _STRATEGY_STRENGTH_DEGRADE.get(strategy_strength, strategy_strength)

    # Annualized historical std for regime comparison
    rolling_std = returns_series.std() * sqrt_252
    
    if vol_forecast > rolling_std * 1.3:
        volatility_context = "EXPANDING_VOL"
    elif vol_forecast < rolling_std * 0.7:
        volatility_context = "CONTRACTING_VOL"
    else:
        volatility_context = "STABLE_VOL"
    
    analytics_summary = {
        "volatility_percent": round(vol_forecast_pct, 2),
        "mispricing_percent": round(mispricing_deviation * 100, 2),
        "is_overpriced": mispricing_classification == "overpriced",
        "is_underpriced": mispricing_classification == "underpriced",
        "signal_strength": round(signal_strength, 4),
        "volatility_context": volatility_context,
        "confidence_score": round(confidence_score, 3)
    }
    signal_priority_score = regime_score * confidence_score

    # Quantitative diagnostics
    # Metric 1: forecast vs historical rolling vol ratio
    volatility_change_ratio = round(vol_forecast / rolling_std, 4) if rolling_std > 0 else 1.0

    # Metric 2: signal strength normalised to [0, 1]
    signal_strength_normalized = round(min(1.0, signal_strength / 0.5), 4)

    # Metric 3: distance from nearest regime boundary (LOW<0.15, NORMAL[0.15,0.25), HIGH[0.25,0.40), EXTREME>=0.40)
    if regime == "LOW_VOL":
        distance_from_boundary = 0.15 - vol_forecast
        regime_width = 0.15
    elif regime == "NORMAL_VOL":
        # Distance from nearest boundary (0.15 or 0.25)
        distance_from_lower = vol_forecast - 0.15
        distance_from_upper = 0.25 - vol_forecast
        distance_from_boundary = min(distance_from_lower, distance_from_upper)
        regime_width = 0.10
    elif regime == "HIGH_VOL":
        # Distance from nearest boundary (0.25 or 0.40)
        distance_from_lower = vol_forecast - 0.25
        distance_from_upper = 0.40 - vol_forecast
        distance_from_boundary = min(distance_from_lower, distance_from_upper)
        regime_width = 0.15
    else:  # EXTREME_VOL
        # Distance from lower boundary (0.40)
        distance_from_boundary = vol_forecast - 0.40
        regime_width = 0.20  # arbitrary width for unbounded regime
    
    regime_confidence_estimate = round(min(1.0, distance_from_boundary / (regime_width / 2)), 4) if regime_width > 0 else 0.0

    diagnostics = {
        "volatility_change_ratio": volatility_change_ratio,
        "signal_strength_normalized": signal_strength_normalized,
        "regime_confidence_estimate": regime_confidence_estimate
    }
    
    # Quantitative integrity checks using existing pipeline outputs
    
    # Check 1: Volatility must be positive and finite
    volatility_valid = (
        isinstance(vol_forecast, (int, float)) and
        vol_forecast > 0 and
        math.isfinite(vol_forecast)
    )
    
    # Check 2: Fair price must be finite and positive
    pricing_valid = (
        isinstance(fair_price, (int, float)) and
        fair_price > 0 and
        math.isfinite(fair_price) and
        pricing_integrity  # Also check that pricing inputs were valid
    )
    
    # Check 3: Regime label matches vol thresholds (LOW<0.15, NORMAL[0.15,0.25), HIGH[0.25,0.40), EXTREME>=0.40)
    expected_regime = None
    if vol_forecast < 0.15:
        expected_regime = "LOW_VOL"
    elif vol_forecast < 0.25:
        expected_regime = "NORMAL_VOL"
    elif vol_forecast < 0.40:
        expected_regime = "HIGH_VOL"
    else:
        expected_regime = "EXTREME_VOL"
    
    regime_valid = (regime == expected_regime)
    
    # Check 4: Mispricing classification aligns with deviation sign/magnitude
    signal_valid = True
    
    if mispricing_classification == "overpriced" and mispricing_deviation <= 0.05:
        signal_valid = False
    elif mispricing_classification == "underpriced" and mispricing_deviation >= -0.05:
        signal_valid = False
    elif mispricing_classification == "fair" and (mispricing_deviation > 0.05 or mispricing_deviation < -0.05):
        signal_valid = False
    
    quant_validation = {
        "volatility_valid": volatility_valid,
        "pricing_valid": pricing_valid,
        "regime_valid": regime_valid,
        "signal_valid": signal_valid
    }
    
    # Stability score: average of 3 validation flags weighted by signal quality
    validation_score = sum([
        1.0 if volatility_valid else 0.0,
        1.0 if pricing_valid else 0.0,
        1.0 if signal_valid else 0.0
    ]) / 3.0
    quant_stability_score = round(validation_score * signal_strength_normalized, 4)

    if quant_stability_score >= 0.7:
        stability_status = "STABLE"
    elif quant_stability_score >= 0.4:
        stability_status = "WATCH"
    else:
        stability_status = "UNSTABLE"
    
    quant_stability = {
        "score": quant_stability_score,
        "status": stability_status
    }
    
    # Horizon context metadata for API response
    horizon_context = {
        "horizon": trading_horizon,
        "volatility_focus": _VOLATILITY_FOCUS.get(trading_horizon, "standard")
    }
    
    # Compute sensitivity indicators using existing fair_price and volatility values
    # Indicator 1: Fair value to volatility ratio (price sensitivity to vol changes)
    fair_value_volatility_ratio = round(fair_price / vol_forecast, 4) if vol_forecast > 0 else 0.0
    
    # Indicator 2: Mispricing adjusted for volatility regime
    # Normalizes mispricing deviation by volatility level to account for regime context
    mispricing_adjusted_for_volatility = round(mispricing_deviation / vol_forecast, 4) if vol_forecast > 0 else 0.0
    
    sensitivity_indicators = {
        "fair_value_volatility_ratio": fair_value_volatility_ratio,
        "mispricing_adjusted_for_volatility": mispricing_adjusted_for_volatility
    }
    
    # Volatility behavior insights using existing volatility and regime values
    # Insight 1: Volatility direction derived from volatility_context
    volatility_direction = _VOL_DIRECTION.get(volatility_context, "STABLE")
    
    # Insight 2: Volatility intensity score (0-1 scale based on magnitude)
    # Maps volatility to intensity: LOW=0-0.25, NORMAL=0.25-0.5, HIGH=0.5-0.75, EXTREME=0.75-1.0
    if vol_forecast < 0.15:
        volatility_intensity_score = round(vol_forecast / 0.15 * 0.25, 4)
    elif vol_forecast < 0.25:
        volatility_intensity_score = round(0.25 + (vol_forecast - 0.15) / 0.10 * 0.25, 4)
    elif vol_forecast < 0.40:
        volatility_intensity_score = round(0.50 + (vol_forecast - 0.25) / 0.15 * 0.25, 4)
    else:
        volatility_intensity_score = round(0.75 + min((vol_forecast - 0.40) / 0.40, 1.0) * 0.25, 4)
    
    # Insight 3: Regime transition flag (true if near regime boundaries)
    # Using already computed distance_from_boundary from regime confidence calculation
    transition_threshold = regime_width * 0.15  # Within 15% of regime width
    regime_transition_flag = (distance_from_boundary < transition_threshold)
    
    volatility_behaviour = {
        "volatility_direction": volatility_direction,
        "volatility_intensity_score": volatility_intensity_score,
        "regime_transition_flag": regime_transition_flag
    }
    
    # Derived signal analytics using existing mispricing deviation
    # Metric 1: Mispricing strength score (0-1 scale based on deviation magnitude)
    # Normalize: 0% deviation = 0.0, 10% deviation = 0.5, 20%+ deviation = 1.0
    mispricing_strength_score = round(min(1.0, mispricing_deviation_abs / 0.20), 4)
    
    # Metric 2: Adjusted signal priority (combines priority with mispricing strength)
    # Base priority weighted 60%, mispricing strength weighted 40%
    adjusted_signal_priority = round(
        (signal_priority_score * 0.6) + (mispricing_strength_score * 4.0 * 0.4), 
        4
    )
    
    # Metric 3: Signal confidence band based on mispricing strength and confidence score
    combined_confidence = (mispricing_strength_score + confidence_score) / 2
    if combined_confidence >= 0.65:
        signal_confidence_band = "HIGH"
    elif combined_confidence >= 0.35:
        signal_confidence_band = "MEDIUM"
    else:
        signal_confidence_band = "LOW"
    
    signal_analytics = {
        "mispricing_strength_score": mispricing_strength_score,
        "adjusted_signal_priority": adjusted_signal_priority,
        "signal_confidence_band": signal_confidence_band
    }
    
    # Horizon impact analytics using existing trading_horizon context
    # Metrics 1 & 2: Horizon risk bias + volatility weight (single lookup pass)
    horizon_risk_bias, horizon_volatility_weight = _HORIZON_META.get(trading_horizon, ("NEUTRAL", 0.50))
    
    # Metric 3: Horizon strategy alignment (compatibility with strategy type)
    strategy_type = strategy_result.get("strategy", "")
    
    # Check if strategy aligns with horizon characteristics
    if trading_horizon == "day_trader":
        # Day traders align with aggressive, high-volatility strategies
        day_trader_keywords = ["buying options", "long volatility", "credit spread"]
        horizon_strategy_alignment = "ALIGNED" if any(kw in strategy_type.lower() for kw in day_trader_keywords) else "MISALIGNED"
    elif trading_horizon == "long_term":
        # Long-term aligns with wait, stable, or no-edge strategies
        long_term_keywords = ["wait", "no strong edge", "stabilize"]
        horizon_strategy_alignment = "ALIGNED" if any(kw in strategy_type.lower() for kw in long_term_keywords) else "MISALIGNED"
    elif trading_horizon == "positional":
        # Positional strategies are flexible, generally aligned
        horizon_strategy_alignment = "ALIGNED"
    else:
        # No horizon specified, neutral alignment
        horizon_strategy_alignment = "NEUTRAL"
    
    horizon_impact = {
        "horizon_risk_bias": horizon_risk_bias,
        "horizon_volatility_weight": round(horizon_volatility_weight, 4),
        "horizon_strategy_alignment": horizon_strategy_alignment
    }
    
    # Quantitative reasoning - human-readable explanations using existing computed values
    
    # Explanation 1: Volatility regime meaning
    if regime == "LOW_VOL":
        volatility_explanation = (
            f"The current volatility forecast of {vol_forecast_pct:.2f}% indicates a LOW volatility regime. "
            "This suggests a calm market environment with relatively stable price movements. "
            "Options are typically cheaper in low volatility conditions."
        )
    elif regime == "NORMAL_VOL":
        volatility_explanation = (
            f"The current volatility forecast of {vol_forecast_pct:.2f}% indicates a NORMAL volatility regime. "
            "This represents typical market conditions with moderate price fluctuations. "
            "Option pricing reflects standard risk-reward parameters."
        )
    elif regime == "HIGH_VOL":
        volatility_explanation = (
            f"The current volatility forecast of {vol_forecast_pct:.2f}% indicates a HIGH volatility regime. "
            "This suggests elevated market uncertainty with significant price swings. "
            "Options are more expensive, reflecting increased risk."
        )
    else:  # EXTREME_VOL
        volatility_explanation = (
            f"The current volatility forecast of {vol_forecast_pct:.2f}% indicates an EXTREME volatility regime. "
            "This represents exceptional market stress with very large price movements. "
            "Options are considerably more expensive due to heightened risk."
        )
    
    # Explanation 2: Mispricing implication
    mispricing_pct = round(mispricing_deviation * 100, 2)
    
    if mispricing_classification == "overpriced":
        mispricing_explanation = (
            f"The option is trading {abs(mispricing_pct)}% above its theoretical fair value, "
            "indicating it is OVERPRICED. This suggests a potential selling opportunity, "
            "as the market premium exceeds the model's valuation."
        )
    elif mispricing_classification == "underpriced":
        mispricing_explanation = (
            f"The option is trading {abs(mispricing_pct)}% below its theoretical fair value, "
            "indicating it is UNDERPRICED. This suggests a potential buying opportunity, "
            "as the option may be trading at a discount."
        )
    else:  # fair
        mispricing_explanation = (
            f"The option is trading within {abs(mispricing_pct)}% of its theoretical fair value, "
            "indicating FAIR pricing. The market price closely matches the model's valuation, "
            "suggesting no significant arbitrage opportunity."
        )
    
    # Explanation 3: Horizon and strategy context
    strategy_text = strategy_result.get("strategy", "No strategy available")
    
    if trading_horizon == "day_trader":
        strategy_context = (
            f"For a DAY TRADER horizon, the volatility is interpreted with higher sensitivity (multiplier: 1.15). "
            f"Strategy recommendation: '{strategy_text}'. "
            "Day trading focuses on short-term price movements and requires quick execution."
        )
    elif trading_horizon == "positional":
        strategy_context = (
            f"For a POSITIONAL horizon, the volatility is interpreted with balanced perspective (multiplier: 1.0). "
            f"Strategy recommendation: '{strategy_text}'. "
            "Positional trading balances medium-term trends with risk management."
        )
    elif trading_horizon == "long_term":
        strategy_context = (
            f"For a LONG-TERM horizon, the volatility is smoothed to reduce noise (multiplier: 0.85). "
            f"Strategy recommendation: '{strategy_text}'. "
            "Long-term investing focuses on fundamental value over time."
        )
    else:
        strategy_context = (
            f"Using standard volatility interpretation (no specific trading horizon). "
            f"Strategy recommendation: '{strategy_text}'. "
            "This analysis applies general market principles without horizon-specific adjustments."
        )
    
    quant_reasoning = {
        "volatility_explanation": volatility_explanation,
        "mispricing_explanation": mispricing_explanation,
        "strategy_context": strategy_context
    }
    
    # Strategy reasoning - explain why the strategy was suggested based on inputs
    strategy_recommendation = strategy_result.get("strategy", "No strategy")
    strategy_confidence = strategy_result.get("confidence", "low")
    
    # Build explanation components
    regime_reason = ""
    if regime == "LOW_VOL":
        regime_reason = "The LOW volatility environment suggests options are relatively cheap, making buying strategies potentially attractive."
    elif regime == "NORMAL_VOL":
        regime_reason = "The NORMAL volatility regime provides balanced conditions for standard option strategies."
    elif regime == "HIGH_VOL":
        regime_reason = "The HIGH volatility environment means options are expensive, favoring strategies that benefit from volatility or sell premium."
    else:  # EXTREME_VOL
        regime_reason = "The EXTREME volatility regime creates uncertain conditions where waiting or defensive strategies are prudent."
    
    mispricing_reason = ""
    if mispricing_classification == "overpriced":
        mispricing_reason = "Since the option is OVERPRICED relative to fair value, strategies that sell premium or avoid buying are preferred."
    elif mispricing_classification == "underpriced":
        mispricing_reason = "Since the option is UNDERPRICED relative to fair value, buying strategies offer potential value capture."
    else:
        mispricing_reason = "With FAIR pricing, there is no significant mispricing edge to exploit."
    
    horizon_reason = ""
    if trading_horizon == "day_trader":
        horizon_reason = "For day traders, strategies should capitalize on short-term volatility movements with quick execution."
    elif trading_horizon == "positional":
        horizon_reason = "For positional traders, strategies balance opportunity with medium-term risk management."
    elif trading_horizon == "long_term":
        horizon_reason = "For long-term investors, strategies should prioritize stability and avoid excessive short-term risk."
    else:
        horizon_reason = "Without a specific trading horizon, the strategy applies general risk-reward principles."
    
    # Combine into full explanation
    strategy_reasoning = (
        f"Strategy: '{strategy_recommendation}' (Confidence: {strategy_confidence}). "
        f"{regime_reason} {mispricing_reason} {horizon_reason}"
    )
    
    # Determine pipeline health
    if vol_forecast > 0 and fair_price > 0:
        pipeline_health = "OK"
    else:
        pipeline_health = "CHECK_DATA"
    
    # Determine risk tag based on regime
    risk_tag = _RISK_TAG.get(regime, "NORMAL_RISK")

    # Determine market bias, signal direction, and strategy intent via lookup maps
    market_bias      = _MARKET_BIAS.get(mispricing_classification, "NEUTRAL")
    signal_direction = _SIGNAL_DIR.get(market_bias, "NO_SIGNAL")
    strategy_intent  = _STRATEGY_INTENT.get(signal_direction, "WAIT_AND_WATCH")
    
    
    
    # Determine strategy category based on regime
    if regime in ["HIGH_VOL", "EXTREME_VOL"]:
        strategy_category = "VOLATILITY_STRATEGY"
    elif regime == "LOW_VOL":
        strategy_category = "PREMIUM_BUYING"
    else:
        strategy_category = "NEUTRAL_SETUP"
    
    # Determine strategy urgency based on strength and regime
    if strategy_strength == "STRONG" and regime in ["HIGH_VOL", "EXTREME_VOL"]:
        strategy_urgency = "HIGH"
    elif strategy_strength == "MODERATE":
        strategy_urgency = "MEDIUM"
    else:
        strategy_urgency = "LOW"
    
    # Compute analytics flags for frontend
    analytics_flags = {
        "high_confidence": confidence_score >= 0.7,
        "high_volatility": regime in ["HIGH_VOL", "EXTREME_VOL"],
        "trade_bias_present": market_bias != "NEUTRAL"
    }
    
    # Calculate analytics health score
    analytics_health_score = 1.0
    if pipeline_health != "OK":
        analytics_health_score -= 0.5
    if confidence_score < 0.3:
        analytics_health_score -= 0.2
    analytics_health_score = max(0.0, analytics_health_score)
    
    # Create display signal for frontend
    display_signal = f"{market_bias} | {regime} | {strategy_strength}"
    
    # Determine execution profile based on urgency
    execution_profile = _EXECUTION_PROFILE.get(strategy_urgency, "PASSIVE")

    # Determine dashboard color hint for UI
    dashboard_color_hint = _DASHBOARD_COLOR.get(market_bias, "YELLOW")
    
    # Determine analytics stability
    if confidence_score >= 0.7 and pipeline_health == "OK":
        analytics_stability = "STABLE"
    elif confidence_score >= 0.4:
        analytics_stability = "WATCH"
    else:
        analytics_stability = "UNSTABLE"
    
    # Create quant_summary for high-level frontend readability
    # Extract key signals from existing analytics without new computations
    quant_summary = {
        "regime": regime,
        "mispricing_classification": mispricing_classification,
        "horizon": trading_horizon if trading_horizon else "not_specified",
        "strategy_intent": strategy_intent,
        "signal_direction": signal_direction,
        "quant_stability_status": stability_status
    }
    
    # Create decision_snapshot - compact summary of key decision outputs
    decision_snapshot = {
        "regime": regime,
        "mispricing_classification": mispricing_classification,
        "strategy_name": strategy_result.get("strategy", "No strategy"),
        "signal_direction": signal_direction,
        "horizon": trading_horizon if trading_horizon else "not_specified"
    }
    
    # Generate research_tags based on existing analytics values
    research_tags = []

    if live_data_health == "DEGRADED":
        research_tags.append("FALLBACK_MODE")
    
    # Volatility behavior tags
    if volatility_direction == "EXPANDING":
        research_tags.append("VOLATILITY_EXPANSION")
    elif volatility_direction == "CONTRACTING":
        research_tags.append("VOLATILITY_CONTRACTION")
    
    # Mispricing tags
    if mispricing_classification != "fair":
        research_tags.append("MISPRICING_SIGNAL")
    if mispricing_classification == "overpriced":
        research_tags.append("OVERPRICED_SIGNAL")
    elif mispricing_classification == "underpriced":
        research_tags.append("UNDERPRICED_SIGNAL")
    
    # Strong mispricing tag
    if mispricing_strength_score >= 0.5:
        research_tags.append("STRONG_MISPRICING")
    
    # Horizon adjustment tag
    if trading_horizon is not None:
        research_tags.append("HORIZON_ADJUSTED")
    
    # Regime tags
    if regime == "LOW_VOL":
        research_tags.append("REGIME_LOW_VOL")
    elif regime == "NORMAL_VOL":
        research_tags.append("REGIME_NORMAL_VOL")
    elif regime == "HIGH_VOL":
        research_tags.append("REGIME_HIGH_VOL")
    elif regime == "EXTREME_VOL":
        research_tags.append("REGIME_EXTREME_VOL")
    
    # Signal direction tags
    if signal_direction == "LONG_SIGNAL":
        research_tags.append("LONG_SIGNAL")
    elif signal_direction == "SHORT_SIGNAL":
        research_tags.append("SHORT_SIGNAL")
    elif signal_direction == "NO_SIGNAL":
        research_tags.append("NEUTRAL_SIGNAL")
    
    # Stability tags
    if stability_status == "STABLE":
        research_tags.append("STABILITY_STABLE")
    elif stability_status == "WATCH":
        research_tags.append("STABILITY_WATCH")
    elif stability_status == "UNSTABLE":
        research_tags.append("STABILITY_UNSTABLE")
    
    # Regime transition tag
    if regime_transition_flag:
        research_tags.append("REGIME_TRANSITION")
    
    # Confidence tags
    if signal_confidence_band == "HIGH":
        research_tags.append("HIGH_CONFIDENCE")
    elif signal_confidence_band == "LOW":
        research_tags.append("LOW_CONFIDENCE")
    
    # Final consistency check before returning response
    quant_warning = None
    consistency_issues = []
    
    # Check 1: Volatility within guardrails (positive, finite, reasonable range)
    if not (isinstance(vol_forecast, (int, float)) and math.isfinite(vol_forecast)):
        consistency_issues.append("volatility_not_finite")
    elif vol_forecast <= 0:
        consistency_issues.append("volatility_not_positive")
    elif vol_forecast > 5.0:  # Volatility guardrail: should not exceed 500%
        consistency_issues.append("volatility_exceeds_guardrail")
    
    # Check 2: Fair price is finite and positive
    if not (isinstance(fair_price, (int, float)) and math.isfinite(fair_price)):
        consistency_issues.append("fair_price_not_finite")
    elif fair_price <= 0:
        consistency_issues.append("fair_price_not_positive")
    
    # Check 3: Regime matches volatility range — reuse expected_regime from quant_validation above
    if regime != expected_regime:
        consistency_issues.append("regime_mismatch")
    
    # Check 4: Horizon value is valid
    allowed_horizons = ["day_trader", "positional", "long_term", None]
    if trading_horizon not in allowed_horizons:
        consistency_issues.append("invalid_horizon")
    
    # Set warning flag if any inconsistency found
    if len(consistency_issues) > 0:
        quant_warning = "CHECK_OUTPUT"
    
    # Return clean structure for frontend consumption - organized by logical sections
    return {
        # ========== FRAMEWORK METADATA ==========
        "quant_framework": {
            "quant_version": "v2_horizon_aware",
            "volatility_model": "EGARCH(1,1)",
            "pricing_model": "Black-Scholes",
            "volatility_source": "forecasted_conditional_volatility",
            "horizon_aware": True,
            "regime_model": "threshold_based_classification"
        },
        "pipeline_description": [
            "Market Data",
            "Log Returns",
            "EGARCH Volatility Forecast",
            "Black-Scholes Pricing",
            "Mispricing Detection",
            "Regime Classification",
            "Strategy Recommendation"
        ],
        
        # ========== EXECUTIVE SUMMARY ==========
        "quant_summary": quant_summary,
        "decision_snapshot": decision_snapshot,
        
        # ========== CORE ANALYTICS RESULTS ==========
        "spot_price": spot,
        "forecast_volatility": vol_forecast,
        "fair_price": fair_price,
        "pricing_integrity": pricing_integrity,
        "market_price": market_price,
        "market_data_live": market_data_live,
        "expiry_live": expiry_live,
        "mispricing": mispricing_result,
        "regime": regime,
        "regime_score": regime_score,
        "risk_tag": risk_tag,
        "market_bias": market_bias,
        "signal_direction": signal_direction,
        "strategy_intent": strategy_intent,
        "strategy": strategy_result,
        "strategy_strength": strategy_strength,
        "strategy_category": strategy_category,
        "strategy_urgency": strategy_urgency,
        
        # ========== ANALYTICS SUMMARY & FLAGS ==========
        "analytics_summary": analytics_summary,
        "analytics_flags": analytics_flags,
        "display_signal": display_signal,
        "execution_profile": execution_profile,
        "signal_priority_score": signal_priority_score,
        "dashboard_color_hint": dashboard_color_hint,
        "strategy_context": {
            "regime": regime,
            "volatility_context": analytics_summary["volatility_context"]
        },
        
        # ========== DIAGNOSTICS & VALIDATION ==========
        "diagnostics": diagnostics,
        "quant_validation": quant_validation,
        "quant_stability": quant_stability,
        "quant_warning": quant_warning,
        "LIVE_DATA_HEALTH": live_data_health,
        
        # ========== DERIVED ANALYTICS ==========
        "sensitivity_indicators": sensitivity_indicators,
        "volatility_behaviour": volatility_behaviour,
        "signal_analytics": signal_analytics,
        "horizon_impact": horizon_impact,
        
        # ========== EXPLANATIONS ==========
        "quant_reasoning": quant_reasoning,
        "strategy_reasoning": strategy_reasoning,
        
        # ========== RESEARCH METADATA ==========
        "research_tags": research_tags,
        
        # ========== PIPELINE TRACE ==========
        "pipeline_trace": {
            "timeframe_used": timeframe,
            "horizon_multiplier": horizon_multiplier,
            "annualization_factor": get_annualization_factor(timeframe),
            "broker_mode": "live" if live_data_health == "HEALTHY" else ("degraded" if live_data_health == "DEGRADED" else "historical"),
            "atm_strike_selected": atm_strike_selected
        },
        
        # ========== SYSTEM METADATA ==========
        "model_info": {
            "vol_model": "EGARCH(1,1)",
            "pricing_model": "Black-Scholes",
            "data_source": "yfinance"
        },
        "volatility_source": volatility_source,
        "trading_horizon": trading_horizon,
        "horizon_context": horizon_context,
        "analytics_version": "v1.1",
        "output_schema": "quant_pipeline_v1_locked",
        "analytics_timestamp": request_ts,
        "pipeline_health": pipeline_health,
        "analytics_health_score": analytics_health_score,
        "analytics_stability": analytics_stability,
        "pipeline_stage": {
            "data_ready": True,
            "volatility_computed": vol_forecast is not None,
            "pricing_computed": fair_price is not None,
            "strategy_generated": strategy_result is not None
        },
        "execution_time_ms": execution_time_ms,
        
        # ========== RAW DATA ==========
        "_data": data.tail(50),
        "_data_with_returns": data_with_returns.tail(50),
        
        # ========== CACHE PERFORMANCE METADATA ==========
        "_performance_cache_hit": cache_hit
    }


# Function-scoped cache: avoids redundant data fetches across repeated calls
run_pipeline.cache = {}
run_pipeline.cache_ttl_seconds = 300  # 5-minute TTL


# ========== ENDPOINTS ==========

@app.get("/")
def root():
    return create_response({"status": "running"})

@app.get(
    "/health",
    summary="Health check",
    description="Lightweight service liveness endpoint for deployment and frontend integration. Does not run the research pipeline.",
    tags=["System"],
    responses=_RESPONSES
)
def health_check():
    start = time.perf_counter()
    record_request("/health")
    try:
        payload = {
            "service": "options-mispricing-backend",
            "status": "ok"
        }
        duration_ms = int((time.perf_counter() - start) * 1000)
        record_result("/health", "ok", duration_ms, None)
        return build_success_response(payload, meta={"execution_time_ms": duration_ms})
    except Exception as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        record_result("/health", "error", duration_ms, str(e))
        return error_json(str(e), status_code=500)

@app.get(
    "/metrics",
    summary="Service metrics",
    description="Lightweight in-memory counters for monitoring. Not a full metrics system.",
    tags=["System"],
    responses=_RESPONSES
)
def get_metrics():
    start = time.perf_counter()
    try:
        duration_ms = int((time.perf_counter() - start) * 1000)
        return build_success_response(METRICS, meta={"execution_time_ms": duration_ms})
    except Exception as e:
        return error_json(str(e), status_code=500)

@app.get(
    "/nifty",
    summary="Fetch latest NIFTY 50 market data",
    description=(
        "Returns the most recent OHLCV records for the NIFTY 50 index sourced from yfinance. "
        "Accepts an optional `symbol` query parameter (default: NIFTY) for forward-compatibility. "
        "This is the raw market data that seeds the quantitative pipeline. "
        "It is intended for data inspection and research purposes, not automated trading decisions."
    ),
    tags=["Market Data"],
    responses=_RESPONSES
)
def get_nifty_data(
    symbol: str = Query(default="NIFTY", min_length=1, max_length=20, description="Market symbol (e.g., NIFTY)"),
    timeframe: str = Query(default=None, description="Supported timeframes: 1m, 5m, 15m, 1h, daily, weekly")
):
    start = time.perf_counter()
    record_request("/nifty")
    try:
        symbol = validate_symbol(symbol)
        pipeline = run_pipeline(symbol=symbol, timeframe=timeframe)
        candles = pipeline["_data"].reset_index().to_dict(orient="records")
        payload = {
            "total_candles": len(candles),
            "candles": candles
        }
        duration_ms = int((time.perf_counter() - start) * 1000)
        log_endpoint_result("/nifty", "ok", duration_ms)
        record_result("/nifty", "ok", duration_ms, None)
        return build_success_response(payload, meta={
            "execution_time_ms": duration_ms,
            "timeframe_used": pipeline["pipeline_trace"]["timeframe_used"],
            "provider": "historical"
        })
    except ValueError as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        log_endpoint_result("/nifty", "error", duration_ms, str(e))
        record_result("/nifty", "error", duration_ms, str(e))
        return error_json(str(e), status_code=400)
    except Exception as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        log_endpoint_result("/nifty", "error", duration_ms, str(e))
        record_result("/nifty", "error", duration_ms, str(e))
        return error_json(str(e), status_code=500)

@app.get(
    "/returns",
    summary="Compute log returns from NIFTY 50 close prices",
    description=(
        "Returns the full time series of daily log returns derived from NIFTY 50 closing prices. "
        "Accepts an optional `symbol` query parameter (default: NIFTY) for forward-compatibility. "
        "Log returns are the primary input to the EGARCH volatility forecasting model. "
        "This endpoint is intended for exploratory data analysis and pipeline inspection within a research context."
    ),
    tags=["Pipeline"],
    responses=_RESPONSES
)
def get_log_returns(
    symbol: str = Query(default="NIFTY", min_length=1, max_length=20, description="Market symbol (e.g., NIFTY)"),
    timeframe: str = Query(default=None, description="Supported timeframes: 1m, 5m, 15m, 1h, daily, weekly")
):
    start = time.perf_counter()
    record_request("/returns")
    try:
        symbol = validate_symbol(symbol)
        pipeline = run_pipeline(symbol=symbol, timeframe=timeframe)
        payload = pipeline["_data_with_returns"].to_dict(orient="records")
        duration_ms = int((time.perf_counter() - start) * 1000)
        log_endpoint_result("/returns", "ok", duration_ms)
        record_result("/returns", "ok", duration_ms, None)
        return build_success_response(payload, meta={
            "execution_time_ms": duration_ms,
            "timeframe_used": pipeline["pipeline_trace"]["timeframe_used"],
            "provider": "historical"
        })
    except ValueError as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        log_endpoint_result("/returns", "error", duration_ms, str(e))
        record_result("/returns", "error", duration_ms, str(e))
        return error_json(str(e), status_code=400)
    except Exception as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        log_endpoint_result("/returns", "error", duration_ms, str(e))
        record_result("/returns", "error", duration_ms, str(e))
        return error_json(str(e), status_code=500)

@app.get(
    "/forecast-vol",
    summary="Forecast annualized volatility using EGARCH(1,1)",
    description=(
        "Returns the one-step-ahead annualized volatility forecast produced by an EGARCH(1,1) model "
        "fitted on recent NIFTY 50 log returns. "
        "Accepts an optional `symbol` query parameter (default: NIFTY) for forward-compatibility. "
        "The output is expressed as a decimal (e.g. 0.18 represents 18% annualized volatility). "
        "This forecasted volatility is subsequently used as the sole volatility input to the Black-Scholes pricing model. "
        "Results are intended for research and decision-support only."
    ),
    tags=["Pipeline"],
    responses=_RESPONSES
)
def get_forecast_volatility(
    symbol: str = Query(default="NIFTY", min_length=1, max_length=20, description="Market symbol (e.g., NIFTY)"),
    timeframe: str = Query(default=None, description="Supported timeframes: 1m, 5m, 15m, 1h, daily, weekly")
):
    start = time.perf_counter()
    record_request("/forecast-vol")
    try:
        symbol = validate_symbol(symbol)
        pipeline = run_pipeline(symbol=symbol, timeframe=timeframe)
        payload = {"forecast_volatility": pipeline["forecast_volatility"]}
        duration_ms = int((time.perf_counter() - start) * 1000)
        log_endpoint_result("/forecast-vol", "ok", duration_ms)
        record_result("/forecast-vol", "ok", duration_ms, None)
        return build_success_response(payload, meta={
            "execution_time_ms": duration_ms,
            "timeframe_used": pipeline["pipeline_trace"]["timeframe_used"],
            "provider": "historical"
        })
    except ValueError as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        log_endpoint_result("/forecast-vol", "error", duration_ms, str(e))
        record_result("/forecast-vol", "error", duration_ms, str(e))
        return error_json(str(e), status_code=400)
    except Exception as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        log_endpoint_result("/forecast-vol", "error", duration_ms, str(e))
        record_result("/forecast-vol", "error", duration_ms, str(e))
        return error_json(str(e), status_code=500)

@app.get(
    "/fair-price",
    summary="Calculate Black-Scholes theoretical option fair value",
    description=(
        "Returns the theoretical fair value of an at-the-money call option computed via the Black-Scholes model. "
        "Accepts an optional `symbol` query parameter (default: NIFTY) for forward-compatibility. "
        "Accepts an optional `trading_horizon` parameter (day_trader, positional, long_term) to adjust volatility interpretation. "
        "Volatility input is the EGARCH(1,1) forecast, not implied volatility. "
        "Time to expiry is expressed in years as required by the pricing model. "
        "This fair value serves as the benchmark for mispricing detection in the pipeline. "
        "Output is for research and analytical decision-support purposes only."
    ),
    tags=["Pipeline"],
    responses=_RESPONSES
)
def get_fair_price(
    symbol: str = Query(default="NIFTY", min_length=1, max_length=20, description="Market symbol (e.g., NIFTY)"),
    trading_horizon: str = Query(default=None, description="Trading horizon: day_trader, positional, or long_term"),
    timeframe: str = Query(default=None, description="Supported timeframes: 1m, 5m, 15m, 1h, daily, weekly")
):
    start = time.perf_counter()
    record_request("/fair-price")
    try:
        symbol = validate_symbol(symbol)
        pipeline = run_pipeline(symbol=symbol, trading_horizon=trading_horizon, timeframe=timeframe)
        payload = {"fair_price": pipeline["fair_price"]}
        duration_ms = int((time.perf_counter() - start) * 1000)
        log_endpoint_result("/fair-price", "ok", duration_ms)
        record_result("/fair-price", "ok", duration_ms, None)
        return build_success_response(payload, meta={
            "execution_time_ms": duration_ms,
            "timeframe_used": pipeline["pipeline_trace"]["timeframe_used"],
            "provider": "historical"
        })
    except ValueError as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        log_endpoint_result("/fair-price", "error", duration_ms, str(e))
        record_result("/fair-price", "error", duration_ms, str(e))
        return error_json(str(e), status_code=400)
    except Exception as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        log_endpoint_result("/fair-price", "error", duration_ms, str(e))
        record_result("/fair-price", "error", duration_ms, str(e))
        return error_json(str(e), status_code=500)

@app.get(
    "/mispricing",
    summary="Detect option mispricing relative to Black-Scholes fair value",
    description=(
        "Compares the observed market price of an option against its Black-Scholes theoretical fair value "
        "and returns the percentage deviation along with a classification of overpriced, underpriced, or fair. "
        "Accepts an optional `symbol` query parameter (default: NIFTY) for forward-compatibility. "
        "A \u00b15% threshold is applied for classification. "
        "Volatility used in fair value computation is the EGARCH(1,1) forecast. "
        "This output is a research signal and does not constitute a trading recommendation."
    ),
    tags=["Pipeline"],
    responses=_RESPONSES
)
def get_mispricing(
    symbol: str = Query(default="NIFTY", min_length=1, max_length=20, description="Market symbol (e.g., NIFTY)"),
    trading_horizon: str = Query(default=None, description="Trading horizon: day_trader, positional, or long_term"),
    timeframe: str = Query(default=None, description="Supported timeframes: 1m, 5m, 15m, 1h, daily, weekly")
):
    start = time.perf_counter()
    record_request("/mispricing")
    try:
        symbol = validate_symbol(symbol)
        pipeline = run_pipeline(symbol=symbol, trading_horizon=trading_horizon, timeframe=timeframe)
        payload = {
            "fair_price": pipeline["fair_price"],
            "market_price": pipeline["market_price"],
            "mispricing": pipeline["mispricing"]
        }
        duration_ms = int((time.perf_counter() - start) * 1000)
        log_endpoint_result("/mispricing", "ok", duration_ms)
        record_result("/mispricing", "ok", duration_ms, None)
        return build_success_response(payload, meta={
            "execution_time_ms": duration_ms,
            "timeframe_used": pipeline["pipeline_trace"]["timeframe_used"],
            "provider": "historical"
        })
    except ValueError as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        log_endpoint_result("/mispricing", "error", duration_ms, str(e))
        record_result("/mispricing", "error", duration_ms, str(e))
        return error_json(str(e), status_code=400)
    except Exception as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        log_endpoint_result("/mispricing", "error", duration_ms, str(e))
        record_result("/mispricing", "error", duration_ms, str(e))
        return error_json(str(e), status_code=500)

@app.get(
    "/regime",
    summary="Classify the current volatility regime",
    description=(
        "Classifies the prevailing market volatility environment into one of four regimes: "
        "LOW_VOL, NORMAL_VOL, HIGH_VOL, or EXTREME_VOL, based on the EGARCH(1,1) annualized forecast. "
        "Accepts an optional `symbol` query parameter (default: NIFTY) for forward-compatibility. "
        "Regime classification is used downstream to modulate strategy recommendations. "
        "This endpoint is intended for regime-aware research and analytical workflows."
    ),
    tags=["Pipeline"],
    responses=_RESPONSES
)
def get_regime(
    symbol: str = Query(default="NIFTY", min_length=1, max_length=20, description="Market symbol (e.g., NIFTY)"),
    trading_horizon: str = Query(default=None, description="Trading horizon: day_trader, positional, or long_term"),
    timeframe: str = Query(default=None, description="Supported timeframes: 1m, 5m, 15m, 1h, daily, weekly")
):
    start = time.perf_counter()
    record_request("/regime")
    try:
        symbol = validate_symbol(symbol)
        pipeline = run_pipeline(symbol=symbol, trading_horizon=trading_horizon, timeframe=timeframe)
        payload = {
            "forecast_volatility": pipeline["forecast_volatility"],
            "regime": pipeline["regime"]
        }
        duration_ms = int((time.perf_counter() - start) * 1000)
        log_endpoint_result("/regime", "ok", duration_ms)
        record_result("/regime", "ok", duration_ms, None)
        return build_success_response(payload, meta={
            "execution_time_ms": duration_ms,
            "timeframe_used": pipeline["pipeline_trace"]["timeframe_used"],
            "provider": "historical"
        })
    except ValueError as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        log_endpoint_result("/regime", "error", duration_ms, str(e))
        record_result("/regime", "error", duration_ms, str(e))
        return error_json(str(e), status_code=400)
    except Exception as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        log_endpoint_result("/regime", "error", duration_ms, str(e))
        record_result("/regime", "error", duration_ms, str(e))
        return error_json(str(e), status_code=500)

@app.get(
    "/strategy",
    summary="Run the full quantitative pipeline and return strategy recommendation",
    description=(
        "Executes the complete pipeline — EGARCH(1,1) volatility forecast, Black-Scholes fair pricing "
        "(with time to expiry in years), mispricing detection, volatility regime classification, "
        "and rule-based strategy recommendation — in a single request. "
        "Accepts an optional `symbol` query parameter (default: NIFTY) for forward-compatibility. "
        "Accepts an optional `trading_horizon` parameter (day_trader, positional, long_term) to adjust volatility interpretation. "
        "Accepts an optional `provider` parameter (dhan) to use live broker data instead of historical data. "
        "Returns a consolidated response including spot price, forecasted volatility, fair value, "
        "mispricing classification, regime label, strategy suggestion, and analytics metadata. "
        "This is a research and decision-support tool; outputs do not constitute automated trading signals."
    ),
    tags=["Pipeline"],
    responses=_RESPONSES
)
def get_strategy(
    symbol: str = Query(default="NIFTY", min_length=1, max_length=20, description="Market symbol (e.g., NIFTY)"),
    trading_horizon: str = Query(default=None, description="Trading horizon: day_trader, positional, or long_term"),
    timeframe: str = Query(default=None, description="Supported timeframes: 1m, 5m, 15m, 1h, daily, weekly"),
    provider: str = Query(default=None, description="Data provider: dhan for live broker data, None for historical data")
):
    start = time.perf_counter()
    record_request("/strategy")
    try:
        symbol = validate_symbol(symbol)
        
        # Use live broker data if provider is specified
        if provider == "dhan":
            live_input = get_live_input(symbol=symbol, timeframe=timeframe or "daily")
            result = run_pipeline(
                input_data=live_input,
                symbol=symbol,
                trading_horizon=trading_horizon,
                timeframe=timeframe
            )
        else:
            result = run_pipeline(symbol=symbol, trading_horizon=trading_horizon, timeframe=timeframe)
        duration_ms = int((time.perf_counter() - start) * 1000)
        log_endpoint_result("/strategy", "ok", duration_ms)
        record_result("/strategy", "ok", duration_ms, None)
        return build_success_response({
            "spot_price": result["spot_price"],
            "forecast_volatility": result["forecast_volatility"],
            "fair_price": result["fair_price"],
            "market_price": result["market_price"],
            "mispricing": result["mispricing"],
            "regime": result["regime"],
            "strategy": result["strategy"],
            "model_info": result.get("model_info"),
            "analytics_summary": result.get("analytics_summary"),
            "pipeline_health": result.get("pipeline_health")
        }, meta={
            "execution_time_ms": duration_ms,
            "timeframe_used": result["pipeline_trace"]["timeframe_used"],
            "provider": provider if provider else "historical"
        })

    except ValueError as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        log_endpoint_result("/strategy", "error", duration_ms, str(e))
        record_result("/strategy", "error", duration_ms, str(e))
        return error_json(str(e), status_code=400)
    except Exception as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        log_endpoint_result("/strategy", "error", duration_ms, str(e))
        record_result("/strategy", "error", duration_ms, str(e))
        raise HTTPException(status_code=500, detail=str(e))