"""
backend/services/trade_service.py
================================================================================
Institutional Paper Trading Ledger & Performance Analytics Service.
Queries persistent SQLite database (data/nifty_live_snapshots.db) and provides
institutional metrics: Win Rate, Sharpe Ratio, Profit Factor, Equity Curve,
Daily Breakdowns, and Active Position Telemetry.
================================================================================
"""

import sqlite3
import math
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "nifty_live_snapshots.db"


def _get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_trades_overview(date_filter: Optional[str] = None) -> Dict[str, Any]:
    """
    Returns comprehensive institutional summary of paper trading performance:
    Capital allocation, Win Rate, Gross/Net P&L, Friction, Sharpe Ratio, Profit Factor,
    active positions, and equity curve.
    """
    if not DB_PATH.exists():
        return {
            "summary": {
                "total_trades": 0, "closed_trades": 0, "open_trades": 0,
                "win_count": 0, "loss_count": 0, "win_rate_pct": 0.0,
                "gross_pnl": 0.0, "net_pnl": 0.0, "friction_cost": 0.0,
                "profit_factor": 0.0, "mean_return_pct": 0.0, "annualized_sharpe": 0.0,
                "capital_base": 2500000.0, "cash_buffer": 500000.0,
                "current_equity": 2500000.0
            },
            "active_positions": [],
            "recent_trades": [],
            "equity_curve": [],
            "daily_performance": []
        }

    conn = _get_connection()
    cur = conn.cursor()

    # Base query for all trades
    query = "SELECT * FROM live_paper_trades"
    params = []
    if date_filter:
        query += " WHERE entry_timestamp LIKE ?"
        params.append(f"{date_filter}%")
    query += " ORDER BY rowid ASC"

    rows = cur.execute(query, params).fetchall()
    all_trades = [dict(r) for r in rows]

    # Segregate open and closed
    open_trades = [t for t in all_trades if t.get("status") == "OPEN"]
    closed_trades = [t for t in all_trades if t.get("status") == "CLOSED"]

    total_closed = len(closed_trades)
    wins = [t for t in closed_trades if (t.get("net_pnl") or 0.0) > 0]
    losses = [t for t in closed_trades if (t.get("net_pnl") or 0.0) < 0]

    win_count = len(wins)
    loss_count = len(losses)
    win_rate = round((win_count / total_closed * 100), 1) if total_closed > 0 else 0.0

    gross_pnl = sum((t.get("gross_pnl") or 0.0) for t in closed_trades)
    net_pnl = sum((t.get("net_pnl") or 0.0) for t in closed_trades)
    friction = sum((t.get("friction_cost") or 0.0) for t in closed_trades)

    gross_wins = sum((t.get("gross_pnl") or 0.0) for t in wins)
    gross_losses = abs(sum((t.get("gross_pnl") or 0.0) for t in losses))
    profit_factor = round(gross_wins / gross_losses, 2) if gross_losses > 0 else (99.0 if gross_wins > 0 else 0.0)

    # Returns & Sharpe calculation
    returns = [float(t.get("return_pct") or 0.0) for t in closed_trades]
    mean_return = sum(returns) / len(returns) if returns else 0.0
    if len(returns) > 1:
        variance = sum((r - mean_return) ** 2 for r in returns) / (len(returns) - 1)
        std_return = math.sqrt(variance)
        sharpe = round((mean_return / std_return) * math.sqrt(252), 2) if std_return > 0 else 0.0
    else:
        sharpe = 0.0

    # Unrealized PnL from open trades
    unrealized_pnl = sum((t.get("net_pnl") or 0.0) for t in open_trades)
    margin_used = sum((t.get("entry_price", 0.0) * t.get("qty", 195) * 5.0) if t.get("side") == "SELL" 
                      else (t.get("entry_price", 0.0) * t.get("qty", 195)) for t in open_trades)

    total_equity = 2500000.0 + net_pnl + unrealized_pnl

    # Construct cumulative equity curve
    cumulative = 0.0
    equity_curve = []
    # Seed with initial zero
    equity_curve.append({
        "trade_id": "INIT",
        "timestamp": all_trades[0].get("entry_timestamp", "2026-10-05") if all_trades else "2026-10-05",
        "trade_pnl": 0.0,
        "cumulative_pnl": 0.0,
        "account_equity": 2500000.0
    })

    for t in closed_trades:
        pnl = float(t.get("net_pnl") or 0.0)
        cumulative += pnl
        equity_curve.append({
            "trade_id": t.get("trade_id"),
            "timestamp": t.get("exit_time") or t.get("entry_timestamp", ""),
            "trade_pnl": round(pnl, 2),
            "cumulative_pnl": round(cumulative, 2),
            "account_equity": round(2500000.0 + cumulative, 2)
        })

    # Daily performance aggregation
    daily_map = {}
    for t in all_trades:
        date_str = str(t.get("entry_timestamp", ""))[:10]
        if not date_str or len(date_str) < 10:
            continue
        if date_str not in daily_map:
            daily_map[date_str] = {
                "date": date_str,
                "total_trades": 0,
                "closed_trades": 0,
                "wins": 0,
                "losses": 0,
                "gross_pnl": 0.0,
                "net_pnl": 0.0,
                "friction": 0.0
            }
        d = daily_map[date_str]
        d["total_trades"] += 1
        if t.get("status") == "CLOSED":
            d["closed_trades"] += 1
            pnl = float(t.get("net_pnl") or 0.0)
            if pnl > 0:
                d["wins"] += 1
            elif pnl < 0:
                d["losses"] += 1
            d["gross_pnl"] += float(t.get("gross_pnl") or 0.0)
            d["net_pnl"] += pnl
            d["friction"] += float(t.get("friction_cost") or 0.0)

    daily_performance = []
    for date_key in sorted(daily_map.keys()):
        d = daily_map[date_key]
        wr = round((d["wins"] / d["closed_trades"] * 100), 1) if d["closed_trades"] > 0 else 0.0
        daily_performance.append({
            "date": d["date"],
            "total_trades": d["total_trades"],
            "closed_trades": d["closed_trades"],
            "wins": d["wins"],
            "losses": d["losses"],
            "win_rate_pct": wr,
            "gross_pnl": round(d["gross_pnl"], 2),
            "net_pnl": round(d["net_pnl"], 2),
            "friction": round(d["friction"], 2)
        })

    conn.close()

    return {
        "summary": {
            "total_trades": len(all_trades),
            "closed_trades": total_closed,
            "open_trades": len(open_trades),
            "win_count": win_count,
            "loss_count": loss_count,
            "win_rate_pct": win_rate,
            "gross_pnl": round(gross_pnl, 2),
            "net_pnl": round(net_pnl, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "total_pnl": round(net_pnl + unrealized_pnl, 2),
            "friction_cost": round(friction, 2),
            "profit_factor": profit_factor,
            "mean_return_pct": round(mean_return, 2),
            "annualized_sharpe": sharpe,
            "capital_base": 2500000.0,
            "cash_buffer": 500000.0,
            "current_equity": round(total_equity, 2),
            "margin_used": round(margin_used, 2),
            "free_margin": round(max(0.0, 2000000.0 - margin_used), 2)
        },
        "active_positions": open_trades,
        "recent_trades": closed_trades[-50:],  # Last 50 closed trades
        "equity_curve": equity_curve,
        "daily_performance": daily_performance
    }


def close_trade_in_db(trade_id: str, exit_price: Optional[float] = None, exit_reason: str = "MANUAL_TERMINAL_CLOSE") -> Dict[str, Any]:
    """Manually close an open position in SQLite database."""
    conn = _get_connection()
    cur = conn.cursor()

    row = cur.execute("SELECT * FROM live_paper_trades WHERE trade_id = ? AND status = 'OPEN'", (trade_id,)).fetchone()
    if not row:
        conn.close()
        return {"success": False, "error": f"Open trade {trade_id} not found"}

    trade = dict(row)
    now_dt = datetime.now()
    exit_time_str = now_dt.strftime("%H:%M:%S")

    # Use current_price or provided exit_price
    price = exit_price if exit_price is not None else float(trade.get("current_price") or trade.get("entry_price"))
    entry_p = float(trade.get("entry_price"))
    qty = int(trade.get("qty", 195))
    side = trade.get("side", "SELL").upper()

    if side == "SELL":
        gross = (entry_p - price) * qty
        ret_pct = ((entry_p - price) / entry_p) * 100 if entry_p > 0 else 0.0
    else:
        gross = (price - entry_p) * qty
        ret_pct = ((price - entry_p) / entry_p) * 100 if entry_p > 0 else 0.0

    # Friction estimate
    friction = round(20.0 + (price * qty * 0.0006), 2)
    net_p = round(gross - friction, 2)

    cur.execute("""
        UPDATE live_paper_trades
        SET status = 'CLOSED',
            exit_price = ?,
            exit_time = ?,
            exit_reason = ?,
            gross_pnl = ?,
            net_pnl = ?,
            friction_cost = ?,
            return_pct = ?
        WHERE trade_id = ?
    """, (price, exit_time_str, exit_reason, round(gross, 2), net_p, friction, round(ret_pct, 2), trade_id))

    conn.commit()
    conn.close()

    return {
        "success": True,
        "trade_id": trade_id,
        "exit_price": price,
        "exit_time": exit_time_str,
        "net_pnl": net_p,
        "return_pct": round(ret_pct, 2),
        "exit_reason": exit_reason
    }


def execute_trade_in_db(
    instrument: str,
    side: str = "SELL",
    strike: float = 22950.0,
    option_type: str = "CE",
    qty: int = 195,
    entry_price: float = 143.30,
    entry_fair: Optional[float] = None,
    strategy: str = "RV Short Overvalued (QUANT)",
    expiry: str = "03-Nov-2026",
    target_price: Optional[float] = None,
    stop_price: Optional[float] = None
) -> Dict[str, Any]:
    """
    Executes a new paper trade and commits it directly to SQLite database.
    """
    conn = _get_connection()
    cur = conn.cursor()

    # Find highest numeric ID in live_paper_trades
    rows = cur.execute("SELECT trade_id FROM live_paper_trades WHERE trade_id LIKE 'TRD-%'").fetchall()
    max_id = 902
    for r in rows:
        tid = r["trade_id"]
        try:
            num = int(tid.replace("TRD-", ""))
            if num > max_id:
                max_id = num
        except Exception:
            pass

    new_id = f"TRD-{max_id + 1}"
    now = datetime.now()
    entry_time_str = now.strftime("%H:%M:%S")
    entry_iso_str = now.isoformat()

    fair = entry_fair if entry_fair is not None else round(entry_price * 0.88, 2)
    dev_pct = round(((entry_price - fair) / fair) * 100, 2) if fair > 0 else 0.0
    m_score = round(dev_pct / 50.0, 2)

    tgt = target_price if target_price is not None else (round(entry_price * 0.65, 2) if side.upper() == "SELL" else round(entry_price * 1.5, 2))
    stp = stop_price if stop_price is not None else (round(entry_price * 1.35, 2) if side.upper() == "SELL" else round(entry_price * 0.75, 2))

    cur.execute("""
        INSERT INTO live_paper_trades (
            trade_id, strategy, instrument, strike, option_type, expiry,
            side, qty, entry_price, current_price, entry_fair, entry_spot,
            entry_mscore, entry_dev_pct, entry_time, entry_timestamp,
            gross_pnl, net_pnl, friction_cost, return_pct, converged,
            holding_seconds, status, target_price, stop_price
        ) VALUES (
            ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?,
            0.0, 0.0, 0.0, 0.0, 0,
            0.0, 'OPEN', ?, ?
        )
    """, (
        new_id, strategy, instrument, strike, option_type.upper(), expiry,
        side.upper(), qty, entry_price, entry_price, fair, 22936.75,
        m_score, dev_pct, entry_time_str, entry_iso_str,
        tgt, stp
    ))

    conn.commit()
    conn.close()

    return {
        "success": True,
        "trade_id": new_id,
        "instrument": instrument,
        "side": side.upper(),
        "qty": qty,
        "entry_price": entry_price,
        "entry_fair": fair,
        "entry_time": entry_time_str,
        "target_price": tgt,
        "stop_price": stp,
        "status": "OPEN",
        "message": f"Trade {new_id} successfully executed and committed to active portfolio."
    }


