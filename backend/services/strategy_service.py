# Strategy Service
# Handles strategy recommendation logic

import math
import os


VOL_EDGE_THRESHOLD = float(os.getenv("STRATEGY_VOL_EDGE_THRESHOLD", "0.03"))
Z_SCORE_THRESHOLD = float(os.getenv("STRATEGY_Z_SCORE_THRESHOLD", "1.0"))


def _finite(value: float | None) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _confidence(abs_z_score: float, abs_vol_edge: float) -> str:
    if abs_z_score >= 2.0 or abs_vol_edge >= 0.08:
        return "high"
    if abs_z_score >= 1.0 or abs_vol_edge >= 0.03:
        return "medium"
    return "low"


def _atm_label(atm_strike: float | None) -> str:
    strike = _finite(atm_strike)
    if strike is None:
        return "ATM"
    return f"ATM {strike:g}"


def generate_strategy(
    mispricing_label: str,
    regime_label: str,
    *,
    sigma_adj: float | None = None,
    iv: float | None = None,
    z_score: float | None = None,
    atm_strike: float | None = None
) -> dict:
    """
    Generate a structured, delta-neutral strategy recommendation.
    
    Args:
        mispricing_label: Mispricing classification - "underpriced", "fair", or "overpriced"
        regime_label: Volatility regime - "LOW_VOL", "NORMAL_VOL", "HIGH_VOL", or "EXTREME_VOL"
        sigma_adj: Adjusted/forecast volatility used for strategy comparison
        iv: Market implied volatility
        z_score: Normalized composite mispricing score
        atm_strike: Selected ATM strike for approximate delta-neutral structure
        
    Returns:
        dict: Structured JSON strategy suggestion
    """
    sigma = _finite(sigma_adj)
    implied_vol = _finite(iv)
    raw_score = _finite(z_score)
    score = raw_score if raw_score is not None else 0.0
    vol_edge = (sigma - implied_vol) if sigma is not None and implied_vol is not None else None
    abs_vol_edge = abs(vol_edge) if vol_edge is not None else 0.0
    abs_z_score = abs(score)
    quant_inputs_available = vol_edge is not None and raw_score is not None
    atm = _atm_label(atm_strike)

    long_vol_signal = (
        quant_inputs_available
        and vol_edge >= VOL_EDGE_THRESHOLD
        and score <= -Z_SCORE_THRESHOLD
    ) or (not quant_inputs_available and mispricing_label == "underpriced")
    short_vol_signal = (
        quant_inputs_available
        and vol_edge <= -VOL_EDGE_THRESHOLD
        and score >= Z_SCORE_THRESHOLD
    ) or (not quant_inputs_available and mispricing_label == "overpriced")

    if long_vol_signal and regime_label != "EXTREME_VOL":
        strategy_type = "LONG_VOLATILITY"
        structure_name = "long_straddle" if abs_z_score >= 1.5 else "long_strangle"
        strategy = "long volatility straddle/strangle"
        position_structure = {
            "delta_neutral_approximation": "ATM focus; buy one call and one put with similar expiry so call delta and put delta offset.",
            "primary": [
                {"action": "buy", "leg": "call", "strike": atm, "quantity": 1},
                {"action": "buy", "leg": "put", "strike": atm, "quantity": 1},
            ],
            "alternative": [
                {"action": "buy", "leg": "call", "strike": "slightly OTM", "quantity": 1},
                {"action": "buy", "leg": "put", "strike": "slightly OTM", "quantity": 1},
            ],
        }
        entry_condition = "Enter when sigma_adj exceeds IV and z_score is negative enough to indicate cheap optionality."
        exit_condition = "Exit on IV expansion, z_score mean reversion toward 0, target premium gain, or before expiry decay accelerates."
        risk_notes = [
            "Maximum loss is limited to net premium paid.",
            "Theta decay is adverse if spot remains near ATM and IV does not rise.",
            "Keep strikes near ATM to preserve an approximately delta-neutral starting point.",
        ]
    elif short_vol_signal:
        strategy_type = "SHORT_VOLATILITY"
        structure_name = "iron_condor" if regime_label in {"HIGH_VOL", "EXTREME_VOL"} else "short_straddle"
        strategy = "short volatility iron condor/short straddle"
        position_structure = {
            "delta_neutral_approximation": "ATM focus; sell balanced call and put exposure so initial directional delta is near zero.",
            "primary": [
                {"action": "sell", "leg": "call", "strike": atm, "quantity": 1},
                {"action": "sell", "leg": "put", "strike": atm, "quantity": 1},
            ],
            "risk_defined_alternative": [
                {"action": "buy", "leg": "put", "strike": "lower wing", "quantity": 1},
                {"action": "sell", "leg": "put", "strike": "lower OTM", "quantity": 1},
                {"action": "sell", "leg": "call", "strike": "upper OTM", "quantity": 1},
                {"action": "buy", "leg": "call", "strike": "upper wing", "quantity": 1},
            ],
        }
        entry_condition = "Enter when IV exceeds sigma_adj and z_score is positive enough to indicate rich optionality."
        exit_condition = "Exit on IV compression, z_score mean reversion toward 0, 50-70% premium capture, or breach of short strikes."
        risk_notes = [
            "Short straddles carry large tail risk; prefer iron condor wings when volatility regime is high or extreme.",
            "Gamma risk increases close to expiry and around fast spot moves.",
            "Rebalance or reduce exposure if net delta drifts materially from neutral.",
        ]
    else:
        strategy_type = "NO_TRADE"
        structure_name = "wait"
        strategy = "no delta-neutral volatility trade"
        position_structure = {
            "delta_neutral_approximation": "No new position; monitor ATM call/put pair for a cleaner volatility edge.",
            "primary": [],
        }
        entry_condition = "Wait until sigma_adj vs IV and z_score align with either long-vol or short-vol conditions."
        exit_condition = "No active trade to exit."
        risk_notes = [
            "Signal is not strong enough for a structured volatility position.",
            "Avoid forcing a delta-neutral trade when volatility edge and z_score disagree.",
        ]

    return {
        "strategy": strategy,
        "strategy_type": strategy_type,
        "structure_name": structure_name,
        "confidence": _confidence(abs_z_score, abs_vol_edge),
        "position_structure": position_structure,
        "entry_condition": entry_condition,
        "exit_condition": exit_condition,
        "risk_notes": risk_notes,
        "delta_neutral": {
            "method": "ATM approximation",
            "target_net_delta": 0.0,
            "rebalance_trigger": "Recheck when spot moves away from ATM or net delta becomes directional.",
        },
        "signal_inputs": {
            "sigma_adj": sigma,
            "iv": implied_vol,
            "vol_edge": vol_edge,
            "z_score": score,
            "mispricing_label": mispricing_label,
            "regime_label": regime_label,
        },
    }
