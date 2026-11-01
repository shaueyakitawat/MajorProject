"""Daily, point-based NIFTY option research backtest.

This module intentionally does not import or call the production backtest
service. It uses only the preserved historical research CSV files.
"""

from __future__ import annotations

import hashlib
import json
import math
import platform
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from hmmlearn.hmm import GaussianHMM

ROOT = Path(__file__).resolve().parents[2]
INDEX_PATH = ROOT / "data/research/nifty50_index_daily.csv"
OPTIONS_PATH = ROOT / "data/research/nifty_options_daily.csv"
OUTPUT = ROOT / "data/research/backtest"
DOCS = ROOT / "docs/research"
FIGURES = DOCS / "figures"
TRAIN_END = pd.Timestamp("2024-12-31")
VALIDATION_END = pd.Timestamp("2025-06-30")
EMA_FAST = 10
EMA_SLOW = 30
RSI_PERIOD = 14
RSI_OVERSOLD = 30.0
RSI_OVERBOUGHT = 70.0
BREAKOUT_PERIOD = 20
ATR_PERIOD = 14
ATR_MULTIPLIER = 1.5
REWARD_RISK = 2.0
MAX_HOLDING_SESSIONS = 10
ATM_TOLERANCE = 0.025
MIN_DTE = 15
MAX_DTE = 45
MIN_HMM_HISTORY = 120
HMM_WINDOW = 120
ANNUAL_DAYS = 252.0


@dataclass(frozen=True)
class Signal:
    strategy: str
    signal_date: pd.Timestamp
    direction: int


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    index = pd.read_csv(INDEX_PATH, parse_dates=["trade_date"]).sort_values("trade_date")
    index = index.drop_duplicates("trade_date").set_index("trade_date")
    options = pd.read_csv(
        OPTIONS_PATH,
        parse_dates=["trade_date", "expiry"],
        low_memory=False,
        usecols=[
            "trade_date", "expiry", "strike", "option_type", "open", "high",
            "low", "close", "contracts", "open_interest", "instrument",
            "symbol", "source_schema", "source_url",
        ],
    )
    numeric = ["strike", "open", "high", "low", "close", "contracts", "open_interest"]
    for field in numeric:
        options[field] = pd.to_numeric(options[field], errors="coerce")
    options = options.sort_values(["trade_date", "expiry", "strike", "option_type"])
    return index, options


