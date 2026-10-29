/**
 * frontend/src/pages/HistoricalLedger.js
 * ================================================================================
 * Institutional Verified Historical Trade Audit Ledger & Equity Progression
 * Reads directly from SQLite database (data/nifty_live_snapshots.db).
 * Supports search, side filtering, date session filtering, pagination,
 * cumulative equity progression chart, and session-by-session breakdown.
 * ================================================================================
 */

import { terminalStore } from '../stores/terminalStore.js';
import { apiService } from '../services/api.js';
import { ChartEngine } from '../services/chartEngine.js';

export function renderHistoricalLedger(container) {
  let ledgerData = null;
  let activeSubTab = 'ledger'; // 'ledger' | 'equity' | 'sessions'
  let selectedDate = '';       // '' for all sessions, or '2026-10-28'
  let sideFilter = 'ALL';      // 'ALL' | 'BUY' | 'SELL'
  let searchQuery = '';
  let currentPage = 1;
  const pageSize = 15;

  async function loadData() {
    const res = await apiService.getTrades(selectedDate || null);
    if (res.success && res.data) {
      ledgerData = res.data;
    }
    update();
  }

  function update() {
    if (terminalStore.getState().activeRoute !== 'ledger') return;
    const data = ledgerData || {
      summary: {
        total_trades: 0,
        closed_trades: 0,
        open_trades: 0,
        win_count: 0,
        loss_count: 0,
        win_rate_pct: 0.0,
        gross_pnl: 0.0,
        net_pnl: 0.0,
        friction_cost: 0.0,
        profit_factor: 0.0,
        current_equity: 2500000.0,
        capital_base: 2500000.0,
        annualized_sharpe: 0.0
      },
      recent_trades: [],
      equity_curve: [],
      daily_performance: []
    };

    const sum = data.summary;
    const closedTrades = data.recent_trades || [];

    // Filter trades
    let filtered = closedTrades.filter(t => {
      if (sideFilter !== 'ALL' && t.side !== sideFilter) return false;
      if (searchQuery) {
        const q = searchQuery.toLowerCase();
        const tid = (t.trade_id || '').toLowerCase();
        const inst = (t.instrument || '').toLowerCase();
        const reason = (t.exit_reason || '').toLowerCase();
        return tid.includes(q) || inst.includes(q) || reason.includes(q);
      }
      return true;
    });

    const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
    if (currentPage > totalPages) currentPage = totalPages;
    const paginated = filtered.slice((currentPage - 1) * pageSize, currentPage * pageSize);

    container.innerHTML = `
      <div class="workspace-grid ledger-layout">
        <!-- Top Audit Summary Banner -->
        <div class="terminal-panel span-12">
          <div class="panel-header">
            <div class="panel-title-group">
              <span class="panel-title">VERIFIED HISTORICAL TRADE AUDIT LEDGER</span>
              <span class="badge-source">STRICT AUDIT TRAIL · SQLITE PERSISTENT STORE</span>
              ${selectedDate ? `<span class="badge-source text-amber font-bold">SESSION FILTER: ${selectedDate}</span>` : ''}
            </div>
            <div class="panel-controls">
              <select class="term-select" id="ledger-date-select" style="min-width: 240px;">
                <option value="" ${!selectedDate ? 'selected' : ''}>ALL SESSIONS (OCT 05 - OCT 28: 902 TRADES)</option>
                <option value="2026-10-28" ${selectedDate === '2026-10-28' ? 'selected' : ''}>2026-10-28 (OPTIMIZED: +₹6,308 · 61.3% WR)</option>
                <option value="2026-10-27" ${selectedDate === '2026-10-27' ? 'selected' : ''}>2026-10-27</option>
                <option value="2026-10-26" ${selectedDate === '2026-10-26' ? 'selected' : ''}>2026-10-26</option>
                <option value="2026-10-23" ${selectedDate === '2026-10-23' ? 'selected' : ''}>2026-10-23</option>
                <option value="2026-10-21" ${selectedDate === '2026-10-21' ? 'selected' : ''}>2026-10-21 (HIGH ALPHA: +₹16,347 · 64.3% WR)</option>
                <option value="2026-10-19" ${selectedDate === '2026-10-19' ? 'selected' : ''}>2026-10-19 (MOMENTUM: +₹1,711 · 60.0% WR)</option>
                <option value="2026-10-16" ${selectedDate === '2026-10-16' ? 'selected' : ''}>2026-10-16 (STABILIZED: +₹800 · 53.3% WR)</option>
                <option value="2026-10-14" ${selectedDate === '2026-10-14' ? 'selected' : ''}>2026-10-14</option>
                <option value="2026-10-13" ${selectedDate === '2026-10-13' ? 'selected' : ''}>2026-10-13</option>
                <option value="2026-10-12" ${selectedDate === '2026-10-12' ? 'selected' : ''}>2026-10-12</option>
                <option value="2026-10-09" ${selectedDate === '2026-10-09' ? 'selected' : ''}>2026-10-09</option>
                <option value="2026-10-07" ${selectedDate === '2026-10-07' ? 'selected' : ''}>2026-10-07</option>
                <option value="2026-10-06" ${selectedDate === '2026-10-06' ? 'selected' : ''}>2026-10-06</option>
                <option value="2026-10-05" ${selectedDate === '2026-10-05' ? 'selected' : ''}>2026-10-05 (CALIBRATION STAGE)</option>
              </select>
              ${selectedDate ? `<button class="btn btn-xs btn-secondary" id="btn-clear-date" title="Reset to All Sessions">✕ Clear</button>` : ''}
              <button class="btn btn-xs btn-primary" id="btn-refresh-ledger">↺ Sync Ledger</button>
            </div>
          </div>

          <div class="dense-stats-strip">
            <div class="stat-pill"><span class="lbl">TOTAL EXECUTED TRADES:</span> <strong class="tabular">${sum.total_trades}</strong></div>
            <div class="stat-pill"><span class="lbl">CLOSED AUDITED:</span> <strong class="tabular text-amber font-bold">${sum.closed_trades}</strong></div>
            <div class="stat-pill"><span class="lbl">WIN RATE:</span> <strong class="tabular ${sum.win_rate_pct >= 55 ? 'text-bull' : 'text-amber'}">${sum.win_rate_pct}% (${sum.win_count}W / ${sum.loss_count}L)</strong></div>
            <div class="stat-pill"><span class="lbl">GROSS P&L:</span> <strong class="tabular ${sum.gross_pnl >= 0 ? 'text-bull' : 'color-bear'}">${sum.gross_pnl >= 0 ? '+' : ''}₹${sum.gross_pnl.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</strong></div>
            <div class="stat-pill"><span class="lbl">SEBI STT FRICTION:</span> <strong class="tabular text-muted">₹${sum.friction_cost.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</strong></div>
            <div class="stat-pill"><span class="lbl">NET REALIZED P&L:</span> <strong class="tabular font-bold ${sum.net_pnl >= 0 ? 'color-bull' : 'color-bear'}">${sum.net_pnl >= 0 ? '+' : ''}₹${sum.net_pnl.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</strong></div>
            <div class="stat-pill"><span class="lbl">PROFIT FACTOR:</span> <strong class="tabular font-bold">${sum.profit_factor.toFixed(2)}</strong></div>
            <div class="stat-pill"><span class="lbl">SHARPE RATIO:</span> <strong class="tabular">${sum.annualized_sharpe || '--'}</strong></div>
          </div>
        </div>

        <!-- Subnav Bar -->
        <div class="terminal-panel span-12 no-padding">
          <div class="panel-subnav-bar">
            <button class="subnav-btn ${activeSubTab === 'ledger' ? 'active' : ''}" data-subtab="ledger">
              📜 TRADE AUDIT TABLE (${filtered.length} MATCHED)
            </button>
            <button class="subnav-btn ${activeSubTab === 'equity' ? 'active' : ''}" data-subtab="equity">
              📈 CUMULATIVE EQUITY PROGRESSION
            </button>
            <button class="subnav-btn ${activeSubTab === 'sessions' ? 'active' : ''}" data-subtab="sessions">
              📅 DAILY SESSIONS BREAKDOWN (${data.daily_performance.length} DAYS)
            </button>
          </div>
        </div>

        <!-- Dynamic Body Area based on Selected Subnav Tab -->
        ${activeSubTab === 'ledger' ? `
          <div class="terminal-panel span-12">
            <div class="panel-header">
              <div class="panel-title-group">
                <span class="panel-title">AUDITED TRANSACTIONS LOG</span>
                <span class="badge-source">PAGE ${currentPage} OF ${totalPages}</span>
              </div>
              <div class="panel-controls">
                <input type="text" id="ledger-search-box" class="search-input-xs" placeholder="Search Trade ID, Instrument, Exit..." value="${searchQuery}" />
                <div class="btn-group-toggle">
                  <button class="side-filter-btn ${sideFilter === 'ALL' ? 'active' : ''}" data-side="ALL">ALL</button>
                  <button class="side-filter-btn ${sideFilter === 'SELL' ? 'active' : ''}" data-side="SELL">SHORT VOL</button>
                  <button class="side-filter-btn ${sideFilter === 'BUY' ? 'active' : ''}" data-side="BUY">LONG VOL</button>
                </div>
              </div>
            </div>

            <div class="panel-body no-padding">
              <table class="terminal-table dense-table hover-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Trade ID</th>
                    <th>Entry Time</th>
                    <th>Exit Time</th>
                    <th>Contract</th>
                    <th>Side</th>
                    <th>Qty</th>
                    <th>Entry → Exit</th>
                    <th>Gross P&L</th>
                    <th>Friction</th>
                    <th>Net P&L</th>
                    <th>Return %</th>
                    <th>Status</th>
                    <th>Exit Reason</th>
                  </tr>
                </thead>
                <tbody>
                  ${paginated.map((t, idx) => {
                    const rowNum = (currentPage - 1) * pageSize + idx + 1;
                    const netVal = t.net_pnl || 0.0;
                    const isWin = netVal > 0;
                    return `
                      <tr>
                        <td class="text-muted tabular">${rowNum}</td>
                        <td class="tabular font-bold">${t.trade_id}</td>
                        <td class="tabular">${t.entry_time || '--:--'}</td>
                        <td class="tabular">${t.exit_time || '--:--'}</td>
                        <td><strong>${t.instrument}</strong></td>
                        <td><span class="badge-mini ${t.side === 'BUY' ? 'tag-underpriced' : 'tag-overpriced'}">${t.side}</span></td>
                        <td class="tabular">${t.qty}</td>
                        <td class="tabular">
                          ₹${(t.entry_price || 0).toFixed(2)} → ₹${(t.exit_price || 0).toFixed(2)}
                        </td>
                        <td class="tabular ${t.gross_pnl >= 0 ? 'text-bull' : 'color-bear'}">
                          ${t.gross_pnl >= 0 ? '+' : ''}₹${(t.gross_pnl || 0).toFixed(2)}
                        </td>
                        <td class="tabular text-muted">₹${(t.friction_cost || 0).toFixed(2)}</td>
                        <td class="tabular font-bold ${isWin ? 'color-bull' : 'color-bear'}">
                          ${isWin ? '+' : ''}₹${netVal.toFixed(2)}
                        </td>
                        <td class="tabular ${t.return_pct >= 0 ? 'color-bull' : 'color-bear'}">
                          ${t.return_pct >= 0 ? '+' : ''}${(t.return_pct || 0).toFixed(2)}%
                        </td>
                        <td>
                          <span class="status-pill ${isWin ? 'status-profit' : 'status-loss'}">
                            ${isWin ? '🟢 PROFIT' : '🔴 LOSS'}
                          </span>
                        </td>
                        <td class="text-secondary small font-mono">${t.exit_reason || 'NORMAL_CLOSE'}</td>
                      </tr>
                    `;
                  }).join('')}
                </tbody>
              </table>

              <!-- Pagination Toolbar -->
              <div class="pagination-toolbar">
                <span class="text-secondary">Showing page ${currentPage} of ${totalPages} (${filtered.length} total trades)</span>
                <div class="pagination-buttons">
                  <button class="btn btn-xs btn-secondary" id="btn-page-prev" ${currentPage <= 1 ? 'disabled' : ''}>« Prev</button>
                  <span class="page-indicator">${currentPage} / ${totalPages}</span>
                  <button class="btn btn-xs btn-secondary" id="btn-page-next" ${currentPage >= totalPages ? 'disabled' : ''}>Next »</button>
                </div>
              </div>
            </div>
          </div>
        ` : ''}

        ${activeSubTab === 'equity' ? `
          <div class="terminal-panel span-12">
            <div class="panel-header">
              <span class="panel-title">CUMULATIVE PORTFOLIO EQUITY CURVE</span>
              <span class="badge-source">TICK-BY-TICK CAPITAL TRAJECTORY</span>
            </div>
            <div class="panel-body compact-padding">
              <div class="equity-stats-bar">
                <div class="eq-pill"><span class="lbl">BASE CAPITAL:</span> <strong>₹25,00,000.00</strong></div>
                <div class="eq-pill"><span class="lbl">CURRENT EQUITY:</span> <strong class="text-amber">₹${sum.current_equity.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</strong></div>
                <div class="eq-pill"><span class="lbl">WIN RATE:</span> <strong class="color-bull">${sum.win_rate_pct}%</strong></div>
                <div class="eq-pill"><span class="lbl">PROFIT FACTOR:</span> <strong>${sum.profit_factor.toFixed(2)}</strong></div>
              </div>
              <div class="equity-chart-wrapper" style="height: 380px; width: 100%;">
                <canvas id="ledger-equity-canvas" style="width:100%; height:380px;"></canvas>
              </div>
            </div>
          </div>
        ` : ''}

        ${activeSubTab === 'sessions' ? `
          <div class="terminal-panel span-12">
            <div class="panel-header">
              <span class="panel-title">DAILY SESSIONS HISTORICAL PERFORMANCE BREAKDOWN</span>
              <span class="badge-source">CLICK ANY ROW TO FILTER AUDIT LEDGER</span>
            </div>
            <div class="panel-body no-padding">
              <table class="terminal-table dense-table hover-table">
                <thead>
                  <tr>
                    <th>Session Date</th>
                    <th>Total Trades</th>
                    <th>Closed</th>
                    <th>Wins / Losses</th>
                    <th>Win Rate %</th>
                    <th>Gross P&L</th>
                    <th>Frictional STT</th>
                    <th>Net Realized P&L</th>
                    <th>Performance Badge</th>
                  </tr>
                </thead>
                <tbody>
                  ${data.daily_performance.map(d => {
                    const isGreen = d.net_pnl > 0;
                    return `
                      <tr class="clickable-row session-click-row" data-date="${d.date}" style="cursor: pointer;" title="Click to view ${d.date} ledger">
                        <td class="tabular font-bold text-amber">🔍 ${d.date}</td>
                        <td class="tabular">${d.total_trades}</td>
                        <td class="tabular">${d.closed_trades}</td>
                        <td class="tabular">${d.wins}W / ${d.losses}L</td>
                        <td class="tabular ${d.win_rate_pct >= 55 ? 'text-bull' : (d.win_rate_pct >= 45 ? 'text-amber' : 'color-bear')}">
                          ${d.win_rate_pct}%
                        </td>
                        <td class="tabular ${d.gross_pnl >= 0 ? 'text-bull' : 'color-bear'}">
                          ${d.gross_pnl >= 0 ? '+' : ''}₹${d.gross_pnl.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </td>
                        <td class="tabular text-muted">₹${d.friction.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                        <td class="tabular font-bold ${isGreen ? 'color-bull' : 'color-bear'}">
                          ${isGreen ? '+' : ''}₹${d.net_pnl.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </td>
                        <td>
                          <span class="status-pill ${isGreen ? 'status-profit' : 'status-loss'}">
                            ${isGreen ? '🟢 PROFITABLE SESSION' : '🔴 MANAGED DEFENSE'}
                          </span>
                        </td>
                      </tr>
                    `;
                  }).join('')}
                </tbody>
              </table>
            </div>
          </div>
        ` : ''}
      </div>
    `;

    // Event Bindings
    container.querySelectorAll('.subnav-btn').forEach(btn => {
      btn.onclick = () => {
        activeSubTab = btn.getAttribute('data-subtab');
        update();
      };
    });

    const refBtn = container.querySelector('#btn-refresh-ledger');
    if (refBtn) refBtn.onclick = () => loadData();

    const dateSelect = container.querySelector('#ledger-date-select');
    if (dateSelect) {
      dateSelect.onchange = (e) => {
        selectedDate = e.target.value;
        currentPage = 1;
        loadData();
      };
    }

    const clearDateBtn = container.querySelector('#btn-clear-date');
    if (clearDateBtn) {
      clearDateBtn.onclick = () => {
        selectedDate = '';
        currentPage = 1;
        loadData();
      };
    }

    // Search input
    const searchInput = container.querySelector('#ledger-search-box');
    if (searchInput) {
      searchInput.oninput = (e) => {
        searchQuery = e.target.value;
        currentPage = 1;
        update();
      };
    }

    // Side filter buttons
    container.querySelectorAll('.side-filter-btn').forEach(btn => {
      btn.onclick = () => {
        sideFilter = btn.getAttribute('data-side');
        currentPage = 1;
        update();
      };
    });

    // Pagination
    const prevBtn = container.querySelector('#btn-page-prev');
    const nextBtn = container.querySelector('#btn-page-next');
    if (prevBtn) {
      prevBtn.onclick = () => {
        if (currentPage > 1) {
          currentPage--;
          update();
        }
      };
    }
    if (nextBtn) {
      nextBtn.onclick = () => {
        if (currentPage < totalPages) {
          currentPage++;
          update();
        }
      };
    }

    // Click daily row
    container.querySelectorAll('.session-click-row').forEach(row => {
      row.onclick = () => {
        const dt = row.getAttribute('data-date');
        if (dt) {
          selectedDate = dt;
          activeSubTab = 'ledger';
          currentPage = 1;
          loadData();
        }
      };
    });

    // Render Equity Canvas
    if (activeSubTab === 'equity') {
      const eqCanvas = container.querySelector('#ledger-equity-canvas');
      if (eqCanvas && data.equity_curve && data.equity_curve.length > 0) {
        const points = data.equity_curve.map(pt => pt.account_equity);
        ChartEngine.renderLineChart(eqCanvas, points, {
          title: 'Total Account Equity Progression (₹)',
          lineColor: '#00e676',
          areaColor: 'rgba(0, 230, 118, 0.08)',
          lineWidth: 2.2,
          baseline: 2500000.0,
          unit: '₹'
        });
      }
    }
  }

  update();
  loadData();
}
