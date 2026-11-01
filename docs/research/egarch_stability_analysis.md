# EGARCH Stability Analysis

- Corrected forecast rows: 312
- Fit/forecast failures: 4
- One-step volatility below 1%: 2
- Below 5%: 3
- Below 10%: 74
- Maximum one-step volatility: 1.1011388496880947

Alternative minimum-history runs use 60, 90, and 120 observations. They are diagnostic sensitivity runs, not selected to improve results. No forecast is clipped or floored.

## Extreme forecasts

| trade_date   |   minimum_history |   volatility |   convergence_flag | failure   |
|:-------------|------------------:|-------------:|-------------------:|:----------|
| 2025-03-06   |                90 |     1.10114  |                  0 |           |
| 2025-03-06   |                60 |     1.10114  |                  0 |           |
| 2025-03-06   |               120 |     1.10114  |                  0 |           |
| 2025-02-17   |               120 |     0.686254 |                  0 |           |
| 2025-02-17   |                60 |     0.686254 |                  0 |           |
| 2025-02-17   |                90 |     0.686254 |                  0 |           |
| 2025-02-14   |               120 |     0.632074 |                  0 |           |
| 2025-02-14   |                90 |     0.632074 |                  0 |           |
| 2025-02-14   |                60 |     0.632074 |                  0 |           |
| 2025-02-03   |                90 |     0.544503 |                  0 |           |
| 2025-02-03   |                60 |     0.544503 |                  0 |           |
| 2025-02-03   |               120 |     0.544503 |                  0 |           |
| 2025-02-12   |               120 |     0.543498 |                  0 |           |
| 2025-02-12   |                60 |     0.543498 |                  0 |           |
| 2025-02-12   |                90 |     0.543498 |                  0 |           |
| 2025-02-10   |                60 |     0.48061  |                  0 |           |
| 2025-02-10   |                90 |     0.48061  |                  0 |           |
| 2025-02-10   |               120 |     0.48061  |                  0 |           |
| 2025-02-07   |                60 |     0.460468 |                  0 |           |
| 2025-02-07   |                90 |     0.460468 |                  0 |           |

## Failures

```json
[
  {
    "trade_date": "2024-10-09",
    "model": "egarch_one_step",
    "reason": "optimizer convergence_flag=4",
    "history": 69,
    "parameters": {
      "mu": -0.02433402397203513,
      "omega": -0.6099510769498836,
      "alpha[1]": -2.4762772078627897,
      "gamma[1]": -1.1740370119922268,
      "beta[1]": 0.3450368810404574
    }
  },
  {
    "trade_date": "2024-10-09",
    "model": "egarch_horizon",
    "reason": "optimizer convergence_flag=4",
    "history": 69,
    "parameters": {
      "mu": -0.02433402397203513,
      "omega": -0.6099510769498836,
      "alpha[1]": -2.4762772078627897,
      "gamma[1]": -1.1740370119922268,
      "beta[1]": 0.3450368810404574
    }
  },
  {
    "trade_date": "2025-03-20",
    "model": "egarch_one_step",
    "reason": "optimizer convergence_flag=9",
    "history": 181,
    "parameters": {
      "mu": -0.03622608947324158,
      "omega": -0.02945386558157665,
      "alpha[1]": -0.20297775932316173,
      "gamma[1]": -0.09939573291825257,
      "beta[1]": 0.9764143397070061
    }
  },
  {
    "trade_date": "2025-03-20",
    "model": "egarch_horizon",
    "reason": "optimizer convergence_flag=9",
    "history": 181,
    "parameters": {
      "mu": -0.03622608947324158,
      "omega": -0.02945386558157665,
      "alpha[1]": -0.20297775932316173,
      "gamma[1]": -0.09939573291825257,
      "beta[1]": 0.9764143397070061
    }
  }
]
```