def add_indicators(index: pd.DataFrame) -> pd.DataFrame:
    frame = index.copy()
    close = frame["close"].astype(float)
    frame["ema_fast"] = close.ewm(span=EMA_FAST, adjust=False, min_periods=EMA_FAST).mean()
    frame["ema_slow"] = close.ewm(span=EMA_SLOW, adjust=False, min_periods=EMA_SLOW).mean()
    change = close.diff()
    gain = change.clip(lower=0).ewm(alpha=1 / RSI_PERIOD, adjust=False, min_periods=RSI_PERIOD).mean()
    loss = (-change.clip(upper=0)).ewm(alpha=1 / RSI_PERIOD, adjust=False, min_periods=RSI_PERIOD).mean()
    frame["rsi"] = 100 - (100 / (1 + gain / loss.replace(0, np.nan)))
    frame["rsi"] = frame["rsi"].fillna(100.0)
    previous_close = close.shift(1)
    true_range = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - previous_close).abs(),
            (frame["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    frame["atr"] = true_range.rolling(ATR_PERIOD, min_periods=ATR_PERIOD).mean()
    frame["atr_ratio"] = frame["atr"] / close
    frame["previous_high"] = frame["high"].shift(1).rolling(BREAKOUT_PERIOD).max()
    frame["previous_low"] = frame["low"].shift(1).rolling(BREAKOUT_PERIOD).min()
    returns = np.log(close / close.shift(1))
    frame["log_return"] = returns
    frame["vol_feature"] = returns.rolling(20, min_periods=20).std() * np.sqrt(ANNUAL_DAYS)
    return frame


def frozen_breakout_threshold(index: pd.DataFrame) -> float:
    threshold = index.loc[index.index <= TRAIN_END, "atr_ratio"].dropna().median()
    if not np.isfinite(threshold):
        raise ValueError("Training ATR/close threshold is unavailable")
    return float(threshold)


def generate_signals(index: pd.DataFrame, breakout_threshold: float) -> tuple[dict[str, list[Signal]], list[dict]]:
    signals = {name: [] for name in ("ema_crossover", "rsi_reversal", "volatility_breakout", "hmm_filtered_ema")}
    for position in range(1, len(index)):
        date = index.index[position]
        previous = index.iloc[position - 1]
        current = index.iloc[position]
        if pd.notna(current["ema_fast"]) and pd.notna(current["ema_slow"]):
            crossed_up = previous["ema_fast"] <= previous["ema_slow"] and current["ema_fast"] > current["ema_slow"]
            crossed_down = previous["ema_fast"] >= previous["ema_slow"] and current["ema_fast"] < current["ema_slow"]
            if crossed_up:
                signals["ema_crossover"].append(Signal("ema_crossover", date, 1))
            if crossed_down:
                signals["ema_crossover"].append(Signal("ema_crossover", date, -1))
        if previous["rsi"] <= RSI_OVERSOLD < current["rsi"]:
            signals["rsi_reversal"].append(Signal("rsi_reversal", date, 1))
        if previous["rsi"] >= RSI_OVERBOUGHT > current["rsi"]:
            signals["rsi_reversal"].append(Signal("rsi_reversal", date, -1))
        if pd.notna(current["previous_high"]) and current["close"] > current["previous_high"]:
            if current["atr_ratio"] >= breakout_threshold:
                signals["volatility_breakout"].append(Signal("volatility_breakout", date, 1))
        if pd.notna(current["previous_low"]) and current["close"] < current["previous_low"]:
            if current["atr_ratio"] >= breakout_threshold:
                signals["volatility_breakout"].append(Signal("volatility_breakout", date, -1))
    signals["hmm_filtered_ema"], hmm_diagnostics = hmm_filter_ema(index, signals["ema_crossover"])
    return signals, hmm_diagnostics


def hmm_state_available(index: pd.DataFrame, date: pd.Timestamp) -> tuple[int | None, dict]:
    before = index.loc[index.index < date, "vol_feature"].dropna().tail(HMM_WINDOW)
    current = index.loc[date, "vol_feature"]
    diagnostic = {
        "signal_date": date.date().isoformat(),
        "training_start": before.index[0].date().isoformat() if len(before) else None,
        "training_endpoint": before.index[-1].date().isoformat() if len(before) else None,
        "training_observations": int(len(before)),
        "state_count": 2,
        "converged": False,
        "filtered_probability_state_0": None,
        "filtered_probability_state_1": None,
        "selected_state": None,
        "state_volatility_ordering": None,
        "passed_filter": False,
        "reason": None,
    }
    if len(before) < MIN_HMM_HISTORY or not np.isfinite(current):
        diagnostic["reason"] = "insufficient_prior_feature_history"
        return None, diagnostic
    mean = float(before.mean())
    std = float(before.std(ddof=0))
    std = std if std > 0 else 1.0
    train = ((before.to_numpy() - mean) / std).reshape(-1, 1)
    current_scaled = (float(current) - mean) / std
    model = GaussianHMM(n_components=2, covariance_type="diag", n_iter=500, random_state=42, tol=1e-4)
    model.fit(train)
    if not model.monitor_.converged:
        diagnostic["reason"] = "hmm_not_converged"
        return None, diagnostic
    probabilities = model.predict_proba(np.vstack([train, [[current_scaled]]]))[-1]
    state = int(np.argmax(probabilities))
    order = np.argsort(model.means_.ravel())
    rank = int(np.where(order == state)[0][0])
    diagnostic.update({
        "converged": True,
        "filtered_probability_state_0": float(probabilities[0]),
        "filtered_probability_state_1": float(probabilities[1]),
        "selected_state": rank,
        "state_volatility_ordering": order.tolist(),
        "passed_filter": False,
    })
    return rank, diagnostic


def hmm_filter_ema(index: pd.DataFrame, ema_signals: list[Signal]) -> tuple[list[Signal], list[dict]]:
    filtered = []
    diagnostics = []
    for signal in ema_signals:
        rank, diagnostic = hmm_state_available(index, signal.signal_date)
        diagnostic["direction"] = signal.direction
        if rank is None:
            diagnostics.append(diagnostic)
            continue
        passed = (signal.direction == 1 and rank == 0) or (signal.direction == -1 and rank == 1)
        diagnostic["passed_filter"] = passed
        diagnostic["reason"] = "accepted_low_state_for_long" if passed and signal.direction == 1 else (
            "accepted_high_state_for_short" if passed else "state_filter_rejected"
        )
        diagnostics.append(diagnostic)
        if passed:
            filtered.append(Signal("hmm_filtered_ema", signal.signal_date, signal.direction))
    return filtered, diagnostics


def evaluation_period(date: pd.Timestamp) -> str | None:
    if date <= TRAIN_END:
        return "training"
    if date <= VALIDATION_END:
        return "validation"
    return "test" if date <= pd.Timestamp("2025-12-31") else None


def select_contract(options: pd.DataFrame, signal_date: pd.Timestamp, direction: int, spot: float) -> tuple[pd.Series | None, str | None]:
    option_type = "CE" if direction > 0 else "PE"
    candidates = options[
        (options["trade_date"] == signal_date)
        & (options["option_type"] == option_type)
        & (options["contracts"] > 0)
        & (options["open_interest"] > 0)
        & (options["strike"] > 0)
        & (options["close"] > 0)
        & (options["expiry"] > signal_date)
    ].copy()
    candidates["dte"] = (candidates["expiry"] - signal_date).dt.days
    candidates = candidates[candidates["dte"].between(MIN_DTE, MAX_DTE)]
    candidates["absolute_strike_distance"] = (candidates["strike"] - spot).abs()
    candidates = candidates[candidates["absolute_strike_distance"] / spot <= ATM_TOLERANCE]
    if candidates.empty:
        return None, "no_valid_contract_at_signal"
    candidates = candidates.sort_values(
        ["absolute_strike_distance", "expiry", "strike", "option_type", "source_schema", "source_url"],
        kind="mergesort",
    )
    return candidates.iloc[0], None


def true_range(frame: pd.DataFrame) -> pd.Series:
    previous = frame["close"].shift(1)
    return pd.concat(
        [frame["high"] - frame["low"], (frame["high"] - previous).abs(), (frame["low"] - previous).abs()],
        axis=1,
    ).max(axis=1)


def prior_atr(options: pd.DataFrame, identity: tuple, entry_date: pd.Timestamp) -> float | None:
    trade_date, expiry, strike, option_type = identity
    bars = options[
        (options["trade_date"] < entry_date)
        & (options["expiry"] == expiry)
        & (options["strike"] == strike)
        & (options["option_type"] == option_type)
        & (options["contracts"] > 0)
        & (options["open"] > 0)
        & (options["high"] > 0)
        & (options["low"] > 0)
        & (options["close"] > 0)
    ].sort_values("trade_date")
    if len(bars) < ATR_PERIOD:
        return None
    values = true_range(bars).dropna()
    if len(values) < ATR_PERIOD:
        return None
    return float(values.tail(ATR_PERIOD).mean())


def resolve_exit(
    entry_price: float, stop: float, target: float, bars: pd.DataFrame,
    include_entry_session: bool = False,
) -> tuple[pd.Series | None, str, float | None, int]:
    """Resolve daily OHLC exits using conservative stop-first ordering."""
    for holding, (_, bar) in enumerate(bars.iterrows(), start=1):
        open_price, high, low = map(float, (bar["open"], bar["high"], bar["low"]))
        is_entry_session = include_entry_session and holding == 1
        if not is_entry_session and open_price <= stop:
            return bar, "stop_loss_gap", open_price, holding
        if not is_entry_session and open_price >= target:
            return bar, "target_gap", open_price, holding
        if low <= stop:
            return bar, "stop_loss", stop, holding
        if high >= target:
            return bar, "target", target, holding
    if bars.empty:
        return None, "no_valid_exit_bars", None, 0
    last = bars.iloc[-1]
    return last, "time_exit", float(last["close"]), len(bars)


def execute_signal(
    index: pd.DataFrame,
    options: pd.DataFrame,
    signal: Signal,
    execution_diagnostics: list[dict] | None = None,
) -> tuple[dict | None, str | None]:
    period = evaluation_period(signal.signal_date)
    if period is None:
        return None, "outside_evaluation_period"
    spot = float(index.loc[signal.signal_date, "close"])
    selected, reason = select_contract(options, signal.signal_date, signal.direction, spot)
    if selected is None:
        return None, reason
    index_dates = index.index
    later = index_dates[index_dates > signal.signal_date]
    if len(later) == 0:
        return None, "no_next_index_session"
    entry_date = later[0]
    period_end = {
        "training": TRAIN_END,
        "validation": VALIDATION_END,
        "test": pd.Timestamp("2025-12-31"),
    }[period]
    if entry_date > period_end:
        return None, "entry_crosses_period_boundary"
    entry = options[
        (options["trade_date"] == entry_date)
        & (options["expiry"] == selected["expiry"])
        & (options["strike"] == selected["strike"])
        & (options["option_type"] == selected["option_type"])
    ].copy()
    if entry.empty:
        return None, "no_valid_next_session_open"
    entry_row = entry.iloc[0]
    entry_ohlc = pd.to_numeric(entry_row[["open", "high", "low", "close"]], errors="coerce")
    if (
        pd.to_numeric(entry_row["contracts"], errors="coerce") <= 0
        or not np.isfinite(entry_ohlc).all()
        or (entry_ohlc <= 0).any()
    ):
        return None, "invalid_or_zero_volume_entry_bar"
    identity = (signal.signal_date, selected["expiry"], selected["strike"], selected["option_type"])
    atr = prior_atr(options, identity, entry_date)
    if atr is None:
        return None, "insufficient_prior_atr_history"
    entry_price = float(entry_row["open"])
    initial_risk = ATR_MULTIPLIER * atr
    stop = entry_price - initial_risk
    target = entry_price + REWARD_RISK * initial_risk
    if stop <= 0:
        return None, "non_positive_stop"
    execution_bars = options[
        (options["trade_date"] >= entry_date)
        & (options["trade_date"] <= period_end)
        & (options["expiry"] == selected["expiry"])
        & (options["strike"] == selected["strike"])
        & (options["option_type"] == selected["option_type"])
    ].sort_values("trade_date")
    execution_ohlc = execution_bars[["open", "high", "low", "close"]].apply(
        pd.to_numeric, errors="coerce"
    )
    valid = (
        pd.to_numeric(execution_bars["contracts"], errors="coerce").gt(0)
        & execution_ohlc.notna().all(axis=1)
        & execution_ohlc.gt(0).all(axis=1)
    )
    if execution_diagnostics is not None:
        for _, excluded in execution_bars.loc[~valid].iterrows():
            execution_diagnostics.append({
                "strategy": signal.strategy,
                "signal_date": signal.signal_date.date().isoformat(),
                "entry_date": entry_date.date().isoformat(),
                "trade_date": excluded["trade_date"].date().isoformat(),
                "expiry": excluded["expiry"].date().isoformat(),
                "strike": float(excluded["strike"]),
                "option_type": excluded["option_type"],
                "reason": "zero_volume_or_invalid_execution_bar",
            })
    future = execution_bars.loc[valid].head(MAX_HOLDING_SESSIONS)
    exit_row, exit_reason, exit_price, holding = resolve_exit(
        entry_price, stop, target, future, include_entry_session=True
    )
    if exit_row is None or exit_price is None:
        return None, "no_valid_exit_bars"
    return {
        "strategy": signal.strategy,
        "period": period,
        "signal_date": signal.signal_date.date().isoformat(),
        "entry_date": entry_date.date().isoformat(),
        "exit_date": pd.Timestamp(exit_row["trade_date"]).date().isoformat(),
        "direction": "LONG",
        "option_type": selected["option_type"],
        "instrument": selected.get("instrument"),
        "symbol": selected.get("symbol"),
        "expiry": selected["expiry"].date().isoformat(),
        "strike": float(selected["strike"]),
        "source_schema": selected.get("source_schema"),
        "source_url": selected.get("source_url"),
        "entry_price": entry_price,
        "exit_price": exit_price,
        "atr": atr,
        "stop_price": stop,
        "target_price": target,
        "holding_sessions": holding,
        "exit_reason": exit_reason,
        "gross_pnl_points": exit_price - entry_price,
        "gross_return": (exit_price - entry_price) / entry_price,
    }, None


def performance(trades: pd.DataFrame, skipped: dict[str, int]) -> dict:
    if trades.empty:
        values = np.array([], dtype=float)
    else:
        values = trades["gross_pnl_points"].to_numpy(dtype=float)
    wins = values[values > 0]
    losses = values[values < 0]
    equity = np.concatenate(([0.0], np.cumsum(values))) if len(values) else np.array([0.0])
    drawdown = equity - np.maximum.accumulate(equity)
    returns = trades["gross_return"].to_numpy(dtype=float) if len(trades) else np.array([], dtype=float)
    downside = returns[returns < 0]
    consecutive = current = 0
    for value in values:
        current = current + 1 if value < 0 else 0
        consecutive = max(consecutive, current)
    return {
        "total_trades": int(len(values)),
        "winning_trades": int(len(wins)),
        "losing_trades": int(len(losses)),
        "win_rate": float(len(wins) / len(values)) if len(values) else None,
        "gross_pnl_points": float(values.sum()) if len(values) else 0.0,
        "average_pnl_points": float(values.mean()) if len(values) else None,
        "average_return_fraction": float(returns.mean()) if len(returns) else None,
        "average_percentage_return": float(returns.mean() * 100.0) if len(returns) else None,
        "profit_factor": float(wins.sum() / abs(losses.sum())) if len(losses) and losses.sum() else None,
        "trade_level_return_mean_fraction": float(returns.mean()) if len(returns) else None,
        "trade_level_return_std_fraction": float(returns.std(ddof=1)) if len(returns) > 1 else None,
        "sharpe_ratio": None,
        "sortino_ratio": None,
        "maximum_drawdown_points": float(drawdown.min()) if len(drawdown) else 0.0,
        "largest_loss_points": float(losses.min()) if len(losses) else None,
        "maximum_consecutive_losses": int(consecutive),
        "stop_loss_exits": int(trades["exit_reason"].str.startswith("stop_loss").sum()) if len(trades) else 0,
        "target_exits": int(trades["exit_reason"].str.startswith("target").sum()) if len(trades) else 0,
        "time_exits": int((trades["exit_reason"] == "time_exit").sum()) if len(trades) else 0,
        "average_holding_sessions": float(trades["holding_sessions"].mean()) if len(trades) else None,
        "skipped_trades_by_reason": skipped,
        "pnl_unit": "option price points; no lot multiplier applied",
    }


def run() -> dict:
    index, options = load_data()
    index = add_indicators(index)
    threshold = frozen_breakout_threshold(index)
    signals, hmm_diagnostics = generate_signals(index, threshold)
    all_trades = []
    execution_diagnostics = []
    metrics = {}
    skipped_rows = []
    for strategy, strategy_signals in signals.items():
        skipped_by_period: dict[str, dict[str, int]] = {}
        accepted = []
        last_exit = None
        for signal in strategy_signals:
            period = evaluation_period(signal.signal_date) or "outside_evaluation_period"
            skipped = skipped_by_period.setdefault(period, {})
            if last_exit is not None and signal.signal_date <= last_exit:
                skipped["overlapping_position"] = skipped.get("overlapping_position", 0) + 1
                skipped_rows.append({"strategy": strategy, "period": period, "signal_date": signal.signal_date.date().isoformat(), "direction": signal.direction, "reason": "overlapping_position"})
                continue
            trade, reason = execute_signal(index, options, signal, execution_diagnostics)
            if trade is None:
                skipped[reason or "unknown"] = skipped.get(reason or "unknown", 0) + 1
                skipped_rows.append({"strategy": strategy, "period": period, "signal_date": signal.signal_date.date().isoformat(), "direction": signal.direction, "reason": reason or "unknown"})
                continue
            last_exit = pd.Timestamp(trade["exit_date"])
            accepted.append(trade)
            all_trades.append(trade)
        frame = pd.DataFrame(accepted)
        for period in ("training", "validation", "test"):
            period_frame = frame[frame["period"] == period] if not frame.empty else frame
            metrics[f"{strategy}|{period}"] = performance(period_frame, skipped_by_period.get(period, {}))
    benchmark = {}
    for period in ("training", "validation", "test"):
        benchmark[f"no_trade|{period}"] = performance(pd.DataFrame(), {})
    OUTPUT.mkdir(parents=True, exist_ok=True)
    trades = pd.DataFrame(all_trades)
    trades.to_csv(OUTPUT / "trades.csv", index=False)
    pd.DataFrame(skipped_rows).to_csv(OUTPUT / "skipped_signals.csv", index=False)
    pd.DataFrame(hmm_diagnostics).to_csv(OUTPUT / "hmm_diagnostics.csv", index=False)
    pd.DataFrame(execution_diagnostics).to_csv(OUTPUT / "execution_bar_diagnostics.csv", index=False)
    comparison = pd.DataFrame(
        [{"strategy": key.split("|")[0], "period": key.split("|")[1], **value} for key, value in {**metrics, **benchmark}.items()]
    )
    comparison.to_csv(OUTPUT / "strategy_comparison.csv", index=False)
    payload = {
        "run_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "datasets": {"index": str(INDEX_PATH.relative_to(ROOT)), "options": str(OPTIONS_PATH.relative_to(ROOT)), "index_sha256": sha256(INDEX_PATH), "options_sha256": sha256(OPTIONS_PATH)},
        "parameters": {"ema_fast": EMA_FAST, "ema_slow": EMA_SLOW, "rsi_period": RSI_PERIOD, "rsi_thresholds": [RSI_OVERSOLD, RSI_OVERBOUGHT], "breakout_period": BREAKOUT_PERIOD, "atr_period": ATR_PERIOD, "atr_multiplier": ATR_MULTIPLIER, "reward_risk": REWARD_RISK, "max_holding_sessions": MAX_HOLDING_SESSIONS, "atm_tolerance": ATM_TOLERANCE, "dte": [MIN_DTE, MAX_DTE], "frozen_breakout_atr_close_threshold": threshold, "hmm_states": 2, "hmm_window": HMM_WINDOW},
        "software": {"python": sys.version, "platform": platform.platform(), "pandas": version("pandas"), "numpy": version("numpy"), "hmmlearn": version("hmmlearn"), "matplotlib": version("matplotlib")},
        "metrics": metrics,
        "benchmark": benchmark,
        "trade_count": len(trades),
        "limitations": ["Gross point-based results only.", "No historical lot-size multiplier.", "No bid/ask or intraday data.", "Daily OHLC same-bar ambiguity uses stop-loss first.", "No rupee P&L or executable-return claim."],
    }
    (OUTPUT / "performance_metrics.json").write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    (OUTPUT / "run_manifest.json").write_text(
        json.dumps(
            {
                "run_timestamp_utc": payload["run_timestamp_utc"],
                "datasets": payload["datasets"],
                "parameters": payload["parameters"],
                "software": payload["software"],
                "output_files": [
                    "trades.csv",
                    "skipped_signals.csv",
                    "performance_metrics.json",
                    "strategy_comparison.csv",
                    "../../docs/research/backtest_methodology.md",
                    "../../docs/research/backtest_results.md",
                    "../../docs/research/backtest_data_limitations.md",
                    "hmm_diagnostics.csv",
                    "execution_bar_diagnostics.csv",
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    write_reports(index, trades, payload)
    return payload


def write_reports(index: pd.DataFrame, trades: pd.DataFrame, payload: dict) -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    equity = trades.copy()
    if not equity.empty:
        equity["exit_date"] = pd.to_datetime(equity["exit_date"])
        equity = equity.sort_values("exit_date")
        equity["equity_points"] = equity.groupby("strategy")["gross_pnl_points"].cumsum()
        plt.figure(figsize=(10, 5))
        for strategy, group in equity.groupby("strategy"):
            plt.plot(group["exit_date"], group["equity_points"], label=strategy)
        plt.title("Research backtest cumulative gross point P&L")
        plt.ylabel("Cumulative option points")
        plt.legend()
        plt.tight_layout()
        plt.savefig(FIGURES / "research_backtest_equity_curves.png", dpi=150)
        plt.close()
        plt.figure(figsize=(10, 5))
        for strategy, group in equity.groupby("strategy"):
            peak = group["equity_points"].cummax()
            plt.plot(group["exit_date"], group["equity_points"] - peak, label=strategy)
        plt.title("Research backtest drawdown")
        plt.ylabel("Drawdown points")
        plt.legend()
        plt.tight_layout()
        plt.savefig(FIGURES / "research_backtest_drawdowns.png", dpi=150)
        plt.close()
    (DOCS / "backtest_methodology.md").write_text(
        "# Phase 4 Research Backtest Methodology\n\n"
        "This isolated daily option backtest uses only the preserved NSE option "
        "bhavcopy dataset and aligned daily NIFTY index dataset. Signals use "
        "the index close at date t and enter the same contract at the next "
        "available session's option OPEN. The entry candle is the first "
        "monitored candle and counts as holding session 1; its high/low are "
        "checked after entry at the open. Subsequent opening gaps are handled "
        "conservatively. Every entry and execution candle requires positive "
        "contracts and valid OHLC. Contracts are never substituted after entry. "
        "Positions do not overlap within a strategy; later signals are recorded "
        "as skipped. A trade cannot cross its evaluation-period end.\n\n"
        "Strategies are deterministic EMA(10/30), RSI(14) reversal at 30/70, "
        "20-session previous-high/low breakout filtered by the frozen training "
        "median ATR/close, and EMA filtered by a two-state walk-forward HMM. "
        "The HMM is fitted only on observations strictly before each signal date.\n\n"
        "Option selection requires CE/PE direction, 15-45 calendar DTE, a strike "
        "within 2.5% of spot, positive contracts, positive OI and positive close. "
        "The option's ATR(14) uses only valid positive OHLC bars strictly before "
        "entry. Stop is entry minus 1.5 ATR and target is entry plus twice the "
        "initial risk. Opening gaps are executed at OPEN; otherwise stop is "
        "checked before target. Same-bar ambiguity is conservatively stop-first. "
        "Unresolved positions exit after 10 valid option sessions at CLOSE.\n\n"
        "Results are gross option price points only. No lot multiplier, rupee P&L, "
        "bid/ask spread, or executable-return claim is made. Transaction-cost "
        "sensitivity is deferred pending verified historical lot sizes and fee "
        "inputs. Sharpe and Sortino are suppressed because the sample is too "
        "small for conventional annualized inference. Every skipped signal is preserved in "
        "`data/research/backtest/skipped_signals.csv` and summarized by period "
        "in the metrics JSON.\n",
        encoding="utf-8",
    )
    (DOCS / "backtest_results.md").write_text(
        "# Phase 4 Research Backtest Results\n\n"
        "The following results were generated from the frozen deterministic "
        "configuration. They are gross point-based option results, not net or "
        "executable returns.\n\n"
        "```json\n" + json.dumps(payload["metrics"], indent=2, default=str) + "\n```\n\n"
        "No-trade benchmark:\n\n```json\n" + json.dumps(payload["benchmark"], indent=2) + "\n```\n",
        encoding="utf-8",
    )
    (DOCS / "backtest_data_limitations.md").write_text(
        "# Phase 4 Research Backtest Data Limitations\n\n"
        "- Options are daily bhavcopy records; intraday execution is unsupported.\n"
        "- No bid, ask, spread, IV, or order-book data exists.\n"
        "- Historical lot-size multipliers are unavailable, so no rupee P&L is reported.\n"
        "- Option CLOSE is a daily last-traded reference; OPEN and OHLC execution are not guaranteed fills.\n"
        "- Zero-volume records are excluded from execution, while source data is preserved.\n"
        "- Settlement-zero anomalies remain in the source dataset and are not used as valid execution prices.\n"
        "- The index source is Yahoo Finance, a third-party source with unresolved redistribution terms.\n"
        "- Daily bars cannot establish the intraday sequence when stop and target are both crossed; stop-first is conservative.\n"
        "- Short sample length limits statistical power and generalization.\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    run()
