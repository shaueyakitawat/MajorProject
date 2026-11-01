# Empirical Experiment Methodology

## Scope
All experiments use the validated NIFTY 50 index and NSE NIFTY option datasets. Evaluation is chronological and walk-forward; no random split is used.

## Volatility
Log return is `ln(C_t/C_(t-1))`. The target is the next-day absolute log return multiplied by `sqrt(252)`. Forecasts are annualized volatility. Baselines are 20-observation rolling standard deviation and EWMA with lambda 0.94. GARCH(1,1) and asymmetric EGARCH(1,1) (`p=1,o=1,q=1`) use the `arch` package, normal innovations, constant mean, returns multiplied by 100 for fitting, `rescale=False`, and one-step forecasts. Minimum training history is 60 returns. Variance is converted to decimal daily volatility by dividing its square root by 100, then annualized by `sqrt(252)`.

## HMM
Two-state and three-state diagonal-covariance Gaussian HMMs use the annualized 20-day rolling volatility feature, a trailing window of 120 observations, `n_iter=500`, tolerance `1e-4`, and `random_state=42`. The current observation is appended only for inference; the final posterior is based on observations through that date. States are ranked by fitted volatility-feature means and have no intrinsic labels.

## Option valuation
Options are filtered to positive contracts, positive CLOSE, valid strike/expiry, and DTE 7--60 days. Daily CLOSE is treated only as an observed last-traded reference. BSM uses EGARCH volatility, continuous dividend yield 0.0125, and risk-free sensitivity rates (0.06, 0.07); no historical rate series was available. Settlement-zero records are retained in a separate audit table and not silently removed from the source data.

## Reproducibility
Random seed: 42 for HMM. Outputs include package versions, failure records, exact counts, and generated figures. The pipeline is separate from the live application.
