import json
import logging
import re
import time
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Query
from backend.services.data_service import fetch_nifty_data, compute_log_returns
from backend.services.volatility_service import forecast_volatility
from backend.services.pricing_service import black_scholes_price
from backend.services.mispricing_service import detect_mispricing
from backend.services.regime_service import classify_volatility_regime
from backend.services.strategy_service import generate_strategy
from backend.broker_adapter import fetch_spot, fetch_option_chain, normalize_broker_payload

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

# Structured JSON log helper
def log_event(event: dict) -> None:
    """
    Emit a single structured JSON log line.

    Args:
        event: Metadata dict. Must not contain large payloads.
    """
    event.setdefault("timestamp", _utc_iso_timestamp())
    logger.info(json.dumps(event, ensure_ascii=False))


# Utility function for UTC timestamp generation
def _utc_iso_timestamp():
    """Generate UTC ISO timestamp with Z suffix."""
    return datetime.utcnow().isoformat() + "Z"


# Response wrapper for standardized API responses
def create_response(data):
    """
    Wrap response data in standardized format.
    
    Args:
        data: Response payload
        
    Returns:
        dict: Standardized response with status, timestamp, and data
    """
    return {
        "status": "success",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "data": data
    }


# Standardized success response for endpoint handlers
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


# Standardized error response for endpoint handlers
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


# Symbol input validation helper
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


# Live market data helper — fetches and normalizes broker data for future endpoint use
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


