# Option Pricing Diagnostic Report

## Input trace

- Spot: Yahoo Finance NIFTY 50 close, in index points, joined by `trade_date`.
- Strike and observed CLOSE: NSE bhavcopy values, in index-option price points.
- DTE: calendar-day difference `expiry - trade_date`; year fraction is `DTE / 365.25`, applied once.
- Volatility: EGARCH one-step forecast, annualized decimal after percentage-return variance conversion.
- Rates: 6% and 7% annual sensitivity assumptions; dividend yield: 1.25% annual continuous yield.
- The BSM implementation uses continuous dividend yield and standard call/put formulas; observed CLOSE is a last-traded reference, not a quote or executable price.

## Distributions (6% sensitivity)

```json
{
  "spot": {
    "n": 189084,
    "missing": 0,
    "min": 22082.650390625,
    "median": 24680.900390625,
    "max": 26216.05078125
  },
  "strike": {
    "n": 189084,
    "missing": 0,
    "min": 13000.0,
    "median": 24600.0,
    "max": 31000.0
  },
  "observed_close": {
    "n": 189084,
    "missing": 0,
    "min": 0.1,
    "median": 170.75,
    "max": 10200.0
  },
  "model_price": {
    "n": 189084,
    "missing": 0,
    "min": 0.0,
    "median": 176.74294287737848,
    "max": 10287.87581440106
  },
  "dte": {
    "n": 189084,
    "missing": 0,
    "min": 7.0,
    "median": 20.0,
    "max": 60.0
  },
  "moneyness": {
    "n": 189084,
    "missing": 0,
    "min": 0.4960828386790185,
    "median": 1.000773861936668,
    "max": 1.4038169989396194
  },
  "egarch_volatility": {
    "n": 189084,
    "missing": 0,
    "min": 2.0001682970036944e-11,
    "median": 0.11807641794120477,
    "max": 1.1011388496880947
  },
  "absolute_error": {
    "n": 189084,
    "missing": 0,
    "min": 0.0006446413747429602,
    "median": 29.274184902649903,
    "max": 3237.224423475982
  },
  "ape": {
    "n": 189084,
    "missing": 0,
    "min": 1.074317500165994e-06,
    "median": 0.2629484829829004,
    "max": 944.3216883817398
  }
}
```

## Grouped pricing errors (6% sensitivity)

| Group | N | MAE | RMSE | MAPE % | Median absolute error | Median absolute percentage error % |
|---|---:|---:|---:|---:|---:|---:|
| CE_ATM_31-60 | 14577 | 115.7328 | 264.1233 | 32.9034 | 72.0802 | 15.1431 |
| CE_ATM_7-30 | 41493 | 64.6362 | 161.6980 | 66.5788 | 34.2467 | 16.5663 |
| CE_ITM_31-60 | 6644 | 76.9884 | 278.9109 | 292.0359 | 15.3045 | 67.6019 |
| CE_ITM_7-30 | 19088 | 27.5319 | 138.7307 | 635.9261 | 3.2931 | 94.6280 |
| CE_OTM_31-60 | 3412 | 103.8856 | 235.7100 | 4.9060 | 76.9491 | 3.2773 |
| CE_OTM_7-30 | 8847 | 58.5116 | 125.0153 | 3.1640 | 40.0347 | 1.9704 |
| PE_ATM_31-60 | 15420 | 114.9373 | 270.8553 | 42.5358 | 63.3903 | 21.1343 |
| PE_ATM_7-30 | 41423 | 66.2558 | 159.8788 | 56.3622 | 35.6327 | 22.6774 |
| PE_ITM_31-60 | 7021 | 50.1697 | 166.3957 | 130.4088 | 23.3084 | 92.1544 |
| PE_ITM_7-30 | 19067 | 22.3530 | 102.3856 | 256.8205 | 6.7500 | 99.8058 |
| PE_OTM_31-60 | 3466 | 156.7173 | 359.1007 | 9.7786 | 93.1960 | 5.2255 |
| PE_OTM_7-30 | 8626 | 74.1139 | 168.2902 | 4.4067 | 42.5625 | 2.3920 |

MAPE and percentage errors become unstable when observed daily CLOSE is zero or near zero; these observations are retained, and median percentage error is reported alongside absolute metrics.
