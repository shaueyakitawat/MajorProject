"""
scripts/run_three_research_experiments.py
================================================================================
Comprehensive IEEE Research Experimental Suite for QuantLens:
1. Experiment 1: Model Ablation (Rolling vs GARCH vs EGARCH vs VRP vs HMM vs Full M-Score)
2. Experiment 2: Realistic Execution Sensitivity (Tiers 0 through 4)
3. Experiment 3: Controlled Holding-Period Analysis (Intraday vs 2D vs 3D vs 5D vs Expiry)
================================================================================
"""

import os
import math
import time
import json
from pathlib import Path
from typing import Dict, List, Any, Tuple
import numpy as np
import pandas as pd
from arch import arch_model
from backend.services.cost_engine import IndianDerivativesCostEngine

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Baseline Parameters
RISK_FREE_RATE = 0.065
DIVIDEND_YIELD = 0.0125
INITIAL_CAPITAL = 2500000.0
MAX_POSITIONS = 8
MAX_SHORT_POSITIONS = 5
MAX_LONG_POSITIONS = 3

def get_nifty_lot_size(trade_date: str) -> int:
    """Official NSE historical lot size calendar for NIFTY 50 options."""
    dt = pd.to_datetime(trade_date)
    if dt < pd.to_datetime("2024-11-20"):
        return 25
    elif dt < pd.to_datetime("2025-10-29"):
        return 75
    else:
        return 65

def black_scholes(S: float, K: float, T: float, r: float, q: float, sigma: float, is_call: bool):
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
        intrinsic = max(0.0, S - K) if is_call else max(0.0, K - S)
        return intrinsic, 1.0 if is_call else -1.0, 0.0, 0.0, 0.0

    df_r = math.exp(-r * T)
    df_q = math.exp(-q * T)
    vol_sqrt_t = sigma * math.sqrt(T)

    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / vol_sqrt_t
    d2 = d1 - vol_sqrt_t

    norm_cdf_d1 = 0.5 * (1.0 + math.erf(d1 / math.sqrt(2.0)))
    norm_cdf_d2 = 0.5 * (1.0 + math.erf(d2 / math.sqrt(2.0)))
    norm_pdf_d1 = (1.0 / math.sqrt(2.0 * math.pi)) * math.exp(-0.5 * d1 * d1)

    if is_call:
        price = max(0.0, S * df_q * norm_cdf_d1 - K * df_r * norm_cdf_d2)
        delta = df_q * norm_cdf_d1
        theta = (
            -(S * df_q * sigma * norm_pdf_d1) / (2.0 * math.sqrt(T))
            - r * K * df_r * norm_cdf_d2
            + q * S * df_q * norm_cdf_d1
        ) / 365.0
    else:
        price = max(0.0, K * df_r * (1.0 - norm_cdf_d2) - S * df_q * (1.0 - norm_cdf_d1))
        delta = -df_q * (1.0 - norm_cdf_d1)
        theta = (
            -(S * df_q * sigma * norm_pdf_d1) / (2.0 * math.sqrt(T))
            + r * K * df_r * (1.0 - norm_cdf_d2)
            - q * S * df_q * (1.0 - norm_cdf_d1)
        ) / 365.0

    gamma = (df_q * norm_pdf_d1) / (S * vol_sqrt_t)
    vega = (S * df_q * math.sqrt(T) * norm_pdf_d1) / 100.0

    return price, delta, gamma, vega, theta

def solve_iv(S: float, K: float, T: float, r: float, q: float, market_price: float, is_call: bool) -> float | None:
    intrinsic = max(0.0, S - K) if is_call else max(0.0, K - S)
    if market_price <= intrinsic:
        return 0.05

    low_vol, high_vol = 0.01, 3.0
    for _ in range(40):
        mid_vol = 0.5 * (low_vol + high_vol)
        price, _, _, vega, _ = black_scholes(S, K, T, r, q, mid_vol, is_call)
        diff = price - market_price
        if abs(diff) < 0.01:
            return mid_vol
        if diff > 0:
            high_vol = mid_vol
        else:
            low_vol = mid_vol
    return 0.5 * (low_vol + high_vol)


