# HMM Diagnostic Report

- Features: annualized 20-observation rolling standard deviation of daily log returns.
- Each fit uses only a trailing 120 observations strictly before the assignment date; the current feature is appended only for endpoint probability inference.
- Gaussian emissions, diagonal covariance, 500 iterations, tolerance `1e-4`, random seed 42.
- State labels are assigned by fitted feature means; state IDs are not treated as economically meaningful.
- Endpoint `predict_proba` is used; because it is the final point in the supplied sequence, no later observation is available for smoothing.
- Transition matrices are reordered by volatility-ranked state before averaging in the corrected summary.

Walk-forward assignments: 468; fit failures: 0. Changing transition matrices and state counts are reported; no regime-improvement claim is made.
