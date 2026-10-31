"""
scripts/run_csv_options_backtest.py
================================================================================
CLI Runner for the Historical NIFTY Options Daily Tradable Backtest Engine.
Runs the complete quantitative options pipeline against
data/nifty_options_daily_tradable.csv and exports research results.
================================================================================
"""

import sys
import os
import json
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from backend.services.csv_options_backtest_engine import CsvOptionsBacktestEngine


def main():
    print("=" * 80)
    print(" QUANTLENS TERMINAL — HISTORICAL OPTIONS MISPRICING BACKTEST")
    print(" Dataset: data/nifty_options_daily_tradable.csv (346,156 rows)")
    print(" Pipeline: EGARCH(1,1) + BSM Fair Value + IV Inversion + VRP + M-Score")
    print("=" * 80)

    csv_path = PROJECT_ROOT / "data" / "nifty_options_daily_tradable.csv"
    if not csv_path.exists():
        print(f"Error: Dataset not found at {csv_path}")
        sys.exit(1)

    engine = CsvOptionsBacktestEngine(
        csv_path=str(csv_path),
        initial_capital=2500000.0,
        min_mscore=1.20,
        take_profit_pct=25.0,
        stop_loss_pct=10.0,
        max_positions=8
    )

    results = engine.run_simulation()
    summary = results["summary"]
    meta = results["metadata"]

    outputs_dir = PROJECT_ROOT / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    # 1. Export summary JSON
    json_path = outputs_dir / "csv_options_backtest_results.json"
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n[✓] Exported full backtest JSON -> {json_path}")

    # 2. Export trades CSV
    trades_df = pd.DataFrame(results["trades"])
    trades_csv_path = outputs_dir / "csv_options_backtest_trades.csv"
    trades_df.to_csv(trades_csv_path, index=False)
    print(f"[✓] Exported {len(trades_df)} closed trades -> {trades_csv_path}")

    # 3. Export daily equity progression CSV
    eq_df = pd.DataFrame(results["equity_curve"])
    eq_csv_path = outputs_dir / "csv_options_backtest_equity_curve.csv"
    eq_df.to_csv(eq_csv_path, index=False)
    print(f"[✓] Exported equity progression -> {eq_csv_path}")

    # 4. Print Executive Research Summary Table
    print("\n" + "=" * 80)
    print("                    EXECUTIVE RESEARCH SUMMARY")
    print("=" * 80)
    print(f" Period Evaluated:           {meta['period']} ({meta['trading_sessions']} sessions)")
    print(f" Initial Trading Capital:     ₹{meta['initial_capital']:,.2f}")
    print(f" Final Portfolio Equity:      ₹{meta['final_equity']:,.2f}")
    print(f" Total Net P&L:               ₹{summary['total_net_pnl']:,.2f} ({summary['total_return_pct']:+.2f}%)")
    print(f" Gross P&L:                   ₹{summary['total_gross_pnl']:,.2f}")
    print(f" Total Regulatory Friction:   ₹{summary['total_friction']:,.2f} (STT, GST, Exchange, Brokerage)")
    print("-" * 80)
    print(f" Total Executed Trades:       {summary['total_trades']}")
    print(f" Win Rate:                    {summary['win_rate_pct']:.1f}% ({summary['win_count']}W / {summary['loss_count']}L)")
    print(f" Profit Factor:               {summary['profit_factor']:.2f}")
    print(f" Payoff Ratio (Avg W/L):      {summary['payoff_ratio']:.2f}")
    print(f" Average Holding Period:      {summary['avg_holding_days']:.1f} trading days")
    print("-" * 80)
    print(f" Compound Annual Growth (CAGR): {summary['cagr_pct']:+.2f}%")
    print(f" Annualized Sharpe Ratio:     {summary['sharpe_ratio']:.3f}")
    print(f" Sortino Ratio:               {summary['sortino_ratio']:.3f}")
    print(f" Calmar Ratio:                {summary['calmar_ratio']:.2f}")
    print(f" Maximum Drawdown (MDD):      ₹{summary['max_drawdown_amount']:,.2f} ({summary['max_drawdown_pct']:.2f}%)")
    print("=" * 80)

    # 5. Monthly breakdown
    print("\nMONTHLY PERFORMANCE BREAKDOWN:")
    print(" Month      | Trades | Win Rate | Net Realized P&L | Regulatory Friction")
    print("-" * 65)
    for m in results["monthly_performance"]:
        print(f" {m['month']}  |  {m['trades']:4d}  |  {m['win_rate']:5.1f}%  |  ₹{m['net_pnl']:14,.2f}  |  ₹{m['friction']:10,.2f}")
    print("-" * 65)

    # 6. Regime breakdown
    print("\nVOLATILITY REGIME PERFORMANCE BREAKDOWN:")
    print(" Regime         | Trades | Win Rate | Net P&L        | Profit Factor")
    print("-" * 65)
    for r in results["regime_performance"]:
        print(f" {r['regime']:14s} |  {r['trades']:4d}  |  {r['win_rate']:5.1f}%  |  ₹{r['net_pnl']:12,.2f}  |  {r['profit_factor']:5.2f}")
    print("=" * 80)


if __name__ == "__main__":
    main()
