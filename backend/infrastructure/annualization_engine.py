"""
Annualization Engine Module

This module provides dynamic volatility annualization infrastructure for 
multi-timeframe quant research. It scales periodic volatility forecasts 
(from EGARCH models) to annualized values using appropriate factors.

IMPORTANT: This is a post-processing layer only.
- DO NOT modify forecast_volatility() in volatility_service
- DO NOT change EGARCH(1,1) model parameters
- Only scales AFTER volatility forecast is computed
- Pure mathematical transformation based on timeframe

Quant Background:
-----------------
Volatility scales with the square root of time (fundamental property of 
Brownian motion in financial mathematics). If σ_period is the volatility
over a period, then the annualized volatility is:

    σ_annual = σ_period × √N

where N is the number of periods per year.

Example:
- Daily volatility of 1%: σ_annual = 0.01 × √252 ≈ 15.87%
- 5-minute volatility of 0.2%: σ_annual = 0.002 × √19656 ≈ 28.05%

This relationship holds under assumptions of:
1. Independent increments (no autocorrelation)
2. Stationarity over the scaling period
3. Geometric Brownian motion (standard finance assumption)

For EGARCH models, the conditional variance forecast represents the period
variance. This module converts it to annualized standard deviation for 
consistent comparison across timeframes.
"""

import math
from backend.infrastructure.timeframe_config import get_annualization_factor


def apply_dynamic_annualization(raw_vol: float, timeframe: str) -> float:
    """
    Apply dynamic annualization to raw volatility forecast.
    
    This function converts periodic volatility (e.g., 1-minute, daily) to 
    annualized volatility using the square root of time rule. It is designed
    to run AFTER the EGARCH forecast is computed, providing a consistent
    annualized metric across different timeframes.
    
    Mathematical Formula:
        annualized_vol = raw_vol × √(annualization_factor)
    
    Where annualization_factor is the number of periods per year:
        - 1m:   252 × 390 = 98,280 (trading minutes per year)
        - 5m:   252 × 78  = 19,656 (5-min bars per year)
        - 15m:  252 × 26  = 6,552  (15-min bars per year)
        - 1h:   252 × 6.5 = 1,638  (hourly bars per year)
        - daily: 252              (trading days per year)
        - weekly: 52              (weeks per year)
    
    **CRITICAL: This function does NOT:**
    - Modify the EGARCH model
    - Change forecast_volatility() in volatility_service
    - Apply any trading logic
    - Perform resampling or data transformation
    
    **This function ONLY:**
    - Scales the EGARCH output to annualized terms
    - Applies the √t scaling rule from financial mathematics
    - Validates input for computational safety
    
    Args:
        raw_vol: Raw volatility from EGARCH forecast (unitless, period-specific)
            Example: If EGARCH forecasts daily volatility of 0.015 (1.5%), 
                     raw_vol = 0.015
        timeframe: Timeframe identifier (e.g., "5m", "daily", "weekly")
            Must be a valid timeframe from timeframe_config
    
    Returns:
        float: Annualized volatility (same units as raw_vol, but annualized)
            Example: Daily vol 0.015 → Annualized ≈ 0.2382 (23.82%)
    
    Raises:
        ValueError: If raw_vol is not finite
        ValueError: If raw_vol is not positive (≤ 0)
        ValueError: If timeframe is invalid (validated by get_annualization_factor)
    
    Example:
        >>> # EGARCH forecasts daily volatility of 1.5%
        >>> raw_vol = 0.015
        >>> annualized_vol = apply_dynamic_annualization(raw_vol, "daily")
        >>> print(f"Annualized: {annualized_vol:.4f}")  # ≈ 0.2382 (23.82%)
        Annualized: 0.2382
        
        >>> # EGARCH forecasts 5-minute volatility of 0.1%
        >>> raw_vol_5m = 0.001
        >>> annualized_vol_5m = apply_dynamic_annualization(raw_vol_5m, "5m")
        >>> print(f"Annualized: {annualized_vol_5m:.4f}")  # ≈ 0.1401 (14.01%)
        Annualized: 0.1401
    
    Notes:
        - This is pure mathematical scaling, not a model
        - Assumes volatility follows √t scaling (standard in finance)
        - Required for comparing volatilities across different timeframes
        - Should be called after EGARCH forecast, before strategy generation
        - Does not replace or modify any existing pipeline logic
    
    Quant Rationale:
        The √t rule comes from the variance of a random walk:
            Var(X_t) = t × Var(X_1)
            StdDev(X_t) = √t × StdDev(X_1)
        
        EGARCH gives us StdDev(X_1) for period 1.
        We multiply by √N to get annual StdDev where N = periods/year.
    """
    
    # Validation Guard 1: Check if raw_vol is finite
    if not math.isfinite(raw_vol):
        raise ValueError(
            f"raw_vol must be finite. Got: {raw_vol} (type: {type(raw_vol).__name__})"
        )
    
    # Validation Guard 2: Check if raw_vol is positive
    if raw_vol <= 0:
        raise ValueError(
            f"raw_vol must be positive (> 0). Got: {raw_vol}. "
            f"Volatility cannot be zero or negative."
        )
    
    # Get annualization factor from config (this validates timeframe)
    try:
        annualization_factor = get_annualization_factor(timeframe)
    except ValueError as e:
        # Re-raise with additional context
        raise ValueError(
            f"Cannot annualize volatility: {str(e)}"
        )
    
    # Apply square root of time scaling rule
    # σ_annual = σ_period × √N
    annualized_vol = raw_vol * math.sqrt(annualization_factor)
    
    # Final safety check (should be finite if input was finite, but verify)
    if not math.isfinite(annualized_vol):
        raise ValueError(
            f"Annualization resulted in non-finite value. "
            f"raw_vol={raw_vol}, factor={annualization_factor}, result={annualized_vol}"
        )
    
    return annualized_vol


