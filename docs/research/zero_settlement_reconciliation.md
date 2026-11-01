# Zero-Settlement Reconciliation

| Population | Records |
|---|---:|
| Expanded validation positive-volume settlement-zero records | 348 |
| After contracts > 0, positive close, valid dates/strike, DTE 7-60 | 164 |
| Excluded from valuation audit by eligibility filters | 184 |

## Exclusion diagnostics

- `dte_outside_7_60`: 184
- `non_positive_close`: 0
- `invalid_strike`: 0
- `missing_date`: 0

Predicates can overlap. The original source rows remain in the options dataset; the eligible audit is a separate table.