# Internal helper function for pipeline execution
def run_pipeline(input_data: dict = None, symbol: str = "NIFTY"):
    """
    Execute the complete quantitative pipeline.

    Args:
        input_data: Optional normalized market data dict from broker_adapter
            (shape: {"spot_price": float, "option_chain": list, "timestamp": str}).
            Reserved for future live-data integration. When None, the pipeline
            fetches data internally via data_service (current default behavior).
        symbol: Ticker symbol hint for future symbol-aware data fetching.
            Accepted and stored for forward-compatibility; data_service currently
            defaults to NIFTY 50. Default: "NIFTY".

    Returns:
        dict: Complete analytics results with clean structure
    """
    # Start performance timer
    start_time = time.perf_counter()
    
    # Broker adapter integration placeholders
    option_expiry_date = None  # broker adapter will populate later
    
    # Step 1: Fetch and prepare data
    data = fetch_nifty_data()
    data_with_returns = compute_log_returns(data)
    
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
    
    # Step 2: Forecast volatility
    vol_forecast = forecast_volatility(returns_series)
    
    # Validation: Ensure volatility is valid type
    if not isinstance(vol_forecast, (int, float)):
        raise HTTPException(
            status_code=500,
            detail=f"Invalid volatility forecast type: {type(vol_forecast)}. Must be numeric."
        )
    
    # Normalize volatility to decimal format if needed
    if vol_forecast > 1:
        vol_forecast = vol_forecast / 100
    
    # Apply volatility sanity guardrails
    if vol_forecast <= 0:
        safe_volatility = 0.05  # minimal floor
    elif vol_forecast > 3:
        safe_volatility = 3.0   # hard cap at 300%
    else:
        safe_volatility = vol_forecast
    
    # Step 3: Extract spot price
    spot = float(data_with_returns["Close"].iloc[-1])
    
    # Validation: Ensure spot price is positive
    if spot <= 0:
        raise HTTPException(
            status_code=500,
            detail=f"Invalid spot price: {spot}. Spot price must be positive."
        )
    
    # Step 4: Calculate fair price (dynamic parameters)
    strike = spot
    
    # Dynamic time to expiry calculation
    if option_expiry_date is not None:
        now_utc = datetime.now(timezone.utc)
        seconds_to_expiry = (option_expiry_date - now_utc).total_seconds()
        time_to_expiry_years = max(seconds_to_expiry, 0) / (365 * 24 * 3600)
    else:
        time_to_expiry_years = 0.1  # temporary fallback (DO NOT REMOVE)
    
    expiry_live = option_expiry_date is not None
    
    risk_free_rate = 0.06
    option_type = "call"
    
    # Apply expiry-adjusted volatility scaling using safe_volatility
    expiry_volatility = safe_volatility * (time_to_expiry_years ** 0.5)
    
    # Volatility transformation metadata for transparency
    volatility_source = {
        "raw_forecast": vol_forecast,
        "safe_volatility": safe_volatility,
        "expiry_adjusted": expiry_volatility,
        "model_step": "daily",
        "annualization": "sqrt(252)"
    }
    
    # Validate pricing inputs integrity
    pricing_integrity = True
    
    if expiry_volatility <= 0:
        pricing_integrity = False
    
    if time_to_expiry_years <= 0:
        pricing_integrity = False
    
    if spot <= 0:
        pricing_integrity = False
    
    # Calculate fair price with integrity check
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
    
    # Step 5: Determine market price (broker-ready structure)
    option_mid_price = None  # Placeholder for live broker feed integration
    
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
    
    # Calculate execution time
    end_time = time.perf_counter()
    execution_time_ms = round((end_time - start_time) * 1000, 2)
    
    # Compute analytics summary
    signal_strength = abs(mispricing_result["deviation"]) * vol_forecast
    confidence_score = min(1.0, abs(mispricing_result["deviation"]) * 5)
    
    # Determine strategy strength based on confidence
    if confidence_score >= 0.7:
        strategy_strength = "STRONG"
    elif confidence_score >= 0.4:
        strategy_strength = "MODERATE"
    else:
        strategy_strength = "WEAK"
    
    # Calculate volatility context
    rolling_std = returns_series.std()
    if vol_forecast > rolling_std * 1.3:
        volatility_context = "EXPANDING_VOL"
    elif vol_forecast < rolling_std * 0.7:
        volatility_context = "CONTRACTING_VOL"
    else:
        volatility_context = "STABLE_VOL"
    
    analytics_summary = {
        "volatility_percent": round(vol_forecast * 100, 2),
        "mispricing_percent": round(mispricing_result["deviation"] * 100, 2),
        "is_overpriced": mispricing_result["classification"] == "overpriced",
        "is_underpriced": mispricing_result["classification"] == "underpriced",
        "signal_strength": round(signal_strength, 4),
        "volatility_context": volatility_context,
        "confidence_score": round(confidence_score, 3)
    }
    
    # Determine pipeline health
    if vol_forecast > 0 and fair_price > 0:
        pipeline_health = "OK"
    else:
        pipeline_health = "CHECK_DATA"
    
    # Determine risk tag based on regime
    if regime == "EXTREME_VOL":
        risk_tag = "HIGH_RISK"
    elif regime == "HIGH_VOL":
        risk_tag = "ELEVATED_RISK"
    elif regime == "LOW_VOL":
        risk_tag = "LOW_RISK"
    else:
        risk_tag = "NORMAL_RISK"
    
    # Determine market bias based on mispricing
    if mispricing_result["classification"] == "overpriced":
        market_bias = "SELL_BIAS"
    elif mispricing_result["classification"] == "underpriced":
        market_bias = "BUY_BIAS"
    else:
        market_bias = "NEUTRAL"
    
    # Determine signal direction based on market bias
    if market_bias == "BUY_BIAS":
        signal_direction = "LONG_SIGNAL"
    elif market_bias == "SELL_BIAS":
        signal_direction = "SHORT_SIGNAL"
    else:
        signal_direction = "NO_SIGNAL"
    
    # Determine strategy intent based on signal direction
    if signal_direction == "LONG_SIGNAL":
        strategy_intent = "ENTER_LONG_VOL"
    elif signal_direction == "SHORT_SIGNAL":
        strategy_intent = "ENTER_SHORT_VOL"
    else:
        strategy_intent = "WAIT_AND_WATCH"
    
    # Determine regime score for numeric representation
    if regime == "LOW_VOL":
        regime_score = 1
    elif regime == "NORMAL_VOL":
        regime_score = 2
    elif regime == "HIGH_VOL":
        regime_score = 3
    else:
        regime_score = 4
    
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
    if strategy_urgency == "HIGH":
        execution_profile = "AGGRESSIVE"
    elif strategy_urgency == "MEDIUM":
        execution_profile = "BALANCED"
    else:
        execution_profile = "PASSIVE"
    
    # Calculate signal priority score for sorting
    signal_priority_score = regime_score * confidence_score
    
    # Determine dashboard color hint for UI
    if market_bias == "BUY_BIAS":
        dashboard_color_hint = "GREEN"
    elif market_bias == "SELL_BIAS":
        dashboard_color_hint = "RED"
    else:
        dashboard_color_hint = "YELLOW"
    
    # Determine analytics stability
    if confidence_score >= 0.7 and pipeline_health == "OK":
        analytics_stability = "STABLE"
    elif confidence_score >= 0.4:
        analytics_stability = "WATCH"
    else:
        analytics_stability = "UNSTABLE"
    
    # Return clean structure for frontend consumption
    return {
        # Raw data (for data endpoints)
        "_data": data,
        "_data_with_returns": data_with_returns,
        # Analytics results
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
        "display_signal": display_signal,
        "execution_profile": execution_profile,
        "signal_priority_score": signal_priority_score,
        "dashboard_color_hint": dashboard_color_hint,
        "strategy_context": {
            "regime": regime,
            "volatility_context": analytics_summary["volatility_context"]
        },
        # Summary
        "analytics_summary": analytics_summary,
        "analytics_flags": analytics_flags,
        # Metadata
        "model_info": {
            "vol_model": "EGARCH(1,1)",
            "pricing_model": "Black-Scholes",
            "data_source": "yfinance"
        },
        "volatility_source": volatility_source,
        "analytics_version": "v1.1",
        "output_schema": "quant_pipeline_v1_locked",
        "analytics_timestamp": _utc_iso_timestamp(),
        "pipeline_health": pipeline_health,
        "analytics_health_score": analytics_health_score,
        "analytics_stability": analytics_stability,
        "pipeline_stage": {
            "data_ready": True,
            "volatility_computed": vol_forecast is not None,
            "pricing_computed": fair_price is not None,
            "strategy_generated": strategy_result is not None
        },
        "execution_time_ms": execution_time_ms
    }


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
    try:
        return build_success_response(METRICS)
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
def get_nifty_data(symbol: str = Query(default="NIFTY", min_length=1, max_length=20, description="Market symbol (e.g., NIFTY)")):
    start = time.perf_counter()
    record_request("/nifty")
    try:
        symbol = validate_symbol(symbol)
        pipeline = run_pipeline(symbol=symbol)
        payload = pipeline["_data"].tail().to_dict(orient="records")
        duration_ms = int((time.perf_counter() - start) * 1000)
        log_event({"timestamp": _utc_iso_timestamp(), "endpoint": "/nifty", "pipeline_health": "ok", "execution_time_ms": duration_ms})
        record_result("/nifty", "ok", duration_ms, None)
        return build_success_response(payload, meta={"execution_time_ms": duration_ms})
    except ValueError as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        log_event({"timestamp": _utc_iso_timestamp(), "endpoint": "/nifty", "pipeline_health": "error", "execution_time_ms": duration_ms, "error_message": str(e)})
        record_result("/nifty", "error", duration_ms, str(e))
        return error_json(str(e), status_code=400)
    except Exception as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        log_event({"timestamp": _utc_iso_timestamp(), "endpoint": "/nifty", "pipeline_health": "error", "execution_time_ms": duration_ms, "error_message": str(e)})
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
def get_log_returns(symbol: str = Query(default="NIFTY", min_length=1, max_length=20, description="Market symbol (e.g., NIFTY)")):
    start = time.perf_counter()
    record_request("/returns")
    try:
        symbol = validate_symbol(symbol)
        pipeline = run_pipeline(symbol=symbol)
        payload = pipeline["_data_with_returns"].to_dict(orient="records")
        duration_ms = int((time.perf_counter() - start) * 1000)
        log_event({"timestamp": _utc_iso_timestamp(), "endpoint": "/returns", "pipeline_health": "ok", "execution_time_ms": duration_ms})
        record_result("/returns", "ok", duration_ms, None)
        return build_success_response(payload, meta={"execution_time_ms": duration_ms})
    except ValueError as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        log_event({"timestamp": _utc_iso_timestamp(), "endpoint": "/returns", "pipeline_health": "error", "execution_time_ms": duration_ms, "error_message": str(e)})
        record_result("/returns", "error", duration_ms, str(e))
        return error_json(str(e), status_code=400)
    except Exception as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        log_event({"timestamp": _utc_iso_timestamp(), "endpoint": "/returns", "pipeline_health": "error", "execution_time_ms": duration_ms, "error_message": str(e)})
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
def get_forecast_volatility(symbol: str = Query(default="NIFTY", min_length=1, max_length=20, description="Market symbol (e.g., NIFTY)")):
    start = time.perf_counter()
    record_request("/forecast-vol")
    try:
        symbol = validate_symbol(symbol)
        pipeline = run_pipeline(symbol=symbol)
        payload = {"forecast_volatility": pipeline["forecast_volatility"]}
        duration_ms = int((time.perf_counter() - start) * 1000)
        log_event({"timestamp": _utc_iso_timestamp(), "endpoint": "/forecast-vol", "pipeline_health": "ok", "execution_time_ms": duration_ms})
        record_result("/forecast-vol", "ok", duration_ms, None)
        return build_success_response(payload, meta={"execution_time_ms": duration_ms})
    except ValueError as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        log_event({"timestamp": _utc_iso_timestamp(), "endpoint": "/forecast-vol", "pipeline_health": "error", "execution_time_ms": duration_ms, "error_message": str(e)})
        record_result("/forecast-vol", "error", duration_ms, str(e))
        return error_json(str(e), status_code=400)
    except Exception as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        log_event({"timestamp": _utc_iso_timestamp(), "endpoint": "/forecast-vol", "pipeline_health": "error", "execution_time_ms": duration_ms, "error_message": str(e)})
        record_result("/forecast-vol", "error", duration_ms, str(e))
        return error_json(str(e), status_code=500)

