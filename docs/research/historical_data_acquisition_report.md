# Historical NIFTY Options Data Acquisition Report

**Scope:** read-only assessment of the current workspace and of feasible data-acquisition routes for genuine historical NIFTY 50 option research.  
**Repository:** `D:\Projects\option-project`  
**Evidence rule:** source code and files are treated as ground truth. Provider claims are included only when supported by the cited public page; otherwise they are marked **UNVERIFIED**.

## Executive summary

No timestamp-aligned historical NIFTY option quote dataset was found in the workspace. The repository defines SQLite schemas and a live snapshot recorder, but no `data/` directory, SQLite database, CSV, Parquet, XLSX, or raw option-market export was present. The only quantitative artifact outside code and dependency manifests is `docs/validation_results_real.json`; it contains synthetic Black-Scholes/VIX proxy observations and cannot serve as historical option ground truth.

The application can record future live snapshots, but that does not reconstruct expired contracts or historical bid/ask quotes. The existing backtest is explicitly an underlying-direction proxy and does not calculate option P&L. Publication-quality mispricing research therefore requires a new, licensed historical dataset with contract identity, timestamped quotes, expiry, strike, option type, underlying spot, and provenance.

The minimum viable route is an end-of-day dataset with expired NIFTY contracts, bid/ask or a documented quote convention, synchronized spot, India VIX, volume, and open interest. The preferred route is timestamped intraday quotes or trades at 5-minute or finer frequency, retained through expiry, with a reproducible export and permission to publish derived results.

## 1. Local inventory and verified availability

### 1.1 Workspace search

The tracked/untracked inventory contains source files, documentation, package manifests, and `.github/copilot-instructions.md`. Git-ignored entries include `.env` and `.venv/`; `.env` was inspected only for variable names and its values were not exposed. No ignored `data/` directory or database was found.

| Artifact | Actual path | Format | Bounds / count | Fields and status |
|---|---|---|---|---|
| Saved validation output | [`docs/validation_results_real.json`](../validation_results_real.json) | JSON | Dates shown in records: 2024-01-01 to 2026-04-29; metrics report 1,674 instances at lines 21771-21790 | Spot/VIX-derived synthetic observations, fair price, synthetic market price, deviation, label, regime, and synthetic next-day outcome. Not quotes. |
| Intended live snapshot database | `data/nifty_live_snapshots.db` | SQLite | Not present locally; first/last timestamp and row count unavailable | Schema is defined in [`option_chain_service.py`](../../backend/services/option_chain_service.py):109-117 and [`record_nifty_snapshots.py`](../../scripts/record_nifty_snapshots.py):32-57. |
| Generic option tick store | Same configured database path | SQLite | Not present locally; row count unavailable | `option_ticks` schema is defined in [`db_service.py`](../../backend/services/db_service.py):23-47. It is a schema and insertion service, not evidence of stored rows. |

### 1.2 Dataset-by-dataset assessment

**Historical option quotes — NOT FOUND / UNVERIFIABLE.** The configured snapshot path is `data/nifty_live_snapshots.db` ([`option_chain_service.py`](../../backend/services/option_chain_service.py):42; [`record_nifty_snapshots.py`](../../scripts/record_nifty_snapshots.py):29), but the file is absent. Consequently, first/last timestamps, record count, missingness percentages, expired-contract retention, and spot/quote timestamp alignment cannot be measured.

**Schema capability — CONFIRMED, contents unavailable.** `option_snapshots` can hold timestamp, spot, expiry, strike, option type, LTP, IV, OI, volume, bid, ask, and Greeks ([`option_chain_service.py`](../../backend/services/option_chain_service.py):109-117). The recorder inserts those fields from a live chain ([`record_nifty_snapshots.py`](../../scripts/record_nifty_snapshots.py):73-126). This is future collection capability, not historical coverage.

**Synthetic seed — CONFIRMED.** If the database is absent or empty, `_seed_initial_snapshot` creates a 14-day, 15%-volatility chain with BSM prices and manufactured bid/ask values ([`option_chain_service.py`](../../backend/services/option_chain_service.py):91-143 and 156-183). Such rows must never be treated as market observations.

**Underlying data — PROVIDER-DEPENDENT, NOT LOCALLY CACHED.** The application requests `^NSEI` through yfinance, applies timeframe windows, converts timestamps to Asia/Kolkata, and retains at most 2,000 candles ([`data_service.py`](../../backend/services/data_service.py):14-76). This is runtime retrieval, not a reproducible local historical export.

**Validation JSON — SYNTHETIC PROXY.** The validator uses NIFTY and India VIX series but generates “market” and fair option prices with Black-Scholes; the source-level evidence is documented in [`critical_findings_verification.md`](./critical_findings_verification.md):2.2. Its dates and 1,674 records must not be reported as historical option quote coverage.

No local dataset has measurable missing-value percentages because no genuine option rows are available. No local option observation can be confirmed as timestamp-aligned with spot, and no expired-contract retention can be confirmed.

