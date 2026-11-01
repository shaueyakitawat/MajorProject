# Critical Findings Verification

**Scope:** source-level, read-only verification of the seven highest-impact findings in `docs/research/repository_audit.md`.  
**Audit date:** 2026-10-31  
**Status meanings:** `CONFIRMED` means directly demonstrated by executable source; `PARTIALLY CONFIRMED` means the capability exists but the stated research property is incomplete or inconsistent; `NOT CONFIRMED` means the inspected source contradicts the claim; `UNVERIFIABLE` means the repository does not contain the data or runtime evidence needed to decide.

## 1. Executive Summary

1. **Historical timestamp-aligned option quotes — UNVERIFIABLE, with strong negative repository evidence.** The repository defines SQLite schemas capable of storing timestamps, LTP, IV, expiry, strike, bid, and ask, and has a live snapshot recorder. However, no `data/` directory or `data/nifty_live_snapshots.db` was present in the inspected repository, and the backtest never reads either snapshot table. Defined schema is not evidence that historical rows exist.
2. **Validation methodology — CONFIRMED as a synthetic proxy.** `RealDataMispricingValidator` downloads NIFTY and India VIX series, but generates both the current “market” option price and model fair price with the same Black-Scholes function. The next-day outcome is also generated from spot/VIX inputs through Black-Scholes. The saved metrics measure reversion of a synthetic volatility proxy, not historical quote-level detection.
3. **Backtesting — CONFIRMED as an underlying-direction proxy, not option P&L.** The signal uses a current quote reused at every historical bar, or a synthetic fair price multiplied by `1.03`; returns are `direction * next underlying return`. The function itself returns `is_option_pnl_backtest: False`.
4. **M-Score consistency — CONFIRMED inconsistent.** The main live pipeline calls `mispricing_service.detect_mispricing`, but separate chain, surface, telemetry, and backtest calculations use different formulas, inputs, and thresholds. The main implementation also has process-global rolling z-score state.
5. **Volatility/regime pipeline — PARTIALLY CONFIRMED.** EGARCH(1,1), one-step forecasting, fallbacks, annualization, and configurable fusion exist. The live pipeline uses daily returns plus optional 5m realized volatility and trains HMM on rolling volatility. The validator and diagnostic runner pass raw returns to the HMM instead, and HMM state/cache behavior is global.
6. **VRP methodology — CONFIRMED as an IV-minus-volatility spread, not a variance risk premium.** The current observation is appended before its reference mean/std are calculated. The reference state is process-global, regime-specific but not instrument-, expiry-, or session-specific.
7. **Reproducibility — PARTIALLY CONFIRMED.** Code and dependency manifests exist for the proxy experiments and live services, but the historical option dataset/database, pinned dependency lock, data snapshots, and exact run environment are absent from the repository. Publication-quality option experiments cannot be reproduced from the current checkout alone.

## 2. Source-Level Verification of Each Finding

### 2.1 Historical option data

**Status: UNVERIFIABLE (schema and recorder confirmed; historical contents not confirmed).**

The option-chain service uses `DB_PATH = .../data/nifty_live_snapshots.db` in `backend/services/option_chain_service.py:42`. Its fallback schema `option_snapshots` includes `timestamp`, `spot_price`, `expiry_date`, `strike`, `option_type`, `ltp`, `iv`, `oi`, `volume`, `bid`, `ask`, and Greeks at `backend/services/option_chain_service.py:109-117`. The loader queries that table at `backend/services/option_chain_service.py:156-173`.

The recorder uses the same database path at `scripts/record_nifty_snapshots.py:29` and creates `option_snapshots` with the same quote fields at `scripts/record_nifty_snapshots.py:32-57`. `record_snapshot` obtains the current chain and inserts one row per available call/put at `scripts/record_nifty_snapshots.py:73-126`. This establishes a mechanism for point-in-time snapshots, not a supplied historical dataset.

There is a second, separate `option_ticks` schema in `backend/services/db_service.py:11-47`, with OHLC, volume, OI, contract identifiers, expiry, and timestamp. It is populated only through `DBService.insert_tick`/`insert_ticks_bulk` at `backend/services/db_service.py:53-87` and queried by `get_aggregated_bars` at `backend/services/db_service.py:89-115`. The inspected backtest does not call `DBService`, `get_aggregated_bars`, `option_snapshots`, or `pipeline_signals`.

