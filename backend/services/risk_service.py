"""
backend/services/risk_service.py
================================================================================
Institutional Portfolio Risk, Scenario Stress-Testing & Greek Sensitivity Engine.
Evaluates portfolio exposure against spot shifts, volatility shocks, and time decay.
================================================================================
"""

import math
from typing import Dict, List, Any
from backend.services.trade_service import get_trades_overview
from backend.services.option_chain_service import get_spot_price


def get_portfolio_risk_report() -> Dict[str, Any]:
    """
    Computes real-time portfolio risk telemetry based on active open positions in SQLite.
    Includes Greek sensitivities, stress scenarios, and loss limits.
    """
    trades = get_trades_overview()
    active_positions = trades.get("active_positions", [])
    spot = get_spot_price("NIFTY") or 22936.75

    lot_size = 65
    port_delta = 0.0
    port_gamma = 0.0
    port_theta = 0.0
    port_vega = 0.0
    gross_notional = 0.0

    for pos in active_positions:
        side_mult = 1 if pos.get("side") == "BUY" else -1
        qty = pos.get("qty", lot_size)
        strike = pos.get("strike", spot)
        ltp = pos.get("current_price", pos.get("entry_price", 100.0))
        
        # Approximate Greeks based on moneyness if not stored directly
        moneyness = (spot - strike) / spot
        is_call = "CE" in pos.get("instrument", "")
        
        if is_call:
            delta_est = 0.50 + moneyness * 2.0
            delta_est = max(0.01, min(0.99, delta_est))
        else:
            delta_est = -0.50 + moneyness * 2.0
            delta_est = max(-0.99, min(-0.01, delta_est))
            
        gamma_est = 0.00035 * math.exp(-15 * (moneyness ** 2))
        vega_est = spot * 0.016 * math.exp(-15 * (moneyness ** 2)) / 100.0
        theta_est = -ltp * 0.08  # ~8% time decay per day near expiry

        port_delta += delta_est * side_mult * qty
        port_gamma += gamma_est * side_mult * qty
        port_theta += theta_est * side_mult * qty
        port_vega += vega_est * side_mult * qty
        gross_notional += strike * qty

    # Stress Test Matrix: Spot Shocks (-3%, -2%, -1%, 0%, +1%, +2%, +3%) vs Vol Shocks (-20%, 0%, +20%)
    spot_shocks_pct = [-0.03, -0.02, -0.01, 0.0, 0.01, 0.02, 0.03]
    vol_shocks_pct = [-0.20, 0.0, 0.20]

    stress_scenarios = []
    for s_pct in spot_shocks_pct:
        row = {"spot_shift_pct": f"{s_pct*100:+.1f}%", "spot_price": round(spot * (1 + s_pct), 2)}
        for v_pct in vol_shocks_pct:
            col_key = f"vol_{int(v_pct*100):+d}%"
            # Delta PnL + Gamma PnL + Vega PnL
            d_spot = spot * s_pct
            d_vol = 0.1543 * v_pct
            pnl_est = (port_delta * d_spot) + (0.5 * port_gamma * (d_spot ** 2)) + (port_vega * (d_vol * 100))
            row[col_key] = round(pnl_est, 2)
        stress_scenarios.append(row)

    capital_base = 2500000.0
    cash_floor = 500000.0
    margin_used = sum(p.get("qty", lot_size) * p.get("current_price", 100.0) * 5.0 for p in active_positions if p.get("side") == "SELL")
    free_margin = max(0.0, capital_base - cash_floor - margin_used)

    return {
        "status": "COMPLIANT" if abs(port_delta) <= 50.0 else "DELTA_EXCEEDED",
        "underlying_spot": round(spot, 2),
        "capital_base": capital_base,
        "cash_buffer_floor": cash_floor,
        "free_margin": round(free_margin, 2),
        "margin_used": round(margin_used, 2),
        "active_contracts_count": len(active_positions),
        "gross_notional": round(gross_notional, 2),
        "greeks": {
            "portfolio_delta": round(port_delta, 2),
            "portfolio_gamma": round(port_gamma, 5),
            "portfolio_daily_theta": round(port_theta, 2),
            "portfolio_vega": round(port_vega, 2)
        },
        "limits": {
            "delta_neutral_bound": "|Δ| ≤ 50 NIFTY",
            "delta_neutral_status": "COMPLIANT" if abs(port_delta) <= 50.0 else "BREACHED",
            "daily_loss_limit": "₹1,25,000.00 (5.0%)",
            "max_margin_utilization": "80.0% of Capital Base"
        },
        "stress_scenarios": stress_scenarios,
        "active_positions": active_positions
    }

