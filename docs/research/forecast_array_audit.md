# Forecast Array Audit

Comparison rows: **312**, joined one-to-one on `trade_date`.

## Array summaries

|               |   non_null |   unique |     minimum |   median |   maximum |
|:--------------|-----------:|---------:|------------:|---------:|----------:|
| rolling       |        312 |      312 | 0.0647731   | 0.107742 |  0.218157 |
| garch         |        312 |      312 | 0.083333    | 0.125323 |  0.319212 |
| egarch_phase1 |        312 |      312 | 2.00017e-11 | 0.117875 |  1.10114  |
| egarch_phase2 |        312 |      312 | 2.00017e-11 | 0.117875 |  1.10114  |

## Pairwise comparisons

|                                |   maximum_absolute_difference |   correlation |   exactly_identical |   rows |
|:-------------------------------|------------------------------:|--------------:|--------------------:|-------:|
| garch_vs_rolling               |                   0.130374    |     0.656548  |                   0 |    312 |
| egarch_phase1_vs_rolling       |                   0.993736    |     0.0867119 |                   0 |    312 |
| egarch_phase1_vs_garch         |                   0.974283    |     0.149282  |                   0 |    312 |
| egarch_phase1_vs_egarch_phase2 |                   1.11022e-16 |     1         |                 286 |    312 |
| egarch_phase2_vs_rolling       |                   0.993736    |     0.0867119 |                   0 |    312 |
| egarch_phase2_vs_garch         |                   0.974283    |     0.149282  |                   0 |    312 |

## First 20 aligned rows

| trade_date          |   target_vol |   rolling20_volatility |   garch11_vol |   egarch11_vol |
|:--------------------|-------------:|-----------------------:|--------------:|---------------:|
| 2024-09-25 00:00:00 |   0.128833   |               0.101607 |     0.0928715 |     0.0937913  |
| 2024-09-26 00:00:00 |   0.0224819  |               0.103789 |     0.109925  |     0.00992672 |
| 2024-09-27 00:00:00 |   0.224794   |               0.104391 |     0.100364  |     0.0506846  |
| 2024-09-30 00:00:00 |   0.00858154 |               0.118843 |     0.121271  |     0.219612   |
| 2024-10-01 00:00:00 |   0.340099   |               0.118927 |     0.119973  |     0.156099   |
| 2024-10-03 00:00:00 |   0.148751   |               0.1427   |     0.13535   |     0.252179   |
| 2024-10-04 00:00:00 |   0.139495   |               0.146467 |     0.137526  |     0.20164    |
| 2024-10-07 00:00:00 |   0.138575   |               0.14377  |     0.138399  |     0.188335   |
| 2024-10-08 00:00:00 |   0.0198141  |               0.146717 |     0.138224  |     0.100111   |
| 2024-10-10 00:00:00 |   0.021732   |               0.144911 |     0.130281  |     0.132756   |
| 2024-10-11 00:00:00 |   0.103755   |               0.127288 |     0.128126  |     0.138549   |
| 2024-10-14 00:00:00 |   0.0446639  |               0.129929 |     0.12735   |     0.0872489  |
| 2024-10-15 00:00:00 |   0.0546081  |               0.130056 |     0.125974  |     0.126125   |
| 2024-10-16 00:00:00 |   0.141407   |               0.130187 |     0.124855  |     0.141312   |
| 2024-10-17 00:00:00 |   0.0666941  |               0.133265 |     0.125347  |     0.168618   |
| 2024-10-18 00:00:00 |   0.0466631  |               0.134344 |     0.124344  |     0.115874   |
| 2024-10-21 00:00:00 |   0.199187   |               0.120783 |     0.123311  |     0.135232   |
| 2024-10-22 00:00:00 |   0.0237591  |               0.122688 |     0.125299  |     0.17718    |
| 2024-10-23 00:00:00 |   0.0234694  |               0.122315 |     0.124088  |     0.154228   |
| 2024-10-24 00:00:00 |   0.142864   |               0.120781 |     0.122985  |     0.145373   |

## Producer trace

- Phase 1 writes `egarch11_vol` in `scripts/run_empirical_research.py:fit_volatility` (line 68).
- Phase 2 recomputes `one_step_volatility` in `scripts/run_phase2_horizon_validation.py:fit_egarch_forecast` (line 42) and `calculate_forecasts` (line 97).
- Phase 2 imports Phase 1 `egarch11_vol` only for the common-sample comparison in `main` (line 365); it does not generate an independent EGARCH specification.

The Phase 1 and Phase 2 one-step EGARCH series are therefore recomputations of the same EGARCH(1,1,1), normal, percentage-scaled fit. They are not independent forecasts. The maximum difference is 1.1102230246251565e-16, consistent with floating-point serialization/recomputation.
