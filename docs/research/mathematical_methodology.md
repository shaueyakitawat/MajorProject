# Mathematical Methodology Extracted From Source

**Scope:** exact mathematical behavior present in the repository as inspected on 2026-10-31. This is a source extraction, not a redesign or validation claim. Equations below describe implementation behavior; implementation does not establish scientific validity.

## 1. Notation and Definitions

| Symbol | Implemented meaning | Source |
|---|---|---|
| \(S\) | Spot price | `backend/services/pricing_service.py::black_scholes_price`, lines 6-29 |
| \(K\) | Strike price | Same as above |
| \(T\) | Time to expiry in years | `backend/services/pricing_service.py::calculate_ttm_years`, lines 109-140 |
| \(r\) | Risk-free rate supplied by caller | `backend/services/pricing_service.py::black_scholes_price`, lines 29-34 |
| \(q\) | Continuous dividend yield; default \(0.0125\) | `backend/services/pricing_service.py::black_scholes_price`, lines 6-29 |
| \(\sigma\) | Volatility input; generally decimal annualized volatility in the live path | `main.py::run_pipeline`, lines 444-629 |
| \(IV\) | Volatility solved from an observed option price | `backend/services/implied_volatility_service.py::calculate_implied_volatility`, lines 13-84 |
| \(RV\) | Realized volatility calculated from price log returns | `backend/services/volatility_service.py::_compute_realized_volatility`, lines 36-59 |
| \(VRP\) | Code variable for \(IV-\sigma\), a volatility-level spread | `backend/services/vrp_service.py::compute_vrp`, lines 21-35 |
| \(M\) | M-Score returned by the main mispricing service | `backend/services/mispricing_service.py::detect_mispricing`, lines 94-109 |

Unless stated otherwise, values are decimal fractions: 0.20 means 20%. The chain display converts some deviations and VRP values to percentage points before its own M-Score calculation.

## 2. Data Preprocessing

### 2.1 Provider mapping and fetch windows

`backend/services/data_service.py::_map_symbol_for_provider`, lines 13-18, maps `NIFTY` to Yahoo Finance ticker `^NSEI`. `_get_fetch_window_for_timeframe`, lines 20-29, defines:

* `1m`: 7 days, 1-minute interval;
* `5m`, `15m`: 60 days;
* `30m`: 60 days;
* `1h`: 730 days at Yahoo interval `60m`;
* `daily`: 10 years at `1d`;
* `weekly`: maximum period at `1wk`.

`fetch_nifty_data`, lines 32-87, downloads adjusted OHLCV data, flattens MultiIndex columns, drops fully empty rows, requires at least 100 candles, and retains only the last 2,000 rows (`TARGET_CANDLES = 2000`, lines 10 and 69-70). NaNs in individual nonempty OHLCV fields are not globally imputed by this function.

Naive datetime indexes are localized to UTC and then converted to `Asia/Kolkata` at lines 72-78. The index is reset and converted to strings at lines 80-87.

### 2.2 Log returns

`backend/services/data_service.py::compute_log_returns`, lines 90-106, computes:

\[
r_t = \ln\left(\frac{C_t}{C_{t-1}}\right)
\]

where \(C_t\) is the `Close` column. The shifted first observation is removed with `dropna()`. `main.py::run_pipeline`, lines 378-421, additionally rejects an empty return frame, fewer than two observations, any NaN, and any nonfinite return. The main pipeline requires at least 100 returns for EGARCH at `main.py:397-401`.

### 2.3 Timeframe normalization and annualization

`backend/infrastructure/timeframe_config.py:11-35` defines annualization factors:

\[
N_{\text{1m}}=252\cdot390,\quad
N_{\text{5m}}=252\cdot78,\quad
N_{\text{15m}}=252\cdot26,
\]
\[
N_{\text{30m}}=252\cdot13,\quad
N_{\text{1h}}=252\cdot6.5,\quad
N_{\text{daily}}=252,\quad
N_{\text{weekly}}=52.
\]

`backend/infrastructure/annualization_engine.py::apply_dynamic_annualization`, lines 42-145, applies:

\[
\sigma_{\text{annual}}=\sigma_{\text{period}}\sqrt{N}.
\]

It rejects nonfinite or nonpositive raw volatility. `timeframe_adapter.py::normalize_timeframe_dataframe` is called by `main.py::run_pipeline` at lines 374-376, but the inspected extraction does not establish that it resamples all provider data rather than normalizing labels; its implementation should be treated as a separate adapter.