The repository root inspection found no `data/` directory and therefore no checked-in `nifty_live_snapshots.db`. Consequently, availability of actual historical rows, coverage, timestamp alignment, and quote quality is not established. The schemas show that bid, ask, LTP, IV, expiry, strike, and timestamps **could** be recorded, but not that they **are** available.

### 2.2 Validation methodology

**Status: CONFIRMED as a synthetic proxy; independent option ground truth is absent.**

`RealDataMispricingValidator.__init__` labels the data source as “NIFTY spot plus India VIX proxy” and the option price source as “Synthetic Black-Scholes prices from VIX proxy” at `validation/daily_mispricing_validator.py:47-57`.

`fetch_market_data` downloads `^NSEI` and `^INDIAVIX` through yfinance at `validation/daily_mispricing_validator.py:68-105`. Missing VIX observations are filled with 15% at `validation/daily_mispricing_validator.py:100`; a complete VIX download failure causes the entire VIX column to be set to 0.15 at `validation/daily_mispricing_validator.py:102-103`.

For each historical day, the validator uses a lookback ending at the current row (`df.iloc[:curr_idx + 1]`) and the last 120 returns at `validation/daily_mispricing_validator.py:130-137`. It computes:

* fair price from current spot, strike, fixed 30-day TTM, risk-free rate, and EGARCH/fused volatility at `validation/daily_mispricing_validator.py:153-161`;
* “real market price” from current spot, the same strike/TTM/rate, and VIX volatility using the same BSM function at `validation/daily_mispricing_validator.py:163-171`;
* a 3% absolute deviation label at `validation/daily_mispricing_validator.py:177-178`;
* next-day “market” and “fair” prices from next-day spot/VIX and the same BSM function at `validation/daily_mispricing_validator.py:181-198`;
* reversion as a reduction in absolute synthetic deviation at `validation/daily_mispricing_validator.py:202-207`.

The validator does not read historical option quotes, bid/ask, option trades, open interest, actual option expiry-specific IV, or an independent outcome label. Its confusion matrix counts “mispriced” synthetic observations against “reverted” synthetic observations at `validation/daily_mispricing_validator.py:225-232`. `compute_metrics` then derives precision, recall, F1, accuracy, MAE, and RMSE from those counts/deviations at `validation/daily_mispricing_validator.py:238-263`.

The saved file reports 1,674 instances and TP/FP/TN/FN of 804/778/72/20 at `docs/validation_results_real.json:21771-21790`. Those metrics measure the validator’s synthetic proxy experiment. They cannot establish historical option mispricing precision, real quote reversion, executable trading performance, or profitability.

### 2.3 Backtesting

**Status: CONFIRMED as an underlying-direction proxy.**

`run_backtest` fetches only OHLCV underlying data through `_fetch_backtest_data` at `backend/services/backtest_service.py:38-64`, with configured yfinance windows at `backend/services/backtest_service.py:25-34`. The only option-chain attempt is a one-time current yfinance chain lookup at `backend/services/backtest_service.py:160-200`. If successful, the current ATM call’s strike, LTP/bid/ask, and current expiry are saved once, and the data quality is explicitly marked `current_chain_quote_reused_across_history` at `backend/services/backtest_service.py:172-183`. If unavailable, the quality is initialized as `synthetic_option_proxy` at `backend/services/backtest_service.py:161-165`.

Inside the walk-forward loop, the model fits on the preceding 60 returns at `backend/services/backtest_service.py:220-233`. The strike is the one current strike or current spot, and the market price is the same current quote for every bar at `backend/services/backtest_service.py:235-240`. If no quote exists, the code computes BSM fair value and sets `mkt_price_i = fp * 1.03` at `backend/services/backtest_service.py:241-252`.

The signal is a 0.6 price-score/0.4 volatility-score combination from `_compute_signal` at `backend/services/backtest_service.py:80-118`. Direction is inferred from the sign of that score at `backend/services/backtest_service.py:264-277`. The realized return is not an option payoff: it is `future_return = (closes[i + 1] - closes[i]) / closes[i]`, followed by `strat_ret = direction * future_return` at `backend/services/backtest_service.py:280-284`.

The result explicitly sets `is_option_pnl_backtest: False` in both insufficient-trade and normal result paths at `backend/services/backtest_service.py:309` and `backend/services/backtest_service.py:336`. No option intrinsic/extrinsic payoff, bid/ask crossing, commissions, slippage, contract multiplier, margin, assignment, expiry, or liquidity cost enters `strategy_returns`.

