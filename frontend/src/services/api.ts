/**
 * QuantLens Terminal — Master Typed API Client
 * Interfaces with FastAPI backend (:8000) with robust timeouts and error normalization.
 */

export const API_BASE = window.location.port === '3000'
  ? `${window.location.protocol}//${window.location.hostname}:8000`
  : window.location.origin;

class ApiClient {
  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<{ success: boolean; data?: T; error?: string }> {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 12000);

    try {
      const url = endpoint.startsWith('http') ? endpoint : `${API_BASE}${endpoint}`;
      const response = await fetch(url, {
        ...options,
        signal: controller.signal,
        headers: {
          'Content-Type': 'application/json',
          ...(options.headers || {})
        }
      });
      clearTimeout(timeoutId);

      const json = await response.json().catch(() => null);

      if (!response.ok) {
        return {
          success: false,
          error: json?.detail || json?.message || `HTTP ${response.status}: ${response.statusText}`
        };
      }

      if (json && typeof json === 'object' && 'status' in json && 'data' in json) {
        return {
          success: json.status === 'success' || json.status === 'ok',
          data: json.data as T,
          error: json.status !== 'success' && json.status !== 'ok' ? json.error || 'Server error' : undefined
        };
      }

      return { success: true, data: json as T };
    } catch (err: any) {
      clearTimeout(timeoutId);
      if (err.name === 'AbortError') {
        return { success: false, error: 'Request timeout (12s exceeded)' };
      }
      return { success: false, error: err.message || 'Network connection failed' };
    }
  }

  // System & Health
  async getHealth() {
    return this.request<any>('/api/health');
  }

  // Market OHLCV Candles
  async getNiftyCandles(symbol: string = 'NIFTY', timeframe: string = '1d') {
    const tf = timeframe === '1d' ? 'daily' : timeframe;
    return this.request<any>(`/nifty?symbol=${symbol}&timeframe=${tf}`);
  }

  // Option Chain
  async getOptionChain(symbol: string = 'NIFTY', expiry?: string, depth: number = 25) {
    let url = `/option-chain?symbol=${symbol}&depth=${depth}`;
    if (expiry) url += `&expiry=${encodeURIComponent(expiry)}`;
    return this.request<any>(url);
  }

  // Expiries
  async getExpiries(symbol: string = 'NIFTY') {
    return this.request<any>(`/expiries?symbol=${symbol}`);
  }

  // Volatility Forecast
  async getForecastVol(symbol: string = 'NIFTY', timeframe: string = '1d') {
    return this.request<any>(`/forecast-vol?symbol=${symbol}&timeframe=${timeframe}`);
  }

  // HMM Regime
  async getRegime() {
    return this.request<any>('/regime');
  }

  // Quant Strategy
  async getStrategy(symbol: string = 'NIFTY', timeframe: string = '1d', horizon: string = 'positional') {
    return this.request<any>(`/strategy?symbol=${symbol}&timeframe=${timeframe}&trading_horizon=${horizon}`);
  }

  // Walk-forward Backtest
  async getBacktest(symbol: string = '^NSEI', timeframe: string = '1d') {
    return this.request<any>(`/backtest?symbol=${symbol}&timeframe=${timeframe}`);
  }

  // Trades & Ledger
  async getTrades(dateFilter?: string | null) {
    let url = '/api/trades';
    if (dateFilter) url += `?date=${encodeURIComponent(dateFilter)}`;
    return this.request<any>(url);
  }

  // DMA Order Execution
  async executeTrade(params: {
    instrument: string;
    side: 'BUY' | 'SELL';
    strike: number;
    option_type: string;
    qty: number;
    price: number;
    expiry: string;
    strategy: string;
  }) {
    return this.request<any>('/api/trades/execute', {
      method: 'POST',
      body: JSON.stringify(params)
    });
  }

  // Position Square Off
  async closeTrade(tradeId: string, exitPrice?: number, exitReason: string = 'MANUAL_TERMINAL_CLOSE') {
    return this.request<any>('/api/trades/close', {
      method: 'POST',
      body: JSON.stringify({
        trade_id: tradeId,
        exit_price: exitPrice,
        exit_reason: exitReason
      })
    });
  }

  // 8-Stage Pipeline Telemetry
  async getPipelineFlow(symbol: string = 'NIFTY', expiry?: string) {
    let url = `/api/pipeline-flow?symbol=${symbol}`;
    if (expiry) url += `&expiry=${encodeURIComponent(expiry)}`;
    return this.request<any>(url);
  }

  // Multi-Dimensional Volatility Surfaces & Smiles
  async getVolatilitySurface(symbol: string = 'NIFTY') {
    return this.request<any>(`/api/volatility-surface?symbol=${symbol}`);
  }

  // Macro News Intelligence Wire
  async getNews() {
    return this.request<any>('/api/news');
  }

  // Model Registry & Validations
  async getModelRegistry() {
    return this.request<any>('/api/model-registry');
  }

  // Portfolio Risk & Stress Scenarios
  async getPortfolioRisk() {
    return this.request<any>('/api/risk');
  }
}

export const apiService = new ApiClient();

