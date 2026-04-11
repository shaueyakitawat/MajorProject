"""
Walk-Forward Backtesting Engine

Validates whether the composite trading signal (price mispricing + vol spread)
has predictive power across multiple timeframes using out-of-sample testing.
"""

import logging
import math
import numpy as np
import pandas as pd
import yfinance as yf
from arch import arch_model
from scipy.stats import norm

from backend.services.pricing_service import black_scholes_price
from backend.services.implied_volatility_service import calculate_implied_volatility
from backend.infrastructure.annualization_engine import apply_dynamic_annualization

logger = logging.getLogger("api")

# ── Configuration ──────────────────────────────────────────────────────────────

TIMEFRAME_CONFIG = {
    "1m":  {"period": "5d",   "interval": "1m"},
    "5m":  {"period": "15d",  "interval": "5m"},
    "15m": {"period": "30d",  "interval": "15m"},
    "1d":  {"period": "6mo",  "interval": "1d"},
}

TRAIN_WINDOW = 60   # rolling training window size
RISK_FREE_RATE = 0.06
FALLBACK_T = 0.1    # time-to-expiry fallback (years)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _fetch_backtest_data(symbol: str, timeframe: str) -> pd.DataFrame:
    """Fetch OHLCV data for backtest, cleaned and sorted."""
    cfg = TIMEFRAME_CONFIG[timeframe]

    data = yf.download(
        symbol,
        period=cfg["period"],
        interval=cfg["interval"],
        auto_adjust=True,
        progress=False,
    )

    # Flatten MultiIndex columns
    data.columns = [c[0] if isinstance(c, tuple) else c for c in data.columns]
    data = data.dropna(how="all").sort_index()

    if data.empty or len(data) < TRAIN_WINDOW + 2:
        raise ValueError(
            f"Insufficient data for backtest: got {len(data)} rows, "
            f"need at least {TRAIN_WINDOW + 2}"
        )

    # Compute log returns
    data["log_return"] = np.log(data["Close"] / data["Close"].shift(1))
    data = data.dropna(subset=["log_return"])

    return data


def _egarch_forecast(returns: pd.Series) -> float | None:
    """Run EGARCH(1,1) on a window of returns. Returns raw daily-scale vol."""
    try:
        pct = returns * 100
        model = arch_model(pct, vol="EGARCH", p=1, q=1, dist="normal")
        fit = model.fit(disp="off", show_warning=False)
        fcast = fit.forecast(horizon=1)
        var_1 = fcast.variance.values[-1, 0]
        return float(np.sqrt(var_1)) / 100      # back to decimal, daily scale
    except Exception:
        return None


def _compute_signal(
    spot: float,
    egarch_vol_ann: float,
    market_price: float,
    strike: float,
    T: float,
) -> dict | None:
    """
    Compute composite signal at a single time step.

    Returns dict with price_score, vol_score, final_score, iv, fair_price
    or None if computation fails.
    """
    if spot <= 0 or egarch_vol_ann <= 0 or T <= 0:
        return None

    # Fair price via Black-Scholes
    try:
        fair_price = black_scholes_price(
            spot=spot,
            strike=strike,
            time_to_expiry=T,
            risk_free_rate=RISK_FREE_RATE,
            volatility=egarch_vol_ann,
            option_type="call",
        )
    except Exception:
        return None

    if fair_price <= 0:
        return None

    # Implied volatility
    iv = calculate_implied_volatility(
        S=spot, K=strike, T=T,
        r=RISK_FREE_RATE,
        market_price=market_price,
        option_type="call",
    )

    price_score = (market_price - fair_price) / fair_price
    vol_score = (iv - egarch_vol_ann) if iv is not None else 0.0
    final_score = 0.6 * price_score + 0.4 * vol_score

    return {
        "fair_price": fair_price,
        "iv": iv,
        "price_score": price_score,
        "vol_score": vol_score,
        "final_score": final_score,
    }


# ── Main Engine ────────────────────────────────────────────────────────────────

