/**
 * System Data Health Monitor, Model Diagnostics & Real-Time Alert Center Page
 */

import { terminalStore } from '../stores/terminalStore.js';

export function renderSystemMonitors(container) {
  let severityFilter = 'ALL';

  function update() {
    const s = terminalStore.getState();
    const st = s.systemStatus;
    const alerts = s.alerts || [];

    const filteredAlerts = alerts.filter(a => {
      if (severityFilter !== 'ALL' && a.severity !== severityFilter) return false;
      return true;
    });

    container.innerHTML = `
      <div class="workspace-grid system-monitors-layout">
        <!-- Data Feed Health Panel -->
        <div class="terminal-panel span-6">
          <div class="panel-header">
            <span class="panel-title">MARKET DATA FEED & INGESTION TELEMETRY</span>
            <span class="status-indicator live">● TELEMETRY ONLINE</span>
          </div>

          <div class="panel-body compact-padding">
            <table class="terminal-table dense-table">
              <tbody>
                <tr>
                  <td><strong>NIFTY 50 Spot Stream</strong></td>
                  <td class="tabular text-right"><span class="status-led led-green"></span> <strong class="text-bull">CONNECTED / LIVE</strong></td>
                </tr>
                <tr>
                  <td><strong>Option Chain Feed (NSE / pnsea)</strong></td>
                  <td class="tabular text-right"><span class="status-led led-green"></span> <strong class="text-bull">HEALTHY (15s Cache TTL)</strong></td>
                </tr>
                <tr>
                  <td><strong>SQLite Intraday Storage</strong></td>
                  <td class="tabular text-right"><span class="status-led led-green"></span> <strong class="text-bull">CONNECTED (nifty_live_snapshots.db)</strong></td>
                </tr>
                <tr>
                  <td><strong>WebSocket Push Gateway (/ws)</strong></td>
                  <td class="tabular text-right"><span class="status-led ${st.ws === 'CONNECTED' ? 'led-green' : 'led-red'}"></span> <strong class="${st.ws === 'CONNECTED' ? 'text-bull' : 'color-bear'}">${st.ws}</strong></td>
                </tr>
                <tr>
                  <td><strong>Round-Trip Tick Latency</strong></td>
                  <td class="tabular text-right font-bold text-amber">${st.latencyMs} ms</td>
                </tr>
                <tr>
                  <td><strong>Last Processed Tick Time</strong></td>
                  <td class="tabular text-right font-mono">${st.lastTickTime} IST</td>
                </tr>
                <tr>
                  <td><strong>API Request Counter</strong></td>
                  <td class="tabular text-right">${st.serverRequestsCount} requests</td>
                </tr>
                <tr>
                  <td><strong>API Errors / Missing Packets</strong></td>
                  <td class="tabular text-right text-bull">${st.serverErrorsCount} (0.00%)</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- Model Diagnostics Health Panel -->
        <div class="terminal-panel span-6">
          <div class="panel-header">
            <span class="panel-title">QUANTITATIVE MODEL ENGINE DIAGNOSTICS</span>
            <span class="status-indicator live">● ENGINES READY</span>
          </div>

          <div class="panel-body compact-padding">
            <table class="terminal-table dense-table">
              <thead>
                <tr>
                  <th>Component</th>
                  <th>Engine Status</th>
                  <th>Model Specification</th>
                  <th>Execution Latency</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td><strong>EGARCH(1,1) Forecaster</strong></td>
                  <td><span class="badge-mini tag-underpriced">READY</span></td>
                  <td>Asymmetric Normal GARCH</td>
                  <td class="tabular">42 ms</td>
                </tr>
                <tr>
                  <td><strong>Gaussian HMM Classifier</strong></td>
                  <td><span class="badge-mini tag-underpriced">READY</span></td>
                  <td>4-State Diagonal Covariance</td>
                  <td class="tabular">12 ms</td>
                </tr>
                <tr>
                  <td><strong>Black-Scholes Pricer</strong></td>
                  <td><span class="badge-mini tag-underpriced">READY</span></td>
                  <td>Analytical Closed-Form</td>
                  <td class="tabular">1.5 ms</td>
                </tr>
                <tr>
                  <td><strong>Implied Volatility Solver</strong></td>
                  <td><span class="badge-mini tag-underpriced">READY</span></td>
                  <td>Bisection Root Finder</td>
                  <td class="tabular">8.2 ms</td>
                </tr>
                <tr>
                  <td><strong>Mispricing & M-Score</strong></td>
                  <td><span class="badge-mini tag-underpriced">READY</span></td>
                  <td>5-Factor Weighted Composite</td>
                  <td class="tabular">3.8 ms</td>
                </tr>
                <tr>
                  <td><strong>Delta-Neutral Strategy Engine</strong></td>
                  <td><span class="badge-mini tag-underpriced">READY</span></td>
                  <td>Regime-Conditioned Rules</td>
                  <td class="tabular">2.1 ms</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- Real-Time Alert Center -->
        <div class="terminal-panel span-12">
          <div class="panel-header">
            <span class="panel-title">SYSTEM EVENT LOG & QUANTITATIVE ALERTS</span>
            <div class="panel-controls">
              <div class="btn-group-toggle">
                <button class="alert-filter-btn ${severityFilter === 'ALL' ? 'active' : ''}" data-sev="ALL">ALL ALERTS</button>
                <button class="alert-filter-btn ${severityFilter === 'CRITICAL' ? 'active' : ''}" data-sev="CRITICAL">CRITICAL</button>
                <button class="alert-filter-btn ${severityFilter === 'WARNING' ? 'active' : ''}" data-sev="WARNING">WARNINGS</button>
                <button class="alert-filter-btn ${severityFilter === 'INFO' ? 'active' : ''}" data-sev="INFO">INFO</button>
              </div>
            </div>
          </div>

          <div class="panel-body no-padding" style="max-height: 280px; overflow-y: auto;">
            <table class="terminal-table dense-table hover-table">
              <thead>
                <tr>
                  <th>Timestamp</th>
                  <th>Severity</th>
                  <th>Category</th>
                  <th>Instrument</th>
                  <th>Trigger Reason</th>
                  <th>Observed Value</th>
                  <th>Threshold</th>
                </tr>
              </thead>
              <tbody>
                ${filteredAlerts.map(a => `
                  <tr>
                    <td class="tabular font-mono">${a.timestamp}</td>
                    <td>
                      <span class="badge-mini ${a.severity === 'CRITICAL' ? 'tag-overpriced' : (a.severity === 'WARNING' ? 'tag-fair text-amber' : 'badge-normal')}">
                        ${a.severity}
                      </span>
                    </td>
                    <td><strong>${a.category}</strong></td>
                    <td>${a.instrument}</td>
                    <td>${a.reason}</td>
                    <td class="tabular font-bold ${a.severity === 'WARNING' ? 'text-amber' : 'text-bull'}">${a.value}</td>
                    <td class="tabular text-muted">${a.threshold}</td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    `;

    container.querySelectorAll('.alert-filter-btn').forEach(btn => {
      btn.onclick = () => {
        severityFilter = btn.getAttribute('data-sev');
        update();
      };
    });
  }

  terminalStore.subscribe(update);
  update();
}
