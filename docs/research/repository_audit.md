# Repository Audit: NIFTY 50 Options Mispricing Engine

**Audit scope:** read-only inspection of repository-owned source, documentation, validation artifacts, configuration, and scripts.  
**Audit date:** 2026-10-31  
**Ground truth rule:** classifications below are based on executable code and saved artifacts, not documentation claims.

## 1. Executive assessment

The repository contains a FastAPI backend, a React/Vite terminal, live-data adapters, SQLite snapshot/paper-trade persistence, a model pipeline, a proxy validator, and a walk-forward underlying-price backtest. The main quantitative services are implemented, but they are not one uniformly connected research system:

* `main.py::run_pipeline` is the primary live analytics path. It fetches historical NIFTY candles, forecasts volatility, obtains an option chain, computes BSM fair value and IV, conditions VRP on the regime, computes an M-Score, and generates a strategy recommendation.
* `backend/services/pipeline_service.py::get_pipeline_execution_trace` is primarily presentation telemetry. Its volatility, regime, M-Score, trade-count, P&L, and risk values are hard-coded examples rather than calls to the model services.
* `validation/daily_mispricing_validator.py::RealDataMispricingValidator` uses real NIFTY and India VIX time series but **synthetic Black-Scholes option prices**, not historical option quotes. Its metrics therefore do not establish quote-level mispricing accuracy or profitability.
* `backend/services/backtest_service.py::run_backtest` is explicitly marked in code as an underlying-direction proxy. It reuses one current option quote across historical bars when available, or manufactures a price at 3% over contemporaneous model fair value.
* Paper-trade persistence and simulated execution exist, but there is no broker order-routing implementation in the inspected repository.

## 2. Directory and architecture inventory

### Backend

* `main.py` — FastAPI application, request validation, pipeline orchestration, REST endpoints, response logging, and paper-trade/backtest endpoint wiring.
* `backend/services/data_service.py` — yfinance OHLCV retrieval, symbol mapping (`NIFTY` to `^NSEI`), timeframe windows, timezone normalization, and log returns.
* `backend/services/volatility_service.py` — EGARCH(1,1) fit, annualization, intraday realized volatility, and weighted fusion.
* `backend/services/regime_service.py` — Gaussian HMM fit, volatility-ordered state labels, posterior classification, and module-level model cache.
* `backend/services/pricing_service.py` — continuous-dividend Black-Scholes-Merton prices, Delta/Gamma/Theta/Vega, and expiry TTM.
* `backend/services/implied_volatility_service.py` — scalar Brent root solve with arbitrage-boundary fallbacks.
* `backend/services/vrp_service.py` — IV minus fused/model volatility and rolling regime-conditioned mean/std.
* `backend/services/mispricing_service.py` — composite M-Score, stateful rolling z-score, and under/fair/over classification.
* `backend/services/option_chain_service.py` — yfinance spot, NSE/pnsea option chain, SQLite snapshot fallback, IV recomputation, model fair prices, Greeks, and chain shaping.
* `backend/services/option_chain_filters.py` — OI, volume, and bid-ask spread liquidity predicate.
* `backend/services/backtest_service.py` — rolling EGARCH and signal backtest.
* `backend/services/trade_service.py` — SQLite paper-trade overview, close, and insert operations.
* `scripts/live_paper_trader.py` — larger live paper-trading loop with risk limits, candidate scans, position state, and SQLite ledger.
* `backend/services/strategy_service.py` — structured long-vol/short-vol/no-trade recommendation.
* `backend/services/risk_service.py`, `surface_service.py`, `model_registry_service.py`, and `db_service.py` — portfolio reporting, surface/registry metadata, and generic tick storage.

### Frontend and validation

* `frontend/src/` — React workspaces and API/store clients for overview, options, volatility, mispricing, backtesting, paper trading, risk, and model registry screens.
* `frontend/test_quant_terminal.mjs` and `frontend/test_full_quant_system.mjs` — frontend/API smoke-style tests.
* `validation/daily_mispricing_validator.py` — real-index/VIX proxy experiment.
* `run_validation.py` — diagnostic runner that invokes live feeds and the proxy validator.
* `scripts/record_nifty_snapshots.py` — periodic option-chain snapshot recorder.

