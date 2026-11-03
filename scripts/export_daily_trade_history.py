#!/usr/bin/env python3
"""Export the persistent paper-trade ledger grouped by trading day."""

import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "nifty_live_snapshots.db"
OUTPUT_PATH = PROJECT_ROOT / "outputs" / "DAILY_TRADE_HISTORY.json"


def money(value: float) -> str:
    return f"₹{value:,.2f}" if value >= 0 else f"-₹{abs(value):,.2f}"


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT *
        FROM live_paper_trades
        ORDER BY substr(entry_timestamp, 1, 10) DESC,
                 entry_timestamp DESC,
                 CAST(REPLACE(trade_id, 'TRD-', '') AS INTEGER) DESC
        """
    ).fetchall()
    conn.close()

    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["entry_timestamp"] or "unknown")[:10]].append(row)

    import json
    json_data = {
        "generated": datetime.now().isoformat(timespec='seconds'),
        "total_trades": len(rows),
        "days": {}
    }

    for day in sorted(grouped, reverse=True):
        day_rows = grouped[day]
        closed = [dict(row) for row in day_rows if row["status"] == "CLOSED"]
        open_rows = [dict(row) for row in day_rows if row["status"] == "OPEN"]
        net = sum(float(row["net_pnl"] or 0) for row in closed)
        gross = sum(float(row["gross_pnl"] or 0) for row in closed)
        fees = sum(float(row["friction_cost"] or 0) for row in closed)
        wins = sum(1 for row in closed if float(row["net_pnl"] or 0) > 0)
        losses = len(closed) - wins

        json_data["days"][day] = {
            "closed_trades": len(closed),
            "open_positions": len(open_rows),
            "winning_trades": wins,
            "losing_trades": losses,
            "gross_closed_pnl": gross,
            "fees": fees,
            "net_closed_pnl": net,
            "trades": [dict(row) for row in day_rows]
        }

    with open(OUTPUT_PATH, "w") as f:
        json.dump(json_data, f, indent=2)
    print(f"Wrote {OUTPUT_PATH} ({len(rows)} trades across {len(grouped)} days)")



if __name__ == "__main__":
    main()