The default horizon mapping is `day_trader -> 5m`, `positional -> daily`, `long_term -> weekly`, and `None -> daily` at `timeframe_config.py:38-44`.

### 2.4 Pipeline cache

`main.py::run_pipeline`, lines 353-376 and 407-444, caches historical and 5m data by symbol/timeframe for `run_pipeline.cache_ttl_seconds = 300` seconds at `main.py:1329`. This is operational caching, not a historical training-window definition.

## 3. EGARCH Forecasting

### 3.1 Production EGARCH specification

`backend/services/volatility_service.py::forecast_volatility`, lines 89-114, constructs:

```python
arch_model(percentage_returns, vol="EGARCH", p=1, q=1, dist="normal")
```

Thus the implemented model is an `arch` EGARCH model with \(p=1\), \(q=1\), and normal innovations. The source does not explicitly set mean specification, optimizer, starting values, or EGARCH parameters; those are library defaults.

The exact high-level model class requested is EGARCH(1,1). The source does not expose fitted \(\omega,\alpha,\beta,\gamma\) values, nor does it manually implement the logarithmic conditional-variance equation. Therefore fixed coefficients claimed in documentation are not verified as runtime parameters.

### 3.2 Input scaling, fit, and forecast horizon

The input returns are multiplied by 100:

\[
x_t=100r_t.
\]

This occurs at `volatility_service.py:96`. The model is fitted with `model.fit(disp="off")` at lines 98-100 and forecast with `fitted_model.forecast(horizon=1)` at lines 101-103. The selected variance is the last row, first horizon:

\[
\widehat{\sigma}_{x,t+1}^2
=\texttt{forecast.variance.values[-1,0]}.
\]

The standard deviation is converted from percentage units to decimal:

\[
\widehat{\sigma}_{\text{raw},t+1}
=\frac{\sqrt{\widehat{\sigma}_{x,t+1}^2}}{100}.
\]

This is implemented at `volatility_service.py:103-107`.

### 3.3 Annualization

The raw value is annualized with the daily factor:

\[
\sigma_{\text{daily, annualized}}
=\sigma_{\text{raw}}\sqrt{252},
\]

through `apply_dynamic_annualization(raw_vol, "daily")` at `volatility_service.py:116`.

In the separate backtest, `backend/services/backtest_service.py::_egarch_forecast`, lines 67-78, fits the same EGARCH specification on each rolling window, converts by `/100`, and returns raw daily-scale volatility. `run_backtest`, lines 220-233, then calls `apply_dynamic_annualization` with the backtest timeframe mapping (`1m`, `5m`, `15m`, `1d -> daily`).

### 3.4 Fallback behavior

If fitting, forecasting, or extraction raises an exception, production EGARCH falls back to `returns_series.std()` at `volatility_service.py:108-110`. If the result is nonpositive or nonfinite, it is replaced with `0.01` at lines 112-114.

The main pipeline then applies `sanitize_volatility`, `main.py:300-307`, which:

* replaces nonfinite values with 0.15;
* clamps values below 0.01 to 0.01;
* clamps values above 2.0 to 2.0.

The backtest has no 0.01 replacement inside `_egarch_forecast`; a failed rolling fit causes that bar to be skipped at `backtest_service.py:224-228`.

## 4. Realized Volatility and Fusion

### 4.1 General realized-volatility equation

`backend/services/volatility_service.py::_compute_realized_volatility`, lines 36-59, removes nonnumeric prices, computes log returns, and calculates:

\[
RV_{\text{period}}
=\sqrt{\sum_{i=1}^{n} r_i^2}.
\]

It then annualizes using the number of observations:

\[
RV_{\text{annualized}}
=RV_{\text{period}}\sqrt{\frac{N_{\text{annual}}}{n}}.
\]

This differs from a sample-standard-deviation estimator: the implementation does not subtract the sample mean and does not divide the squared-return sum by \(n\) before scaling.

### 4.2 5-minute realized volatility

`compute_intraday_realized_volatility`, lines 61-63, calls the general function with timeframe `"5m"`:

\[
RV_{5m}
=\sqrt{\sum r_{5m,i}^2}
\sqrt{\frac{19656}{n}}.
\]

The factor \(19656=252\cdot78\) is from `timeframe_config.py:15-18`.

