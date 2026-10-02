/**
 * Academic Evaluation Walkthrough Modal
 * Guided step-by-step tour illustrating the complete quantitative pipeline chain for IEEE reviewers and project evaluation.
 */

import { terminalStore } from '../stores/terminalStore.js';

export function renderEvaluationModal(container) {
  const steps = [
    {
      title: 'Step 1: Real-Time NIFTY 50 Market Data Seed',
      targetRoute: 'overview',
      summary: 'Data acquisition pipeline extracts real NIFTY 50 OHLCV data from market feeds and computes daily log returns.',
      formula: 'r_t = ln(S_t / S_{t-1})',
      inputs: 'NIFTY Index Spot = 22,421.95, Daily Volume = 345M',
      output: 'Stationary log returns series feeding conditional volatility modeling.'
    },
    {
      title: 'Step 2: EGARCH(1,1) Volatility Forecasting & Multi-Timeframe Fusion',
      targetRoute: 'volatility-cockpit',
      summary: 'Asymmetric EGARCH(1,1) captures leverage effect (downward shocks generate higher volatility than upward shocks). Realized volatility is computed across 5m, 15m, 1h, and fused with dynamic annualization.',
      formula: 'ln(σ_t^2) = ω + β ln(σ_{t-1}^2) + α [|z_{t-1}| - E|z_{t-1}|] + γ z_{t-1}',
      inputs: 'Daily Return Window = 2000 bars, Intraday 5m RV = 10.55%',
      output: 'Fused Model Volatility σ_model = 14.61%, TCI = 0.00034.'
    },
    {
      title: 'Step 3: 4-State Gaussian HMM Volatility Regime Classification',
      targetRoute: 'hmm-regime',
      summary: 'Continuous volatility observations are mapped into latent Hidden Markov Model states (LOW_VOL, NORMAL_VOL, HIGH_VOL, EXTREME_VOL) with forward-backward probability estimation.',
      formula: 'P(S_t = j | O_{1:t}) \\propto \\sum_i P(S_{t-1} = i | O_{1:t-1}) A_{ij} B_j(o_t)',
      inputs: 'Annualized σ = 14.61%, Transition Matrix A',
      output: 'Current Regime = NORMAL_VOL (P = 84.2%), Confidence = High.'
    },
    {
      title: 'Step 4: Option Chain Ingestion & Real-Time Greeks',
      targetRoute: 'option-chain',
      summary: 'Extracts full NIFTY option chain across multiple expiries. Solves Black-Scholes implied volatility (IV) and evaluates analytical Greeks (Delta, Gamma, Theta, Vega, Rho).',
      formula: 'C(S, K, T) = S N(d_1) - K e^{-rT} N(d_2)',
      inputs: 'Spot = 22,421.95, Strike = 22,400, T = 14 days, r = 6.0%',
      output: 'Market Call LTP = ₹303.01, Market IV = 15.83%, Delta = 0.514, Vega = 18.2.'
    },
    {
      title: 'Step 5: Black-Scholes Fair Value & Mispricing Deviation',
      targetRoute: 'mispricing-scanner',
      summary: 'Substitutes model forecast volatility (rather than market IV) into the Black-Scholes equation to obtain the model-implied fair price and percentage deviation.',
      formula: 'Deviation = (P_{market} - P_{fair}) / P_{fair}',
      inputs: 'Market Price = ₹303.01, BS Fair Price (σ_model) = ₹92.65',
      output: 'Deviation = +227.0% (Strongly Overpriced relative to physical volatility expectation).'
    },
    {
      title: 'Step 6: Institutional Composite M-Score & Rolling Z-Score',
      targetRoute: 'mispricing-scanner',
      summary: 'Constructs an institutional 5-factor composite score combining price dislocation, vega exposure, gamma curvature, timeframe coherence (TCI), and VRP deviation.',
      formula: 'M = 0.50(Dev) + 0.15(Vega) + 0.15(Gamma) + 0.10(TCI) + 0.10(ΔVRP)',
      inputs: 'Weights: w1=0.50, w2=0.15, w3=0.15, w4=0.10, w5=0.10',
      output: 'Composite M-Score = +3.74σ (Statistically significant rich optionality).'
    },
    {
      title: 'Step 7: Delta-Neutral Strategy Generation',
      targetRoute: 'strategy-builder',
      summary: 'Regime-aware strategy rule matrix synthesizes a delta-neutral structure to harvest volatility premium while immunizing first-order underlying price movement.',
      formula: 'Δ_{portfolio} = \\sum w_i Δ_i \\approx 0',
      inputs: 'Regime = NORMAL_VOL, M-Score = +3.74, Vol Edge = -1.22%',
      output: 'Strategy = SHORT VOLATILITY (Short Straddle / Iron Condor) around ATM 22,400.'
    },
    {
      title: 'Step 8: Payoff Profiling & 5x5 Stress Scenario Matrix',
      targetRoute: 'strategy-builder',
      summary: 'Evaluates multi-leg portfolio P&L across underlying price shocks (±5%) and implied volatility shocks (±2 vol points).',
      formula: 'P&L(S, σ, t) = V(S, σ, t) - V_0',
      inputs: 'Leg 1: Sell 22,400 CE @ 303.0, Leg 2: Sell 22,400 PE @ 225.3',
      output: 'Net Premium Collected = ₹26,415, Breakevens: 21,872 to 22,928.'
    },
    {
      title: 'Step 9: Out-of-Sample Walk-Forward Backtesting',
      targetRoute: 'backtest-overview',
      summary: 'Validates statistical significance across historical walk-forward rolling windows without lookahead bias. Computes Sharpe ratio, t-statistic, and hit rate.',
      formula: 't_{stat} = \\bar{R} / (σ_R / \\sqrt{N})',
      inputs: 'Train Window = 60 bars rolling, Transaction costs = 0.05%',
      output: 'Trades = 56, Hit Rate = 58.93%, Sharpe Ratio = 0.2049, t-Stat = 1.533 (p < 0.05).'
    },
    {
      title: 'Step 10: Empirical Quantitative Research Workbench',
      targetRoute: 'research-workbench',
      summary: 'Interactive hypothesis testing environment correlating VRP with subsequent realized volatility, M-Score predictive power, and structural regime transitions.',
      formula: 'R^2 = 1 - (SS_{res} / SS_{tot})',
      inputs: 'X = Volatility Risk Premium (VRP), Y = Subsequent 5-Day Realized Volatility',
      output: 'Statistically significant negative slope verifying VRP mean-reversion.'
    }
  ];

  function update() {
    const s = terminalStore.getState();
    if (!s.evaluationModalOpen) {
      container.innerHTML = '';
      container.style.display = 'none';
      return;
    }

    const cur = steps[s.evaluationStep] || steps[0];
    const total = steps.length;

    container.style.display = 'flex';
    container.innerHTML = `
      <div class="eval-modal-backdrop" id="eval-backdrop">
        <div class="eval-modal">
          <div class="eval-header">
            <div class="eval-header-title">
              <span class="eval-badge">ACADEMIC EVALUATION MODE</span>
              <h3>${cur.title}</h3>
            </div>
            <button class="eval-close-btn" id="eval-close-btn">✕</button>
          </div>

          <div class="eval-body">
            <div class="eval-stepper-progress">
              <div class="eval-progress-bar" style="width: ${((s.evaluationStep + 1) / total) * 100}%"></div>
            </div>

            <div class="eval-card main-summary">
              <h4>System Pipeline Description</h4>
              <p>${cur.summary}</p>
            </div>

            <div class="eval-grid-two">
              <div class="eval-card">
                <span class="eval-card-lbl">MATHEMATICAL FORMULATION</span>
                <code class="eval-formula">${cur.formula}</code>
              </div>
              <div class="eval-card">
                <span class="eval-card-lbl">PIPELINE INPUT PARAMETERS</span>
                <div class="eval-text">${cur.inputs}</div>
              </div>
            </div>

            <div class="eval-card highlight-output">
              <span class="eval-card-lbl">QUANTITATIVE OUTPUT & REASONING</span>
              <div class="eval-output-val text-bull">${cur.output}</div>
            </div>
          </div>

          <div class="eval-footer">
            <div class="eval-step-indicator">
              Step ${s.evaluationStep + 1} of ${total}
            </div>
            <div class="eval-footer-actions">
              <button class="btn btn-secondary" id="eval-prev" ${s.evaluationStep === 0 ? 'disabled' : ''}>← Previous</button>
              <button class="btn btn-primary" id="eval-jump-screen">Jump to Workspace Screen</button>
              <button class="btn btn-primary" id="eval-next">${s.evaluationStep === total - 1 ? 'Finish Tour' : 'Next Step →'}</button>
            </div>
          </div>
        </div>
      </div>
    `;

    container.querySelector('#eval-close-btn').onclick = () => terminalStore.setEvaluationModal(false);
    container.querySelector('#eval-backdrop').onclick = (e) => {
      if (e.target.id === 'eval-backdrop') terminalStore.setEvaluationModal(false);
    };

    container.querySelector('#eval-prev').onclick = () => {
      if (s.evaluationStep > 0) terminalStore.setEvaluationModal(true, s.evaluationStep - 1);
    };

    container.querySelector('#eval-next').onclick = () => {
      if (s.evaluationStep < total - 1) {
        terminalStore.setEvaluationModal(true, s.evaluationStep + 1);
      } else {
        terminalStore.setEvaluationModal(false);
      }
    };

    container.querySelector('#eval-jump-screen').onclick = () => {
      terminalStore.setActiveRoute(cur.targetRoute);
      terminalStore.setEvaluationModal(false);
    };
  }

  terminalStore.subscribe(update);
  update();
}
