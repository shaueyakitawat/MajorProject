/**
 * ============================================================================
 * QuantLens — Frontend Application Logic
 * NIFTY 50 Option Mispricing Engine Dashboard
 * ============================================================================
 */

// ========== CONFIGURATION ==========
const API_BASE = window.location.origin;
let currentTimeframe = 'daily';
let currentHorizon = '';
let isRefreshing = false;
let lastStrategyData = null;

// ========== THEME MANAGEMENT ==========
function getStoredTheme() {
  return localStorage.getItem('quantlens-theme') || 'dark';
}

function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  const icon = document.getElementById('theme-icon');
  const label = document.getElementById('theme-label');
  if (theme === 'dark') {
    icon.textContent = '🌙';
    label.textContent = 'Dark';
  } else {
    icon.textContent = '☀️';
    label.textContent = 'Light';
  }
  localStorage.setItem('quantlens-theme', theme);
}

function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme');
  const next = current === 'dark' ? 'light' : 'dark';
  applyTheme(next);
}

// Initialize theme
applyTheme(getStoredTheme());

// ========== TOAST NOTIFICATIONS ==========
function showToast(message, type = 'info', duration = 4000) {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  
  const icons = { success: '✓', error: '✕', info: 'ℹ' };
  toast.innerHTML = `
    <span style="font-weight:700;font-size:1rem;">${icons[type] || 'ℹ'}</span>
    <span>${message}</span>
  `;
  
  container.appendChild(toast);
  
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(20px)';
    toast.style.transition = 'all 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

// ========== API UTILITIES ==========
async function apiCall(endpoint, params = {}) {
  const url = new URL(`${API_BASE}${endpoint}`);
  Object.entries(params).forEach(([key, val]) => {
    if (val !== null && val !== undefined && val !== '') {
      url.searchParams.set(key, val);
    }
  });
  
  const response = await fetch(url.toString());
  if (!response.ok) {
    throw new Error(`API Error: ${response.status} ${response.statusText}`);
  }
  return response.json();
}

async function checkHealth() {
  try {
    const data = await apiCall('/health');
    setApiStatus(true);
    return data;
  } catch (e) {
    setApiStatus(false);
    return null;
  }
}

function setApiStatus(online) {
  const dot = document.getElementById('status-dot');
  const text = document.getElementById('status-text');
  
  if (online) {
    dot.classList.remove('offline');
    text.textContent = 'Connected';
  } else {
    dot.classList.add('offline');
    text.textContent = 'Offline';
  }
}

// ========== FORMATTING UTILITIES ==========
function formatNumber(num, decimals = 2) {
  if (num === null || num === undefined || isNaN(num)) return '--';
  return Number(num).toLocaleString('en-IN', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals
  });
}

function formatPercent(num, decimals = 2) {
  if (num === null || num === undefined || isNaN(num)) return '--';
  return `${Number(num).toFixed(decimals)}%`;
}

function formatPrice(num) {
  if (num === null || num === undefined || isNaN(num)) return '--';
  return `₹${formatNumber(num, 2)}`;
}

function formatTimestamp() {
  return new Date().toLocaleTimeString('en-IN', { hour12: false });
}

function getSignalColor(signal) {
  if (!signal) return '';
  const s = signal.toLowerCase();
  if (s.includes('overpriced') || s.includes('sell')) return 'text-bearish';
  if (s.includes('underpriced') || s.includes('buy')) return 'text-bullish';
  if (s.includes('fair') || s.includes('hold')) return 'text-info';
  return '';
}

function getSignalBadgeClass(signal) {
  if (!signal) return '';
  const s = signal.toLowerCase();
  if (s.includes('overpriced')) return 'overpriced';
  if (s.includes('underpriced')) return 'underpriced';
  return 'fair';
}

function getRegimeBadgeClass(regime) {
  if (!regime) return '';
  const r = regime.toLowerCase();
  if (r.includes('low')) return 'low';
  if (r.includes('normal') || r.includes('moderate')) return 'normal';
  if (r.includes('high')) return 'high';
  if (r.includes('extreme') || r.includes('panic') || r.includes('crisis')) return 'extreme';
  return 'normal';
}

