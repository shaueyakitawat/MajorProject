# Volatility Service
# Handles GARCH/EGARCH volatility forecasting

import pandas as pd
import numpy as np
from arch import arch_model


def forecast_volatility(returns_series: pd.Series) -> float:
    """
    Forecast annualized volatility using GARCH/EGARCH models.
    
    Args:
        returns_series: Series of log returns
        
    Returns:
        float: Annualized forecasted volatility
    """
    # Convert log returns to percentage returns for model fitting
    percentage_returns = returns_series * 100
    
    # Fit EGARCH(1,1) model
    model = arch_model(percentage_returns, vol="EGARCH", p=1, q=1, dist="normal")
    fitted_model = model.fit(disp="off")
    
    # Forecast one-step ahead variance
    forecast = fitted_model.forecast(horizon=1)
    forecasted_variance = forecast.variance.values[-1, 0]
    
    # Convert variance to volatility (standard deviation)
    forecasted_volatility = np.sqrt(forecasted_variance)
    
    # Annualize volatility (convert from percentage to decimal and annualize)
    annualized_volatility = (forecasted_volatility / 100) * np.sqrt(252)
    
    return float(annualized_volatility)
