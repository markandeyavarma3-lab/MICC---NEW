# marketdb.py - MICC Data Pipeline Query API
# Clean access layer for D:/marketDB (SQLite + Parquet)
# Works from any script in D:/MICC/ or D:/MICC/data_extraction/
#
# Quick usage:
#   from marketdb import MarketDB
#   db = MarketDB()
#   df = db.get_stock("RELIANCE", last_n=252)
#   nifty = db.get_index("NIFTY 50", last_n=60)
#   fii = db.get_fiidii_net("FII", segment="EQ", last_n=30)
#   chain = db.get_options_chain("NIFTY", date="2026-05-09")
#   gex = db.get_gex_net("NIFTY", date="2026-05-09")
#   db.summary()

import sqlite3
from pathlib import Path
from datetime import datetime

import pandas as pd

DB_PATH    = Path(r"D:\\marketDB\\db\\market.db")
STOCKS_DIR = Path(r"D:\\marketDB\\stocks\\all")


class MarketDB:
    def __init__(self, db_path=None, stocks_dir=None):
        self.db_path    = db_path    or DB_PATH
        self.stocks_dir = stocks_dir or STOCKS_DIR

    def _conn(self):
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _table_exists(self, conn, table):
        r = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        return r is not None

    def _parse_dates(self, df, col="date"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
            df = df.dropna(subset=[col]).sort_values(col).reset_index(drop=True)
        return df

    def _read_parquets(self, folder, years=None):
        if not folder.exists():
            return pd.DataFrame()
        files = sorted(folder.glob("*.parquet"))
        if not files:
            return pd.DataFrame()
        if years:
            files = [f for f in files if f.stem.isdigit() and int(f.stem) in years]
        if not files:
            return pd.DataFrame()
        dfs = []
        for f in files:
            try:
                dfs.append(pd.read_parquet(f))
            except Exception:
                pass
        return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()

    def _year_range(self, start, end):
        s = (pd.to_datetime(start) if start else datetime(2000, 1, 1)).year
        e = (pd.to_datetime(end)   if end   else datetime.today()).year
        return list(range(s, e + 1))

    # -- Stocks (Parquet) -----------------------------------------------------
    def get_stock(self, symbol, start=None, end=None, last_n=None):
        symbol = symbol.upper()
        folder = self.stocks_dir / symbol
        if not folder.exists():
            return pd.DataFrame()
        if last_n:
            years = [datetime.today().year - i for i in range(max(1, last_n // 200 + 2))]
        else:
            years = self._year_range(start, end)
        df = self._read_parquets(folder, years)
        if df.empty:
            return df
        df.columns = [c.lower().strip() for c in df.columns]
        for alias in ("timestamp", "date1"):
            if alias in df.columns and "date" not in df.columns:
                df.rename(columns={alias: "date"}, inplace=True)
                break
        for alias in ("close_price", "last_price", "ltp"):
            if alias in df.columns and "close" not in df.columns:
                df.rename(columns={alias: "close"}, inplace=True)
                break
        df = self._parse_dates(df)
        if last_n:
            return df.tail(last_n).reset_index(drop=True)
        if start:
            df = df[df["date"] >= pd.to_datetime(start)]
        if end:
            df = df[df["date"] <= pd.to_datetime(end)]
        return df.reset_index(drop=True)

    def get_close_prices(self, symbols, start=None, end=None, last_n=None):
        frames = {}
        for sym in symbols:
            df = self.get_stock(sym, start=start, end=end, last_n=last_n)
            if not df.empty and "close" in df.columns:
                frames[sym] = df.set_index("date")["close"]
        return pd.DataFrame(frames).sort_index() if frames else pd.DataFrame()

    def get_latest_price(self, symbol):
        df = self.get_stock(symbol, last_n=5)
        return df.iloc[-1].to_dict() if not df.empty else {}

    # -- Indices (SQLite) -----------------------------------------------------
    def list_indices(self):
        conn = self._conn()
        rows = conn.execute("SELECT DISTINCT name FROM indices_data ORDER BY name").fetchall()
        conn.close()
        return [r[0] for r in rows]

    def get_index(self, name, start=None, end=None, last_n=None):
        conn = self._conn()
        df = pd.read_sql("SELECT * FROM indices_data WHERE name=? ORDER BY date", conn, params=(name,))
        if df.empty:
            all_names = [r[0] for r in conn.execute("SELECT DISTINCT name FROM indices_data").fetchall()]
            match = next((n for n in all_names if n.lower() == name.lower()), None)
            if match:
                df = pd.read_sql("SELECT * FROM indices_data WHERE name=? ORDER BY date", conn, params=(match,))
        conn.close()
        if df.empty:
            return df
        df = self._parse_dates(df)
        if last_n:
            return df.tail(last_n).reset_index(drop=True)
        if start:
            df = df[df["date"] >= pd.to_datetime(start)]
        if end:
            df = df[df["date"] <= pd.to_datetime(end)]
        return df.reset_index(drop=True)

    # -- FII/DII (SQLite) -----------------------------------------------------
    def get_fiidii(self, start=None, end=None, participant=None, segment=None):
        q, params = "SELECT * FROM fii_dii_data WHERE 1=1", []
        if start:
            q += " AND date >= ?"; params.append(start)
        if end:
            q += " AND date <= ?"; params.append(end)
        if participant:
            q += " AND participant = ?"; params.append(participant)
        if segment:
            q += " AND segment = ?"; params.append(segment)
        q += " ORDER BY date"
        conn = self._conn()
        df = pd.read_sql(q, conn, params=params)
        conn.close()
        return self._parse_dates(df)

    def get_fiidii_net(self, participant="FII", segment="EQ", start=None, end=None, last_n=None):
        df = self.get_fiidii(start=start, end=end, participant=participant, segment=segment)
        if df.empty:
            return df
        df = df[["date", "net_contracts", "net_value"]].reset_index(drop=True)
        if last_n:
            df = df.tail(last_n).reset_index(drop=True)
        return df

    def get_fiidii_summary(self, start=None, end=None):
        df = self.get_fiidii(start=start, end=end, segment="EQ")
        if df.empty:
            return df
        pivot = df.pivot_table(index="date", columns="participant", values="net_value", aggfunc="sum").reset_index()
        pivot.columns.name = None
        return pivot

    # -- F&O (SQLite - ALWAYS filter by date, 144M rows) ----------------------
    def get_fo(self, symbol, instrument=None, start=None, end=None, expiry=None, option_typ=None, last_n=None):
        q, params = "SELECT * FROM fo_data WHERE symbol=?", [symbol.upper()]
        if instrument:
            q += " AND instrument=?"; params.append(instrument.upper())
        if start:
            q += " AND date>=?";     params.append(start)
        if end:
            q += " AND date<=?";     params.append(end)
        if expiry:
            q += " AND expiry=?";    params.append(expiry)
        if option_typ:
            q += " AND option_typ=?"; params.append(option_typ.upper())
        q += " ORDER BY date, expiry, strike"
        if last_n:
            q += " LIMIT %d" % int(last_n)
        conn = self._conn()
        df = pd.read_sql(q, conn, params=params)
        conn.close()
        return self._parse_dates(df)

    def get_fo_oi(self, symbol, instrument=None, start=None, end=None):
        df = self.get_fo(symbol=symbol, instrument=instrument, start=start, end=end)
        if df.empty:
            return df
        return df.groupby("date").agg(
            total_oi=("open_int", "sum"),
            total_contracts=("contracts", "sum")
        ).reset_index().sort_values("date").reset_index(drop=True)

    def get_options_chain(self, symbol, date, expiry=None):
        q = ("SELECT strike, option_typ, expiry, open_int, contracts, close, settle_pr "
             "FROM fo_data WHERE symbol=? AND instrument IN ('IDO','OPTIDX','OPTSTK','STO') "
             "AND date=? AND option_typ IN ('CE','PE')")
        params = [symbol.upper(), date]
        if expiry:
            q += " AND expiry=?"; params.append(expiry)
        q += " ORDER BY expiry, strike"
        conn = self._conn()
        df = pd.read_sql(q, conn, params=params)
        conn.close()
        return df

    # -- Greeks + GEX (SQLite) ------------------------------------------------
    def get_greeks(self, symbol, date, expiry=None):
        q = "SELECT * FROM option_greeks_raw WHERE symbol=? AND date=?"
        params = [symbol.upper(), date]
        if expiry:
            q += " AND expiry=?"; params.append(expiry)
        q += " ORDER BY expiry, strike, option_type"
        conn = self._conn()
        df = pd.read_sql(q, conn, params=params)
        conn.close()
        return df

    def get_gex(self, symbol, date):
        conn = self._conn()
        df = pd.read_sql(
            "SELECT strike, option_type, gamma_exposure, open_interest "
            "FROM gamma_exposure_daily WHERE symbol=? AND date=? ORDER BY strike",
            conn, params=(symbol.upper(), date)
        )
        conn.close()
        return df

    def get_gex_net(self, symbol, date):
        df = self.get_gex(symbol, date)
        if df.empty:
            return df
        ce  = df[df["option_type"] == "CE"].set_index("strike")["gamma_exposure"]
        pe  = df[df["option_type"] == "PE"].set_index("strike")["gamma_exposure"]
        net = ce.subtract(pe, fill_value=0).reset_index()
        net.columns = ["strike", "net_gex"]
        return net.sort_values("strike")

    # -- Fundamentals (SQLite) ------------------------------------------------
    def get_fundamentals(self, symbols=None):
        if symbols:
            ph = ",".join("?" * len(symbols))
            q, params = "SELECT * FROM stock_fundamentals WHERE symbol IN (%s)" % ph, [s.upper() for s in symbols]
        else:
            q, params = "SELECT * FROM stock_fundamentals", []
        conn = self._conn()
        df = pd.read_sql(q, conn, params=params)
        conn.close()
        return df

    # -- Delivery % (SQLite) --------------------------------------------------
    def get_delivery(self, symbol=None, start=None, end=None, last_n=None):
        q, params = "SELECT * FROM stock_delivery WHERE 1=1", []
        if symbol:
            q += " AND symbol=?"; params.append(symbol.upper())
        if start:
            q += " AND date>=?";  params.append(start)
        if end:
            q += " AND date<=?";  params.append(end)
        q += " ORDER BY date"
        if last_n and symbol:
            q += " LIMIT %d" % int(last_n)
        conn = self._conn()
        df = pd.read_sql(q, conn, params=params)
        conn.close()
        return self._parse_dates(df)

    # -- Global Macro (SQLite) ------------------------------------------------
    def get_global(self, ticker, start=None, end=None, last_n=None):
        q, params = "SELECT * FROM global_data WHERE ticker=?", [ticker]
        if start:
            q += " AND date>=?"; params.append(start)
        if end:
            q += " AND date<=?"; params.append(end)
        q += " ORDER BY date"
        conn = self._conn()
        df = pd.read_sql(q, conn, params=params)
        conn.close()
        df = self._parse_dates(df)
        if last_n:
            return df.tail(last_n).reset_index(drop=True)
        return df

    def list_global_tickers(self):
        conn = self._conn()
        rows = conn.execute("SELECT DISTINCT ticker FROM global_data ORDER BY ticker").fetchall()
        conn.close()
        return [r[0] for r in rows]

    # -- US Macro (SQLite) ----------------------------------------------------
    def get_us_macro(self, series_id, last_n=None):
        conn = self._conn()
        df = pd.read_sql(
            "SELECT date, value, frequency FROM us_macro_data WHERE series_id=? ORDER BY date",
            conn, params=(series_id,)
        )
        conn.close()
        df = self._parse_dates(df)
        if last_n:
            return df.tail(last_n).reset_index(drop=True)
        return df

    def list_us_macro_series(self):
        conn = self._conn()
        rows = conn.execute("SELECT DISTINCT series_id FROM us_macro_data ORDER BY series_id").fetchall()
        conn.close()
        return [r[0] for r in rows]

    # -- India Macro (SQLite) -------------------------------------------------
    def get_india_macro_fred(self, series_id, last_n=None):
        conn = self._conn()
        df = pd.read_sql(
            "SELECT date, value, frequency FROM india_macro_fred WHERE series_id=? ORDER BY date",
            conn, params=(series_id,)
        )
        conn.close()
        df = self._parse_dates(df)
        if last_n:
            return df.tail(last_n).reset_index(drop=True)
        return df

    def get_world_bank(self, indicator_code):
        conn = self._conn()
        df = pd.read_sql(
            "SELECT date, value, indicator_name FROM world_bank_macro WHERE indicator_code=? ORDER BY date",
            conn, params=(indicator_code,)
        )
        conn.close()
        return self._parse_dates(df)

    # -- MF NAV (SQLite) ------------------------------------------------------
    def get_mf_nav(self, scheme_code=None, last_n=None):
        if scheme_code:
            q      = "SELECT * FROM mf_nav_history WHERE scheme_code=? ORDER BY date"
            params = (scheme_code,)
        else:
            q      = ("SELECT * FROM mf_nav_history "
                      "WHERE date=(SELECT MAX(date) FROM mf_nav_history) ORDER BY scheme_name")
            params = ()
        conn = self._conn()
        df = pd.read_sql(q, conn, params=params)
        conn.close()
        df = self._parse_dates(df)
        if last_n and scheme_code:
            return df.tail(last_n).reset_index(drop=True)
        return df

    # -- Corporate Events (SQLite) --------------------------------------------
    def get_corporate_actions(self, symbols=None, start=None, end=None, action_type=None):
        q, params = "SELECT * FROM corporate_actions WHERE 1=1", []
        if symbols:
            ph = ",".join("?" * len(symbols))
            q += " AND symbol IN (%s)" % ph
            params.extend([s.upper() for s in symbols])
        if start:
            q += " AND date>=?"; params.append(start)
        if end:
            q += " AND date<=?"; params.append(end)
        if action_type:
            q += " AND action_type=?"; params.append(action_type.upper())
        q += " ORDER BY date DESC"
        conn = self._conn()
        df = pd.read_sql(q, conn, params=params)
        conn.close()
        return self._parse_dates(df)

    def get_insider_trading(self, symbols=None, start=None, end=None):
        q, params = "SELECT * FROM insider_trading WHERE 1=1", []
        if symbols:
            ph = ",".join("?" * len(symbols))
            q += " AND symbol IN (%s)" % ph
            params.extend([s.upper() for s in symbols])
        if start:
            q += " AND filing_date>=?"; params.append(start)
        if end:
            q += " AND filing_date<=?"; params.append(end)
        q += " ORDER BY filing_date DESC"
        conn = self._conn()
        df = pd.read_sql(q, conn, params=params)
        conn.close()
        return df

    # -- Registry & Search (SQLite) -------------------------------------------
    def list_tradable(self):
        conn = self._conn()
        rows = conn.execute("SELECT symbol FROM tradable_eq_stocks ORDER BY symbol").fetchall()
        conn.close()
        return [r[0] for r in rows]

    def search_symbol(self, query):
        q = query.upper()
        conn = self._conn()
        df = pd.read_sql(
            "SELECT symbol, company_name, is_active FROM stock_registry "
            "WHERE UPPER(symbol) LIKE ? OR UPPER(company_name) LIKE ? ORDER BY is_active DESC, symbol",
            conn, params=("%" + q + "%", "%" + q + "%")
        )
        conn.close()
        return df

    # -- Health Summary --------------------------------------------------------
    def summary(self):
        conn = self._conn()

        def rc(table):
            if not self._table_exists(conn, table):
                return "MISSING"
            n = conn.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
            return "%s rows" % format(n, ",")

        def md(table, col="date"):
            if not self._table_exists(conn, table):
                return "N/A"
            r = conn.execute("SELECT MAX(%s) FROM %s" % (col, table)).fetchone()[0]
            return r or "N/A"

        stock_dirs = sum(1 for d in self.stocks_dir.iterdir() if d.is_dir() and any(d.glob("*.parquet")))                      if self.stocks_dir.exists() else 0

        print("=" * 60)
        print("  MarketDB Summary")
        print("=" * 60)
        print("  Parquet symbols     : %s" % format(stock_dirs, ","))
        print("  indices_data        : %-20s latest: %s" % (rc("indices_data"),        md("indices_data")))
        print("  fo_data             : %-20s latest: %s" % (rc("fo_data"),             md("fo_data")))
        print("  fii_dii_data        : %-20s latest: %s" % (rc("fii_dii_data"),        md("fii_dii_data")))
        print("  stock_delivery      : %-20s latest: %s" % (rc("stock_delivery"),      md("stock_delivery")))
        print("  global_data         : %-20s latest: %s" % (rc("global_data"),         md("global_data")))
        print("  option_greeks_raw   : %-20s latest: %s" % (rc("option_greeks_raw"),   md("option_greeks_raw")))
        print("  gamma_exposure_daily: %-20s latest: %s" % (rc("gamma_exposure_daily"),md("gamma_exposure_daily")))
        print("  us_macro_data       : %-20s latest: %s" % (rc("us_macro_data"),       md("us_macro_data")))
        print("  stock_fundamentals  : %-20s latest: %s" % (rc("stock_fundamentals"),  md("stock_fundamentals","last_updated")))
        print("  mf_nav_history      : %-20s latest: %s" % (rc("mf_nav_history"),      md("mf_nav_history")))
        print("  insider_trading     : %-20s latest: %s" % (rc("insider_trading"),     md("insider_trading","filing_date")))
        print("  tradable_eq_stocks  : %s" % rc("tradable_eq_stocks"))
        print("=" * 60)
        conn.close()


if __name__ == "__main__":
    db = MarketDB()
    db.summary()
    print()
    print("get_stock RELIANCE last 3:")
    print(db.get_stock("RELIANCE", last_n=3))
    print()
    print("get_index NIFTY 50 last 3:")
    print(db.get_index("NIFTY 50", last_n=3))
    print()
    print("get_fiidii_net FII EQ last 5:")
    print(db.get_fiidii_net("FII", segment="EQ", last_n=5))