def run_backtest(symbol: str = "^NSEI", timeframe: str = "1d") -> dict:
    """
    Execute walk-forward backtest for a given symbol and timeframe.

    Args:
        symbol: Ticker symbol (default "^NSEI")
        timeframe: One of "1m", "5m", "15m", "1d"

    Returns:
        dict with backtest statistics
    """
    if timeframe not in TIMEFRAME_CONFIG:
        raise ValueError(f"Unsupported timeframe: {timeframe}")

    cfg = TIMEFRAME_CONFIG[timeframe]

    logger.info(f"[BACKTEST] Starting | symbol={symbol} timeframe={timeframe}")

    # Step 1: Fetch data
    data = _fetch_backtest_data(symbol, timeframe)
    closes = data["Close"].values
    returns = data["log_return"].values
    N = len(data)

    logger.info(f"[BACKTEST] Data fetched | rows={N} | range={data.index[0]} → {data.index[-1]}")

    # Try to get option chain once (it doesn't change per bar)
    option_strike = None
    option_market_price = None
    option_T = FALLBACK_T

    try:
        ticker = yf.Ticker(symbol)
        expiries = ticker.options
        if expiries:
            nearest_expiry = expiries[0]
            chain = ticker.option_chain(nearest_expiry)
            calls = chain.calls
            if not calls.empty:
                spot_now = float(closes[-1])
                calls["strike_diff"] = (calls["strike"] - spot_now).abs()
                atm_row = calls.loc[calls["strike_diff"].idxmin()]
                option_strike = float(atm_row["strike"])
                ltp = float(atm_row["lastPrice"])
                bid = float(atm_row["bid"])
                ask = float(atm_row["ask"])
                option_market_price = ltp if ltp > 0 else ((bid + ask) / 2 if bid > 0 and ask > 0 else None)

                # Parse expiry for T
                import dateutil.parser
                exp_dt = dateutil.parser.parse(str(nearest_expiry))
                from datetime import datetime, timezone
                now_utc = datetime.now(timezone.utc)
                if exp_dt.tzinfo is None:
                    exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                secs = max((exp_dt - now_utc).total_seconds(), 0)
                option_T = secs / (365 * 24 * 3600) if secs > 0 else FALLBACK_T

                logger.info(
                    f"[BACKTEST] Option chain loaded | strike={option_strike} "
                    f"mkt_price={option_market_price} T={option_T:.4f}"
                )
    except Exception as e:
        logger.warning(f"[BACKTEST] Option chain unavailable: {e}. Using synthetic pricing.")

    # Step 2–7: Walk-forward loop
    strategy_returns: list[float] = []
    signals: list[int] = []
    skipped = 0

    for i in range(TRAIN_WINDOW, N - 1):
        # Train window
        window_returns = pd.Series(returns[i - TRAIN_WINDOW : i])

        # Step 3: EGARCH on rolling window
        daily_vol = _egarch_forecast(window_returns)
        if daily_vol is None:
            skipped += 1
            continue

        # Map backtest timeframe to annualization-engine timeframe key
        _tf_map = {"1m": "1m", "5m": "5m", "15m": "15m", "1d": "daily"}
        _ann_tf = _tf_map.get(timeframe, "daily")

        if daily_vol <= 0:
            skipped += 1
            continue

        egarch_vol_ann = apply_dynamic_annualization(daily_vol, _ann_tf)
        egarch_vol_ann = max(0.01, min(2.0, egarch_vol_ann))

        spot_i = float(closes[i])

        # Determine strike and market price for this step
        strike_i = option_strike if option_strike is not None else spot_i
        if option_market_price is not None:
            mkt_price_i = option_market_price
        else:
            # Synthetic fallback: BS fair * 1.03
            try:
                fp = black_scholes_price(
                    spot=spot_i, strike=strike_i, time_to_expiry=option_T,
                    risk_free_rate=RISK_FREE_RATE, volatility=egarch_vol_ann,
                    option_type="call"
                )
                mkt_price_i = fp * 1.03 if fp > 0 else None
            except Exception:
                mkt_price_i = None

        if mkt_price_i is None or mkt_price_i <= 0:
            skipped += 1
            continue

        # Step 4: Compute signal
        sig = _compute_signal(
            spot=spot_i,
            egarch_vol_ann=egarch_vol_ann,
            market_price=mkt_price_i,
            strike=strike_i,
            T=option_T,
        )

        if sig is None:
            skipped += 1
            continue

        final_score = sig["final_score"]

        # Step 6: Direction
        if final_score > 0:
            direction = -1    # overpriced → sell
        elif final_score < 0:
            direction = 1     # underpriced → buy
        else:
            direction = 0

        # Step 5: Future return
        future_return = (closes[i + 1] - closes[i]) / closes[i]

        # Step 7: Strategy return
        strat_ret = direction * future_return
        strategy_returns.append(strat_ret)
        signals.append(direction)

    # Step 8: Statistical metrics
    num_trades = len(strategy_returns)
    if num_trades < 2:
        logger.warning(f"[BACKTEST] Too few trades ({num_trades}). Cannot compute stats.")
        return {
            "timeframe": timeframe,
            "mean_return": None,
            "sharpe_ratio": None,
            "t_stat": None,
            "hit_rate": None,
            "num_trades": num_trades,
            "skipped": skipped,
            "error": "Insufficient trades for statistical analysis",
        }

    sr = np.array(strategy_returns)
    mean_ret = float(np.mean(sr))
    std_dev = float(np.std(sr, ddof=1))

    sharpe = mean_ret / std_dev if std_dev > 0 else 0.0
    t_stat = mean_ret / (std_dev / math.sqrt(num_trades)) if std_dev > 0 else 0.0
    hit_rate = float(np.sum(sr > 0) / num_trades) * 100

    logger.info(
        f"[BACKTEST] Complete | trades={num_trades} skipped={skipped} "
        f"sharpe={sharpe:.4f} t={t_stat:.4f} hit={hit_rate:.1f}%"
    )

    return {
        "timeframe": timeframe,
        "mean_return": round(mean_ret, 6),
        "sharpe_ratio": round(sharpe, 4),
        "t_stat": round(t_stat, 4),
        "hit_rate": round(hit_rate, 2),
        "num_trades": num_trades,
        "skipped": skipped,
    }
