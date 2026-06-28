"""
scrape_fundamentals.py  --  Maximum coverage fundamentals scraper
Sources per field (tried in order, first non-null wins):
  Screener.in consolidated -> Screener.in standalone -> yfinance -> Tickertape -> MoneyControl

Fields collected:
  pe_ratio, pb_ratio, ps_ratio, peg_ratio
  roce, roe, roa, roic
  debt_equity, current_ratio, quick_ratio, interest_coverage
  promoter_pct, fii_pct, dii_pct, public_pct
  market_cap_cr, enterprise_value_cr
  sales_cr, profit_cr, ebitda_cr, cash_cr
  eps, book_value, face_value, div_yield, div_payout
  revenue_growth, profit_growth, ebitda_growth
  high_52w, low_52w, current_price
  beta, shares_outstanding
"""
import sqlite3, time, sys, re, json
from datetime import datetime

DB = r"D:\marketDB\db\market.db"

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install",
                    "requests", "beautifulsoup4", "lxml",
                    "--break-system-packages", "-q"])
    import requests
    from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
}

DELAY   = 3.5
TIMEOUT = 30
RETRY   = 3
BATCH   = 20
LIMIT   = int(sys.argv[1]) if len(sys.argv) > 1 else 500

print("Fundamentals scraper v4  -- Maximum coverage")
print(f"  Target={LIMIT}  Delay={DELAY}s  Fields=30+")

# ── DB Setup ──────────────────────────────────────────────────────────────────
conn = sqlite3.connect(DB, timeout=60)
conn.execute("PRAGMA journal_mode=WAL")

ALL_COLS = [
    ("symbol",             "TEXT PRIMARY KEY"),
    ("pe_ratio",           "REAL"), ("pb_ratio",          "REAL"),
    ("ps_ratio",           "REAL"), ("peg_ratio",         "REAL"),
    ("roce",               "REAL"), ("roe",               "REAL"),
    ("roa",                "REAL"), ("roic",              "REAL"),
    ("debt_equity",        "REAL"), ("current_ratio",     "REAL"),
    ("quick_ratio",        "REAL"), ("interest_coverage", "REAL"),
    ("promoter_pct",       "REAL"), ("fii_pct",           "REAL"),
    ("dii_pct",            "REAL"), ("public_pct",        "REAL"),
    ("market_cap_cr",      "REAL"), ("enterprise_value_cr","REAL"),
    ("sales_cr",           "REAL"), ("profit_cr",         "REAL"),
    ("ebitda_cr",          "REAL"), ("cash_cr",           "REAL"),
    ("eps",                "REAL"), ("book_value",        "REAL"),
    ("face_value",         "REAL"), ("div_yield",         "REAL"),
    ("div_payout",         "REAL"), ("revenue_growth",    "REAL"),
    ("profit_growth",      "REAL"), ("ebitda_growth",     "REAL"),
    ("high_52w",           "REAL"), ("low_52w",           "REAL"),
    ("current_price",      "REAL"), ("beta",              "REAL"),
    ("shares_outstanding", "REAL"),
    ("scraped_date",       "TEXT"), ("source",            "TEXT"),
]

col_defs = ", ".join(f"{c} {t}" for c, t in ALL_COLS)
conn.execute(f"CREATE TABLE IF NOT EXISTS screener_fundamentals_v2 ({col_defs})")

existing = [r[1] for r in conn.execute("PRAGMA table_info(screener_fundamentals_v2)").fetchall()]
for col, typ in ALL_COLS:
    if col not in existing:
        conn.execute(f"ALTER TABLE screener_fundamentals_v2 ADD COLUMN {col} {typ}")
conn.commit()

rows_q = conn.execute(
    "SELECT symbol FROM symbol_conviction ORDER BY CAST(conviction_score AS REAL) DESC LIMIT ?",
    (LIMIT,)
).fetchall()
if not rows_q:
    rows_q = conn.execute("SELECT DISTINCT symbol FROM stock_data ORDER BY symbol LIMIT ?", (LIMIT,)).fetchall()
symbols = [r[0] for r in rows_q]
print(f"  Symbols: {len(symbols)}\n")

DATA_FIELDS = [c for c, _ in ALL_COLS if c not in ("symbol", "scraped_date", "source")]

