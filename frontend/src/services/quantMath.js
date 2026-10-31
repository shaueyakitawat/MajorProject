/**
 * Quantitative Financial Mathematics & Numerical Computing Service
 * Rigorous Black-Scholes equations, Greeks, payoff evaluation, and statistical regression.
 */

// Standard normal cumulative distribution function (Abramowitz and Stegun approximation)
export function cdfNormal(x) {
  const a1 =  0.254829592;
  const a2 = -0.284496736;
  const a3 =  1.421413741;
  const a4 = -1.453152027;
  const a5 =  1.061405429;
  const p  =  0.3275911;

  const sign = x < 0 ? -1 : 1;
  const absX = Math.abs(x) / Math.SQRT2;

  const t = 1.0 / (1.0 + p * absX);
  const erf = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * Math.exp(-absX * absX);

  return 0.5 * (1.0 + sign * erf);
}

// Standard normal probability density function
export function pdfNormal(x) {
  return (1.0 / Math.sqrt(2 * Math.PI)) * Math.exp(-0.5 * x * x);
}

/**
 * Analytical Black-Scholes Option Pricing
 * @param {number} S Spot price
 * @param {number} K Strike price
 * @param {number} T Time to expiry in years
 * @param {number} r Risk-free interest rate (decimal, e.g. 0.06)
 * @param {number} sigma Annualized volatility (decimal, e.g. 0.15)
 * @param {'call'|'put'} type Option type
 */
export function blackScholesPrice(S, K, T, r, sigma, type = 'call') {
  if (T <= 0 || sigma <= 0 || S <= 0 || K <= 0) return 0.0;

  const d1 = (Math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * Math.sqrt(T));
  const d2 = d1 - sigma * Math.sqrt(T);

  if (type.toLowerCase() === 'call') {
    return Math.max(0, S * cdfNormal(d1) - K * Math.exp(-r * T) * cdfNormal(d2));
  } else {
    return Math.max(0, K * Math.exp(-r * T) * cdfNormal(-d2) - S * cdfNormal(-d1));
  }
}

/**
 * Analytical Black-Scholes Greeks
 */
export function calculateGreeks(S, K, T, r, sigma, type = 'call') {
  if (T <= 0 || sigma <= 0 || S <= 0 || K <= 0) {
    return { delta: 0, gamma: 0, theta: 0, vega: 0, rho: 0 };
  }

  const sqrtT = Math.sqrt(T);
  const d1 = (Math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * sqrtT);
  const d2 = d1 - sigma * sqrtT;
  const pdfD1 = pdfNormal(d1);

  const gamma = pdfD1 / (S * sigma * sqrtT);
  const vega = (S * pdfD1 * sqrtT) / 100.0; // Vega per 1% vol change

  let delta = 0;
  let theta = 0;
  let rho = 0;

  if (type.toLowerCase() === 'call') {
    delta = cdfNormal(d1);
    theta = (-(S * pdfD1 * sigma) / (2 * sqrtT) - r * K * Math.exp(-r * T) * cdfNormal(d2)) / 365.0;
    rho = (K * T * Math.exp(-r * T) * cdfNormal(d2)) / 100.0;
  } else {
    delta = cdfNormal(d1) - 1.0;
    theta = (-(S * pdfD1 * sigma) / (2 * sqrtT) + r * K * Math.exp(-r * T) * cdfNormal(-d2)) / 365.0;
    rho = (-K * T * Math.exp(-r * T) * cdfNormal(-d2)) / 100.0;
  }

  return { delta, gamma, theta, vega, rho };
}

/**
 * Implied Volatility Solver via Bisection
 */
export function solveImpliedVolatility(S, K, T, r, marketPrice, type = 'call') {
  if (marketPrice <= 0 || T <= 0 || S <= 0 || K <= 0) return 0.15;

  let low = 0.001;
  let high = 5.0;
  let mid = 0.20;

  for (let i = 0; i < 40; i++) {
    mid = (low + high) / 2.0;
    const price = blackScholesPrice(S, K, T, r, mid, type);
    const diff = price - marketPrice;

    if (Math.abs(diff) < 0.001) {
      return mid;
    }
    if (diff > 0) {
      high = mid;
    } else {
      low = mid;
    }
  }
  return mid;
}

/**
 * Compute institutional M-Score decomposition
 * 5 components: Price deviation (50%), Vega (15%), Gamma (15%), TCI (10%), VRP (10%)
 */
export function computeMScoreDecomposition(marketPrice, fairPrice, vega, gamma, tci, currentVrp, expectedVrp) {
  const priceDev = fairPrice > 0 ? (marketPrice - fairPrice) / fairPrice : 0;
  const vrpDev = (currentVrp || 0) - (expectedVrp || 0);

  const c1 = 0.50 * priceDev;
  const c2 = 0.15 * (vega || 0);
  const c3 = 0.15 * ((gamma || 0) * 1000); // scaled
  const c4 = 0.10 * ((tci || 0) * 100);
  const c5 = 0.10 * (vrpDev * 10);

  const mScore = c1 + c2 + c3 + c4 + c5;
  const zScore = mScore / 1.5; // normalized approximation

  return {
    mScore,
    zScore,
    components: {
      priceDevWeight: c1,
      vegaWeight: c2,
      gammaWeight: c3,
      tciWeight: c4,
      vrpWeight: c5,
    }
  };
}

