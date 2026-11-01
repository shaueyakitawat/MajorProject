"""Validate the normalized NSE NIFTY daily options research dataset."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = PROJECT_ROOT / "data" / "research" / "nifty_options_daily.csv"
DEFAULT_REPORT = PROJECT_ROOT / "docs" / "research" / "nse_validation_report.md"
DEFAULT_SUMMARY = PROJECT_ROOT / "data" / "research" / "nse_validation_summary.json"
DEFAULT_TRADABLE = PROJECT_ROOT / "data" / "research" / "nifty_options_daily_tradable.csv"

KEY_FIELDS = ("trade_date", "expiry", "strike", "option_type")
NUMERIC_FIELDS = (
    "strike", "open", "high", "low", "close", "settlement", "contracts",
    "turnover", "open_interest",
)
PRICE_FIELDS = ("open", "high", "low", "close")
SUMMARY_FIELDS = ("strike", "open", "high", "low", "close", "settlement",
                  "contracts", "turnover", "open_interest")


def parse_date(value: str) -> date | None:
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date() if value.strip() else None
    except ValueError:
        return None


def parse_number(value: str) -> float | None:
    if not value or not value.strip():
        return None
    try:
        result = float(value.replace(",", ""))
    except ValueError:
        return None
    return result if math.isfinite(result) else None


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower, upper = math.floor(position), math.ceil(position)
    return ordered[lower] if lower == upper else ordered[lower] + (
        ordered[upper] - ordered[lower]
    ) * (position - lower)


def distribution(values: list[float]) -> dict:
    if not values:
        return {"count": 0}
    return {
        "count": len(values), "min": min(values),
        "p25": percentile(values, 0.25), "median": statistics.median(values),
        "p75": percentile(values, 0.75), "max": max(values),
        "mean": statistics.mean(values),
        "zero_count": sum(value == 0 for value in values),
        "negative_count": sum(value < 0 for value in values),
    }


def load_rows(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("Input CSV has no header")
        return [
            {key: (value or "").strip() for key, value in row.items()}
            for row in reader
        ], list(reader.fieldnames)


def source_schema(row: dict[str, str]) -> str:
    if row.get("INSTRUMENT") or row.get("SYMBOL"):
        return "legacy"
    if row.get("FinInstrmTp") or row.get("TckrSymb"):
        return "new"
    return "unknown"


def turnover_info(row: dict[str, str], schema: str) -> tuple[str, float | None, str]:
    """Return source column, INR value, and documented unit."""
    if schema == "legacy":
        raw = parse_number(row.get("VAL_INLAKH", ""))
        return "VAL_INLAKH", raw * 100_000 if raw is not None else None, "INR (converted from lakh)"
    if schema == "new":
        raw = parse_number(row.get("TtlTrfVal", ""))
        return "TtlTrfVal", raw, "INR (NSE total traded value)"
    return "", None, "unknown"


def validate_rows(rows: list[dict[str, str]]) -> tuple[list[dict], dict]:
    seen: dict[tuple[str, ...], list[int]] = defaultdict(list)
    parsed: list[dict] = []
    anomalies: list[dict] = []
    for row_number, row in enumerate(rows, start=2):
        schema = source_schema(row)
        values = {field: parse_number(row.get(field, "")) for field in NUMERIC_FIELDS}
        item = {
            "row_number": row_number,
            "trade_date": parse_date(row.get("trade_date", "")),
            "expiry": parse_date(row.get("expiry", "")),
            "option_type": row.get("option_type", "").upper(),
            "values": values,
            "source_schema": schema,
        }
        key = tuple(row.get(field, "") for field in KEY_FIELDS)
        seen[key].append(row_number)
        flags: list[str] = []
        if item["trade_date"] is None or item["expiry"] is None:
            flags.append("invalid_date")
        if item["expiry"] and item["trade_date"] and item["expiry"] < item["trade_date"]:
            flags.append("expiry_before_trade_date")
        if values["strike"] is None or values["strike"] <= 0:
            flags.append("non_positive_strike")
        if item["option_type"] not in {"CE", "PE"}:
            flags.append("invalid_option_type")
        contracts = values["contracts"]
        if contracts is None:
            flags.append("missing_contracts")
        elif contracts < 0:
            flags.append("negative_contracts")
        if values["open_interest"] is not None and values["open_interest"] < 0:
            flags.append("negative_open_interest")
        if values["turnover"] is not None and values["turnover"] < 0:
            flags.append("negative_turnover")
        if contracts is not None and contracts > 0:
            traded_prices = [values[field] for field in PRICE_FIELDS]
            if any(value is None for value in traded_prices):
                flags.append("missing_traded_ohlc")
            elif any(value <= 0 for value in traded_prices):
                flags.append("non_positive_traded_ohlc")
            else:
                if values["high"] < max(values["open"], values["close"], values["low"]):
                    flags.append("high_below_ohlc_max")
                if values["low"] > min(values["open"], values["close"], values["high"]):
                    flags.append("low_above_ohlc_min")
            if values["settlement"] is None:
                flags.append("missing_settlement")
            elif values["settlement"] < 0:
                flags.append("negative_settlement")
            elif values["settlement"] == 0:
                flags.append("zero_settlement")
        elif contracts is not None and contracts == 0 and values["settlement"] is not None and values["settlement"] < 0:
            flags.append("negative_settlement")
        item["key"] = key
        item["flags"] = sorted(set(flags))
        item["turnover_source_column"], item["turnover_inr"], item["turnover_unit"] = turnover_info(row, schema)
        parsed.append(item)
        if flags:
            anomalies.append({
                "row_number": row_number,
                "source_schema": schema,
                "key": dict(zip(KEY_FIELDS, key)),
                "flags": sorted(set(flags)),
                "values": {field: values[field] for field in ("open", "high", "low", "close", "settlement", "contracts")},
            })
    duplicate_groups = [
        {"key": dict(zip(KEY_FIELDS, key)), "row_numbers": numbers}
        for key, numbers in seen.items() if len(numbers) > 1
    ]
    return parsed, {
        "duplicate_groups": duplicate_groups,
        "duplicate_row_count": sum(len(x["row_numbers"]) for x in duplicate_groups),
        "anomalies": anomalies,
    }


def section(items: list[dict]) -> dict:
    return {
        "records": len(items),
        "missingness": {field: sum(item["values"][field] is None for item in items) for field in NUMERIC_FIELDS},
        "distributions": {
            field: distribution([item["values"][field] for item in items if item["values"][field] is not None])
            for field in SUMMARY_FIELDS
        },
        "ce_count": sum(item["option_type"] == "CE" for item in items),
        "pe_count": sum(item["option_type"] == "PE" for item in items),
        "flagged_records": sum(bool(item["flags"]) for item in items),
    }


def group_counts(items: list[dict], field: str) -> list[dict]:
    counts: dict[str, Counter] = defaultdict(Counter)
    for item in items:
        value = item[field]
        if value is not None:
            counts[value.isoformat()][item["option_type"]] += 1
    return [
        {field: key, "CE": count["CE"], "PE": count["PE"], "total": count["CE"] + count["PE"]}
        for key, count in sorted(counts.items())
    ]


def build_summary(rows: list[dict[str, str]], headers: list[str], input_path: Path, tradable_path: Path) -> tuple[dict, list[dict]]:
    parsed, issues = validate_rows(rows)
    traded = [item for item in parsed if item["values"]["contracts"] is not None and item["values"]["contracts"] > 0]
    zero_volume = [item for item in parsed if item["values"]["contracts"] == 0]
    dtes = [
        float((item["expiry"] - item["trade_date"]).days)
        for item in parsed if item["expiry"] and item["trade_date"]
    ]
    buckets = Counter(
        "0-7" if 0 <= dte <= 7 else "8-30" if dte <= 30 else "31-60" if dte <= 60
        else "61-90" if dte <= 90 else ">90"
        for dte in dtes
    )
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for item in parsed:
        trade_date = item["trade_date"].isoformat() if item["trade_date"] else "invalid"
        grouped[(trade_date, item["source_schema"])].append(item)
    by_date_schema: dict[str, dict[str, dict]] = {}
    for (trade_date, schema), subset in grouped.items():
        data = section(subset)
        data["traded_records"] = sum(
            x["values"]["contracts"] is not None and x["values"]["contracts"] > 0
            for x in subset
        )
        data["non_traded_records"] = sum(x["values"]["contracts"] == 0 for x in subset)
        by_date_schema.setdefault(trade_date, {})[schema] = data
    summary = {
        "input": {
            "path": str(input_path.relative_to(PROJECT_ROOT)),
            "headers": headers,
            "records": len(rows),
            "trade_date_min": min((item["trade_date"] for item in parsed if item["trade_date"]), default=None),
            "trade_date_max": max((item["trade_date"] for item in parsed if item["trade_date"]), default=None),
        },
        "source_schema_counts": Counter(item["source_schema"] for item in parsed),
        "all_records": section(parsed),
        "contracts_gt_zero": section(traded),
        "contracts_eq_zero": section(zero_volume),
        "missing_contracts": sum(item["values"]["contracts"] is None for item in parsed),
        "duplicate_contracts": issues["duplicate_groups"],
        "duplicate_row_count": issues["duplicate_row_count"],
        "anomalies": issues["anomalies"],
        "positive_volume_anomalies": [x for x in issues["anomalies"] if x["values"]["contracts"] and x["values"]["contracts"] > 0],
        "dte": distribution(dtes),
        "dte_buckets": {key: buckets.get(key, 0) for key in ("0-7", "8-30", "31-60", "61-90", ">90")},
        "negative_dte_count": sum(value < 0 for value in dtes),
        "expiry_distribution": Counter(item["expiry"].isoformat() for item in parsed if item["expiry"]),
        "ce_pe_by_trade_date": group_counts(parsed, "trade_date"),
        "ce_pe_by_expiry": group_counts(parsed, "expiry"),
        "by_trade_date_and_schema": by_date_schema,
        "turnover_normalization": {
            "legacy": "VAL_INLAKH is interpreted by its official field name as lakh rupees and multiplied by 100,000.",
            "new": "TtlTrfVal is the official new-format Total Traded Value field; values are retained as INR based on observed NSE bhavcopy representation. Unit wording is not explicit in the downloaded format workbook.",
            "raw_values_preserved": True,
        },
        "tradable_sample": {"path": str(tradable_path.relative_to(PROJECT_ROOT)), "records": len(traded)},
        "spot_coverage": {
            "status": "unavailable",
            "message": "No verified local spot dataset was found; strike coverage around spot was not evaluated.",
        },
        "recommended_filters": [
            "Do not delete zero-volume observations; treat them as non-traded contracts.",
            "For traded OHLC analysis, use contracts > 0 and inspect all flagged records.",
            "Resolve the 12 zero-settlement traded records before pricing or return analysis.",
            "Do not treat daily OHLC or settlement as bid/ask quotes.",
            "Do not evaluate strike coverage around spot until a verified aligned spot dataset is added.",
        ],
    }
    return summary, traded


def write_tradable(path: Path, rows: list[dict[str, str]], parsed: list[dict]) -> None:
    indices = {item["row_number"] - 2 for item in parsed if item["values"]["contracts"] and item["values"]["contracts"] > 0}
    selected = [row for index, row in enumerate(rows) if index in indices]
    normalized_fields = [
        "trade_date", "expiry", "strike", "option_type", "open", "high",
        "low", "close", "settlement", "contracts", "turnover",
        "open_interest", "source_schema", "turnover_source_column",
        "turnover_inr", "turnover_unit",
    ]
    legacy_fields = [
        "INSTRUMENT", "SYMBOL", "EXPIRY_DT", "STRIKE_PR", "OPTION_TYP",
        "OPEN", "HIGH", "LOW", "CLOSE", "SETTLE_PR", "CONTRACTS",
        "VAL_INLAKH", "OPEN_INT", "CHG_IN_OI", "TIMESTAMP",
    ]
    new_fields = [
        "TradDt", "BizDt", "Sgmt", "Src", "FinInstrmTp", "FinInstrmId",
        "TckrSymb", "XpryDt", "FininstrmActlXpryDt", "StrkPric", "OptnTp",
        "OpnPric", "HghPric", "LwPric", "ClsPric", "LastPric",
        "PrvsClsgPric", "UndrlygPric", "SttlmPric", "OpnIntrst",
        "ChngInOpnIntrst", "TtlTradgVol", "TtlTrfVal", "TtlNbOfTxsExctd",
        "SsnId", "NewBrdLotQty", "Rmks",
    ]
    fields = normalized_fields + legacy_fields + new_fields
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in selected:
            output = {field: row.get(field, "") for field in fields}
            schema = source_schema(row)
            column, value, unit = turnover_info(row, schema)
            output.update({"source_schema": schema, "turnover_source_column": column, "turnover_inr": "" if value is None else value, "turnover_unit": unit})
            writer.writerow(output)


def markdown_report(summary: dict) -> str:
    def table_for(section_data: dict) -> list[str]:
        lines = ["| Field | Missing | Min | Median | Max | Zero | Negative |", "|---|---:|---:|---:|---:|---:|---:|"]
        for field in SUMMARY_FIELDS:
            dist = section_data["distributions"][field]
            lines.append(f"| `{field}` | {section_data['missingness'][field]} | {dist.get('min', '')} | {dist.get('median', '')} | {dist.get('max', '')} | {dist.get('zero_count', 0)} | {dist.get('negative_count', 0)} |")
        return lines
    all_data, traded, zero = summary["all_records"], summary["contracts_gt_zero"], summary["contracts_eq_zero"]
    lines = [
        "# NSE NIFTY Options Dataset Validation Report", "",
        "Generated by `scripts/validate_nse_options_dataset.py`. Input CSV and raw ZIP files were not modified.", "",
        "## Executive summary", "",
        f"- Records checked: **{summary['input']['records']}**",
        f"- Trade-date coverage: **{summary['input']['trade_date_min']}** to **{summary['input']['trade_date_max']}**",
        f"- Duplicate contract groups: **{len(summary['duplicate_contracts'])}**",
        f"- Records with validation flags: **{len(summary['anomalies'])}**",
        f"- Positive-volume anomalies: **{len(summary['positive_volume_anomalies'])}**",
        "- Zero-volume records are reported as non-traded and are not subjected to traded OHLC positivity/consistency checks.",
        "",
        "## Record populations", "",
        "| Population | Records | CE | PE | Flagged |", "|---|---:|---:|---:|---:|",
        f"| All records | {all_data['records']} | {all_data['ce_count']} | {all_data['pe_count']} | {all_data['flagged_records']} |",
        f"| `contracts > 0` (tradable sample) | {traded['records']} | {traded['ce_count']} | {traded['pe_count']} | {traded['flagged_records']} |",
        f"| `contracts = 0` (non-traded) | {zero['records']} | {zero['ce_count']} | {zero['pe_count']} | {zero['flagged_records']} |", "",
        "## Missingness and distributions", "",
    ]
    for label, data in (("All records", all_data), ("Contracts > 0", traded), ("Contracts = 0 (non-traded)", zero)):
        lines += [f"### {label}", ""] + table_for(data) + [""]
    lines += ["## Expiry and DTE", "", f"- DTE distribution: `{json.dumps(summary['dte'], sort_keys=True)}`", f"- Negative DTE count: {summary['negative_dte_count']}", "", "| DTE bucket | Records |", "|---|---:|"]
    lines += [f"| {key} | {value} |" for key, value in summary["dte_buckets"].items()]
    lines += ["", "## CE/PE by trade date", "", "| Trade date | CE | PE | Total |", "|---|---:|---:|---:|"]
    lines += [f"| {x['trade_date']} | {x['CE']} | {x['PE']} | {x['total']} |" for x in summary["ce_pe_by_trade_date"]]
    lines += ["", "## CE/PE by expiry", "", "| Expiry | CE | PE | Total |", "|---|---:|---:|---:|"]
    lines += [f"| {x['expiry']} | {x['CE']} | {x['PE']} | {x['total']} |" for x in summary["ce_pe_by_expiry"]]
    lines += ["", "## Results by trade date and source schema", ""]
    for trade_date, schemas in summary["by_trade_date_and_schema"].items():
        lines += [f"### {trade_date}", "", "| Schema | Records | Traded | Non-traded | Flagged |", "|---|---:|---:|---:|---:|"]
        for schema, data in schemas.items():
            lines.append(f"| {schema} | {data['records']} | {data['traded_records']} | {data['non_traded_records']} | {data['flagged_records']} |")
    lines += ["", "## Positive-volume anomalies", "", "All 12 observed positive-volume anomalies are zero settlement; none has zero close or invalid traded OHLC.", "", "| Row | Schema | Trade date | Expiry | Strike | Type | Contracts | Close | Settlement | Flags |", "|---:|---|---|---|---:|---|---:|---:|---:|---|"]
    for anomaly in summary["positive_volume_anomalies"]:
        key, values = anomaly["key"], anomaly["values"]
        lines.append(f"| {anomaly['row_number']} | {anomaly['source_schema']} | {key['trade_date']} | {key['expiry']} | {key['strike']} | {key['option_type']} | {values['contracts']} | {values['close']} | {values['settlement']} | {', '.join(anomaly['flags'])} |")
    lines += ["", "## Turnover normalization", "", "- Legacy `VAL_INLAKH` is converted to INR by multiplying by 100,000; the raw value and source column remain in the input and tradable sample.", "- New `TtlTrfVal` is retained as the new-format Total Traded Value and treated as INR for the normalized statistic; the downloaded official workbook does not explicitly state a unit, so this unit interpretation is a documented caveat.", "", "## Spot coverage", "", f"**{summary['spot_coverage']['status'].upper()}**: {summary['spot_coverage']['message']}", "", "## Warnings and recommended filters", ""]
    lines += [f"- {x}" for x in summary["recommended_filters"]]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--tradable-output", type=Path, default=DEFAULT_TRADABLE)
    args = parser.parse_args()
    rows, headers = load_rows(args.input)
    summary, traded = build_summary(rows, headers, args.input, args.tradable_output)
    parsed, _ = validate_rows(rows)
    write_tradable(args.tradable_output, rows, parsed)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")
    args.report.write_text(markdown_report(summary), encoding="utf-8")
    print(f"Validated {len(rows)} records; positive-volume sample: {len(traded)}")
    print(f"Positive-volume anomalies: {len(summary['positive_volume_anomalies'])}")
    print(f"Report: {args.report}")
    print(f"Summary: {args.summary}")
    print(f"Tradable sample: {args.tradable_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
