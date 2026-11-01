# NIFTY 50 Daily Index Data Validation Report

## Source and provenance

- Source: Yahoo Finance chart API, symbol `^NSEI`.
- URL: `https://query1.finance.yahoo.com/v8/finance/chart/%5ENSEI?period1=1719792000&period2=1767225600&interval=1d&events=history&includeAdjustedClose=true`
- Raw response: `data\research\raw\nifty50_yahoo_chart.json`
- Raw SHA-256: `14c0616f4644e2a566716496ddbc0b89d3f7eda4c42d27ca448e464cff146f0b`
- Official alternative: [NIFTY Indices historical data](https://www.niftyindices.com/reports/historical-data).
- This dataset is third-party data; licensing and academic redistribution rights are not established by this acquisition.

## Coverage and alignment

- Options distinct trading dates: **375** (2024-07-01 to 2025-12-31)
- Index observations: **375** (2024-07-01 to 2025-12-31)
- Missing dates relative to options: **0**
- Missing date list: `none`

## Validation

- Duplicate dates: **0**
- Invalid OHLC/non-positive records: **0**
- Null/empty fields: `{"trade_date": 0, "open": 0, "high": 0, "low": 0, "close": 0, "source": 0}`

No prices were interpolated, synthesized, or filled.
