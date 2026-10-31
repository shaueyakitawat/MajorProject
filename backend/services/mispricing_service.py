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

    price_deviation = float(deviation)
    vega_component = _finite_or_zero(vega)
    gamma_component = _finite_or_zero(gamma)
    tci_component = _finite_or_zero(tci)
    vrp_deviation = _finite_or_zero(current_vrp) - _finite_or_zero(expected_vrp)

    active_weights = MSCORE_WEIGHTS | (weights or {})

    # Directional normalization: 5% price deviation = 1.0 unit
    norm_price_dev = price_deviation * 20.0
    # Normalized VRP deviation: 2% vol difference = 1.0 unit
    norm_vrp_dev = vrp_deviation * 50.0

    # Greeks are non-directional sensitivities (always >= 0).
    # To scale mispricing without corrupting the sign, multiply by the deviation sign:
    dev_sign = 1.0 if price_deviation > 0.001 else (-1.0 if price_deviation < -0.001 else 0.0)
    norm_vega = min(2.5, max(0.0, vega_component / 15.0))
    norm_gamma = min(2.5, max(0.0, gamma_component / 0.0003))

    vega_directional = dev_sign * norm_vega
    gamma_directional = dev_sign * norm_gamma
    tci_mult = (1.0 + (tci_component - 0.5) * 0.4) if tci_component > 0 else 1.0

    w_price = active_weights.get("price_deviation", 0.50)
    w_vrp = active_weights.get("vrp_deviation", 0.20)
    w_vega = active_weights.get("vega_component", 0.15)
    w_gamma = active_weights.get("gamma_component", 0.10)

    m_score = (
        (w_price * norm_price_dev +
         w_vrp * norm_vrp_dev +
         w_vega * vega_directional +
         w_gamma * gamma_directional) * tci_mult
    )

    # Strict sign-consistency guard: underpriced must be negative, overpriced must be positive
    if price_deviation < -0.03 and m_score > 0:
        m_score = -abs(m_score)
    elif price_deviation > 0.03 and m_score < 0:
        m_score = abs(m_score)

    if deviation > 0.05 or m_score >= 1.2:
        classification = "overpriced"
    elif deviation < -0.05 or m_score <= -1.2:
        classification = "underpriced"
    else:
        classification = "fair"

    z_score = _z_score(m_score)
    
    return {
        "deviation": float(deviation),
        "classification": classification,
        "m_score": float(m_score),
        "z_score": float(z_score)
    }
