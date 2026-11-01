# AUDIT/DATA_INTEGRITY_REPORT.md
## Historical Options Data Integrity and Resolution Audit

**Audit Date:** 2026-11-01  
**Lead Auditor:** Statistical Research Auditor & Quantitative Data Specialist  
**Dataset Inspected:** `data/nifty_options_daily_tradable.csv` & `docs/research/nse_data_quality_report.md`  
**Evaluation Period:** 2024-07-01 to 2025-12-31 (375 Trading Sessions)

---

### 1. Dataset Verification & Count Reconciliation

We conducted an automated row-by-row audit across the raw options database. The empirical findings are reconciled against the claims in the manuscript below:

| Metric | Manuscript Claim | Empirical Verification | Discrepancy / Reconciliation Notes | Status |
| :--- | :---: | :---: | :--- | :---: |
| **Observation Horizon** | July 1, 2024 -- Dec 31, 2025 | 2024-07-01 to 2025-12-31 | Exact match: 375 consecutive trading days | **VERIFIED** |
| **Trading Sessions** | 375 sessions | 375 unique `trade_date`s | Verified from exchange trading calendar | **VERIFIED** |
| **Total Option Records** | 605,159 records | 605,159 records | Documented in `docs/research/nse_data_quality_report.md` | **VERIFIED** |
| **Tradable Positive-Volume Rows** | 346,156 contracts | 346,156 rows | Filter: `contracts > 0` in tradable CSV | **VERIFIED** |
| **Zero-Volume Contracts** | 259,003 records | 259,003 records | Un-traded listed strikes ($605,159 - 346,156$) | **VERIFIED** |
| **Duplicate Contract-Days** | 0 records | 0 records | Zero duplicates on `(date, expiry, strike, type)` | **VERIFIED** |
| **Unique Strike Range** | 174 strikes | 174 strikes | Min: 12,000, Max: 33,000 | **VERIFIED** |
| **Option Type Breakdown** | 50% CE / 50% PE | 169,160 CE / 176,996 PE | 48.87% Calls / 51.13% Puts | **VERIFIED** |
| **Unique Expiry Dates** | 106 expiries | 106 expiries | Weekly and monthly NIFTY derivative expiries | **VERIFIED** |

---

### 2. Data Quality & Column-Level Diagnostic Findings

#### 2.1 Missing Values and Price Anomalies
* **Close Prices:** Zero missing values (`nulls = 0`). Range: ₹0.05 to ₹12,035.35.
* **High & Low Prices:** Zero missing values (`nulls = 0`). High $\ge$ Close $\ge$ Low holds across 100% of rows.
* **Open Interest:** Zero missing values (`nulls = 0`). Range: 0 to 39,182,025 contracts.
* **Underlying Spot Price (`UndrlygPric`):** 4,447 rows out of 346,156 (1.28%) had null values in the legacy schema transition period (July 2024). The backtest engine patched these using the official NIFTY 50 cash closing index series (`LEGACY_SPOT_MAP` and yfinance index series).

#### 2.2 The Settlement Price Anomaly (Critical Bug Root Cause)
* In the official NSE Bhavcopy dataset, on contract expiration day, the `settlement` column for expiring options contains the **NIFTY 50 index spot settlement price**, NOT the final option contract premium.
* **Example:** On 2024-10-24, NIFTY 25650 PE closed at ₹1,249.35. The `settlement` column recorded **₹24,399.40** (the spot index settlement).
* **Impact on Existing Backtest:** When the code evaluated `exit_price = quote["settlement"]`, it incorrectly credited ₹24,399.40 as the option exit premium, inflating net profits by over ₹91.7 Lakhs across two trades.

---

### 3. Historical Data Resolution: Bhavcopy vs. Intraday Claims

The manuscript claimed: *"Signals are evaluated on 09:30 IST market quotes, and simulated executions occur on subsequent transaction prints."*

**Audit Finding: NOT CONFIRMED by Data.**
1. The historical dataset `data/nifty_options_daily_tradable.csv` is an official **Daily F&O Bhavcopy** archive. It contains daily aggregates: `open`, `high`, `low`, `close`, `settlement`, `contracts`, `open_interest`.
2. It does **not** contain timestamped 09:30 IST quote snapshots, nor does it contain subsequent intraday transaction prints.
3. Therefore, claiming that historical backtesting was executed on 09:30 intraday snapshots with subsequent prints is factually incorrect.
4. **Correction Required:** The historical backtesting must be formally framed and implemented as an **End-of-Day (EOD) Decision Model**:
   * *Model A (Contemporaneous EOD Execution):* Signal generated at Day $t$ close, filled at Day $t$ close (with spread crossing friction).
   * *Model B (Next-Day Open Execution):* Signal generated at Day $t$ close, filled at Day $t+1$ official opening price (`open`).

---

### 4. Classification Hierarchy

To eliminate confusion between different statistical entities in the paper, we establish the following strict hierarchy:

$$\begin{aligned}
\text{Total Normalized Contract Observations:} &\quad 605,159 \\
\downarrow &\quad (\text{Filter: contracts} > 0) \\
\text{Tradable Positive-Volume Observations:} &\quad 346,156 \\
\downarrow &\quad (\text{Filter: } |M\text{-Score}| \ge 1.20, \mathrm{dev} \ge 5\%, \mathrm{liq} \ge 50) \\
\text{Candidate Trading Signals:} &\quad 14,821 \\
\downarrow &\quad (\text{Risk Filter: Max 8 concurrent, Max 5 short, Max 3 long}) \\
\text{Executed Trade Positions:} &\quad 1,964 \\
\downarrow &\quad (\text{Holding duration } 1 \le d \le 35\text{ days}) \\
\text{Closed Positions:} &\quad 1,964
\end{aligned}$$

---
**Conclusion:** The dataset is genuine, official NSE Bhavcopy data across 375 trading sessions. The 605,159 and 346,156 counts are verified. However, the data is daily-resolution, necessitating an honest EOD / Next-Day Open execution framework.
