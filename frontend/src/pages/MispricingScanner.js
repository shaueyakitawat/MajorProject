/**
 * Institutional Mispricing Scanner & Heatmap Page
 * Screen ranking options by M-score and VRP, interactive Strike x Expiry heatmap,
 * and dual scatter plots (IV vs Model Vol, Mispricing % vs Liquidity Score).
 */

import { terminalStore } from '../stores/terminalStore.js';
import { apiService } from '../services/api.js';
import { ChartEngine } from '../services/chartEngine.js';

export function renderMispricingScanner(container) {
  let viewSubTab = 'table'; // 'table' | 'heatmap' | 'scatters'
  let sortField = 'absMScore';
  let minMScore = 1.0;
  let typeFilter = 'BOTH';

  async function ensureChainLoaded() {
    const s = terminalStore.getState();
    if (!s.optionChain || s.optionChain.length === 0) {
      const res = await apiService.getOptionChain('NIFTY', s.selectedExpiry, 30);
      if (res.success && res.data && res.data.chain) {
        terminalStore.setState({ optionChain: res.data.chain });
        update();
      }
    }
  }

  function update() {
    const s = terminalStore.getState();
    const chain = s.optionChain || [];

    // Extract all individual contracts
    const contracts = [];
    chain.forEach(row => {
      ['call', 'put'].forEach(t => {
        const c = row[t];
        if (c) {
          contracts.push({
            strike: row.strike,
            type: t,
            instrument: `NIFTY ${row.strike} ${t.toUpperCase()}`,
            expiry: s.selectedExpiry,
            ltp: c.ltp,
            fairPrice: c.fairPrice,
            deviation: c.mispricingPct,
            iv: c.iv,
            modelVol: c.modelVol,
            vrp: c.vrp,
            mScore: c.mScore,
            zScore: c.zScore,
            tci: 0.00034,
            regime: s.regime,
            oi: c.oi,
            volume: c.volume,
            spread: c.spread,
            liquidityClass: c.liquidityClass,
            liquidityScore: c.liquidityScore || 75,
            signal: c.signal,
            absMScore: Math.abs(c.mScore || 0),
            absDev: Math.abs(c.mispricingPct || 0),
          });
        }
      });
    });

    // Filter
    const filtered = contracts.filter(c => {
      if (typeFilter !== 'BOTH' && c.type.toLowerCase() !== (typeFilter === 'CE' ? 'call' : 'put')) return false;
      if (c.absMScore < minMScore) return false;
      return true;
    });

    // Sort
    filtered.sort((a, b) => b[sortField] - a[sortField]);

    // KPI counts
    const totalCount = contracts.length;
    const liquidCount = contracts.filter(c => c.liquidityClass === 'HIGH' || c.liquidityClass === 'MEDIUM').length;
    const underpricedCount = contracts.filter(c => c.signal === 'underpriced').length;
    const overpricedCount = contracts.filter(c => c.signal === 'overpriced').length;
    const extremeCount = contracts.filter(c => c.absMScore >= 2.5).length;

    container.innerHTML = `
      <div class="workspace-grid scanner-layout">
        <!-- Top Metrics KPI Banner -->
        <div class="terminal-panel span-12">
          <div class="panel-header">
            <span class="panel-title">INSTITUTIONAL MISPRICING SCANNER & CROSS-SECTIONAL DISLOCATION ENGINE</span>
            <div class="panel-controls">
              <div class="btn-group-toggle">
                <button class="scanner-tab-btn ${viewSubTab === 'table' ? 'active' : ''}" data-tab="table">GRID TABLE</button>
                <button class="scanner-tab-btn ${viewSubTab === 'heatmap' ? 'active' : ''}" data-tab="heatmap">DISLOCATION HEATMAP</button>
                <button class="scanner-tab-btn ${viewSubTab === 'scatters' ? 'active' : ''}" data-tab="scatters">ANALYTICAL SCATTERS</button>
              </div>
            </div>
          </div>

          <div class="dense-stats-strip">
            <div class="stat-pill"><span class="lbl">TOTAL OPTIONS ANALYZED:</span> <strong class="tabular">${totalCount}</strong></div>
            <div class="stat-pill"><span class="lbl">LIQUID & TRADABLE:</span> <strong class="tabular text-bull">${liquidCount}</strong></div>
            <div class="stat-pill"><span class="lbl">UNDERPRICED:</span> <strong class="tabular color-bull font-bold">${underpricedCount}</strong></div>
            <div class="stat-pill"><span class="lbl">OVERPRICED:</span> <strong class="tabular color-bear font-bold">${overpricedCount}</strong></div>
            <div class="stat-pill"><span class="lbl">EXTREME DISLOCATIONS (≥2.5σ):</span> <strong class="tabular text-amber font-bold">${extremeCount}</strong></div>
          </div>
        </div>

        ${viewSubTab === 'table' ? `
          <!-- Scanner Data Grid -->
          <div class="terminal-panel span-12">
            <div class="panel-header">
              <span class="panel-title">RANKED OPTION MISPRICING OPPORTUNITIES</span>
              <div class="panel-controls">
                <div class="control-item">
                  <label>MIN M-SCORE:</label>
                  <select class="term-select" id="scan-mscore-filter">
                    <option value="0.0" ${minMScore === 0 ? 'selected' : ''}>All</option>
                    <option value="1.0" ${minMScore === 1.0 ? 'selected' : ''}>≥ 1.0σ</option>
                    <option value="2.0" ${minMScore === 2.0 ? 'selected' : ''}>≥ 2.0σ</option>
                    <option value="3.0" ${minMScore === 3.0 ? 'selected' : ''}>≥ 3.0σ (Extreme)</option>
                  </select>
                </div>

                <div class="control-item">
                  <label>SORT BY:</label>
                  <select class="term-select" id="scan-sort-select">
                    <option value="absMScore" ${sortField === 'absMScore' ? 'selected' : ''}>Absolute M-Score</option>
                    <option value="absDev" ${sortField === 'absDev' ? 'selected' : ''}>Absolute Deviation %</option>
                    <option value="vrp" ${sortField === 'vrp' ? 'selected' : ''}>Net VRP</option>
                    <option value="volume" ${sortField === 'volume' ? 'selected' : ''}>Traded Volume</option>
                    <option value="oi" ${sortField === 'oi' ? 'selected' : ''}>Open Interest</option>
                  </select>
                </div>
              </div>
            </div>

            <div class="panel-body no-padding" style="max-height: 480px; overflow-y: auto;">
              <table class="terminal-table dense-table hover-table">
                <thead>
                  <tr>
                    <th>Rank</th>
                    <th>Instrument</th>
                    <th>Strike</th>
                    <th>Type</th>
                    <th>LTP</th>
                    <th>BS Fair</th>
                    <th>Deviation %</th>
                    <th>IV</th>
                    <th>Model Vol</th>
                    <th>VRP</th>
                    <th>M-Score</th>
                    <th>Z-Score</th>
                    <th>OI</th>
                    <th>Volume</th>
                    <th>Spread</th>
                    <th>Liquidity</th>
                    <th>Signal</th>
                  </tr>
                </thead>
                <tbody>
                  ${filtered.slice(0, 50).map((c, idx) => `
                    <tr class="clickable-scan-row" data-strike="${c.strike}" data-type="${c.type}">
                      <td class="tabular font-bold">${idx + 1}</td>
                      <td><strong>${c.instrument}</strong></td>
                      <td class="tabular">${c.strike}</td>
                      <td><span class="badge-type ${c.type === 'call' ? 'badge-ce' : 'badge-pe'}">${c.type.toUpperCase()}</span></td>
                      <td class="tabular font-bold">₹${c.ltp.toFixed(2)}</td>
                      <td class="tabular">₹${c.fairPrice.toFixed(2)}</td>
                      <td class="tabular ${c.deviation > 0 ? 'color-bear' : 'color-bull'} font-bold">
                        ${c.deviation > 0 ? '+' : ''}${c.deviation.toFixed(1)}%
                      </td>
                      <td class="tabular">${(c.iv * 100).toFixed(1)}%</td>
                      <td class="tabular">${(c.modelVol * 100).toFixed(1)}%</td>
                      <td class="tabular text-amber">${c.vrp ? (c.vrp * 100).toFixed(2) + '%' : '--'}</td>
                      <td class="tabular text-amber font-bold">${c.mScore ? (c.mScore >= 0 ? '+' : '') + c.mScore.toFixed(2) + 'σ' : '--'}</td>
                      <td class="tabular">${c.zScore ? (c.zScore >= 0 ? '+' : '') + c.zScore.toFixed(2) + 'σ' : '--'}</td>
                      <td class="tabular">${c.oi.toLocaleString('en-IN')}</td>
                      <td class="tabular">${c.volume.toLocaleString('en-IN')}</td>
                      <td class="tabular text-muted">₹${c.spread.toFixed(2)}</td>
                      <td><span class="badge-liq text-bull">${c.liquidityClass}</span></td>
                      <td>
                        <span class="badge-signal ${c.signal === 'overpriced' ? 'tag-overpriced' : (c.signal === 'underpriced' ? 'tag-underpriced' : 'tag-fair')}">
                          ${c.signal === 'overpriced' ? 'SELL / RICH' : (c.signal === 'underpriced' ? 'BUY / CHEAP' : 'FAIR')}
                        </span>
                      </td>
                    </tr>
                  `).join('')}
                </tbody>
              </table>
            </div>
          </div>
        ` : ''}

        ${viewSubTab === 'heatmap' ? `
          <!-- Mispricing Heatmap -->
          <div class="terminal-panel span-12">
            <div class="panel-header">
              <span class="panel-title">CROSS-SECTIONAL MISPRICING HEATMAP (STRIKE X EXPIRY)</span>
              <span class="badge-source">COLOR: M-SCORE INTENSITY (RED = OVERPRICED, GREEN = UNDERPRICED)</span>
            </div>
            <div class="panel-body compact-padding">
              <canvas id="scanner-heatmap-canvas" style="width:100%; height:420px;"></canvas>
            </div>
          </div>
        ` : ''}

        ${viewSubTab === 'scatters' ? `
          <!-- Dual Scatters -->
          <div class="terminal-panel span-6">
            <div class="panel-header">
              <span class="panel-title">IV VS MODEL VOLATILITY SCATTER (PARITY = 45°)</span>
            </div>
            <div class="panel-body compact-padding">
              <canvas id="scatter-iv-model-canvas" style="width:100%; height:340px;"></canvas>
            </div>
          </div>

          <div class="terminal-panel span-6">
            <div class="panel-header">
              <span class="panel-title">MISPRICING % VS LIQUIDITY SCORE (ISOLATE TRADABLE OPPORTUNITIES)</span>
            </div>
            <div class="panel-body compact-padding">
              <canvas id="scatter-liq-mispricing-canvas" style="width:100%; height:340px;"></canvas>
            </div>
          </div>
        ` : ''}
      </div>
    `;

    // Bind sub-tabs
    container.querySelectorAll('.scanner-tab-btn').forEach(btn => {
      btn.onclick = () => {
        viewSubTab = btn.getAttribute('data-tab');
        update();
      };
    });

    const mScoreFilter = container.querySelector('#scan-mscore-filter');
    if (mScoreFilter) {
      mScoreFilter.onchange = (e) => {
        minMScore = parseFloat(e.target.value);
        update();
      };
    }

    const sortSelect = container.querySelector('#scan-sort-select');
    if (sortSelect) {
      sortSelect.onchange = (e) => {
        sortField = e.target.value;
        update();
      };
    }

    // Row clicks
    container.querySelectorAll('.clickable-scan-row').forEach(row => {
      row.onclick = () => {
        const strike = parseInt(row.getAttribute('data-strike'));
        const type = row.getAttribute('data-type');
        const c = contracts.find(x => x.strike === strike && x.type === type);
        if (c) terminalStore.openOptionDetail(c);
      };
    });

    // Render Heatmap or Scatters
    setTimeout(() => {
      if (viewSubTab === 'heatmap') {
        const cv = container.querySelector('#scanner-heatmap-canvas');
        if (cv) {
          const strikes = [21800, 22000, 22200, 22400, 22600, 22800, 23000];
          const expiries = ['16 OCT', '23 OCT', '30 OCT', '27 NOV', '31 DEC'];
          const matrix = expiries.map((_, r) => strikes.map((st) => {
            const match = contracts.find(c => Math.abs(c.strike - st) <= 25);
            const baseM = match ? match.mScore : (st < s.niftySpot ? 1.4 : -1.2);
            const termFactor = 1.0 / Math.sqrt(1 + r * 0.35);
            return Math.round(baseM * termFactor * 10) / 10;
          }));
          ChartEngine.renderHeatmap(cv, strikes.map(s => s.toString()), expiries, matrix);
        }
      } else if (viewSubTab === 'scatters') {
        const cv1 = container.querySelector('#scatter-iv-model-canvas');
        if (cv1) {
          const pts = contracts.map(c => ({
            x: c.modelVol,
            y: c.iv,
            color: c.signal === 'overpriced' ? '#ff5252' : '#00e676',
            size: 4
          }));
          ChartEngine.renderScatter(cv1, pts, {
            showParityLine: true,
            xLabel: 'Model Volatility (σ_model)',
            yLabel: 'Market Implied Volatility (IV)'
          });
        }

        const cv2 = container.querySelector('#scatter-liq-mispricing-canvas');
        if (cv2) {
          const pts = contracts.map(c => ({
            x: c.liquidityScore,
            y: c.deviation,
            color: c.signal === 'overpriced' ? '#ff5252' : '#00e676',
            size: Math.max(3, Math.min(8, c.oi / 20000))
          }));
          ChartEngine.renderScatter(cv2, pts, {
            xLabel: 'Liquidity Score (0-100)',
            yLabel: 'Mispricing Deviation %'
          });
        }
      }
    }, 50);
  }

  terminalStore.subscribe(update);
  update();
  ensureChainLoaded();
}
