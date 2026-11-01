# EGARCH Multi-step Implementation Audit

## Package behavior

The installed `arch` package's `EGARCH._check_forecasting_method` (`.venv/Lib/site-packages/arch/univariate/volatility.py:2755`) raises `ValueError('Analytic forecasts not available for horizon > 1')`. Its public forecast API supports `analytic`, `simulation`, and `bootstrap` (`.venv/Lib/site-packages/arch/univariate/base.py:1027`); the package documentation states that EGARCH does not support analytic forecasts beyond one step. The package simulation path uses a caller-supplied RNG and a configurable simulation count.

## Experiment behavior

`fit_egarch_forecast` (line 42) requests the package analytic one-step forecast, converts percentage-scale variance by dividing by 10,000, and then constructs longer horizons itself. For steps after the first it applies `exp(omega + beta * log(previous_variance))`. This is a deterministic expected-log-variance recursion under the normal-innovation mean terms, not `arch` simulation and not the exact expected future variance of the asymmetric EGARCH process. No simulation count or random seed is used.

The resulting vectors are horizon-specific and are not repeated copies: the audit found 311 of 312 rows where the stored `horizon_volatility_60` differs from the one-step volatility. For each option, `load_eligible_options` counts observed index dates strictly after trade date through expiry and slices the stored daily variance vector to that count (`load_eligible_options`, line 164). No future return is used in fitting.

## Methodological conclusion

The Phase 2 arrays are reproducible under the current deterministic recursion, but the multi-step method must be labeled an expected-log-variance approximation. A publication-grade multi-step EGARCH forecast should use `arch` simulation with a documented simulation count, RNG, and repeated-run stability analysis, or explicitly justify this approximation. Existing forecast values were not changed in this audit.
