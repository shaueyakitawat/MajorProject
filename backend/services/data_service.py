# Data Service
# Handles market data fetching and preprocessing

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime


TARGET_CANDLES = 2000


def _map_symbol_for_provider(symbol: str) -> str:
    symbol_map = {
        "NIFTY": "^NSEI"
    }
    return symbol_map.get(symbol.upper(), symbol)


def _get_fetch_window_for_timeframe(timeframe: str) -> tuple[str, str]:
    timeframe_window_map = {
        "1m": ("7d", "1m"),
        "5m": ("60d", "5m"),
        "15m": ("60d", "15m"),
        "30m": ("60d", "30m"),
        "1h": ("730d", "60m"),
        "daily": ("10y", "1d"),
        "weekly": ("max", "1wk"),
    }
    return timeframe_window_map.get(timeframe, ("7d", "1m"))


def fetch_nifty_data(symbol: str = "NIFTY", timeframe: str = "1m") -> pd.DataFrame:
    """
    Fetch market data for the requested symbol and timeframe.
    
    Returns:
        pd.DataFrame: DataFrame with Date, Open, High, Low, Close, Volume columns
    """
    ticker_symbol = _map_symbol_for_provider(symbol)
    period, interval = _get_fetch_window_for_timeframe(timeframe)

    data = yf.download(
        ticker_symbol,
        period=period,
        interval=interval,
        auto_adjust=True,
        progress=False,
    )
    
    # Flatten columns (fix MultiIndex problem)
    data.columns = [col[0] if isinstance(col, tuple) else col for col in data.columns]

    # Drop fully empty rows from intraday payload
    data = data.dropna(how="all")

    if data.empty:
        raise ValueError(
            f"No data returned from yfinance for symbol '{symbol}' and timeframe '{timeframe}'"
        )

    if len(data) < TARGET_CANDLES:
        raise ValueError(
            f"Insufficient candles for timeframe '{timeframe}'. "
            f"Required={TARGET_CANDLES}, fetched={len(data)}"
        )

    data = data.tail(TARGET_CANDLES)

    # Ensure timezone-aware index for stable downstream timestamp handling
    if isinstance(data.index, pd.DatetimeIndex) and data.index.tz is None:
        data.index = data.index.tz_localize("UTC")

    # Convert to India Standard Time for API-facing timestamps
    if isinstance(data.index, pd.DatetimeIndex):
        data.index = data.index.tz_convert("Asia/Kolkata")

    print(
        f"[DATA] timeframe={timeframe} period={period} interval={interval} | rows={len(data)} | "
        f"start={data.index.min()} | end={data.index.max()}"
    )
    
    # Convert index to string for JSON compatibility
    data.reset_index(inplace=True)
    if "Datetime" in data.columns and "Date" not in data.columns:
        data.rename(columns={"Datetime": "Date"}, inplace=True)
    data["Date"] = data["Date"].astype(str)
    
    return data


def compute_log_returns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute log returns from Close prices.
    
    Args:
        df: DataFrame containing a 'Close' column
        
    Returns:
        pd.DataFrame: DataFrame with added 'log_return' column, NaN rows removed
    """
    df = df.copy()
    df["log_return"] = np.log(df["Close"] / df["Close"].shift(1))
    df = df.dropna()
    
    return df
