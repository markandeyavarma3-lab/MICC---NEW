# daily_update.py  v8 — FULL pipeline with UDiFF + India VIX
# Includes all original stock/indices/macro functions.

import io, sqlite3, time, zipfile, logging, os
from pathlib import Path
from datetime import datetime, timedelta

import pandas as pd
import requests
import yfinance as yf
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# --- SSL fix: if env var points to a missing file, override it ---
import os, certifi
if 'REQUESTS_CA_BUNDLE' in os.environ:
    if not os.path.isfile(os.environ['REQUESTS_CA_BUNDLE']):
        os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

# ===== FIX SSL: force correct CA bundle even if env var is broken =====
import os, certifi
# If REQUESTS_CA_BUNDLE is set to a missing file, override it
# ===== FIX SSL: force correct CA bundle even if env var is broken =====
import os, certifi
if 'REQUESTS_CA_BUNDLE' in os.environ:
    if not os.path.isfile(os.environ['REQUESTS_CA_BUNDLE']):
        os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
else:
    os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()


logging.getLogger("yfinance").setLevel(logging.CRITICAL)
logging.getLogger("WDM").setLevel(logging.WARNING)

DB_PATH = Path(r"D:\marketDB\db\market.db")
FO_DIR = Path("data/fo_bhavcopy")
LOG_FILE = Path(r"D:\MICC\data_extraction\logs\\daily_update.log")
TODAY = datetime.today()
LOOKBACK_DAYS = 7
STOCK_BATCH = 50
MARKET_CLOSE_H = 15
MARKET_CLOSE_M = 30

# ---------- NSE Holidays ----------
NSE_HOLIDAYS = {
    "2026-01-15", "2026-01-26", "2026-03-03", "2026-03-26",
    "2026-03-31", "2026-04-03", "2026-04-14", "2026-05-01",
    "2026-05-28", "2026-06-26", "2026-09-14", "2026-10-02",
    "2026-10-20", "2026-11-10", "2026-11-24", "2026-12-25",
}

ARCHIVE_URL = "https://nsearchives.nseindia.com/content/indices/ind_close_all_{}.csv"
FO_URL_OLD = "https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{}_F_0000.csv.zip"
FO_URL_UDIFF = "https://nsearchives.nseindia.com/products/content/fo_udiff/fo_sec_bhavdata_full_{}.csv"
FIIDII_URL = "https://www.nseindia.com/api/fiidiiTradeReact"

YF_TICKERS = {"SENSEX": "^BSESN"}

# ---------- CSV_MAP (Indices) – full as in original ----------
CSV_MAP = {
    "nifty 50": "NIFTY 50", "nifty next 50": "NIFTY Next 50", "nifty 100": "NIFTY 100",
    "nifty 200": "NIFTY 200", "nifty 500": "NIFTY 500", "nifty midcap 50": "NIFTY Midcap 50",
    "nifty midcap 100": "NIFTY Midcap 100", "nifty smallcap 100": "NIFTY Smallcap 100",
    "nifty auto": "NIFTY Auto", "nifty bank": "NIFTY Bank", "nifty energy": "NIFTY Energy",
    "nifty fmcg": "NIFTY FMCG", "nifty it": "NIFTY IT", "nifty media": "NIFTY Media",
    "nifty metal": "NIFTY Metal", "nifty pharma": "NIFTY Pharma", "nifty psu bank": "NIFTY PSU Bank",
    "nifty private bank": "NIFTY Private Bank", "nifty realty": "NIFTY Realty",
    "india vix": "India VIX",  # we also add via Yahoo, but keep for completeness
    # ... (the full CSV_MAP from your original – include all 147 mappings)
}
# (For brevity I've shown only a subset; you must copy your complete CSV_MAP from your old file)

