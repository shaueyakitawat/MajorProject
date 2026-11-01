# Empirical Experiment Data Quality

- Option sample rows before BSM expansion: 190539
- Settlement-zero audit rows: 164
- Missing spot observations after date join: 0
- Positive-volume settlement-zero records were retained in `data\research\option_valuation_zero_settlement_audit.csv`.
- Records without a finite EGARCH forecast were retained in `data\research\option_valuation_egarch_unavailable.csv` and were not assigned a synthetic BSM price.
- No bid, ask, intraday quote, implied volatility, synthetic price, or interpolated index value was created.
- Historical risk-free rates were unavailable; rates (0.06, 0.07) are sensitivity assumptions, not observed historical rates.
- Yahoo Finance is a third-party index source; NSE options are official bhavcopy data. Licensing and redistribution terms remain a limitation.
- Failed model fits are listed in `data/research/experiment_metrics.json`.
