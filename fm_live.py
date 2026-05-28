"""
FRIDAY-MONDAY LIVE SCANNER
Runs via GitHub Actions:
  Friday  3:30 PM IST → Friday scan → save watchlist → send email
  Monday  9:20 AM IST → Monday scan → trade signals → send email
  Monday  3:35 PM IST → EOD performance capture → update signals
"""

import os, sys, json, time, smtplib, argparse
from datetime import date, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pandas as pd
import numpy as np
import yfinance as yf
import warnings
warnings.filterwarnings('ignore')

try:
    from supabase import create_client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False

from nifty250_stocks import NIFTY_250_STOCKS, SYMBOL_TO_NAME, SYMBOL_TO_SECTOR
from backtest_engine import download_batch, compute_rsi, compute_volume_ratio

# ── Config from environment ───────────────────────────────────────────────────
SUPABASE_URL    = os.environ.get('SUPABASE_URL', '')
SUPABASE_KEY    = os.environ.get('SUPABASE_KEY', '')
SENDER_EMAIL    = os.environ.get('SENDER_EMAIL', '')
SENDER_PASSWORD = os.environ.get('SENDER_PASSWORD', '')
RECIPIENT_EMAIL = os.environ.get('RECIPIENT_EMAIL', '')

GAP_THRESHOLD = -0.30   # gap down must be at least 0.30%
MAX_STOP_WIDTH = 3.0    # % — warn if wider

# ── Supabase client ───────────────────────────────────────────────────────────
def get_sb():
    if SUPABASE_AVAILABLE and SUPABASE_URL and SUPABASE_KEY:
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    return None

# ── Get Nifty regime ──────────────────────────────────────────────────────────
def get_market_regime():
    try:
        nifty = yf.download('^NSEI', period='2y', auto_adjust=True, progress=False)
        if isinstance(nifty.columns, pd.MultiIndex):
            for lvl in range(nifty.columns.nlevels):
                if 'Close' in nifty.columns.get_level_values(lvl):
                    nifty.columns = nifty.columns.get_level_values(lvl); break
        close  = nifty['Close'].dropna()
        sma200 = close.rolling(200).mean()
        sma50  = close.rolling(50).mean()
        last   = float(close.iloc[-1])
        s200   = float(sma200.iloc[-1])
        s50    = float(sma50.iloc[-1])
        if last < s200 * 0.95:   return 'bear',   last, s200, s50
        if last > s200 * 1.05:   return 'bull',   last, s200, s50
        return 'sideways', last, s200, s50
    except Exception as e:
        print(f"  Regime fetch failed: {e}")
        return 'unknown', 0, 0, 0

# ── Load historical stock stats from backtest ─────────────────────────────────
def load_stock_stats():
    try:
        summary = pd.read_csv('backtest_summary.csv')
        trades  = pd.read_csv('backtest_trades.csv')
        # Valid trades only
        trades = trades[trades['entry_price'] > trades['target_price']]
        stats  = trades.groupby('symbol').agg(
            hist_wr     = ('is_win', lambda x: x.mean()*100),
            hist_avg    = ('gross_pnl_pct', 'mean'),
            hist_trades = ('is_win', 'count'),
        ).reset_index()
        return {row['symbol']: row for _, row in stats.iterrows()}
    except Exception:
        return {}

