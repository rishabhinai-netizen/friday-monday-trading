"""
FM STRATEGY — EMAIL AUTOMATION
Modes:
  python email_alerts.py --mode friday   → 3:35 PM IST, run Friday scan
  python email_alerts.py --mode monday   → 9:20 AM IST, send trade signals
  python email_alerts.py --mode eod      → 3:35 PM IST Monday, log outcomes
"""

import os, sys, json, time, smtplib, argparse
from datetime import date, datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pandas as pd
import numpy as np
import yfinance as yf
import warnings
warnings.filterwarnings('ignore')

try:
    from supabase import create_client
except ImportError:
    print("⚠ supabase package not installed. Running without DB.")
    create_client = None

from nifty250_stocks import NIFTY_250_STOCKS, SYMBOL_TO_NAME, SYMBOL_TO_SECTOR
from backtest_engine import compute_rsi, compute_volume_ratio

# ── Config from env / Streamlit secrets ──────────────────────────────────────
def get_config():
    return {
        'sender_email':    os.environ.get('SENDER_EMAIL', ''),
        'sender_password': os.environ.get('SENDER_PASSWORD', ''),
        'recipient_email': os.environ.get('RECIPIENT_EMAIL', ''),
        'smtp_server':     os.environ.get('SMTP_SERVER', 'smtp.gmail.com'),
        'smtp_port':       int(os.environ.get('SMTP_PORT', '587')),
        'supabase_url':    os.environ.get('SUPABASE_URL', ''),
        'supabase_key':    os.environ.get('SUPABASE_KEY', ''),
        'trading_capital': float(os.environ.get('TRADING_CAPITAL', '500000')),
        'risk_per_trade':  float(os.environ.get('RISK_PER_TRADE', '1.0')),  # % of capital
    }

# ── Email sender ─────────────────────────────────────────────────────────────
def send_email(cfg: dict, subject: str, html_body: str):
    if not cfg['sender_email']:
        print("⚠ No email config. Skipping send.")
        return False
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From']    = cfg['sender_email']
        msg['To']      = cfg['recipient_email']
        msg.attach(MIMEText(html_body, 'html'))

        with smtplib.SMTP(cfg['smtp_server'], cfg['smtp_port']) as server:
            server.ehlo()
            server.starttls()
            server.login(cfg['sender_email'], cfg['sender_password'])
            server.sendmail(cfg['sender_email'], cfg['recipient_email'], msg.as_string())
        print(f"✓ Email sent: {subject}")
        return True
    except Exception as e:
        print(f"✗ Email failed: {e}")
        return False

# ── Supabase client ───────────────────────────────────────────────────────────
def get_sb(cfg: dict):
    if not create_client or not cfg['supabase_url']:
        return None
    try:
        return create_client(cfg['supabase_url'], cfg['supabase_key'])
    except Exception:
        return None

# ── Get latest stock data (1 month for indicators) ───────────────────────────
def fetch_stock_data(symbol: str, period: str = '3mo') -> pd.DataFrame:
    try:
        df = yf.download(symbol, period=period, auto_adjust=True, progress=False)
        if df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.index = pd.to_datetime(df.index)
        df.sort_index(inplace=True)
        return df
    except Exception:
        return None

