# Mispricing Service
# Handles mispricing detection logic


def detect_mispricing(market_price: float, fair_price: float) -> dict:
    """
    Detect mispricing by comparing market price with Black-Scholes fair value.
    
    Args:
        market_price: Actual traded/quoted option price from market
        fair_price: Theoretical option price from Black-Scholes model
        
    Returns:
        dict: Contains 'deviation' (float) and 'classification' (str)
              Classification: "underpriced", "fair", or "overpriced"
    """
    deviation = (market_price - fair_price) / fair_price

    if deviation > 0.05:
        classification = "overpriced"
    elif deviation < -0.05:
        classification = "underpriced"
    else:
        classification = "fair"
    
    return {
        "deviation": float(deviation),
        "classification": classification
    }
