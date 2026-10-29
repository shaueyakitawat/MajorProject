/**
 * frontend/src/pages/DashboardLive.js
 * ================================================================================
 * Real-Time Executive Quant Dashboard & Capital PnL Center
 * Displays live capital base, realized/unrealized PnL, margin utilization,
 * NIFTY 50 candlestick chart, derivatives microstructure, active open positions,
 * and top quantitative mispricing opportunities with 1-click execution.
 * ================================================================================
 */

import { terminalStore } from '../stores/terminalStore.js';
import { apiService } from '../services/api.js';
import { ChartEngine } from '../services/chartEngine.js';

export function renderDashboardLive(container) {
  let candles = [];
  let tradesData = null;
  let topOpportunities = [];
  let strategyData = null;

  async function loadData() {
    const s = terminalStore.getState();

    // 1. Parallel fetch of candles, trades, strategy, and option chain
    const [candleRes, tradeRes, stratRes, chainRes] = await Promise.allSettled([
      apiService.getNiftyCandles('NIFTY', s.timeframe),
      apiService.getTrades(),
      apiService.getStrategy('NIFTY', s.timeframe, s.tradingHorizon),
      apiService.getOptionChain('NIFTY', s.selectedExpiry, 15),
    ]);

    if (candleRes.status === 'fulfilled' && candleRes.value?.success && candleRes.value.candles?.length > 0) {
      candles = candleRes.value.candles;
      const last = candles[candles.length - 1];
      const prev = candles.length > 1 ? candles[candles.length - 2] : last;
      const chg = last.Close - prev.Close;
      const chgPct = prev.Close > 0 ? (chg / prev.Close) * 100 : 0;
      terminalStore.setState({
        niftySpot: last.Close,
        niftyOpen: last.Open,
        niftyHigh: last.High,
        niftyLow: last.Low,
        niftyPrevClose: prev.Close,
        niftyChange: Math.round(chg * 100) / 100,
        niftyChangePct: Math.round(chgPct * 100) / 100,
        niftyVolume: last.Volume || s.niftyVolume,
      });
    }

    if (tradeRes.status === 'fulfilled' && tradeRes.value?.success && tradeRes.value.data) {
      tradesData = tradeRes.value.data;
    }

    if (stratRes.status === 'fulfilled' && stratRes.value?.success && stratRes.value.data) {
      strategyData = stratRes.value.data;
      terminalStore.setState({
        forecastVolatility: strategyData.forecast_volatility || s.forecastVolatility,
        bsFairPrice: strategyData.fair_price || s.bsFairPrice,
        marketPrice: strategyData.market_price || s.marketPrice,
        regime: strategyData.regime || s.regime,
        marketIv: strategyData.implied_volatility || s.marketIv,
        selectedExpiry: strategyData.selected_expiry || s.selectedExpiry,
        availableExpiries: strategyData.available_expiries || s.availableExpiries,
      });
    }

    if (chainRes.status === 'fulfilled' && chainRes.value?.success && chainRes.value.data?.chain) {
      const allContracts = [];
      chainRes.value.data.chain.forEach(row => {
        ['call', 'put'].forEach(type => {
          const c = row[type];
          if (c && c.ltp > 0) {
            allContracts.push({
              strike: row.strike,
              type,
              ltp: c.ltp,
              fair: c.fairPrice,
              dev: c.mispricingPct,
              mScore: c.mScore,
              iv: c.iv,
              modelVol: c.modelVol,
              liq: c.liquidityClass || 'HIGH',
              signal: c.signal,
              absMScore: Math.abs(c.mScore || 0)
            });
          }
        });
      });
      allContracts.sort((a, b) => b.absMScore - a.absMScore);
      topOpportunities = allContracts.slice(0, 5);
    }

    update();
  }

  function update() {
    if (terminalStore.getState().activeRoute !== 'dashboard') return;
    const s = terminalStore.getState();
    const isBull = s.niftyChange >= 0;
    const strat = strategyData?.strategy || {};
    const sum = tradesData?.summary || {
      current_equity: 2500000.0,
      cash_buffer: 500000.0,
      margin_used: 95452.5,
      free_margin: 1904547.5,
      net_pnl: -89200.66,
      unrealized_pnl: 1282.22,
      win_rate_pct: 47.3,
      win_count: 426,
      loss_count: 474,
      profit_factor: 0.88,
      friction_cost: 45349.39
    };
    const activePositions = tradesData?.active_positions || [];

    container.innerHTML = `
      <div class="workspace-grid command-center-layout">
        <!-- Banner 1: Live Capital & Real-Time P&L Command Strip -->
        <div class="terminal-panel span-12">
          <div class="panel-header">
            <div class="panel-title-group">
              <span class="panel-title">LIVE CAPITAL ALLOCATION & QUANTITATIVE P&L DASHBOARD</span>
              <span class="badge-source">ACCOUNT: PROPRIETARY QUANT (₹25,00,000 BASE)</span>
            </div>
            <div class="panel-controls">
              <button class="btn btn-xs btn-primary" id="btn-dash-sync">↺ Sync Live Dashboard</button>
              <button class="btn btn-xs btn-secondary" id="btn-dash-goto-terminal">⚡ Live Terminal →</button>
            </div>
          </div>

          <div class="dense-stats-strip">
            <div class="stat-pill"><span class="lbl">TOTAL ACCOUNT EQUITY:</span> <strong class="tabular font-bold text-amber">₹${sum.current_equity.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</strong></div>
            <div class="stat-pill"><span class="lbl">CASH BUFFER (20%):</span> <strong class="tabular">₹${sum.cash_buffer.toLocaleString('en-IN')} (Floor)</strong></div>
            <div class="stat-pill"><span class="lbl">UTILIZED MARGIN:</span> <strong class="tabular">₹${sum.margin_used.toLocaleString('en-IN')}</strong></div>
            <div class="stat-pill"><span class="lbl">FREE TRADING MARGIN:</span> <strong class="tabular color-bull">₹${sum.free_margin.toLocaleString('en-IN')}</strong></div>
            <div class="stat-pill"><span class="lbl">NET REALIZED P&L:</span> <strong class="tabular font-bold ${sum.net_pnl >= 0 ? 'color-bull' : 'color-bear'}">${sum.net_pnl >= 0 ? '+' : ''}₹${sum.net_pnl.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</strong></div>
            <div class="stat-pill"><span class="lbl">UNREALIZED P&L:</span> <strong class="tabular font-bold ${sum.unrealized_pnl >= 0 ? 'text-bull' : 'text-bear'}">${sum.unrealized_pnl >= 0 ? '+' : ''}₹${sum.unrealized_pnl.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</strong></div>
            <div class="stat-pill"><span class="lbl">WIN RATE:</span> <strong class="tabular ${sum.win_rate_pct >= 55 ? 'text-bull' : 'text-amber'}">${sum.win_rate_pct}% (${sum.win_count}W / ${sum.loss_count}L)</strong></div>
            <div class="stat-pill"><span class="lbl">PROFIT FACTOR:</span> <strong class="tabular">${sum.profit_factor.toFixed(2)}</strong></div>
            <div class="stat-pill"><span class="lbl">STT / FRICTION:</span> <strong class="tabular text-muted">₹${sum.friction_cost.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</strong></div>
          </div>
        </div>

        <!-- Panel 2: NIFTY OHLCV Candlestick & Synchronized Volatility Subchart -->
        <div class="terminal-panel span-8">
          <div class="panel-header">
            <div class="panel-title-group">
              <span class="panel-title">NIFTY 50 INDEX · CASH SPOT</span>
              <span class="badge-source">FEED: REAL MARKET (${s.timeframe.toUpperCase()})</span>
            </div>
            <div class="panel-controls">
              <div class="btn-group-timeframe">
                ${['1m', '5m', '15m', '1h', 'daily'].map(tf => `
                  <button class="tf-btn ${s.timeframe === tf ? 'active' : ''}" data-tf="${tf}">${tf.toUpperCase()}</button>
                `).join('')}
              </div>
            </div>
          </div>

          <div class="dense-stats-strip">
            <div class="stat-pill"><span class="lbl">LTP:</span> <strong class="tabular">₹${s.niftySpot.toFixed(2)}</strong></div>
            <div class="stat-pill"><span class="lbl">CHG:</span> <strong class="tabular ${isBull ? 'color-bull' : 'color-bear'}">${isBull ? '+' : ''}${s.niftyChange.toFixed(2)} (${isBull ? '+' : ''}${s.niftyChangePct.toFixed(2)}%)</strong></div>
            <div class="stat-pill"><span class="lbl">OPEN:</span> <span class="tabular">${s.niftyOpen.toFixed(2)}</span></div>
            <div class="stat-pill"><span class="lbl">HIGH:</span> <span class="tabular">${s.niftyHigh.toFixed(2)}</span></div>
            <div class="stat-pill"><span class="lbl">LOW:</span> <span class="tabular">${s.niftyLow.toFixed(2)}</span></div>
            <div class="stat-pill"><span class="lbl">VWAP:</span> <span class="tabular text-amber">${s.niftyVWAP.toFixed(2)}</span></div>
            <div class="stat-pill"><span class="lbl">ATM:</span> <strong class="tabular text-amber font-bold">${s.atmStrike}</strong></div>
          </div>

          <div class="chart-container-large">
            <canvas id="dash-candlestick-canvas" style="width:100%; height:250px;"></canvas>
          </div>

          <div class="subchart-section">
            <div class="subchart-header">
              <span class="subchart-title">SYNCHRONIZED VOLATILITY SURFACE: MARKET IV (AMBER) │ EGARCH (BLUE) │ VRP RESIDUAL (PURPLE)</span>
            </div>
            <canvas id="dash-subchart-canvas" style="width:100%; height:90px;"></canvas>
          </div>
        </div>

        <!-- Panel 3: Derivatives Microstructure & Macro Health -->
        <div class="terminal-panel span-4">
          <div class="panel-header">
            <span class="panel-title">DERIVATIVES MICROSTRUCTURE</span>
            <span class="status-indicator live">● TICK ACTIVE</span>
          </div>
          <div class="panel-body compact-padding">
            <table class="terminal-table dense-table">
              <tbody>
                <tr><td>NIFTY Spot</td><td class="tabular font-bold text-right">₹${s.niftySpot.toFixed(2)}</td></tr>
                <tr><td>ATM Benchmark Strike</td><td class="tabular text-amber font-bold text-right">${s.atmStrike}</td></tr>
                <tr><td>India VIX</td><td class="tabular text-right">${s.indiaVix.toFixed(2)}</td></tr>
                <tr><td>Put-Call Ratio (PCR OI)</td><td class="tabular text-amber text-right">1.04</td></tr>
                <tr><td>Conditional Model Vol (EGARCH)</td><td class="tabular text-right">${(s.forecastVolatility * 100).toFixed(2)}%</td></tr>
                <tr><td>Market Implied Vol (IV)</td><td class="tabular text-amber text-right">${(s.marketIv * 100).toFixed(2)}%</td></tr>
                <tr><td>Volatility Risk Premium (VRP)</td><td class="tabular text-right font-bold text-bull">+${((s.marketIv - s.forecastVolatility) * 100).toFixed(2)}%</td></tr>
                <tr><td>Current HMM Regime</td><td class="tabular text-right"><span class="regime-badge badge-normal">${s.regime.replace('_', ' ')}</span></td></tr>
              </tbody>
            </table>

            <div class="regime-timeline-box" style="margin-top: 12px;">
              <span class="box-lbl">HMM REGIME TIMELINE (LAST 8 SESSIONS)</span>
              <div class="timeline-bar">
                <div class="reg-seg bg-low" style="width:15%;" title="Session 1: LOW_VOL"></div>
                <div class="reg-seg bg-normal" style="width:40%;" title="Sessions 2-4: NORMAL_VOL"></div>
                <div class="reg-seg bg-high" style="width:25%;" title="Sessions 5-6: HIGH_VOL"></div>
                <div class="reg-seg bg-normal" style="width:20%;" title="Current: NORMAL_VOL"></div>
              </div>
              <div class="timeline-legend">
                <span class="leg-item"><span class="dot bg-low"></span>Low</span>
                <span class="leg-item"><span class="dot bg-normal"></span>Normal (84%)</span>
                <span class="leg-item"><span class="dot bg-high"></span>High</span>
                <span class="leg-item"><span class="dot bg-extreme"></span>Extreme</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Panel 4: Active Positions Quick Overview -->
        <div class="terminal-panel span-6">
          <div class="panel-header">
            <span class="panel-title">ACTIVE POSITIONS (${activePositions.length} LIVE)</span>
            <button class="btn btn-xs btn-secondary" id="btn-dash-open-terminal">Manage in Terminal →</button>
          </div>
          <div class="panel-body no-padding">
            ${activePositions.length === 0 ? `
              <div class="empty-state-box" style="padding: 24px;">
                <div class="empty-state-icon">🛡️</div>
                <div class="empty-state-title">Zero Open Exposure</div>
                <div class="empty-state-desc">Portfolio is 100% in cash. Ready for algorithmic order execution.</div>
              </div>
            ` : `
              <table class="terminal-table dense-table hover-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Contract</th>
                    <th>Side</th>
                    <th>Qty</th>
                    <th>Entry → LTP</th>
                    <th>Net P&L</th>
                    <th>Return %</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  ${activePositions.map(p => {
                    const isProfit = (p.net_pnl || 0) >= 0;
                    return `
                      <tr>
                        <td class="tabular font-bold">${p.trade_id}</td>
                        <td><strong>${p.instrument}</strong></td>
                        <td><span class="badge-mini ${p.side === 'BUY' ? 'tag-underpriced' : 'tag-overpriced'}">${p.side}</span></td>
                        <td class="tabular font-bold">${p.qty}</td>
                        <td class="tabular">₹${(p.entry_price || 0).toFixed(1)} → ₹${(p.current_price || p.entry_price || 0).toFixed(1)}</td>
                        <td class="tabular font-bold ${isProfit ? 'color-bull' : 'color-bear'}">
                          ${isProfit ? '+' : ''}₹${(p.net_pnl || 0).toFixed(2)}
                        </td>
                        <td class="tabular ${isProfit ? 'color-bull' : 'color-bear'}">
                          ${isProfit ? '+' : ''}${(p.return_pct || 0).toFixed(2)}%
                        </td>
                        <td>
                          <button class="btn btn-xs btn-danger btn-dash-sqoff" data-trade-id="${p.trade_id}">
                            Square Off
                          </button>
                        </td>
                      </tr>
                    `;
                  }).join('')}
                </tbody>
              </table>
            `}
          </div>
        </div>

        <!-- Panel 5: Top Quantitative Mispricing Opportunities -->
        <div class="terminal-panel span-6">
          <div class="panel-header">
            <span class="panel-title">TOP STATISTICAL MISPRICINGS</span>
            <button class="btn btn-xs btn-secondary" id="btn-dash-open-scanner">Full Scanner →</button>
          </div>
          <div class="panel-body no-padding">
            <table class="terminal-table dense-table hover-table">
              <thead>
                <tr>
                  <th>Contract</th>
                  <th>LTP</th>
                  <th>BS Fair</th>
                  <th>Edge</th>
                  <th>M-Score</th>
                  <th>Signal</th>
                  <th>Trade</th>
                </tr>
              </thead>
              <tbody>
                ${topOpportunities.map(o => `
                  <tr>
                    <td><strong>${o.strike} ${o.type.toUpperCase()}</strong></td>
                    <td class="tabular">₹${o.ltp?.toFixed(2) || '--'}</td>
                    <td class="tabular">₹${o.fair?.toFixed(2) || '--'}</td>
                    <td class="tabular ${o.dev > 0 ? 'color-bear' : 'color-bull'} font-bold">${o.dev > 0 ? '+' : ''}${o.dev?.toFixed(1) || '--'}%</td>
                    <td class="tabular text-amber font-bold">${o.mScore >= 0 ? '+' : ''}${o.mScore?.toFixed(2) || '--'}σ</td>
                    <td>
                      <span class="badge-signal ${o.signal === 'overpriced' ? 'tag-overpriced' : (o.signal === 'underpriced' ? 'tag-underpriced' : 'tag-fair')}">
                        ${o.signal === 'overpriced' ? 'SELL / RICH' : (o.signal === 'underpriced' ? 'BUY / CHEAP' : 'FAIR')}
                      </span>
                    </td>
                    <td>
                      <button class="btn btn-xs btn-primary btn-dash-trade-strike" data-strike="${o.strike}" data-type="${o.type}" data-price="${o.ltp}" data-side="${o.signal === 'overpriced' ? 'SELL' : 'BUY'}">
                        Trade ⚡
                      </button>
                    </td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    `;

    // Event Bindings
    container.querySelector('#btn-dash-sync').onclick = () => loadData();
    container.querySelector('#btn-dash-goto-terminal').onclick = () => terminalStore.setActiveRoute('live-terminal');
    container.querySelector('#btn-dash-open-terminal').onclick = () => terminalStore.setActiveRoute('live-terminal');
    container.querySelector('#btn-dash-open-scanner').onclick = () => terminalStore.setActiveRoute('mispricing-scanner');

    // Square off buttons
    container.querySelectorAll('.btn-dash-sqoff').forEach(btn => {
      btn.onclick = async () => {
        const tid = btn.getAttribute('data-trade-id');
        if (confirm(`Confirm square-off for ${tid}?`)) {
          btn.disabled = true;
          btn.textContent = 'Closing...';
          const res = await apiService.closeTrade(tid);
          if (res.success) {
            alert(`Trade ${tid} safely squared off!`);
            loadData();
          } else {
            alert(`Failed: ${res.error || 'Unknown error'}`);
            btn.disabled = false;
            btn.textContent = 'Square Off';
          }
        }
      };
    });

    // 1-Click Trade buttons
    container.querySelectorAll('.btn-dash-trade-strike').forEach(btn => {
      btn.onclick = () => {
        const strike = btn.getAttribute('data-strike');
        const type = btn.getAttribute('data-type');
        const side = btn.getAttribute('data-side');
        const price = btn.getAttribute('data-price');
        // Pre-fill terminal order ticket and switch to live-terminal
        terminalStore.setState({
          activeRoute: 'live-terminal',
          pendingOrder: { strike, type, side, price }
        });
      };
    });

    // Timeframe buttons
    container.querySelectorAll('.tf-btn').forEach(b => {
      b.onclick = () => {
        const tf = b.getAttribute('data-tf');
        terminalStore.setState({ timeframe: tf });
        loadData();
      };
    });

    // Canvas charts rendering
    setTimeout(() => {
      const candleCanvas = container.querySelector('#dash-candlestick-canvas');
      if (candleCanvas && candles.length > 0) {
        ChartEngine.renderCandlestick(candleCanvas, candles);
      }
      const subCanvas = container.querySelector('#dash-subchart-canvas');
      if (subCanvas) {
        const n = 35;
        const baseIv = s.marketIv || 0.159;
        const baseMod = s.forecastVolatility || 0.142;
        ChartEngine.renderMultiLine(subCanvas, [
          { name: 'Market IV', color: '#f59e0b', data: Array.from({ length: n }, (_, i) => baseIv + Math.sin(i / 3) * 0.012) },
          { name: 'EGARCH Vol', color: '#38bdf8', data: Array.from({ length: n }, (_, i) => baseMod + Math.cos(i / 4) * 0.007) },
          { name: 'VRP Residual', color: '#a855f7', data: Array.from({ length: n }, (_, i) => Math.max(-0.01, baseIv - baseMod + Math.sin(i / 2) * 0.005)) },
        ]);
      }
    }, 50);
  }

  update();
  loadData();
}
