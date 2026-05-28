"""
FRIDAY-MONDAY PATTERN — FULL BACKTEST ENGINE
Universe  : Nifty LargeMidcap 250 (current composition, survivorship bias noted)
Period    : 2011-04-01 → last Friday close
Strategy  : SHORT at Monday open when (1) Fri High < Thu High and (2) gap down >0.3%
            If Thursday is a holiday, use Wednesday as the reference day.
            If Friday is a holiday, the week is skipped entirely.
Exit      : Target = Fri Low  |  Stop = Fri High  |  EOD = Mon Close if neither hit.
            Conservative: if both stop and target could be hit intraday, STOP is assumed first.
Costs     : Gross P&L + Net P&L (net = gross − 0.05% round-trip)
            Flat estimate covers: brokerage ₹20/leg, STT 0.025%, exchange 0.00345%, SEBI, GST.
"""

import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, date, timedelta
import sys, os, time, json
import warnings
warnings.filterwarnings('ignore')

# ── Optional Supabase upload ─────────────────────────────────────────────────
try:
    from supabase import create_client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False

from nifty250_stocks import NIFTY_250_STOCKS, SYMBOL_TO_NAME, SYMBOL_TO_SECTOR, SYMBOL_TO_TIER

# ── Constants ────────────────────────────────────────────────────────────────
BACKTEST_START    = '2011-04-01'
BACKTEST_END      = (date.today() - timedelta(days=1)).strftime('%Y-%m-%d')
GAP_THRESHOLD_PCT = -0.30          # gap down must exceed this (negative = down)
TXN_COST_PCT      = 0.05           # round-trip transaction cost (%)
REGIME_WINDOW     = 200            # SMA period for regime detection
BATCH_SIZE        = 50             # stocks per yfinance download batch

# ── Regime helper ────────────────────────────────────────────────────────────
def build_regime_series(nifty_df: pd.DataFrame) -> pd.Series:
    """
    Bull  : Nifty 50 > 200-DMA * 1.05
    Bear  : Nifty 50 < 200-DMA * 0.95
    Sideways: within 5% band of 200-DMA
    """
    sma = nifty_df['Close'].rolling(REGIME_WINDOW, min_periods=100).mean()
    regime = pd.Series('bull', index=nifty_df.index)
    regime[nifty_df['Close'] < sma * 0.95] = 'bear'
    regime[(nifty_df['Close'] >= sma * 0.95) & (nifty_df['Close'] <= sma * 1.05)] = 'sideways'
    return regime

# ── Technical indicators ─────────────────────────────────────────────────────
def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain  = delta.clip(lower=0).rolling(period, min_periods=period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period, min_periods=period).mean()
    rs    = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).round(2)

def compute_volume_ratio(volume: pd.Series, window: int = 20) -> pd.Series:
    return (volume / volume.rolling(window, min_periods=10).mean()).round(3)

