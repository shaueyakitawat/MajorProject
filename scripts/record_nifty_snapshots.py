"""
NIFTY Live Option Chain Snapshot Recorder
=========================================
Captures real live NIFTY option chain snapshots into SQLite DB
for IEEE paper validation and reproducible backtesting.
"""

import os
import sys
import time
import sqlite3
import json
import logging
from datetime import datetime
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.option_chain_service import get_spot_price, get_full_chain

logger = logging.getLogger("snapshot_recorder")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

DB_PATH = PROJECT_ROOT / "data" / "nifty_live_snapshots.db"


def init_db(db_path: Path = DB_PATH):
    """Initialize SQLite database schema for live snapshots."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS option_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        symbol TEXT NOT NULL,
        spot_price REAL NOT NULL,
        expiry_date TEXT NOT NULL,
        strike REAL NOT NULL,
        option_type TEXT NOT NULL,
        ltp REAL,
        iv REAL,
        oi INTEGER,
        volume INTEGER,
        bid REAL,
        ask REAL,
        delta REAL,
        gamma REAL,
        theta REAL,
        vega REAL
    )
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pipeline_signals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        spot_price REAL NOT NULL,
        strike REAL NOT NULL,
        option_type TEXT NOT NULL,
        market_price REAL NOT NULL,
        fair_price REAL NOT NULL,
        mispricing_pct REAL NOT NULL,
        is_mispriced INTEGER NOT NULL,
        regime TEXT NOT NULL,
        egarch_vol REAL NOT NULL,
        vrp REAL NOT NULL,
        z_score REAL NOT NULL
    )
    """)
    
    conn.commit()
    conn.close()
    logger.info(f"Initialized database at: {db_path}")


def record_snapshot(symbol: str = "NIFTY", db_path: Path = DB_PATH):
    """Fetch current live option chain and record into database."""
    init_db(db_path)
    
    logger.info(f"Fetching live option chain snapshot for {symbol}...")
    try:
        chain_data = get_full_chain(symbol=symbol)
    except Exception as exc:
        logger.error(f"Failed to fetch live option chain: {exc}")
        return 0

    spot = chain_data.get("spot_price", 0.0)
    expiry = chain_data.get("expiry_date", "")
    timestamp = chain_data.get("timestamp", datetime.now().isoformat())
    chain_list = chain_data.get("chain", [])

    if not chain_list or spot <= 0:
        logger.warning("No option chain data retrieved.")
        return 0

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    records_added = 0

    for strike_item in chain_list:
        strike = strike_item.get("strike", 0.0)
        
        for opt_type in ["call", "put"]:
            opt = strike_item.get(opt_type)
            if not opt:
                continue
            
            cursor.execute("""
            INSERT INTO option_snapshots (
                timestamp, symbol, spot_price, expiry_date, strike, option_type,
                ltp, iv, oi, volume, bid, ask, delta, gamma, theta, vega
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                timestamp, symbol, spot, expiry, strike, opt_type.upper(),
                opt.get("ltp"), opt.get("iv"), opt.get("oi"), opt.get("volume"),
                opt.get("bid"), opt.get("ask"), opt.get("delta"), opt.get("gamma"),
                opt.get("theta"), opt.get("vega")
            ))
            records_added += 1

    conn.commit()
    conn.close()
    logger.info(f"✅ Recorded {records_added} option contracts at {timestamp} (Spot: {spot:.2f})")
    return records_added


def record_loop(interval_seconds: int = 60, symbol: str = "NIFTY"):
    """Continuously record live snapshots at given interval."""
    logger.info(f"Starting continuous snapshot recording for {symbol} every {interval_seconds}s...")
    while True:
        try:
            record_snapshot(symbol=symbol)
        except Exception as e:
            logger.error(f"Error in recording loop: {e}")
        time.sleep(interval_seconds)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Record live NIFTY option chain snapshots.")
    parser.add_argument("--once", action="store_true", help="Record a single snapshot and exit")
    parser.add_argument("--interval", type=int, default=60, help="Interval in seconds for continuous mode")
    args = parser.parse_args()

    if args.once:
        record_snapshot()
    else:
        record_loop(interval_seconds=args.interval)
