-- MICC schema snapshot BEFORE Part 1 (pre-flight, Stage 0)
-- generated 2026-07-01T23:46:03.779303  | 136 objects

CREATE INDEX idx_ca_symbol ON corporate_actions(symbol);
CREATE INDEX idx_corp_date ON corporate_announcements(announcement_date);
CREATE INDEX idx_corp_symbol ON corporate_announcements(symbol);
CREATE INDEX idx_date ON us_macro_data(date);
CREATE INDEX idx_fdd_date ON fii_dii_detailed(date);
CREATE INDEX idx_ff ON fundamentals_features(symbol, pit_date);
CREATE INDEX idx_fm_date ON features_monthly(rebal_date);
CREATE INDEX idx_fm_sym ON features_monthly(symbol);
CREATE INDEX idx_fo_date   ON fo_data(date);
CREATE INDEX idx_fo_inst   ON fo_data(instrument);
CREATE INDEX idx_fo_symbol ON fo_data(symbol);
CREATE INDEX idx_fpit ON fundamentals_pit(symbol, pit_date);
CREATE INDEX idx_gid_date ON global_indices_daily (date);
CREATE INDEX idx_gid_sym ON global_indices_daily (symbol);
CREATE INDEX idx_gid_sym_date ON global_indices_daily (symbol, date);
CREATE INDEX idx_gt_sym ON google_trends(symbol,date);
CREATE INDEX idx_ic_symbol ON index_constituents(symbol);
CREATE INDEX idx_im_isin ON isin_master(isin);
CREATE INDEX idx_im_symbol ON isin_master(symbol);
CREATE INDEX idx_insider_filing_date ON insider_trading(filing_date);
CREATE INDEX idx_insider_symbol ON insider_trading(symbol);
CREATE INDEX idx_mfnav_date ON mf_nav_history(date);
CREATE INDEX idx_news_pub ON news_headlines(published);
CREATE INDEX idx_poi_date ON participant_oi(date);
CREATE INDEX idx_pu_date ON pit_universe(rebal_date);
CREATE INDEX idx_rbi_date ON rbi_monetary_data(date);
CREATE INDEX idx_scorr_sym  ON symbol_correlations  (symbol, benchmark);
CREATE INDEX idx_sda_symdate ON stock_data_adj(symbol,date);
CREATE INDEX idx_series_date ON us_macro_data(series_id, date);
CREATE INDEX idx_sh_quarter ON shareholding_history(quarter);
CREATE INDEX idx_sh_sym ON shareholding_history(symbol);
CREATE INDEX idx_sh_symbol ON shareholding_history(symbol);
CREATE INDEX idx_sseas_sym  ON symbol_seasonality   (symbol);
CREATE INDEX idx_sss_at     ON symbol_series_stats  (asset_type);
CREATE INDEX idx_sss_sym    ON symbol_series_stats  (symbol);
CREATE INDEX idx_stech_sym  ON symbol_technicals    (symbol);
CREATE INDEX idx_stock_data_date ON stock_data(date);
CREATE INDEX idx_tr_symdate ON stock_data_tr(symbol,date);
CREATE INDEX idx_we_sym_dir ON window_extremes (symbol, window_days, direction);
CREATE INDEX idx_we_sym_win ON window_extremes (symbol, window_days);
CREATE INDEX idx_wrs_reg    ON window_regime_stats  (regime, window_days);
CREATE INDEX idx_wrs_sw     ON window_regime_stats  (symbol, window_days);
CREATE INDEX idx_ws_atype ON window_stats (asset_type, window_days);
CREATE INDEX idx_ws_sym_win ON window_stats (symbol, window_days);
CREATE INDEX idx_ws_symbol ON window_stats (symbol);
CREATE TABLE annual_balance (
            symbol TEXT, report_date TEXT, data_json TEXT, last_updated TEXT,
            PRIMARY KEY(symbol, report_date));
CREATE TABLE annual_cashflow (
            symbol TEXT, report_date TEXT, data_json TEXT, last_updated TEXT,
            PRIMARY KEY(symbol, report_date));
CREATE TABLE annual_income (
            symbol TEXT, report_date TEXT, data_json TEXT, last_updated TEXT,
            PRIMARY KEY(symbol, report_date));
