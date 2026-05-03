# NIFTY 50 Options Mispricing Detection Engine

A research-oriented quantitative trading system that detects options mispricing using EGARCH volatility forecasting and Black-Scholes pricing. Integrates real-time option chain data from Upstox API and generates data-driven strategy recommendations.

**Status:** Phase 1 Complete (core pipeline implemented)  
**Publication Target:** IEEE Transactions (pending real-data validation)  
**Current Version:** 1.1.0  
**Last Updated:** May 3, 2026

## 🎯 Project Overview

Automated pipeline that:
1. Fetches historical NIFTY 50 market data (yfinance) & real option chain (Upstox API)
2. Computes log returns and forecasts conditional volatility using EGARCH(1,1)
3. Derives Black-Scholes theoretical fair prices
4. Detects mispricing by comparing market vs fair values
5. Classifies volatility regimes (LOW/NORMAL/HIGH/EXTREME)
6. Generates rule-based strategy recommendations (BUY/SELL/NEUTRAL with confidence)
7. Returns all analytics via RESTful API with Swagger documentation

**⚠️ IMPORTANT:** This is a research and decision-support tool, NOT an automated trading system. Outputs do not constitute financial advice.

---

## 🏗️ Architecture

### Core Pipeline (7 Stages)
```
Historical Data (yfinance)        Real Option Chain (Upstox API v2)
        │                                │
        ├─→ Fetch NIFTY OHLCV            ├─→ Spot Price + ATM Options
        │                                │
        ├─→ Log Returns                  └─→ 21+ Strikes with OI/Vol/IV
        │
        ├─→ EGARCH(1,1) Volatility (arch library)
        │
        ├─→ Black-Scholes Fair Price (scipy)
        │
        ├─→ Mispricing Detection (% deviation)
        │
        ├─→ Volatility Regime Classification
        │
        └─→ Strategy Recommendation Generation
        
        └─→ HTTP/JSON Response via FastAPI
```

### Tech Stack

- **Language:** Python 3.10
- **API Framework:** FastAPI + Uvicorn
- **Data Processing:** pandas, numpy
- **Volatility Modeling:** `arch` (EGARCH), statsmodels
- **Options Pricing:** scipy (Black-Scholes)
- **Data Sources:** yfinance (historical), Upstox API v2 (real option chain)
- **Deployment:** Docker
- **Documentation:** Swagger/OpenAPI

### Project Structure

```
├── main.py                              # FastAPI app + 15 endpoints
├── backend/
│   ├── services/
│   │   ├── data_service.py             # ✅ yfinance data fetch
│   │   ├── volatility_service.py       # ✅ EGARCH(1,1) forecast
│   │   ├── pricing_service.py          # ✅ Black-Scholes pricing
│   │   ├── mispricing_service.py       # ✅ Mispricing detection
│   │   ├── regime_service.py           # ✅ Volatility regime
│   │   ├── strategy_service.py         # ✅ Strategy generation
│   │   ├── option_chain_service.py     # ✅ Upstox API integration (NEW)
│   │   ├── implied_volatility_service.py # ✅ IV solver
│   │   ├── backtest_service.py         # ⚠️ Untested
│   │   └── upstox_option_chain_service.py # Alternative implementation
│   ├── infrastructure/
│   │   ├── timeframe_config.py         # Multi-timeframe support
│   │   ├── timeframe_adapter.py        # Dataframe normalization
│   │   └── annualization_engine.py     # Dynamic vol scaling
│   └── broker_adapter.py               # ❌ Dhan integration (stub)
├── scripts/
│   └── upstox_token.py                 # Upstox OAuth token exchange
├── Dockerfile                          # Container configuration
├── requirements.txt                    # Dependencies
├── Phase1_Report.md/.tex               # Comprehensive documentation
└── PROJECT_AUDIT.md                    # ⭐ READ THIS - Honest status
```



---

## 🚀 Quick Start

### Local Development (No Docker)

```bash
# 1. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set up Upstox credentials
cp .env.example .env
# Edit .env with your Upstox API credentials

# 4. Run server
python3 main.py

# 5. Open API documentation
# http://localhost:8000/docs
# http://localhost:8000/redoc
```

### Docker Deployment