function getRegimeEmoji(regime) {
  if (!regime) return '🔮';
  const r = regime.toLowerCase();
  if (r.includes('low')) return '🟢';
  if (r.includes('normal') || r.includes('moderate')) return '🔵';
  if (r.includes('high')) return '🟡';
  if (r.includes('extreme') || r.includes('panic') || r.includes('crisis')) return '🔴';
  return '🔮';
}

// ========== TIMEFRAME & HORIZON CONTROLS ==========
function setTimeframe(tf) {
  currentTimeframe = tf;
  document.querySelectorAll('#timeframe-tabs .tab').forEach(btn => {
    btn.classList.toggle('active', btn.getAttribute('data-tf') === tf);
  });
  refreshAll();
}

function setHorizon(horizon) {
  currentHorizon = horizon;
  refreshAll();
}

// ========== MAIN DATA LOADERS ==========
async function loadStrategy() {
  try {
    const params = { timeframe: currentTimeframe };
    if (currentHorizon) params.trading_horizon = currentHorizon;
    
    const data = await apiCall('/strategy', params);
    
    if (data.status === 'success' && data.data) {
      lastStrategyData = data.data;
      renderStrategy(data.data, data.meta);
      setApiStatus(true);
    } else {
      throw new Error(data.error || 'Unknown error');
    }
  } catch (e) {
    console.error('Strategy load error:', e);
    showToast(`Strategy error: ${e.message}`, 'error');
    setApiStatus(false);
  }
}

function renderStrategy(d, meta) {
  // KPIs
  document.getElementById('kpi-spot-value').textContent = formatPrice(d.spot_price);
  
  const volVal = d.forecast_volatility;
  const volDisplay = volVal ? `${(volVal * 100).toFixed(2)}%` : '--';
  document.getElementById('kpi-vol-value').textContent = volDisplay;
  
  document.getElementById('kpi-fair-value').textContent = formatPrice(d.fair_price);
  document.getElementById('kpi-market-value').textContent = formatPrice(d.market_price);
  
  // Mispricing Signal KPI
  const mispricingSignal = d.mispricing?.signal || d.mispricing?.classification || '--';
  const mispricingDev = d.mispricing?.deviation_pct ?? d.mispricing?.deviation;
  const signalEl = document.getElementById('kpi-signal-value');
  signalEl.innerHTML = `<span class="signal-badge ${getSignalBadgeClass(mispricingSignal)}">${mispricingSignal}</span>`;
  
  const devEl = document.getElementById('kpi-signal-deviation');
  if (mispricingDev !== null && mispricingDev !== undefined) {
    const devColor = mispricingDev > 0 ? 'text-bearish' : mispricingDev < 0 ? 'text-bullish' : '';
    const devSign = mispricingDev > 0 ? '+' : '';
    devEl.innerHTML = `<span class="${devColor}">${devSign}${formatPercent(mispricingDev)}</span> deviation`;
  }
  
  // Regime KPI
  const regime = d.regime || '--';
  const regimeEl = document.getElementById('kpi-regime-value');
  regimeEl.innerHTML = `<span class="regime-badge ${getRegimeBadgeClass(regime)}">${getRegimeEmoji(regime)} ${regime}</span>`;
  
  // Pipeline flow nodes
  updatePipelineFlow(d, meta);
  
  // Strategy Card
  renderStrategyCard(d);
  
  // Volatility Analysis Card
  renderVolatilityCard(d);
  
  // Mispricing Details Card
  renderMispricingCard(d);
  
  // Regime Detail Card
  renderRegimeCard(d);
  
  // Model Info Card
  renderModelInfoCard(d);
  
  // Pipeline Health Card
  renderHealthCard(d);
  
  // Execution time
  if (meta?.execution_time_ms) {
    document.getElementById('exec-time-value').textContent = `${meta.execution_time_ms} ms`;
  }
  
  // Pipeline status badge
  document.getElementById('pipeline-status-badge').textContent = 'LIVE';
  document.getElementById('pipeline-status-badge').className = 'card-badge bg-bullish';
  
  // Last update time
  document.getElementById('last-update-time').textContent = formatTimestamp();
}

