import pandas as pd
import numpy as np
from pathlib import Path
import os
import glob
from datetime import datetime

class NSEDataService:
    def __init__(self, data_dir=r"d:\MajorProject\data\nse_bhavcopy"):
        self.data_dir = Path(data_dir)
        self._data_cache = {}
        
    def _parse_date(self, date_str):
        # Handle formats like '01-FEB-2024' or datetime objects
        if isinstance(date_str, datetime):
            return date_str
        elif isinstance(date_str, str):
            try:
                return datetime.strptime(date_str, "%d-%b-%Y")
            except ValueError:
                # Some legacy Bhavcopies use YYYY-MM-DD
                return pd.to_datetime(date_str).to_pydatetime()
        elif isinstance(date_str, pd.Timestamp):
            return date_str.to_pydatetime()
            
        return pd.to_datetime(date_str)

    def load_bhavcopy_for_date(self, target_date: datetime) -> pd.DataFrame:
        """Loads and filters a single day's Bhavcopy for NIFTY Index Options"""
        date_str_key = target_date.strftime("%Y-%m-%d")
        
        if date_str_key in self._data_cache:
            return self._data_cache[date_str_key]

        # foDDMMMYYYYbhav.csv
        day = target_date.strftime("%d")
        month = target_date.strftime("%b").upper()
        year = target_date.strftime("%Y")
        
        file_name = f"fo{day}{month}{year}bhav.csv"
        file_path = self.data_dir / file_name
        
        if not file_path.exists():
            return pd.DataFrame()
            
        # Read F&O CSV
        df = pd.read_csv(file_path, skipinitialspace=True)
        
        # Filter for NIFTY Index Options
        options_df = df[(df["INSTRUMENT"] == "OPTIDX") & (df["SYMBOL"] == "NIFTY")].copy()
        
        if options_df.empty:
            return pd.DataFrame()
            
        # Parse Expiry Dates
        options_df["EXPIRY_DT"] = pd.to_datetime(options_df["EXPIRY_DT"], format="%d-%b-%Y")
        
        # Calculate DTE (Days to Expiry)
        timestamp = pd.to_datetime(options_df["TIMESTAMP"].iloc[0], format="%d-%b-%Y")
        options_df["DTE"] = (options_df["EXPIRY_DT"] - timestamp).dt.days
        
        # Cache and return
        self._data_cache[date_str_key] = options_df
        return options_df
        
    def get_real_option_price(self, date: datetime, strike: float, option_type: str, min_dte: int = 1) -> float:
        """
        Fetches the actual closing market price for a specific option contract.
        If multiple expiries exist, fetches the nearest expiry that has at least min_dte days.
        """
        df = self.load_bhavcopy_for_date(date)
        if df.empty:
            return None
            
        opt_type_mapped = "CE" if option_type.lower() == "call" else "PE"
        
        # Filter by strike and type
        contract_df = df[(df["STRIKE_PR"] == strike) & (df["OPTION_TYP"] == opt_type_mapped)]
        
        if contract_df.empty:
            return None
            
        # Filter by minimum DTE to avoid expiry day anomalies
        valid_expiries = contract_df[contract_df["DTE"] >= min_dte]
        if valid_expiries.empty:
            # Fallback to absolute nearest if everything is expiring very soon
            valid_expiries = contract_df
            
        # Get the nearest expiry (smallest DTE)
        nearest = valid_expiries.loc[valid_expiries["DTE"].idxmin()]
        
        # For mispricing analysis, CLOSE or SETTLE_PR are the most stable metrics
        close_price = nearest["CLOSE"]
        
        # Ignore dead contracts (0 price or minimal trade volume)
        if close_price <= 0.05 or nearest["CONTRACTS"] < 10:
            return None
            
        return float(close_price)
