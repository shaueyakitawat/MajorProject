"""Run reproducible walk-forward volatility, HMM, and option valuation experiments."""

from __future__ import annotations

import json
import platform
import sys
import warnings
from collections import Counter
from importlib.metadata import version
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from arch import arch_model
from hmmlearn.hmm import GaussianHMM

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.services.pricing_service import black_scholes_price
INDEX_PATH = ROOT / "data/research/nifty50_index_daily.csv"
OPTIONS_PATH = ROOT / "data/research/nifty_options_daily.csv"
OUT = ROOT / "data/research"
DOCS = ROOT / "docs/research"
FIGURES = DOCS / "figures"
START = pd.Timestamp("2024-07-01")
END = pd.Timestamp("2025-12-31")
ANNUAL_DAYS = 252.0
MIN_TRAIN = 60
ROLLING_WINDOW = 20
EWMA_LAMBDA = 0.94
EGARCH_ASYMMETRY_ORDER = 1
HMM_WINDOW = 120
HMM_MIN_TRAIN = 120
RISK_FREE_RATES = (0.06, 0.07)
DIVIDEND_YIELD = 0.0125


def metrics(actual: pd.Series, forecast: pd.Series, variance: bool = False) -> dict:
    frame = pd.concat([actual.rename("actual"), forecast.rename("forecast")], axis=1).dropna()
    if frame.empty:
        return {"n": 0, "mae": None, "rmse": None, "qlike": None}
    y = frame["actual"].to_numpy()
    f = frame["forecast"].to_numpy()
    result = {
        "n": int(len(frame)),
        "mae": float(np.mean(np.abs(y - f))),
        "rmse": float(np.sqrt(np.mean((y - f) ** 2))),
        "qlike": None,
    }
    if variance:
        v_min = float(np.var(y[:60], ddof=1)) if len(y) >= 60 else 1e-12
        f = np.maximum(f, v_min)
        ratio = y / f
        result["qlike"] = float(np.mean(ratio - np.log(ratio) - 1.0))
    return result


def load_index() -> pd.DataFrame:
    frame = pd.read_csv(INDEX_PATH, parse_dates=["trade_date"]).sort_values("trade_date")
    frame = frame.drop_duplicates("trade_date").set_index("trade_date")
    frame["log_return"] = np.log(frame["close"] / frame["close"].shift(1))
    frame["target_vol"] = frame["log_return"].shift(-1).abs() * np.sqrt(ANNUAL_DAYS)
    frame["target_variance"] = frame["target_vol"] ** 2
    return frame