### 4.3 15-minute and hourly realized volatility

`_compute_15m_realized_volatility_from_5m`, lines 77-87, either resamples a DatetimeIndex to `15min` using the last price in each bin or selects every third observation when the index is not datetime. It then applies the general formula with \(N=6552\).

`_compute_hourly_realized_volatility_from_5m`, lines 65-75, either resamples to `1h` using the last price in each bin or selects every twelfth observation. It then applies the general formula with \(N=1638\).

The 15-minute and hourly quantities are not included in the fused volatility; they are used only to compute TCI.

### 4.4 Production fusion equation and weights

`volatility_service.py:23-24` reads:

\[
w_d=\texttt{VOL\_FUSION\_DAILY\_WEIGHT},\quad
w_i=\texttt{VOL\_FUSION\_INTRADAY\_WEIGHT},
\]

with defaults \(w_d=0.7\), \(w_i=0.3\). If intraday data exists, `_normalize_weights`, lines 27-34, divides both by \(w_d+w_i\). If no intraday value exists, it returns \((1,0)\). If the total is nonpositive, it returns \((0.5,0.5)\).

The production fusion at `volatility_service.py:119-123` is:

\[
\sigma_{\text{fused}}
=w_d\sigma_{\text{daily}}
+w_i\sigma_{5m}.
\]

The main pipeline calls this service at `main.py:444`.

### 4.5 TCI

When hourly, 15m, and 5m values all exist, `forecast_volatility`, lines 125-131, defines:

\[
TCI=\operatorname{Var}\left(
\sigma_{\text{daily}},
\sigma_{\text{hourly}},
\sigma_{15m},
\sigma_{5m}
\right).
\]

The source uses NumPy population variance (`np.var`) and does not normalize the result to a fixed range.

### 4.6 Telemetry path discrepancy

`backend/services/pipeline_service.py::get_pipeline_execution_trace`, lines 48-57, does not call `forecast_volatility`; it assigns `egarch_daily=0.1290`, `rv_5m=0.1721`, and computes:

\[
\sigma_{\text{telemetry}}
=0.65RV_{5m}+0.35\sigma_{\text{EGARCH}}.
\]

The telemetry path therefore differs from the production runtime defaults of 70% daily and 30% intraday. Its 15m value and TCI are also constants at `pipeline_service.py:51-57`.

## 5. HMM Regime Classification

### 5.1 Model configuration

`backend/services/regime_service.py::_fit_hmm`, lines 31-38, constructs:

```python
GaussianHMM(
    n_components=state_count,
    covariance_type="diag",
    n_iter=500,
    random_state=42
)
```

The default state count is read from `REGIME_STATE_COUNT`, default 4, at line 10. Values of three or fewer are coerced to 3; all larger values are coerced to 4 at `classify_volatility_regime`, lines 63-64.

The emission distribution is Gaussian with diagonal covariance. The source does not explicitly specify or report the transition matrix; it is estimated internally by `hmmlearn`. The model is fitted with `model.fit(vol_series)` at lines 35-36.

### 5.2 Input features and training window

`_prepare_series`, lines 19-28, converts the supplied feature series to finite floating-point values, requires at least `MIN_TRAIN_SAMPLES=120`, and reshapes to one feature:

\[
y_t=\text{one supplied scalar observation}.
\]

In the main live pipeline, `main.py:595-599` supplies:

\[
y_t=252^{1/2}\operatorname{std}_{60}(r),
\]

where the rolling window is 60 returns and the annualization constant is `sqrt_252 = 15.8745` at `main.py:447`.

The current observation passed to `predict_proba` is the fused/current forecast volatility:

\[
y_{t+1}^{\text{obs}}=\sigma_{\text{forecast}},
\]

at `regime_service.py:78-80`.

The validator and diagnostic runner use a different input: raw returns are passed directly to `classify_volatility_regime` at `validation/daily_mispricing_validator.py:140-142` and `run_validation.py:102`.

### 5.3 State ordering and posterior classification

After fitting, state means are sorted:

\[
\text{state\_order}=\operatorname{argsort}(\mu_j),
\]

at `regime_service.py:38-39`. The predicted posterior vector is:

\[
p_j=P(S=j\mid y_{\text{current}})
\]

from `model.predict_proba(obs)[0]` at lines 78-81. The selected state is:

\[
\hat{j}=\arg\max_j p_j,\qquad
\text{confidence}=p_{\hat{j}}.
\]