function updatePipelineFlow(d, meta) {
  const tf = meta?.timeframe_used || currentTimeframe;
  document.getElementById('pn-data-val').textContent = tf.toUpperCase();
  document.getElementById('pn-data').classList.add('active');
  
  document.getElementById('pn-returns-val').textContent = 'ln(Sₜ/Sₜ₋₁)';
  document.getElementById('pn-returns').classList.add('active');
  
  const vol = d.forecast_volatility;
  document.getElementById('pn-egarch-val').textContent = vol ? `σ = ${(vol * 100).toFixed(1)}%` : '--';
  document.getElementById('pn-egarch').classList.add('active');
  
  document.getElementById('pn-hmm-val').textContent = d.regime || '--';
  document.getElementById('pn-hmm').classList.add('active');
  
  document.getElementById('pn-bs-val').textContent = d.fair_price ? formatPrice(d.fair_price) : '--';
  document.getElementById('pn-bs').classList.add('active');
  
  const sig = d.mispricing?.signal || '--';
  document.getElementById('pn-signal-val').textContent = sig;
  document.getElementById('pn-signal').classList.add('active');
}

function renderStrategyCard(d) {
  const container = document.getElementById('strategy-content');
  const strategy = d.strategy || {};
  const signal = strategy.strategy_type || strategy.action || strategy.signal || strategy.strategy || '--';
  const confidence = strategy.confidence || '--';
  const rationale = strategy.entry_condition || strategy.rationale || strategy.reason || strategy.strategy || '--';
  const riskLevel = strategy.risk_notes ? strategy.risk_notes[0] : (strategy.risk_level || '--');
  
  // Update badge
  const badge = document.getElementById('strategy-type-badge');
  if (signal.toLowerCase().includes('sell')) {
    badge.className = 'card-badge bg-bearish';
  } else if (signal.toLowerCase().includes('buy')) {
    badge.className = 'card-badge bg-bullish';
  } else {
    badge.className = 'card-badge bg-info';
  }
  badge.textContent = signal;
  
  container.innerHTML = `
    <div style="margin-bottom:var(--space-md);">
      <div style="font-size:1.2rem;font-weight:800;margin-bottom:4px;" class="${getSignalColor(signal)}">${signal}</div>
      <div style="font-size:0.82rem;color:var(--text-secondary);line-height:1.5;">${rationale}</div>
    </div>
    <div class="divider"></div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--space-md);">
      <div class="stat-row" style="flex-direction:column;align-items:flex-start;border:none;">
        <span class="stat-label">Confidence</span>
        <span class="stat-value">${typeof confidence === 'number' ? formatPercent(confidence * 100, 0) : confidence}</span>
      </div>
      <div class="stat-row" style="flex-direction:column;align-items:flex-start;border:none;">
        <span class="stat-label">Risk Level</span>
        <span class="stat-value">${riskLevel}</span>
      </div>
    </div>
    ${strategy.suggested_spread ? `
    <div class="divider"></div>
    <div>
      <span class="stat-label" style="display:block;margin-bottom:6px;">Suggested Spread</span>
      <span class="stat-value" style="font-size:0.85rem;">${strategy.suggested_spread}</span>
    </div>
    ` : ''}
  `;
}

