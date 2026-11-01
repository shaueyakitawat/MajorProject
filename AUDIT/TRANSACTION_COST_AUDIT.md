# AUDIT/TRANSACTION_COST_AUDIT.md
## Indian Derivatives Statutory Transaction Cost Audit

**Audit Date:** 2026-11-01  
**Auditor Roles:** Senior Derivatives Operations Specialist & Algorithmic Trading Systems Engineer  
**Component Audited:** Indian Exchange, SEBI, and Ministry of Finance Statutory Friction Engine  
**Implementation:** `backend/services/cost_engine.py`

---

### 1. Executive Summary

A critical weakness in options backtesting literature is the oversimplification of transaction costs. In India, derivatives trading is subject to a complex, multi-tiered statutory taxation framework governed by the **Securities Contracts (Regulation) Act**, the **Finance Act**, and **NSE Exchange Circulars**.

The existing implementation applied a static, uniform STT rate of 0.125% across all transaction types and dates. This assumption has been replaced by a **centralized, historically versioned statutory cost engine** (`IndianDerivativesCostEngine`) that accurately models pre- and post-October 1, 2024 statutory regimes.

---

### 2. Historical Regulatory Tax Regimes

#### 2.1 Pre-October 1, 2024 Regime (Baseline Rules)
* **Securities Transaction Tax (STT):**
  * *Option Sale:* **0.0625%** on option premium turnover.
  * *Option Purchase:* **0.00%** (STT is not levied on option purchases in India).
  * *In-The-Money (ITM) Exercise Settlement:* **0.125%** on intrinsic settlement value for option buyers.
* **Exchange Turnover Fee (NSE):** **0.053%** of premium turnover.
* **SEBI Turnover Fee:** ₹10 per crore (**0.0001%**).
* **Stamp Duty (Indian Stamp Act):** **0.003%** on buy-side turnover only.
* **Goods and Services Tax (GST):** **18.0%** levied on (Brokerage + Exchange Turnover Fee + SEBI Fee). STT and Stamp Duty are statutory taxes and are exempt from GST.
* **Brokerage:** ₹20.00 flat per executed order.

#### 2.2 Post-October 1, 2024 Regime (Finance (No. 2) Act, 2024 Revisions)
Effective October 1, 2024, the Indian Ministry of Finance enacted significant revisions to derivative taxation:
* **Securities Transaction Tax (STT) Revision:**
  * STT on the sale of options was increased by 60%, from **0.0625% to 0.100%** of premium turnover (Finance Act 2024, Section 98).
  * *Note on Common Literature Error:* Many papers incorrectly cite 0.125% for options. The 0.125% rate applies to equity futures turnover (increased from 0.0125% to 0.0200%), whereas options premium STT was revised specifically to 0.100%.
* **Exchange Turnover Fee Revision:**
  * Concurrently, SEBI mandated a flat fee structure for market infrastructure institutions, eliminating slab-based rebates. The effective NSE index options fee transitioned to a flat tariff of ₹350 per crore (**0.035%**).

---

### 3. Mathematical Formula for Round-Trip Friction

For an option trade entered at price $P_1$ on date $t_1$ and closed at price $P_2$ on date $t_2$ for quantity $Q$:

$$\begin{aligned}
\text{Turnover}_1 &= P_1 \times Q, \quad \text{Turnover}_2 = P_2 \times Q \\
\text{Brokerage} &= \text{₹}20 + \text{₹}20 = \text{₹}40.00 \\
\text{STT} &= \begin{cases} 
\text{Turnover}_1 \times \tau_{\mathrm{STT}}(t_1) & \text{if Short (Entry SELL, Exit BUY)} \\
\text{Turnover}_2 \times \tau_{\mathrm{STT}}(t_2) & \text{if Long (Entry BUY, Exit SELL)} 
\end{cases} \\
\text{Stamp Duty} &= \begin{cases} 
\text{Turnover}_1 \times 0.00003 & \text{if Long (Entry BUY)} \\
\text{Turnover}_2 \times 0.00003 & \text{if Short (Exit BUY)} 
\end{cases} \\
\text{Exchange Fee} &= \text{Turnover}_1 \times \tau_{\mathrm{NSE}}(t_1) + \text{Turnover}_2 \times \tau_{\mathrm{NSE}}(t_2) \\
\text{SEBI Fee} &= (\text{Turnover}_1 + \text{Turnover}_2) \times 0.000001 \\
\text{GST} &= 0.18 \times (\text{Brokerage} + \text{Exchange Fee} + \text{SEBI Fee}) \\
\mathbf{\text{Total Friction}} &= \text{Brokerage} + \text{STT} + \text{Stamp Duty} + \text{Exchange Fee} + \text{SEBI Fee} + \text{GST}
\end{aligned}$$

---

### 4. Implementation Validation

The new module `backend/services/cost_engine.py` passes all automated unit tests (`tests/test_cost_engine.py`), verifying exact penny reconciliation across both pre- and post-October 2024 execution legs.

---
**Document Status:** Complete and verified.