# ─────────────────────────────────────────────────────────────────────────────
# MODE: FRIDAY — generate watchlist and send email
# ─────────────────────────────────────────────────────────────────────────────
def run_friday_mode(cfg: dict):
    today = date.today()
    print(f"\n{'='*55}")
    print(f"  FRIDAY SCAN — {today.strftime('%d %b %Y %A')}")
    print(f"{'='*55}\n")

    sb = get_sb(cfg)

    # Load historical win rates from Supabase
    hist_wr = {}
    hist_trades = {}
    hist_avg = {}
    if sb:
        try:
            rows = sb.table('fm_stock_summary').select(
                'symbol, win_rate_pct, total_trades, avg_gross_pnl'
            ).execute().data
            for row in rows:
                sym = row['symbol'] + '.NS'
                hist_wr[sym]     = row['win_rate_pct']
                hist_trades[sym] = row['total_trades']
                hist_avg[sym]    = row['avg_gross_pnl']
        except Exception as e:
            print(f"⚠ Could not load historical stats: {e}")

    watchlist = []
    symbols   = list(NIFTY_250_STOCKS.keys())
    total     = len(symbols)

    for idx, symbol in enumerate(symbols, 1):
        print(f"  [{idx:>3}/{total}] {SYMBOL_TO_NAME.get(symbol, symbol):<30}", end=' ')

        df = fetch_stock_data(symbol, period='2mo')
        if df is None or len(df) < 10:
            print("no data")
            continue

        df['RSI']      = compute_rsi(df['Close'])
        df['VolRatio'] = compute_volume_ratio(df['Volume'])
        df['SMA20']    = df['Close'].rolling(20).mean()

        trading_days = df.index.tolist()
        n = len(trading_days)

        # Find today's (or last available) Friday
        for i in range(n - 1, max(n - 7, -1), -1):
            if trading_days[i].weekday() == 4:
                friday_idx = i
                friday     = trading_days[i]
                break
        else:
            print("no Friday found")
            continue

        fri_row = df.iloc[friday_idx]

        # Find reference day (Thursday or Wednesday if Thu holiday)
        ref_row = None
        for back in range(1, 6):
            if friday_idx - back < 0:
                break
            cand = trading_days[friday_idx - back]
            if cand.weekday() == 3:
                ref_row = df.iloc[friday_idx - back]
                break
            if cand.weekday() == 2:
                thu_cand = cand + timedelta(days=1)
                if thu_cand not in df.index:
                    ref_row = df.iloc[friday_idx - back]
                    break
                break

        if ref_row is None:
            print("no ref day")
            continue

        if fri_row['High'] >= ref_row['High']:
            print(f"no setup (Fri H {fri_row['High']:.2f} ≥ Ref H {ref_row['High']:.2f})")
            continue

        # Setup confirmed!
        wr     = hist_wr.get(symbol, 0.0)
        trades = hist_trades.get(symbol, 0)
        avg_g  = hist_avg.get(symbol, 0.0)
        rsi    = float(fri_row['RSI']) if not pd.isna(fri_row['RSI']) else 50.0
        volr   = float(fri_row['VolRatio']) if not pd.isna(fri_row['VolRatio']) else 1.0
        above  = bool(fri_row['Close'] > fri_row['SMA20']) if not pd.isna(fri_row['SMA20']) else True

        print(f"✓ SETUP | RSI {rsi:.0f} | VolR {volr:.1f}x | WR {wr:.1f}%")

        watchlist.append({
            'week_date':           friday.date().isoformat(),
            'symbol':              symbol,
            'stock_name':          SYMBOL_TO_NAME.get(symbol, symbol),
            'sector':              SYMBOL_TO_SECTOR.get(symbol, 'Unknown'),
            'tier':                NIFTY_250_STOCKS[symbol]['tier'],
            'ref_day_type':        'thursday' if ref_row.name.weekday() == 3 else 'wednesday',
            'ref_day_high':        round(float(ref_row['High']), 2),
            'fri_high':            round(float(fri_row['High']), 2),
            'fri_low':             round(float(fri_row['Low']), 2),
            'fri_close':           round(float(fri_row['Close']), 2),
            'fri_rsi':             round(rsi, 2),
            'fri_volume_ratio':    round(volr, 3),
            'fri_above_sma20':     above,
            'historical_wr_pct':   wr,
            'historical_trades':   trades,
            'historical_avg_gross': round(avg_g, 4),
        })

    print(f"\n✓ Watchlist: {len(watchlist)} stocks\n")

    if not watchlist:
        send_email(cfg,
            f"📊 FM Strategy: No Setups This Friday {today.strftime('%d %b')}",
            "<p>No stocks met the Friday High &lt; Thursday High condition this week.</p>")
        return

    # Save to Supabase
    if sb and watchlist:
        try:
            # Delete old entries for this Friday
            sb.table('fm_weekly_watchlist')\
              .delete().eq('week_date', watchlist[0]['week_date']).execute()
            sb.table('fm_weekly_watchlist').insert(watchlist).execute()
            print(f"✓ Saved {len(watchlist)} stocks to fm_weekly_watchlist")
        except Exception as e:
            print(f"⚠ Supabase save failed: {e}")

    # Sort by historical win rate
    watchlist.sort(key=lambda x: x['historical_wr_pct'], reverse=True)

    # Build email
    subject = (f"🔍 FM Strategy: {len(watchlist)} Stocks on Watchlist | "
               f"Friday {today.strftime('%d %b %Y')}")
    html = build_friday_email(watchlist, today)
    send_email(cfg, subject, html)