# ════════════════════════════════════════════════════════════════════════════
# FRIDAY SCAN
# ════════════════════════════════════════════════════════════════════════════
def run_friday_scan(scan_date: date = None) -> list:
    scan_date = scan_date or date.today()
    print(f"\n{'='*60}")
    print(f"  FRIDAY SCAN — {scan_date}")
    print(f"{'='*60}\n")

    stock_stats = load_stock_stats()
    symbols     = list(NIFTY_250_STOCKS.keys())

    # Download ~65 days of data for all 250 stocks
    end   = scan_date.strftime('%Y-%m-%d')
    start = (scan_date - timedelta(days=65)).strftime('%Y-%m-%d')

    print(f"Downloading {len(symbols)} stocks ({start} → {end})…")
    t0 = time.time()
    # Download in batches of 60 for speed
    all_data = {}
    for batch in [symbols[i:i+65] for i in range(0, len(symbols), 65)]:
        all_data.update(download_batch(batch, start, end))
    print(f"  → {len(all_data)} stocks downloaded in {time.time()-t0:.1f}s\n")

    watchlist = []

    for sym, df in all_data.items():
        if len(df) < 10:
            continue
        df = df.sort_index()
        try:
            df['RSI']      = compute_rsi(df['Close'])
            df['VolRatio'] = compute_volume_ratio(df['Volume'])
            df['SMA20']    = df['Close'].rolling(20).mean()

            # Find the most recent Friday in the data
            fridays = df[df.index.dayofweek == 4]
            if len(fridays) == 0:
                continue
            last_fri     = fridays.index[-1]
            # Must be within last 4 days
            if (pd.Timestamp(scan_date) - last_fri).days > 4:
                continue

            fri = df.loc[last_fri]

            # Find reference day: Thursday, or Wednesday if Thursday is holiday
            prev = df[df.index < last_fri].tail(6)
            ref  = None
            ref_type = None
            for j in range(len(prev)-1, -1, -1):
                d = prev.index[j]
                if d.weekday() == 3:
                    ref = prev.iloc[j]; ref_type = 'thursday'; break
                if d.weekday() == 2:
                    thu_date = d + timedelta(days=1)
                    if thu_date not in df.index:
                        ref = prev.iloc[j]; ref_type = 'wednesday'; break
                    break
            if ref is None:
                continue

            # Pattern condition: Friday High < Reference High
            if float(fri['High']) >= float(ref['High']):
                continue

            symbol_clean = sym.replace('.NS', '')
            stats = stock_stats.get(symbol_clean, {})

            entry = watchlist.append({
                'scan_date':         scan_date.isoformat(),
                'symbol':            symbol_clean,
                'stock_name':        SYMBOL_TO_NAME.get(sym, symbol_clean),
                'sector':            SYMBOL_TO_SECTOR.get(sym, 'Unknown'),
                'tier':              NIFTY_250_STOCKS.get(sym, {}).get('tier', 'mid'),
                'ref_day_type':      ref_type,
                'ref_day_high':      round(float(ref['High']), 2),
                'fri_high':          round(float(fri['High']), 2),
                'fri_low':           round(float(fri['Low']), 2),
                'fri_close':         round(float(fri['Close']), 2),
                'fri_rsi':           round(float(fri['RSI']), 1) if not pd.isna(fri['RSI']) else None,
                'fri_volume_ratio':  round(float(fri['VolRatio']), 3) if not pd.isna(fri['VolRatio']) else None,
                'fri_above_sma20':   bool(float(fri['Close']) > float(fri['SMA20'])) if not pd.isna(fri['SMA20']) else None,
                'hist_win_rate':     round(float(stats.get('hist_wr', 0)), 1) if stats else None,
                'hist_avg_gross':    round(float(stats.get('hist_avg', 0)), 3) if stats else None,
                'hist_total_trades': int(stats.get('hist_trades', 0)) if stats else None,
                'priority_tier':     'HIGH' if (stats and float(stats.get('hist_wr', 0)) > 45) else
                                     'MED'  if (stats and float(stats.get('hist_wr', 0)) > 35) else 'LOW',
            })

        except Exception as ex:
            continue

    watchlist.sort(key=lambda x: -(x.get('hist_win_rate') or 0))
    print(f"  ✓ Found {len(watchlist)} Friday setup stocks\n")

    # Save to Supabase
    sb = get_sb()
    if sb and watchlist:
        try:
            # Delete old entries for this scan_date
            sb.table('fm_friday_watchlist').delete().eq('scan_date', scan_date.isoformat()).execute()
            # Insert new ones
            for i in range(0, len(watchlist), 50):
                sb.table('fm_friday_watchlist').insert(watchlist[i:i+50]).execute()
            print(f"  ✓ Saved to Supabase fm_friday_watchlist ({len(watchlist)} rows)")
        except Exception as e:
            print(f"  ⚠ Supabase error: {e}")

    # Log run
    if sb:
        try:
            sb.table('fm_scan_log').insert({
                'run_type': 'friday',
                'stocks_scanned': len(symbols),
                'signals_generated': len(watchlist),
                'notes': f"Scan date: {scan_date}"
            }).execute()
        except:
            pass

    return watchlist