## 2. Required research dataset

### 2.1 Canonical observation grain

The canonical primary key should be `(timestamp_utc, underlying, expiry_date, strike, option_type)`. Preserve the original exchange/vendor timestamp and timezone in addition to normalized UTC. A quote snapshot and a trade/tick should not be silently mixed; use an explicit `observation_type`.

### 2.2 Proposed schema

| Field | Requirement | Definition / provenance |
|---|---|---|
| `timestamp_ist` | Mandatory | Original observation timestamp in Asia/Kolkata, including exchange session date. |
| `timestamp_utc` | Mandatory | Normalized UTC timestamp derived from `timestamp_ist`; retain conversion method. |
| `underlying_symbol` | Mandatory | NIFTY underlying identifier and vendor symbol. |
| `spot_price` | Mandatory | Spot/index observation synchronized to the option timestamp, with source and quote type. |
| `option_symbol` | Mandatory | Vendor/exchange contract identifier where available. |
| `expiry_date` | Mandatory | Contract expiry; retain expired contracts. |
| `strike` | Mandatory | Contract strike. |
| `option_type` | Mandatory | CE/PE, normalized from vendor representation. |
| `bid`, `ask` | Strongly mandatory for execution research | Top-of-book quotes; preserve nulls rather than substituting LTP. |
| `ltp` | Mandatory if available | Last traded price and its trade timestamp; do not assume it is contemporaneous with the quote timestamp. |
| `trade_timestamp` | Optional but preferred | Timestamp of the LTP trade. |
| `implied_volatility` | Optional / derived | Vendor IV with provenance, or derived IV from a documented price, rate, dividend, and time convention. |
| `volume`, `open_interest` | Mandatory for liquidity filters | Preserve exchange/vendor definitions and units. |
| `contract_multiplier` | Mandatory for P&L | Historical multiplier if it changed; do not assume a constant. |
| `risk_free_rate` | Mandatory model input | Rate value, tenor, timestamp, and source. |
| `india_vix` | Strongly recommended | Timestamp-aligned India VIX observation and source. |
| `dividend_yield` | Recommended | Assumption or observed input with provenance. |
| `data_source_id` | Mandatory | Provider, file/API version, retrieval date, and license identifier. |
| `observation_type` | Mandatory | Quote, trade, OHLC bar, or vendor snapshot. |
| `quality_flags` | Mandatory | Stale quote, crossed market, zero price, missing side, outlier, and synchronization flags. |

Derived fields should include mid-price, spread, time-to-expiry, moneyness, log-moneyness, and data-quality status. Derived IV must never overwrite vendor IV; store both with separate provenance columns.

## 3. Data acquisition requirements

### 3.1 Coverage

For each timestamp, the extract should include a sufficiently wide strike range around spot, both CE and PE, all listed expiries available at that time, and contracts retained after expiry for auditability. At minimum, include the nearest weekly expiry, the next weekly/monthly expiry, and at least one longer-dated expiry where listed. A publication study should span multiple volatility regimes and market conditions rather than a single recent period.

### 3.2 Frequency

* **Minimum viable:** end-of-day observations with a well-defined close/mid convention.
* **Preferred:** 5-minute synchronized snapshots or trades during the regular Indian session.
* **Best for execution analysis:** tick or quote updates with bid/ask and trade timestamps, resampled only after preserving raw data.

End-of-day data can support cross-sectional pricing tests but is weak for claims about intraday execution, stale quotes, or short-horizon reversion.

### 3.3 External data-source evaluation

