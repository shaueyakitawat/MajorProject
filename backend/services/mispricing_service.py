# Mispricing Service
# Handles mispricing detection logic

import math
import os
from collections import deque
from typing import Deque


MSCORE_WEIGHTS = {
    "price_deviation": float(os.getenv("MSCORE_W1", "0.50")),
    "vega_component": float(os.getenv("MSCORE_W2", "0.15")),
    "gamma_component": float(os.getenv("MSCORE_W3", "0.15")),
    "tci": float(os.getenv("MSCORE_W4", "0.10")),
    "vrp_deviation": float(os.getenv("MSCORE_W5", "0.10")),
}
MSCORE_Z_WINDOW = int(os.getenv("MSCORE_Z_WINDOW", "60"))

_mscore_window: Deque[float] = deque(maxlen=MSCORE_Z_WINDOW)


def _finite_or_zero(value: float | None) -> float:
    if value is None:
        return 0.0
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    return parsed if math.isfinite(parsed) else 0.0


def _z_score(value: float) -> float:
    _mscore_window.append(value)
    if len(_mscore_window) < 2:
        return 0.0

    mean = sum(_mscore_window) / len(_mscore_window)
    variance = sum((item - mean) ** 2 for item in _mscore_window) / len(_mscore_window)
    std = math.sqrt(variance)

    if std <= 0 or not math.isfinite(std):
        return 0.0
    return (value - mean) / std


def detect_mispricing(
    market_price: float,
    fair_price: float,
    *,
    vega: float | None = None,
    gamma: float | None = None,
    tci: float | None = None,
    current_vrp: float | None = None,
    expected_vrp: float | None = None,
    weights: dict[str, float] | None = None
) -> dict:
    """
    Detect mispricing by comparing market price with Black-Scholes fair value.
    
    Args:
        market_price: Actual traded/quoted option price from market
        fair_price: Theoretical option price from Black-Scholes model
        vega: Existing option Vega value, if available
        gamma: Existing option Gamma value, if available
        tci: Timeframe Coherence Index from volatility service, if available
        current_vrp: Current volatility risk premium
        expected_vrp: Expected volatility risk premium
        weights: Optional MScore weights override
        
    Returns:
        dict: Contains legacy 'deviation' and 'classification' fields plus
              composite 'm_score' and normalized 'z_score' fields.
              Classification: "underpriced", "fair", or "overpriced"
    """
    if not math.isfinite(market_price) or not math.isfinite(fair_price) or fair_price <= 0:
        return {
            "deviation": 0.0,
            "classification": "fair",
            "m_score": 0.0,
            "z_score": 0.0,
        }

    deviation = (market_price - fair_price) / fair_price

    if deviation > 0.05:
        classification = "overpriced"
    elif deviation < -0.05:
        classification = "underpriced"
    else:
        classification = "fair"

    active_weights = MSCORE_WEIGHTS | (weights or {})
    price_deviation = float(deviation)
    vega_component = _finite_or_zero(vega)
    gamma_component = _finite_or_zero(gamma)
    tci_component = _finite_or_zero(tci)
    vrp_deviation = _finite_or_zero(current_vrp) - _finite_or_zero(expected_vrp)

    m_score = (
        active_weights["price_deviation"] * price_deviation +
        active_weights["vega_component"] * vega_component +
        active_weights["gamma_component"] * gamma_component +
        active_weights["tci"] * tci_component +
        active_weights["vrp_deviation"] * vrp_deviation
    )
    z_score = _z_score(m_score)
    
    return {
        "deviation": float(deviation),
        "classification": classification,
        "m_score": float(m_score),
        "z_score": float(z_score)
    }
