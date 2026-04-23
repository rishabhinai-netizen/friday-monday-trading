# Friday-Monday Pattern Trading System

> One of the most persistent anomalies in Indian equity markets — now systematically quantified.

A Streamlit application that identifies, measures, and scans for the Friday close → Monday open price pattern across the Nifty 50 universe. Built on pre-calculated historical success rates, with live signal generation and RSI/MA confirmation overlays.

---

## The Anomaly

Markets are not perfectly random across the week. The Friday-Monday window — driven by weekend institutional positioning, derivatives expiry dynamics, and retail sentiment gaps — consistently produces directional bias in a subset of Nifty 50 stocks.

This tool answers three questions:
1. **Which stocks** exhibit the most reliable Friday-Monday pattern historically?
2. **Under what conditions** does the pattern have the highest success rate?
3. **Right now** — which stocks are setting up for the pattern this week?

## Historical Analysis

Pre-calculated success rates in `nifty50_summary_stats.csv` cover:

| Metric | Tracked |
|--------|---------|
| Pattern direction (gap up / gap down) | Per stock |
| Success rate by market regime | Bull / Bear / Sideways |
| RSI threshold with highest success | Per stock |
| Volume confirmation impact | Measured |
| Seasonal patterns (pre-expiry weeks) | Included |

## Live Scanner

The app pulls real-time data via yfinance to check:
- Current Friday close vs previous Monday open (last 4 weeks)
- RSI level at Friday close
- Volume vs 20-day average
- MA alignment (above/below 20/50 DMA)

Stocks meeting historical success-rate thresholds are flagged as live setups.

## Features

- Pattern success rate heatmap across Nifty 50
- Live scanner with configurable RSI and volume filters
- Individual stock drill-down with historical pattern chart
- Regime filter (bull/bear/sideways market context)
- Email automation module for end-of-week signal dispatch

## Setup

```bash
git clone https://github.com/rishabhinai-netizen/friday-monday-trading
cd friday-monday-trading
pip install -r requirements.txt
streamlit run trading_app.py
```

## Project Structure

```
friday-monday-trading/
├── trading_app.py              # Main Streamlit application
├── email_automation.py         # Weekly signal email dispatch
├── nifty50_summary_stats.csv   # Pre-calculated historical stats
└── .github/                    # Workflow automation
```

---

*One anomaly, rigorously measured. Not a tip — a system.*