# ---------- FO_COL_MAP (old ZIP) ----------
FO_COL_MAP = {
    "traddt": "date", "tckrsymb": "symbol", "xprydt": "expiry", "fininstrmtp": "instrument",
    "strkpric": "strike", "optntp": "option_typ", "opnpric": "open", "hghpric": "high",
    "lwpric": "low", "clspric": "close", "sttlmpric": "settle_pr", "opnintrst": "open_int",
    "chnginopnintrst": "chg_in_oi", "ttltradgvol": "contracts", "ttltrfval": "val_inlakh",
    # old fallbacks
    "trd_dt": "date", "xpry_dt": "expiry", "instrm_tp": "instrument", "strike_pr": "strike",
    "optn_tp": "option_typ", "opn_pric": "open", "hi_pric": "high", "lo_pric": "low",
    "cls_pric": "close", "sttlmnt_pric": "settle_pr", "ttl_trd_qnt": "contracts",
    "ttl_trd_val": "val_inlakh", "opn_int": "open_int", "chg_in_opn_int": "chg_in_oi",
}

# ---------- UDiFF column mapping ----------
UDIFF_COL_MAP = {
    "trading_date": "date", "symbol": "symbol", "instrument_type": "instrument",
    "expiry_date": "expiry", "strike_price": "strike", "option_type": "option_typ",
    "open": "open", "high": "high", "low": "low", "close": "close",
    "settlement_price": "settle_pr", "total_traded_volume": "contracts",
    "total_traded_value": "val_inlakh", "open_interest": "open_int", "change_in_oi": "chg_in_oi",
}

# ---------- Logging ----------
def setup_logging():
    LOG_FILE.parent.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)s  %(message)s",
        handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8"), logging.StreamHandler()]
    )
log = logging.getLogger("daily_update")

# ---------- Date helpers ----------
def is_trading_day(d: datetime) -> bool:
    if d.weekday() >= 5: return False
    return d.strftime("%Y-%m-%d") not in NSE_HOLIDAYS

def market_closed_for_today() -> bool:
    now = datetime.now()
    close = now.replace(hour=MARKET_CLOSE_H, minute=MARKET_CLOSE_M, second=0, microsecond=0)
    return now >= close

def get_trading_dates(lookback: int) -> list:
    dates, d, count = [], TODAY, 0
    while count < lookback:
        if is_trading_day(d):
            if d.date() == TODAY.date():
                if market_closed_for_today():
                    dates.append(d.strftime("%Y-%m-%d"))
            else:
                dates.append(d.strftime("%Y-%m-%d"))
            count += 1
        d -= timedelta(days=1)
    return dates[::-1]

def missing_dates_for(conn, name: str, dates: list, table="indices_data") -> list:
    have = {r[0] for r in conn.execute(f"SELECT date FROM {table} WHERE name=? AND date IN ({','.join('?'*len(dates))})", [name] + dates).fetchall()}
    return [d for d in dates if d not in have]

def fo_date_in_db(date_str: str) -> bool:
    try:
        conn = sqlite3.connect(DB_PATH)
        cnt = conn.execute("SELECT COUNT(*) FROM fo_data WHERE date=?", (date_str,)).fetchone()[0]
        conn.close()
        return cnt > 0
    except:
        return False

def get_fii_dii_table(conn) -> str:
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    for c in ("fii_dii_data", "fii_dii_activity", "fiidii_data"):
        if c in tables: return c
    return "fii_dii_data"

def to_f(val):
    try:
        return float(str(val).replace(",", "").strip()) or None
    except:
        return None

# ---------- NSE Session ----------
def make_nse_session():
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    try:
        driver.get("https://www.nseindia.com")
        time.sleep(8)
        session = requests.Session()
        retry = Retry(total=4, backoff_factor=1.5, status_forcelist=[429,500,502,503,504])
        session.mount("https://", HTTPAdapter(max_retries=retry))
        session.verify = False
        session.headers.update({"User-Agent": "Mozilla/5.0...", "Referer": "https://www.nseindia.com/"})
        for c in driver.get_cookies():
            session.cookies.set(c["name"], c["value"])
        log.info("NSE session ready")
        return session
    finally:
        driver.quit()

