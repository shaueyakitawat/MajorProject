# Empirical Experiment Results

## Counts
- Index observations: 375
- Volatility forecast rows: 314
- HMM rows: 468
- Option valuation rows: 378168
- Volatility failures: 2
- HMM failures: 0

## Volatility forecast metrics
```json
{
  "rolling20": {
    "n": 314,
    "mae": 0.06838720673072184,
    "rmse": 0.08707812976627399,
    "qlike": null,
    "variance_qlike": 1.5119666176973934
  },
  "ewma": {
    "n": 314,
    "mae": 0.06722890136103545,
    "rmse": 0.08518721023148448,
    "qlike": null,
    "variance_qlike": 1.4742180880286124
  },
  "garch11": {
    "n": 314,
    "mae": 0.06965533782392692,
    "rmse": 0.0862127463022265,
    "qlike": null,
    "variance_qlike": 1.5173920781292236
  },
  "egarch11": {
    "n": 312,
    "mae": 0.08291542264044842,
    "rmse": 0.12815526293714097,
    "qlike": null,
    "variance_qlike": 1.9139311771860135
  }
}
```

## Option valuation metrics
```json
{
  "r=0.06_CE": {
    "n": 94061,
    "mae": 66.74537779906456,
    "rmse": 187.69876167606236,
    "mape": 184.62232548704569
  },
  "r=0.06_CE_moneyness_lt_0.95": {
    "n": 12259,
    "mae": 71.14037907742375,
    "rmse": 163.53132180861618,
    "mape": 3.6488708492528423
  },
  "r=0.06_CE_moneyness_0.95_1.05": {
    "n": 56070,
    "mae": 77.92022922950237,
    "rmse": 193.61087797855123,
    "mape": 57.82389863796509
  },
  "r=0.06_CE_moneyness_gt_1.05": {
    "n": 25732,
    "mae": 40.301563079025186,
    "rmse": 185.37135086498006,
    "mape": 547.1336488910816
  },
  "r=0.06_CE_dte_7_30": {
    "n": 69428,
    "mae": 53.654593710356984,
    "rmse": 151.3571685898129,
    "mape": 215.0299968013379
  },
  "r=0.06_CE_dte_31_60": {
    "n": 24633,
    "mae": 103.64169402976279,
    "rmse": 264.49925366287744,
    "mape": 98.918440292036
  },
  "r=0.06_PE": {
    "n": 95023,
    "mae": 68.17067643613788,
    "rmse": 185.66539435463218,
    "mape": 93.39735953221246
  },
  "r=0.06_PE_moneyness_lt_0.95": {
    "n": 26088,
    "mae": 29.839199065531847,
    "rmse": 122.93525675827,
    "mape": 222.79961350850047
  },
  "r=0.06_PE_moneyness_0.95_1.05": {
    "n": 56843,
    "mae": 79.46182918724114,
    "rmse": 196.28671645271993,
    "mape": 52.611508812958505
  },
  "r=0.06_PE_moneyness_gt_1.05": {
    "n": 12092,
    "mae": 97.79096967244352,
    "rmse": 239.0946734859,
    "mape": 5.946492074484426
  },
  "r=0.06_PE_dte_7_30": {
    "n": 69116,
    "mae": 55.125091590928974,
    "rmse": 147.46544177404695,
    "mape": 105.17827376862388
  },
  "r=0.06_PE_dte_31_60": {
    "n": 25907,
    "mae": 102.97434502615057,
    "rmse": 261.57520509082156,
    "mape": 61.967642916478894
  },
  "r=0.07_CE": {
    "n": 94061,
    "mae": 63.67961364521989,
    "rmse": 187.23169764031493,
    "mape": 185.34537613393647
  },
  "r=0.07_CE_moneyness_lt_0.95": {
    "n": 12259,
    "mae": 62.370391013026826,
    "rmse": 160.46623609751956,
    "mape": 3.2250583319345516
  },
  "r=0.07_CE_moneyness_0.95_1.05": {
    "n": 56070,
    "mae": 74.49637983463909,
    "rmse": 192.92704839320368,
    "mape": 57.77666804708686
  },
  "r=0.07_CE_moneyness_gt_1.05": {
    "n": 25732,
    "mae": 40.73361955254618,
    "rmse": 186.47116492972015,
    "mape": 550.0815193938619
  },
  "r=0.07_CE_dte_7_30": {
    "n": 69428,
    "mae": 51.6128545490947,
    "rmse": 151.01260126499085,
    "mape": 215.79597699545147
  },
  "r=0.07_CE_dte_31_60": {
    "n": 24633,
    "mae": 97.68972002794953,
    "rmse": 263.78935414024266,
    "mape": 99.52049420265486
  },
  "r=0.07_PE": {
    "n": 95023,
    "mae": 65.53977941482789,
    "rmse": 183.2273900908227,
    "mape": 92.92192604122664
  },
  "r=0.07_PE_moneyness_lt_0.95": {
    "n": 26088,
    "mae": 29.845373829157133,
    "rmse": 122.26126685832016,
    "mape": 222.3402001398044
  },
  "r=0.07_PE_moneyness_0.95_1.05": {
    "n": 56843,
    "mae": 77.48458571576418,
    "rmse": 194.1784234664516,
    "mape": 52.170498671028845
  },
  "r=0.07_PE_moneyness_gt_1.05": {
    "n": 12092,
    "mae": 86.39795245112109,
    "rmse": 233.07755374064638,
    "mape": 5.274675902329602
  },
  "r=0.07_PE_dte_7_30": {
    "n": 69116,
    "mae": 53.3928823628208,
    "rmse": 146.01900299892918,
    "mape": 104.71136442427745
  },
  "r=0.07_PE_dte_31_60": {
    "n": 25907,
    "mae": 97.94588342712271,
    "rmse": 257.40121193632666,
    "mape": 61.46946827757439
  }
}
```

## HMM state summaries
```json
{
  "2": {
    "rows": 234,
    "state_rank_counts": {
      "0": 174,
      "1": 60
    },
    "state_rank_mean_feature": {
      "0": 0.0908726368749864,
      "1": 0.1712424269467342
    },
    "mean_filtered_confidence": 0.9797829633843149,
    "unique_transition_matrices": 234,
    "mean_transition_matrix_rank_aligned": [
      [
        0.9774968952763667,
        0.0225031047236331
      ],
      [
        0.05650650915470778,
        0.9434934908452925
      ]
    ],
    "stability_note": "Walk-forward fits are compared through changing state counts, ranks, and transition matrices; no persistence claim is made from a single fit."
  },
  "3": {
    "rows": 234,
    "state_rank_counts": {
      "0": 155,
      "1": 37,
      "2": 42
    },
    "state_rank_mean_feature": {
      "0": 0.08862229229465207,
      "1": 0.14696664546334082,
      "2": 0.16457531536278575
    },
    "mean_filtered_confidence": 0.913285402067732,
    "unique_transition_matrices": 234,
    "mean_transition_matrix_rank_aligned": [
      [
        0.8028759076503983,
        0.18299550436775672,
        0.01412858798184515
      ],
      [
        0.2511114358708193,
        0.043104556011738834,
        0.705784008117442
      ],
      [
        0.01587202418376613,
        0.7429018416835155,
        0.2412261341327179
      ]
    ],
    "stability_note": "Walk-forward fits are compared through changing state counts, ranks, and transition matrices; no persistence claim is made from a single fit."
  }
}
```

These are historical pricing errors relative to daily option CLOSE values. They do not establish mispricing, arbitrage, executable prices, profitability, or EGARCH superiority.