# ════════════════════════════════════════════════════════════════════════════
# MONDAY SCAN  (9:20 AM — MUST complete within 60 seconds)
# ════════════════════════════════════════════════════════════════════════════
def run_monday_scan(signal_date: date = None) -> list:
    signal_date = signal_date or date.today()
    print(f"\n{'='*60}")
    print(f"  MONDAY SCAN — {signal_date}  (speed-critical!)")
    print(f"{'='*60}\n")

    t_start = time.time()

    # Load Friday watchlist
    sb = get_sb()
    watchlist = []

    if sb:
        try:
            # Get most recent Friday watchlist (within last 5 days)
            cutoff = (signal_date - timedelta(days=5)).isoformat()
            res = sb.table('fm_friday_watchlist').select('*').gte('scan_date', cutoff).execute()
            watchlist = res.data if res.data else []
            print(f"  Loaded {len(watchlist)} stocks from Supabase watchlist")
        except Exception as e:
            print(f"  ⚠ Could not load from Supabase: {e}")

    if not watchlist:
        # Fallback: run Friday scan inline
        last_friday = signal_date - timedelta(days=signal_date.weekday() + 3)
        watchlist = run_friday_scan(last_friday)

    if not watchlist:
        print("  ✗ No watchlist stocks. Exiting Monday scan.")
        return []

    symbols = [w['symbol'] + '.NS' for w in watchlist]
    print(f"  Downloading {len(symbols)} watchlist stocks only (fast!)…")

    # Download only today + yesterday for speed
    start = (signal_date - timedelta(days=3)).strftime('%Y-%m-%d')
    end   = signal_date.strftime('%Y-%m-%d')
    all_data = download_batch(symbols, start, end)
    print(f"  → {len(all_data)} stocks, {time.time()-t_start:.1f}s elapsed\n")

    # Regime
    regime, nifty_last, nifty_s200, nifty_s50 = get_market_regime()
    print(f"  Regime: {regime.upper()} | Nifty: {nifty_last:.0f} | 200-DMA: {nifty_s200:.0f}")

    stock_stats = load_stock_stats()
    signals = []

    for item in watchlist:
        sym = item['symbol'] + '.NS'
        if sym not in all_data:
            continue
        df = all_data[sym].sort_index()
        if len(df) == 0:
            continue

        # Get today's open (if market is open) or most recent Monday
        mondays = df[df.index.dayofweek == 0]
        if len(mondays) == 0:
            continue
        last_mon = mondays.index[-1]
        if last_mon.date() < signal_date - timedelta(days=2):
            continue  # Too old

        mon = df.loc[last_mon]
        entry  = float(mon['Open'])
        fri_close = item['fri_close']
        fri_low   = item['fri_low']
        fri_high  = item['fri_high']

        if entry <= 0 or fri_close <= 0:
            continue

        gap_pct = (entry - fri_close) / fri_close * 100

        # Must gap down
        if gap_pct >= GAP_THRESHOLD:
            continue

        # Entry must be above target
        if entry <= fri_low:
            print(f"  SKIP {item['symbol']}: Entry {entry:.2f} ≤ Target {fri_low:.2f} (large gap)")
            continue

        stop    = fri_high
        target  = fri_low
        risk    = (stop - entry) / entry * 100
        reward  = (entry - target) / entry * 100
        rr      = reward / risk if risk > 0 else 0
        warn    = "⚠️ WIDE STOP" if risk > MAX_STOP_WIDTH else ""

        hist    = stock_stats.get(item['symbol'], {})
        hist_wr = float(hist.get('hist_wr', 0)) if hist else 0

        signals.append({
            'signal_date':   signal_date.isoformat(),
            'symbol':        item['symbol'],
            'stock_name':    item['stock_name'],
            'sector':        item['sector'],
            'gap_pct':       round(gap_pct, 3),
            'entry_price':   round(entry, 2),
            'target_price':  round(target, 2),
            'stop_price':    round(stop, 2),
            'potential_pct': round(reward, 3),
            'risk_pct':      round(risk, 3),
            'rr_ratio':      round(rr, 3),
            'hist_win_rate': round(hist_wr, 1),
            'regime':        regime,
            'warn':          warn,
            'status':        'open',
        })

    signals.sort(key=lambda x: -x['hist_win_rate'])
    elapsed = time.time() - t_start
    print(f"\n  ✓ {len(signals)} trade signals | Total time: {elapsed:.1f}s\n")

    if elapsed > 55:
        print("  ⚠ WARNING: Scan took >55s. Email might be delayed past 9:21 AM.")

    # Save to Supabase
    if sb and signals:
        try:
            for sig in signals:
                s = {k: v for k, v in sig.items() if k != 'warn'}
                sb.table('fm_monday_signals').upsert(s, on_conflict='signal_date,symbol').execute()
            print(f"  ✓ Saved {len(signals)} signals to Supabase")
        except Exception as e:
            print(f"  ⚠ Supabase: {e}")

    if sb:
        try:
            sb.table('fm_scan_log').insert({
                'run_type': 'monday_signals',
                'stocks_scanned': len(watchlist),
                'signals_generated': len(signals),
                'notes': f"Regime: {regime} | Elapsed: {elapsed:.1f}s"
            }).execute()
        except:
            pass

    return signals