def reverse_annualization(annualized_vol: float, timeframe: str) -> float:
    """
    Reverse annualization to get period-specific volatility.
    
    This is the inverse operation of apply_dynamic_annualization.
    Useful for backtesting or when you need to convert annualized
    volatility back to period-specific values.
    
    Mathematical Formula:
        period_vol = annualized_vol / √(annualization_factor)
    
    Args:
        annualized_vol: Annualized volatility value
        timeframe: Timeframe identifier (e.g., "5m", "daily", "weekly")
    
    Returns:
        float: Period-specific volatility
    
    Raises:
        ValueError: If annualized_vol is not finite or not positive
        ValueError: If timeframe is invalid
    
    Example:
        >>> # Annualized volatility of 23.82%
        >>> annualized_vol = 0.2382
        >>> daily_vol = reverse_annualization(annualized_vol, "daily")
        >>> print(f"Daily vol: {daily_vol:.4f}")  # ≈ 0.015 (1.5%)
        Daily vol: 0.0150
    
    Notes:
        - This is the mathematical inverse of apply_dynamic_annualization
        - Useful for converting annualized targets to period metrics
        - Maintains consistency with the √t rule
    """
    
    # Validation (same as forward direction)
    if not math.isfinite(annualized_vol):
        raise ValueError(
            f"annualized_vol must be finite. Got: {annualized_vol}"
        )
    
    if annualized_vol <= 0:
        raise ValueError(
            f"annualized_vol must be positive (> 0). Got: {annualized_vol}"
        )
    
    # Get annualization factor
    try:
        annualization_factor = get_annualization_factor(timeframe)
    except ValueError as e:
        raise ValueError(
            f"Cannot reverse annualization: {str(e)}"
        )
    
    # Apply inverse square root of time scaling
    # σ_period = σ_annual / √N
    period_vol = annualized_vol / math.sqrt(annualization_factor)
    
    # Safety check
    if not math.isfinite(period_vol):
        raise ValueError(
            f"Reverse annualization resulted in non-finite value. "
            f"annualized_vol={annualized_vol}, factor={annualization_factor}, result={period_vol}"
        )
    
    return period_vol


def get_annualization_info(timeframe: str) -> dict:
    """
    Get detailed annualization information for a given timeframe.
    
    Useful for debugging, logging, and research transparency.
    
    Args:
        timeframe: Timeframe identifier (e.g., "5m", "daily", "weekly")
    
    Returns:
        dict: Information about annualization for this timeframe:
            - 'timeframe': The input timeframe
            - 'annualization_factor': Number of periods per year
            - 'sqrt_factor': Square root of annualization factor
            - 'example_period_vol': Example period vol (1%)
            - 'example_annual_vol': Corresponding annual vol
    
    Example:
        >>> info = get_annualization_info("daily")
        >>> print(f"Daily: {info['sqrt_factor']:.2f}x multiplier")
        Daily: 15.87x multiplier
    """
    
    from backend.infrastructure.timeframe_config import get_annualization_factor
    
    factor = get_annualization_factor(timeframe)
    sqrt_factor = math.sqrt(factor)
    
    # Example calculation: 1% period vol → annual vol
    example_period_vol = 0.01
    example_annual_vol = example_period_vol * sqrt_factor
    
    return {
        'timeframe': timeframe,
        'annualization_factor': factor,
        'sqrt_factor': sqrt_factor,
        'example_period_vol': example_period_vol,
        'example_annual_vol': example_annual_vol,
        'description': f"Multiply period volatility by {sqrt_factor:.4f} to annualize"
    }