No repository-owned CSV, Parquet, NumPy, or historical option dataset was found. The only checked-in quantitative result artifact is `docs/validation_results_real.json`; the SQLite database is referenced by code under `data/nifty_live_snapshots.db` but was not present in the inspected top-level file inventory.

## 3. Actual end-to-end data flow

### 3.1 Live analytics path (`main.py::run_pipeline`)

1. `backend/services/data_service.py::fetch_nifty_data` calls `yfinance.download` for `^NSEI`, using timeframe-specific windows (for example 10 years daily, 60 days for 5m/15m). It flattens columns, drops empty rows, caps at `TARGET_CANDLES = 2000`, converts timestamps to Asia/Kolkata, and returns OHLCV records.
2. `compute_log_returns` adds `log_return = log(Close / Close.shift(1))`.
3. `run_pipeline` requires at least 100 returns, then calls `forecast_volatility(returns_series, price_series_5min=intraday_prices)`.
4. `forecast_volatility` fits EGARCH to percentage returns, annualizes the one-step volatility, computes 5m/15m/hourly realized volatility, and fuses daily and 5m values.
5. The pipeline obtains the spot and ATM option through `get_spot_price`, `fetch_option_chain`, and `get_atm_option`. The preferred chain source is NSE via `pnsea`; the fallback is SQLite snapshots. If all live/DB chain access fails, `run_pipeline` switches to a synthetic fair-price path.
6. Fair value is computed with `black_scholes_price`. The pipeline then solves IV from the market price, computes IV spread and `compute_vrp`, and uses the regime label to select the rolling VRP history.
7. `detect_mispricing` combines normalized price deviation, VRP deviation, Vega, Gamma, and TCI into `m_score`; its stateful z-score is appended to a process-global deque.
8. `generate_strategy` converts the signal/volatility edge into long-vol, short-vol, or no-trade output. The result is exposed through REST endpoints such as `/forecast-vol`, `/fair-price`, and the mispricing-related routes in `main.py`.

### 3.2 Option-chain path

`backend/services/option_chain_service.py::get_full_chain` first checks a five-second in-memory cache, then calls `_fetch_chain_from_pnsea`. The NSE path:

* reads live spot, expiry, LTP, published IV, OI, volume, bid, and ask;
* recomputes IV from LTP using the local BSM solver where the result is in the accepted range;
* uses a fixed `model_vol = 0.135` for chain fair prices;
* calculates deviations, a separate chain-local M-Score, VRP, and BSM Greeks;
* returns a strike-centered chain.

If pnsea fails, `_load_chain_from_db` reads `data/nifty_live_snapshots.db`. If the database does not exist, `_seed_initial_snapshot` creates a synthetic 14-day, 15%-volatility chain. This directly contradicts the module header's claim that all synthetic/mock fallbacks were removed. The main live pipeline also has an additional synthetic fallback when the chain call raises.

### 3.3 Diagnostic pipeline trace

`backend/services/pipeline_service.py::get_pipeline_execution_trace` does not follow the above data flow. It calls only `get_spot_price` and `fetch_option_chain` at the beginning, then assigns constants such as `egarch_daily = 0.1290`, `rv_5m = 0.1721`, `regime = "EXTREME_VOL"`, `regime_confidence = 0.89`, `active_mispricings_count = 8`, and `today_net_pnl = 7590.16`. It is therefore a UI/status fixture, not evidence that the eight described stages executed.

## 4. Implemented mathematical models

### 4.1 EGARCH volatility forecasting — **IMPLEMENTED, with fallback and scale caveats**

`backend/services/volatility_service.py::forecast_volatility` and `backend/services/backtest_service.py::_egarch_forecast` call `arch.arch_model(..., vol="EGARCH", p=1, q=1, dist="normal")`, fit a one-step forecast, and convert percentage-return standard deviation back to decimal form. The production service annualizes the result through `apply_dynamic_annualization`; the backtest applies the same annualization after its rolling forecast.

