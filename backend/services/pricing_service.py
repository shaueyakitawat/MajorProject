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
    expected_vrp: float | None = None,
    use_adjusted_vol: bool = True
) -> float:
    """
    Calculate theoretical option price using Black-Scholes model.
    """
    sigma = volatility
    if use_adjusted_vol and expected_vrp is not None and np.isfinite(expected_vrp):
        sigma = volatility + expected_vrp

    if time_to_expiry <= 0 or sigma <= 0 or spot <= 0 or strike <= 0:
        return 0.0

    d1 = (np.log(spot / strike) + (risk_free_rate + 0.5 * sigma**2) * time_to_expiry) / (sigma * np.sqrt(time_to_expiry))
    d2 = d1 - sigma * np.sqrt(time_to_expiry)

    if option_type.lower() == "call":
        price = spot * norm.cdf(d1) - strike * np.exp(-risk_free_rate * time_to_expiry) * norm.cdf(d2)
    elif option_type.lower() == "put":
        price = strike * np.exp(-risk_free_rate * time_to_expiry) * norm.cdf(-d2) - spot * norm.cdf(-d1)
    else:
        raise ValueError(f"Invalid option_type: {option_type}. Must be 'call' or 'put'.")
    
    return float(price)


def calculate_greeks(
    spot: float,
    strike: float,
    time_to_expiry: float,
    risk_free_rate: float,
    volatility: float,
    option_type: str = "call"
) -> dict[str, float]:
    """
    Calculate analytical Black-Scholes Greeks: Delta, Gamma, Theta, Vega.
    """
    if time_to_expiry <= 0 or volatility <= 0 or spot <= 0 or strike <= 0:
        return {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0}

    sigma = volatility
    d1 = (np.log(spot / strike) + (risk_free_rate + 0.5 * sigma**2) * time_to_expiry) / (sigma * np.sqrt(time_to_expiry))
    d2 = d1 - sigma * np.sqrt(time_to_expiry)

    pdf_d1 = norm.pdf(d1)

    # Gamma (same for Call and Put)
    gamma = pdf_d1 / (spot * sigma * np.sqrt(time_to_expiry))

    # Vega (same for Call and Put, per 1% vol change)
    vega = (spot * pdf_d1 * np.sqrt(time_to_expiry)) / 100.0

    if option_type.lower() == "call":
        delta = norm.cdf(d1)
        theta = (- (spot * pdf_d1 * sigma) / (2 * np.sqrt(time_to_expiry))
                 - risk_free_rate * strike * np.exp(-risk_free_rate * time_to_expiry) * norm.cdf(d2)) / 365.0
    else:
        delta = norm.cdf(d1) - 1.0
        theta = (- (spot * pdf_d1 * sigma) / (2 * np.sqrt(time_to_expiry))
                 + risk_free_rate * strike * np.exp(-risk_free_rate * time_to_expiry) * norm.cdf(-d2)) / 365.0

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
        diff_sec = (exp_dt - current_time).total_seconds()
        diff_sec = max(900.0, diff_sec)  # Floor at 15 minutes
        return float(diff_sec / (365.25 * 86400.0))
    except Exception:
        return 7.0 / 365.0

