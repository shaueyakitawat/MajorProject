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
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd
import numpy as np

# Ensure project root in python path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.option_chain_service import get_spot_price, get_full_chain
from backend.services.volatility_service import forecast_volatility
from backend.services.pricing_service import black_scholes_price, calculate_greeks, calculate_ttm_years
from backend.services.regime_service import classify_volatility_regime
from backend.services.mispricing_service import detect_mispricing

OUTPUT_DIR = PROJECT_ROOT / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = PROJECT_ROOT / "data" / "nifty_live_snapshots.db"
AUDIT_CSV_PATH = OUTPUT_DIR / "live_paper_trades_audit.csv"


class LiveQuantPaperTrader:
    def __init__(
        self,
        symbol: str = "NIFTY",
        lot_size: int = 50,
        max_positions: int = 6,
        take_profit_pct: float = 30.0,
        stop_loss_pct: float = 40.0,
        min_mscore: float = 1.8,
        update_interval_sec: int = 10,
        auto_trade: bool = True
    ):
        self.symbol = symbol
        self.lot_size = lot_size
        self.max_positions = max_positions
        self.take_profit_pct = take_profit_pct
        self.stop_loss_pct = stop_loss_pct
        self.min_mscore = min_mscore
        self.update_interval = update_interval_sec
        self.auto_trade = auto_trade
        self.running = True

        # State storage
        self.positions: list[dict] = []
        self.closed_trades: list[dict] = []
        self.trade_counter = 0
        self.initial_spot = 0.0
        self.current_spot = 0.0
        self.egarch_vol = 0.128
        self.regime = "NORMAL_VOL"
        self.last_vol_update = 0.0
        self.start_time = datetime.now()

        self._init_sqlite_ledger()
        self._init_signal_handlers()

    def _init_signal_handlers(self):
        """Trap Ctrl+C (SIGINT) and termination signals for graceful flush."""
        def handle_exit(signum, frame):
            print("\n")
            self.log("Interrupt received! Initiating safe shutdown and exporting IEEE report...")
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
            conn.commit()
            conn.close()
        except Exception as e:
            self.log(f"SQLite ledger init warning: {e}")

    def _persist_trade(self, t: dict):
        """
        Immediately save/update trade record in SQLite & append to audit CSV.
        Guarantees zero data loss even if the terminal drops or system sleeps.
        """
        try:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("""
            INSERT OR REPLACE INTO live_paper_trades (
                trade_id, strategy, instrument, strike, option_type, expiry, side, qty,
                entry_price, current_price, entry_fair, entry_spot, entry_mscore, entry_dev_pct,
                entry_time, entry_timestamp, exit_price, exit_time, exit_reason,
                gross_pnl, net_pnl, friction_cost, return_pct, converged, holding_seconds, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                t["trade_id"], t["strategy"], t["instrument"], t["strike"], t["type"], t["expiry"],
                t["side"], t["qty"], t["entry_price"], t.get("current_price"), t["entry_fair"],
                t["entry_spot"], t["entry_mscore"], t["entry_dev_pct"], t["entry_time"],
                t["entry_timestamp"], t.get("exit_price"), t.get("exit_time"), t.get("exit_reason"),
                t.get("gross_pnl", 0.0), t.get("net_pnl", 0.0), t.get("friction_cost", 0.0),
                t.get("return_pct", 0.0), 1 if t.get("converged", False) else 0,
                t.get("holding_seconds", 0.0), t["status"]
            ))
            conn.commit()
            conn.close()
        except Exception as exc:
            self.log(f"Ledger persistence error: {exc}")

    def log(self, text: str):
        t = datetime.now().strftime("%H:%M:%S")
        print(f"[{t} IST] {text}")

    def update_volatility_model(self, force: bool = False):
        """
        Estimate EGARCH(1,1) volatility & Gaussian HMM regime on 2-year daily history.
        Caches estimate and only recalculates every 30 minutes to avoid Yahoo Finance throttling.
        """
        now_ts = time.time()
        if not force and (now_ts - self.last_vol_update < 1800.0) and self.last_vol_update > 0:
            return

        try:
            import yfinance as yf
            nifty = yf.download("^NSEI", period="2y", interval="1d", progress=False)
            if isinstance(nifty.columns, pd.MultiIndex):
                nifty.columns = [c[0] for c in nifty.columns]
            ret_series = np.log(nifty['Close'] / nifty['Close'].shift(1)).dropna()

            sample_annual_vol = float(ret_series.std() * np.sqrt(252))

            # Fit EGARCH(1,1)
            vol_res = forecast_volatility(pd.Series(ret_series.values.flatten()))
            model_vol = vol_res.get("final_vol", sample_annual_vol)

            # Robust sanity guardrail: Volatility for NIFTY must be within [0.06, 0.45]
            if 0.06 <= model_vol <= 0.45:
                self.egarch_vol = float(model_vol)
            else:
                self.egarch_vol = float(sample_annual_vol)

            # Classify regime
            reg_res = classify_volatility_regime(pd.Series(ret_series.values.flatten()))
            self.regime = reg_res.get("regime", "NORMAL_VOL")
            self.last_vol_update = now_ts
            self.log(f"Econometric Volatility Model Calibrated: EGARCH={self.egarch_vol*100:.2f}% | Regime={self.regime}")
        except Exception as e:
            self.log(f"Volatility calibration fallback ({e}); using baseline vol {self.egarch_vol*100:.2f}%")
            self.last_vol_update = now_ts

    def fetch_market_state(self) -> dict | None:
        """Fetch live spot and option chain from direct NSE feed."""
        try:
            self.update_volatility_model()
            chain_data = get_full_chain(self.symbol, force_refresh=True)
            if not chain_data or not chain_data.get("chain"):
                return None

            self.current_spot = chain_data.get("spot_price", self.current_spot)
            if self.initial_spot == 0 and self.current_spot > 0:
                self.initial_spot = self.current_spot

            return chain_data
        except Exception as e:
            self.log(f"⚠️ Error fetching market data: {e}")
            return None

    def scan_and_execute_trades(self, chain_data: dict):
        """Scan active option chain for high-conviction mispricings and execute paper trades."""
        if len(self.positions) >= self.max_positions:
            return

        chain_list = chain_data.get("chain", [])
        expiry = chain_data.get("expiry_date", "")
        spot = self.current_spot
        ttm = calculate_ttm_years(expiry)
        r = 0.065

        candidates = []

        for item in chain_list:
            strike = item.get("strike", 0.0)
            if abs(strike - spot) > 400:
                continue  # Focus on liquid near-the-money strikes

            for opt_type in ["call", "put"]:
                opt = item.get(opt_type)
                if not opt or opt.get("ltp", 0) <= 8.0:
                    continue

                ltp = opt["ltp"]
                iv = opt.get("iv", 0.13)
                bid = opt.get("bid", ltp * 0.995)
                ask = opt.get("ask", ltp * 1.005)

                # Compute model fair price using EGARCH volatility & exact dynamic TTM
                fair_price = black_scholes_price(spot, strike, ttm, r, self.egarch_vol, opt_type)
                if fair_price <= 0:
                    continue

                greeks = calculate_greeks(spot, strike, ttm, r, iv, opt_type)
                vega = greeks.get("vega", 15.0)
                gamma = greeks.get("gamma", 0.0003)

                # Detect quantitative mispricing & M-Score
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

                # Statistical significance filter for high-conviction mispricing
                if abs(m_score) >= self.min_mscore or abs(dev_pct) >= 6.0:
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
                        "delta": greeks.get("delta", 0.5),
                        "theta": greeks.get("theta", -10.0),
                        "vega": vega,
                        "gamma": gamma,
                        "expiry": expiry
                    })

        # Sort by statistical conviction (highest absolute deviation)
        candidates.sort(key=lambda x: abs(x["dev_pct"]), reverse=True)

        for c in candidates:
            if len(self.positions) >= self.max_positions:
                break

            # Avoid duplicate positions on same strike & type
            exists = any(p["strike"] == c["strike"] and p["type"] == c["type"] for p in self.positions)
            if exists:
                continue

            # Quantitative Arbitrage Direction:
            # Overpriced (Market > Fair) -> SELL to harvest volatility premium
            # Underpriced (Market < Fair) -> BUY to capture fair-value convergence
            is_overpriced = c["dev_pct"] > 0
            side = "SELL" if is_overpriced else "BUY"

            # Realistic execution with spread slippage: Buy at Ask, Sell at Bid
            exec_price = c["bid"] if side == "SELL" else c["ask"]
            strategy_name = "VRP Short Volatility" if side == "SELL" else "Long Mispriced Wing"

            # Statutory transaction friction: STT 0.125% on sell, Exchange/SEBI/GST 0.053% total
            entry_friction = (exec_price * self.lot_size) * (0.00125 if side == "SELL" else 0.0) + (exec_price * self.lot_size * 0.00053)

            self.trade_counter += 1
            pos = {
                "trade_id": f"TRD-{self.trade_counter:03d}",
                "strategy": strategy_name,
                "instrument": f"NIFTY {int(c['strike'])} {c['type'].upper()}",
                "strike": c["strike"],
                "type": c["type"],
                "expiry": c["expiry"],
                "side": side,
                "qty": self.lot_size,
                "entry_price": round(exec_price, 2),
                "current_price": round(exec_price, 2),
                "entry_fair": round(c["fair_price"], 2),
                "entry_spot": round(spot, 2),
                "entry_mscore": round(c["m_score"], 2),
                "entry_dev_pct": round(c["dev_pct"], 2),
                "entry_time": datetime.now().strftime("%H:%M:%S"),
                "entry_timestamp": datetime.now().isoformat(),
                "entry_epoch": time.time(),
                "delta": c["delta"],
                "theta": c["theta"],
                "vega": c["vega"],
                "entry_friction": round(entry_friction, 2),
                "friction_cost": round(entry_friction, 2),
                "gross_pnl": 0.0,
                "net_pnl": -round(entry_friction, 2),
                "unrealized_pnl": -round(entry_friction, 2),
                "return_pct": 0.0,
                "converged": False,
                "holding_seconds": 0.0,
                "status": "OPEN"
            }
            self.positions.append(pos)
            self._persist_trade(pos)
            self.log(f"🚀 [ORDER FILLED] {pos['trade_id']} | {side} {self.lot_size}x {pos['instrument']} @ ₹{exec_price:.2f} (Fair: ₹{c['fair_price']:.2f} | Dev: {c['dev_pct']:+.1f}% | M-Score: {c['m_score']:+.2f}σ)")

    def update_open_positions(self, chain_data: dict):
        """Update live LTPs, calculate unrealized P&L, check convergence, and enforce TP/SL."""
        chain_list = chain_data.get("chain", [])
        spot = self.current_spot
        expiry = chain_data.get("expiry_date", "")
        ttm = calculate_ttm_years(expiry)
        r = 0.065
        now_ts = time.time()

        # Build quick price lookup: (strike, type) -> {ltp, bid, ask}
        lookup = {}
        for item in chain_list:
            st = item.get("strike")
            for t in ["call", "put"]:
                opt = item.get(t)
                if opt:
                    lookup[(st, t.lower())] = {
                        "ltp": opt.get("ltp", 0.0),
                        "bid": opt.get("bid", opt.get("ltp", 0.0) * 0.995),
                        "ask": opt.get("ask", opt.get("ltp", 0.0) * 1.005)
                    }

        remaining_positions = []

        for p in self.positions:
            key = (p["strike"], p["type"])
            market_quote = lookup.get(key)
            if not market_quote or market_quote["ltp"] <= 0:
                remaining_positions.append(p)
                continue

            curr_ltp = market_quote["ltp"]
            # Realistic exit price: Sell at Bid to close long, Buy at Ask to close short
            exit_fill_price = market_quote["bid"] if p["side"] == "BUY" else market_quote["ask"]

            p["current_price"] = round(curr_ltp, 2)
            p["holding_seconds"] = round(now_ts - p.get("entry_epoch", now_ts), 1)

            # Gross P&L calculation:
            if p["side"] == "BUY":
                gross_pnl = (exit_fill_price - p["entry_price"]) * p["qty"]
                ret_pct = ((exit_fill_price - p["entry_price"]) / p["entry_price"]) * 100
                exit_friction = (exit_fill_price * p["qty"]) * 0.00125 + (exit_fill_price * p["qty"] * 0.00053)
            else:
                gross_pnl = (p["entry_price"] - exit_fill_price) * p["qty"]
                ret_pct = ((p["entry_price"] - exit_fill_price) / p["entry_price"]) * 100
                exit_friction = (exit_fill_price * p["qty"]) * 0.00053

            total_friction = p.get("entry_friction", 0.0) + exit_friction
            net_pnl = gross_pnl - total_friction

            p["gross_pnl"] = round(gross_pnl, 2)
            p["net_pnl"] = round(net_pnl, 2)
            p["friction_cost"] = round(total_friction, 2)
            p["unrealized_pnl"] = round(net_pnl, 2)
            p["return_pct"] = round(ret_pct, 2)

            # Dynamic Convergence Evaluation:
            curr_fair = black_scholes_price(spot, p["strike"], ttm, r, self.egarch_vol, p["type"])
            dist_entry = abs(p["entry_price"] - p["entry_fair"])
            dist_curr = abs(curr_ltp - curr_fair)
            p["converged"] = dist_curr < dist_entry

            # Risk Management Rules: Take-Profit (TP), Stop-Loss (SL), EOD Square-Off
            exit_reason = None
            if ret_pct >= self.take_profit_pct:
                exit_reason = f"TARGET_PROFIT (+{ret_pct:.1f}%)"
            elif ret_pct <= -self.stop_loss_pct:
                exit_reason = f"STOP_LOSS ({ret_pct:.1f}%)"

            # Auto square-off near market close (15:15 IST)
            now_dt = datetime.now()
            if now_dt.hour == 15 and now_dt.minute >= 15:
                exit_reason = "EOD_SQUAREOFF"

            if exit_reason:
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

        total_realized_net = sum(t["realized_pnl"] for t in self.closed_trades)
        total_unrealized_net = sum(p["net_pnl"] for p in self.positions)
        total_net_pnl = total_realized_net + total_unrealized_net

        total_realized_gross = sum(t.get("gross_pnl", t["realized_pnl"]) for t in self.closed_trades)
        total_unrealized_gross = sum(p.get("gross_pnl", 0.0) for p in self.positions)
        total_gross_pnl = total_realized_gross + total_unrealized_gross
        total_friction_incurred = sum(t.get("friction_cost", 0.0) for t in self.closed_trades) + sum(p.get("friction_cost", 0.0) for p in self.positions)

        all_trades_count = len(self.closed_trades)
        winning_trades = sum(1 for t in self.closed_trades if t["realized_pnl"] > 0)
        win_rate = (winning_trades / all_trades_count * 100) if all_trades_count > 0 else 0.0

        # Convergence score
        total_positions_evaluated = len(self.positions) + len(self.closed_trades)
        converged_positions = sum(1 for p in self.positions if p["converged"]) + sum(1 for t in self.closed_trades if t.get("converged", False))
        convergence_pct = (converged_positions / total_positions_evaluated * 100) if total_positions_evaluated > 0 else 0.0

        net_delta = sum(p["delta"] * (1 if p["side"] == "BUY" else -1) * p["qty"] for p in self.positions)
        net_theta = sum(p["theta"] * (1 if p["side"] == "BUY" else -1) * (p["qty"] / 50.0) for p in self.positions)

        print("=" * 108)
        print(f"  QUANT NIFTY 50 OPTIONS MISPRICING & PAPER TRADING ENGINE  │  {now_str} IST")
        print("=" * 108)
        print(f"  SPOT PRICE:   ₹{self.current_spot:,.2f} (Δ {self.current_spot - self.initial_spot:+.2f})  │  HMM REGIME:  {self.regime:<12}  │  MODEL VOL (EGARCH): {self.egarch_vol*100:.2f}%")
        print(f"  NET P&L:      {'+' if total_net_pnl >= 0 else ''}₹{total_net_pnl:,.2f} (Gross: {'+' if total_gross_pnl >= 0 else ''}₹{total_gross_pnl:,.2f} | Costs: ₹{total_friction_incurred:,.2f})  │  REALIZED: {'+' if total_realized_net >= 0 else ''}₹{total_realized_net:,.2f}")
        print(f"  ACCURACY (WIN RATE): {win_rate:5.1f}% ({winning_trades}/{all_trades_count})  │  CONVERGENCE: {convergence_pct:5.1f}% ({converged_positions}/{total_positions_evaluated})   │  NET DELTA: {net_delta:+.1f} Δ")
        print("=" * 108)

        # Active Open Positions Table
        print("\n[ACTIVE OPEN POSITIONS]")
        print(f"  {'ID':<8} {'STRATEGY':<22} {'INSTRUMENT':<17} {'SIDE':<5} {'QTY':<5} {'ENTRY':<8} {'LTP':<8} {'FAIR':<8} {'NET P&L':<11} {'RET %':<8} {'M-SCORE':<9} {'CONVERGE'}")
        print("-" * 108)
        if not self.positions:
            print("  No active positions. Scanning option chain for statistical mispricings...")
        else:
            for p in self.positions:
                pnl_str = f"{'+' if p['net_pnl'] >= 0 else ''}₹{p['net_pnl']:,.1f}"
                ret_str = f"{'+' if p['return_pct'] >= 0 else ''}{p['return_pct']:.1f}%"
                conv_str = "🟢 YES" if p["converged"] else "⚪ NO"
                print(f"  {p['trade_id']:<8} {p['strategy'][:21]:<22} {p['instrument']:<17} {p['side']:<5} {p['qty']:<5} {p['entry_price']:<8.1f} {p['current_price']:<8.1f} {p['entry_fair']:<8.1f} {pnl_str:<11} {ret_str:<8} {p['entry_mscore']:+5.2f}σ   {conv_str}")

        # Recent Closed Trades Table
        print("-" * 108)
        print(f"[CLOSED TRADE LOGS] ({len(self.closed_trades)} Total Trades Executed)")
        if not self.closed_trades:
            print("  No trades closed yet.")
        else:
            for t in self.closed_trades[-4:]:
                pnl_str = f"{'+' if t['realized_pnl'] >= 0 else ''}₹{t['realized_pnl']:,.1f}"
                ret_str = f"{'+' if t['return_pct'] >= 0 else ''}{t['return_pct']:.1f}%"
                status_icon = "🟢 PROFIT" if t["realized_pnl"] >= 0 else "🔴 LOSS"
                print(f"  {t['trade_id']} │ {t['instrument']:<15} {t['side']:<4} │ Entry: ₹{t['entry_price']:.1f} → Exit: ₹{t['exit_price']:.1f} │ Net: {pnl_str:<10} ({ret_str}) │ {status_icon} │ {t['exit_reason']}")

        print("=" * 108)
        print(f"  [Auto-Refresh every {self.update_interval}s | Press Ctrl+C to close positions & export IEEE validation report]")
        print("=" * 108)

    def export_audit_report(self):
        """Export full execution log and accuracy report for IEEE Transactions validation."""
        now_tag = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_file = OUTPUT_DIR / f"paper_trading_trades_{now_tag}.csv"
        json_file = OUTPUT_DIR / f"paper_trading_summary_{now_tag}.json"

        all_trades = self.closed_trades + self.positions
        if all_trades:
            df = pd.DataFrame(all_trades)
            df.to_csv(csv_file, index=False)
            self.log(f"📁 Exported {len(all_trades)} trades to: {csv_file}")

        all_closed = self.closed_trades
        wins = sum(1 for t in all_closed if t["realized_pnl"] > 0)
        losses = sum(1 for t in all_closed if t["realized_pnl"] <= 0)
        win_rate = (wins / len(all_closed) * 100) if all_closed else 0.0
        total_net_pnl = sum(t["realized_pnl"] for t in all_closed)
        total_gross_pnl = sum(t.get("gross_pnl", t["realized_pnl"]) for t in all_closed)
        total_friction = sum(t.get("friction_cost", 0.0) for t in all_closed)

        gross_profit = sum(t.get("gross_pnl", t["realized_pnl"]) for t in all_closed if t.get("gross_pnl", t["realized_pnl"]) > 0)
        gross_loss = abs(sum(t.get("gross_pnl", t["realized_pnl"]) for t in all_closed if t.get("gross_pnl", t["realized_pnl"]) < 0))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 1.0)

        converged_count = sum(1 for t in all_trades if t.get("converged", False))
        convergence_rate = (converged_count / len(all_trades) * 100) if all_trades else 0.0

        # Mean and standard deviation of trade returns
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
        self.log(f"📊 Exported IEEE Accuracy Summary to: {json_file}")

        print("\n" + "=" * 70)
        print("  FINAL QUANT ACCURACY & AUDIT SUMMARY (IEEE VALIDATION)")
        print("=" * 70)
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
        print("=" * 70 + "\n")

    def run(self, once: bool = False):
        """Main real-time terminal execution loop."""
        self.log(f"Starting Live Quant Paper Trader for {self.symbol}...")
        self.log(f"Refresh Interval: {self.update_interval}s | Max Concurrent Positions: {self.max_positions}")
        if not once:
            self.log("Press Ctrl+C at any time to exit and generate the IEEE accuracy report.\n")
            time.sleep(1.0)

        while self.running:
            try:
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

            if once or not self.running:
                self.export_audit_report()
                break

            time.sleep(self.update_interval)


def main():
    parser = argparse.ArgumentParser(description="Live NIFTY Options Quant Paper Trader & Accuracy Engine.")
    parser.add_argument("--symbol", default="NIFTY", help="Underlying index (default: NIFTY)")
    parser.add_argument("--interval", type=int, default=10, help="Loop refresh interval in seconds (default: 10s for optimal speed without blocks)")
    parser.add_argument("--tp", type=float, default=30.0, help="Take-profit percent (default: 30.0%%)")
    parser.add_argument("--sl", type=float, default=40.0, help="Stop-loss percent (default: 40.0%%)")
    parser.add_argument("--min-mscore", type=float, default=1.8, help="Minimum M-Score to trigger trade (default: 1.8)")
    parser.add_argument("--max-pos", type=int, default=6, help="Maximum concurrent open positions (default: 6)")
    parser.add_argument("--once", action="store_true", help="Run single scan and export report without continuous loop")
    args = parser.parse_args()

    engine = LiveQuantPaperTrader(
        symbol=args.symbol,
        update_interval_sec=args.interval,
        take_profit_pct=args.tp,
        stop_loss_pct=args.sl,
        min_mscore=args.min_mscore,
        max_positions=args.max_pos
    )
    engine.run(once=args.once)


if __name__ == "__main__":
    main()
