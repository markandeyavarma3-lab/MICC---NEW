# SHP extraction routes — Step-0 verification (2026-07-04)

Live-tested from this machine with `py -3.14` + `requests`. Every claim below was
verified with an actual HTTP round-trip on 2026-07-04; nothing is assumed from the
research report. Verdict per route first, then exact URL patterns and payload shapes.

## Verdict summary

| Route (from research report) | Verdict | Notes |
|---|---|---|
| BSE undocumented JSON API (`api.bseindia.com/BseIndiaAPI/api/...`) | ✅ **LIVE — primary route** | Full SHP endpoint family found in the Angular bundle and verified. Depth: **2001→present** per scrip; PIT filing timestamp from **March 2016**. |
| BSE corporate-announcements search, category "Shareholding Pattern" | ❌ **DEAD as described** | The announcements API has **no SHP category** (9 categories: AGM/EGM, Board Meeting, Company Update, Corp. Action, Insider Trading/SAST, New Listing, Result, Integrated Filing, Others). SHP filings live in a separate Corp Filings module with their own endpoints (below). |
| BSE SME portal (`bsesme.com`) SHP page + bulk export | ❌ **DEAD** — and **unnecessary** | `bsesme.com/shareholding/shareholding_pattern.aspx` returns an error-image stub (285 bytes). Irrelevant anyway: SME scrips (groups M/MT/MS, 497 active) are served by the **same** `api.bseindia.com` SHP endpoints (verified on 534109 Pyxis Finvest, 35 quarters with filing timestamps). |
| NSE SHP corporate-filings endpoints | ✅ **LIVE — bulk detector + cross-check** | Per-symbol history (90 qtrs for RELIANCE, 2005→present) *and* a bulk date-range enumeration across all symbols. `broadcastDate` present on recent rows; missing on old rows. |
| Company IR pages / annual reports | not tested | Stage 2/3 fallback only; out of Stage-1 scope. |

**No route needed CAPTCHA/token bypassing.** Both exchanges need browser-like headers
and a cookie-priming GET — the same pattern already used by
`registry/refresh_bse_registry.py` (BSE) and `macro/fetch_phase1_data.py` (NSE). That
is normal header hygiene, not anti-bot circumvention.

---

## Route A (primary): BSE JSON API

Headers (all endpoints):

```
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36
Accept: application/json, text/plain, */*
Referer: https://www.bseindia.com/
Origin: https://www.bseindia.com
```

Prime cookies with `GET https://www.bseindia.com/` once per session.
Base: `https://api.bseindia.com/BseIndiaAPI/api`

### A1. Universe: `ListofScripData/w`

```
GET /ListofScripData/w?Group=&Scripcode=&industry=&segment=Equity&status=Active
```

→ JSON array, **4,913 active equity scrips** (2026-07-04) with `SCRIP_CD`, `Scrip_Name`,
`ISIN_NUMBER`, `GROUP`, `Status`, `scrip_id`, `Issuer_Name`, `Mktcap`. Mainboard + SME in
one list; SME = `GROUP` ∈ {M (317), MT (175), MS (5)} → `exchange_segment` derivation.
(The `segment=SME` param is ignored — returns a bigger mixed list; do not use it.)
Already consumed by `refresh_bse_registry.py` → `bse_stock_registry`.

### A2. Per-scrip filing index: `SHPQNewFormat/w`  ← the enumerator

```
GET /SHPQNewFormat/w?scripcode=500325
```

→ `{"Table":[...]}`, one row per quarter, newest first. RELIANCE: **105 quarters,
March 2001 → March 2026**. Fields:

| field | example | use |
|---|---|---|
| `qtrid` | `129.00` | BSE quarter id (129 = Mar 2026; +1 per quarter) — key for all detail endpoints |
| `qtr`, `yr` | `"March 2026"`, `"2025 - 2026"` | `quarter_end_date` derivation |
| `status` | `"New"` / `"Revised"` / `null` | revision flag (null on pre-2016 rows) |
| `filing_date_time` | `"2026-04-21T13:16:58.457"` | **THE PIT timestamp** → `broadcast_datetime` |
| `revised_date_time` | timestamp or null | PIT timestamp of the revision |
| `revised_reson` | text | revision reason |
| `XbrlFile` | `"500325_2142026131656_SHP.xml"` | raw XBRL filename |
| `xbrlurl` | `"/XBRLFILES/SHPXBRLDataXML/..._SP.html"` | HTML rendition |

**Critical depth fact:** `filing_date_time` is populated from **March 2016** onward
(XBRL era). RELIANCE: 44 of 105 rows have it; the 61 pre-2016 rows have data but **no
filing timestamp** → no honest PIT date without an estimation policy. Stage 1 =
2016→present only, where PIT is exact.

### A3. Raw XBRL download

```
GET https://www.bseindia.com/XBRLFILES/SHPXBRLDataXML/{XbrlFile}
```

→ `text/xml`, SEBI SHP XBRL instance (RELIANCE Mar-2026: 537 KB, taxonomy
`in-bse-shp` versioned in a comment, e.g. `SHP V1.1 (01-12-2025)`). This is the
raw-file artifact for `raw_blob_path` + `file_hash`. Note: the `/xml-data/...` prefix
404s; use the bare `/XBRLFILES/` path.

### A4. Parsed-table endpoints (per scrip × quarter)

All verified live; params as shown (case matters — mixed conventions per endpoint):

| Endpoint | Params | Returns |
|---|---|---|
| `Corp_shpSec_shpqtrinfo_ng/w` | `scripcode=&qtrcode=` | quarter meta: name, start/end dates, notes |
| `Corp_shpSec_SHPSUMMARY_ng/w` | `scripcode=&qtrcode=` | **Table I** category summary: `Fld_Code` (A/B/C…), holders, fully/partly-paid shares, DR shares, total %, voting rights (~8.5 KB) |
| `Corp_shpPromoterNGroup_ng/w` | `SCRIPCODE=&QtrCode=` | **Table II** named promoters + PAC (62 KB for RELIANCE) |
| `Corp_shpSec_SHPPubShold_ng/w` | `SCRIPCODE=&QtrCode=` | **Table III** public shareholders incl. named ≥1% holders (43 KB) |
| `Corp_SHPNonPromoterNonPublic_ng/w` | `SCRIPCODE=&QtrCode=` | **Table IV** custodian/DR (3.5 KB) |
| `shpDecleraction/w` | `scripcode=&qtrid=` | declaration flags + `Mid` record id |
| `CorporatesSHPSecuritybeta/w` | `scripcode=&qtrid=` | combined summary (works for old quarters too) |

**Pre-2016 quarters serve parsed data too**: `SHPSUMMARY` returns Table I back to
qtrid 29 (March 2001) — old-format quarters just have an empty `Table` (flag block)
and no XBRL. So Stages 2–3 can extend BSE coverage to ~2001 for currently-listed
scrips, with an *estimated* PIT policy (no filing timestamps pre-2016).

### Dead/nonexistent BSE endpoints (guessed names that 404-shell)
`Corpshpsearch/w`, `ShareHoldingSecurtieswise/w` — return the ASPX error shell, do not
exist. The full real endpoint dictionary lives in the site bundle
(`assets/includenew/js/main-*.js`); re-extract from there if BSE renames things.

### No bulk "all scrips filed in date range" endpoint found on BSE
The Corp-Filings SHP search is per-security. New-filing detection on BSE is therefore
**per-scrip iteration** of A2 (1 call/scrip ≈ 4,913 calls/cycle) — or indirectly via
the NSE bulk route for the cross-listed subset. With 0.4 s pacing ≈ ~35 min/sweep;
weekly cadence is comfortably viable.

---

## Stage 2 findings (2026-07-04) — PIT floor + format breaks

