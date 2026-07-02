#!/usr/bin/env python3
"""fetch_niftyindices_nifty50.py — download the survivorship-bias-free NIFTY 50
constituent-weights history (monthly, 2008-01 -> present) sourced from official
niftyindices.com reports and archived on HuggingFace.

Dataset: AMP4010/Historical_Nifty_50_Constituent_Weights_20Y (CC BY-NC-SA 4.0,
non-commercial -- fine for a personal research tool). This is the REAL historical
NIFTY 50 membership that replaces the weak (~58%) turnover-rank reconstruction.

Saves weights.csv (+ sectors.csv) to data_storage/raw/niftyindices/. Idempotent;
retries the download once. Network-only step, kept separate from the DB builder.

Run:  py -3.14 registry/fetch_niftyindices_nifty50.py
"""
import time
import urllib.request
from pathlib import Path

BASE = ("https://huggingface.co/datasets/AMP4010/"
        "Historical_Nifty_50_Constituent_Weights_20Y/resolve/main/")
FILES = ["weights.csv", "sectors.csv", "summary.csv"]
DEST = Path(__file__).resolve().parents[1].parent / "data_storage" / "raw" / "niftyindices"


def download(name):
    url = BASE + name
    for attempt in (1, 2):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            data = urllib.request.urlopen(req, timeout=90).read()
            DEST.mkdir(parents=True, exist_ok=True)
            (DEST / name).write_bytes(data)
            return len(data)
        except Exception as e:
            print(f"  {name} attempt {attempt} failed: {str(e)[:80]}", flush=True)
            if attempt == 1:
                time.sleep(3)
    return None


def main():
    for name in FILES:
        n = download(name)
        print(f"  {name}: {'OK ' + str(n) + ' bytes' if n else 'FAILED'}", flush=True)
    w = DEST / "weights.csv"
    if w.exists():
        import csv
        rows = list(csv.reader(w.open(encoding="utf-8")))
        print(f"  weights.csv: {len(rows)-1} monthly snapshots, "
              f"{len(rows[0])-1} distinct symbols, {rows[1][0]} -> {rows[-1][0]}", flush=True)


if __name__ == "__main__":
    main()