CREATE TABLE av_earnings_calendar (
        symbol TEXT, name TEXT, report_date TEXT, fiscal_date_ending TEXT,
        estimate REAL, currency TEXT, time_of_day TEXT, fetched_at TEXT,
        PRIMARY KEY(symbol, report_date, fiscal_date_ending));
CREATE TABLE av_insider_transactions (
        symbol TEXT, transaction_date TEXT, executive TEXT, executive_title TEXT,
        security_type TEXT, acquisition_or_disposal TEXT, shares REAL,
        share_price REAL, fetched_at TEXT,
        PRIMARY KEY(symbol, transaction_date, executive, security_type,
                    acquisition_or_disposal, shares, share_price));
CREATE TABLE av_institutional_holdings (
        symbol TEXT, holder_name TEXT, last_reported TEXT, shares_held INTEGER,
        shares_changed INTEGER, shares_changed_pct TEXT, change_type TEXT,
        fetched_at TEXT, PRIMARY KEY(symbol, holder_name, last_reported));
CREATE TABLE block_deals (
            date TEXT, symbol TEXT, name TEXT, client TEXT, buy_sell TEXT,
            qty REAL, price REAL, remarks TEXT,
            PRIMARY KEY(date, symbol, client, buy_sell, qty));
CREATE TABLE board_meetings (
        symbol TEXT, meeting_date TEXT, purpose TEXT, description TEXT, industry TEXT,
        company TEXT, fetched_at TEXT, PRIMARY KEY(symbol, meeting_date, purpose));
CREATE TABLE bse_stock_registry (
            symbol TEXT PRIMARY KEY,
            company_name TEXT,
            isin TEXT,
            sector TEXT,
            face_value REAL,
            yahoo_symbol TEXT,
            is_active INTEGER DEFAULT 1,
            last_updated TEXT
        );
CREATE TABLE bt_best (date TEXT, ret REAL, equity REAL);
CREATE TABLE bt_equity (strategy TEXT, date TEXT, ret REAL, equity REAL);
CREATE TABLE bt_execution (date TEXT, ret REAL, equity REAL);
CREATE TABLE "bt_holdings" (
"date" TEXT,
  "symbol" TEXT,
  "weight" REAL,
  "strategy" TEXT
);
CREATE TABLE bt_metrics (strategy TEXT, metric TEXT, value REAL);
CREATE TABLE bt_ml_ranker (date TEXT, ret REAL, equity REAL);
CREATE TABLE bt_multifactor (date TEXT, ret REAL, equity REAL);
CREATE TABLE "bt_portfolio_daily" (
"date" TEXT,
  "gross" REAL,
  "net" REAL,
  "net_gated" REAL,
  "turnover" REAL,
  "equity" REAL,
  "strategy" TEXT
);
CREATE TABLE bt_strategy_metrics (strategy TEXT, metric TEXT, value REAL);
CREATE TABLE "bt_trades" (
"date" TEXT,
  "symbol" TEXT,
  "side" TEXT,
  "dweight" REAL,
  "strategy" TEXT
);
CREATE TABLE bulk_deals (
            date TEXT, symbol TEXT, name TEXT, client TEXT, buy_sell TEXT,
            qty REAL, price REAL, remarks TEXT,
            PRIMARY KEY(date, symbol, client, buy_sell, qty));
CREATE TABLE corporate_actions (
        symbol TEXT, date TEXT, action_type TEXT, ratio TEXT, amount REAL, subject TEXT,
        PRIMARY KEY(symbol, date, action_type, subject));
CREATE TABLE corporate_announcements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            announcement_date TEXT NOT NULL,
            symbol TEXT,
            subject TEXT,
            attachment_url TEXT,
            received_date TEXT,
            last_updated TEXT
        );
CREATE TABLE current_signals (
        rebal_date TEXT, rank INTEGER, symbol TEXT, company TEXT, decile INTEGER,
        score REAL, mom_12_1 REAL, prox_52w_high REAL, deliv_1m REAL,
        med_turnover REAL, in_portfolio INTEGER);
CREATE TABLE "deals_intel" (
"category" TEXT,
  "symbol" TEXT,
  "detail" TEXT,
  "value" REAL,
  "window" TEXT
);
CREATE TABLE dim_sector (
        symbol TEXT PRIMARY KEY, sector_raw TEXT, sector TEXT, source TEXT, updated TEXT);
