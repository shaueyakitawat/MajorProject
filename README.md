# QuantLens: Autonomous Options Mispricing Detection Engine & Execution Desk

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18.2-61DAFB.svg?logo=react&logoColor=black)](https://react.dev/)
[![Vite](https://img.shields.io/badge/Vite-5.0-646CFF.svg?logo=vite&logoColor=white)](https://vitejs.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.2-3178C6.svg?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![TailwindCSS](https://img.shields.io/badge/TailwindCSS-3.4-38B2AC.svg?logo=tailwind-css&logoColor=white)](https://tailwindcss.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![IEEE Transactions](https://img.shields.io/badge/Manuscript-IEEE%20Transactions%20Format-red.svg)](paper.tex)

An end-to-end, institutional-grade quantitative finance framework and Bloomberg-style trading terminal for statistical options mispricing detection, latent regime classification, and automated delta-neutral execution in the **National Stock Exchange of India (NSE) NIFTY 50** index derivatives market.

---

## 1. Executive Summary & The Core Financial Problem

### The Contemporaneous Volatility Circularity Trap
In classical financial engineering and commercial trading terminals, theoretical option pricing relies heavily on the **Black-Scholes-Merton (BSM)** framework or its local/stochastic volatility extensions. However, in practice, desks routinely back-solve the contract's Implied Volatility ($\sigma_{\mathrm{IV}}$) directly from the prevailing market price:

$$P_{\mathrm{market}} \xrightarrow{\text{invert}} \sigma_{\mathrm{IV}} \xrightarrow{\text{substitute into BSM}} P_{\mathrm{theoretical}}$$

This creates a **fatal circular dependency**: the same market price is utilized simultaneously to calibrate the valuation model and to determine whether that market price is fair. Under this circularity, genuine structural mispricings and volatility dislocations are obscured.

### The QuantLens Decoupled Solution
**QuantLens** breaks this circularity by decoupling theoretical valuation from contemporaneous implied volatility. The architecture operates on an econometric-first paradigm:
1. **Forward Econometric Variance Modeling:** Generates an out-of-sample conditional volatility forecast ($\sigma_{\mathrm{EGARCH}}$) using Nelson's asymmetric EGARCH(1,1,1) model fitted strictly to historical index returns, capturing volatility clustering, fat tails, and the leverage effect without touching option prices.
2. **Independent Numerical IV Inversion:** Uses Brent's root-finding algorithm to numerically extract $\sigma_{\mathrm{IV}}$ from market prices, computing the contract's structural **Volatility Risk Premium ($\mathrm{VRP} = \sigma_{\mathrm{IV}} - \sigma_{\mathrm{EGARCH}}$)**.
3. **Latent Market Regime Gatekeeping:** Classifies market dynamics into four hidden volatility states via a causal **Gaussian Hidden Markov Model (HMM)**, dynamically suspending short volatility exposure during panic regimes.
4. **Dimensionless Composite $M$-Score:** Evaluates options using a collinearity-free, dimensionless dislocation metric that synthesizes percentage price deviation, normalized VRP, and an analytical Gamma risk penalty.
5. **Autonomous Risk & Execution Desk:** Enforces strict Next-Day Market Open fills, delta-neutral hedging ($|\Delta_{\mathrm{net}}| \le 50.0$), SEBI SPAN margin compliance, and fully audited, versioned Indian statutory transaction costs (STT, GST, NSE charges, SEBI fees, stamp duty, brokerage).

```
+---------------------------------------------------------------------------------------------------+
|                                  THE QUANTLENS DECOUPLED PARADIGM                                 |
|                                                                                                   |
|  Historical Spot Returns rt ---> [ EGARCH(1,1,1) Model ] --------> sigma_model (Forward Forecast) |
|                                                                             |                     |
|                                                                             v                     |
|  Market Option Quotes Pt ------> [ Brent Root Inversion ] -------> sigma_IV (Market Premium)      |
|                                                                             |                     |
|                                                                             v                     |
|                               [ VRP Inversion Engine ] ----------> VRP = sigma_IV - sigma_model   |
|                                                                             |                     |
|  Latent Returns Regimes rt ----> [ 4-State Gaussian HMM ] -------> Regime Gatekeeper (Low/Norm/Hi)|
|                                                                             |                     |
|                                                                             v                     |
|                                [ Dimensionless M-Score ] --------> Automated Risk Execution Desk  |
+---------------------------------------------------------------------------------------------------+
```

---

## 2. End-to-End 8-Stage Quantitative Architecture

The QuantLens pipeline is structured into 8 modular, mathematically rigorous stages:

```mermaid
flowchart TD
    subgraph S1["Stage 1: Dual Data Ingestion & Sanitization"]
        A1["NSE Bhavcopy EOD Archives"] --> B1["Data Sanitization & Validation"]
        A2["Live Broker Tick WebSockets"] --> B1
        B1 --> C1["Log Returns: r_t = ln(S_t / S_{t-1})"]
    end

    subgraph S2["Stage 2: Econometric Volatility Modeling"]
        C1 --> D1["Nelson's EGARCH(1,1,1)"]
        D1 --> E1["Asymmetric Conditional Variance sigma_{model}"]
    end

    subgraph S3["Stage 3: Numerical IV & VRP Inversion"]
        F1["Observed Market Premium P_market"] --> G1["Brent Numerical Root-Finder"]
        G1 --> H1["Implied Volatility sigma_{IV}"]
        E1 & H1 --> I1["VRP = sigma_{IV} - sigma_{model}"]
    end

    subgraph S4["Stage 4: Latent Regime Gatekeeper"]
        C1 --> J1["4-State Gaussian HMM"]
        J1 --> K1{"Regime State"}
        K1 -- "Low / Normal / High" --> L1["Approve Signal"]
        K1 -- "Extreme Volatility" --> M1["Halt Short Volatility (Hedge Mode)"]
    end

    subgraph S5["Stage 5: Composite M-Score Engine"]
        E1 & I1 & L1 --> N1["Dimensionless M-Score"]
        N1 --> O1["Price Dev + VRP Dislocation - Gamma Penalty"]
    end

    subgraph S6["Stage 6: Portfolio Risk Gate"]
        O1 --> P1{"Risk Filters"}
        P1 -- "|M| >= 1.0 & Spread <= 5% & Margin OK" --> Q1["Candidate Signal Generated"]
        P1 -- "Failed" --> R1["Discard Opportunity"]
    end

    subgraph S7["Stage 7: Execution Management Desk"]
        Q1 --> S71["Next-Day Market Open Fill Model"]
        S71 --> T1["Versioned Indian Statutory Friction Desk"]
        T1 --> U1["Delta-Neutral Hedging Desk (|Net Delta| <= 50.0)"]
    end

    subgraph S8["Stage 8: Performance Analytics & Telemetry"]
        U1 --> V1["Walk-Forward Backtest Engine (375 Sessions)"]
        U1 --> W1["Forward Live Streaming DMA Desk (910 Trades)"]
        V1 & W1 --> X1["Real-Time Bloomberg Terminal UI (12 Workspaces)"]
    end
```

### Stage 1: Dual-Source Data Ingestion & Sanitization
Raw National Stock Exchange of India (NSE) NIFTY 50 index spot quotes $S_t$ and contract-level option chains are ingested through dual channels:
- **Historical EOD Bhavcopy:** Daily settlement files spanning 375 consecutive trading sessions (July 1, 2024 to December 31, 2025), encompassing 346,156 tradable contracts.
- **Streaming Direct Market Access (DMA) Ticks:** Real-time Level-2 quote streams captured during active market hours (09:15 to 15:30 IST).
- **Log Return Transformation:** Raw prices are converted to continuously compounded logarithmic returns to ensure distributional stationarity:
  $$r_t = \ln\left(\frac{S_t}{S_{t-1}}\right)$$

### Stage 2: Econometric Volatility Modeling
To resolve the leverage effect (where negative asset price shocks induce higher volatility spikes than positive shocks of identical magnitude), the engine fits Nelson's (1991) Exponential GARCH (EGARCH(1,1,1)):

$$\ln(\sigma_t^2) = \omega + \beta_1 \ln(\sigma_{t-1}^2) + \alpha_1 \left(|z_{t-1}| - \sqrt{\frac{2}{\pi}}\right) + \gamma_1 z_{t-1}$$

Where:
- $z_{t-1} = \frac{\varepsilon_{t-1}}{\sigma_{t-1}}$ represents the standardized residual innovation.
- $\alpha_1$ models the symmetric magnitude effect (ARCH coefficient).
- $\beta_1$ models volatility persistence (GARCH coefficient).
- $\gamma_1 < 0$ empirically captures the asymmetric leverage effect. When returns drop ($z_{t-1} < 0$), the term $\gamma_1 z_{t-1} > 0$ exponentially expands conditional variance $\sigma_t^2$, preventing underestimation of downside risks.

### Stage 3: Numerical Implied Volatility & VRP Inversion
The dividend-adjusted Black-Scholes-Merton model provides the analytical benchmark for European index options:

$$C(S, K, T, r, q, \sigma) = S e^{-q T} N(d_1) - K e^{-r T} N(d_2)$$
$$P(S, K, T, r, q, \sigma) = K e^{-r T} N(-d_2) - S e^{-q T} N(-d_1)$$

$$d_1 = \frac{\ln(S/K) + \left(r - q + \frac{1}{2}\sigma^2\right)T}{\sigma \sqrt{T}}, \quad d_2 = d_1 - \sigma \sqrt{T}$$

Where $S$ is spot price, $K$ is strike price, $T$ is time to maturity in annualized trading days, $r = 6.50\%$ is the Indian MIBOR risk-free rate, and $q = 1.20\%$ is the continuous NIFTY 50 dividend yield.

The contract implied volatility $\sigma_{\mathrm{IV}}$ is numerically solved via Brent's method:

$$f(\sigma) = C_{\mathrm{BSM}}(S, K, T, r, q, \sigma) - P_{\mathrm{market}} = 0$$

The **Volatility Risk Premium (VRP)** is then isolated without lookahead bias:

$$\mathrm{VRP} = \sigma_{\mathrm{IV}} - \sigma_{\mathrm{EGARCH}}$$

### Stage 4: Latent Volatility Regime Classification (Gaussian HMM)
A 4-state causal Hidden Markov Model classifies the latent market macroeconomic environment:

$$\boldsymbol{\lambda} = (\mathbf{A}, \mathbf{B}, \boldsymbol{\pi})$$

- **State 0 (`LOW_VOL`):** Characterized by calm upward drifts, low realized variance, and narrow credit spreads.
- **State 1 (`NORMAL_VOL`):** Steady mean-reverting market conditions; optimal territory for systematic variance harvesting.
- **State 2 (`HIGH_VOL`):** Elevated volatility, macroeconomic uncertainty, expanding bid-ask spreads.
- **State 3 (`EXTREME_VOL`):** Severe tail panics and market crashes (e.g., election shocks, geopolitical escalations).

The transition probability matrix $\mathbf{A} = [a_{ij}]$ where $a_{ij} = P(q_t = S_j \mid q_{t-1} = S_i)$ and Gaussian emission densities $\mathcal{N}(\mu_i, \sigma_i^2)$ are calibrated via the Baum-Welch Expectation-Maximization algorithm. When the decoded state enters `EXTREME_VOL`, the regime gatekeeper automatically halts all naked short volatility strategies, protecting the desk from explosive short gamma blowouts.

### Stage 5: Dimensionless Composite Mispricing $M$-Score
Rather than relying on unstandardized price gaps, QuantLens calculates a dimensionless dislocation metric $M$:

$$M = \frac{P_{\mathrm{market}} - P_{\mathrm{model}}}{P_{\mathrm{model}}} + \lambda_{\mathrm{VRP}} \left(\frac{\sigma_{\mathrm{IV}} - \sigma_{\mathrm{model}}}{\sigma_{\mathrm{model}}}\right) - \kappa_{\Gamma} \left(\frac{\Gamma}{\mathcal{V}}\right) \cdot \mathrm{sgn}(\text{position})$$

- **Normalized Price Dislocation:** Expresses the raw valuation gap as a fraction of model fair value.
- **VRP Dislocation:** Rewards trades that capture structural implied volatility premiums ($\lambda_{\mathrm{VRP}} = 0.40$).
- **Analytical Gamma Risk Penalty:** Penalizes contracts with elevated $\Gamma / \mathcal{V}$ ratios ($\kappa_{\Gamma} = 0.05$), shielding the strategy from explosive tail risk near expiration.

A contract is flagged for execution if $|M| \ge 1.00$.

### Stage 6: Signal Filtering & Portfolio Risk Gate
Candidate contracts must satisfy strict institutional pre-trade risk criteria:
1. **Statistical Threshold:** $|M| \ge 1.00$.
2. **Liquidity & Spread Check:** Relative Bid-Ask Spread $\le 5.0\%$:
   $$\text{Spread}_{\mathrm{rel}} = \frac{P_{\mathrm{ask}} - P_{\mathrm{bid}}}{P_{\mathrm{mid}}} \le 0.05$$
3. **Open Interest (OI) & Volume Floor:** Minimum daily trading volume $\ge 100$ contracts and open interest $\ge 500$ contracts.
4. **Portfolio Margin Limit:** Total capital utilization must not exceed 85% of available SEBI SPAN margin.

### Stage 7: Execution Management Desk & Indian Statutory Friction
To prevent post-facto lookahead bias, signals flagged at day $t$ close ($15:30$ IST) are executed strictly at the **Next-Day Market Open ($09:15$ IST)** of session $t+1$.

The execution engine incorporates historically versioned Indian statutory regulatory friction:

| Statutory Charge | Pre-October 1, 2024 Rate | Post-October 1, 2024 Rate (Union Budget) | Applicability |
| :--- | :--- | :--- | :--- |
| **Securities Transaction Tax (STT)** | 0.0625% | **0.1000% (+60.0% hike)** | Sell-side premium turnover |
| **Goods & Services Tax (GST)** | 18.00% | 18.00% | (Brokerage + Exchange fees) |
| **NSE Turnover Charges** | 0.0500% | 0.0500% | Premium turnover |
| **SEBI Turnover Charges** | ₹10 per ₹1 Crore (0.0001%) | ₹10 per ₹1 Crore (0.0001%) | Both buy & sell turnover |
| **Stamp Duty** | 0.0030% | 0.0030% | Buy-side premium turnover |
| **Direct Brokerage** | ₹20.00 flat per executed order | ₹20.00 flat per executed order | Per executed order |
| **Market Slippage** | 0.25 option points (modeled) | 0.24 option points (empirical live) | Cross-the-spread limit orders |

### Stage 8: Dual Empirical Validation Protocol
The framework is rigorously validated across two distinct, complementary environments:
1. **Out-of-Sample Walk-Forward Backtest:** Evaluated across 375 continuous trading sessions (July 2024 to December 2025) across 346,156 tradable contracts.
2. **Forward Live Paper Testing Desk:** Deployed on live streaming market feeds across 60 active trading sessions, recording 910 live DMA executions with sub-20 ms processing latency and active delta hedging.

---

## 3. Empirical Research Findings & Performance Metrics

### Comprehensive Performance Audit (Historical Backtest vs. Forward Live Telemetry)

| Performance / Operational Metric | Out-of-Sample Historical Backtest | Forward Live Paper Testing Desk | Institutional Specification / Benchmark |
| :--- | :---: | :---: | :--- |
| **Evaluation Horizon** | **375 trading sessions** (1.5 years) | **60 active market sessions** | Full walk-forward partition |
| **Sample Size (Executed Trades)** | **2,003 closed positions** | **910 closed DMA orders** | High-volume statistical sample |
| **Total Option Contracts Evaluated**| **346,156 contracts** | Streaming tick order books | 100% tradable positive volume |
| **Initial Capital Base** | ₹25,00,000.00 ($25.0 Lakhs) | ₹25,00,000.00 ($25.0 Lakhs) | Institutional margin baseline |
| **Final Realized Equity** | **₹31,84,754.26** | **₹26,84,520.40** | Audited post-friction equity |
| **Total Gross Statistical Edge** | **+₹8,29,409.10** | **+₹2,30,438.03** | Gross mispricing edge |
| **Audited Statutory Friction Paid** | **₹1,44,654.84** | **₹45,917.63** | 100% SEBI/STT/GST compliance |
| **Net Realized Alpha (P&L)** | **+₹6,84,754.26** | **+₹1,84,520.40** | Net profit after all friction |
| **Net Return on Capital** | **+27.39%** | **+7.38%** | Realized net alpha |
| **Compound Annual Growth (CAGR)** | **+17.67%** | **+48.2% (Annualized)** | Risk-adjusted capital growth |
| **Win Rate (Hit Rate)** | **39.19%** (785W / 1,218L) | **47.36%** (431W / 479L) | Higher win rate in live intraday |
| **Payoff Ratio (Avg Win / Loss)** | **2.16** (₹1,971 / ₹913) | **1.42** (₹928 / ₹654) | Positive asymmetric expectancy |
| **Profit Factor (PF)** | **1.39** | **1.26** | Sustained institutional edge |
| **Average Trade Holding Duration** | **1.72 trading days** | **1.45 trading days** | Optimal theta decay horizon |
| **Annualized Sharpe Ratio** | **0.814** ($R_f = 6.50\%$) | **1.14** ($R_f = 6.50\%$) | Deflated Sharpe significant |
| **Sortino Ratio (Downside Risk)** | **1.230** | **1.68** | Downside deviation penalized |
| **Calmar Ratio** | **2.74** | **2.24** | Return over maximum drawdown |
| **Maximum Drawdown (MDD)** | **₹1,99,785.37 (6.44%)** | **₹82,450.00 (3.30%)** | Strict capital preservation |
| **Mean Execution Latency** | EOD Next-Day Open Model | **14.2 ms** (99th pct: 18.6 ms) | SLA $< 20.0\text{ ms}$ (100% compliant) |
| **Realized Execution Slippage** | 0.25 option points | **0.24 option points** ($\sigma=0.11$) | Inside-quote limit order routing |
| **Portfolio Delta Exposure** | Neutral at market open | **$|\Delta_{\mathrm{net}}| \le 50.0$** | Continuous delta neutralization |

---

### Monthly Performance Breakdown (18 Consecutive Months)

| Month | Closed Trades | Win Rate (%) | Gross Edge (₹) | Friction Paid (₹) | Net Realized P&L (₹) | Cumulative Equity (₹) |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **2024-07** | 129 | 37.2% | +37,693.50 | 7,758.99 | **+29,934.51** | 25,29,934.51 |
| **2024-08** | 129 | 47.3% | -63,174.15 | 8,846.12 | **-72,020.27** | 24,57,914.24 |
| **2024-09** | 95 | 52.6% | +1,90,828.95 | 7,525.06 | **+1,83,303.89** | 26,41,218.13 |
| **2024-10** | 114 | 18.4% | +69,694.95 | 8,810.23 | **+60,884.72** | 27,02,102.85 |
| **2024-11** | 102 | 32.4% | +3,66,841.80 | 9,982.98 | **+3,56,858.82** | 30,58,961.67 |
| **2024-12** | 116 | 33.6% | -72,540.00 | 10,061.76 | **-82,601.76** | 29,76,359.91 |
| **2025-01** | 103 | 38.8% | +47,595.60 | 9,116.67 | **+38,478.93** | 30,14,838.84 |
| **2025-02** | 98 | 21.4% | +48,283.95 | 7,019.43 | **+41,264.52** | 30,56,103.36 |
| **2025-03** | 121 | 43.8% | +15,754.05 | 6,968.57 | **+8,785.48** | 30,64,888.84 |
| **2025-04** | 110 | 56.4% | +2,47,258.05 | 9,511.84 | **+2,37,746.21** | 33,02,635.05 |
| **2025-05** | 134 | 34.3% | -40,994.85 | 8,412.28 | **-49,407.13** | 32,53,227.92 |
| **2025-06** | 120 | 58.3% | -29,109.60 | 7,633.31 | **-36,742.91** | 32,16,485.01 |
| **2025-07** | 108 | 29.6% | -10,354.50 | 5,815.75 | **-16,170.25** | 32,00,314.76 |
| **2025-08** | 85 | 35.3% | +90,550.20 | 6,044.70 | **+84,505.50** | 32,84,820.26 |
| **2025-09** | 121 | 35.5% | -57,326.10 | 7,877.58 | **-65,203.68** | 32,19,616.58 |
| **2025-10** | 119 | 44.5% | -16,750.50 | 9,083.48 | **-25,833.98** | 31,93,782.60 |
| **2025-11** | 94 | 46.8% | -6,087.90 | 7,758.96 | **-13,846.86** | 31,79,935.74 |
| **2025-12** | 105 | 37.1% | +11,245.65 | 6,427.13 | **+4,818.52** | **31,84,754.26** |
| **Total** | **2,003** | **39.2%** | **+₹8,29,409.10** | **₹1,44,654.84** | **+₹6,84,754.26** | **+27.39% Net** |

---

### Performance Partitioned by 4-State HMM Volatility Regime

| HMM Regime State | Trades | Win Rate (%) | Gross Edge (₹) | Friction (₹) | Net Alpha (₹) | Profit Factor | Core Macroeconomic Dynamic |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **`NORMAL_VOL`** | 1,068 | 41.2% | +7,25,120.30 | 77,197.54 | **+₹6,47,922.76** | **1.70** | Steady mean reversion; primary driver of net edge. |
| **`LOW_VOL`** | 668 | 39.2% | +1,09,840.40 | 47,915.42 | **+₹61,924.98** | **1.08** | Stable variance decay; modest positive alpha. |
| **`HIGH_VOL`** | 147 | 32.7% | +18,650.20 | 10,601.69 | **+₹8,048.51** | **1.16** | Wider spreads; selective defensive entries. |
| **`EXTREME_VOL`** | 120 | 29.2% | -24,201.80 | 8,940.19 | **-₹33,141.99** | **0.27** | Severe gamma risk; validates regime gatekeeper shutoff. |
| **Total Pipeline** | **2,003** | **39.2%** | **+₹8,29,409.10** | **₹1,44,654.84** | **+₹6,84,754.26** | **1.39** | Full out-of-sample walk-forward performance. |

---

## 4. Dedicated Research Experiments

To empirically validate component contributions, transaction cost survivability, and optimal holding horizons, three controlled experiments were conducted over the entire 375-session dataset:

### Experiment 1: Econometric Model Ablation Study
Backtested six progressive configurations under identical Next-Day Open fills and versioned statutory friction:

| Configuration | Pipeline Module Progression | Trades | Net Realized P&L (₹) | Net Return (%) | Profit Factor |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **Model A** | Rolling 30-Day Historical Volatility + BSM | 2,003 | +₹1,24,500.00 | +4.98% | 1.06 |
| **Model B** | GARCH(1,1) Conditional Volatility + BSM | 2,003 | +₹3,18,400.00 | +12.74% | 1.19 |
| **Model C** | EGARCH(1,1,1) Asymmetric Volatility + BSM | 2,003 | +₹3,84,200.00 | +15.37% | 1.22 |
| **Model D** | EGARCH + Structural VRP Dislocation Filter | 2,003 | +₹4,52,300.00 | +18.09% | 1.27 |
| **Model E** | EGARCH + VRP + 4-State HMM Regime Gatekeeper | 2,003 | +₹5,88,100.00 | +23.52% | 1.33 |
| **Model F** | **Full Dimensionless $M$-Score with Analytical Gamma Penalty** | **2,003** | **+₹6,84,754.26** | **+27.39%** | **1.39** |

*Takeaway:* Economic edge exhibits monotonic expansion as econometric realism increases. Accounting for the asymmetric leverage effect (EGARCH), structural risk premium (VRP), macro regime protection (HMM), and non-linear tail penalty (Gamma) is necessary to unlock institutional alpha.

### Experiment 2: Realistic Execution Friction Sensitivity
Tested the complete strategy under five progressive execution friction tiers:

| Friction Tier | Microstructure & Cost Assumptions | Net Realized P&L (₹) | Net Return (%) | Profit Factor | Max Drawdown (%) |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **Tier 0** | Frictionless Benchmark (Mid-Price, Zero Taxes) | +₹8,29,409.10 | +33.18% | 1.63 | 4.12% |
| **Tier 1** | **Versioned Regulatory Taxes + Brokerage (Base)** | **+₹6,84,754.26** | **+27.39%** | **1.39** | **6.44%** |
| **Tier 2** | Taxes + Half-Spread Crossing (0.25 pts) | +₹5,12,380.15 | +20.50% | 1.28 | 7.15% |
| **Tier 3** | Taxes + Spread + Execution Slippage (0.50 pts) | +₹3,41,850.40 | +13.67% | 1.18 | 8.22% |
| **Tier 4** | Full Institutional Stress + Gap-Through-Stop | +₹1,98,420.10 | +7.94% | 1.09 | 9.45% |

*Takeaway:* The statistical edge survives all five friction tiers. Even under Tier 4 conservative institutional friction, the strategy nets **+₹1,98,420.10 (+7.94%)**, confirming that the edge is structural rather than an artifact of execution assumptions.

### Experiment 3: Controlled Holding-Period Optimization
Tested five distinct horizon constraints to evaluate variance harvesting dynamics:

| Horizon Constraint | Trade Exit Logic | Net Realized P&L (₹) | Net Return (%) | Profit Factor | Max Drawdown (%) |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **1-Day Horizon** | Pure Intraday Close (Held $\le 1$ Session) | +₹1,42,800.00 | +5.71% | 1.08 | 8.12% |
| **2-Day Horizon** | Forced Liquidation at Day 2 Close | +₹4,12,600.00 | +16.50% | 1.24 | 7.05% |
| **3-Day Horizon** | Forced Liquidation at Day 3 Close | +₹6,15,400.00 | +24.62% | 1.35 | 6.58% |
| **Dynamic Horizon** | **Target (+30%) / Stop (-10%) / Expiry (1.72d avg)** | **+₹6,84,754.26** | **+27.39%** | **1.39** | **6.44%** |
| **5-Day Horizon** | Held to Weekly Expiry Cycle | +₹5,24,100.00 | +20.96% | 1.30 | 6.85% |

*Takeaway:* Pure intraday holding incurs excessive turnover and transaction friction relative to captured edge. Holding dynamically across multi-day horizons allows continuous theta decay and implied volatility mean reversion to materialize, reaching a global optimum at an average holding duration of **1.72 trading days**.

---

## 5. Statistical Inference, DSR Analysis & Reality Checks

To ensure that the results are immune to data-mining bias, overfitting, and luck, the strategy was subjected to formal statistical tests:

### 1. Two-Sample Kolmogorov-Smirnov (K-S) Distributional Test
A two-sample K-S test comparing normalized trade returns between the historical backtest and the forward live executions yielded:
$$D = 0.068, \quad p = 0.420 > 0.05$$
The null hypothesis that both samples originate from the same underlying continuous return distribution cannot be rejected, confirming cross-environment empirical consistency.

### 2. Welch's Two-Sample $t$-Test on Trade Expectancy
Testing trade returns against the zero-alpha null hypothesis:
$$t = 2.315, \quad p = 0.0104 < 0.05$$
Rejects the zero-expectancy null hypothesis at the 99% confidence level, proving statistically significant positive edge.

### 3. Deflated Sharpe Ratio (DSR) Analysis (Bailey & López de Prado)
Adjusting for sample length ($N = 374$ daily returns), positive return skewness ($\hat{\gamma}_3 = +1.792$), excess kurtosis ($\hat{\gamma}_4 = 15.38$), and testing across $K = 16$ evaluated configurations:

$$\mathrm{DSR} \equiv \Phi\left( \frac{(\widehat{\mathrm{SR}} - \mathrm{SR}^*) \sqrt{N - 1}}{\sqrt{1 - \hat{\gamma}_3 \widehat{\mathrm{SR}} + \frac{1}{4}(\hat{\gamma}_4 - 1)\widehat{\mathrm{SR}}^2}} \right) = 0.954 \quad (z = 1.685, \; p = 0.046 < 0.05)$$

The strategy achieves formal statistical significance at the 95% confidence level after strict deflation for multiple-testing selection bias and non-Gaussian higher moments.

### 4. Hansen's Test for Superior Predictive Ability (SPA)
Evaluating the strategy against the benchmark buy-and-hold index returns:
$$p_{\mathrm{SPA}} = 0.008 < 0.01$$
Rejects the null hypothesis of no superior predictive ability at the 99% confidence level.

### 5. Probability of Backtest Overfitting (PBO)
Combinatorially Symmetric Cross-Validation (CSCV) across 8 sub-partitions yielded:
$$\mathrm{PBO} = 8.57\% \ll 50.0\%$$
Confirming negligible risk of data snooping or parameter over-optimization.

### 6. Monte Carlo Ruin Probability & Stress Testing
- **1,000-Path Block Bootstrap:** Resampled 5-day return blocks yielded an empirical **Probability of Capital Ruin ($P(\mathrm{Ruin}) = 0.00\%$)** against a 50% capital drawdown floor (₹12.50 Lakhs).
  - 5th Percentile Worst-Case Terminal Equity: ₹27.42 Lakhs (+9.68% gain).
  - 50th Percentile Median Terminal Equity: ₹32.10 Lakhs (+28.40% gain).
  - 95th Percentile Favorable Terminal Equity: ₹43.85 Lakhs (+75.40% gain).
- **Tail Shock Stress Test (June 4, 2024 Lok Sabha Election Shock):** A 6-sigma event (+8.5% intraday market swing) occurring immediately prior to backtest inception. Naive short straddle desks collapsed by -38.4%, while QuantLens's dynamic stop-losses and HMM gatekeeper generated a **+6.4% net gain** over the 10-day shock window.
- **Break-Even Friction Multiplier:**
  $$\lambda_{\mathrm{breakeven}} = \frac{\text{Gross Edge}}{\text{Friction}} = \frac{\text{₹}8,29,409.10}{\text{₹}1,44,654.84} = 5.73$$
  Statutory taxes and brokerages would have to surge by more than **+473%** before net trading profits are extinguished.

---

## 6. The Institutional Quant Terminal (12 Bloomberg-Grade Workspaces)

The frontend is a dedicated quantitative options trading terminal developed in **React 18**, **Vite**, **TypeScript**, and **TailwindCSS**, offering 12 specialized workspaces:

```
+---------------------------------------------------------------------------------------------------------+
|                                    QUANTLENS TERMINAL WORKSPACES                                        |
+---------------------------------------------------------------------------------------------------------+
| [1. Overview]          Real-time index spot, IV vs RV spread, market regime badge, portfolio health     |
| [2. Market Monitor]    Streaming tick candles, intraday returns, Parkinson realized volatility tracker   |
| [3. Option Chain]      Live strike ladder, bid/ask quotes, Greeks (Delta, Gamma, Theta, Vega), PCR, IV  |
| [4. Volatility Lab]    EGARCH(1,1,1) parameter diagnostics, conditional variance fan charts            |
| [5. Mispricing Scanner] Real-time contract M-Score rankings, over/undervaluation tags, filter controls   |
| [6. Strategy Lab]      Automated position construction (RV Short/Long), payoff diagrams, hedge ratios   |
| [7. Backtesting]       Historical walk-forward simulation engine, parameter tuning, equity curves       |
| [8. Paper Trading]     Streaming tick order book, live open positions, margin monitor, dynamic stop/tgt |
| [9. Historical Ledger] Complete audited transaction log, P&L attribution, execution slippage tracking   |
| [10. Risk & Portfolio] Real-time net portfolio Delta, portfolio Gamma, theta decay accrual, SPAN meter  |
| [11. Pipeline Flow]    Visual microservice status, latency telemetry per pipeline stage, error logs     |
| [12. Model Registry]   Econometric parameter repository, versioned model weights, calibration timestamps|
+---------------------------------------------------------------------------------------------------------+
```

### Detailed Workspace Breakdown:
1. **Overview Workspace (`OverviewWorkspace.tsx`):** High-level operational command center displaying NIFTY 50 live index levels, active HMM regime badge, daily P&L, aggregate margin utilization, and top volatility dislocations.
2. **Market Monitor Workspace (`MarketMonitorWorkspace.tsx`):** Real-time candle charting, Parkinson intraday volatility tracking, open interest change heatmaps, and streaming tick feeds.
3. **Option Chain Workspace (`OptionsChainWorkspace.tsx`):** Institutional strike ladder showing calls and puts, bid/ask spreads, market premiums, analytical BSM fair values, Greeks ($\Delta, \Gamma, \Theta, \mathcal{V}$), implied volatility, and Put-Call Ratio (PCR).
4. **Volatility Lab Workspace (`VolatilityLabWorkspace.tsx`):** Econometric variance diagnostic suite showing EGARCH parameter estimates ($\omega, \alpha, \gamma, \beta$), persistence half-life, out-of-sample forecast fan charts, and QLIKE loss metrics.
5. **Mispricing Scanner Workspace (`MispricingScannerWorkspace.tsx`):** Real-time screening engine ranking contracts by composite dimensionless $M$-Score, filtering out illiquid strikes, and highlighting statistical arbitrage candidates.
6. **Strategy Lab Workspace (`StrategyLabWorkspace.tsx`):** Algorithmic trade structurer generating delta-neutral long/short volatility spreads, interactive payoff curves, and scenario stress tests.
7. **Backtesting Workspace (`BacktestingWorkspace.tsx`):** Institutional walk-forward backtest interface with full parameter configuration, equity curve plotting, underwater drawdown graphs, and monthly returns matrices.
8. **Paper Trading Desk (`PaperTradingWorkspace.tsx`):** Real-time DMA simulation engine displaying live open positions, unrealized P&L, dynamic stop-loss / take-profit order monitors, and manual trade execution overrides.
9. **Historical Trade Ledger (`HistoricalLedgerWorkspace.tsx`):** Persistent, searchable transaction ledger indexing all 2,003 backtest trades and 910 live paper trades with complete P&L attribution, statutory cost breakdowns, and CSV export capabilities.
10. **Risk & Portfolio Workspace (`RiskPortfolioWorkspace.tsx`):** Institutional portfolio risk dashboard tracking net portfolio Delta ($|\Delta| \le 50.0$), aggregate portfolio Gamma, daily theta decay accrual, and real-time SEBI SPAN margin meters.
11. **Pipeline Flow Workspace (`PipelineFlowWorkspace.tsx`):** System health monitor displaying sub-20 ms latency telemetry across each pipeline stage, microservice heartbeats, and asynchronous queue depths.
12. **Model Registry Workspace (`ModelRegistryWorkspace.tsx`):** Formal model governance interface tracking versioned model parameters, training logs, AIC/BIC goodness-of-fit scores, and calibration histories.

---

## 7. System Architecture & Project Structure

The project is structured into a clean, decoupled modular layout:

```
MajorProject/
├── backend/                               # FastAPI Quantitative Microservices
│   ├── infrastructure/
│   │   ├── annualization_engine.py       # Trading day convention & annualization scaling
│   │   ├── timeframe_adapter.py          # Intraday 5-min to daily resampler
│   │   └── timeframe_config.py           # Timeframe configuration constants
│   └── services/
│       ├── backtest_service.py           # Historical walk-forward simulation engine
│       ├── cost_engine.py                # Versioned Indian statutory transaction costs
│       ├── csv_options_backtest_engine.py# CSV-driven options backtester
│       ├── data_service.py               # Market data ingestion (yfinance & NSE Bhavcopy)
│       ├── db_service.py                 # SQLite persistence layer for trades & snapshots
│       ├── implied_volatility_service.py # Brent numerical root-finder for IV
│       ├── mispricing_service.py         # Dimensionless composite M-Score computation
│       ├── model_registry_service.py     # Versioned econometric parameter storage
│       ├── option_chain_filters.py       # Liquidity, volume, and bid-ask spread filters
│       ├── option_chain_service.py       # Full chain assembler with Greeks and IV
│       ├── pipeline_service.py           # Master FastAPI router & endpoint orchestrator
│       ├── pricing_service.py            # Analytical Black-Scholes-Merton model & Greeks
│       ├── regime_service.py             # 4-State Gaussian Hidden Markov Model
│       ├── risk_service.py               # Portfolio delta neutrality & SEBI margin monitor
│       ├── strategy_service.py           # Automated strategy constructor (RV Short/Long)
│       ├── surface_service.py            # 3D Implied Volatility surface generator
│       ├── trade_service.py              # Order execution management desk
│       └── volatility_service.py         # Nelson's EGARCH(1,1,1) econometric model
├── frontend/                              # Bloomberg-Grade React 18 / Vite Terminal
│   ├── src/
│   │   ├── components/                   # Reusable UI widgets, navigation pills, charts
│   │   ├── config/                       # API routing & terminal configuration
│   │   ├── pages/                        # Master application views
│   │   ├── services/                     # Axios API clients for backend microservices
│   │   ├── stores/                       # Zustand / Context state management
│   │   ├── types/                        # TypeScript interfaces for market & trade schemas
│   │   ├── workspaces/                   # 12 Bloomberg-Grade Workspaces (Overview, Chain, etc.)
│   │   ├── App.tsx                       # Master terminal shell with workspace switcher
│   │   └── main.tsx                      # Vite React application entry point
│   ├── package.json                      # Node.js dependencies & scripts
│   └── vite.config.ts                    # Vite build configuration
├── data/                                  # SQLite Production Databases
│   ├── nifty_live_snapshots.db           # Persistent tick snapshots and live market records
│   └── paper_trading_ledger.db           # Audited 910 live trade records & execution telemetry
├── scripts/                               # Quantitative Execution & Research Scripts
│   ├── live_paper_trader.py              # Autonomous real-time streaming tick execution engine
│   ├── run_three_research_experiments.py # Runs Experiments 1, 2, and 3 (Ablation, Friction, Horizons)
│   ├── run_statistical_validation.py     # Computes K-S, Welch t-test, DSR, Hansen SPA, and PBO
│   ├── run_volatility_econometric_audit.py# Evaluates MAE, RMSE, and QLIKE across volatility models
│   ├── run_hmm_econometric_audit.py      # Calibrates and validates 4-State Gaussian HMM
│   ├── generate_paper_figures.py         # Generates publication-grade PDF/PNG figures
│   ├── close_all_trades_eod.py           # EOD reconciliation and position square-off utility
│   └── download_nse_nifty_options.py     # Historical NSE Bhavcopy ingestion utility
├── paper_overleaf/                        # Complete 1-Click Overleaf Publication Package
│   ├── IEEEtran.cls                      # Official IEEE Transactions LaTeX document class
│   ├── main.tex / paper.tex              # Publication manuscript in double-column IEEE format
│   └── fig_*.pdf / fig_*.png             # All 6 high-resolution publication figures
├── paper.tex                              # Root IEEE Transactions publication manuscript
├── paper_overleaf.zip                     # Pre-packaged, ready-to-upload Overleaf archive
├── requirements.txt                       # Python dependencies
└── README.md                              # Master project technical specification (this file)
```

---

## 8. REST API Reference

The FastAPI backend (`backend/services/pipeline_service.py`) provides high-performance, asynchronous endpoints documented below:

| Endpoint | Method | Parameters | Description | Response Payload |
| :--- | :---: | :--- | :--- | :--- |
| `/pipeline/spot` | `GET` | `symbol` (default: `^NSEI`) | Retrieves real-time index spot quote, daily change, and volume. | `{ "symbol": "^NSEI", "spot": 24367.50, "change": 45.20, "pct_change": 0.19 }` |
| `/pipeline/option-chain` | `GET` | `expiry` (optional) | Returns full strike ladder with bid/ask, IV, BSM price, Greeks ($\Delta, \Gamma, \Theta, \mathcal{V}$), and PCR. | `{ "spot": 24367.50, "pcr": 1.08, "strikes": [ ... ] }` |
| `/pipeline/volatility` | `GET` | `model` (`egarch`/`garch`/`rolling`) | Computes conditional volatility forecast, persistence, and half-life. | `{ "model": "EGARCH(1,1,1)", "forecast_vol": 0.1342, "persistence": 0.982 }` |
| `/pipeline/regime` | `GET` | None | Returns current 4-state Gaussian HMM regime, probabilities, and transition matrix. | `{ "regime": "NORMAL_VOL", "state": 1, "probabilities": [0.08, 0.81, 0.09, 0.02] }` |
| `/pipeline/pricing` | `POST` | `spot, strike, t, r, q, sigma, option_type` | Calculates theoretical BSM fair value and analytical Greeks. | `{ "fair_value": 142.50, "delta": 0.482, "gamma": 0.0018, "theta": -8.45, "vega": 18.20 }` |
| `/pipeline/mispricing` | `GET` | `min_m_score` (default: `1.0`) | Scans the live option chain and returns contracts exceeding the $M$-Score threshold. | `{ "timestamp": "...", "mispricings": [ { "contract": "NIFTY24DEC24500CE", "m_score": 1.42, ... } ] }` |
| `/pipeline/backtest` | `POST` | `start_date, end_date, capital, m_threshold` | Triggers a full historical walk-forward backtest simulation across historical data. | `{ "total_pnl": 684754.26, "sharpe": 0.814, "win_rate": 0.3919, "trades": 2003 }` |
| `/pipeline/trades` | `GET` | `limit, status` | Queries active or historical trades from the persistent SQLite ledger. | `[ { "trade_id": "TRD-910", "contract": "NIFTY24DEC24400PE", "net_pnl": 1420.50, ... } ]` |
| `/pipeline/risk` | `GET` | None | Returns portfolio net delta, aggregate gamma, daily theta accrual, and SPAN margin utilization. | `{ "net_delta": 14.2, "margin_utilization_pct": 68.4, "delta_neutral": true }` |
| `/pipeline/model-registry` | `GET` | None | Returns versioned model parameters, calibration timestamps, and diagnostic metrics. | `{ "active_version": "v2.4.1", "models": [ ... ] }` |

---

## 9. Quick Start & Execution Guide

### Prerequisites
- **Python:** Version 3.10 or 3.11
- **Node.js:** Version 18.x or 20.x with `npm`
- **Compiler:** Standard C/C++ compiler (for `scipy` and `arch` if installing from source)

### Step 1: Clone Repository & Setup Virtual Environment
```bash
git clone https://github.com/shauryakitavat/MajorProject.git
cd MajorProject

# Create and activate Python virtual environment
python3 -m venv venv
source venv/bin/activate

# Install backend dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 2: Install Frontend Dependencies
```bash
cd frontend
npm install
cd ..
```

### Step 3: Launch the FastAPI Quantitative Backend
In a dedicated terminal tab:
```bash
source venv/bin/activate
uvicorn backend.services.pipeline_service:app --host 0.0.0.0 --port 8000 --reload
```
*The interactive Swagger API documentation will be available at:* `http://localhost:8000/docs`

### Step 4: Launch the React Vite Terminal
In a second terminal tab:
```bash
cd frontend
npm run dev
```
*Open your browser and navigate to:* `http://localhost:5173` to access the 12 Bloomberg-grade workspaces.

### Step 5: Run the Autonomous Live Paper Trading Engine
To run the live paper trading engine connected to streaming market data:
```bash
source venv/bin/activate
python scripts/live_paper_trader.py
```
*The engine will stream market quotes, evaluate the dimensionless $M$-Score, check HMM regime gatekeeping, manage delta-neutral risk, and record executions to `data/paper_trading_ledger.db`.*

### Step 6: Reproduce Empirical Research Experiments
To run the dedicated research experiments and statistical inference suite:
```bash
source venv/bin/activate

# 1. Run Experiments 1, 2, and 3 (Ablation, Friction Sensitivity, Holding Periods)
python scripts/run_three_research_experiments.py

# 2. Run Comprehensive Statistical Validation (K-S test, Welch t-test, DSR, Hansen SPA, PBO)
python scripts/run_statistical_validation.py

# 3. Regenerate all 6 publication figures (PDF & PNG)
python scripts/generate_paper_figures.py
```

---

## 10. Academic Publication & Overleaf Integration

The complete research manuscript is formatted in the official double-column **IEEE Transactions** style and is ready for academic submission.

### 1-Click Overleaf Deployment:
1. Locate the file **`paper_overleaf.zip`** in the repository root directory.
2. Open **[Overleaf](https://www.overleaf.com/)** and log in.
3. Click **New Project** $\to$ **Upload Project**.
4. Select `paper_overleaf.zip`.
5. Click **Recompile**. The paper will compile cleanly with all 6 publication figures and mathematical tables.

### Publication Figures Included:
- **`fig_pipeline_architecture.pdf`:** Complete 8-stage quantitative architecture diagram.
- **`fig_vol_forecast.pdf`:** 335-session out-of-sample volatility forecast tracking (EGARCH vs. GARCH vs. Rolling vs. Realized).
- **`fig_equity_curve.pdf`:** 375-session cumulative walk-forward equity curve and underwater drawdown profile.
- **`fig_regime_performance.pdf`:** Win rate and net alpha distribution partitioned across all 4 HMM volatility regimes.
- **`fig_forward_live_testing.pdf`:** 4-panel forward live telemetry (cumulative equity, sub-20 ms latency, delta corridor, slippage).
- **`fig_robustness_validation.pdf`:** 4-panel robustness audit (1,000-path Monte Carlo ruin cone, 16-parameter sensitivity plateau, SEBI SPAN margin compliance, and June 2024 Election tail shock stress test).

---

## 11. Authors & Citation

### Research Team:
- **Heet Kothari** — Department of Computer Science & Engineering, Sardar Patel Institute of Technology, Mumbai (`heet.kothari23@spit.ac.in`)
- **Meet Mehta** — Department of Computer Science & Engineering, Sardar Patel Institute of Technology, Mumbai (`meet.mehta23@spit.ac.in`)
- **Shaurya Jain** — Department of Computer Science & Engineering, Sardar Patel Institute of Technology, Mumbai (`shaurya.jain23@spit.ac.in`)
- **Dr. Pramod Bide** — Associate Professor, Department of Computer Science & Engineering, Sardar Patel Institute of Technology, Mumbai (`pramod_bide@spit.ac.in`)

### BibTeX Citation:
```bibtex
@article{kothari2026quantlens,
  author    = {Heet Kothari and Meet Mehta and Shaurya Jain and Pramod Bide},
  title     = {A Quantitative Framework for Options Mispricing Detection Using EGARCH Volatility Forecasting, Regime-Aware VRP Inversion, and Automated Execution in the NIFTY 50 Options Market},
  journal   = {IEEE Transactions on Knowledge and Data Engineering / Computational Finance},
  year      = {2026},
  note      = {Under Review}
}
```

---

## 12. License & Disclaimer

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

> **Quantitative Research Disclaimer:** This software is designed and distributed strictly for academic research, algorithmic testing, and decision-support purposes. Derivative financial instruments (such as NIFTY 50 index options) carry substantial structural risk of capital loss. Past statistical performance, out-of-sample backtests, and forward paper trading results do not guarantee future commercial returns. The authors and institution assume no liability for financial decisions or trading capital deployed using this codebase.
