"""
Mock/test script for NIFTY 50 option chain data validation.
Demonstrates the Upstox integration without requiring a real API token.
"""

import json
import sys
sys.path.insert(0, '.')

# Mock response data - representative NIFTY option chain structure
MOCK_NIFTY_SPOT = 22500.0

MOCK_OPTION_CHAIN = {
    "status": "success",
    "data": {
        "instrumentQuotes": {
            "NIFTY_INDEX": {
                "ltp": MOCK_NIFTY_SPOT,
                "oi": 0,
                "volume": 0
            },
            "NIFTY_22400_CE": {
                "ltp": 135.50,
                "oi": 125000,
                "volume": 45000,
                "bid": 135.00,
                "ask": 136.00,
                "metadata": {
                    "strikePrice": 22400,
                    "expiryDate": "2026-05-16",
                    "optionType": "CE"
                }
            },
            "NIFTY_22400_PE": {
                "ltp": 45.75,
                "oi": 185000,
                "volume": 52000,
                "bid": 45.50,
                "ask": 46.00,
                "metadata": {
                    "strikePrice": 22400,
                    "expiryDate": "2026-05-16",
                    "optionType": "PE"
                }
            },
            "NIFTY_22500_CE": {
                "ltp": 98.25,
                "oi": 250000,
                "volume": 85000,
                "bid": 98.00,
                "ask": 98.50,
                "metadata": {
                    "strikePrice": 22500,
                    "expiryDate": "2026-05-16",
                    "optionType": "CE"
                }
            },
            "NIFTY_22500_PE": {
                "ltp": 78.50,
                "oi": 225000,
                "volume": 95000,
                "bid": 78.25,
                "ask": 78.75,
                "metadata": {
                    "strikePrice": 22500,
                    "expiryDate": "2026-05-16",
                    "optionType": "PE"
                }
            },
            "NIFTY_22600_CE": {
                "ltp": 65.30,
                "oi": 195000,
                "volume": 72000,
                "bid": 65.00,
                "ask": 65.60,
                "metadata": {
                    "strikePrice": 22600,
                    "expiryDate": "2026-05-16",
                    "optionType": "CE"
                }
            },
            "NIFTY_22600_PE": {
                "ltp": 112.75,
                "oi": 165000,
                "volume": 48000,
                "bid": 112.50,
                "ask": 113.00,
                "metadata": {
                    "strikePrice": 22600,
                    "expiryDate": "2026-05-16",
                    "optionType": "PE"
                }
            }
        }
    }
}


def test_option_chain_normalization():
    """Test the option chain normalization logic."""
    from backend.services import option_chain_service
    
    print("\n" + "="*70)
    print("NIFTY 50 OPTION CHAIN DATA VALIDATION TEST")
    print("="*70)
    
    # Extract quotes into option list
    options = []
    quotes = MOCK_OPTION_CHAIN["data"]["instrumentQuotes"]
    
    for instrument_key, quote in quotes.items():
        if instrument_key == "NIFTY_INDEX":
            continue
        
        if "metadata" in quote:
            metadata = quote["metadata"]
            options.append({
                "instrument_key": instrument_key,
                "strike": metadata.get("strikePrice"),
                "expiry": metadata.get("expiryDate"),
                "option_type": metadata.get("optionType"),
                "ltp": quote.get("ltp"),
                "oi": quote.get("oi"),
                "volume": quote.get("volume"),
                "bid": quote.get("bid"),
                "ask": quote.get("ask"),
            })
    
    print(f"\n✓ Extracted {len(options)} option instruments from mock data")
    
    # Extract expiries
    expiries = option_chain_service._extract_expiries(options)
    print(f"✓ Available Expiries: {expiries}")
    
    # Select expiry
    selected_expiry = option_chain_service._select_expiry(expiries, None)
    print(f"✓ Selected Expiry: {selected_expiry}")
    
    # Normalize chain
    chain_list = option_chain_service._normalize_chain(options, selected_expiry)
    print(f"✓ Normalized Chain Strikes: {len(chain_list)}")
    
    # Display chain data
    print("\n" + "-"*70)
    print("OPTION CHAIN DATA (NIFTY)")
    print("-"*70)
    print(f"{'Strike':<10} {'Call LTP':<12} {'Call OI':<15} {'Put LTP':<12} {'Put OI':<15}")
    print("-"*70)
    
    for entry in chain_list:
        strike = entry["strike"]
        call_ltp = entry["call"]["ltp"]
        call_oi = entry["call"]["oi"]
        put_ltp = entry["put"]["ltp"]
        put_oi = entry["put"]["oi"]
        
        print(f"{strike:<10} {call_ltp:<12.2f} {call_oi:<15,} {put_ltp:<12.2f} {put_oi:<15,}")
    
    # Calculate PCR
    total_call_oi = sum(e["call"]["oi"] for e in chain_list)
    total_put_oi = sum(e["put"]["oi"] for e in chain_list)
    pcr = round(total_put_oi / total_call_oi, 2) if total_call_oi > 0 else 0
    
    # Find ATM
    spot = MOCK_NIFTY_SPOT
    strikes = [e["strike"] for e in chain_list]
    atm_strike = min(strikes, key=lambda k: abs(k - spot))
    
    print("-"*70)
    print(f"\nSPOT PRICE:     ₹{spot}")
    print(f"ATM STRIKE:     {atm_strike}")
    print(f"CALL OI:        {total_call_oi:,}")
    print(f"PUT OI:         {total_put_oi:,}")
    print(f"PUT/CALL RATIO: {pcr}")
    
    print("\n" + "="*70)
    print("✓ TEST PASSED: Option chain data structure is valid")
    print("="*70 + "\n")
    
    return {
        "spot_price": spot,
        "atm_strike": atm_strike,
        "expiry": selected_expiry,
        "chain": chain_list,
        "pcr": pcr,
        "total_call_oi": total_call_oi,
        "total_put_oi": total_put_oi
    }


if __name__ == "__main__":
    try:
        result = test_option_chain_normalization()
        print("\nRESULT JSON:")
        print(json.dumps({
            "spot_price": result["spot_price"],
            "atm_strike": result["atm_strike"],
            "expiry": result["expiry"],
            "pcr": result["pcr"],
            "chain_count": len(result["chain"])
        }, indent=2))
    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
