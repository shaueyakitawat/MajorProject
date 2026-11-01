"""Run horizon-consistent EGARCH and option valuation validation."""

from __future__ import annotations

import json
import math
import platform
import sys
import warnings
from importlib.metadata import version
from pathlib import Path

import numpy as np
import pandas as pd
from arch import arch_model
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.services.pricing_service import black_scholes_price

INDEX_PATH = ROOT / "data/research/nifty50_index_daily.csv"
OPTIONS_PATH = ROOT / "data/research/nifty_options_daily.csv"
PHASE1_FORECASTS = ROOT / "data/research/volatility_forecasts.csv"
OUT = ROOT / "data/research/phase2"
DOCS = ROOT / "docs/research"
ANNUAL_DAYS = 252.0
ROLLING_WINDOW = 20
EWMA_LAMBDA = 0.94
RISK_FREE_RATE = 0.06
DIVIDEND_YIELD = 0.0125
INIT_LENGTHS = (60, 90, 120)


def load_index() -> pd.DataFrame:
    frame = pd.read_csv(INDEX_PATH, parse_dates=["trade_date"]).sort_values("trade_date")
    frame = frame.drop_duplicates("trade_date").set_index("trade_date")
    frame["log_return"] = np.log(frame["close"] / frame["close"].shift(1))
    return frame


def fit_egarch_forecast(
    returns: pd.Series, position: int, minimum_history: int, horizon: int
) -> tuple[dict | None, dict | None]:
    train = returns.iloc[1:position + 1].dropna()
    if len(train) < minimum_history:
        return None, {"reason": "insufficient_history", "history": len(train)}
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = arch_model(
                train * 100,
                mean="Constant",
                vol="EGARCH",
                p=1,
                o=1,
                q=1,
                dist="normal",
                rescale=False,
            )
            fitted = model.fit(disp="off", show_warning=False)
        convergence_flag = int(getattr(fitted, "convergence_flag", 0))
        if convergence_flag != 0:
            return None, {
                "reason": f"optimizer convergence_flag={convergence_flag}",
                "history": len(train),
                "parameters": {k: float(v) for k, v in fitted.params.items()},
            }
        first_forecast = fitted.forecast(horizon=1, reindex=False).variance.iloc[-1, 0]
        if horizon == 1:
            forecasts = np.array([first_forecast], dtype=float)
        else:
            # Under normal innovations, future standardized shock terms have
            # zero expectation, so EGARCH log variance follows its beta recursion.
            params = fitted.params
            beta = float(params["beta[1]"])
            omega = float(params["omega"])
            forecasts = np.empty(horizon, dtype=float)
            forecasts[0] = first_forecast
            for step in range(1, horizon):
                forecasts[step] = math.exp(
                    omega + beta * math.log(forecasts[step - 1])
                )
        if len(forecasts) != horizon or not np.all(np.isfinite(forecasts)) or np.any(forecasts < 0):
            return None, {"reason": "invalid forecast variance", "history": len(train)}
        parameters = {k: float(v) for k, v in fitted.params.items()}
        return {
            "daily_variances": (forecasts / 10000.0).tolist(),
            "parameters": parameters,
            "convergence_flag": convergence_flag,
            "history": len(train),
        }, None
    except Exception as exc:
        return None, {"reason": str(exc), "history": len(train)}


