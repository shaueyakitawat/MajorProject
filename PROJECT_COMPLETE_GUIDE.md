# Comprehensive System & Execution Guide: Quantitative NIFTY 50 Option Mispricing Engine

**Target Journal:** IEEE Transactions on Knowledge and Data Engineering (TKDE) / IEEE Transactions on Computational Finance  
**Version:** 2.0.0 (Production & IEEE Validation Ready)  
**System Identity:** `options-mispricing-engine`  

---

## 1. Project Overview & Architectural Vision

In quantitative derivative pricing, standard theoretical models (such as Black-Scholes) rely on the flawed assumption of **constant volatility** and rational market behavior. In real-world financial markets—specifically the **NIFTY 50 Index Options market**—human fear and structural leverage cause volatility to explode during market downturns, giving rise to the **Volatility Risk Premium (VRP)**.

This project implements an end-to-end, regime-aware quantitative software engine designed to:
1. Forecast asymmetric volatility using **EGARCH(1,1)**.
2. Uncover hidden market states using an **Unsupervised 4-State Hidden Markov Model (HMM)**.
3. Compute **Regime-Adjusted Theoretical Fair Values** for NIFTY 50 options.
4. Detect real-world market mispricings in real time.
5. Validate detection quality using **100% Real Market Data** (NIFTY 50 & India VIX feeds) without any synthetic/mock noise generators.

---

## 2. Complete Repository Directory Structure

```
MajorProject/
├── backend/
│   ├── infrastructure/
│   │   ├── annualization_engine.py      # Dynamic annualization (daily, 5m, 1h)
│   │   ├── timeframe_adapter.py         # Multi-horizon return resampling
│   │   └── timeframe_config.py          # Timeframe scaling constants
│   └── services/
│       ├── backtest_service.py          # Backtesting engine & equity curve tracer
│       ├── data_service.py              # Log return transformation & spot feeds
│       ├── db_service.py                # SQLite tick/snapshot data layer
│       ├── implied_volatility_service.py# Newton-Raphson / py_vollib IV engine
│       ├── mispricing_service.py        # Mispricing signal filter (Z-score, dev %)
│       ├── option_chain_filters.py      # Liquidity & bid-ask spread filters
│       ├── option_chain_service.py      # Real-time NIFTY option chain feed & DB snapshots
│       ├── pricing_service.py           # Black-Scholes pricing & analytical Greeks
│       ├── regime_service.py            # HMM Gaussian 4-state regime classifier
│       ├── strategy_service.py          # Option spread & delta-neutral trade generator
│       ├── upstox_option_chain_service.py # Upstox API compatibility wrapper
│       ├── volatility_service.py        # EGARCH(1,1) forecast & intraday vol fusion
│       └── vrp_service.py               # Variance Risk Premium calculator
├── data/
│   └── nifty_live_snapshots.db          # Real live option chain snapshot database
├── docs/
│   ├── options_mispricing_technical_audit.md
│   ├── validation_results_real.json     # Empirical IEEE JSON benchmark output
│   └── paper/
│       ├── Phase1_Report.tex            # Full IEEE LaTeX manuscript draft
│       └── latexcode.tex                # Extended LaTeX paper code
├── images/                              # Publication visual figures & plots
├── scripts/
│   ├── generate_visual_results.py       # Metrics infographic plot generator
│   ├── record_nifty_snapshots.py       # Live NIFTY option chain snapshot logger
│   └── upstox_token.py                  # Upstox OAuth access token exchanger
├── validation/
│   └── daily_mispricing_validator.py    # Empirical Real NIFTY Data Validator
├── .env.example                         # Environment configuration template
├── Dockerfile                           # Containerized production deployment
├── main.py                              # Production FastAPI REST backend (19 routes)
├── PROJECT_COMPLETE_GUIDE.md            # Comprehensive project documentation
├── PROJECT_EXPLANATION.md
├── requirements.txt                     # Verified dependency manifest
└── run_validation.py                    # Diagnostic system audit CLI
```

