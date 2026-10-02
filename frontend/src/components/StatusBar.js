/**
 * Bottom Terminal Status Bar Component
 * Displays system connectivity, latency, active instrument state, and database status.
 */

import { terminalStore } from '../stores/terminalStore.js';

export function renderStatusBar(container) {
  function update() {
    const s = terminalStore.getState();
    const st = s.systemStatus;

    container.innerHTML = `
      <div class="statusbar-inner">
        <div class="statusbar-left">
          <span class="status-item"><strong class="status-label">DATA:</strong> <span class="status-val text-bull">${st.data}</span></span>
          <span class="status-sep">│</span>
          <span class="status-item"><strong class="status-label">LATENCY:</strong> <span class="status-val tabular">${st.latencyMs}ms</span></span>
          <span class="status-sep">│</span>
          <span class="status-item"><strong class="status-label">NIFTY:</strong> <span class="status-val tabular">${s.niftySpot.toFixed(2)}</span></span>
          <span class="status-sep">│</span>
          <span class="status-item"><strong class="status-label">ATM:</strong> <span class="status-val tabular text-amber">${s.atmStrike}</span></span>
          <span class="status-sep">│</span>
          <span class="status-item"><strong class="status-label">EXPIRY:</strong> <span class="status-val">${s.selectedExpiry}</span></span>
          <span class="status-sep">│</span>
          <span class="status-item"><strong class="status-label">REGIME:</strong> <span class="status-val">${s.regime.replace('_', ' ')}</span></span>
        </div>

        <div class="statusbar-right">
          <span class="status-item"><strong class="status-label">MODEL:</strong> <span class="status-val text-bull">${st.model}</span></span>
          <span class="status-sep">│</span>
          <span class="status-item"><strong class="status-label">WS:</strong> <span class="status-val ${st.ws === 'CONNECTED' ? 'text-bull' : 'text-bear'}">${st.ws}</span></span>
          <span class="status-sep">│</span>
          <span class="status-item"><strong class="status-label">DB:</strong> <span class="status-val text-bull">${st.db}</span></span>
          <span class="status-sep">│</span>
          <span class="status-item text-muted">LAST TICK: <span class="tabular">${st.lastTickTime}</span></span>
        </div>
      </div>
    `;
  }

  terminalStore.subscribe(update);
  update();
}
