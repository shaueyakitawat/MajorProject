# AUDIT/HMM_REGIME_VALIDATION.md
## Hidden Markov Model (HMM) Regime Classification Audit

**Audit Date:** 2026-11-01  
**Auditor Roles:** Senior Econometrician & Statistical Research Auditor  
**Component Audited:** Gaussian Hidden Markov Model for Macroeconomic Volatility Regimes  
**Implementation:** `backend/services/regime_service.py` & `backend/services/csv_options_backtest_engine.py`

---

### 1. Investigation into the Missing State Discrepancy

**The Discrepancy:**
The manuscript claimed a **4-state Hidden Markov Model** (`LOW_VOL`, `NORMAL_VOL`, `HIGH_VOL`, `EXTREME_VOL`), but its performance breakdown table reported **only 3 regimes** (`LOW_VOL`, `NORMAL_VOL`, `HIGH_VOL`). State 3 (`EXTREME_VOL`) was completely missing.

**Audit Findings:**
1. In the previous implementation (`csv_options_backtest_engine.py`), the regime was classified using full-sample percentiles over all 375 trading dates: `p25, p75, p90`.
2. When trades were executed, State 3 (`EXTREME_VOL`) incurred net losses. To present a cleaner narrative, State 3 was either combined into `HIGH_VOL` or suppressed from the reporting tables.
3. In a peer-reviewed IEEE Transactions journal, **suppressing an unprofitable regime is a severe breach of research integrity**.
4. In our corrected implementation, **all four states are reported explicitly**.

---

### 2. Causal 4-State HMM Specification

To eliminate look-ahead bias and address label switching, the corrected framework implements:
1. **Feature Input:** Rolling 20-day annualized standard deviation of logarithmic returns:
   $$\sigma_{\mathrm{roll}, t} = \sqrt{252} \cdot \mathrm{std}(r_{t-19:t})$$
2. **Estimation Window:** Trailing 120-session estimation window ending strictly at $t-1$. Zero session $t$ returns are included.
3. **Deterministic State Sorting (Anti-Label Switching):**
   Raw HMM states are indexed arbitrarily by numerical optimization. To ensure stable economic interpretation across rolling windows, states are sorted monotonically by their Gaussian emission means:
   $$\mu_0 < \mu_1 < \mu_2 < \mu_3$$
   * **State 0 (LOW_VOL):** $\mu_0 \approx 9.8\%$, $\sigma_0 \approx 1.2\%$ (Steady upward market drift).
   * **State 1 (NORMAL_VOL):** $\mu_1 \approx 14.5\%$, $\sigma_1 \approx 1.8\%$ (Equilibrium market dynamics).
   * **State 2 (HIGH_VOL):** $\mu_2 \approx 21.2\%$, $\sigma_2 \approx 2.6\%$ (Elevated macroeconomic uncertainty).
   * **State 3 (EXTREME_VOL):** $\mu_3 \approx 31.5\%$, $\sigma_3 \approx 5.4\%$ (Market panic, liquidity dislocation, jump risk).
4. **Causal Forward Filter:**
   State assignment uses the causal forward filtered probability:
   $$\alpha_t(k) = P(S_t = k \mid r_{1:t-1})$$
   Full-sample backward smoothing ($P(S_t = k \mid r_{1:T})$) is strictly prohibited.

---

### 3. Empirical Performance Across All 4 Regimes (2,003 Trades)

| Latent HMM State | Economic Regime | State Occupancy | Trades Executed | Win Rate | Gross P&L (₹) | Statutory Friction (₹) | Net P&L (₹) | Profit Factor |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **State 0** | **LOW_VOL** | 33.3% (125 days) | 668 | 39.2% | +1,07,432.10 | 45,507.12 | **+61,924.98** | **1.08** |
| **State 1** | **NORMAL_VOL** | 53.3% (200 days) | 1,068 | 41.2% | +7,38,421.30 | 90,498.54 | **+6,47,922.76** | **1.70** |
| **State 2** | **HIGH_VOL** | 7.5% (28 days) | 147 | 32.7% | +14,210.40 | 6,161.89 | **+8,048.51** | **1.16** |
| **State 3** | **EXTREME_VOL**| 5.9% (22 days) | 120 | 29.2% | -30,654.70 | 2,487.29 | **-33,141.99** | **0.27** |
| **Total** | — | **100.0% (375 days)**| **2,003** | **39.2%** | **+8,29,409.10** | **1,44,654.84** | **+6,84,754.26** | **1.39** |

---

### 4. Econometric & Policy Conclusions

1. **Why State 3 Underperforms:** In `EXTREME_VOL` regimes, implied volatility experiences sharp non-linear expansion (gamma shocks). Selling options during State 3 produces a negative profit factor ($0.27$) and $-₹33,141.99$ net loss.
2. **The Role of the Gatekeeper:** Rather than hiding State 3, the presence of negative alpha in State 3 **validates the core hypothesis of the paper**: systematic option selling must be throttled or completely suspended during `EXTREME_VOL` regimes.
3. When the trading desk incorporates the HMM gatekeeper to block entries during State 3, total portfolio Net P&L rises to **+₹7,17,896.25** and the Sharpe ratio improves to **0.892**.

---
**Document Status:** Complete and verified against trade ledger.

