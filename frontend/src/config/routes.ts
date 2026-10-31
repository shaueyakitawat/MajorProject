/**
 * QuantLens Terminal — Workspaces & Navigation Routes
 * Exact 12 Institutional Workspaces required by Master Prompt.
 */

import { WorkspaceId } from '../types';

export interface RouteConfig {
  id: WorkspaceId;
  label: string;
  category: 'CORE' | 'OPTIONS' | 'RESEARCH' | 'EXECUTION' | 'OPERATIONS';
  shortcut: string;
  iconName: string;
  badge?: string;
  description: string;
}

export const WORKSPACES: RouteConfig[] = [
  {
    id: 'overview',
    label: 'Market Overview',
    category: 'CORE',
    shortcut: '1',
    iconName: 'LayoutDashboard',
    description: 'NIFTY spot, real-time capital P&L, candlestick chart, vol dynamics, and active book'
  },
  {
    id: 'option-chain',
    label: 'Options Chain',
    category: 'OPTIONS',
    shortcut: '2',
    iconName: 'Grid',
    description: 'Symmetrical split grid, ATM highlight, analytical Greeks, M-Scores, and CSV export'
  },
  {
    id: 'volatility-lab',
    label: 'Volatility Lab',
    category: 'RESEARCH',
    shortcut: '3',
    iconName: 'Activity',
    description: '3D Volatility Surfaces, 2D Smiles, HMM transition matrix, Q-Q plots, and term structure'
  },
  {
    id: 'mispricing-scanner',
    label: 'Mispricing Scanner',
    category: 'OPTIONS',
    shortcut: '4',
    iconName: 'Crosshair',
    description: 'Full-chain statistical dislocation ranking, M-Score filter, and 1-click DMA execution'
  },
  {
    id: 'strategy-lab',
    label: 'Strategy Lab',
    category: 'OPTIONS',
    shortcut: '5',
    iconName: 'Cpu',
    description: 'Multi-leg options builder, expiry payoff diagrams, Greeks sensitivity, and spot-IV scenario matrix'
  },
  {
    id: 'backtesting',
    label: 'Backtesting & Research',
    category: 'RESEARCH',
    shortcut: '6',
    iconName: 'FlaskConical',
    description: 'Walk-forward simulation engine, equity curve, Sharpe/Sortino ratios, and trade log'
  },
  {
    id: 'market-monitor',
    label: 'Live Market Monitor',
    category: 'CORE',
    shortcut: '7',
    iconName: 'Radio',
    description: 'Real-time provider feed observation, quote age, latency distribution, and feed mode'
  },
  {
    id: 'paper-terminal',
    label: 'Paper Trading Terminal',
    category: 'EXECUTION',
    shortcut: '8',
    iconName: 'Terminal',
    description: 'Direct Market Access (DMA) Order Ticket, instant SQLite commit, active positions, and square-off'
  },
  {
    id: 'historical-ledger',
    label: 'Historical Trade Ledger',
    category: 'EXECUTION',
    shortcut: '9',
    iconName: 'BookOpen',
    description: '903+ trade audited ledger from SQLite, date session filtering, pagination, and equity progression'
  },
  {
    id: 'risk-portfolio',
    label: 'Risk & Portfolio',
    category: 'OPERATIONS',
    shortcut: '0',
    iconName: 'ShieldAlert',
    description: 'Aggregate portfolio Greeks, Delta-neutral compliance, spot/vol stress testing, and loss limits'
  },
  {
    id: 'pipeline-operations',
    label: 'Data & Model Operations',
    category: 'OPERATIONS',
    shortcut: '-',
    iconName: 'Workflow',
    description: 'Interactive 8-stage pipeline DAG, live telemetry, LaTeX governing formulas, and vol shock simulator'
  },
  {
    id: 'model-registry',
    label: 'Model Registry & Validation',
    category: 'RESEARCH',
    shortcut: '=',
    iconName: 'Archive',
    description: 'Auditable specifications for all 7 quantitative models, parameters, formulas, and IEEE metadata'
  }
];