# ─────────────────────────────────────────────────────────────────────────────
# MODE: MONDAY — check gap downs and send trade signals
# ─────────────────────────────────────────────────────────────────────────────
def run_monday_mode(cfg: dict):
    today = date.today()
    print(f"\n{'='*55}")
    print(f"  MONDAY SIGNAL SCAN — {datetime.now().strftime('%d %b %Y %H:%M:%S IST')}")
    print(f"{'='*55}\n")

    sb = get_sb(cfg)
    capital = cfg['trading_capital']
    risk_pct = cfg['risk_per_trade']

    # Load Friday watchlist from Supabase
    watchlist = []
    if sb:
        try:
            # Get most recent Friday watchlist
            rows = sb.table('fm_weekly_watchlist')\
                     .select('*')\
                     .order('week_date', desc=True)\
                     .limit(250)\
                     .execute().data
            if rows:
                latest_friday = rows[0]['week_date']
                watchlist = [r for r in rows if r['week_date'] == latest_friday]
                print(f"Loaded {len(watchlist)} stocks from Friday {latest_friday}\n")
        except Exception as e:
            print(f"⚠ Could not load watchlist: {e}")

    if not watchlist:
        send_email(cfg,
            f"⚡ FM Strategy: No Watchlist Found for Monday {today.strftime('%d %b')}",
            "<p>No Friday watchlist was found. Please check Friday scanner.</p>")
        return

    trade_signals = []

    for item in watchlist:
        symbol     = item['symbol']
        stock_name = item['stock_name']
        print(f"  Checking {stock_name:<30}", end=' ')

        # Get today's 1-min data to get Monday open
        try:
            df_1m = yf.download(symbol, period='1d', interval='1m',
                                 auto_adjust=True, progress=False)
            if isinstance(df_1m.columns, pd.MultiIndex):
                df_1m.columns = df_1m.columns.get_level_values(0)
            if df_1m.empty:
                print("no intraday data")
                continue
            mon_open = float(df_1m['Open'].iloc[0])
        except Exception as e:
            print(f"error: {e}")
            continue

        fri_close = item['fri_close']
        gap_pct   = (mon_open - fri_close) / fri_close * 100

        if gap_pct >= -0.30:
            print(f"gap only {gap_pct:.2f}% — skip")
            continue

        # Trade confirmed
        entry  = mon_open
        stop   = item['fri_high']
        target = item['fri_low']

        if entry >= stop:
            print(f"⚠ entry ≥ stop — skip")
            continue

        risk_per_share = stop - entry
        risk_amount    = capital * risk_pct / 100
        shares         = max(1, int(risk_amount / risk_per_share))
        pos_value      = shares * entry
        profit_pct     = (entry - target) / entry * 100
        risk_pct_trade = (stop - entry) / entry * 100
        rr             = profit_pct / risk_pct_trade if risk_pct_trade > 0 else 0
        cap_risk_pct   = (shares * risk_per_share) / capital * 100

        print(f"✓ GAP {gap_pct:.2f}% | Entry ₹{entry:.2f} | WR {item['historical_wr_pct']:.0f}%")

        trade_signals.append({
            'trade_date':        today.isoformat(),
            'friday_date':       item['week_date'],
            'symbol':            symbol,
            'stock_name':        stock_name,
            'sector':            item['sector'],
            'gap_pct':           round(gap_pct, 4),
            'entry_price':       round(entry, 2),
            'stop_price':        round(stop, 2),
            'target_price':      round(target, 2),
            'position_size':     round(pos_value, 0),
            'shares':            shares,
            'capital_at_risk_pct': round(cap_risk_pct, 2),
            'historical_wr_pct': item['historical_wr_pct'],
            'profit_potential_pct': round(profit_pct, 2),
            'risk_pct_per_trade': round(risk_pct_trade, 2),
            'risk_reward':        round(rr, 2),
            'email_sent_at':      datetime.utcnow().isoformat(),
        })

    print(f"\n✓ {len(trade_signals)} trade signals\n")

    if not trade_signals:
        send_email(cfg,
            f"⚡ FM Strategy: No Gap Down Signals — Monday {today.strftime('%d %b')}",
            "<p>Watchlist stocks scanned. None gapped down >0.3% at open.</p>")
        return

    # Save to Supabase
    if sb:
        try:
            for sig in trade_signals:
                sb.table('fm_live_trades').insert(sig).execute()
            print(f"✓ Saved {len(trade_signals)} trades to fm_live_trades")
        except Exception as e:
            print(f"⚠ Supabase save failed: {e}")

    # Sort by win rate descending
    trade_signals.sort(key=lambda x: x['historical_wr_pct'], reverse=True)

    # Send email
    subject = (f"⚡ FM TRADE SIGNALS NOW — {len(trade_signals)} SHORTS | "
               f"Monday {today.strftime('%d %b %Y')} | Enter before 9:25 AM")
    html = build_monday_email(trade_signals, today, capital)
    send_email(cfg, subject, html)

