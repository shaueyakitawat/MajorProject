# Phase 4 Research Backtest Data Limitations

- Options are daily bhavcopy records; intraday execution is unsupported.
- No bid, ask, spread, IV, or order-book data exists.
- Historical lot-size multipliers are unavailable, so no rupee P&L is reported.
- Option CLOSE is a daily last-traded reference; OPEN and OHLC execution are not guaranteed fills.
- Zero-volume records are excluded from execution, while source data is preserved.
- Settlement-zero anomalies remain in the source dataset and are not used as valid execution prices.
- The index source is Yahoo Finance, a third-party source with unresolved redistribution terms.
- Daily bars cannot establish the intraday sequence when stop and target are both crossed; stop-first is conservative.
- Short sample length limits statistical power and generalization.