# ── Core backtest logic per stock ─────────────────────────────────────────────
def backtest_single_stock(symbol: str, df: pd.DataFrame, regime_series: pd.Series) -> list:
    """
    Identify all valid Friday setups and simulate trades for one stock.
    Returns a list of trade dicts (one per confirmed trade).
    """
    if df is None or len(df) < 30:
        return []

    df = df.copy()
    df.index = pd.to_datetime(df.index)
    df.sort_index(inplace=True)

    # Flatten multi-level columns if present
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # Ensure required columns
    required = {'Open', 'High', 'Low', 'Close', 'Volume'}
    if not required.issubset(df.columns):
        return []

    # Pre-compute indicators
    df['RSI']         = compute_rsi(df['Close'])
    df['VolRatio']    = compute_volume_ratio(df['Volume'])
    df['SMA20']       = df['Close'].rolling(20).mean()

    trading_days = df.index.tolist()
    n = len(trading_days)
    trades = []

    for i, friday in enumerate(trading_days):
        # ── Must be a Friday (weekday 4) ──────────────────────────────────
        if friday.weekday() != 4:
            continue

        fri_row = df.iloc[i]

        # ── Find reference day: last Thursday OR Wednesday (if Thu is holiday) ──
        ref_day_row = None
        ref_day_name = None
        for back in range(1, 6):
            if i - back < 0:
                break
            candidate_day = trading_days[i - back]
            # If it's Thursday → perfect reference
            if candidate_day.weekday() == 3:
                ref_day_row  = df.iloc[i - back]
                ref_day_name = 'thursday'
                break
            # If it's Wednesday and we already skipped Thursday (Thursday was holiday)
            if candidate_day.weekday() == 2:
                # Check: did a Thursday exist between this Wednesday and Friday?
                # i.e., was Thursday a trading day? If not, use Wednesday.
                thu_candidate = candidate_day + timedelta(days=1)
                if thu_candidate not in df.index:
                    ref_day_row  = df.iloc[i - back]
                    ref_day_name = 'wednesday'
                    break
                # Thursday WAS a trading day but we hit Wednesday first → skip (shouldn't happen)
                break

        if ref_day_row is None:
            continue  # Can't identify reference day

        # ── Setup condition: Fri High < Ref High ─────────────────────────
        if fri_row['High'] >= ref_day_row['High']:
            continue  # Pattern not met

        # ── Find next Monday (skip if Monday is a holiday) ───────────────
        mon_row = None
        monday_date = None
        for fwd in range(1, 6):
            if i + fwd >= n:
                break
            candidate_day = trading_days[i + fwd]
            if candidate_day.weekday() == 0:   # Monday
                mon_row     = df.iloc[i + fwd]
                monday_date = candidate_day
                break
            # If we hit Tuesday/Wednesday before Monday, that means Monday was holiday → no trade
            if candidate_day.weekday() in (1, 2):
                break

        if mon_row is None:
            continue  # No Monday (holiday or end of data)

        # ── Gap down condition: Mon Open < Fri Close * (1 + threshold) ───
        gap_pct = (mon_row['Open'] - fri_row['Close']) / fri_row['Close'] * 100
        if gap_pct >= GAP_THRESHOLD_PCT:     # GAP_THRESHOLD_PCT is -0.30
            continue   # Not enough gap down

        # ── Trade confirmed — define levels ──────────────────────────────
        entry  = mon_row['Open']
        stop   = fri_row['High']       # SHORT stop = above entry
        target = fri_row['Low']        # SHORT target = below entry

        # Safety check: entry must be between target and stop
        if entry >= stop or entry <= target:
            # Entry already outside range → skip degenerate case
            pass  # Still allow, just unusual

        # ── Determine exit (conservative: stop checked first) ────────────
        if mon_row['High'] >= stop:
            exit_price = stop
            exit_type  = 'stop'
        elif mon_row['Low'] <= target:
            exit_price = target
            exit_type  = 'target'
        else:
            exit_price = mon_row['Close']
            exit_type  = 'eod'

        # ── P&L — SHORT trade ─────────────────────────────────────────────
        gross_pnl_pct = round((entry - exit_price) / entry * 100, 4)
        net_pnl_pct   = round(gross_pnl_pct - TXN_COST_PCT, 4)
        is_win        = gross_pnl_pct > 0

        # ── Regime on this Friday ─────────────────────────────────────────
        regime = 'unknown'
        if friday in regime_series.index:
            regime = regime_series.loc[friday]

        # ── Collect trade ─────────────────────────────────────────────────
        trades.append({
            'symbol':          symbol.replace('.NS', ''),
            'stock_name':      SYMBOL_TO_NAME.get(symbol, symbol),
            'sector':          SYMBOL_TO_SECTOR.get(symbol, 'Unknown'),
            'tier':            SYMBOL_TO_TIER.get(symbol, 'mid'),
            'friday_date':     friday.date().isoformat(),
            'monday_date':     monday_date.date().isoformat(),
            'ref_day_type':    ref_day_name,
            'ref_day_high':    round(float(ref_day_row['High']), 2),
            'fri_high':        round(float(fri_row['High']), 2),
            'fri_low':         round(float(fri_row['Low']), 2),
            'fri_close':       round(float(fri_row['Close']), 2),
            'fri_volume_ratio':round(float(fri_row['VolRatio']) if not pd.isna(fri_row['VolRatio']) else 1.0, 3),
            'fri_rsi':         round(float(fri_row['RSI']) if not pd.isna(fri_row['RSI']) else 50.0, 2),
            'fri_above_sma20': bool(fri_row['Close'] > fri_row['SMA20']) if not pd.isna(fri_row['SMA20']) else True,
            'mon_open':        round(float(mon_row['Open']), 2),
            'mon_high':        round(float(mon_row['High']), 2),
            'mon_low':         round(float(mon_row['Low']), 2),
            'mon_close':       round(float(mon_row['Close']), 2),
            'gap_pct':         round(float(gap_pct), 4),
            'entry_price':     round(float(entry), 2),
            'stop_price':      round(float(stop), 2),
            'target_price':    round(float(target), 2),
            'exit_price':      round(float(exit_price), 2),
            'exit_type':       exit_type,
            'gross_pnl_pct':   gross_pnl_pct,
            'net_pnl_pct':     net_pnl_pct,
            'is_win':          is_win,
            'regime':          regime,
            'year':            friday.year,
            'month':           friday.month,
            'quarter':         f"Q{(friday.month - 1) // 3 + 1}",
        })

    return trades

