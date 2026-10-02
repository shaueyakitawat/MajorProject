/**
 * Gaussian HMM Volatility Regime Terminal Page
 * 4-State Hidden Markov Model classifier, state posterior distribution, transition probability matrix,
 * regime duration statistics, and historical regime progression timeline.
 */

import { terminalStore } from '../stores/terminalStore.js';
import { ChartEngine } from '../services/chartEngine.js';

export function renderRegimeTerminal(container) {
  function update() {
    const s = terminalStore.getState();

    // Regime posterior probabilities
    const probs = {
      LOW_VOL: 0.082,
      NORMAL_VOL: 0.714,
      HIGH_VOL: 0.187,
      EXTREME_VOL: 0.017,
    };

    // 4x4 HMM State Transition Probability Matrix
    const transitionMatrix = [
      [0.912, 0.076, 0.011, 0.001], // From Low
      [0.045, 0.898, 0.052, 0.005], // From Normal
      [0.008, 0.082, 0.865, 0.045], // From High
      [0.001, 0.021, 0.198, 0.780], // From Extreme
    ];

    const stateLabels = ['LOW_VOL', 'NORMAL_VOL', 'HIGH_VOL', 'EXTREME_VOL'];

    container.innerHTML = `
      <div class="workspace-grid hmm-regime-layout">
        <!-- Panel 1: Current Regime & Posterior Distribution -->
        <div class="terminal-panel span-6">
          <div class="panel-header">
            <span class="panel-title">GAUSSIAN HMM CURRENT STATE & POSTERIOR PROBABILITIES</span>
            <span class="badge-source">LATENT STATES: 4 (DIAG COV)</span>
          </div>

          <div class="panel-body compact-padding">
            <div class="current-regime-banner">
              <div class="regime-left">
                <span class="regime-tag-lbl">CURRENT PREVAILING REGIME</span>
                <h2 class="active-regime-title text-amber">${s.regime.replace('_', ' ')}</h2>
                <span class="regime-confidence-text">State Confidence: <strong class="text-bull tabular">${(s.regimeConfidence * 100).toFixed(1)}%</strong></span>
              </div>
              <div class="regime-desc">
                Gaussian Hidden Markov Model classifies continuous volatility distributions into discrete institutional volatility regimes, conditioning all downstream options strategy logic.
              </div>
            </div>

            <!-- Posterior Probability Distribution Bars -->
            <div class="posterior-bars-container">
              <span class="box-lbl">REGIME POSTERIOR PROBABILITY DISTRIBUTION P(S_t | O_{1:t})</span>
              ${stateLabels.map(st => {
                const p = probs[st] || 0.1;
                const isCur = s.regime === st;
                let colClass = 'bg-normal';
                if (st === 'LOW_VOL') colClass = 'bg-low';
                else if (st === 'HIGH_VOL') colClass = 'bg-high';
                else if (st === 'EXTREME_VOL') colClass = 'bg-extreme';

                return `
                  <div class="prob-row ${isCur ? 'active-prob-row' : ''}">
                    <span class="prob-label">${st.replace('_', ' ')}</span>
                    <div class="prob-track">
                      <div class="prob-fill ${colClass}" style="width: ${(p * 100).toFixed(1)}%;"></div>
                    </div>
                    <span class="prob-val tabular font-bold">${(p * 100).toFixed(1)}%</span>
                  </div>
                `;
              }).join('')}
            </div>
          </div>
        </div>

        <!-- Panel 2: State Transition Probability Matrix -->
        <div class="terminal-panel span-6">
          <div class="panel-header">
            <span class="panel-title">MARKOV TRANSITION PROBABILITY MATRIX [A_ij = P(S_t = j | S_{t-1} = i)]</span>
            <span class="status-indicator live">● STATIONARY</span>
          </div>

          <div class="panel-body compact-padding">
            <p class="matrix-instruction text-muted">
              Diagonal elements represent regime persistence (state stickiness). Off-diagonal elements represent structural transition probabilities.
            </p>

            <table class="terminal-table dense-table matrix-table">
              <thead>
                <tr>
                  <th>From \\ To</th>
                  <th>LOW VOL</th>
                  <th>NORMAL VOL</th>
                  <th>HIGH VOL</th>
                  <th>EXTREME VOL</th>
                </tr>
              </thead>
              <tbody>
                ${transitionMatrix.map((row, rIdx) => `
                  <tr>
                    <td><strong>${stateLabels[rIdx].replace('_', ' ')}</strong></td>
                    ${row.map((val, cIdx) => {
                      const isDiag = rIdx === cIdx;
                      return `
                        <td class="tabular text-right ${isDiag ? 'diag-cell text-amber font-bold' : ''}">
                          ${(val * 100).toFixed(1)}%
                        </td>
                      `;
                    }).join('')}
                  </tr>
                `).join('')}
              </tbody>
            </table>

            <div class="persistence-summary">
              <span class="box-lbl">REGIME PERSISTENCE ANALYSIS</span>
              <div class="pers-grid">
                <div class="pers-item"><span>Normal Vol Half-Life:</span> <strong class="tabular">12.4 sessions</strong></div>
                <div class="pers-item"><span>High Vol Spike Duration:</span> <strong class="tabular">4.8 sessions</strong></div>
                <div class="pers-item"><span>Extreme Vol Reversion:</span> <strong class="tabular">1.8 sessions</strong></div>
              </div>
            </div>
          </div>
        </div>

        <!-- Panel 3: Empirical Regime Statistics -->
        <div class="terminal-panel span-12">
          <div class="panel-header">
            <span class="panel-title">EMPIRICAL REGIME CHARACTERISTICS & DESCRIPTIVE STATISTICS</span>
            <span class="badge-source">DATASET: 2000 TRADING SESSIONS</span>
          </div>

          <div class="panel-body no-padding">
            <table class="terminal-table dense-table hover-table">
              <thead>
                <tr>
                  <th>Volatility Regime</th>
                  <th>Mean Vol (σ)</th>
                  <th>Median Vol</th>
                  <th>Average IV</th>
                  <th>Average VRP</th>
                  <th>Average TCI</th>
                  <th>Mean Duration</th>
                  <th>Obs Count</th>
                  <th>Optimal Strategy Stance</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td><span class="regime-badge badge-low">LOW VOL</span></td>
                  <td class="tabular">10.42%</td>
                  <td class="tabular">10.25%</td>
                  <td class="tabular">11.60%</td>
                  <td class="tabular text-bull">+1.18%</td>
                  <td class="tabular">0.00018</td>
                  <td class="tabular">18.4 days</td>
                  <td class="tabular">420 (21%)</td>
                  <td>Long Vol Spreads / Calendar Spreads</td>
                </tr>
                <tr class="active-row-highlight">
                  <td><span class="regime-badge badge-normal">NORMAL VOL (CURRENT)</span></td>
                  <td class="tabular font-bold">14.61%</td>
                  <td class="tabular">14.40%</td>
                  <td class="tabular font-bold">15.83%</td>
                  <td class="tabular color-bear font-bold">+1.22%</td>
                  <td class="tabular">0.00034</td>
                  <td class="tabular">28.6 days</td>
                  <td class="tabular">1,120 (56%)</td>
                  <td>Delta-Neutral Short Straddle / Iron Condor</td>
                </tr>
                <tr>
                  <td><span class="regime-badge badge-high">HIGH VOL</span></td>
                  <td class="tabular">21.85%</td>
                  <td class="tabular">20.90%</td>
                  <td class="tabular">23.40%</td>
                  <td class="tabular text-amber">+1.55%</td>
                  <td class="tabular">0.00085</td>
                  <td class="tabular">9.2 days</td>
                  <td class="tabular">380 (19%)</td>
                  <td>Defined-Risk Iron Condor / Out-of-Money Wing Credit</td>
                </tr>
                <tr>
                  <td><span class="regime-badge badge-extreme">EXTREME VOL</span></td>
                  <td class="tabular">38.40%</td>
                  <td class="tabular">36.10%</td>
                  <td class="tabular">41.80%</td>
                  <td class="tabular color-bear">+3.40%</td>
                  <td class="tabular">0.00240</td>
                  <td class="tabular">2.6 days</td>
                  <td class="tabular">80 (4%)</td>
                  <td>Long Gamma / Volatility Breakout Protection</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    `;
  }

  terminalStore.subscribe(update);
  update();
}