Important caveats:

* Any fit exception falls back to the sample standard deviation; the production service then applies a 1% minimum.
* The default `main.py` daily path uses daily data, but intraday realized volatility is optionally fetched separately.
* No calibrated parameter set from the documentation is loaded. Parameters are re-estimated at runtime.

### 4.2 HMM regime classification — **IMPLEMENTED, but not validated as documented**

`backend/services/regime_service.py::_fit_hmm` fits `hmmlearn.hmm.GaussianHMM` with 3 or 4 diagonal-covariance states and `random_state=42`. State labels are assigned by sorting fitted means, not by fixed state IDs. `classify_volatility_regime` uses posterior probabilities for the supplied current annualized volatility and caches one model globally per state count.

The production pipeline trains on a rolling standard-deviation series. `run_validation.py` and the proxy validator call `classify_volatility_regime(returns.values)`; this passes raw returns rather than a historical volatility series despite the function's volatility-oriented API. The saved JSON uses numeric state IDs, not the documented semantic labels.

### 4.3 Volatility fusion — **IMPLEMENTED, with inconsistent documented weights**

`forecast_volatility` fuses annualized EGARCH daily volatility and 5m realized volatility using environment defaults `0.7/0.3` (`VOL_FUSION_DAILY_WEIGHT` and `VOL_FUSION_INTRADAY_WEIGHT`). Missing intraday data normalizes to 100% daily.

Contradictions:

* `pipeline_service.py` hard-codes `0.65 * rv_5m + 0.35 * egarch_daily`.
* Its UI output says “65% 5m RV + 35% EGARCH Daily”.
* `.env.example` and `volatility_service.py` default to 70% daily and 30% intraday.
* The 15m/hourly values are used for TCI only; they are not included in the fused volatility.

### 4.4 VRP estimation — **IMPLEMENTED, but stateful and not a variance premium**

`backend/services/vrp_service.py::compute_vrp` calculates `vrp = iv - final_vol`, then stores observations in global 60-observation overall and regime-specific deques. It returns the current value, mean expected VRP, and standard deviation.

This is a volatility-level spread, not a variance-level risk premium. The expected value is contaminated by the current observation because the function appends before computing the mean. State is process-global and is not persisted or reset by date, symbol, expiry, or contract.

### 4.5 Option pricing and Greeks — **IMPLEMENTED**

`backend/services/pricing_service.py::black_scholes_price` implements European BSM with continuous dividend yield, including calls and puts. `calculate_greeks` returns Delta, Gamma, Theta (per day), and Vega (per 1% volatility change). `calculate_ttm_years` uses 15:30 expiry time and floors TTM at 15 minutes.

`calculate_implied_volatility` uses `scipy.optimize.brentq` over a fixed volatility interval, with intrinsic and upper-bound fallbacks. Documentation claims a vectorized Brent-Decker/Newton implementation, Brenner-Subrahmanyam seeding, fewer than five iterations, and Rho; those features are not present in this service.

### 4.6 M-Score — **IMPLEMENTED in the main service; duplicated/inconsistent in chain and telemetry paths**

`backend/services/mispricing_service.py::detect_mispricing` uses default weights:

* price deviation 0.50;
* Vega 0.15;
* Gamma 0.15;
* TCI 0.10;
* VRP deviation 0.10.

Price deviation is multiplied by 20, VRP deviation by 50, Vega and Gamma are clipped after unit scaling, and TCI acts as a multiplier. A process-global rolling z-score is maintained, but the z-score does not participate in the classification threshold.

`option_chain_service.py::_fetch_chain_from_pnsea` calculates a different chain M-Score using price deviation, VRP, and a constant `+0.10`; `pipeline_service.py` calculates a third illustrative M-Score. The documentation formula using only deviation, VRP, and regime weights is not the formula in the main service.

### 4.7 Mispricing detection — **IMPLEMENTED, but threshold semantics differ**

