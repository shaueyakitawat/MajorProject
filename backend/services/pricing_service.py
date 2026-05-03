# Pricing Service
# Handles Black-Scholes option pricing

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
    
    Args:
        spot: Current spot price of the underlying asset
        strike: Strike price of the option
        time_to_expiry: Time to expiration in YEARS
        risk_free_rate: Risk-free interest rate (annualized, as decimal)
        volatility: Annualized volatility (as decimal, from forecast)
        option_type: "call" or "put"
        
    Returns:
        float: Theoretical option price (fair value)
    """
    sigma = volatility
    if use_adjusted_vol and expected_vrp is not None and np.isfinite(expected_vrp):
        sigma = volatility + expected_vrp

    d1 = (np.log(spot / strike) + (risk_free_rate + 0.5 * sigma**2) * time_to_expiry) / (sigma * np.sqrt(time_to_expiry))
    d2 = d1 - sigma * np.sqrt(time_to_expiry)

    if option_type.lower() == "call":
        price = spot * norm.cdf(d1) - strike * np.exp(-risk_free_rate * time_to_expiry) * norm.cdf(d2)
    elif option_type.lower() == "put":
        price = strike * np.exp(-risk_free_rate * time_to_expiry) * norm.cdf(-d2) - spot * norm.cdf(-d1)
    else:
        raise ValueError(f"Invalid option_type: {option_type}. Must be 'call' or 'put'.")
    
    return float(price)
