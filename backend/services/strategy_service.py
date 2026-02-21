# Strategy Service
# Handles strategy recommendation logic


def generate_strategy(mispricing_label: str, regime_label: str) -> dict:
    """
    Generate trading strategy recommendation based on mispricing and volatility regime.
    
    Args:
        mispricing_label: Mispricing classification - "underpriced", "fair", or "overpriced"
        regime_label: Volatility regime - "LOW_VOL", "NORMAL_VOL", "HIGH_VOL", or "EXTREME_VOL"
        
    Returns:
        dict: Structured strategy suggestion containing recommendation and reasoning
    """
    # Rule-based strategy mapping
    strategy_map = {
        # Underpriced scenarios
        ("underpriced", "LOW_VOL"): {
            "strategy": "Consider long volatility strategy",
            "confidence": "high"
        },
        ("underpriced", "NORMAL_VOL"): {
            "strategy": "Consider buying options",
            "confidence": "medium"
        },
        ("underpriced", "HIGH_VOL"): {
            "strategy": "Consider buying options with caution",
            "confidence": "medium"
        },
        ("underpriced", "EXTREME_VOL"): {
            "strategy": "Wait for volatility to stabilize before entry",
            "confidence": "low"
        },
        
        # Fair priced scenarios
        ("fair", "LOW_VOL"): {
            "strategy": "No strong edge",
            "confidence": "low"
        },
        ("fair", "NORMAL_VOL"): {
            "strategy": "No strong edge",
            "confidence": "low"
        },
        ("fair", "HIGH_VOL"): {
            "strategy": "Market fairly priced, no arbitrage opportunity",
            "confidence": "low"
        },
        ("fair", "EXTREME_VOL"): {
            "strategy": "Wait for better opportunity",
            "confidence": "low"
        },
        
        # Overpriced scenarios
        ("overpriced", "LOW_VOL"): {
            "strategy": "Consider selling premium with caution",
            "confidence": "medium"
        },
        ("overpriced", "NORMAL_VOL"): {
            "strategy": "Consider selling premium strategies",
            "confidence": "medium"
        },
        ("overpriced", "HIGH_VOL"): {
            "strategy": "Consider credit spread strategy",
            "confidence": "high"
        },
        ("overpriced", "EXTREME_VOL"): {
            "strategy": "High risk short volatility idea",
            "confidence": "medium"
        }
    }
    
    # Get strategy based on combination
    key = (mispricing_label, regime_label)
    result = strategy_map.get(key, {
        "strategy": "No strategy recommendation available",
        "confidence": "low"
    })
    
    return result