class ExperimentEngine:
    def __init__(self):
        print("[INIT] Loading historical options dataset...")
        t0 = time.time()
        csv_path = PROJECT_ROOT / "data" / "nifty_options_daily_tradable.csv"
        self.df = pd.read_csv(csv_path, low_memory=False)
        self.trading_dates = sorted(self.df["trade_date"].unique().tolist())
        print(f"[INIT] Loaded {len(self.df):,} rows across {len(self.trading_dates)} trading sessions in {time.time()-t0:.2f}s.")

        # Build fast lookup map: (trade_date, expiry, strike, option_type) -> row dict
        print("[INIT] Indexing quote lookup table...")
        self.quote_map = {}
        for _, r in self.df.iterrows():
            key = (r["trade_date"], r["expiry"], float(r["strike"]), r["option_type"])
            self.quote_map[key] = {
                "open": float(r["open"]),
                "high": float(r["high"]),
                "low": float(r["low"]),
                "close": float(r["close"]),
                "settlement": float(r["settlement"]) if pd.notna(r["settlement"]) else 0.0,
                "contracts": float(r["contracts"]) if pd.notna(r["contracts"]) else 0.0,
                "open_interest": float(r["open_interest"]) if pd.notna(r["open_interest"]) else 0.0,
            }

        # Spot prices
        self.spot_map = self.df.groupby("trade_date")["UndrlygPric"].median().dropna().to_dict()
        fallback_spots = {
            "2024-07-01": 24141.95, "2024-07-02": 24123.85, "2024-07-03": 24286.50,
            "2024-07-04": 24302.15, "2024-07-05": 24323.85,
        }
        for d, s in fallback_spots.items():
            if d not in self.spot_map or pd.isna(self.spot_map[d]):
                self.spot_map[d] = s

        # Group by date for scanning
        self.grouped_by_date = self.df.groupby("trade_date")

        # Precompute Volatilities: Rolling, GARCH, EGARCH
        self.precompute_volatilities()

        # Load calibrated HMM mapping
        hmm_path = PROJECT_ROOT / "outputs" / "hmm_regime_model_params.json"
        if hmm_path.exists():
            hmm_data = json.loads(hmm_path.read_text())
            self.regime_map = hmm_data["dates_mapped"]
        else:
            self.regime_map = {d: "NORMAL_VOL" for d in self.trading_dates}

    def precompute_volatilities(self):
        print("[INIT] Precomputing causal out-of-sample volatility forecasts...")
        spots = pd.Series(self.spot_map).sort_index()
        log_ret = np.log(spots / spots.shift(1)).dropna()

        self.vol_rolling = {}
        self.vol_garch = {}
        self.vol_egarch = {}

        for d in self.trading_dates:
            dt = pd.to_datetime(d)
            # Strictly causal: returns < d
            sub = log_ret[log_ret.index < d]
            if len(sub) < 30:
                ann_vol = 0.14
                self.vol_rolling[d] = ann_vol
                self.vol_garch[d] = ann_vol
                self.vol_egarch[d] = ann_vol
                continue

            # Rolling 30D
            r_vol = float(sub.iloc[-30:].std() * math.sqrt(252.0))
            self.vol_rolling[d] = max(0.06, min(0.45, r_vol))

            win = sub.iloc[-60:] * 100.0
            # GARCH(1,1)
            try:
                am_g = arch_model(win, vol="GARCH", p=1, q=1, dist="normal")
                res_g = am_g.fit(disp="off", show_warning=False)
                g_vol = math.sqrt(res_g.forecast(horizon=1).variance.values[-1, 0]) / 100.0 * math.sqrt(252.0)
            except Exception:
                g_vol = r_vol
            self.vol_garch[d] = max(0.06, min(0.45, g_vol))

            # EGARCH(1,1,1)
            try:
                am_e = arch_model(win, vol="EGARCH", p=1, o=1, q=1, dist="normal")
                res_e = am_e.fit(disp="off", show_warning=False)
                e_vol = math.sqrt(res_e.forecast(horizon=1).variance.values[-1, 0]) / 100.0 * math.sqrt(252.0)
            except Exception:
                e_vol = r_vol
            self.vol_egarch[d] = max(0.06, min(0.45, e_vol))

        print("[INIT] Volatility precomputation complete.")

    def run_backtest(
        self,
        vol_model_type: str = "EGARCH",     # "ROLLING", "GARCH", "EGARCH"
        use_vrp_filter: bool = True,
        use_hmm_filter: bool = True,
        use_greeks_in_score: bool = True,
        execution_tier: int = 1,            # 0=Zero, 1=Regulatory, 2=Half-Spread, 3=Full-Spread, 4=Institutional
        holding_horizon_days: int | None = None, # None=standard target/stop/expiry; integer=fixed holding limit
        lots_per_trade: int = 1
    ) -> Dict[str, Any]:
        """Runs walk-forward backtest under specified research configuration."""
        
        # Select vol map
        if vol_model_type == "ROLLING":
            vol_map = self.vol_rolling
        elif vol_model_type == "GARCH":
            vol_map = self.vol_garch
        else:
            vol_map = self.vol_egarch

        open_positions = []
        closed_trades = []
        equity_records = []
        current_cash = INITIAL_CAPITAL
        trade_id_seq = 0

        # Slippage and spread parameters by tier
        spread_pts = 0.0
        slippage_pts = 0.0
        apply_gap_penalty = False
        apply_statutory_friction = True

        if execution_tier == 0:
            apply_statutory_friction = False
            spread_pts = 0.0
            slippage_pts = 0.0
        elif execution_tier == 1:
            apply_statutory_friction = True
            spread_pts = 0.0
            slippage_pts = 0.0
        elif execution_tier == 2:
            apply_statutory_friction = True
            spread_pts = 0.25 # half spread
            slippage_pts = 0.0
        elif execution_tier == 3:
            apply_statutory_friction = True
            spread_pts = 0.35
            slippage_pts = 0.25
        elif execution_tier == 4:
            apply_statutory_friction = True
            spread_pts = 0.50
            slippage_pts = 0.25
            apply_gap_penalty = True

        for current_idx, current_date in enumerate(self.trading_dates):
            current_spot = self.spot_map.get(current_date, 24000.0)
            model_vol = vol_map.get(current_date, 0.14)
            current_regime = self.regime_map.get(current_date, "NORMAL_VOL")
            curr_dt = pd.to_datetime(current_date)

            # ─────────────────────────────────────────────────────────────
            # 1. Evaluate Open Positions (Exits)
            # ─────────────────────────────────────────────────────────────
            remaining_positions = []
            for pos in open_positions:
                key = (current_date, pos["expiry"], pos["strike"], pos["option_type"])
                quote = self.quote_map.get(key)
                exp_dt = pd.to_datetime(pos["expiry"])
                is_expired = curr_dt >= exp_dt
                days_held = (curr_dt - pd.to_datetime(pos["entry_date"])).days

                exit_price = None
                exit_reason = None

                # Check fixed holding period limit if configured
                if holding_horizon_days is not None and days_held >= holding_horizon_days and quote is not None:
                    exit_price = quote["close"]
                    exit_reason = "HORIZON_REACHED"

                elif quote is not None:
                    high_p = quote["high"]
                    low_p = quote["low"]
                    open_p = quote["open"]

                    # Conservative touch evaluation: stop-loss evaluates first
                    if pos["side"] == "SELL":
                        if high_p >= pos["stop_price"]:
                            base_exit = pos["stop_price"]
                            if apply_gap_penalty and open_p > pos["stop_price"]:
                                base_exit = open_p # gapped through stop
                            exit_price = base_exit + (spread_pts + slippage_pts)
                            exit_reason = "STOP_LOSS_CUT"
                        elif low_p <= pos["target_price"]:
                            exit_price = max(0.5, pos["target_price"] + (spread_pts + slippage_pts))
                            exit_reason = "ALPHA_HARVESTED"
                    else:  # BUY
                        if low_p <= pos["stop_price"]:
                            base_exit = pos["stop_price"]
                            if apply_gap_penalty and open_p < pos["stop_price"]:
                                base_exit = open_p
                            exit_price = max(0.1, base_exit - (spread_pts + slippage_pts))
                            exit_reason = "STOP_LOSS_CUT"
                        elif high_p >= pos["target_price"]:
                            exit_price = pos["target_price"] - (spread_pts + slippage_pts)
                            exit_reason = "ALPHA_HARVESTED"

                    # If expired today and not stopped/targeted, cash settle intrinsic
                    if exit_price is None and is_expired:
                        if pos["option_type"] == "CE":
                            exit_price = max(0.0, current_spot - pos["strike"])
                        else:
                            exit_price = max(0.0, pos["strike"] - current_spot)
                        exit_reason = "EXPIRY_INTRINSIC"

                elif is_expired:
                    if pos["option_type"] == "CE":
                        exit_price = max(0.0, current_spot - pos["strike"])
                    else:
                        exit_price = max(0.0, pos["strike"] - current_spot)
                    exit_reason = "EXPIRY_INTRINSIC"

                if exit_price is not None:
                    gross_pnl = (
                        (pos["entry_price"] - exit_price) * pos["qty"]
                        if pos["side"] == "SELL"
                        else (exit_price - pos["entry_price"]) * pos["qty"]
                    )
                    
                    if apply_statutory_friction:
                        f_res = IndianDerivativesCostEngine.calculate_round_trip_friction(
                            entry_date=pos["entry_date"],
                            exit_date=current_date,
                            entry_price=pos["entry_price"],
                            exit_price=exit_price,
                            side=pos["side"],
                            qty=pos["qty"],
                            is_expiry_settlement=(exit_reason == "EXPIRY_INTRINSIC")
                        )
                        friction = f_res.total_friction
                    else:
                        friction = 0.0

                    net_pnl = gross_pnl - friction
                    closed_trades.append({
                        "trade_id": pos["trade_id"],
                        "entry_date": pos["entry_date"],
                        "exit_date": current_date,
                        "holding_days": max(1, days_held),
                        "side": pos["side"],
                        "qty": pos["qty"],
                        "entry_price": pos["entry_price"],
                        "exit_price": exit_price,
                        "gross_pnl": round(gross_pnl, 2),
                        "friction": round(friction, 2),
                        "net_pnl": round(net_pnl, 2),
                        "exit_reason": exit_reason
                    })
                    current_cash += net_pnl
                else:
                    pos["current_price"] = quote["close"] if quote else pos["entry_price"]
                    remaining_positions.append(pos)

            open_positions = remaining_positions

            # ─────────────────────────────────────────────────────────────
            # 2. Candidate Scanning at Session Close for Next-Day Open Execution
            # ─────────────────────────────────────────────────────────────
            # Regime gating: In extreme volatility, suppress option selling
            if use_hmm_filter and current_regime == "EXTREME_VOL":
                allow_selling = False
            else:
                allow_selling = True

            if len(open_positions) < MAX_POSITIONS and current_idx < len(self.trading_dates) - 3:
                try:
                    day_contracts = self.grouped_by_date.get_group(current_date)
                except KeyError:
                    day_contracts = pd.DataFrame()

                # Determine next session date for execution
                next_date = self.trading_dates[current_idx + 1]
                lot_size = get_nifty_lot_size(next_date)
                trade_qty = lots_per_trade * lot_size

                candidates = []
                for _, row in day_contracts.iterrows():
                    contracts_vol = row["contracts"]
                    oi = row["open_interest"]
                    close_px = row["close"]
                    strike = float(row["strike"])
                    opt_type = row["option_type"]
                    expiry_str = row["expiry"]

                    if contracts_vol < 50 or oi < 500 or close_px < 3.0:
                        continue
                    if abs(strike - current_spot) / current_spot > 0.08:
                        continue

                    exp_dt = pd.to_datetime(expiry_str)
                    dte_days = (exp_dt - curr_dt).days
                    if dte_days < 2 or dte_days > 35:
                        continue

                    ttm = dte_days / 365.0
                    is_call = opt_type == "CE"

                    fair_px, delta, gamma, vega, theta = black_scholes(
                        S=current_spot, K=strike, T=ttm, r=RISK_FREE_RATE,
                        q=DIVIDEND_YIELD, sigma=model_vol, is_call=is_call
                    )
                    if fair_px <= 0.5:
                        continue

                    iv = solve_iv(current_spot, strike, ttm, RISK_FREE_RATE, DIVIDEND_YIELD, close_px, is_call)
                    if iv is None:
                        continue

                    vrp = iv - model_vol
                    dev = (close_px - fair_px) / fair_px

                    # Score calculation
                    if not use_vrp_filter:
                        # Raw BSM price deviation score
                        m_score = dev * 20.0
                    elif not use_greeks_in_score:
                        # Price dev + VRP
                        m_score = 0.70 * (dev * 20.0) + 0.30 * (vrp * 50.0)
                    else:
                        # Full M-Score with dimensionless Greeks
                        dev_sign = 1.0 if dev > 0.001 else (-1.0 if dev < -0.001 else 0.0)
                        norm_vega = min(2.5, max(0.0, vega / 15.0))
                        norm_gamma = min(2.5, max(0.0, gamma / 0.0003))
                        m_score = (
                            0.50 * (dev * 20.0) +
                            0.20 * (vrp * 50.0) +
                            0.15 * dev_sign * norm_vega -
                            0.10 * dev_sign * norm_gamma  # gamma risk penalty
                        )

                    abs_edge = abs(close_px - fair_px)
                    if abs_edge < 2.0:
                        continue

                    # Next-day open quote lookup for execution
                    next_quote = self.quote_map.get((next_date, expiry_str, strike, opt_type))
                    if next_quote is None or next_quote["open"] <= 1.0:
                        continue # Cannot execute next day if no open print
                    
                    next_open = next_quote["open"]

                    # SELL Candidate
                    if allow_selling and m_score >= 1.20 and dev >= 0.05 and (not use_vrp_filter or vrp > 0):
                        # Executed at Next-Day Open with spread/slippage
                        entry_px = next_open - (spread_pts + slippage_pts)
                        candidates.append({
                            "strike": strike, "option_type": opt_type, "expiry": expiry_str,
                            "side": "SELL", "entry_price": entry_px, "abs_mscore": abs(m_score),
                            "target_price": round(max(0.5, entry_px * 0.75), 2),
                            "stop_price": round(entry_px * 1.10, 2),
                            "entry_date": next_date, "qty": trade_qty
                        })
                    # BUY Candidate
                    elif m_score <= -1.20 and dev <= -0.05 and (not use_vrp_filter or vrp < 0.02):
                        entry_px = next_open + (spread_pts + slippage_pts)
                        candidates.append({
                            "strike": strike, "option_type": opt_type, "expiry": expiry_str,
                            "side": "BUY", "entry_price": entry_px, "abs_mscore": abs(m_score),
                            "target_price": round(entry_px * 1.25, 2),
                            "stop_price": round(max(0.5, entry_px * 0.90), 2),
                            "entry_date": next_date, "qty": trade_qty
                        })

                candidates.sort(key=lambda c: c["abs_mscore"], reverse=True)
                existing_keys = {(p["expiry"], p["strike"], p["option_type"]) for p in open_positions}
                short_count = sum(1 for p in open_positions if p["side"] == "SELL")
                long_count = sum(1 for p in open_positions if p["side"] == "BUY")

                for cand in candidates:
                    if len(open_positions) >= MAX_POSITIONS:
                        break
                    cand_key = (cand["expiry"], cand["strike"], cand["option_type"])
                    if cand_key in existing_keys:
                        continue
                    if cand["side"] == "SELL" and short_count >= MAX_SHORT_POSITIONS:
                        continue
                    if cand["side"] == "BUY" and long_count >= MAX_LONG_POSITIONS:
                        continue

                    trade_id_seq += 1
                    open_positions.append({
                        "trade_id": f"BT-{trade_id_seq:04d}",
                        "entry_date": cand["entry_date"],
                        "strike": cand["strike"],
                        "option_type": cand["option_type"],
                        "expiry": cand["expiry"],
                        "side": cand["side"],
                        "qty": cand["qty"],
                        "entry_price": cand["entry_price"],
                        "current_price": cand["entry_price"],
                        "target_price": cand["target_price"],
                        "stop_price": cand["stop_price"],
                    })

            # Record Daily Marked-to-Market Portfolio Equity
            unrealized = sum(
                ((p["entry_price"] - p["current_price"]) * p["qty"] if p["side"] == "SELL"
                 else (p["current_price"] - p["entry_price"]) * p["qty"])
                for p in open_positions
            )
            total_equity = current_cash + unrealized
            equity_records.append({"date": current_date, "equity": total_equity})

        # Calculate Summary Metrics
        eq_series = pd.Series([r["equity"] for r in equity_records])
        daily_ret = eq_series.pct_change().dropna()
        rf_daily = RISK_FREE_RATE / 252.0
        excess_ret = daily_ret - rf_daily

        total_net_pnl = current_cash - INITIAL_CAPITAL
        total_return_pct = (total_net_pnl / INITIAL_CAPITAL) * 100.0
        ann_sharpe = float((excess_ret.mean() / (excess_ret.std() + 1e-8)) * math.sqrt(252.0))

        # Max drawdown
        cum_max = eq_series.cummax()
        drawdown = (eq_series - cum_max) / cum_max
        max_dd_pct = float(abs(drawdown.min()) * 100.0)

        # Win rate & profit factor
        n_trades = len(closed_trades)
        if n_trades > 0:
            pnl_arr = np.array([t["net_pnl"] for t in closed_trades])
            wins = pnl_arr[pnl_arr > 0]
            losses = pnl_arr[pnl_arr < 0]
            win_rate = (len(wins) / n_trades) * 100.0
            sum_win = np.sum(wins) if len(wins) > 0 else 0.0
            sum_loss = abs(np.sum(losses)) if len(losses) > 0 else 1.0
            profit_factor = float(sum_win / max(1.0, sum_loss))
            avg_holding = float(np.mean([t["holding_days"] for t in closed_trades]))
            total_gross = sum(t["gross_pnl"] for t in closed_trades)
            total_friction = sum(t["friction"] for t in closed_trades)
        else:
            win_rate, profit_factor, avg_holding, total_gross, total_friction = 0.0, 0.0, 0.0, 0.0, 0.0

        return {
            "n_trades": n_trades,
            "total_net_pnl": round(total_net_pnl, 2),
            "total_return_pct": round(total_return_pct, 2),
            "gross_pnl": round(total_gross, 2),
            "total_friction": round(total_friction, 2),
            "win_rate": round(win_rate, 2),
            "profit_factor": round(profit_factor, 2),
            "annualized_sharpe": round(ann_sharpe, 3),
            "max_drawdown_pct": round(max_dd_pct, 2),
            "avg_holding_days": round(avg_holding, 2),
            "final_equity": round(float(eq_series.iloc[-1]), 2),
        }