The rolling training window itself is causal for the underlying return forecast: it ends at `i-1`, while the outcome is `i+1`. The material look-ahead/data-integrity problem is the current option quote and current expiry being reused over historical bars, plus current quote selection based on `closes[-1]` at `backend/services/backtest_service.py:176`, which is not an historical timestamp-aligned contract selection.

A genuine option P&L backtest is **not possible from the currently verified repository contents**. It would become possible only after confirming a populated, timestamp-aligned option dataset with historical bid/ask or executable prices, contract metadata, and a defined quote-to-trade/exit policy. The existing schemas alone are insufficient.

### 2.4 M-Score consistency

**Status: CONFIRMED inconsistent; main live path identified.**

#### Main live implementation

`backend/services/mispricing_service.py:10-17` defines configurable default weights: price 0.50, Vega 0.15, Gamma 0.15, TCI 0.10, and VRP deviation 0.10. `detect_mispricing` is implemented at `backend/services/mispricing_service.py:46-140`.

Its inputs are market price, fair price, Vega, Gamma, TCI, current VRP, expected VRP, and optional weight overrides at `backend/services/mispricing_service.py:46-57`. It normalizes price deviation by multiplying by 20 and VRP deviation by 50 at `backend/services/mispricing_service.py:78-80`, clips normalized Vega/Gamma at `backend/services/mispricing_service.py:84-86`, applies the deviation sign to Greeks at `backend/services/mispricing_service.py:82-89`, and applies a TCI multiplier at `backend/services/mispricing_service.py:91`. Classification is overpriced if deviation exceeds 5% **or** M-Score is at least 1.2, underpriced if deviation is below -5% **or** M-Score is at most -1.2, otherwise fair, at `backend/services/mispricing_service.py:113-118`.

The function appends M-Scores to the process-global `_mscore_window` at `backend/services/mispricing_service.py:18` and `backend/services/mispricing_service.py:25-42`. The resulting z-score is returned but is not used in the classification condition.

`main.py::run_pipeline` calls the actual main implementation at `main.py:629-638`, after obtaining IV/VRP and the regime at `main.py:595-604`. The live path therefore uses `detect_mispricing`, not the other M-Score formulas below.

#### Other implementations

* **Option-chain M-Score:** `backend/services/option_chain_service.py:370-374` uses 0.50 price deviation, 0.30 VRP, and a constant `+0.10`; it uses percentage values divided by 5 and 2, respectively. It classifies with the same 1.2 threshold at `backend/services/option_chain_service.py:374`.
* **Pipeline telemetry M-Score:** `backend/services/pipeline_service.py:101-105` computes a call gap divided by a Vega/TTM expression; the top dislocation is then hard-coded with `mscore: 1.14` at `backend/services/pipeline_service.py:108-115`. The stage description claims `|M| >= 1.0` at `backend/services/pipeline_service.py:260-274`, which is not the main service threshold.
* **Surface M-Score:** `backend/services/surface_service.py:70-77` computes a VRP/T maturity expression only; it is not the composite main-service formula.
* **Backtest score:** `backend/services/backtest_service.py:117-118` uses `0.6 * price_score + 0.4 * vol_score`, with no M-Score service, Greeks, TCI, or VRP-history normalization.

Thus there is no single repository-wide M-Score definition. The main live pipeline uses `mispricing_service.detect_mispricing`; option-chain display, surface display, telemetry, and backtest calculations are separate.

### 2.5 Volatility and regime pipeline

**Status: PARTIALLY CONFIRMED.**

`forecast_volatility` uses `arch_model(percentage_returns, vol="EGARCH", p=1, q=1, dist="normal")` at `backend/services/volatility_service.py:94-99`, fits the full supplied `returns_series`, and requests a one-step forecast at `backend/services/volatility_service.py:100-104`. It converts forecast variance to decimal volatility at `backend/services/volatility_service.py:104-107`. Any fitting/forecast exception falls back to `returns_series.std()` at `backend/services/volatility_service.py:108-110`; nonpositive/nonfinite output is replaced with 0.01 at `backend/services/volatility_service.py:112-114`.