# ── Summary stats per stock ───────────────────────────────────────────────────
def compute_stock_summary(symbol: str, trades: list) -> dict:
    if not trades:
        return None

    df = pd.DataFrame(trades)
    total    = len(df)
    wins     = int(df['is_win'].sum())
    losses   = total - wins
    targets  = int((df['exit_type'] == 'target').sum())
    stops    = int((df['exit_type'] == 'stop').sum())
    eods     = int((df['exit_type'] == 'eod').sum())

    win_trades  = df[df['is_win']]['gross_pnl_pct']
    loss_trades = df[~df['is_win']]['gross_pnl_pct']

    avg_win   = float(win_trades.mean())  if len(win_trades)  else 0.0
    avg_loss  = float(loss_trades.mean()) if len(loss_trades) else 0.0
    gross_sum = float(df['gross_pnl_pct'].sum())
    net_sum   = float(df['net_pnl_pct'].sum())
    
    profit_factor = (abs(float(win_trades.sum())) / abs(float(loss_trades.sum()))
                     if len(loss_trades) and float(loss_trades.sum()) != 0 else 999.0)

    # Equity curve for drawdown calculation (gross cumulative)
    equity = df['gross_pnl_pct'].cumsum()
    rolling_max = equity.cummax()
    drawdown = equity - rolling_max
    max_dd = float(drawdown.min())

    # Win rates by regime
    regime_stats = {}
    for regime, grp in df.groupby('regime'):
        regime_stats[regime] = {
            'trades': len(grp),
            'win_rate': round(float(grp['is_win'].mean() * 100), 1),
            'avg_gross': round(float(grp['gross_pnl_pct'].mean()), 3),
        }

    return {
        'symbol':           symbol.replace('.NS', ''),
        'stock_name':       SYMBOL_TO_NAME.get(symbol, symbol),
        'sector':           SYMBOL_TO_SECTOR.get(symbol, 'Unknown'),
        'tier':             SYMBOL_TO_TIER.get(symbol, 'mid'),
        'total_trades':     total,
        'wins':             wins,
        'losses':           losses,
        'targets_hit':      targets,
        'stops_hit':        stops,
        'eod_exits':        eods,
        'win_rate_pct':     round(wins / total * 100, 2),
        'avg_gross_pnl':    round(float(df['gross_pnl_pct'].mean()), 4),
        'avg_net_pnl':      round(float(df['net_pnl_pct'].mean()), 4),
        'total_gross_pnl':  round(gross_sum, 2),
        'total_net_pnl':    round(net_sum, 2),
        'avg_win_pct':      round(avg_win, 4),
        'avg_loss_pct':     round(avg_loss, 4),
        'profit_factor':    round(profit_factor, 3),
        'max_drawdown_pct': round(max_dd, 4),
        'avg_gap_pct':      round(float(df['gap_pct'].mean()), 4),
        'avg_fri_rsi':      round(float(df['fri_rsi'].mean()), 2),
        'regime_stats':     json.dumps(regime_stats),
    }