CREATE TABLE eq_bhavcopy_universe (
    symbol TEXT PRIMARY KEY, company_name TEXT, last_seen TEXT);
CREATE TABLE "features_monthly" (
"rebal_date" TEXT,
  "symbol" TEXT,
  "adv_rank" INTEGER,
  "med_turnover" REAL,
  "top500" INTEGER,
  "liquid" INTEGER,
  "ret_1m" REAL,
  "ret_3m" REAL,
  "ret_6m" REAL,
  "ret_12m" REAL,
  "mom_12_1" REAL,
  "mom_6_1" REAL,
  "vol_3m" REAL,
  "vol_6m" REAL,
  "dist_sma50" REAL,
  "dist_sma200" REAL,
  "above_200" INTEGER,
  "prox_52w_high" REAL,
  "amihud" REAL,
  "deliv_1m" REAL,
  "deliv_3m" REAL,
  "deliv_trend" REAL,
  "fwd_ret_1m" REAL,
  "fwd_ret_3m" REAL
);
CREATE TABLE fii_dii_data (
            date TEXT, participant TEXT, segment TEXT,
            buy_contracts REAL, buy_value REAL, sell_contracts REAL, sell_value REAL,
            net_contracts REAL, net_value REAL,
            PRIMARY KEY(date, participant, segment));
CREATE TABLE fii_dii_detailed (
            date TEXT NOT NULL,
            category TEXT NOT NULL,
            segment TEXT,
            buy_value REAL,
            sell_value REAL,
            net_value REAL,
            last_updated TEXT,
            PRIMARY KEY (date, category, segment)
        );
CREATE TABLE financial_results (
        symbol TEXT, period TEXT, broadcast_date TEXT, audited TEXT, consolidated TEXT,
        company TEXT, fetched_at TEXT, PRIMARY KEY(symbol, period, broadcast_date));
CREATE TABLE "fno_intel" (
"category" TEXT,
  "symbol" TEXT,
  "detail" TEXT,
  "value" REAL,
  "asof" TEXT
);
CREATE TABLE fo_ban (date TEXT, symbol TEXT, PRIMARY KEY(date, symbol));
CREATE TABLE "fo_data" (
"date" TEXT,
  "instrument" TEXT,
  "symbol" TEXT,
  "expiry" TEXT,
  "strike" REAL,
  "option_typ" TEXT,
  "open" REAL,
  "high" REAL,
  "low" REAL,
  "close" REAL,
  "settle_pr" REAL,
  "contracts" INTEGER,
  "val_inlakh" REAL,
  "open_int" INTEGER,
  "chg_in_oi" INTEGER
);
CREATE TABLE "fundamentals_features" (
"symbol" TEXT,
  "report_date" TEXT,
  "pit_date" TEXT,
  "eps" REAL,
  "net_income" REAL,
  "revenue" REAL,
  "total_equity" REAL,
  "roe" REAL
);
CREATE TABLE "fundamentals_pit" (
"statement" TEXT,
  "symbol" TEXT,
  "period_type" TEXT,
  "report_date" TEXT,
  "pit_date" TEXT,
  "dated_by" TEXT
);
CREATE TABLE gamma_exposure_daily (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            symbol TEXT NOT NULL,
            expiry TEXT NOT NULL,
            strike REAL,
            option_type TEXT,
            gamma_exposure REAL,
            open_interest INTEGER,
            UNIQUE(date, symbol, expiry, strike, option_type)
        );
CREATE TABLE global_data (
            ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL,
            PRIMARY KEY(ticker, date));
CREATE TABLE global_indices_daily (
            symbol          TEXT    NOT NULL,
            date            TEXT    NOT NULL,   -- YYYY-MM-DD
            open            REAL,
            high            REAL,
            low             REAL,
            close           REAL    NOT NULL,
            volume          REAL,
            pct_change      REAL,               -- daily % change, computed on insert

            PRIMARY KEY (symbol, date)
        );
CREATE TABLE google_trends (
            query TEXT NOT NULL,
            symbol TEXT,
            date TEXT NOT NULL,
            interest_score INTEGER,
            category TEXT,
            geo TEXT,
            last_updated TEXT,
            PRIMARY KEY (query, date)
        );
