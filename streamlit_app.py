
import io
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd
import requests
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="Indian Stock Scanner V4.2", page_icon="🇮🇳", layout="wide")

IST = timezone(timedelta(hours=5, minutes=30))
NSE_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
BSE_URL = "https://www.bseindia.com/downloads/StockReach/Static/Securities.csv"

@st.cache_data(ttl=24*3600, show_spinner=False)
def load_nse():
    try:
        r = requests.get(NSE_URL, timeout=20, headers={"User-Agent":"Mozilla/5.0"})
        r.raise_for_status()
        df = pd.read_csv(io.BytesIO(r.content))
        cols = {c.upper().strip(): c for c in df.columns}
        sym = cols.get("SYMBOL")
        series = cols.get("SERIES")
        if not sym:
            return pd.DataFrame(columns=["symbol","exchange","name"])
        if series:
            df = df[df[series].astype(str).str.upper().eq("EQ")]
        out = pd.DataFrame({
            "symbol": df[sym].astype(str).str.strip().str.upper(),
            "exchange": "NSE",
            "name": df.get(cols.get("NAME OF COMPANY", sym), df[sym]).astype(str)
        })
        return out.drop_duplicates("symbol")
    except Exception:
        return pd.DataFrame(columns=["symbol","exchange","name"])

@st.cache_data(ttl=24*3600, show_spinner=False)
def load_bse():
    try:
        r = requests.get(BSE_URL, timeout=25, headers={"User-Agent":"Mozilla/5.0"})
        r.raise_for_status()
        raw = r.content
        try:
            df = pd.read_csv(io.BytesIO(raw), encoding="utf-8", on_bad_lines="skip")
        except Exception:
            df = pd.read_csv(io.BytesIO(raw), encoding="latin1", on_bad_lines="skip")
        cols = {c.upper().strip(): c for c in df.columns}
        code = None
        for k in ["SECURITY CODE","SCRIP CODE","SC_CODE","CODE"]:
            if k in cols:
                code = cols[k]; break
        namecol = None
        for k in ["SECURITY NAME","SCRIP NAME","NAME OF COMPANY","SECURITY NAME*"]:
            if k in cols:
                namecol = cols[k]; break
        if not code:
            return pd.DataFrame(columns=["symbol","exchange","name"])
        codes = pd.to_numeric(df[code], errors="coerce").dropna().astype(int).astype(str)
        names = df.loc[codes.index, namecol].astype(str) if namecol else codes
        out = pd.DataFrame({"symbol": codes.values, "exchange":"BSE", "name":names.values})
        return out.drop_duplicates("symbol")
    except Exception:
        return pd.DataFrame(columns=["symbol","exchange","name"])

def make_universe():
    nse, bse = load_nse(), load_bse()
    return nse, bse

def ticker(exchange, symbol):
    return f"{symbol}.NS" if exchange == "NSE" else f"{symbol}.BO"

@st.cache_data(ttl=15*60, show_spinner=False)
def fetch_history(tkr, period="6mo"):
    try:
        df = yf.download(tkr, period=period, interval="1d", auto_adjust=False,
                          progress=False, threads=False)
        if df is None or df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.columns = [str(c).title() for c in df.columns]
        need = ["Open","High","Low","Close","Volume"]
        if not all(c in df.columns for c in need):
            return None
        df = df[need].dropna()
        return df if len(df) >= 55 else None
    except Exception:
        return None