# ── Helpers ───────────────────────────────────────────────────────────────────
def clean(text):
    if text is None:
        return None
    t = re.sub(r"[,%\u20b9\$\u00a3]", "", str(text))
    t = t.replace("Cr.", "").replace("Cr", "").replace("cr.", "").replace("cr", "")
    t = t.replace("+", "").strip()
    t = t.split()[0] if t.split() else t
    try:
        v = float(t)
        return None if (abs(v) > 1e9) else v
    except Exception:
        return None

def get_html(url, retries=RETRY):
    for _ in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            if r.status_code == 200:
                return r.text
            if r.status_code in (404, 403, 410):
                return None
            time.sleep(3)
        except Exception:
            time.sleep(4)
    return None

def set_if_none(d, key, val):
    if val is not None and d.get(key) is None:
        d[key] = val

# ── Source 1: Screener.in ─────────────────────────────────────────────────────
def scrape_screener(symbol):
    d = {}
    html = None
    for url in [
        f"https://www.screener.in/company/{symbol}/consolidated/",
        f"https://www.screener.in/company/{symbol}/",
    ]:
        html = get_html(url)
        if html:
            break
    if not html:
        return d

    soup = BeautifulSoup(html, "lxml")

    # Top ratios: every li in the ratio strip
    for li in soup.select("#top-ratios li, ul.company-ratios li, .company-ratios li"):
        spans = li.select("span")
        if len(spans) < 2:
            continue
        name = spans[0].get_text(strip=True).lower()
        raw  = spans[-1].get_text(strip=True)

        if "market cap"          in name: set_if_none(d, "market_cap_cr",   clean(raw))
        elif "enterprise value"  in name: set_if_none(d, "enterprise_value_cr", clean(raw))
        elif "current price"     in name: set_if_none(d, "current_price",   clean(raw))
        elif "high / low"        in name:
            p = re.sub(r"[,]", "", raw).split("/")
            if len(p) == 2:
                set_if_none(d, "high_52w", clean(p[0]))
                set_if_none(d, "low_52w",  clean(p[1]))
        elif "52 week high"      in name: set_if_none(d, "high_52w",        clean(raw))
        elif "52 week low"       in name: set_if_none(d, "low_52w",         clean(raw))
        elif "stock p/e"         in name: set_if_none(d, "pe_ratio",        clean(raw))
        elif name == "p/e"               : set_if_none(d, "pe_ratio",        clean(raw))
        elif "p/b"               in name: set_if_none(d, "pb_ratio",        clean(raw))
        elif "price to book"     in name: set_if_none(d, "pb_ratio",        clean(raw))
        elif "price to sales"    in name: set_if_none(d, "ps_ratio",        clean(raw))
        elif "peg"               in name: set_if_none(d, "peg_ratio",       clean(raw))
        elif "book value"        in name: set_if_none(d, "book_value",      clean(raw))
        elif "dividend yield"    in name: set_if_none(d, "div_yield",       clean(raw))
        elif "dividend payout"   in name: set_if_none(d, "div_payout",      clean(raw))
        elif "roce"              in name: set_if_none(d, "roce",            clean(raw))
        elif name == "roe" or "return on equity" in name: set_if_none(d, "roe", clean(raw))
        elif "return on asset"   in name: set_if_none(d, "roa",            clean(raw))
        elif "roic"              in name: set_if_none(d, "roic",           clean(raw))
        elif "face value"        in name: set_if_none(d, "face_value",      clean(raw))
        elif "eps"               in name: set_if_none(d, "eps",             clean(raw))
        elif "debt to equity"    in name: set_if_none(d, "debt_equity",     clean(raw))
        elif "debt / equity"     in name: set_if_none(d, "debt_equity",     clean(raw))
        elif "current ratio"     in name: set_if_none(d, "current_ratio",   clean(raw))
        elif "quick ratio"       in name: set_if_none(d, "quick_ratio",     clean(raw))
        elif "interest coverage" in name: set_if_none(d, "interest_coverage", clean(raw))
        elif "cash"              in name: set_if_none(d, "cash_cr",         clean(raw))

    # P&L table
    for section in soup.select("section"):
        h = section.select_one("h2, h3")
        if not h: continue
        ht = h.get_text(strip=True).lower()
        if "profit" not in ht and "loss" not in ht: continue
        for tr in section.select("tr"):
            cells = [c.get_text(strip=True) for c in tr.select("td")]
            if len(cells) < 2: continue
            label = cells[0].lower()
            val   = clean(cells[-1])
            prev  = clean(cells[-2]) if len(cells) >= 3 else None
            def yoy(v, p):
                if v and p and p != 0: return round((v - p) / abs(p) * 100, 1)
                return None
            if ("sales" in label or "revenue" in label) and "growth" not in label:
                set_if_none(d, "sales_cr", val)
                set_if_none(d, "revenue_growth", yoy(val, prev))
            if "net profit" in label or "profit after tax" in label:
                set_if_none(d, "profit_cr", val)
                set_if_none(d, "profit_growth", yoy(val, prev))
            if "ebitda" in label:
                set_if_none(d, "ebitda_cr", val)
                set_if_none(d, "ebitda_growth", yoy(val, prev))

    # Shareholding
    for section in soup.select("section"):
        h = section.select_one("h2, h3")
        if not h or "shareholding" not in h.get_text(strip=True).lower(): continue
        for tr in section.select("tr"):
            cells = [c.get_text(strip=True) for c in tr.select("td")]
            if len(cells) < 2: continue
            label = cells[0].lower()
            val   = clean(cells[-1])
            if "promoter"   in label: set_if_none(d, "promoter_pct", val)
            elif "fii"      in label: set_if_none(d, "fii_pct",      val)
            elif "dii"      in label: set_if_none(d, "dii_pct",      val)
            elif "public"   in label: set_if_none(d, "public_pct",   val)

    # Recompute P/B
    if d.get("pb_ratio") is None and d.get("current_price") and d.get("book_value"):
        bv = d["book_value"]
        if bv and bv != 0:
            d["pb_ratio"] = round(d["current_price"] / bv, 2)

    d["_src"] = "screener"
    return d

