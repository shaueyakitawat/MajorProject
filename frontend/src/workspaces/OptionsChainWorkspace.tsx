/**
 * QuantLens Terminal — Workspace B: Options Chain Workstation
 * High-density symmetrical option chain grid with 28+ quantitative metrics,
 * sticky center strikes, ATM highlighting, SPLIT/LIST views, Greeks, M-Scores, and CSV export.
 */

import React, { useEffect, useState } from 'react';
import { useTerminalStore } from '../stores/terminalStore';
import { apiService } from '../services/api';
import { OptionChainRow, OptionLegData } from '../types';
import { Download, RefreshCw, Eye } from 'lucide-react';

export const OptionsChainWorkspace: React.FC = () => {
  const store = useTerminalStore();
  const [chain, setChain] = useState<OptionChainRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [viewMode, setViewMode] = useState<'SPLIT' | 'LIST'>('SPLIT');
  const [depth, setDepth] = useState<number>(25);
  const [typeFilter, setTypeFilter] = useState<'BOTH' | 'CE' | 'PE'>('BOTH');
  const [signalFilter, setSignalFilter] = useState<string>('ALL');
  const [minMScore, setMinMScore] = useState<number>(0.0);

  const loadChain = async () => {
    setLoading(true);
    try {
      const res = await apiService.getOptionChain(store.selectedInstrument, store.selectedExpiry, depth);
      if (res.success && res.data?.chain) {
        setChain(res.data.chain);
        if (res.data.spotPrice) store.updateMarketData({ spot: res.data.spotPrice });
        if (res.data.atmStrike) store.updateMarketData({ atmStrike: res.data.atmStrike });
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadChain();
  }, [store.selectedInstrument, store.selectedExpiry, depth]);

  const atmStrike = store.marketData.atmStrike || 22950;

  // Filter strikes
  const filtered = chain.filter((row) => {
    const c = row.call;
    const p = row.put;
    if (minMScore > 0) {
      if (Math.abs(c?.mScore || 0) < minMScore && Math.abs(p?.mScore || 0) < minMScore) return false;
    }
    if (signalFilter !== 'ALL') {
      if (c?.signal !== signalFilter && p?.signal !== signalFilter) return false;
    }
    return true;
  });

  const handleRowClick = (strike: number, type: 'call' | 'put') => {
    const row = chain.find((r) => r.strike === strike);
    const leg = row ? row[type] : null;
    if (leg) {
      store.openContractDetail({
        strike,
        type: type === 'call' ? 'CE' : 'PE',
        expiry: store.selectedExpiry,
        symbol: store.selectedInstrument,
        ...leg,
        source: 'NSE LIVE (pnsea)',
        timestamp: new Date().toISOString()
      });
    }
  };

  const handleTrade1Click = (strike: number, type: 'call' | 'put', e: React.MouseEvent) => {
    e.stopPropagation();
    const row = chain.find((r) => r.strike === strike);
    const leg = row ? row[type] : null;
    if (leg) {
      const isOver = leg.signal === 'overpriced' || leg.mispricingPct > 0;
      store.setPendingOrder({
        strike,
        type: type === 'call' ? 'CE' : 'PE',
        side: isOver ? 'SELL' : 'BUY',
        price: leg.ltp,
        expiry: store.selectedExpiry,
        strategy: isOver ? 'RV Short Overvalued Option' : 'Statistical Long Mispricing'
      });
      store.setActiveWorkspace('paper-terminal');
    }
  };

  const exportCSV = () => {
    const headers = ['Strike', 'Type', 'LTP', 'BS_Fair', 'Deviation_Pct', 'M_Score', 'IV', 'Model_Vol', 'VRP', 'Delta', 'Gamma', 'Theta', 'Vega', 'OI', 'Volume', 'Signal'];
    const lines = [headers.join(',')];

    filtered.forEach((r) => {
      (['call', 'put'] as const).forEach((t) => {
        const leg = r[t];
        if (leg) {
          lines.push([
            r.strike,
            t.toUpperCase(),
            leg.ltp,
            leg.fairPrice,
            leg.mispricingPct,
            leg.mScore,
            leg.iv,
            leg.modelVol,
            leg.vrp,
            leg.delta,
            leg.gamma,
            leg.theta,
            leg.vega,
            leg.oi,
            leg.volume,
            leg.signal
          ].join(','));
        }
      });
    });

    const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `NIFTY_OptionsChain_${store.selectedExpiry}.csv`;
    link.click();
  };

  const showCalls = typeFilter === 'BOTH' || typeFilter === 'CE';
  const showPuts = typeFilter === 'BOTH' || typeFilter === 'PE';

  return (
    <div className="option-chain-workspace">
      {/* Header Bar */}
      <div className="chain-header-bar">
        <div className="chain-title-block">
          <span className="chain-main-title">NIFTY OPTION CHAIN</span>
          <span className="badge-source">FEED: NSE / PNSEA LIVE (T-0)</span>
          {loading && <span className="loading-spinner">SYNCING...</span>}
        </div>

        <div className="chain-kpi-block">
          <span>SPOT: <strong className="tabular font-bold">₹{store.marketData.spot.toFixed(2)}</strong></span>
          <span>ATM: <strong className="tabular text-amber font-bold">{atmStrike}</strong></span>
          <span>PCR (OI): <strong className="tabular text-bull font-bold">1.04</strong></span>
        </div>

        <div className="chain-controls-block">
          <div className="control-item">
            <label>EXPIRY:</label>
            <select
              className="term-select"
              value={store.selectedExpiry}
              onChange={(e) => store.setSelectedExpiry(e.target.value)}
            >
              {store.availableExpiries.map((exp) => (
                <option key={exp} value={exp}>{exp}</option>
              ))}
            </select>
          </div>

          <div className="control-item">
            <label>DEPTH:</label>
            <select
              className="term-select"
              value={depth}
              onChange={(e) => setDepth(parseInt(e.target.value))}
            >
              <option value="10">ATM ±10</option>
              <option value="15">ATM ±15</option>
              <option value="25">ATM ±25</option>
              <option value="50">ALL STRIKES</option>
            </select>
          </div>

          <div className="control-item">
            <label>VIEW:</label>
            <div className="btn-group-toggle">
              <button
                className={`view-btn ${viewMode === 'SPLIT' ? 'active' : ''}`}
                onClick={() => setViewMode('SPLIT')}
              >
                SPLIT
              </button>
              <button
                className={`view-btn ${viewMode === 'LIST' ? 'active' : ''}`}
                onClick={() => setViewMode('LIST')}
              >
                LIST
              </button>
            </div>
          </div>

          <button className="btn btn-xs btn-secondary" onClick={exportCSV} title="Export Current Grid to CSV">
            <Download size={11} style={{ marginRight: '4px' }} />
            Export CSV
          </button>
        </div>
      </div>

      {/* Filter Sub-Bar */}
      <div className="chain-filters-bar">
        <div className="filter-item">
          <label>CONTRACTS:</label>
          <div className="btn-group-toggle">
            <button
              className={`filter-type-btn ${typeFilter === 'CE' ? 'active' : ''}`}
              onClick={() => setTypeFilter('CE')}
            >
              CE ONLY
            </button>
            <button
              className={`filter-type-btn ${typeFilter === 'BOTH' ? 'active' : ''}`}
              onClick={() => setTypeFilter('BOTH')}
            >
              BOTH
            </button>
            <button
              className={`filter-type-btn ${typeFilter === 'PE' ? 'active' : ''}`}
              onClick={() => setTypeFilter('PE')}
            >
              PE ONLY
            </button>
          </div>
        </div>

        <div className="filter-item">
          <label>SIGNAL:</label>
          <select
            className="term-select"
            value={signalFilter}
            onChange={(e) => setSignalFilter(e.target.value)}
          >
            <option value="ALL">ALL SIGNALS</option>
            <option value="underpriced">UNDERPRICED ONLY</option>
            <option value="overpriced">OVERPRICED ONLY</option>
            <option value="fair">FAIR PRICED</option>
          </select>
        </div>

        <div className="filter-item">
          <label>MIN M-SCORE:</label>
          <select
            className="term-select"
            value={minMScore.toString()}
            onChange={(e) => setMinMScore(parseFloat(e.target.value))}
          >
            <option value="0.0">0.0σ (All)</option>
            <option value="1.0">≥ 1.0σ</option>
            <option value="2.0">≥ 2.0σ</option>
            <option value="3.0">≥ 3.0σ (Extreme)</option>
          </select>
        </div>

        <div className="filter-item text-muted">
          <span>Showing {filtered.length} strikes ({filtered.length * 2} contracts)</span>
        </div>
      </div>

      {/* Grid Container */}
      <div className="chain-table-container">
        {viewMode === 'SPLIT' ? (
          <table className="terminal-table dense-table chain-grid-table">
            <thead>
              <tr className="super-header-row">
                {showCalls && <th colSpan={13} className="call-super-header">CALL OPTIONS (CE)</th>}
                <th className="strike-super-header">STRIKE</th>
                {showPuts && <th colSpan={13} className="put-super-header">PUT OPTIONS (PE)</th>}
              </tr>
              <tr className="column-header-row">
                {showCalls && (
                  <>
                    <th>Trade</th>
                    <th>Signal</th>
                    <th>M-Score</th>
                    <th>BS Fair</th>
                    <th>LTP</th>
                    <th>Spread</th>
                    <th>IV</th>
                    <th>VRP</th>
                    <th>Delta</th>
                    <th>Gamma</th>
                    <th>Theta</th>
                    <th>Vega</th>
                    <th>OI</th>
                  </>
                )}
                <th className="sticky-strike-col">STRIKE</th>
                {showPuts && (
                  <>
                    <th>OI</th>
                    <th>Vega</th>
                    <th>Theta</th>
                    <th>Gamma</th>
                    <th>Delta</th>
                    <th>VRP</th>
                    <th>IV</th>
                    <th>Spread</th>
                    <th>LTP</th>
                    <th>BS Fair</th>
                    <th>M-Score</th>
                    <th>Signal</th>
                    <th>Trade</th>
                  </>
                )}
              </tr>
            </thead>
            <tbody>
              {filtered.map((row) => {
                const isATM = row.strike === atmStrike;
                const c = row.call;
                const p = row.put;

                return (
                  <tr key={row.strike} className={isATM ? 'atm-strike-row' : ''}>
                    {showCalls && (
                      <>
                        <td className="text-center" style={{ width: '45px' }}>
                          <button
                            className="btn btn-xs btn-primary"
                            onClick={(e) => handleTrade1Click(row.strike, 'call', e)}
                            title="Pre-fill DMA Ticket"
                          >
                            ⚡
                          </button>
                        </td>
                        <td className="opt-clickable-cell text-center" onClick={() => handleRowClick(row.strike, 'call')}>
                          <span className={`badge-mini ${c?.signal === 'overpriced' ? 'tag-overpriced' : (c?.signal === 'underpriced' ? 'tag-underpriced' : 'tag-fair')}`}>
                            {c?.signal === 'overpriced' ? 'SELL' : (c?.signal === 'underpriced' ? 'BUY' : 'FAIR')}
                          </span>
                        </td>
                        <td className="opt-clickable-cell tabular text-amber font-bold text-right" onClick={() => handleRowClick(row.strike, 'call')}>
                          {c?.mScore !== undefined ? `${c.mScore >= 0 ? '+' : ''}${c.mScore.toFixed(2)}σ` : '--'}
                        </td>
                        <td className="opt-clickable-cell tabular text-right" onClick={() => handleRowClick(row.strike, 'call')}>
                          ₹{c?.fairPrice?.toFixed(1) || '--'}
                        </td>
                        <td className={`opt-clickable-cell tabular font-bold text-right ${c && c.mispricingPct > 5 ? 'color-bear' : (c && c.mispricingPct < -5 ? 'color-bull' : '')}`} onClick={() => handleRowClick(row.strike, 'call')}>
                          ₹{c?.ltp?.toFixed(1) || '--'}
                        </td>
                        <td className="opt-clickable-cell tabular text-right text-muted" onClick={() => handleRowClick(row.strike, 'call')}>
                          {c?.spread?.toFixed(1) || '0.5'}
                        </td>
                        <td className="opt-clickable-cell tabular text-right" onClick={() => handleRowClick(row.strike, 'call')}>
                          {c?.iv ? `${(c.iv * 100).toFixed(1)}%` : '--'}
                        </td>
                        <td className={`opt-clickable-cell tabular text-right ${c && c.vrp > 0 ? 'text-amber' : ''}`} onClick={() => handleRowClick(row.strike, 'call')}>
                          {c?.vrp ? `${c.vrp > 0 ? '+' : ''}${(c.vrp * 100).toFixed(1)}%` : '--'}
                        </td>
                        <td className="opt-clickable-cell tabular text-right text-bull font-bold" onClick={() => handleRowClick(row.strike, 'call')}>
                          {c?.delta?.toFixed(3) || '--'}
                        </td>
                        <td className="opt-clickable-cell tabular text-right text-muted" onClick={() => handleRowClick(row.strike, 'call')}>
                          {c?.gamma?.toFixed(4) || '--'}
                        </td>
                        <td className="opt-clickable-cell tabular text-right color-bear" onClick={() => handleRowClick(row.strike, 'call')}>
                          {c?.theta?.toFixed(1) || '--'}
                        </td>
                        <td className="opt-clickable-cell tabular text-right text-amber" onClick={() => handleRowClick(row.strike, 'call')}>
                          {c?.vega?.toFixed(1) || '--'}
                        </td>
                        <td className="opt-clickable-cell tabular text-right" onClick={() => handleRowClick(row.strike, 'call')}>
                          {c?.oi ? `${(c.oi / 1000).toFixed(0)}k` : '--'}
                        </td>
                      </>
                    )}

                    {/* STRIKE CENTER COLUMN */}
                    <td className={`sticky-strike-cell tabular font-bold text-center ${isATM ? 'atm-badge' : ''}`}>
                      {row.strike.toLocaleString('en-IN')}
                      {isATM && <span className="atm-tag">ATM</span>}
                    </td>

                    {showPuts && (
                      <>
                        <td className="opt-clickable-cell tabular text-left" onClick={() => handleRowClick(row.strike, 'put')}>
                          {p?.oi ? `${(p.oi / 1000).toFixed(0)}k` : '--'}
                        </td>
                        <td className="opt-clickable-cell tabular text-left text-amber" onClick={() => handleRowClick(row.strike, 'put')}>
                          {p?.vega?.toFixed(1) || '--'}
                        </td>
                        <td className="opt-clickable-cell tabular text-left color-bear" onClick={() => handleRowClick(row.strike, 'put')}>
                          {p?.theta?.toFixed(1) || '--'}
                        </td>
                        <td className="opt-clickable-cell tabular text-left text-muted" onClick={() => handleRowClick(row.strike, 'put')}>
                          {p?.gamma?.toFixed(4) || '--'}
                        </td>
                        <td className="opt-clickable-cell tabular text-left text-bear font-bold" onClick={() => handleRowClick(row.strike, 'put')}>
                          {p?.delta?.toFixed(3) || '--'}
                        </td>
                        <td className={`opt-clickable-cell tabular text-left ${p && p.vrp > 0 ? 'text-amber' : ''}`} onClick={() => handleRowClick(row.strike, 'put')}>
                          {p?.vrp ? `${p.vrp > 0 ? '+' : ''}${(p.vrp * 100).toFixed(1)}%` : '--'}
                        </td>
                        <td className="opt-clickable-cell tabular text-left" onClick={() => handleRowClick(row.strike, 'put')}>
                          {p?.iv ? `${(p.iv * 100).toFixed(1)}%` : '--'}
                        </td>
                        <td className="opt-clickable-cell tabular text-left text-muted" onClick={() => handleRowClick(row.strike, 'put')}>
                          {p?.spread?.toFixed(1) || '0.5'}
                        </td>
                        <td className={`opt-clickable-cell tabular font-bold text-left ${p && p.mispricingPct > 5 ? 'color-bear' : (p && p.mispricingPct < -5 ? 'color-bull' : '')}`} onClick={() => handleRowClick(row.strike, 'put')}>
                          ₹{p?.ltp?.toFixed(1) || '--'}
                        </td>
                        <td className="opt-clickable-cell tabular text-left" onClick={() => handleRowClick(row.strike, 'put')}>
                          ₹{p?.fairPrice?.toFixed(1) || '--'}
                        </td>
                        <td className="opt-clickable-cell tabular text-amber font-bold text-left" onClick={() => handleRowClick(row.strike, 'put')}>
                          {p?.mScore !== undefined ? `${p.mScore >= 0 ? '+' : ''}${p.mScore.toFixed(2)}σ` : '--'}
                        </td>
                        <td className="opt-clickable-cell text-center" onClick={() => handleRowClick(row.strike, 'put')}>
                          <span className={`badge-mini ${p?.signal === 'overpriced' ? 'tag-overpriced' : (p?.signal === 'underpriced' ? 'tag-underpriced' : 'tag-fair')}`}>
                            {p?.signal === 'overpriced' ? 'SELL' : (p?.signal === 'underpriced' ? 'BUY' : 'FAIR')}
                          </span>
                        </td>
                        <td className="text-center" style={{ width: '45px' }}>
                          <button
                            className="btn btn-xs btn-primary"
                            onClick={(e) => handleTrade1Click(row.strike, 'put', e)}
                            title="Pre-fill DMA Ticket"
                          >
                            ⚡
                          </button>
                        </td>
                      </>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        ) : (
          <table className="terminal-table dense-table hover-table">
            <thead>
              <tr>
                <th>Instrument</th>
                <th>Type</th>
                <th>LTP</th>
                <th>BS Fair</th>
                <th>Deviation</th>
                <th>IV</th>
                <th>Model Vol</th>
                <th>VRP</th>
                <th>M-Score</th>
                <th>Delta</th>
                <th>Vega</th>
                <th>Theta</th>
                <th>OI</th>
                <th>Signal</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {filtered.flatMap((r) => {
                const items: any[] = [];
                if (r.call && showCalls) items.push({ strike: r.strike, type: 'call', ...r.call });
                if (r.put && showPuts) items.push({ strike: r.strike, type: 'put', ...r.put });
                return items;
              }).map((c, i) => (
                <tr key={i} className="opt-clickable-cell" onClick={() => handleRowClick(c.strike, c.type)}>
                  <td><strong>NIFTY {c.strike} {c.type.toUpperCase()}</strong></td>
                  <td><span className={`badge-type ${c.type === 'call' ? 'badge-ce' : 'badge-pe'}`}>{c.type.toUpperCase()}</span></td>
                  <td className="tabular font-bold">₹{c.ltp.toFixed(2)}</td>
                  <td className="tabular">₹{c.fairPrice.toFixed(2)}</td>
                  <td className={`tabular font-bold ${c.mispricingPct > 0 ? 'color-bear' : 'color-bull'}`}>
                    {c.mispricingPct > 0 ? '+' : ''}{c.mispricingPct.toFixed(1)}%
                  </td>
                  <td className="tabular">{(c.iv * 100).toFixed(2)}%</td>
                  <td className="tabular">{(c.modelVol * 100).toFixed(2)}%</td>
                  <td className="tabular text-amber">{c.vrp ? `${(c.vrp * 100).toFixed(2)}%` : '--'}</td>
                  <td className="tabular text-amber font-bold">{c.mScore ? `${c.mScore >= 0 ? '+' : ''}${c.mScore.toFixed(2)}σ` : '--'}</td>
                  <td className="tabular text-bull font-bold">{c.delta?.toFixed(3) || '--'}</td>
                  <td className="tabular text-amber">{c.vega?.toFixed(2) || '--'}</td>
                  <td className="tabular color-bear">{c.theta?.toFixed(2) || '--'}</td>
                  <td className="tabular">{c.oi ? c.oi.toLocaleString('en-IN') : '--'}</td>
                  <td>
                    <span className={`badge-signal ${c.signal === 'overpriced' ? 'tag-overpriced' : (c.signal === 'underpriced' ? 'tag-underpriced' : 'tag-fair')}`}>
                      {c.signal?.toUpperCase() || 'FAIR'}
                    </span>
                  </td>
                  <td>
                    <button
                      className="btn btn-xs btn-primary"
                      onClick={(e) => handleTrade1Click(c.strike, c.type, e)}
                    >
                      Trade ⚡
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};