CREATE TABLE index_constituents (
        index_name TEXT, symbol TEXT, company TEXT, industry TEXT, isin TEXT, updated TEXT,
        PRIMARY KEY(index_name, symbol));
CREATE TABLE index_valuation (
        index_name TEXT, date TEXT, pe REAL, pb REAL, div_yield REAL,
        PRIMARY KEY(index_name, date));
CREATE TABLE india_bond_yields (
            date TEXT PRIMARY KEY,
            yield_10y REAL,
            yield_source TEXT,
            last_updated TEXT
        );
CREATE TABLE india_macro_fred (
            series_id TEXT NOT NULL,
            date TEXT NOT NULL,
            value REAL,
            frequency TEXT,
            last_updated TEXT,
            PRIMARY KEY (series_id, date)
        );
CREATE TABLE indices_data (
            name TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL, adj_close REAL,
            PRIMARY KEY(name, date));
CREATE TABLE insider_trading (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filing_date TEXT NOT NULL,
            symbol TEXT,
            company TEXT,
            name TEXT,
            category TEXT,
            transaction_type TEXT,
            quantity INTEGER,
            price REAL,
            value REAL,
            post_holding INTEGER,
            report_date TEXT,
            last_updated TEXT
        );
CREATE TABLE ipo_data (
        name TEXT PRIMARY KEY, gmp TEXT, rating TEXT, subscription TEXT, price TEXT,
        ipo_size TEXT, lot TEXT, open_date TEXT, close_date TEXT, boa_date TEXT,
        listing TEXT, updated_on TEXT, fetched_at TEXT);
CREATE TABLE isin_master (
        isin TEXT, symbol TEXT, company TEXT, first_date TEXT, last_date TEXT,
        listing_date TEXT, is_active INTEGER, source TEXT,
        PRIMARY KEY(isin, symbol));
CREATE TABLE isin_renames(
  isin TEXT,
  n_symbols,
  symbols
);
CREATE TABLE market_breadth (
        date TEXT PRIMARY KEY, advances INTEGER, declines INTEGER, unchanged INTEGER,
        ad_ratio REAL, new_highs_52w INTEGER, new_lows_52w INTEGER,
        pct_above_50dma REAL, pct_above_200dma REAL, total_traded INTEGER);
CREATE TABLE mf_industry_monthly (
        report_month TEXT, category TEXT, num_schemes REAL, num_folios REAL,
        funds_mobilized REAL, redemption REAL, net_flow REAL, aum REAL, avg_aum REAL,
        PRIMARY KEY(report_month, category));
CREATE TABLE mf_nav_history (
            scheme_code TEXT,
            scheme_name TEXT,
            date TEXT,
            nav REAL,
            PRIMARY KEY (scheme_code, date)
        );
CREATE TABLE mf_scheme_master (
        scheme_code TEXT PRIMARY KEY, scheme_name TEXT, isin TEXT,
        amc TEXT, category TEXT, scheme_type TEXT, updated TEXT);
CREATE TABLE "mf_scorecard" (
"scheme_code" TEXT,
  "scheme_name" TEXT,
  "amc" TEXT,
  "cat_short" TEXT,
  "plan" TEXT,
  "last_date" TEXT,
  "last_nav" REAL,
  "years" REAL,
  "cagr_1y" REAL,
  "cagr_3y" REAL,
  "cagr_5y" REAL,
  "ann_vol" REAL,
  "max_dd" REAL,
  "sharpe_3y" REAL,
  "consistency" REAL,
  "rank_in_cat" REAL
);
CREATE TABLE monitoring_log (
        ts TEXT, check_name TEXT, status TEXT, detail TEXT);
CREATE TABLE news_headlines (
        link TEXT PRIMARY KEY, title TEXT, published TEXT, source TEXT, fetched_at TEXT);
CREATE TABLE oms_orders (
        ts TEXT, asof TEXT, symbol TEXT, side TEXT, qty INTEGER, price REAL,
        notional REAL, status TEXT, reason TEXT);
CREATE TABLE option_greeks_raw (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            symbol TEXT NOT NULL,
            expiry TEXT NOT NULL,
            strike REAL,
            option_type TEXT,
            underlying_price REAL,
            iv REAL,
            delta REAL,
            gamma REAL,
            theta REAL,
            vega REAL,
            rho REAL,
            UNIQUE(date, symbol, expiry, strike, option_type)
        );
