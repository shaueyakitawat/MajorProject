# Pricing Service
# Handles Black-Scholes option pricing and Greeks calculation

import numpy as np
from scipy.stats import norm


def black_scholes_price(
    spot: float,
    strike: float,
    time_to_expiry: float,
    risk_free_rate: float,
    volatility: float,
    option_type: str,
    dividend_yield: float = 0.0125,
    expected_vrp: float | None = None,
    use_adjusted_vol: bool = True
) -> float:
    """
    Calculate theoretical option price using Black-Scholes-Merton model with continuous dividend yield.
    """
    sigma = volatility
    if use_adjusted_vol and expected_vrp is not None and np.isfinite(expected_vrp):
        sigma = volatility + expected_vrp

    if spot <= 0 or strike <= 0:
        return 0.0

    if time_to_expiry <= 0 or sigma <= 0:
        # At expiration (T<=0) or zero vol, price is intrinsic value
        if option_type.lower() == "call":
            return float(max(0.0, spot - strike))
        elif option_type.lower() == "put":
            return float(max(0.0, strike - spot))
        return 0.0

    q = dividend_yield
    r = risk_free_rate
    sqrt_t = max(1e-5, np.sqrt(time_to_expiry))

    d1 = (np.log(spot / strike) + (r - q + 0.5 * sigma**2) * time_to_expiry) / (sigma * sqrt_t)
    d2 = d1 - sigma * sqrt_t

    df_q = np.exp(-q * time_to_expiry)
    df_r = np.exp(-r * time_to_expiry)

    if option_type.lower() == "call":
        price = spot * df_q * norm.cdf(d1) - strike * df_r * norm.cdf(d2)
    elif option_type.lower() == "put":
        price = strike * df_r * norm.cdf(-d2) - spot * df_q * norm.cdf(-d1)
    else:
        raise ValueError(f"Invalid option_type: {option_type}. Must be 'call' or 'put'.")
    
    return float(max(0.0, price))


def calculate_greeks(
    spot: float,
    strike: float,
    time_to_expiry: float,
    risk_free_rate: float,
    volatility: float,
    option_type: str = "call",
    dividend_yield: float = 0.0125
) -> dict[str, float]:
    """
    Calculate analytical Black-Scholes-Merton Greeks: Delta, Gamma, Theta, Vega with dividend yield.
    """
    if time_to_expiry <= 0 or volatility <= 0 or spot <= 0 or strike <= 0:
        return {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0}

    sigma = volatility
    q = dividend_yield
    r = risk_free_rate
    sqrt_t = max(1e-5, np.sqrt(time_to_expiry))

    d1 = (np.log(spot / strike) + (r - q + 0.5 * sigma**2) * time_to_expiry) / (sigma * sqrt_t)
    d2 = d1 - sigma * sqrt_t

    pdf_d1 = norm.pdf(d1)
    df_q = np.exp(-q * time_to_expiry)
    df_r = np.exp(-r * time_to_expiry)

    # Gamma (same for Call and Put)
    gamma = (df_q * pdf_d1) / (spot * sigma * sqrt_t)

    # Vega (same for Call and Put, per 1% vol change)
    vega = (spot * df_q * pdf_d1 * sqrt_t) / 100.0

    if option_type.lower() == "call":
        delta = df_q * norm.cdf(d1)
        theta = (- (spot * df_q * pdf_d1 * sigma) / (2 * sqrt_t)
                 - r * strike * df_r * norm.cdf(d2)
                 + q * spot * df_q * norm.cdf(d1)) / 365.0
    else:
        delta = df_q * (norm.cdf(d1) - 1.0)
        theta = (- (spot * df_q * pdf_d1 * sigma) / (2 * sqrt_t)
                 + r * strike * df_r * norm.cdf(-d2)
                 - q * spot * df_q * norm.cdf(-d1)) / 365.0

    return {
        "delta": float(delta),
        "gamma": float(gamma),
        "theta": float(theta),
        "vega": float(vega),
    }


def calculate_ttm_years(expiry_date: str, current_time=None) -> float:
    """
    Calculate annualized time-to-maturity (TTM) in years.
    NSE options expire at 15:30 IST on the expiration date.
    Enforces a realistic minimum TTM (15 minutes = ~0.000028y) to prevent singularity.
    Harmonizes timezone awareness between naive and aware datetime inputs.
    """
    import datetime as _dt
    import dateutil.parser as _dp

    if current_time is None:
        current_time = _dt.datetime.now()

    try:
        if isinstance(expiry_date, str):
            exp_dt = _dp.parse(expiry_date)
        elif isinstance(expiry_date, _dt.date) and not isinstance(expiry_date, _dt.datetime):
            exp_dt = _dt.datetime.combine(expiry_date, _dt.time(15, 30))
        else:
            exp_dt = expiry_date

        exp_dt = exp_dt.replace(hour=15, minute=30, second=0, microsecond=0)

        # Harmonize timezone offset: strip tzinfo if one is naive and other is aware
        if hasattr(exp_dt, "tzinfo") and hasattr(current_time, "tzinfo"):
            if (exp_dt.tzinfo is not None) != (current_time.tzinfo is not None):
                exp_dt = exp_dt.replace(tzinfo=None)
                current_time = current_time.replace(tzinfo=None)

        diff_sec = (exp_dt - current_time).total_seconds()
        diff_sec = max(900.0, diff_sec)  # Floor at 15 minutes
        return float(diff_sec / (365.25 * 86400.0))
    except Exception:
        return 7.0 / 365.0

