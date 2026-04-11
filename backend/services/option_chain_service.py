import logging
import yfinance as yf
import pandas as pd

logger = logging.getLogger("api")

def get_spot_price(symbol: str) -> float:
    """
    Fetch the latest spot price for the given symbol.
    
    Args:
        symbol: Ticker symbol (e.g., '^NSEI' or 'NIFTY')
        
    Returns:
        float: Last closing price
        
    Raises:
        ValueError: If data is empty or fetch fails
    """
    # Assuming symbol might need mapping, but let's stick to the prompt's simplicity.
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="1d")
        
        if hist.empty:
            raise ValueError(f"No spot price data returned for symbol: {symbol}")
            
        last_price = float(hist["Close"].iloc[-1])
        return last_price
        
    except Exception as e:
        raise ValueError(f"Failed to fetch spot price for {symbol}: {str(e)}")

def fetch_option_chain(symbol: str) -> dict:
    """
    Fetch the option chain for the nearest expiry.
    
    Args:
        symbol: Ticker symbol
        
    Returns:
        dict: Containing 'expiry', 'calls' (DataFrame), and 'puts' (DataFrame)
        
    Raises:
        ValueError: If no expiries found or chain data is empty
    """
    try:
        ticker = yf.Ticker(symbol)
        expiries = ticker.options
        
        if not expiries:
            raise ValueError(f"No option expiries found for symbol: {symbol}")
            
        nearest_expiry = expiries[0]
        chain = ticker.option_chain(nearest_expiry)
        
        calls = chain.calls
        puts = chain.puts
        
        if calls.empty and puts.empty:
            raise ValueError(f"Option chain data is empty for expiry: {nearest_expiry}")
            
        return {
            "expiry": nearest_expiry,
            "calls": calls,
            "puts": puts
        }
        
    except Exception as e:
        if isinstance(e, ValueError):
            raise
        raise ValueError(f"Failed to fetch option chain for {symbol}: {str(e)}")

def get_atm_option(chain: dict, spot_price: float, option_type: str) -> dict:
    """
    Extract the At-The-Money (ATM) option from the chain.
    
    Args:
        chain: Option chain dictionary returned by fetch_option_chain
        spot_price: Current market spot price
        option_type: "call" or "put"
        
    Returns:
        dict: Containing 'strike', 'ltp', and 'iv'
        
    Raises:
        ValueError: If invalid option type, or pricing data is invalid
    """
    option_type = option_type.lower()
    if option_type not in ["call", "put"]:
        raise ValueError(f"Invalid option_type: '{option_type}'. Must be 'call' or 'put'.")
        
    df = chain["calls"] if option_type == "call" else chain["puts"]
    
    if df.empty:
        raise ValueError(f"The {option_type}s DataFrame is empty.")
        
    # Find ATM strike
    df["strike_diff"] = (df["strike"] - spot_price).abs()
    atm_row = df.loc[df["strike_diff"].idxmin()]
    
    strike = float(atm_row["strike"])
    last_price = float(atm_row["lastPrice"])
    bid = float(atm_row["bid"])
    ask = float(atm_row["ask"])
    iv = float(atm_row["impliedVolatility"])
    
    # Determine LTP
    if last_price > 0:
        ltp = last_price
        source = "lastPrice"
    elif bid > 0 and ask > 0 and ask >= bid:
        ltp = (bid + ask) / 2.0
        source = "mid_price (bid/ask)"
    else:
        raise ValueError(f"Invalid pricing data for ATM {option_type} (Strike: {strike}). Last: {last_price}, Bid: {bid}, Ask: {ask}")
        
    logger.info(
        f"Selected ATM {option_type.upper()} | Expiry: {chain['expiry']} | "
        f"Strike: {strike} | Spot: {spot_price:.2f} | "
        f"LTP: {ltp:.2f} (Source: {source})"
    )
    
    return {
        "strike": strike,
        "ltp": ltp,
        "iv": iv
    }
