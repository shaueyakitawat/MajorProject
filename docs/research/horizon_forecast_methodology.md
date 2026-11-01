# Horizon Forecast Methodology

Daily returns are decimal log returns. The corrected asymmetric EGARCH specification is `arch_model(returns*100, mean='Constant', vol='EGARCH', p=1, o=1, q=1, dist='normal', rescale=False)`.

For each valuation date, the forecast horizon is the number of actual NIFTY 50 trading observations strictly after the valuation date and no later than the option expiry date. Calendar DTE remains the source eligibility measure; option valuation uses the trading-day count. The expiration date is included only when it is an observed trading date. Non-trading days therefore contribute no conditional variance. Daily percentage-scale conditional variances are divided by 10,000, summed, and converted to equivalent annualized volatility as `sqrt(sum(v_daily) * 252 / N_trading_days)`. No volatility floor or clipping is applied.

The one-step approach uses the first daily conditional variance annualized. The horizon approach uses the full forecast vector through the maximum 60 observed trading days and the option-specific count within that vector. The rolling benchmark uses the trailing 20 daily returns annualized by `sqrt(252)`. All fits use only returns available through the valuation date.

Risk-free rate is a sensitivity assumption of 6.00%; continuous dividend yield is 1.25%. Option CLOSE is a daily last-traded reference, not bid/ask or executable price. Package versions are recorded in `data/research/phase2/phase2_metrics.json`.
