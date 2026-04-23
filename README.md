# Friday-Monday Pattern Trading System

**Automated pattern scanner for the Friday-Monday overnight anomaly on Nifty 50.**

A Streamlit web app that identifies and visualises the Friday close → Monday open price pattern across all Nifty 50 stocks. Includes historical success rate analysis, RSI/MA overlays, and signal generation.

---

## What Is the Friday-Monday Pattern?

Certain stocks consistently exhibit a directional bias between Friday's close and Monday's open — driven by weekend sentiment, institutional positioning, and derivatives expiry effects. This tool quantifies and scans for those patterns systematically.

---

## Features

- Historical success rate analysis across Nifty 50 universe
- Live pattern scanner with configurable thresholds
- RSI + Moving Average overlays for confirmation
- Interactive Plotly charts
- Pre-calculated statistics from `nifty50_summary_stats.csv`

---

## Setup

```bash
pip install -r requirements.txt
streamlit run trading_app.py
```

---

## Tech Stack

- **Streamlit** — UI framework
- **yfinance** — Market data
- **Plotly** — Interactive charts
- **Pandas / NumPy** — Data analysis

---

## Data

Historical summary statistics are pre-calculated and stored in `nifty50_summary_stats.csv`. Live data is fetched via yfinance with 5-minute caching.

---

## Built By

Rishabh Inai — NSE trader and fraud investigator, Mumbai.