| Source | Publicly evidenced capability | Limits / claims not established |
|---|---|---|
| NSE official data pages | Official pages exist for reports and market-data products: [NSE All Reports](https://www.nseindia.com/all-reports), [NSE real-time data subscription](https://www.nseindia.com/market-data/real-time-data-subscription), and [NSE historical data subscription](https://www.nseindia.com/market-data/historical-data-subscription). | The pages were not reliably retrievable during this audit. Exact historical option-chain depth, bid/ask fields, intraday granularity, price, licensing, and academic publication rights are **UNVERIFIED** here and require written confirmation or a successful product specification. |
| NSE India VIX | NSE publishes an India VIX market-data page at [NSE India VIX](https://www.nseindia.com/market-data/india-vix). | Historical downloadable depth, timestamp granularity, licensing, and export format are **UNVERIFIED**. |
| yfinance / Yahoo Finance | Official yfinance documentation exposes `Ticker.option_chain(expiration)` and historical price APIs; see [yfinance documentation](https://ranaroussi.github.io/yfinance/) and [repository](https://github.com/ranaroussi/yfinance). | The documentation does not establish historical timestamped NIFTY option quotes, expired-contract coverage, bid/ask history, or publication rights. The documentation states Yahoo API use is intended for personal use; research licensing must be checked. Not adequate as the assumed source for this study without a verified export test. |
| Global Datafeeds | The vendor page states coverage for NSE/NFO and advertises real-time, delayed, historical, snapshot, exchange-snapshot, end-of-day, option-chain, and Greeks APIs: [Global Datafeeds](https://globaldatafeeds.in/) and [API data types](https://globaldatafeeds.in/global-datafeeds-apis/global-datafeeds-apis/introduction/type-of-data-available/). | Exact NIFTY expired-contract depth, quote-level bid/ask history, timestamp granularity, API retention, price, academic license, and reproducible bulk-export terms are **UNVERIFIED** and require a vendor quote and sample file. |
| TrueData | The public site advertises real-time market-data, option-chain, charting, and workspace products: [TrueData](https://www.truedata.in/). | Historical NIFTY option quote coverage, expired contracts, bid/ask fields, intraday retention, pricing, academic rights, and export/API terms are **UNVERIFIED** from the reviewed public page. |

No provider should be selected solely from a marketing statement. Before purchase, require a sample covering an expired NIFTY contract and verify timestamps, bid/ask, spot synchronization, OI/volume, and field definitions.

## 4. Feasibility assessment

### 4.1 Existing local data

**Not feasible for genuine option mispricing experiments.** The repository has no historical option rows and no local database. Existing code can run proxy validation and live collection, but cannot establish historical quote-level labels or option P&L from the current checkout.

### 4.2 Publicly accessible data

**Partially feasible, not publication-ready by assumption.** Public index/VIX downloads may support a volatility or underlying-only study. Public yfinance option-chain access does not establish the historical, expired-contract, timestamped quote panel required here. Official NSE availability, terms, and historical fields must be verified before relying on them.

### 4.3 Commercial data

**Feasible in principle, subject to sample and license verification.** Global Datafeeds and TrueData publicly advertise relevant products, but the exact historical option panel required for this project remains unverified. A commercial purchase is appropriate only after confirming expired contracts, bid/ask or a defined quote convention, synchronized spot, export reproducibility, and publication rights.

## 5. Estimated acquisition requirements

### 5.1 Minimum viable dataset

* At least 3 years of daily observations, including multiple expiry cycles and high- and low-volatility periods.
* Every listed NIFTY CE/PE contract available at each daily timestamp for the selected expiry set.
* Spot, expiry, strike, option type, LTP or mid, volume, OI, timestamp, and source identifier.
* A documented risk-free-rate series and India VIX history.
* Explicit handling of missing bid/ask and stale LTP.

### 5.2 Ideal dataset

* At least 5 years, preferably including a stressed regime and several contract-calendar changes.
* 5-minute synchronized quote snapshots or better, covering all strikes and expiries, with bid, ask, LTP/trade timestamp, volume, OI, and underlying spot.
* Expired contracts retained, immutable raw files, checksums, schema versioning, and a reproducible extraction manifest.
* Vendor IV retained separately from model-derived IV.
* Contract multiplier, corporate/calendar metadata, risk-free rates, dividend assumptions, and India VIX with aligned timestamps.

The exact number of rows depends on strike universe, expiries, and frequency and must be measured from the provider sample rather than invented. Storage should use partitioned Parquet for immutable raw and normalized data, with SQLite or DuckDB indexes for research queries. Raw vendor files must be retained unchanged.

## 6. Acquisition and validation workflow

1. Obtain written coverage, licensing, and publication terms before acquisition.
2. Request a sample containing at least one expired contract, one weekly expiry, both CE and PE, multiple strikes, and a full trading session.
3. Validate timezone, session boundaries, duplicate keys, monotonic timestamps, crossed markets, zero/negative prices, stale quotes, and missingness by field.
4. Reconcile spot timestamps to option timestamps and record the synchronization tolerance.
5. Recompute mid-price and IV independently; compare with vendor IV without replacing either value.
6. Verify expiry and strike continuity, OI/volume units, contract multiplier, and retention after expiry.
7. Freeze raw files with checksums and create a manifest containing provider, retrieval date, query parameters, schema version, and license.
8. Produce a data-quality report before model fitting; exclude or flag observations transparently.
9. Split experiments chronologically into training, validation, and strictly out-of-sample test periods. Prevent current/future quotes from entering reference statistics.
10. Only after these checks, adapt the application backtest to use historical option observations and realistic bid/ask, multiplier, transaction-cost, and slippage assumptions.

## 7. Final recommendation

Do not use the current validation JSON or the synthetic SQLite seed as empirical option evidence. First procure a vendor sample and select the source that demonstrably provides:

1. expired NIFTY contracts;
2. timestamped option observations with bid/ask or a defensible close/mid convention;
3. synchronized underlying spot, volume, and OI;
4. historical India VIX and rate inputs or compatible sources;
5. immutable export and reproducible access; and
6. explicit academic/publication permission.

The recommended research target is a 5-minute, 5-year panel stored as raw Parquet plus a normalized analytical database, with a daily end-of-day fallback if cost or licensing prevents intraday acquisition. Until that dataset is obtained and validated, conclusions should be limited to the implemented synthetic proxy and underlying-direction backtest, not genuine NIFTY option mispricing or profitability.
