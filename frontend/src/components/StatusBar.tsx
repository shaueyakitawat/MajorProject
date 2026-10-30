/**
 * QuantLens Terminal — Bottom Sticky Status Bar
 * Displays low-level network latency, persistent SQLite connection, and research telemetry.
 */

import React from 'react';
import { useTerminalStore } from '../stores/terminalStore';

export const StatusBar: React.FC = () => {
  const store = useTerminalStore();
  const h = store.systemHealth;

  return (
    <div className="statusbar-inner" style={{ display: 'flex', justifyContent: 'space-between', padding: '0 12px', height: '22px', fontSize: '10px', alignItems: 'center' }}>
      <div className="statusbar-left" style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
        <div className="status-item">
          <span className="lbl text-muted">SYSTEM:</span>{' '}
          <strong className="text-bull">● {h.api}</strong>
        </div>
        <div className="status-item">
          <span className="lbl text-muted">DATABASE:</span>{' '}
          <strong className="text-amber">● SQLITE WAL (Active Ledger)</strong>
        </div>
        <div className="status-item">
          <span className="lbl text-muted">FEED:</span>{' '}
          <strong className={store.marketData.feedMode === 'NSE_LIVE' ? 'text-bull' : 'text-amber'}>
            ● {store.marketData.feedMode || 'NSE_LIVE'}
          </strong>
        </div>
        <div className="status-item">
          <span className="lbl text-muted">LATENCY:</span>{' '}
          <strong className="font-mono">{h.latencyMs} ms</strong>
        </div>
      </div>

      <div className="statusbar-right" style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
        <div className="status-item">
          <span className="lbl text-muted">EXECUTION SAFETY:</span>{' '}
          <strong className={store.killSwitchActive ? 'color-bear' : 'text-bull'}>
            {store.killSwitchActive ? '● KILL SWITCH ENGAGED' : '● NOMINAL'}
          </strong>
        </div>
        <div className="status-item">
          <span className="lbl text-muted">ENVIRONMENT:</span>{' '}
          <span className="text-amber font-mono font-bold">PAPER TRADING / IEEE TRANSACTIONS</span>
        </div>
        <div className="status-item text-muted">
          <span>TICK TIME: {new Date(store.marketData.timestamp).toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour12: false })} IST</span>
        </div>
      </div>
    </div>
  );
};

