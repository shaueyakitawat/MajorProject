"""
Functional verification of the Options Mispricing Detection pipeline.
Tests each service with real data from Yahoo Finance.
"""
import sys, os, warnings, math, time
warnings.filterwarnings('ignore')

os.environ.setdefault("PYTHONPATH", r"d:\MajorProject")
sys.path.insert(0, r"d:\MajorProject")

results = {}

def record(name, status, detail=""):
    results[name] = {"status": status, "detail": detail}
    icon = "[OK]" if status == "PASS" else "[FAIL]"
    print(f"  {icon} {name}: {detail}")

print("=" * 60)
print("  FUNCTIONAL VERIFICATION - Real Pipeline Test")
print("=" * 60)

# ── TEST A: Data Fetch ──────────────────────────────────
print("\n--- TEST A: Fetch NIFTY daily data from Yahoo Finance ---")
try:
    from backend.services.data_service import fetch_nifty_data, compute_log_returns
    t0 = time.time()
    data = fetch_nifty_data(symbol="NIFTY", timeframe="daily")
    elapsed = time.time() - t0
    record("data_fetch", "PASS", f"Fetched {len(data)} rows in {elapsed:.1f}s, last close={data['Close'].iloc[-1]:.2f}")
except Exception as e:
    record("data_fetch", "FAIL", str(e))
    print("  Cannot continue without data. Exiting.")
    sys.exit(1)

# ── TEST B: Log Returns ──────────────────────────────────
print("\n--- TEST B: Compute log returns ---")
try:
    data_with_returns = compute_log_returns(data)
    returns = data_with_returns["log_return"]
    record("log_returns", "PASS", f"{len(returns)} values, mean={returns.mean():.6f}, std={returns.std():.6f}")
except Exception as e:
    record("log_returns", "FAIL", str(e))
    sys.exit(1)

# ── TEST C: EGARCH Volatility Forecast ────────────────────
print("\n--- TEST C: EGARCH(1,1) volatility forecast ---")
try:
    from backend.services.volatility_service import forecast_volatility
    t0 = time.time()
    vol_payload = forecast_volatility(returns)
    elapsed = time.time() - t0
    final_vol = vol_payload["final_vol"]
    vol_ok = 0.05 < final_vol < 1.0 and math.isfinite(final_vol)
    tci_info = vol_payload.get("tci")
    record("egarch_forecast", "PASS" if vol_ok else "FAIL",
           f"daily={vol_payload['daily_vol']:.4f}, final={final_vol:.4f} ({final_vol*100:.1f}%), time={elapsed:.1f}s, tci={tci_info}")
except Exception as e:
    record("egarch_forecast", "FAIL", str(e))
    import traceback; traceback.print_exc()
    final_vol = 0.20

# ── TEST D: Black-Scholes Pricing ─────────────────────────
print("\n--- TEST D: Black-Scholes pricing ---")
try:
    from backend.services.pricing_service import black_scholes_price
    spot = float(data_with_returns["Close"].iloc[-1])
    fair_call = black_scholes_price(spot=spot, strike=spot, time_to_expiry=0.1, risk_free_rate=0.06, volatility=final_vol, option_type="call")
    fair_put = black_scholes_price(spot=spot, strike=spot, time_to_expiry=0.1, risk_free_rate=0.06, volatility=final_vol, option_type="put")
    pricing_ok = fair_call > 0 and fair_put > 0
    record("bs_pricing", "PASS" if pricing_ok else "FAIL",
           f"spot={spot:.2f}, call={fair_call:.4f}, put={fair_put:.4f}")
except Exception as e:
    record("bs_pricing", "FAIL", str(e))
    fair_call = 100.0

# ── TEST E: Implied Volatility ────────────────────────────
print("\n--- TEST E: Implied Volatility solver ---")
try:
    from backend.services.implied_volatility_service import calculate_implied_volatility, classify_vol_spread
    market_price = fair_call * 1.05
    iv = calculate_implied_volatility(S=spot, K=spot, T=0.1, r=0.06, market_price=market_price, option_type="call")
    vol_spread, vol_signal = classify_vol_spread(iv, final_vol)
    iv_ok = iv is not None and iv > 0
    if iv_ok:
        record("iv_solver", "PASS", f"IV={iv:.4f} ({iv*100:.1f}%), spread={vol_spread:.4f}, signal={vol_signal}")
    else:
        record("iv_solver", "FAIL", "IV solver returned None")