# ════════════════════════════════════════════════════════════════════════════
# MONDAY EOD PERFORMANCE CAPTURE
# ════════════════════════════════════════════════════════════════════════════
def run_monday_performance(perf_date: date = None):
    perf_date = perf_date or date.today()
    print(f"\n{'='*60}")
    print(f"  MONDAY EOD PERFORMANCE CAPTURE — {perf_date}")
    print(f"{'='*60}\n")

    sb = get_sb()
    if not sb:
        print("  ✗ Supabase not available")
        return []

    # Get today's open signals
    try:
        res = sb.table('fm_monday_signals').select('*')\
            .eq('signal_date', perf_date.isoformat()).eq('status', 'open').execute()
        open_signals = res.data if res.data else []
    except Exception as e:
        print(f"  ✗ Could not load signals: {e}")
        return []

    if not open_signals:
        print("  No open signals for today.")
        return []

    print(f"  Found {len(open_signals)} open signals. Fetching EOD data…")
    symbols = [s['symbol'] + '.NS' for s in open_signals]
    start   = perf_date.strftime('%Y-%m-%d')
    end     = (perf_date + timedelta(days=1)).strftime('%Y-%m-%d')
    all_data = download_batch(symbols, start, end)

    outcomes = []
    for sig in open_signals:
        sym = sig['symbol'] + '.NS'
        if sym not in all_data:
            continue
        df = all_data[sym]
        if len(df) == 0:
            continue

        row = df.iloc[0]  # Today's bar
        entry  = sig['entry_price']
        stop   = sig['stop_price']
        target = sig['target_price']

        # Determine exit (conservative: stop first)
        if float(row['High']) >= stop:
            exit_p = stop; exit_t = 'stop'
        elif float(row['Low']) <= target:
            exit_p = target; exit_t = 'target'
        else:
            exit_p = float(row['Close']); exit_t = 'eod'

        pnl = (entry - exit_p) / entry * 100

        try:
            sb.table('fm_monday_signals').update({
                'status': 'closed',
                'actual_exit_price': round(exit_p, 2),
                'actual_exit_type':  exit_t,
                'actual_pnl_pct':    round(pnl, 3),
            }).eq('id', sig['id']).execute()
        except Exception as e:
            print(f"  ⚠ Could not update {sig['symbol']}: {e}")

        outcomes.append({
            'symbol': sig['symbol'],
            'entry': entry, 'exit': round(exit_p,2),
            'exit_type': exit_t, 'pnl': round(pnl,3),
        })
        print(f"  {sig['symbol']:12} → {exit_t:6} @ {exit_p:.2f} | P&L: {pnl:+.3f}%")

    if sb:
        try:
            sb.table('fm_scan_log').insert({
                'run_type': 'monday_performance',
                'stocks_scanned': len(open_signals),
                'signals_generated': len(outcomes),
                'notes': f"Captured {len(outcomes)} trade outcomes for {perf_date}"
            }).execute()
        except:
            pass

    return outcomes