The production pipeline obtains historical candles, computes returns, and requires at least 100 returns at `main.py:309-421` before calling `forecast_volatility` at `main.py:444`. It separately attempts to fetch 5m prices at `main.py:420-444`. The service computes 5m, hourly, and 15m realized volatility at `backend/services/volatility_service.py:48-87`, but only daily and 5m volatility enter the fusion at `backend/services/volatility_service.py:119-123`.

Runtime fusion weights are read once from environment variables with defaults 0.7 daily and 0.3 intraday at `backend/services/volatility_service.py:23-24`; missing intraday data forces 1.0 daily and 0.0 intraday at `backend/services/volatility_service.py:27-34`. The example configuration confirms those defaults at `.env.example:8-9`. The production `main.py` path calls this service at `main.py:444`.

The live pipeline forms its HMM training input as a 60-period rolling standard deviation annualized by `sqrt_252` at `main.py:595-598`, then calls `classify_volatility_regime(vol_forecast, vol_series=rolling_vol_series)` at `main.py:599`. The HMM requires 120 finite samples at `backend/services/regime_service.py:12-27`, fits a four-state diagonal Gaussian HMM with `n_iter=500` and `random_state=42` at `backend/services/regime_service.py:31-38`, and orders labels by fitted means at `backend/services/regime_service.py:41-47`.

The validator and diagnostic runner do not use that same HMM input. The validator passes raw return values via `classify_volatility_regime(returns.values)` at `validation/daily_mispricing_validator.py:140-142`; `run_validation.py` does the same at `run_validation.py:102`. In `regime_service.py`, raw returns are accepted as generic observations, so the resulting model is not trained on the same volatility feature described by the live pipeline. The global `_HMM_MODEL`, `_HMM_STATE_ORDER`, and `_HMM_STATE_COUNT` at `backend/services/regime_service.py:15-17` also mean the fitted model persists across calls and is replaced only when state count changes, not when symbol/session/training data changes.

Within the validator’s current-row construction, the lookback ends at `curr_idx` and does not include future rows (`validation/daily_mispricing_validator.py:130-137`). The main confirmed issue is therefore feature/path inconsistency and global cache contamination, not direct future-row leakage in that specific lookback.

### 2.6 VRP methodology

**Status: CONFIRMED as a volatility spread with contaminated reference statistics.**

`compute_vrp` defines `vrp = iv - final_vol` at `backend/services/vrp_service.py:19-35`. It appends the current observation to both the overall and regime-specific global deques before calculating the reference statistics at `backend/services/vrp_service.py:36-45`. It then sets `expected_vrp = mean(values)` and `vrp_std = std(values)` at `backend/services/vrp_service.py:47-62`.

Therefore the current observation is included in its own expected mean and standard deviation. There is no lagged-only reference, expanding-window warm-up policy, or minimum-history requirement beyond the deque being nonempty. The state is initialized once at import in `_vrp_by_regime` and `_vrp_window` at `backend/services/vrp_service.py:9-18`; no reset, persistence, symbol key, expiry key, contract key, or session key exists.

The main pipeline calls `compute_vrp(iv, vol_forecast, regime_label=regime)` at `main.py:604`. The formula uses IV and annualized physical volatility, not squared IV minus squared forecast variance. It is therefore a volatility-level spread, despite the service name “VRP”.

### 2.7 Reproducibility

**Status: PARTIALLY CONFIRMED.**

The proxy validator can be executed from repository source using `validation/daily_mispricing_validator.py:299-322`, subject to live yfinance availability and the installed Python dependencies. `run_validation.py` invokes the same validator and live services at `run_validation.py:80-169`. The dependency names are listed in `requirements.txt:1-15`, but no lockfile or exact Python/package version manifest is present at the repository root.

The saved result file exists at `docs/validation_results_real.json`, and its metric block is at `docs/validation_results_real.json:21771-21790`. However, the validator downloads data dynamically and does not store the downloaded NIFTY/VIX input frame. The repository has no checked-in historical option database under `data/`; the snapshot recorder is an acquisition script, not a bundled dataset.

The backtest can be invoked through the backend endpoint wired to `run_backtest`, but its results depend on live yfinance data and, if available, a current option chain. Its source explicitly labels the output as not option P&L at `backend/services/backtest_service.py:309` and `336`.

The exact `.env` runtime state is not a reproducible research artifact. The example configuration supplies defaults for fusion and VRP at `.env.example:8-12`, but other runtime values can come from process environment or local environment files. No frozen data snapshot, model parameter export, or experiment manifest is present.

