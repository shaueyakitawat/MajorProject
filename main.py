import time
from datetime import datetime
from fastapi import FastAPI, HTTPException
from backend.services.data_service import fetch_nifty_data, compute_log_returns
from backend.services.volatility_service import forecast_volatility
from backend.services.pricing_service import black_scholes_price
from backend.services.mispricing_service import detect_mispricing
from backend.services.regime_service import classify_volatility_regime
from backend.services.strategy_service import generate_strategy

app = FastAPI()


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


# Internal helper function for pipeline execution
def run_pipeline():
    """
    Execute the complete quantitative pipeline.
    
    Returns:
        dict: Complete analytics results with clean structure
    """
    # Start performance timer
    start_time = time.perf_counter()
    
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
    
    # Validation: Ensure volatility is positive and valid
    if vol_forecast <= 0 or not isinstance(vol_forecast, (int, float)):
        raise HTTPException(
            status_code=500,
            detail=f"Invalid volatility forecast: {vol_forecast}. Volatility must be positive."
        )
    
    # Normalize volatility to decimal format if needed
    if vol_forecast > 1:
        vol_forecast = vol_forecast / 100
    
    # Step 3: Extract spot price
    spot = float(data_with_returns["Close"].iloc[-1])
    
    # Validation: Ensure spot price is positive
    if spot <= 0:
        raise HTTPException(
            status_code=500,
            detail=f"Invalid spot price: {spot}. Spot price must be positive."
        )
    
    # Step 4: Calculate fair price (placeholder parameters)
    strike = spot
    time_to_expiry = 0.05
    risk_free_rate = 0.06
    option_type = "call"
    
    fair_price = black_scholes_price(
        spot=spot,
        strike=strike,
        time_to_expiry=time_to_expiry,
        risk_free_rate=risk_free_rate,
        volatility=vol_forecast,
        option_type=option_type
    )
    
    # Validation: Ensure fair price is valid
    if fair_price <= 0 or not isinstance(fair_price, (int, float)):
        raise HTTPException(
            status_code=500,
            detail=f"Invalid fair price calculation: {fair_price}. Price must be positive."
        )
    
    # Step 5: Simulate market price and detect mispricing
    market_price = fair_price * 1.03
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
        "market_price": market_price,
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

@app.get("/nifty")
def get_nifty_data():
    pipeline = run_pipeline()
    return create_response(pipeline["_data"].tail().to_dict(orient="records"))

@app.get("/returns")
def get_log_returns():
    pipeline = run_pipeline()
    return create_response(pipeline["_data_with_returns"].to_dict(orient="records"))

@app.get("/forecast-vol")
def get_forecast_volatility():
    pipeline = run_pipeline()
    return create_response({"forecast_volatility": pipeline["forecast_volatility"]})

@app.get("/fair-price")
def get_fair_price():
    pipeline = run_pipeline()
    return create_response({"fair_price": pipeline["fair_price"]})

@app.get("/mispricing")
def get_mispricing():
    pipeline = run_pipeline()
    return create_response({
        "fair_price": pipeline["fair_price"],
        "market_price": pipeline["market_price"],
        "mispricing": pipeline["mispricing"]
    })

@app.get("/regime")
def get_regime():
    pipeline = run_pipeline()
    return create_response({
        "forecast_volatility": pipeline["forecast_volatility"],
        "regime": pipeline["regime"]
    })

@app.get("/strategy")
def get_strategy():
    try:
        result = run_pipeline()
        
        return create_response({
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
        })
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))