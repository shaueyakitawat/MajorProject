"""Download and normalize official NSE daily NIFTY option bhavcopy files."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import logging
import re
import sys
import zipfile
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "research" / "nse_bhavcopy_raw"
NORMALIZED_PATH = PROJECT_ROOT / "data" / "research" / "nifty_options_daily.csv"
MANIFEST_PATH = PROJECT_ROOT / "docs" / "research" / "nse_data_manifest.json"
QUALITY_PATH = PROJECT_ROOT / "docs" / "research" / "nse_data_quality_report.md"

DEFAULT_DATES = (date(2024, 7, 1), date(2024, 7, 10))
OLD_BASE = "https://archives.nseindia.com/content/historical/DERIVATIVES"
NEW_BASE = "https://archives.nseindia.com/content/fo"
REQUEST_TIMEOUT = 30

NORMALIZED_FIELDS = [
    "trade_date",
    "expiry",
    "strike",
    "option_type",
    "open",
    "high",
    "low",
    "close",
    "settlement",
    "contracts",
    "turnover",
    "open_interest",
    "source_schema",
    "source_url",
]

FIELD_ALIASES = {
    "instrument": ("INSTRUMENT", "FININSTRMTP"),
    "symbol": ("SYMBOL", "TCKRSYMB"),
    "trade_date": ("TIMESTAMP", "TRADDT", "TRADE_DATE", "DATE"),
    "expiry": ("EXPIRY_DT", "XPRYDT", "EXPIRY_DATE", "EXPIRY"),
    "strike": ("STRIKE_PR", "STRKPRIC", "STRIKE_PRICE", "STRIKE"),
    "option_type": ("OPTION_TYP", "OPTNTP", "OPTION_TYPE"),
    "open": ("OPEN", "OPNPRIC"),
    "high": ("HIGH", "HGHPRIC"),
    "low": ("LOW", "LWPRIC"),
    "close": ("CLOSE", "CLSPRIC"),
    "settlement": ("SETTLE_PR", "STTLMPRIC", "SETTLEMENT_PRICE", "SETTLEMENT"),
    "contracts": ("CONTRACTS", "TTLTRADGVOL", "VOLUME", "TOTAL_TRADED_VOLUME"),
    "turnover": ("VAL_INLAKH", "TTLTRFVAL", "TURNOVER", "TURNOVER_VALUE"),
    "open_interest": ("OPEN_INT", "OPNINTRST", "OPEN_INTEREST", "OI"),
}

logger = logging.getLogger("nse_bhavcopy")


def parse_iso_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Expected YYYY-MM-DD, got {value!r}") from exc


def requested_dates(args: argparse.Namespace) -> list[date]:
    if args.dates:
        return sorted(set(args.dates))
    if args.start_date is None and args.end_date is None:
        return list(DEFAULT_DATES)
    if args.start_date is None or args.end_date is None:
        raise ValueError("--start-date and --end-date must be supplied together")
    if args.end_date < args.start_date:
        raise ValueError("--end-date must not precede --start-date")
    result = []
    current = args.start_date
    while current <= args.end_date:
        result.append(current)
        current += timedelta(days=1)
    return result


def candidate_urls(day: date) -> list[str]:
    month = day.strftime("%b").upper()
    old_url = (
        f"{OLD_BASE}/{day:%Y}/{month}/fo{day:%d}{month}{day:%Y}bhav.csv.zip"
    )
    new_url = f"{NEW_BASE}/BhavCopy_NSE_FO_0_0_0_{day:%Y%m%d}_F_0000.csv.zip"
    if day < date(2024, 7, 8):
        return [old_url, new_url]
    return [new_url, old_url]


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def clean_header(value: str) -> str:
    return re.sub(r"[^A-Z0-9_]", "", value.strip().upper())


def read_csv_payload(payload: bytes) -> tuple[str, list[str], list[dict[str, str]]]:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if not names:
            raise ValueError("ZIP contains no CSV file")
        csv_name = names[0]
        text = archive.read(csv_name).decode("utf-8-sig")
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",|;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        raise ValueError("CSV has no header")
    headers = [header.strip() for header in reader.fieldnames]
    rows = []
    for row in reader:
        rows.append({(key or "").strip(): (value or "").strip() for key, value in row.items()})
    return csv_name, headers, rows


def resolve_columns(headers: Iterable[str]) -> dict[str, str | None]:
    by_clean = {clean_header(header): header for header in headers}
    resolved = {}
    for field, aliases in FIELD_ALIASES.items():
        resolved[field] = next(
            (by_clean[clean_header(alias)] for alias in aliases if clean_header(alias) in by_clean),
            None,
        )
    return resolved


def get_value(row: dict[str, str], column: str | None) -> str:
    return row.get(column, "") if column else ""


def normalize_date_value(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d-%B-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return value


def normalize_numeric_value(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    try:
        number = float(value.replace(",", ""))
    except ValueError:
        return value
    return format(number, ".15g")


def normalize_row(
    row: dict[str, str],
    resolved: dict[str, str | None],
    source_date: date,
) -> dict[str, str]:
    values = {field: get_value(row, column) for field, column in resolved.items()}
    if not values["trade_date"]:
        values["trade_date"] = source_date.isoformat()
    values["trade_date"] = normalize_date_value(values["trade_date"])
    values["expiry"] = normalize_date_value(values["expiry"])
    values["option_type"] = values["option_type"].upper()
    for field in (
        "strike", "open", "high", "low", "close", "settlement",
        "contracts", "turnover", "open_interest",
    ):
        values[field] = normalize_numeric_value(values[field])
    return values


def schema_name(instrument: str) -> str:
    return "legacy" if instrument.upper() == "OPTIDX" else "new" if instrument.upper() == "IDO" else "unknown"


def download_one(
    day: date,
    session: requests.Session,
    user_agent: str,
) -> tuple[dict, list[str], list[dict[str, str]]]:
    attempts = []
    for url in candidate_urls(day):
        entry = {"url": url, "http_status": None, "error": None}
        try:
            response = session.get(
                url,
                headers={"User-Agent": user_agent, "Accept": "application/zip"},
                timeout=REQUEST_TIMEOUT,
            )
            entry["http_status"] = response.status_code
            if response.status_code != 200:
                entry["error"] = f"HTTP {response.status_code}"
                attempts.append(entry)
                logger.warning("%s failed: %s", url, entry["error"])
                continue
            if not response.content.startswith(b"PK"):
                entry["error"] = "HTTP 200 response is not a ZIP payload"
                attempts.append(entry)
                logger.error("%s failed: %s", url, entry["error"])
                continue

            payload = response.content
            csv_name, headers, rows = read_csv_payload(payload)
            sha = sha256_bytes(payload)
            raw_path = RAW_DIR / f"{day:%Y-%m-%d}_{Path(url).name}"
            raw_path.write_bytes(payload)
            logger.info("Downloaded %s (%d CSV rows)", url, len(rows))
            return (
                {
                    "requested_date": day.isoformat(),
                    "status": "downloaded",
                    "source_url": url,
                    "filename": raw_path.name,
                    "raw_path": str(raw_path.relative_to(PROJECT_ROOT)),
                    "sha256": sha,
                    "csv_filename": csv_name,
                    "csv_headers": headers,
                    "csv_row_count": len(rows),
                    "attempts": attempts + [entry],
                },
                headers,
                rows,
            )
        except (OSError, requests.RequestException, ValueError, zipfile.BadZipFile) as exc:
            entry["error"] = str(exc)
            attempts.append(entry)
            logger.exception("%s failed", url)

    statuses = [attempt.get("http_status") for attempt in attempts]
    unavailable = attempts and all(status == 404 for status in statuses if status is not None)
    return (
        {
            "requested_date": day.isoformat(),
            "status": "not_available_404" if unavailable else "failed",
            "source_url": None,
            "filename": None,
            "raw_path": None,
            "sha256": None,
            "csv_filename": None,
            "csv_headers": [],
            "csv_row_count": 0,
            "attempts": attempts,
            "reason": "Both archive URL patterns returned HTTP 404; likely weekend, holiday, or unavailable archive date."
            if unavailable else "All candidate URL attempts failed.",
        },
        [],
        [],
    )


def write_normalized(path: Path, raw_headers: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    headers = list(raw_headers)
    for field in NORMALIZED_FIELDS:
        if field not in headers:
            headers.append(field)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def quality_report(
    manifest: list[dict],
    raw_headers: list[str],
    normalized_rows: list[dict[str, str]],
    resolved: dict[str, str | None],
) -> str:
    successful = [item for item in manifest if item["status"] == "downloaded"]
    missingness = {}
    for field in NORMALIZED_FIELDS:
        missing = sum(not row.get(field, "").strip() for row in normalized_rows)
        missingness[field] = {
            "missing": missing,
            "total": len(normalized_rows),
            "percentage": round(100 * missing / len(normalized_rows), 4)
            if normalized_rows
            else 0.0,
        }
    sides = Counter(row.get("option_type", "") for row in normalized_rows)
    strikes = sorted({row.get("strike", "") for row in normalized_rows if row.get("strike", "")})
    expiries = sorted({row.get("expiry", "") for row in normalized_rows if row.get("expiry", "")})
    zero_volume = sum(
        row.get("contracts", "").strip() in {"0", "0.0", "0.00"} for row in normalized_rows
    )
    schemas = {tuple(item["csv_headers"]) for item in successful}
    schema_note = "No schema differences detected." if len(schemas) <= 1 else (
        f"{len(schemas)} distinct CSV header layouts were observed."
    )
    lines = [
        "# NSE NIFTY Option Data Quality Report",
        "",
        "Generated by `scripts/download_nse_nifty_options.py`.",
        "",
        "## Coverage",
        "",
        f"- Requested dates: {len(manifest)}",
        f"- Downloaded dates: {len(successful)}",
        f"- Failed dates: {len(manifest) - len(successful)}",
        f"- Normalized NIFTY option rows: {len(normalized_rows)}",
        f"- Trade-date coverage in rows: {min((r.get('trade_date', '') for r in normalized_rows), default='')} "
        f"to {max((r.get('trade_date', '') for r in normalized_rows), default='')}",
        f"- Expiry values: {len(expiries)}",
        f"- Strike values: {len(strikes)}",
        "",
        "## Missingness",
        "",
        "| Field | Missing | Total | Missing % |",
        "|---|---:|---:|---:|",
    ]
    lines.extend(
        f"| `{field}` | {item['missing']} | {item['total']} | {item['percentage']:.4f}% |"
        for field, item in missingness.items()
    )
    lines.extend(
        [
            "",
            "## CE/PE counts",
            "",
            f"- CE: {sides.get('CE', 0)}",
            f"- PE: {sides.get('PE', 0)}",
            f"- Other/unmapped option types: {sum(v for k, v in sides.items() if k not in {'CE', 'PE'})}",
            "",
            "## Strike and expiry coverage",
            "",
            f"- Strikes: {', '.join(strikes) if strikes else 'none'}",
            f"- Expiries: {', '.join(expiries) if expiries else 'none'}",
            "",
            "## Zero-volume records",
            "",
            f"- Records with `contracts` equal to zero: {zero_volume}",
            "",
            "## Schema differences",
            "",
            f"- {schema_note}",
            f"- Raw headers observed: {', '.join(raw_headers) if raw_headers else 'none'}",
            "- Normalized source columns by downloaded file:",
        ]
    )
    for item in successful:
        mapping = item.get("normalized_source_columns", {})
        lines.append(
            f"  - `{item['requested_date']}`: "
            + ", ".join(
                f"`{field}` <- `{mapping.get(field)}`" if mapping.get(field)
                else f"`{field}` <- unavailable"
                for field in NORMALIZED_FIELDS
            )
        )
    lines.extend(
        [
            "",
            "## Data limitations",
            "",
            "- Bid, ask, timestamps finer than the trade date, and implied volatility are not manufactured.",
            "- OHLC and settlement values are daily trade/settlement summaries, not bid/ask quotes.",
            "- Missing dates include weekends, exchange holidays, unavailable files, or HTTP failures; inspect the manifest.",
            "- NSE licensing and redistribution permissions for downloaded raw files remain subject to NSE terms and are not established by public accessibility.",
        ]
    )
    return "\n".join(lines) + "\n"


def run(days: list[date]) -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    user_agent = "NIFTY-research-bhavcopy-downloader/1.0"
    existing_manifest = {}
    if MANIFEST_PATH.exists():
        try:
            prior = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
            existing_manifest = {
                item["requested_date"]: item
                for item in prior.get("downloads", [])
                if item.get("requested_date")
            }
        except (OSError, json.JSONDecodeError):
            logger.warning("Existing manifest could not be read; starting a fresh manifest.")
    existing_rows: list[dict[str, str]] = []
    if NORMALIZED_PATH.exists():
        try:
            with NORMALIZED_PATH.open(newline="", encoding="utf-8-sig") as handle:
                existing_rows = [
                    {key: (value or "").strip() for key, value in row.items()}
                    for row in csv.DictReader(handle)
                ]
        except (OSError, csv.Error):
            logger.warning("Existing normalized CSV could not be read; downloaded rows will be rebuilt.")
    manifest = []
    all_headers: list[str] = []
    normalized_rows: list[dict[str, str]] = []
    row_keys: set[tuple[str, str, str, str]] = set()
    resolved: dict[str, str | None] = {field: None for field in FIELD_ALIASES}

    for day in days:
        day_text = day.isoformat()
        prior_item = existing_manifest.get(day_text)
        prior_rows = [row for row in existing_rows if row.get("trade_date") == day_text]
        if prior_item and prior_item.get("status") == "downloaded" and prior_rows:
            manifest.append(prior_item)
            for row in prior_rows:
                row["source_schema"] = row.get("source_schema") or (
                    "legacy" if row.get("INSTRUMENT") else "new" if row.get("FinInstrmTp") else "unknown"
                )
                row["source_url"] = row.get("source_url") or prior_item.get("source_url", "")
                key = tuple(row.get(field, "") for field in ("trade_date", "expiry", "strike", "option_type"))
                if key not in row_keys:
                    normalized_rows.append(row)
                    row_keys.add(key)
                    all_headers.extend(field for field in row if field not in all_headers)
            logger.info("Reusing existing download for %s (%d normalized rows)", day_text, len(prior_rows))
            continue
        item, headers, source_rows = download_one(day, session, user_agent)
        manifest.append(item)
        if item["status"] != "downloaded":
            logger.error("No file downloaded for requested date %s", day.isoformat())
            continue
        if headers != all_headers:
            all_headers = list(dict.fromkeys(all_headers + headers))
        current_resolved = resolve_columns(headers)
        instrument_column = current_resolved["instrument"]
        symbol_column = current_resolved["symbol"]
        option_type_column = current_resolved["option_type"]
        if not instrument_column or not symbol_column or not option_type_column:
            item["status"] = "schema_error"
            item["schema_error"] = (
                "Required identity columns INSTRUMENT, SYMBOL, or OPTION_TYP are missing"
            )
            logger.error("%s: %s", day.isoformat(), item["schema_error"])
            continue
        for field, column in current_resolved.items():
            resolved[field] = resolved[field] or column
        item["normalized_source_columns"] = current_resolved
        filtered = [
            row for row in source_rows
            if row.get(instrument_column, "").strip().upper() in {"OPTIDX", "IDO"}
            and row.get(symbol_column, "").strip().upper() == "NIFTY"
            and row.get(option_type_column, "").strip().upper() in {"CE", "PE"}
        ]
        for row in filtered:
            normalized = dict(row)
            normalized.update(normalize_row(row, current_resolved, day))
            instrument = get_value(row, instrument_column).upper()
            normalized["source_schema"] = schema_name(instrument)
            normalized["source_url"] = item["source_url"]
            key = tuple(normalized.get(field, "") for field in ("trade_date", "expiry", "strike", "option_type"))
            if key not in row_keys:
                normalized_rows.append(normalized)
                row_keys.add(key)
                all_headers.extend(field for field in normalized if field not in all_headers)
        item["filtered_nifty_option_rows"] = len(filtered)
        normalized_dates = [
            normalize_date_value(normalize_row(row, current_resolved, day)["trade_date"])
            for row in filtered
        ]
        item["filtered_trade_date_min"] = min(normalized_dates, default=None)
        item["filtered_trade_date_max"] = max(normalized_dates, default=None)

    write_normalized(NORMALIZED_PATH, all_headers, normalized_rows)
    MANIFEST_PATH.write_text(
        json.dumps(
            {
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "requested_dates": [day.isoformat() for day in days],
                "filter": {
                    "instrument": ["OPTIDX", "IDO"],
                    "symbol": "NIFTY",
                    "option_type": ["CE", "PE"],
                    "note": "IDO is the newer NSE index-options instrument code.",
                },
                "fields": NORMALIZED_FIELDS,
                "bid_ask_manufactured": False,
                "iv_manufactured": False,
                "timestamps_manufactured": False,
                "downloads": manifest,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    QUALITY_PATH.write_text(
        quality_report(manifest, all_headers, normalized_rows, resolved),
        encoding="utf-8",
    )
    failed = sum(item["status"] != "downloaded" for item in manifest)
    logger.info("Wrote %s, %s, and %s", NORMALIZED_PATH, MANIFEST_PATH, QUALITY_PATH)
    return 1 if failed else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download official NSE daily NIFTY option bhavcopy files."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dates", nargs="+", type=parse_iso_date,
                       help="Explicit dates (default: 2024-07-01 2024-07-10)")
    group.add_argument("--start-date", type=parse_iso_date)
    parser.add_argument("--end-date", type=parse_iso_date,
                        help="Inclusive end date used with --start-date")
    return parser


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = build_parser()
    args = parser.parse_args()
    try:
        days = requested_dates(args)
    except ValueError as exc:
        parser.error(str(exc))
    return run(days)


if __name__ == "__main__":
    sys.exit(main())