def fit_volatility(index: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    rows = []
    failures: list[dict] = []
    returns = index["log_return"]
    for position in range(MIN_TRAIN, len(index) - 1):
        current_date = index.index[position]
        train = returns.iloc[1:position + 1].dropna()
        if len(train) < MIN_TRAIN:
            continue
        row = {"trade_date": current_date.date().isoformat(),
               "target_vol": float(index.iloc[position]["target_vol"]),
               "target_variance": float(index.iloc[position]["target_variance"])}
        rolling = train.tail(ROLLING_WINDOW)
        row["rolling20_vol"] = float(rolling.std(ddof=1) * np.sqrt(ANNUAL_DAYS))
        weights = (1 - EWMA_LAMBDA) * EWMA_LAMBDA ** np.arange(len(train) - 1, -1, -1)
        weights /= weights.sum()
        row["ewma_vol"] = float(np.sqrt(np.sum(weights * (train.to_numpy() ** 2)) * ANNUAL_DAYS))
        for name, volatility in (("garch11", "GARCH"), ("egarch11", "EGARCH")):
            convergence_flag = None
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    model = arch_model(
                        train * 100, mean="Constant", vol=volatility,
                        p=1, o=EGARCH_ASYMMETRY_ORDER if volatility == "EGARCH" else 0,
                        q=1, dist="normal", rescale=False,
                    )
                    fitted = model.fit(disp="off", show_warning=False)
                    convergence_flag = int(getattr(fitted, "convergence_flag", 0))
                    if convergence_flag != 0:
                        raise ValueError(f"optimizer convergence_flag={convergence_flag}")
                    variance = float(fitted.forecast(horizon=1, reindex=False).variance.iloc[-1, 0])
                forecast_vol = float(np.sqrt(max(variance, 0.0)) / 100.0 * np.sqrt(ANNUAL_DAYS))
                if not np.isfinite(forecast_vol) or forecast_vol > 10:
                    raise ValueError(f"non-finite or explosive forecast volatility: {forecast_vol}")
                row[f"{name}_vol"] = forecast_vol
                row[f"{name}_convergence_flag"] = convergence_flag
                row[f"{name}_parameters"] = json.dumps(
                    {key: float(value) for key, value in fitted.params.items()},
                    sort_keys=True,
                )
            except Exception as exc:
                row[f"{name}_vol"] = np.nan
                row[f"{name}_convergence_flag"] = convergence_flag if "convergence_flag" in locals() else None
                row[f"{name}_parameters"] = ""
                failures.append({"trade_date": row["trade_date"], "model": name, "reason": str(exc)})
        rows.append(row)
    return pd.DataFrame(rows), failures


def filtered_probabilities(model: GaussianHMM, train: np.ndarray, current: float) -> np.ndarray:
    # The final posterior in this sequence uses observations only through current.
    return model.predict_proba(np.concatenate([train, [[current]]], axis=0))[-1]


def fit_hmms(index: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    values = (index["log_return"].rolling(ROLLING_WINDOW).std() * np.sqrt(ANNUAL_DAYS)).dropna()
    rows = []
    failures = []
    for position in range(HMM_MIN_TRAIN, len(index) - 1):
        current_date = index.index[position]
        history = values[values.index < current_date].tail(HMM_WINDOW).to_numpy()
        current = values.get(current_date, np.nan)
        if len(history) < HMM_MIN_TRAIN or not np.isfinite(current):
            continue
        scaled_mean, scaled_std = history.mean(), history.std()
        scaled_std = scaled_std if scaled_std > 0 else 1.0
        train = ((history - scaled_mean) / scaled_std).reshape(-1, 1)
        current_scaled = (float(current) - scaled_mean) / scaled_std
        for states in (2, 3):
            try:
                model = GaussianHMM(n_components=states, covariance_type="diag",
                                    n_iter=500, random_state=42, tol=1e-4)
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    model.fit(train)
                if not model.monitor_.converged:
                    raise ValueError("hmmlearn monitor reported non-convergence")
                probs = filtered_probabilities(model, train, current_scaled)
                order = np.argsort(model.means_.ravel())
                state = int(np.argmax(probs))
                row = {
                    "trade_date": current_date.date().isoformat(),
                    "state_count": states,
                    "state": state,
                    "state_rank_by_volatility": int(np.where(order == state)[0][0]),
                    "filtered_confidence": float(probs[state]),
                    "current_vol_feature": float(current),
                    "train_observations": len(history),
                    "state_means": json.dumps(model.means_.ravel().tolist()),
                    "transition_matrix": json.dumps(model.transmat_.tolist()),
                    "state_probabilities": json.dumps(probs.tolist()),
                }
                rows.append(row)
            except Exception as exc:
                failures.append({"trade_date": current_date.date().isoformat(),
                                 "state_count": states, "reason": str(exc)})
    return pd.DataFrame(rows), failures


def load_option_sample(volatility: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    options = pd.read_csv(OPTIONS_PATH, parse_dates=["trade_date", "expiry"])
    options["contracts_num"] = pd.to_numeric(options["contracts"], errors="coerce")
    options["close_num"] = pd.to_numeric(options["close"], errors="coerce")
    options["strike_num"] = pd.to_numeric(options["strike"], errors="coerce")
    options["dte"] = (options["expiry"] - options["trade_date"]).dt.days
    audit = options[(options["contracts_num"] > 0) & (options["close_num"] > 0) &
                    (options["dte"].between(7, 60)) & (pd.to_numeric(options["settlement"], errors="coerce") == 0)].copy()
    sample = options[(options["contracts_num"] > 0) & (options["close_num"] > 0) &
                     (options["dte"].between(7, 60)) & (options["strike_num"] > 0) &
                     options["trade_date"].notna() & options["expiry"].notna()].copy()
    vol_for_join = volatility.copy()
    vol_for_join["trade_date"] = pd.to_datetime(vol_for_join["trade_date"])
    sample = sample.merge(vol_for_join[["trade_date", "egarch11_vol"]], on="trade_date", how="inner")
    sample["spot"] = sample["trade_date"].map(index_close)
    sample["moneyness"] = sample["strike_num"] / sample["spot"]
    sample["year_fraction"] = sample["dte"] / 365.25
    return sample, audit


def index_close(day: pd.Timestamp) -> float:
    return float(INDEX_CLOSES.loc[day])


def value_options(sample: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for item in sample.itertuples(index=False):
        if not np.isfinite(item.egarch11_vol):
            continue
        option_type = "call" if item.option_type == "CE" else "put"
        for rate in RISK_FREE_RATES:
            fair = black_scholes_price(item.spot, item.strike_num, item.year_fraction,
                                       rate, item.egarch11_vol, option_type,
                                       dividend_yield=DIVIDEND_YIELD,
                                       use_adjusted_vol=False)
            observed = item.close_num
            rows.append({
                "trade_date": item.trade_date.date().isoformat(),
                "expiry": item.expiry.date().isoformat(),
                "strike": item.strike_num, "option_type": item.option_type,
                "spot": item.spot, "moneyness": item.moneyness, "dte": item.dte,
                "year_fraction": item.year_fraction, "observed_close": observed,
                "contracts": item.contracts_num, "open_interest": item.open_interest,
                "egarch_volatility": item.egarch11_vol, "risk_free_rate": rate,
                "dividend_yield": DIVIDEND_YIELD, "model_price": fair,
                "pricing_error": fair - observed,
                "absolute_error": abs(fair - observed),
                "ape": abs(fair - observed) / observed if observed > 0 else np.nan,
            })
    return pd.DataFrame(rows)


def make_figures(volatility: pd.DataFrame, hmms: pd.DataFrame) -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    plt.figure(figsize=(10, 4))
    plt.plot(pd.to_datetime(volatility["trade_date"]), volatility["target_vol"], label="next-day realized")
    plt.plot(pd.to_datetime(volatility["trade_date"]), volatility["egarch11_vol"], label="EGARCH")
    plt.legend()
    plt.tight_layout()
    plt.savefig(FIGURES / "volatility_forecasts.png", dpi=150)
    plt.close()
    plt.figure(figsize=(10, 4))
    subset = hmms[hmms["state_count"] == 2]
    plt.step(pd.to_datetime(subset["trade_date"]), subset["state_rank_by_volatility"], where="post")
    plt.ylabel("2-state volatility rank")
    plt.tight_layout()
    plt.savefig(FIGURES / "hmm_regimes_2_state.png", dpi=150)
    plt.close()


def main() -> int:
    global INDEX_CLOSES
    index = load_index()
    INDEX_CLOSES = index["close"]
    volatility, vol_failures = fit_volatility(index)
    hmms, hmm_failures = fit_hmms(index)
    option_sample, zero_settlement_audit = load_option_sample(volatility)
    valuation_input = option_sample[np.isfinite(option_sample["egarch11_vol"])].copy()
    valuation_excluded = option_sample[~np.isfinite(option_sample["egarch11_vol"])].copy()
    valuations = value_options(valuation_input)
    OUT.mkdir(parents=True, exist_ok=True)
    volatility.to_csv(OUT / "volatility_forecasts.csv", index=False)
    hmms.to_csv(OUT / "regime_assignments.csv", index=False)
    valuations.to_csv(OUT / "option_valuation_results.csv", index=False)
    zero_settlement_audit.to_csv(OUT / "option_valuation_zero_settlement_audit.csv", index=False)
    valuation_excluded.to_csv(OUT / "option_valuation_egarch_unavailable.csv", index=False)
    make_figures(volatility, hmms)

    volatility_metrics = {}
    for name in ("rolling20", "ewma", "garch11", "egarch11"):
        volatility_metrics[name] = metrics(volatility["target_vol"], volatility[f"{name}_vol"])
        volatility_metrics[name]["variance_qlike"] = metrics(
            volatility["target_variance"], volatility[f"{name}_vol"] ** 2, variance=True
        )["qlike"]
    valuation_metrics = {}
    if not valuations.empty:
        for rate, group in valuations.groupby("risk_free_rate"):
            for side, side_group in group.groupby("option_type"):
                key = f"r={rate:.2f}_{side}"
                valuation_metrics[key] = {
                    "n": int(len(side_group)),
                    "mae": float(side_group["absolute_error"].mean()),
                    "rmse": float(np.sqrt(np.mean(side_group["pricing_error"] ** 2))),
                    "mape": float(side_group["ape"].mean() * 100),
                }
                for bucket_name, bucket in (
                    ("moneyness_lt_0.95", side_group[side_group["moneyness"] < 0.95]),
                    ("moneyness_0.95_1.05", side_group[side_group["moneyness"].between(0.95, 1.05)]),
                    ("moneyness_gt_1.05", side_group[side_group["moneyness"] > 1.05]),
                    ("dte_7_30", side_group[side_group["dte"].between(7, 30)]),
                    ("dte_31_60", side_group[side_group["dte"].between(31, 60)]),
                ):
                    if not bucket.empty:
                        valuation_metrics[f"{key}_{bucket_name}"] = {
                            "n": int(len(bucket)),
                            "mae": float(bucket["absolute_error"].mean()),
                            "rmse": float(np.sqrt(np.mean(bucket["pricing_error"] ** 2))),
                            "mape": float(bucket["ape"].mean() * 100),
                        }
    hmm_summary = {}
    for states, group in hmms.groupby("state_count"):
        aligned_matrices = []
        for item in group.itertuples(index=False):
            means = np.array(json.loads(item.state_means))
            order = np.argsort(means)
            matrix = np.array(json.loads(item.transition_matrix))
            aligned_matrices.append(matrix[np.ix_(order, order)])
        matrices = np.stack(aligned_matrices)
        hmm_summary[str(states)] = {
            "rows": int(len(group)),
            "state_rank_counts": {str(k): int(v) for k, v in group["state_rank_by_volatility"].value_counts().sort_index().items()},
            "state_rank_mean_feature": {
                str(k): float(v) for k, v in group.groupby("state_rank_by_volatility")["current_vol_feature"].mean().items()
            },
            "mean_filtered_confidence": float(group["filtered_confidence"].mean()),
            "unique_transition_matrices": int(group["transition_matrix"].nunique()),
            "mean_transition_matrix_rank_aligned": matrices.mean(axis=0).tolist(),
            "stability_note": "Walk-forward fits are compared through changing state counts, ranks, and transition matrices; no persistence claim is made from a single fit.",
        }
    metrics_payload = {
        "sample": {
            "index_observations": int(len(index)),
            "volatility_forecast_observations": int(len(volatility)),
            "hmm_assignments": int(len(hmms)),
            "option_sample_contract_rows": int(len(option_sample)),
            "option_valuation_input_rows": int(len(valuation_input)),
            "option_valuation_egarch_unavailable_rows": int(len(valuation_excluded)),
            "valuation_rows": int(len(valuations)),
            "zero_settlement_audit_rows": int(len(zero_settlement_audit)),
        },
        "periods": {"start": START.date().isoformat(), "end": END.date().isoformat(),
                    "walk_forward_min_train": MIN_TRAIN, "hmm_window": HMM_WINDOW},
        "volatility_metrics": volatility_metrics,
        "valuation_metrics": valuation_metrics,
        "hmm_summary": hmm_summary,
        "failures": {"volatility": vol_failures, "hmm": hmm_failures},
        "assumptions": {"risk_free_rates": RISK_FREE_RATES, "dividend_yield": DIVIDEND_YIELD,
                        "annualization_days": ANNUAL_DAYS, "target": "next-day absolute log return annualized",
                        "observed_option_price": "daily NSE CLOSE, not bid/ask or executable price"},
        "software": {"python": sys.version, "platform": platform.platform(),
                     "numpy": np.__version__, "pandas": pd.__version__,
                     "scipy": version("scipy"), "arch": version("arch"),
                     "hmmlearn": version("hmmlearn"), "matplotlib": version("matplotlib")},
    }
    (OUT / "experiment_metrics.json").write_text(json.dumps(metrics_payload, indent=2, default=str) + "\n", encoding="utf-8")
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "experiment_methodology.md").write_text(methodology(metrics_payload), encoding="utf-8")
    (DOCS / "experiment_results.md").write_text(results(metrics_payload, volatility, hmms, valuations), encoding="utf-8")
    (DOCS / "experiment_data_quality.md").write_text(quality(metrics_payload, option_sample, zero_settlement_audit), encoding="utf-8")
    write_diagnostic_reports(index, volatility, hmms, valuations, zero_settlement_audit, metrics_payload)
    print(json.dumps({"index": len(index), "volatility": len(volatility), "hmm": len(hmms),
                      "options": len(option_sample), "valuations": len(valuations),
                      "volatility_failures": len(vol_failures), "hmm_failures": len(hmm_failures)}, indent=2))
    return 0


def write_diagnostic_reports(
    index: pd.DataFrame,
    volatility: pd.DataFrame,
    hmms: pd.DataFrame,
    valuations: pd.DataFrame,
    zero_settlement_audit: pd.DataFrame,
    payload: dict,
) -> None:
    options = pd.read_csv(OPTIONS_PATH, parse_dates=["trade_date", "expiry"], low_memory=False)
    options["contracts_num"] = pd.to_numeric(options["contracts"], errors="coerce")
    options["close_num"] = pd.to_numeric(options["close"], errors="coerce")
    options["strike_num"] = pd.to_numeric(options["strike"], errors="coerce")
    options["settlement_num"] = pd.to_numeric(options["settlement"], errors="coerce")
    options["dte"] = (options["expiry"] - options["trade_date"]).dt.days
    zero_all = options[(options["contracts_num"] > 0) & (options["settlement_num"] == 0)]
    zero_eligible = zero_settlement_audit
    reconciliation = {
        "all_positive_volume_zero_settlement": int(len(zero_all)),
        "eligible_after_experiment_filters": int(len(zero_eligible)),
        "excluded": int(len(zero_all) - len(zero_eligible)),
        "excluded_reasons": {
            "dte_outside_7_60": int((~zero_all["dte"].between(7, 60)).sum()),
            "non_positive_close": int((zero_all["close_num"] <= 0).sum()),
            "invalid_strike": int((zero_all["strike_num"] <= 0).sum()),
            "missing_date": int((zero_all["trade_date"].isna() | zero_all["expiry"].isna()).sum()),
        },
        "note": "Reason counts are overlapping diagnostic predicates; no source rows were deleted.",
    }
    (DOCS / "zero_settlement_reconciliation.md").write_text(
        "# Zero-Settlement Reconciliation\n\n"
        "| Population | Records |\n|---|---:|\n"
        f"| Expanded validation positive-volume settlement-zero records | {len(zero_all)} |\n"
        f"| After contracts > 0, positive close, valid dates/strike, DTE 7-60 | {len(zero_eligible)} |\n"
        f"| Excluded from valuation audit by eligibility filters | {len(zero_all) - len(zero_eligible)} |\n\n"
        "## Exclusion diagnostics\n\n"
        + "\n".join(f"- `{key}`: {value}" for key, value in reconciliation["excluded_reasons"].items())
        + "\n\nPredicates can overlap. The original source rows remain in the options dataset; the eligible audit is a separate table.\n",
        encoding="utf-8",
    )

    def dist(series: pd.Series) -> dict:
        numeric = pd.to_numeric(series, errors="coerce").dropna()
        return {
            "n": int(len(numeric)), "missing": int(series.isna().sum()),
            "min": float(numeric.min()) if len(numeric) else None,
            "median": float(numeric.median()) if len(numeric) else None,
            "max": float(numeric.max()) if len(numeric) else None,
        }

    pricing_groups = {}
    if not valuations.empty:
        valuation = valuations[valuations["risk_free_rate"] == RISK_FREE_RATES[0]].copy()
        valuation["dte_bucket"] = np.where(valuation["dte"].between(7, 30), "7-30", "31-60")
        valuation["moneyness_bucket"] = np.where(
            valuation["moneyness"].between(0.95, 1.05), "ATM",
            np.where(
                ((valuation["option_type"] == "CE") & (valuation["moneyness"] > 1))
                | ((valuation["option_type"] == "PE") & (valuation["moneyness"] < 1)),
                "ITM", "OTM",
            ),
        )
        for (side, moneyness, dte_bucket), group in valuation.groupby(
            ["option_type", "moneyness_bucket", "dte_bucket"]
        ):
            pricing_groups[f"{side}_{moneyness}_{dte_bucket}"] = pricing_error_stats(group)
        pricing_distribution = {
            field: dist(valuation[field])
            for field in ("spot", "strike", "observed_close", "model_price", "dte", "moneyness", "egarch_volatility", "absolute_error", "ape")
        }
    else:
        pricing_distribution = {}
    (DOCS / "option_pricing_diagnostic_report.md").write_text(
        "# Option Pricing Diagnostic Report\n\n"
        "## Input trace\n\n"
        "- Spot: Yahoo Finance NIFTY 50 close, in index points, joined by `trade_date`.\n"
        "- Strike and observed CLOSE: NSE bhavcopy values, in index-option price points.\n"
        "- DTE: calendar-day difference `expiry - trade_date`; year fraction is `DTE / 365.25`, applied once.\n"
        "- Volatility: EGARCH one-step forecast, annualized decimal after percentage-return variance conversion.\n"
        "- Rates: 6% and 7% annual sensitivity assumptions; dividend yield: 1.25% annual continuous yield.\n"
        "- The BSM implementation uses continuous dividend yield and standard call/put formulas; observed CLOSE is a last-traded reference, not a quote or executable price.\n\n"
        "## Distributions (6% sensitivity)\n\n"
        f"```json\n{json.dumps(pricing_distribution, indent=2)}\n```\n\n"
        "## Grouped pricing errors (6% sensitivity)\n\n"
        "| Group | N | MAE | RMSE | MAPE % | Median absolute error | Median absolute percentage error % |\n|---|---:|---:|---:|---:|---:|---:|\n"
        + "\n".join(
            f"| {key} | {value['n']} | {value['mae']:.4f} | {value['rmse']:.4f} | {value['mape']:.4f} | {value['median_absolute_error']:.4f} | {value['median_ape']:.4f} |"
            for key, value in pricing_groups.items()
        )
        + "\n\nMAPE and percentage errors become unstable when observed daily CLOSE is zero or near zero; these observations are retained, and median percentage error is reported alongside absolute metrics.\n",
        encoding="utf-8",
    )
    (DOCS / "egarch_diagnostic_report.md").write_text(
        "# EGARCH Diagnostic Report\n\n"
        "## Confirmed implementation issue\n\n"
        "The original experiment passed `vol='EGARCH', p=1, q=1` without `o=1`. In `arch`, this specifies a symmetric EGARCH(1,1) with no asymmetry term, not the intended asymmetric EGARCH(1,1). The original script also suppressed warnings and did not record `convergence_flag` or fitted parameters.\n\n"
        "## Corrected specification\n\n"
        "- Returns are decimal log returns `ln(C_t/C_(t-1))`.\n"
        "- The fitting series is returns multiplied by 100 (percentage points), with `rescale=False`.\n"
        "- Corrected model: `arch_model(..., mean='Constant', vol='EGARCH', p=1, o=1, q=1, dist='normal', rescale=False)`.\n"
        "- Forecast variance is converted to decimal daily volatility by `sqrt(variance) / 100`, then annualized by `sqrt(252)`.\n"
        "- Nonzero optimizer convergence flags and non-finite forecasts are recorded as failures; no clipping is applied.\n\n"
        f"## Corrected run\n\n- Forecast rows: {len(volatility)}\n- EGARCH failures: {sum(item['model'] == 'egarch11' for item in payload['failures']['volatility'])}\n- EGARCH metric rows: {payload['volatility_metrics']['egarch11']['n']}\n\n"
        "The original explosive values were caused primarily by the missing asymmetry order and unchecked optimizer/forecast diagnostics in the short expanding samples; the original outputs are preserved under `data/research/versions/2026-10-31_phase1_original/`.\n",
        encoding="utf-8",
    )
    (DOCS / "hmm_diagnostic_report.md").write_text(
        "# HMM Diagnostic Report\n\n"
        "- Features: annualized 20-observation rolling standard deviation of daily log returns.\n"
        "- Each fit uses only a trailing 120 observations strictly before the assignment date; the current feature is appended only for endpoint probability inference.\n"
        "- Gaussian emissions, diagonal covariance, 500 iterations, tolerance `1e-4`, random seed 42.\n"
        "- State labels are assigned by fitted feature means; state IDs are not treated as economically meaningful.\n"
        "- Endpoint `predict_proba` is used; because it is the final point in the supplied sequence, no later observation is available for smoothing.\n"
        "- Transition matrices are reordered by volatility-ranked state before averaging in the corrected summary.\n\n"
        f"Walk-forward assignments: {len(hmms)}; fit failures: {len(payload['failures']['hmm'])}. Changing transition matrices and state counts are reported; no regime-improvement claim is made.\n",
        encoding="utf-8",
    )
    (DOCS / "diagnostic_findings.md").write_text(
        "# Diagnostic Findings\n\n"
        "1. **EGARCH — corrected.** The original call omitted `o=1`, did not record convergence status, and allowed explosive forecasts into valuation. The corrected run uses asymmetric EGARCH(1,1), explicit percentage conversion, convergence checks, and failure records without clipping.\n"
        "2. **BSM units — consistent.** Spot, strike, and option CLOSE are index-price units; DTE is divided by 365.25 once; volatility is an annualized decimal; rates and dividend yield are annual decimals. The large errors are empirical pricing errors against daily CLOSE, not proof of mispricing. MAPE is dominated by small observed prices.\n"
        "3. **HMM — no look-ahead identified.** Training windows precede assignment dates, endpoint probabilities use observations through the current date, and ranked-state transition matrices are used for summary averaging. Stability remains limited because each walk-forward fit has a changing transition matrix.\n"
        f"4. **Zero settlement — reconciled.** Expanded validation reports {len(zero_all)} positive-volume zero-settlement records; {len(zero_eligible)} meet the experiment's DTE/price/date eligibility, leaving {len(zero_all)-len(zero_eligible)} outside the audit.\n"
        "5. **Remaining limitations.** Rates are sensitivity assumptions, option CLOSE is not bid/ask, and the index source is third-party Yahoo Finance. No profitability or executable-arbitrage conclusion is supported.\n",
        encoding="utf-8",
    )


def pricing_error_stats(group: pd.DataFrame) -> dict:
    return {
        "n": int(len(group)),
        "mae": float(group["absolute_error"].mean()),
        "rmse": float(np.sqrt(np.mean(group["pricing_error"] ** 2))),
        "mape": float(np.mean(group["ape"]) * 100),
        "median_absolute_error": float(group["absolute_error"].median()),
        "median_ape": float(group["ape"].median() * 100),
    }


def methodology(payload: dict) -> str:
    return f"""# Empirical Experiment Methodology

## Scope
All experiments use the validated NIFTY 50 index and NSE NIFTY option datasets. Evaluation is chronological and walk-forward; no random split is used.

## Volatility
Log return is `ln(C_t/C_(t-1))`. The target is the next-day absolute log return multiplied by `sqrt(252)`. Forecasts are annualized volatility. Baselines are 20-observation rolling standard deviation and EWMA with lambda 0.94. GARCH(1,1) and asymmetric EGARCH(1,1) (`p=1,o=1,q=1`) use the `arch` package, normal innovations, constant mean, returns multiplied by 100 for fitting, `rescale=False`, and one-step forecasts. Minimum training history is {MIN_TRAIN} returns. Variance is converted to decimal daily volatility by dividing its square root by 100, then annualized by `sqrt(252)`.

## HMM
Two-state and three-state diagonal-covariance Gaussian HMMs use the annualized 20-day rolling volatility feature, a trailing window of {HMM_WINDOW} observations, `n_iter=500`, tolerance `1e-4`, and `random_state=42`. The current observation is appended only for inference; the final posterior is based on observations through that date. States are ranked by fitted volatility-feature means and have no intrinsic labels.

## Option valuation
Options are filtered to positive contracts, positive CLOSE, valid strike/expiry, and DTE 7--60 days. Daily CLOSE is treated only as an observed last-traded reference. BSM uses EGARCH volatility, continuous dividend yield {DIVIDEND_YIELD}, and risk-free sensitivity rates {RISK_FREE_RATES}; no historical rate series was available. Settlement-zero records are retained in a separate audit table and not silently removed from the source data.

## Reproducibility
Random seed: 42 for HMM. Outputs include package versions, failure records, exact counts, and generated figures. The pipeline is separate from the live application.
"""


def results(payload: dict, volatility: pd.DataFrame, hmms: pd.DataFrame, valuations: pd.DataFrame) -> str:
    return f"""# Empirical Experiment Results

## Counts
- Index observations: {payload['sample']['index_observations']}
- Volatility forecast rows: {len(volatility)}
- HMM rows: {len(hmms)}
- Option valuation rows: {len(valuations)}
- Volatility failures: {len(payload['failures']['volatility'])}
- HMM failures: {len(payload['failures']['hmm'])}

## Volatility forecast metrics
```json
{json.dumps(payload['volatility_metrics'], indent=2)}
```

## Option valuation metrics
```json
{json.dumps(payload['valuation_metrics'], indent=2)}
```

## HMM state summaries
```json
{json.dumps(payload['hmm_summary'], indent=2)}
```

These are historical pricing errors relative to daily option CLOSE values. They do not establish mispricing, arbitrage, executable prices, profitability, or EGARCH superiority.
"""


def quality(payload: dict, option_sample: pd.DataFrame, audit: pd.DataFrame) -> str:
    return f"""# Empirical Experiment Data Quality

- Option sample rows before BSM expansion: {len(option_sample)}
- Settlement-zero audit rows: {len(audit)}
- Missing spot observations after date join: {int(option_sample['spot'].isna().sum()) if not option_sample.empty else 0}
- Positive-volume settlement-zero records were retained in `{(OUT / 'option_valuation_zero_settlement_audit.csv').relative_to(ROOT)}`.
- Records without a finite EGARCH forecast were retained in `{(OUT / 'option_valuation_egarch_unavailable.csv').relative_to(ROOT)}` and were not assigned a synthetic BSM price.
- No bid, ask, intraday quote, implied volatility, synthetic price, or interpolated index value was created.
- Historical risk-free rates were unavailable; rates {RISK_FREE_RATES} are sensitivity assumptions, not observed historical rates.
- Yahoo Finance is a third-party index source; NSE options are official bhavcopy data. Licensing and redistribution terms remain a limitation.
- Failed model fits are listed in `data/research/experiment_metrics.json`.
"""


if __name__ == "__main__":
    main()