These are implemented at lines 80-82. Labels are assigned by the rank of the fitted mean, not by fixed numeric state ID, at lines 41-47 and 84-86:

* rank 0: `LOW_VOL`;
* rank 1: `NORMAL_VOL`;
* rank 2: `HIGH_VOL`;
* rank 3: `EXTREME_VOL` for four states.

### 5.4 Caching and limitations

`_HMM_MODEL`, `_HMM_STATE_ORDER`, and `_HMM_STATE_COUNT` are module-global at `regime_service.py:15-17`. A new model is fitted only when no model exists or the state count changes, at lines 68-71. The cache is not keyed by symbol, timeframe, date, training sample, or session. A call with a new training series but the same state count can reuse the previous fitted model.

If no valid model exists or the current volatility is nonfinite, the function returns state 0, label `NORMAL_VOL`, confidence 0.0 at `regime_service.py:73-77`.

## 6. BSM Pricing and Greeks

### 6.1 Volatility adjustment

`backend/services/pricing_service.py::black_scholes_price`, lines 6-29, starts with \(\sigma=\text{volatility}\). If `use_adjusted_vol=True` and `expected_vrp` is finite:

\[
\sigma_{\text{pricing}}=\sigma+\text{expected\_vrp}.
\]

This is implemented at lines 17-19. The default `use_adjusted_vol` is `True`. The main pipeline initially prices with `use_adjusted_vol=False` at `main.py:570-578`, then reprices with `use_adjusted_vol=True` and expected VRP at `main.py:609-617`.

### 6.2 BSM quantities and price equations

For positive spot, strike, time, and volatility, the implementation defines:

\[
d_1=
\frac{\ln(S/K)+(r-q+\frac{1}{2}\sigma^2)T}
{\sigma\sqrt{T}},
\qquad
d_2=d_1-\sigma\sqrt{T}.
\]

Source: `pricing_service.py:31-39`.

Discount factors are:

\[
D_q=e^{-qT},\qquad D_r=e^{-rT}.
\]

Source: `pricing_service.py:40-41`.

The call price is:

\[
C=S e^{-qT}N(d_1)-K e^{-rT}N(d_2).
\]

The put price is:

\[
P=K e^{-rT}N(-d_2)-S e^{-qT}N(-d_1).
\]

Source: `pricing_service.py:43-50`.

The result is floored at zero at line 54. If spot or strike is nonpositive, the function returns zero at lines 21-22. If \(T\le0\) or \(\sigma\le0\), it returns intrinsic value for recognized call/put types at lines 23-29.

### 6.3 Rates and dividend yield

The pricing function receives \(r\) from the caller and uses a default continuous dividend yield \(q=0.0125\) at `pricing_service.py:6-15`. The main live pipeline passes \(r=0.06\) at `main.py:570-578` and `main.py:609-617`. The option-chain service uses \(r=0.065\) at `option_chain_service.py:319-320` and uses the pricing function's default dividend yield. The validator uses its configured risk-free rate \(r=0.065\) at `validation/daily_mispricing_validator.py:47-65`.

There is no single repository-wide risk-free-rate convention.

### 6.4 Time to maturity

`calculate_ttm_years`, `pricing_service.py:109-140`, parses the expiry, sets expiry time to 15:30:00, harmonizes naive/aware timezone handling, and computes:

\[
T=\frac{\max(900,\;t_{\text{expiry}}-t_{\text{now}})}
{365.25\cdot86400}.
\]

The 900-second floor is at line 135. On parsing errors it returns \(7/365\) at line 140.

The main pipeline does not use this helper for its live chain TTM; it parses the chain expiry and calculates elapsed seconds divided by \(365\cdot86400\) at `main.py:556-563`, with no 15-minute floor. The validator hard-codes \(T=30/365\) at `daily_mispricing_validator.py:149`. The backtest uses current expiry time or `FALLBACK_T=0.1` at `backtest_service.py:31` and `:165-200`.

### 6.5 Greeks

`calculate_greeks`, `pricing_service.py:57-105`, returns zero for invalid/nonpositive inputs at lines 68-69. It reuses \(d_1,d_2,D_q,D_r\) and defines:

\[
\Gamma=\frac{e^{-qT}\phi(d_1)}{S\sigma\sqrt{T}}.
\]

Source: `pricing_service.py:82-83`.

Vega is:

