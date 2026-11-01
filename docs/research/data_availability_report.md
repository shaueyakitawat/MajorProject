# Phase 4 Research Backtest: Data Availability and Proposed Specification

## Scope and implementation boundary

This is a pre-run design report. No backtest was executed and no existing
application file, dataset, manuscript, or prior experiment output was
modified. The eventual implementation must be isolated under
`scripts/research_backtest/`.

The existing `backend/services/backtest_service.py` is not suitable for this
experiment. It downloads Yahoo Finance data at runtime, reuses one current
option-chain quote across historical dates, and falls back to synthetic
Black-Scholes prices when no quote is available
(`backend/services/backtest_service.py:102-177`). It explicitly identifies
itself as an underlying-direction proxy rather than an option P&L backtest
(`backend/services/backtest_service.py:176-179`). It will not be changed or
called by the research module.

## 1. Available historical data

### NIFTY 50 index

| Property | Verified value |
|---|---|
| File | `data/research/nifty50_index_daily.csv` |
| Source | Yahoo Finance chart API, `^NSEI` |
| Frequency | Daily |
| Coverage | 2024-07-01 through 2025-12-31 |
| Observations | 375 |
| Fields | `trade_date`, `open`, `high`, `low`, `close`, `source` |
| Alignment | All 375 option trading dates are represented |
| Validation | 0 duplicate dates, 0 missing aligned dates, 0 invalid OHLC records |

This is third-party data, not an official NSE historical index archive. The
source, URL, raw response checksum, and licensing caveat are recorded in
`docs/research/nifty50_index_validation_report.md`. No price interpolation or
filling was performed.

### NIFTY index options

| Property | Verified value |
|---|---|
| File | `data/research/nifty_options_daily.csv` |
| Source | NSE daily F&O bhavcopy files |
| Frequency | Daily |
| Coverage | 2024-07-01 through 2025-12-31 |
| Records | 605,159 |
| Distinct trade dates | 375 |
| Positive-volume records | 346,156 |
| CE / PE records | 299,793 / 305,366 |
| Source schemas | Legacy 8,406; new 596,753 |
| Duplicate contract-date groups | 0 |

The normalized and preserved raw fields include trade date, expiry, strike,
option type, daily OHLC, close, settlement, contracts, turnover, open
interest, source schema, and source URL. The source schema also retains the
original NSE columns. There are no historical bid, ask, intraday timestamp,
or implied-volatility fields.

The validation report confirms that all 348 flagged records are
positive-volume settlement-zero anomalies. Zero-volume records remain in the
dataset, but are not eligible for execution. Traded OHLC checks are valid only
for `contracts > 0`; non-traded rows have zero OHLC and positive stale/closing
values in some cases. The research sample must therefore require positive
contracts and positive entry/exit prices without deleting the source data.

### Data fields that are unavailable

The following must not be manufactured:

- Bid, ask, bid/ask spread, or executable quote.
- Intraday timestamps or intraday option candles.
- Historical implied volatility.
- Lot size or contract multiplier in the normalized research file.
- A guaranteed fill price or order-book depth.

Consequently, the initial experiment supports only daily option-bar execution
and reports results as historical daily-close/open reference-price results,
not executable market performance.

## 2. Existing indicators and strategy infrastructure

The repository does not contain a reusable EMA, RSI, or ATR indicator module;
searches found no dedicated indicator implementation. The existing strategy
service is a live volatility/mispricing recommendation function
(`backend/services/strategy_service.py:37-165`), not a directional historical
signal engine. The existing regime service fits a cached 3- or 4-state HMM and
requires a supplied historical volatility series
(`backend/services/regime_service.py:14-85`).

The research module will implement only small, transparent pandas-based
indicator helpers inside `scripts/research_backtest/`, without modifying
production services. The existing BSM function may be reused for diagnostics,
but it is not required for the directional option-entry rules
(`backend/services/pricing_service.py:7-65`).

## 3. Proposed chronological experiment design

### Period split

The available sample is short. The proposed fixed chronological split is:

| Period | Dates | Purpose |
|---|---|---|
| Training | 2024-07-01 to 2024-12-31 | Freeze rules and risk parameters |
| Validation | 2025-01-01 to 2025-06-30 | Confirm that frozen rules are operational |
| Test | 2025-07-01 to 2025-12-31 | Final out-of-sample evaluation |

No parameter search or stop-loss optimization may use the test period. If the
training period is too short for a stable calibration, the result must be
reported as underpowered rather than re-partitioned after seeing test results.

Signals are generated from the index bar close at date `t`. Entry is no
earlier than the next observed session, `t+1`. The signal date and execution
date must be stored separately in every trade.

## 4. Proposed deterministic strategies

All rules below are proposed for review and are not yet run.

### A. EMA crossover

- Compute 10-session and 30-session exponential moving averages of NIFTY
  closes.
- Long signal: fast EMA crosses from at-or-below slow EMA to above it at the
  signal close.
- Short signal: fast EMA crosses from at-or-above slow EMA to below it.
- One signal per crossing; no repeated entries while a position is open.
- The long signal selects a CE; the short signal selects a PE.

### B. RSI reversal

- Compute 14-session Wilder-style RSI from NIFTY closes.
- Long signal: RSI crosses upward through 30.
- Short signal: RSI crosses downward through 70.
- The signal is generated only on the crossing, not while RSI remains
  oversold/overbought.
