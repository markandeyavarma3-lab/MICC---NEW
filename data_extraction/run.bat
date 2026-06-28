@echo off
REM Launch the MICC daily extraction with the correct interpreter (3.14 has nselib/fredapi).
cd /d "%~dp0"
py -3.14 run_pipeline.py %*
