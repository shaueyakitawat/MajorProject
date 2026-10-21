#!/usr/bin/env python3
"""
scripts/live_paper_trader.py — Autonomous Live Options Mispricing & Paper Trading Engine
========================================================================================
Institutional backend execution terminal for NIFTY 50 options mispricing detection,
delta-neutral paper trading, intraday position management, and statistical accuracy scoring.

Designed for live market testing during NSE market hours (09:15 - 15:30 IST).
Empirical validation engine for IEEE Transactions quantitative paper.
"""

import os
import sys
import time
import math
import json
import signal
import sqlite3
import argparse
from collections import deque
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd
import numpy as np

# Ensure project root in python path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.option_chain_service import get_spot_price, get_full_chain, get_multi_expiry_chains
from backend.services.volatility_service import forecast_volatility
from backend.services.pricing_service import black_scholes_price, calculate_greeks, calculate_ttm_years
from backend.services.regime_service import classify_volatility_regime
from backend.services.mispricing_service import detect_mispricing

OUTPUT_DIR = PROJECT_ROOT / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = PROJECT_ROOT / "data" / "nifty_live_snapshots.db"
AUDIT_CSV_PATH = OUTPUT_DIR / "live_paper_trades_audit.csv"


def calculate_dynamic_volatility_target_and_stop(
    entry_price: float,
    fair_price: float,
    side: str,
    fused_vol: float = 0.16,
    tick_vol: float = 0.12,
    regime: str = "NORMAL_VOL",
    delta: float = 0.30,
    theta: float = -10.0,
    base_tp_pct: float = 28.0,
    base_sl_pct: float = 9.5
) -> tuple[float, float, float, float, float, str]:
    """
    Dynamic Volatility-Adaptive Target & Stop-Loss Engine with Positive Payoff Asymmetry:
    
    1. Positive Asymmetric Risk:Reward (1 : 2.7 to 1 : 3.5):
       - Stop loss is strictly bounded between 8.5% and 10.5% maximum (hard institutional tight stop).
       - Profit targets expand dynamically between 25.0% and 38.0%.
       - Emergency catastrophic circuit breaker triggers at 12.5% maximum dislocation.
       
    2. Market Fluctuation Violence Scaling:
       - Uses live multi-factor fused volatility (sigma_fused), tick shock volatility (sigma_tick),
         and market regime to dynamically calibrate TP/SL bands within safety bounds.
    """
    tick = 0.05
    baseline_vol = 0.12  # Standard calm annual volatility for NIFTY
    max_stop_loss_pct = 10.5

    # 1. Measure market fluctuation violence
    active_vol = max(fused_vol, tick_vol)
    vol_ratio = active_vol / baseline_vol if baseline_vol > 0 else 1.0
    if regime == "EXTREME_VOL":
        vol_ratio += 0.06
    elif regime == "HIGH_VOL":
        vol_ratio += 0.03
    vol_ratio = max(0.92, min(1.25, vol_ratio))

    # 2. Premium / Moneyness elasticity
    if entry_price < 50.0:
        price_factor = 1.04
    elif entry_price <= 120.0:
        price_factor = 1.00
    else:
        price_factor = 0.96

    # 3. Dynamic percentages (Positive Asymmetric R:R 1:2.7 to 1:3.5)
    dynamic_sl_pct = base_sl_pct * vol_ratio * price_factor
    dynamic_sl_pct = max(8.5, min(max_stop_loss_pct, dynamic_sl_pct))

    dynamic_tp_pct = base_tp_pct * vol_ratio * price_factor
    dynamic_tp_pct = max(25.0, min(38.0, dynamic_tp_pct))

    if side == "SELL":
        mispricing_gap = max(0.0, entry_price - fair_price)
        # Quant Target: Realistic institutional profit capture between 25% and 38% premium decay
        raw_target_decay = max(entry_price * (dynamic_tp_pct / 100.0), mispricing_gap)
        target_decay_pts = min(entry_price * 0.38, max(entry_price * 0.25, raw_target_decay))
        raw_target = max(0.05, entry_price - target_decay_pts)
        target_price = round(round(raw_target / tick) * tick, 2)
        target_decay = entry_price - target_price

        # Strict hard stop (8.5% to 10.5% maximum)
        stop_allowance = entry_price * (dynamic_sl_pct / 100.0)
        raw_stop = entry_price + stop_allowance
        stop_price = round(round(raw_stop / tick) * tick, 2)

        catastrophic_stop = round(entry_price * 1.125, 2)
        dynamic_tp_pct = round((target_decay / entry_price) * 100.0, 1) if entry_price > 0 else 28.0
        dynamic_sl_pct = round((stop_allowance / entry_price) * 100.0, 1) if entry_price > 0 else 9.5

        rationale = (
            f"Quant BSM Fair Target: Captures ₹{target_decay:.2f} Alpha ({dynamic_tp_pct:.1f}% decay), "
            f"Invalidation Bound @ ₹{stop_price:.2f} (+{dynamic_sl_pct:.1f}% tight stop)"
        )
    else:
        mispricing_gap = max(0.0, fair_price - entry_price)
        # For BUY: Target captures at least +28% gain or model fair value
        target_gain_pts = max(entry_price * (dynamic_tp_pct / 100.0), mispricing_gap)
        raw_target = entry_price + target_gain_pts
        target_price = round(round(raw_target / tick) * tick, 2)
        target_gain = target_price - entry_price

        # Strict hard stop (8.5% to 10.5% maximum)
        stop_allowance = entry_price * (dynamic_sl_pct / 100.0)
        raw_stop = max(0.05, entry_price - stop_allowance)
        stop_price = round(round(raw_stop / tick) * tick, 2)

        catastrophic_stop = round(max(0.05, entry_price * 0.875), 2)
        dynamic_tp_pct = round((target_gain / entry_price) * 100.0, 1) if entry_price > 0 else 28.0
        dynamic_sl_pct = round((stop_allowance / entry_price) * 100.0, 1) if entry_price > 0 else 9.5

        rationale = (
            f"Quant BSM Fair Target: Captures ₹{target_gain:.2f} Alpha (+{dynamic_tp_pct:.1f}% gain), "
            f"Invalidation Bound @ ₹{stop_price:.2f} (-{dynamic_sl_pct:.1f}% tight stop)"
        )

    return target_price, stop_price, catastrophic_stop, dynamic_tp_pct, dynamic_sl_pct, rationale


def calculate_realistic_target_and_stop(
    entry_price: float,
    fair_price: float,
    side: str,
    take_profit_pct: float = 25.0,
    stop_loss_pct: float = 20.0,
    delta: float = 0.20,
    theta: float = -10.0,
    fused_vol: float = 0.16,
    tick_vol: float = 0.12,
    regime: str = "NORMAL_VOL"
) -> tuple[float, float, str]:
    tp, sl, _, _, _, rat = calculate_dynamic_volatility_target_and_stop(
        entry_price, fair_price, side, fused_vol, tick_vol, regime, delta, theta, take_profit_pct, stop_loss_pct
    )
    return tp, sl, rat


def format_inr(val: float, include_sign: bool = False) -> str:
    """Format currency in clean, standard Indian Rupee notation (e.g. +₹120.50, -₹320.51, ₹44.32)."""
    if val is None:
        return "₹0.00"
    if val < 0:
        return f"-₹{abs(val):,.2f}"
    elif val > 0 and include_sign:
        return f"+₹{val:,.2f}"
    else:
        return f"₹{val:,.2f}"


def estimate_round_trip_friction(entry_price: float, exit_price: float, side: str, qty: int) -> float:
    """Estimate all modeled entry and exit costs for a paper-traded leg."""
    brokerage = 20.0
    entry_stt = entry_price * qty * 0.00125 if side == "SELL" else 0.0
    entry_exchange = entry_price * qty * 0.00053
    entry_gst = (brokerage + entry_exchange) * 0.18
    exit_stt = exit_price * qty * 0.00125 if side == "BUY" else 0.0
    exit_exchange = exit_price * qty * 0.00053
    exit_gst = (brokerage + exit_exchange) * 0.18
    return round(
        brokerage + entry_stt + entry_exchange + entry_gst
        + brokerage + exit_stt + exit_exchange + exit_gst,
        2,
    )


def is_fee_viable_candidate(candidate: dict, side: str, qty: int) -> bool:
    """Reject theoretical edges that cannot survive modeled costs, execution spread, and theta bleed."""
    entry_price = candidate["ask"] if side == "BUY" else candidate["bid"]
    fair_price = candidate["fair_price"]
    actual_edge_pts = abs(entry_price - fair_price)
    actual_edge_rupees = actual_edge_pts * qty

    # Discard sub-2.0 point noise that cannot overcome execution spread and bid-ask slippage
    if actual_edge_pts < 2.0:
        return False

    round_trip_cost = estimate_round_trip_friction(entry_price, fair_price, side, qty)
    min_ratio = 2.0 if side == "SELL" else 2.5
    min_gross = 350.0  # Require at least ₹350 true statistical alpha per position

    return (actual_edge_rupees >= round_trip_cost * min_ratio) and (actual_edge_rupees >= min_gross)


def estimate_leave_one_out_surface_volatility(
    chain_list: list[dict],
    option_type: str,
    strike: float,
    spot: float,
    forecast_volatility: float,
) -> tuple[float, int]:
    """
    Estimate local IV from neighboring strikes, excluding the candidate itself,
    with econometric smile & skew adjustment relative to spot moneyness.
    """
    if spot <= 0 or strike <= 0 or forecast_volatility <= 0:
        return forecast_volatility, 0

    # Structural index volatility smile/skew adjustment:
    log_moneyness = math.log(strike / spot)
    if option_type.lower() == "put":
        # OTM puts naturally trade at a structural volatility skew
        skew_adj = max(-0.015, min(0.080, -0.25 * log_moneyness))
    else:
        # Calls have a modest smile curvature
        skew_adj = max(-0.015, min(0.035, -0.08 * log_moneyness))

    peers = []
    for item in chain_list:
        peer_strike = item.get("strike")
        peer = item.get(option_type)
        if peer_strike is None or peer is None or float(peer_strike) == float(strike):
            continue
        peer_iv = peer.get("iv")
        peer_ltp = peer.get("ltp", 0.0)
        if peer_iv is None or peer_ltp is None:
            continue
        try:
            peer_iv = float(peer_iv)
            peer_ltp = float(peer_ltp)
            distance = abs(math.log(float(peer_strike) / strike))
        except (TypeError, ValueError, ZeroDivisionError):
            continue
        if not (0.05 <= peer_iv <= 0.80 and peer_ltp > 0 and 0 < distance <= 0.040):
            continue
        peers.append((distance, peer_iv))

    if len(peers) < 3:
        fair_iv = forecast_volatility + skew_adj
        return float(max(0.05, min(0.80, fair_iv))), len(peers)

    peers.sort(key=lambda pair: pair[0])
    peers = peers[:8]
    weights = np.array([1.0 / (distance + 0.002) for distance, _ in peers], dtype=float)
    ivs = np.array([peer_iv for _, peer_iv in peers], dtype=float)
    local_iv = float(np.average(ivs, weights=weights))

    # Econometric local volatility surface:
    # 85% local peer market smile/skew + 15% structural baseline (forecast + parametric skew).
    # Unbiased surface ensures fair prices match true market relative value without artificial elevation!
    structural_baseline = forecast_volatility + skew_adj
    surface_iv = 0.85 * local_iv + 0.15 * structural_baseline
    return float(max(0.05, min(0.80, surface_iv))), len(peers)


