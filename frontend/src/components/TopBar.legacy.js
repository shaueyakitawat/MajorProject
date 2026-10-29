/**
 * Top Global Terminal Bar
 * Displays live tickers, regime status, market health badges, and real-time IST clock.
 */

import { terminalStore } from '../stores/terminalStore.js';

export function renderTopBar(container) {
  function update() {
    const s = terminalStore.getState();
    const isBull = s.niftyChange >= 0;
    const changeColor = isBull ? 'color-bull' : 'color-bear';
    const changeSign = isBull ? '+' : '';

    const istTime = new Date().toLocaleTimeString('en-IN', {
      timeZone: 'Asia/Kolkata',
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });

    // Regime color
    let regimeBadgeClass = 'badge-normal';
    if (s.regime === 'LOW_VOL') regimeBadgeClass = 'badge-low';
    else if (s.regime === 'HIGH_VOL') regimeBadgeClass = 'badge-high';
    else if (s.regime === 'EXTREME_VOL') regimeBadgeClass = 'badge-extreme';

    container.innerHTML = `
      <div class="topbar-inner">
        <!-- Brand & Quick Jump -->
        <div class="topbar-section brand-group">
          <span class="terminal-brand-tag">QUANT TERMINAL</span>
          <button class="terminal-cmd-btn" id="topbar-cmd-btn" title="Open Command Palette (Ctrl+K)">
            <span class="cmd-icon">⌘</span>
            <span class="cmd-text">SEARCH / CMD</span>
            <kbd class="kbd-hint">Ctrl+K</kbd>
          </button>
        </div>

        <!-- Live Financial Ticker Strip -->
        <div class="topbar-section ticker-strip">
          <!-- NIFTY 50 -->
          <div class="ticker-item" title="NIFTY 50 Spot Index">
            <span class="ticker-label">NIFTY 50</span>
            <span class="ticker-val tabular">${s.niftySpot.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
            <span class="ticker-delta ${changeColor} tabular">${changeSign}${s.niftyChange.toFixed(2)} (${changeSign}${s.niftyChangePct.toFixed(2)}%)</span>
          </div>

          <div class="ticker-sep">│</div>

          <!-- INDIA VIX -->
          <div class="ticker-item" title="India Volatility Index">
            <span class="ticker-label">INDIA VIX</span>
            <span class="ticker-val tabular">${s.indiaVix.toFixed(2)}</span>
            <span class="ticker-delta color-bull tabular">${s.indiaVixChange >= 0 ? '+' : ''}${s.indiaVixChange.toFixed(2)}%</span>
          </div>

          <div class="ticker-sep">│</div>

          <!-- REGIME -->
          <div class="ticker-item" title="Gaussian HMM Volatility Regime">
            <span class="ticker-label">REGIME</span>
            <span class="regime-badge ${regimeBadgeClass}">${s.regime.replace('_', ' ')}</span>
          </div>

          <div class="ticker-sep">│</div>

          <!-- ATM Strike -->
          <div class="ticker-item" title="At-The-Money Strike">
            <span class="ticker-label">ATM</span>
            <span class="ticker-val tabular text-amber">${s.atmStrike.toLocaleString('en-IN')}</span>
          </div>

          <div class="ticker-sep">│</div>

          <!-- Nearest Expiry -->
          <div class="ticker-item" title="Nearest Weekly Option Expiry">
            <span class="ticker-label">NEAREST EXPIRY</span>
            <span class="ticker-val">${s.selectedExpiry}</span>
          </div>

          <div class="ticker-sep">│</div>

          <!-- Next Expiry -->
          <div class="ticker-item" title="Next Weekly Option Expiry">
            <span class="ticker-label">NEXT EXPIRY</span>
            <span class="ticker-val">${s.secondExpiry}</span>
          </div>
        </div>

        <!-- Terminal Status Badges & Controls -->
        <div class="topbar-section control-group">
          <div class="status-badge-item" title="Real-time market feed connection">
            <span class="status-led led-green"></span>
            <span class="status-badge-label">DATA: ${s.systemStatus.data}</span>
          </div>

          <div class="status-badge-item" title="FastAPI Backend Health">
            <span class="status-led ${s.systemStatus.api === 'CONNECTED' ? 'led-green' : 'led-red'}"></span>
            <span class="status-badge-label">API: ${s.systemStatus.api}</span>
          </div>

          <div class="status-badge-item" title="Quantitative model engine status">
            <span class="status-led led-green"></span>
            <span class="status-badge-label">MODEL: ${s.systemStatus.model}</span>
          </div>

          <!-- Real-Time Clock -->
          <div class="clock-display" title="Indian Standard Time">
            <span class="clock-time tabular">${istTime} IST</span>
          </div>

          <!-- Guided Academic Walkthrough -->
          <button class="topbar-action-btn eval-btn" id="btn-eval-walkthrough" title="Start Academic Evaluation Walkthrough">
            <span>🎓 EVALUATION</span>
          </button>

          <!-- Density Toggle -->
          <button class="topbar-action-btn icon-only" id="btn-toggle-density" title="Toggle Display Density (Compact / Normal)">
            <span>${s.density === 'compact' ? '↕' : '≡'}</span>
          </button>

          <!-- Theme Toggle -->
          <button class="topbar-action-btn icon-only" id="btn-toggle-theme" title="Toggle Terminal Dark / Light Mode">
            <span>${s.theme === 'dark' ? '🌙' : '☀️'}</span>
          </button>
        </div>
      </div>
    `;

    // Bind event handlers
    const cmdBtn = container.querySelector('#topbar-cmd-btn');
    if (cmdBtn) cmdBtn.onclick = () => terminalStore.setCommandPalette(true);

    const evalBtn = container.querySelector('#btn-eval-walkthrough');
    if (evalBtn) evalBtn.onclick = () => terminalStore.setEvaluationModal(true, 0);

    const densityBtn = container.querySelector('#btn-toggle-density');
    if (densityBtn) densityBtn.onclick = () => terminalStore.toggleDensity();

    const themeBtn = container.querySelector('#btn-toggle-theme');
    if (themeBtn) themeBtn.onclick = () => terminalStore.toggleTheme();
  }

  // Live real-time tick interval for clock
  setInterval(() => {
    const clockEl = container.querySelector('.clock-time');
    if (clockEl) {
      clockEl.textContent = new Date().toLocaleTimeString('en-IN', {
        timeZone: 'Asia/Kolkata',
        hour12: false,
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      }) + ' IST';
    }
  }, 1000);

  terminalStore.subscribe(update);
  update();
}
