"""
Implied Volatility Service
Back-solves Black-Scholes to find the market-implied volatility.
"""

import logging
from scipy.optimize import brentq
from backend.services.pricing_service import black_scholes_price

logger = logging.getLogger("api")


def calculate_implied_volatility(
    S: float,
    K: float,
    T: float,
    r: float,
    market_price: float,
    option_type: str = "call",
    dividend_yield: float = 0.0125
) -> float | None:
    """
    Calculate implied volatility by solving BS(vol) - market_price = 0.
    Robustly handles sub-intrinsic, extreme OTM, and boundary quotes without throwing bracket exceptions.

    Args:
        S: Spot price
        K: Strike price
        T: Time to expiry in years
        r: Risk-free rate (decimal)
        market_price: Observed market option price (LTP or mid)
        option_type: "call" or "put"
        dividend_yield: Dividend yield (decimal)

    Returns:
        float: Implied volatility as decimal (e.g. 0.20 = 20%), or None if solver fails
    """
    if market_price <= 0 or S <= 0 or K <= 0 or T <= 0:
        return None

    import math

    # Analytical arbitrage boundary checks
    df_r = math.exp(-r * T)
    df_q = math.exp(-dividend_yield * T)
    is_call = option_type.lower() == "call"

    if is_call:
        intrinsic = max(0.0, S * df_q - K * df_r)
        upper_bound = S * df_q
    else:
        intrinsic = max(0.0, K * df_r - S * df_q)
        upper_bound = K * df_r

    # Sub-intrinsic quote (negative or zero extrinsic value) -> vol is at lower floor
    if market_price <= intrinsic + 1e-4:
        return 0.001

    # Price exceeds theoretical max -> vol is bounded at upper ceiling
    if market_price >= upper_bound - 1e-4:
        return 3.0

    def objective(vol: float) -> float:
        return black_scholes_price(
            spot=S,
            strike=K,
            time_to_expiry=T,
            risk_free_rate=r,
            volatility=vol,
            option_type=option_type,
            dividend_yield=dividend_yield
        ) - market_price

    f_low = objective(0.0001)
    f_high = objective(4.0)

    # Bracket check: f(a) and f(b) must have different signs for brentq
    if f_low * f_high > 0:
        if f_low > 0:
            return 0.001
        return 3.0

    try:
        iv = brentq(objective, 0.0001, 4.0, xtol=1e-5, maxiter=100)
        return float(iv)
    except Exception as e:
        logger.debug(f"IV solver fallback: {e}")
        return None


def classify_vol_spread(iv: float | None, egarch_vol: float) -> tuple[float | None, str]:
    """
    Compute vol spread and classify the IV signal.

    Args:
        iv: Implied volatility (decimal), or None
        egarch_vol: EGARCH forecasted volatility (decimal)

    Returns:
        tuple: (vol_spread, vol_signal)
    """
    if iv is None:
        return None, "IV_UNAVAILABLE"

    vol_spread = iv - egarch_vol

    if vol_spread > 0.05:
        return vol_spread, "IV_HIGH"
    elif vol_spread < -0.05:
        return vol_spread, "IV_LOW"
    else:
        return vol_spread, "IV_FAIR"
