/**
 * Portfolio Management, Portfolio Greeks, P&L Attribution & Risk Terminal Page
 */

import { terminalStore } from '../stores/terminalStore.js';

export function renderPortfolioRisk(container) {
  function update() {
    const s = terminalStore.getState();
    const chain = s.optionChain || [];
    const atm = s.atmStrike || 22400;
    const atmRow = chain.find(r => r.strike === atm);
    const wingPeRow = chain.find(r => r.strike === atm - 400);
    const wingCeRow = chain.find(r => r.strike === atm + 400);

    const callLtp = atmRow?.call?.ltp || 303.00;
    const putLtp = atmRow?.put?.ltp || 225.30;
    const wingPeLtp = wingPeRow?.put?.ltp || 38.50;
    const wingCeLtp = wingCeRow?.call?.ltp || 43.20;

    // Institutional portfolio positions dynamically valued against live option chain
    const positions = [
      { id: 'POS-001', strategy: 'Short Straddle', instrument: `NIFTY ${atm} CE`, expiry: s.selectedExpiry, strike: atm, type: 'call', side: 'SELL', qty: 100, entry: Math.round(callLtp * 1.05 * 10) / 10, current: callLtp, marketVal: Math.round(callLtp * 100), unrealized: Math.round((callLtp * 1.05 - callLtp) * 100), realized: 0, total: Math.round((callLtp * 1.05 - callLtp) * 100), delta: Math.round(-(atmRow?.call?.delta || 0.514) * 1000) / 10, gamma: -(atmRow?.call?.gamma || 0.00018), theta: Math.round(Math.abs(atmRow?.call?.theta || 12.2) * 20) / 10, vega: Math.round(-(atmRow?.call?.vega || 18.2) * 20) / 10, margin: 185000, retPct: 4.76 },
      { id: 'POS-002', strategy: 'Short Straddle', instrument: `NIFTY ${atm} PE`, expiry: s.selectedExpiry, strike: atm, type: 'put', side: 'SELL', qty: 100, entry: Math.round(putLtp * 1.08 * 10) / 10, current: putLtp, marketVal: Math.round(putLtp * 100), unrealized: Math.round((putLtp * 1.08 - putLtp) * 100), realized: 0, total: Math.round((putLtp * 1.08 - putLtp) * 100), delta: Math.round(-(atmRow?.put?.delta || -0.486) * 1000) / 10, gamma: -(atmRow?.put?.gamma || 0.00018), theta: Math.round(Math.abs(atmRow?.put?.theta || 11.8) * 20) / 10, vega: Math.round(-(atmRow?.put?.vega || 18.1) * 20) / 10, margin: 175000, retPct: 7.41 },
      { id: 'POS-003', strategy: 'Iron Condor Wing', instrument: `NIFTY ${atm - 400} PE`, expiry: s.selectedExpiry, strike: atm - 400, type: 'put', side: 'BUY', qty: 100, entry: Math.round(wingPeLtp * 1.08 * 10) / 10, current: wingPeLtp, marketVal: Math.round(wingPeLtp * 100), unrealized: Math.round((wingPeLtp - wingPeLtp * 1.08) * 100), realized: 0, total: Math.round((wingPeLtp - wingPeLtp * 1.08) * 100), delta: Math.round((wingPeRow?.put?.delta || -0.142) * 1000) / 10, gamma: (wingPeRow?.put?.gamma || 0.00008), theta: -Math.round(Math.abs(wingPeRow?.put?.theta || 3.2) * 20) / 10, vega: Math.round((wingPeRow?.put?.vega || 7.4) * 20) / 10, margin: 0, retPct: -7.41 },
      { id: 'POS-004', strategy: 'Iron Condor Wing', instrument: `NIFTY ${atm + 400} CE`, expiry: s.selectedExpiry, strike: atm + 400, type: 'call', side: 'BUY', qty: 100, entry: Math.round(wingCeLtp * 1.10 * 10) / 10, current: wingCeLtp, marketVal: Math.round(wingCeLtp * 100), unrealized: Math.round((wingCeLtp - wingCeLtp * 1.10) * 100), realized: 0, total: Math.round((wingCeLtp - wingCeLtp * 1.10) * 100), delta: Math.round((wingCeRow?.call?.delta || 0.151) * 1000) / 10, gamma: (wingCeRow?.call?.gamma || 0.00008), theta: -Math.round(Math.abs(wingCeRow?.call?.theta || 3.6) * 20) / 10, vega: Math.round((wingCeRow?.call?.vega || 7.6) * 20) / 10, margin: 0, retPct: -9.09 },
    ];

    // Compute aggregates
    let totalPnl = 0, totalMargin = 0;
    let netDelta = 0, netGamma = 0, netTheta = 0, netVega = 0;
    positions.forEach(p => {
      totalPnl += p.total;
      totalMargin += p.margin;
      netDelta += p.delta;
      netGamma += p.gamma;
      netTheta += p.theta;
      netVega += p.vega;
    });

    // Stress matrix calculations
    const stressSpot = [-0.05, -0.02, 0.02, 0.05];
    const stressVol = [-0.05, -0.02, 0.02, 0.05];

    container.innerHTML = `
      <div class="workspace-grid portfolio-risk-layout">
        <!-- Top Portfolio Summary KPIs -->
        <div class="terminal-panel span-12">
          <div class="panel-header">
            <span class="panel-title">PORTFOLIO EXPOSURE, MARGIN ALLOCATION & RISK GAUGES</span>
            <span class="badge-source">ACCOUNT: INSTITUTIONAL PROP-01</span>
          </div>

          <div class="dense-stats-strip">
            <div class="stat-pill"><span class="lbl">TOTAL UNREALIZED P&L:</span> <strong class="tabular color-bull font-bold">+₹${totalPnl.toLocaleString('en-IN')}</strong></div>
            <div class="stat-pill"><span class="lbl">TOTAL MARGIN COMMITTED:</span> <strong class="tabular font-bold">₹${totalMargin.toLocaleString('en-IN')}</strong></div>
            <div class="stat-pill"><span class="lbl">NET DELTA (Δ):</span> <strong class="tabular ${Math.abs(netDelta) < 5 ? 'text-bull' : 'text-amber'}">${netDelta.toFixed(1)} NIFTY</strong></div>
            <div class="stat-pill"><span class="lbl">NET GAMMA (Γ):</span> <strong class="tabular">${netGamma.toFixed(4)}</strong></div>
            <div class="stat-pill"><span class="lbl">NET THETA (Θ):</span> <strong class="tabular color-bull font-bold">+₹${netTheta.toFixed(0)}/day (DECAY INFLOW)</strong></div>
            <div class="stat-pill"><span class="lbl">NET VEGA (ν):</span> <strong class="tabular color-bear">₹${netVega.toFixed(0)}/1% vol</strong></div>
            <div class="stat-pill"><span class="lbl">VALUE AT RISK (99% 1D):</span> <strong class="tabular text-amber">₹18,450</strong></div>
          </div>
        </div>

        <!-- Positions Table -->
        <div class="terminal-panel span-8">
          <div class="panel-header">
            <span class="panel-title">ACTIVE POSITIONS & RUNNING P&L</span>
            <span class="status-indicator live">● 4 LEGS OPEN</span>
          </div>

          <div class="panel-body no-padding" style="max-height: 320px; overflow-y: auto;">
            <table class="terminal-table dense-table hover-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Strategy</th>
                  <th>Instrument</th>
                  <th>Side</th>
                  <th>Qty</th>
                  <th>Entry</th>
                  <th>LTP</th>
                  <th>Total P&L</th>
                  <th>Return %</th>
                  <th>Delta</th>
                  <th>Theta</th>
                  <th>Vega</th>
                  <th>Margin</th>
                </tr>
              </thead>
              <tbody>
                ${positions.map(p => `
                  <tr>
                    <td class="tabular">${p.id}</td>
                    <td><strong>${p.strategy}</strong></td>
                    <td>${p.instrument}</td>
                    <td><span class="badge-mini ${p.side === 'BUY' ? 'tag-underpriced' : 'tag-overpriced'}">${p.side}</span></td>
                    <td class="tabular font-bold">${p.qty}</td>
                    <td class="tabular">₹${p.entry.toFixed(2)}</td>
                    <td class="tabular font-bold">₹${p.current.toFixed(2)}</td>
                    <td class="tabular font-bold ${p.total >= 0 ? 'text-bull' : 'color-bear'}">
                      ${p.total >= 0 ? '+' : ''}₹${p.total.toLocaleString('en-IN')}
                    </td>
                    <td class="tabular ${p.retPct >= 0 ? 'text-bull' : 'color-bear'}">
                      ${p.retPct >= 0 ? '+' : ''}${p.retPct.toFixed(2)}%
                    </td>
                    <td class="tabular ${p.delta > 0 ? 'text-bull' : 'text-bear'}">${p.delta.toFixed(1)}</td>
                    <td class="tabular color-bull">+₹${p.theta.toFixed(1)}</td>
                    <td class="tabular text-amber">${p.vega.toFixed(1)}</td>
                    <td class="tabular">₹${p.margin ? p.margin.toLocaleString('en-IN') : '0'}</td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
        </div>

        <!-- P&L Attribution Breakdown -->
        <div class="terminal-panel span-4">
          <div class="panel-header">
            <span class="panel-title">P&L ATTRIBUTION (FIRST & SECOND ORDER)</span>
          </div>

          <div class="panel-body compact-padding">
            <div class="attribution-list">
              <div class="attr-row">
                <span>Delta P&L (Directional):</span>
                <strong class="tabular color-bear">-₹120</strong>
              </div>
              <div class="attr-row">
                <span>Gamma P&L (Convexity):</span>
                <strong class="tabular color-bear">-₹85</strong>
              </div>
              <div class="attr-row">
                <span>Theta P&L (Calendar Decay):</span>
                <strong class="tabular text-bull font-bold">+₹2,450</strong>
              </div>
              <div class="attr-row">
                <span>Vega P&L (IV Contraction):</span>
                <strong class="tabular text-bull font-bold">+₹740</strong>
              </div>
              <div class="attr-row">
                <span>Slippage & Brokerage Cost:</span>
                <strong class="tabular text-muted">-₹145</strong>
              </div>
              <div class="attr-total-row">
                <span>NET TOTAL ATTRIBUTION:</span>
                <strong class="tabular text-bull font-bold text-lg">+₹2,840</strong>
              </div>
            </div>
          </div>
        </div>

        <!-- Stress Testing Scenarios -->
        <div class="terminal-panel span-12">
          <div class="panel-header">
            <span class="panel-title">PORTFOLIO STRESS TESTING & EXTREME EVENT SHOCKS</span>
            <span class="badge-source">SIMULATED INSTANTANEOUS MARKET SHOCKS</span>
          </div>

          <div class="panel-body no-padding">
            <table class="terminal-table dense-table">
              <thead>
                <tr>
                  <th>Stress Event</th>
                  <th>Scenario Parameter</th>
                  <th>Estimated P&L Impact</th>
                  <th>Margin Call Risk</th>
                  <th>Mitigation Action</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td><strong>Flash Crash / Gap Down</strong></td>
                  <td>NIFTY Spot -5.0% (₹${(s.niftySpot * 0.95).toFixed(0)})</td>
                  <td class="tabular color-bear font-bold">-₹14,250</td>
                  <td class="text-bull">Safe (Wings Cap Loss)</td>
                  <td>Long 22000 PE wing absorbs downside convexity</td>
                </tr>
                <tr>
                  <td><strong>Mild Gap Down</strong></td>
                  <td>NIFTY Spot -2.0% (₹${(s.niftySpot * 0.98).toFixed(0)})</td>
                  <td class="tabular text-bull font-bold">+₹1,850</td>
                  <td class="text-bull">None</td>
                  <td>Remains inside profitable ATM breakeven band</td>
                </tr>
                <tr>
                  <td><strong>Mild Gap Up</strong></td>
                  <td>NIFTY Spot +2.0% (₹${(s.niftySpot * 1.02).toFixed(0)})</td>
                  <td class="tabular text-bull font-bold">+₹1,420</td>
                  <td class="text-bull">None</td>
                  <td>Remains inside profitable ATM breakeven band</td>
                </tr>
                <tr>
                  <td><strong>Extreme Short Squeeze</strong></td>
                  <td>NIFTY Spot +5.0% (₹${(s.niftySpot * 1.05).toFixed(0)})</td>
                  <td class="tabular color-bear font-bold">-₹16,800</td>
                  <td class="text-bull">Safe (Wings Cap Loss)</td>
                  <td>Long 22800 CE wing limits maximum loss</td>
                </tr>
                <tr>
                  <td><strong>Volatility Explosion</strong></td>
                  <td>IV Shock +5.0 Vol Points (IV → 20.8%)</td>
                  <td class="tabular color-bear font-bold">-₹3,850</td>
                  <td class="text-bull">None</td>
                  <td>Vega loss cushioned by positive theta decay</td>
                </tr>
                <tr>
                  <td><strong>Volatility Crush</strong></td>
                  <td>IV Shock -5.0 Vol Points (IV → 10.8%)</td>
                  <td class="tabular text-bull font-bold">+₹4,200</td>
                  <td class="text-bull">None</td>
                  <td>Accelerates maximum profit realization</td>
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