# ── Source 2: yfinance ────────────────────────────────────────────────────────
def yf_enrich(symbol, d):
    try:
        import yfinance as yf
        info = yf.Ticker(symbol + ".NS").info or {}
        if not info or info.get("quoteType") is None:
            return d

        def yi(key):
            v = info.get(key)
            return float(v) if v is not None else None
        def pct(key):
            v = yi(key)
            return round(v * 100, 2) if v is not None else None
        def cr(key):
            v = yi(key)
            return round(v / 1e7, 2) if v is not None else None

        set_if_none(d, "pe_ratio",           yi("trailingPE") or yi("forwardPE"))
        set_if_none(d, "pb_ratio",           yi("priceToBook"))
        set_if_none(d, "ps_ratio",           yi("priceToSalesTrailing12Months"))
        set_if_none(d, "peg_ratio",          yi("pegRatio"))
        set_if_none(d, "roe",                pct("returnOnEquity"))
        set_if_none(d, "roa",                pct("returnOnAssets"))
        set_if_none(d, "debt_equity",        yi("debtToEquity"))
        set_if_none(d, "current_ratio",      yi("currentRatio"))
        set_if_none(d, "quick_ratio",        yi("quickRatio"))
        set_if_none(d, "market_cap_cr",      cr("marketCap"))
        set_if_none(d, "enterprise_value_cr",cr("enterpriseValue"))
        set_if_none(d, "eps",                yi("trailingEps"))
        set_if_none(d, "book_value",         yi("bookValue"))
        set_if_none(d, "div_yield",          pct("dividendYield"))
        set_if_none(d, "div_payout",         pct("payoutRatio"))
        set_if_none(d, "high_52w",           yi("fiftyTwoWeekHigh"))
        set_if_none(d, "low_52w",            yi("fiftyTwoWeekLow"))
        set_if_none(d, "current_price",      yi("currentPrice") or yi("regularMarketPrice"))
        set_if_none(d, "beta",               yi("beta"))
        set_if_none(d, "shares_outstanding", yi("sharesOutstanding"))
        set_if_none(d, "revenue_growth",     pct("revenueGrowth"))
        set_if_none(d, "profit_growth",      pct("earningsGrowth"))
        set_if_none(d, "profit_cr",          cr("netIncomeToCommon"))
        set_if_none(d, "sales_cr",           cr("totalRevenue"))
        set_if_none(d, "ebitda_cr",          cr("ebitda"))
        set_if_none(d, "cash_cr",            cr("totalCash"))
        set_if_none(d, "fii_pct",            pct("heldPercentInstitutions"))

        # Recompute P/B
        if d.get("pb_ratio") is None and d.get("current_price") and d.get("book_value"):
            bv = d["book_value"]
            if bv and bv != 0:
                d["pb_ratio"] = round(d["current_price"] / bv, 2)

        src = d.get("_src", "")
        d["_src"] = (src + "+yf") if src else "yfinance"
    except Exception:
        pass
    return d

