# Data Service
# Handles market data fetching and preprocessing

import yfinance as yf
import pandas as pd
import numpy as np


def fetch_nifty_data() -> pd.DataFrame:
    """
    Fetch NIFTY 50 index data for the last 5 days.
    
    Returns:
        pd.DataFrame: DataFrame with Date, Open, High, Low, Close, Volume columns
    """
    data = yf.download("^NSEI", period="5d")
    
    # Flatten columns (fix MultiIndex problem)
    data.columns = [col[0] if isinstance(col, tuple) else col for col in data.columns]
    
    # Convert index to string for JSON compatibility
    data.reset_index(inplace=True)
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