```bash
# Build image
docker build -t nifty-options:latest .

# Run container
docker run -d --name nifty-options-api \
  -p 8000:8000 \
  -e UPSTOX_ACCESS_TOKEN="<your_token>" \
  nifty-options:latest

# Check logs
docker logs -f nifty-options-api

# Stop container
docker stop nifty-options-api
docker rm nifty-options-api
```

---

## 📡 API Endpoints (15 Total)

### Health & System (3)
| Endpoint | Method | Status | Purpose |
|----------|--------|--------|---------|
| `/` | GET | ✅ | Service health check |
| `/health` | GET | ✅ | Liveness probe |
| `/metrics` | GET | ✅ | Request counter metrics |

### Market Data (3)
| Endpoint | Method | Status | Purpose |
|----------|--------|--------|---------|
| `/nifty` | GET | ✅ | Latest NIFTY spot price & candle |
| `/expiries` | GET | ✅ | Available option expiry dates |
| `/option-chain` | GET | ✅ NEW | **Real Upstox chain (21 strikes, live OI/IV)** |

### Quantitative Pipeline (6)
| Endpoint | Method | Status | Purpose |
|----------|--------|--------|---------|
| `/returns` | GET | ✅ | Historical log returns |
| `/forecast-vol` | GET | ✅ | EGARCH(1,1) annualized volatility |
| `/fair-price` | GET | ✅ | Black-Scholes theoretical fair price |
| `/mispricing` | GET | ✅ | Mispricing % vs fair value |
| `/regime` | GET | ✅ | Volatility regime classification |
| `/strategy` | GET | ✅ | **MAIN** - Full pipeline + strategy signal |

### Advanced (3)
| Endpoint | Method | Status | Purpose |
|----------|--------|--------|---------|
| `/backtest` | GET | ⚠️ | Walk-forward backtest *(untested)* |
| `/debug-option` | GET | ✅ | Debug option chain fetching |
| `/option-chain-demo` | GET | ✅ | Demo endpoint (representative data) |

### Query Parameters

**All pipeline endpoints accept:**
```
?symbol=NIFTY                    # Default: NIFTY (only NIFTY works currently)
?trading_horizon=positional      # day_trader, positional, long_term
?timeframe=daily                 # 1m, 5m, 15m, 1h, daily, weekly
?expiry=2026-05-05              # Specific option expiry (YYYY-MM-DD)
?expiry_type=nearest            # nearest, weekly, monthly
?depth=20                        # Number of strikes to return
```

---

## 🔧 Configuration

### Upstox Integration (OAuth Token)

1. **Set API credentials in `.env`:**
```bash
UPSTOX_API_KEY="<your_api_key>"
UPSTOX_API_SECRET="<your_api_secret>"
UPSTOX_REDIRECT_URI="http://localhost:8000/callback"
```

2. **Exchange auth code for access token:**
```bash
python scripts/upstox_token.py --code "<authorization_code>"
```

3. **Save token to `.env`:**
```bash
UPSTOX_ACCESS_TOKEN="eyJ0eXAiOiJKV1QiLCJrZXlfaWQiOiJza192MS4wIiwiYWxnIjoiSFMyNTYifQ..."
```

### Environment Variables

```bash
# Required for Upstox integration
UPSTOX_API_KEY=<your_api_key>
UPSTOX_API_SECRET=<your_api_secret>
UPSTOX_ACCESS_TOKEN=<your_access_token>
UPSTOX_REDIRECT_URI=http://localhost:8000/callback

# Optional
LOG_LEVEL=INFO
CACHE_TTL_SECONDS=15
```

---

## 📊 Real Data Example

### Get Full Strategy Signal
```bash
curl "http://localhost:8000/strategy?trading_horizon=positional&timeframe=daily"
```

**Response:**
```json
{
  "status": "success",
  "timestamp": "2026-05-03T10:30:00Z",
  "data": {
    "spot_price": 23997.55,
    "forecast_volatility": 16.91,
    "fair_price": 221.50,
    "market_price": 221.50,
    "mispricing": {
      "deviation_percent": 0.00,
      "classification": "FAIR_VALUED"
    },
    "regime": "NORMAL_VOL",
    "strategy": {
      "signal": "NEUTRAL",
      "strength": "WEAK",
      "confidence": 0.35,
      "rationale": "Option fairly priced, normal volatility regime"
    },
    "selected_expiry": "2026-05-05",
    "available_expiries": ["2026-05-05"],
    "pipeline_health": "HEALTHY"
  }
}
```

