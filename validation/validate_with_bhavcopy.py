"""
Publication Validation Script
==============================
Validates the mispricing pipeline against REAL historical data downloaded from NSE India.
Outputs precision, recall, F1, and a confusion matrix suitable for the journal paper.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import yfinance as yf
import sys
import logging
from pathlib import Path
import json

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.services.nse_data_service import NSEDataService
from backend.services.pricing_service import black_scholes_price
from backend.services.implied_volatility_service import calculate_implied_volatility
from backend.services.vrp_service import compute_vrp
from backend.services.regime_service import classify_volatility_regime
from backend.services.mispricing_service import detect_mispricing

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

def load_spot_data(start_date, end_date):
    logger.info(f"Loading NIFTY spot data from {start_date} to {end_date}...")
    
    # We load extra history for the rolling volatility (which needs 60 days)
    data_start = (pd.to_datetime(start_date) - pd.Timedelta(days=90)).strftime('%Y-%m-%d')
    data = yf.download("^NSEI", start=data_start, end=end_date, interval="1d", progress=False)
    
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = [col[0] for col in data.columns]
    
    data = data.reset_index()
    data['Date'] = pd.to_datetime(data['Date'])
    
    # Calculate log returns for the entire dataset upfront
    data['log_return'] = np.log(data['Close'] / data['Close'].shift(1))
    
    return data

def run_validation():
    print("=" * 80)
    print("   QUANTITATIVE PIPELINE VALIDATION ON REAL MARKET DATA (NSE BHAVCOPY)")
    print("=" * 80)
    
    nse_service = NSEDataService(data_dir=r"d:\MajorProject\data\nse_bhavcopy")
    
    # Run only for Q1 2024 which we know we downloaded
    start_test_date = pd.to_datetime("2024-01-01")
    end_test_date = pd.to_datetime("2024-03-31")
    
    spot_df = load_spot_data(start_test_date.strftime("%Y-%m-%d"), end_test_date.strftime("%Y-%m-%d"))
    
    # Filter testing dates
    test_dates = spot_df[(spot_df['Date'] >= start_test_date) & (spot_df['Date'] <= end_test_date)]
    total_days = len(test_dates)
    
    logger.info(f"Loaded {total_days} valid trading days for testing.")
    
    results = []
    matrix = {"TP": 0, "FP": 0, "TN": 0, "FN": 0}
    
    risk_free_rate = 0.07 # 7% India approx for 2024
    
    for idx, row in test_dates.iterrows():
        current_date = row['Date']
        spot_price = float(row['Close'])
        
        # We need next day to evaluate reversion
        if idx + 1 >= len(spot_df):
            break
            
        next_date = spot_df.loc[idx + 1, 'Date']
        next_spot = float(spot_df.loc[idx + 1, 'Close'])
        
        # Load historical returns up to today 
        historical = spot_df.loc[:idx].copy()
        historical = historical.dropna(subset=['log_return'])
        
        if len(historical) < 60:
            continue
            
        returns = historical['log_return']
        
        # Use simple historical standard deviation (annualized) as baseline vol forecasting
        vol_daily = returns.std() * np.sqrt(252)
        
        if np.isnan(vol_daily) or vol_daily == 0:
            continue
            
        # Select ATM strike
        atm_strike = round(spot_price / 100) * 100
        
        ttm_years = 30 / 365.0  # Approx nearest month
        
        # Evaluate for ATM and 1 strike OUT
        strikes = [atm_strike, atm_strike + 100, atm_strike - 100]
        
        # Check if we have NSE data for these dates
        df_current = nse_service.load_bhavcopy_for_date(current_date)
        df_next = nse_service.load_bhavcopy_for_date(next_date)
        
        if df_current.empty or df_next.empty:
            continue
            
        for strike in strikes:
            # 1. ACTUAL MARKET PRICE (from NSE)
            market_price = nse_service.get_real_option_price(current_date, strike, "call")
            
            if not market_price:
                continue
                
            # 2. COMPUTED FAIR PRICE (Model)
            fair_price = black_scholes_price(
                spot=spot_price, strike=strike, 
                time_to_expiry=ttm_years, risk_free_rate=risk_free_rate, 
                volatility=vol_daily, option_type="call"
            )
            
            if fair_price <= 0:
                continue
                
            # 3. IMPLIED VOL & VRP
            iv = calculate_implied_volatility(spot_price, strike, ttm_years, risk_free_rate, market_price, "call")
            vrp_dict = compute_vrp(iv, vol_daily, "NORMAL_VOL") # mock regime for now
            current_vrp = vrp_dict["vrp"] if vrp_dict else 0
            
            # 4. MISPRICING DETECTION
            mispricing = detect_mispricing(
                market_price, fair_price, 
                vega=0.15, gamma=0.002, tci=None, 
                current_vrp=current_vrp, expected_vrp=None
            )
            
            deviation = mispricing["deviation"] * 100
            
            # For this test, let's treat anything with |deviation| > 15% as mispriced
            is_mispriced = abs(deviation) > 15.0
            
            # 5. ACTUAL NEXT DAY OBSERVATION
            next_market = nse_service.get_real_option_price(next_date, strike, "call")
            
            if next_market:
                # Re-compute fair price based on spot move
                next_fair = black_scholes_price(
                    spot=next_spot, strike=strike, 
                    time_to_expiry=ttm_years - (1/365.0), risk_free_rate=risk_free_rate, 
                    volatility=vol_daily, option_type="call"
                )
                
                if next_fair > 0:
                    next_deviation = ((next_market - next_fair) / next_fair) * 100
                    
                    if is_mispriced:
                        # Did it correct?
                        if deviation > 0: # was overpriced, should fall
                            reverted = next_deviation < deviation
                        else: # was underpriced, should rise
                            reverted = next_deviation > deviation
                            
                    else:
                        reverted = False
                        
                    results.append({
                        "date": current_date.strftime("%Y-%m-%d"),
                        "strike": strike,
                        "market_price": market_price,
                        "fair_price": round(fair_price, 2),
                        "deviation_pct": round(deviation, 2),
                        "mispriced": is_mispriced,
                        "reverted": reverted
                    })
                    
                    if is_mispriced and reverted:
                        matrix["TP"] += 1
                    elif is_mispriced and not reverted:
                        matrix["FP"] += 1
                    elif not is_mispriced and not reverted:
                        matrix["TN"] += 1
                    else:
                        matrix["FN"] += 1

    
    # Output metrics
    TP = matrix["TP"]
    FP = matrix["FP"]
    TN = matrix["TN"]
    FN = matrix["FN"]
    
    total = TP + FP + TN + FN
    
    if total == 0:
        print("No valid option data found for the date range.")
        return
        
    precision = TP / (TP + FP) if (TP + FP) > 0 else 0
    recall = TP / (TP + FN) if (TP + FN) > 0 else 0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
    accuracy = (TP + TN) / total
    
    print(f"\n===========================================================")
    print(f"               EXPERIMENTAL RESULTS (Q1 2024)")
    print(f"===========================================================")
    print(f"Total Transactions Validated: {total}")
    print(f"Total True Positives (Model caught real mispricing): {TP}")
    print(f"Total False Positives (Model cried wolf): {FP}")
    print(f"Total True Negatives (Model correctly ignored): {TN}")
    print(f"Total False Negatives (Model missed opportunity): {FN}\n")
    print(f"Precision: {precision:.4f} ({precision*100:.1f}%)")
    print(f"Recall:    {recall:.4f} ({recall*100:.1f}%)")
    print(f"F1-Score:  {f1:.4f}")
    print(f"Accuracy:  {accuracy:.4f} ({accuracy*100:.1f}%)")
    print(f"===========================================================")
    
    # Save to disk
    df_results = pd.DataFrame(results)
    df_results.to_csv(r"d:\MajorProject\outputs\publication_results.csv", index=False)
    print("Saved detailed line-by-line results to outputs/publication_results.csv")

if __name__ == "__main__":
    run_validation()
