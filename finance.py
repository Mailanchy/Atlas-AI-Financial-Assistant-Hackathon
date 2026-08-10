import yfinance as yf
import finnhub
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os

load_dotenv()
finnhub_client = finnhub.Client(api_key=os.getenv("FINNHUB_API_KEY"))

def get_financial_intelligence(ticker_symbol, insight_types=None, start_date=None, end_date=None):
    print(f"\n---> [FINANCE API] get_financial_intelligence triggered for '{ticker_symbol}'")
    
    if insight_types is None:
        insight_types = []
        
    # 1. Get basic price
    print(f"---> [FINANCE API] Fetching yfinance live price for {ticker_symbol}...")
    stock = yf.Ticker(ticker_symbol)
    current_price = stock.fast_info.get('lastPrice', 'N/A')
    print(f"---> [FINANCE API] Live Price for {ticker_symbol}: {current_price}")
    
    financial_data = {
        "ticker": ticker_symbol,
        "live_price": round(current_price, 2) if isinstance(current_price, float) else current_price,
    }
    
    prefs_str = str(insight_types).lower()
    
    # FIX 1: Only fetch data from Yesterday and Today (Daily Briefing)
    if not end_date:
        end_date = datetime.today().strftime('%Y-%m-%d')
    if not start_date:
        start_date = (datetime.today() - timedelta(days=30)).strftime('%Y-%m-%d')
        
    print(f"---> [FINANCE API] Finnhub Date Range set to: {start_date} to {end_date}")
    
    try:
        # 2. FETCH NEWS
        if "news" in prefs_str or not insight_types:
            print(f"---> [FINANCE API] Fetching Finnhub Company News for {ticker_symbol}...")
            raw_news = finnhub_client.company_news(ticker_symbol, _from=start_date, to=end_date)
            print(f"---> [FINANCE API] Found {len(raw_news)} news articles for {ticker_symbol}")
            
            financial_data["recent_news"] = [
                f"Headline: {a['headline']} | Summary: {a['summary']}" for a in raw_news[:3]
            ]
            
        # 3. FETCH EARNINGS
        if "earning" in prefs_str:
            print(f"---> [FINANCE API] Fetching Finnhub Earnings Calendar for {ticker_symbol}...")
            earnings = finnhub_client.earnings_calendar(_from=start_date, to=end_date, symbol=ticker_symbol)
            if earnings.get('earningsCalendar'):
                print(f"---> [FINANCE API] Found {len(earnings['earningsCalendar'])} earnings records.")
                financial_data["recent_earnings_data"] = earnings['earningsCalendar'][:2]
            else:
                print(f"---> [FINANCE API] No earnings records found in this timeframe.")
                financial_data["recent_earnings_data"] = "No earnings released in the last 24 hours."
                
        # 4. FETCH SEC FILINGS
        if "sec" in prefs_str or "filing" in prefs_str:
            print(f"---> [FINANCE API] Fetching Finnhub SEC Filings for {ticker_symbol}...")
            filings = finnhub_client.filings(symbol=ticker_symbol, _from=start_date, to=end_date)
            if filings:
                print(f"---> [FINANCE API] Found {len(filings)} SEC filings.")
                financial_data["recent_sec_filings"] = [
                    f"Form: {f['form']} | Date: {f['filedDate']} | URL: {f['reportUrl']}" for f in filings[:2]
                ]
            else:
                print(f"---> [FINANCE API] No SEC filings found in this timeframe.")
                financial_data["recent_sec_filings"] = "No new SEC filings in the last 24 hours."
                
    except Exception as e:
        print(f"---> [FINANCE ERROR] API Error for {ticker_symbol}: {e}")
        financial_data["error"] = "Some data could not be retrieved."

    print(f"---> [FINANCE API] Completed data fetch for {ticker_symbol}.")
    return financial_data


def get_daily_brief_data(profile):
    print(f"\n---> [FINANCE ROUTER] get_daily_brief_data triggered.")
    
    watchlist = profile.get('watchlist', [])
    sectors = profile.get('sectors', [])
    insight_types = profile.get('insight_types', [])
    start_date = profile.get('start_date')
    end_date = profile.get('end_date')
    
    print(f"---> [FINANCE ROUTER] Extracted Profile Vars - Watchlist: {watchlist} | Insights: {insight_types}")
    
    aggregated_data = {}
    
    if watchlist:
        print(f"---> [FINANCE ROUTER] Watchlist detected. Iterating through tickers...")
        aggregated_data['watchlist_updates'] = []
        for ticker in watchlist:
            # Passing insight_types so the function knows what to fetch
            stock_data = get_financial_intelligence(ticker, insight_types, start_date, end_date)
            aggregated_data['watchlist_updates'].append(stock_data)
            
    if not watchlist or "macro" in str(insight_types).lower():
        print(f"---> [FINANCE ROUTER] Fetching Macro/General Market News...")
        try:
            raw_general = finnhub_client.general_news('general', min_id=0)
            print(f"---> [FINANCE ROUTER] Successfully fetched {len(raw_general)} general news articles.")
            
            # FIX 3 & 4: Passing the summary so the LLM can explain "Why it matters"
            aggregated_data['general_market_news'] = [
                f"Headline: {a['headline']} | Summary: {a['summary']}" for a in raw_general[:3]
            ]
        except Exception as e:
            print(f"---> [FINANCE ERROR] General News Error: {e}")
            
    aggregated_data['user_context'] = {
        "role": profile.get('role', 'Unknown'),
        "insight_types": insight_types
    }
    
    print(f"---> [FINANCE ROUTER] Assembly complete. Returning aggregated data payload.")
    return aggregated_data