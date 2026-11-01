# Common-Sample Model Comparison

Target: next-day absolute log return multiplied by `sqrt(252)`; variance QLIKE uses the squared target and forecast variance. Models are evaluated on identical non-missing dates.

```json
{
  "rolling20_volatility": {
    "n": 312,
    "mae": 0.06834745046368344,
    "rmse": 0.08701577668506887,
    "variance_qlike": 1.5078798380736493
  },
  "one_step_volatility": {
    "n": 312,
    "mae": 0.08291542264044843,
    "rmse": 0.128155262937141,
    "variance_qlike": 185402337.86206266
  },
  "garch11_vol": {
    "n": 312,
    "mae": 0.06965295060737581,
    "rmse": 0.08620243502159677,
    "variance_qlike": 1.5138709517451825
  },
  "egarch11_vol": {
    "n": 312,
    "mae": 0.08291542264044842,
    "rmse": 0.128155262937141,
    "variance_qlike": 185402337.86206266
  }
}
```

Diebold-Mariano comparisons use squared-error loss differences with a Newey-West lag of 5. They are reported only as diagnostics; the short sample and overlapping volatility construction limit inference.

```json
{
  "one_step_volatility_vs_rolling20_volatility": {
    "n": 312,
    "loss": "squared error of next-day annualized absolute-return volatility target",
    "newey_west_lag": 5,
    "null": "equal expected forecast loss",
    "mean_loss_difference_a_minus_b": 0.008852026026381967,
    "statistic": 1.7130958098836373,
    "p_value": 0.08669491477610466
  },
  "one_step_volatility_vs_garch11_vol": {
    "n": 312,
    "loss": "squared error of next-day annualized absolute-return volatility target",
    "newey_west_lag": 5,
    "null": "equal expected forecast loss",
    "mean_loss_difference_a_minus_b": 0.008992911614835128,
    "statistic": 1.7642910367596147,
    "p_value": 0.07768299226337448
  },
  "one_step_volatility_vs_egarch11_vol": {
    "n": 312,
    "loss": "squared error of next-day annualized absolute-return volatility target",
    "newey_west_lag": 5,
    "null": "equal expected forecast loss",
    "mean_loss_difference_a_minus_b": 0.0,
    "statistic": 0.0,
    "p_value": 1.0,
    "identical_loss_series": true
  }
}
```
