
"""
Universe updater for GitHub/Streamlit.
Downloads the latest NSE equity list and BSE securities list into CSV files.
Run locally or from a scheduled GitHub Action.
"""
import io
import requests
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NSE_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
BSE_URL = "https://www.bseindia.com/downloads/StockReach/Static/Securities.csv"

def save_nse():
    r = requests.get(NSE_URL, timeout=30, headers={"User-Agent":"Mozilla/5.0"})
    r.raise_for_status()
    df = pd.read_csv(io.BytesIO(r.content))
    cols = {c.upper().strip(): c for c in df.columns}
    sym = cols.get("SYMBOL")
    series = cols.get("SERIES")
    name = cols.get("NAME OF COMPANY", sym)
    if series:
        df = df[df[series].astype(str).str.upper().eq("EQ")]
    out = pd.DataFrame({
        "symbol": df[sym].astype(str).str.strip().str.upper(),
        "exchange": "NSE",
        "name": df[name].astype(str)
    }).drop_duplicates("symbol")
    out.to_csv(ROOT/"nse_symbols.csv", index=False)
    print("NSE:", len(out))

def save_bse():
    r = requests.get(BSE_URL, timeout=30, headers={"User-Agent":"Mozilla/5.0"})
    r.raise_for_status()
    try:
        df = pd.read_csv(io.BytesIO(r.content), encoding="utf-8", on_bad_lines="skip")
    except Exception:
        df = pd.read_csv(io.BytesIO(r.content), encoding="latin1", on_bad_lines="skip")
    cols = {c.upper().strip(): c for c in df.columns}
    code = next((cols[k] for k in ["SECURITY CODE","SCRIP CODE","SC_CODE","CODE"] if k in cols), None)
    name = next((cols[k] for k in ["SECURITY NAME","SCRIP NAME","NAME OF COMPANY","SECURITY NAME*"] if k in cols), None)
    if not code:
        raise RuntimeError("BSE file format changed: security-code column not found.")
    codes = pd.to_numeric(df[code], errors="coerce")
    mask = codes.notna()
    out = pd.DataFrame({
        "symbol": codes[mask].astype(int).astype(str),
        "exchange": "BSE",
        "name": df.loc[mask, name].astype(str).values if name else codes[mask].astype(int).astype(str).values
    }).drop_duplicates("symbol")
    out.to_csv(ROOT/"bse_symbols.csv", index=False)
    print("BSE:", len(out))

if __name__ == "__main__":
    save_nse()
    save_bse()
    print("Universe files updated.")
