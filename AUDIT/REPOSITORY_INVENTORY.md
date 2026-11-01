# AUDIT/REPOSITORY_INVENTORY.md
## QuantLens Research Codebase: Component & Architecture Inventory

**Audit Date:** 2026-11-01  
**Auditor Roles:** Senior Quantitative Finance Researcher, Derivatives Pricing Specialist, Algorithmic Trading Systems Engineer, Econometrician, Statistical Research Auditor, IEEE Transactions Reviewer.  
**Classification:** Research Audit & Scientific Integrity Baseline.

---

### 1. Executive Overview

The QuantLens repository contains an end-to-end framework designed for options mispricing detection, volatility forecasting, regime classification, and execution modeling in the National Stock Exchange of India (NSE) NIFTY 50 derivatives market.

The repository exhibits a bifurcated evolution:
1. **Production / Live Research Terminal:** FastAPI backend (`backend/services/`) and React/Vite frontend (`frontend/`) wired to live data feeds, paper trading, and local SQLite databases.
2. **Historical Research Scripts:** Separate backtest scripts (`backend/services/csv_options_backtest_engine.py`, `scripts/research_backtest/engine.py`, `scripts/run_empirical_research.py`) that evaluate historical daily option datasets.

This inventory provides a comprehensive, source-verified audit of every component, detailing inputs, outputs, mathematical formulations, observed limitations, and required corrections.

---

### 2. Component Inventory

#### 2.1 Econometric Volatility Modeling
* **File:** `backend/services/volatility_service.py`
* **Purpose:** Calibrates conditional heteroskedasticity models (GARCH, EGARCH) on historical returns and computes intraday realized volatility.
* **Inputs:** Daily index closing prices ($S_t$), intraday 5-minute interval OHLC data.
* **Outputs:** 1-step ahead conditional volatility forecast ($\hat{\sigma}_{t+1}$), annualized decimal volatility, intraday RV proxy.
* **Mathematical Assumptions:**
  * Asymmetric EGARCH(1,1) formulation: $\ln(\sigma_t^2) = \omega + \alpha_1 (|z_{t-1}| - \sqrt{2/\pi}) + \gamma_1 z_{t-1} + \beta_1 \ln(\sigma_{t-1}^2)$.
  * Gaussian error distribution $\epsilon_t \sim \mathcal{N}(0, \sigma_t^2)$.
  * Constant parameter persistence across 60-day rolling estimation window.
* **Existing Problems:**
  * In earlier experiment scripts, `arch_model` was called with `vol='EGARCH', p=1, q=1` (omitting `o=1`), fitting a symmetric EGARCH without the leverage parameter ($\gamma_1=0$).
  * QLIKE loss exploded to $1.85 \times 10^8$ on unconstrained small-sample convergence failures.
  * Live pipeline applies dynamic clipping `[0.08, 0.40]` which masks optimizer divergence.
* **Required Modifications:**
  * Enforce strictly specified `p=1, o=1, q=1` with convergence checks.
  * Report optimizer convergence flags and discard/flag non-converged sessions.
  * Evaluate Student-$t$ innovations to accommodate excess kurtosis in Indian index returns.

---

#### 2.2 Hidden Markov Model (HMM) Regime Classifier
* **File:** `backend/services/regime_service.py`
* **Purpose:** Classifies macroeconomic volatility environments into latent market states.
* **Inputs:** Rolling 20-day annualized standard deviation of logarithmic returns.
* **Outputs:** Latent state label (0, 1, 2, 3), filtered state probabilities $P(S_t = k | \mathcal{F}_t)$.
* **Mathematical Assumptions:**
  * First-order 4-state Markov chain with Gaussian emission distributions $\mathcal{N}(\mu_k, \sigma_k^2)$.
  * Stationary transition probability matrix $A = [a_{ij}]$.
* **Existing Problems:**
  * Causal filtered probabilities ($P(S_t | r_{1:t})$) must be strictly distinguished from full-sample smoothed probabilities ($P(S_t | r_{1:T})$).
  * State label switching: State IDs (0, 1, 2, 3) are arbitrary without sorting by emission mean ($\mu_k$).
  * The published paper claimed 4 latent states but reported only 3 in performance tables (State 3 was suppressed).