def calculate_forecasts(index: pd.DataFrame) -> tuple[pd.DataFrame, list[dict], pd.DataFrame]:
    returns = index["log_return"]
    dates = index.index
    rows = []
    failures = []
    stability_rows = []
    for position in range(60, len(index) - 1):
        day = dates[position]
        future_count = len(dates[position + 1:])
        if future_count < 1:
            continue
        horizon = min(future_count, 60)
        one, error = fit_egarch_forecast(returns, position, 60, 1)
        long, long_error = fit_egarch_forecast(returns, position, 60, horizon)
        if error:
            failures.append({"trade_date": day.date().isoformat(), "model": "egarch_one_step", **error})
        if long_error:
            failures.append({"trade_date": day.date().isoformat(), "model": "egarch_horizon", **long_error})
        rolling = returns.iloc[1:position + 1].tail(ROLLING_WINDOW)
        rolling_vol = float(rolling.std(ddof=1) * np.sqrt(ANNUAL_DAYS))
        if one and long:
            one_vol = math.sqrt(one["daily_variances"][0] * ANNUAL_DAYS)
            rows.append({
                "trade_date": day.date().isoformat(),
                "one_step_volatility": one_vol,
                "horizon_max_days": horizon,
                "horizon_variance_sum_60": float(sum(long["daily_variances"])),
                "horizon_volatility_60": math.sqrt(sum(long["daily_variances"]) * ANNUAL_DAYS / horizon),
                "daily_variances_60": json.dumps(long["daily_variances"]),
                "rolling20_volatility": rolling_vol,
                "history_observations": one["history"],
                "one_step_parameters": json.dumps(one["parameters"], sort_keys=True),
                "horizon_parameters": json.dumps(long["parameters"], sort_keys=True),
                "convergence_flag": one["convergence_flag"],
            })
        for minimum in INIT_LENGTHS:
            forecast, init_error = fit_egarch_forecast(returns, position, minimum, 1)
            stability_rows.append({
                "trade_date": day.date().isoformat(),
                "minimum_history": minimum,
                "volatility": math.sqrt(forecast["daily_variances"][0] * ANNUAL_DAYS)
                if forecast else np.nan,
                "convergence_flag": forecast["convergence_flag"] if forecast else None,
                "failure": init_error["reason"] if init_error else "",
            })
    return pd.DataFrame(rows), failures, pd.DataFrame(stability_rows)


def load_eligible_options(index: pd.DataFrame, forecasts: pd.DataFrame) -> pd.DataFrame:
    options = pd.read_csv(OPTIONS_PATH, parse_dates=["trade_date", "expiry"], low_memory=False)
    for field in ("contracts", "close", "strike", "settlement"):
        options[f"{field}_num"] = pd.to_numeric(options[field], errors="coerce")
    options["dte"] = (options["expiry"] - options["trade_date"]).dt.days
    options = options[
        (options["contracts_num"] > 0)
        & (options["close_num"] > 0)
        & (options["strike_num"] > 0)
        & options["trade_date"].notna()
        & options["expiry"].notna()
        & options["dte"].between(7, 60)
        & options["option_type"].isin(["CE", "PE"])
    ].copy()
    spot = index["close"].rename("spot")
    options = options.join(spot, on="trade_date")
    forecast_dates = forecasts.copy()
    forecast_dates["trade_date"] = pd.to_datetime(forecast_dates["trade_date"])
    options = options.merge(forecast_dates, on="trade_date", how="inner")
    index_dates = index.index
    options["trading_days_to_expiry"] = options.apply(
        lambda item: int(((index_dates > item["trade_date"]) & (index_dates <= item["expiry"])).sum()),
        axis=1,
    )
    options["horizon_volatility"] = options.apply(
        lambda item: math.sqrt(
            sum(json.loads(item["daily_variances_60"])[: item["trading_days_to_expiry"]])
            * ANNUAL_DAYS / item["trading_days_to_expiry"]
        ) if item["trading_days_to_expiry"] > 0 else np.nan,
        axis=1,
    )
    options["moneyness"] = options["strike_num"] / options["spot"]
    options["year_fraction"] = options["dte"] / 365.25
    return options