# ─────────────────────────────────────────────────────────────────────────────
# MODE: EOD — log Monday outcomes
# ─────────────────────────────────────────────────────────────────────────────
def run_eod_mode(cfg: dict):
    today = date.today()
    print(f"\n{'='*55}")
    print(f"  MONDAY EOD PERFORMANCE — {today.strftime('%d %b %Y')}")
    print(f"{'='*55}\n")

    sb = get_sb(cfg)
    if not sb:
        print("No Supabase connection. Exiting.")
        return

    # Load today's live trades
    try:
        rows = sb.table('fm_live_trades')\
                 .select('*')\
                 .eq('trade_date', today.isoformat())\
                 .is_('exit_price', 'null')\
                 .execute().data
    except Exception as e:
        print(f"⚠ Could not load live trades: {e}")
        return

    if not rows:
        print("No open trades found for today.")
        return

    print(f"Found {len(rows)} open trades. Fetching EOD data…\n")
    results = []

    for row in rows:
        symbol     = row['symbol']
        stock_name = row['stock_name']
        entry      = row['entry_price']
        stop       = row['stop_price']
        target     = row['target_price']
        shares     = row['shares']
        pos_size   = row['position_size']

        print(f"  {stock_name:<30}", end=' ')

        try:
            df = yf.download(symbol, period='1d', auto_adjust=True, progress=False)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            if df.empty:
                print("no data")
                continue

            mon_high  = float(df['High'].iloc[-1])
            mon_low   = float(df['Low'].iloc[-1])
            mon_close = float(df['Close'].iloc[-1])
        except Exception as e:
            print(f"error: {e}")
            continue

        # Determine exit (conservative: stop first)
        if mon_high >= stop:
            exit_price = stop
            exit_type  = 'stop'
        elif mon_low <= target:
            exit_price = target
            exit_type  = 'target'
        else:
            exit_price = mon_close
            exit_type  = 'eod'

        gross_pnl_pct = round((entry - exit_price) / entry * 100, 4)
        net_pnl_pct   = round(gross_pnl_pct - 0.05, 4)
        gross_pnl_inr = round(shares * (entry - exit_price), 2)
        net_pnl_inr   = round(gross_pnl_inr - pos_size * 0.0005, 2)
        is_win        = gross_pnl_pct > 0

        icon = '✓' if is_win else '✗'
        print(f"{icon} {exit_type:<6} | Exit ₹{exit_price:.2f} | {gross_pnl_pct:+.2f}% | ₹{gross_pnl_inr:+.0f}")

        # Update Supabase
        try:
            sb.table('fm_live_trades').update({
                'exit_price':        round(exit_price, 2),
                'exit_type':         exit_type,
                'gross_pnl_pct':     gross_pnl_pct,
                'net_pnl_pct':       net_pnl_pct,
                'gross_pnl_inr':     gross_pnl_inr,
                'net_pnl_inr':       net_pnl_inr,
                'is_win':            is_win,
                'outcome_logged_at': datetime.utcnow().isoformat(),
            }).eq('id', row['id']).execute()
        except Exception as e:
            print(f"  ⚠ DB update failed: {e}")

        results.append({**row, 'exit_price': exit_price, 'exit_type': exit_type,
                         'gross_pnl_pct': gross_pnl_pct, 'net_pnl_pct': net_pnl_pct,
                         'gross_pnl_inr': gross_pnl_inr, 'net_pnl_inr': net_pnl_inr,
                         'is_win': is_win})

    # Summary
    wins       = sum(1 for r in results if r['is_win'])
    total_gross = sum(r['gross_pnl_inr'] for r in results)
    total_net   = sum(r['net_pnl_inr'] for r in results)

    print(f"\nToday: {wins}/{len(results)} wins | Gross ₹{total_gross:+.0f} | Net ₹{total_net:+.0f}\n")

    # Log to performance table
    if sb and results:
        try:
            sb.table('fm_performance_log').upsert({
                'log_date':     today.isoformat(),
                'total_signals': len(results),
                'trades_taken':  len(results),
                'wins':          wins,
                'losses':        len(results) - wins,
                'gross_pnl_inr': round(total_gross, 2),
                'net_pnl_inr':   round(total_net, 2),
            }, on_conflict='log_date').execute()
        except Exception as e:
            print(f"⚠ Performance log failed: {e}")

    # Send EOD email
    subject = (f"📊 FM Strategy EOD — Monday {today.strftime('%d %b %Y')} | "
               f"{wins}/{len(results)} Wins | Net ₹{total_net:+,.0f}")
    html = build_eod_email(results, today, total_gross, total_net, wins)
    send_email(cfg, subject, html)

