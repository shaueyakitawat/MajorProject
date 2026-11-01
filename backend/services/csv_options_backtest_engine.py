"""
backend/services/csv_options_backtest_engine.py
================================================================================
Institutional Quantitative Options Mispricing Walk-Forward Backtesting Engine
Evaluates the 8-stage econometric, pricing, and execution pipeline against
the complete historical NIFTY options database (data/nifty_options_daily_tradable.csv).
================================================================================
"""

import os
import math
import time
import logging
from datetime import datetime
from typing import Dict, List, Any, Tuple
import numpy as np
import pandas as pd
import scipy.stats as stats
import yfinance as yf
from arch import arch_model
from backend.services.cost_engine import IndianDerivativesCostEngine

logger = logging.getLogger("api")

# Configuration Constants
RISK_FREE_RATE = 0.065          # 6.50% Indian Benchmark Repo / 91D T-Bill Rate
DIVIDEND_YIELD = 0.0125         # 1.25% NIFTY 50 Dividend Yield
INITIAL_CAPITAL = 2500000.0     # ₹25,00,000 Institutional Base Capital
MAX_CONCURRENT_POSITIONS = 8    # Max 8 concurrent positions
MAX_SHORT_POSITIONS = 5
MAX_LONG_POSITIONS = 3
DEFAULT_LOTS_PER_TRADE = 3      # 3 lots
LOT_SIZE = 65                   # 65 qty per lot -> 195 qty per trade
DEFAULT_QTY = DEFAULT_LOTS_PER_TRADE * LOT_SIZE

# Fallback spot prices for legacy dates missing UndrlygPric
LEGACY_SPOT_MAP = {
    "2024-07-01": 24141.95,
    "2024-07-02": 24123.85,
    "2024-07-03": 24286.50,
    "2024-07-04": 24302.15,
    "2024-07-05": 24323.85,
}

# Mispricing Weights
W_PRICE = 0.50
W_VRP = 0.20
W_VEGA = 0.15
W_GAMMA = 0.10


def black_scholes_analytical(
    S: float, K: float, T: float, r: float, q: float, sigma: float, is_call: bool
) -> Tuple[float, float, float, float, float]:
    """
    High-precision analytical Black-Scholes-Merton formula.
    Returns (price, delta, gamma, vega, theta).
    """
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
    vega = (S * df_q * math.sqrt(T) * norm_pdf_d1) / 100.0  # ₹ per 1% vol

    return price, delta, gamma, vega, theta


def solve_implied_volatility(
    S: float, K: float, T: float, r: float, q: float, market_price: float, is_call: bool
) -> float | None:
    """
    Numerically inverts Black-Scholes using Brent's method with robust boundary guarantees.
    """
    if market_price <= 0.05 or S <= 0 or K <= 0 or T <= 0:
        return None

    df_r = math.exp(-r * T)
    df_q = math.exp(-q * T)
    intrinsic = max(0.0, S * df_q - K * df_r) if is_call else max(0.0, K * df_r - S * df_q)
    upper_bound = S * df_q if is_call else K * df_r

    if market_price <= intrinsic + 1e-4:
        return 0.01  # Lower bound
    if market_price >= upper_bound - 1e-4:
        return 3.00  # Upper bound

    low_vol, high_vol = 0.005, 3.50
    f_low, _, _, _, _ = black_scholes_analytical(S, K, T, r, q, low_vol, is_call)
    f_high, _, _, _, _ = black_scholes_analytical(S, K, T, r, q, high_vol, is_call)

    if (f_low - market_price) * (f_high - market_price) > 0:
        return None

    # Brent / Bisection loop
    for _ in range(32):
        mid_vol = 0.5 * (low_vol + high_vol)
        f_mid, _, _, _, _ = black_scholes_analytical(S, K, T, r, q, mid_vol, is_call)
        diff = f_mid - market_price
        if abs(diff) < 0.02:
            return mid_vol
        if (f_low - market_price) * diff < 0:
            high_vol = mid_vol
        else:
            low_vol = mid_vol
            f_low = f_mid

    return 0.5 * (low_vol + high_vol)


