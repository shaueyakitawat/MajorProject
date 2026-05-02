"""
Upstox-based option chain data service.
Fetches NIFTY 50 option chain data via Upstox API.
"""

import os
import datetime as dt
import logging
import math
import json
from typing import Any

import dateutil.parser
import requests

logger = logging.getLogger(__name__)

UPSTOX_ACCESS_TOKEN = os.getenv("UPSTOX_ACCESS_TOKEN")
UPSTOX_API_KEY = os.getenv("UPSTOX_API_KEY")

# Upstox API base URL
UPSTOX_API_BASE = "https://api.upstox.com/v2"

if not UPSTOX_ACCESS_TOKEN:
    logger.warning("UPSTOX_ACCESS_TOKEN not set. Option chain features may not work.")


class OptionChainFetchError(Exception):
    pass


_CHAIN_CACHE: dict[str, tuple[dict, dt.datetime]] = {}


def _make_upstox_request(endpoint: str, params: dict | None = None) -> dict:
    """Make an authenticated request to Upstox API."""
    if not UPSTOX_ACCESS_TOKEN:
        raise OptionChainFetchError("UPSTOX_ACCESS_TOKEN is not configured")

    url = f"{UPSTOX_API_BASE}{endpoint}"
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {UPSTOX_ACCESS_TOKEN}",
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=20)
        response.raise_for_status()
        data = response.json()
        return data
    except requests.exceptions.RequestException as exc:
        raise OptionChainFetchError(f"Upstox API request failed: {exc}") from exc


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


def _get_nifty_spot_price() -> float:
    """Fetch current NIFTY 50 spot price from Upstox."""
    try:
        # NIFTY 50 instrument key in Upstox
        data = _make_upstox_request("/market-quote/quotes/", params={
            "mode": "LTP",
            "instrumentKeys": "NIFTY_INDEX"
        })
        
        if data.get("status") == "success" and "data" in data:
            quotes = data["data"].get("instrumentQuotes", {})
            if quotes:
                # Get the first (and typically only) quote
                quote_data = list(quotes.values())[0] if isinstance(quotes, dict) else None
                if quote_data and "ltp" in quote_data:
                    spot = _parse_float(quote_data["ltp"])
                    if spot is not None:
                        return spot
        
        raise OptionChainFetchError("Could not fetch NIFTY spot price from Upstox")
    except Exception as exc:
        raise OptionChainFetchError(f"Failed to get NIFTY spot price: {exc}") from exc


def _get_option_instruments(symbol: str = "NIFTY") -> list[dict]:
    """
    Fetch available option instruments for the given symbol.
    Returns list of option instrument details.
    """
    try:
        # Search for options on the symbol
        data = _make_upstox_request("/search/", params={
            "q": f"{symbol} options",
            "instrumentType": "optionchain"
        })
        
        if data.get("status") == "success" and "data" in data:
            return data["data"]
        
        return []
    except Exception as exc:
        logger.warning(f"Could not fetch option instruments: {exc}")
        return []


def _fetch_nifty_option_quotes(expiry_date: str | None = None) -> list[dict]:
    """
    Fetch NIFTY option quotes from Upstox.
    Groups all available NIFTY options and their quotes.
    """
    try:
        # Try to get all NIFTY option quotes
        # Upstox groups options by underlying
        data = _make_upstox_request("/market-quote/quotes/", params={
            "mode": "FULL",
            "instrumentKeys": "NIFTY_OPTIONS"
        })
        
        if data.get("status") == "success" and "data" in data:
            quotes = data["data"].get("instrumentQuotes", {})
            options = []
            
            for instrument_key, quote in quotes.items():
                if not isinstance(quote, dict):
                    continue
                
                # Parse the instrument key to get strike, expiry, type
                # Typical format: NIFTY25000PE20250529 or similar
                try:
                    # Extract info from quote metadata if available
                    if "instrumentToken" in quote and "metadata" in quote:
                        metadata = quote["metadata"]
                        options.append({
                            "instrument_key": instrument_key,
                            "strike": metadata.get("strikePrice"),
                            "expiry": metadata.get("expiryDate"),
                            "option_type": metadata.get("optionType"),
                            "ltp": quote.get("ltp"),
                            "oi": quote.get("oi"),
                            "volume": quote.get("volume"),
                            "bid": quote.get("bid"),
                            "ask": quote.get("ask"),
                            "bid_qty": quote.get("bidQty"),
                            "ask_qty": quote.get("askQty"),
                        })
                except Exception as e:
                    logger.debug(f"Could not parse option quote {instrument_key}: {e}")
                    continue
            
            return options
        
        return []
    except Exception as exc:
        raise OptionChainFetchError(f"Failed to fetch NIFTY options: {exc}") from exc


