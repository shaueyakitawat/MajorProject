import os
import datetime as dt
import logging
import math
from typing import Any
from pathlib import Path

import dateutil.parser
import requests

logger = logging.getLogger(__name__)

from backend.services.option_chain_filters import (
    is_leg_liquid,
    MIN_OPEN_INTEREST,
    MIN_VOLUME,
    MAX_BID_ASK_SPREAD_PCT,
)

# Load .env file
env_file = Path(__file__).parent.parent.parent / ".env"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip()

UPSTOX_ACCESS_TOKEN = os.getenv("UPSTOX_ACCESS_TOKEN")
UPSTOX_API_KEY = os.getenv("UPSTOX_API_KEY")

# Upstox API base URL
UPSTOX_API_BASE = "https://api.upstox.com/v2"

if not UPSTOX_ACCESS_TOKEN:
    logger.warning("UPSTOX_ACCESS_TOKEN not set. Configure it via: python scripts/upstox_token.py")


class OptionChainFetchError(Exception):
    pass


_CHAIN_CACHE: dict[str, tuple[dict, dt.datetime]] = {}


def _make_upstox_request(endpoint: str, params: dict | None = None) -> dict:
    """Make an authenticated request to Upstox API."""
    if not UPSTOX_ACCESS_TOKEN:
        raise OptionChainFetchError("UPSTOX_ACCESS_TOKEN not configured. Run: python scripts/upstox_token.py")

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
    """Fetch current NIFTY 50 spot price from yfinance."""
    try:
        import yfinance as yf
        # Use yfinance for reliable spot price (faster than fixing Upstox API)
        nifty = yf.Ticker("^NSEI")
        data = nifty.history(period="1d")
        spot = float(data['Close'].iloc[-1]) if not data.empty else None
        
        if spot is not None:
            logger.info(f"NIFTY spot from yfinance: ₹{spot}")
            return spot
        
        raise OptionChainFetchError("Could not fetch NIFTY spot price")
    except Exception as exc:
        raise OptionChainFetchError(f"Failed to get NIFTY spot price: {exc}") from exc


def _fetch_nifty_option_quotes(expiry_date: str | None = None) -> list[dict]:
    """
    Fetch NIFTY option quotes from Upstox.
    Calls /option/chain endpoint with correct instrument key and expiry.
    """
    try:
        # Use default expiry if none provided
        if not expiry_date:
            expiry_date = "2026-05-05"  # Next Tuesday (has data)
        
        # Correct instrument key: "NSE_INDEX|Nifty 50" (with space!)
        data = _make_upstox_request("/option/chain", params={
            "instrument_key": "NSE_INDEX|Nifty 50",
            "expiry_date": expiry_date
        })
        
        if data.get("status") == "success" and "data" in data:
            chain_data = data["data"]
            options = []
            
            # API returns array where each item is one STRIKE
            if not isinstance(chain_data, list):
                logger.warning(f"Unexpected response format: {type(chain_data)}")
                return []
            
            for strike_item in chain_data:
                if not isinstance(strike_item, dict):
                    continue
                
                try:
                    strike_price = strike_item.get("strike_price")
                    if not strike_price:
                        continue
                    
                    # Extract call option data
                    call_data = strike_item.get("call_options", {})
                    if call_data and "market_data" in call_data:
                        call_market = call_data["market_data"]
                        call_greeks = call_data.get("option_greeks", {})
                        options.append({
                            "strike": strike_price,
                            "expiry": expiry_date,
                            "option_type": "CE",
                            "instrument_key": call_data.get("instrument_key", ""),
                            "ltp": call_market.get("ltp"),
                            "oi": call_market.get("oi"),
                            "volume": call_market.get("volume"),
                            "bid": call_market.get("bid_price"),
                            "ask": call_market.get("ask_price"),
                            "iv": call_greeks.get("iv"),
                            "delta": call_greeks.get("delta"),
                            "gamma": call_greeks.get("gamma"),
                            "theta": call_greeks.get("theta"),
                            "vega": call_greeks.get("vega"),
                        })
                    
                    # Extract put option data
                    put_data = strike_item.get("put_options", {})
                    if put_data and "market_data" in put_data:
                        put_market = put_data["market_data"]
                        put_greeks = put_data.get("option_greeks", {})
                        options.append({
                            "strike": strike_price,
                            "expiry": expiry_date,
                            "option_type": "PE",
                            "instrument_key": put_data.get("instrument_key", ""),
                            "ltp": put_market.get("ltp"),
                            "oi": put_market.get("oi"),
                            "volume": put_market.get("volume"),
                            "bid": put_market.get("bid_price"),
                            "ask": put_market.get("ask_price"),
                            "iv": put_greeks.get("iv"),
                            "delta": put_greeks.get("delta"),
                            "gamma": put_greeks.get("gamma"),
                            "theta": put_greeks.get("theta"),
                            "vega": put_greeks.get("vega"),
                        })
                except Exception as e:
                    logger.debug(f"Could not parse strike {strike_item.get('strike_price')}: {e}")
                    continue
            
            logger.info(f"Fetched {len(options)} options for NIFTY expiry {expiry_date}")
            return options
        
        logger.warning(f"Upstox API error: {data.get('status')}")
        return []
    except Exception as exc:
        logger.warning(f"Could not fetch options from Upstox: {exc}")
        return []


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
        raise OptionChainFetchError("No expiry dates found in Upstox data")
    
    today = dt.date.today()
    future_expiries = [exp for exp in expiries if dateutil.parser.parse(exp).date() >= today]
    if future_expiries:
        return future_expiries[0]
    return expiries[-1]