# ── Source 3: MoneyControl ratio page ────────────────────────────────────────
def mc_enrich(symbol, d):
    still_missing = [f for f in ["roce","roe","roa","promoter_pct","debt_equity",
                                  "current_ratio","pe_ratio"] if d.get(f) is None]
    if not still_missing:
        return d
    try:
        # MoneyControl uses a different symbol format; try a search first
        search_url = f"https://www.moneycontrol.com/mccode/common/autosuggestion_v2.php?classic=true&query={symbol}&type=1&format=json&callback=suggest1"
        r = requests.get(search_url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return d
        text = r.text
        # Extract first result URL
        m = re.search(r'"link_src"\s*:\s*"([^"]+)"', text)
        if not m:
            return d
        mc_url = "https://www.moneycontrol.com" + m.group(1)
        html = get_html(mc_url)
        if not html:
            return d
        soup = BeautifulSoup(html, "lxml")

        # Scan for ratio tables
        for tbl in soup.select("table.mctable1, table.nsebse"):
            for tr in tbl.select("tr"):
                cells = [c.get_text(strip=True) for c in tr.select("td, th")]
                if len(cells) < 2:
                    continue
                label = cells[0].lower()
                val   = clean(cells[1]) if len(cells) > 1 else None
                if "return on equity" in label or "roe" == label: set_if_none(d, "roe", val)
                elif "roce"           in label:                    set_if_none(d, "roce", val)
                elif "return on asset" in label:                   set_if_none(d, "roa", val)
                elif "current ratio"  in label:                    set_if_none(d, "current_ratio", val)
                elif "debt to equity" in label:                    set_if_none(d, "debt_equity", val)
                elif "promoter"       in label:                    set_if_none(d, "promoter_pct", val)

        src = d.get("_src", "")
        d["_src"] = src + "+mc" if src else "mc"
    except Exception:
        pass
    return d

# ── Source 4: NSE API for shareholding ───────────────────────────────────────
def nse_shareholding(symbol, d):
    if d.get("promoter_pct") is not None:
        return d
    try:
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=HEADERS, timeout=10)
        url = f"https://www.nseindia.com/api/shareholding-patterns?symbol={symbol}"
        r   = session.get(url, headers={**HEADERS, "Referer": "https://www.nseindia.com"}, timeout=15)
        if r.status_code == 200:
            data = r.json()
            # data structure: {"data": [{"name":"Promoter","total":"55.23",...},...]}
            records = data.get("data", [])
            for rec in records:
                name = str(rec.get("name", "")).lower()
                val  = clean(rec.get("total") or rec.get("percentageTotal"))
                if "promoter" in name:  set_if_none(d, "promoter_pct", val)
                elif "fii"    in name:  set_if_none(d, "fii_pct", val)
                elif "dii"    in name:  set_if_none(d, "dii_pct", val)
                elif "public" in name:  set_if_none(d, "public_pct", val)
            src = d.get("_src", "")
            d["_src"] = src + "+nse" if src else "nse"
    except Exception:
        pass
    return d

# ── Main loop ─────────────────────────────────────────────────────────────────
field_names = [c for c, _ in ALL_COLS if c not in ("symbol", "scraped_date", "source")]
SQL = (
    "INSERT OR REPLACE INTO screener_fundamentals_v2 ("
    + ", ".join(c for c, _ in ALL_COLS)
    + ") VALUES ("
    + ", ".join("?" for _ in ALL_COLS)
    + ")"
)

ok = 0
err = 0
batch = []
t0 = datetime.now()