def indicators(df):
    x = df.copy()
    c, h, l, v = x["Close"], x["High"], x["Low"], x["Volume"]
    x["SMA20"] = c.rolling(20).mean()
    x["SMA50"] = c.rolling(50).mean()
    delta = c.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    x["RSI"] = 100 - (100 / (1 + rs))
    tr = pd.concat([(h-l), (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    x["ATR"] = tr.rolling(14).mean()
    x["AvgVol20"] = v.rolling(20).mean()
    x["VolRatio"] = v / x["AvgVol20"]
    x["Ret1M"] = c.pct_change(21) * 100
    x["High20"] = h.shift(1).rolling(20).max()
    return x

def score_stock(df):
    x = indicators(df).dropna()
    if x.empty: return None
    r = x.iloc[-1]
    prev = x.iloc[-2] if len(x) > 1 else r
    price = float(r["Close"])
    score = 0
    reasons = []

    if price > r["SMA20"]: score += 15; reasons.append("above SMA20")
    if price > r["SMA50"]: score += 15; reasons.append("above SMA50")
    if r["SMA20"] > r["SMA50"]: score += 10; reasons.append("SMA20>SMA50")
    if 50 <= r["RSI"] <= 70: score += 15; reasons.append("healthy RSI")
    elif r["RSI"] > 70: score += 5; reasons.append("RSI>70")
    if r["VolRatio"] >= 1.5: score += 15; reasons.append("volume breakout")
    elif r["VolRatio"] >= 1.1: score += 8; reasons.append("volume improving")
    if price > r["High20"]: score += 15; reasons.append("20D breakout")
    if r["Ret1M"] > 5: score += 10; reasons.append("1M momentum")
    elif r["Ret1M"] > 0: score += 5; reasons.append("positive 1M")
    score = min(score, 100)

    if score >= 70: signal = "STRONG BUY"
    elif score >= 58: signal = "BUY"
    elif score >= 45: signal = "WATCH"
    else: signal = "AVOID"

    atr = float(r["ATR"])
    stop = max(0.0, price - 1.5*atr)
    t1 = price + 2*atr
    t2 = price + 3*atr
    return {
        "Price": price, "Score": score, "Signal": signal,
        "RSI": float(r["RSI"]), "Volume Ratio": float(r["VolRatio"]),
        "1M Return %": float(r["Ret1M"]), "ATR": atr,
        "Stop Loss": stop, "Target 1": t1, "Target 2": t2,
        "Reasons": ", ".join(reasons), "Date": x.index[-1].date().isoformat()
    }

def scan_row(item):
    exchange, symbol, name = item
    tkr = ticker(exchange, symbol)
    df = fetch_history(tkr)
    if df is None: return None
    result = score_stock(df)
    if result is None: return None
    result.update({"Stock": symbol, "Exchange": exchange, "Company": name})
    return result

st.title("🇮🇳 Indian Stock Scanner V4.2")
st.caption("NSE + BSE equity universe • EOD completed-day data • technical + momentum + breakout + ATR")

with st.sidebar:
    st.header("Scanner Settings")
    nse, bse = make_universe()
    st.write(f"**NSE universe:** {len(nse):,}")
    st.write(f"**BSE universe:** {len(bse):,}")
    st.write(f"**Combined:** {len(nse)+len(bse):,}")

    exchanges = st.multiselect("Exchange", ["NSE","BSE"], ["NSE","BSE"])
    max_scan = st.number_input("Maximum stocks to scan", min_value=50, max_value=10000,
                               value=min(1000, max(50, len(nse)+len(bse))), step=50)
    workers = st.slider("Parallel workers", 2, 12, 6)
    period = st.selectbox("History", ["3mo","6mo","1y"], index=1)

    if st.button("🔄 Refresh universe"):
        load_nse.clear(); load_bse.clear()
        st.rerun()

    run = st.button("▶ RUN EOD SCAN", type="primary", use_container_width=True)

if not exchanges:
    st.warning("Select at least one exchange.")
    st.stop()

universe = pd.concat([nse if "NSE" in exchanges else nse.iloc[0:0],
                      bse if "BSE" in exchanges else bse.iloc[0:0]], ignore_index=True)
universe = universe.drop_duplicates(["exchange","symbol"])

query = st.text_input("🔎 Search stock/company", placeholder="TITAN, RELIANCE, PRICOL...")
if query.strip():
    q = query.strip().upper()
    universe = universe[universe["symbol"].str.contains(q, na=False) |
                        universe["name"].str.upper().str.contains(q, na=False)]

st.metric("Universe available", f"{len(universe):,}")

if run:
    work = universe.head(int(max_scan))
    items = list(work[["exchange","symbol","name"]].itertuples(index=False, name=None))
    results = []
    progress = st.progress(0)
    status = st.empty()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(scan_row, item) for item in items]
        done = 0
        for f in as_completed(futures):
            done += 1
            try:
                r = f.result()
                if r: results.append(r)
            except Exception:
                pass
            progress.progress(done/len(futures))
            status.write(f"Scanning {done:,}/{len(futures):,} • usable results: {len(results):,}")
    progress.empty(); status.empty()

    if not results:
        st.error("No usable market data was returned. Try a smaller scan or retry later.")
        st.stop()

    out = pd.DataFrame(results).sort_values(["Score","Volume Ratio"], ascending=False)
    st.session_state["results"] = out
    st.session_state["scan_time"] = datetime.now(IST).strftime("%d %b %Y, %H:%M:%S IST")

if "results" in st.session_state:
    out = st.session_state["results"]
    c1,c2,c3 = st.columns(3)
    c1.metric("Stocks with data", f"{len(out):,}")
    c2.metric("BUY / STRONG BUY", f"{out['Signal'].isin(['BUY','STRONG BUY']).sum():,}")
    c3.metric("Top score", f"{out['Score'].max():.0f}/100")

    st.subheader("Ranked Watchlist")
    display_cols = ["Stock","Exchange","Company","Price","Score","Signal","RSI",
                    "Volume Ratio","1M Return %","Stop Loss","Target 1","Target 2","Date"]
    st.dataframe(out[display_cols], use_container_width=True, hide_index=True)

    st.subheader("Top setups")
    st.dataframe(out.head(20)[display_cols], use_container_width=True, hide_index=True)

    csv = out.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Download scan CSV", csv, "scanner_results.csv", "text/csv")

    st.caption(f"Last scan: {st.session_state.get('scan_time','')}")
else:
    st.info("Choose NSE/BSE and press RUN EOD SCAN. The scanner uses the latest completed daily candles available from the data provider.")