`detect_mispricing` classifies as overpriced when deviation is above 5% or M-Score is at least 1.2, underpriced below -5% or at most -1.2, otherwise fair. Invalid prices return a fair-shaped zero result.

The validator uses a separate 3% absolute-deviation rule and does not call `detect_mispricing`; it only compares synthetic BSM prices. Documentation claims “3% AND Z-score >= 1.0” plus liquidity filtering, but the production classifier uses OR logic and does not require z-score or `is_leg_liquid`.

## 5. Backtesting, validation, and trade execution

### 5.1 Walk-forward backtest — **PARTIAL / PROXY**

`backend/services/backtest_service.py::run_backtest` fetches yfinance OHLCV data for 1m/5m/15m/1d periods, fits EGARCH on a rolling 60-observation window, computes a BSM fair price and IV, and takes the sign of a combined price/volatility score. The return is `direction * next_underlying_return`.

It is not option P&L:

* the code returns `is_option_pnl_backtest: False`;
* one current option-chain quote is reused across all historical bars when available;
* otherwise the market price is synthesized as fair price times 1.03;
* expiry and strike are not historically timestamp-aligned;
* transaction costs, bid-ask execution, option payoff, contract multiplier, and margin are absent from the returned strategy return.

Reported Sharpe, t-statistic, hit rate, and trade log therefore describe an underlying-direction proxy.

### 5.2 Proxy validator — **IMPLEMENTED AS A PROXY, NOT HISTORICAL OPTION VALIDATION**

`RealDataMispricingValidator` downloads `^NSEI` and `^INDIAVIX` daily data, fits the volatility service, and evaluates three ATM-near strikes. Both “fair” and “market” option prices are generated by the same BSM function, using EGARCH volatility versus VIX. The next-day “reversion” is also generated from next-day spot and VIX through BSM.

The checked-in `docs/validation_results_real.json` reports 1,674 instances, precision 0.5082, recall 0.9757, F1 0.6683, accuracy 0.5233, MAE 66.4948%, RMSE 222.4994%, and TP/FP/TN/FN of 804/778/72/20. These are reproducible only relative to the data download and runtime code; they are not historical option quote metrics. The JSON metadata says “NIFTY 50 Real Market Data” and omits the synthetic option-price disclaimer present in the current validator source.

### 5.3 Snapshot storage — **IMPLEMENTED, data availability UNVERIFIED**

`scripts/record_nifty_snapshots.py` creates SQLite tables `option_snapshots` and `pipeline_signals`, and records live chain fields, IV, liquidity fields, Greeks, model fair values/signals only indirectly through the chain payload. `backend/services/option_chain_service.py` reads `option_snapshots`. `backend/services/db_service.py` separately defines an `option_ticks` schema and resampling API; this is not the same schema used by the option-chain fallback.

No checked-in database was found during this audit, so the completeness, timestamp coverage, and contents of the referenced snapshot database are UNVERIFIED.

### 5.4 Paper trade execution — **IMPLEMENTED as paper persistence; live brokerage UNVERIFIED/PLANNED**

`backend/services/trade_service.py::execute_trade_in_db` inserts an OPEN trade into SQLite, and `close_trade_in_db` computes gross P&L, a simple friction estimate, and updates the row. `scripts/live_paper_trader.py::LiveQuantPaperTrader` contains a longer-running paper trader with position/risk controls, stale-chain controls, margin estimates, stop/target handling, and SQLite ledger state.

The word “execution” means local paper-trade state mutation. No broker API order submission, exchange acknowledgement, fill reconciliation, or live execution audit trail was found.

## 6. Dataset and schema inventory