def value_options(options: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for item in options.itertuples(index=False):
        option_type = "call" if item.option_type == "CE" else "put"
        for approach, volatility in (
            ("one_step_egarch", item.one_step_volatility),
            ("horizon_egarch", item.horizon_volatility),
            ("rolling20", item.rolling20_volatility),
        ):
            if not np.isfinite(volatility):
                continue
            price = black_scholes_price(
                item.spot,
                item.strike_num,
                item.year_fraction,
                RISK_FREE_RATE,
                volatility,
                option_type,
                dividend_yield=DIVIDEND_YIELD,
                use_adjusted_vol=False,
            )
            error = price - item.close_num
            rows.append({
                "trade_date": item.trade_date.date().isoformat(),
                "expiry": item.expiry.date().isoformat(),
                "strike": item.strike_num,
                "option_type": item.option_type,
                "spot": item.spot,
                "moneyness": item.moneyness,
                "dte": item.dte,
                "year_fraction": item.year_fraction,
                "observed_close": item.close_num,
                "contracts": item.contracts_num,
                "open_interest": item.open_interest,
                "approach": approach,
                "volatility": volatility,
                "model_price": price,
                "pricing_error": error,
                "absolute_error": abs(error),
                "ape": abs(error) / item.close_num,
            })
    return pd.DataFrame(rows)


def error_metrics(group: pd.DataFrame) -> dict:
    return {
        "n": int(len(group)),
        "mae": float(group["absolute_error"].mean()),
        "rmse": float(np.sqrt(np.mean(group["pricing_error"] ** 2))),
        "mape_percent": float(group["ape"].mean() * 100),
        "median_absolute_error": float(group["absolute_error"].median()),
        "median_absolute_percentage_error_percent": float(group["ape"].median() * 100),
    }


def grouped_metrics(values: pd.DataFrame) -> dict:
    result = {}
    values = values.copy()
    values["dte_bucket"] = np.where(values["dte"].between(7, 30), "7-30", "31-60")
    values["moneyness_bucket"] = np.where(
        values["moneyness"].between(0.95, 1.05),
        "ATM",
        np.where(
            ((values["option_type"] == "CE") & (values["moneyness"] > 1))
            | ((values["option_type"] == "PE") & (values["moneyness"] < 1)),
            "ITM",
            "OTM",
        ),
    )
    for key, group in values.groupby(["approach", "option_type", "moneyness_bucket", "dte_bucket"]):
        result["|".join(key)] = error_metrics(group)
    return result


def common_sample_model_metrics(forecasts: pd.DataFrame) -> dict:
    frame = forecasts.dropna(subset=[
        "one_step_volatility", "rolling20_volatility",
    ]).copy()
    frame["target"] = np.nan
    # Target is the next-day absolute log return annualized; recover it from the index in main.
    return {"dates": int(len(frame))}


def dm_test(loss_a: np.ndarray, loss_b: np.ndarray, lag: int = 5) -> dict:
    difference = np.asarray(loss_a) - np.asarray(loss_b)
    n = len(difference)
    mean = float(np.mean(difference))
    if np.allclose(difference, 0.0, rtol=0.0, atol=1e-12):
        return {
            "n": n,
            "loss": "squared error of next-day annualized absolute-return volatility target",
            "newey_west_lag": lag,
            "null": "equal expected forecast loss",
            "mean_loss_difference_a_minus_b": 0.0,
            "statistic": 0.0,
            "p_value": 1.0,
            "identical_loss_series": True,
        }
    centered = difference - mean
    gamma0 = float(np.mean(centered * centered))
    variance = gamma0
    for order in range(1, min(lag, n - 1) + 1):
        gamma = float(np.mean(centered[order:] * centered[:-order]))
        variance += 2 * (1 - order / (lag + 1)) * gamma
    variance /= n
    statistic = mean / math.sqrt(variance) if variance > 0 else None
    p_value = float(2 * stats.norm.sf(abs(statistic))) if statistic is not None else None
    return {
        "n": n,
        "loss": "squared error of next-day annualized absolute-return volatility target",
        "newey_west_lag": lag,
        "null": "equal expected forecast loss",
        "mean_loss_difference_a_minus_b": mean,
        "statistic": statistic,
        "p_value": p_value,
    }


def write_reports(
    index: pd.DataFrame,
    forecasts: pd.DataFrame,
    failures: list[dict],
    stability: pd.DataFrame,
    valuations: pd.DataFrame,
    metrics: dict,
) -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "horizon_forecast_methodology.md").write_text(
        "# Horizon Forecast Methodology\n\n"
        "Daily returns are decimal log returns. The corrected asymmetric EGARCH specification is "
        "`arch_model(returns*100, mean='Constant', vol='EGARCH', p=1, o=1, q=1, dist='normal', rescale=False)`.\n\n"
        "For each valuation date, the forecast horizon is the number of actual NIFTY 50 trading observations strictly after the valuation date and no later than the option expiry date. Calendar DTE remains the source eligibility measure; option valuation uses the trading-day count. The expiration date is included only when it is an observed trading date. Non-trading days therefore contribute no conditional variance. Daily percentage-scale conditional variances are divided by 10,000, summed, and converted to equivalent annualized volatility as `sqrt(sum(v_daily) * 252 / N_trading_days)`. No volatility floor or clipping is applied.\n\n"
        "The one-step approach uses the first daily conditional variance annualized. The horizon approach uses the full forecast vector through the maximum 60 observed trading days and the option-specific count within that vector. The rolling benchmark uses the trailing 20 daily returns annualized by `sqrt(252)`. All fits use only returns available through the valuation date.\n\n"
        f"Risk-free rate is a sensitivity assumption of {RISK_FREE_RATE:.2%}; continuous dividend yield is {DIVIDEND_YIELD:.2%}. Option CLOSE is a daily last-traded reference, not bid/ask or executable price. Package versions are recorded in `data/research/phase2/phase2_metrics.json`.\n",
        encoding="utf-8",
    )
    (DOCS / "horizon_valuation_comparison.md").write_text(
        "# Horizon Valuation Comparison\n\n"
        f"Common eligible option rows: **{metrics['sample']['common_option_rows']}**. All approaches use the same contracts, spot, DTE, rate, dividend yield, and BSM implementation.\n\n"
        "```json\n" + json.dumps(metrics["valuation_metrics"], indent=2) + "\n```\n\n"
        "MAPE and percentage errors are unstable for low observed CLOSE values; median absolute error and median absolute percentage error are reported. Results are pricing errors relative to daily CLOSE, not evidence of mispricing, arbitrage, or execution quality.\n",
        encoding="utf-8",
    )
    extreme = stability[np.isfinite(stability["volatility"])].sort_values("volatility", ascending=False).head(20)
    (DOCS / "egarch_stability_analysis.md").write_text(
        "# EGARCH Stability Analysis\n\n"
        f"- Corrected forecast rows: {len(forecasts)}\n"
        f"- Fit/forecast failures: {len(failures)}\n"
        f"- One-step volatility below 1%: {int((forecasts['one_step_volatility'] < .01).sum())}\n"
        f"- Below 5%: {int((forecasts['one_step_volatility'] < .05).sum())}\n"
        f"- Below 10%: {int((forecasts['one_step_volatility'] < .10).sum())}\n"
        f"- Maximum one-step volatility: {forecasts['one_step_volatility'].max()}\n\n"
        "Alternative minimum-history runs use 60, 90, and 120 observations. They are diagnostic sensitivity runs, not selected to improve results. No forecast is clipped or floored.\n\n"
        "## Extreme forecasts\n\n"
        + extreme.to_markdown(index=False)
        + "\n\n## Failures\n\n```json\n"
        + json.dumps(failures, indent=2)
        + "\n```\n",
        encoding="utf-8",
    )
    (DOCS / "common_sample_model_comparison.md").write_text(
        "# Common-Sample Model Comparison\n\n"
        "Target: next-day absolute log return multiplied by `sqrt(252)`; variance QLIKE uses the squared target and forecast variance. Models are evaluated on identical non-missing dates.\n\n"
        "```json\n" + json.dumps(metrics["volatility_metrics"], indent=2) + "\n```\n\n"
        "Diebold-Mariano comparisons use squared-error loss differences with a Newey-West lag of 5. They are reported only as diagnostics; the short sample and overlapping volatility construction limit inference.\n\n"
        "```json\n" + json.dumps(metrics["dm_tests"], indent=2) + "\n```\n",
        encoding="utf-8",
    )


