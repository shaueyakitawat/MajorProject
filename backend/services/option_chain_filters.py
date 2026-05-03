import math
import os

MIN_OPEN_INTEREST = int(os.getenv("OPTION_CHAIN_MIN_OI", "1000"))
MIN_VOLUME = int(os.getenv("OPTION_CHAIN_MIN_VOLUME", "500"))
MAX_BID_ASK_SPREAD_PCT = float(os.getenv("OPTION_CHAIN_MAX_SPREAD_PCT", "0.01"))


def _safe_float(value) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
        if not math.isfinite(parsed):
            return None
        return parsed
    except (TypeError, ValueError):
        return None


def _safe_int(value) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def is_leg_liquid(leg: dict) -> bool:
    if not leg:
        return False

    ltp = _safe_float(leg.get("ltp"))
    oi = _safe_int(leg.get("oi"))
    volume = _safe_int(leg.get("volume"))
    bid = _safe_float(leg.get("bid"))
    ask = _safe_float(leg.get("ask"))

    if ltp is None or ltp <= 0:
        return False
    if oi is None or oi < MIN_OPEN_INTEREST:
        return False
    if volume is None or volume < MIN_VOLUME:
        return False
    if bid is None or ask is None:
        return False

    spread = max(ask - bid, 0.0)
    spread_pct = spread / ltp
    if spread_pct > MAX_BID_ASK_SPREAD_PCT:
        return False

    return True
