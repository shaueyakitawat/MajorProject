# Diebold-Mariano Test Validation

The Phase 2 implementation constructs losses as squared forecast errors in `main` (line 383), subtracts them observation by observation in `dm_test` (line 265), and estimates a Newey-West variance using the resulting loss-difference series. The two input arrays are aligned through the common date frame before loss construction (line 365).

## Reproduced comparison

```json
{
  "n": 312,
  "loss": "squared error of next-day annualized absolute-return volatility target",
  "newey_west_lag": 5,
  "null": "equal expected forecast loss",
  "mean_loss_difference_a_minus_b": 0.0,
  "statistic": 0.0,
  "p_value": 1.0,
  "identical_loss_series": true
}
```

The compared one-step EGARCH arrays differ only at roundoff level. Before correction, this produced a tiny nonzero loss difference and an unstable near-zero standard error, yielding a spurious statistic of approximately 3.0. The corrected implementation treats an all-close-zero loss difference as identical.

## Identical-array unit case

```json
{
  "n": 312,
  "loss": "squared error of next-day annualized absolute-return volatility target",
  "newey_west_lag": 5,
  "null": "equal expected forecast loss",
  "mean_loss_difference_a_minus_b": 0.0,
  "statistic": 0.0,
  "p_value": 1.0,
  "identical_loss_series": true
}
```

For identical loss arrays the corrected result is statistic 0 and p-value 1, so it cannot claim a significant difference. This is a numerical guard, not a change to the loss definition or forecast values.
