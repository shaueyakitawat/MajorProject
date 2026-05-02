# Option Mispricing Backend

FastAPI backend for options analytics on NIFTY market data. The service fetches market data, computes log returns, forecasts volatility with EGARCH, derives Black-Scholes fair price, detects mispricing, classifies volatility regime, and returns a strategy signal.

## Project Overview

This project provides a research-oriented quantitative pipeline exposed as HTTP endpoints.

### Pipeline Stages

1. Market data fetch (`yfinance`)
2. Log returns computation
3. EGARCH volatility forecast (`arch`)
4. Black-Scholes fair pricing (`scipy`)
5. Mispricing detection
6. Volatility regime classification
7. Strategy generation

### Tech Stack

- Python 3.10
- FastAPI + Uvicorn
- pandas, numpy
- yfinance
- arch, statsmodels, scipy
- Docker

### Project Structure

- `main.py`: FastAPI app and route handlers
- `backend/services/data_service.py`: data fetch + return preprocessing
- `backend/services/volatility_service.py`: EGARCH forecast
- `backend/services/pricing_service.py`: Black-Scholes pricing
- `backend/services/mispricing_service.py`: mispricing logic
- `backend/services/regime_service.py`: volatility regime classification
- `backend/services/strategy_service.py`: strategy recommendation
- `backend/broker_adapter.py`: broker payload normalization scaffolding

## Run with Docker

### 1) Build image

```bash
docker build -t option-project:latest .
```

### 2) Run container

```bash
docker run -d --name option-project-api -p 8000:8000 option-project:latest
```

### 3) Verify container is running

```bash
docker ps --filter name=option-project-api
```

### 4) Check API health/availability

```bash
curl http://localhost:8000/
```

Also open Swagger docs:

- http://localhost:8000/docs

### 5) View logs

```bash
docker logs -f option-project-api
```

### 6) Stop and remove container

```bash
docker stop option-project-api
docker rm option-project-api
```

## Useful Docker Commands

### Rebuild after code changes

```bash
docker build -t option-project:latest .
docker rm -f option-project-api
docker run -d --name option-project-api -p 8000:8000 option-project:latest
```

### Remove image

```bash
docker rmi option-project:latest
```

## Dhan Provider (broker_adapter)

The Dhan integration is currently added in `backend/broker_adapter.py` and is not yet wired into `main.py` routes.

### Required environment variables

```bash
export DHAN_ACCESS_TOKEN="<your_token>"
export DHAN_SECURITY_ID="13"
export DHAN_EXCHANGE_SEGMENT="IDX_I"
export DHAN_INSTRUMENT="INDEX"
export DHAN_INTERVAL_MIN="1"
```

### Quick adapter test (without changing API routes)

```bash
python - << 'PY'
from backend.broker_adapter import fetch_spot
print(fetch_spot(provider="dhan", symbol="NIFTY"))
PY
```

If token/config is valid, this returns a payload containing `spot_price`, `provider="dhan"`, and timestamp.

## Upstox (auth + access token)

Add these values to .env (do not commit your real secrets):

```bash
UPSTOX_API_KEY="<your_api_key>"
UPSTOX_API_SECRET="<your_api_secret>"
UPSTOX_REDIRECT_URI="http://localhost:8000/callback"
UPSTOX_ACCESS_TOKEN="<fill_after_exchange>"
```

Exchange the one-time authorization code for an access token:

```bash
python scripts/upstox_token.py --code "<authorization_code>"
```

Copy the `access_token` from the output into `UPSTOX_ACCESS_TOKEN` in .env.

## API Endpoints

- `GET /` : Service running check
- `GET /health` : Liveness check
- `GET /metrics` : In-memory request metrics
- `GET /nifty` : Latest market data snapshot
- `GET /returns` : Log returns
- `GET /forecast-vol` : Annualized volatility forecast
- `GET /fair-price` : Theoretical fair option price
- `GET /mispricing` : Mispricing vs fair value
- `GET /regime` : Volatility regime label
- `GET /strategy` : Consolidated pipeline + strategy output

Query params supported on pipeline endpoints:

- `symbol` (default: `NIFTY`)
- `trading_horizon` (optional: `day_trader`, `positional`, `long_term`)

## Notes

- This project is intended for research and decision support, not automated trading execution.
- Internet access is required for market data fetch (`yfinance`).
- If your running container does not show all endpoints (for example `/health`), rebuild the image to ensure it matches latest source code.
