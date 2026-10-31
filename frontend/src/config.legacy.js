/**
 * Terminal Global Configuration & Constants
 */

export const API_BASE = window.location.port === '3000'
  ? `${window.location.protocol}//${window.location.hostname}:8000`
  : window.location.origin;

export const WS_BASE = (window.location.protocol === 'https:' ? 'wss://' : 'ws://') + 
  (window.location.port === '3000' ? `${window.location.hostname}:8000` : window.location.host);

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
  { id: 'dashboard', label: 'Live Dashboard (Capital & PnL)', category: 'PORTFOLIO', shortcut: '1', icon: '📊' },
  { id: 'live-terminal', label: 'Live Execution Terminal', category: 'EXECUTION', shortcut: '2', icon: '⚡' },
  { id: 'option-chain', label: 'Option Chain & Greeks', category: 'OPTIONS', shortcut: '3', icon: '📈' },
  { id: 'ledger', label: 'Historical Trade Ledger', category: 'AUDIT', shortcut: '4', icon: '📜' },
  { id: 'pipeline-flow', label: 'Visual Pipeline & Health', category: 'PIPELINE', shortcut: '5', icon: '🔄' },
  { id: 'volatility-surfaces', label: 'Volatility Surfaces & News', category: 'ANALYTICS', shortcut: '6', icon: '🌐' },
  { id: 'mispricing-scanner', label: 'Mispricing Opportunities', category: 'ALPHA', shortcut: '7', icon: '🎯' },
];