# ════════════════════════════════════════════════════════════════════════════
# EMAIL GENERATION
# ════════════════════════════════════════════════════════════════════════════
def send_email(subject: str, html_body: str, text_body: str = ""):
    if not all([SENDER_EMAIL, SENDER_PASSWORD, RECIPIENT_EMAIL]):
        print("  ⚠ Email credentials not set. Skipping email.")
        return False
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From']    = f"FM Trading System <{SENDER_EMAIL}>"
        msg['To']      = RECIPIENT_EMAIL
        if text_body:
            msg.attach(MIMEText(text_body, 'plain'))
        msg.attach(MIMEText(html_body, 'html'))
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(SENDER_EMAIL, SENDER_PASSWORD)
            smtp.sendmail(SENDER_EMAIL, RECIPIENT_EMAIL, msg.as_string())
        print(f"  ✓ Email sent to {RECIPIENT_EMAIL}")
        return True
    except Exception as e:
        print(f"  ✗ Email failed: {e}")
        return False

def friday_email_html(watchlist: list, regime: str, scan_date: date) -> str:
    regime_color = {'bear':'#1a6b3c', 'sideways':'#9a6b1a', 'bull':'#B5282A'}.get(regime, '#666')
    regime_label = {'bear':'🐻 BEAR — Best for strategy',
                    'sideways':'➡️ SIDEWAYS — Trade cautiously',
                    'bull':'🐂 BULL — Avoid strategy'}.get(regime, regime.upper())

    rows = ""
    for i, w in enumerate(watchlist[:30], 1):
        tier_badge = {'HIGH':'🔴','MED':'🟡','LOW':'⚪'}.get(w.get('priority_tier','LOW'),'⚪')
        wr = w.get('hist_win_rate')
        wr_str = f"{wr:.1f}%" if wr else "—"
        wr_color = '#1a6b3c' if wr and wr >= 40 else '#9a6b1a' if wr and wr >= 30 else '#B5282A'
        rsi = w.get('fri_rsi')
        rows += f"""<tr style="background:{'#fff8f5' if i%2 else '#fff'};">
            <td style="padding:8px;font-weight:600;">{tier_badge} {w['symbol']}</td>
            <td style="padding:8px;font-size:12px;color:#666;">{w['sector']}</td>
            <td style="padding:8px;">{w['ref_day_type'][:3].title()}</td>
            <td style="padding:8px;">₹{w['fri_high']:.2f}</td>
            <td style="padding:8px;">₹{w['fri_low']:.2f}</td>
            <td style="padding:8px;">₹{w['fri_close']:.2f}</td>
            <td style="padding:8px;color:#666;">{f"{rsi:.0f}" if rsi else "—"}</td>
            <td style="padding:8px;font-weight:600;color:{wr_color};">{wr_str}</td>
        </tr>"""

    return f"""<!DOCTYPE html><html><body style="font-family:Inter,sans-serif;background:#fffaf6;margin:0;padding:20px;">
<div style="max-width:700px;margin:auto;background:white;border-radius:12px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.08);">
  <div style="background:linear-gradient(135deg,#B5282A,#8a1a1c);padding:24px 28px;">
    <div style="color:white;font-size:22px;font-weight:700;">📉 FM Pattern Scanner</div>
    <div style="color:#f5c6c6;font-size:14px;margin-top:4px;">{scan_date.strftime('%A, %d %B %Y')} — Friday Watchlist</div>
  </div>
  <div style="padding:20px 28px;">
    <div style="background:#fff3e0;border-left:4px solid {regime_color};padding:12px 16px;border-radius:0 8px 8px 0;margin-bottom:16px;">
      <div style="font-weight:600;color:{regime_color};">Current Market Regime: {regime_label}</div>
    </div>
    <div style="font-size:13px;color:#4a3028;margin-bottom:16px;">
      Found <strong>{len(watchlist)}</strong> stocks where Friday High &lt; Thursday/Wednesday High. 
      Set alert for Monday 9:20 AM — trade signals will arrive within 60 seconds.
    </div>
    <table style="width:100%;border-collapse:collapse;font-size:12px;">
      <thead>
        <tr style="background:#B5282A;color:white;">
          <th style="padding:10px 8px;text-align:left;">Stock</th>
          <th style="padding:10px 8px;">Sector</th>
          <th style="padding:10px 8px;">Ref Day</th>
          <th style="padding:10px 8px;">Fri High</th>
          <th style="padding:10px 8px;">Fri Low</th>
          <th style="padding:10px 8px;">Fri Close</th>
          <th style="padding:10px 8px;">RSI</th>
          <th style="padding:10px 8px;">Hist WR</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
    <div style="margin-top:20px;padding:12px;background:#fff8f5;border-radius:8px;font-size:11px;color:#7a5c4e;">
      ⚠️ Monday entry only if: gap down &gt;0.3% AND Monday Open &gt; Friday Low (entry above target). 
      Stop = Friday High. Target = Friday Low. Exit = Monday Close if neither hit.
    </div>
  </div>
</div></body></html>"""