### Get Real Option Chain (Upstox)
```bash
curl "http://localhost:8000/option-chain"
```

**Returns 21 strikes with live data:**
```json
{
  "status": "success",
  "data": {
    "spot_price": 23997.55,
    "atm_strike": 24000,
    "expiry_date": "2026-05-05",
    "chain": [
      {
        "strike": 23500,
        "call": { "ltp": 604.05, "oi": 635310, "volume": 3708965, "iv": 19.5 },
        "put": { "ltp": 29.15, "oi": 4454385, "volume": 74438195, "iv": 17.38 }
      },
      ...
    ]
  }
}
```

---

## ✅ Validation Summary

Daily validation has been run using historical NIFTY spot prices and a deterministic noise model for option prices. This validates pipeline logic but is **not** a substitute for real historical option prices.

- Validation details: [VALIDATION_EXPLANATION.md](VALIDATION_EXPLANATION.md)
- Validator script: [validation/daily_validator_simple.py](validation/daily_validator_simple.py)
- Results artifact: [validation_results_daily.json](validation_results_daily.json)

**Next required step:** repeat validation using real option chain snapshots (see [implementation.md](implementation.md)).

---

## ⚠️ HONEST STATUS ASSESSMENT

### ✅ What's Working (Ready for Use)
- Core quantitative pipeline (EGARCH + Black-Scholes)
- Real Upstox option chain integration (May 2026 data)
- FastAPI endpoints with Swagger documentation
- Docker containerization
- Volatility forecasting and mispricing detection
- Phase 1 research documentation

### 🟡 What's Partially Working
- Backtesting code exists but **NOT VALIDATED**
- Multi-timeframe infrastructure exists but **NOT THOROUGHLY TESTED**
- Greeks calculated from Upstox but **NOT INTEGRATED** into strategy
- Dhan broker integration is a **STUB** (not wired in)

### ❌ What's Missing (Critical for Publication)
1. **Real Option Price Validation** - Current daily validation uses synthetic option prices
2. **Backtest Validation** - Backtest engine exists but is unverified
3. **Risk Management** - No position sizing, stop-loss, portfolio risk
4. **Frontend Dashboard** - API only, no UI for traders
5. **Multi-Asset Support** - Only NIFTY 50, no other symbols

### Publication Readiness
**Current Status:** ❌ **NOT READY FOR IEEE PUBLICATION**

**Why:**
- Daily validation uses synthetic option prices (no historical option chain yet)
- Backtest results are unverified
- Intraday validation not available

### See Also
- [implementation.md](implementation.md)
- [track.md](track.md)
- [VALIDATION_EXPLANATION.md](VALIDATION_EXPLANATION.md)
- [Phase1_Report.md](Phase1_Report.md)

---

## 🔍 Component Status Matrix

| Component | Code | Tests | Documentation | Production Ready |
|-----------|------|-------|-----------------|-----------------|
| EGARCH Volatility | ✅ | ⚠️ | ✅ | ✅ |
| Black-Scholes Pricing | ✅ | ✅ | ✅ | ✅ |
| Mispricing Detection | ✅ | ⚠️ | ✅ | ✅ |
| Regime Classification | ✅ | ⚠️ | ✅ | ✅ |
| Strategy Generation | ✅ | ⚠️ | ✅ | ⚠️ |
| Upstox Integration | ✅ | ✅ | ✅ | ✅ |
| Backtesting | ✅ | ❌ | ⚠️ | ❌ |
| Multi-Timeframe | ⚠️ | ❌ | ✅ | ❌ |
| Dhan Integration | ⚠️ | ❌ | ⚠️ | ❌ |
| Frontend Dashboard | ❌ | N/A | N/A | ❌ |
| Risk Management | ❌ | N/A | N/A | ❌ |

---

## 💡 Usage Examples

### 1. Get Strategy Signal for Positional Trading
```bash
curl "http://localhost:8000/strategy?trading_horizon=positional&timeframe=daily"
```

### 2. Check Real Option Chain
```bash
curl "http://localhost:8000/option-chain"
```

