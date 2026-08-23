import os
import time
import zipfile
import requests
from datetime import datetime, timedelta
import pandas as pd
from pathlib import Path

# NSE website blocks default python requests, so we need typical browser headers
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
    'Accept-Language': 'en-US,en;q=0.5',
    'Connection': 'keep-alive',
}

def get_nse_session():
    """Initializes a session and visits the homepage to get the required cookies"""
    session = requests.Session()
    session.headers.update(HEADERS)
    print("Initializing NSE session (fetching cookies)...")
    try:
        session.get("https://www.nseindia.com", timeout=10)
        time.sleep(2)
    except Exception as e:
        print(f"Failed to get initial cookies: {e}")
    return session


def download_bhavcopy(date_obj, session, output_dir):
    """
    Downloads the F&O Bhavcopy for a specific date.
    NSE URL format for older bhavcopy: https://archives.nseindia.com/content/historical/DERIVATIVES/YYYY/MMM/foDDMMMYYYYbhav.csv.zip
    """
    year = date_obj.strftime("%Y")
    month_upper = date_obj.strftime("%b").upper() # e.g. JAN
    day_str = date_obj.strftime("%d")
    
    file_name = f"fo{day_str}{month_upper}{year}bhav.csv.zip"
    url = f"https://archives.nseindia.com/content/historical/DERIVATIVES/{year}/{month_upper}/{file_name}"
    
    zip_path = os.path.join(output_dir, file_name)
    csv_path = zip_path.replace(".zip", "")
    
    if os.path.exists(csv_path):
        print(f"Skipping {date_obj.strftime('%Y-%m-%d')}: CSV already exists.")
        return True
        
    print(f"Downloading {date_obj.strftime('%Y-%m-%d')}...")
    
    try:
        response = session.get(url, timeout=10)
        if response.status_code == 200:
            with open(zip_path, 'wb') as f:
                f.write(response.content)
            
            # Unzip it immediately
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(output_dir)
            
            # Clean up zip file
            os.remove(zip_path)
            print(f"  -> Successfully saved and extracted data for {date_obj.strftime('%Y-%m-%d')}")
            return True
        elif response.status_code == 404:
            print(f"  -> Not found (likely a weekend/holiday).")
            return False
        else:
            print(f"  -> Failed with status {response.status_code}")
            return False
    except Exception as e:
        print(f"  -> Error: {e}")
        return False


def main():
    print("=========================================================")
    print("      NSE F&O BHAVCOPY DOWNLOADER FOR BACKTESTING        ")
    print("=========================================================")
    
    output_dir = Path(r"d:\MajorProject\data\nse_bhavcopy")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # We will download January to March 2024 (approx 3 months)
    start_date = datetime(2024, 1, 1)
    end_date = datetime(2024, 3, 31)
    
    print(f"Target directory: {output_dir}")
    print(f"Target range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    print("=========================================================\n")
    
    session = get_nse_session()
    
    current_date = start_date
    success_count = 0
    
    while current_date <= end_date:
        # Skip weekends automatically
        if current_date.weekday() < 5: 
            success = download_bhavcopy(current_date, session, output_dir)
            if success:
                success_count += 1
            time.sleep(1) # Be nice to the NSE servers!
            
        current_date += timedelta(days=1)
        
    print(f"\n=========================================================")
    print(f"Download complete! Saved {success_count} trading days of data.")
    print("You can verify the files in:")
    print(output_dir)
    print("=========================================================")

if __name__ == "__main__":
    main()