## 3. Evidence: File Paths, Functions, and Line Numbers

| Finding | Exact evidence |
|---|---|
| Option DB path and schema | `backend/services/option_chain_service.py:42`, `_seed_initial_snapshot` at `:109-149`, `_load_chain_from_db` at `:156-190` |
| Snapshot acquisition | `scripts/record_nifty_snapshots.py:29-61`, `record_snapshot` at `:73-126` |
| Separate tick schema | `backend/services/db_service.py:11-47`, `insert_tick`/`insert_ticks_bulk` at `:53-87`, `get_aggregated_bars` at `:89-115` |
| Validator data inputs | `validation/daily_mispricing_validator.py:68-105`, `validate_real_data` at `:110-232` |
| Validator synthetic prices | `validation/daily_mispricing_validator.py:153-198` |
| Validator metrics | `validation/daily_mispricing_validator.py:238-263`; saved output `docs/validation_results_real.json:21771-21790` |
| Backtest data and quote reuse | `backend/services/backtest_service.py:38-64`, `run_backtest` at `:135-208`, loop at `:220-284` |
| Backtest proxy declaration | `backend/services/backtest_service.py:204-205`, result fields at `:303-344` |
| Main M-Score | `backend/services/mispricing_service.py:10-17`, `_z_score` at `:25-42`, `detect_mispricing` at `:46-140` |
| Live pipeline call site | `main.py:595-638`, `run_pipeline` beginning at `main.py:309` |
| Other M-Scores | `backend/services/option_chain_service.py:350-414`, `backend/services/pipeline_service.py:101-115`, `backend/services/surface_service.py:70-77`, `backend/services/backtest_service.py:117-118` |
| EGARCH/fusion | `backend/services/volatility_service.py:23-24`, `:89-140`; live call `main.py:444` |
| HMM | `backend/services/regime_service.py:12-91`; live input `main.py:595-599`; validator input `validation/daily_mispricing_validator.py:140-142` |
| VRP | `backend/services/vrp_service.py:7-71`; live call `main.py:604` |

## 4. Confirmed Issues

1. **No verified historical option dataset is present.** The repository contains schemas and a recorder, but no verified database rows.
2. **The validator uses synthetic option construction for both sides of the comparison.**
3. **The validator’s positive labels are next-day reductions in synthetic BSM deviation, not independent market outcomes.**
4. **The backtest is not an option P&L backtest and explicitly says so.**
5. **The backtest reuses a current quote/current expiry across historical bars or creates a fixed 3% synthetic premium.**
6. **The main M-Score is duplicated by incompatible chain, surface, telemetry, and backtest formulas.**
7. **The main M-Score z-score is stateful and is not the classification gate.**
8. **Runtime fusion defaults are 70/30 daily/intraday; other telemetry claims 35/65.**
9. **Live HMM training uses rolling volatility, while validator/diagnostic calls pass raw returns.**
10. **HMM, M-Score, and VRP state are process-global and not keyed by instrument/session.**
11. **VRP reference mean/std include the current observation.**
12. **The implemented VRP is `IV - volatility`, not `IV² - forecast variance`.**

## 5. Audit Findings That Need Correction

The previous audit is directionally correct, but the following wording should be made more precise in any research record:

* “Historical option data exists” should be replaced with “historical option storage schemas and a live snapshot recorder exist; actual historical rows are unverified and no database is present in the checkout.”
* “Real-data validation” should be qualified as “real NIFTY/VIX input with synthetic BSM option-price proxy.”
* “Backtesting” should be called “underlying-direction proxy backtest” unless a separate timestamp-aligned option-P&L engine is added.
* “VRP” should be called “IV-minus-forecast-volatility spread” unless the research definition is intentionally changed to a variance-level measure.
* “M-Score” should be qualified by implementation path because the chain, surface, telemetry, backtest, and main live calculations are not equivalent.
* “HMM regime classification” should state which feature is used: rolling annualized volatility in the live pipeline versus raw returns in the validator/diagnostic path.
* Saved validation metrics should not be described as quote-level precision, recall, accuracy, MAE/RMSE of market prices, or profitability.

## 6. Data Availability and Reproducibility

### Available in the repository