def estimate_round_trip_friction(entry_price: float, exit_price: float, side: str, qty: int) -> float:
    """
    Audited regulatory friction for NSE index options:
    - Brokerage: ₹20 entry + ₹20 exit
    - STT: 0.125% on sell turnover (entry for SELL, exit for BUY)
    - Exchange turnover: 0.053% of premium
    - GST: 18% on (brokerage + exchange)
    - Stamp duty: 0.003% on buy value
    """
    brokerage = 20.0 + 20.0
    entry_val = entry_price * qty
    exit_val = exit_price * qty

    stt = (entry_val * 0.00125 if side == "SELL" else 0.0) + (exit_val * 0.00125 if side == "BUY" else 0.0)
    exchange_fee = (entry_val + exit_val) * 0.00053
    gst = (brokerage + exchange_fee) * 0.18
    stamp_duty = (entry_val * 0.00003 if side == "BUY" else exit_val * 0.00003)

    return round(brokerage + stt + exchange_fee + gst + stamp_duty, 2)


class CsvOptionsBacktestEngine:
    def __init__(
        self,
        csv_path: str = "data/nifty_options_daily_tradable.csv",
        initial_capital: float = INITIAL_CAPITAL,
        qty: int = DEFAULT_QTY,
        min_mscore: float = 1.20,
        take_profit_pct: float = 25.0,
        stop_loss_pct: float = 10.0,
        max_positions: int = MAX_CONCURRENT_POSITIONS,
    ):
        self.csv_path = csv_path
        self.initial_capital = initial_capital
        self.qty = qty
        self.min_mscore = min_mscore
        self.take_profit_pct = take_profit_pct
        self.stop_loss_pct = stop_loss_pct
        self.max_positions = max_positions

        self.df: pd.DataFrame | None = None
        self.price_map: Dict[Tuple[str, str, float, str], Dict[str, float]] = {}
        self.trading_dates: List[str] = []
        self.daily_spot_map: Dict[str, float] = {}
        self.daily_vol_map: Dict[str, float] = {}
        self.daily_regime_map: Dict[str, str] = {}

    def load_data(self) -> None:
        """Loads and pre-indexes the options dataset and underlying time series."""
        if not os.path.exists(self.csv_path) and os.path.exists(self.csv_path + ".gz"):
            self.csv_path = self.csv_path + ".gz"

        logger.info(f"[CSV BACKTEST] Loading options dataset from {self.csv_path}...")
        t0 = time.time()

        cols = [
            "trade_date", "expiry", "strike", "option_type",
            "open", "high", "low", "close", "settlement",
            "contracts", "open_interest", "UndrlygPric"
        ]
        self.df = pd.read_csv(self.csv_path, usecols=cols)

        # Fill missing legacy spot prices
        for dt, sp in LEGACY_SPOT_MAP.items():
            self.df.loc[self.df["trade_date"] == dt, "UndrlygPric"] = sp

        # Map daily spot prices
        spot_series = self.df.groupby("trade_date")["UndrlygPric"].first()
        self.daily_spot_map = spot_series.dropna().to_dict()
        self.trading_dates = sorted(list(self.daily_spot_map.keys()))

        # Pre-index all contract quotes for instant O(1) lookup
        records = zip(
            self.df["trade_date"], self.df["expiry"], self.df["strike"], self.df["option_type"],
            self.df["open"], self.df["high"], self.df["low"], self.df["close"],
            self.df["settlement"], self.df["contracts"], self.df["open_interest"]
        )
        self.price_map = {
            (r[0], r[1], float(r[2]), r[3]): {
                "open": float(r[4]), "high": float(r[5]), "low": float(r[6]),
                "close": float(r[7]), "settlement": float(r[8]),
                "volume": float(r[9]), "oi": float(r[10])
            }
            for r in records
        }

        logger.info(
            f"[CSV BACKTEST] Data loaded in {time.time()-t0:.2f}s | "
            f"Dates={len(self.trading_dates)} | Contracts Indexed={len(self.price_map)}"
        )

        # Precompute Econometric Volatility & Regimes
        self._precompute_econometric_volatility()

    def _precompute_econometric_volatility(self) -> None:
        """
        Calibrates rolling EGARCH(1,1) model and assigns 4-state volatility regimes
        for every trading session across the backtest window.
        """
        logger.info("[CSV BACKTEST] Calibrating rolling econometric EGARCH(1,1) series...")
        t0 = time.time()

        # Fetch broader NIFTY history from yfinance for warm-up prior to 2024-07-01
        try:
            yf_data = yf.download("^NSEI", start="2024-01-01", end="2026-01-05", progress=False)
            closes = yf_data["Close"]["^NSEI"].dropna()
            log_returns = np.log(closes / closes.shift(1)).dropna()
        except Exception:
            # Fallback to local spot map returns
            spots = pd.Series(self.daily_spot_map).sort_index()
            log_returns = np.log(spots / spots.shift(1)).dropna()

        # Rolling 60-day window EGARCH calibration (strictly causal: returns < dt)
        vol_cache = {}
        for date_str in self.trading_dates:
            dt = pd.to_datetime(date_str)
            sub_returns = log_returns[log_returns.index < dt]
            if len(sub_returns) >= 40:
                win = sub_returns.iloc[-60:] * 100.0
                try:
                    am = arch_model(win, vol="EGARCH", p=1, o=1, q=1, dist="normal")
                    fit = am.fit(disp="off", show_warning=False)
                    if fit.convergence_flag == 0:
                        var_next = fit.forecast(horizon=1).variance.values[-1, 0]
                        daily_vol = math.sqrt(var_next) / 100.0
                        ann_vol = daily_vol * math.sqrt(252.0)
                    else:
                        ann_vol = float(sub_returns.iloc[-30:].std() * math.sqrt(252.0))
                except Exception:
                    ann_vol = float(sub_returns.iloc[-30:].std() * math.sqrt(252.0))
            else:
                ann_vol = 0.145

            ann_vol = max(0.08, min(0.40, ann_vol))
            vol_cache[date_str] = ann_vol

        self.daily_vol_map = vol_cache

        # Causal Trailing Regime Classification (No full-sample look-ahead)
        trading_dates_list = self.trading_dates
        for idx, date_str in enumerate(trading_dates_list):
            curr_v = vol_cache[date_str]
            # Use trailing 60 to 120 sessions prior to date_str
            past_dates = trading_dates_list[max(0, idx - 120):idx]
            if len(past_dates) >= 30:
                past_vols = [vol_cache[d] for d in past_dates]
                p25, p75, p90 = np.percentile(past_vols, 25), np.percentile(past_vols, 75), np.percentile(past_vols, 90)
                if curr_v < p25:
                    reg = "LOW_VOL"
                elif curr_v <= p75:
                    reg = "NORMAL_VOL"
                elif curr_v <= p90:
                    reg = "HIGH_VOL"
                else:
                    reg = "EXTREME_VOL"
            else:
                # Fixed baseline thresholds for warm-up phase
                if curr_v < 0.12:
                    reg = "LOW_VOL"
                elif curr_v <= 0.18:
                    reg = "NORMAL_VOL"
                elif curr_v <= 0.25:
                    reg = "HIGH_VOL"
                else:
                    reg = "EXTREME_VOL"
            self.daily_regime_map[date_str] = reg

        logger.info(f"[CSV BACKTEST] Causal volatility and regimes calibrated in {time.time()-t0:.2f}s.")

    def run_simulation(self) -> Dict[str, Any]:
        """
        Executes the walk-forward options mispricing backtest day-by-day.
        """
        if self.df is None or not self.price_map:
            self.load_data()

        logger.info("[CSV BACKTEST] Launching full walk-forward options backtesting engine...")
        t_start = time.time()

        open_positions: List[Dict[str, Any]] = []
        closed_trades: List[Dict[str, Any]] = []
        equity_curve: List[Dict[str, Any]] = []

        current_cash = self.initial_capital
        trade_id_seq = 0

        # Group data by trade_date for candidate scanning
        grouped_by_date = self.df.groupby("trade_date")

        for current_idx, current_date in enumerate(self.trading_dates):
            current_spot = self.daily_spot_map.get(current_date, 24000.0)
            model_vol = self.daily_vol_map.get(current_date, 0.14)
            current_regime = self.daily_regime_map.get(current_date, "NORMAL_VOL")
            curr_dt = pd.to_datetime(current_date)

            # ─────────────────────────────────────────────────────────────
            # Stage 1: Mark-to-Market & Exit Evaluation on Open Positions
            # ─────────────────────────────────────────────────────────────
            remaining_positions: List[Dict[str, Any]] = []
            session_realized_pnl = 0.0

            for pos in open_positions:
                key = (current_date, pos["expiry"], pos["strike"], pos["option_type"])
                quote = self.price_map.get(key)
                exp_dt = pd.to_datetime(pos["expiry"])
                is_expired = curr_dt >= exp_dt

                exit_price = None
                exit_reason = None

                if quote is not None:
                    high_p = quote["high"]
                    low_p = quote["low"]
                    close_p = quote["close"]

                    # Check intraday touch (Conservative risk priority: stop-loss evaluates first)
                    if pos["side"] == "SELL":
                        if high_p >= pos["stop_price"]:
                            exit_price = pos["stop_price"]
                            exit_reason = "STOP_LOSS_CUT"
                        elif low_p <= pos["target_price"]:
                            exit_price = pos["target_price"]
                            exit_reason = "ALPHA_HARVESTED"
                    else:  # BUY
                        if low_p <= pos["stop_price"]:
                            exit_price = pos["stop_price"]
                            exit_reason = "STOP_LOSS_CUT"
                        elif high_p >= pos["target_price"]:
                            exit_price = pos["target_price"]
                            exit_reason = "ALPHA_HARVESTED"

                    # If expired today and not stopped/targeted, cash settle at intrinsic value
                    if exit_price is None and is_expired:
                        if pos["option_type"] == "CE":
                            exit_price = max(0.0, current_spot - pos["strike"])
                        else:
                            exit_price = max(0.0, pos["strike"] - current_spot)
                        exit_reason = "EXPIRY_INTRINSIC"

                elif is_expired:
                    # Intrinsic settlement if quote missing on expiry
                    if pos["option_type"] == "CE":
                        exit_price = max(0.0, current_spot - pos["strike"])
                    else:
                        exit_price = max(0.0, pos["strike"] - current_spot)
                    exit_reason = "EXPIRY_INTRINSIC"

                if exit_price is not None:
                    # Close trade
                    gross_pnl = (
                        (pos["entry_price"] - exit_price) * pos["qty"]
                        if pos["side"] == "SELL"
                        else (exit_price - pos["entry_price"]) * pos["qty"]
                    )
                    friction_res = IndianDerivativesCostEngine.calculate_round_trip_friction(
                        entry_date=pos["entry_date"],
                        exit_date=current_date,
                        entry_price=pos["entry_price"],
                        exit_price=exit_price,
                        side=pos["side"],
                        qty=pos["qty"],
                        is_expiry_settlement=(exit_reason == "EXPIRY_INTRINSIC")
                    )
                    friction = friction_res.total_friction
                    net_pnl = gross_pnl - friction
                    return_pct = (net_pnl / (pos["entry_price"] * pos["qty"])) * 100.0

                    closed_trades.append({
                        "trade_id": pos["trade_id"],
                        "entry_date": pos["entry_date"],
                        "exit_date": current_date,
                        "holding_days": max(1, (curr_dt - pd.to_datetime(pos["entry_date"])).days),
                        "instrument": f"NIFTY {int(pos['strike'])} {pos['option_type']}",
                        "strike": pos["strike"],
                        "option_type": pos["option_type"],
                        "expiry": pos["expiry"],
                        "side": pos["side"],
                        "strategy": pos["strategy"],
                        "qty": pos["qty"],
                        "entry_price": pos["entry_price"],
                        "exit_price": exit_price,
                        "target_price": pos["target_price"],
                        "stop_price": pos["stop_price"],
                        "entry_mscore": pos["entry_mscore"],
                        "entry_vrp": pos["entry_vrp"],
                        "regime": pos["regime"],
                        "gross_pnl": round(gross_pnl, 2),
                        "friction": friction,
                        "net_pnl": round(net_pnl, 2),
                        "return_pct": round(return_pct, 2),
                        "status": "PROFIT" if net_pnl > 0 else "LOSS",
                        "exit_reason": exit_reason
                    })
                    current_cash += net_pnl
                    session_realized_pnl += net_pnl
                else:
                    # Keep position open and update mark-to-market
                    pos["current_price"] = quote["close"] if quote else pos["entry_price"]
                    pos["unrealized_pnl"] = (
                        (pos["entry_price"] - pos["current_price"]) * pos["qty"]
                        if pos["side"] == "SELL"
                        else (pos["current_price"] - pos["entry_price"]) * pos["qty"]
                    )
                    remaining_positions.append(pos)

            open_positions = remaining_positions

            # ─────────────────────────────────────────────────────────────
            # Stage 2: Scan for New Statistical Mispricing Opportunities
            # ─────────────────────────────────────────────────────────────
            if len(open_positions) < self.max_positions and current_idx < len(self.trading_dates) - 3:
                try:
                    day_contracts = grouped_by_date.get_group(current_date)
                except KeyError:
                    day_contracts = pd.DataFrame()

                candidates = []
                for _, row in day_contracts.iterrows():
                    contracts_vol = row["contracts"]
                    oi = row["open_interest"]
                    close_px = row["close"]
                    strike = float(row["strike"])
                    opt_type = row["option_type"]
                    expiry_str = row["expiry"]

                    # Filter liquidity & moneyness bounds
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

                    # Calculate BSM Fair Value & Greeks
                    fair_px, delta, gamma, vega, theta = black_scholes_analytical(
                        S=current_spot, K=strike, T=ttm, r=RISK_FREE_RATE,
                        q=DIVIDEND_YIELD, sigma=model_vol, is_call=is_call
                    )
                    if fair_px <= 0.5:
                        continue

                    # Solve Implied Volatility
                    iv = solve_implied_volatility(
                        S=current_spot, K=strike, T=ttm, r=RISK_FREE_RATE,
                        q=DIVIDEND_YIELD, market_price=close_px, is_call=is_call
                    )
                    if iv is None:
                        continue

                    vrp = iv - model_vol
                    dev = (close_px - fair_px) / fair_px

                    # Econometric M-Score
                    norm_price_dev = dev * 20.0
                    norm_vrp_dev = vrp * 50.0
                    dev_sign = 1.0 if dev > 0.001 else (-1.0 if dev < -0.001 else 0.0)
                    norm_vega = min(2.5, max(0.0, vega / 15.0))
                    norm_gamma = min(2.5, max(0.0, gamma / 0.0003))

                    m_score = (
                        W_PRICE * norm_price_dev +
                        W_VRP * norm_vrp_dev +
                        W_VEGA * dev_sign * norm_vega +
                        W_GAMMA * dev_sign * norm_gamma
                    )

                    abs_edge = abs(close_px - fair_px)
                    if abs_edge < 2.0:
                        continue

                    # Overpriced Short Candidate
                    if m_score >= self.min_mscore and dev >= 0.05 and vrp > 0:
                        candidates.append({
                            "strike": strike,
                            "option_type": opt_type,
                            "expiry": expiry_str,
                            "side": "SELL",
                            "strategy": "RV Short Overvalued Option",
                            "entry_price": close_px,
                            "fair_price": fair_px,
                            "m_score": m_score,
                            "abs_mscore": abs(m_score),
                            "vrp": vrp,
                            "delta": delta,
                            "target_price": round(max(0.5, close_px * (1.0 - self.take_profit_pct / 100.0)), 2),
                            "stop_price": round(close_px * (1.0 + self.stop_loss_pct / 100.0), 2)
                        })
                    # Underpriced Long Candidate
                    elif m_score <= -self.min_mscore and dev <= -0.05 and vrp < 0.02:
                        candidates.append({
                            "strike": strike,
                            "option_type": opt_type,
                            "expiry": expiry_str,
                            "side": "BUY",
                            "strategy": "RV Long Undervalued Option",
                            "entry_price": close_px,
                            "fair_price": fair_px,
                            "m_score": m_score,
                            "abs_mscore": abs(m_score),
                            "vrp": vrp,
                            "delta": delta,
                            "target_price": round(close_px * (1.0 + self.take_profit_pct / 100.0), 2),
                            "stop_price": round(max(0.5, close_px * (1.0 - self.stop_loss_pct / 100.0)), 2)
                        })

                # Sort candidates by statistical dislocation magnitude
                candidates.sort(key=lambda c: c["abs_mscore"], reverse=True)

                existing_keys = {(p["expiry"], p["strike"], p["option_type"]) for p in open_positions}
                short_count = sum(1 for p in open_positions if p["side"] == "SELL")
                long_count = sum(1 for p in open_positions if p["side"] == "BUY")

                for cand in candidates:
                    if len(open_positions) >= self.max_positions:
                        break
                    cand_key = (cand["expiry"], cand["strike"], cand["option_type"])
                    if cand_key in existing_keys:
                        continue

                    if cand["side"] == "SELL" and short_count >= MAX_SHORT_POSITIONS:
                        continue
                    if cand["side"] == "BUY" and long_count >= MAX_LONG_POSITIONS:
                        continue

                    trade_id_seq += 1
                    trade_id = f"BT-{trade_id_seq:04d}"

                    open_positions.append({
                        "trade_id": trade_id,
                        "entry_date": current_date,
                        "strike": cand["strike"],
                        "option_type": cand["option_type"],
                        "expiry": cand["expiry"],
                        "side": cand["side"],
                        "strategy": cand["strategy"],
                        "qty": self.qty,
                        "entry_price": cand["entry_price"],
                        "current_price": cand["entry_price"],
                        "fair_price": cand["fair_price"],
                        "target_price": cand["target_price"],
                        "stop_price": cand["stop_price"],
                        "entry_mscore": round(cand["m_score"], 2),
                        "entry_vrp": round(cand["vrp"] * 100.0, 2),
                        "regime": current_regime,
                        "unrealized_pnl": 0.0
                    })
                    existing_keys.add(cand_key)
                    if cand["side"] == "SELL":
                        short_count += 1
                    else:
                        long_count += 1

            # ─────────────────────────────────────────────────────────────
            # Stage 3: Equity Curve Progression
            # ─────────────────────────────────────────────────────────────
            total_unrealized = sum(p["unrealized_pnl"] for p in open_positions)
            total_equity = current_cash + total_unrealized

            equity_curve.append({
                "date": current_date,
                "spot": current_spot,
                "cash": round(current_cash, 2),
                "unrealized_pnl": round(total_unrealized, 2),
                "total_equity": round(total_equity, 2),
                "open_positions_count": len(open_positions),
                "cumulative_return_pct": round(((total_equity - self.initial_capital) / self.initial_capital) * 100.0, 3)
            })

        # Close any lingering positions on the final date
        final_date = self.trading_dates[-1]
        for pos in open_positions:
            quote = self.price_map.get((final_date, pos["expiry"], pos["strike"], pos["option_type"]))
            exit_px = quote["close"] if quote else pos["entry_price"]
            gross_pnl = (
                (pos["entry_price"] - exit_px) * pos["qty"]
                if pos["side"] == "SELL"
                else (exit_px - pos["entry_price"]) * pos["qty"]
            )
            friction = estimate_round_trip_friction(pos["entry_price"], exit_px, pos["side"], pos["qty"])
            net_pnl = gross_pnl - friction
            return_pct = (net_pnl / (pos["entry_price"] * pos["qty"])) * 100.0

            closed_trades.append({
                "trade_id": pos["trade_id"],
                "entry_date": pos["entry_date"],
                "exit_date": final_date,
                "holding_days": max(1, (pd.to_datetime(final_date) - pd.to_datetime(pos["entry_date"])).days),
                "instrument": f"NIFTY {int(pos['strike'])} {pos['option_type']}",
                "strike": pos["strike"],
                "option_type": pos["option_type"],
                "expiry": pos["expiry"],
                "side": pos["side"],
                "strategy": pos["strategy"],
                "qty": pos["qty"],
                "entry_price": pos["entry_price"],
                "exit_price": exit_px,
                "target_price": pos["target_price"],
                "stop_price": pos["stop_price"],
                "entry_mscore": pos["entry_mscore"],
                "entry_vrp": pos["entry_vrp"],
                "regime": pos["regime"],
                "gross_pnl": round(gross_pnl, 2),
                "friction": friction,
                "net_pnl": round(net_pnl, 2),
                "return_pct": round(return_pct, 2),
                "status": "PROFIT" if net_pnl > 0 else "LOSS",
                "exit_reason": "BACKTEST_END_MTM"
            })
            current_cash += net_pnl

        # ─────────────────────────────────────────────────────────────
        # Stage 4: Statistical Metrics & Risk Decomposition
        # ─────────────────────────────────────────────────────────────
        total_trades = len(closed_trades)
        wins = [t for t in closed_trades if t["net_pnl"] > 0]
        losses = [t for t in closed_trades if t["net_pnl"] <= 0]

        win_count = len(wins)
        loss_count = len(losses)
        win_rate = (win_count / total_trades * 100.0) if total_trades > 0 else 0.0

        total_gross_pnl = sum(t["gross_pnl"] for t in closed_trades)
        total_friction = sum(t["friction"] for t in closed_trades)
        total_net_pnl = sum(t["net_pnl"] for t in closed_trades)

        total_gain = sum(t["net_pnl"] for t in wins)
        total_loss = abs(sum(t["net_pnl"] for t in losses))
        profit_factor = round(total_gain / total_loss, 2) if total_loss > 0 else 99.9

        avg_win = (total_gain / win_count) if win_count > 0 else 0.0
        avg_loss = (total_loss / loss_count) if loss_count > 0 else 0.0
        payoff_ratio = round(avg_win / avg_loss, 2) if avg_loss > 0 else 0.0

        # Equity Returns & Drawdowns
        eq_df = pd.DataFrame(equity_curve)
        eq_df["daily_return"] = eq_df["total_equity"].pct_change().fillna(0.0)
        daily_returns = eq_df["daily_return"].values

        # Maximum Drawdown
        running_max = eq_df["total_equity"].cummax()
        drawdowns = (eq_df["total_equity"] - running_max) / running_max
        max_drawdown_pct = abs(float(drawdowns.min())) * 100.0
        max_drawdown_amount = float((running_max - eq_df["total_equity"]).max())

        # Annualized Sharpe & Sortino
        trading_days_count = len(self.trading_dates)
        years = trading_days_count / 252.0
        cagr_pct = (((eq_df["total_equity"].iloc[-1] / self.initial_capital) ** (1.0 / years)) - 1.0) * 100.0

        excess_daily_returns = daily_returns - (RISK_FREE_RATE / 252.0)
        mean_excess = np.mean(excess_daily_returns)
        std_returns = np.std(daily_returns, ddof=1) if len(daily_returns) > 1 else 0.01

        sharpe_ratio = round((mean_excess / std_returns) * math.sqrt(252.0), 3) if std_returns > 0 else 0.0

        downside_returns = daily_returns[daily_returns < 0]
        downside_std = np.std(downside_returns, ddof=1) if len(downside_returns) > 1 else 0.005
        sortino_ratio = round((mean_excess / downside_std) * math.sqrt(252.0), 3) if downside_std > 0 else 0.0

        calmar_ratio = round(cagr_pct / max_drawdown_pct, 2) if max_drawdown_pct > 0 else 0.0

        # Monthly performance aggregation
        trades_df = pd.DataFrame(closed_trades)
        trades_df["month"] = pd.to_datetime(trades_df["entry_date"]).dt.strftime("%Y-%m")
        monthly_groups = trades_df.groupby("month")
        monthly_summary = []
        for m, g in monthly_groups:
            m_win = len(g[g["net_pnl"] > 0])
            m_total = len(g)
            monthly_summary.append({
                "month": m,
                "trades": m_total,
                "win_rate": round((m_win / m_total) * 100.0, 1),
                "net_pnl": round(float(g["net_pnl"].sum()), 2),
                "friction": round(float(g["friction"].sum()), 2)
            })

        # Regime breakdown
        regime_groups = trades_df.groupby("regime")
        regime_summary = []
        for r, g in regime_groups:
            r_win = len(g[g["net_pnl"] > 0])
            r_total = len(g)
            regime_summary.append({
                "regime": r,
                "trades": r_total,
                "win_rate": round((r_win / r_total) * 100.0, 1),
                "net_pnl": round(float(g["net_pnl"].sum()), 2),
                "profit_factor": round(float(g[g['net_pnl'] > 0]['net_pnl'].sum() / abs(g[g['net_pnl'] < 0]['net_pnl'].sum() or 1)), 2)
            })

        # Strategy breakdown
        strat_groups = trades_df.groupby("strategy")
        strat_summary = []
        for s, g in strat_groups:
            s_win = len(g[g["net_pnl"] > 0])
            s_total = len(g)
            strat_summary.append({
                "strategy": s,
                "trades": s_total,
                "win_rate": round((s_win / s_total) * 100.0, 1),
                "net_pnl": round(float(g["net_pnl"].sum()), 2)
            })

        execution_duration = round(time.time() - t_start, 2)

        results = {
            "metadata": {
                "dataset": self.csv_path,
                "period": f"{self.trading_dates[0]} to {self.trading_dates[-1]}",
                "trading_sessions": trading_days_count,
                "initial_capital": self.initial_capital,
                "final_equity": round(eq_df["total_equity"].iloc[-1], 2),
                "lot_size": LOT_SIZE,
                "lots_per_trade": DEFAULT_LOTS_PER_TRADE,
                "trade_qty": self.qty,
                "execution_duration_seconds": execution_duration
            },
            "summary": {
                "total_trades": total_trades,
                "win_count": win_count,
                "loss_count": loss_count,
                "win_rate_pct": round(win_rate, 2),
                "profit_factor": profit_factor,
                "payoff_ratio": payoff_ratio,
                "total_gross_pnl": round(total_gross_pnl, 2),
                "total_friction": round(total_friction, 2),
                "total_net_pnl": round(total_net_pnl, 2),
                "total_return_pct": round((total_net_pnl / self.initial_capital) * 100.0, 2),
                "cagr_pct": round(cagr_pct, 2),
                "sharpe_ratio": sharpe_ratio,
                "sortino_ratio": sortino_ratio,
                "calmar_ratio": calmar_ratio,
                "max_drawdown_pct": round(max_drawdown_pct, 2),
                "max_drawdown_amount": round(max_drawdown_amount, 2),
                "avg_holding_days": round(float(trades_df["holding_days"].mean()), 1) if total_trades > 0 else 0.0
            },
            "monthly_performance": monthly_summary,
            "regime_performance": regime_summary,
            "strategy_performance": strat_summary,
            "equity_curve": equity_curve,
            "trades": closed_trades
        }

        logger.info(
            f"[CSV BACKTEST] Completed in {execution_duration}s | "
            f"Trades={total_trades} | WinRate={win_rate:.1f}% | "
            f"Net PnL=₹{total_net_pnl:,.2f} | Sharpe={sharpe_ratio:.2f}"
        )

        return results
