#!/usr/bin/env python3
"""
run_validation.py — Full System Audit for the Options Mispricing Engine.

Classifies each component as WORKING / WEAK / BROKEN and produces
a structured diagnostic report using real yfinance data (SPY).
"""

import sys
import os
import math
import json
import warnings
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timezone

warnings.filterwarnings("ignore")

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.services.option_chain_service import get_spot_price, fetch_option_chain, get_atm_option
from backend.services.volatility_service import forecast_volatility
from backend.services.pricing_service import black_scholes_price
from backend.services.implied_volatility_service import calculate_implied_volatility
from backend.infrastructure.annualization_engine import apply_dynamic_annualization

# ── Config ─────────────────────────────────────────────────────────────────────

SYMBOL = "SPY"
TIMEFRAME = "5m"
RISK_FREE_RATE = 0.06
TRAIN_WINDOW = 60


def sep(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def tag(status: str) -> str:
    icons = {"WORKING": "🟢", "WEAK": "🟡", "BROKEN": "🔴", "STRONG": "🟢", "NO EDGE": "🔴"}
    return f"{icons.get(status, '⚪')} {status}"


# ── STEP 1: Data Layer ────────────────────────────────────────────────────────

def audit_data_layer() -> tuple[str, dict]:
    sep("STEP 1: DATA LAYER")
    issues = []

    try:
        spot = get_spot_price(SYMBOL)
    except Exception as e:
        print(f"  ❌ Spot fetch failed: {e}")
        return "BROKEN", {"spot": None, "error": str(e)}

    if spot <= 0:
        issues.append("spot_price <= 0")
    print(f"  Spot Price:  ${spot:.2f}  {'✅' if spot > 0 else '❌'}")

    try:
        chain = fetch_option_chain(SYMBOL)
    except Exception as e:
        print(f"  ❌ Option chain fetch failed: {e}")
        return "BROKEN", {"spot": spot, "error": str(e)}

    expiry = chain["expiry"]
    calls = chain["calls"]
    puts = chain["puts"]

    if calls.empty:
        issues.append("calls_empty")
    if puts.empty:
        issues.append("puts_empty")

    print(f"  Expiry:      {expiry}  ✅")
    print(f"  Calls:       {len(calls)} contracts  {'✅' if not calls.empty else '❌'}")
    print(f"  Puts:        {len(puts)} contracts  {'✅' if not puts.empty else '❌'}")

    try:
        atm_call = get_atm_option(chain, spot, "call")
        atm_put = get_atm_option(chain, spot, "put")
    except Exception as e:
        print(f"  ❌ ATM extraction failed: {e}")
        return "BROKEN", {"spot": spot, "chain": chain, "error": str(e)}

    # ATM strike within 1% of spot
    call_dev = abs(atm_call["strike"] - spot) / spot
    put_dev = abs(atm_put["strike"] - spot) / spot
    atm_ok = call_dev < 0.01 and put_dev < 0.01

    print(f"  ATM Call:    K={atm_call['strike']}  ltp={atm_call['ltp']:.2f}  iv={atm_call['iv']:.4f}")
    print(f"  ATM Put:     K={atm_put['strike']}  ltp={atm_put['ltp']:.2f}  iv={atm_put['iv']:.4f}")
    print(f"  Strike Dev:  call={call_dev:.4f}  put={put_dev:.4f}  {'✅' if atm_ok else '⚠️ >1%'}")

    if not atm_ok:
        issues.append("atm_strike_deviation_>1%")

    # T
    import dateutil.parser
    exp_dt = dateutil.parser.parse(str(expiry))
    now_utc = datetime.now(timezone.utc)
    if exp_dt.tzinfo is None:
        exp_dt = exp_dt.replace(tzinfo=timezone.utc)
    T = max((exp_dt - now_utc).total_seconds(), 0) / (365 * 24 * 3600)
    print(f"  T (years):   {T:.6f}  {'✅' if T > 0 else '❌'}")
    if T <= 0:
        issues.append("T_expired")

    status = "BROKEN" if len(issues) > 0 else "WORKING"
    print(f"\n  {tag(status)} DATA LAYER")

    return status, {
        "spot": spot, "chain": chain, "atm_call": atm_call, "atm_put": atm_put,
        "expiry": expiry, "T": T, "issues": issues
    }


# ── STEP 2: Volatility Layer ──────────────────────────────────────────────────

def audit_vol_layer(data: dict) -> tuple[str, dict]:
    sep("STEP 2: VOLATILITY LAYER")

    ohlcv = yf.download(SYMBOL, period="15d", interval="5m", auto_adjust=True, progress=False)
    ohlcv.columns = [c[0] if isinstance(c, tuple) else c for c in ohlcv.columns]
    ohlcv = ohlcv.dropna(how="all")
    log_ret = np.log(ohlcv["Close"] / ohlcv["Close"].shift(1)).dropna()

    raw_vol = forecast_volatility(log_ret)
    egarch_vol = apply_dynamic_annualization(raw_vol, TIMEFRAME)
    egarch_vol = max(0.01, min(2.0, egarch_vol))

    print(f"  Raw EGARCH:     {raw_vol:.6f}")
    print(f"  Annualized:     {egarch_vol:.4f} ({egarch_vol*100:.2f}%)")

    # Stability: run on 5 rolling sub-windows
    vols = []
    N = len(log_ret)
    for j in range(5):
        start_idx = max(0, N - TRAIN_WINDOW - (4 - j) * 10)
        end_idx = start_idx + TRAIN_WINDOW
        if end_idx > N:
            break
        window = log_ret.iloc[start_idx:end_idx]
        try:
            rv = forecast_volatility(window)
            if rv > 0:
                av = apply_dynamic_annualization(rv, TIMEFRAME)
                vols.append(av)
        except Exception:
            pass

    if len(vols) >= 3:
        vol_std = float(np.std(vols))
        vol_mean = float(np.mean(vols))
        cv = vol_std / vol_mean if vol_mean > 0 else 999
        stable = cv < 0.5
        print(f"  Stability:      {len(vols)} windows  CV={cv:.4f}  {'✅ Stable' if stable else '⚠️ Unstable'}")
    else:
        stable = False
        cv = None
        print(f"  Stability:      Insufficient windows")

    # Classification
    in_range = 0.05 < egarch_vol < 1.0
    not_nan = math.isfinite(egarch_vol) and egarch_vol > 0

    print(f"  Range [0.05–1.0]: {'✅' if in_range else '❌'}")
    print(f"  Finite & >0:      {'✅' if not_nan else '❌'}")

    if in_range and not_nan and stable:
        status = "WORKING"
    elif in_range and not_nan:
        status = "WEAK"
    else:
        status = "BROKEN"

    print(f"\n  {tag(status)} VOLATILITY LAYER")

    return status, {"egarch_vol": egarch_vol, "raw_vol": raw_vol, "log_ret": log_ret, "ohlcv": ohlcv, "stability_cv": cv}


# ── STEP 3: Pricing Layer ─────────────────────────────────────────────────────

def audit_pricing_layer(data: dict, vol_data: dict) -> tuple[str, dict]:
    sep("STEP 3: PRICING LAYER")

    spot = data["spot"]
    strike = data["atm_call"]["strike"]
    market_price = data["atm_call"]["ltp"]
    T = data["T"]
    egarch_vol = vol_data["egarch_vol"]

    expiry_vol = egarch_vol * (T ** 0.5)
    fair_price = black_scholes_price(
        spot=spot, strike=strike, time_to_expiry=T,
        risk_free_rate=RISK_FREE_RATE, volatility=expiry_vol, option_type="call"
    )

    ratio = fair_price / market_price if market_price > 0 else 0

    print(f"  Fair Price:     ${fair_price:.4f}")
    print(f"  Market Price:   ${market_price:.4f}")
    print(f"  Ratio (F/M):    {ratio:.4f}")
    print(f"  Fair > 0:       {'✅' if fair_price > 0 else '❌'}")
    print(f"  Ratio in [0.2, 5]: {'✅' if 0.2 < ratio < 5 else '❌'}")

    if fair_price > 0 and 0.2 < ratio < 5:
        status = "WORKING"
    else:
        status = "BROKEN"

    print(f"\n  {tag(status)} PRICING LAYER")

    return status, {"fair_price": fair_price, "market_price": market_price, "ratio": ratio}


# ── STEP 4: Vol Comparison ─────────────────────────────────────────────────────

def audit_vol_signal(data: dict, vol_data: dict) -> tuple[str, dict]:
    sep("STEP 4: VOL COMPARISON")

    spot = data["spot"]
    strike = data["atm_call"]["strike"]
    market_price = data["atm_call"]["ltp"]
    T = data["T"]
    egarch_vol = vol_data["egarch_vol"]

    iv = calculate_implied_volatility(
        S=spot, K=strike, T=T, r=RISK_FREE_RATE,
        market_price=market_price, option_type="call"
    )

    if iv is not None:
        spread = abs(iv - egarch_vol)
        print(f"  IV:           {iv:.4f} ({iv*100:.2f}%)")
        print(f"  EGARCH:       {egarch_vol:.4f} ({egarch_vol*100:.2f}%)")
        print(f"  |Spread|:    {spread:.4f}")
        print(f"  < 0.20:       {'✅' if spread < 0.2 else '❌'}")
        status = "WORKING" if spread < 0.2 else "WEAK"
    else:
        spread = None
        print(f"  ❌ IV solver failed")
        status = "WEAK"

    print(f"\n  {tag(status)} VOL COMPARISON")
    return status, {"iv": iv, "egarch_vol": egarch_vol, "spread": spread}


# ── STEP 5: Signal Stability ──────────────────────────────────────────────────

def audit_signal_stability(data: dict, vol_data: dict) -> tuple[str, dict]:
    sep("STEP 5: SIGNAL STABILITY")

    ohlcv = vol_data["ohlcv"]
    closes = ohlcv["Close"].values
    returns = np.log(closes[1:] / closes[:-1])
    T = data["T"]
    spot_now = data["spot"]
    strike = data["atm_call"]["strike"]
    market_price = data["atm_call"]["ltp"]
    N = len(returns)

    scores = []
    for i in range(TRAIN_WINDOW, min(N - 1, TRAIN_WINDOW + 100)):
        window = pd.Series(returns[i - TRAIN_WINDOW : i])
        try:
            from arch import arch_model
            pct = window * 100
            model = arch_model(pct, vol="EGARCH", p=1, q=1, dist="normal")
            fit = model.fit(disp="off", show_warning=False)
            fcast = fit.forecast(horizon=1)
            daily_vol = float(np.sqrt(fcast.variance.values[-1, 0])) / 100
            if daily_vol <= 0:
                continue
            egarch_ann = apply_dynamic_annualization(daily_vol, TIMEFRAME)
            egarch_ann = max(0.01, min(2.0, egarch_ann))
        except Exception:
            continue

        spot_i = float(closes[i])
        try:
            expiry_vol = egarch_ann * (T ** 0.5)
            fp = black_scholes_price(
                spot=spot_i, strike=spot_i, time_to_expiry=T,
                risk_free_rate=RISK_FREE_RATE, volatility=expiry_vol, option_type="call"
            )
            mkt_i = fp * 1.03
        except Exception:
            continue

        if fp <= 0:
            continue

        iv_i = calculate_implied_volatility(
            S=spot_i, K=spot_i, T=T, r=RISK_FREE_RATE,
            market_price=mkt_i, option_type="call"
        )
        price_score = (mkt_i - fp) / fp
        vol_score = (iv_i - egarch_ann) if iv_i is not None else 0.0
        final_score = 0.6 * price_score + 0.4 * vol_score
        scores.append(final_score)

    if len(scores) < 10:
        print(f"  ⚠️  Only {len(scores)} scores computed")
        status = "WEAK"
        return status, {"count": len(scores)}

    arr = np.array(scores)
    mean_s = float(np.mean(arr))
    std_s = float(np.std(arr))
    outliers = int(np.sum(np.abs(arr) > 2))
    mean_near_zero = abs(mean_s) < 1.0

    print(f"  Scores:       {len(scores)}")
    print(f"  Mean:         {mean_s:.4f}  {'✅ near 0' if mean_near_zero else '⚠️ biased'}")
    print(f"  Std Dev:      {std_s:.4f}")
    print(f"  Outliers:     {outliers}  {'✅' if outliers == 0 else '⚠️'}")

    if mean_near_zero and outliers == 0:
        status = "WORKING"
    else:
        status = "WEAK"

    print(f"\n  {tag(status)} SIGNAL STABILITY")
    return status, {"mean": mean_s, "std": std_s, "outliers": outliers, "count": len(scores)}


# ── STEP 6: Statistical Performance ───────────────────────────────────────────

def audit_performance(data: dict, vol_data: dict) -> tuple[str, dict]:
    sep("STEP 6: STATISTICAL PERFORMANCE")

    ohlcv = vol_data["ohlcv"]
    closes = ohlcv["Close"].values
    returns = np.log(closes[1:] / closes[:-1])
    T = data["T"]
    N = len(returns)

    strategy_returns = []
    skipped = 0

    for i in range(TRAIN_WINDOW, min(N - 1, TRAIN_WINDOW + 200)):
        window = pd.Series(returns[i - TRAIN_WINDOW : i])
        try:
            from arch import arch_model
            pct = window * 100
            model = arch_model(pct, vol="EGARCH", p=1, q=1, dist="normal")
            fit = model.fit(disp="off", show_warning=False)
            fcast = fit.forecast(horizon=1)
            daily_vol = float(np.sqrt(fcast.variance.values[-1, 0])) / 100
            if daily_vol <= 0:
                skipped += 1
                continue
            egarch_ann = apply_dynamic_annualization(daily_vol, TIMEFRAME)
            egarch_ann = max(0.01, min(2.0, egarch_ann))
        except Exception:
            skipped += 1
            continue

        spot_i = float(closes[i])
        try:
            expiry_vol = egarch_ann * (T ** 0.5)
            fp = black_scholes_price(
                spot=spot_i, strike=spot_i, time_to_expiry=T,
                risk_free_rate=RISK_FREE_RATE, volatility=expiry_vol, option_type="call"
            )
            mkt_i = fp * 1.03
        except Exception:
            skipped += 1
            continue

        if fp <= 0:
            skipped += 1
            continue

        iv_i = calculate_implied_volatility(
            S=spot_i, K=spot_i, T=T, r=RISK_FREE_RATE,
            market_price=mkt_i, option_type="call"
        )
        price_score = (mkt_i - fp) / fp
        vol_score = (iv_i - egarch_ann) if iv_i is not None else 0.0
        final_score = 0.6 * price_score + 0.4 * vol_score

        direction = -1 if final_score > 0 else (1 if final_score < 0 else 0)
        future_ret = (closes[i + 1] - closes[i]) / closes[i]
        strategy_returns.append(direction * future_ret)

    trades = len(strategy_returns)
    if trades < 2:
        print(f"  ⚠️  Only {trades} trades")
        return "NO EDGE", {"sharpe": 0, "t_stat": 0, "hit_rate": 0, "trades": trades}

    sr = np.array(strategy_returns)
    mean_ret = float(np.mean(sr))
    std_dev = float(np.std(sr, ddof=1))
    sharpe = mean_ret / std_dev if std_dev > 0 else 0.0
    t_stat = mean_ret / (std_dev / math.sqrt(trades)) if std_dev > 0 else 0.0
    hit_rate = float(np.sum(sr > 0) / trades) * 100

    print(f"  Trades:       {trades}")
    print(f"  Skipped:      {skipped}")
    print(f"  Mean Return:  {mean_ret:.6f}")
    print(f"  Sharpe Ratio: {sharpe:.4f}")
    print(f"  t-Statistic:  {t_stat:.4f}")
    print(f"  Hit Rate:     {hit_rate:.1f}%")

    if sharpe > 1 and t_stat > 2:
        status = "STRONG"
    elif sharpe > 0.5:
        status = "WEAK"
    else:
        status = "NO EDGE"

    print(f"\n  {tag(status)} PERFORMANCE")
    return status, {"sharpe": round(sharpe, 4), "t_stat": round(t_stat, 4), "hit_rate": round(hit_rate, 2), "trades": trades}


# ── STEP 7 & 8: Final Classification & Report ─────────────────────────────────

def final_classification(layers: dict, metrics: dict):
    sep("SYSTEM CLASSIFICATION")

    # Step 7: Decide system status
    all_working = all(v == "WORKING" for k, v in layers.items() if k != "performance")
    data_broken = layers["data_layer"] == "BROKEN"
    vol_broken = layers["vol_layer"] == "BROKEN"
    perf = layers["performance"]

    if all_working and perf != "NO EDGE":
        system_status = "VALID QUANT SYSTEM"
    elif data_broken or vol_broken:
        system_status = "SYSTEM BROKEN"
    else:
        system_status = "FUNCTIONAL BUT NO EDGE"

    # Step 8: Structured report
    report = {
        "data_layer": layers["data_layer"],
        "volatility_layer": layers["vol_layer"],
        "pricing_layer": layers["pricing_layer"],
        "vol_signal_layer": layers["vol_signal_layer"],
        "signal_stability": layers["signal_stability"],
        "performance": layers["performance"],
        "system_status": system_status,
        "metrics": metrics
    }

    print(json.dumps(report, indent=2))

    # Visual summary
    print(f"\n  {'─'*40}")
    for key in ["data_layer", "vol_layer", "pricing_layer", "vol_signal_layer", "signal_stability", "performance"]:
        print(f"  {key:25s} {tag(layers[key])}")
    print(f"  {'─'*40}")

    icon = "🟢" if system_status == "VALID QUANT SYSTEM" else ("🟡" if "FUNCTIONAL" in system_status else "🔴")
    print(f"\n  {icon} SYSTEM STATUS: {system_status}\n")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    sep("OPTIONS MISPRICING ENGINE — FULL SYSTEM AUDIT")
    print(f"  Symbol:    {SYMBOL}")
    print(f"  Timeframe: {TIMEFRAME}")
    print(f"  Time:      {datetime.now(timezone.utc).isoformat()}")

    try:
        # Step 1
        data_status, data = audit_data_layer()
        if data_status == "BROKEN":
            final_classification(
                {"data_layer": "BROKEN", "vol_layer": "BROKEN", "pricing_layer": "BROKEN",
                 "vol_signal_layer": "BROKEN", "signal_stability": "BROKEN", "performance": "NO EDGE"},
                {"sharpe": 0, "t_stat": 0, "hit_rate": 0}
            )
            sys.exit(1)

        # Step 2
        vol_status, vol_data = audit_vol_layer(data)

        # Step 3
        pricing_status, pricing_data = audit_pricing_layer(data, vol_data)

        # Step 4
        vol_sig_status, vol_sig_data = audit_vol_signal(data, vol_data)

        # Step 5
        sig_status, sig_data = audit_signal_stability(data, vol_data)

        # Step 6
        perf_status, perf_data = audit_performance(data, vol_data)

        # Step 7 & 8
        layers = {
            "data_layer": data_status,
            "vol_layer": vol_status,
            "pricing_layer": pricing_status,
            "vol_signal_layer": vol_sig_status,
            "signal_stability": sig_status,
            "performance": perf_status,
        }
        final_classification(layers, perf_data)

    except Exception as e:
        sep("FATAL ERROR")
        print(f"  ❌ {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