except Exception as e:
    record("iv_solver", "FAIL", str(e))
    iv = final_vol * 1.1

# ── TEST F: VRP ───────────────────────────────────────────
print("\n--- TEST F: VRP computation ---")
try:
    from backend.services.vrp_service import compute_vrp
    vrp_result = compute_vrp(iv, final_vol)
    vrp_ok = vrp_result["vrp"] is not None
    record("vrp", "PASS" if vrp_ok else "FAIL",
           f"VRP={vrp_result['vrp']:.6f}, expected={vrp_result['expected_vrp']}")
except Exception as e:
    record("vrp", "FAIL", str(e))
    vrp_result = {"vrp": 0.01, "expected_vrp": None}

# ── TEST G: Regime Classification ─────────────────────────
print("\n--- TEST G: Regime classification (HMM) ---")
try:
    from backend.services.regime_service import classify_volatility_regime
    import numpy as np

    regime_fallback = classify_volatility_regime(final_vol)
    print(f"  Fallback (no HMM data): {regime_fallback}")

    rolling_vol = returns.rolling(window=60).std() * np.sqrt(252)
    rolling_vol = rolling_vol.dropna()
    regime = classify_volatility_regime(final_vol, vol_series=rolling_vol)
    hmm_ok = regime["confidence"] > 0
    record("regime_hmm", "PASS" if hmm_ok else "FAIL",
           f"regime={regime['regime_label']}, confidence={regime['confidence']:.4f}")
    regime_label = regime["regime_label"]
except Exception as e:
    record("regime_hmm", "FAIL", str(e))
    import traceback; traceback.print_exc()
    regime_label = "NORMAL_VOL"

# ── TEST H: Mispricing Detection ──────────────────────────
print("\n--- TEST H: Mispricing detection (MScore + Z-score) ---")
try:
    from backend.services.mispricing_service import detect_mispricing
    mispricing = detect_mispricing(
        market_price, fair_call,
        vega=0.15, gamma=0.002, tci=vol_payload.get("tci"),
        current_vrp=vrp_result["vrp"],
        expected_vrp=vrp_result["expected_vrp"]
    )
    record("mispricing", "PASS",
           f"dev={mispricing['deviation']*100:.2f}%, class={mispricing['classification']}, m_score={mispricing['m_score']:.6f}, z={mispricing['z_score']:.4f}")
except Exception as e:
    record("mispricing", "FAIL", str(e))
    mispricing = {"classification": "overpriced", "z_score": 0.5}

# ── TEST I: Strategy Generation ───────────────────────────
print("\n--- TEST I: Strategy generation ---")
try:
    from backend.services.strategy_service import generate_strategy
    strategy = generate_strategy(
        mispricing["classification"], regime_label,
        sigma_adj=final_vol, iv=iv,
        z_score=mispricing["z_score"], atm_strike=spot
    )
    record("strategy", "PASS",
           f"type={strategy['strategy_type']}, structure={strategy['structure_name']}, confidence={strategy['confidence']}")
except Exception as e:
    record("strategy", "FAIL", str(e))

# ── TEST J: FastAPI app ─────────────────────────────────
print("\n--- TEST J: FastAPI app object ---")
try:
    from main import app
    routes = [r.path for r in app.routes if hasattr(r, "path")]
    record("fastapi_app", "PASS", f"{len(routes)} routes loaded")
except Exception as e:
    record("fastapi_app", "FAIL", str(e))
    import traceback; traceback.print_exc()

# ── SUMMARY ───────────────────────────────────────────────
print("\n" + "=" * 60)
print("  VERIFICATION SUMMARY")
print("=" * 60)
passed = sum(1 for r in results.values() if r["status"] == "PASS")
failed = sum(1 for r in results.values() if r["status"] == "FAIL")
total = len(results)
print(f"\n  PASSED: {passed}/{total}")
print(f"  FAILED: {failed}/{total}")
for name, r in results.items():
    icon = "PASS" if r["status"] == "PASS" else "FAIL"
    print(f"  [{icon}] {name}")
print()
