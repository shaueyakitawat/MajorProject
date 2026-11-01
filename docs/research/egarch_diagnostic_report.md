# EGARCH Diagnostic Report

## Confirmed implementation issue

The original experiment passed `vol='EGARCH', p=1, q=1` without `o=1`. In `arch`, this specifies a symmetric EGARCH(1,1) with no asymmetry term, not the intended asymmetric EGARCH(1,1). The original script also suppressed warnings and did not record `convergence_flag` or fitted parameters.

## Corrected specification

- Returns are decimal log returns `ln(C_t/C_(t-1))`.
- The fitting series is returns multiplied by 100 (percentage points), with `rescale=False`.
- Corrected model: `arch_model(..., mean='Constant', vol='EGARCH', p=1, o=1, q=1, dist='normal', rescale=False)`.
- Forecast variance is converted to decimal daily volatility by `sqrt(variance) / 100`, then annualized by `sqrt(252)`.
- Nonzero optimizer convergence flags and non-finite forecasts are recorded as failures; no clipping is applied.

## Corrected run

- Forecast rows: 314
- EGARCH failures: 2
- EGARCH metric rows: 312

The original explosive values were caused primarily by the missing asymmetry order and unchecked optimizer/forecast diagnostics in the short expanding samples; the original outputs are preserved under `data/research/versions/2026-10-31_phase1_original/`.
