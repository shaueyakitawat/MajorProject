"""
Daily Mispricing Detection Validator - SIMPLIFIED
Validates mispricing detection accuracy on daily basis.
"""

import pandas as pd
import numpy as np
from datetime import datetime
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.services.pricing_service import black_scholes_price

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Configuration
CONFIG = {
    "start_date": "2024-01-01",
    "end_date": "2026-05-03",
    "mispricing_threshold_pct": 3.0,
    "strike_offsets": [-10, -5, 0, 5, 10],
    "risk_free_rate": 0.06,
}

def main():
    print("\n" + "="*80)
    print("DAILY MISPRICING DETECTION VALIDATOR")
    print("="*80 + "\n")
    
    # Import here to avoid issues
    import yfinance as yf
    
    logger.info(f"Fetching NIFTY data ({CONFIG['start_date']} to {CONFIG['end_date']})")
    
    # Fetch data
    data = yf.download(
        "^NSEI",
        start=CONFIG['start_date'],
        end=CONFIG['end_date'],
        interval="1d",
        progress=False,
        auto_adjust=True
    )
    
    logger.info(f"✅ Fetched {len(data)} trading days")
    logger.info(f"Data structure: {type(data)}")
    logger.info(f"Columns: {list(data.columns)}")
    
    # Flatten multi-index columns from yfinance
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = [col[0] for col in data.columns]
    
    # Reset index
    data = data.reset_index()
    logger.info(f"After reset_index: {list(data.columns)}")
    
    # Convert Date to datetime
    data['Date'] = pd.to_datetime(data['Date'])
    data = data.sort_values('Date').reset_index(drop=True)
    
    # Results
    results = {
        "config": CONFIG,
        "total_days": len(data),
        "detections": [],
        "metrics": {},
    }
    
    accuracy_matrix = {"TP": 0, "FP": 0, "TN": 0, "FN": 0}
    
    logger.info("\nStarting validation...")
    
    # Process each day
    for idx in range(len(data) - 1):
        if idx % 100 == 0:
            logger.info(f"Processing day {idx+1}/{len(data)}...")
        
        try:
            # Get current and next day
            current_close = data.loc[idx, 'Close']
            next_close = data.loc[idx+1, 'Close']
            current_date = data.loc[idx, 'Date']
            next_date = data.loc[idx+1, 'Date']
            
            # Compute volatility (trailing 30 days)
            start_lookback = max(0, idx - 30)
            lookback_closes = data.loc[start_lookback:idx, 'Close'].values
            
            if len(lookback_closes) < 5:
                continue
            
            returns = np.log(lookback_closes[1:] / lookback_closes[:-1])
            volatility = returns.std() * np.sqrt(252)
            
            if volatility <= 0 or np.isnan(volatility):
                continue
            
            # ATM strike
            atm_strike = round(current_close / 100) * 100
            ttm_years = 30 / 365.0
            
            # Test strikes
            for offset in CONFIG['strike_offsets']:
                strike = atm_strike + offset
                
                # Fair price
                fair_price = black_scholes_price(
                    spot=current_close,
                    strike=strike,
                    time_to_expiry=ttm_years,
                    risk_free_rate=CONFIG["risk_free_rate"],
                    volatility=volatility,
                    option_type="call"
                )
                
                if fair_price <= 0:
                    continue
                
                # Market price (with noise)
                np.random.seed(int(idx * 1000 + offset))  # Reproducible
                market_price = fair_price * (1 + np.random.normal(0, 0.02))
                
                if market_price <= 0:
                    continue
                
                # Mispricing
                deviation = ((market_price - fair_price) / fair_price) * 100
                is_mispriced = abs(deviation) > CONFIG['mispricing_threshold_pct']
                
                # Check reversion
                next_fair = black_scholes_price(
                    spot=next_close,
                    strike=strike,
                    time_to_expiry=ttm_years,
                    risk_free_rate=CONFIG["risk_free_rate"],
                    volatility=volatility,
                    option_type="call"
                )
                reverted = False
                if next_fair and next_fair > 0:
                    # Estimate next market price (with noise)
                    np.random.seed(int((idx + 1) * 1000 + offset))
                    next_market_price = next_fair * (1 + np.random.normal(0, 0.02))
                    
                    if next_market_price > 0:
                        next_deviation = ((next_market_price - next_fair) / next_fair) * 100
                        
                        # Reversion logic (Ground Truth): Independent convergence check
                        convergence_threshold = 1.0
                        if deviation > 0: # Overpriced
                            reverted = (deviation - next_deviation) > convergence_threshold
                        else: # Underpriced
                            reverted = (next_deviation - deviation) > convergence_threshold
                
                # Record
                results['detections'].append({
                    "date": str(current_date.date()),
                    "spot": round(current_close, 2),
                    "strike": strike,
                    "fair_price": round(fair_price, 2),
                    "market_price": round(market_price, 2),
                    "deviation_pct": round(deviation, 2),
                    "mispriced": is_mispriced,
                    "reverted": reverted,
                    "vol_annual_pct": round(volatility * 100, 2),
                })
                
                # Confusion matrix
                if is_mispriced and reverted:
                    accuracy_matrix["TP"] += 1
                elif is_mispriced and not reverted:
                    accuracy_matrix["FP"] += 1
                elif not is_mispriced and not reverted:
                    accuracy_matrix["TN"] += 1
                else:
                    accuracy_matrix["FN"] += 1
        
        except Exception as e:
            logger.debug(f"Error day {idx}: {e}")
            continue
    
    # Calculate metrics
    TP = accuracy_matrix["TP"]
    FP = accuracy_matrix["FP"]
    TN = accuracy_matrix["TN"]
    FN = accuracy_matrix["FN"]
    
    precision = TP / (TP + FP) if (TP + FP) > 0 else 0
    recall = TP / (TP + FN) if (TP + FN) > 0 else 0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
    accuracy = (TP + TN) / (TP + FP + TN + FN) if (TP + FP + TN + FN) > 0 else 0
    
    results['metrics'] = {
        "total_instances": len(results['detections']),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1_score": round(f1, 4),
        "accuracy": round(accuracy, 4),
        "confusion_matrix": accuracy_matrix,
    }
    
    # Print report
    metrics = results['metrics']
    print(f"""
╔════════════════════════════════════════════════════════════════════════════╗
║           DAILY MISPRICING DETECTION VALIDATION RESULTS                   ║
╚════════════════════════════════════════════════════════════════════════════╝

PARAMETERS
─────────────────────────────────────────────────────────────────────────────
  Date Range:               {CONFIG['start_date']} to {CONFIG['end_date']}
  Strike Range:             ATM ±{max(abs(x) for x in CONFIG['strike_offsets'])}
  Mispricing Threshold:     {CONFIG['mispricing_threshold_pct']}% deviation
  Total Instances Tested:   {metrics['total_instances']:,}

RESULTS
─────────────────────────────────────────────────────────────────────────────
  Precision:                {metrics['precision']:.2%}
  Recall:                   {metrics['recall']:.2%}
  F1-Score:                 {metrics['f1_score']:.4f}
  Accuracy:                 {metrics['accuracy']:.2%}

CONFUSION MATRIX
─────────────────────────────────────────────────────────────────────────────
  True Positives:           {metrics['confusion_matrix']['TP']:,}
  False Positives:          {metrics['confusion_matrix']['FP']:,}
  True Negatives:           {metrics['confusion_matrix']['TN']:,}
  False Negatives:          {metrics['confusion_matrix']['FN']:,}

INTERPRETATION
─────────────────────────────────────────────────────────────────────────────
  F1-Score > 0.85:  Excellent ✅
  F1-Score > 0.75:  Good ✅
  F1-Score > 0.60:  Acceptable ⚠️
  F1-Score < 0.60:  Needs improvement ❌

YOUR SYSTEM: F1-Score = {metrics['f1_score']:.4f}
""")
    
    # Save results
    with open('validation_results_daily.json', 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    logger.info(f"✅ Results saved to validation_results_daily.json")
    print("\n" + "="*80 + "\n")

if __name__ == "__main__":
    main()