def _extract_expiries(options: list[dict]) -> list[str]:
    """Extract unique expiry dates from option list."""
    expiries: set[str] = set()
    for option in options:
        expiry_raw = option.get("expiry")
        if not expiry_raw:
            continue
        try:
            expiry_dt = dateutil.parser.parse(str(expiry_raw)).date()
            expiries.add(expiry_dt.isoformat())
        except (ValueError, TypeError):
            continue
    
    return sorted(expiries)


def _select_expiry(expiries: list[str], requested: str | None) -> str:
    """Select appropriate expiry date."""
    if requested and requested in expiries:
        return requested
    if not expiries:
        raise OptionChainFetchError("No expiry dates found")
    
    today = dt.date.today()
    future_expiries = [exp for exp in expiries if dateutil.parser.parse(exp).date() >= today]
    if future_expiries:
        return future_expiries[0]
    return expiries[-1]


def _normalize_option_chain(options: list[dict], selected_expiry: str) -> list[dict]:
    """
    Normalize option data into chain format.
    Groups by strike and combines call/put data.
    """
    chain_map: dict[float, dict] = {}
    
    for option in options:
        # Filter by expiry
        expiry_raw = option.get("expiry")
        if not expiry_raw:
            continue
        
        try:
            option_expiry = dateutil.parser.parse(str(expiry_raw)).date().isoformat()
        except (ValueError, TypeError):
            continue
        
        if option_expiry != selected_expiry:
            continue
        
        # Parse strike and option type
        strike = _parse_float(option.get("strike"))
        opt_type = str(option.get("option_type", "")).upper()
        
        if strike is None:
            continue
        
        strike = int(strike)
        
        if opt_type == "CE":
            leg = "call"
        elif opt_type == "PE":
            leg = "put"
        else:
            continue
        
        # Parse prices and metrics
        ltp = _parse_float(option.get("ltp"))
        oi = _parse_int(option.get("oi"))
        volume = _parse_int(option.get("volume"))
        
        # Calculate IV if not provided (can use Black-Scholes inverse)
        iv = _parse_float(option.get("iv"))
        
        if ltp is None or oi is None:
            continue
        
        # Handle missing volume/iv
        if volume is None:
            volume = 0
        if iv is None:
            iv = 0.25  # Default IV estimate
        
        # Build chain entry
        entry = chain_map.setdefault(strike, {"strike": strike})
        entry[leg] = {
            "ltp": ltp,
            "oi": oi,
            "volume": volume,
            "iv": iv,
            "bid": option.get("bid"),
            "ask": option.get("ask"),
        }
    
    # Filter: keep only strikes with both call and put
    chain_list: list[dict] = []
    for strike, entry in chain_map.items():
        if "call" in entry and "put" in entry:
            chain_list.append(entry)
    
    chain_list.sort(key=lambda x: x["strike"])
    
    if not chain_list:
        raise OptionChainFetchError("No valid option chain data after normalization")
    
    return chain_list


def get_spot_price(symbol: str = "NIFTY") -> float:
    """Get current spot price of the underlying."""
    if symbol.upper() != "NIFTY":
        raise ValueError("Only NIFTY spot is supported")
    return _get_nifty_spot_price()