CREATE TABLE options_max_pain (
        date TEXT, symbol TEXT, expiry TEXT, max_pain_strike REAL,
        PRIMARY KEY(date, symbol));
CREATE TABLE options_pcr_daily (
        date TEXT, symbol TEXT, call_oi REAL, put_oi REAL, pcr_oi REAL,
        call_vol REAL, put_vol REAL, pcr_vol REAL, total_oi REAL,
        PRIMARY KEY(date, symbol));
CREATE TABLE "paper_nav" (
"strategy" TEXT,
  "date" TEXT,
  "nav" REAL,
  "cash" REAL,
  "invested" REAL
);
CREATE TABLE "paper_positions" (
"strategy" TEXT,
  "date" TEXT,
  "symbol" TEXT,
  "shares" INTEGER,
  "value" REAL
);
CREATE TABLE "paper_trades" (
"strategy" TEXT,
  "date" TEXT,
  "symbol" TEXT,
  "side" TEXT,
  "shares" INTEGER,
  "price" REAL,
  "cost" REAL
);
CREATE TABLE participant_oi (
            date TEXT NOT NULL,
            category TEXT NOT NULL,
            index_fut_long REAL,  index_fut_short REAL,  index_fut_net REAL,
            index_call_long REAL, index_call_short REAL,
            index_put_long REAL,  index_put_short REAL,
            stock_fut_long REAL,  stock_fut_short REAL,  stock_fut_net REAL,
            stock_call_long REAL, stock_put_long REAL,
            last_updated TEXT,
            PRIMARY KEY (date, category)
        );
CREATE TABLE pit_universe (
        rebal_date TEXT, symbol TEXT, n_days INTEGER, med_turnover REAL,
        adv_rank INTEGER, top100 INTEGER, top250 INTEGER, top500 INTEGER,
        liquid INTEGER, PRIMARY KEY(rebal_date, symbol));
CREATE TABLE quarterly_balance (
                symbol TEXT, report_date TEXT, data_json TEXT, last_updated TEXT,
                PRIMARY KEY (symbol, report_date)
            );
CREATE TABLE quarterly_cashflow (
                symbol TEXT, report_date TEXT, data_json TEXT, last_updated TEXT,
                PRIMARY KEY (symbol, report_date)
            );
CREATE TABLE quarterly_income (
                symbol TEXT, report_date TEXT, data_json TEXT, last_updated TEXT,
                PRIMARY KEY (symbol, report_date)
            );
CREATE TABLE rbi_monetary_data (
            date TEXT NOT NULL,
            series TEXT NOT NULL,
            value REAL,
            unit TEXT,
            last_updated TEXT,
            PRIMARY KEY (date, series)
        );
CREATE TABLE recommendations (
        rec_date TEXT, symbol TEXT, company TEXT, strategy TEXT, score REAL,
        horizon_days INTEGER, entry REAL, target REAL, stop REAL, status TEXT,
        close_date TEXT, exit_price REAL, realized_return REAL, outcome TEXT,
        PRIMARY KEY(rec_date, symbol, strategy));
CREATE TABLE screener_fundamentals (
            symbol TEXT PRIMARY KEY,
            company_name TEXT,
            sector TEXT,
            market_cap_cr REAL,
            pe_ttm REAL,
            pb REAL,
            roce_pct REAL,
            roe_pct REAL,
            div_yield_pct REAL,
            debt_equity REAL,
            current_ratio REAL,
            sales_5yr_cagr REAL,
            profit_5yr_cagr REAL,
            promoter_holding_pct REAL,
            fii_holding_pct REAL,
            pledge_pct REAL,
            eps_ttm REAL,
            book_value REAL,
            face_value REAL,
            data_json TEXT,
            last_updated TEXT
        );