**PIT floor is empirical, not assumed.** Filings-per-quarter cliff-jumps 6 → 58 →
**2,226** at qtrid 89 (**March 2016**). Pre-2016 filings that carry a timestamp are
**retro-uploads**: a 2006 filing shows a *2023* broadcast time (avg lag 2,734 days vs
22 days post-2016). They are PIT-honest but useless for a quarter-aligned test.
`fetch_shp.py` gates them out with `--max-filing-lag-days 400` (parse iff broadcast
within N days of quarter-end). Usable real-time-filed window: **Mar 2016 → present,
~41 quarters**.

**Table III institutional format break ~Sept 2022.** Two structurally different SHP
layouts:
- **New (≈2022-Sep →):** clean `Sub Total B1` (domestic institutions) / `Sub Total B2`
  (foreign institutions); FPI split into `Category I` / `Category II`.
- **Old (2016 → 2022-Jun):** `B1` lumps **all** institutions together, `B2` reads `0`,
  FPI is a single `Foreign Portfolio Investors` line, and an `Any Other (specify)`
  institution line is an ambiguous foreign/domestic bucket.
Consequence for the future signals: `fpi_delta` is recoverable across the whole window
(sum `is_aggregate=1` rows where `level LIKE 'Foreign Portfolio Investors%'`), but
`dii_delta` via the clean B1 subtotal is only reliable post-break — the coverage audit's
§3b measures exactly when B2 becomes populated.

**Named-holder nesting.** Table III lists each institution type as an AGGREGATE row
(`Fld_ShareHolderName` NULL) optionally followed by named ≥1% holders NESTED inside it
(name set). Summing a level's rows double-counts. `shp_institutional_summary.is_aggregate`
flags the usable aggregate; FPI/DII aggregation MUST filter `is_aggregate=1`.

## Route B (bulk detector + cross-check): NSE JSON API

Headers: Chrome-like UA + `Referer:
https://www.nseindia.com/companies-listing/corporate-filings-shareholding-pattern`;
prime cookies with `GET https://www.nseindia.com/` (session expires — refresh on 403,
same pattern as `fetch_phase1_data.py`).

### B1. Bulk date-range enumeration (all symbols)

```
GET https://www.nseindia.com/api/corporate-share-holdings-master?index=equities&from_date=20-06-2026&to_date=04-07-2026
```

→ JSON array of **every SHP filing broadcast in the window** across the NSE universe.
Fields: `symbol`, `name`, `date` (quarter end), `submissionDate`,
**`broadcastDate`** (`"03-JUL-2026 15:31:41"` — PIT), `revisedData` (Y/N),
`revisedDate`, `recordId`, `xbrl` (full URL on `nsearchives.nseindia.com`),
`pr_and_prgrp` / `public_val` (headline %). Date format `DD-MM-YYYY`.

### B2. Per-symbol history

```
GET .../api/corporate-share-holdings-master?index=equities&symbol=RELIANCE
```

→ same shape; RELIANCE: **90 quarters, Jun-2005 → Mar-2026**. `broadcastDate` is null
on old rows (oldest with a broadcast timestamp not systematically mapped; recent
years are populated). XBRL links point at `nsearchives.nseindia.com/corporate/xbrl/`.

Role: (1) weekly *what's-new* detector (one call per week instead of 4,913),
(2) independent cross-check of BSE parse for cross-listed names, (3) delivery of NSE
XBRL raw files as a second raw source where wanted. Not the primary store — BSE covers
BSE-only + SME names that NSE misses.

---

## Politeness / stability rules (bind the fetcher to these)

- ≥ 0.3–0.5 s sleep between calls, jittered; single-threaded per host.
- Cookie-prime once per session; on 401/403/HTML-instead-of-JSON, re-prime and retry
  once; on second failure, log and move on (weekly sweep catches it next run).
- Cache-by-hash: `SHPQNewFormat` response unchanged for a scrip ⇒ skip detail fetches
  entirely (idempotent no-op).
- These are undocumented endpoints — assume they can rename without notice. The
  monitor alert on "0 new filings for 2 consecutive weekly sweeps during filing
  season" is the canary.
