#!/usr/bin/env python3
"""export_pdf.py — render the MICC HTML artifacts to PDF via headless Edge/Chrome.

No Python PDF library needed — drives the installed browser's print engine so the PDF
matches the styled page exactly (each slide becomes a page via the deck's @media print CSS).

Run:  py -3.14 common/export_pdf.py            # export the slide deck -> MICC_slides.pdf
      py -3.14 common/export_pdf.py --all        # also export the dashboard
"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(r"D:\MICC")
BROWSERS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]
JOBS = [("MICC_slides.html", "MICC_slides.pdf", True)]            # (src, out, landscape)
JOBS_ALL = JOBS + [("MICC_dashboard.html", "MICC_dashboard.pdf", False)]


def find_browser():
    for b in BROWSERS:
        if Path(b).exists():
            return b
    return None


def to_pdf(browser, src, out, landscape):
    src_f, out_f = ROOT / src, ROOT / out
    if not src_f.exists():
        print(f"  SKIP {src} (not found — build it first)"); return False
    if out_f.exists():
        try: out_f.unlink()
        except Exception: pass
    url = src_f.as_uri()
    args = [browser, "--headless=new", "--disable-gpu", "--no-sandbox",
            "--no-pdf-header-footer", f"--print-to-pdf={out_f}", url]
    if landscape:
        args.insert(-1, "--landscape")
    subprocess.run(args, capture_output=True, timeout=120)
    # headless print is async-ish on some builds; wait briefly for the file
    for _ in range(20):
        if out_f.exists() and out_f.stat().st_size > 1000:
            print(f"  OK  {out}  ({out_f.stat().st_size/1024:.0f} KB)"); return True
        time.sleep(0.5)
    print(f"  FAIL {out} (browser produced no file)"); return False


def main():
    browser = find_browser()
    if not browser:
        print("No Edge/Chrome found — install one, or open the HTML and Ctrl+P -> Save as PDF.")
        return
    print(f"Using: {browser}")
    jobs = JOBS_ALL if "--all" in sys.argv else JOBS
    for src, out, ls in jobs:
        to_pdf(browser, src, out, ls)
    print("Done. PDFs are in D:\\MICC\\")


if __name__ == "__main__":
    main()
