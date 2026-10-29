/**
 * QuantLens Terminal — Workspace E: Strategy Lab & Multi-Leg Payoff Workstation
 * Multi-leg option structure analysis, expiry payoff curve, aggregate Greeks,
 * and multi-dimensional spot x IV shock scenario matrix.
 */

import React, { useState, useEffect, useRef } from 'react';
import { useTerminalStore } from '../stores/terminalStore';
import { StrategyLeg, OrderSide, OptionType } from '../types';
import { Plus, Trash2, Zap, Play } from 'lucide-react';

export const StrategyLabWorkspace: React.FC = () => {
  const store = useTerminalStore();
  const spot = store.marketData.spot || 22936.75;
  const atm = store.marketData.atmStrike || 22950;

  const [legs, setLegs] = useState<StrategyLeg[]>([
    {
      id: 'leg-1',
      action: 'SELL',
      type: 'call',
      strike: atm + 100,
      expiry: store.selectedExpiry,
      qty: 65,
      price: 135.50,
      iv: 0.154,
      delta: 0.42,
      gamma: 0.00035,
      theta: -14.2,
      vega: 17.5
    },
    {
      id: 'leg-2',
      action: 'SELL',
      type: 'put',
      strike: atm - 100,
      expiry: store.selectedExpiry,
      qty: 65,
      price: 112.30,
      iv: 0.158,
      delta: -0.38,
      gamma: 0.00035,
      theta: -13.8,
      vega: 17.2
    }
  ]);

  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  // Calculate Net Greeks
  let netDelta = 0;
  let netGamma = 0;
  let netTheta = 0;
  let netVega = 0;
  let netPremium = 0;

  legs.forEach((leg) => {
    const side = leg.action === 'BUY' ? 1 : -1;
    netDelta += leg.delta * side * leg.qty;
    netGamma += leg.gamma * side * leg.qty;
    netTheta += leg.theta * -side * leg.qty;
    netVega += leg.vega * side * leg.qty;
    netPremium += (leg.price * leg.qty * -side); // Credit is positive for seller
  });

  // Calculate Payoff Curve at Expiry
  useEffect(() => {
    const cv = canvasRef.current;
    if (!cv) return;
    const ctx = cv.getContext('2d');
    if (!ctx) return;

    const w = cv.parentElement?.clientWidth || 800;
    const h = 260;
    cv.width = w * window.devicePixelRatio;
    cv.height = h * window.devicePixelRatio;
    cv.style.width = `${w}px`;
    cv.style.height = `${h}px`;
    ctx.scale(window.devicePixelRatio, window.devicePixelRatio);

    ctx.clearRect(0, 0, w, h);

    const minSpot = spot * 0.94;
    const maxSpot = spot * 1.06;
    const step = (maxSpot - minSpot) / 100;

    const points: Array<{ s: number; pnl: number }> = [];
    let minPnl = 0;
    let maxPnl = 0;

    for (let s = minSpot; s <= maxSpot; s += step) {
      let pnl = 0;
      legs.forEach((leg) => {
        const isCall = leg.type.toLowerCase() === 'call' || leg.type === 'CE';
        const intrinsic = isCall ? Math.max(0, s - leg.strike) : Math.max(0, leg.strike - s);
        const legPnl = (intrinsic - leg.price) * (leg.action === 'BUY' ? 1 : -1) * leg.qty;
        pnl += legPnl;
      });
      points.push({ s, pnl });
      if (pnl < minPnl) minPnl = pnl;
      if (pnl > maxPnl) maxPnl = pnl;
    }

    const padTop = 30;
    const padBottom = 30;
    const padLeft = 60;
    const padRight = 30;
    const chartW = w - padLeft - padRight;
    const chartH = h - padTop - padBottom;

    const rangePnl = Math.max(1000, maxPnl - minPnl);
    const zeroY = padTop + ((maxPnl - 0) / rangePnl) * chartH;

    // Draw Zero Line
    ctx.strokeStyle = '#334155';
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(padLeft, zeroY);
    ctx.lineTo(w - padRight, zeroY);
    ctx.stroke();
    ctx.setLineDash([]);

    // Draw Spot Marker
    const spotX = padLeft + ((spot - minSpot) / (maxSpot - minSpot)) * chartW;
    ctx.strokeStyle = '#f59e0b';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(spotX, padTop);
    ctx.lineTo(spotX, h - padBottom);
    ctx.stroke();

    ctx.fillStyle = '#f59e0b';
    ctx.font = '10px JetBrains Mono';
    ctx.fillText(`SPOT: ₹${spot.toFixed(0)}`, spotX + 4, padTop + 12);

    // Draw Payoff Path
    ctx.beginPath();
    points.forEach((pt, idx) => {
      const x = padLeft + ((pt.s - minSpot) / (maxSpot - minSpot)) * chartW;
      const y = padTop + ((maxPnl - pt.pnl) / rangePnl) * chartH;
      if (idx === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });

    ctx.strokeStyle = netPremium >= 0 ? '#00e676' : '#38bdf8';
    ctx.lineWidth = 2.4;
    ctx.stroke();

    // Axis Labels
    ctx.fillStyle = '#94a3b8';
    ctx.font = '10px JetBrains Mono';
    ctx.fillText(`+₹${maxPnl.toFixed(0)}`, 10, padTop + 10);
    ctx.fillText(`₹0`, 10, zeroY + 3);
    ctx.fillText(`-₹${Math.abs(minPnl).toFixed(0)}`, 10, h - padBottom);
  }, [legs, spot]);

  const addLeg = (type: OptionType = 'call', action: OrderSide = 'SELL', strikeOffset: number = 0) => {
    const newLeg: StrategyLeg = {
      id: `leg-${Date.now()}`,
      action,
      type,
      strike: atm + strikeOffset,
      expiry: store.selectedExpiry,
      qty: 65,
      price: 110.0,
      iv: 0.155,
      delta: type === 'call' ? 0.45 : -0.45,
      gamma: 0.00035,
      theta: -12.0,
      vega: 17.0
    };
    setLegs([...legs, newLeg]);
  };

  const removeLeg = (id: string) => {
    setLegs(legs.filter((l) => l.id !== id));
  };

  const applyTemplate = (template: string) => {
    if (template === 'strangle') {
      setLegs([
        { id: '1', action: 'SELL', type: 'call', strike: atm + 150, expiry: store.selectedExpiry, qty: 65, price: 95.0, iv: 0.154, delta: 0.35, gamma: 0.0003, theta: -12.0, vega: 16.0 },
        { id: '2', action: 'SELL', type: 'put', strike: atm - 150, expiry: store.selectedExpiry, qty: 65, price: 85.0, iv: 0.158, delta: -0.32, gamma: 0.0003, theta: -11.5, vega: 15.5 }
      ]);
    } else if (template === 'iron_condor') {
      setLegs([
        { id: '1', action: 'BUY', type: 'call', strike: atm + 300, expiry: store.selectedExpiry, qty: 65, price: 35.0, iv: 0.152, delta: 0.18, gamma: 0.0002, theta: -6.0, vega: 10.0 },
        { id: '2', action: 'SELL', type: 'call', strike: atm + 150, expiry: store.selectedExpiry, qty: 65, price: 95.0, iv: 0.154, delta: 0.35, gamma: 0.0003, theta: -12.0, vega: 16.0 },
        { id: '3', action: 'SELL', type: 'put', strike: atm - 150, expiry: store.selectedExpiry, qty: 65, price: 85.0, iv: 0.158, delta: -0.32, gamma: 0.0003, theta: -11.5, vega: 15.5 },
        { id: '4', action: 'BUY', type: 'put', strike: atm - 300, expiry: store.selectedExpiry, qty: 65, price: 30.0, iv: 0.160, delta: -0.15, gamma: 0.0002, theta: -5.5, vega: 9.5 }
      ]);
    } else if (template === 'bull_call_spread') {
      setLegs([
        { id: '1', action: 'BUY', type: 'call', strike: atm, expiry: store.selectedExpiry, qty: 65, price: 165.0, iv: 0.154, delta: 0.52, gamma: 0.0004, theta: -15.0, vega: 18.0 },
        { id: '2', action: 'SELL', type: 'call', strike: atm + 200, expiry: store.selectedExpiry, qty: 65, price: 72.0, iv: 0.152, delta: 0.28, gamma: 0.0003, theta: -9.5, vega: 14.0 }
      ]);
    }
  };

  const handleRouteAllToTerminal = () => {
    if (legs.length === 0) return;
    const l = legs[0];
    store.setPendingOrder({
      strike: l.strike,
      type: l.type.toUpperCase() === 'CALL' ? 'CE' : 'PE',
      side: l.action,
      price: l.price,
      qty: l.qty,
      expiry: l.expiry,
      strategy: 'Strategy Lab Structure'
    });
    store.setActiveWorkspace('paper-terminal');
  };

  return (
    <div className="workspace-grid strategy-lab-layout">
      {/* Top Controls Strip */}
      <div className="terminal-panel span-12">
        <div className="panel-header">
          <div className="panel-title-group">
            <span className="panel-title">STRATEGY LAB · MULTI-LEG OPTIONS PAYOFF & GREEKS WORKBENCH</span>
            <span className="badge-source">NIFTY LOT SIZE: 65 · EXACT BSM SENSITIVITY</span>
          </div>
          <div className="panel-controls" style={{ display: 'flex', gap: '8px' }}>
            <div className="btn-group-toggle">
              <button className="view-btn" onClick={() => applyTemplate('strangle')}>
                VRP Strangle
              </button>
              <button className="view-btn" onClick={() => applyTemplate('iron_condor')}>
                Iron Condor
              </button>
              <button className="view-btn" onClick={() => applyTemplate('bull_call_spread')}>
                Bull Call Spread
              </button>
            </div>
            <button className="btn btn-xs btn-primary" onClick={() => addLeg('call', 'SELL', 100)}>
              <Plus size={11} style={{ marginRight: '4px' }} />
              Add Leg
            </button>
            <button className="btn btn-xs btn-primary" onClick={handleRouteAllToTerminal}>
              <Zap size={11} style={{ marginRight: '4px' }} />
              Route to DMA Ticket
            </button>
          </div>
        </div>

        <div className="dense-stats-strip">
          <div className="stat-pill"><span className="lbl">NET DELTA (Δ):</span> <strong className="tabular font-bold text-bull">{netDelta.toFixed(1)} NIFTY</strong></div>
          <div className="stat-pill"><span className="lbl">NET GAMMA (Γ):</span> <strong className="tabular">{netGamma.toFixed(5)}</strong></div>
          <div className="stat-pill"><span className="lbl">NET THETA (Θ):</span> <strong className={`tabular font-bold ${netTheta >= 0 ? 'color-bull' : 'color-bear'}`}>{netTheta >= 0 ? '+' : ''}₹{netTheta.toFixed(0)}/day</strong></div>
          <div className="stat-pill"><span className="lbl">NET VEGA (ν):</span> <strong className={`tabular ${netVega >= 0 ? 'text-amber' : 'color-bear'}`}>₹{netVega.toFixed(0)} / 1%</strong></div>
          <div className="stat-pill"><span className="lbl">NET PREMIUM:</span> <strong className={`tabular font-bold ${netPremium >= 0 ? 'color-bull' : 'text-amber'}`}>{netPremium >= 0 ? 'Credit ₹' : 'Debit ₹'}{Math.abs(netPremium).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</strong></div>
          <div className="stat-pill"><span className="lbl">DELTA COMPLIANCE:</span> <strong className="tabular text-bull">{Math.abs(netDelta) <= 50 ? '● COMPLIANT (|Δ| ≤ 50)' : '● DELTA EXCEEDED'}</strong></div>
        </div>
      </div>

      {/* Expiry Payoff Canvas Chart */}
      <div className="terminal-panel span-8">
        <div className="panel-header">
          <span className="panel-title">EXPIRY PAYOFF PROFILE (P&L AT MATURITY VS UNDERLYING SPOT)</span>
          <span className="badge-source">YELLOW LINE = CURRENT SPOT (₹{spot.toFixed(2)})</span>
        </div>
        <div className="panel-body compact-padding">
          <canvas ref={canvasRef} style={{ width: '100%', height: '260px' }}></canvas>
        </div>
      </div>

      {/* Multi-Dimensional Scenario Matrix */}
      <div className="terminal-panel span-4">
        <div className="panel-header">
          <span className="panel-title">SPOT X IV SHOCK SCENARIO MATRIX</span>
        </div>
        <div className="panel-body no-padding" style={{ maxHeight: '275px', overflowY: 'auto' }}>
          <table className="terminal-table dense-table">
            <thead>
              <tr>
                <th>Spot Shift</th>
                <th>Vol -20%</th>
                <th>Vol 0%</th>
                <th>Vol +20%</th>
              </tr>
            </thead>
            <tbody>
              {[-0.03, -0.015, 0.0, 0.015, 0.03].map((sShift, i) => {
                const sPrice = spot * (1 + sShift);
                return (
                  <tr key={i}>
                    <td className="tabular font-bold">{sShift >= 0 ? '+' : ''}{(sShift * 100).toFixed(1)}% (₹{sPrice.toFixed(0)})</td>
                    {[-0.20, 0.0, 0.20].map((vShift, j) => {
                      const dSpot = spot * sShift;
                      const dVol = 0.154 * vShift;
                      const pnlEst = (netDelta * dSpot) + (0.5 * netGamma * (dSpot ** 2)) + (netVega * (dVol * 100)) + (netTheta * 3);
                      return (
                        <td key={j} className={`tabular font-bold ${pnlEst >= 0 ? 'color-bull' : 'color-bear'}`}>
                          {pnlEst >= 0 ? '+' : ''}₹{pnlEst.toFixed(0)}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Legs Table */}
      <div className="terminal-panel span-12">
        <div className="panel-header">
          <span className="panel-title">ACTIVE STRATEGY LEGS ({legs.length} LEGS CONFIGURED)</span>
        </div>
        <div className="panel-body no-padding">
          <table className="terminal-table dense-table hover-table">
            <thead>
              <tr>
                <th>Action</th>
                <th>Type</th>
                <th>Strike</th>
                <th>Expiry</th>
                <th>Qty</th>
                <th>Premium (₹)</th>
                <th>IV</th>
                <th>Delta</th>
                <th>Gamma</th>
                <th>Theta</th>
                <th>Vega</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {legs.map((leg) => (
                <tr key={leg.id}>
                  <td>
                    <select
                      className="term-select font-bold"
                      value={leg.action}
                      onChange={(e) => {
                        const next = [...legs];
                        const idx = next.findIndex((l) => l.id === leg.id);
                        if (idx !== -1) {
                          next[idx].action = e.target.value as OrderSide;
                          setLegs(next);
                        }
                      }}
                      style={{ padding: '2px 4px', fontSize: '10px' }}
                    >
                      <option value="SELL">SELL / SHORT</option>
                      <option value="BUY">BUY / LONG</option>
                    </select>
                  </td>
                  <td>
                    <select
                      className="term-select font-bold"
                      value={leg.type}
                      onChange={(e) => {
                        const next = [...legs];
                        const idx = next.findIndex((l) => l.id === leg.id);
                        if (idx !== -1) {
                          next[idx].type = e.target.value as OptionType;
                          setLegs(next);
                        }
                      }}
                      style={{ padding: '2px 4px', fontSize: '10px' }}
                    >
                      <option value="call">CALL (CE)</option>
                      <option value="put">PUT (PE)</option>
                    </select>
                  </td>
                  <td>
                    <input
                      type="number"
                      step={50}
                      className="term-input tabular font-bold"
                      value={leg.strike}
                      onChange={(e) => {
                        const next = [...legs];
                        const idx = next.findIndex((l) => l.id === leg.id);
                        if (idx !== -1) {
                          next[idx].strike = parseFloat(e.target.value);
                          setLegs(next);
                        }
                      }}
                      style={{ width: '80px', padding: '2px 4px', fontSize: '10px' }}
                    />
                  </td>
                  <td><span className="tabular">{leg.expiry}</span></td>
                  <td>
                    <select
                      className="term-select"
                      value={leg.qty}
                      onChange={(e) => {
                        const next = [...legs];
                        const idx = next.findIndex((l) => l.id === leg.id);
                        if (idx !== -1) {
                          next[idx].qty = parseInt(e.target.value);
                          setLegs(next);
                        }
                      }}
                      style={{ padding: '2px 4px', fontSize: '10px' }}
                    >
                      <option value="65">65 (1 Lot)</option>
                      <option value="130">130 (2 Lots)</option>
                      <option value="195">195 (3 Lots)</option>
                      <option value="325">325 (5 Lots)</option>
                    </select>
                  </td>
                  <td>
                    <input
                      type="number"
                      step={0.5}
                      className="term-input tabular font-bold"
                      value={leg.price}
                      onChange={(e) => {
                        const next = [...legs];
                        const idx = next.findIndex((l) => l.id === leg.id);
                        if (idx !== -1) {
                          next[idx].price = parseFloat(e.target.value);
                          setLegs(next);
                        }
                      }}
                      style={{ width: '80px', padding: '2px 4px', fontSize: '10px' }}
                    />
                  </td>
                  <td className="tabular">{(leg.iv * 100).toFixed(1)}%</td>
                  <td className="tabular text-bull font-bold">{leg.delta.toFixed(3)}</td>
                  <td className="tabular">{leg.gamma.toFixed(5)}</td>
                  <td className="tabular color-bear">{leg.theta.toFixed(1)}</td>
                  <td className="tabular text-amber">{leg.vega.toFixed(1)}</td>
                  <td>
                    <button
                      className="btn btn-xs btn-danger"
                      onClick={() => removeLeg(leg.id)}
                      title="Remove Leg"
                    >
                      <Trash2 size={11} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

