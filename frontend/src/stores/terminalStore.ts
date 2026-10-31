/**
 * QuantLens Terminal — Reactive Zustand Store
 * High-performance, zero-latency shared workstation state.
 */

import { create } from 'zustand';
import { WorkspaceId, Timeframe, FeedMode, ContractDetail, PaperTradeRecord, MarketQuote } from '../types';

interface SystemHealthState {
  api: 'CONNECTED' | 'DISCONNECTED' | 'ERROR';
  database: 'CONNECTED' | 'DISCONNECTED' | 'ERROR';
  marketFeed: 'LIVE' | 'STALE' | 'SIMULATED';
  models: 'READY' | 'COMPUTING' | 'ERROR';
  paperTrading: 'ACTIVE' | 'HALTED';
  latencyMs: number;
  lastTickIso: string;
  serverRequestsCount: number;
  serverErrorsCount: number;
}

interface TerminalState {
  // Navigation & Context
  activeWorkspace: WorkspaceId;
  selectedInstrument: string;
  selectedExpiry: string;
  secondExpiry: string;
  availableExpiries: string[];
  selectedTimeframe: Timeframe;
  
  // Market Topbar Data
  marketData: MarketQuote;
  systemHealth: SystemHealthState;
  
  // Inspection & Execution Context
  activeContract: ContractDetail | null;
  pendingOrder: {
    strike?: number;
    type?: string;
    side?: 'BUY' | 'SELL';
    price?: number;
    qty?: number;
    expiry?: string;
    strategy?: string;
  } | null;
  
  // Safety & Controls
  killSwitchActive: boolean;
  density: 'compact' | 'normal';
  theme: 'dark' | 'light';
  sidebarCollapsed: boolean;
  commandPaletteOpen: boolean;
  evaluationModalOpen: boolean;

  // Actions
  setActiveWorkspace: (id: WorkspaceId) => void;
  setSelectedExpiry: (exp: string) => void;
  setSelectedTimeframe: (tf: Timeframe) => void;
  setSelectedInstrument: (inst: string) => void;
  openContractDetail: (contract: ContractDetail) => void;
  closeContractDetail: () => void;
  setPendingOrder: (order: any) => void;
  toggleKillSwitch: () => void;
  toggleDensity: () => void;
  toggleTheme: () => void;
  toggleSidebar: () => void;
  setCommandPalette: (open: boolean) => void;
  setEvaluationModal: (open: boolean) => void;
  updateMarketData: (partial: Partial<MarketQuote>) => void;
  updateSystemHealth: (partial: Partial<SystemHealthState>) => void;
}

export const useTerminalStore = create<TerminalState>((set) => ({
  // Defaults
  activeWorkspace: 'overview',
  selectedInstrument: 'NIFTY',
  selectedExpiry: '03-Nov-2026',
  secondExpiry: '09-Nov-2026',
  availableExpiries: ['03-Nov-2026', '09-Nov-2026', '17-Nov-2026', '23-Nov-2026'],
  selectedTimeframe: '1d',

  marketData: {
    symbol: 'NIFTY',
    spot: 22936.75,
    open: 22890.00,
    high: 22985.50,
    low: 22850.10,
    prevClose: 22904.80,
    change: 31.95,
    changePct: 0.14,
    volume: 345000000,
    vwap: 22920.40,
    indiaVix: 13.82,
    regime: 'NORMAL_VOL',
    regimeConfidence: 0.84,
    atmStrike: 22950,
    timestamp: new Date().toISOString(),
    source: 'NSE LIVE (pnsea)',
    feedMode: 'NSE_LIVE',
    isSimulated: false,
  },

  systemHealth: {
    api: 'CONNECTED',
    database: 'CONNECTED',
    marketFeed: 'LIVE',
    models: 'READY',
    paperTrading: 'ACTIVE',
    latencyMs: 14,
    lastTickIso: new Date().toISOString(),
    serverRequestsCount: 28,
    serverErrorsCount: 0,
  },

  activeContract: null,
  pendingOrder: null,
  killSwitchActive: false,
  density: (localStorage.getItem('quantlens_density') as any) || 'compact',
  theme: (localStorage.getItem('quantlens_theme') as any) || 'dark',
  sidebarCollapsed: false,
  commandPaletteOpen: false,
  evaluationModalOpen: false,

  setActiveWorkspace: (id) => set({ activeWorkspace: id }),
  setSelectedExpiry: (exp) => set({ selectedExpiry: exp }),
  setSelectedTimeframe: (tf) => set({ selectedTimeframe: tf }),
  setSelectedInstrument: (inst) => set({ selectedInstrument: inst }),
  openContractDetail: (contract) => set({ activeContract: contract }),
  closeContractDetail: () => set({ activeContract: null }),
  setPendingOrder: (order) => set({ pendingOrder: order }),
  toggleKillSwitch: () => set((s) => ({ killSwitchActive: !s.killSwitchActive })),
  toggleDensity: () =>
    set((s) => {
      const next = s.density === 'compact' ? 'normal' : 'compact';
      localStorage.setItem('quantlens_density', next);
      document.documentElement.setAttribute('data-density', next);
      return { density: next };
    }),
  toggleTheme: () =>
    set((s) => {
      const next = s.theme === 'dark' ? 'light' : 'dark';
      localStorage.setItem('quantlens_theme', next);
      document.documentElement.setAttribute('data-theme', next);
      return { theme: next };
    }),
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
  setCommandPalette: (open) => set({ commandPaletteOpen: open }),
  setEvaluationModal: (open) => set({ evaluationModalOpen: open }),
  updateMarketData: (partial) => set((s) => ({ marketData: { ...s.marketData, ...partial } })),
  updateSystemHealth: (partial) => set((s) => ({ systemHealth: { ...s.systemHealth, ...partial } })),
}));