/**
 * Payoff curve calculator for multi-leg strategies
 */
export function calculateStrategyPayoff(legs, spotRange, currentSpot, daysToExpiry = 0, volShock = 0) {
  const points = [];
  const r = 0.06;
  const T = Math.max(0.0001, daysToExpiry / 365.0);

  let netEntryCost = 0;
  for (const leg of legs) {
    const sign = leg.action.toLowerCase() === 'buy' ? 1 : -1;
    netEntryCost += sign * leg.price * leg.qty;
  }

  for (const s of spotRange) {
    let expiryPayoff = -netEntryCost;
    let theoreticalPayoff = -netEntryCost;

    for (const leg of legs) {
      const mult = leg.action.toLowerCase() === 'buy' ? 1 : -1;
      const isCall = leg.type.toLowerCase() === 'call';
      const K = leg.strike;
      const qty = leg.qty;

      // Expiry intrinsic value
      const intrinsic = isCall ? Math.max(0, s - K) : Math.max(0, K - s);
      expiryPayoff += mult * intrinsic * qty;

      // Theoretical price before expiry
      const sigma = Math.max(0.01, (leg.iv || 0.15) + volShock);
      const bsVal = blackScholesPrice(s, K, T, r, sigma, leg.type);
      theoreticalPayoff += mult * bsVal * qty;
    }

    points.push({
      spot: s,
      expiryPnl: Math.round(expiryPayoff * 100) / 100,
      theoreticalPnl: Math.round(theoreticalPayoff * 100) / 100,
    });
  }

  // Find breakevens where expiry payoff crosses 0
  const breakevens = [];
  for (let i = 1; i < points.length; i++) {
    if ((points[i - 1].expiryPnl < 0 && points[i].expiryPnl >= 0) ||
        (points[i - 1].expiryPnl >= 0 && points[i].expiryPnl < 0)) {
      breakevens.push(points[i].spot);
    }
  }

  const pnlValues = points.map(p => p.expiryPnl);
  const maxProfit = Math.max(...pnlValues);
  const maxLoss = Math.min(...pnlValues);

  return { points, breakevens, maxProfit, maxLoss, netPremium: netEntryCost };
}

/**
 * 5x5 Scenario Matrix: Spot price vs IV Shock
 */
export function generateScenarioMatrix(legs, spotPrice) {
  const spotShocks = [-0.05, -0.02, 0.0, 0.02, 0.05];
  const ivShocks = [-0.02, -0.01, 0.0, 0.01, 0.02];
  const r = 0.06;
  const T = 7 / 365.0; // 1 week horizon assumption

  let netEntryCost = 0;
  for (const leg of legs) {
    const sign = leg.action.toLowerCase() === 'buy' ? 1 : -1;
    netEntryCost += sign * leg.price * leg.qty;
  }

  const matrix = [];

  for (const sPct of spotShocks) {
    const targetSpot = spotPrice * (1 + sPct);
    const row = {
      spotChangePct: sPct * 100,
      targetSpot: Math.round(targetSpot),
      values: []
    };

    for (const ivShock of ivShocks) {
      let theoreticalPayoff = -netEntryCost;
      for (const leg of legs) {
        const mult = leg.action.toLowerCase() === 'buy' ? 1 : -1;
        const sigma = Math.max(0.01, (leg.iv || 0.15) + ivShock);
        const bsVal = blackScholesPrice(targetSpot, leg.strike, T, r, sigma, leg.type);
        theoreticalPayoff += mult * bsVal * leg.qty;
      }
      row.values.push({
        ivShockPct: ivShock * 100,
        pnl: Math.round(theoreticalPayoff)
      });
    }
    matrix.push(row);
  }

  return { matrix, ivHeaders: ivShocks.map(v => (v >= 0 ? `+${v * 100}%` : `${v * 100}%`)) };
}

/**
 * OLS Linear Regression & Pearson Correlation
 */
export function calculateRegression(xData, yData) {
  const n = Math.min(xData.length, yData.length);
  if (n < 2) {
    return { r: 0, rSquared: 0, slope: 0, intercept: 0, meanX: 0, meanY: 0, stdX: 0, stdY: 0, count: n };
  }

  let sumX = 0, sumY = 0;
  for (let i = 0; i < n; i++) {
    sumX += xData[i];
    sumY += yData[i];
  }
  const meanX = sumX / n;
  const meanY = sumY / n;

  let num = 0, denX = 0, denY = 0;
  for (let i = 0; i < n; i++) {
    const dx = xData[i] - meanX;
    const dy = yData[i] - meanY;
    num += dx * dy;
    denX += dx * dx;
    denY += dy * dy;
  }

  const stdX = Math.sqrt(denX / (n - 1));
  const stdY = Math.sqrt(denY / (n - 1));
  const r = (denX > 0 && denY > 0) ? num / Math.sqrt(denX * denY) : 0;
  const slope = denX > 0 ? num / denX : 0;
  const intercept = meanY - slope * meanX;
  const rSquared = r * r;

  return { r, rSquared, slope, intercept, meanX, meanY, stdX, stdY, count: n };
}
