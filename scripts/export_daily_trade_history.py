#!/usr/bin/env python3
"""Export the persistent paper-trade ledger grouped by trading day."""

import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "nifty_live_snapshots.db"
OUTPUT_PATH = PROJECT_ROOT / "outputs" / "DAILY_TRADE_HISTORY.md"


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

    lines = [
        "# Daily NIFTY Paper-Trade History",
        "",
        f"Generated: `{datetime.now().isoformat(timespec='seconds')}`",
        "",
        "This report is generated from `data/nifty_live_snapshots.db`. Open positions are marked separately from closed trades.",
        "",
    ]

    for day in sorted(grouped, reverse=True):
        day_rows = grouped[day]
        closed = [row for row in day_rows if row["status"] == "CLOSED"]
        open_rows = [row for row in day_rows if row["status"] == "OPEN"]
        net = sum(float(row["net_pnl"] or 0) for row in closed)
        gross = sum(float(row["gross_pnl"] or 0) for row in closed)
        fees = sum(float(row["friction_cost"] or 0) for row in closed)
        wins = sum(1 for row in closed if float(row["net_pnl"] or 0) > 0)
        losses = len(closed) - wins

        lines.extend([
            f"## {day}",
            "",
            "| Metric | Value |",
            "| :--- | ---: |",
            f"| Closed trades | {len(closed)} |",
            f"| Open positions | {len(open_rows)} |",
            f"| Winning trades | {wins} |",
            f"| Losing trades | {losses} |",
            f"| Gross closed P&L | {money(gross)} |",
            f"| Closed fees | {money(fees)} |",
            f"| Net closed P&L | **{money(net)}** |",
            "",
            "### Strategy Summary",
            "",
            "| Strategy | Status | Trades | Net P&L |",
            "| :--- | :--- | ---: | ---: |",
        ])

        strategy_groups = defaultdict(list)
        for row in day_rows:
            strategy_groups[(row["strategy"], row["status"])].append(row)
        for (strategy, status), strategy_rows in sorted(strategy_groups.items()):
            strategy_net = sum(float(row["net_pnl"] or 0) for row in strategy_rows)
            lines.append(f"| {strategy} | {status} | {len(strategy_rows)} | {money(strategy_net)} |")

        lines.extend([
            "",
            "### Trade Ledger",
            "",
            "| ID | Status | Strategy | Instrument | Side | Qty | Entry | Exit | Entry Px | Exit Px | Gross P&L | Fees | Net P&L | Reason |",
            "| :--- | :--- | :--- | :--- | :---: | ---: | :--- | :--- | ---: | ---: | ---: | ---: | ---: | :--- |",
        ])
        for row in day_rows:
            reason = str(row["exit_reason"] or "OPEN").replace("|", "/").replace("\n", " ")
            entry_time = str(row["entry_time"] or "--")
            exit_time = str(row["exit_time"] or "--")
            qty_val = int(row["qty"] or 65)
            exit_px_str = f"{float(row['exit_price']):.2f}" if row["exit_price"] is not None else "--"
            lines.append(
                f"| `{row['trade_id']}` | {row['status']} | {row['strategy']} | {row['instrument']} | {row['side']} | {qty_val} | "
                f"{entry_time} | {exit_time} | {float(row['entry_price'] or 0):.2f} | "
                f"{exit_px_str} | {money(float(row['gross_pnl'] or 0))} | "
                f"{money(float(row['friction_cost'] or 0))} | {money(float(row['net_pnl'] or 0))} | {reason} |"
            )
        lines.append("")

    OUTPUT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH} ({len(rows)} trades)")


if __name__ == "__main__":
    main()