\[
\text{Vega}_{1\%}
=\frac{S e^{-qT}\phi(d_1)\sqrt{T}}{100}.
\]

Source: `pricing_service.py:85-86`. It is explicitly per one percentage-point volatility change.

For a call:

\[
\Delta_C=e^{-qT}N(d_1),
\]
\[
\Theta_C^{\text{day}}
=\frac{
-\frac{S e^{-qT}\phi(d_1)\sigma}{2\sqrt{T}}
-rKe^{-rT}N(d_2)
+qSe^{-qT}N(d_1)}
{365}.
\]

For a put:

\[
\Delta_P=e^{-qT}(N(d_1)-1),
\]
\[
\Theta_P^{\text{day}}
=\frac{
-\frac{S e^{-qT}\phi(d_1)\sigma}{2\sqrt{T}}
+rKe^{-rT}N(-d_2)
-qSe^{-qT}N(-d_1)}
{365}.
\]

Sources: `pricing_service.py:88-101`. Rho is not implemented in the returned Greek dictionary.

## 7. Implied Volatility

`backend/services/implied_volatility_service.py::calculate_implied_volatility`, lines 13-84, solves:

\[
f(v)=BS(S,K,T,r,v,\text{type},q)-P_{\text{market}}=0.
\]

Input values with nonpositive market price, spot, strike, or T return `None` at lines 38-39. Discount factors for boundary checks are \(e^{-rT}\) and \(e^{-qT}\) at lines 44-45.

For calls, the lower boundary is:

\[
I_C=\max(0,Se^{-qT}-Ke^{-rT}),\quad U_C=Se^{-qT}.
\]

For puts:

\[
I_P=\max(0,Ke^{-rT}-Se^{-qT}),\quad U_P=Ke^{-rT}.
\]

Source: `implied_volatility_service.py:47-55`.

If market price \(\le I+10^{-4}\), the function returns \(0.001\). If market price \(\ge U-10^{-4}\), it returns \(3.0\), at lines 57-63. Otherwise it evaluates the BSM objective at \(v=0.0001\) and \(v=4.0\), checks the bracket, and returns 0.001 or 3.0 if no sign change at lines 69-78. A successful solve uses SciPy `brentq(objective, 0.0001, 4.0, xtol=1e-5, maxiter=100)` at lines 80-81. Exceptions return `None` and log at debug level at lines 82-84.

The source does not implement vectorized IV, Newton-Raphson, Brenner-Subrahmanyam seeding, or a stated fewer-than-five-iteration guarantee.

`classify_vol_spread`, lines 87-115, computes:

\[
\text{vol\_spread}=IV-\sigma_{\text{EGARCH}},
\]

and labels `IV_HIGH` if above 0.05, `IV_LOW` if below -0.05, otherwise `IV_FAIR`.

## 8. VRP Estimation

### 8.1 Exact formula

`backend/services/vrp_service.py::compute_vrp`, lines 21-35, defines:

\[
VRP_t=IV_t-\sigma_t,
\]

where \(\sigma_t\) is the supplied `final_vol`/`vol_forecast`. The function returns `vrp=None` if either input is absent or nonfinite at lines 22-31.

This is a volatility-level spread. A variance risk premium would ordinarily involve variance-scale quantities such as \(IV_t^2-\widehat{\sigma_t^2}\), but that equation is not implemented here.

### 8.2 Rolling normalization

The rolling length is `VRP_ROLLING_WINDOW`, default 60, at `vrp_service.py:7`. The current VRP is appended to the overall deque and, when recognized, the regime-specific deque at lines 36-43. The active values are:

\[
\bar{VRP}_g=\frac{1}{n_g}\sum_{i=1}^{n_g}VRP_i,
\]
\[
s_g=\sqrt{\frac{1}{n_g}\sum_{i=1}^{n_g}(VRP_i-\bar{VRP}_g)^2}.
\]

These are NumPy population mean/std calls at `vrp_service.py:47-49`. The current observation is included before both calculations.

There is no implemented standardized VRP z-score. `vrp_std` is returned but not used by `detect_mispricing`; the main pipeline passes `current_vrp` and `expected_vrp` at `main.py:604` and `main.py:635-638`.

### 8.3 State contamination

`_vrp_by_regime` and `_vrp_window` are module-global deques at `vrp_service.py:9-18`. They are not keyed by symbol, expiry, strike, option type, timeframe, user, or session, and no reset function exists. Requests can therefore alter later expected VRP values. Unknown regime labels use the overall window at lines 41-43.

