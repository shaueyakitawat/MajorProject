/**
 * Institutional Terminal API Adapter Layer
 * Centralizes all communication with FastAPI backend endpoints.
 * Automatically computes latency, normalizes payloads, and isolates simulated adapters.
 */

import { API_BASE } from '../config.js';
import { blackScholesPrice, calculateGreeks, computeMScoreDecomposition } from './quantMath.js';

class ApiService {
  constructor() {
    this.requestCount = 0;
    this.errorCount = 0;
  }

  async _fetch(endpoint, params = {}) {
    const url = new URL(`${API_BASE}${endpoint}`);
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') {
        url.searchParams.set(k, v);
      }
    });

    const start = performance.now();
    this.requestCount++;

    try {
      const response = await fetch(url.toString(), {
        headers: { Accept: 'application/json' },
      });
      const durationMs = Math.round(performance.now() - start);

      if (!response.ok) {
        throw new Error(`HTTP ${response.status} ${response.statusText}`);
      }

      const json = await response.json();
      return {
        success: true,
        data: json.data !== undefined ? json.data : json,
        meta: json.meta || {},
        latencyMs: durationMs,
      };
    } catch (err) {
      const durationMs = Math.round(performance.now() - start);
      this.errorCount++;
      console.warn(`[API] Endpoint ${endpoint} failed (${durationMs}ms):`, err.message);
      return {
        success: false,
        error: err.message,
        latencyMs: durationMs,
      };
    }
  }

  async getHealth() {
    return this._fetch('/health');
  }

  async getMetrics() {
    return this._fetch('/metrics');
  }

  async getNiftyCandles(symbol = 'NIFTY', timeframe = 'daily') {
    const res = await this._fetch('/nifty', { symbol, timeframe });
    if (res.success && res.data && res.data.candles) {
      return {
        ...res,
        candles: res.data.candles,
      };
    }
    return res;
  }

  async getReturns(symbol = 'NIFTY', timeframe = 'daily') {
    return this._fetch('/returns', { symbol, timeframe });
  }

  async getOptionChain(symbol = 'NIFTY', expiry = null, depth = 20) {
    const res = await this._fetch('/option-chain', { symbol, expiry, depth });
    if (res.success && res.data && res.data.chain) {
      return {
        ...res,
        data: this._normalizeOptionChain(res.data, false),
      };
    }

    // Try demo option chain endpoint if full chain failed or unauthenticated
    const demoRes = await this._fetch('/option-chain-demo', { symbol });
    if (demoRes.success && demoRes.data && demoRes.data.chain) {
      return {
        ...demoRes,
        data: this._normalizeOptionChain(demoRes.data, true),
      };
    }

    return res;
  }

  async getStrategy(symbol = 'NIFTY', timeframe = 'daily', horizon = 'positional', expiry = null) {
    return this._fetch('/strategy', { symbol, timeframe, trading_horizon: horizon, expiry });
  }

  async getDebugOption(symbol = 'NIFTY', expiry = null) {
    return this._fetch('/debug-option', { symbol, expiry });
  }

  async getExpiries(symbol = 'NIFTY') {
    return this._fetch('/expiries', { symbol });
  }

  async getBacktest(symbol = '^NSEI', timeframe = '1d') {
    return this._fetch('/backtest', { symbol, timeframe });
  }

  /**
   * Normalizes raw option chain records and computes derived institutional metrics.
   * Clearly flags if chain data is simulated or live.
   */
  _normalizeOptionChain(rawChain, isSimulated = false) {
    const spot = rawChain.spot_price || 22421.95;
    const atm = rawChain.atm_strike || Math.round(spot / 50) * 50;
    const expiry = rawChain.expiry_date || '2026-10-16';
    const chainList = rawChain.chain || [];

    // Calculate time to expiry T in years
    const expiryDate = new Date(expiry);
    const now = new Date();
    const diffMs = Math.max(0, expiryDate - now);
    const T = Math.max(0.002, diffMs / (365 * 24 * 3600 * 1000));
    const r = 0.06;

    const normalizedChain = chainList.map(row => {
      const strike = row.strike;

      const normalizeLeg = (leg, type) => {
        if (!leg) return null;

        const ltp = leg.ltp || 0;
        const iv = leg.iv || 0.15;
        const bid = leg.bid || (ltp > 0 ? ltp * 0.995 : 0);
        const ask = leg.ask || (ltp > 0 ? ltp * 1.005 : 0);
        const spread = ask - bid;
        const spreadPct = ltp > 0 ? (spread / ltp) * 100 : 0;
        const oi = leg.oi || 0;
        const volume = leg.volume || 0;

        // Greeks calculation if missing from backend
        let greeks = {
          delta: leg.delta !== undefined ? leg.delta : null,
          gamma: leg.gamma !== undefined ? leg.gamma : null,
          theta: leg.theta !== undefined ? leg.theta : null,
          vega: leg.vega !== undefined ? leg.vega : null,
        };

        if (greeks.delta === null || greeks.gamma === null) {
          const computed = calculateGreeks(spot, strike, T, r, iv, type);
          greeks = {
            delta: computed.delta,
            gamma: computed.gamma,
            theta: computed.theta,
            vega: computed.vega,
            rho: computed.rho,
          };
        }

        // Theoretical Black-Scholes Fair Price
        const modelVol = 0.1461; // Fused Model Volatility baseline
        const fairPrice = blackScholesPrice(spot, strike, T, r, modelVol, type);
        const deviation = fairPrice > 0 ? (ltp - fairPrice) / fairPrice : 0;
        const deviationPct = deviation * 100;

        // M-Score & Liquidity Scoring
        const mScoreData = computeMScoreDecomposition(
          ltp, fairPrice, greeks.vega, greeks.gamma, 0.00034, iv - modelVol, 0.015
        );

        let liquidityScore = Math.min(100, Math.round((oi / 50000) * 40 + (volume / 20000) * 40 + Math.max(0, (2 - spreadPct)) * 10));
        let liquidityClass = 'HIGH';
        if (liquidityScore < 30) liquidityClass = 'ILLIQUID';
        else if (liquidityScore < 60) liquidityClass = 'LOW';
        else if (liquidityScore < 80) liquidityClass = 'MEDIUM';

        let signal = 'fair';
        if (deviationPct < -5.0) signal = 'underpriced';
        else if (deviationPct > 5.0) signal = 'overpriced';

        return {
          ...leg,
          ltp: Math.round(ltp * 100) / 100,
          iv: Math.round(iv * 10000) / 10000,
          bid: Math.round(bid * 100) / 100,
          ask: Math.round(ask * 100) / 100,
          spread: Math.round(spread * 100) / 100,
          spreadPct: Math.round(spreadPct * 100) / 100,
          oi,
          volume,
          delta: greeks.delta !== null ? Math.round(greeks.delta * 10000) / 10000 : null,
          gamma: greeks.gamma !== null ? Math.round(greeks.gamma * 100000) / 100000 : null,
          theta: greeks.theta !== null ? Math.round(greeks.theta * 100) / 100 : null,
          vega: greeks.vega !== null ? Math.round(greeks.vega * 100) / 100 : null,
          rho: greeks.rho !== undefined ? Math.round(greeks.rho * 100) / 100 : 0,
          fairPrice: Math.round(fairPrice * 100) / 100,
          mispricingPct: Math.round(deviationPct * 100) / 100,
          mScore: Math.round(mScoreData.mScore * 100) / 100,
          zScore: Math.round(mScoreData.zScore * 100) / 100,
          liquidityScore,
          liquidityClass,
          signal,
          modelVol,
          vrp: Math.round((iv - modelVol) * 10000) / 10000,
        };
      };

      return {
        strike,
        call: normalizeLeg(row.call, 'call'),
        put: normalizeLeg(row.put, 'put'),
      };
    });

    return {
      spotPrice: spot,
      atmStrike: atm,
      expiryDate: expiry,
      availableExpiries: rawChain.available_expiries || [expiry],
      pcr: rawChain.pcr || 1.0,
      timestamp: rawChain.timestamp || new Date().toISOString(),
      isSimulated: isSimulated,
      dataSourceBadge: isSimulated ? 'SIMULATED / DEMO DATA' : 'REAL MARKET FEED',
      chain: normalizedChain,
    };
  }
}

export const apiService = new ApiService();
