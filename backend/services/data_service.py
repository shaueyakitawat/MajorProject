# Data Service
# Handles market data fetching and preprocessing

import yfinance as yf
import pandas as pd
import numpy as np


def fetch_nifty_data() -> pd.DataFrame:
    """
    Fetch NIFTY 50 index intraday data (1-minute interval) for the last 5 days.
    
    Returns:
        pd.DataFrame: DataFrame with Date, Open, High, Low, Close, Volume columns
    """
    data = yf.download(
        "^NSEI",
        period="5d",
        interval="1m",
        auto_adjust=True,
        progress=False,
    )
    
    # Flatten columns (fix MultiIndex problem)
    data.columns = [col[0] if isinstance(col, tuple) else col for col in data.columns]

    # Drop fully empty rows from intraday payload
    data = data.dropna(how="all")

    if data.empty:
        raise ValueError("No intraday data returned from yfinance for the given symbol")

    # Ensure timezone-aware index for stable downstream timestamp handling
    if isinstance(data.index, pd.DatetimeIndex) and data.index.tz is None:
        data.index = data.index.tz_localize("UTC")

    # Convert to India Standard Time for API-facing timestamps
    if isinstance(data.index, pd.DatetimeIndex):
        data.index = data.index.tz_convert("Asia/Kolkata")

    print(
        f"[DATA] 1m data fetched | rows={len(data)} | "
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