def _normalize_chain(options: list[dict], selected_expiry: str) -> list[dict]:
    """
    Normalize option data into chain format.
    Groups by strike and combines call/put data.
    """
    chain_map: dict[int, dict] = {}
    
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
        iv = _parse_float(option.get("iv"))
        
        if ltp is None or oi is None:
            continue
        
        if volume is None:
            volume = 0
        if iv is None:
            iv = 0.25  # Default IV estimate
        
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


def _apply_liquidity_filters(chain_list: list[dict]) -> list[dict]:
    total = len(chain_list)
    if total == 0:
        return chain_list

    filtered = []
    for entry in chain_list:
        call_leg = entry.get("call")
        put_leg = entry.get("put")
        if is_leg_liquid(call_leg) and is_leg_liquid(put_leg):
            filtered.append(entry)

    removed = total - len(filtered)
    logger.info(
        "Liquidity filter: total=%s kept=%s removed=%s | min_oi=%s min_vol=%s max_spread_pct=%s",
        total,
        len(filtered),
        removed,
        MIN_OPEN_INTEREST,
        MIN_VOLUME,
        MAX_BID_ASK_SPREAD_PCT,
    )
    return filtered


def get_spot_price(symbol: str = "NIFTY") -> float:
    """Get current spot price of the underlying."""
    if symbol.upper() != "NIFTY":
        raise ValueError("Only NIFTY spot is supported via Upstox")
    return _get_nifty_spot_price()


def get_full_chain(symbol: str = "NIFTY", expiry_date: str | None = None, depth: int = 20) -> dict:
    """
    Fetch complete NIFTY option chain from Upstox.
    
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
            logger.info(f"Using cached chain (age: {(now - cached_time).total_seconds():.1f}s)")
            return cached_data
    
    logger.info(f"Fetching NIFTY option chain from Upstox (expiry={expiry_date})")
    
    # Get spot price
    spot = _get_nifty_spot_price()
    
    # Fetch option quotes
    options = _fetch_nifty_option_quotes(expiry_date)
    if not options:
        logger.warning("No option quotes from Upstox, using empty chain")
        options = []
    
    # Extract and select expiry
    expiries = _extract_expiries(options) if options else []
    
    if not expiries:
        # Return minimal valid response even without data
        logger.warning("No expiry dates found, returning default response")
        result = {
            "spot_price": spot,
            "atm_strike": None,
            "expiry_date": None,
            "available_expiries": [],
            "pcr": 0,
            "chain": [],
            "timestamp": dt.datetime.now().isoformat()
        }
        return result
    
    selected_expiry = _select_expiry(expiries, expiry_date)
    logger.info(f"Using expiry: {selected_expiry} (available: {expiries})")
    
    # Normalize chain
    chain_list = _normalize_chain(options, selected_expiry)
    logger.info(f"Normalized {len(chain_list)} strikes")

    # Apply liquidity and execution filters
    chain_list = _apply_liquidity_filters(chain_list)
    if not chain_list:
        logger.warning("Liquidity filter removed all strikes; returning empty chain")
        result = {
            "spot_price": spot,
            "atm_strike": None,
            "expiry_date": selected_expiry,
            "available_expiries": expiries,
            "pcr": 0,
            "chain": [],
            "timestamp": dt.datetime.now().isoformat()
        }
        _CHAIN_CACHE[cache_key] = (result, now)
        return result
    
    # Get ATM strike
    strikes = [entry["strike"] for entry in chain_list]
    atm_strike = min(strikes, key=lambda k: abs(k - spot)) if strikes else None
    
    # Apply depth filter
    if depth and depth > 0 and atm_strike:
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
    
    logger.info(f"PCR: {pcr} | Call OI: {total_call_oi} | Put OI: {total_put_oi}")
    
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
        raise OptionChainFetchError("Could not fetch expiries from Upstox")
    return expiries


def get_atm_option(chain_dict: dict, spot_price: float, option_type: str = "call") -> dict:
    """Get ATM option from chain dict."""
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