# ── Download data in batches ──────────────────────────────────────────────────
def download_batch(symbols: list, start: str, end: str, retry: int = 3) -> dict:
    """
    Download OHLCV for a list of symbols. Returns dict: symbol → DataFrame.
    """
    result = {}
    tickers_str = ' '.join(symbols)
    
    for attempt in range(retry):
        try:
            raw = yf.download(
                tickers_str,
                start=start,
                end=end,
                auto_adjust=True,
                progress=False,
                threads=True,
                group_by='ticker',
            )
            if raw.empty:
                break

            for sym in symbols:
                try:
                    if len(symbols) == 1:
                        df = raw.copy()
                    else:
                        df = raw[sym].copy()

                    # Robustly flatten MultiIndex — yfinance swaps levels depending on
                    # download period length. Find whichever level has OHLCV names.
                    if isinstance(df.columns, pd.MultiIndex):
                        ohlcv = {'Open', 'High', 'Low', 'Close', 'Volume'}
                        flattened = False
                        for lvl in range(df.columns.nlevels):
                            vals = df.columns.get_level_values(lvl).tolist()
                            if ohlcv.issubset(set(vals)):
                                df.columns = vals
                                flattened = True
                                break
                        if not flattened:
                            df.columns = df.columns.get_level_values(-1)

                    df.dropna(how='all', inplace=True)
                    if len(df) > 20:
                        result[sym] = df
                except Exception:
                    pass
            break
        except Exception as e:
            if attempt < retry - 1:
                time.sleep(5)
            else:
                print(f"  ⚠ Download failed after {retry} attempts: {e}")

    return result