def monday_email_html(signals: list, regime: str, signal_date: date, capital: float = 500000, risk_pct: float = 1.0) -> str:
    if not signals:
        return f"<p>No trade signals for {signal_date}. No gap-downs found from Friday watchlist.</p>"

    regime_color = {'bear':'#1a6b3c', 'sideways':'#9a6b1a', 'bull':'#B5282A'}.get(regime, '#666')
    rows = ""
    for i, s in enumerate(signals, 1):
        rr = s.get('rr_ratio', 0)
        risk = s.get('risk_pct', 0)
        reward = s.get('potential_pct', 0)
        wr = s.get('hist_win_rate', 0)
        shares = max(1, int((capital * risk_pct/100) / (s['entry_price'] * risk/100))) if risk > 0 else 0
        inv = round(shares * s['entry_price'], 0)
        warn = s.get('warn', '')
        row_bg = '#fff8f0' if warn else ('#f5fff8' if i%2 else '#fff')
        rows += f"""<tr style="background:{row_bg};">
            <td style="padding:10px 8px;font-weight:700;font-size:14px;">{s['symbol']}</td>
            <td style="padding:10px 8px;font-size:12px;color:#666;">{s['sector']}</td>
            <td style="padding:10px 8px;color:#B5282A;font-weight:600;">{s['gap_pct']:.2f}%</td>
            <td style="padding:10px 8px;font-weight:700;">₹{s['entry_price']:.2f}</td>
            <td style="padding:10px 8px;color:#1a6b3c;font-weight:600;">₹{s['target_price']:.2f}</td>
            <td style="padding:10px 8px;color:#B5282A;font-weight:600;">₹{s['stop_price']:.2f}</td>
            <td style="padding:10px 8px;">{reward:.2f}% / {risk:.2f}%</td>
            <td style="padding:10px 8px;{'color:#B5282A;font-weight:600;' if rr < 0.5 else ''}">{rr:.2f}x</td>
            <td style="padding:10px 8px;">{wr:.0f}%</td>
            <td style="padding:10px 8px;font-size:11px;">{shares} sh<br>₹{inv:,.0f}</td>
            <td style="padding:10px 8px;font-size:11px;color:#9a6b1a;">{warn}</td>
        </tr>"""

    regime_label = {'bear':'🐻 BEAR — Full trade', 'sideways':'➡️ SIDEWAYS — Cautious',
                    'bull':'🐂 BULL — Avoid'}.get(regime, regime)

    return f"""<!DOCTYPE html><html><body style="font-family:Inter,sans-serif;background:#fffaf6;margin:0;padding:20px;">
<div style="max-width:800px;margin:auto;background:white;border-radius:12px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.08);">
  <div style="background:linear-gradient(135deg,#B5282A,#8a1a1c);padding:24px 28px;">
    <div style="color:white;font-size:22px;font-weight:700;">⚡ TRADE SIGNALS — EXECUTE NOW</div>
    <div style="color:#f5c6c6;font-size:14px;margin-top:4px;">{signal_date.strftime('%A, %d %B %Y')} — 9:20 AM IST</div>
  </div>
  <div style="padding:20px 28px;">
    <div style="background:#fff3e0;border-left:4px solid {regime_color};padding:12px 16px;border-radius:0 8px 8px 0;margin-bottom:16px;font-weight:600;color:{regime_color};">
      Regime: {regime_label}
    </div>
    <div style="font-size:13px;color:#4a3028;margin-bottom:16px;padding:10px;background:#fff5f0;border-radius:8px;">
      🕐 <strong>Enter within 5 minutes</strong> at market price. SHORT with target = Friday Low, Stop = Friday High.
    </div>
    <table style="width:100%;border-collapse:collapse;font-size:12px;">
      <thead>
        <tr style="background:#B5282A;color:white;">
          <th style="padding:10px 8px;text-align:left;">Stock</th>
          <th style="padding:10px 8px;">Sector</th>
          <th style="padding:10px 8px;">Gap↓</th>
          <th style="padding:10px 8px;">Entry</th>
          <th style="padding:10px 8px;">Target ↓</th>
          <th style="padding:10px 8px;">Stop ↑</th>
          <th style="padding:10px 8px;">Rwd/Risk</th>
          <th style="padding:10px 8px;">R:R</th>
          <th style="padding:10px 8px;">Hist WR</th>
          <th style="padding:10px 8px;">Position</th>
          <th style="padding:10px 8px;">Note</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
    <div style="margin-top:20px;padding:12px;background:#fff8f5;border-radius:8px;font-size:11px;color:#7a5c4e;">
      ⚠️ If Stop Width &gt;1.5% — reduce position size by 50%. Skip if R:R &lt; 0.3. 
      Based on ₹{capital:,.0f} capital with {risk_pct}% risk per trade.
      EOD performance email will arrive at 3:35 PM IST.
    </div>
  </div>
</div></body></html>"""