* **Required Modifications:**
  * Sort states deterministically by emission mean $\mu_0 < \mu_1 < \mu_2 < \mu_3$ to ensure stable mapping to `LOW_VOL`, `NORMAL_VOL`, `HIGH_VOL`, `EXTREME_VOL`.
  * Ensure causal forward algorithm only; zero backward smoothing in historical decision-making.
  * Report all 4 states in empirical performance breakdowns.

---

#### 2.3 Black-Scholes-Merton (BSM) Analytical Pricing & Greeks Engine
* **File:** `backend/services/pricing_service.py` & `backend/services/csv_options_backtest_engine.py`
* **Purpose:** Computes continuous-dividend closed-form European option fair values and analytical Greeks.
* **Inputs:** Spot price ($S$), Strike ($K$), Time-to-maturity ($T$), Risk-free rate ($r$), Dividend yield ($q$), Model volatility ($\sigma$).
* **Outputs:** Fair Call ($C_{\mathrm{fair}}$), Fair Put ($P_{\mathrm{fair}}$), Delta ($\Delta$), Gamma ($\Gamma$), Vega ($\mathcal{V}$), Theta ($\Theta$).
* **Mathematical Assumptions:**
  * Merton (1973) continuous dividend yield extension of Black-Scholes (1973).
  * Geometric Brownian motion with constant volatility over contract life.
  * Risk-free rate $r = 6.50\%$ (constant T-bill rate), dividend yield $q = 1.25\%$.
* **Existing Problems:**
  * Assumes constant $r$ and $q$ across all maturities and historical dates.
  * Minimum time-to-maturity was clamped to $0.5 / 365$, preventing expired contracts from collapsing to pure intrinsic value at $T=0$.
  * Put-Call parity consistency checks were not automated across strike chains.
* **Required Modifications:**
  * Implement explicit expiry boundary: $T = 0 \implies C = \max(0, S-K), P = \max(0, K-S)$.
  * Add automated Put-Call Parity validation tests across option chains.

---

#### 2.4 Numerical Implied Volatility (IV) Solver & VRP Calculator
* **Files:** `backend/services/implied_volatility_service.py`, `backend/services/vrp_service.py`
* **Purpose:** Inverts market prices to obtain contract-specific implied volatility and computes the Volatility Risk Premium spread.
* **Inputs:** Observed market price ($P_{\mathrm{mkt}}$), $S$, $K$, $T$, $r$, $q$, Econometric forecast ($\sigma_{\mathrm{model}}$).
* **Outputs:** Implied Volatility ($\sigma_{\mathrm{IV}}$), Volatility Risk Premium ($\mathrm{VRP} = \sigma_{\mathrm{IV}} - \sigma_{\mathrm{model}}$).
* **Mathematical Assumptions:**
  * Brent's method / bisection bounded within $[0.005, 3.50]$.
  * $\mathrm{VRP}$ defined as a linear spread between risk-neutral IV ($\mathbb{Q}$) and physical forecast ($\mathbb{P}$).
* **Existing Problems:**
  * The term "Variance Risk Premium" in academic literature (Carr & Wu, 2009) formally refers to $\mathbb{E}^\mathbb{Q}[Var] - \mathbb{E}^\mathbb{P}[Var]$ derived from synthetic variance swap portfolios. Computing $\sigma_{\mathrm{IV}} - \sigma_{\mathrm{model}}$ is an Implied-Realized Volatility Spread Proxy, not a true synthetic variance swap VRP.
  * Deep OTM options near intrinsic value produce numerical instability or fail Brent root-finding.
* **Required Modifications:**
  * Document the terminology clearly: designate $\sigma_{\mathrm{IV}} - \sigma_{\mathrm{model}}$ as the "Implied Volatility Spread Proxy ($\mathrm{IVS}$)".
  * Reject contracts violating no-arbitrage bounds ($P_{\mathrm{mkt}} < \text{intrinsic}$) before calling Brent's solver.

---

