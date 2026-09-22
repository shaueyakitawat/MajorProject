import sqlite3
import pandas as pd
from pathlib import Path
from datetime import datetime
import threading
import logging

logger = logging.getLogger(__name__)

class DBService:
    def __init__(self, db_path=r"d:\MajorProject\data\intraday_data.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn_local = threading.local()
        self._init_db()

    def _get_conn(self):
        if not hasattr(self.conn_local, "conn"):
            self.conn_local.conn = sqlite3.connect(
                self.db_path, check_same_thread=False
            )
            # Enable WAL mode for better concurrent write/read performance
            self.conn_local.conn.execute("PRAGMA journal_mode=WAL;")
        return self.conn_local.conn

    def _init_db(self):
        query = """
        CREATE TABLE IF NOT EXISTS option_ticks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            instrument_key TEXT,
            symbol TEXT,
            strike REAL,
            option_type TEXT,
            expiry TEXT,
            timestamp DATETIME,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume INTEGER,
            oi INTEGER
        );
        """
        conn = self._get_conn()
        with conn:
            conn.execute(query)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_symbol_ts ON option_ticks(symbol, timestamp);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_inst_ts ON option_ticks(instrument_key, timestamp);")

    def insert_tick(self, instrument_key: str, symbol: str, strike: float, option_type: str, 
                    expiry: str, timestamp: datetime, open_price: float, high: float, 
                    low: float, close: float, volume: int, oi: int):
        """Insert a single 1-minute tick into the database."""
        query = """
        INSERT INTO option_ticks 
        (instrument_key, symbol, strike, option_type, expiry, timestamp, open, high, low, close, volume, oi)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        conn = self._get_conn()
        with conn:
            conn.execute(query, (
                instrument_key, symbol, strike, option_type, expiry, timestamp,
                open_price, high, low, close, volume, oi
            ))

    def insert_ticks_bulk(self, df: pd.DataFrame):
        """Insert multiple ticks from a DataFrame."""
        if df.empty:
            return
            
        required_cols = ["instrument_key", "symbol", "strike", "option_type", "expiry", 
                         "timestamp", "open", "high", "low", "close", "volume", "oi"]
        
        insert_df = df[required_cols].copy()
        
        # Ensure timestamp is string for SQLite
        if pd.api.types.is_datetime64_any_dtype(insert_df["timestamp"]):
            insert_df["timestamp"] = insert_df["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
            
        conn = self._get_conn()
        insert_df.to_sql("option_ticks", conn, if_exists="append", index=False)

    def get_aggregated_bars(self, target_date: datetime, symbol: str = "NIFTY", timeframe="5min") -> pd.DataFrame:
        """
        Queries raw 1-minute ticks for a given date and resamples down to the target timeframe (e.g., '5min', '15min').
        Formats output to exactly match the nse_data_service.py schema.
        
        Returns DataFrame columns:
        INSTRUMENT, SYMBOL, EXPIRY_DT, STRIKE_PR, OPTION_TYP, OPEN, HIGH, LOW, CLOSE, CONTRACTS, OPEN_INT, TIMESTAMP, DTE
        """
        date_str = target_date.strftime("%Y-%m-%d")
        start_ts = f"{date_str} 00:00:00"
        end_ts = f"{date_str} 23:59:59"

        query = """
        SELECT instrument_key, symbol, strike, option_type, expiry, timestamp, 
               open, high, low, close, volume, oi
        FROM option_ticks
        WHERE symbol = ? AND timestamp >= ? AND timestamp <= ?
        """
        
        conn = self._get_conn()
        df = pd.read_sql_query(query, conn, params=(symbol, start_ts, end_ts))
        
        if df.empty:
            return pd.DataFrame()

        # Convert timestamp to proper datetime
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df.set_index("timestamp", inplace=True)

        # Resample per contract (instrument_key)
        # We need OHLC logic for prices, sum for volume, last for OI.
        agg_funcs = {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
            "oi": "last",
            "symbol": "last",
            "strike": "last",
            "option_type": "last",
            "expiry": "last"
        }
        
        # Group by instrument_key, then resample
        resampled_dfs = []
        for key, group in df.groupby("instrument_key"):
            resampled = group.resample(timeframe).agg(agg_funcs).dropna()
            if not resampled.empty:
                resampled.reset_index(inplace=True)
                # Map to nse schema
                resampled["INSTRUMENT"] = "OPTIDX"
                resampled["SYMBOL"] = resampled["symbol"]
                resampled["EXPIRY_DT"] = pd.to_datetime(resampled["expiry"])
                resampled["STRIKE_PR"] = resampled["strike"]
                resampled["OPTION_TYP"] = resampled["option_type"].apply(lambda x: "CE" if str(x).lower() == "call" else "PE")
                resampled["OPEN"] = resampled["open"]
                resampled["HIGH"] = resampled["high"]
                resampled["LOW"] = resampled["low"]
                resampled["CLOSE"] = resampled["close"]
                resampled["CONTRACTS"] = resampled["volume"]
                resampled["OPEN_INT"] = resampled["oi"]
                resampled["TIMESTAMP"] = resampled["timestamp"]
                
                # Calculate DTE
                resampled["DTE"] = (resampled["EXPIRY_DT"] - resampled["TIMESTAMP"]).dt.days
                
                # Keep matching schema cols
                final_cols = ["INSTRUMENT", "SYMBOL", "EXPIRY_DT", "STRIKE_PR", "OPTION_TYP", 
                              "OPEN", "HIGH", "LOW", "CLOSE", "CONTRACTS", "OPEN_INT", "TIMESTAMP", "DTE"]
                resampled_dfs.append(resampled[final_cols])
                
        if not resampled_dfs:
            return pd.DataFrame()
            
        return pd.concat(resampled_dfs, ignore_index=True)
