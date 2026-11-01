# Diagnostic Findings

1. **EGARCH — corrected.** The original call omitted `o=1`, did not record convergence status, and allowed explosive forecasts into valuation. The corrected run uses asymmetric EGARCH(1,1), explicit percentage conversion, convergence checks, and failure records without clipping.
2. **BSM units — consistent.** Spot, strike, and option CLOSE are index-price units; DTE is divided by 365.25 once; volatility is an annualized decimal; rates and dividend yield are annual decimals. The large errors are empirical pricing errors against daily CLOSE, not proof of mispricing. MAPE is dominated by small observed prices.
3. **HMM — no look-ahead identified.** Training windows precede assignment dates, endpoint probabilities use observations through the current date, and ranked-state transition matrices are used for summary averaging. Stability remains limited because each walk-forward fit has a changing transition matrix.
4. **Zero settlement — reconciled.** Expanded validation reports 348 positive-volume zero-settlement records; 164 meet the experiment's DTE/price/date eligibility, leaving 184 outside the audit.
5. **Remaining limitations.** Rates are sensitivity assumptions, option CLOSE is not bid/ask, and the index source is third-party Yahoo Finance. No profitability or executable-arbitrage conclusion is supported.