function renderVolatilityCard(d) {
  const container = document.getElementById('vol-analysis-content');
  const forecastVol = d.forecast_volatility || d.forecasted_volatility;
  const iv = d.implied_volatility;
  const volSpread = d.vol_spread;
  const volSignal = d.vol_signal;
  
  const analytics = d.analytics_summary || {};
  
  container.innerHTML = `
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--space-md);margin-bottom:var(--space-md);">
      <div>
        <span class="stat-label" style="display:block;margin-bottom:4px;">EGARCH Forecast</span>
        <span class="num-highlight" style="font-size:1.3rem;">${forecastVol ? `${(forecastVol * 100).toFixed(2)}%` : '--'}</span>
      </div>
      <div>
        <span class="stat-label" style="display:block;margin-bottom:4px;">Implied Volatility</span>
        <span class="num-highlight" style="font-size:1.3rem;">${iv ? `${(iv * 100).toFixed(2)}%` : '--'}</span>
      </div>
    </div>
    ${volSpread !== null && volSpread !== undefined ? `
    <div class="divider"></div>
    <div class="stat-row">
      <span class="stat-label">Vol Spread (IV − EGARCH)</span>
      <span class="stat-value ${volSpread > 0 ? 'text-bearish' : 'text-bullish'}">${volSpread > 0 ? '+' : ''}${(volSpread * 100).toFixed(2)}%</span>
    </div>
    ` : ''}
    ${volSignal ? `
    <div class="stat-row">
      <span class="stat-label">Vol Signal</span>
      <span class="stat-value text-accent">${volSignal}</span>
    </div>
    ` : ''}
    ${analytics.vol_percentile_rank !== undefined ? `
    <div class="stat-row">
      <span class="stat-label">Volatility Percentile</span>
      <span class="stat-value">${formatPercent(analytics.vol_percentile_rank)}</span>
    </div>
    ` : ''}
    ${analytics.volatility_interpretation ? `
    <div class="divider"></div>
    <div style="font-size:0.78rem;color:var(--text-secondary);line-height:1.5;">
      ${analytics.volatility_interpretation}
    </div>
    ` : ''}
  `;
}

function renderMispricingCard(d) {
  const container = document.getElementById('mispricing-content');
  const m = d.mispricing || {};
  
  container.innerHTML = `
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:var(--space-md);margin-bottom:var(--space-md);">
      <div>
        <span class="stat-label" style="display:block;margin-bottom:4px;">Fair Price</span>
        <span class="num-highlight" style="font-size:1.1rem;">${formatPrice(d.fair_price)}</span>
      </div>
      <div>
        <span class="stat-label" style="display:block;margin-bottom:4px;">Market Price</span>
        <span class="num-highlight" style="font-size:1.1rem;">${formatPrice(d.market_price)}</span>
      </div>
      <div>
        <span class="stat-label" style="display:block;margin-bottom:4px;">Deviation</span>
        <span class="num-highlight ${(m.deviation_pct ?? m.deviation) > 0 ? 'text-bearish' : (m.deviation_pct ?? m.deviation) < 0 ? 'text-bullish' : ''}" style="font-size:1.1rem;">
          ${(m.deviation_pct ?? m.deviation) !== undefined ? `${(m.deviation_pct ?? m.deviation) > 0 ? '+' : ''}${formatPercent((m.deviation_pct ?? m.deviation) * (m.deviation !== undefined && m.deviation_pct === undefined ? 100 : 1))}` : '--'}
        </span>
      </div>
    </div>
    <div class="divider"></div>
    <div class="stat-row">
      <span class="stat-label">Signal Classification</span>
      <span class="signal-badge ${getSignalBadgeClass(m.signal || m.classification)}">${m.signal || m.classification || '--'}</span>
    </div>
    ${m.z_score !== undefined ? `
    <div class="stat-row">
      <span class="stat-label">Z-Score</span>
      <span class="stat-value">${formatNumber(m.z_score, 3)}</span>
    </div>
    ` : ''}
    ${m.threshold !== undefined ? `
    <div class="stat-row">
      <span class="stat-label">Detection Threshold</span>
      <span class="stat-value">±${formatPercent(m.threshold)}</span>
    </div>
    ` : ''}
    ${d.analytics_summary?.mispricing_interpretation ? `
    <div class="divider"></div>
    <div style="font-size:0.78rem;color:var(--text-secondary);line-height:1.5;">
      ${d.analytics_summary.mispricing_interpretation}
    </div>
    ` : ''}
  `;
}