CREATE TABLE screener_fundamentals_v2 (symbol TEXT PRIMARY KEY, pe_ratio REAL, pb_ratio REAL, ps_ratio REAL, peg_ratio REAL, roce REAL, roe REAL, roa REAL, roic REAL, debt_equity REAL, current_ratio REAL, quick_ratio REAL, interest_coverage REAL, promoter_pct REAL, fii_pct REAL, dii_pct REAL, public_pct REAL, market_cap_cr REAL, enterprise_value_cr REAL, sales_cr REAL, profit_cr REAL, ebitda_cr REAL, cash_cr REAL, eps REAL, book_value REAL, face_value REAL, div_yield REAL, div_payout REAL, revenue_growth REAL, profit_growth REAL, ebitda_growth REAL, high_52w REAL, low_52w REAL, current_price REAL, beta REAL, shares_outstanding REAL, scraped_date TEXT, source TEXT);
CREATE TABLE shareholding_history (
            symbol TEXT NOT NULL,
            quarter TEXT NOT NULL,
            promoter_pct REAL,
            fii_pct REAL,
            dii_pct REAL,
            public_pct REAL,
            pledge_pct REAL,
            source TEXT,
            last_updated TEXT,
            PRIMARY KEY (symbol, quarter)
        );
CREATE TABLE short_deals (
            date TEXT, symbol TEXT, name TEXT, client TEXT, buy_sell TEXT,
            qty REAL, price REAL, remarks TEXT,
            PRIMARY KEY(date, symbol, client, buy_sell, qty));
CREATE TABLE sqlite_sequence(name,seq);
CREATE TABLE sqlite_stat1(tbl,idx,stat);
CREATE TABLE stock_data (
        symbol TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL,
        PRIMARY KEY(symbol, date));
CREATE TABLE stock_data_adj (
            symbol TEXT, date TEXT, open REAL, high REAL, low REAL,
            close REAL, volume REAL, adj_factor REAL);
CREATE TABLE stock_data_tr (symbol TEXT, date TEXT, close_tr REAL, tr_factor REAL);
CREATE TABLE stock_delivery (
            symbol TEXT, date TEXT, total_traded_qty REAL, delivery_qty REAL,
            delivery_percent REAL, PRIMARY KEY (symbol, date)
        );
CREATE TABLE stock_fundamentals (
            symbol TEXT PRIMARY KEY, last_updated TEXT,
            sector TEXT, industry TEXT, marketCap REAL, trailingPE REAL, forwardPE REAL,
            priceToBook REAL, dividendYield REAL, payoutRatio REAL, beta REAL
        );
CREATE TABLE stock_registry
                   (
                       symbol
                       TEXT
                       PRIMARY
                       KEY,
                       company_name
                       TEXT,
                       is_active
                       INTEGER
                       DEFAULT
                       1,
                       yahoo_symbol
                       TEXT,
                       last_updated
                       TEXT
                   );
CREATE TABLE symbol_correlations (
            symbol TEXT NOT NULL, asset_type TEXT NOT NULL DEFAULT 'stock',
            benchmark TEXT NOT NULL,
            corr_1y REAL, corr_3y REAL, corr_5y REAL, corr_alltime REAL, beta_1y REAL,
            computed_date TEXT,
            PRIMARY KEY (symbol, asset_type, benchmark)
        );
CREATE TABLE symbol_seasonality (
            symbol TEXT NOT NULL, asset_type TEXT NOT NULL DEFAULT 'stock',
            period_type TEXT NOT NULL, period_value INTEGER NOT NULL,
            n_obs INTEGER, mean_return_pct REAL, median_return_pct REAL,
            std_return_pct REAL, p25 REAL, p75 REAL, prob_positive REAL,
            computed_date TEXT,
            PRIMARY KEY (symbol, asset_type, period_type, period_value)
        );
CREATE TABLE symbol_series_stats (
            symbol TEXT NOT NULL, asset_type TEXT NOT NULL DEFAULT 'stock',
            first_date TEXT, last_date TEXT, n_trading_days INTEGER,
            cagr_pct REAL, total_return_pct REAL, ann_volatility_pct REAL,
            max_drawdown_pct REAL, mdd_start_date TEXT, mdd_trough_date TEXT,
            mdd_recovery_date TEXT, mdd_duration_days INTEGER, mdd_recovery_days INTEGER,
            sharpe_ratio REAL, calmar_ratio REAL, sortino_ratio REAL,
            skewness REAL, kurtosis REAL, pct_positive_days REAL,
            last_close REAL, high_52w REAL, low_52w REAL,
            pct_from_52w_high REAL, pct_from_52w_low REAL,
            computed_date TEXT,
            PRIMARY KEY (symbol, asset_type)
        );
