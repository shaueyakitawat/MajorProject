"""Download and validate daily NIFTY 50 OHLC data aligned to NSE option dates."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OPTIONS = ROOT / "data" / "research" / "nifty_options_daily.csv"
OUTPUT = ROOT / "data" / "research" / "nifty50_index_daily.csv"
RAW = ROOT / "data" / "research" / "raw" / "nifty50_yahoo_chart.json"
MANIFEST = ROOT / "data" / "research" / "nifty50_index_manifest.json"
REPORT = ROOT / "docs" / "research" / "nifty50_index_validation_report.md"
SOURCE_URL = (
    "https://query1.finance.yahoo.com/v8/finance/chart/%5ENSEI"
    "?period1=1719792000&period2=1767225600&interval=1d"
    "&events=history&includeAdjustedClose=true"
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def option_dates() -> set[str]:
    with OPTIONS.open(newline="", encoding="utf-8-sig") as handle:
        return {row["trade_date"] for row in csv.DictReader(handle) if row.get("trade_date")}


def number(value: object) -> str:
    return "" if value is None else format(float(value), ".15g")


def main() -> int:
    dates = option_dates()
    start = min(dates)
    end = max(dates)
    response = requests.get(SOURCE_URL, timeout=60, headers={"User-Agent": "NIFTY-research/1.0"})
    response.raise_for_status()
    raw_bytes = response.content
    RAW.parent.mkdir(parents=True, exist_ok=True)
    RAW.write_bytes(raw_bytes)
    payload = response.json()
    result = payload["chart"]["result"][0]
    meta = result.get("meta", {})
    timestamps = result.get("timestamp", [])
    quote = result["indicators"]["quote"][0]
    rows = []
    for index, timestamp in enumerate(timestamps):
        day = datetime.fromtimestamp(timestamp, timezone.utc).date().isoformat()
        rows.append({
            "trade_date": day,
            "open": number(quote["open"][index]),
            "high": number(quote["high"][index]),
            "low": number(quote["low"][index]),
            "close": number(quote["close"][index]),
            "source": "Yahoo Finance chart API (^NSEI)",
        })
    rows = [row for row in rows if start <= row["trade_date"] <= end]
    duplicate_dates = sorted(day for day in {row["trade_date"] for row in rows}
                             if sum(row["trade_date"] == day for row in rows) > 1)
    invalid = []
    for row in rows:
        values = [float(row[field]) for field in ("open", "high", "low", "close")]
        if any(value <= 0 for value in values):
            invalid.append({"trade_date": row["trade_date"], "reason": "non_positive_price"})
        elif row["high"] and row["low"] and (
            float(row["high"]) < max(float(row["open"]), float(row["close"]), float(row["low"]))
            or float(row["low"]) > min(float(row["open"]), float(row["close"]), float(row["high"]))
        ):
            invalid.append({"trade_date": row["trade_date"], "reason": "invalid_ohlc"})
    present = {row["trade_date"] for row in rows}
    missing = sorted(dates - present)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["trade_date", "open", "high", "low", "close", "source"])
        writer.writeheader()
        writer.writerows(rows)
    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "requested_date_range": {"start": start, "end": end},
        "source": {
            "provider": "Yahoo Finance",
            "symbol": "^NSEI",
            "url": SOURCE_URL,
            "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
            "raw_path": str(RAW.relative_to(ROOT)),
            "raw_sha256": sha256(raw_bytes),
            "metadata": meta,
            "official_alternative": "https://www.niftyindices.com/reports/historical-data",
            "limitations": [
                "Yahoo Finance is a third-party redistribution source, not the NSE exchange archive.",
                "OHLC provenance and licensing/academic redistribution rights are subject to Yahoo Finance terms.",
                "The official NIFTY Indices historical portal is dynamic; no stable direct export was used.",
            ],
        },
        "options_alignment": {
            "options_distinct_dates": len(dates),
            "index_observations": len(rows),
            "missing_options_dates": missing,
        },
        "validation": {
            "duplicate_dates": duplicate_dates,
            "invalid_records": invalid,
            "date_min": min((row["trade_date"] for row in rows), default=None),
            "date_max": max((row["trade_date"] for row in rows), default=None),
            "null_or_empty_fields": {
                field: sum(not row[field] for row in rows)
                for field in ("trade_date", "open", "high", "low", "close", "source")
            },
        },
    }
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    report = [
        "# NIFTY 50 Daily Index Data Validation Report", "",
        "## Source and provenance", "",
        "- Source: Yahoo Finance chart API, symbol `^NSEI`.",
        f"- URL: `{SOURCE_URL}`",
        f"- Raw response: `{RAW.relative_to(ROOT)}`",
        f"- Raw SHA-256: `{manifest['source']['raw_sha256']}`",
        "- Official alternative: [NIFTY Indices historical data](https://www.niftyindices.com/reports/historical-data).",
        "- This dataset is third-party data; licensing and academic redistribution rights are not established by this acquisition.",
        "",
        "## Coverage and alignment", "",
        f"- Options distinct trading dates: **{len(dates)}** ({start} to {end})",
        f"- Index observations: **{len(rows)}** ({manifest['validation']['date_min']} to {manifest['validation']['date_max']})",
        f"- Missing dates relative to options: **{len(missing)}**",
        f"- Missing date list: `{', '.join(missing) if missing else 'none'}`",
        "",
        "## Validation", "",
        f"- Duplicate dates: **{len(duplicate_dates)}**",
        f"- Invalid OHLC/non-positive records: **{len(invalid)}**",
        f"- Null/empty fields: `{json.dumps(manifest['validation']['null_or_empty_fields'])}`",
        "",
        "No prices were interpolated, synthesized, or filled.",
        "",
    ]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(report), encoding="utf-8")
    print(json.dumps({
        "options_dates": len(dates), "index_rows": len(rows),
        "missing_dates": len(missing), "duplicate_dates": len(duplicate_dates),
        "invalid_records": len(invalid), "source": SOURCE_URL,
    }, indent=2))
    return 0 if not duplicate_dates and not invalid else 1


if __name__ == "__main__":
    raise SystemExit(main())
