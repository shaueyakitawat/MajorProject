/**
 * QuantLens Terminal — Top Global Terminal Header
 * Persistent command bar with global selectors, live market tickers, feed provenance, and system status.
 */

import React, { useEffect, useState } from 'react';
import { useTerminalStore } from '../stores/terminalStore';
import { Search, ShieldAlert, Moon, Sun, SlidersHorizontal } from 'lucide-react';
import { Timeframe } from '../types';

export const Header: React.FC = () => {
  const store = useTerminalStore();
  const [istTime, setIstTime] = useState('');

  useEffect(() => {
    const updateTime = () => {
      setIstTime(
        new Date().toLocaleTimeString('en-IN', {
          timeZone: 'Asia/Kolkata',
          hour12: false,
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
        }) + ' IST'
      );
    };
    updateTime();
    const timer = setInterval(updateTime, 1000);
    return () => clearInterval(timer);
  }, []);

  const m = store.marketData;
  const isBull = m.change >= 0;
  const changeColor = isBull ? 'color-bull' : 'color-bear';
  const changeSign = isBull ? '+' : '';

  return (
    <div className="topbar-inner">
      {/* Brand & Global Search */}
      <div className="topbar-section brand-group">
        <span className="terminal-brand-tag">⚡ QUANTLENS</span>
        <button
          className="terminal-cmd-btn"
          onClick={() => store.setCommandPalette(true)}
          title="Open Command Palette (Ctrl+K / Cmd+K)"
        >
          <Search size={13} className="cmd-icon" />
          <span className="cmd-text">SEARCH / CMD</span>
          <kbd className="kbd-hint">Ctrl+K</kbd>
        </button>
      </div>

      {/* Global Instrument & Expiry Selectors */}
      <div className="topbar-section context-selectors" style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
        <select
          className="term-select font-bold"
          value={store.selectedInstrument}
          onChange={(e) => store.setSelectedInstrument(e.target.value)}
          title="Select Target Underlying Index"
          style={{ padding: '3px 6px', fontSize: '11px', height: '24px' }}
        >
          <option value="NIFTY">NIFTY 50</option>
          <option value="BANKNIFTY">BANK NIFTY</option>
        </select>

        <select
          className="term-select"
          value={store.selectedExpiry}
          onChange={(e) => store.setSelectedExpiry(e.target.value)}
          title="Global Option Expiry"
          style={{ padding: '3px 6px', fontSize: '11px', height: '24px' }}
        >
          {store.availableExpiries.map((exp) => (
            <option key={exp} value={exp}>
              {exp}
            </option>
          ))}
        </select>

        <div className="btn-group-timeframe" style={{ display: 'flex', gap: '2px' }}>
          {(['1m', '5m', '15m', '1h', '1d'] as Timeframe[]).map((tf) => (
            <button
              key={tf}
              className={`tf-btn ${store.selectedTimeframe === tf ? 'active' : ''}`}
              onClick={() => store.setSelectedTimeframe(tf)}
              style={{ padding: '2px 6px', fontSize: '10px', height: '24px' }}
            >
              {tf.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      {/* Live Financial Ticker Strip */}
      <div className="topbar-section ticker-strip">
        {/* NIFTY 50 Spot */}
        <div className="ticker-item" title="NIFTY 50 Spot Index">
          <span className="ticker-label">NIFTY 50</span>
          <span className="ticker-val tabular font-bold">
            {m.spot.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </span>
          <span className={`ticker-delta ${changeColor} tabular`}>
            {changeSign}
            {m.change.toFixed(2)} ({changeSign}
            {m.changePct.toFixed(2)}%)
          </span>
        </div>

        <div className="ticker-sep">│</div>

        {/* INDIA VIX */}
        <div className="ticker-item" title="India Volatility Index">
          <span className="ticker-label">INDIA VIX</span>
          <span className="ticker-val tabular">{m.indiaVix.toFixed(2)}</span>
        </div>

        <div className="ticker-sep">│</div>

        {/* REGIME */}
        <div className="ticker-item" title="Gaussian HMM Volatility Regime Gatekeeper">
          <span className="ticker-label">REGIME</span>
          <span className={`regime-badge badge-${m.regime.toLowerCase().replace('_vol', '')}`}>
            {m.regime.replace('_', ' ')}
          </span>
        </div>

        <div className="ticker-sep">│</div>

        {/* ATM Strike */}
        <div className="ticker-item" title="At-The-Money Benchmark Strike">
          <span className="ticker-label">ATM</span>
          <span className="ticker-val tabular text-amber font-bold">{m.atmStrike}</span>
        </div>
      </div>

      {/* Provenance & Status Controls */}
      <div className="topbar-section control-group">
        {/* Feed Provenance Badge */}
        <div
          className="status-badge-item"
          title={m.isSimulated ? 'Simulation Replay Mode Active' : 'Live Real Exchange Feed (pnsea)'}
        >
          <span className={`status-led ${m.isSimulated ? 'led-amber' : 'led-green'}`}></span>
          <span className="status-badge-label font-bold">
            FEED: {m.feedMode.replace('_', ' ')}
          </span>
        </div>

        <div className="status-badge-item" title="FastAPI Backend Health">
          <span className={`status-led ${store.systemHealth.api === 'CONNECTED' ? 'led-green' : 'led-red'}`}></span>
          <span className="status-badge-label">API: {store.systemHealth.api}</span>
        </div>

        {/* IST Live Clock */}
        <div className="clock-display" title="Indian Standard Time">
          <span className="clock-time tabular">{istTime}</span>
        </div>

        {/* Kill Switch Toggle */}
        <button
          className={`topbar-action-btn ${store.killSwitchActive ? 'btn-danger active' : ''}`}
          onClick={() => {
            if (
              confirm(
                store.killSwitchActive
                  ? 'Re-enable automated execution?'
                  : 'ACTIVATING KILL SWITCH: Immediately halts all automated paper order execution. Confirm?'
              )
            ) {
              store.toggleKillSwitch();
            }
          }}
          title="Emergency Execution Kill Switch"
          style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '11px', fontWeight: 700 }}
        >
          <ShieldAlert size={12} />
          <span>{store.killSwitchActive ? 'HALTED' : 'KILL SWITCH'}</span>
        </button>

        {/* Density Toggle */}
        <button
          className="topbar-action-btn icon-only"
          onClick={store.toggleDensity}
          title="Toggle Display Density"
        >
          <SlidersHorizontal size={12} />
        </button>

        {/* Theme Toggle */}
        <button
          className="topbar-action-btn icon-only"
          onClick={store.toggleTheme}
          title="Toggle Dark / Light Theme"
        >
          {store.theme === 'dark' ? <Moon size={12} /> : <Sun size={12} />}
        </button>
      </div>
    </div>
  );
};