CREATE TABLE symbol_technicals (
            symbol TEXT NOT NULL, asset_type TEXT NOT NULL DEFAULT 'stock',
            as_of_date TEXT NOT NULL,
            rsi_14 REAL, rsi_21 REAL,
            macd_line REAL, macd_signal REAL, macd_histogram REAL,
            bb_position REAL, bb_width_pct REAL,
            atr_14_pct REAL, adx_14 REAL,
            pct_above_sma20 REAL, pct_above_sma50 REAL, pct_above_sma200 REAL,
            sma20_above_sma50 INTEGER, sma50_above_sma200 INTEGER,
            high_52w REAL, low_52w REAL, pct_from_52w_high REAL, pct_from_52w_low REAL,
            vol_surge_20d REAL, computed_date TEXT,
            PRIMARY KEY (symbol, asset_type)
        );
CREATE TABLE tradable_eq_stocks (
        symbol TEXT PRIMARY KEY,
        company_name TEXT,
        updated TEXT
    );
CREATE TABLE us_macro_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            series_id TEXT NOT NULL,
            date TEXT NOT NULL,
            value REAL,
            frequency TEXT,
            last_updated TEXT,
            UNIQUE(series_id, date)
        );
CREATE TABLE window_extremes (
            symbol          TEXT    NOT NULL,
            asset_type      TEXT    NOT NULL DEFAULT 'stock',
            window_days     INTEGER NOT NULL,
            direction       TEXT    NOT NULL,   -- 'up' or 'down'
            rank_n          INTEGER NOT NULL,   -- 1..5

            start_date      TEXT    NOT NULL,
            end_date        TEXT    NOT NULL,
            return_pct      REAL    NOT NULL,

            computed_date   TEXT,

            PRIMARY KEY (symbol, asset_type, window_days, direction, rank_n)
        );
CREATE TABLE window_regime_stats (
            symbol TEXT NOT NULL, asset_type TEXT NOT NULL DEFAULT 'stock',
            window_days INTEGER NOT NULL, regime TEXT NOT NULL,
            n_windows INTEGER, mean_return REAL, median_return REAL, std_return REAL,
            p5 REAL, p25 REAL, p75 REAL, p95 REAL,
            prob_positive REAL, prob_gt10 REAL, prob_lt_neg10 REAL,
            min_return REAL, max_return REAL, computed_date TEXT,
            PRIMARY KEY (symbol, asset_type, window_days, regime)
        );
CREATE TABLE window_stats (
            symbol          TEXT    NOT NULL,
            asset_type      TEXT    NOT NULL DEFAULT 'stock',
            window_days     INTEGER NOT NULL,

            -- coverage
            first_date      TEXT,
            last_date       TEXT,
            n_windows       INTEGER,

            -- central tendency
            mean_return     REAL,
            median_return   REAL,
            std_return      REAL,

            -- extremes
            min_return      REAL,
            max_return      REAL,

            -- percentiles
            p5              REAL,
            p25             REAL,
            p75             REAL,
            p95             REAL,

            -- probability metrics
            prob_positive   REAL,    -- P(return > 0)
            prob_gt5        REAL,    -- P(return > +5%)
            prob_gt10       REAL,    -- P(return > +10%)
            prob_gt20       REAL,    -- P(return > +20%)
            prob_lt_neg5    REAL,    -- P(return < -5%)
            prob_lt_neg10   REAL,    -- P(return < -10%)
            prob_lt_neg20   REAL,    -- P(return < -20%)

            -- annualised (for longer windows, optional)
            ann_return_equiv REAL,   -- annualised equivalent of mean_return

            -- metadata
            computed_date   TEXT, p1 REAL, p10 REAL, p90 REAL, p99 REAL, prob_gt2 REAL, prob_gt50 REAL, prob_lt_neg2 REAL, prob_lt_neg50 REAL, sharpe_ratio REAL, calmar_ratio REAL,    -- YYYY-MM-DD when this row was last computed

            PRIMARY KEY (symbol, asset_type, window_days)
        );
CREATE TABLE world_bank_macro (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            indicator_code TEXT NOT NULL,
            indicator_name TEXT NOT NULL,
            value REAL,
            last_updated TEXT,
            UNIQUE(date, indicator_code)
        );