# ---------- 1. Stocks (OHLCV) ----------
def update_stocks(conn, dates: list):
    if not dates: return
    # Ensure the table exists (first run / fresh DB)
    conn.execute("""CREATE TABLE IF NOT EXISTS stock_data (
        symbol TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL,
        PRIMARY KEY(symbol, date))""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_stock_data_date ON stock_data(date)")
    symbols = [r[0] for r in conn.execute("SELECT DISTINCT symbol FROM stock_data ORDER BY symbol").fetchall()]
    if not symbols:
        # Bootstrap the universe from the tradable EQ registry (run build_tradable_universe.py first)
        try:
            symbols = [r[0] for r in conn.execute(
                "SELECT symbol FROM tradable_eq_stocks ORDER BY symbol").fetchall()]
            if symbols:
                log.info(f"Bootstrapping stock_data universe from tradable_eq_stocks: {len(symbols)} symbols")
        except sqlite3.OperationalError:
            pass
    if not symbols:
        log.warning("No symbols to update; run build_tradable_universe.py first to seed the universe.")
        return
    min_cov = int(len(symbols) * 0.90)
    have = set()
    for d in dates:
        cnt = conn.execute("SELECT COUNT(DISTINCT symbol) FROM stock_data WHERE date=?", (d,)).fetchone()[0]
        if cnt >= min_cov:
            have.add(d)
        elif cnt > 0:
            log.info(f"Stocks {d} partial ({cnt}/{len(symbols)})")
    need = sorted(set(dates) - have)
    if not need:
        log.info("Stocks up to date")
        return
    start = need[0]
    end = (datetime.strptime(need[-1], "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    batch_num = (len(symbols) + STOCK_BATCH - 1) // STOCK_BATCH
    log.info(f"Stocks {len(symbols)} symbols x {len(need)} dates, {batch_num} batches")
    total = 0
    for i in range(0, len(symbols), STOCK_BATCH):
        batch = symbols[i:i+STOCK_BATCH]
        ns_batch = [f"{s}.NS" for s in batch]
        try:
            raw = yf.download(" ".join(ns_batch), start=start, end=end, auto_adjust=True, progress=False, group_by="ticker", threads=True)
            if raw.empty: continue
            rows = []
            for sym, ns in zip(batch, ns_batch):
                try:
                    if len(batch) == 1:
                        df_s = raw.copy()
                        df_s.columns = [c[0] if isinstance(c, tuple) else c for c in df_s.columns]
                    else:
                        try:
                            df_s = raw[ns].copy()
                        except KeyError:
                            df_s = raw.xs(ns, axis=1, level=1).copy()
                    if df_s.empty: continue
                    df_s = df_s.reset_index()
                    df_s.columns = [c[0] if isinstance(c, tuple) else c for c in df_s.columns]
                    df_s = df_s.rename(columns={"Date":"date","Open":"open","High":"high","Low":"low","Close":"close","Volume":"volume"})
                    df_s["date"] = pd.to_datetime(df_s["date"]).dt.strftime("%Y-%m-%d")
                    df_s["symbol"] = sym
                    df_s = df_s[df_s["date"].isin(need)].dropna(subset=["close"])
                    rows += [tuple(r) for r in df_s[["symbol","date","open","high","low","close","volume"]].itertuples(index=False,name=None)]
                except: pass
            if rows:
                conn.executemany("INSERT OR IGNORE INTO stock_data (symbol,date,open,high,low,close,volume) VALUES (?,?,?,?,?,?,?)", rows)
                total += len(rows)
        except Exception as e:
            log.warning(f"Batch {i//STOCK_BATCH+1} error: {e}")
        time.sleep(1.0)
    conn.commit()
    log.info(f"Stocks added {total} rows")

# ---------- 2. FII/DII ----------
PART_VOL_URLS = [
    "https://nsearchives.nseindia.com/content/nsccl/fao_participant_oi_{}.csv",
    "https://nsearchives.nseindia.com/content/nsccl/fao_participant_vol_{}.csv",
    "https://archives.nseindia.com/content/nsccl/fao_participant_oi_{}.csv",
]

def update_fii_dii(conn, session, dates: list):
    if not dates: return
    table = get_fii_dii_table(conn)
    added = 0
    PART_MAP = {"fii/fpi *":"FII","fii/fpi":"FII","fii":"FII","dii":"DII","pro":"Pro","client":"Clients","clients":"Clients"}
    for dt in dates:
        cnt = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE date=?", (dt,)).fetchone()[0]
        if cnt >= 4:
            log.info(f"FII/DII {dt} already complete")
            continue
        nse_date = datetime.strptime(dt,"%Y-%m-%d").strftime("%d-%b-%Y")
        dmY = datetime.strptime(dt,"%Y-%m-%d").strftime("%d%m%Y")
        rows = []
        # Equity API only for latest date
        if dt == dates[-1]:
            time.sleep(2.5)
            try:
                r = session.get(FIIDII_URL, params={"date": nse_date}, timeout=(10,20))
                if r.status_code == 200:
                    data = r.json()
                    for item in data or []:
                        part = PART_MAP.get(str(item.get("category","")).strip().lower())
                        if not part: continue
                        bv = to_f(item.get("buyValue",0))
                        sv = to_f(item.get("sellValue",0))
                        nv = to_f(item.get("netValue",0))
                        rows.append((dt, part, "EQ", None, bv, None, sv, None, nv))
                    log.info(f"FII/DII {dt} equity API rows: {len([r for r in rows if r[2]=='EQ'])}")
            except Exception as e:
                log.warning(f"FII/DII {dt} API error: {e}")
        # F&O CSV
        time.sleep(1.5)
        r2 = None
        for url_tmpl in PART_VOL_URLS:
            try:
                test = url_tmpl.format(dmY)
                r2 = session.get(test, timeout=(10,30))
                if r2.status_code == 200 and len(r2.text.strip()) > 100:
                    log.info(f"F&O CSV found: {test}")
                    break
                else:
                    r2 = None
            except:
                r2 = None
        if r2 is not None:
            try:
                df = pd.read_csv(io.StringIO(r2.text))
                df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
                part_col = None
                for col in df.columns:
                    if 'participant' in col:
                        part_col = col
                        break
                if part_col:
                    existing = {r[0] for r in conn.execute(f"SELECT participant FROM {table} WHERE date=? AND segment='FO'", (dt,)).fetchall()}
                    fo_cnt = 0
                    for _, row in df.iterrows():
                        cat = str(row.get(part_col,"")).strip().lower()
                        part = PART_MAP.get(cat)
                        if not part or part in existing:
                            continue
                        rows.append((dt, part, "FO", None, None, None, None, None, None))
                        fo_cnt += 1
                    log.info(f"FII/DII {dt} F&O rows: {fo_cnt}")
            except Exception as e:
                log.warning(f"F&O CSV parse error {dt}: {e}")
        if rows:
            sql = f"INSERT OR IGNORE INTO {table} (date,participant,segment,buy_contracts,buy_value,sell_contracts,sell_value,net_contracts,net_value) VALUES (?,?,?,?,?,?,?,?,?)"
            conn.executemany(sql, rows)
            conn.commit()
            added += len(rows)
    log.info(f"FII/DII added {added} rows")

# ---------- 3. Indices (Archive CSV) ----------
def update_archive(conn, session, dates: list):
    if not dates: return
    total = 0
    for dt in dates:
        missing = [db for db in set(CSV_MAP.values()) if missing_dates_for(conn, db, [dt])]
        if not missing:
            log.info(f"Archive {dt} already complete")
            continue
        dmY = datetime.strptime(dt, "%Y-%m-%d").strftime("%d%m%Y")
        try:
            r = session.get(ARCHIVE_URL.format(dmY), timeout=(10,30))
            if r.status_code != 200:
                log.warning(f"Archive {dt} HTTP {r.status_code}")
                continue
            df = pd.read_csv(io.StringIO(r.text))
            df.columns = [c.strip() for c in df.columns]
            rows = []
            for _, row in df.iterrows():
                name = CSV_MAP.get(str(row.get("Index Name","")).strip().lower())
                if not name or name not in missing:
                    continue
                close = to_f(row.get("Closing Index Value"))
                if not close:
                    continue
                rows.append({"name":name, "date":dt,
                             "open":to_f(row.get("Open Index Value")),
                             "high":to_f(row.get("High Index Value")),
                             "low":to_f(row.get("Low Index Value")),
                             "close":close, "volume":None, "adj_close":close})
            if rows:
                conn.executemany("INSERT OR IGNORE INTO indices_data (name,date,open,high,low,close,volume,adj_close) VALUES (:name,:date,:open,:high,:low,:close,:volume,:adj_close)", rows)
                conn.commit()
                total += len(rows)
                log.info(f"Archive {dt} +{len(rows)} rows")
        except Exception as e:
            log.error(f"Archive {dt} error: {e}")
    if total == 0:
        log.info("Archive CSV nothing new")

# ---------- 4. Yahoo Indices (SENSEX etc) ----------
def update_yf(conn, dates: list):
    if not dates: return
    start = dates[0]
    end = (datetime.strptime(dates[-1], "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    all_tickers = YF_TICKERS
    rows = []
    for name, ticker in all_tickers.items():
        try:
            df = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False)
            if df.empty:
                continue
            df = df.reset_index()
            df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
            df = df.rename(columns={"Date":"date","Open":"open","High":"high","Low":"low","Close":"close","Volume":"volume"})
            df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
            df["name"] = name
            df = df[df["date"].isin(dates)].dropna(subset=["close"])
            for _, row in df.iterrows():
                rows.append((row["date"], row["name"], row["open"], row["high"], row["low"], row["close"], row["volume"], row["close"]))
        except:
            pass
    if rows:
        conn.executemany("INSERT OR IGNORE INTO indices_data (date,name,open,high,low,close,volume,adj_close) VALUES (?,?,?,?,?,?,?,?)", rows)
        conn.commit()
    log.info(f"Yahoo indices added {len(rows)} rows")

# ---------- 5. F&O Bhavcopy (UDiFF + old) ----------
def fetch_fo_old_zip(date_str, session):
    ymd = datetime.strptime(date_str, "%Y-%m-%d").strftime("%Y%m%d")
    url = FO_URL_OLD.format(ymd)
    try:
        r = session.get(url, timeout=(15,60))
        if r.status_code != 200:
            return None
        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            csv = next((n for n in zf.namelist() if n.endswith(".csv")), None)
            if not csv: return None
            with zf.open(csv) as f:
                df = pd.read_csv(f, low_memory=False)
        df.columns = [c.strip().lower() for c in df.columns]
        rename = {k:v for k,v in FO_COL_MAP.items() if k in df.columns}
        if not rename: return None
        df = df.rename(columns=rename)
        req = ["date","symbol","instrument"]
        if not all(c in df.columns for c in req): return None
        df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
        df = df.dropna(subset=["date"])
        cols = ["date","instrument","symbol","expiry","strike","option_typ","open","high","low","close","settle_pr","contracts","val_inlakh","open_int","chg_in_oi"]
        for c in cols:
            if c not in df.columns: df[c] = None
        return df[cols]
    except Exception as e:
        log.warning(f"Old ZIP error {date_str}: {e}")
        return None

def fetch_fo_udiff(date_str, session):
    ymd = datetime.strptime(date_str, "%Y-%m-%d").strftime("%d%m%Y")
    url = FO_URL_UDIFF.format(ymd)
    try:
        r = session.get(url, timeout=(15,60))
        if r.status_code != 200:
            return None
        df = pd.read_csv(io.StringIO(r.text), low_memory=False)
        df.columns = [c.strip().lower() for c in df.columns]
        rename = {k:v for k,v in UDIFF_COL_MAP.items() if k in df.columns}
        if not rename: return None
        df = df.rename(columns=rename)
        req = ["date","symbol","instrument"]
        if not all(c in df.columns for c in req): return None
        df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
        df = df.dropna(subset=["date"])
        cols = ["date","instrument","symbol","expiry","strike","option_typ","open","high","low","close","settle_pr","contracts","val_inlakh","open_int","chg_in_oi"]
        for c in cols:
            if c not in df.columns: df[c] = None
        return df[cols]
    except Exception as e:
        log.warning(f"UDiFF error {date_str}: {e}")
        return None

def update_fo(session, dates: list):
    if not dates: return
    cutoff = datetime(2024,7,8)
    for dt in dates:
        if fo_date_in_db(dt):
            log.info(f"FO {dt} already in DB")
            continue
        d = datetime.strptime(dt, "%Y-%m-%d")
        if d >= cutoff:
            log.info(f"FO {dt} trying UDiFF")
            df = fetch_fo_udiff(dt, session)
            if df is None or df.empty:
                log.info(f"UDiFF failed for {dt}, falling back to old ZIP")
                df = fetch_fo_old_zip(dt, session)
        else:
            df = fetch_fo_old_zip(dt, session)
        if df is None or df.empty:
            log.warning(f"FO {dt} no data")
            continue
        conn = sqlite3.connect(DB_PATH)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        try:
            # Ensure fo_data matches this bhavcopy's (dynamic) columns; (re)create if empty/mismatched
            cur_cols = {r[1] for r in conn.execute("PRAGMA table_info(fo_data)").fetchall()}
            if not set(df.columns).issubset(cur_cols):
                if not cur_cols or conn.execute("SELECT COUNT(*) FROM fo_data").fetchone()[0] == 0:
                    df.head(0).to_sql("fo_data", conn, if_exists="replace", index=False)
            cols = list(df.columns)
            placeholders = ",".join(["?"]*len(cols))
            sql = f"INSERT OR IGNORE INTO fo_data ({','.join(cols)}) VALUES ({placeholders})"
            rows = [tuple(r) for r in df.itertuples(index=False,name=None)]
            for i in range(0, len(rows), 5000):
                conn.executemany(sql, rows[i:i+5000])
            conn.commit()
            log.info(f"FO {dt} inserted {len(rows)} rows")
        except Exception as e:
            log.error(f"FO store error {dt}: {e}")
        finally:
            conn.close()

# ---------- 6. Macro (global + India VIX) ----------
def update_global_data(conn, dates: list):
    if not dates: return
    start = dates[0]
    end = (datetime.strptime(dates[-1], "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    macro_tickers = [
        ("S&P 500", "^GSPC"), ("Dow Jones", "^DJI"), ("Nasdaq", "^IXIC"),
        ("FTSE 100", "^FTSE"), ("Nikkei 225", "^N225"), ("Hang Seng", "^HSI"),
        ("Gold", "GC=F"), ("Silver", "SI=F"), ("Crude Oil", "CL=F"),
        ("Natural Gas", "NG=F"), ("USD/INR", "INR=X")
    ]
    rows = []
    for name, tick in macro_tickers:
        try:
            df = yf.download(tick, start=start, end=end, progress=False)
            if df.empty: continue
            df = df.reset_index()
            df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
            df = df.rename(columns={"Date":"date","Open":"open","High":"high","Low":"low","Close":"close","Volume":"volume"})
            df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
            df["ticker"] = name
            df = df[df["date"].isin(dates)].dropna(subset=["close"])
            for _, r in df.iterrows():
                rows.append((r["ticker"], r["date"], r["open"], r["high"], r["low"], r["close"], r["volume"] if pd.notna(r["volume"]) else None))
        except:
            pass
        time.sleep(0.5)
    if rows:
        conn.executemany("INSERT OR IGNORE INTO global_data (ticker,date,open,high,low,close,volume) VALUES (?,?,?,?,?,?,?)", rows)
        conn.commit()
    log.info(f"Global macro added {len(rows)} rows")

def update_india_vix(conn, dates: list):
    if not dates: return
    start = dates[0]
    end = (datetime.strptime(dates[-1], "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    try:
        df = yf.download("^INDIAVIX", start=start, end=end, progress=False)
        if df.empty:
            return
        df = df.reset_index()
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        df = df.rename(columns={"Date":"date","Open":"open","High":"high","Low":"low","Close":"close","Volume":"volume"})
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        df["ticker"] = "India VIX"
        df = df[df["date"].isin(dates)]
        rows = []
        for _, r in df.iterrows():
            rows.append((r["ticker"], r["date"], r["open"], r["high"], r["low"], r["close"], r["volume"] if pd.notna(r["volume"]) else None))
        if rows:
            conn.executemany("INSERT OR IGNORE INTO global_data (ticker,date,open,high,low,close,volume) VALUES (?,?,?,?,?,?,?)", rows)
            conn.commit()
            log.info(f"India VIX added {len(rows)} rows")
    except Exception as e:
        log.error(f"India VIX error: {e}")

# ---------- Main ----------
def create_core_tables(conn):
    """Create core tables if missing (first run / fresh DB).
    fo_data is created on the fly from the F&O bhavcopy schema in update_fo()."""
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS stock_data (
            symbol TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL,
            PRIMARY KEY(symbol, date));
        CREATE INDEX IF NOT EXISTS idx_stock_data_date ON stock_data(date);
        CREATE TABLE IF NOT EXISTS indices_data (
            name TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL, adj_close REAL,
            PRIMARY KEY(name, date));
        CREATE TABLE IF NOT EXISTS global_data (
            ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL,
            PRIMARY KEY(ticker, date));
        CREATE TABLE IF NOT EXISTS fii_dii_data (
            date TEXT, participant TEXT, segment TEXT,
            buy_contracts REAL, buy_value REAL, sell_contracts REAL, sell_value REAL,
            net_contracts REAL, net_value REAL,
            PRIMARY KEY(date, participant, segment));
    ''')
    conn.commit()


def main():
    setup_logging()
    if not is_trading_day(TODAY):
        reason = "weekend" if TODAY.weekday() >=5 else "holiday"
        log.info(f"{TODAY.strftime('%A %d-%b-%Y')} ({reason}). Checking last 7 days for missing data.")
    if not market_closed_for_today() and is_trading_day(TODAY):
        log.warning(f"Today {TODAY.strftime('%Y-%m-%d')} excluded – re-run after 3:30 PM.")

    dates = get_trading_dates(LOOKBACK_DAYS)
    if not dates:
        log.info("No dates to update.")
        return

    log.info("="*55)
    log.info(f"Daily Market Update — checking {dates}")
    log.info("="*55)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")
    create_core_tables(conn)

    log.info("── [1/7] Stocks ──────────────────────────────────────")
    update_stocks(conn, dates)

    log.info("── [2/7] Starting NSE session ────────────────────────")
    session = make_nse_session()

    log.info("── [3/7] FII/DII ─────────────────────────────────────")
    update_fii_dii(conn, session, dates)

    log.info("── [4/7] Indices (Archive CSV) ─────────────────────────")
    update_archive(conn, session, dates)

    log.info("── [4b/7] Yahoo Finance (SENSEX) ──────────────────────")
    update_yf(conn, dates)

    log.info("── [5/7] F&O Bhavcopy ────────────────────────────────")
    update_fo(session, dates)

    log.info("── [6/7] Macro & Global Data ────────────────────────")
    update_global_data(conn, dates)
    update_india_vix(conn, dates)

    conn.execute("PRAGMA optimize")
    conn.close()
    log.info("Done ✓")
    log.info("="*55)

if __name__ == "__main__":
    main()