| Asset | Schema / source | Role | Status |
|---|---|---|---|
| NIFTY index candles | yfinance `^NSEI`; OHLCV plus `Date`/`log_return` | EGARCH, realized volatility, proxy validation, direction backtest | Implemented live retrieval; historical reproducibility depends on provider |
| India VIX | yfinance `^INDIAVIX`; `Date`, `VIX` decimal | Proxy market IV baseline | Implemented retrieval; missing values filled with 15% |
| NSE option chain | pnsea DataFrame fields for strike, CE/PE LTP, IV, OI, volume, bid/ask | Live chain, IV, Greeks, fair value | Implemented retrieval; external availability unverified |
| `option_snapshots` SQLite table | timestamp, symbol, spot, expiry, strike, option type, LTP, IV, OI, volume, bid, ask, Greeks | Chain fallback and snapshot recording | Schema implemented; actual DB not found in audit inventory |
| `pipeline_signals` SQLite table | timestamp, spot, strike, type, market/fair price, deviation, flag, regime, EGARCH, VRP, z-score | Intended signal history | Schema implemented; no checked-in rows verified |
| `option_ticks` SQLite table | instrument, symbol, strike, type, expiry, timestamp, OHLC, volume, OI | Generic raw tick/resampling layer | Schema/API implemented; connection to main option-chain path not demonstrated |
| `validation_results_real.json` | metadata, daily result records, metrics, confusion matrix | Saved proxy experiment output | Present and internally consistent with its recorded counts |

## 7. External sources and dependencies

### Data and services

* Yahoo Finance through `yfinance` for `^NSEI` and `^INDIAVIX`, including historical OHLCV and current spot.
* NSE through `pnsea` for option-chain data, with retries and session reset.
* Local SQLite for snapshots, ticks, and paper trades.
* FastAPI/Uvicorn REST service and React/Vite frontend.

### Quantitative/runtime dependencies

`requirements.txt` includes NumPy, pandas, SciPy, `arch`, `hmmlearn`, yfinance, statsmodels, matplotlib, FastAPI, Uvicorn, python-dateutil, py_vollib, pytz, requests, and pnsea. The inspected production IV service uses SciPy rather than py_vollib. The frontend uses React, TypeScript, Vite, Zustand, ECharts, lightweight-charts, and Lucide.

## 8. Feature classification

| Feature | Classification | Evidence and qualification |
|---|---|---|
| NIFTY historical ingestion and log returns | **IMPLEMENTED** | `data_service.py::fetch_nifty_data`, `compute_log_returns` |
| Live spot retrieval | **IMPLEMENTED** | `option_chain_service.py::get_spot_price`; yfinance/DB/reference fallback |
| NSE option-chain ingestion | **IMPLEMENTED** | `option_chain_service.py::_fetch_chain_from_pnsea`; external feed availability remains operationally unverified |
| SQLite chain snapshots | **IMPLEMENTED / UNVERIFIED DATA** | Recorder and schema exist; checked-in database not found |
| EGARCH(1,1) forecast | **IMPLEMENTED** | `volatility_service.py::forecast_volatility`; fallback to sample volatility |
| Intraday realized volatility | **IMPLEMENTED** | 5m, 15m, hourly helpers |
| Volatility fusion | **IMPLEMENTED** | Runtime service uses configurable 70/30 defaults; telemetry uses conflicting hard-coded 65/35 |
| HMM regime classification | **IMPLEMENTED** | `regime_service.py`; validation input and scientific calibration are weak/unverified |
| VRP estimate | **IMPLEMENTED** | `vrp_service.py`; volatility spread, not variance premium; stateful process memory |
| BSM prices and four Greeks | **IMPLEMENTED** | `pricing_service.py` |
| Implied volatility solver | **IMPLEMENTED** | Brent solve and boundary fallbacks; documented algorithm claims are inaccurate |
| Main M-Score | **IMPLEMENTED** | `mispricing_service.py::detect_mispricing` |
| Chain M-Score | **PARTIAL / INCONSISTENT** | Separate hard-coded formula in `option_chain_service.py` |
| Mispricing classification | **IMPLEMENTED / INCONSISTENT** | Main classifier uses 5%/1.2 OR logic; validator/docs use different rules |
| Liquidity filtering | **IMPLEMENTED IN ISOLATION** | `option_chain_filters.py::is_leg_liquid`; not proven to gate every signal |
| Strategy recommendation | **IMPLEMENTED** | `strategy_service.py::generate_strategy` |
| Walk-forward backtest | **PARTIAL** | Out-of-sample loop exists, but it is an underlying-direction proxy |
| Historical option P&L backtest | **PLANNED / NOT IMPLEMENTED** | Explicitly false in backtest result; no timestamp-aligned quote history |
| Proxy validation experiment | **IMPLEMENTED AS PROXY** | Real index/VIX inputs; synthetic option prices |
| Live paper trading | **IMPLEMENTED** | Local SQLite paper ledger and risk controls |
| Broker/exchange execution | **PLANNED / UNVERIFIED** | No broker order API or fill reconciliation found |
| Reproducible research dataset | **UNVERIFIED** | No checked-in historical option dataset or DB |
| Publication-grade empirical claims | **NOT SUPPORTED BY CURRENT EVIDENCE** | Results are proxy metrics and documentation overstates their meaning |