## 9. M-Score Construction

### 9.1 Main live pipeline formula

The main live route calls `detect_mispricing` at `main.py:629-638`. The default weights are read at `mispricing_service.py:10-17`:

\[
w_p=0.50,\quad w_v=0.15,\quad w_g=0.15,\quad w_t=0.10,\quad w_r=0.10.
\]

Inputs are market price \(P_m\), fair price \(P_f\), Vega, Gamma, TCI, current VRP, expected VRP, and optional weight overrides at `mispricing_service.py:46-57`.

The base price deviation is:

\[
d=\frac{P_m-P_f}{P_f}.
\]

Source: `mispricing_service.py:67-69`.

The VRP deviation is:

\[
\Delta VRP=VRP_{\text{current}}-VRP_{\text{expected}}.
\]

Missing/nonfinite components are converted to zero by `_finite_or_zero` at `mispricing_service.py:20-23`, and the VRP calculation is at lines 71-73.

Normalizations are:

\[
z_p=20d,
\qquad
z_{VRP}=50\Delta VRP,
\]

at `mispricing_service.py:78-80`.

The sign of \(d\) is:

\[
\operatorname{sgn}_{0.001}(d)=
\begin{cases}
1,&d>0.001\\
-1,&d<-0.001\\
0,&\text{otherwise}.
\end{cases}
\]

Directional Greek components are:

\[
z_V=\operatorname{sgn}_{0.001}(d)\,
\min(2.5,\max(0,\text{Vega}/15)),
\]
\[
z_G=\operatorname{sgn}_{0.001}(d)\,
\min(2.5,\max(0,\text{Gamma}/0.0003)).
\]

Source: `mispricing_service.py:82-89`.

If \(TCI>0\), the multiplier is:

\[
m_{TCI}=1+0.4(TCI-0.5);
\]

otherwise \(m_{TCI}=1\). Source: `mispricing_service.py:91`.

The main M-Score is:

\[
M=
\left(
w_pz_p+w_rz_{VRP}+w_vz_V+w_gz_G
\right)m_{TCI}.
\]

Source: `mispricing_service.py:94-109`. The `tci` weight \(w_t\) is declared at line 14 but is not used as a linear term; TCI only enters through \(m_{TCI}\).

For \(|d|>0.03\), sign-consistency guards force \(M\) to have the same sign as \(d\) if the composite sign disagrees, at `mispricing_service.py:111-115`.

### 9.2 Rolling z-score

`_mscore_window` is a global deque of maximum length `MSCORE_Z_WINDOW`, default 60, at `mispricing_service.py:18`. `_z_score`, lines 25-42, appends the current M-Score before calculating:

\[
\bar M=\frac{1}{n}\sum M_i,
\qquad
s_M=\sqrt{\frac{1}{n}\sum(M_i-\bar M)^2},
\qquad
z_M=\frac{M-\bar M}{s_M}.
\]

Population variance is used. If fewer than two observations, zero/nonfinite standard deviation, or invalid standard deviation occurs, z-score is 0. The current M-Score is included in its own reference window.

The returned z-score is not used by the main classification rule.

### 9.3 Other M-Score-like calculations

1. **Option-chain path:** `backend/services/option_chain_service.py:350-374` sets `model_vol=0.135`, computes BSM fair prices, percentage deviations using `max(0.5, fair_price)`, and VRP as percentage points:

\[
M_{\text{chain}}
=0.50\frac{d_{\%}}{5}
+0.30\frac{VRP_{\%}}{2}
+0.10.
\]

It classifies at \(\pm1.2\) at lines 373-374. It does not use main-service Vega, Gamma, TCI, expected VRP, or rolling z-score.

2. **Pipeline telemetry:** `backend/services/pipeline_service.py:101-105` uses:

\[
M_{\text{telemetry}}
=\frac{P_{\text{market}}-P_{\text{fair}}}
{\text{Vega}\sqrt{T}\cdot10+0.1}.
\]

The top dislocation object is hard-coded with `mscore: 1.14` at lines 108-115.

3. **Surface path:** `backend/services/surface_service.py:70-77` uses:

\[
M_{\text{surface}}
=\frac{100\,VRP}{2.5\sqrt{T}+0.1}.
\]

4. **Backtest path:** `backend/services/backtest_service.py:117-118` uses:

