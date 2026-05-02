import os
import datetime as dt
import logging
import math
from typing import Any

import dateutil.parser
from dhanhq import dhanhq

logger = logging.getLogger(__name__)

DHAN_ACCESS_TOKEN = os.getenv("DHAN_ACCESS_TOKEN")
DHAN_CLIENT_ID = os.getenv("DHAN_CLIENT_ID")

if not DHAN_ACCESS_TOKEN or not DHAN_CLIENT_ID:
    raise Exception("Missing Dhan credentials")

dhan = dhanhq(DHAN_CLIENT_ID, DHAN_ACCESS_TOKEN)


class OptionChainFetchError(Exception):
    pass


_CHAIN_CACHE: dict[str, tuple[dict, dt.datetime]] = {}


def _pick_value(payload: dict, keys: list[str]) -> Any:
    for key in keys:
        if key in payload and payload[key] not in (None, ""):
            return payload[key]
    return None


def _parse_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
        if not math.isfinite(parsed):
            return None
        return parsed
    except (TypeError, ValueError):
        return None


def _parse_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(float(value))
        return parsed
    except (TypeError, ValueError):
        return None


def _extract_expiries(items: list[dict]) -> list[str]:
    expiries: set[str] = set()
    for item in items:
        expiry_raw = _pick_value(item, ["expiry", "expiry_date", "expiryDate"])
        if not expiry_raw:
            continue
        try:
            expiry_dt = dateutil.parser.parse(str(expiry_raw)).date()
            expiries.add(expiry_dt.isoformat())
        except (ValueError, TypeError):
            continue

    return sorted(expiries)


def _select_expiry(expiries: list[str], requested: str | None) -> str:
    if requested and requested in expiries:
        return requested
    if not expiries:
        raise OptionChainFetchError("Failed to extract any expiry dates from Dhan data")

    today = dt.date.today()
    future_expiries = [exp for exp in expiries if dateutil.parser.parse(exp).date() >= today]
    if future_expiries:
        return future_expiries[0]
    return expiries[0]


def _normalize_chain(items: list[dict]) -> list[dict]:
    chain_map: dict[int, dict] = {}
    for item in items:
        if not isinstance(item, dict):
            continue

        strike_raw = _pick_value(item, ["strike", "strike_price", "strikePrice"])
        try:
            strike = int(float(strike_raw))
        except (TypeError, ValueError):
            continue

        opt_type = _pick_value(item, ["option_type", "instrument_type", "opt_type", "type"])
        if not opt_type:
            continue
        opt_type = str(opt_type).upper()
        if opt_type in ("CE", "CALL", "C"):
            leg = "call"
        elif opt_type in ("PE", "PUT", "P"):
            leg = "put"
        else:
            continue

        ltp = _parse_float(_pick_value(item, ["ltp", "last_price", "last_traded_price", "ltp_price"]))
        oi = _parse_int(_pick_value(item, ["oi", "open_interest", "openInterest"]))
        volume = _parse_int(_pick_value(item, ["volume", "vol", "trade_volume"]))
        iv = _parse_float(_pick_value(item, ["iv", "implied_volatility", "impliedVolatility"]))

        if ltp is None or oi is None or volume is None or iv is None:
            continue

        entry = chain_map.setdefault(strike, {"strike": strike})
        entry[leg] = {
            "ltp": ltp,
            "oi": oi,
            "volume": volume,
            "iv": iv
        }

    chain_list: list[dict] = []
    for strike, entry in chain_map.items():
        if "call" not in entry or "put" not in entry:
            continue
        chain_list.append(entry)

    chain_list.sort(key=lambda x: x["strike"])
    if not chain_list:
        raise OptionChainFetchError("No valid option chain data found after normalization")

    return chain_list


def _fetch_option_chain_payload(symbol: str) -> dict:
    try:
        resp = dhan.option_chain(underlying_symbol=symbol)
    except Exception as exc:
        raise Exception(f"Dhan API failed to fetch data: {exc}")

    if not resp or "data" not in resp:
        raise Exception("Dhan API failed to fetch data")

    return resp


