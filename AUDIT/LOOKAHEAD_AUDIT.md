# AUDIT/LOOKAHEAD_AUDIT.md
## Quantitative Look-Ahead Bias and Causal Filtration Audit

**Audit Date:** 2026-11-01  
**Auditor Roles:** Senior Econometrician & Statistical Research Auditor  
**Scope:** Verification of temporal causality, information filtrations ($\mathcal{F}_t$), and execution realism in `backend/services/csv_options_backtest_engine.py` and research scripts.

---

### 1. Executive Summary

A rigorous temporal causality audit revealed **three distinct forms of look-ahead bias** and one **execution priority distortion** in the historical options backtesting engine:

1. **Full-Sample Regime Classification Look-Ahead Bias (CONFIRMED):**
   * *Location:* `backend/services/csv_options_backtest_engine.py:277-287`.
   * *Mechanism:* Volatility regime boundaries were derived using `np.percentile(vol_vals, [25, 75, 90])` calculated over the entire 375-session evaluation period (July 2024 to December 2025). Furthermore, this static percentile binning replaced the claimed causal Gaussian Hidden Markov Model.
   * *Impact:* On session $t=1$ (July 2024), regime classification utilized future volatility information spanning through December 2025.

2. **EGARCH Estimation Window Alignment (CONFIRMED):**
   * *Location:* `backend/services/csv_options_backtest_engine.py:253`.
   * *Mechanism:* The rolling window filtered returns using `sub_returns = log_returns[log_returns.index <= dt]`, where `dt` was the trade date. The return on date `dt` ($\ln(S_{\mathrm{close},t}/S_{\mathrm{close},t-1})$) was thus included in the estimation sample, after which a 1-step ahead forecast was used to price options on date `dt`.
   * *Impact:* Day $t$ option valuation conditioned on Day $t$ realized closing price rather than strictly $\mathcal{F}_{t-1}$.

3. **Intraday Target/Stop Priority Bias (CONFIRMED):**
   * *Location:* `backend/services/csv_options_backtest_engine.py:332-348`.
   * *Mechanism:* On sessions where a position's high and low prices breached both the stop-loss and take-profit thresholds, the code evaluated `if low_p <= target: exit_price = target` *before* checking `elif high_p >= stop`.
   * *Impact:* Dual-breach sessions were systematically credited as profitable target exits rather than conservative stop-loss executions.

4. **Contemporaneous Close-to-Close Execution Model:**
   * *Location:* `backend/services/csv_options_backtest_engine.py:466-515`.
   * *Mechanism:* Candidate options were identified using date $t$ closing prices ($P_{\mathrm{mkt}}$) and entered at date $t$ closing prices.
   * *Impact:* In actual exchange trading, options cannot be filled at the exact closing price without MOC order infrastructure. A realistic execution model must either execute on date $t+1$ Open or incorporate explicit bid-ask spread crossing friction on Day $t$.

---

### 2. Detailed Technical Audit of Violations

#### 2.1 The Pseudo-HMM Full-Sample Leakage
In `backend/services/csv_options_backtest_engine.py`, the regime assignment was implemented as:
```python
# Lines 277-287
vol_vals = list(vol_cache.values())
p25, p75, p90 = np.percentile(vol_vals, 25), np.percentile(vol_vals, 75), np.percentile(vol_vals, 90)
for d, v in vol_cache.items():
    if v < p25:
        reg = "LOW_VOL"
    elif v <= p75:
        reg = "NORMAL_VOL"
    elif v <= p90:
        reg = "HIGH_VOL"
    else:
        reg = "EXTREME_VOL"
```
* **Theoretical Violation:** By calculating `p25, p75, p90` across `vol_vals` (which spans all 375 trading sessions), the threshold that determines whether July 2024 is `LOW_VOL` or `NORMAL_VOL` depends on market volatility observed during the August 2025 sell-off.
* **Correction Required:** A causal 4-state `GaussianHMM` must be calibrated on an expanding or rolling historical window $[t-120, t-1]$, computing the causal forward filtered probability $P(S_t = k | r_{1:t-1})$ using strictly pre-session data.

#### 2.2 Econometric Information Set Filtration
The standard filtration for a 1-step ahead conditional volatility forecast $\hat{\sigma}_t^2$ is:
$$\hat{\sigma}_t^2 = \mathbb{E}[\sigma_t^2 \mid \mathcal{F}_{t-1}]$$
where $\mathcal{F}_{t-1} = \sigma(r_1, r_2, \dots, r_{t-1})$.
* In the existing code, `sub_returns` included $r_t$. The forecast `fit.forecast(horizon=1)` computed $\mathbb{E}[\sigma_{t+1}^2 \mid \mathcal{F}_t]$, which was then mapped to session $t$.
* **Correction Required:** The estimation slice must be strictly defined as:
```python
sub_returns = log_returns[log_returns.index < dt]  # Strictly prior to dt
```

#### 2.3 Intraday Barrier Crossing Priority
When evaluating a short option position with $P_{\mathrm{entry}} = 100$, Target $= 75$, Stop $= 110$:
If on a subsequent session, Low $= 70$ and High $= 115$:
* In the existing code:
```python
if low_p <= pos["target_price"]:
    exit_price = pos["target_price"]
    exit_reason = "ALPHA_HARVESTED"
elif high_p >= pos["stop_price"]:
    exit_price = pos["stop_price"]
    exit_reason = "STOP_LOSS_CUT"
```
* Because `if low_p <= target` evaluates first, the trade exits with $+25\%$ profit, even if the price spiked to $115$ at 09:35 AM and only touched $70$ at 15:20 PM!
* **Correction Required (Conservative Execution Principle):** If both barriers are breached on the same daily bar, the stop-loss must take priority (`STOP_LOSS_CUT`), representing conservative, worst-case intra-bar path assumption in the absence of intraday tick data.

---

### 3. Automated Look-Ahead Verification Test Suite

We construct an automated test (`tests/test_lookahead_causality.py`) that:
1. Artificially mutates future market prices at $t+k$ ($k \ge 1$) and verifies that model inputs, volatility forecasts, and signals at time $t$ remain strictly identical.
2. Verifies that $r_t$ is excluded from the estimation sample for $\hat{\sigma}_t^2$.
3. Verifies that HMM probabilities at time $t$ are computed using the forward algorithm on $r_{1:t-1}$ only.

---
**Document Status:** Complete. Proceeding to Part 4 (P&L Reconciliation & Reconstructing the Entire Backtest).
