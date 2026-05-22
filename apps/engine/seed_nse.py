import pandas as pd
from sqlalchemy import create_engine, text
import requests
import io
import os

DB_URL = "postgresql://trader:trader@postgres:5432/smart_trading"
engine = create_engine(DB_URL)

NSE_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"

def seed_nse_stocks():
    print("Downloading NSE equities list...")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    response = requests.get(NSE_URL, headers=headers)
    if response.status_code != 200:
        print(f"Failed to fetch data: {response.status_code}")
        return

    df = pd.read_csv(io.StringIO(response.text))
    print(f"Loaded {len(df)} symbols from NSE.")

    inserted = 0
    with engine.connect() as conn:
        # Clear existing
        conn.execute(text('TRUNCATE TABLE "NseStock" RESTART IDENTITY CASCADE'))
        
        for _, row in df.iterrows():
            symbol = row['SYMBOL'].strip()
            company_name = row['NAME OF COMPANY'].strip() if pd.notna(row['NAME OF COMPANY']) else symbol
            
            conn.execute(text("""
                INSERT INTO "NseStock" (symbol, "companyName", "createdAt")
                VALUES (:sym, :name, NOW())
                ON CONFLICT (symbol) DO NOTHING
            """), {"sym": symbol, "name": company_name})
            inserted += 1
        
        conn.commit()

    print(f"Successfully seeded {inserted} stocks into NseStock table.")

if __name__ == "__main__":
    seed_nse_stocks()