@app.get(
    "/fair-price",
    summary="Calculate Black-Scholes theoretical option fair value",
    description=(
        "Returns the theoretical fair value of an at-the-money call option computed via the Black-Scholes model. "
        "Accepts an optional `symbol` query parameter (default: NIFTY) for forward-compatibility. "
        "Volatility input is the EGARCH(1,1) forecast, not implied volatility. "
        "Time to expiry is expressed in years as required by the pricing model. "
        "This fair value serves as the benchmark for mispricing detection in the pipeline. "
        "Output is for research and analytical decision-support purposes only."
    ),
    tags=["Pipeline"],
    responses=_RESPONSES
)
def get_fair_price(symbol: str = Query(default="NIFTY", min_length=1, max_length=20, description="Market symbol (e.g., NIFTY)")):
    start = time.perf_counter()
    record_request("/fair-price")
    try:
        symbol = validate_symbol(symbol)
        pipeline = run_pipeline(symbol=symbol)
        payload = {"fair_price": pipeline["fair_price"]}
        duration_ms = int((time.perf_counter() - start) * 1000)
        log_event({"timestamp": _utc_iso_timestamp(), "endpoint": "/fair-price", "pipeline_health": "ok", "execution_time_ms": duration_ms})
        record_result("/fair-price", "ok", duration_ms, None)
        return build_success_response(payload, meta={"execution_time_ms": duration_ms})
    except ValueError as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        log_event({"timestamp": _utc_iso_timestamp(), "endpoint": "/fair-price", "pipeline_health": "error", "execution_time_ms": duration_ms, "error_message": str(e)})
        record_result("/fair-price", "error", duration_ms, str(e))
        return error_json(str(e), status_code=400)
    except Exception as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        log_event({"timestamp": _utc_iso_timestamp(), "endpoint": "/fair-price", "pipeline_health": "error", "execution_time_ms": duration_ms, "error_message": str(e)})
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
def get_mispricing(symbol: str = Query(default="NIFTY", min_length=1, max_length=20, description="Market symbol (e.g., NIFTY)")):
    start = time.perf_counter()
    record_request("/mispricing")
    try:
        symbol = validate_symbol(symbol)
        pipeline = run_pipeline(symbol=symbol)
        payload = {
            "fair_price": pipeline["fair_price"],
            "market_price": pipeline["market_price"],
            "mispricing": pipeline["mispricing"]
        }
        duration_ms = int((time.perf_counter() - start) * 1000)
        log_event({"timestamp": _utc_iso_timestamp(), "endpoint": "/mispricing", "pipeline_health": "ok", "execution_time_ms": duration_ms})
        record_result("/mispricing", "ok", duration_ms, None)
        return build_success_response(payload, meta={"execution_time_ms": duration_ms})
    except ValueError as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        log_event({"timestamp": _utc_iso_timestamp(), "endpoint": "/mispricing", "pipeline_health": "error", "execution_time_ms": duration_ms, "error_message": str(e)})
        record_result("/mispricing", "error", duration_ms, str(e))
        return error_json(str(e), status_code=400)
    except Exception as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        log_event({"timestamp": _utc_iso_timestamp(), "endpoint": "/mispricing", "pipeline_health": "error", "execution_time_ms": duration_ms, "error_message": str(e)})
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
def get_regime(symbol: str = Query(default="NIFTY", min_length=1, max_length=20, description="Market symbol (e.g., NIFTY)")):
    start = time.perf_counter()
    record_request("/regime")
    try:
        symbol = validate_symbol(symbol)
        pipeline = run_pipeline(symbol=symbol)
        payload = {
            "forecast_volatility": pipeline["forecast_volatility"],
            "regime": pipeline["regime"]
        }
        duration_ms = int((time.perf_counter() - start) * 1000)
        log_event({"timestamp": _utc_iso_timestamp(), "endpoint": "/regime", "pipeline_health": "ok", "execution_time_ms": duration_ms})
        record_result("/regime", "ok", duration_ms, None)
        return build_success_response(payload, meta={"execution_time_ms": duration_ms})
    except ValueError as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        log_event({"timestamp": _utc_iso_timestamp(), "endpoint": "/regime", "pipeline_health": "error", "execution_time_ms": duration_ms, "error_message": str(e)})
        record_result("/regime", "error", duration_ms, str(e))
        return error_json(str(e), status_code=400)
    except Exception as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        log_event({"timestamp": _utc_iso_timestamp(), "endpoint": "/regime", "pipeline_health": "error", "execution_time_ms": duration_ms, "error_message": str(e)})
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
        "Returns a consolidated response including spot price, forecasted volatility, fair value, "
        "mispricing classification, regime label, strategy suggestion, and analytics metadata. "
        "This is a research and decision-support tool; outputs do not constitute automated trading signals."
    ),    tags=["Pipeline"],    responses=_RESPONSES
)
def get_strategy(symbol: str = Query(default="NIFTY", min_length=1, max_length=20, description="Market symbol (e.g., NIFTY)")):
    start = time.perf_counter()
    record_request("/strategy")
    try:
        symbol = validate_symbol(symbol)
        result = run_pipeline(symbol=symbol)
        duration_ms = int((time.perf_counter() - start) * 1000)
        log_event({
            "timestamp": _utc_iso_timestamp(),
            "endpoint": "/strategy",
            "pipeline_health": "ok",
            "execution_time_ms": duration_ms
        })
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
            "pipeline_health": result.get("pipeline_health"),
            "execution_time_ms": result.get("execution_time_ms")
        }, meta={"execution_time_ms": duration_ms})

    except ValueError as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        log_event({
            "timestamp": _utc_iso_timestamp(),
            "endpoint": "/strategy",
            "pipeline_health": "error",
            "execution_time_ms": duration_ms,
            "error_message": str(e)
        })
        record_result("/strategy", "error", duration_ms, str(e))
        return error_json(str(e), status_code=400)
    except Exception as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        log_event({
            "timestamp": _utc_iso_timestamp(),
            "endpoint": "/strategy",
            "pipeline_health": "error",
            "execution_time_ms": duration_ms,
            "error_message": str(e)
        })
        record_result("/strategy", "error", duration_ms, str(e))
        raise HTTPException(status_code=500, detail=str(e))