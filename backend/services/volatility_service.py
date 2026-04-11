# Volatility Service
# Handles GARCH/EGARCH volatility forecasting

import pandas as pd
import numpy as np
from arch import arch_model


def forecast_volatility(returns_series: pd.Series) -> float:
    """
    Forecast next-period volatility using EGARCH(1,1).
    
    Returns RAW per-period volatility (not annualized).
    Caller must annualize using annualization_engine.apply_dynamic_annualization().
    
    Args:
        returns_series: Series of log returns
        
    Returns:
        float: Raw per-period forecasted volatility (decimal scale)
    """
    percentage_returns = returns_series * 100

    model = arch_model(percentage_returns, vol="EGARCH", p=1, q=1, dist="normal")
    fitted_model = model.fit(disp="off")

    forecast = fitted_model.forecast(horizon=1)
    forecasted_variance = forecast.variance.values[-1, 0]

    forecasted_volatility = np.sqrt(forecasted_variance)

    # Convert from percentage scale back to decimal
    # DO NOT annualize here — caller handles timeframe-aware scaling
    raw_volatility = forecasted_volatility / 100

    return float(raw_volatility)
