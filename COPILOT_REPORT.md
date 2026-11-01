# Reproducibility Run Report

## Scope and evidence policy

This run used the preserved repository artifacts under `data/research/` and
recorded all command output under `.copilot_run/`. No datasets were changed.
The three primary research scripts were attempted from the current Windows
environment. They could not start because the environment lacks `matplotlib`
and `arch`; no dependencies were installed and no failed computation was
replaced with fabricated output.

## Task status

| Task | Status | Evidence or limitation |
|---|---|---|
| T01 Diebold--Mariano statistics | COMPLETED | Recomputed from the preserved 312-row forecast CSV with Newey--West lag 5. |
| T02 Floored mean QLIKE | COMPLETED WITH ARTIFACT DERIVATION | Computed from the preserved forecast CSV using the documented floor definition and the first 60 target-volatility observations as the available training sample. |
| T03 Median QLIKE | COMPLETED WITH ARTIFACT DERIVATION | Same calculation as T02; values are recorded below. |
| T04 HMM acceptance | COMPLETED | `hmm_diagnostics.csv` contains 13 signals, 9 converged cases, and 5 accepted cases. |
| T05 Figures | FAILED | `matplotlib` is unavailable; no PDF figures were generated. |
| T06 Monte-Carlo plug-in bias | FAILED | `arch` is unavailable; no bias estimate is reported. |
| T07 Citation keys | COMPLETED | All 11 citation keys used in `latexcode.tex` have matching bibliography entries. |
| T08 Rolling-volatility diagnostic | NOT RUN | No additional ACF/R-squared diagnostic was added; the existing claim is now limited to observed forecast metrics. |
| T09 HMM discussion decision | COMPLETED | HMM discussion retained but corrected to distinguish signal rejection from completed-trade overlap. |
| T10 Trade totals | COMPLETED | Totals were checked against unrounded `gross_pnl_points`; the manuscript now discloses rounding. |
| T11 Line numbers | DEFERRED | Journal requirement is not specified. |
| T12 ORCID metadata | DEFERRED | ORCID values are not available in repository evidence. |
| T13 Abstract and keywords | COMPLETED | Abstract contains 201 words; keywords are alphabetized. |
| T14 Spell check | NOT RUN | No approved spell-check executable is installed. |
| T15 Dataset checksums | COMPLETED | Actual SHA-256 values match `run_manifest.json`. |

## Recomputed diagnostics

The common forecast sample contains 312 rows. Using a variance floor of
`0.007009807437425868`, computed as the sample variance of the first 60
target-volatility observations, the mean and median QLIKE values are:

| Forecast | Mean QLIKE | Median QLIKE |
|---|---:|---:|
| Rolling 20-day | 0.4480911671 | 0.1368834890 |
| GARCH(1,1) | 0.4135527337 | 0.2305137187 |
| EGARCH(1,1,1) | 0.5191555618 | 0.1747693189 |

The associated Diebold--Mariano results use squared annualized-volatility
errors and Newey--West lag 5:

| Comparison | DM statistic | Two-sided normal p-value |
|---|---:|---:|
| Rolling vs GARCH | 0.2832880504 | 0.7769560367 |
| Rolling vs EGARCH | -1.7146193444 | 0.0864150397 |
| GARCH vs EGARCH | -1.7657797330 | 0.0774328095 |

These are short-sample diagnostics, not evidence of statistically significant
superiority.

## HMM and backtest verification

The preserved HMM diagnostics contain 13 EMA signals. Five were accepted,
four were rejected after convergence, and four lacked the required prior
feature history. Thus, acceptance was 5/13 overall and 5/9 among converged
cases, not 100%.

The trade ledger contains 13 strategy-level rows. The three completed
HMM-filtered EMA trades overlap completed EMA trades, while the filter did
reject other signals that did not generate completed positions. The four
strategy-level test trades therefore represent two distinct test events.
P&L remains gross option price-point P&L without verified costs, spreads,
slippage, or lot-size scaling.

## Dataset integrity

The actual checksums match the preserved manifest:

- `data/research/nifty50_index_daily.csv`: `d56103561b861ad580fb85ba5ae4cd8105ad422e93be5589a787f3d44c21b19f`
- `data/research/nifty_options_daily.csv`: `664908f7058b4b1696357a11c7dc232224cf631b8ec43867d45b797ad1f5ab3a`

## Execution failures

The following commands were attempted and failed before computation:

```text
python scripts/run_empirical_research.py
ModuleNotFoundError: No module named 'matplotlib'

python scripts/run_phase2_horizon_validation.py
ModuleNotFoundError: No module named 'arch'

python scripts/research_backtest/engine.py
ModuleNotFoundError: No module named 'matplotlib'
```

The failed commands and their stdout/stderr are preserved in
`.copilot_run/verification_stdout.txt`. The derived artifact-only diagnostics
are preserved in `.copilot_run/derived_metrics.json`.

## Manuscript changes