### 3. Get Volatility Forecast
```bash
curl "http://localhost:8000/forecast-vol?timeframe=1h"
```

### 4. Run Walk-Forward Backtest ⚠️ *Untested*
```bash
curl "http://localhost:8000/backtest?timeframe=1d"
```

### 5. View Metrics
```bash
curl "http://localhost:8000/metrics"
```

---

## 📚 Documentation

- [Phase1_Report.md](Phase1_Report.md) - Complete research proposal (15+ pages)
- [Phase1_Report.tex](Phase1_Report.tex) - LaTeX version for IEEE submission
- [VALIDATION_EXPLANATION.md](VALIDATION_EXPLANATION.md) - Validation methodology and math details
- [implementation.md](implementation.md) - Completion plan
- [track.md](track.md) - Progress tracker
- [README.md](README.md) - This file
- Swagger UI - http://localhost:8000/docs (when running)

---

## 🛠️ Development

### Install Dependencies
```bash
pip install -r requirements.txt
```

### Run Tests
```bash
# Validate services manually
python run_validation.py

# Test specific endpoint
curl http://localhost:8000/strategy
```

### Add New Endpoint
1. Create function in main.py
2. Decorate with `@app.get()` or `@app.post()`
3. Add to Swagger tags
4. Test via `/docs` UI

### Debug Option Chain
```bash
curl "http://localhost:8000/debug-option"
```

---

## 📦 Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| pandas | Latest | Data manipulation |
| numpy | Latest | Numerical computing |
| yfinance | Latest | Historical market data |
| arch | Latest | EGARCH volatility |
| statsmodels | Latest | Time series analysis |
| scipy | Latest | Black-Scholes (norm CDF) |
| fastapi | Latest | API framework |
| uvicorn | Latest | ASGI server |
| requests | Latest | HTTP client (Upstox) |
| py_vollib | Latest | Implied volatility |
| matplotlib | Latest | Visualization support |
| python-dateutil | Latest | Date parsing |
| pytz | Latest | Timezone handling |

See [requirements.txt](requirements.txt) for exact versions.

---

## 🚨 Known Limitations

1. **Hardcoded Symbol** - Accepts `?symbol=` parameter but internally uses only NIFTY 50
2. **No Transaction Costs** - Assumes zero slippage and commissions
3. **yfinance Latency** - 15-minute delayed historical data
4. **In-Memory Cache** - Resets on server restart
5. **No Rate Limiting** - Endpoints can be abused
6. **No Authentication** - Public API, no API keys required
7. **Single Process** - Can handle ~10-20 concurrent requests
8. **No Database** - Results not persisted; no query history

---

## 📖 Citation (For Academic Use)

If you use this project in research, please cite:

```bibtex
@inproceedings{nifty2026options,
  title={NIFTY 50 Options Mispricing Detection using EGARCH and Black-Scholes},
  author={Your Name},
  year={2026},
  note={Available at: https://github.com/your/repo}
}
```

---

## ⚖️ Disclaimer

This software is provided for research and educational purposes only. It is **NOT intended for live trading** or investment decisions. Use at your own risk. The authors and contributors assume no liability for trading losses or errors in execution. All strategy recommendations are hypothetical and based on historical data; past performance does not guarantee future results.

---

## 📞 Support & Feedback

For issues, feature requests, or questions:
1. Review [track.md](track.md) for current blockers
2. Review [Phase1_Report.md](Phase1_Report.md) for methodology
3. Test via Swagger UI: http://localhost:8000/docs
4. Enable debug logging by setting `LOG_LEVEL=DEBUG`

---

## Dhan Provider (NOT CURRENTLY USED)

The Dhan broker integration code exists in `backend/broker_adapter.py` but is **NOT WIRED INTO THE API**. To enable:

1. Set Dhan credentials in `.env`:
```bash
DHAN_ACCESS_TOKEN="<your_token>"
DHAN_SECURITY_ID="13"
DHAN_EXCHANGE_SEGMENT="IDX_I"
DHAN_INSTRUMENT="INDEX"
```

2. Test locally (without API integration):
```bash
python -c "from backend.broker_adapter import fetch_spot; print(fetch_spot('dhan', 'NIFTY'))"
```

**Status:** ❌ Stub integration, not production ready