## 9. Contradictions and investigation priorities

1. **Synthetic fallback versus “100% real” claims:** `option_chain_service.py::_seed_initial_snapshot` creates BSM prices at 15% volatility; `main.py::run_pipeline` also creates a synthetic market price after live-chain failure. This conflicts with module headers and `PROJECT_COMPLETE_GUIDE.md`.
2. **Validation naming and metadata:** the validator source explicitly says synthetic option prices, but the saved JSON metadata says “Real Market Data” without the option-proxy qualification.
3. **Validation metrics differ across documents:** the checked-in JSON has 1,674 instances and TP=804; `PROJECT_COMPLETE_GUIDE.md` claims 1,676 and TP=806; other documents report 1,676/TP=806 or slightly different rounded metrics.
4. **Mispricing thresholds differ:** documentation says 3% plus z-score and liquidity; validator uses 3% deviation only; main service uses 5% deviation or M-Score 1.2; chain service uses another formula.
5. **Volatility fusion weights differ:** environment/runtime defaults are 70% daily and 30% intraday; pipeline telemetry and documentation state 35% daily and 65% 5m.
6. **Regime input differs:** the live pipeline trains on rolling volatility; validation passes raw returns. Labels and IDs are also used inconsistently.
7. **Hard-coded telemetry:** `pipeline_service.py` reports fabricated-looking current regime, confidence, M-Score, opportunity count, latency-stage outputs, trade count, and P&L without invoking the corresponding services.
8. **Backtest overclaim:** documentation calls the system a backtester, while the implementation explicitly returns `is_option_pnl_backtest: False` and warns that quotes are not timestamp-aligned.
9. **Model specification overclaim:** documentation lists fixed EGARCH coefficients, HMM state volatilities, Rho, and a specific IV solver; source code estimates parameters dynamically, returns no Rho, and uses SciPy Brent.
10. **Data-layer fragmentation:** `DBService` manages `option_ticks`, while the option-chain service/recorder manage `option_snapshots`; the repository does not show a complete conversion from recorded historical option snapshots into the backtest.
11. **Fallback semantics in invalid inputs:** `detect_mispricing` returns a “fair” result for invalid inputs, which can silently look like a valid no-signal result rather than an explicit error or unavailable status.
12. **State leakage across requests:** VRP and M-Score windows are module-global and keyed neither by symbol, expiry, contract, nor session, so API request order affects results.

## 10. Bottom line

The repository has a usable research prototype and live decision-support/paper-trading implementation. EGARCH, HMM, volatility fusion, BSM pricing, IV, VRP, M-Score, chain processing, and paper ledger components exist in executable code. However, the current evidence does not support claiming a validated historical option-mispricing detector or profitable trading system. Before manuscript changes, the highest-priority investigations are: obtain and verify timestamp-aligned option quotes; remove or label all synthetic fallbacks; unify the M-Score/threshold/fusion definitions; isolate state by instrument/session; and replace the proxy backtest with a true option P&L backtest including bid-ask spreads, costs, liquidity, margin, and out-of-sample controls.