# ── Email HTML builders ───────────────────────────────────────────────────────
def build_friday_email(watchlist: list, today: date) -> str:
    rows_html = ''
    for i, s in enumerate(watchlist, 1):
        wr_color = '#228B22' if s['historical_wr_pct'] >= 60 else ('#CC7722' if s['historical_wr_pct'] >= 50 else '#CC0000')
        bg = '#FFF5F0' if i % 2 == 0 else '#FFFFFF'
        rows_html += f"""
        <tr style="background:{bg};">
          <td style="padding:8px 10px;font-weight:600;">{i}</td>
          <td style="padding:8px 10px;">{s['stock_name']}</td>
          <td style="padding:8px 10px;color:#666;">{s['sector']}</td>
          <td style="padding:8px 10px;">₹{s['fri_close']:.2f}</td>
          <td style="padding:8px 10px;color:#CC0000;">₹{s['fri_high']:.2f}</td>
          <td style="padding:8px 10px;color:#228B22;">₹{s['fri_low']:.2f}</td>
          <td style="padding:8px 10px;">{s['fri_rsi']:.0f}</td>
          <td style="padding:8px 10px;">{s['fri_volume_ratio']:.1f}x</td>
          <td style="padding:8px 10px;font-weight:700;color:{wr_color};">{s['historical_wr_pct']:.1f}%</td>
          <td style="padding:8px 10px;color:#888;">{s['historical_trades']}</td>
        </tr>"""

    return f"""
<html><body style="font-family:Arial,sans-serif;background:#FFF8F0;color:#1A0500;max-width:900px;margin:0 auto;">
  <div style="background:linear-gradient(135deg,#8B0000,#B8860B);padding:24px 32px;border-radius:12px 12px 0 0;">
    <h1 style="color:#FFF;margin:0;font-size:22px;">🔍 Friday Watchlist — {today.strftime('%d %b %Y')}</h1>
    <p style="color:#FFD700;margin:6px 0 0;font-size:14px;">
      {len(watchlist)} stocks with Friday High &lt; Thursday High | Watch for Monday gap down
    </p>
  </div>
  <div style="background:#FFF;padding:24px 32px;">
    <div style="display:flex;gap:20px;margin-bottom:20px;">
      <div style="background:#FFF0E0;padding:12px 20px;border-radius:8px;border-left:4px solid #B8860B;">
        <div style="font-size:11px;color:#888;text-transform:uppercase;letter-spacing:.05em;">Total Setups</div>
        <div style="font-size:24px;font-weight:700;color:#8B0000;">{len(watchlist)}</div>
      </div>
      <div style="background:#FFF0E0;padding:12px 20px;border-radius:8px;border-left:4px solid #B8860B;">
        <div style="font-size:11px;color:#888;text-transform:uppercase;letter-spacing:.05em;">High Conf. (&gt;60% WR)</div>
        <div style="font-size:24px;font-weight:700;color:#8B0000;">{sum(1 for s in watchlist if s['historical_wr_pct'] >= 60)}</div>
      </div>
    </div>
    <h3 style="color:#8B0000;border-bottom:2px solid #FFD700;padding-bottom:8px;">
      ⏰ Action: Check these Monday 9:20 AM for gap down &gt;0.3%
    </h3>
    <table style="width:100%;border-collapse:collapse;font-size:13px;">
      <thead>
        <tr style="background:#8B0000;color:#FFD700;">
          <th style="padding:10px;">#</th>
          <th style="padding:10px;text-align:left;">Stock</th>
          <th style="padding:10px;text-align:left;">Sector</th>
          <th style="padding:10px;">Fri Close</th>
          <th style="padding:10px;">SL Level (Fri H)</th>
          <th style="padding:10px;">Target (Fri L)</th>
          <th style="padding:10px;">RSI</th>
          <th style="padding:10px;">Vol Ratio</th>
          <th style="padding:10px;">Hist WR%</th>
          <th style="padding:10px;"># Trades</th>
        </tr>
      </thead>
      <tbody>{rows_html}</tbody>
    </table>
    <div style="background:#FFF3CD;border:1px solid #FFD700;border-radius:8px;padding:16px;margin-top:20px;">
      <strong>⚡ Monday Morning Protocol:</strong><br>
      At 9:20 AM — check which of these gapped down &gt;0.3% from Fri close.<br>
      SHORT at Monday open | Stop = Friday High | Target = Friday Low | Max 5 trades | 1% risk per trade
    </div>
  </div>
  <div style="background:#F5F5F5;padding:12px 32px;font-size:11px;color:#888;text-align:center;">
    FM Strategy Automation | {today.strftime('%d %b %Y')} | For personal trading use only. Not investment advice.
  </div>
</body></html>"""