function renderRegimeCard(d) {
  const container = document.getElementById('regime-content');
  const regime = d.regime || '--';
  const regimeDetail = d.regime_detail || {};
  const analytics = d.analytics_summary || {};
  
  container.innerHTML = `
    <div style="text-align:center;margin-bottom:var(--space-md);">
      <span style="font-size:2.5rem;">${getRegimeEmoji(regime)}</span>
      <div style="margin-top:var(--space-sm);">
        <span class="regime-badge ${getRegimeBadgeClass(regime)}" style="font-size:0.85rem;padding:6px 20px;">${regime}</span>
      </div>
    </div>
    <div class="divider"></div>
    ${regimeDetail.description ? `
    <div style="font-size:0.82rem;color:var(--text-secondary);line-height:1.5;margin-bottom:var(--space-md);">
      ${regimeDetail.description}
    </div>
    ` : ''}
    <div class="stat-row">
      <span class="stat-label">EGARCH Vol</span>
      <span class="stat-value">${d.forecast_volatility ? `${(d.forecast_volatility * 100).toFixed(2)}%` : '--'}</span>
    </div>
    ${regimeDetail.vol_lower_bound !== undefined ? `
    <div class="stat-row">
      <span class="stat-label">Regime Bounds</span>
      <span class="stat-value">${formatPercent(regimeDetail.vol_lower_bound * 100, 1)} — ${formatPercent(regimeDetail.vol_upper_bound * 100, 1)}</span>
    </div>
    ` : ''}
    ${analytics.regime_interpretation ? `
    <div class="divider"></div>
    <div style="font-size:0.78rem;color:var(--text-secondary);line-height:1.5;">
      ${analytics.regime_interpretation}
    </div>
    ` : ''}
  `;
}

function renderModelInfoCard(d) {
  const container = document.getElementById('model-info-content');
  const info = d.model_info || {};
  
  const rows = [];
  if (info.vol_model) rows.push(['Volatility Model', info.vol_model]);
  if (info.pricing_model) rows.push(['Pricing Model', info.pricing_model]);
  if (info.risk_free_rate !== undefined) rows.push(['Risk-Free Rate', formatPercent(info.risk_free_rate * 100)]);
  if (info.expiry) rows.push(['Expiry Used', info.expiry]);
  if (info.time_to_expiry_years !== undefined) rows.push(['Time to Expiry', `${info.time_to_expiry_years.toFixed(4)} years`]);
  if (info.option_type) rows.push(['Option Type', info.option_type.toUpperCase()]);
  if (info.strike) rows.push(['Strike', formatPrice(info.strike)]);
  if (info.data_points) rows.push(['Data Points', info.data_points.toLocaleString()]);
  
  if (d.selected_expiry) rows.push(['Selected Expiry', d.selected_expiry]);
  
  if (rows.length === 0) {
    container.innerHTML = `<div class="error-state" style="padding:var(--space-md);"><span class="error-icon">⚙️</span><p class="error-message">Model info not available</p></div>`;
    return;
  }
  
  container.innerHTML = rows.map(([label, value]) => `
    <div class="stat-row">
      <span class="stat-label">${label}</span>
      <span class="stat-value">${value}</span>
    </div>
  `).join('');
}

function renderHealthCard(d) {
  const container = document.getElementById('health-content');
  const health = d.pipeline_health || {};
  
  const checks = [];
  Object.entries(health).forEach(([key, val]) => {
    const label = key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
    let statusIcon = '⚪';
    let statusClass = '';
    
    if (val === true || val === 'OK' || val === 'PASS') {
      statusIcon = '✅';
      statusClass = 'text-bullish';
    } else if (val === false || val === 'FAIL') {
      statusIcon = '❌';
      statusClass = 'text-bearish';
    } else if (typeof val === 'string' && val.includes('WARNING')) {
      statusIcon = '⚠️';
      statusClass = 'text-warning';
    }
    
    checks.push({ label, val, statusIcon, statusClass });
  });
  
  if (checks.length === 0) {
    container.innerHTML = `
      <div style="text-align:center;padding:var(--space-md);">
        <span style="font-size:2rem;">✅</span>
        <p style="margin-top:var(--space-sm);color:var(--text-secondary);font-size:0.82rem;">All systems operational</p>
      </div>
    `;
    return;
  }
  
  container.innerHTML = checks.map(c => `
    <div class="stat-row">
      <span class="stat-label">${c.statusIcon} ${c.label}</span>
      <span class="stat-value ${c.statusClass}">${typeof c.val === 'boolean' ? (c.val ? 'PASS' : 'FAIL') : c.val}</span>
    </div>
  `).join('');
}

