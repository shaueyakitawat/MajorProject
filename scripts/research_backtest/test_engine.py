import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from engine import (
    ATR_PERIOD,
    add_indicators,
    execute_signal,
    hmm_filter_ema,
    performance,
    prior_atr,
    resolve_exit,
    select_contract,
    Signal,
)


def option_rows(values):
    rows = []
    for i, value in enumerate(values):
        date = pd.Timestamp("2024-01-01") + pd.Timedelta(days=i)
        rows.append({
            "trade_date": date, "expiry": pd.Timestamp("2024-03-01"), "strike": 100.0,
            "option_type": "CE", "open": value, "high": value + 2, "low": value - 1,
            "close": value + 1, "contracts": 1, "open_interest": 1,
            "instrument": "IDO", "symbol": "NIFTY", "source_schema": "new", "source_url": "test",
        })
    return pd.DataFrame(rows)


class ResearchBacktestTests(unittest.TestCase):
    def test_indicators_use_only_prior_breakout_window(self):
        index = pd.DataFrame(
            {"open": [10] * 25, "high": np.arange(25) + 10, "low": np.arange(25) + 9, "close": np.arange(25) + 10},
            index=pd.date_range("2024-01-01", periods=25),
        )
        result = add_indicators(index)
        self.assertEqual(result.loc[pd.Timestamp("2024-01-21"), "previous_high"], 29.0)
        self.assertTrue(pd.isna(result.loc[pd.Timestamp("2024-01-20"), "previous_high"]))

    def test_prior_atr_excludes_entry_and_future_bars(self):
        options = option_rows(range(10, 30))
        entry_date = options.iloc[15]["trade_date"]
        identity = (options.iloc[0]["trade_date"], options.iloc[0]["expiry"], 100.0, "CE")
        atr = prior_atr(options, identity, entry_date)
        expected = float(((options["high"] - options["low"]).iloc[1:15]).tail(ATR_PERIOD).mean())
        self.assertAlmostEqual(atr, expected)

    def test_performance_is_point_based(self):
        trades = pd.DataFrame({
            "gross_pnl_points": [2.0, -1.0, 3.0],
            "gross_return": [0.2, -0.1, 0.3],
            "exit_reason": ["target", "stop_loss", "time_exit"],
            "holding_sessions": [1, 1, 2],
        })
        metrics = performance(trades, {"skipped": 1})
        self.assertEqual(metrics["gross_pnl_points"], 4.0)
        self.assertEqual(metrics["target_exits"], 1)
        self.assertEqual(metrics["stop_loss_exits"], 1)
        self.assertEqual(metrics["time_exits"], 1)
        self.assertEqual(metrics["pnl_unit"], "option price points; no lot multiplier applied")

    def test_no_production_backtest_import(self):
        source = Path(__file__).with_name("engine.py").read_text()
        self.assertNotIn("backend.services.backtest_service", source)

    def test_exit_opening_gap(self):
        bars = pd.DataFrame([{"open": 8.0, "high": 9.0, "low": 7.0, "close": 8.0}])
        _, reason, price, holding = resolve_exit(10.0, 9.0, 12.0, bars)
        self.assertEqual((reason, price, holding), ("stop_loss_gap", 8.0, 1))

    def test_same_bar_stop_target_is_stop_first(self):
        bars = pd.DataFrame([{"open": 10.0, "high": 13.0, "low": 8.0, "close": 11.0}])
        _, reason, price, _ = resolve_exit(10.0, 9.0, 12.0, bars)
        self.assertEqual((reason, price), ("stop_loss", 9.0))

    def test_entry_session_checks_stop_and_target_after_open(self):
        stop_bar = pd.DataFrame([{"open": 10.0, "high": 11.0, "low": 8.0, "close": 10.0}])
        _, reason, price, holding = resolve_exit(10.0, 9.0, 12.0, stop_bar, True)
        self.assertEqual((reason, price, holding), ("stop_loss", 9.0, 1))
        target_bar = pd.DataFrame([{"open": 10.0, "high": 13.0, "low": 10.0, "close": 12.0}])
        _, reason, price, holding = resolve_exit(10.0, 9.0, 12.0, target_bar, True)
        self.assertEqual((reason, price, holding), ("target", 12.0, 1))

    def test_entry_session_same_bar_is_stop_first(self):
        bars = pd.DataFrame([{"open": 10.0, "high": 13.0, "low": 8.0, "close": 10.0}])
        _, reason, price, holding = resolve_exit(10.0, 9.0, 12.0, bars, True)
        self.assertEqual((reason, price, holding), ("stop_loss", 9.0, 1))

    def test_target_gap_and_time_exit(self):
        gap = pd.DataFrame([{"open": 13.0, "high": 14.0, "low": 12.0, "close": 13.0}])
        _, reason, price, _ = resolve_exit(10.0, 9.0, 12.0, gap)
        self.assertEqual((reason, price), ("target_gap", 13.0))
        bars = pd.DataFrame([
            {"open": 10.0, "high": 11.0, "low": 9.5, "close": 10.5},
            {"open": 10.5, "high": 11.0, "low": 10.0, "close": 10.75},
        ])
        _, reason, price, holding = resolve_exit(10.0, 9.0, 12.0, bars)
        self.assertEqual((reason, price, holding), ("time_exit", 10.75, 2))

    def test_contract_identity_is_not_changed_by_exit_bars(self):
        bars = pd.DataFrame([
            {"trade_date": pd.Timestamp("2024-07-02"), "expiry": pd.Timestamp("2024-08-01"), "strike": 100.0, "option_type": "CE", "open": 10.0, "high": 11.0, "low": 9.0, "close": 10.5},
        ])
        resolve_exit(10.0, 8.0, 14.0, bars)
        self.assertEqual(tuple(bars.iloc[0][["expiry", "strike", "option_type"]]), (pd.Timestamp("2024-08-01"), 100.0, "CE"))

    def test_no_synthetic_price_is_created(self):
        source = Path(__file__).with_name("engine.py").read_text()
        self.assertNotIn("* 1.03", source)
        self.assertNotIn("black_scholes_price", source)

    def test_hmm_and_entry_are_strictly_forward(self):
        source = Path(__file__).with_name("engine.py").read_text()
        self.assertIn("index.index < date", source)
        self.assertIn("index_dates > signal.signal_date", source)
        self.assertIn("entry_date > period_end", source)

    def test_maximum_holding_period_is_bounded(self):
        bars = pd.DataFrame(
            [{"open": 10.0, "high": 11.0, "low": 9.5, "close": 10.0}] * 10
        )
        _, reason, _, holding = resolve_exit(10.0, 8.0, 14.0, bars)
        self.assertEqual((reason, holding), ("time_exit", 10))

    def test_drawdown_includes_initial_zero_equity(self):
        metrics = performance(
            pd.DataFrame({
                "gross_pnl_points": [-163.2535714286],
                "gross_return": [-0.5],
                "exit_reason": ["stop_loss"],
                "holding_sessions": [1],
            }),
            {},
        )
        self.assertAlmostEqual(metrics["maximum_drawdown_points"], -163.2535714286, places=6)

    def test_contract_selection_prioritizes_strike_distance_then_expiry(self):
        signal_date = pd.Timestamp("2024-07-01")
        options = pd.DataFrame([
            {"trade_date": signal_date, "expiry": pd.Timestamp("2024-08-01"), "strike": 101.0,
             "option_type": "CE", "contracts": 1, "open_interest": 1, "close": 1.0,
             "open": 1.0, "high": 1.0, "low": 1.0, "instrument": "I", "symbol": "N",
             "source_schema": "new", "source_url": "a"},
            {"trade_date": signal_date, "expiry": pd.Timestamp("2024-07-20"), "strike": 101.0,
             "option_type": "CE", "contracts": 1, "open_interest": 1, "close": 1.0,
             "open": 1.0, "high": 1.0, "low": 1.0, "instrument": "I", "symbol": "N",
             "source_schema": "new", "source_url": "b"},
            {"trade_date": signal_date, "expiry": pd.Timestamp("2024-07-20"), "strike": 100.5,
             "option_type": "CE", "contracts": 1, "open_interest": 1, "close": 1.0,
             "open": 1.0, "high": 1.0, "low": 1.0, "instrument": "I", "symbol": "N",
             "source_schema": "new", "source_url": "c"},
        ])
        selected, reason = select_contract(options, signal_date, 1, 100.0)
        self.assertIsNone(reason)
        self.assertEqual(float(selected["strike"]), 100.5)

    def test_zero_contract_entry_is_rejected(self):
        dates = pd.date_range("2024-07-01", periods=25, freq="D")
        index = pd.DataFrame({"close": [100.0] * len(dates)}, index=dates)
        options = option_rows([10.0] * len(dates))
        options["trade_date"] = dates
        options["expiry"] = pd.Timestamp("2024-08-10")
        options.loc[options["trade_date"] == pd.Timestamp("2024-07-21"), "contracts"] = 0
        trade, reason = execute_signal(index, options, Signal("ema_crossover", pd.Timestamp("2024-07-20"), 1))
        self.assertIsNone(trade)
        self.assertEqual(reason, "invalid_or_zero_volume_entry_bar")

    def test_zero_contract_execution_bar_is_excluded_and_diagnosed(self):
        dates = pd.date_range("2024-07-01", periods=25, freq="D")
        index = pd.DataFrame({"close": [100.0] * len(dates)}, index=dates)
        options = option_rows([10.0] * len(dates))
        options["trade_date"] = dates
        options["expiry"] = pd.Timestamp("2024-08-10")
        options.loc[options["trade_date"] == pd.Timestamp("2024-07-22"), "contracts"] = 0
        diagnostics = []
        trade, reason = execute_signal(
            index, options, Signal("ema_crossover", pd.Timestamp("2024-07-20"), 1), diagnostics
        )
        self.assertIsNone(reason)
        self.assertIsNotNone(trade)
        self.assertEqual(len(diagnostics), 1)
        self.assertEqual(diagnostics[0]["reason"], "zero_volume_or_invalid_execution_bar")

    def test_hmm_emits_diagnostic_for_each_signal(self):
        dates = pd.date_range("2024-07-01", periods=20, freq="D")
        index = pd.DataFrame({"vol_feature": np.linspace(0.01, 0.02, len(dates))}, index=dates)
        signals = [Signal("ema_crossover", dates[-1], 1)]
        filtered, diagnostics = hmm_filter_ema(index, signals)
        self.assertEqual(len(diagnostics), 1)
        self.assertEqual(diagnostics[0]["signal_date"], dates[-1].date().isoformat())
        self.assertIn("reason", diagnostics[0])


if __name__ == "__main__":
    unittest.main()
