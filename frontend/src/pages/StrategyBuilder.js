/**
 * Quantitative Strategy Engine, Multi-Leg Builder, Payoff Graph & 5x5 Scenario Matrix Page
 */

import { terminalStore } from '../stores/terminalStore.js';
import { apiService } from '../services/api.js';
import { calculateStrategyPayoff, generateScenarioMatrix, calculateGreeks } from '../services/quantMath.js';
import { ChartEngine } from '../services/chartEngine.js';

export function renderStrategyBuilder(container) {
  let daysToExpiry = 14;
  let volShockPct = 0.0;
  let spotSlider = null;

  async function ensureStrategyLoaded() {
    const s = terminalStore.getState();
    if (!s.activeSignal) {
      const res = await apiService.getStrategy('NIFTY', s.timeframe, s.tradingHorizon);
      if (res.success && res.data) {
        terminalStore.setState({
          activeSignal: res.data.strategy || null,
          forecastVolatility: res.data.forecast_volatility || s.forecastVolatility,
          bsFairPrice: res.data.fair_price || s.bsFairPrice,
          marketPrice: res.data.market_price || s.marketPrice,
          regime: res.data.regime || s.regime,
          marketIv: res.data.implied_volatility || s.marketIv,
        });
        update();
      }
    }
  }

  function update() {
    const s = terminalStore.getState();
    const legs = s.strategyBuilderLegs || [];
    const currentSpot = spotSlider !== null ? spotSlider : s.niftySpot;

    // Calculate Net Greeks and Net Premium
    let netDelta = 0, netGamma = 0, netTheta = 0, netVega = 0, netRho = 0;
    let netPremium = 0;

    legs.forEach(leg => {
      const sign = leg.action.toLowerCase() === 'buy' ? 1 : -1;
      const g = calculateGreeks(currentSpot, leg.strike, Math.max(0.001, daysToExpiry / 365), 0.06, (leg.iv || 0.15) + (volShockPct / 100), leg.type);
      netDelta += sign * g.delta * leg.qty;
      netGamma += sign * g.gamma * leg.qty;
      netTheta += sign * g.theta * leg.qty;
      netVega += sign * g.vega * leg.qty;
      netRho += sign * g.rho * leg.qty;
      netPremium += sign * leg.price * leg.qty;
    });

    // Generate Payoff Range (Spot ± 6%)
    const spotMin = Math.round(currentSpot * 0.94);
    const spotMax = Math.round(currentSpot * 1.06);
    const spotRange = [];
    for (let sp = spotMin; sp <= spotMax; sp += 25) spotRange.push(sp);

    const payoffData = calculateStrategyPayoff(legs, spotRange, currentSpot, daysToExpiry, volShockPct / 100);

    // Scenario Analysis 5x5 Matrix
    const scenario = generateScenarioMatrix(legs, currentSpot);

    const sigAction = s.activeSignal?.action || 'SHORT VOLATILITY';
    const sigName = s.activeSignal?.recommended_strategy || 'DELTA-NEUTRAL ATM STRADDLE / CONDOR';
    const vrpVal = (s.marketIv - s.forecastVolatility) * 100;

    container.innerHTML = `
      <div class="workspace-grid strategy-workspace-layout">
        <!-- Transparent Model Signal Card -->
        <div class="terminal-panel span-12">
          <div class="panel-header">
            <span class="panel-title">SYSTEM QUANTITATIVE STRATEGY SIGNAL & TRANSPARENT REASONING</span>
            <span class="badge-confidence">CONFIDENCE: HIGH (DELTA-NEUTRAL)</span>
          </div>

          <div class="panel-body compact-padding">
            <div class="signal-banner-dense">
              <div class="signal-tag-group">
                <span class="signal-badge ${sigAction.includes('SHORT') ? 'tag-short' : 'tag-underpriced'}">${sigAction}</span>
                <strong class="signal-title">${sigName}</strong>
              </div>
              <div class="signal-metrics-row">
                <div class="sig-met"><span>Market IV:</span> <strong class="tabular">${(s.marketIv * 100).toFixed(2)}%</strong></div>
                <div class="sig-met"><span>Model Vol (σ):</span> <strong class="tabular">${(s.forecastVolatility * 100).toFixed(2)}%</strong></div>
                <div class="sig-met"><span>Net VRP:</span> <strong class="tabular text-amber">${vrpVal >= 0 ? '+' : ''}${vrpVal.toFixed(2)}%</strong></div>
                <div class="sig-met"><span>M-Score:</span> <strong class="tabular color-bear">${s.mScore >= 0 ? '+' : ''}${s.mScore.toFixed(2)}σ</strong></div>
                <div class="sig-met"><span>Regime:</span> <strong>${s.regime}</strong></div>
                <div class="sig-met"><span>TCI:</span> <strong class="text-bull">${(s.tci || 0.00034).toFixed(5)} (STABLE)</strong></div>
                <div class="sig-met"><span>Liquidity:</span> <strong class="text-bull">HIGH</strong></div>
              </div>
            </div>
          </div>
        </div>

        <!-- Strategy Builder: Multi-Leg Grid -->
        <div class="terminal-panel span-7">
          <div class="panel-header">
            <span class="panel-title">MULTI-LEG EXECUTION STRUCTURE</span>
            <div class="panel-controls">
              <!-- Strategy Presets -->
              <div class="btn-group-toggle">
                <button class="preset-btn" id="preset-straddle">ATM Straddle</button>
                <button class="preset-btn" id="preset-condor">Iron Condor</button>
                <button class="preset-btn" id="preset-strangle">Strangle</button>
              </div>
              <button class="btn btn-xs btn-primary" id="btn-add-leg">+ Add Leg</button>
            </div>
          </div>

          <div class="panel-body no-padding" style="max-height: 240px; overflow-y: auto;">
            <table class="terminal-table dense-table">
              <thead>
                <tr>
                  <th>Action</th>
                  <th>Type</th>
                  <th>Strike</th>
                  <th>Expiry</th>
                  <th>Qty</th>
                  <th>Price</th>
                  <th>IV</th>
                  <th>Delta</th>
                  <th>Vega</th>
                  <th>Theta</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                ${legs.map((leg, i) => `
                  <tr>
                    <td>
                      <select class="term-select leg-input" data-idx="${i}" data-field="action">
                        <option value="buy" ${leg.action === 'buy' ? 'selected' : ''}>BUY</option>
                        <option value="sell" ${leg.action === 'sell' ? 'selected' : ''}>SELL</option>
                      </select>
                    </td>
                    <td>
                      <select class="term-select leg-input" data-idx="${i}" data-field="type">
                        <option value="call" ${leg.type === 'call' ? 'selected' : ''}>CE</option>
                        <option value="put" ${leg.type === 'put' ? 'selected' : ''}>PE</option>
                      </select>
                    </td>
                    <td>
                      <input type="number" step="50" class="term-input leg-input tabular" style="width:75px;" data-idx="${i}" data-field="strike" value="${leg.strike}"/>
                    </td>
                    <td>
                      <span class="tabular">${s.selectedExpiry}</span>
                    </td>
                    <td>
                      <input type="number" step="50" class="term-input leg-input tabular" style="width:60px;" data-idx="${i}" data-field="qty" value="${leg.qty}"/>
                    </td>
                    <td>
                      <input type="number" step="0.5" class="term-input leg-input tabular" style="width:70px;" data-idx="${i}" data-field="price" value="${leg.price}"/>
                    </td>
                    <td class="tabular">${((leg.iv || 0.15) * 100).toFixed(1)}%</td>
                    <td class="tabular ${leg.delta > 0 ? 'text-bull' : 'text-bear'}">${leg.delta?.toFixed(3) || '--'}</td>
                    <td class="tabular text-amber">${leg.vega?.toFixed(1) || '--'}</td>
                    <td class="tabular color-bear">${leg.theta?.toFixed(1) || '--'}</td>
                    <td>
                      <button class="btn btn-xs btn-danger btn-remove-leg" data-idx="${i}">✕</button>
                    </td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>

          <!-- Aggregate Position Greeks & Metrics Strip -->
          <div class="aggregate-greeks-strip">
            <div class="agg-cell"><span>Net Premium:</span> <strong class="tabular ${netPremium < 0 ? 'text-bull' : 'color-bear'}">${netPremium < 0 ? 'Credit ₹' + Math.abs(netPremium).toFixed(0) : 'Debit ₹' + netPremium.toFixed(0)}</strong></div>
            <div class="agg-cell"><span>Net Delta (Δ):</span> <strong class="tabular ${Math.abs(netDelta) < 5 ? 'text-bull' : 'text-amber'}">${netDelta.toFixed(2)}</strong></div>
            <div class="agg-cell"><span>Net Gamma (Γ):</span> <strong class="tabular">${netGamma.toFixed(4)}</strong></div>
            <div class="agg-cell"><span>Net Theta (Θ):</span> <strong class="tabular color-bear">₹${netTheta.toFixed(0)}/day</strong></div>
            <div class="agg-cell"><span>Net Vega (ν):</span> <strong class="tabular text-amber">₹${netVega.toFixed(0)}/1%</strong></div>
            <div class="agg-cell"><span>Max Profit:</span> <strong class="tabular text-bull">₹${payoffData.maxProfit.toFixed(0)}</strong></div>
            <div class="agg-cell"><span>Max Loss:</span> <strong class="tabular color-bear">${payoffData.maxLoss < -999999 ? 'Unlimited' : '₹' + Math.abs(payoffData.maxLoss).toFixed(0)}</strong></div>
          </div>
        </div>

        <!-- Interactive Payoff Graph & Scenario Sliders -->
        <div class="terminal-panel span-5">
          <div class="panel-header">
            <span class="panel-title">DYNAMIC PAYOFF PROFILE & SENSITIVITY CONTROLS</span>
          </div>

          <div class="panel-body compact-padding">
            <!-- Sliders -->
            <div class="slider-controls-bar">
              <div class="slider-item">
                <label>Days to Expiry: <strong class="tabular">${daysToExpiry}d</strong></label>
                <input type="range" id="slider-days" min="0" max="30" value="${daysToExpiry}" class="range-slider"/>
              </div>
              <div class="slider-item">
                <label>IV Shock: <strong class="tabular text-amber">${volShockPct >= 0 ? '+' : ''}${volShockPct}%</strong></label>
                <input type="range" id="slider-iv-shock" min="-5" max="5" step="0.5" value="${volShockPct}" class="range-slider"/>
              </div>
            </div>

            <!-- Payoff Canvas -->
            <div class="payoff-canvas-wrapper" style="height: 230px;">
              <canvas id="strategy-payoff-canvas" style="width:100%; height:230px;"></canvas>
            </div>
          </div>
        </div>

        <!-- 5x5 Scenario Analysis Matrix -->
        <div class="terminal-panel span-12">
          <div class="panel-header">
            <span class="panel-title">SCENARIO ANALYSIS MATRIX: UNDERLYING PRICE SHOCK VS IMPLIED VOLATILITY SHOCK</span>
            <span class="badge-source">ESTIMATED THEORETICAL P&L (₹) AT HORIZON</span>
          </div>

          <div class="panel-body no-padding">
            <table class="terminal-table dense-table scenario-table">
              <thead>
                <tr>
                  <th>Spot Shift \\ IV Shock</th>
                  ${scenario.ivHeaders.map(h => `<th class="text-right">${h} Vol</th>`).join('')}
                </tr>
              </thead>
              <tbody>
                ${scenario.matrix.map(row => `
                  <tr>
                    <td><strong>${row.spotChangePct >= 0 ? '+' : ''}${row.spotChangePct}% (₹${row.targetSpot})</strong></td>
                    ${row.values.map(val => `
                      <td class="tabular text-right ${val.pnl >= 0 ? 'text-bull' : 'color-bear font-bold'}">
                        ${val.pnl >= 0 ? '+' : ''}₹${val.pnl.toLocaleString('en-IN')}
                      </td>
                    `).join('')}
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    `;

    // Bind Presets
    container.querySelector('#preset-straddle').onclick = () => {
      const atm = s.atmStrike;
      terminalStore.setState({
        strategyBuilderLegs: [
          { id: 1, action: 'sell', type: 'call', strike: atm, expiry: s.selectedExpiry, qty: 50, price: 303.0, iv: 0.158, delta: 0.52, gamma: 0.0004, theta: -12.5, vega: 18.2 },
          { id: 2, action: 'sell', type: 'put', strike: atm, expiry: s.selectedExpiry, qty: 50, price: 225.3, iv: 0.155, delta: -0.48, gamma: 0.0004, theta: -11.8, vega: 18.1 },
        ]
      });
      update();
    };

    container.querySelector('#preset-condor').onclick = () => {
      const atm = s.atmStrike;
      terminalStore.setState({
        strategyBuilderLegs: [
          { id: 1, action: 'buy', type: 'put', strike: atm - 400, expiry: s.selectedExpiry, qty: 50, price: 45.0, iv: 0.170, delta: -0.15, gamma: 0.0002, theta: -4.0, vega: 8.0 },
          { id: 2, action: 'sell', type: 'put', strike: atm - 150, expiry: s.selectedExpiry, qty: 50, price: 135.0, iv: 0.158, delta: -0.32, gamma: 0.0003, theta: -8.5, vega: 14.0 },
          { id: 3, action: 'sell', type: 'call', strike: atm + 150, expiry: s.selectedExpiry, qty: 50, price: 155.0, iv: 0.156, delta: 0.34, gamma: 0.0003, theta: -9.0, vega: 14.5 },
          { id: 4, action: 'buy', type: 'call', strike: atm + 400, expiry: s.selectedExpiry, qty: 50, price: 52.0, iv: 0.165, delta: 0.16, gamma: 0.0002, theta: -4.5, vega: 8.5 },
        ]
      });
      update();
    };

    container.querySelector('#preset-strangle').onclick = () => {
      const atm = s.atmStrike;
      terminalStore.setState({
        strategyBuilderLegs: [
          { id: 1, action: 'sell', type: 'put', strike: atm - 200, expiry: s.selectedExpiry, qty: 50, price: 120.0, iv: 0.156, delta: -0.30, gamma: 0.0003, theta: -8.0, vega: 13.0 },
          { id: 2, action: 'sell', type: 'call', strike: atm + 200, expiry: s.selectedExpiry, qty: 50, price: 135.0, iv: 0.154, delta: 0.31, gamma: 0.0003, theta: -8.5, vega: 13.5 },
        ]
      });
      update();
    };

    // Add Leg
    container.querySelector('#btn-add-leg').onclick = () => {
      const atm = s.atmStrike;
      const cur = s.strategyBuilderLegs || [];
      const newLeg = {
        id: Date.now(),
        action: 'buy',
        type: 'call',
        strike: atm,
        expiry: s.selectedExpiry,
        qty: 50,
        price: 150.0,
        iv: 0.155,
        delta: 0.50,
        gamma: 0.0003,
        theta: -10.0,
        vega: 16.0
      };
      terminalStore.setState({ strategyBuilderLegs: [...cur, newLeg] });
      update();
    };

    // Remove Leg
    container.querySelectorAll('.btn-remove-leg').forEach(btn => {
      btn.onclick = () => {
        const idx = parseInt(btn.getAttribute('data-idx'));
        const cur = [...s.strategyBuilderLegs];
        cur.splice(idx, 1);
        terminalStore.setState({ strategyBuilderLegs: cur });
        update();
      };
    });

    // Leg inputs
    container.querySelectorAll('.leg-input').forEach(input => {
      input.onchange = (e) => {
        const idx = parseInt(input.getAttribute('data-idx'));
        const field = input.getAttribute('data-field');
        const cur = [...s.strategyBuilderLegs];
        let val = e.target.value;
        if (field === 'strike' || field === 'qty' || field === 'price') {
          val = parseFloat(val);
        }
        cur[idx][field] = val;
        terminalStore.setState({ strategyBuilderLegs: cur });
        update();
      };
    });

    // Sliders
    const dSlider = container.querySelector('#slider-days');
    if (dSlider) {
      dSlider.oninput = (e) => {
        daysToExpiry = parseInt(e.target.value);
        update();
      };
    }

    const ivSlider = container.querySelector('#slider-iv-shock');
    if (ivSlider) {
      ivSlider.oninput = (e) => {
        volShockPct = parseFloat(e.target.value);
        update();
      };
    }

    // Render Payoff Chart
    setTimeout(() => {
      const cv = container.querySelector('#strategy-payoff-canvas');
      if (cv && payoffData.points.length > 0) {
        ChartEngine.renderPayoff(cv, payoffData.points, payoffData.breakevens, currentSpot);
      }
    }, 50);
  }

  terminalStore.subscribe(update);
  update();
  ensureStrategyLoaded();
}
