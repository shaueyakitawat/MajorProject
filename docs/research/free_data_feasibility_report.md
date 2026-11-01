# Free Historical NIFTY Derivatives Data Feasibility Report

**Date:** 2026-10-31  
**Objective:** identify the fastest no-cost route for a reproducible daily NIFTY option analysis before submission.  
**Scope:** official NSE archives and free underlying/VIX sources only. No data was downloaded into the repository.

## Executive conclusion

The fastest credible free route is the official NSE daily F&O bhavcopy archive, filtered to `INSTRUMENT=OPTIDX` and `SYMBOL=NIFTY`, combined with daily NIFTY spot and India VIX series. Representative official URLs were directly reachable and returned ZIP files containing CSV files:

* [NSE archive example: 1 July 2024](https://archives.nseindia.com/content/historical/DERIVATIVES/2024/JUL/fo01JUL2024bhav.csv.zip)
* [NSE archive example: 10 July 2024](https://archives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_20240710_F_0000.csv.zip)

This route can support a **daily end-of-day contract panel** with NIFTY CE/PE contract identity, expiry, strike, daily OHLC/close, settlement price, traded contracts/turnover, and open interest. It does **not** establish bid/ask quotes, quote timestamps, intraday observations, or executable transaction prices. OHLC and settlement must not be described as bid/ask.

The exact earliest and latest date available through the public archive, complete field definitions for every historical format, and rights to redistribute raw NSE files are **UNVERIFIED** from the sources reachable in this audit. The report therefore recommends a one-day pilot on a small date range, with checksums and a data manifest, before reporting any empirical result.

## 1. Official NSE historical derivatives files

### 1.1 Download formats and URL patterns

The official NSE archive exposes compressed ZIP downloads containing CSV files. This was verified by fetching both representative URLs above; the responses had `application/zip` content and contained filenames:

* `fo01JUL2024bhav.csv`
* `BhavCopy_NSE_FO_0_0_0_20240710_F_0000.csv`

The two naming patterns indicate a format transition:

```text
Older-style example:
https://archives.nseindia.com/content/historical/DERIVATIVES/YYYY/MON/foDDMONYYYYbhav.csv.zip

Newer-style example:
https://archives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_YYYYMMDD_F_0000.csv.zip
```

The patterns are verified for the cited 2024 examples, not for every date. A missing file, holiday, format change, or archive migration must not be treated as missing market data without checking the NSE reports page.

The official NSE historical-data framework is described by [Historical Data Dissemination of Future and Options Segment](https://nsearchives.nseindia.com/content/press/Data_Details_F_n_O.pdf). The PDF was discoverable as an official NSE archive document, but it was not reliably retrievable during this run; detailed claims below are consequently limited to directly verified archive behavior and clearly marked documentation/search evidence.

The official navigation page is [NSE derivatives reports](https://www.nseindia.com/all-reports-derivatives). It timed out during retrieval, so its current filters, authentication requirements, and retention policy are **UNVERIFIED**.

### 1.2 Historical coverage

**Verified:** the public archive contains at least the cited 2024 daily files.

**Not verified:** the complete earliest date, latest date, continuity by trading day, and whether every historical format remains downloadable through the same URL pattern. Search results commonly report public F&O archive coverage beginning around 2003, but that start-date claim was not established from a successfully retrieved official file index and must remain **UNVERIFIED**.

The relevant distinction is:

* A historical file for a trading date contains contracts observed/traded on that date.
* A NIFTY option whose expiry later occurred is represented in earlier daily files while it was active and traded.
* The file should not be assumed to contain observations after expiry, a complete contract history independent of trading activity, or a quote record for an illiquid contract with no trade.

Thus, “expired contracts included” is **PARTIALLY CONFIRMED**: historical files can preserve observations of contracts that subsequently expired, but a separate post-expiry archive or guaranteed complete expired-contract panel is **UNVERIFIED**.

## 2. Expected fields and research meaning

The standard F&O bhavcopy layout is widely documented as containing fields equivalent to:

| Field | Use in daily NIFTY option analysis | Status |
|---|---|---|
| `INSTRUMENT` | Select `OPTIDX` for index options | Expected; verify exact spelling in each downloaded file |
| `SYMBOL` | Select `NIFTY` | Expected; verify exact spelling |
| `EXPIRY_DT` | Contract expiry | Expected |
| `STRIKE_PR` | Option strike | Expected |
| `OPTION_TYP` | `CE` or `PE` | Expected |
| `OPEN`, `HIGH`, `LOW`, `CLOSE` | Daily traded-price summary | Expected |
| `SETTLE_PR` | Daily settlement price | Expected in traditional layout; verify in each file |
| `CONTRACTS` | Number of contracts traded | Expected |
| `VAL_INLAKH` | Traded value/turnover measure | Expected in traditional layout; verify units |
| `OPEN_INT` | End-of-day open interest | Expected |
| `CHG_IN_OI` | Change in open interest | Expected in traditional layout; verify |
| `TIMESTAMP` | File/observation trading date in newer layouts | Expected in some layouts; verify |

The exact current schema must be read from the downloaded CSV header, not copied blindly from a third-party description. The official NSE search result references a format-readme workbook at [new bhavcopy format readme](https://nsearchives.nseindia.com/content/new_bhavcopy_format_readme.xlsx), but the workbook was not retrieved and inspected in this run.

### 2.1 Required contract observations

For rows satisfying:

```text
INSTRUMENT == "OPTIDX"
SYMBOL == "NIFTY"
OPTION_TYP in {"CE", "PE"}
```

the archive is suitable for obtaining:

* NIFTY CE/PE identity;
* expiry date;
* strike;
* daily open, high, low, and close;
* settlement price, if present in that file version;
* traded contract count/volume;
* open interest and usually change in open interest.

This is sufficient for a transparent daily cross-sectional pricing or liquidity-screening experiment, provided the manuscript calls the price a daily close or settlement price rather than a quote midpoint.

### 2.2 Bid/ask

**No bid/ask field was verified in the official bhavcopy archive responses or documented standard field list.** The archive is a daily trade/settlement summary, not a top-of-book quote feed. `OPEN`, `HIGH`, `LOW`, `CLOSE`, and `SETTLE_PR` are not bid or ask values.

Therefore:

* bid/ask availability: **NOT CONFIRMED / treat as unavailable**;
* executable spread analysis: **not feasible** from bhavcopy alone;
* transaction-cost analysis: requires an explicit external assumption or additional quote data;
* replacing missing bid/ask with close, settlement, or synthetic ± spread is not acceptable as observed quote data.

## 3. Free NIFTY spot and India VIX sources

### 3.1 Yahoo Finance / yfinance

The repository already uses yfinance for `^NSEI` and `^INDIAVIX` in [`data_service.py`](../../backend/services/data_service.py):14-76 and the validator described in [`critical_findings_verification.md`](./critical_findings_verification.md):2.2.

The [official yfinance documentation](https://ranaroussi.github.io/yfinance/) documents historical price access through `Ticker.history` and `download`. The Yahoo historical pages are reachable for:

* [NIFTY 50 `^NSEI` history](https://finance.yahoo.com/quote/%5ENSEI/history/)
* [India VIX `^INDIAVIX` history](https://finance.yahoo.com/quote/%5EINDIAVIX/history/)

These pages expose daily OHLC-style historical tables. The India VIX page displayed no meaningful volume values in the retrieved table; only the VIX index level is needed here.

Use of Yahoo data remains subject to [Yahoo terms](https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html). The yfinance documentation explicitly states that yfinance is not affiliated with Yahoo and that the Yahoo API is intended for personal use. Academic publication and redistribution rights for downloaded Yahoo data are **UNVERIFIED** and must not be assumed.

### 3.2 Official NSE index history

The official historical index-data page is [NSE historical index data](https://www.nseindia.com/products/content/equities/indices/historical_index_data.htm), and the official India VIX page is [NSE India VIX](https://www.nseindia.com/market-data/india-vix). Both official pages timed out during this audit. Their current downloadable range, format, access controls, and licensing terms are therefore **UNVERIFIED**.

For a one-day reproducible pilot, use Yahoo only if the resulting license and citation position is acceptable; otherwise use the NSE index download after manually confirming the current terms.

## 4. Feasibility for the submission deadline

### 4.1 What can be done in one day

The smallest defensible experiment is:

1. Select one contiguous period for which official daily ZIP files can be verified, preferably 2024-01-01 through 2024-12-31 or a smaller 3–6 month pilot.
2. Download only trading-date ZIPs from the official NSE archive.
3. Extract each CSV without changing raw values.
4. Filter `OPTIDX/NIFTY/CE/PE`.
5. Normalize field names and dates into one Parquet or CSV file.
6. Join daily `^NSEI` close and `^INDIAVIX` close by trading date.
7. Save URLs, retrieval timestamps, SHA-256 checksums, headers, row counts, and rejected-file logs.
8. Run a small descriptive analysis: contract counts, expiry/strike coverage, close/settlement distributions, volume/OI missingness, and calendar coverage.

Do not claim intraday mispricing, bid/ask execution, or option P&L from this dataset.

### 4.2 Minimal normalized schema

```text
trade_date
symbol
instrument
expiry_date
strike
option_type
open
high
low
close
settle_price
contracts
turnover_value
open_interest
change_in_open_interest
underlying_spot_close
india_vix_close
source_url
source_file
source_sha256
```

Retain all original columns in a raw table. The normalized table should add `price_kind` metadata indicating `CLOSE` or `SETTLE_PR`; it must not create `bid` or `ask` columns populated with proxy values.

### 4.3 Minimal ingestion logic

No ingestion script is created by this task. The required implementation is small enough to write and validate within one day:

```python
for trading_day in verified_trading_days:
    url = official_nse_url(trading_day)
    payload = download(url)
    save_raw_zip(payload, sha256(payload))
    csv = extract_single_csv(payload)
    frame = read_csv(csv)
    frame = normalize_columns(frame)
    frame = frame[
        (frame["INSTRUMENT"] == "OPTIDX")
        & (frame["SYMBOL"] == "NIFTY")
        & (frame["OPTION_TYP"].isin(["CE", "PE"]))
    ]
    append(frame, source_url=url, source_sha256=sha256(payload))
```

The loader must stop and log a schema mismatch rather than silently accepting a format change. It must also record holidays, HTTP failures, duplicate contract keys, invalid expiry dates, and files whose header lacks settlement, volume, or OI.

## 5. Reproducibility and validation checklist

Before calculating any metric:

* verify ZIP and CSV checksums;
* store the exact URL and raw filename;
* record the CSV header for every format version;
* parse dates explicitly and preserve the original date;
* check one row per `(trade_date, expiry_date, strike, option_type)` unless the file documents another key;
* quantify missingness for close, settlement, contracts, and OI;
* confirm `CE` and `PE` counts separately;
* verify that NIFTY rows include multiple expiries and strikes;
* compare `CLOSE` and `SETTLE_PR` rather than conflating them;
* join spot and VIX only on the documented trading date;
* report that the panel is daily and end-of-day;
* exclude or label zero-volume contracts rather than treating them as executable quotes.

The existing application’s synthetic validator and underlying-direction backtest must not be relabeled as results from this dataset. A new dataset would support a separate daily experiment, not silently change the existing pipeline.

## 6. Licensing and publication terms

**Status: UNVERIFIED.**

Public accessibility of an NSE ZIP URL does not establish a right to redistribute the raw CSV/ZIP or to include the raw data in supplementary material. The official [NSE historical-data dissemination document](https://nsearchives.nseindia.com/content/press/Data_Details_F_n_O.pdf), [NSE reports page](https://www.nseindia.com/all-reports-derivatives), and current NSE website terms must be reviewed directly. If the terms are ambiguous, request written permission from NSE/NSE Data & Analytics before publication.

The safe publication posture is:

* cite NSE as the source;
* publish the exact acquisition code, URL template, schema, checksums, and date manifest;
* do not commit raw NSE files to this repository unless redistribution permission is confirmed;
* publish derived aggregates and results rather than raw contract data;
* retain the downloaded raw files privately for audit, subject to the applicable terms;
* record the license decision in the experiment metadata.

Yahoo/yfinance rights are likewise **UNVERIFIED** for academic redistribution; cite the source and review Yahoo terms before distributing downloaded spot/VIX files.

## 7. Final recommendation

For tomorrow’s deadline, use the official NSE daily bhavcopy route only for a clearly labeled **daily end-of-day NIFTY option dataset**. Pair it with daily `^NSEI` and `^INDIAVIX` histories, retain raw files and checksums outside the repository if licensing is unclear, and report:

> “The experiment uses daily NSE F&O bhavcopy contract summaries. Prices are daily traded close/settlement values; bid/ask quotes and intraday timestamps are unavailable.”

Do not claim:

* timestamp-aligned quote-level observations;
* bid/ask execution;
* historical option-chain snapshots at arbitrary intraday times;
* complete expired-contract history beyond the daily files’ active/traded records;
* transaction-cost-adjusted option profitability;
* unrestricted data redistribution rights.

This is the fastest free route that can produce genuine contract-level observations without fabricating quotes, but it supports a narrower daily descriptive/pricing study than the original intraday mispricing objective.
