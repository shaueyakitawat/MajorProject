"""
================================================================================
QUANT PIPELINE FINALIZED — DO NOT MODIFY CORE LOGIC.
Future changes should focus only on API formatting or frontend integration.
================================================================================
"""

import json
import logging
import math
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
from backend.infrastructure.timeframe_config import (
    validate_timeframe,
    get_default_timeframe_for_horizon
)
from backend.infrastructure.timeframe_adapter import normalize_timeframe_dataframe
from backend.infrastructure.annualization_engine import apply_dynamic_annualization

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
def run_pipeline(input_data: dict = None, symbol: str = "NIFTY", trading_horizon: str = None, timeframe: str = "daily"):
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
    
    # Start performance timer
    start_time = time.perf_counter()
    
    # Broker adapter integration placeholders
    option_expiry_date = None  # broker adapter will populate later
    
    # Step 1: Fetch and prepare data
    data = fetch_nifty_data()
    # Safety guard: current data_service still returns daily candles
    if timeframe in ["1m", "5m", "15m", "1h"]:
        log_event({
            "warning": "intraday_timeframe_requested_but_daily_data_source",
            "timeframe": timeframe
        })
    
    # Normalize dataframe structure for timeframe consistency
    data = normalize_timeframe_dataframe(data, timeframe)
    
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
    
    # Apply dynamic annualization to convert period volatility to annualized terms
    vol_forecast = apply_dynamic_annualization(vol_forecast, timeframe)
    
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
    
    # Trading horizon interpretation (influences volatility perception without altering EGARCH)
    horizon_multiplier = 1.0
    horizon_interpretation = "standard"
    
    if trading_horizon == "day_trader":
        # Day traders: emphasize short-term volatility, higher sensitivity
        horizon_multiplier = 1.15
        horizon_interpretation = "short_term_sensitive"
    elif trading_horizon == "positional":
        # Positional traders: balanced medium-term view
        horizon_multiplier = 1.0
        horizon_interpretation = "medium_term_balanced"
    elif trading_horizon == "long_term":
        # Long-term investors: dampen short-term noise
        horizon_multiplier = 0.85
        horizon_interpretation = "long_term_smoothed"
    
    # Apply horizon-adjusted interpretation to safe_volatility
    horizon_adjusted_volatility = safe_volatility * horizon_multiplier
    
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
    
    # Apply expiry-adjusted volatility scaling using horizon-adjusted volatility
    expiry_volatility = horizon_adjusted_volatility * (time_to_expiry_years ** 0.5)
    
    # Volatility transformation metadata for transparency
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
    # Determine regime score for numeric representation
    if regime == "LOW_VOL":
        regime_score = 1
    elif regime == "NORMAL_VOL":
        regime_score = 2
    elif regime == "HIGH_VOL":
        regime_score = 3
    else:
        regime_score = 4
    
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
    # Normalize historical std to annualized scale
    rolling_std = returns_series.std() * (252 ** 0.5)
    
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
    # Calculate signal priority score early so downstream analytics can use it
    signal_priority_score = regime_score * confidence_score
    
    # Compute quantitative diagnostics for research interpretability
    # Metric 1: Volatility change ratio (forecast vs historical rolling volatility)
    volatility_change_ratio = round(vol_forecast / rolling_std, 4) if rolling_std > 0 else 1.0
    
    # Metric 2: Signal strength normalized to [0, 1] scale using empirical threshold
    signal_strength_normalized = round(min(1.0, signal_strength / 0.5), 4)
    
    # Metric 3: Regime confidence estimate based on distance from regime boundaries
    # Regime boundaries: LOW < 0.15, NORMAL [0.15, 0.25), HIGH [0.25, 0.40), EXTREME >= 0.40
    if regime == "LOW_VOL":
        # Distance from upper boundary (0.15)
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
    
    regime_confidence_estimate = round(min(1.0, distance_from_boundary / (regime_width / 2)), 4)
    
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
    
    # Check 3: Regime label must match volatility threshold logic from regime_service
    # Regime boundaries: LOW < 0.15, NORMAL [0.15, 0.25), HIGH [0.25, 0.40), EXTREME >= 0.40
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
    
    # Check 4: Signal consistency - mispricing classification aligns with deviation
    signal_valid = True
    deviation = mispricing_result.get("deviation", 0)
    classification = mispricing_result.get("classification", "")
    
    if classification == "overpriced" and deviation <= 0.05:
        signal_valid = False
    elif classification == "underpriced" and deviation >= -0.05:
        signal_valid = False
    elif classification == "fair" and (deviation > 0.05 or deviation < -0.05):
        signal_valid = False
    
    quant_validation = {
        "volatility_valid": volatility_valid,
        "pricing_valid": pricing_valid,
        "regime_valid": regime_valid,
        "signal_valid": signal_valid
    }
    
    # Compute quant_stability_score from existing diagnostics and validation
    # Combine: volatility validity, pricing integrity, signal strength
    # Each validation contributes equally to base score
    validation_score = sum([
        1.0 if volatility_valid else 0.0,
        1.0 if pricing_valid else 0.0,
        1.0 if signal_valid else 0.0
    ]) / 3.0  # Average of 3 key validations
    
    # Weight by signal strength normalized (0-1) to factor in signal quality
    quant_stability_score = round(validation_score * signal_strength_normalized, 4)
    
    # Determine status based on score thresholds
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
    volatility_focus_map = {
        "day_trader": "short_memory",
        "positional": "medium_memory",
        "long_term": "long_memory",
        None: "standard"
    }
    
    horizon_context = {
        "horizon": trading_horizon,
        "volatility_focus": volatility_focus_map.get(trading_horizon, "standard")
    }
    
    # Compute sensitivity indicators using existing fair_price and volatility values
    # Indicator 1: Fair value to volatility ratio (price sensitivity to vol changes)
    fair_value_volatility_ratio = round(fair_price / vol_forecast, 4) if vol_forecast > 0 else 0.0
    
    # Indicator 2: Mispricing adjusted for volatility regime
    # Normalizes mispricing deviation by volatility level to account for regime context
    mispricing_deviation = mispricing_result.get("deviation", 0)
    mispricing_adjusted_for_volatility = round(mispricing_deviation / vol_forecast, 4) if vol_forecast > 0 else 0.0
    
    sensitivity_indicators = {
        "fair_value_volatility_ratio": fair_value_volatility_ratio,
        "mispricing_adjusted_for_volatility": mispricing_adjusted_for_volatility
    }
    
    # Volatility behavior insights using existing volatility and regime values
    # Insight 1: Volatility direction derived from volatility_context
    if volatility_context == "EXPANDING_VOL":
        volatility_direction = "EXPANDING"
    elif volatility_context == "CONTRACTING_VOL":
        volatility_direction = "CONTRACTING"
    else:
        volatility_direction = "STABLE"
    
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
    mispricing_deviation_abs = abs(mispricing_result.get("deviation", 0))
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
    # Metric 1: Horizon risk bias (risk appetite by horizon)
    if trading_horizon == "day_trader":
        horizon_risk_bias = "HIGH_RISK"  # Day traders accept higher risk for quick gains
    elif trading_horizon == "positional":
        horizon_risk_bias = "MODERATE_RISK"  # Positional traders balance risk-reward
    elif trading_horizon == "long_term":
        horizon_risk_bias = "LOW_RISK"  # Long-term investors prefer stability
    else:
        horizon_risk_bias = "NEUTRAL"  # No specific horizon bias
    
    # Metric 2: Horizon volatility weight (relative importance of volatility by horizon)
    # Day traders care most about volatility, long-term least
    if trading_horizon == "day_trader":
        horizon_volatility_weight = 0.85  # High weight on volatility movements
    elif trading_horizon == "positional":
        horizon_volatility_weight = 0.60  # Moderate weight
    elif trading_horizon == "long_term":
        horizon_volatility_weight = 0.35  # Lower weight, focus on fundamentals
    else:
        horizon_volatility_weight = 0.50  # Default balanced weight
    
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
    vol_percent = round(vol_forecast * 100, 2)
    if regime == "LOW_VOL":
        volatility_explanation = (
            f"The current volatility forecast of {vol_percent}% indicates a LOW volatility regime. "
            "This suggests a calm market environment with relatively stable price movements. "
            "Options are typically cheaper in low volatility conditions."
        )
    elif regime == "NORMAL_VOL":
        volatility_explanation = (
            f"The current volatility forecast of {vol_percent}% indicates a NORMAL volatility regime. "
            "This represents typical market conditions with moderate price fluctuations. "
            "Option pricing reflects standard risk-reward parameters."
        )
    elif regime == "HIGH_VOL":
        volatility_explanation = (
            f"The current volatility forecast of {vol_percent}% indicates a HIGH volatility regime. "
            "This suggests elevated market uncertainty with significant price swings. "
            "Options are more expensive, reflecting increased risk."
        )
    else:  # EXTREME_VOL
        volatility_explanation = (
            f"The current volatility forecast of {vol_percent}% indicates an EXTREME volatility regime. "
            "This represents exceptional market stress with very large price movements. "
            "Options are considerably more expensive due to heightened risk."
        )
    
    # Explanation 2: Mispricing implication
    mispricing_pct = round(mispricing_result["deviation"] * 100, 2)
    classification = mispricing_result["classification"]
    
    if classification == "overpriced":
        mispricing_explanation = (
            f"The option is trading {abs(mispricing_pct)}% above its theoretical fair value, "
            "indicating it is OVERPRICED. This suggests a potential selling opportunity, "
            "as the market premium exceeds the model's valuation."
        )
    elif classification == "underpriced":
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
    if classification == "overpriced":
        mispricing_reason = "Since the option is OVERPRICED relative to fair value, strategies that sell premium or avoid buying are preferred."
    elif classification == "underpriced":
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
    
    # Create quant_summary for high-level frontend readability
    # Extract key signals from existing analytics without new computations
    quant_summary = {
        "regime": regime,
        "mispricing_classification": classification,
        "horizon": trading_horizon if trading_horizon else "not_specified",
        "strategy_intent": strategy_intent,
        "signal_direction": signal_direction,
        "quant_stability_status": stability_status
    }
    
    # Create decision_snapshot - compact summary of key decision outputs
    decision_snapshot = {
        "regime": regime,
        "mispricing_classification": classification,
        "strategy_name": strategy_result.get("strategy", "No strategy"),
        "signal_direction": signal_direction,
        "horizon": trading_horizon if trading_horizon else "not_specified"
    }
    
    # Generate research_tags based on existing analytics values
    research_tags = []
    
    # Volatility behavior tags
    if volatility_direction == "EXPANDING":
        research_tags.append("VOLATILITY_EXPANSION")
    elif volatility_direction == "CONTRACTING":
        research_tags.append("VOLATILITY_CONTRACTION")
    
    # Mispricing tags
    if classification != "fair":
        research_tags.append("MISPRICING_SIGNAL")
    if classification == "overpriced":
        research_tags.append("OVERPRICED_SIGNAL")
    elif classification == "underpriced":
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
    
    # Check 3: Regime matches volatility range
    # Regime boundaries: LOW < 0.15, NORMAL [0.15, 0.25), HIGH [0.25, 0.40), EXTREME >= 0.40
    regime_consistency = True
    if regime == "LOW_VOL" and vol_forecast >= 0.15:
        regime_consistency = False
    elif regime == "NORMAL_VOL" and (vol_forecast < 0.15 or vol_forecast >= 0.25):
        regime_consistency = False
    elif regime == "HIGH_VOL" and (vol_forecast < 0.25 or vol_forecast >= 0.40):
        regime_consistency = False
    elif regime == "EXTREME_VOL" and vol_forecast < 0.40:
        regime_consistency = False
    
    if not regime_consistency:
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
        "execution_time_ms": execution_time_ms,
        
        # ========== RAW DATA ==========
        "_data": data.tail(50),
        "_data_with_returns": data_with_returns.tail(50)
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
def get_nifty_data(
    symbol: str = Query(default="NIFTY", min_length=1, max_length=20, description="Market symbol (e.g., NIFTY)"),
    timeframe: str = Query(default=None, description="Supported timeframes: 1m, 5m, 15m, 1h, daily, weekly")
):
    start = time.perf_counter()
    record_request("/nifty")
    try:
        symbol = validate_symbol(symbol)
        pipeline = run_pipeline(symbol=symbol, timeframe=timeframe)
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
        "Accepts an optional `trading_horizon` parameter (day_trader, positional, long_term) to adjust volatility interpretation. "
        "Returns a consolidated response including spot price, forecasted volatility, fair value, "
        "mispricing classification, regime label, strategy suggestion, and analytics metadata. "
        "This is a research and decision-support tool; outputs do not constitute automated trading signals."
    ),    tags=["Pipeline"],    responses=_RESPONSES
)
def get_strategy(
    symbol: str = Query(default="NIFTY", min_length=1, max_length=20, description="Market symbol (e.g., NIFTY)"),
    trading_horizon: str = Query(default=None, description="Trading horizon: day_trader, positional, or long_term"),
    timeframe: str = Query(default=None, description="Supported timeframes: 1m, 5m, 15m, 1h, daily, weekly")
):
    start = time.perf_counter()
    record_request("/strategy")
    try:
        symbol = validate_symbol(symbol)
        result = run_pipeline(symbol=symbol, trading_horizon=trading_horizon, timeframe=timeframe)
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