def get_full_chain(symbol: str = "NIFTY", expiry_date: str | None = None, depth: int = 20) -> dict:
    """
    Fetch complete NIFTY option chain.
    
    Returns:
        dict with keys:
        - spot_price: Current spot price
        - atm_strike: At-the-money strike
        - expiry_date: Selected expiry date
        - available_expiries: List of available expiries
        - pcr: Put-call ratio
        - chain: List of option chain entries (normalized)
        - timestamp: Fetch timestamp
    """
    cache_key = f"{symbol}_{expiry_date}_{depth}"
    now = dt.datetime.now()
    cached = _CHAIN_CACHE.get(cache_key)
    
    if cached is not None:
        cached_data, cached_time = cached
        if (now - cached_time).total_seconds() < 15:
            logger.info(f"Returning cached chain data (age: {(now - cached_time).total_seconds():.1f}s)")
            return cached_data
    
    logger.info(f"Fetching fresh NIFTY option chain from Upstox (expiry={expiry_date})")
    
    # Get spot price
    spot = _get_nifty_spot_price()
    logger.info(f"NIFTY spot price: {spot}")
    
    # Fetch option quotes
    options = _fetch_nifty_option_quotes(expiry_date)
    if not options:
        raise OptionChainFetchError("No option data fetched from Upstox")
    
    # Extract and select expiry
    expiries = _extract_expiries(options)
    if not expiries:
        raise OptionChainFetchError("Could not extract expiry dates")
    
    selected_expiry = _select_expiry(expiries, expiry_date)
    logger.info(f"Using expiry: {selected_expiry} (available: {expiries})")
    
    # Normalize chain
    chain_list = _normalize_option_chain(options, selected_expiry)
    logger.info(f"Normalized {len(chain_list)} strikes")
    
    # Get ATM strike
    strikes = [entry["strike"] for entry in chain_list]
    atm_strike = min(strikes, key=lambda k: abs(k - spot))
    
    # Apply depth filter
    if depth and depth > 0:
        half_depth = depth // 2
        try:
            atm_idx = strikes.index(atm_strike)
            start_idx = max(0, atm_idx - half_depth)
            end_idx = min(len(strikes), atm_idx + half_depth + 1)
            allowed = set(strikes[start_idx:end_idx])
            chain_list = [entry for entry in chain_list if entry["strike"] in allowed]
            logger.info(f"Applied depth filter: {len(chain_list)} strikes within {depth} of ATM")
        except (ValueError, IndexError):
            pass
    
    # Calculate PCR
    total_call_oi = sum(entry.get("call", {}).get("oi", 0) for entry in chain_list)
    total_put_oi = sum(entry.get("put", {}).get("oi", 0) for entry in chain_list)
    
    if total_call_oi > 0:
        pcr = round(total_put_oi / total_call_oi, 2)
    else:
        pcr = 0
    
    logger.info(f"PCR: {pcr} (Call OI: {total_call_oi}, Put OI: {total_put_oi})")
    
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


def fetch_option_chain(symbol: str, expiry: str | None = None, expiry_type: str = "nearest") -> dict:
    """Fetch option chain in legacy format."""
    data = get_full_chain(symbol, expiry)
    return {
        "expiry": data["expiry_date"],
        "selected_expiry": data["expiry_date"],
        "available_expiries": data["available_expiries"],
        "chain": data["chain"]
    }


def get_available_expiries(symbol: str = "NIFTY") -> list[str]:
    """Get list of available option expiries."""
    options = _fetch_nifty_option_quotes()
    expiries = _extract_expiries(options)
    if not expiries:
        raise OptionChainFetchError("Could not fetch expiries")
    return expiries


def get_atm_option(symbol: str = "NIFTY", expiry: str | None = None, option_type: str = "CE") -> dict:
    """Get ATM option for the given symbol and expiry."""
    data = get_full_chain(symbol, expiry)
    atm_strike = data["atm_strike"]
    
    # Find ATM strike in chain
    for entry in data["chain"]:
        if entry["strike"] == atm_strike:
            if option_type.upper() == "CE":
                return {**entry["call"], "strike": atm_strike, "expiry": data["expiry_date"]}
            else:
                return {**entry["put"], "strike": atm_strike, "expiry": data["expiry_date"]}
    
    raise OptionChainFetchError(f"ATM {option_type} not found")
