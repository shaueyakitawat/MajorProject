import os
import math
from collections import deque
from typing import Deque, Dict
import numpy as np

ROLLING_WINDOW = int(os.getenv("VRP_ROLLING_WINDOW", "60"))

# Store VRP history by regime for regime-conditioned expected VRP
_vrp_by_regime: Dict[str, Deque[float]] = {
    "LOW_VOL": deque(maxlen=ROLLING_WINDOW),
    "NORMAL_VOL": deque(maxlen=ROLLING_WINDOW),
    "HIGH_VOL": deque(maxlen=ROLLING_WINDOW),
    "EXTREME_VOL": deque(maxlen=ROLLING_WINDOW),
}

# Also keep the overall window for fallback
_vrp_window: Deque[float] = deque(maxlen=ROLLING_WINDOW)


def compute_vrp(iv: float | None, final_vol: float, regime_label: str = "NORMAL_VOL") -> dict:
    if iv is None or final_vol is None:
        return {
            "vrp": None,
            "expected_vrp": None,
            "vrp_std": None,
        }

    if not math.isfinite(iv) or not math.isfinite(final_vol):
        return {
            "vrp": None,
            "expected_vrp": None,
            "vrp_std": None,
        }

    vrp = float(iv - final_vol)
    
    # Update global window
    _vrp_window.append(vrp)
    
    # Update regime-specific window
    if regime_label in _vrp_by_regime:
        _vrp_by_regime[regime_label].append(vrp)
        active_window = _vrp_by_regime[regime_label]
    else:
        active_window = _vrp_window

    if len(active_window) == 0:
        return {
            "vrp": vrp,
            "expected_vrp": None,
            "vrp_std": None,
        }

    values = np.array(list(active_window), dtype=float)
    if not np.all(np.isfinite(values)):
        return {
            "vrp": vrp,
            "expected_vrp": None,
            "vrp_std": None,
        }

    expected_vrp = float(np.mean(values))
    vrp_std = float(np.std(values))

    return {
        "vrp": vrp,
        "expected_vrp": expected_vrp,
        "vrp_std": vrp_std,
    }

