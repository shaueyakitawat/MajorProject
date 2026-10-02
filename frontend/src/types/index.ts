/**
 * Institutional NIFTY 50 Quantitative Terminal — TypeScript Interfaces & Schemas
 * Maps exactly to FastAPI backend domain objects and quantitative pipeline outputs.
 */

export type VolatilityRegime = 'LOW_VOL' | 'NORMAL_VOL' | 'HIGH_VOL' | 'EXTREME_VOL';
export type MispricingClass = 'underpriced' | 'fair' | 'overpriced' | 'NO_TRADE';
export type OptionType = 'call' | 'put';
export type Timeframe = '1m' | '5m' | '15m' | '30m' | '1h' | 'daily' | 'weekly';
export type DataHealthStatus = 'CONNECTED' | 'LIVE' | 'STALE' | 'DEGRADED' | 'ERROR' | 'OFFLINE';

export interface OHLCVCandle {
  Date: string;
  Open: number;
  High: number;
  Low: number;
  Close: number;
  Volume: number;
}

export interface NiftyMarketDataResponse {
  total_candles: number;
  candles: OHLCVCandle[];
}

export interface OptionGreeks {
  delta: number | null;
  gamma: number | null;
  theta: number | null;
  vega: number | null;
  rho?: number | null;
}

export interface OptionContractQuote {
  ltp: number;
  iv: number;
  oi: number;
  volume: number;
  bid: number;
  ask: number;
  bid_size?: number;
  ask_size?: number;
  spread?: number;
  spread_pct?: number;
  delta?: number | null;
  gamma?: number | null;
  theta?: number | null;
  vega?: number | null;
  rho?: number | null;
  fair_price?: number | null;
  mispricing_pct?: number | null;
  m_score?: number | null;
  z_score?: number | null;
  liquidity_score?: number | null;
  liquidity_class?: 'HIGH' | 'MEDIUM' | 'LOW' | 'ILLIQUID';
  signal?: MispricingClass;
}

export interface OptionStrikeRow {
  strike: number;
  call: OptionContractQuote | null;
  put: OptionContractQuote | null;
}

export interface OptionChainPayload {
  spot_price: number;
  atm_strike: number;
  expiry_date: string;
  available_expiries: string[];
  pcr: number;
  chain: OptionStrikeRow[];
  timestamp: string;
  expiry_source?: string;
  is_simulated?: boolean;
}

export interface VRPData {
  vrp: number | null;
  expected_vrp: number | null;
  vrp_std: number | null;
}

export interface MispricingDetail {
  deviation: number;
  classification: MispricingClass;
  m_score: number;
  z_score: number;
  components?: {
    price_deviation?: number;
    vega_component?: number;
    gamma_component?: number;
    tci?: number;
    vrp_deviation?: number;
  };
}

export interface StrategyPositionLeg {
  action: 'buy' | 'sell';
  leg: 'call' | 'put';
  strike: string | number;
  quantity: number;
  price?: number;
  iv?: number;
  delta?: number;
  gamma?: number;
  theta?: number;
  vega?: number;
}

export interface StrategyPayload {
  strategy: string;
  strategy_type: 'LONG_VOLATILITY' | 'SHORT_VOLATILITY' | 'NO_TRADE';
  structure_name: string;
  confidence: 'high' | 'medium' | 'low';
  position_structure: {
    delta_neutral_approximation?: string;
    primary: StrategyPositionLeg[];
    alternative?: StrategyPositionLeg[];
    risk_defined_alternative?: StrategyPositionLeg[];
  };
  entry_condition: string;
  exit_condition: string;
  risk_notes: string[];
}

export interface FullStrategyResponse {
  selected_expiry: string;
  available_expiries: string[];
  spot_price: number;
  forecast_volatility: number;
  fair_price: number;
  market_price: number;
  mispricing: MispricingDetail;
  regime: VolatilityRegime;
  strategy: StrategyPayload;
  model_info?: {
    vol_model: string;
    pricing_model: string;
    data_source: string;
  };
  analytics_summary?: {
    volatility_context?: string;
    signal_confidence?: string;
    actionable_intent?: string;
  };
  pipeline_health?: string;
  implied_volatility?: number | null;
  forecasted_volatility?: number | null;
  vol_spread?: number | null;
  vol_signal?: string | null;
}

export interface BacktestSummaryResult {
  timeframe: string;
  mean_return: number | null;
  sharpe_ratio: number | null;
  t_stat: number | null;
  hit_rate: number | null;
  num_trades: number;
  skipped: number;
  initial_capital?: number;
  final_capital?: number;
  total_return?: number;
  cagr?: number;
  sortino_ratio?: number;
  max_drawdown?: number;
  profit_factor?: number;
  win_rate?: number;
}

export interface BacktestTradeRecord {
  id: string;
  entry_time: string;
  exit_time: string;
  instrument: string;
  expiry: string;
  strike: number;
  type: OptionType;
  strategy: string;
  entry_price: number;
  exit_price: number;
  quantity: number;
  pnl: number;
  return_pct: number;
  m_score: number;
  iv: number;
  model_vol: number;
  vrp: number;
  regime: VolatilityRegime;
  holding_time_bars: number;
  entry_state: {
    spot: number;
    iv: number;
    egarch_vol: number;
    realized_vol: number;
    final_vol: number;
    vrp: number;
    tci: number;
    regime: VolatilityRegime;
    m_score: number;
    fair_price: number;
    market_price: number;
    greeks: OptionGreeks;
  };
  replay_snapshots?: Array<{
    bar: number;
    timestamp: string;
    spot: number;
    option_price: number;
    unrealized_pnl: number;
    delta: number;
    vega: number;
  }>;
}

export interface PortfolioPosition {
  id: string;
  strategy: string;
  instrument: string;
  expiry: string;
  strike: number;
  type: OptionType;
  side: 'BUY' | 'SELL';
  quantity: number;
  entry_price: number;
  current_price: number;
  market_value: number;
  unrealized_pnl: number;
  realized_pnl: number;
  total_pnl: number;
  delta: number;
  gamma: number;
  theta: number;
  vega: number;
  margin: number;
  return_pct: number;
}

export interface AlertItem {
  id: string;
  timestamp: string;
  severity: 'INFO' | 'WARNING' | 'CRITICAL';
  category: 'MSCORE' | 'VRP' | 'REGIME' | 'LIQUIDITY' | 'SYSTEM';
  instrument: string;
  reason: string;
  value: string | number;
  threshold: string | number;
}
