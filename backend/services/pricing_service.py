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
    option_type: str
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
    # Calculate d1 and d2
    d1 = (np.log(spot / strike) + (risk_free_rate + 0.5 * volatility**2) * time_to_expiry) / (volatility * np.sqrt(time_to_expiry))
    d2 = d1 - volatility * np.sqrt(time_to_expiry)
    
    # Calculate option price based on type
    if option_type.lower() == "call":
        price = spot * norm.cdf(d1) - strike * np.exp(-risk_free_rate * time_to_expiry) * norm.cdf(d2)
    elif option_type.lower() == "put":
        price = strike * np.exp(-risk_free_rate * time_to_expiry) * norm.cdf(-d2) - spot * norm.cdf(-d1)
    else:
        raise ValueError(f"Invalid option_type: {option_type}. Must be 'call' or 'put'.")
    
    return float(price)