def get_nifty_spot() -> float:
    try:
        resp = dhan.ticker_data(
            security_id="13",
            exchange_segment="IDX_I",
            instrument="INDEX"
        )
    except Exception as exc:
        raise Exception(f"Dhan API failed to fetch data: {exc}")

    spot = _parse_float(resp.get("last_price") if isinstance(resp, dict) else None)
    if spot is None:
        raise Exception("Dhan API failed to fetch data")
    return spot


def get_full_chain(symbol: str = "NIFTY", expiry_date: str | None = None, depth: int = 20) -> dict:
    cache_key = f"{symbol}_{expiry_date}_{depth}"
    now = dt.datetime.now()
    cached = _CHAIN_CACHE.get(cache_key)
    if cached is not None:
        cached_data, cached_time = cached
        if (now - cached_time).total_seconds() < 15:
            return cached_data

    payload = _fetch_option_chain_payload(symbol)
    items = payload.get("data")
    if not isinstance(items, list):
        raise Exception("Dhan API failed to fetch data")

    expiries = _extract_expiries(items)
    selected_expiry = _select_expiry(expiries, expiry_date)

    filtered_items = [
        item for item in items
        if str(_pick_value(item, ["expiry", "expiry_date", "expiryDate"]) or "").startswith(selected_expiry)
    ]
    if filtered_items:
        items = filtered_items

    chain_list = _normalize_chain(items)

    spot = get_nifty_spot()
    strikes = [entry["strike"] for entry in chain_list]
    atm_strike = min(strikes, key=lambda k: abs(k - spot))

    if depth and depth > 0:
        half_depth = depth // 2
        atm_idx = strikes.index(atm_strike)
        start_idx = max(0, atm_idx - half_depth)
        end_idx = min(len(strikes), atm_idx + half_depth + 1)
        allowed = set(strikes[start_idx:end_idx])
        chain_list = [entry for entry in chain_list if entry["strike"] in allowed]

    total_call_oi = sum(entry["call"]["oi"] for entry in chain_list)
    total_put_oi = sum(entry["put"]["oi"] for entry in chain_list)
    if total_call_oi <= 0 or total_put_oi <= 0:
        raise Exception("Dhan API failed to fetch data")

    pcr = round(total_put_oi / total_call_oi, 2)

    result = {
        "spot_price": spot,
        "atm_strike": atm_strike,
        "expiry_date": selected_expiry,
        "available_expiries": expiries,
        "pcr": pcr,
        "chain": chain_list,
        "timestamp": dt.datetime.now().isoformat()
    }

    _CHAIN_CACHE[cache_key] = (result, now)
    return result


def get_spot_price(symbol: str = "NIFTY") -> float:
    if symbol.upper() != "NIFTY":
        raise ValueError("Only NIFTY spot is supported for Dhan spot quote")
    return get_nifty_spot()


def fetch_option_chain(symbol: str, expiry: str | None = None, expiry_type: str = "nearest") -> dict:
    data = get_full_chain(symbol, expiry)
    return {
        "expiry": data["expiry_date"],
        "selected_expiry": data["expiry_date"],
        "available_expiries": data["available_expiries"],
        "chain": data["chain"]
    }


def get_available_expiries(symbol: str = "NIFTY") -> list[str]:
    payload = _fetch_option_chain_payload(symbol)
    items = payload.get("data")
    if not isinstance(items, list):
        raise Exception("Dhan API failed to fetch data")
    expiries = _extract_expiries(items)
    if not expiries:
        raise Exception("Dhan API failed to fetch data")
    return expiries


def get_atm_option(chain_dict: dict, spot_price: float, option_type: str = "call") -> dict:
    chain_list = chain_dict.get("chain", [])
    if not chain_list:
        raise ValueError("Option chain is empty")

    closest = min(chain_list, key=lambda x: abs(x["strike"] - spot_price))
    if option_type == "call":
        data = closest.get("call")
    else:
        data = closest.get("put")

    if not data:
        raise ValueError("ATM option data missing")

    return {
        "strike": closest["strike"],
        "price": data["ltp"],
        "ltp": data["ltp"],
        "iv": data["iv"]
    }