---

## 3. Mathematical Pipeline & Model Mechanics

The engine processes data across 6 sequential stages:

```
[Real NIFTY Spot & IV Feed] 
         │
         ▼
[Logarithmic Returns: r_t = ln(S_t / S_{t-1})]
         │
         ▼
[EGARCH(1,1) Volatility Forecast]
   ln(σ_t^2) = ω + α |ε_{t-1}/σ_{t-1}| + γ (ε_{t-1}/σ_{t-1}) + β ln(σ_{t-1}^2)
         │
         ▼
[HMM 4-State Volatility Regime Classification]
   S_t ∈ { Low, Normal, High, Extreme Panic }
         │
         ▼
[Black-Scholes Theoretical Fair Pricing & Greeks]
   C(S,K,t) = S · N(d_1) - K e^{-r t} N(d_2)
   Greeks: Δ (Delta), Γ (Gamma), Θ (Theta), V (Vega)
         │
         ▼
[Mispricing Signal Detection]
   Deviation % = [(P_{market} - P_{fair}) / P_{fair}] × 100
   Signal Flag: |Deviation| ≥ 3.0% AND Z-score ≥ 1.0
```

---

## 4. Empirical IEEE Validation Results

The quantitative engine was validated against **1,676 real NIFTY 50 option instances** across the 2024–2026 market horizon.

### IEEE Publication Metrics
- **Empirical Precision:** `50.88%`
- **Empirical Recall:** `97.58%`
- **Empirical F1-Score:** `0.6689`
- **Overall System Accuracy:** `52.39%`
- **Evaluated Contracts:** `1,676 real market instances`

### Confusion Matrix
- **True Positives (TP):** `806` (Flagged mispricings that objectively reverted next day)
- **False Positives (FP):** `778` (Flagged mispricings where noise persisted)
- **True Negatives (TN):** `72` (Fairly priced options correctly ignored)
- **False Negatives (FN):** `20` (Unflagged mispricing opportunities)

---

## 5. Execution Commands & Operating Instructions

### A. Environment Setup
Using Python 3.10 with pre-installed quantitative dependencies:
```bash
# Verify system dependencies
python -c "import arch, statsmodels, py_vollib, yfinance, fastapi; print('Dependencies OK')"
```

### B. Execute Full Diagnostic System Audit
Runs a complete 4-layer system verification (Data Layer, Volatility Layer, Pricing Layer, Validation Layer):
```bash
python run_validation.py
```
*Expected Output:* `System Status: 🟢 PASSED & PUBLICATION READY`

### C. Execute Real NIFTY Data Empirical Validation
Executes the empirical backtest across 1,676 real market option instances:
```bash
python validation/daily_mispricing_validator.py
```
*Output File:* `docs/validation_results_real.json`

### D. Continuous Live Option Chain Snapshot Recorder
Runs in background during market hours to log live NIFTY option chain snapshots:
```bash
# Single snapshot
python scripts/record_nifty_snapshots.py --once

# Continuous recording every 60 seconds
python scripts/record_nifty_snapshots.py --interval 60
```
*Storage File:* `data/nifty_live_snapshots.db`

### E. Start Production REST API Backend
Launches the FastAPI server exposing 19 quantitative endpoints:
```bash
python main.py
# Or using uvicorn:
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```
Interactive API Documentation will be available at: `http://localhost:8000/docs`

---

## 6. Key REST API Endpoints

- `GET /pipeline/spot` — Real-time NIFTY spot price.
- `GET /pipeline/option-chain` — Full option chain with Greeks, IV, PCR, and depth.
- `GET /pipeline/volatility` — EGARCH(1,1) forecast & intraday vol fusion.
- `GET /pipeline/regime` — HMM 4-state market regime classification.
- `GET /pipeline/pricing` — Black-Scholes theoretical fair value calculation.
- `GET /pipeline/mispricing` — Real-time mispricing signal detection.
- `POST /pipeline/backtest` — Out-of-sample quantitative backtester.
