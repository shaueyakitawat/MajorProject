# Volatility Service
# Handles GARCH/EGARCH volatility forecasting

import math
import os
import pandas as pd
import numpy as np
from arch import arch_model

from backend.infrastructure.annualization_engine import apply_dynamic_annualization
from backend.infrastructure.timeframe_config import get_annualization_factor


DAILY_VOL_WEIGHT = float(os.getenv("VOL_FUSION_DAILY_WEIGHT", "0.7"))
INTRADAY_VOL_WEIGHT = float(os.getenv("VOL_FUSION_INTRADAY_WEIGHT", "0.3"))


def _normalize_weights(daily_weight: float, intraday_weight: float, intraday_available: bool) -> tuple[float, float]:
    if not intraday_available:
        return 1.0, 0.0
    total = daily_weight + intraday_weight
    if total <= 0:
        return 0.5, 0.5
    return daily_weight / total, intraday_weight / total


def _compute_realized_volatility(price_series: pd.Series, timeframe: str) -> float | None:
    if price_series is None or len(price_series) < 2:
        return None

    prices = pd.to_numeric(price_series, errors="coerce").dropna()
    if len(prices) < 2:
        return None

    log_returns = np.log(prices / prices.shift(1)).dropna()
    if log_returns.empty:
        return None

    realized_vol = float(np.sqrt(np.sum(np.square(log_returns))))
    obs_count = len(log_returns)
    if obs_count <= 0:
        return None

    annual_factor = get_annualization_factor(timeframe)
    annualized = realized_vol * math.sqrt(annual_factor / obs_count)
    if not math.isfinite(annualized) or annualized <= 0:
        return None

    return float(annualized)


def compute_intraday_realized_volatility(price_series_5min: pd.Series) -> float | None:
    return _compute_realized_volatility(price_series_5min, "5m")


def _compute_hourly_realized_volatility_from_5m(price_series_5min: pd.Series) -> float | None:
    if price_series_5min is None or len(price_series_5min) < 12:
        return None

    if isinstance(price_series_5min.index, pd.DatetimeIndex):
        hourly_prices = price_series_5min.resample("1h").last().dropna()
    else:
        hourly_prices = price_series_5min.iloc[::12]

    return _compute_realized_volatility(hourly_prices, "1h")


def forecast_volatility(returns_series: pd.Series, price_series_5min: pd.Series | None = None) -> dict:
    """
    Forecast next-period volatility using EGARCH(1,1) and fuse with intraday realized vol.

    Returns dict with daily_vol, intraday_vol, and final_vol (annualized).

    Args:
        returns_series: Series of log returns (daily scale)
        price_series_5min: Series of 5-minute prices for intraday realized vol

    Returns:
        dict: {"daily_vol": float, "intraday_vol": float|None, "final_vol": float}
    """
    percentage_returns = returns_series * 100

    model = arch_model(percentage_returns, vol="EGARCH", p=1, q=1, dist="normal")
    fitted_model = model.fit(disp="off")

    forecast = fitted_model.forecast(horizon=1)
    forecasted_variance = forecast.variance.values[-1, 0]

    forecasted_volatility = np.sqrt(forecasted_variance)
    raw_volatility = forecasted_volatility / 100

    daily_vol = apply_dynamic_annualization(float(raw_volatility), "daily")
    intraday_vol = compute_intraday_realized_volatility(price_series_5min)
    hourly_vol = _compute_hourly_realized_volatility_from_5m(price_series_5min)

    w_daily, w_intraday = _normalize_weights(DAILY_VOL_WEIGHT, INTRADAY_VOL_WEIGHT, intraday_vol is not None)
    final_vol = (w_daily * daily_vol) + (w_intraday * intraday_vol if intraday_vol is not None else 0.0)

    tci = None
    if hourly_vol is not None and intraday_vol is not None:
        tci_values = np.array([daily_vol, hourly_vol, intraday_vol], dtype=float)
        if np.all(np.isfinite(tci_values)):
            tci = float(np.var(tci_values))

    return {
        "daily_vol": float(daily_vol),
        "intraday_vol": float(intraday_vol) if intraday_vol is not None else None,
        "final_vol": float(final_vol),
        "tci": tci,
    }