// ========== OPTION CHAIN ==========
async function loadExpiries() {
  try {
    const data = await apiCall('/expiries');
    if (data.status === 'success' && data.data) {
      const select = document.getElementById('expiry-select');
      const expiries = data.data.expiries || data.data.available_expiries || [];
      
      select.innerHTML = expiries.map((exp, i) => 
        `<option value="${exp}" ${i === 0 ? 'selected' : ''}>${exp}</option>`
      ).join('');
      
      if (expiries.length > 0) {
        loadOptionChain(expiries[0]);
      }
    }
  } catch (e) {
    console.error('Expiries load error:', e);
    document.getElementById('expiry-select').innerHTML = '<option value="">Error loading</option>';
  }
}

async function loadOptionChain(expiry) {
  const depth = document.getElementById('depth-select')?.value || 20;
  const container = document.getElementById('option-chain-content');
  
  container.innerHTML = `
    <div style="text-align:center;padding:var(--space-2xl);">
      <div class="loading-spinner" style="margin:0 auto;"></div>
      <p style="margin-top:var(--space-md);color:var(--text-muted);font-size:0.82rem;">Loading option chain…</p>
    </div>
  `;
  
  try {
    const params = { depth };
    if (expiry) params.expiry = expiry;
    
    const data = await apiCall('/option-chain', params);
    renderOptionChain(data, container);
  } catch (e) {
    console.error('Option chain error:', e);
    container.innerHTML = `
      <div class="error-state">
        <span class="error-icon">📋</span>
        <p class="error-message">Failed to load option chain: ${e.message}</p>
        <button class="btn btn-sm btn-outline" onclick="loadOptionChain('${expiry}')">Retry</button>
      </div>
    `;
  }
}

