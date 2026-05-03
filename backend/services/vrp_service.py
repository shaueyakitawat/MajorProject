import os
import math
from collections import deque
from typing import Deque
import numpy as np

ROLLING_WINDOW = int(os.getenv("VRP_ROLLING_WINDOW", "60"))

_vrp_window: Deque[float] = deque(maxlen=ROLLING_WINDOW)


def compute_vrp(iv: float | None, final_vol: float) -> dict:
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
    _vrp_window.append(vrp)

    if len(_vrp_window) == 0:
        return {
            "vrp": vrp,
            "expected_vrp": None,
            "vrp_std": None,
        }

    values = np.array(list(_vrp_window), dtype=float)
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
