"""
Timeframe Configuration Module

This module provides configuration for different trading timeframes and their
annualization factors. It supports intraday (1m, 5m, 15m, 1h), daily, and 
weekly timeframes with appropriate horizon group mappings.

DO NOT modify existing pipeline logic. This is configuration only.
"""

TIMEFRAME_CONFIG = {
    "1m": {
        "annualization": 252 * 390,  # 252 trading days * 390 minutes per day
        "horizon_group": "day_trader"
    },
    "5m": {
        "annualization": 252 * 78,  # 252 trading days * 78 5-min bars per day
        "horizon_group": "day_trader"
    },
    "15m": {
        "annualization": 252 * 26,  # 252 trading days * 26 15-min bars per day
        "horizon_group": "day_trader"
    },
    "1h": {
        "annualization": 252 * 6.5,  # 252 trading days * 6.5 hours per day
        "horizon_group": "positional"
    },
    "daily": {
        "annualization": 252,  # 252 trading days per year
        "horizon_group": "positional"
    },
    "weekly": {
        "annualization": 52,  # 52 weeks per year
        "horizon_group": "long_term"
    }
}

# Default timeframe mapping for each horizon type
HORIZON_DEFAULT_TIMEFRAMES = {
    "day_trader": "5m",
    "positional": "daily",
    "long_term": "weekly",
    None: "daily"
}


def validate_timeframe(timeframe: str) -> str:
    """
    Validate that the provided timeframe is supported.
    
    Args:
        timeframe: Timeframe string to validate (e.g., "1m", "5m", "daily")
    
    Returns:
        str: The validated timeframe string (unchanged if valid)
    
    Raises:
        ValueError: If the timeframe is not in TIMEFRAME_CONFIG
    
    Example:
        >>> validate_timeframe("5m")
        '5m'
        >>> validate_timeframe("invalid")
        ValueError: Invalid timeframe 'invalid'. Must be one of: 1m, 5m, 15m, 1h, daily, weekly
    """
    if timeframe not in TIMEFRAME_CONFIG:
        valid_timeframes = ", ".join(sorted(TIMEFRAME_CONFIG.keys()))
        raise ValueError(
            f"Invalid timeframe '{timeframe}'. Must be one of: {valid_timeframes}"
        )
    return timeframe


def get_annualization_factor(timeframe: str) -> float:
    """
    Get the annualization factor for a given timeframe.
    
    The annualization factor is used to convert periodic volatility (e.g., 1-minute)
    to annualized volatility by multiplying: vol_annual = vol_period * sqrt(factor)
    
    Args:
        timeframe: Timeframe string (must be valid, will be validated)
    
    Returns:
        float: The annualization factor for the given timeframe
    
    Raises:
        ValueError: If the timeframe is invalid
    
    Example:
        >>> get_annualization_factor("daily")
        252
        >>> get_annualization_factor("5m")
        19656
    """
    validated_timeframe = validate_timeframe(timeframe)
    return TIMEFRAME_CONFIG[validated_timeframe]["annualization"]


def get_default_timeframe_for_horizon(horizon: str | None) -> str:
    """
    Get the default timeframe for a given trading horizon.
    
    Maps trading horizons to their most appropriate default timeframes:
    - day_trader -> 5m (intraday focus)
    - positional -> daily (swing trading)
    - long_term -> weekly (position trading)
    - None -> daily (general purpose default)
    
    Args:
        horizon: Trading horizon string or None
            Valid values: "day_trader", "positional", "long_term", None
    
    Returns:
        str: The default timeframe for the given horizon
    
    Raises:
        ValueError: If horizon is not None and not in the valid set
    
    Example:
        >>> get_default_timeframe_for_horizon("day_trader")
        '5m'
        >>> get_default_timeframe_for_horizon(None)
        'daily'
        >>> get_default_timeframe_for_horizon("invalid")
        ValueError: Invalid horizon 'invalid'. Must be one of: day_trader, positional, long_term, or None
    """
    if horizon not in HORIZON_DEFAULT_TIMEFRAMES:
        valid_horizons = ", ".join([str(h) for h in HORIZON_DEFAULT_TIMEFRAMES.keys()])
        raise ValueError(
            f"Invalid horizon '{horizon}'. Must be one of: {valid_horizons}"
        )
    return HORIZON_DEFAULT_TIMEFRAMES[horizon]


def get_horizon_group(timeframe: str) -> str:
    """
    Get the horizon group associated with a given timeframe.
    
    Args:
        timeframe: Timeframe string (must be valid, will be validated)
    
    Returns:
        str: The horizon group ("day_trader", "positional", or "long_term")
    
    Raises:
        ValueError: If the timeframe is invalid
    
    Example:
        >>> get_horizon_group("5m")
        'day_trader'
        >>> get_horizon_group("daily")
        'positional'
    """
    validated_timeframe = validate_timeframe(timeframe)
    return TIMEFRAME_CONFIG[validated_timeframe]["horizon_group"]