#### 2.5 Statistical Mispricing M-Score Framework
* **File:** `backend/services/mispricing_service.py`
* **Purpose:** Synthesizes relative price deviation, VRP, Vega, and Gamma into a normalized dislocation score.
* **Inputs:** Relative deviation $\mathrm{dev} = (P_{\mathrm{mkt}} - P_{\mathrm{fair}})/P_{\mathrm{fair}}$, $\mathrm{VRP}$, Vega, Gamma.
* **Outputs:** Composite $M$-Score, Signal Classification (`OVERPRICED`, `UNDERPRICED`, `FAIR`).
* **Mathematical Formulation (Equation 8):**
  $$M\text{-Score} = w_p \left(\frac{\mathrm{dev}}{0.05}\right) + w_v \left(\frac{\mathrm{VRP}}{0.02}\right) + w_{\mathcal{V}} \cdot \mathrm{sgn}(\mathrm{dev})\cdot \min\left(2.5, \frac{\mathcal{V}}{15.0}\right) + w_{\Gamma}\cdot \mathrm{sgn}(\mathrm{dev})\cdot \min\left(2.5, \frac{\Gamma}{0.0003}\right)$$
  with weights $(0.50, 0.20, 0.15, 0.10)$.
* **Existing Problems:**
  * **Dimensional Inconsistency:** The four components have fundamentally different scales and dimensions: percentage price deviation (dimensionless), VRP (annualized volatility points), Vega (rupees per 1% vol), and Gamma (delta change per index point). Normalizing by ad-hoc denominators ($0.05, 0.02, 15.0, 0.0003$) lacks statistical derivation.
  * **Greek Amplification vs. Penalty:** Multiplying by $\mathrm{sgn}(\mathrm{dev})$ causes high Vega and Gamma to *increase* the absolute M-score, encouraging entries into contracts with extreme gamma risk rather than penalizing tail exposure.
  * **Double Counting:** Both $\mathrm{dev}$ and $\mathrm{VRP}$ are monotonic transformations of the market price $P_{\mathrm{mkt}}$ relative to BSM fair value.
* **Required Modifications:**
  * Conduct a formal ablation study (Price Dev only vs. +VRP vs. +Greeks vs. Full Model).
  * Use cross-sectional standardization ($z$-scores across the contemporaneous strike surface) to guarantee dimensional consistency.

---

#### 2.6 Historical Options Walk-Forward Backtesting Engine
* **File:** `backend/services/csv_options_backtest_engine.py`
* **Purpose:** Executes the 8-stage mispricing strategy on historical NIFTY options database (`data/nifty_options_daily_tradable.csv`).
* **Inputs:** 346,156 tradable contracts across 375 trading sessions (July 1, 2024 to December 31, 2025).
* **Outputs:** Trade ledger (1,964 trades), daily equity curve, performance ratios.
* **Critical Findings & Bugs Uncovered:**
  1. **CRITICAL EXPIRY SETTLEMENT BUG (SMOKING GUN):**
     * On expiry day, `exit_price` was extracted as: `exit_price = quote["settlement"] if quote["settlement"] > 0 else close_p`.
     * In the official NSE Bhavcopy dataset, on expiration day, the `settlement` column for expiring options contains the **NIFTY 50 index spot settlement price**, NOT the option premium!
     * Example Trade BT-0459 (NIFTY 25650 PE on 2024-10-24): Bought at ₹1,050.00. The code assigned `exit_price = 24399.40` (the NIFTY index close), generating a fake net profit of **₹45,44,028.67** on a single trade!
     * Example Trade BT-1530 (NIFTY 25900 PE on 2025-08-26): Assigned `exit_price = 24868.60`, generating a fake net profit of **₹46,34,287.64** on a single trade!
     * **Impact:** These two erroneous trades alone accounted for **₹91,78,316.31 (86.9%)** of the entire reported ₹1.05 Crore net P&L!
  2. **Intraday Target/Stop Evaluation Bias:**
     * Code evaluated `if low_p <= target: exit_price = target` before checking `elif high_p >= stop`. On volatile days where both bounds were touched, the model always credited a profit.
  3. **Execution Assumption:**
     * Trades were entered at `close_px` on the day the signal was detected, which is an end-of-day execution assumption rather than an intraday 09:30 entry.
* **Required Modifications:**
  * Correct option cash settlement: Intrinsic value at expiry is $\max(0, S_T - K)$ for Calls and $\max(0, K - S_T)$ for Puts.
  * Evaluate conservative stop-loss priority or next-day open execution.
  * Reconstruct the genuine, uncorrupted performance ledger.