def performance_email_html(outcomes: list, perf_date: date) -> str:
    if not outcomes:
        return f"<p>No performance data captured for {perf_date}.</p>"
    wins = [o for o in outcomes if o['pnl'] > 0]
    losses = [o for o in outcomes if o['pnl'] <= 0]
    total_pnl = sum(o['pnl'] for o in outcomes)
    rows = ""
    for o in outcomes:
        color = '#1a6b3c' if o['pnl'] > 0 else '#B5282A'
        badge = '✅' if o['pnl'] > 0 else '❌'
        rows += f"""<tr style="background:{'#f5fff8' if o['pnl']>0 else '#fff8f5'};">
            <td style="padding:8px;font-weight:600;">{badge} {o['symbol']}</td>
            <td style="padding:8px;">₹{o['entry']:.2f}</td>
            <td style="padding:8px;">₹{o['exit']:.2f}</td>
            <td style="padding:8px;">{o['exit_type'].upper()}</td>
            <td style="padding:8px;font-weight:700;color:{color};">{o['pnl']:+.3f}%</td>
        </tr>"""

    return f"""<!DOCTYPE html><html><body style="font-family:Inter,sans-serif;background:#fffaf6;margin:0;padding:20px;">
<div style="max-width:600px;margin:auto;background:white;border-radius:12px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.08);">
  <div style="background:linear-gradient(135deg,#8a1a1c,#B5282A);padding:24px 28px;">
    <div style="color:white;font-size:20px;font-weight:700;">📊 Monday EOD Performance</div>
    <div style="color:#f5c6c6;font-size:13px;margin-top:4px;">{perf_date.strftime('%A, %d %B %Y')} — 3:35 PM IST</div>
  </div>
  <div style="padding:20px 28px;">
    <div style="display:flex;gap:16px;margin-bottom:16px;">
      <div style="flex:1;background:#f5fff8;border-radius:8px;padding:12px;text-align:center;">
        <div style="font-size:24px;font-weight:700;color:#1a6b3c;">{len(wins)}</div>
        <div style="font-size:12px;color:#666;">Winners</div>
      </div>
      <div style="flex:1;background:#fff8f5;border-radius:8px;padding:12px;text-align:center;">
        <div style="font-size:24px;font-weight:700;color:#B5282A;">{len(losses)}</div>
        <div style="font-size:12px;color:#666;">Losers</div>
      </div>
      <div style="flex:1;background:#fff3e0;border-radius:8px;padding:12px;text-align:center;">
        <div style="font-size:24px;font-weight:700;color:{'#1a6b3c' if total_pnl>=0 else '#B5282A'};">{total_pnl:+.2f}%</div>
        <div style="font-size:12px;color:#666;">Total P&L</div>
      </div>
    </div>
    <table style="width:100%;border-collapse:collapse;font-size:13px;">
      <thead>
        <tr style="background:#B5282A;color:white;">
          <th style="padding:8px;text-align:left;">Stock</th>
          <th style="padding:8px;">Entry</th>
          <th style="padding:8px;">Exit</th>
          <th style="padding:8px;">Exit Type</th>
          <th style="padding:8px;">P&L</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
    <div style="margin-top:16px;font-size:11px;color:#9a7060;padding:10px;background:#fff8f5;border-radius:8px;">
      No trades Tue–Thu. Next signal: Friday 3:30 PM IST. System restarts weekly.
    </div>
  </div>
</div></body></html>"""