# ── Main backtest runner ──────────────────────────────────────────────────────
def run_full_backtest(
    symbols: list = None,
    start: str = BACKTEST_START,
    end: str = BACKTEST_END,
    save_csv: bool = True,
    upload_supabase: bool = False,
    supabase_url: str = None,
    supabase_key: str = None,
    verbose: bool = True,
) -> tuple:
    """
    Run the full backtest. Returns (all_trades_df, summary_df).
    """
    if symbols is None:
        symbols = list(NIFTY_250_STOCKS.keys())

    print(f"\n{'='*65}")
    print(f"  FRIDAY-MONDAY BACKTEST ENGINE")
    print(f"  Universe : {len(symbols)} stocks")
    print(f"  Period   : {start} → {end}")
    print(f"  Strategy : SHORT | Gap<{GAP_THRESHOLD_PCT}% | EOD exit if no hit")
    print(f"{'='*65}\n")

    # ── Download Nifty 50 for regime ─────────────────────────────────────
    print("Downloading Nifty 50 index for market regime…")
    nifty_raw = yf.download('^NSEI', start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(nifty_raw.columns, pd.MultiIndex):
        nifty_raw.columns = nifty_raw.columns.get_level_values(0)
    nifty_raw.index = pd.to_datetime(nifty_raw.index)
    regime_series = build_regime_series(nifty_raw)
    print(f"  Regime series: {len(regime_series)} days.\n")

    # ── Download stock data in batches ────────────────────────────────────
    all_stock_data = {}
    batches = [symbols[i:i+BATCH_SIZE] for i in range(0, len(symbols), BATCH_SIZE)]

    for batch_num, batch in enumerate(batches, 1):
        batch_names = [SYMBOL_TO_NAME.get(s, s) for s in batch]
        print(f"Downloading batch {batch_num}/{len(batches)} ({len(batch)} stocks)… ", end='', flush=True)
        t0 = time.time()
        batch_data = download_batch(batch, start, end)
        all_stock_data.update(batch_data)
        elapsed = time.time() - t0
        print(f"got {len(batch_data)}/{len(batch)} in {elapsed:.1f}s")

    print(f"\nTotal stocks with data: {len(all_stock_data)}/{len(symbols)}\n")

    # ── Run backtest per stock ────────────────────────────────────────────
    all_trades    = []
    stock_summaries = []
    failed        = []

    for idx, symbol in enumerate(symbols, 1):
        if symbol not in all_stock_data:
            failed.append(symbol)
            continue

        df = all_stock_data[symbol]
        trades = backtest_single_stock(symbol, df, regime_series)

        if verbose:
            n_trades = len(trades)
            if n_trades > 0:
                wr = sum(1 for t in trades if t['is_win']) / n_trades * 100
                print(f"  [{idx:>3}/{len(symbols)}] {SYMBOL_TO_NAME.get(symbol, symbol):<30}  "
                      f"{n_trades:>4} trades  WR: {wr:>5.1f}%")
            else:
                print(f"  [{idx:>3}/{len(symbols)}] {SYMBOL_TO_NAME.get(symbol, symbol):<30}  0 trades")

        all_trades.extend(trades)

        summary = compute_stock_summary(symbol, trades)
        if summary:
            stock_summaries.append(summary)

    # ── Assemble DataFrames ───────────────────────────────────────────────
    trades_df  = pd.DataFrame(all_trades)
    summary_df = pd.DataFrame(stock_summaries)

    print(f"\n{'='*65}")
    print(f"  BACKTEST COMPLETE")
    print(f"  Total trades   : {len(trades_df):,}")
    if len(trades_df) > 0:
        overall_wr  = trades_df['is_win'].mean() * 100
        avg_gross   = trades_df['gross_pnl_pct'].mean()
        avg_net     = trades_df['net_pnl_pct'].mean()
        total_gross = trades_df['gross_pnl_pct'].sum()
        print(f"  Overall WR     : {overall_wr:.1f}%")
        print(f"  Avg gross P&L  : {avg_gross:+.3f}% per trade")
        print(f"  Avg net P&L    : {avg_net:+.3f}% per trade")
        print(f"  Sum gross P&L  : {total_gross:+.1f}% (across all trades)")
    print(f"  Failed stocks  : {len(failed)}")
    print(f"{'='*65}\n")

    # ── Save CSV ──────────────────────────────────────────────────────────
    if save_csv:
        trades_df.to_csv('backtest_trades.csv', index=False)
        summary_df.to_csv('backtest_summary.csv', index=False)
        print("Saved: backtest_trades.csv and backtest_summary.csv\n")

    # ── Upload to Supabase ────────────────────────────────────────────────
    if upload_supabase and SUPABASE_AVAILABLE and supabase_url and supabase_key:
        upload_to_supabase(trades_df, summary_df, supabase_url, supabase_key)

    return trades_df, summary_df

# ── Supabase upload ───────────────────────────────────────────────────────────
def upload_to_supabase(trades_df: pd.DataFrame, summary_df: pd.DataFrame,
                        url: str, key: str):
    print("Uploading to Supabase…")
    sb = create_client(url, key)

    # ── Upload summary (upsert by symbol) ─────────────────────────────────
    summary_records = summary_df.to_dict(orient='records')
    CHUNK = 200
    for i in range(0, len(summary_records), CHUNK):
        chunk = summary_records[i:i+CHUNK]
        sb.table('fm_stock_summary').upsert(chunk, on_conflict='symbol').execute()
    print(f"  ✓ fm_stock_summary: {len(summary_records)} rows")

    # ── Upload trades in chunks ────────────────────────────────────────────
    trade_records = trades_df.to_dict(orient='records')
    # Clean up any non-JSON-serializable types
    for rec in trade_records:
        for k, v in rec.items():
            if isinstance(v, (np.integer,)):
                rec[k] = int(v)
            elif isinstance(v, (np.floating,)):
                rec[k] = float(v)
            elif isinstance(v, (np.bool_,)):
                rec[k] = bool(v)

    for i in range(0, len(trade_records), CHUNK):
        chunk = trade_records[i:i+CHUNK]
        sb.table('fm_backtest_trades').insert(chunk).execute()
        if i % 2000 == 0:
            print(f"  ✓ fm_backtest_trades: {i + len(chunk):,} rows inserted…")

    print(f"  ✓ fm_backtest_trades: {len(trade_records):,} rows total")
    print("Supabase upload complete.\n")

# ── Analytics helpers (used by Streamlit app) ─────────────────────────────────
def load_backtest_results(csv_path_trades='backtest_trades.csv',
                           csv_path_summary='backtest_summary.csv') -> tuple:
    """Load backtest results from CSV (for Streamlit app)."""
    try:
        trades  = pd.read_csv(csv_path_trades, parse_dates=['friday_date', 'monday_date'])
        summary = pd.read_csv(csv_path_summary)
        return trades, summary
    except Exception as e:
        print(f"Could not load CSV results: {e}")
        return pd.DataFrame(), pd.DataFrame()

def compute_equity_curve(trades_df: pd.DataFrame, initial_capital: float = 100000) -> pd.DataFrame:
    """Compute running equity curve from trades."""
    if trades_df.empty:
        return pd.DataFrame()
    df = trades_df.sort_values('monday_date').copy()
    df['equity_gross'] = initial_capital * (1 + df['gross_pnl_pct'] / 100).cumprod()
    df['equity_net']   = initial_capital * (1 + df['net_pnl_pct']   / 100).cumprod()
    return df[['monday_date', 'equity_gross', 'equity_net']]

def yearly_stats(trades_df: pd.DataFrame) -> pd.DataFrame:
    """Year-by-year performance."""
    if trades_df.empty:
        return pd.DataFrame()
    grp = trades_df.groupby('year').agg(
        trades       = ('is_win', 'count'),
        wins         = ('is_win', 'sum'),
        avg_gross    = ('gross_pnl_pct', 'mean'),
        total_gross  = ('gross_pnl_pct', 'sum'),
        avg_net      = ('net_pnl_pct', 'mean'),
    ).reset_index()
    grp['win_rate'] = (grp['wins'] / grp['trades'] * 100).round(1)
    grp['avg_gross'] = grp['avg_gross'].round(3)
    grp['total_gross'] = grp['total_gross'].round(2)
    grp['avg_net'] = grp['avg_net'].round(3)
    return grp

def sector_stats(trades_df: pd.DataFrame) -> pd.DataFrame:
    """Sector-level performance summary."""
    if trades_df.empty:
        return pd.DataFrame()
    grp = trades_df.groupby('sector').agg(
        trades    = ('is_win', 'count'),
        wins      = ('is_win', 'sum'),
        avg_gross = ('gross_pnl_pct', 'mean'),
        avg_net   = ('net_pnl_pct', 'mean'),
    ).reset_index()
    grp['win_rate'] = (grp['wins'] / grp['trades'] * 100).round(1)
    grp['avg_gross'] = grp['avg_gross'].round(3)
    grp['avg_net'] = grp['avg_net'].round(3)
    return grp.sort_values('win_rate', ascending=False)

def regime_stats(trades_df: pd.DataFrame) -> pd.DataFrame:
    """Performance by market regime."""
    if trades_df.empty:
        return pd.DataFrame()
    grp = trades_df.groupby('regime').agg(
        trades    = ('is_win', 'count'),
        wins      = ('is_win', 'sum'),
        avg_gross = ('gross_pnl_pct', 'mean'),
        avg_net   = ('net_pnl_pct', 'mean'),
    ).reset_index()
    grp['win_rate'] = (grp['wins'] / grp['trades'] * 100).round(1)
    return grp

def exit_type_breakdown(trades_df: pd.DataFrame) -> dict:
    vc = trades_df['exit_type'].value_counts()
    return vc.to_dict()

def gap_bucket_stats(trades_df: pd.DataFrame) -> pd.DataFrame:
    """Win rate and avg P&L by gap size bucket."""
    if trades_df.empty:
        return pd.DataFrame()
    df = trades_df.copy()
    bins   = [-99, -2, -1.5, -1.0, -0.5, -0.3, 0]
    labels = ['>2% gap', '1.5–2%', '1–1.5%', '0.5–1%', '0.3–0.5%', '<0.3% (filtered)']
    df['gap_bucket'] = pd.cut(df['gap_pct'], bins=bins, labels=labels)
    grp = df.groupby('gap_bucket', observed=True).agg(
        trades    = ('is_win', 'count'),
        wins      = ('is_win', 'sum'),
        avg_gross = ('gross_pnl_pct', 'mean'),
    ).reset_index()
    grp['win_rate'] = (grp['wins'] / grp['trades'] * 100).round(1)
    return grp

# ── CLI entry point ───────────────────────────────────────────────────────────
if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Run FM Strategy backtest')
    parser.add_argument('--start',    default=BACKTEST_START, help='Start date YYYY-MM-DD')
    parser.add_argument('--end',      default=BACKTEST_END,   help='End date YYYY-MM-DD')
    parser.add_argument('--symbols',  default=None, nargs='*', help='Subset of symbols')
    parser.add_argument('--upload',   action='store_true',     help='Upload to Supabase')
    parser.add_argument('--url',      default=None,            help='Supabase URL')
    parser.add_argument('--key',      default=None,            help='Supabase anon key')
    args = parser.parse_args()

    supabase_url = args.url or os.environ.get('SUPABASE_URL')
    supabase_key = args.key or os.environ.get('SUPABASE_KEY')
    symbols      = args.symbols or list(NIFTY_250_STOCKS.keys())

    trades_df, summary_df = run_full_backtest(
        symbols          = symbols,
        start            = args.start,
        end              = args.end,
        save_csv         = True,
        upload_supabase  = args.upload,
        supabase_url     = supabase_url,
        supabase_key     = supabase_key,
        verbose          = True,
    )