def build_monday_email(signals: list, today: date, capital: float) -> str:
    rows_html = ''
    for i, t in enumerate(signals, 1):
        wr_color = '#228B22' if t['historical_wr_pct'] >= 60 else '#CC7722'
        bg = '#FFF5F0' if i % 2 == 0 else '#FFFFFF'
        rows_html += f"""
        <tr style="background:{bg};">
          <td style="padding:8px 10px;font-weight:700;color:#8B0000;">{i}</td>
          <td style="padding:8px 10px;font-weight:700;">{t['stock_name']}</td>
          <td style="padding:8px 10px;color:#666;">{t['sector']}</td>
          <td style="padding:8px 10px;color:#CC0000;font-weight:700;">{t['gap_pct']:.2f}%</td>
          <td style="padding:8px 10px;font-weight:700;">₹{t['entry_price']:.2f}</td>
          <td style="padding:8px 10px;color:#CC0000;">₹{t['stop_price']:.2f}</td>
          <td style="padding:8px 10px;color:#228B22;">₹{t['target_price']:.2f}</td>
          <td style="padding:8px 10px;">{t['shares']:,}</td>
          <td style="padding:8px 10px;">₹{t['position_size']:,.0f}</td>
          <td style="padding:8px 10px;">{t['risk_reward']:.1f}x</td>
          <td style="padding:8px 10px;font-weight:700;color:{wr_color};">{t['historical_wr_pct']:.1f}%</td>
        </tr>"""

    total_risk = sum(t['position_size'] * t['risk_pct_per_trade'] / 100 for t in signals)

    return f"""
<html><body style="font-family:Arial,sans-serif;background:#FFF8F0;color:#1A0500;max-width:900px;margin:0 auto;">
  <div style="background:linear-gradient(135deg,#8B0000,#B8860B);padding:24px 32px;border-radius:12px 12px 0 0;">
    <h1 style="color:#FFD700;margin:0;font-size:22px;">⚡ TRADE SIGNALS — {today.strftime('%d %b %Y')} 9:20 AM</h1>
    <p style="color:#FFF;margin:6px 0 0;font-size:15px;font-weight:700;">
      {len(signals)} SHORT trade{'s' if len(signals) != 1 else ''} confirmed | ENTER BEFORE 9:25 AM
    </p>
  </div>
  <div style="background:#FFF;padding:24px 32px;">
    <div style="background:#FFE4E4;border:2px solid #CC0000;border-radius:8px;padding:16px;margin-bottom:20px;">
      <strong style="color:#CC0000;font-size:15px;">🚨 TIME SENSITIVE — Execute within 5-10 minutes of market open</strong><br>
      <span style="font-size:13px;">Entry = Monday Open Price shown below | Stop = Friday High | Target = Friday Low</span>
    </div>
    <table style="width:100%;border-collapse:collapse;font-size:13px;">
      <thead>
        <tr style="background:#8B0000;color:#FFD700;">
          <th style="padding:10px;">#</th>
          <th style="padding:10px;text-align:left;">Stock</th>
          <th style="padding:10px;text-align:left;">Sector</th>
          <th style="padding:10px;">Gap%</th>
          <th style="padding:10px;">SHORT @ Entry</th>
          <th style="padding:10px;">Stop Loss</th>
          <th style="padding:10px;">Target</th>
          <th style="padding:10px;">Qty</th>
          <th style="padding:10px;">Position ₹</th>
          <th style="padding:10px;">R:R</th>
          <th style="padding:10px;">Hist WR%</th>
        </tr>
      </thead>
      <tbody>{rows_html}</tbody>
    </table>
    <div style="background:#F0FFF0;border:1px solid #228B22;border-radius:8px;padding:16px;margin-top:20px;">
      <strong style="color:#228B22;">📊 Risk Summary</strong><br>
      Capital: ₹{capital:,.0f} | Trades: {len(signals)} | Total Capital at Risk: ₹{total_risk:,.0f} | Max 5 concurrent trades
    </div>
    <div style="background:#FFF3CD;border:1px solid #FFD700;border-radius:8px;padding:16px;margin-top:12px;">
      <strong>📋 Trade Rules Reminder:</strong><br>
      ✓ SHORT (sell) at the entry price shown<br>
      ✓ Set STOP LOSS at the Friday High level shown (mandatory)<br>
      ✓ Set TARGET at the Friday Low level shown<br>
      ✓ If neither hits by 3:20 PM → EXIT at market (Monday close)<br>
      ✓ Stop hit = exit immediately, no averaging
    </div>
  </div>
  <div style="background:#F5F5F5;padding:12px 32px;font-size:11px;color:#888;text-align:center;">
    FM Strategy Automation | {today.strftime('%d %b %Y')} | Not investment advice.
  </div>
</body></html>"""