function renderOptionChain(data, container) {
  // Handle different response formats
  let chain = [];
  let spotPrice = null;
  let pcr = null;
  
  if (data.status === 'success' && data.data) {
    chain = data.data.chain || [];
    spotPrice = data.data.spot_price;
    pcr = data.data.pcr;
  } else if (data.chain) {
    chain = data.chain;
    spotPrice = data.spot_price;
    pcr = data.pcr;
  } else if (Array.isArray(data)) {
    chain = data;
  }
  
  if (chain.length === 0) {
    container.innerHTML = `
      <div class="error-state">
        <span class="error-icon">📋</span>
        <p class="error-message">No option chain data available</p>
      </div>
    `;
    return;
  }
  
  // Find ATM strike
  const atmStrike = spotPrice ? Math.round(spotPrice / 50) * 50 : null;
  
  let html = `
    ${spotPrice || pcr ? `
      <div style="display:flex;gap:var(--space-lg);margin-bottom:var(--space-md);flex-wrap:wrap;">
        ${spotPrice ? `<div><span class="stat-label">Spot: </span><span class="num-highlight">${formatPrice(spotPrice)}</span></div>` : ''}
        ${pcr ? `<div><span class="stat-label">PCR: </span><span class="num-highlight">${formatNumber(pcr, 2)}</span></div>` : ''}
      </div>
    ` : ''}
    <div class="data-table-container">
      <table class="option-chain-table">
        <thead>
          <tr>
            <th colspan="5" style="text-align:center;background:var(--color-bullish-bg);color:var(--color-bullish);border-bottom:2px solid var(--color-bullish);">CALLS</th>
            <th style="text-align:center;background:var(--bg-input);">STRIKE</th>
            <th colspan="5" style="text-align:center;background:var(--color-bearish-bg);color:var(--color-bearish);border-bottom:2px solid var(--color-bearish);">PUTS</th>
          </tr>
          <tr>
            <th>OI</th><th>Vol</th><th>IV</th><th>LTP</th><th>Bid/Ask</th>
            <th style="text-align:center;">K</th>
            <th>Bid/Ask</th><th>LTP</th><th>IV</th><th>Vol</th><th>OI</th>
          </tr>
        </thead>
        <tbody>
  `;
  
  chain.forEach(row => {
    const strike = row.strike;
    const isATM = atmStrike && Math.abs(strike - atmStrike) < 50;
    const rowClass = isATM ? 'atm-row' : '';
    
    const call = row.call || {};
    const put = row.put || {};
    
    html += `
      <tr class="${rowClass}">
        <td class="call-side">${call.oi ? call.oi.toLocaleString() : '--'}</td>
        <td class="call-side">${call.volume ? call.volume.toLocaleString() : '--'}</td>
        <td class="call-side">${call.iv ? formatPercent(call.iv * 100, 1) : '--'}</td>
        <td class="call-side" style="font-weight:700;">${call.ltp ? formatNumber(call.ltp) : '--'}</td>
        <td class="call-side" style="font-size:0.7rem;color:var(--text-muted);">${call.bid && call.ask ? `${formatNumber(call.bid,1)}/${formatNumber(call.ask,1)}` : '--'}</td>
        <td class="strike-col">${strike}</td>
        <td class="put-side" style="font-size:0.7rem;color:var(--text-muted);">${put.bid && put.ask ? `${formatNumber(put.bid,1)}/${formatNumber(put.ask,1)}` : '--'}</td>
        <td class="put-side" style="font-weight:700;">${put.ltp ? formatNumber(put.ltp) : '--'}</td>
        <td class="put-side">${put.iv ? formatPercent(put.iv * 100, 1) : '--'}</td>
        <td class="put-side">${put.volume ? put.volume.toLocaleString() : '--'}</td>
        <td class="put-side">${put.oi ? put.oi.toLocaleString() : '--'}</td>
      </tr>
    `;
  });
  
  html += '</tbody></table></div>';
  container.innerHTML = html;
}

// ========== BACKTEST ==========
async function runBacktest() {
  const container = document.getElementById('backtest-content');
  container.innerHTML = `
    <div style="text-align:center;padding:var(--space-2xl);">
      <div class="loading-spinner" style="margin:0 auto;"></div>
      <p style="margin-top:var(--space-md);color:var(--text-muted);font-size:0.82rem;">Running walk-forward backtest… This may take a moment.</p>
    </div>
  `;
  
  try {
    const data = await apiCall('/backtest', { timeframe: '1d' });
    
    if (data.status === 'success' && data.data) {
      renderBacktest(data.data);
      showToast('Backtest completed successfully', 'success');
    } else {
      throw new Error(data.error || 'Unknown error');
    }
  } catch (e) {
    console.error('Backtest error:', e);
    container.innerHTML = `
      <div class="error-state">
        <span class="error-icon">⚠️</span>
        <p class="error-message">Backtest failed: ${e.message}</p>
        <button class="btn btn-sm btn-outline" onclick="runBacktest()">Retry</button>
      </div>
    `;
    showToast(`Backtest error: ${e.message}`, 'error');
  }
}

