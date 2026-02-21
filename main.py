from fastapi import FastAPI
import yfinance as yf
from backend.services.data_service import fetch_nifty_data, compute_log_returns
from backend.services.volatility_service import forecast_volatility
from backend.services.pricing_service import black_scholes_price
from backend.services.mispricing_service import detect_mispricing
from backend.services.regime_service import classify_volatility_regime
from backend.services.strategy_service import generate_strategy

app = FastAPI()

@app.get("/")
def root():
    return {"status": "running"}

@app.get("/nifty")
def get_nifty_data():
    data = yf.download("^NSEI", period="5d")

    # 🔧 Flatten columns (fix MultiIndex problem)
    data.columns = [col[0] if isinstance(col, tuple) else col for col in data.columns]

    # Convert index to string for JSON
    data.reset_index(inplace=True)
    data["Date"] = data["Date"].astype(str)

    return data.tail().to_dict(orient="records")

@app.get("/returns")
def get_log_returns():
    data = fetch_nifty_data()
    data_with_returns = compute_log_returns(data)
    return data_with_returns.to_dict(orient="records")

@app.get("/forecast-vol")
def get_forecast_volatility():
    data = fetch_nifty_data()
    data_with_returns = compute_log_returns(data)
    vol_forecast = forecast_volatility(data_with_returns["log_return"])
    return {"forecast_volatility": vol_forecast}

@app.get("/fair-price")
def get_fair_price():
    data = fetch_nifty_data()
    data_with_returns = compute_log_returns(data)
    vol_forecast = forecast_volatility(data_with_returns["log_return"])
    
    # Use latest Close price as spot
    spot = float(data_with_returns["Close"].iloc[-1])
    
    # Placeholder values
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
    
    return {"fair_price": fair_price}

@app.get("/mispricing")
def get_mispricing():
    data = fetch_nifty_data()
    data_with_returns = compute_log_returns(data)
    vol_forecast = forecast_volatility(data_with_returns["log_return"])
    
    # Use latest Close price as spot
    spot = float(data_with_returns["Close"].iloc[-1])
    
    # Placeholder values
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
    
    # Simulate market price
    market_price = fair_price * 1.03
    
    # Detect mispricing
    mispricing_result = detect_mispricing(market_price, fair_price)
    
    return {
        "fair_price": fair_price,
        "market_price": market_price,
        "mispricing": mispricing_result
    }

@app.get("/regime")
def get_regime():
    data = fetch_nifty_data()
    data_with_returns = compute_log_returns(data)
    vol_forecast = forecast_volatility(data_with_returns["log_return"])
    
    # Classify volatility regime
    regime = classify_volatility_regime(vol_forecast)
    
    return {
        "forecast_volatility": vol_forecast,
        "regime": regime
    }

@app.get("/strategy")
def get_strategy():
    # Execute full pipeline
    data = fetch_nifty_data()
    data_with_returns = compute_log_returns(data)
    vol_forecast = forecast_volatility(data_with_returns["log_return"])
    
    # Use latest Close price as spot
    spot = float(data_with_returns["Close"].iloc[-1])
    
    # Placeholder values
    strike = spot
    time_to_expiry = 0.05
    risk_free_rate = 0.06
    option_type = "call"
    
    # Calculate fair price
    fair_price = black_scholes_price(
        spot=spot,
        strike=strike,
        time_to_expiry=time_to_expiry,
        risk_free_rate=risk_free_rate,
        volatility=vol_forecast,
        option_type=option_type
    )
    
    # Simulate market price
    market_price = fair_price * 1.03
    
    # Detect mispricing
    mispricing_result = detect_mispricing(market_price, fair_price)
    
    # Classify regime
    regime = classify_volatility_regime(vol_forecast)
    
    # Generate strategy
    strategy_result = generate_strategy(
        mispricing_result["classification"],
        regime
    )
    
    return {
        "volatility": vol_forecast,
        "regime": regime,
        "mispricing": mispricing_result,
        "strategy": strategy_result
    }