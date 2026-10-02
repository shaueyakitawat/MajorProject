# Complete Technical & System Documentation: Quantitative NIFTY 50 Option Mispricing Engine

---

## 1. Executive Summary

This document serves as the master technical specification for the **Quantitative NIFTY Option Mispricing Detection Engine**. 

Designed to operate under the stringent requirements of high-impact journal publications (such as *IEEE Transactions on Knowledge and Data Engineering* and *IEEE Transactions on Computational Finance*), the system detects mispricings in the **NIFTY 50 Index Options market** using a fusion of asymmetric volatility forecasting (**EGARCH**), unsupervised regime classification (**Hidden Markov Model - HMM**), dynamic annualization engines, and analytical Black-Scholes valuation.

---

## 2. Core Quantitative Architecture

The system operates across six integrated mathematical modules:

### Module 1: Data Transformation & Logarithmic Returns
Raw market index prices $S_t$ are converted to continuous log returns to standardize financial variance:
$$r_t = \ln\left(\frac{S_t}{S_{t-1}}\right)$$

### Module 2: EGARCH(1,1) Volatility Forecasting
To model the leverage effect—where negative market shocks trigger higher volatility spikes than positive shocks—the engine uses Exponential GARCH:
$$\ln(\sigma_t^2) = \omega + \alpha \left| \frac{\varepsilon_{t-1}}{\sigma_{t-1}} \right| + \gamma \frac{\varepsilon_{t-1}}{\sigma_{t-1}} + \beta \ln(\sigma_{t-1}^2)$$

### Module 3: HMM Unsupervised Volatility Regime Classification
Market environments are classified into four hidden volatility states using Gaussian HMM:
- **State 0:** Low Volatility (Calm market growth)
- **State 1:** Normal Volatility (Standard market noise)
- **State 2:** High Volatility (Elevated risk)
- **State 3:** Extreme Volatility (Panic sell-offs & market crashes)

### Module 4: Analytical Black-Scholes Fair Value & Greeks
Options theoretical fair value $C(S, K, t)$ and sensitive Greeks ($\Delta, \Gamma, \Theta, \mathcal{V}$) are calculated:
$$C(S, K, t) = S \cdot N(d_1) - K e^{-r t} N(d_2)$$
$$d_1 = \frac{\ln(S/K) + (r + 0.5\sigma^2)t}{\sigma \sqrt{t}}, \quad d_2 = d_1 - \sigma \sqrt{t}$$

### Module 5: Mispricing Signal Detection & Noise Filters
A contract is flagged as **mispriced** if and only if:
1. Percentage Deviation exceeds threshold: $\left| \frac{P_{\text{market}} - P_{\text{fair}}}{P_{\text{fair}}} \right| \ge 3.0\%$
2. Z-Score normalization confirms statistical significance: $Z \ge 1.0$
3. Liquidity and Bid-Ask Spread filters are satisfied: $\text{Spread} \le 5.0\%$

---

## 3. Real NIFTY 50 Empirical Results

Validation was conducted on **1,674 real NIFTY option contracts** (2024–2026 horizon) using actual spot return series and India VIX market feeds:

- **Empirical Precision:** `50.82%`
- **Empirical Recall:** `97.57%`
- **Empirical F1-Score:** `0.6683`
- **Overall Accuracy:** `52.33%`
- **Mean Absolute Error (MAE):** `66.49%`
- **Root Mean Square Error (RMSE):** `222.50%`

### Confusion Matrix
- **True Positives (TP):** `804` (Flagged mispricings that objectively reverted next day)
- **False Positives (FP):** `778` (Flagged mispricings that failed to revert)
- **True Negatives (TN):** `72` (Fairly priced options correctly unflagged)
- **False Negatives (FN):** `20` (Missed mispricing opportunities)

---

## 4. REST API Endpoint Registry (`main.py`)

- `GET /pipeline/spot` — Live NIFTY 50 spot price.
- `GET /pipeline/option-chain` — Full option chain with Greeks, IV, PCR, and strike depth.
- `GET /pipeline/volatility` — EGARCH(1,1) forecast & intraday vol fusion.
- `GET /pipeline/regime` — HMM 4-state market regime classification.
- `GET /pipeline/pricing` — Black-Scholes theoretical fair value calculation.
- `GET /pipeline/mispricing` — Real-time mispricing signal detection.
- `POST /pipeline/backtest` — Out-of-sample quantitative backtester.
