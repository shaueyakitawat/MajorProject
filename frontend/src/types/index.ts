/**
 * QuantLens Terminal — Master Type Definitions
 * Typed contracts for market data, quantitative models, options, risk, and ledger.
 */

export type WorkspaceId =
  | 'overview'
  | 'option-chain'
  | 'volatility-lab'
  | 'mispricing-scanner'
  | 'strategy-lab'
  | 'backtesting'
  | 'market-monitor'
  | 'paper-terminal'
  | 'historical-ledger'
  | 'risk-portfolio'
  | 'pipeline-operations'
  | 'model-registry';

export type OptionType = 'call' | 'put' | 'CE' | 'PE';
export type OrderSide = 'BUY' | 'SELL';
export type FeedMode = 'NSE_LIVE' | 'SIMULATION_REPLAY';
export type Timeframe = '1m' | '5m' | '15m' | '1h' | '1d';
export type VolatilityRegime = 'LOW_VOL' | 'NORMAL_VOL' | 'HIGH_VOL' | 'EXTREME_VOL';

export interface MarketQuote {
  symbol: string;
  spot: number;
  open: number;
  high: number;
  low: number;
  prevClose: number;
  change: number;
  changePct: number;
  volume: number;
  vwap: number;
  indiaVix: number;
  regime: VolatilityRegime;
  regimeConfidence: number;
  atmStrike: number;
  timestamp: string;
  source: string;
  feedMode: FeedMode;
  isSimulated: boolean;
}

export interface OptionLegData {
  ltp: number;
  fairPrice: number;
  mispricingPct: number;
  mScore: number;
  zScore: number;
  iv: number;
  modelVol: number;
  vrp: number;
  delta: number;
  gamma: number;
  theta: number;
  vega: number;
  rho?: number;
  oi: number;
  volume: number;
  bid: number;
  ask: number;
  spread: number;
  liquidityClass: 'HIGH' | 'MEDIUM' | 'LOW';
  signal: 'underpriced' | 'overpriced' | 'fair';
}

export interface OptionChainRow {
  strike: number;
  call?: OptionLegData;
  put?: OptionLegData;
}

export interface ContractDetail {
  strike: number;
  type: OptionType;
  expiry: string;
  symbol: string;
  ltp: number;
  fairPrice: number;
  mispricingPct: number;
  mScore: number;
  zScore: number;
  iv: number;
  modelVol: number;
  vrp: number;
  delta: number;
  gamma: number;
  theta: number;
  vega: number;
  oi: number;
  volume: number;
  bid: number;
  ask: number;
  spread: number;
  liquidityClass: string;
  signal: string;
  source: string;
  timestamp: string;
}

export interface StrategyLeg {
  id: string;
  action: OrderSide;
  type: OptionType;
  strike: number;
  expiry: string;
  qty: number;
  price: number;
  iv: number;
  delta: number;
  gamma: number;
  theta: number;
  vega: number;
}

export interface PaperTradeRecord {
  trade_id: string;
  strategy: string;
  instrument: string;
  strike: number;
  option_type: string;
  expiry: string;
  side: OrderSide;
  qty: number;
  entry_price: number;
  current_price?: number;
  entry_fair: number;
  entry_spot: number;
  entry_mscore: number;
  entry_dev_pct: number;
  entry_time: string;
  entry_timestamp: string;
  exit_price?: number;
  exit_time?: string;
  exit_reason?: string;
  gross_pnl?: number;
  net_pnl?: number;
  friction_cost?: number;
  return_pct?: number;
  converged?: number;
  holding_seconds?: number;
  status: 'OPEN' | 'CLOSED';
  target_price?: number;
  stop_price?: number;
}

export interface PipelineStageInfo {
  number: number;
  id: string;
  name: string;
  tag: string;
  icon: string;
  status: string;
  latency_ms: number;
  formula: string;
  description: string;
  inputs: Record<string, any>;
  outputs: Record<string, any>;
}

export interface ModelRegistryItem {
  id: string;
  name: string;
  short_name: string;
  category: string;
  version: string;
  file_path: string;
  governing_equation_latex: string;
  parameters?: Record<string, any>;
  training_window?: string;
  annualization_factor?: string;
  economic_intuition?: string;
  validation_status: string;
  coverage?: string;
  states?: Array<{ state: number; label: string; typical_annual_vol: string; action: string }>;
  transition_matrix?: number[][];
  inputs?: string[];
  greeks_supported?: string[];
  signal_thresholds?: Record<string, string>;
  accuracy_metrics?: Record<string, any>;
}

export interface PortfolioRiskReport {
  status: string;
  underlying_spot: number;
  capital_base: number;
  cash_buffer_floor: number;
  free_margin: number;
  margin_used: number;
  active_contracts_count: number;
  gross_notional: number;
  greeks: {
    portfolio_delta: number;
    portfolio_gamma: number;
    portfolio_daily_theta: number;
    portfolio_vega: number;
  };
  limits: {
    delta_neutral_bound: string;
    delta_neutral_status: string;
    daily_loss_limit: string;
    max_margin_utilization: string;
  };
  stress_scenarios: Array<{
    spot_shift_pct: string;
    spot_price: number;
    [key: string]: any;
  }>;
  active_positions: PaperTradeRecord[];
}