def run_all_experiments():
    engine = ExperimentEngine()
    out_dir = PROJECT_ROOT / "outputs"
    out_dir.mkdir(exist_ok=True)

    # ─────────────────────────────────────────────────────────────
    # EXPERIMENT 1: Model Ablation
    # ─────────────────────────────────────────────────────────────
    print("\n" + "="*80)
    print("RUNNING EXPERIMENT 1: MODEL ABLATION")
    print("="*80)

    exp1_configs = {
        "A_Rolling_BSM": {"vol_model_type": "ROLLING", "use_vrp_filter": False, "use_hmm_filter": False, "use_greeks_in_score": False},
        "B_GARCH_BSM":   {"vol_model_type": "GARCH",   "use_vrp_filter": False, "use_hmm_filter": False, "use_greeks_in_score": False},
        "C_EGARCH_BSM":  {"vol_model_type": "EGARCH",  "use_vrp_filter": False, "use_hmm_filter": False, "use_greeks_in_score": False},
        "D_EGARCH_VRP":  {"vol_model_type": "EGARCH",  "use_vrp_filter": True,  "use_hmm_filter": False, "use_greeks_in_score": False},
        "E_EGARCH_VRP_HMM": {"vol_model_type": "EGARCH", "use_vrp_filter": True, "use_hmm_filter": True, "use_greeks_in_score": False},
        "F_Full_MScore": {"vol_model_type": "EGARCH",  "use_vrp_filter": True,  "use_hmm_filter": True,  "use_greeks_in_score": True},
    }

    exp1_results = {}
    for name, cfg in exp1_configs.items():
        print(f"Executing Exp 1: {name}...")
        res = engine.run_backtest(
            vol_model_type=cfg["vol_model_type"],
            use_vrp_filter=cfg["use_vrp_filter"],
            use_hmm_filter=cfg["use_hmm_filter"],
            use_greeks_in_score=cfg["use_greeks_in_score"],
            execution_tier=1, # standard regulatory friction
            lots_per_trade=1
        )
        exp1_results[name] = res
        print(f"  -> Trades: {res['n_trades']} | Net PnL: ₹{res['total_net_pnl']:,.2f} ({res['total_return_pct']}%) | Sharpe: {res['annualized_sharpe']} | PF: {res['profit_factor']} | MDD: {res['max_drawdown_pct']}%")

    (out_dir / "experiment1_model_ablation.json").write_text(json.dumps(exp1_results, indent=2))
    print("[✓] Saved experiment1_model_ablation.json")

    # ─────────────────────────────────────────────────────────────
    # EXPERIMENT 2: Realistic Execution Sensitivity
    # ─────────────────────────────────────────────────────────────
    print("\n" + "="*80)
    print("RUNNING EXPERIMENT 2: REALISTIC EXECUTION SENSITIVITY")
    print("="*80)

    tier_names = {
        0: "Tier_0_Zero_Friction",
        1: "Tier_1_Regulatory_Friction_Only",
        2: "Tier_2_Friction_Plus_HalfSpread",
        3: "Tier_3_Friction_Spread_Slippage",
        4: "Tier_4_Full_Institutional_Friction"
    }

    exp2_results = {}
    for tier, label in tier_names.items():
        print(f"Executing Exp 2: {label} (Tier {tier})...")
        res = engine.run_backtest(
            vol_model_type="EGARCH",
            use_vrp_filter=True,
            use_hmm_filter=True,
            use_greeks_in_score=True,
            execution_tier=tier,
            lots_per_trade=1
        )
        exp2_results[label] = res
        print(f"  -> Trades: {res['n_trades']} | Net PnL: ₹{res['total_net_pnl']:,.2f} ({res['total_return_pct']}%) | Sharpe: {res['annualized_sharpe']} | PF: {res['profit_factor']} | MDD: {res['max_drawdown_pct']}%")

    (out_dir / "experiment2_execution_sensitivity.json").write_text(json.dumps(exp2_results, indent=2))
    print("[✓] Saved experiment2_execution_sensitivity.json")

    # ─────────────────────────────────────────────────────────────
    # EXPERIMENT 3: Controlled Holding-Period Analysis
    # ─────────────────────────────────────────────────────────────
    print("\n" + "="*80)
    print("RUNNING EXPERIMENT 3: CONTROLLED HOLDING-PERIOD ANALYSIS")
    print("="*80)

    horizons = {
        "1D_Intraday_Close": 1,
        "2D_Holding": 2,
        "3D_Holding": 3,
        "5D_Weekly_Cycle": 5,
        "Dynamic_Target_Stop": None
    }

    exp3_results = {}
    for label, h_days in horizons.items():
        print(f"Executing Exp 3: {label} (Limit {h_days} days)...")
        res = engine.run_backtest(
            vol_model_type="EGARCH",
            use_vrp_filter=True,
            use_hmm_filter=True,
            use_greeks_in_score=True,
            execution_tier=1,
            holding_horizon_days=h_days,
            lots_per_trade=1
        )
        exp3_results[label] = res
        print(f"  -> Trades: {res['n_trades']} | Avg Hold: {res['avg_holding_days']}d | Net PnL: ₹{res['total_net_pnl']:,.2f} ({res['total_return_pct']}%) | Sharpe: {res['annualized_sharpe']} | PF: {res['profit_factor']}")

    (out_dir / "experiment3_holding_analysis.json").write_text(json.dumps(exp3_results, indent=2))
    print("[✓] Saved experiment3_holding_analysis.json")


if __name__ == "__main__":
    run_all_experiments()