* Source code for live yfinance NIFTY/VIX ingestion.
* Source code for live NSE/pnsea option-chain retrieval.
* SQLite schema definitions for `option_snapshots`, `pipeline_signals`, `option_ticks`, and paper trades.
* Snapshot-recording and export scripts.
* The saved synthetic-proxy result artifact `docs/validation_results_real.json`.
* Python dependency names in `requirements.txt`.
* Frontend/backend smoke-test files and the validation entry points.

### Not verified or absent

* A populated `data/nifty_live_snapshots.db`.
* Any checked-in historical option quote rows.
* A historical option dataset with timestamp-aligned bid, ask, LTP, IV, expiry, strike, OI, and volume.
* A frozen NIFTY/VIX input dataset for the saved validation metrics.
* A dependency lockfile and exact interpreter/package build record.
* An experiment manifest recording data retrieval timestamps, timezone policy, runtime environment, and configuration values.
* A genuine option-P&L backtest using the defined schemas.

### Minimum data required for publication-quality experiments

At minimum, each quote observation must include:

* UTC/IST-normalized timestamp and session date;
* underlying spot or futures reference at the same timestamp;
* option symbol, expiry, strike, call/put type;
* bid, ask, last trade price, and quote/trade status;
* IV provenance and solver convention;
* volume, open interest, and contract multiplier;
* transaction-cost and slippage assumptions;
* a survivorship-complete contract universe, including expired and delisted observations where relevant.

The research dataset must also retain the raw source files/API responses, retrieval timestamps, schema version, and a deterministic train/validation/test split.

## 7. Experiments Possible With Existing Data

These are possible without claiming historical option-market performance:

1. **EGARCH forecast diagnostics** on downloaded NIFTY returns, including rolling one-step volatility forecasts and forecast-error comparisons against realized underlying volatility.
2. **HMM feature sensitivity** comparing the live rolling-volatility input against the validator’s raw-return input, with state ordering and transition diagnostics.
3. **Fusion ablations** comparing daily-only, intraday-only, and the configured 70/30 fusion on underlying realized-volatility forecasting.
4. **BSM/IV numerical tests** using synthetic prices generated under known inputs; these validate numerical behavior, not market accuracy.
5. **Proxy-validator replication** if the data retrieval date and provider response are preserved; the result remains a synthetic proxy.
6. **Code-path consistency tests** that compare the main M-Score with chain/surface/telemetry formulas on controlled inputs.
7. **State contamination tests** demonstrating how sequential requests change M-Score/VRP outputs because of global deques.

## 8. Experiments Requiring Additional Data

The following cannot be responsibly reported as empirical market results from the current checkout:

1. Historical option quote-level mispricing precision/recall.
2. Next-day option-price reversion using actual option prices.
3. Option strategy P&L, Sharpe, drawdown, hit rate, or profitability after costs.
4. Transaction-cost, bid-ask, liquidity, margin, and market-impact analysis.
5. Cross-sectional surface mispricing and term-structure studies using historical contracts.
6. Out-of-sample validation across expired contracts and multiple market regimes.
7. Robust VRP forecasting or regime-conditioned VRP estimation using historical IV and realized variance.
8. Economic significance testing against buy-and-hold, BSM, constant-volatility, realized-volatility, and standard option-pricing baselines.

## 9. Recommended Research Decisions

Before writing the research methodology, decide:

1. **What is the target estimand?** Statistical price deviation, IV-versus-realized-volatility spread, variance risk premium, option-price reversion, or executable trading profitability are different targets.
2. **Which data source is authoritative?** Obtain and freeze timestamp-aligned historical option quotes, or explicitly limit the study to underlying/VIX proxy experiments.
3. **Which single M-Score and threshold definition is the research model?** Remove or quarantine incompatible display, surface, chain, and backtest formulas from empirical claims.
4. **What is the leakage-safe evaluation design?** Define walk-forward training, quote selection, expiry/strike handling, costs, liquidity, and out-of-sample periods before computing metrics.
5. **What reproducibility package will be archived?** Preserve raw data, database snapshot, environment lock, configuration, code revision, run manifest, and generated outputs.

### Five decisions that must be made first

1. Choose proxy research versus genuine historical option research.
2. Acquire and freeze timestamp-aligned option data if genuine option research is required.
3. Select and formalize one M-Score/VRP definition.
4. Design and implement a true option-P&L walk-forward evaluation with costs.
5. Freeze the complete data, environment, configuration, and experiment manifest.
