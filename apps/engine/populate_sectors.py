import requests
import yfinance as yf
import time
import random
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

API_URL = "http://api:3000/api/nse-stocks"

def get_all_stocks():
    try:
        response = requests.get(f"{API_URL}/all")
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logging.error(f"Failed to fetch stocks: {e}")
        return []

def update_stock_sector(symbol, sector):
    try:
        response = requests.patch(
            f"{API_URL}/update-sector",
            json={"symbol": symbol, "sector": sector}
        )
        response.raise_for_status()
        return True
    except Exception as e:
        logging.error(f"Failed to update sector for {symbol}: {e}")
        return False

def main():
    logging.info("Fetching all stocks from DB...")
    stocks = get_all_stocks()
    if not stocks:
        logging.error("No stocks found or API is down.")
        return

    # Filter stocks that don't have a sector yet
    pending_stocks = [s for s in stocks if not s.get("sector")]
    logging.info(f"Total stocks: {len(stocks)}. Stocks missing sector: {len(pending_stocks)}")

    # We will prioritize fetching sectors for the ones missing them.
    # To prevent rate limiting, we do batches of 100 with a sleep.
    # For now, let's process them all but with randomized sleep.
    
    updated_count = 0
    failed_count = 0

    for i, stock in enumerate(pending_stocks):
        symbol = stock["symbol"]
        
        # We assume symbol is something like RELIANCE, so we append .NS
        yf_symbol = f"{symbol}.NS"
        
        try:
            ticker = yf.Ticker(yf_symbol)
            info = ticker.info
            sector = info.get("sector")
            
            if not sector:
                sector = "Unknown"
                
            success = update_stock_sector(symbol, sector)
            if success:
                logging.info(f"[{i+1}/{len(pending_stocks)}] Updated {symbol} -> {sector}")
                updated_count += 1
            else:
                failed_count += 1

        except Exception as e:
            if "Rate limited" in str(e) or "429" in str(e):
                logging.warning(f"Rate limit hit at {symbol}. Sleeping for 60 seconds...")
                time.sleep(60)
            else:
                logging.error(f"[{i+1}/{len(pending_stocks)}] Failed to fetch info for {symbol}: {e}")
                # Mark as Unknown if it completely fails (e.g. delisted)
                update_stock_sector(symbol, "Unknown")
                failed_count += 1
                
        # Sleep to avoid rate limiting
        time.sleep(random.uniform(0.5, 1.5))

    logging.info(f"Finished! Updated: {updated_count}, Failed/Unknown: {failed_count}")

if __name__ == "__main__":
    main()
