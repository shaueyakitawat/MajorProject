# Regime Service
# Handles volatility regime classification


def classify_volatility_regime(volatility_value: float) -> str:
    """
    Classify market volatility regime based on annualized volatility level.
    
    Args:
        volatility_value: Annualized forecasted volatility (as decimal)
        
    Returns:
        str: Regime label - "LOW_VOL", "NORMAL_VOL", "HIGH_VOL", or "EXTREME_VOL"
    """
    # Classify based on volatility thresholds
    if volatility_value < 0.15:
        return "LOW_VOL"
    elif volatility_value < 0.25:
        return "NORMAL_VOL"
    elif volatility_value < 0.40:
        return "HIGH_VOL"
    else:
        return "EXTREME_VOL"