\[
M_{\text{backtest-like}}
=0.6\frac{P_m-P_f}{P_f}
+0.4(IV-\sigma_{\text{EGARCH}}).
\]

It is called `final_score`, not M-Score, and is used only for direction.

There is therefore no single mathematical M-Score across the repository. The main live pipeline uses `mispricing_service.detect_mispricing`.

## 10. Mispricing Classification

The main service classifies at `mispricing_service.py:117-123`:

\[
\text{classification}=
\begin{cases}
\text{overpriced},&d>0.05\ \lor\ M\ge1.2\\
\text{underpriced},&d<-0.05\ \lor\ M\le-1.2\\
\text{fair},&\text{otherwise}.
\end{cases}
\]

The rolling z-score is returned but not required. Liquidity is not an argument to `detect_mispricing` and is not enforced there.

The isolated liquidity predicate `backend/services/option_chain_filters.py::is_leg_liquid`, lines 30-60, requires positive LTP, OI at least 1,000, volume at least 500, bid/ask present, and:

\[
\frac{\max(\text{ask}-\text{bid},0)}{\text{LTP}}
\le0.01.
\]

The source extraction does not establish that this predicate gates the main live mispricing call. The validator instead labels a quote synthetic when absolute percentage deviation is at least 3% at `validation/daily_mispricing_validator.py:177-178`.

## 11. Strategy Recommendation

### 11.1 Inputs and derived edge

`backend/services/strategy_service.py::generate_strategy`, lines 37-69, receives mispricing label, regime label, adjusted forecast volatility \(\sigma_{\text{adj}}\), IV, z-score, and ATM strike. It computes:

\[
\text{vol\_edge}=\sigma_{\text{adj}}-IV.
\]

Source: `strategy_service.py:63`. The defaults are `VOL_EDGE_THRESHOLD=0.03` and `Z_SCORE_THRESHOLD=1.0` at lines 8-9.

Quantitative inputs are considered available only when both volatility edge and raw z-score are finite/nonmissing at line 67.

### 11.2 Long-volatility condition

The quantitative long signal is:

\[
(\text{inputs available})
\land(\text{vol\_edge}\ge0.03)
\land(z\le-1.0).
\]

If quantitative inputs are unavailable, the fallback is `mispricing_label == "underpriced"`. Source: `strategy_service.py:71-78`.

Long volatility is selected only when `long_vol_signal` is true and the regime is not `EXTREME_VOL` at lines 80-81. Structure is `long_straddle` when \(|z|\ge1.5\), otherwise `long_strangle`, at lines 82-84.

### 11.3 Short-volatility condition

The quantitative short signal is:

\[
(\text{inputs available})
\land(\text{vol\_edge}\le-0.03)
\land(z\ge1.0).
\]

If inputs are unavailable, fallback is `mispricing_label == "overpriced"`. Source: `strategy_service.py:76-78`.

Short volatility is selected in the `elif short_vol_signal` branch at lines 102-103. The structure is `iron_condor` in `HIGH_VOL` or `EXTREME_VOL`, otherwise `short_straddle`, at lines 104-105.

### 11.4 No-trade condition

If neither long nor short condition is satisfied, the strategy is `NO_TRADE`, structure `wait`, with no new position at `strategy_service.py:132-149`.

### 11.5 Confidence and risk text

Confidence is:

\[
\text{confidence}=
\begin{cases}
\text{high},&|z|\ge2\ \lor\ |\text{vol\_edge}|\ge0.08\\
\text{medium},&|z|\ge1\ \lor\ |\text{vol\_edge}|\ge0.03\\
\text{low},&\text{otherwise}.
\end{cases}
\]

Source: `_confidence`, `strategy_service.py:22-27`.

The returned risk notes state qualitative assumptions: long options have maximum loss equal to premium, short straddles have tail risk, gamma rises near expiry/fast spot moves, and positions should be approximately delta-neutral. These are recommendation text, not demonstrated execution or risk-model calculations. The ATM structure uses one call and one put with quantity 1 in the returned suggestion at `strategy_service.py:92-100` and `:113-130`; no actual delta solve is performed.

The main pipeline passes the main M-Score’s returned z-score into strategy generation at `main.py:642-649`. Therefore the main live strategy path depends on the stateful M-Score z-score, even though that z-score does not affect the mispricing classification itself.

## 12. Implementation Discrepancies