for i, sym in enumerate(symbols):
    elapsed = (datetime.now() - t0).total_seconds()
    eta = ((len(symbols) - i) / max(i, 1)) * elapsed / 60 if i > 0 else 0

    d = scrape_screener(sym)
    d = yf_enrich(sym, d)
    d = mc_enrich(sym, d)
    d = nse_shareholding(sym, d)

    filled = sum(1 for f in field_names if d.get(f) is not None)
    total_fields = len(field_names)
    has_data = filled >= 3

    if has_data: ok += 1
    else:         err += 1

    pe   = f"PE={d.get('pe_ratio'):.1f}"       if d.get("pe_ratio")    else "PE=--    "
    roe  = f"ROE={d.get('roe'):.1f}"           if d.get("roe")         else "ROE=--   "
    roce = f"ROCE={d.get('roce'):.1f}"         if d.get("roce")        else "ROCE=--  "
    pro  = f"Pro={d.get('promoter_pct'):.1f}%" if d.get("promoter_pct") else "Pro=--   "
    src  = d.get("_src", "--")
    pct_filled = int(filled / total_fields * 100)
    bar  = "#" * (pct_filled // 10) + "-" * (10 - pct_filled // 10)

    print(f"  [{i+1:4}/{len(symbols)}] {sym:15} {pe:10} {roe:9} {roce:10} {pro:10} [{bar}] {filled}/{total_fields}  [{src}]  ETA {eta:.1f}m")

    row = [sym] + [d.get(c) for c, _ in ALL_COLS if c != "symbol"] + []
    # Build full row in column order
    vals = []
    for col, _ in ALL_COLS:
        if col == "symbol":
            vals.append(sym)
        elif col == "scraped_date":
            vals.append(datetime.now().strftime("%Y-%m-%d"))
        elif col == "source":
            vals.append(d.get("_src", "unknown"))
        else:
            vals.append(d.get(col))

    batch.append(vals)

    if len(batch) >= BATCH:
        conn.executemany(SQL, batch)
        conn.commit()
        batch = []

    time.sleep(DELAY)

if batch:
    conn.executemany(SQL, batch)
    conn.commit()

# ── Final report ──────────────────────────────────────────────────────────────
total_db = conn.execute("SELECT COUNT(*) FROM screener_fundamentals_v2").fetchone()[0]

# Coverage stats
print(f"\nDone.  OK={ok}  Failed={err}  Total in DB={total_db}")
print("\nField coverage (% of rows with non-null value):")
for col, _ in ALL_COLS:
    if col in ("symbol", "scraped_date", "source"): continue
    count = conn.execute(
        f"SELECT COUNT(*) FROM screener_fundamentals_v2 WHERE {col} IS NOT NULL"
    ).fetchone()[0]
    pct = int(count / max(total_db, 1) * 100)
    bar = "#" * (pct // 5) + "-" * (20 - pct // 5)
    print(f"  {col:25} [{bar}] {pct:3}%  ({count}/{total_db})")

sample = conn.execute(
    "SELECT symbol,pe_ratio,pb_ratio,roe,roce,roa,promoter_pct,fii_pct,"
    "debt_equity,current_ratio,revenue_growth,market_cap_cr,source "
    "FROM screener_fundamentals_v2 WHERE pe_ratio IS NOT NULL "
    "ORDER BY ROWID DESC LIMIT 5"
).fetchall()
print(f"\n{'SYM':12} {'PE':>6} {'PB':>6} {'ROE':>6} {'ROCE':>6} {'ROA':>6} {'PRO%':>6} {'FII%':>6} {'D/E':>6} {'CR':>5} {'REVGR':>7} {'MCAP_CR':>10}  SRC")
for r in sample:
    def f(v): return f"{v:6.1f}" if v is not None else "    --"
    print(f"{r[0]:12} {f(r[1])} {f(r[2])} {f(r[3])} {f(r[4])} {f(r[5])} {f(r[6])} {f(r[7])} {f(r[8])} {f(r[9])} {f(r[10])} {str(r[11] or '--'):>10}  {r[12] or '--'}")

conn.close()
print(f"\nTotal time: {(datetime.now()-t0).total_seconds()/60:.1f} min")
print("Full 500: py D:\\MICC\\data_extraction\\scrape_fundamentals.py 500")