def build_eod_email(results: list, today: date, total_gross: float, total_net: float, wins: int) -> str:
    rows_html = ''
    for t in results:
        icon = '✅' if t['is_win'] else '❌'
        bg   = '#F0FFF0' if t['is_win'] else '#FFF0F0'
        pnl_color = '#228B22' if t['is_win'] else '#CC0000'
        rows_html += f"""
        <tr style="background:{bg};">
          <td style="padding:8px 10px;">{icon}</td>
          <td style="padding:8px 10px;font-weight:600;">{t['stock_name']}</td>
          <td style="padding:8px 10px;">{t.get('exit_type','—')}</td>
          <td style="padding:8px 10px;">₹{t['entry_price']:.2f}</td>
          <td style="padding:8px 10px;">₹{t['exit_price']:.2f}</td>
          <td style="padding:8px 10px;font-weight:700;color:{pnl_color};">{t['gross_pnl_pct']:+.2f}%</td>
          <td style="padding:8px 10px;font-weight:700;color:{pnl_color};">₹{t['gross_pnl_inr']:+,.0f}</td>
        </tr>"""

    summary_color = '#228B22' if total_net >= 0 else '#CC0000'
    return f"""
<html><body style="font-family:Arial,sans-serif;background:#FFF8F0;color:#1A0500;max-width:800px;margin:0 auto;">
  <div style="background:linear-gradient(135deg,#8B0000,#B8860B);padding:24px 32px;border-radius:12px 12px 0 0;">
    <h1 style="color:#FFD700;margin:0;font-size:22px;">📊 EOD Performance — Monday {today.strftime('%d %b %Y')}</h1>
    <p style="color:#FFF;margin:6px 0 0;font-size:15px;">
      {wins}/{len(results)} Wins | Gross ₹{total_gross:+,.0f} | Net ₹{total_net:+,.0f}
    </p>
  </div>
  <div style="background:#FFF;padding:24px 32px;">
    <div style="display:flex;gap:20px;margin-bottom:20px;">
      <div style="background:#FFF0E0;padding:12px 20px;border-radius:8px;border-left:4px solid #B8860B;flex:1;">
        <div style="font-size:11px;color:#888;text-transform:uppercase;">Win Rate</div>
        <div style="font-size:28px;font-weight:700;color:#8B0000;">{wins}/{len(results)} ({wins/len(results)*100:.0f}%)</div>
      </div>
      <div style="background:#FFF0E0;padding:12px 20px;border-radius:8px;border-left:4px solid #228B22;flex:1;">
        <div style="font-size:11px;color:#888;text-transform:uppercase;">Net P&L Today</div>
        <div style="font-size:28px;font-weight:700;color:{summary_color};">₹{total_net:+,.0f}</div>
      </div>
    </div>
    <table style="width:100%;border-collapse:collapse;font-size:13px;">
      <thead>
        <tr style="background:#8B0000;color:#FFD700;">
          <th style="padding:10px;"></th>
          <th style="padding:10px;text-align:left;">Stock</th>
          <th style="padding:10px;">Exit Type</th>
          <th style="padding:10px;">Entry</th>
          <th style="padding:10px;">Exit</th>
          <th style="padding:10px;">Gross %</th>
          <th style="padding:10px;">Gross ₹</th>
        </tr>
      </thead>
      <tbody>{rows_html}</tbody>
    </table>
  </div>
  <div style="background:#F5F5F5;padding:12px 32px;font-size:11px;color:#888;text-align:center;">
    FM Strategy Automation | {today.strftime('%d %b %Y')} | Not investment advice.
  </div>
</body></html>"""

# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['friday', 'monday', 'eod'], required=True)
    args = parser.parse_args()

    cfg = get_config()
    if args.mode == 'friday':
        run_friday_mode(cfg)
    elif args.mode == 'monday':
        run_monday_mode(cfg)
    elif args.mode == 'eod':
        run_eod_mode(cfg)
