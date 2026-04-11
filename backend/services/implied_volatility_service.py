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
    option_type: str = "call"
) -> float | None:
    """
    Calculate implied volatility by solving BS(vol) - market_price = 0.

    Args:
        S: Spot price
        K: Strike price
        T: Time to expiry in years
        r: Risk-free rate (decimal)
        market_price: Observed market option price (LTP or mid)
        option_type: "call" or "put"

    Returns:
        float: Implied volatility as decimal (e.g. 0.20 = 20%), or None if solver fails
    """
    if market_price <= 0 or S <= 0 or K <= 0 or T <= 0:
        logger.warning(
            f"IV calculation skipped: invalid inputs "
            f"(S={S}, K={K}, T={T}, market_price={market_price})"
        )
        return None

    def objective(vol: float) -> float:
        return black_scholes_price(
            spot=S,
            strike=K,
            time_to_expiry=T,
            risk_free_rate=r,
            volatility=vol,
            option_type=option_type
        ) - market_price

    try:
        iv = brentq(objective, 0.0001, 5.0, xtol=1e-6, maxiter=200)
        logger.info(f"IV solved: {iv:.4f} (S={S:.2f}, K={K:.2f}, T={T:.4f}, mkt={market_price:.2f})")
        return float(iv)
    except (ValueError, RuntimeError) as e:
        logger.warning(f"IV solver failed: {e}")
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
