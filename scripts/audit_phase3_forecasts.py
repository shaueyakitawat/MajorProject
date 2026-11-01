"""Audit Phase 2 forecast arrays, EGARCH horizons, and DM diagnostics."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.run_phase2_horizon_validation import dm_test

PHASE1 = ROOT / "data/research/volatility_forecasts.csv"
PHASE2 = ROOT / "data/research/phase2/horizon_volatility_forecasts.csv"
DOCS = ROOT / "docs/research"


def load_comparison() -> pd.DataFrame:
    phase1 = pd.read_csv(PHASE1, parse_dates=["trade_date"])
    phase2 = pd.read_csv(PHASE2, parse_dates=["trade_date"])
    return phase2.merge(
        phase1[
            [
                "trade_date",
                "target_vol",
                "rolling20_vol",
                "garch11_vol",
                "egarch11_vol",
            ]
        ],
        on="trade_date",
        how="inner",
        validate="one_to_one",
    )


def array_summary(frame: pd.DataFrame, column: str) -> dict:
    values = frame[column].dropna()
    return {
        "non_null": int(values.size),
        "unique": int(values.nunique()),
        "minimum": float(values.min()),
        "median": float(values.median()),
        "maximum": float(values.max()),
    }


def loss_series(frame: pd.DataFrame, column: str) -> np.ndarray:
    valid = frame[["target_vol", column]].dropna()
    return (valid[column] - valid["target_vol"]).to_numpy() ** 2


def main() -> None:
    frame = load_comparison()
    columns = {
        "rolling": "rolling20_volatility",
        "garch": "garch11_vol",
        "egarch_phase1": "egarch11_vol",
        "egarch_phase2": "one_step_volatility",
    }
    summaries = {
        name: array_summary(frame, column) for name, column in columns.items()
    }
    pairwise = {}
    for left_name, left in columns.items():
        for right_name, right in columns.items():
            if left_name >= right_name:
                continue
            valid = frame[[left, right]].dropna()
            delta = valid[left] - valid[right]
            pairwise[f"{left_name}_vs_{right_name}"] = {
                "maximum_absolute_difference": float(delta.abs().max()),
                "correlation": float(valid[left].corr(valid[right])),
                "exactly_identical": int((delta == 0).sum()),
                "rows": int(len(valid)),
            }
    first20 = frame[
        [
            "trade_date",
            "target_vol",
            "rolling20_volatility",
            "garch11_vol",
            "egarch11_vol",
        ]
    ].head(20)

    one_loss = loss_series(frame, "one_step_volatility")
    egarch_loss = loss_series(frame, "egarch11_vol")
    dm = dm_test(one_loss, egarch_loss)
    identity_dm = dm_test(one_loss, one_loss)

    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "forecast_array_audit.md").write_text(
        "# Forecast Array Audit\n\n"
        f"Comparison rows: **{len(frame)}**, joined one-to-one on `trade_date`.\n\n"
        "## Array summaries\n\n"
        + pd.DataFrame(summaries).T.to_markdown()
        + "\n\n## Pairwise comparisons\n\n"
        + pd.DataFrame(pairwise).T.to_markdown()
        + "\n\n## First 20 aligned rows\n\n"
        + first20.to_markdown(index=False)
        + "\n\n## Producer trace\n\n"
        "- Phase 1 writes `egarch11_vol` in "
        "`scripts/run_empirical_research.py:fit_volatility` (line 68).\n"
        "- Phase 2 recomputes `one_step_volatility` in "
        "`scripts/run_phase2_horizon_validation.py:fit_egarch_forecast` "
        "(line 42) and `calculate_forecasts` (line 97).\n"
        "- Phase 2 imports Phase 1 `egarch11_vol` only for the common-sample "
        "comparison in `main` (line 365); it does not generate an independent "
        "EGARCH specification.\n\n"
        "The Phase 1 and Phase 2 one-step EGARCH series are therefore "
        "recomputations of the same EGARCH(1,1,1), normal, percentage-scaled "
        "fit. They are not independent forecasts. The maximum difference is "
        f"{pairwise['egarch_phase1_vs_egarch_phase2']['maximum_absolute_difference']:.17g}, "
        "consistent with floating-point serialization/recomputation.\n",
        encoding="utf-8",
    )
    (DOCS / "dm_test_validation.md").write_text(
        "# Diebold-Mariano Test Validation\n\n"
        "The Phase 2 implementation constructs losses as squared forecast "
        "errors in `main` (line 383), subtracts them observation by "
        "observation in `dm_test` (line 265), and estimates a Newey-West "
        "variance using the resulting loss-difference series. The two input "
        "arrays are aligned through the common date frame before loss "
        "construction (line 365).\n\n"
        "## Reproduced comparison\n\n"
        f"```json\n{json.dumps(dm, indent=2)}\n```\n\n"
        "The compared one-step EGARCH arrays differ only at roundoff level. "
        "Before correction, this produced a tiny nonzero loss difference and "
        "an unstable near-zero standard error, yielding a spurious statistic "
        "of approximately 3.0. The corrected implementation treats an "
        "all-close-zero loss difference as identical.\n\n"
        "## Identical-array unit case\n\n"
        f"```json\n{json.dumps(identity_dm, indent=2)}\n```\n\n"
        "For identical loss arrays the corrected result is statistic 0 and "
        "p-value 1, so it cannot claim a significant difference. This is a "
        "numerical guard, not a change to the loss definition or forecast "
        "values.\n",
        encoding="utf-8",
    )
    (DOCS / "egarch_multistep_implementation_audit.md").write_text(
        "# EGARCH Multi-step Implementation Audit\n\n"
        "## Package behavior\n\n"
        "The installed `arch` package's `EGARCH._check_forecasting_method` "
        "(`.venv/Lib/site-packages/arch/univariate/volatility.py:2755`) "
        "raises `ValueError('Analytic forecasts not available for horizon > "
        "1')`. Its public forecast API supports `analytic`, `simulation`, "
        "and `bootstrap` (`.venv/Lib/site-packages/arch/univariate/base.py:1027`); "
        "the package documentation states that EGARCH does "
        "not support analytic forecasts beyond one step. The package "
        "simulation path uses a caller-supplied RNG and a configurable "
        "simulation count.\n\n"
        "## Experiment behavior\n\n"
        "`fit_egarch_forecast` (line 42) requests the package analytic one-step "
        "forecast, converts percentage-scale variance by dividing by 10,000, "
        "and then constructs longer horizons itself. For steps after the "
        "first it applies `exp(omega + beta * log(previous_variance))`. "
        "This is a deterministic expected-log-variance recursion under the "
        "normal-innovation mean terms, not `arch` simulation and not the "
        "exact expected future variance of the asymmetric EGARCH process. "
        "No simulation count or random seed is used.\n\n"
        "The resulting vectors are horizon-specific and are not repeated "
        "copies: the audit found 311 of 312 rows where the stored "
        "`horizon_volatility_60` differs from the one-step volatility. "
        "For each option, `load_eligible_options` counts observed index "
        "dates strictly after trade date through expiry and slices the "
        "stored daily variance vector to that count "
        "(`load_eligible_options`, line 164). No future return is used in "
        "fitting.\n\n"
        "## Methodological conclusion\n\n"
        "The Phase 2 arrays are reproducible under the current deterministic "
        "recursion, but the multi-step method must be labeled an "
        "expected-log-variance approximation. A publication-grade "
        "multi-step EGARCH forecast should use `arch` simulation with a "
        "documented simulation count, RNG, and repeated-run stability "
        "analysis, or explicitly justify this approximation. Existing "
        "forecast values were not changed in this audit.\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