- CE is used for long signals and PE for short signals.

### C. Volatility breakout

- Use the prior 20 completed index sessions' high and low.
- Long signal: current close exceeds the prior-window high.
- Short signal: current close falls below the prior-window low.
- Volatility filter: current 14-session ATR divided by current close must be
  at least the training-period median of that ratio.
- The filter threshold is estimated from training data only and then frozen.

### D. HMM-filtered EMA

- Generate the same EMA crossing signals as Strategy A.
- Fit a two-state Gaussian HMM to a trailing volatility feature using only
  observations strictly before the signal date.
- Permit long/short EMA entries only when the filtered state assignment is
  available and has been estimated without future observations.
- Because the production HMM service caches state and can be trained on the
  entire supplied series, it must not be called directly for this experiment.
- The separate research implementation must use walk-forward fitting and
  record the training endpoint, state count, filtered probabilities, and
  state-volatility ordering.
- If reliable filtered assignments cannot be produced for a date, the
  filtered strategy skips that date; it must not fall back silently to the
  unfiltered strategy.

The unfiltered EMA strategy is the direct benchmark for Strategy D. A no-trade
benchmark is also required.

## 5. Deterministic contract selection

For a signal at index date `t`, selection uses only information available by
the close of `t`:

1. Direction determines CE for a long signal and PE for a short signal.
2. Select the nearest available strike to the NIFTY close at `t` among valid
   contracts, using a fixed ATM tolerance of 2.5% of spot.
3. Select the nearest expiry with calendar DTE between 15 and 45 days at `t`.
4. Require the candidate's `contracts > 0`, `open_interest > 0`, positive
   strike, valid expiry, and positive close on `t`.
5. Preserve the exact trade-date, expiry, strike, option type, instrument,
   and source-schema identifiers.
6. Enter on the selected contract's next-session `open`, requiring a positive
   next-session open. If the contract has no valid next-session bar, skip the
   trade rather than substituting another price.

The current dataset has no verified lot-size/multiplier field. Initial results
must therefore be reported in option-price points and percentage returns, not
rupee P&L. A rupee conversion requires a separately verified historical NSE
lot-size schedule and must not be inferred from current configuration.

## 6. Proposed daily risk management

- ATR period: 14 completed option bars.
- ATR source: selected option's daily OHLC, calculated using only bars before
  the entry date. If fewer than 14 valid prior bars exist, no ATR-based
  trade is opened.
- Stop-loss multiplier: 1.5 ATR.
- Reward-to-risk ratio: 2.0.
- Maximum holding period: 10 observed option sessions.
- Position size: one contract unit in price-point reporting; no rupee sizing
  until lot size is verified.
- Maximum capital risk: not operationally defined until a verified multiplier
  and capital base are supplied.

The proposed values are fixed design defaults, not optimized results. They
must be frozen after training/validation review and before the test period.
For a daily bar, if the next bar opens through the stop or target, exit at the
opening price. If both stop and target are crossed within one bar and sequence
is unknown, apply stop-loss first. No intraday stop-loss claim may be made.

## 7. Transaction-cost treatment

The live paper trader contains estimated assumptions of ₹20 brokerage per
leg, exchange charge `0.00053` of turnover, STT `0.00125` on the applicable
sell leg, and GST at 18% on brokerage plus exchange charges
(`scripts/live_paper_trader.py:175-190` and `:1575-1605`). These are live
paper-trading estimates, not verified historical fee schedules for every
date.

The research module should expose three clearly labeled sensitivity cases:

1. Zero modeled cost, as a gross reference.
2. Existing paper-trader statutory-cost approximation, with assumptions
   copied into the output metadata.
3. The same statutory approximation plus a documented percentage slippage
   sensitivity, since bid/ask spreads are unavailable.

No historical spread or fill quality may be claimed. Cost cases must be
reported separately and must not be selected after inspecting test
profitability.

## 8. Required outputs after approval

Only after this specification is reviewed should the separate module be
implemented and run. It should create:

- `scripts/research_backtest/`
- `docs/research/backtest_methodology.md`
- `docs/research/backtest_results.md`
- `docs/research/backtest_data_limitations.md`
- `data/research/backtest/trades.csv`
- `data/research/backtest/performance_metrics.json`
- `data/research/backtest/strategy_comparison.csv`
- Figures under `docs/research/figures/`

The outputs must include trade counts, win rate, gross/net point returns,
average return, profit factor, Sharpe, Sortino, drawdown, largest loss,
stop/target counts, holding period, skipped-trade reasons, and benchmark
results. The report must distinguish gross point performance from any
rupee-denominated result and must not claim profitability unless the frozen
out-of-sample test results support it.

## Review decision required before implementation

The following choices should be confirmed before code is written:

1. Whether the proposed 10/30 EMA, 14 RSI, 20-session breakout, and
   15-45 DTE/2.5% ATM defaults are accepted without further tuning.
2. Whether the 2024/2025 chronological split is accepted.
3. Whether one-session delayed entry at the next daily open is the required
   execution convention.
4. Which transaction-cost sensitivity cases should be primary.
5. Whether point-return reporting is acceptable until a historical lot-size
   schedule is obtained.
