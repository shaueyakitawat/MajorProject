# Regime Service
# Handles volatility regime classification via HMM

import os
import math
from typing import Any

import numpy as np
from hmmlearn.hmm import GaussianHMM

DEFAULT_STATE_COUNT = int(os.getenv("REGIME_STATE_COUNT", "4"))
MIN_TRAIN_SAMPLES = int(os.getenv("REGIME_MIN_SAMPLES", "120"))

_HMM_MODEL: GaussianHMM | None = None
_HMM_STATE_ORDER: list[int] | None = None
_HMM_STATE_COUNT: int | None = None


def _prepare_series(vol_series: Any) -> np.ndarray | None:
    if vol_series is None:
        return None

    values = np.array(vol_series, dtype=float)
    values = values[np.isfinite(values)]
    if values.size < MIN_TRAIN_SAMPLES:
        return None

    return values.reshape(-1, 1)


def _fit_hmm(vol_series: np.ndarray, state_count: int) -> tuple[GaussianHMM, list[int]]:
    model = GaussianHMM(n_components=state_count, covariance_type="diag", n_iter=500, random_state=42)
    model.fit(vol_series)

    means = model.means_.flatten()
    state_order = list(np.argsort(means))

    return model, state_order


def _map_state_to_label(state_rank: int, state_count: int) -> str:
    if state_count <= 3:
        mapping = {0: "LOW_VOL", 1: "NORMAL_VOL", 2: "HIGH_VOL"}
        return mapping.get(state_rank, "HIGH_VOL")

    mapping = {0: "LOW_VOL", 1: "NORMAL_VOL", 2: "HIGH_VOL", 3: "EXTREME_VOL"}
    return mapping.get(state_rank, "EXTREME_VOL")


def classify_volatility_regime(volatility_value: float, vol_series: Any | None = None, state_count: int | None = None) -> dict:
    """
    Classify market volatility regime using a Hidden Markov Model.

    Args:
        volatility_value: Current annualized volatility (decimal)
        vol_series: Historical volatility series for HMM training
        state_count: Optional number of hidden states (3 or 4)

    Returns:
        dict: {"regime": int, "regime_label": str, "confidence": float}
    """
    global _HMM_MODEL, _HMM_STATE_ORDER, _HMM_STATE_COUNT

    target_states = int(state_count or DEFAULT_STATE_COUNT)
    target_states = 3 if target_states <= 3 else 4

    series = _prepare_series(vol_series)
    if series is not None and (_HMM_MODEL is None or _HMM_STATE_COUNT != target_states):
        _HMM_MODEL, _HMM_STATE_ORDER = _fit_hmm(series, target_states)
        _HMM_STATE_COUNT = target_states

    if _HMM_MODEL is None or _HMM_STATE_ORDER is None or not math.isfinite(volatility_value):
        return {
            "regime": 0,
            "regime_label": "NORMAL_VOL",
            "confidence": 0.0,
        }

    obs = np.array([[float(volatility_value)]])
    state_probs = _HMM_MODEL.predict_proba(obs)[0]
    state_id = int(np.argmax(state_probs))
    confidence = float(state_probs[state_id])

    state_rank = _HMM_STATE_ORDER.index(state_id) if state_id in _HMM_STATE_ORDER else 1
    regime_label = _map_state_to_label(state_rank, _HMM_STATE_COUNT or target_states)

    return {
        "regime": state_id,
        "regime_label": regime_label,
        "confidence": confidence,
    }
