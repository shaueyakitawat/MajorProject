# QuantLens IEEE Transactions Overleaf Bundle

This directory contains everything required to compile the IEEE Transactions publication manuscript for **QuantLens**.

## 1-Click Overleaf Instructions:
1. Log into **[Overleaf](https://www.overleaf.com/)**.
2. Click **New Project** -> **Upload Project**.
3. Select `paper_overleaf.zip` from this repository (located in the project root).
4. Click **Recompile**.
   - Overleaf will compile `main.tex` (or `paper.tex`) with all 6 publication figures and `IEEEtran.cls`.

## Directory Contents:
- `main.tex` / `paper.tex`: The publication-grade IEEE journal LaTeX manuscript.
- `IEEEtran.cls`: Official IEEE Transactions v1.8b class definition.
- `fig_pipeline_architecture.pdf` / `.png`: 8-stage quantitative architecture diagram.
- `fig_vol_forecast.pdf` / `.png`: 312-session out-of-sample volatility forecast tracking.
- `fig_equity_curve.pdf` / `.png`: Historical walk-forward backtest equity progression & drawdown profile.
- `fig_regime_performance.pdf` / `.png`: Performance and win rate partitioned by Hidden Markov volatility regime.
- `fig_forward_live_testing.pdf` / `.png`: 4-panel forward live paper testing telemetry (latency, slippage, equity, delta).
- `fig_robustness_validation.pdf` / `.png`: 4-panel institutional robustness audit (Monte Carlo ruin cone, sensitivity matrix, SEBI SPAN margin compliance, and June 2024 election shock stress test).