---

#### 2.7 Transaction Cost & Regulatory Friction Engine
* **File:** `backend/services/csv_options_backtest_engine.py:estimate_round_trip_friction`
* **Purpose:** Computes Indian exchange and statutory deductions.
* **Existing Implementation:**
  * Fixed Brokerage: ₹20 entry + ₹20 exit.
  * Uniform STT: 0.125% on sell turnover.
  * Exchange Turnover Fee: 0.053%.
  * GST: 18% on (Brokerage + Exchange).
  * Stamp Duty: 0.003% on buy turnover.
* **Existing Problems:**
  * Applies a single static tax rate across all historical periods.
  * Indian Budget 2024 revised STT effective October 1, 2024: STT on sale of an option in securities was raised from **0.0625% to 0.10%** of premium (0.125% was the futures rate).
  * Ignores SEBI turnover fee (₹10 per crore).
  * Does not distinguish between in-the-money cash exercise settlement fees and regular secondary market trading.
* **Required Modifications:**
  * Implement a centralized, historically versioned `CostEngine` with date-effective tax brackets.

---

#### 2.8 Forward Live Paper Trading Engine & SQLite Storage
* **Files:** `scripts/live_paper_trader.py`, `backend/services/trade_service.py`, `data/nifty_live_snapshots.db`
* **Purpose:** Asynchronous live paper execution on streaming market quotes during NSE trading hours.
* **Inputs:** Live option-chain snapshots, real-time index spot ticks.
* **Outputs:** `live_paper_trades` table (911 rows recorded in `data/nifty_live_snapshots.db`).
* **Existing State:**
  * 911 audited rows exist with timestamps, entry/exit prices, Greek sensitivities, and exit reasons.
  * Performance: 431 wins / 479 losses (47.36% raw hit rate) with gross PnL -₹47.2K and net PnL -₹93.1K after ₹45.9K friction.
  * In `paper.tex`, the forward testing results were artificially embellished to claim +₹12.48 Lakhs net P&L and 61.8% win rate.
* **Required Modifications:**
  * Publish the actual, empirical 911-trade live forward performance without embellishment.
  * Analyze the gap between backtested assumptions and live forward paper fills (bid-ask spread crossing, market timing, theta decay).

---

### 3. Summary of Component Audit Status

| Component | File Path | Current Status | Scientific Integrity Issue | Required Action |
| :--- | :--- | :--- | :--- | :--- |
| **Data Ingestion** | `data/nifty_options_daily_tradable.csv` | Daily Bhavcopy | Missing intraday quote resolution | Model as Daily EOD or next-day Open |
| **Volatility Model** | `backend/services/volatility_service.py` | Partially Confirmed | Symmetric EGARCH used; QLIKE explosion | Fit asymmetric `p=1, o=1, q=1` with convergence flags |
| **HMM Classifier** | `backend/services/regime_service.py` | Partially Confirmed | 4 states trained; 1 state omitted in paper | Order states by emission mean; report all 4 |
| **Pricing Engine** | `backend/services/pricing_service.py` | Confirmed BSM | Constant $r=6.5\%$; clamp at $T=0.5/365$ | Set $T=0$ intrinsic boundary; check parity |
| **IV Solver** | `backend/services/implied_volatility_service.py` | Confirmed Brent | No-arbitrage bound check missing | Reject $P < \text{intrinsic}$; name IVS spread |
| **M-Score** | `backend/services/mispricing_service.py` | Inconsistent | Dimensional mismatch; Greek amplification | Cross-sectional standardization; ablation |
| **Backtest Engine** | `backend/services/csv_options_backtest_engine.py` | **CRITICAL BUG** | **Spot price used as option settlement in 2 trades** | **Fix settlement formula; reconstruct clean ledger** |
| **Cost Engine** | `backend/services/csv_options_backtest_engine.py` | Simplistic | Static STT rate; wrong post-2024 rate | Versioned cost engine with Oct 1, 2024 split |
| **Forward Trader** | `scripts/live_paper_trader.py` | 911 Real Rows | Paper figures were inflated in manuscript | Report actual empirical telemetry |

---
**Document Status:** Complete and verified against source repository. Proceeding to Part 3 (Historical Data and Look-Ahead Audit).