def main() -> int:
    index = load_index()
    forecasts, failures, stability = calculate_forecasts(index)
    options = load_eligible_options(index, forecasts)
    valuations = value_options(options)
    OUT.mkdir(parents=True, exist_ok=True)
    forecasts.to_csv(OUT / "horizon_volatility_forecasts.csv", index=False)
    stability.to_csv(OUT / "egarch_stability_forecasts.csv", index=False)
    valuations.to_csv(OUT / "horizon_option_valuation_results.csv", index=False)

    phase1 = pd.read_csv(PHASE1_FORECASTS, parse_dates=["trade_date"])
    phase1["target_vol"] = pd.to_numeric(phase1["target_vol"], errors="coerce")
    phase1["target_variance"] = phase1["target_vol"] ** 2
    forecasts["trade_date"] = pd.to_datetime(forecasts["trade_date"])
    comparison = forecasts.merge(phase1[["trade_date", "target_vol", "target_variance", "garch11_vol", "egarch11_vol"]], on="trade_date", how="inner")
    model_metrics = {}
    for name in ("rolling20_volatility", "one_step_volatility", "garch11_vol", "egarch11_vol"):
        valid = comparison[["target_vol", name]].dropna()
        variance_valid = comparison[["target_variance", name]].dropna()
        model_metrics[name] = {
            "n": int(len(valid)),
            "mae": float(np.mean(np.abs(valid["target_vol"] - valid[name]))),
            "rmse": float(np.sqrt(np.mean((valid["target_vol"] - valid[name]) ** 2))),
            "variance_qlike": float(np.mean(
                np.maximum(variance_valid["target_variance"], 1e-12)
                / np.maximum(variance_valid[name] ** 2, 1e-12)
                - np.log(np.maximum(variance_valid["target_variance"], 1e-12)
                         / np.maximum(variance_valid[name] ** 2, 1e-12)) - 1
            )),
        }
    common = comparison.dropna(subset=["target_vol", "rolling20_volatility", "one_step_volatility", "garch11_vol", "egarch11_vol"])
    dm = {}
    losses = {name: (common[name] - common["target_vol"]) ** 2 for name in ("rolling20_volatility", "one_step_volatility", "garch11_vol", "egarch11_vol")}
    for a, b in (("one_step_volatility", "rolling20_volatility"), ("one_step_volatility", "garch11_vol"), ("one_step_volatility", "egarch11_vol")):
        dm[f"{a}_vs_{b}"] = dm_test(losses[a].to_numpy(), losses[b].to_numpy())
    payload = {
        "sample": {
            "index_rows": len(index), "forecast_rows": len(forecasts),
            "common_forecast_rows": len(common), "common_option_rows": len(options),
            "valuation_rows": len(valuations), "fit_failures": len(failures),
        },
        "volatility_metrics": model_metrics,
        "valuation_metrics": grouped_metrics(valuations),
        "dm_tests": dm,
        "stability": {
            "counts_below_1_percent": int((forecasts["one_step_volatility"] < .01).sum()),
            "counts_below_5_percent": int((forecasts["one_step_volatility"] < .05).sum()),
            "counts_below_10_percent": int((forecasts["one_step_volatility"] < .10).sum()),
            "min": float(forecasts["one_step_volatility"].min()),
            "median": float(forecasts["one_step_volatility"].median()),
            "max": float(forecasts["one_step_volatility"].max()),
        },
        "software": {
            "python": sys.version, "platform": platform.platform(),
            "numpy": np.__version__, "pandas": pd.__version__,
            "arch": version("arch"), "scipy": version("scipy"),
        },
        "assumptions": {
            "calendar_dte": "expiry date minus trade date in calendar days",
            "trading_horizon": "actual index observations strictly after trade date through expiry, inclusive if traded",
            "annualization_days": ANNUAL_DAYS, "risk_free_rate": RISK_FREE_RATE,
            "dividend_yield": DIVIDEND_YIELD, "no_clipping_or_floor": True,
        },
    }
    (OUT / "phase2_metrics.json").write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    write_reports(index, forecasts, failures, stability, valuations, payload)
    print(json.dumps(payload["sample"] | payload["stability"], indent=2))


if __name__ == "__main__":
    main()