function renderBacktest(d) {
  const container = document.getElementById('backtest-content');
  
  const metrics = [
    ['Sharpe Ratio', d.sharpe_ratio !== undefined ? formatNumber(d.sharpe_ratio, 3) : '--', d.sharpe_ratio > 1 ? 'text-bullish' : d.sharpe_ratio > 0 ? 'text-info' : 'text-bearish'],
    ['Hit Rate', d.hit_rate !== undefined ? formatPercent(d.hit_rate * 100) : '--', d.hit_rate > 0.55 ? 'text-bullish' : 'text-warning'],
    ['Total Trades', d.total_trades || d.n_trades || '--', ''],
    ['T-Statistic', d.t_statistic !== undefined ? formatNumber(d.t_statistic, 3) : '--', Math.abs(d.t_statistic) > 1.96 ? 'text-bullish' : 'text-warning'],
    ['Mean Return', d.mean_return !== undefined ? formatPercent(d.mean_return * 100, 4) : '--', d.mean_return > 0 ? 'text-bullish' : 'text-bearish'],
    ['Std Dev', d.std_return !== undefined ? formatPercent(d.std_return * 100, 4) : '--', ''],
    ['Max Drawdown', d.max_drawdown !== undefined ? formatPercent(d.max_drawdown * 100) : '--', 'text-bearish'],
    ['Win/Loss Ratio', d.win_loss_ratio !== undefined ? formatNumber(d.win_loss_ratio, 2) : '--', d.win_loss_ratio > 1 ? 'text-bullish' : 'text-bearish'],
  ];
  
  container.innerHTML = `
    <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(180px, 1fr));gap:var(--space-md);">
      ${metrics.map(([label, value, colorClass]) => `
        <div style="padding:var(--space-md);background:var(--bg-input);border-radius:var(--radius-md);border:1px solid var(--border-primary);">
          <div style="font-size:0.7rem;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;color:var(--text-muted);margin-bottom:4px;">${label}</div>
          <div class="num-highlight ${colorClass}" style="font-size:1.1rem;">${value}</div>
        </div>
      `).join('')}
    </div>
    ${d.statistical_significance ? `
    <div style="margin-top:var(--space-md);padding:var(--space-sm) var(--space-md);background:var(--color-bullish-bg);border:1px solid rgba(16,185,129,0.3);border-radius:var(--radius-md);font-size:0.82rem;">
      ✅ <strong>Statistically Significant</strong> — The trading signal demonstrates statistically significant alpha (t-stat > 1.96).
    </div>
    ` : d.t_statistic !== undefined && Math.abs(d.t_statistic) < 1.96 ? `
    <div style="margin-top:var(--space-md);padding:var(--space-sm) var(--space-md);background:var(--color-warning-bg);border:1px solid rgba(245,158,11,0.3);border-radius:var(--radius-md);font-size:0.82rem;">
      ⚠️ <strong>Not Statistically Significant</strong> — t-stat below 1.96 threshold. Requires larger sample.
    </div>
    ` : ''}
  `;
}

// ========== REFRESH ALL ==========
async function refreshAll() {
  if (isRefreshing) return;
  isRefreshing = true;
  
  const btn = document.getElementById('btn-refresh');
  btn.classList.add('spinning');
  
  try {
    await Promise.all([
      loadStrategy(),
      loadExpiries(),
    ]);
    showToast('Dashboard refreshed', 'success', 2000);
  } catch (e) {
    showToast(`Refresh error: ${e.message}`, 'error');
  } finally {
    isRefreshing = false;
    btn.classList.remove('spinning');
  }
}

// ========== INITIALIZATION ==========
async function init() {
  // Check API health first
  const healthOk = await checkHealth();
  
  if (healthOk) {
    showToast('Connected to QuantLens backend', 'success', 2500);
    await refreshAll();
  } else {
    showToast('Backend not reachable. Start the server: python main.py', 'error', 8000);
    
    // Show offline state in KPIs
    document.querySelectorAll('.kpi-value').forEach(el => {
      if (el.querySelector('.skeleton')) {
        el.innerHTML = '<span style="color:var(--text-muted);">--</span>';
      }
    });
    
    // Update pipeline badge
    document.getElementById('pipeline-status-badge').textContent = 'OFFLINE';
    document.getElementById('pipeline-status-badge').className = 'card-badge bg-bearish';
  }
}

// Start
document.addEventListener('DOMContentLoaded', init);

// Auto-refresh every 60 seconds
setInterval(() => {
  if (!document.hidden) {
    refreshAll();
  }
}, 60000);