1. **Fusion:** production service uses normalized runtime defaults 70% daily/30% intraday (`volatility_service.py:23-24`, `:119-123`); telemetry uses 35% daily/65% 5m (`pipeline_service.py:48-57`).
2. **EGARCH coefficients:** runtime fits parameters dynamically; no fixed documented coefficients are loaded or verified.
3. **HMM feature:** live pipeline trains on annualized 60-period rolling standard deviation; validator/diagnostic calls pass raw returns.
4. **HMM cache:** model cache is global and not keyed by data series or instrument.
5. **BSM rates:** main pipeline uses 6%, chain uses 6.5%, validator uses 6.5%, and the pricing function defaults dividend yield to 1.25%.
6. **TTM:** pricing helper uses 15:30 expiry and a 15-minute floor; main pipeline uses a direct seconds calculation without that floor; validator fixes 30 days.
7. **M-Score:** main, chain, surface, telemetry, and backtest formulas are incompatible.
8. **M-Score TCI:** `tci` has a declared weight but is not used as a weighted additive component in the main formula.
9. **M-Score z-score:** current value is included in its own window and the z-score is not a classification requirement.
10. **VRP terminology:** code uses IV minus volatility, not a variance-level difference.
11. **VRP/Greek state:** global histories are not instrument/session isolated.
12. **Liquidity:** a liquid-leg predicate exists, but the source does not establish universal enforcement before main mispricing classification.
13. **Strategy fallback:** missing quantitative inputs can trigger strategies from the categorical label alone.

## 13. Unverified Assumptions

The following are not established by the source extraction:

* EGARCH parameter estimates, leverage effect magnitude, stationarity, or forecast accuracy.
* HMM transition matrix values, state persistence, economic interpretation, or out-of-sample regime stability.
* Whether the square-root-of-time annualization assumptions hold for the downloaded NIFTY returns.
* Whether yfinance OHLCV timestamps and adjusted prices are suitable for the intended market microstructure analysis.
* Whether the live NSE/pnsea option fields are timestamp-aligned with the underlying spot used by the pipeline.
* Whether risk-free rates of 6%/6.5% and dividend yield 1.25% are empirically appropriate for each expiry.
* Whether the BSM European model is appropriate for the instrument and expiry conventions.
* Whether IV boundary clamps at 0.001 and 3.0 are economically valid.
* Whether a 60-observation VRP/M-Score history is sufficient.
* Whether “delta-neutral” ATM call/put pairs are actually delta-neutral after dividends, skew, quantities, and discrete strikes.
* Whether strategy risk notes, premium-capture targets, and regime gates correspond to realized executions.
* Any profitability, precision, recall, or publication-grade predictive validity.

## 14. Candidate Research Methodology

This section is deliberately separated from the implemented methodology. It records minimum methodological decisions that would be required for a defensible research study; none of the following should be attributed to the current implementation.

1. **Define the estimand before equations are reported.** Choose one of: price deviation, IV-versus-realized-volatility spread, variance risk premium, option-price reversion, or net trading profitability.
2. **Freeze one production-equivalent equation set.** Specify one volatility feature for HMM training, one fusion weighting rule, one VRP definition, one M-Score formula, one threshold rule, and one liquidity gate.
3. **Use timestamp-aligned option observations.** Match underlying spot, option bid/ask/LTP, IV, strike, expiry, OI, and volume at the same timestamp; preserve expired contracts and the raw source.
4. **Use strictly causal rolling features.** For an observation at \(t\), estimate volatility, HMM state, VRP reference statistics, and M-Score normalization using data available no later than \(t\), excluding the current observation from any historical reference statistic where the research design requires a lagged baseline.
5. **Evaluate actual option P&L.** Define entry at bid/ask or mid plus slippage, exit/expiry handling, contract multiplier, transaction costs, margin, position limits, and liquidity constraints. Report gross and net results.
6. **Use walk-forward out-of-sample splits.** Keep calibration, threshold selection, and test periods separate; report performance by regime and expiry/moneyness bucket.
7. **Compare baselines.** At minimum, compare against constant volatility, historical realized volatility, a simple IV edge rule, and no-trade/buy-and-hold alternatives as appropriate to the estimand.
8. **Archive reproducibility artifacts.** Store raw data, normalized tables, environment lock, configuration, source revision, timezone policy, run manifest, and generated outputs.

These are candidate research controls, not claims about what the repository currently implements.