Only `latexcode.tex` and this report were added or modified by this workflow.
The manuscript now removes the processed TODO claims, reports the computed DM
and QLIKE diagnostics, corrects the HMM acceptance statement, discloses
rounded trade totals, and states explicitly that the maturity-aligned
EGARCH plug-in has no completed Monte-Carlo bias estimate in this environment.

`git diff --check` passes. A LaTeX compiler was not available, and the two
figure files referenced by the current manuscript remain absent because figure
generation failed. The current manuscript contains two figure environments;
no separate `fig_forecast_errors` environment was present to generate.

## Follow-up: Narrative Reconciliation

- Corrections applied:
  - Abstract forecast ranking changed from rolling-lowest RMSE/QLIKE to
    GARCH-lowest mean QLIKE/RMSE and rolling-lowest MAE/median QLIKE.
  - Abstract now reports that no Diebold--Mariano comparison rejects equal
    predictive accuracy at the 5% level.
  - Section V.A now distinguishes the metric leaders and states that the two
    benchmarks are statistically indistinguishable on this sample.
  - Section VI.A was renamed to “Rolling versus GARCH Benchmarks” and no
    longer describes rolling as uniquely difficult to beat.
  - Section VI.E now reports 5/13 accepted HMM signals, or 5/9 after
    excluding insufficient-history fits, while preserving the completed-trade
    overlap finding.
  - Section VII now separates forecast rankings from valuation rankings.
- Verified claims:
  - GARCH mean QLIKE: 0.4136; GARCH RMSE: 0.08620.
  - Rolling MAE: 0.06835; rolling median QLIKE: 0.1369.
  - Rolling remains lowest-error in every reported valuation MAE/RMSE group.
  - DM p-values are 0.7770, 0.0864, and 0.0774; none rejects at 5%.
- Figure status: generated `fig_vol_forecast.pdf` and `fig_val_errors.pdf`
  from preserved research outputs after installing matplotlib.
- pdflatex status: unavailable; `pdflatex` is not installed.

The pre-follow-up backup is
`.copilot_run/latexcode.before.tex` (the requested `/tmp/latexcode.before.tex`
path does not exist on this Windows workspace).

## Final Audit

- Compilation: NOT VERIFIED (tool unavailable). Neither `tectonic` nor
  `pdflatex` is installed. No submission PDF was produced.
- Numerical consistency: 0 conflicting rendered values found. Rounded and
  full-precision occurrences are consistent:
  - Rolling: MAE 0.068347/0.06835, RMSE 0.087016/0.08702, mean QLIKE
    0.4481, median QLIKE 0.1369.
  - GARCH: MAE 0.069653/0.06965, RMSE 0.086202/0.08620, mean QLIKE
    0.4136, median QLIKE 0.2305.
  - EGARCH: MAE 0.082915/0.08292, RMSE 0.128155/0.12816, mean QLIKE
    0.5192, median QLIKE 0.1748.
  - DM statistics/p-values: 0.2833/0.7770, -1.7146/0.0864, and
    -1.7658/0.0774.
  - HMM acceptance: 5/13 overall and 5/9 among converged fits.
  - Trade counts: EMA 5, RSI 0, volatility breakout 5, HMM-filtered EMA 3,
    totaling 13 strategy-level rows. Partition totals are 4/5/4.
  - Gross P&L across all 13 ledger rows is 437.5571428571 price points;
    manuscript partition totals are consistent with rounded table values.
- Claim verification: 1 issue found. A false superseded forecast statement
  remains inside a non-rendered `\iffalse` block at line 436, stating that
  rolling achieved the lowest RMSE. The rendered narrative correctly states
  that GARCH leads on RMSE. The valuation statements that rolling has the
  lowest error in every group are correctly scoped to valuation tables.
  HMM wording correctly reports 5/13 and 5/9 and refers to completed-trade
  overlap, not identical signal acceptance. No “100%”, “accepted every
  signal”, or “provides no information” claim remains.
- Reference verification: 0 orphan citations and 0 phantom citations.
  All 11 cited keys have matching `\bibitem` entries and plausible years.
  There are 13 defined but unused bibliography entries.
- LaTeX hygiene: PASS for static checks. The file has 124 dollar signs,
  balanced braces/parentheses/brackets, three matched `\iffalse...\fi`
  blocks, zero `% TODO` markers, and zero `% FAILED` markers. Figure files
  `fig_vol_forecast.pdf` (24,807 bytes) and `fig_val_errors.pdf` (14,449
  bytes) exist, but the requested compiled-PDF size check cannot be made.
- Recommendation: REVIEW MANUALLY. The rendered narrative and static syntax
  checks are consistent, but compilation was not verified and the stale
  false sentence in a non-rendered audit block should be removed before
  submission.

## Post-Audit Cleanup

- `\iffalse` block at line ~436: DELETED. The block was lines 435--437,
  contained only obsolete text, and referenced no figure.
- Compilation: STILL NOT INSTALLED. `tectonic` is unavailable; compilation
  was not attempted with another tool because the requested procedure stops
  when tectonic is missing.
- Remaining warnings: unavailable because no compilation log was produced.
- Final verdict: FIX FIRST. Install tectonic and compile before submission.
