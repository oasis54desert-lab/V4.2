# Indian Stock Scanner V4.2

A Streamlit EOD stock scanner for Indian equities.

## Features
- NSE + BSE universe
- Automatic NSE/BSE universe refresh
- Search by symbol/company
- EOD scan using the latest completed daily candles
- RSI, SMA20/SMA50, volume ratio, 20-day breakout, 1-month momentum
- ATR-based stop loss and targets
- Score from 0–100
- BUY / STRONG BUY / WATCH / AVOID
- CSV export
- Parallel scanning

## Streamlit deployment

Use:

Repository: your GitHub repository  
Branch: `main`  
Main file path: `streamlit_app.py`

Do NOT enter a shell command in Main file path.

## Important data note

This version is designed for end-of-day scanning. `yfinance` is a convenient public data source but is not an exchange-certified real-time feed. For broker-grade live/intraday data, connect an authorised market-data/broker API.

## Large universe

The app attempts to download the latest NSE and BSE equity/security lists automatically. `nse_symbols.csv` and `bse_symbols.csv` are included as repository fallbacks.

If an exchange changes its download format or blocks automated requests, run `update_universe.py` locally and commit the refreshed CSV files.

## Performance

Scanning thousands of symbols can take time and data providers can throttle requests. Start with 500–1,000 symbols, verify the app, then increase the scan limit.

This is a research/technical screening tool, not investment advice.
