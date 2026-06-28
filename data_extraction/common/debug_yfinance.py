# debug_yfinance.py — run this once, paste output
# py D:\MICC\data_extraction\debug_yfinance.py

import yfinance as yf, json

t = yf.Ticker("RELIANCE.NS")
news = t.news or []
print(f"Total items: {len(news)}")
print(f"\nFirst item full dict:")
if news:
    print(json.dumps(news[0], indent=2, default=str))
print(f"\nSecond item keys: {list(news[1].keys()) if len(news)>1 else 'N/A'}")
