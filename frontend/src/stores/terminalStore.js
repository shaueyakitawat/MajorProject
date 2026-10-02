/**
 * Institutional Terminal Reactive Central Store
 * Implements observer pub/sub pattern for ultra-fast, zero-dependency updates.
 */

import { THEME_STORAGE_KEY, DENSITY_STORAGE_KEY } from '../config.js';

class TerminalStore {
  constructor() {
    this.subscribers = new Set();

    this.state = {
      // Navigation & Layout
      activeRoute: 'overview',
      theme: localStorage.getItem(THEME_STORAGE_KEY) || 'dark',
      density: localStorage.getItem(DENSITY_STORAGE_KEY) || 'compact',
      sidebarCollapsed: false,
      commandPaletteOpen: false,
      evaluationModalOpen: false,
      evaluationStep: 0,
      activeDrawerOption: null, // If set, opens right-hand detail drawer

      // Market Top-Bar State
      niftySpot: 22421.95,
      niftyOpen: 22380.00,
      niftyHigh: 22480.50,
      niftyLow: 22350.10,
      niftyPrevClose: 22390.00,
      niftyChange: 31.95,
      niftyChangePct: 0.14,
      niftyVolume: 345000000,
      niftyVWAP: 22415.20,
      nifty52wHigh: 26277.35,
      nifty52wLow: 18837.85,
      indiaVix: 13.82,
      indiaVixChange: -0.32,
      regime: 'NORMAL_VOL',
      regimeConfidence: 0.84,
      atmStrike: 22400,
      selectedExpiry: '2026-10-16',
      secondExpiry: '2026-10-30',
      availableExpiries: ['2026-10-16', '2026-10-23', '2026-10-30'],
      timeframe: 'daily',
      tradingHorizon: 'positional',

      // Volatility & Models
      forecastVolatility: 0.1420,
      realizedVolDaily: 0.1394,
      realizedVol5m: 0.1342,
      realizedVol15m: 0.1387,
      realizedVol1h: 0.1411,
      finalModelVol: 0.1461,
      marketIv: 0.1583,
      currentVrp: 0.0146,
      expectedVrp: 0.0150,
      tci: 0.00034,
      bsFairPrice: 92.65,
      marketPrice: 303.01,
      mispricingDeviation: 2.27,
      mScore: 3.74,
      zScore: 1.82,

      // Options Grid State
      optionChain: [],
      chainLoading: false,
      chainFilters: {
        type: 'BOTH', // 'CE' | 'PE' | 'BOTH'
        strikeRange: 15, // ATM +/- strikes
        minOI: 0,
        minVolume: 0,
        maxSpreadPct: 15.0,
        minMScore: 0.0,
        mispricingClass: 'ALL', // 'ALL' | 'underpriced' | 'fair' | 'overpriced'
        regimeFilter: 'ALL',
      },

      // Strategy
      activeSignal: null,
      strategyBuilderLegs: [
        { id: 1, action: 'sell', type: 'call', strike: 22400, expiry: '2026-10-16', qty: 50, price: 303.00, iv: 0.158, delta: 0.52, gamma: 0.0004, theta: -12.5, vega: 18.2 },
        { id: 2, action: 'sell', type: 'put', strike: 22400, expiry: '2026-10-16', qty: 50, price: 225.30, iv: 0.155, delta: -0.48, gamma: 0.0004, theta: -11.8, vega: 18.1 },
      ],

      // Portfolio
      portfolioPositions: [],
      portfolioGreeks: { delta: 2.1, gamma: 0.024, theta: -142.5, vega: 36.4, rho: 12.0 },
      portfolioPnL: { realized: 14250, unrealized: 6850, total: 21100, marginUsed: 385000 },

      // Backtest & Trade Replay
      backtestSummary: null,
      backtestTradeLog: [],
      activeReplayTrade: null,
      replayStepIndex: 0,
      isReplaying: false,

      // System Health & Latency
      systemStatus: {
        data: 'LIVE',
        api: 'CONNECTED',
        model: 'READY',
        ws: 'CONNECTED',
        db: 'CONNECTED',
        latencyMs: 18,
        lastTickTime: new Date().toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour12: false }),
        lastUpdateEpoch: Date.now(),
        serverRequestsCount: 14,
        serverErrorsCount: 0,
      },

      // Alerts
      alerts: [
        { id: 'alt-1', timestamp: '10:41:02', severity: 'WARNING', category: 'MSCORE', instrument: 'NIFTY 22400 CE', reason: 'M-Score +3.74σ exceeded threshold 2.5σ', value: '+3.74σ', threshold: '2.50σ' },
        { id: 'alt-2', timestamp: '10:35:18', severity: 'INFO', category: 'VRP', instrument: 'NIFTY ATM Pair', reason: 'VRP widened to +1.46 vol pts', value: '+1.46%', threshold: '1.00%' },
        { id: 'alt-3', timestamp: '09:15:00', severity: 'INFO', category: 'REGIME', instrument: 'NSE Index', reason: 'Market opened in NORMAL_VOL regime', value: 'NORMAL', threshold: '--' }
      ]
    };
  }

  getState() {
    return this.state;
  }

  setState(partialState) {
    this.state = { ...this.state, ...partialState };
    this.notify();
  }

  subscribe(callback) {
    this.subscribers.add(callback);
    return () => this.subscribers.delete(callback);
  }

  notify() {
    for (const callback of this.subscribers) {
      try {
        callback(this.state);
      } catch (err) {
        console.error('TerminalStore subscriber error:', err);
      }
    }
  }

  setActiveRoute(routeId) {
    this.setState({ activeRoute: routeId });
  }

  toggleTheme() {
    const nextTheme = this.state.theme === 'dark' ? 'light' : 'dark';
    localStorage.setItem(THEME_STORAGE_KEY, nextTheme);
    document.documentElement.setAttribute('data-theme', nextTheme);
    this.setState({ theme: nextTheme });
  }

  toggleDensity() {
    const nextDensity = this.state.density === 'compact' ? 'normal' : 'compact';
    localStorage.setItem(DENSITY_STORAGE_KEY, nextDensity);
    document.documentElement.setAttribute('data-density', nextDensity);
    this.setState({ density: nextDensity });
  }

  openOptionDetail(option) {
    this.setState({ activeDrawerOption: option });
  }

  closeOptionDetail() {
    this.setState({ activeDrawerOption: null });
  }

  setCommandPalette(open) {
    this.setState({ commandPaletteOpen: open });
  }

  setEvaluationModal(open, step = 0) {
    this.setState({ evaluationModalOpen: open, evaluationStep: step });
  }

  addAlert(alert) {
    this.setState({ alerts: [alert, ...this.state.alerts.slice(0, 99)] });
  }
}

export const terminalStore = new TerminalStore();
