/**
 * Terminal Global Configuration & Constants
 */

export const API_BASE = window.location.origin;
export const WS_BASE = (window.location.protocol === 'https:' ? 'wss://' : 'ws://') + window.location.host;

export const THEME_STORAGE_KEY = 'bloomberg_terminal_theme';
export const DENSITY_STORAGE_KEY = 'bloomberg_terminal_density';

export const COLORS = {
  bgPrimary: '#080b11',
  bgSecondary: '#0d111a',
  bgCard: '#111724',
  border: '#1f293d',
  borderHighlight: '#334155',
  textPrimary: '#f8fafc',
  textSecondary: '#94a3b8',
  textMuted: '#64748b',
  
  // Institutional Financial Semantics
  bullish: '#00e676',   // Underpriced / Profit / Positive
  bearish: '#ff5252',   // Overpriced / Loss / Negative
  warning: '#f59e0b',   // Dislocation / Notice
  analytical: '#38bdf8',// Neutral analytics / Delta / IV
  model: '#a855f7',     // EGARCH / Quant signals
  terminalAmber: '#ff9800', // Bloomberg brand accent / ATM highlight
};

export const ROUTES = [
  // MARKET
  { id: 'overview', label: 'Overview', category: 'MARKET', shortcut: '1' },
  { id: 'nifty-chart', label: 'NIFTY Chart', category: 'MARKET' },
  { id: 'market-depth', label: 'Market Depth', category: 'MARKET' },

  // OPTIONS
  { id: 'option-chain', label: 'Option Chain', category: 'OPTIONS', shortcut: '2' },
  { id: 'option-scanner', label: 'Option Scanner', category: 'OPTIONS' },
  { id: 'greeks-surface', label: 'Greeks Terminal', category: 'OPTIONS' },
  { id: 'iv-surface', label: 'IV Surface 3D', category: 'OPTIONS' },
  { id: 'dislocation-surface', label: 'Volatility Surface', category: 'OPTIONS' },

  // QUANT
  { id: 'volatility-cockpit', label: 'Volatility Cockpit', category: 'QUANT' },
  { id: 'egarch-model', label: 'EGARCH Model', category: 'QUANT' },
  { id: 'realized-vol', label: 'Realized Vol & TCI', category: 'QUANT' },
  { id: 'hmm-regime', label: 'HMM Regime Monitor', category: 'QUANT' },
  { id: 'vrp-terminal', label: 'VRP Terminal', category: 'QUANT' },
  { id: 'mispricing-scanner', label: 'Mispricing & M-Score', category: 'QUANT', shortcut: '3' },

  // STRATEGIES
  { id: 'strategy-signals', label: 'Signals & Insights', category: 'STRATEGIES' },
  { id: 'strategy-builder', label: 'Strategy Builder', category: 'STRATEGIES', shortcut: '4' },
  { id: 'payoff-matrix', label: 'Scenario Matrix', category: 'STRATEGIES' },

  // PORTFOLIO
  { id: 'portfolio-positions', label: 'Positions & P&L', category: 'PORTFOLIO', shortcut: '5' },
  { id: 'portfolio-risk', label: 'Risk & Stress Tests', category: 'PORTFOLIO' },

  // BACKTEST
  { id: 'backtest-overview', label: 'Walk-Forward Backtest', category: 'BACKTEST', shortcut: '6' },
  { id: 'trade-replay', label: 'Trade Replay Engine', category: 'BACKTEST' },

  // RESEARCH
  { id: 'research-workbench', label: 'Research Workbench', category: 'RESEARCH' },

  // SYSTEM
  { id: 'data-monitor', label: 'Data Monitor', category: 'SYSTEM' },
  { id: 'model-monitor', label: 'Model Diagnostics', category: 'SYSTEM' },
  { id: 'alerts-feed', label: 'Alert Center', category: 'SYSTEM' },
];