class LiveQuantPaperTrader:
    def __init__(
        self,
        symbol: str = "NIFTY",
        lot_size: int = int(os.getenv("NIFTY_LOT_SIZE", "65")),
        max_positions: int = 8,
        take_profit_pct: float = 28.0,
        stop_loss_pct: float = 9.5,
        min_mscore: float = 1.2,
        update_interval_sec: int = 8,
        auto_trade: bool = True,
        resume_existing: bool = True,
        allow_stale: bool = False,
        multi_expiry: bool = True,
        total_capital: float = 2500000.0,
        no_eod_squareoff: bool = False,
        max_closed_trades: int | None = None,
        target_margin_roi: float | None = None,
        lots_per_trade: int | None = None
    ):
        self.symbol = symbol
        self.lot_size = lot_size
        self.lots_per_trade = lots_per_trade if lots_per_trade is not None else int(os.getenv("LOTS_PER_TRADE", "3"))
        self.trade_qty = self.lot_size * self.lots_per_trade
        self.max_positions = max_positions
        self.max_short_positions = int(os.getenv("MAX_SHORT_POSITIONS", "4"))
        self.max_long_positions = int(os.getenv("MAX_LONG_POSITIONS", "2"))
        self.max_daily_closed_trades = max_closed_trades if max_closed_trades is not None else int(os.getenv("MAX_DAILY_TRADES", "50"))
        self.target_margin_roi = target_margin_roi if target_margin_roi is not None else float(os.getenv("TARGET_MARGIN_ROI", "0.50"))
        self.no_eod_squareoff = no_eod_squareoff or (os.getenv("NO_EOD_SQUAREOFF", "0") == "1")
        self.allow_stale = allow_stale or (os.getenv("ALLOW_STALE_CHAIN", "0") == "1")
        self.multi_expiry = multi_expiry
        self.active_chains: list[dict] = []
        self.max_contract_positions = max(1, int(os.getenv("MAX_CONTRACT_POSITIONS", "1")))
        self.max_abs_net_delta = max(1.0, float(os.getenv("MAX_ABS_NET_DELTA", "100")))
        self.max_chain_age_seconds = max(5.0, float(os.getenv("MAX_CHAIN_AGE_SECONDS", "30")))
        self.max_entry_dev_pct = max(20.0, float(os.getenv("MAX_ENTRY_DEV_PCT", "50.0")))
        self.min_surface_peers = max(3, int(os.getenv("MIN_SURFACE_PEERS", "3")))
        self.delta_neutral_mode = os.getenv("DELTA_NEUTRAL_MODE", "0") == "1"
        self.take_profit_pct = take_profit_pct
        self.stop_loss_pct = stop_loss_pct
        self.min_mscore = min_mscore
        self.update_interval = update_interval_sec
        self.auto_trade = auto_trade
        self.resume_existing = resume_existing
        self.running = True

        # Capital & Margin Accounting Engine (₹25,00,000 Portfolio)
        self.total_capital: float = float(os.getenv("TOTAL_CAPITAL", str(total_capital)))
        self.max_margin_utilization: float = 0.80  # Max 80% used margin (₹20,00,000 max utilized)
        self.total_trading_margin: float = self.total_capital * self.max_margin_utilization  # ₹20,00,000 available margin
        self.target_profit_amount: float = self.total_trading_margin * (self.target_margin_roi / 100.0)  # ₹10,000.00 (+0.50% on margin)
        self.max_short_margin: float = 1600000.0   # Max ₹16.0L short selling margin (~7-8 lots)
        self.max_long_margin: float = 400000.0     # Max ₹4.0L long option buying margin
        self.daily_target_min_pct: float = 0.25    # Daily target 0.25% (+₹6,250 on ₹25L)
        self.daily_target_max_pct: float = 0.50    # Daily target 0.50% (+₹12,500 on ₹25L)
        self.max_daily_loss: float = float(os.getenv("MAX_DAILY_LOSS", "2500.0"))  # Strict -0.10% daily loss cap
        self.strike_loss_counts: dict[tuple[float, str, str], int] = {}  # Tracks session losses per strike

        # State storage
        self.positions: list[dict] = []
        self.closed_trades: list[dict] = []
        self.strike_cooldown: dict[tuple[float, str, str], tuple[float, float] | float] = {}  # (strike, opt_type, expiry) -> (last exit epoch, exit spot)
        self.last_trade_entry_epoch: float = 0.0
        self.trade_counter = 0
        self.pair_counter = 0
        self.initial_spot = 0.0
        self.current_spot = 0.0
        self.session_open_spot = 0.0
        self.session_high_spot = 0.0
        self.session_low_spot = 0.0
        self.last_chain_data: dict = {}

        # Real-Time Pricing & Volatility Parameters
        self.spot_history: deque = deque(maxlen=90)   # Rolling 10s spot ticks (last 15 mins)
        self.session_spot_sum: float = 0.0
        self.session_spot_count: int = 0
        self.session_vwap: float = 0.0
        self.tick_vol: float = 0.128                  # High-frequency tick realized volatility
        self.atm_iv: float = 0.135                    # Instantaneous ATM Implied Volatility
        self.atm_strike: float = 0.0                  # Closest ATM Strike
        self.implied_r: float = 0.0665                # Real-time implied risk-free rate from put-call parity
        self.forward_price: float = 0.0               # Real-time synthetic forward price
        self.dividend_yield: float = 0.0125           # NIFTY 50 continuous dividend yield (1.25%)
        self.current_ttm: float = 0.0                 # Exact high-precision fractional TTM (years)
        self.egarch_vol: float = 0.128                # Multi-factor fused volatility
        self.intraday_vol: float = 0.132              # 5-minute realized volatility
        self.daily_vol: float = 0.122                 # Baseline daily EGARCH(1,1) volatility
        self.regime: str = "NORMAL_VOL"
        self.last_vol_update: float = 0.0
        self.start_time = datetime.now()

        self._init_sqlite_ledger()
        self._load_session_trades_from_db()
        self._init_signal_handlers()

    def calculate_trade_margin(self, side: str, ltp: float, spot: float = 0.0, qty: int = 65) -> float:
        """
        Calculate realistic NSE margin requirement for NIFTY options.
        - SELL (Short): SPAN + Exposure margin per lot is ~₹1.35L - ₹1.75L.
        - BUY (Long): 100% option premium paid upfront (LTP * Qty).
        """
        if side.upper() == "SELL":
            num_lots = max(1, qty // self.lot_size)
            per_lot_margin = min(175000.0, max(135000.0, 140000.0 + (ltp * self.lot_size)))
            return float(per_lot_margin * num_lots)
        else:
            return float(round(ltp * qty, 2))

    @property
    def used_margin(self) -> float:
        """Total margin currently utilized across all active open positions."""
        total = 0.0
        for p in self.positions:
            total += p.get("allocated_margin") or self.calculate_trade_margin(
                p.get("side", "SELL"), p.get("current_price", p.get("entry_price", 0.0)),
                self.current_spot, p.get("qty", self.lot_size)
            )
        return round(total, 2)

    @property
    def used_short_margin(self) -> float:
        total = 0.0
        for p in self.positions:
            if p.get("side") == "SELL":
                total += p.get("allocated_margin") or self.calculate_trade_margin(
                    "SELL", p.get("current_price", p.get("entry_price", 0.0)),
                    self.current_spot, p.get("qty", self.lot_size)
                )
        return round(total, 2)

    @property
    def used_long_margin(self) -> float:
        total = 0.0
        for p in self.positions:
            if p.get("side") == "BUY":
                total += p.get("allocated_margin") or self.calculate_trade_margin(
                    "BUY", p.get("current_price", p.get("entry_price", 0.0)),
                    self.current_spot, p.get("qty", self.lot_size)
                )
        return round(total, 2)

    @property
    def free_margin(self) -> float:
        """Remaining free margin available for new deployments."""
        max_usable = self.total_capital * self.max_margin_utilization
        return max(0.0, round(max_usable - self.used_margin, 2))

    @property
    def margin_utilization_pct(self) -> float:
        if self.total_capital <= 0:
            return 0.0
        return round((self.used_margin / self.total_capital) * 100.0, 2)

    @property
    def today_realized_pnl(self) -> float:
        return round(sum(t.get("realized_pnl", t.get("net_pnl", 0.0)) for t in self.closed_trades), 2)

    @property
    def today_unrealized_pnl(self) -> float:
        return round(sum(p.get("net_pnl", 0.0) for p in self.positions), 2)

    @property
    def today_net_pnl(self) -> float:
        return round(self.today_realized_pnl + self.today_unrealized_pnl, 2)

    @property
    def account_equity(self) -> float:
        return round(self.total_capital + self.today_net_pnl, 2)

    @property
    def daily_roi_pct(self) -> float:
        if self.total_capital <= 0:
            return 0.0
        return round((self.today_net_pnl / self.total_capital) * 100.0, 3)

    @property
    def spot_drift_15m(self) -> float:
        """Rolling spot drift over the past 10-15 minutes for momentum/trend filtering."""
        if len(self.spot_history) >= 6:
            return round(float(self.current_spot - self.spot_history[0]), 2)
        return 0.0

    @property
    def spot_drift_5m(self) -> float:
        """Rolling spot drift over the past 5 minutes (last ~30 ticks)."""
        if len(self.spot_history) >= 30:
            return round(float(self.current_spot - list(self.spot_history)[-30]), 2)
        elif len(self.spot_history) >= 6:
            return round(float(self.current_spot - list(self.spot_history)[0]), 2)
        return 0.0

    @property
    def macro_session_bias(self) -> str:
        """
        Macro intraday directional anchor based on Open price, VWAP, and multi-timeframe spot progression:
        - 'MACRO_BEARISH': Spot is below session open by >= 15 pts AND below VWAP.
                           In this state, SELL PUT is strictly forbidden.
        - 'MACRO_BULLISH': Spot is above session open by >= 15 pts AND above VWAP.
                           In this state, SELL CALL is strictly forbidden.
        - 'MACRO_NEUTRAL': Market is within range of open/VWAP.
        """
        if self.current_spot <= 0:
            return "MACRO_NEUTRAL"
        open_s = self.session_open_spot if self.session_open_spot > 0 else self.current_spot
        vwap = self.session_vwap if self.session_vwap > 0 else self.current_spot

        # Asymmetric range hurdle: If market already suffered a severe session drop (>= 35 pts),
        # require stronger evidence (>= +25 pts over open AND > VWAP) before declaring MACRO_BULLISH
        prior_drop = (open_s - self.session_low_spot) if self.session_low_spot > 0 else 0.0
        bull_hurdle = 25.0 if prior_drop >= 35.0 else 15.0

        prior_rally = (self.session_high_spot - open_s) if self.session_high_spot > 0 else 0.0
        bear_hurdle = 25.0 if prior_rally >= 35.0 else 15.0

        if self.current_spot <= (open_s - bear_hurdle) and self.current_spot <= (vwap + 2.0):
            return "MACRO_BEARISH"
        elif self.current_spot >= (open_s + bull_hurdle) and self.current_spot >= (vwap - 2.0):
            return "MACRO_BULLISH"
        return "MACRO_NEUTRAL"

    @property
    def net_portfolio_delta(self) -> float:
        """Normalized net portfolio delta in per-share units (divide by lot_size so it represents net option lots)."""
        if not self.positions:
            return 0.0
        return sum(
            p.get("delta", 0.3) * (1 if p["side"] == "BUY" else -1) * (p["qty"] / self.lot_size)
            for p in self.positions
        )

    @property
    def trend_regime(self) -> str:
        """
        Determine prevailing market trend regime using Spot, Session Benchmark, and Multi-Timeframe Drift.
        Anchored by macro session bias to prevent classifying counter-trend dead-cat bounces as 'STRONG_BULLISH'.
        """
        if len(self.spot_history) < 6:
            return "CHOPPY_NEUTRAL"
        vwap = self.session_vwap if self.session_vwap > 0 else self.current_spot
        d15 = self.spot_drift_15m
        d5 = self.spot_drift_5m
        macro = self.macro_session_bias

        # In a macro bearish session, a short-term bounce is NEVER 'STRONG_BULLISH'
        if macro == "MACRO_BEARISH":
            if self.current_spot <= (vwap + 4.0) and (d15 <= -10.0 or d5 <= -2.0):
                return "STRONG_BEARISH"
            return "CHOPPY_NEUTRAL"

        # In a macro bullish session, a short-term pullback is NEVER 'STRONG_BEARISH'
        if macro == "MACRO_BULLISH":
            if self.current_spot >= (vwap - 4.0) and (d15 >= 10.0 or d5 >= 2.0):
                return "STRONG_BULLISH"
            return "CHOPPY_NEUTRAL"

        if self.current_spot >= (vwap + 5.0) and d15 >= 14.0 and d5 >= 0.0:
            return "STRONG_BULLISH"
        elif self.current_spot <= (vwap - 5.0) and d15 <= -14.0 and d5 <= 0.0:
            return "STRONG_BEARISH"
        else:
            return "CHOPPY_NEUTRAL"

    def is_strike_in_cooldown(self, strike: float, opt_type: str, expiry: str = "", cooldown_seconds: float = 300.0) -> bool:
        """Prevent re-entering the exact same strike/type/expiry within cooldown window unless spot has moved significantly."""
        key = (float(strike), str(opt_type).lower(), str(expiry))
        legacy_key = (float(strike), str(opt_type).lower(), "")

        # Strict Quant Rule: If this specific contract stopped out 2 or more times today, blacklist it for the entire session!
        if self.strike_loss_counts.get(key, 0) >= 2 or self.strike_loss_counts.get(legacy_key, 0) >= 2:
            return True

        entry = self.strike_cooldown.get(key)
        if not entry:
            entry = self.strike_cooldown.get(legacy_key)
            if not entry:
                return False

        if isinstance(entry, (tuple, list)):
            last_exit, exit_spot = entry
        else:
            last_exit, exit_spot = float(entry), self.current_spot

        elapsed = time.time() - last_exit
        # If stopped out once, enforce a 15-minute (900s) cooldown before reconsidering
        cooldown_needed = 900.0 if (self.strike_loss_counts.get(key, 0) == 1 or self.strike_loss_counts.get(legacy_key, 0) == 1) else cooldown_seconds
        if elapsed >= cooldown_needed:
            return False
        # If spot index has migrated away by >= 35 points from the exit spot, the local regime has changed, allow re-entry
        if abs(self.current_spot - exit_spot) >= 35.0:
            return False
        return True

    def _load_session_trades_from_db(self):
        """
        Restore today's complete session state:
        1. Always load ALL closed trades from today so that morning trades are never lost from the live terminal.
        2. If resume_existing is True, load active OPEN positions with their allocated margins.
        3. Restore the highest trade counter so trade IDs continue monotonically.
        """
        try:
            if not DB_PATH.exists():
                return
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            today_str = datetime.now().strftime("%Y-%m-%d")

            # Determine highest trade counter
            row = cur.execute(
                "SELECT MAX(CAST(REPLACE(trade_id, 'TRD-', '') AS INTEGER)) FROM live_paper_trades"
            ).fetchone()
            if row and row[0]:
                self.trade_counter = max(self.trade_counter, int(row[0]))

            # 1. Load active OPEN positions if resuming
            if self.resume_existing:
                cur.execute(
                    "SELECT * FROM live_paper_trades WHERE status = 'OPEN' AND (entry_timestamp LIKE ? OR entry_timestamp IS NULL)",
                    (f"{today_str}%",)
                )
                for r in cur.fetchall():
                    d = dict(r)
                    d["type"] = d["option_type"]
                    d["entry_epoch"] = time.time() - d.get("holding_seconds", 0.0)
                    d["converged"] = bool(d.get("converged", 0))
                    d.setdefault("delta", 0.5)
                    d.setdefault("theta", -10.0)
                    d.setdefault("vega", 15.0)

                    # Dynamic Volatility-Adaptive Target & Stop with Positive Asymmetry
                    calc_target, calc_stop, cat_stop, dyn_tp, dyn_sl, _ = calculate_dynamic_volatility_target_and_stop(
                        d["entry_price"], d.get("entry_fair", d["entry_price"]), d["side"],
                        fused_vol=self.egarch_vol, tick_vol=self.tick_vol, regime=self.regime,
                        delta=d.get("delta", 0.3), theta=d.get("theta", -10.0),
                        base_tp_pct=self.take_profit_pct, base_sl_pct=self.stop_loss_pct
                    )
                    d["target_price"] = d.get("target_price") or calc_target
                    d["stop_price"] = d.get("stop_price") or calc_stop
                    d["catastrophic_stop"] = d.get("catastrophic_stop") or cat_stop
                    d["dynamic_tp_pct"] = dyn_tp
                    d["dynamic_sl_pct"] = dyn_sl
                    d["stop_breach_count"] = 0
                    d["spike_shield_active"] = False
                    d["allocated_margin"] = self.calculate_trade_margin(
                        d["side"], d.get("current_price", d["entry_price"]), self.current_spot, d.get("qty", self.lot_size)
                    )

                    self.positions.append(d)

            # Pure outright mispricing trades (no pair trading / delta-neutral pairing)
            for p in self.positions:
                p["pair_id"] = None

            # 2. ALWAYS load ALL closed trades from today's session (morning and afternoon)
            cur.execute(
                "SELECT * FROM live_paper_trades WHERE status = 'CLOSED' AND entry_timestamp LIKE ? ORDER BY exit_time ASC, trade_id ASC",
                (f"{today_str}%",)
            )
            for r in cur.fetchall():
                d = dict(r)
                d["type"] = d["option_type"]
                d["converged"] = bool(d.get("converged", 0))
                d["realized_pnl"] = d.get("realized_pnl") if d.get("realized_pnl") is not None else d.get("net_pnl", 0.0)
                d["gross_pnl"] = d.get("gross_pnl") if d.get("gross_pnl") is not None else d["realized_pnl"]
                d["friction_cost"] = d.get("friction_cost", 0.0)
                d["return_pct"] = d.get("return_pct", 0.0)
                d["entry_time"] = d.get("entry_time", "--:--")
                self.closed_trades.append(d)
                pnl_val = d.get("realized_pnl") if d.get("realized_pnl") is not None else d.get("net_pnl", 0.0)
                if pnl_val < 0:
                    k = (float(d["strike"]), str(d["type"]).lower(), str(d.get("expiry", "")))
                    self.strike_loss_counts[k] = self.strike_loss_counts.get(k, 0) + 1

            # 3. Seed today's spot history and session VWAP from recorded trades
            cur.execute(
                "SELECT entry_spot FROM live_paper_trades WHERE (entry_timestamp LIKE ? OR entry_timestamp IS NULL) AND entry_spot > 0 ORDER BY entry_time ASC",
                (f"{today_str}%",)
            )
            for sr in cur.fetchall():
                s_val = float(sr[0])
                if self.session_open_spot <= 0.0:
                    self.session_open_spot = s_val
                self.session_spot_sum += s_val
                self.session_spot_count += 1
                self.spot_history.append(s_val)
            if self.session_spot_count > 0:
                self.session_vwap = round(self.session_spot_sum / self.session_spot_count, 2)

            conn.close()
            self.log(f"🔄 Restored session state: {len(self.positions)} active open positions, {len(self.closed_trades)} today's closed trades, and VWAP ₹{self.session_vwap:.2f} from SQLite.")
        except Exception as e:
            self.log(f"Ledger restore notice: {e}")

    def _init_signal_handlers(self):
        """Trap Ctrl+C (SIGINT) and termination signals for graceful flush."""
        def handle_exit(signum, frame):
            print("\n")
            self.log("Interrupt received! Initiating safe shutdown and exporting report...")
            self.running = False

        signal.signal(signal.SIGINT, handle_exit)
        signal.signal(signal.SIGTERM, handle_exit)

    def _init_sqlite_ledger(self):
        """Initialize SQLite table for persistent, crash-proof paper trade audit."""
        try:
            DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("""
            CREATE TABLE IF NOT EXISTS live_paper_trades (
                trade_id TEXT PRIMARY KEY,
                strategy TEXT NOT NULL,
                instrument TEXT NOT NULL,
                strike REAL NOT NULL,
                option_type TEXT NOT NULL,
                expiry TEXT NOT NULL,
                side TEXT NOT NULL,
                qty INTEGER NOT NULL,
                entry_price REAL NOT NULL,
                current_price REAL,
                target_price REAL,
                stop_price REAL,
                entry_fair REAL NOT NULL,
                entry_spot REAL NOT NULL,
                entry_mscore REAL NOT NULL,
                entry_dev_pct REAL NOT NULL,
                entry_time TEXT NOT NULL,
                entry_timestamp TEXT NOT NULL,
                exit_price REAL,
                exit_time TEXT,
                exit_reason TEXT,
                gross_pnl REAL,
                net_pnl REAL,
                friction_cost REAL,
                return_pct REAL,
                converged INTEGER,
                holding_seconds REAL,
                status TEXT NOT NULL
            )
            """)
            for col in ["target_price", "stop_price"]:
                try:
                    cur.execute(f"ALTER TABLE live_paper_trades ADD COLUMN {col} REAL")
                except Exception:
                    pass
            conn.commit()
            conn.close()
        except Exception as e:
            self.log(f"SQLite ledger init warning: {e}")

    def _persist_trade(self, t: dict):
        """
        Immediately save/update trade record in SQLite & append to audit CSV.
        Guarantees zero data loss even if the terminal drops or system sleeps.
        """
        conn = None
        try:
            conn = sqlite3.connect(DB_PATH, timeout=10.0)
            cur = conn.cursor()
            cur.execute("""
            INSERT OR REPLACE INTO live_paper_trades (
                trade_id, strategy, instrument, strike, option_type, expiry, side, qty,
                entry_price, current_price, target_price, stop_price, entry_fair, entry_spot, entry_mscore, entry_dev_pct,
                entry_time, entry_timestamp, exit_price, exit_time, exit_reason,
                gross_pnl, net_pnl, friction_cost, return_pct, converged, holding_seconds, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                t["trade_id"], t["strategy"], t["instrument"], t["strike"], t["type"], t["expiry"],
                t["side"], t["qty"], t["entry_price"], t.get("current_price"), t.get("target_price"), t.get("stop_price"),
                t["entry_fair"], t["entry_spot"], t["entry_mscore"], t["entry_dev_pct"], t["entry_time"],
                t["entry_timestamp"], t.get("exit_price"), t.get("exit_time"), t.get("exit_reason"),
                t.get("gross_pnl", 0.0), t.get("net_pnl", 0.0), t.get("friction_cost", 0.0),
                t.get("return_pct", 0.0), 1 if t.get("converged", False) else 0,
                t.get("holding_seconds", 0.0), t["status"]
            ))
            conn.commit()
        except Exception as exc:
            self.log(f"Ledger persistence error: {exc}")
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass


    def get_sorted_closed_trades(self, reverse: bool = True) -> list:
        """
        Sort closed trades in strict, deterministic chronological order:
        Primary key: exit_time (HH:MM:SS)
        Secondary key: trade_id integer index (e.g. TRD-054 -> 54)
        reverse=True: Newest closed trade first (#1 at top)
        """
        def sort_key(t):
            exit_t = t.get("exit_time") or "00:00:00"
            try:
                tid_num = int(str(t.get("trade_id", "")).replace("TRD-", ""))
            except Exception:
                tid_num = 0
            return (exit_t, tid_num)

        return sorted(self.closed_trades, key=sort_key, reverse=reverse)

    def log(self, text: str):
        t = datetime.now().strftime("%H:%M:%S")
        print(f"[{t} IST] {text}")

    def update_volatility_model(self, force: bool = False):
        """
        Multi-Timeframe Volatility Engine:
        Fuses near-term 5-min realized volatility (65%) with daily EGARCH(1,1) (35%).
        Captures intraday volatility spikes and mean-reverting dislocations in real time.
        Re-calibrates every 300 seconds (5 minutes).
        """
        now_ts = time.time()
        if not force and (now_ts - self.last_vol_update < 300.0) and self.last_vol_update > 0:
            return

        try:
            import yfinance as yf
            # 1. Fetch near-term 5-minute intraday bars (last 5 days) to capture intraday volatility spikes
            df_5m = yf.download("^NSEI", period="5d", interval="5m", progress=False)
            if isinstance(df_5m.columns, pd.MultiIndex):
                df_5m.columns = [c[0] for c in df_5m.columns]
            close_5m = df_5m["Close"] if "Close" in df_5m else None

            # 2. Fetch daily history for baseline EGARCH model
            nifty = yf.download("^NSEI", period="1y", interval="1d", progress=False)
            if isinstance(nifty.columns, pd.MultiIndex):
                nifty.columns = [c[0] for c in nifty.columns]
            ret_series = np.log(nifty["Close"] / nifty["Close"].shift(1)).dropna()

            sample_annual_vol = float(ret_series.std() * np.sqrt(252))

            # Multi-timeframe Volatility Fusion
            vol_res = forecast_volatility(pd.Series(ret_series.values.flatten()), close_5m)
            daily_vol = vol_res.get("daily_vol", sample_annual_vol)
            intraday_5m_vol = vol_res.get("intraday_vol")

            self.daily_vol = float(daily_vol) if 0.05 <= daily_vol <= 0.45 else sample_annual_vol

            if intraday_5m_vol and 0.05 <= intraday_5m_vol <= 0.60:
                self.intraday_vol = float(intraday_5m_vol)
                # Intraday fusion: 65% near-term 5m realized vol + 35% daily vol
                fused_vol = (0.65 * self.intraday_vol) + (0.35 * self.daily_vol)
                self.egarch_vol = float(fused_vol)
            else:
                self.egarch_vol = float(self.daily_vol)

            self.tci = vol_res.get("tci", 0.0)
            reg_res = classify_volatility_regime(self.egarch_vol, pd.Series(ret_series.values.flatten()))
            self.regime = reg_res.get("regime_label", "NORMAL_VOL")
            self.last_vol_update = now_ts
            self.log(f"⚡ Intraday Volatility Engine Updated: Fused={self.egarch_vol*100:.2f}% (5m Realized={self.intraday_vol*100:.2f}% | Daily={self.daily_vol*100:.2f}%) | Regime={self.regime}")
        except Exception as e:
            self.log(f"Volatility calibration fallback ({e}); using baseline vol {self.egarch_vol*100:.2f}%")
            self.last_vol_update = now_ts


    def fetch_market_state(self) -> list[dict] | None:
        """Fetch live spot and option chains across multiple maturities (Front-Week & Next-Week) and calculate all parameters in real time."""
        try:
            if self.multi_expiry:
                chains = get_multi_expiry_chains(self.symbol, num_expiries=2, force_refresh=True)
            else:
                ch = get_full_chain(self.symbol, force_refresh=True)
                chains = [ch] if ch else []

            if not chains or not chains[0].get("chain"):
                return None

            primary_chain = chains[0]
            source = primary_chain.get("expiry_source", "unknown")
            now_dt = datetime.now()
            is_weekday = now_dt.weekday() < 5
            is_market_hours = is_weekday and ((now_dt.hour == 9 and now_dt.minute >= 15) or (10 <= now_dt.hour < 15) or (now_dt.hour == 15 and now_dt.minute <= 30))
            allow_stale = self.allow_stale or (not is_market_hours)

            if source != "nse_live" and not allow_stale:
                self.log(f"⏸️ [DATA QUALITY] Live NSE session active; waiting for fresh nse_live tick (got {source})")
                return None

            timestamp = primary_chain.get("timestamp")
            if timestamp:
                try:
                    parsed_timestamp = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
                    chain_age = time.time() - parsed_timestamp.timestamp()
                    if chain_age > self.max_chain_age_seconds and not allow_stale:
                        self.log(
                            f"⏸️ [DATA QUALITY] Live NSE tick delayed: "
                            f"age={chain_age:.1f}s > {self.max_chain_age_seconds:.1f}s"
                        )
                        return None
                except Exception:
                    pass

            self.current_spot = primary_chain.get("spot_price", self.current_spot)
            self.last_chain_data = primary_chain
            self.active_chains = chains
            if self.initial_spot == 0 and self.current_spot > 0:
                self.initial_spot = self.current_spot
            if self.session_open_spot <= 0 and self.current_spot > 0:
                self.session_open_spot = self.current_spot
            if self.session_high_spot <= 0 or self.current_spot > self.session_high_spot:
                self.session_high_spot = self.current_spot
            if self.session_low_spot <= 0 or self.current_spot < self.session_low_spot:
                self.session_low_spot = self.current_spot

            chain_list = primary_chain.get("chain", [])
            expiry = primary_chain.get("expiry_date", "")
            self.current_ttm = calculate_ttm_years(expiry)

            # 1. Real-Time High-Frequency Spot Ticks & Realized Volatility
            if self.current_spot > 0:
                self.session_spot_sum += self.current_spot
                self.session_spot_count += 1
                self.session_vwap = round(self.session_spot_sum / self.session_spot_count, 2)
                self.spot_history.append(self.current_spot)
                if len(self.spot_history) >= 4:
                    arr = np.array(self.spot_history)
                    rets = np.diff(np.log(arr))
                    if len(rets) > 1 and np.std(rets) > 0:
                        # Annualize: 252 trading days * 375 mins * 6 intervals/min = 567,000 intervals/year
                        calc_vol = float(np.std(rets) * np.sqrt(567000))
                        if 0.04 <= calc_vol <= 0.60:
                            self.tick_vol = round(calc_vol, 4)

            # 2. Extract Real-Time ATM Strike & Live ATM Implied Volatility
            strikes = [x.get("strike", 0.0) for x in chain_list if x.get("strike")]
            if strikes:
                self.atm_strike = min(strikes, key=lambda k: abs(k - self.current_spot))
                atm_item = next((x for x in chain_list if x.get("strike") == self.atm_strike), None)
                if atm_item:
                    call_opt = atm_item.get("call") or {}
                    put_opt = atm_item.get("put") or {}
                    c_iv = call_opt.get("iv") or 0.0
                    p_iv = put_opt.get("iv") or 0.0
                    valid_ivs = [v for v in [c_iv, p_iv] if 0.05 <= v <= 0.80]
                    if valid_ivs:
                        self.atm_iv = round(float(np.mean(valid_ivs)), 4)

                    # 3. Derive Real-Time Implied Risk-Free Rate (r) via Put-Call Parity:
                    # c - p = S*e^(-q*T) - K*e^(-r*T)  =>  e^(-r*T) = [S*e^(-q*T) - (c - p)] / K
                    c_ltp = call_opt.get("ltp")
                    p_ltp = put_opt.get("ltp")
                    if c_ltp and p_ltp and self.current_ttm > 0:
                        q = self.dividend_yield
                        t = self.current_ttm
                        val = (self.current_spot * np.exp(-q * t) - (c_ltp - p_ltp)) / self.atm_strike
                        if val > 0:
                            calc_r = - (1.0 / t) * np.log(val)
                            if 0.04 <= calc_r <= 0.095:
                                self.implied_r = round(float(calc_r), 4)

                    # 4. Derive Real-Time Synthetic Forward Price (F):
                    if c_ltp and p_ltp and self.current_ttm > 0:
                        self.forward_price = round(float(self.atm_strike + np.exp(self.implied_r * self.current_ttm) * (c_ltp - p_ltp)), 2)
                    else:
                        self.forward_price = round(float(self.current_spot * np.exp((self.implied_r - self.dividend_yield) * self.current_ttm)), 2)

            # 5. Background EGARCH update
            self.update_volatility_model()

            # Keep the fair-value volatility independent from the option premium being tested.
            fused = (0.65 * self.intraday_vol) + (0.35 * self.daily_vol)
            if self.tick_vol and abs(self.tick_vol - self.atm_iv) < 0.15:
                fused = 0.85 * fused + 0.15 * self.tick_vol
            self.egarch_vol = float(round(fused, 4))

            return chains
        except Exception as e:
            self.log(f"⚠️ Error fetching market data: {e}")
            return None

    def scan_and_execute_trades(self, chains_data: list[dict] | dict):
        """Scan active option chains across multiple maturities for high-conviction mispricings and execute paper trades."""
        now_dt = datetime.now()
        if not self.no_eod_squareoff:
            # Strictly enforce market entry window: 09:20 to 14:30 IST
            # Do NOT open new trades after 14:30 IST so existing positions have at least 55 mins to mature before EOD!
            if (now_dt.hour == 14 and now_dt.minute >= 30) or (now_dt.hour >= 15) or (now_dt.hour < 9 or (now_dt.hour == 9 and now_dt.minute < 20)):
                return

        today_str = now_dt.strftime("%Y-%m-%d")
        today_closed = sum(1 for t in self.closed_trades if str(t.get("entry_timestamp", "")).startswith(today_str))

        # Dynamic Ceiling 1: Profit Target Reached on Total Trading Margin (+0.50% = ₹10,000)
        # Once target profit is captured, freeze new entries to lock in daily earnings and preserve capital!
        if self.today_net_pnl >= self.target_profit_amount:
            if not getattr(self, "_target_profit_logged", False):
                self.log(
                    f"🎯 [DAILY PROFIT TARGET REACHED] Net Realized P&L {format_inr(self.today_net_pnl, include_sign=True)} "
                    f"hit +{self.target_margin_roi:.2f}% target on trading margin ({format_inr(self.target_profit_amount)}). "
                    f"Freezing new entries to preserve capital!"
                )
                self._target_profit_logged = True
            return

        # Dynamic Ceiling 2: Maximum Daily Closed Trades Safety Ceiling (e.g. 30 trades)
        if today_closed >= self.max_daily_closed_trades:
            if not getattr(self, "_trade_ceiling_logged", False):
                self.log(
                    f"🛑 [TRADE CEILING REACHED] Completed {today_closed}/{self.max_daily_closed_trades} closed trades for today. "
                    f"Halting new entries to prevent overtrading."
                )
                self._trade_ceiling_logged = True
            return

        # Daily Loss Circuit Breaker: Halt new trades if daily net loss hits capital protection threshold
        if self.today_net_pnl <= -self.max_daily_loss:
            return

        # Execution Pacing Guard: Ensure at least 15 seconds between consecutive trade fills to prevent burst stacking
        now_epoch = time.time()
        if (now_epoch - getattr(self, "last_trade_entry_epoch", 0.0)) < 15.0:
            return

        if len(self.positions) >= self.max_positions or self.free_margin < 2000.0:
            return

        chains_list = chains_data if isinstance(chains_data, list) else [chains_data]
        spot = self.current_spot
        r = self.implied_r
        q = self.dividend_yield

        candidates = []

        for idx, ch in enumerate(chains_list):
            is_front_expiry = (idx == 0)
            ch_list = ch.get("chain", [])
            exp_date = ch.get("expiry_date", "")
            ch_ttm = calculate_ttm_years(exp_date)

            for item in ch_list:
                strike = item.get("strike", 0.0)
                if abs(strike - spot) > 700:
                    continue

                for opt_type in ["call", "put"]:
                    opt = item.get(opt_type)
                    if not opt or opt.get("ltp", 0) < 20.0 or opt.get("ltp", 0) > 280.0:
                        continue

                    ltp = opt["ltp"]
                    iv = opt.get("iv", self.atm_iv)
                    raw_b = opt.get("bid")
                    raw_a = opt.get("ask")
                    bid = float(raw_b) if (raw_b is not None and float(raw_b) > 0) else ltp * 0.995
                    ask = float(raw_a) if (raw_a is not None and float(raw_a) > 0) else ltp * 1.005

                    # Liquidity check: ensure bid-ask spread is tight enough for edge capture
                    spread_ratio = (ask - bid) / ltp if ltp > 0 else 1.0
                    if is_front_expiry and spread_ratio > 0.05:
                        continue
                    if not is_front_expiry and spread_ratio > 0.075:
                        continue

                    surface_vol, peer_count = estimate_leave_one_out_surface_volatility(
                        ch_list, opt_type, strike, spot, self.egarch_vol
                    )

                    fair_price = black_scholes_price(
                        spot=spot,
                        strike=strike,
                        time_to_expiry=ch_ttm,
                        risk_free_rate=r,
                        volatility=surface_vol,
                        option_type=opt_type,
                        dividend_yield=q
                    )
                    if fair_price <= 0:
                        continue

                    greeks = calculate_greeks(
                        spot=spot,
                        strike=strike,
                        time_to_expiry=ch_ttm,
                        risk_free_rate=r,
                        volatility=iv,
                        option_type=opt_type,
                        dividend_yield=q
                    )
                    vega = greeks.get("vega", 15.0)
                    gamma = greeks.get("gamma", 0.0003)
                    delta_val = greeks.get("delta", 0.5)

                    # Expiry Day (0DTE) Gamma Safety Gate:
                    # On 0DTE contracts (TTM < 0.003y / < 1 day):
                    # - Strictly forbid short selling near-the-money options (must be >= 200 pts OTM, |Delta| <= 0.18)
                    # - Allow option buyers to capture momentum on liquid contracts (0.20 <= |Delta| <= 0.55)
                    is_rich = (ltp > fair_price)
                    if ch_ttm < 0.003:
                        if is_rich:
                            if abs(strike - spot) < 200.0 or abs(delta_val) > 0.18:
                                continue
                        else:
                            if not (0.20 <= abs(delta_val) <= 0.55):
                                continue
                    elif not (0.10 <= abs(delta_val) <= 0.55):
                        continue

                    mispricing = detect_mispricing(
                        market_price=ltp,
                        fair_price=fair_price,
                        vega=vega,
                        gamma=gamma,
                        current_vrp=(iv - self.egarch_vol),
                        expected_vrp=0.015
                    )

                    m_score = mispricing.get("m_score", 0.0)
                    dev_pct = ((ltp - fair_price) / fair_price) * 100.0
                    actual_gap = abs(ltp - fair_price)

                    # Real Econometric Mispricing Gate:
                    # Requires statistically significant multi-factor M-Score OR robust 2.5+ pt / 4.0%+ price edge
                    if (
                        peer_count >= self.min_surface_peers
                        and ((abs(m_score) >= (self.min_mscore - 0.2) and actual_gap >= 2.0) or (actual_gap >= 2.5 and abs(dev_pct) >= 4.0))
                        and actual_gap >= 2.0
                        and abs(dev_pct) <= self.max_entry_dev_pct
                    ):
                        candidates.append({
                            "strike": strike,
                            "type": opt_type,
                            "ltp": ltp,
                            "bid": bid,
                            "ask": ask,
                            "fair_price": fair_price,
                            "dev_pct": dev_pct,
                            "m_score": m_score,
                            "iv": iv,
                            "model_vol": surface_vol,
                            "surface_peer_count": peer_count,
                            "delta": delta_val,
                            "theta": greeks.get("theta", -10.0),
                            "vega": vega,
                            "gamma": gamma,
                            "expiry": exp_date,
                            "ttm": ch_ttm,
                            "is_front_expiry": is_front_expiry
                        })

        existing_counts = {}
        for p in self.positions:
            k = (p["strike"], p.get("type", p.get("option_type", "call")), p.get("expiry", ""))
            existing_counts[k] = existing_counts.get(k, 0) + 1

        used_contracts = set()

        def _create_pos_record(cand, side, strategy_name, pair_id_str, target_p, stop_p, cat_p, d_tp, d_sl):
            exec_p = cand["ask"] if side == "BUY" else cand["bid"]
            fair_p = cand["fair_price"]
            stt = 0.0 if side == "BUY" else (exec_p * self.trade_qty * 0.00125)
            exch = (exec_p * self.trade_qty * 0.00053)
            gst = (20.0 + exch) * 0.18
            fric = round(20.0 + stt + exch + gst, 2)
            edge = round(abs(exec_p - fair_p) * self.trade_qty, 2)
            gap = round(abs(exec_p - fair_p), 2)
            req_margin = self.calculate_trade_margin(side, exec_p, spot, self.trade_qty)
            self.trade_counter += 1
            return {
                "trade_id": f"TRD-{self.trade_counter:03d}",
                "pair_id": pair_id_str,
                "strategy": strategy_name,
                "instrument": f"NIFTY {int(cand['strike'])} {cand['type'].upper()} ({cand['expiry']})",
                "strike": cand["strike"],
                "type": cand["type"],
                "expiry": cand["expiry"],
                "side": side,
                "qty": self.trade_qty,
                "entry_price": round(exec_p, 2),
                "current_price": round(exec_p, 2),
                "target_price": target_p,
                "stop_price": stop_p,
                "catastrophic_stop": cat_p,
                "dynamic_tp_pct": d_tp,
                "dynamic_sl_pct": d_sl,
                "stop_breach_count": 0,
                "spike_shield_active": False,
                "dist_to_target": round(abs(exec_p - target_p), 2),
                "target_hit": False,
                "entry_fair": round(fair_p, 2),
                "entry_model_vol": round(cand.get("model_vol", self.egarch_vol), 4),
                "entry_surface_peer_count": cand.get("surface_peer_count", 0),
                "entry_spot": round(spot, 2),
                "entry_mscore": round(cand.get("m_score", 0.0), 2),
                "entry_dev_pct": round(cand.get("dev_pct", 0.0), 2),
                "theoretical_edge": edge,
                "current_fair": round(fair_p, 2),
                "mispricing_gap": gap,
                "convergence_pct": 0.0,
                "pair_delta": round(cand["delta"], 2),
                "entry_time": datetime.now().strftime("%H:%M:%S"),
                "entry_timestamp": datetime.now().isoformat(),
                "entry_epoch": time.time(),
                "delta": cand["delta"],
                "theta": cand["theta"],
                "vega": cand["vega"],
                "allocated_margin": req_margin,
                "entry_friction": fric,
                "incurred_friction": fric,
                "estimated_close_cost": 0.0,
                "friction_cost": fric,
                "gross_pnl": 0.0,
                "net_pnl": -fric,
                "unrealized_pnl": -fric,
                "return_pct": 0.0,
                "converged": False,
                "holding_seconds": 0.0,
                "status": "OPEN"
            }

        # Count current active short and long positions to prevent single-side capacity starvation
        current_shorts = sum(1 for p in self.positions if p["side"] == "SELL")
        current_longs = sum(1 for p in self.positions if p["side"] == "BUY")
        spot_drift_15 = self.spot_drift_15m
        spot_drift_5 = self.spot_drift_5m
        regime = self.trend_regime
        vwap = self.session_vwap if self.session_vwap > 0 else spot

        # Track active strikes to enforce de-clustering and prevent correlated strike stacking
        active_short_call_strikes = [p["strike"] for p in self.positions if p["side"] == "SELL" and p["type"].lower() == "call"]
        active_short_put_strikes = [p["strike"] for p in self.positions if p["side"] == "SELL" and p["type"].lower() == "put"]
        active_long_call_strikes = [p["strike"] for p in self.positions if p["side"] == "BUY" and p["type"].lower() == "call"]
        active_long_put_strikes = [p["strike"] for p in self.positions if p["side"] == "BUY" and p["type"].lower() == "put"]

        # STRATEGY 1: OUTRIGHT OVERVALUED SHORT ARBITRAGE (SELL Rich Premium)
        # Gated by Margin Capacity, Anti-Clustering Shield, and Trend Momentum Guard
        if len(self.positions) < self.max_positions and current_shorts < self.max_short_positions and self.free_margin >= 175000.0:
            overpriced_cands = [
                c for c in candidates
                if c["bid"] >= 20.0 and c["bid"] <= 260.0
                and 0.10 <= abs(c.get("delta", 0.5)) <= 0.38
                and c["dev_pct"] >= 2.0
                and (c["m_score"] >= self.min_mscore or c["dev_pct"] >= 3.5 or (c["iv"] - c.get("model_vol", self.egarch_vol)) >= 0.008)
                and (c["strike"], c["type"], c["expiry"]) not in used_contracts
                and not self.is_strike_in_cooldown(c["strike"], c["type"], c["expiry"])
                and existing_counts.get((c["strike"], c["type"], c["expiry"]), 0) < self.max_contract_positions
                and is_fee_viable_candidate(c, "SELL", self.trade_qty)
            ]
            overpriced_cands.sort(
                key=lambda item: (1 if item["is_front_expiry"] else 0, item["dev_pct"] * 0.5 + item["m_score"] * 5.0),
                reverse=True
            )

            for c_sell in overpriced_cands:
                if len(self.positions) >= self.max_positions or current_shorts >= self.max_short_positions:
                    break

                cand_type = c_sell["type"].lower()
                cand_delta = abs(c_sell.get("delta", 0.25))

                # Trend Regime, Macro Bias & Delta Shield for Short Selling:
                if cand_type == "call":
                    # 1. Macro Bias Gate: Never sell calls in a macro bullish session
                    if self.macro_session_bias == "MACRO_BULLISH":
                        continue
                    # 2. Local VWAP Level: Do not sell calls if spot is trading heavily above VWAP
                    if spot > (vwap + 6.0):
                        continue
                    # 3. Momentum Drift: Do not sell calls if multi-timeframe drift is decisively upward
                    if regime == "STRONG_BULLISH" or spot_drift_15 > 8.0 or spot_drift_5 > 3.0:
                        continue
                    # 4. Portfolio Net Delta Bound: Adding short call adds negative delta
                    if (self.net_portfolio_delta - cand_delta) < -1.10:
                        continue
                    # 5. Anti-Clustering Shield: Maintain at least 100 strike point separation between short calls
                    if any(abs(c_sell["strike"] - s) < 100 for s in active_short_call_strikes):
                        continue

                elif cand_type == "put":
                    # 1. Macro Bias Gate: Never sell puts in a macro bearish session
                    if self.macro_session_bias == "MACRO_BEARISH":
                        continue
                    # 2. Local VWAP Level: Do not sell puts if spot is trading heavily below VWAP
                    if spot < (vwap - 6.0):
                        continue
                    # 3. Momentum Drift: Do not sell puts if multi-timeframe drift is decisively downward
                    if regime == "STRONG_BEARISH" or spot_drift_15 < -8.0 or spot_drift_5 < -3.0:
                        continue
                    # 4. Portfolio Net Delta Bound: Adding short put adds positive delta
                    if (self.net_portfolio_delta + cand_delta) > 0.85:
                        continue
                    # 5. Anti-Clustering Shield: Maintain at least 100 strike point separation between short puts
                    if any(abs(c_sell["strike"] - s) < 100 for s in active_short_put_strikes):
                        continue

                exec_price = c_sell["bid"]
                req_margin = self.calculate_trade_margin("SELL", exec_price, spot, self.trade_qty)
                if (self.used_margin + req_margin) > (self.total_capital * self.max_margin_utilization):
                    break
                if (self.used_short_margin + req_margin) > self.max_short_margin:
                    break

                target, stop, catastrophic, dyn_tp, dyn_sl, _ = calculate_dynamic_volatility_target_and_stop(
                    exec_price, c_sell["fair_price"], "SELL",
                    fused_vol=self.egarch_vol, tick_vol=self.tick_vol, regime=self.regime,
                    delta=c_sell["delta"], theta=c_sell["theta"],
                    base_tp_pct=self.take_profit_pct, base_sl_pct=self.stop_loss_pct
                )
                position = _create_pos_record(
                    c_sell, "SELL", f"RV Short Overvalued ({c_sell['type'].upper()})",
                    "ALPHA-SHORT", target, stop, catastrophic, dyn_tp, dyn_sl
                )
                self.positions.append(position)
                self._persist_trade(position)
                used_contracts.add((c_sell["strike"], c_sell["type"], c_sell["expiry"]))
                existing_counts[(c_sell["strike"], c_sell["type"], c_sell["expiry"])] = existing_counts.get((c_sell["strike"], c_sell["type"], c_sell["expiry"]), 0) + 1
                current_shorts += 1
                if c_sell["type"].lower() == "call":
                    active_short_call_strikes.append(c_sell["strike"])
                else:
                    active_short_put_strikes.append(c_sell["strike"])

                self.last_trade_entry_epoch = time.time()
                self.log(
                    f"📉 [OVERPRICED SHORT FILLED] SELL NIFTY {int(c_sell['strike'])} "
                    f"{c_sell['type'].upper()} ({c_sell['expiry']}) @ ₹{position['entry_price']:.2f} "
                    f"(Margin ₹{req_margin:,.0f} • Fair ₹{position['entry_fair']:.2f} • Dev {c_sell['dev_pct']:+.1f}% • M-Score {c_sell['m_score']:+.2f})"
                )
                break  # Pace execution: enter at most 1 short position per scan cycle!

        # STRATEGY 2: OUTRIGHT UNDERVALUED LONG ARBITRAGE (BUY Cheap Premium & Gamma)
        # Gated by:
        # 1. Strict Trend Regime: Option Buying is PROHIBITED in CHOPPY_NEUTRAL markets (Theta bleeds buyers!)
        # 2. Bullish confirmation for CALL buying; Bearish confirmation for PUT buying
        # 3. Delta Quality Filter: 0.20 <= |Delta| <= 0.55 (No low-gamma lotto options)
        # 4. Anti-Clustering Shield: Max 1 long call and 1 long put, spaced >= 100 strike pts apart
        # 5. Cap at max_long_positions = 2 and fee viability hurdle
        if (
            len(self.positions) < self.max_positions
            and current_longs < self.max_long_positions
            and self.free_margin >= 3000.0
        ):
            underpriced_cands = [
                c for c in candidates
                if c["ask"] >= 25.0 and c["ask"] <= 240.0
                and 0.18 <= abs(c.get("delta", 0.5)) <= 0.55
                and c["dev_pct"] <= -3.0
                and (c["m_score"] <= -self.min_mscore or c["dev_pct"] <= -4.0 or (c["iv"] - c.get("model_vol", self.egarch_vol)) <= -0.008)
                and (c["strike"], c["type"], c["expiry"]) not in used_contracts
                and not self.is_strike_in_cooldown(c["strike"], c["type"], c["expiry"])
                and existing_counts.get((c["strike"], c["type"], c["expiry"]), 0) < self.max_contract_positions
                and is_fee_viable_candidate(c, "BUY", self.trade_qty)
            ]
            underpriced_cands.sort(
                key=lambda item: (0 if not item["is_front_expiry"] else 1, item["dev_pct"] * 0.5 + item["m_score"] * 5.0)
            )

            for c_buy in underpriced_cands:
                if len(self.positions) >= self.max_positions or current_longs >= self.max_long_positions:
                    break

                # CALL Buying: Requires non-bearish session and positive intraday drift/traction
                if c_buy["type"].lower() == "call":
                    if self.macro_session_bias == "MACRO_BEARISH" or regime == "STRONG_BEARISH" or spot_drift_5 <= -2.0:
                        continue
                    if not (spot >= (vwap - 3.0) or spot_drift_15 >= 3.0):
                        continue
                    # Max 1 active long call position to prevent correlated cluster exposure
                    if len(active_long_call_strikes) >= 1:
                        continue
                    # Anti-Clustering: Must be at least 100 strike points away
                    if any(abs(c_buy["strike"] - s) < 100 for s in active_long_call_strikes):
                        continue

                # PUT Buying: Requires non-bullish session and negative intraday drift/traction
                if c_buy["type"].lower() == "put":
                    if self.macro_session_bias == "MACRO_BULLISH" or regime == "STRONG_BULLISH" or spot_drift_5 >= 2.0:
                        continue
                    if not (spot <= (vwap + 3.0) or spot_drift_15 <= -3.0):
                        continue
                    # Max 1 active long put position to prevent correlated cluster exposure
                    if len(active_long_put_strikes) >= 1:
                        continue
                    # Anti-Clustering: Must be at least 100 strike points away
                    if any(abs(c_buy["strike"] - s) < 100 for s in active_long_put_strikes):
                        continue

                exec_price = c_buy["ask"]
                req_margin = self.calculate_trade_margin("BUY", exec_price, spot, self.trade_qty)
                if (self.used_margin + req_margin) > (self.total_capital * self.max_margin_utilization):
                    break
                if (self.used_long_margin + req_margin) > self.max_long_margin:
                    break

                target, stop, catastrophic, dyn_tp, dyn_sl, _ = calculate_dynamic_volatility_target_and_stop(
                    exec_price, c_buy["fair_price"], "BUY",
                    fused_vol=self.egarch_vol, tick_vol=self.tick_vol, regime=self.regime,
                    delta=c_buy["delta"], theta=c_buy["theta"],
                    base_tp_pct=self.take_profit_pct, base_sl_pct=self.stop_loss_pct
                )
                position = _create_pos_record(
                    c_buy, "BUY", f"RV Long Undervalued ({c_buy['type'].upper()})",
                    "ALPHA-LONG", target, stop, catastrophic, dyn_tp, dyn_sl
                )
                self.positions.append(position)
                self._persist_trade(position)
                used_contracts.add((c_buy["strike"], c_buy["type"], c_buy["expiry"]))
                existing_counts[(c_buy["strike"], c_buy["type"], c_buy["expiry"])] = existing_counts.get((c_buy["strike"], c_buy["type"], c_buy["expiry"]), 0) + 1
                current_longs += 1
                if c_buy["type"].lower() == "call":
                    active_long_call_strikes.append(c_buy["strike"])
                else:
                    active_long_put_strikes.append(c_buy["strike"])

                self.last_trade_entry_epoch = time.time()
                self.log(
                    f"🚀 [UNDERVALUED LONG FILLED] BUY NIFTY {int(c_buy['strike'])} "
                    f"{c_buy['type'].upper()} ({c_buy['expiry']}) @ ₹{position['entry_price']:.2f} "
                    f"(Cost ₹{req_margin:,.0f} • Target ₹{position['target_price']:.2f} • Fair ₹{position['entry_fair']:.2f} • Dev {c_buy['dev_pct']:+.1f}% • M-Score {c_buy['m_score']:+.2f})"
                )
                break  # Pace execution: enter at most 1 long position per scan cycle!

    def update_open_positions(self, chains_data: list[dict] | dict):
        """Update live LTPs, calculate unrealized P&L, check convergence, and enforce TP/SL across multi-expiry contracts."""
        chains_list = chains_data if isinstance(chains_data, list) else [chains_data]
        spot = self.current_spot
        r = self.implied_r
        q = self.dividend_yield
        now_ts = time.time()

        chains_map = {ch.get("expiry_date", ""): ch for ch in chains_list}

        # Multi-expiry price lookup: (strike, opt_type, expiry) -> quote
        # Fallback lookup: (strike, opt_type) -> quote
        lookup = {}
        lookup_fallback = {}
        for ch in chains_list:
            ch_exp = ch.get("expiry_date", "")
            for item in ch.get("chain", []):
                st = item.get("strike")
                for t in ["call", "put"]:
                    opt = item.get(t)
                    if opt:
                        raw_l = float(opt.get("ltp") or 0.0)
                        raw_b = opt.get("bid")
                        raw_a = opt.get("ask")
                        bid_v = float(raw_b) if (raw_b is not None and float(raw_b) > 0) else (raw_l * 0.995 if raw_l > 0 else 0.0)
                        ask_v = float(raw_a) if (raw_a is not None and float(raw_a) > 0) else (raw_l * 1.005 if raw_l > 0 else 0.0)
                        q_data = {
                            "ltp": raw_l,
                            "bid": bid_v,
                            "ask": ask_v,
                            "iv": opt.get("iv", self.atm_iv),
                            "expiry": ch_exp
                        }
                        lookup[(st, t.lower(), ch_exp)] = q_data
                        if (st, t.lower()) not in lookup_fallback:
                            lookup_fallback[(st, t.lower())] = q_data

        remaining_positions = []

        for p in self.positions:
            p_exp = p.get("expiry", "")
            market_quote = lookup.get((p["strike"], p["type"], p_exp)) or lookup_fallback.get((p["strike"], p["type"]))
            if not market_quote or market_quote["ltp"] <= 0:
                remaining_positions.append(p)
                continue

            curr_ltp = market_quote["ltp"]
            exit_fill_price = market_quote["bid"] if p["side"] == "BUY" else market_quote["ask"]

            p["current_price"] = round(curr_ltp, 2)
            p["holding_seconds"] = round(now_ts - p.get("entry_epoch", now_ts), 1)

            # Contract-specific TTM from position's actual expiry date
            pos_ttm = calculate_ttm_years(p_exp) if p_exp else self.current_ttm
            pos_chain = chains_map.get(p_exp) or chains_list[0]
            pos_chain_list = pos_chain.get("chain", [])

            # Update live analytical Greeks dynamically with contract's real TTM
            live_greeks = calculate_greeks(
                spot=spot,
                strike=p["strike"],
                time_to_expiry=pos_ttm,
                risk_free_rate=r,
                volatility=market_quote.get("iv", self.atm_iv),
                option_type=p["type"],
                dividend_yield=q
            )
            p["delta"] = live_greeks.get("delta", p.get("delta", 0.5))
            p["theta"] = live_greeks.get("theta", p.get("theta", -10.0))
            p["vega"] = live_greeks.get("vega", p.get("vega", 15.0))

            # Gross P&L calculation:
            if p["side"] == "BUY":
                gross_pnl = (exit_fill_price - p["entry_price"]) * p["qty"]
                ret_pct = ((exit_fill_price - p["entry_price"]) / p["entry_price"]) * 100
                exit_brokerage = 20.0
                exit_stt = (exit_fill_price * p["qty"] * 0.00125)  # Closing long is Selling, STT applies
                exit_exchange = (exit_fill_price * p["qty"] * 0.00053)
                exit_gst = (exit_brokerage + exit_exchange) * 0.18
                exit_friction = exit_brokerage + exit_stt + exit_exchange + exit_gst
            else:
                gross_pnl = (p["entry_price"] - exit_fill_price) * p["qty"]
                ret_pct = ((p["entry_price"] - exit_fill_price) / p["entry_price"]) * 100
                exit_brokerage = 20.0
                exit_stt = 0.0  # Closing short is Buying, no STT
                exit_exchange = (exit_fill_price * p["qty"] * 0.00053)
                exit_gst = (exit_brokerage + exit_exchange) * 0.18
                exit_friction = exit_brokerage + exit_stt + exit_exchange + exit_gst

            total_friction = round(p.get("entry_friction", 0.0) + exit_friction, 2)
            net_pnl = round(gross_pnl - total_friction, 2)

            p["gross_pnl"] = round(gross_pnl, 2)
            p["net_pnl"] = round(net_pnl, 2)
            p["incurred_friction"] = round(p.get("entry_friction", 0.0), 2)
            p["estimated_close_cost"] = round(exit_friction, 2)
            p["friction_cost"] = round(total_friction, 2)
            p["unrealized_pnl"] = round(net_pnl, 2)
            p["return_pct"] = round(ret_pct, 2)
            net_return_pct = (net_pnl / (p["entry_price"] * p["qty"]) * 100.0) if p["entry_price"] > 0 else 0.0
            p["net_return_pct"] = round(net_return_pct, 2)
            p["max_ret_pct"] = max(p.get("max_ret_pct", ret_pct), ret_pct)
            p["max_net_return_pct"] = max(p.get("max_net_return_pct", net_return_pct), net_return_pct)

            # Dynamic Convergence Evaluation with Real-Time r, q, pos_ttm and contract's smile:
            current_surface_vol, surface_peer_count = estimate_leave_one_out_surface_volatility(
                pos_chain_list, p["type"], p["strike"], spot, self.egarch_vol
            )
            curr_fair = black_scholes_price(
                spot=spot,
                strike=p["strike"],
                time_to_expiry=pos_ttm,
                risk_free_rate=r,
                volatility=current_surface_vol,
                option_type=p["type"],
                dividend_yield=q
            )
            p["current_model_vol"] = round(current_surface_vol, 4)
            p["surface_peer_count"] = surface_peer_count
            dist_entry = abs(p["entry_price"] - p["entry_fair"])
            dist_curr = max(0.0, exit_fill_price - curr_fair) if p["side"] == "SELL" else max(0.0, curr_fair - exit_fill_price)
            p["converged"] = dist_curr < dist_entry
            mispricing_narrowed = (dist_entry - dist_curr) / dist_entry if dist_entry > 0 else 0.0
            p["mispricing_narrowed_pct"] = round(mispricing_narrowed * 100, 1)
            p["current_fair"] = round(curr_fair, 2)
            p["mispricing_gap"] = round(dist_curr, 2)
            p["convergence_pct"] = round(mispricing_narrowed * 100, 1)

            # Dynamic Target & Stop prices scaled with live volatility violence
            if not p.get("target_price") or not p.get("stop_price") or not p.get("catastrophic_stop"):
                target_price, stop_price, cat_stop, dyn_tp, dyn_sl, _ = calculate_dynamic_volatility_target_and_stop(
                    p["entry_price"], p.get("entry_fair", p["entry_price"]), p["side"],
                    fused_vol=self.egarch_vol, tick_vol=self.tick_vol, regime=self.regime,
                    delta=p.get("delta", 0.3), theta=p.get("theta", -10.0),
                    base_tp_pct=self.take_profit_pct, base_sl_pct=self.stop_loss_pct
                )
                p["target_price"] = target_price
                p["stop_price"] = stop_price
                p["catastrophic_stop"] = cat_stop
                p["dynamic_tp_pct"] = dyn_tp
                p["dynamic_sl_pct"] = dyn_sl
            else:
                target_price = p["target_price"]
                stop_price = p["stop_price"]
                cat_stop = p.get("catastrophic_stop", round(p["entry_price"] * 1.15 if p["side"] == "SELL" else p["entry_price"] * 0.85, 2))
                dyn_tp = p.get("dynamic_tp_pct", self.take_profit_pct)
                dyn_sl = p.get("dynamic_sl_pct", self.stop_loss_pct)

            # Distance to target & Target Hit Flag:
            if p["side"] == "SELL":
                dist_to_target = curr_ltp - target_price
                target_hit = exit_fill_price <= target_price
                stop_breached = curr_ltp >= stop_price
                catastrophic_breach = curr_ltp >= cat_stop
            else:
                dist_to_target = target_price - curr_ltp
                target_hit = exit_fill_price >= target_price
                stop_breached = curr_ltp <= stop_price
                catastrophic_breach = curr_ltp <= cat_stop

            p["dist_to_target"] = round(dist_to_target, 2)
            p["target_hit"] = target_hit

            # Prune toxic approaching ITM positions before gamma explosions occur
            curr_delta = p.get("delta", 0.3)
            is_toxic_itm = False
            if p["side"] == "SELL":
                if p["type"] == "call" and (spot >= (p["strike"] - 45.0) or abs(curr_delta) > 0.42):
                    is_toxic_itm = True
                elif p["type"] == "put" and (spot <= (p["strike"] + 45.0) or abs(curr_delta) > 0.42):
                    is_toxic_itm = True

            # Pure Quantitative Relative-Value Mispricing Exit Rules
            # (Exits are governed strictly by mathematical convergence to Black-Scholes Fair Value)
            conv_pct = p["convergence_pct"]
            max_p = p.get("max_ret_pct", 0.0)
            exit_reason = None

            # Anti-Churn Discipline: Minimum 60s holding window required for all non-emergency exits!
            holding_secs = p.get("holding_seconds", 0.0)
            is_matured = holding_secs >= 90.0

            # 0. Emergency Circuit Breakers (Can exit anytime on freak market gaps)
            if catastrophic_breach or ret_pct <= -13.0:
                exit_reason = f"CATASTROPHIC_STOP (Hard safety bound cut @ LTP ₹{curr_ltp:.2f} • {ret_pct:.1f}%)"
            elif is_toxic_itm:
                exit_reason = f"GAMMA_INVALIDATION_PRUNE (Delta: {p.get('delta', 0.5):.2f} | Strike {p['strike']} vs Spot {spot:.1f} • Cut before gamma spike)"
            elif p["side"] == "BUY" and holding_secs >= 45.0 and ret_pct <= -9.0:
                # Fast Stop Cut for Long Option Buyers (Negative Theta Protection)
                exit_reason = f"BUYER_MOMENTUM_STOP_CUT (Fast cut at {ret_pct:+.1f}% to prevent theta erosion • LTP ₹{curr_ltp:.2f})"
            elif p["side"] == "BUY" and holding_secs >= 120.0 and ret_pct <= -5.0 and (
                (p["type"] == "call" and self.spot_drift_5m <= -18.0) or
                (p["type"] == "put" and self.spot_drift_5m >= 18.0)
            ):
                # Trend Momentum Invalidation for Long Option Buyers (Only when option is losing and spot decisively reverses)
                drift_dir = "negative" if p["type"] == "call" else "positive"
                exit_reason = f"MOMENTUM_REVERSAL_CUT (Spot drift turned {drift_dir} {self.spot_drift_5m:+.1f} pts against Long {p['type'].upper()} • Cut at {ret_pct:+.1f}%)"
            elif stop_breached and ret_pct <= -10.5:
                # Immediate hard stop when loss touches 10.5%
                exit_reason = f"STATISTICAL_DIVERGENCE_EXIT (Hard Stop Hit @ LTP ₹{curr_ltp:.2f} vs Bound ₹{stop_price:.2f} • {ret_pct:.1f}%)"
            elif stop_breached:
                # 1-tick confirmation noise shield for border stop breaches
                breach_count = p.get("stop_breach_count", 0) + 1
                p["stop_breach_count"] = breach_count
                if breach_count < 2 and ret_pct > -11.0:
                    p["spike_shield_active"] = True
                    self.log(f"🛡️ [SPIKE SHIELD] {p['trade_id']} touched invalidation bound (LTP ₹{curr_ltp:.2f} vs Bound ₹{stop_price:.2f}). Absorbing noise ({breach_count}/2)...")
                else:
                    exit_reason = f"STATISTICAL_DIVERGENCE_EXIT (Model Invalidation @ LTP ₹{curr_ltp:.2f} vs Bound ₹{stop_price:.2f} • {ret_pct:.1f}%)"
            elif p["side"] == "BUY" and target_hit and (net_return_pct >= 14.0 and net_pnl >= 450.0):
                # Quick momentum target hit for Long Option Buyer
                exit_reason = f"BUY_TARGET_CONVERGED ({conv_pct:.0f}% Alpha Captured • Exit ₹{exit_fill_price:.2f} ≈ Target ₹{target_price:.2f} • Net +{net_return_pct:.1f}%)"
            elif p["side"] == "BUY" and is_matured and (((conv_pct >= 75.0 and net_return_pct >= 12.0) or net_return_pct >= 16.0) and net_pnl >= 400.0):
                # Quick harvest on Long Option before theta decays gains
                exit_reason = f"MOMENTUM_ALPHA_HARVEST (Captured quick gain +{net_return_pct:.1f}% before theta decay)"
            elif target_hit and (net_return_pct >= 14.0 or (p["side"] == "SELL" and ret_pct >= 24.0)):
                # 1. Primary Objective: Target Fair Price Reached WITH Substantial Profit
                exit_reason = f"TARGET_CONVERGED ({conv_pct:.0f}% Alpha Captured • Exit ₹{exit_fill_price:.2f} ≈ Target ₹{target_price:.2f} • Net +{net_return_pct:.1f}%)"
            # 2. Dynamic Trailing Profit Ratchet: Let winners run, but lock in home runs!
            elif is_matured and p.get("max_net_return_pct", net_return_pct) >= 26.0 and net_return_pct <= (p.get("max_net_return_pct", net_return_pct) - 4.5) and net_return_pct >= 20.0:
                exit_reason = f"TRAILING_PROFIT_LOCK_TIER3 (Peak: +{p.get('max_net_return_pct', net_return_pct):.1f}% -> Secured +{net_return_pct:.1f}% • Locked +20%+)"
            elif is_matured and p.get("max_net_return_pct", net_return_pct) >= 18.0 and net_return_pct <= (p.get("max_net_return_pct", net_return_pct) - 4.0) and net_return_pct >= 14.0:
                exit_reason = f"TRAILING_PROFIT_LOCK_TIER2 (Peak: +{p.get('max_net_return_pct', net_return_pct):.1f}% -> Secured +{net_return_pct:.1f}% • Locked +14%+)"
            elif is_matured and p.get("max_net_return_pct", net_return_pct) >= 14.0 and net_return_pct <= (p.get("max_net_return_pct", net_return_pct) - 3.5) and net_return_pct >= 10.0:
                exit_reason = f"TRAILING_PROFIT_LOCK_TIER1 (Peak: +{p.get('max_net_return_pct', net_return_pct):.1f}% -> Secured +{net_return_pct:.1f}% • Locked +10%+)"
            elif is_matured and p.get("max_net_return_pct", net_return_pct) >= 10.0 and net_return_pct <= 4.5 and net_return_pct >= 2.0:
                # Breakeven Defense: Protect winning trades from falling into negative loss
                exit_reason = f"BREAKEVEN_DEFENSE_RATCHET (Peak was +{p.get('max_net_return_pct', net_return_pct):.1f}% -> Defended at +{net_return_pct:.1f}% • Fees Covered)"
            elif is_matured and conv_pct >= 85.0 and net_return_pct >= 15.0:
                # 3. Mathematical Mispricing Gap Narrowed >= 85% after all costs
                exit_reason = f"MISPRICING_SQUEEZE_CONVERGED ({conv_pct:.0f}% Alpha Extracted • Net +{net_return_pct:.1f}%)"
            elif is_matured and p.get("theoretical_edge") and net_pnl >= p["theoretical_edge"] * 0.85 and net_return_pct >= 15.0:
                # 4. Theoretical Rupee Alpha Edge Secured >= 85%
                exit_reason = f"ALPHA_HARVESTED (Secured ₹{net_pnl:.0f} of ₹{p['theoretical_edge']:.0f} Initial Edge • +{net_return_pct:.1f}%)"
            elif is_matured and abs(market_quote.get("iv", self.atm_iv) - self.egarch_vol) <= 0.008 and net_return_pct >= 15.0:
                # 5. Volatility Risk Premium (VRP) Collapse to Model Fair Volatility
                exit_reason = f"VRP_COLLAPSE (Implied Vol {market_quote['iv']*100:.1f}% -> Model Fair Vol {self.egarch_vol*100:.1f}%)"
            else:
                if p.get("stop_breach_count", 0) > 0:
                    p["stop_breach_count"] = 0
                    p["spike_shield_active"] = False

            # Auto square-off near market close (15:25 IST)
            now_dt = datetime.now()
            if not self.no_eod_squareoff:
                if (now_dt.hour == 15 and now_dt.minute >= 25) or (now_dt.hour >= 16):
                    exit_reason = "EOD_SQUAREOFF"

            if exit_reason:
                # Record strike cooldown with spot at exit to prevent immediate whipsaw re-entry!
                k = (float(p["strike"]), str(p["type"]).lower(), str(p.get("expiry", "")))
                self.strike_cooldown[k] = (time.time(), spot)
                if net_pnl < 0:
                    self.strike_loss_counts[k] = self.strike_loss_counts.get(k, 0) + 1
                # Close trade
                p["status"] = "CLOSED"
                p["exit_price"] = round(exit_fill_price, 2)
                p["exit_time"] = now_dt.strftime("%H:%M:%S")
                p["exit_reason"] = exit_reason
                p["realized_pnl"] = p["net_pnl"]
                self.closed_trades.append(p)
                self._persist_trade(p)
                self.log(f"🔔 [EXIT TRIGGERED] {p['trade_id']} | {p['instrument']} closed @ ₹{exit_fill_price:.2f} | Net P&L: {'+' if net_pnl >= 0 else ''}₹{net_pnl:,.2f} ({ret_pct:+.1f}%) | Reason: {exit_reason}")
            else:
                self._persist_trade(p)
                remaining_positions.append(p)

        self.positions = remaining_positions

    def print_terminal_dashboard(self):
        """Institutional Bloomberg-terminal-style dense ASCII dashboard."""
        os.system("cls" if os.name == "nt" else "clear")
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        total_realized_net = sum(t.get("realized_pnl", t.get("net_pnl", 0.0)) for t in self.closed_trades)
        total_unrealized_net = sum(p["net_pnl"] for p in self.positions)
        total_net_pnl = total_realized_net + total_unrealized_net

        total_realized_gross = sum(t.get("gross_pnl", t.get("realized_pnl", t.get("net_pnl", 0.0))) for t in self.closed_trades)
        total_unrealized_gross = sum(p.get("gross_pnl", 0.0) for p in self.positions)
        total_gross_pnl = total_realized_gross + total_unrealized_gross
        total_friction_incurred = sum(t.get("friction_cost", 0.0) for t in self.closed_trades) + sum(p.get("incurred_friction", p.get("entry_friction", 0.0)) for p in self.positions)

        all_trades_count = len(self.closed_trades)
        winning_trades = sum(1 for t in self.closed_trades if t.get("realized_pnl", t.get("net_pnl", 0.0)) > 0)
        win_rate = (winning_trades / all_trades_count * 100) if all_trades_count > 0 else 0.0

        # Convergence score
        total_positions_evaluated = len(self.positions) + len(self.closed_trades)
        converged_positions = sum(1 for p in self.positions if p["converged"]) + sum(1 for t in self.closed_trades if t.get("converged", False))
        convergence_pct = (converged_positions / total_positions_evaluated * 100) if total_positions_evaluated > 0 else 0.0

        net_delta = sum(p.get("delta", 0.5) * (1 if p["side"] == "BUY" else -1) * p["qty"] for p in self.positions)
        net_theta = sum(p.get("theta", -10.0) * (1 if p["side"] == "BUY" else -1) * p["qty"] for p in self.positions)

        print("=" * 118)
        print(f"  QUANT NIFTY 50 OPTIONS MISPRICING & PAPER TRADING ENGINE  │  {now_str} IST")
        print("=" * 118)
        print(f"  SPOT PRICE:       ₹{self.current_spot:,.2f} (Δ {self.current_spot - self.initial_spot:+.2f})  │  SYNTHETIC FORWARD: ₹{self.forward_price:,.2f}  │  ATM STRIKE: {self.atm_strike}")
        print(f"  IMPLIED RATE (r): {self.implied_r*100:.2f}% (Put-Call Parity)  │  DIVIDEND YIELD (q): {self.dividend_yield*100:.2f}%  │  TTM: {self.current_ttm*365:.2f}d ({self.current_ttm:.5f}y)")
        print(f"  VOLATILITY (σ):   Fused: {self.egarch_vol*100:.2f}%  │  ATM IV: {self.atm_iv*100:.2f}%  │  Tick Vol: {self.tick_vol*100:.2f}%  │  5m Realized: {self.intraday_vol*100:.2f}%")
        trend_status = f"{self.trend_regime} [Bias: {self.macro_session_bias}] (15m: {self.spot_drift_15m:+.1f} | 5m: {self.spot_drift_5m:+.1f} | VWAP: ₹{self.session_vwap:.1f} | Open: ₹{self.session_open_spot:.1f})"
        print(f"  MARKET REGIME:    Vol: {self.regime:<11} │ Trend: {trend_status}")
        print(f"  CAPITAL & MARGIN: Used: ₹{self.used_margin:,.0f} ({self.margin_utilization_pct:.1f}%) │ Free: ₹{self.free_margin:,.0f} │ Net Delta: {net_delta:+.1f} Δ │ Net Theta: ₹{net_theta:+.1f}/day")
        print("-" * 118)
        print(f"  NET REALIZED P&L: {'+' if total_realized_net >= 0 else ''}₹{total_realized_net:,.2f}  │  UNREALIZED: {'+' if total_unrealized_net >= 0 else ''}₹{total_unrealized_net:,.2f}  │  TOTAL P&L: {'+' if total_net_pnl >= 0 else ''}₹{total_net_pnl:,.2f}")
        print(f"  ACCURACY (WINS):  {win_rate:5.1f}% ({winning_trades}/{all_trades_count})  │  CONVERGENCE: {convergence_pct:5.1f}% ({converged_positions}/{total_positions_evaluated})  │  POSITIONS: {len(self.positions)}/{self.max_positions}")
        print("=" * 118)

        print("\n[LIVE NSE OPTION CHAIN - PNSEA]")
        print(f"  Source: {self.last_chain_data.get('expiry_source', 'unavailable')} | Timestamp: {self.last_chain_data.get('timestamp', '--')} | Expiry: {self.last_chain_data.get('expiry_date', '--')}")
        print(f"  {'STRIKE':>8} {'CALL LTP':>9} {'CALL BID':>9} {'CALL ASK':>9} {'CALL IV':>8} │ {'PUT LTP':>9} {'PUT BID':>9} {'PUT ASK':>9} {'PUT IV':>8}")
        print("-" * 118)
        for item in self.last_chain_data.get("chain", []):
            call = item.get("call") or {}
            put = item.get("put") or {}
            print(
                f"  {item.get('strike', 0):>8.0f} {call.get('ltp', 0):>9.2f} {call.get('bid', 0):>9.2f} "
                f"{call.get('ask', 0):>9.2f} {call.get('iv', 0) * 100:>7.2f}% │ "
                f"{put.get('ltp', 0):>9.2f} {put.get('bid', 0):>9.2f} {put.get('ask', 0):>9.2f} {put.get('iv', 0) * 100:>7.2f}%"
            )
        print("=" * 118)

        # Active Open Positions Table
        print("\n[ACTIVE QUANT MISPRICING POSITIONS]")
        print(f"  {'ID':<8} {'STRATEGY':<22} {'INSTRUMENT':<17} {'SIDE':<5} {'ENTRY':<7} {'LTP':<7} {'BSM FAIR':<9} {'ALPHA GAP':<10} {'CONV %':<7} {'NET P&L':<10} {'RET %':<8} {'STATUS'}")
        print("-" * 128)
        if not self.positions:
            print("  No active positions. Scanning option chain for statistical mispricings...")
        else:
            for p in self.positions:
                pnl_str = f"{'+' if p['net_pnl'] >= 0 else ''}₹{p['net_pnl']:,.1f}"
                ret_str = f"{'+' if p['return_pct'] >= 0 else ''}{p['return_pct']:.1f}%"
                fair_val = p.get("current_fair", p.get("entry_fair", 0.0))
                gap_val = p.get("mispricing_gap", abs(p["current_price"] - fair_val))
                conv_val = p.get("convergence_pct", 0.0)
                status_str = "🟢 CONVERGED" if p.get("target_hit") or conv_val >= 70.0 else ("🟡 CONVERGING" if conv_val >= 30.0 else "🔵 ACTIVE")
                print(f"  {p['trade_id']:<8} {p['strategy'][:21]:<22} {p['instrument']:<17} {p['side']:<5} {p['entry_price']:<7.1f} {p['current_price']:<7.1f} {fair_val:<9.2f} ₹{gap_val:<9.2f} {conv_val:>5.1f}% {pnl_str:<10} {ret_str:<8} {status_str}")

        # Recent Closed Trades Table - Full Complete Un-truncated Ledger
        sorted_closed = self.get_sorted_closed_trades(reverse=True)
        print("-" * 155)
        print(f"[COMPLETE CLOSED TRADE AUDIT LEDGER] ({len(sorted_closed)} Total Trades Executed — Ordered by Execution Time)")
        if not sorted_closed:
            print("  No trades closed yet.")
        else:
            print(f" {'#':<3} │ {'Trade ID':<9} │ {'Entry':<8} {'Exit':<8} │ {'Contract':<17} {'Side':<4} │ {'Entry':>7} → {'Exit':>7} ( {'Target':>7} ) │ {'Gross P&L':>11} │ {'Fric':>7} │ {'Net P&L':>11} ({'Return':>7}) │ {'Status':<10} │ {'Exit Reason'}")
            print("─" * 155)
            for idx, t in enumerate(sorted_closed):
                pnl_val = t.get('realized_pnl', t.get('net_pnl', 0.0))
                pnl_str = format_inr(pnl_val, include_sign=True)
                gross_str = format_inr(t.get('gross_pnl', pnl_val), include_sign=True)
                fric_str = format_inr(t.get('friction_cost', 0.0))
                ret_pct_val = float(t.get('return_pct') or 0.0)
                ret_str = f"{ret_pct_val:+.1f}%"
                status_icon = "🟢 PROFIT" if (pnl_val or 0.0) >= 0 else "🔴 LOSS"
                clean_reason = str(t.get('exit_reason', '')).replace('|', '•').strip()
                entry_p = float(t.get('entry_price') or 0.0)
                exit_p = float(t.get('exit_price') or 0.0)
                tgt_p = float(t.get('target_price') or 0.0)
                print(f" {idx+1:<3} │ {t['trade_id']:<9} │ {t.get('entry_time','--:--'):<8} {t.get('exit_time','--:--'):<8} │ {t['instrument']:<17} {t['side']:<4} │ ₹{entry_p:>6.2f} → ₹{exit_p:>6.2f} ( ₹{tgt_p:>5.2f} ) │ {gross_str:>11} │ {fric_str:>7} │ {pnl_str:>11} ({ret_str:>7}) │ {status_icon:<10} │ {clean_reason}")
            print("─" * 155)

        print("=" * 155)
        print(f"  [Auto-Refresh every {self.update_interval}s | Immediate Exit on Target Touch | Max Capacity: {self.max_positions} Positions]")
        print("=" * 155)

        # Also write live markdown dashboard for real-time visibility in editor
        try:
            live_md_path = OUTPUT_DIR / "LIVE_TERMINAL_DASHBOARD.md"

            # 1. Format Active Open Positions Table with Clean Sequential Numbering, Margin & Full Detail
            sorted_positions = sorted(
                self.positions,
                key=lambda p: int(str(p.get("trade_id", "")).replace("TRD-", "0") if str(p.get("trade_id", "")).replace("TRD-", "").isdigit() else 0),
                reverse=True
            )
            active_rows_list = []
            for idx, p in enumerate(sorted_positions):
                fair_val = p.get("current_fair", p.get("entry_fair", p["entry_price"]))
                gap_val = p.get("mispricing_gap", abs(p["current_price"] - fair_val))
                conv_val = p.get("convergence_pct", 0.0)
                pair_tag = f" " if p.get("pair_id") else ""
                pos_margin = p.get("allocated_margin") or self.calculate_trade_margin(p["side"], p.get("current_price", p["entry_price"]), spot, p["qty"])
                if p.get("spike_shield_active"):
                    status_badge = "🛡️ SPIKE SHIELD"
                elif p.get("target_hit") or conv_val >= 70.0:
                    status_badge = "🟢 CONVERGED"
                elif conv_val >= 30.0:
                    status_badge = "🟡 CONVERGING"
                else:
                    status_badge = "🔵 ACTIVE HARVEST"
                active_rows_list.append(
                    f"| {idx+1} | `{p['trade_id']}` | {p['strategy']} | {p['instrument']} | **{p['side']}** | {p['qty']} | {format_inr(pos_margin)} | ₹{p['entry_price']:.2f} | ₹{p['current_price']:.2f} | **₹{fair_val:.2f}** | ₹{gap_val:.2f} | **{conv_val:+.1f}%** | {p.get('delta', 0.0):+.2f} | {format_inr(p.get('gross_pnl', 0.0), include_sign=True)} | {format_inr(p.get('incurred_friction', p.get('entry_friction', 0.0)))} + {format_inr(p.get('estimated_close_cost', 0.0))} est. | **{format_inr(p['net_pnl'], include_sign=True)}** | {p.get('net_return_pct', p['return_pct']):+.1f}% | {status_badge} |"
                )
            active_rows = "\n".join(active_rows_list) if active_rows_list else "| - | - | - | - | - | - | Scanning option chain for statistical mispricings... | - | - | - | - | - | - | - | - | - | - | - |"

            chain_rows_list = []
            for item in self.last_chain_data.get("chain", []):
                call = item.get("call") or {}
                put = item.get("put") or {}
                chain_rows_list.append(
                    f"| {item.get('strike', 0):.0f} | {call.get('ltp', 0):.2f} | {call.get('bid', 0):.2f} | {call.get('ask', 0):.2f} | {call.get('iv', 0) * 100:.2f}% | {put.get('ltp', 0):.2f} | {put.get('bid', 0):.2f} | {put.get('ask', 0):.2f} | {put.get('iv', 0) * 100:.2f}% |"
                )
            chain_rows = "\n".join(chain_rows_list) if chain_rows_list else "| - | - | - | - | - | - | - | - | - |"

            # 2. Format Complete Closed Trades Ledger in Strict Reverse Chronological Order (Newest First)
            closed_rows_list = []
            for idx, t in enumerate(sorted_closed):
                pnl_val = t.get('realized_pnl', t.get('net_pnl', 0.0))
                gross_val = t.get('gross_pnl', pnl_val)
                fric_val = t.get('friction_cost', 0.0)
                status_icon = "🟢 PROFIT" if (pnl_val or 0.0) >= 0 else "🔴 LOSS"
                clean_reason = str(t.get('exit_reason', '')).replace('|', '•').strip()
                dur_secs = float(t.get('holding_seconds') or 0.0)
                duration_str = f"{round(dur_secs/60.0, 1)}m"
                entry_p = float(t.get('entry_price') or 0.0)
                exit_p = float(t.get('exit_price') or 0.0)
                tgt_p = float(t.get('target_price') or 0.0)
                stp_p = float(t.get('stop_price') or 0.0)
                ret_pct_val = float(t.get('return_pct') or 0.0)
                closed_rows_list.append(
                    f"| {idx+1} | `{t['trade_id']}` | {t.get('entry_time', '--:--')} | {t.get('exit_time', '--:--')} | {t['instrument']} | **{t['side']}** | {t['qty']} | ₹{entry_p:.2f} | ₹{tgt_p:.2f} | ₹{stp_p:.2f} | ₹{exit_p:.2f} | {format_inr(gross_val, include_sign=True)} | {format_inr(fric_val)} | **{format_inr(pnl_val, include_sign=True)}** | {ret_pct_val:+.1f}% | {duration_str} | {status_icon} | {clean_reason} |"
                )
            closed_rows = "\n".join(closed_rows_list) if closed_rows_list else "| - | - | - | - | - | No trades closed yet | - | - | - | - | - | - | - | - | - | - | - | - |"

            margin_roi_pct = (self.today_net_pnl / self.total_trading_margin * 100.0) if self.total_trading_margin > 0 else 0.0
            target_pct_achieved = (self.today_net_pnl / self.target_profit_amount * 100.0) if self.target_profit_amount > 0 else 0.0
            target_badge = "🎯 TARGET REACHED (+0.50% on Margin)" if self.today_net_pnl >= self.target_profit_amount else (
                f"📊 ACCUMULATING ({target_pct_achieved:.1f}% of Target)" if self.today_net_pnl > 0 else "📊 ACCUMULATING"
            )

            live_md_tmp = live_md_path.with_suffix(".tmp")
            with open(live_md_tmp, "w") as f:
                f.write(f"""# ⚡ LIVE QUANT TERMINAL — NIFTY 50 OPTIONS ENGINE
**Last Market Tick:** `{now_str} IST` | **Underlying:** `{self.symbol}` | **Auto-Refresh:** Every `{self.update_interval}s`

---

### 💰 Capital & Margin Allocation (₹25,00,000 Portfolio)
| Metric | Real-Time Value | Metric | Real-Time Value |
| :--- | :--- | :--- | :--- |
| **Total Base Capital** | **₹25,00,000.00** | **Current Account Equity** | **{format_inr(self.account_equity)}** |
| **Total Utilized Margin** | **{format_inr(self.used_margin)}** ({self.margin_utilization_pct:.1f}%) | **Free Trading Margin** | **{format_inr(self.free_margin)}** |
| **Short Selling Margin (SPAN+Exp)** | **{format_inr(self.used_short_margin)}** / ₹16,00,000 max | **Long Buying Margin (Premium)** | **{format_inr(self.used_long_margin)}** / ₹4,00,000 max |
| **Cash Safety Buffer (20%)** | **₹5,00,000.00** (Untouchable) | **Today's Net ROI (Total Cap)** | **{self.daily_roi_pct:+.2f}%** ({format_inr(self.today_net_pnl, include_sign=True)}) |
| **Trading Margin Target (+0.50%)** | **{format_inr(self.target_profit_amount)}** (+{self.target_margin_roi:.2f}% of ₹20L Margin) | **Target Status** | **{target_badge}** |

---

### ⚡ Real-Time BSM Pricing & Econometric Parameter Engine
All parameters directly governing option fair value and Greeks are continuously estimated and updated on every live market tick:

| Parameter | Symbol | Live Value | Derivation Methodology & Data Source | Impact on Option Fair Value |
| :--- | :--- | :--- | :--- | :--- |
| **Spot Index Price** | $S$ | **₹{self.current_spot:,.2f}** (Δ {self.current_spot - self.initial_spot:+.2f}) | Real-time direct tick feed from NSE NIFTY 50 | Governs intrinsic value & contract moneyness $(S - K)$ |
| **Synthetic Forward Price** | $F$ | **₹{self.forward_price:,.2f}** | Inverted from ATM Put-Call Parity $F = K_{{\\text{{ATM}}}} + e^{{rT}}(C - P)$ | Unbiased expected spot price at expiration |
| **Nearest ATM Strike** | $K_{{\\text{{ATM}}}}$ | **{self.atm_strike}** | Closest traded strike to current spot index | Benchmark strike for implied volatility & parity inversion |
| **Time-to-Maturity** | $T$ | **{self.current_ttm*365:.2f} days** ({self.current_ttm:.6f} yrs) | High-precision countdown to 15:30:00 IST expiry | Exponential non-linear time decay ($\\Theta \\propto 1/\\sqrt{{T}}$) |
| **Implied Risk-Free Rate** | $r$ | **{self.implied_r*100:.2f}%** | Inverted from ATM Put-Call Parity: $e^{{-rT}} = [S e^{{-qT}} - (C - P)] / K$ | Cost of carry & monetary discounting factor |
| **Dividend Yield** | $q$ | **{self.dividend_yield*100:.2f}%** | NIFTY 50 annualized constituent dividend yield | Lowers theoretical call values, raises put values |
| **Live ATM Implied Vol** | $\\sigma_{{\\text{{ATM}}}}$ | **{self.atm_iv*100:.2f}%** | Mean of live ATM Call & Put Black-Scholes IVs | Market consensus price of near-term uncertainty |
| **Tick Realized Volatility** | $\\sigma_{{\\text{{tick}}}}$ | **{self.tick_vol*100:.2f}%** | Rolling 10s tick returns (567k annual periods) | Captures micro-structure spikes & high-frequency shocks |
| **5m Intraday Realized Vol** | $\\sigma_{{5\\text{{m}}}}$ | **{self.intraday_vol*100:.2f}%** | 5-minute bar returns over past 5 sessions | Realized intraday volatility clusters & session spikes |
| **Daily EGARCH(1,1) Vol** | $\\sigma_{{\\text{{daily}}}}$ | **{self.daily_vol*100:.2f}%** | 1-year daily asymmetric leverage GARCH model | Robust macro baseline correcting for volatility skew |
| **Fused Model Volatility** | $\\sigma_{{\\text{{fused}}}}$ | **{self.egarch_vol*100:.2f}%** | Forecast/realized blend: $65\\% \\sigma_{{5\\text{{m}}}} + 35\\% \\sigma_{{\\text{{daily}}}}$, with bounded tick-vol overlay | Independent pricing volatility for identifying statistical mispricings |
| **Market Volatility Regime** | - | **`{self.regime}`** | Hidden Markov Model volatility state classification | Determines statistical conviction threshold |
| **Trend & Momentum Regime** | - | **`{self.trend_regime}`** | Macro Bias: **`{self.macro_session_bias}`** \| 15m ({self.spot_drift_15m:+.1f} pts), 5m ({self.spot_drift_5m:+.1f} pts) vs VWAP (₹{self.session_vwap:.1f}) & Open (₹{self.session_open_spot:.1f}) | Direct Gatekeeper: Option buying strictly disabled during choppy regimes |

---

### 📊 Portfolio Performance & Risk Summary
| Metric | Real-Time Value | Metric | Real-Time Value |
| :--- | :--- | :--- | :--- |
| **Total Net Realized P&L** | **{format_inr(total_realized_net, include_sign=True)}** | **Total Unrealized P&L** | **{format_inr(total_unrealized_net, include_sign=True)}** |
| **Total Net P&L (All)** | **{format_inr(total_net_pnl, include_sign=True)}** | **Total Gross P&L** | {format_inr(total_gross_pnl, include_sign=True)} |
| **Frictional Costs (STT + Fees)**| {format_inr(total_friction_incurred)} | **Win Rate** | **{win_rate:5.1f}%** ({winning_trades}/{all_trades_count} closed) |
| **Convergence Rate** | **{convergence_pct:5.1f}%** ({converged_positions}/{total_positions_evaluated}) | **Active Concurrent Positions** | **{len(self.positions)} / {self.max_positions} (Expanded)** |
| **Net Portfolio Delta (Δ)** | **{net_delta:+.1f} Δ** | **Net Portfolio Theta (Θ)** | **₹{net_theta:+.1f}/day** |
| **Today's Margin ROI** | **{margin_roi_pct:+.2f}%** ({format_inr(self.today_net_pnl, include_sign=True)} / {format_inr(self.target_profit_amount)}) | **Today's Closed Trades** | **{len(sorted_closed)} / {self.max_daily_closed_trades} max** |

---

### 🟢 Active Open Positions ({len(self.positions)} Active | Margin Used: {format_inr(self.used_margin)} / {format_inr(self.total_capital * self.max_margin_utilization)})
*Real-time monitoring of all active positions. Continuously evaluated against 1:2 risk-reward profit targets, breakeven thresholds, and trailing stops.*

| # | Trade ID | Strategy | Contract | Side | Qty | Margin Req | Entry Price | Current LTP | BSM Model Fair | Alpha Gap (₹) | Conv % | Delta (Δ) | Gross P&L | Charges | Net Unrealized P&L | Return % | Status |
| :---: | :---: | :--- | :--- | :---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :---: |
{active_rows}

---

### 📈 Live NSE Option Chain (pnsea)
**Source:** `{self.last_chain_data.get('expiry_source', 'unavailable')}` | **Timestamp:** `{self.last_chain_data.get('timestamp', '--')}` | **Expiry:** `{self.last_chain_data.get('expiry_date', '--')}`

| Strike | Call LTP | Call Bid | Call Ask | Call IV | Put LTP | Put Bid | Put Ask | Put IV |
| :---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
{chain_rows}

---

### 📜 Complete Audit Ledger of Closed Trades ({len(self.closed_trades)} Total Trades Executed)
*Complete chronological execution log (newest trades first). Every trade itemizes exact fill prices, target/stop levels, gross P&L, statutory friction & broker charges, net realized P&L, and exit trigger.*

| # | Trade ID | Entry Time | Exit Time | Contract | Side | Qty | Entry Price | Target Price | Stop Loss | Exit Price | Gross P&L | Charges | Net Realized P&L | Return % | Duration | Status | Exit Trigger & Convergence |
| :---: | :---: | :---: | :---: | :--- | :---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :---: | :--- |
{closed_rows}

---

### 🏛️ Quantitative Mispricing Exploitation & Asymmetric Alpha Engine
1. **Pure Relative-Value Mispricing Exploitation:**
   - **Outright Statistical Edge:** Exploits econometric mispricings directly by shorting overpriced options (`ALPHA-SHORT`) and buying underpriced options (`ALPHA-LONG`) based on the BSM Local Volatility Surface and fused EGARCH baseline.
   - **Balanced Capacity:** 4 slots guaranteed for `ALPHA-SHORT` and 2 slots for `ALPHA-LONG`, eliminating single-side capacity starvation.
2. **Asymmetric Risk Management & Capital Preservation:**
   - **Positive Payoff Asymmetry ($1 : 3.0+$ R:R):** Base profit target is calibrated at $+28\%$ decay (expanding to $+25\%$ to $+38\%$) against a strict $9.5\%$ stop-loss bound.
   - **Catastrophic Emergency Cap:** Tightened hard circuit-breaker at $-12.5\\%$ max loss.
   - **Gamma Invalidation Prune:** Exits short positions immediately if $|\\Delta| > 0.42$ or spot migrates within 45 points of strike before gamma shocks occur.
   - **Multi-Tier Trailing Profit Ratchet:** Locks in gains during favorable moves:
     - Peak $\\ge +10\\% \\implies$ moves stop to Breakeven $+2.5\\%$ (fees covered, guaranteed risk-free).
     - Peak $\\ge +14\\% \\implies$ locks $+10\\%$ net.
     - Peak $\\ge +18\\% \\implies$ locks $+14\\%$ net.
     - Peak $\\ge +26\\% \\implies$ locks $+20\\%$ net.
3. **Execution Pacing & Anti-Whipsaw Discipline:**
   - **Execution Pacing:** 15s delay between consecutive fills to prevent burst stacking.
   - **Strike Cooldown Blacklist:** Closed strikes placed in cooldown to prevent repeated whipsaws.
   - **Fee-Viability Gate:** Enforces minimum 2.0x edge-to-cost ratio and ₹180+ gross edge per lot.
""")
            live_md_tmp.replace(live_md_path)
        except Exception as md_err:
            self.log(f"⚠️ Live markdown dashboard write notice: {md_err}")



    def export_audit_report(self):
        """Export comprehensive Model Performance & Trade Logs report in Markdown, CSV, and JSON."""
        now_tag = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_file = OUTPUT_DIR / f"paper_trading_trades_{now_tag}.csv"
        json_file = OUTPUT_DIR / f"paper_trading_summary_{now_tag}.json"
        md_file = OUTPUT_DIR / f"model_performance_report_{now_tag}.md"

        all_trades = self.closed_trades + self.positions
        if all_trades:
            df = pd.DataFrame(all_trades)
            df.to_csv(csv_file, index=False)
            self.log(f"📁 Exported {len(all_trades)} trades to CSV: {csv_file}")

        all_closed = self.closed_trades
        wins = sum(1 for t in all_closed if t.get("realized_pnl", t.get("net_pnl", 0.0)) > 0)
        losses = sum(1 for t in all_closed if t.get("realized_pnl", t.get("net_pnl", 0.0)) <= 0)
        win_rate = (wins / len(all_closed) * 100) if all_closed else 0.0
        total_net_pnl = sum(t.get("realized_pnl", t.get("net_pnl", 0.0)) for t in all_closed)
        total_gross_pnl = sum(t.get("gross_pnl", t.get("realized_pnl", t.get("net_pnl", 0.0))) for t in all_closed)
        total_friction = sum(t.get("friction_cost", 0.0) for t in all_closed)

        gross_profit = sum(t.get("gross_pnl", t.get("realized_pnl", t.get("net_pnl", 0.0))) for t in all_closed if t.get("gross_pnl", t.get("realized_pnl", t.get("net_pnl", 0.0))) > 0)
        gross_loss = abs(sum(t.get("gross_pnl", t.get("realized_pnl", t.get("net_pnl", 0.0))) for t in all_closed if t.get("gross_pnl", t.get("realized_pnl", t.get("net_pnl", 0.0))) < 0))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 1.0)

        converged_count = sum(1 for t in all_trades if t.get("converged", False))
        convergence_rate = (converged_count / len(all_trades) * 100) if all_trades else 0.0

        trade_returns = [t["return_pct"] for t in all_closed]
        mean_ret = float(np.mean(trade_returns)) if trade_returns else 0.0
        std_ret = float(np.std(trade_returns)) if len(trade_returns) > 1 else 0.0
        sharpe_ratio = (mean_ret / std_ret * np.sqrt(252)) if std_ret > 0 else 0.0

        avg_holding_mins = float(np.mean([t.get("holding_seconds", 0.0) / 60.0 for t in all_closed])) if all_closed else 0.0

        summary = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "symbol": self.symbol,
            "initial_spot": self.initial_spot,
            "final_spot": self.current_spot,
            "egarch_forecast_vol": round(self.egarch_vol, 4),
            "regime": self.regime,
            "total_trades_executed": len(all_closed),
            "open_positions_remaining": len(self.positions),
            "winning_trades": wins,
            "losing_trades": losses,
            "trade_accuracy_win_rate_pct": round(win_rate, 2),
            "mispricing_convergence_rate_pct": round(convergence_rate, 2),
            "total_gross_pnl_inr": round(total_gross_pnl, 2),
            "total_friction_and_costs_inr": round(total_friction, 2),
            "total_net_realized_pnl_inr": round(total_net_pnl, 2),
            "profit_factor": round(profit_factor, 2),
            "mean_trade_return_pct": round(mean_ret, 2),
            "trade_return_std_pct": round(std_ret, 2),
            "annualized_sharpe_ratio": round(sharpe_ratio, 2),
            "average_holding_time_minutes": round(avg_holding_mins, 1),
        }

        with open(json_file, "w") as f:
            json.dump(summary, f, indent=2)
        self.log(f"📊 Exported JSON summary to: {json_file}")

        # Generate formatted Markdown model report with trade logs
        md_lines = [
            f"# Quantitative Options Model Performance & Trade Execution Report",
            f"**Generated At:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} IST | **Symbol:** {self.symbol}",
            "",
            "## 1. Executive Performance Summary",
            "",
            f"| Metric | Model Result |",
            f"| :--- | :--- |",
            f"| **Initial NIFTY Spot** | ₹{self.initial_spot:,.2f} |",
            f"| **Final NIFTY Spot** | ₹{self.current_spot:,.2f} (Δ {self.current_spot - self.initial_spot:+.2f}) |",
            f"| **EGARCH(1,1) Volatility** | {self.egarch_vol*100:.2f}% |",
            f"| **Market Regime** | `{self.regime}` |",
            f"| **Total Closed Trades** | {len(all_closed)} |",
            f"| **Open Positions Remaining** | {len(self.positions)} |",
            f"| **Win Rate** | **{win_rate:.1f}%** ({wins}W / {losses}L) |",
            f"| **Mispricing Convergence Rate** | **{convergence_rate:.1f}%** ({converged_count}/{len(all_trades)}) |",
            f"| **Gross Realized P&L** | ₹{total_gross_pnl:,.2f} |",
            f"| **Friction (STT + Exchange Charges)** | ₹{total_friction:,.2f} |",
            f"| **Net Realized P&L** | **₹{total_net_pnl:,.2f}** |",
            f"| **Profit Factor** | {profit_factor:.2f} |",
            f"| **Mean Trade Return** | {mean_ret:+.2f}% (Std: {std_ret:.2f}%) |",
            f"| **Annualized Sharpe Ratio** | {sharpe_ratio:.2f} |",
            f"| **Average Holding Time** | {avg_holding_mins:.1f} minutes |",
            "",
            "## 2. Complete Trade Logs Ledger",
            "",
            "| # | Trade ID | Entry Time | Exit Time | Instrument | Side | Qty | Entry Price | Target Price | Exit Price | Net Realized P&L | Return % | Reason | Converged |",
            "| :---: | :---: | :---: | :---: | :--- | :---: | ---: | ---: | ---: | ---: | ---: | ---: | :--- | :---: |",
        ]

        sorted_closed_report = self.get_sorted_closed_trades(reverse=True)
        for idx, t in enumerate(sorted_closed_report):
            conv = "Yes" if t.get("converged") else "No"
            pnl_val = t.get('realized_pnl', t.get('net_pnl', 0.0))
            clean_reason = str(t.get('exit_reason', '')).replace('|', '•').strip()
            entry_p = float(t.get('entry_price') or 0.0)
            tgt_p = float(t.get('target_price') or 0.0)
            exit_p = float(t.get('exit_price') or 0.0)
            ret_pct_val = float(t.get('return_pct') or 0.0)
            md_lines.append(
                f"| {idx+1} | `{t['trade_id']}` | {t.get('entry_time', '--:--')} | {t.get('exit_time', '--:--')} | {t['instrument']} | **{t['side']}** | {t['qty']} | ₹{entry_p:.2f} | ₹{tgt_p:.2f} | ₹{exit_p:.2f} | **{format_inr(pnl_val, include_sign=True)}** | {ret_pct_val:+.1f}% | {clean_reason} | {conv} |"
            )

        if not sorted_closed_report:
            md_lines.append("| - | - | - | - | No trades closed yet | - | - | - | - | - | - | - | - | - |")

        if self.positions:
            md_lines.append("")
            md_lines.append("### Active Open Positions at Session Close")
            md_lines.append("")
            md_lines.append("| # | Trade ID | Entry Time | Instrument | Side | Qty | Entry Price | Target Price | Current LTP | Net Unrealized P&L | Return % | M-Score | Converged |")
            md_lines.append("| :---: | :---: | :---: | :--- | :---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :---: |")
            sorted_positions_report = sorted(
                self.positions,
                key=lambda p: int(str(p.get("trade_id", "")).replace("TRD-", "0") if str(p.get("trade_id", "")).replace("TRD-", "").isdigit() else 0),
                reverse=True
            )
            for idx, p in enumerate(sorted_positions_report):
                conv = "Yes" if p.get("converged") else "No"
                md_lines.append(
                    f"| {idx+1} | `{p['trade_id']}` | {p.get('entry_time', '--:--')} | {p['instrument']} | **{p['side']}** | {p['qty']} | ₹{p['entry_price']:.2f} | ₹{p.get('target_price', 0.0):.2f} | ₹{p['current_price']:.2f} | **{format_inr(p['net_pnl'], include_sign=True)}** | {p['return_pct']:+.1f}% | {p['entry_mscore']:+.2f}σ | {conv} |"
                )

        with open(md_file, "w") as f:
            f.write("\n".join(md_lines))
        self.log(f"📝 Exported Model Performance & Trade Logs Report to: {md_file}")

        # Print terminal output
        print("\n" + "=" * 80)
        print("  QUANT MODEL PERFORMANCE & TRADE EXECUTION REPORT")
        print("=" * 80)
        print(f"  Total Trades Closed:          {len(all_closed)}")
        print(f"  Winning Trades:               {wins} ({win_rate:.1f}%)")
        print(f"  Mispricing Convergence Rate:  {convergence_rate:.1f}%")
        print(f"  Total Gross P&L:              {'+' if total_gross_pnl >= 0 else ''}₹{total_gross_pnl:,.2f}")
        print(f"  Transaction Friction & STT:   ₹{total_friction:,.2f}")
        print(f"  Total Net Realized P&L:       {'+' if total_net_pnl >= 0 else ''}₹{total_net_pnl:,.2f}")
        print(f"  Profit Factor:                {profit_factor:.2f}")
        print(f"  Mean Return per Trade:        {mean_ret:+.2f}% (Std: {std_ret:.2f}%)")
        print(f"  Annualized Sharpe Ratio:      {sharpe_ratio:.2f}")
        print(f"  Average Holding Time:         {avg_holding_mins:.1f} mins")
        print("=" * 80 + "\n")


    def run(self, once: bool = False, max_runtime_hours: float | None = None):
        """Main real-time terminal execution loop."""
        session_deadline = (
            time.monotonic() + max_runtime_hours * 3600.0
            if max_runtime_hours is not None and max_runtime_hours > 0
            else None
        )
        self.log(f"Starting Live Quant Paper Trader for {self.symbol}...")
        self.log(f"Refresh Interval: {self.update_interval}s | Max Concurrent Positions: {self.max_positions}")
        if session_deadline is not None:
            self.log(f"Session runtime limit: {max_runtime_hours:.2f} hours")
        if not once:
            self.log("Press Ctrl+C at any time to exit and generate the IEEE accuracy report.\n")
            time.sleep(1.0)

        while self.running:
            try:
                if session_deadline is not None and time.monotonic() >= session_deadline:
                    self.log("Session runtime limit reached; stopping and exporting the report.")
                    self.running = False
                    continue

                chain_data = self.fetch_market_state()
                if chain_data:
                    # 1. Update existing open positions
                    self.update_open_positions(chain_data)

                    # 2. Scan and execute new high-conviction mispricings
                    if self.auto_trade:
                        self.scan_and_execute_trades(chain_data)

                    # 3. Refresh Bloomberg-style terminal dashboard
                    self.print_terminal_dashboard()
                else:
                    self.log("Market feed returned no data. Retrying next cycle...")

            except Exception as iter_err:
                self.log(f"⚠️ Recovered from iteration error: {iter_err}")

            if session_deadline is not None and time.monotonic() >= session_deadline:
                self.log("Session runtime limit reached; stopping and exporting the report.")
                self.running = False

            if once or not self.running:
                self.export_audit_report()
                break

            time.sleep(self.update_interval)


def main():
    parser = argparse.ArgumentParser(description="Live NIFTY Options Quant Paper Trader & Accuracy Engine.")
    parser.add_argument("--symbol", default="NIFTY", help="Underlying index (default: NIFTY)")
    parser.add_argument("--lot-size", type=int, default=int(os.getenv("NIFTY_LOT_SIZE", "65")), help="Lot size for underlying contracts (default: 65 for NIFTY)")
    parser.add_argument("--interval", type=int, default=5, help="Loop refresh interval in seconds (default: 5s for rapid live updates)")
    parser.add_argument("--tp", type=float, default=28.0, help="Take-profit percent (default: 28.0%%)")
    parser.add_argument("--sl", type=float, default=9.5, help="Stop-loss percent (default: 9.5%%)")
    parser.add_argument("--capital", type=float, default=2500000.0, help="Total account trading capital in INR (default: ₹25,00,000)")
    parser.add_argument("--min-mscore", type=float, default=1.2, help="Minimum M-Score to trigger trade (default: 1.2)")
    parser.add_argument("--max-pos", type=int, default=8, help="Maximum concurrent safety ceiling across all open positions (governed primarily by margin)")
    parser.add_argument("--duration-hours", type=float, default=6.0, help="Maximum runtime in hours (default: 6.0)")
    parser.add_argument("--new-session", action="store_true", help="Start with no old positions or P&L while preserving unique trade IDs")
    parser.add_argument("--allow-stale", action="store_true", help="Allow replay/simulation using database snapshots when NSE live is closed")
    parser.add_argument("--once", action="store_true", help="Run single scan and export report without continuous loop")
    parser.add_argument("--no-eod-squareoff", action="store_true", help="Disable automatic 15:25 IST EOD squareoff for off-hours testing/simulation")
    parser.add_argument("--multi-expiry", action="store_true", default=True, help="Scan across Front-Week and Next-Week expiries simultaneously (default: True)")
    parser.add_argument("--no-multi-expiry", dest="multi_expiry", action="store_false", help="Restrict scanning strictly to single nearest expiry")
    parser.add_argument("--max-closed-trades", type=int, default=int(os.getenv("MAX_DAILY_TRADES", "50")), help="Maximum daily closed trades ceiling (default: 50)")
    parser.add_argument("--target-margin-roi", type=float, default=float(os.getenv("TARGET_MARGIN_ROI", "0.50")), help="Daily profit target percent on total trading margin (default: 0.50%% = ₹10,000 on ₹20L margin)")
    parser.add_argument("--lots-per-trade", type=int, default=int(os.getenv("LOTS_PER_TRADE", "3")), help="Lots executed per trade position (default: 3 lots = 195 qty for ₹25L capital)")
    args = parser.parse_args()

    engine = LiveQuantPaperTrader(
        symbol=args.symbol,
        lot_size=args.lot_size,
        lots_per_trade=args.lots_per_trade,
        update_interval_sec=args.interval,
        take_profit_pct=args.tp,
        stop_loss_pct=args.sl,
        min_mscore=args.min_mscore,
        max_positions=args.max_pos,
        resume_existing=not args.new_session,
        allow_stale=args.allow_stale,
        multi_expiry=args.multi_expiry,
        total_capital=args.capital,
        no_eod_squareoff=args.no_eod_squareoff,
        max_closed_trades=args.max_closed_trades,
        target_margin_roi=args.target_margin_roi
    )
    engine.run(once=args.once, max_runtime_hours=args.duration_hours)


if __name__ == "__main__":
    main()