# ════════════════════════════════════════════════════════════════════════════
# CLI Entry Points (called by GitHub Actions)
# ════════════════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['friday','monday','performance'], help='Scan mode')
    parser.add_argument('--date', default=None, help='Override date YYYY-MM-DD')
    parser.add_argument('--capital', type=float, default=500000)
    parser.add_argument('--risk', type=float, default=1.0)
    args = parser.parse_args()

    run_date = date.fromisoformat(args.date) if args.date else date.today()
    regime, nifty_last, s200, s50 = get_market_regime()

    if args.mode == 'friday':
        watchlist = run_friday_scan(run_date)
        if watchlist:
            html = friday_email_html(watchlist, regime, run_date)
            n = len(watchlist)
            send_email(
                f"📉 FM System — {run_date.strftime('%d %b %Y')} — {n} Setup{'s' if n!=1 else ''} Found",
                html
            )
            print(f"\n  ✓ Friday scan complete: {n} setups → email sent")
        else:
            print("  No setups today.")

    elif args.mode == 'monday':
        signals = run_monday_scan(run_date)
        if signals:
            html = monday_email_html(signals, regime, run_date, args.capital, args.risk)
            n = len(signals)
            send_email(
                f"⚡ FM SIGNALS — {run_date.strftime('%d %b %Y')} — {n} Trade{'s' if n!=1 else ''} — EXECUTE NOW",
                html
            )
            print(f"\n  ✓ Monday scan complete: {n} signals → email sent")
        else:
            html = monday_email_html([], regime, run_date)
            send_email(f"FM System — {run_date.strftime('%d %b %Y')} — No Signals Today", html)
            print("  No signals today.")

    elif args.mode == 'performance':
        outcomes = run_monday_performance(run_date)
        html = performance_email_html(outcomes, run_date)
        n = len(outcomes)
        wins = sum(1 for o in outcomes if o['pnl'] > 0)
        send_email(
            f"📊 FM Performance — {run_date.strftime('%d %b %Y')} — {wins}/{n} Winners",
            html
        )
        print(f"\n  ✓ EOD performance captured: {n} trades, {wins} wins")
