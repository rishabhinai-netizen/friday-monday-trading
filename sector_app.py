"""
BANKING & INFRASTRUCTURE FM STRATEGY PLATFORM
Friday-Monday SHORT Strategy | Bear Regime Only | 2011–2026
Full 15-year trade-by-trade analysis, equity simulation, live scanner
Theme: Navy + Ivory (Sky Ledger)
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import date, timedelta
import os, warnings
warnings.filterwarnings('ignore')

st.set_page_config(
    page_title="Banking & Infra FM Platform",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Theme: Navy + Ivory ───────────────────────────────────────────────────────
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700&family=Inter:wght@400;500;600&display=swap');
  html, body, [class*="css"] { font-family: 'Inter', sans-serif; background: #F5F9FF; }
  h1, h2, h3 { font-family: 'Playfair Display', serif !important; }

  .hero { background: linear-gradient(135deg, #042C53 0%, #0C447C 60%, #1a5a9a 100%);
    border-radius: 16px; padding: 28px 32px; color: white; margin-bottom: 24px; }
  .hero-title  { font-size: 26px; font-weight: 700; font-family: 'Playfair Display',serif; margin-bottom: 4px; }
  .hero-sub    { font-size: 13px; opacity: .75; margin-bottom: 20px; }
  .hero-stats  { display: flex; gap: 24px; flex-wrap: wrap; }
  .hero-stat   { text-align: center; }
  .hero-val    { font-size: 28px; font-weight: 800; color: #7dd3fc; font-family: 'Playfair Display',serif; }
  .hero-lbl    { font-size: 11px; opacity: .65; text-transform: uppercase; letter-spacing: .06em; margin-top: 2px; }

  .stat-box { background: white; border: 1px solid #d1e4f5; border-radius: 10px;
    padding: 16px 18px; text-align: center; }
  .stat-val { font-size: 26px; font-weight: 700; font-family: 'Playfair Display',serif; }
  .stat-lbl { font-size: 11px; color: #5a7a98; text-transform: uppercase; letter-spacing: .05em; margin-top: 3px; }

  .sec-header { font-family: 'Playfair Display',serif; font-size: 19px; color: #042C53;
    border-bottom: 2px solid #c0d8f0; padding-bottom: 8px; margin: 16px 0 14px; }

  .trade-win  { background: #f0faf4 !important; }
  .trade-loss { background: #fff5f5 !important; }

  .insight-box { background: #f0f6ff; border-left: 4px solid #0C447C;
    border-radius: 0 8px 8px 0; padding: 12px 16px; margin-bottom: 10px; }
  .insight-title { font-weight: 700; font-size: 13px; color: #042C53; margin-bottom: 4px; }
  .insight-body  { font-size: 12px; color: #2a4060; line-height: 1.6; }

  .stTabs [data-baseweb="tab-list"] { gap: 4px; background: #e8f0fa; padding: 6px; border-radius: 10px; }
  .stTabs [data-baseweb="tab"] {
    background: transparent; border-radius: 8px; padding: 8px 18px;
    font-size: 13px; font-weight: 500; color: #3a5a7a !important; }
  .stTabs [aria-selected="true"] { background: #042C53 !important; color: white !important; }
  div[data-testid="metric-container"] { background: white; border: 1px solid #d1e4f5;
    border-radius: 10px; padding: 10px 16px; }
</style>
""", unsafe_allow_html=True)

COST_PCT = 0.05
SECTORS  = ['Banking', 'Infrastructure']

# ── Data helpers ──────────────────────────────────────────────────────────────
def colour_pnl(val):
    if not isinstance(val, (int, float)) or pd.isna(val): return ''
    return f"color:{'#1a6b3c' if val >= 0 else '#B5282A'};font-weight:600"

def style_wr(val):
    if not isinstance(val, (int, float)) or pd.isna(val): return ''
    if val >= 80: return 'background:#c8f0d8;color:#0d4a28;font-weight:700'
    if val >= 65: return 'background:#e6f4ec;color:#1a6b3c;font-weight:600'
    if val >= 50: return 'background:#fef5e0;color:#9a6b1a;font-weight:600'
    return 'background:#fde8e8;color:#B5282A;font-weight:500'

@st.cache_data(ttl=3600)
def load_bi_data(capital: float, risk_pct: float):
    """Load and preprocess Banking + Infra bear trades with equity simulation."""
    trades = pd.read_csv('backtest_trades.csv',
                         parse_dates=['friday_date','monday_date'])
    valid  = trades[trades['entry_price'] > trades['target_price']].copy()
    bi     = valid[valid['sector'].isin(SECTORS) & (valid['regime'] == 'bear')].copy()
    bi     = bi.sort_values('monday_date').reset_index(drop=True)

    bi['stop_width']   = (bi['stop_price']  - bi['entry_price']) / bi['entry_price'] * 100
    bi['target_depth'] = (bi['entry_price'] - bi['target_price'])/ bi['entry_price'] * 100
    bi['rr_ratio']     = bi['target_depth'] / bi['stop_width']
    bi['monday_date']  = pd.to_datetime(bi['monday_date'])
    bi['year']         = bi['monday_date'].dt.year

    # Equity simulation
    cap   = capital
    equit = [cap]
    pnl_rs = []
    shares_list = []
    for _, row in bi.iterrows():
        entry  = row['entry_price']
        stop   = row['stop_price']
        risk_pp = stop - entry
        if risk_pp <= 0: shares = 1
        else:            shares = max(1, int(cap * risk_pct / risk_pp))
        net_pct = row['net_pnl_pct'] / 100
        pnl     = shares * entry * net_pct
        cap    += pnl
        equit.append(cap)
        pnl_rs.append(pnl)
        shares_list.append(shares)

    bi['pnl_rs']  = pnl_rs
    bi['shares']  = shares_list
    bi['equity']  = equit[1:]
    bi['cum_pnl'] = bi['pnl_rs'].cumsum()

    # Drawdown
    eq_series = pd.Series(equit)
    peak      = eq_series.expanding().max()
    dd        = (eq_series - peak) / peak * 100
    bi['drawdown'] = dd.iloc[1:].values

    return bi, equit

@st.cache_data(ttl=1800)
def get_regime():
    import yfinance as yf
    start = (date.today() - timedelta(days=400)).strftime('%Y-%m-%d')
    n = yf.download('^NSEI', start=start, auto_adjust=True, progress=False)
    if isinstance(n.columns, pd.MultiIndex):
        for l in range(n.columns.nlevels):
            if 'Close' in n.columns.get_level_values(l):
                n.columns = n.columns.get_level_values(l); break
    c = n['Close'].dropna()
    last, s200, s50 = float(c.iloc[-1]), float(c.rolling(200).mean().iloc[-1]), float(c.rolling(50).mean().iloc[-1])
    reg = 'bear' if last < s200*0.95 else ('bull' if last > s200*1.05 else 'sideways')
    return reg, last, s200, s50

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('<div style="font-size:20px;font-weight:700;color:#042C53;font-family:Playfair Display,serif;">🏦 Banking & Infra</div>', unsafe_allow_html=True)
    st.caption("FM Strategy | Bear Regime Only")
    st.divider()
    st.subheader("💰 Simulation Capital")
    capital  = st.number_input("Starting Capital (₹)", 100000, 50000000, 500000, 100000)
    risk_pct = st.slider("Risk per trade %", 0.25, 2.0, 1.0, 0.25) / 100
    st.divider()
    st.subheader("🔍 Filters")
    sector_sel = st.multiselect("Sector", SECTORS, default=SECTORS)
    year_range = st.slider("Year Range", 2011, 2026, (2011, 2026))
    st.divider()
    st.caption("Universe: 21 stocks (Banking + Infra)")
    st.caption("Strategy: Bear regime only (Nifty < 200-DMA × 0.95)")
    st.caption("Period: 2011-04-01 → 30 May 2026")

# ── Load data ─────────────────────────────────────────────────────────────────
bi, equit = load_bi_data(capital, risk_pct)
bi_f = bi[bi['sector'].isin(sector_sel) & bi['year'].between(year_range[0], year_range[1])].copy()

if bi_f.empty:
    st.error("No trades with current filters."); st.stop()

# ── Recalculate equity for filtered set ───────────────────────────────────────
cap2 = capital
eq2  = [cap2]; pnl2 = []
for _, row in bi_f.iterrows():
    entry  = row['entry_price']; stop = row['stop_price']
    rpp    = max(stop - entry, 0.01)
    shares = max(1, int(cap2 * risk_pct / rpp))
    pnl    = shares * entry * (row['net_pnl_pct']/100)
    cap2  += pnl; eq2.append(cap2); pnl2.append(pnl)
bi_f = bi_f.copy(); bi_f['pnl_rs_f'] = pnl2; bi_f['equity_f'] = eq2[1:]
total_return = (eq2[-1] - capital) / capital * 100
total_pnl_rs = eq2[-1] - capital
wins_f = bi_f[bi_f['is_win']]; loss_f = bi_f[~bi_f['is_win']]
wr_f   = bi_f['is_win'].mean()*100
avg_g  = bi_f['gross_pnl_pct'].mean()

# ── Hero banner ───────────────────────────────────────────────────────────────
try:
    reg_now, n_last, n_s200, _ = get_regime()
except Exception:
    reg_now = 'unknown'; n_last = n_s200 = 0

reg_badge = {'bear':'🐻 BEAR — Strategy ACTIVE','sideways':'➡️ SIDEWAYS — Wait','bull':'🐂 BULL — Stay out'}.get(reg_now,'❓')
reg_color = {'bear':'#7dd3fc','sideways':'#fcd34d','bull':'#fca5a5'}.get(reg_now,'#ccc')

st.markdown(f"""<div class="hero">
  <div class="hero-title">🏦 Banking & Infrastructure FM Strategy Platform</div>
  <div class="hero-sub">Friday-Monday SHORT | Bear Regime Only | Nifty 250 | 2011–2026<br>
    Current Regime: <span style="color:{reg_color};font-weight:700;">{reg_badge}</span>
    &nbsp;|&nbsp; Nifty: {n_last:,.0f} &nbsp;|&nbsp; 200-DMA: {n_s200:,.0f}
  </div>
  <div class="hero-stats">
    <div class="hero-stat"><div class="hero-val">{len(bi_f)}</div><div class="hero-lbl">Total Trades</div></div>
    <div class="hero-stat"><div class="hero-val">{wr_f:.1f}%</div><div class="hero-lbl">Win Rate</div></div>
    <div class="hero-stat"><div class="hero-val" style="color:{'#86efac' if total_pnl_rs>=0 else '#fca5a5'};">₹{total_pnl_rs:+,.0f}</div><div class="hero-lbl">Total P&L</div></div>
    <div class="hero-stat"><div class="hero-val" style="color:{'#86efac' if total_return>=0 else '#fca5a5'};">{total_return:+.1f}%</div><div class="hero-lbl">Total Return</div></div>
    <div class="hero-stat"><div class="hero-val">₹{capital:,.0f}</div><div class="hero-lbl">Starting Capital</div></div>
    <div class="hero-stat"><div class="hero-val">₹{eq2[-1]:,.0f}</div><div class="hero-lbl">Final Capital</div></div>
  </div>
</div>""", unsafe_allow_html=True)

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📊 15-Year Overview", "🏦 Banking", "🏗️ Infrastructure",
    "📋 Trade-by-Trade", "🧭 Strategy Intelligence", "📡 Live Scanner"
])

# ════════════════════════════════════════════════════════════════════════════
# TAB 1 — 15-YEAR OVERVIEW
# ════════════════════════════════════════════════════════════════════════════
with tab1:
    # KPI row
    k1,k2,k3,k4,k5,k6 = st.columns(6)
    kpis = [
        ("Trades",     f"{len(bi_f)}",            f"{bi_f['symbol'].nunique()} stocks"),
        ("Win Rate",   f"{wr_f:.1f}%",             f"{len(wins_f)} wins / {len(loss_f)} losses"),
        ("Avg Gross",  f"{avg_g:+.3f}%",           "per trade"),
        ("Avg Net",    f"{bi_f['net_pnl_pct'].mean():+.3f}%",  f"after {COST_PCT}% cost"),
        ("Best Trade", f"+{bi_f['gross_pnl_pct'].max():.2f}%", bi_f.loc[bi_f['gross_pnl_pct'].idxmax(),'symbol']),
        ("Worst Trade",f"{bi_f['gross_pnl_pct'].min():.2f}%",  bi_f.loc[bi_f['gross_pnl_pct'].idxmin(),'symbol']),
    ]
    for col, (lbl, val, sub) in zip([k1,k2,k3,k4,k5,k6], kpis):
        c = '#1a6b3c' if '+' in val else ('#B5282A' if val.startswith('-') else '#042C53')
        with col:
            st.markdown(f"""<div class="stat-box">
              <div class="stat-val" style="color:{c};">{val}</div>
              <div class="stat-lbl">{lbl}</div>
              <div style="font-size:10px;color:#888;margin-top:3px;">{sub}</div>
            </div>""", unsafe_allow_html=True)

    st.divider()

    # ── Equity curve + drawdown ───────────────────────────────────────────
    st.markdown('<div class="sec-header">📈 Equity Curve — ₹ Capital Growth</div>', unsafe_allow_html=True)

    dates_eq = [bi_f['monday_date'].iloc[0] - timedelta(days=3)] + bi_f['monday_date'].tolist()
    fig_eq   = go.Figure()
    fig_eq.add_trace(go.Scatter(
        x=dates_eq, y=eq2[:len(dates_eq)],
        mode='lines', name='Portfolio Value',
        line=dict(color='#0C447C', width=2.5),
        fill='tozeroy', fillcolor='rgba(12,68,124,0.08)'))
    fig_eq.add_hline(y=capital, line_dash='dash', line_color='#888',
        annotation_text=f"Start ₹{capital:,.0f}", annotation_position="bottom left")
    fig_eq.update_layout(
        height=320, plot_bgcolor='#F5F9FF', paper_bgcolor='#F5F9FF',
        yaxis_title='Portfolio Value (₹)', xaxis_title='',
        margin=dict(t=10,b=20), showlegend=False,
        yaxis=dict(tickprefix='₹', tickformat=',.0f'))
    st.plotly_chart(fig_eq, use_container_width=True)

    # Drawdown
    peak_eq  = pd.Series(eq2).expanding().max()
    dd_ser   = (pd.Series(eq2) - peak_eq) / peak_eq * 100
    dd_dates = dates_eq
    fig_dd   = go.Figure()
    fig_dd.add_trace(go.Scatter(
        x=dd_dates, y=dd_ser[:len(dd_dates)].tolist(),
        mode='lines', name='Drawdown %',
        line=dict(color='#B5282A', width=1.5),
        fill='tozeroy', fillcolor='rgba(181,40,42,0.08)'))
    fig_dd.update_layout(
        height=160, plot_bgcolor='#F5F9FF', paper_bgcolor='#F5F9FF',
        yaxis_title='Drawdown %', margin=dict(t=5,b=20), showlegend=False)
    st.plotly_chart(fig_dd, use_container_width=True)
    max_dd = dd_ser.min()
    st.caption(f"Max Drawdown: {max_dd:.2f}% &nbsp;|&nbsp; "
               f"Years traded: {bi_f['year'].nunique()} of 15 &nbsp;|&nbsp; "
               f"Non-trading years (bull/sideways): {6} years (2014, 2017, 2019, 2021, 2023, 2024)")

    st.divider()

    # ── Year-by-year ──────────────────────────────────────────────────────
    st.markdown('<div class="sec-header">📅 Year-by-Year Performance</div>', unsafe_allow_html=True)

    ystat = bi_f.groupby('year').agg(
        trades=('is_win','count'), wins=('is_win','sum'),
        avg_g=('gross_pnl_pct','mean'), pnl_rs=('pnl_rs_f','sum')
    ).reset_index()
    ystat['wr']   = (ystat['wins']/ystat['trades']*100).round(1)
    ystat['avg_g']= ystat['avg_g'].round(3)

    fig_yr = go.Figure()
    fig_yr.add_trace(go.Bar(
        x=ystat['year'].astype(str), y=ystat['pnl_rs'],
        marker_color=['#1a6b3c' if v >= 0 else '#B5282A' for v in ystat['pnl_rs']],
        name='P&L (₹)', text=[f"₹{v:+,.0f}" for v in ystat['pnl_rs']],
        textposition='outside'))
    fig_yr.add_trace(go.Scatter(
        x=ystat['year'].astype(str), y=ystat['wr'],
        mode='lines+markers', name='Win Rate %', yaxis='y2',
        line=dict(color='#378ADD', width=2), marker=dict(size=7)))
    fig_yr.update_layout(
        height=340,
        yaxis =dict(title='P&L (₹)', tickprefix='₹', tickformat=',.0f',
                    zeroline=True, zerolinecolor='#042C53', zerolinewidth=1.5),
        yaxis2=dict(title='Win Rate %', overlaying='y', side='right', range=[0,110]),
        plot_bgcolor='#F5F9FF', paper_bgcolor='#F5F9FF',
        legend=dict(orientation='h', x=0, y=1.08),
        margin=dict(t=20,b=30,r=60))
    st.plotly_chart(fig_yr, use_container_width=True)

    ydisp = ystat[['year','trades','wr','avg_g','pnl_rs']].copy()
    ydisp.columns = ['Year','Trades','Win Rate %','Avg Gross %','P&L (₹)']
    st.dataframe(
        ydisp.style
        .format({'Win Rate %':'{:.1f}','Avg Gross %':'{:+.3f}','P&L (₹)':'₹{:+,.0f}'})
        .map(colour_pnl, subset=['Avg Gross %'])
        .map(colour_pnl, subset=['P&L (₹)'])
        .map(style_wr,   subset=['Win Rate %']),
        hide_index=True, use_container_width=True)
    st.caption("⚪ 2014, 2017, 2019, 2021, 2023, 2024 not shown — Nifty above 200-DMA in those years, zero bear signals.")

    st.divider()

    # ── Insights ──────────────────────────────────────────────────────────
    st.markdown('<div class="sec-header">🔬 Key Insights</div>', unsafe_allow_html=True)
    i1, i2 = st.columns(2)
    best_yr  = ystat.loc[ystat['pnl_rs'].idxmax()]
    worst_yr = ystat.loc[ystat['pnl_rs'].idxmin()]
    with i1:
        st.markdown(f"""<div class="insight-box">
          <div class="insight-title">🏆 Strategy works best in panic-sell markets</div>
          <div class="insight-body">Best year: <b>{int(best_yr['year'])}</b> — ₹{best_yr['pnl_rs']:+,.0f} |
          WR {best_yr['wr']:.0f}% on {int(best_yr['trades'])} trades.
          Banking stocks show extreme Friday weakness before gap-down Monday opens during
          broad market stress — the classic setup this strategy is built for.</div>
        </div>""", unsafe_allow_html=True)
        st.markdown(f"""<div class="insight-box">
          <div class="insight-title">📐 R:R Profile</div>
          <div class="insight-body">Avg win: <b>{wins_f['gross_pnl_pct'].mean():+.2f}%</b> |
          Avg loss: <b>{loss_f['gross_pnl_pct'].mean():+.2f}%</b> |
          Profit factor: <b>{abs(wins_f['gross_pnl_pct'].sum())/abs(loss_f['gross_pnl_pct'].sum()):.2f}</b>.
          The high win rate compensates for the asymmetric R:R.</div>
        </div>""", unsafe_allow_html=True)
    with i2:
        st.markdown(f"""<div class="insight-box">
          <div class="insight-title">⚠️ Bad years are still real</div>
          <div class="insight-body">Worst year: <b>{int(worst_yr['year'])}</b> — ₹{worst_yr['pnl_rs']:+,.0f} |
          WR {worst_yr['wr']:.0f}% on {int(worst_yr['trades'])} trades.
          2015 in particular saw whipsaw — bear regime was brief and stocks recovered intraday.
          Stop width is critical: use ≤1.5% stop width to limit bleed.</div>
        </div>""", unsafe_allow_html=True)
        st.markdown(f"""<div class="insight-box">
          <div class="insight-title">💡 Infrastructure edge is extreme</div>
          <div class="insight-body">Infrastructure sector: <b>WR 93.8%</b> in bear (16 trades).
          ADANIPORTS, LT, and ENGINERSIN show near-perfect follow-through on Friday weakness
          in bear markets — likely because they're high-beta and directional during risk-off.</div>
        </div>""", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════════════════
# TAB 2 — BANKING
# ════════════════════════════════════════════════════════════════════════════
with tab2:
    bank = bi_f[bi_f['sector']=='Banking'].copy()
    if bank.empty:
        st.info("No Banking trades in current filter range.")
    else:
        st.markdown('<div class="sec-header">🏦 Banking Sector — Bear Regime Performance</div>', unsafe_allow_html=True)

        # Summary
        b_wr = bank['is_win'].mean()*100
        b_ag = bank['gross_pnl_pct'].mean()
        b_wins = bank[bank['is_win']]; b_loss = bank[~bank['is_win']]
        bk1,bk2,bk3,bk4 = st.columns(4)
        for col,(l,v) in zip([bk1,bk2,bk3,bk4],[
            ("Trades", str(len(bank))),
            ("Win Rate", f"{b_wr:.1f}%"),
            ("Avg Gross", f"{b_ag:+.3f}%"),
            ("Total ₹ P&L", f"₹{bank['pnl_rs_f'].sum():+,.0f}")]):
            c = '#1a6b3c' if '+' in v or b_ag >= 0 else '#B5282A'
            with col:
                st.markdown(f"""<div class="stat-box">
                  <div class="stat-val" style="color:{'#042C53' if '₹' not in v and '+' not in v and v.replace('%','').replace('.','').lstrip('-').isdigit() else ('#1a6b3c' if '+' in v or (v.endswith('%') and float(v.rstrip('%'))>50) else '#B5282A')};">{v}</div>
                  <div class="stat-lbl">{l}</div>
                </div>""", unsafe_allow_html=True)

        st.divider()

        # Per-stock breakdown
        st.markdown('<div class="sec-header">Per Stock Performance</div>', unsafe_allow_html=True)
        bstk = bank.groupby(['symbol','stock_name']).agg(
            trades=('is_win','count'), wins=('is_win','sum'),
            avg_g=('gross_pnl_pct','mean'), total_rs=('pnl_rs_f','sum'),
            avg_stop=('stop_width','mean'), avg_rr=('rr_ratio','mean')
        ).reset_index()
        bstk['wr'] = (bstk['wins']/bstk['trades']*100).round(1)
        bstk = bstk.sort_values('avg_g', ascending=False)

        fig_b = go.Figure()
        fig_b.add_trace(go.Bar(
            x=bstk['symbol'], y=bstk['avg_g'],
            marker_color=['#0C447C' if v >= 0 else '#B5282A' for v in bstk['avg_g']],
            text=[f"{v:+.2f}%" for v in bstk['avg_g']], textposition='outside'))
        fig_b.update_layout(height=320, plot_bgcolor='#F5F9FF', paper_bgcolor='#F5F9FF',
            yaxis_title='Avg Gross P&L %', margin=dict(t=10,b=30))
        st.plotly_chart(fig_b, use_container_width=True)

        bdisp = bstk[['symbol','stock_name','trades','wr','avg_g','total_rs']].copy()
        bdisp.columns = ['Symbol','Name','Trades','Win Rate %','Avg Gross %','Total P&L (₹)']
        st.dataframe(
            bdisp.style
            .format({'Win Rate %':'{:.1f}','Avg Gross %':'{:+.3f}','Total P&L (₹)':'₹{:+,.0f}'})
            .map(colour_pnl, subset=['Avg Gross %','Total P&L (₹)'])
            .map(style_wr,   subset=['Win Rate %']),
            hide_index=True, use_container_width=True)

        st.divider()

        # Year-by-year for banking
        st.markdown('<div class="sec-header">Banking — Year-by-Year</div>', unsafe_allow_html=True)
        byyr = bank.groupby('year').agg(
            trades=('is_win','count'), wins=('is_win','sum'),
            avg_g=('gross_pnl_pct','mean'), pnl_rs=('pnl_rs_f','sum')
        ).reset_index()
        byyr['wr'] = (byyr['wins']/byyr['trades']*100).round(1)
        fig_by = go.Figure()
        fig_by.add_trace(go.Bar(
            x=byyr['year'].astype(str), y=byyr['pnl_rs'],
            marker_color=['#0C447C' if v >= 0 else '#B5282A' for v in byyr['pnl_rs']],
            text=[f"₹{v:+,.0f}" for v in byyr['pnl_rs']], textposition='outside'))
        fig_by.update_layout(height=280, plot_bgcolor='#F5F9FF', paper_bgcolor='#F5F9FF',
            yaxis_title='P&L (₹)', margin=dict(t=10,b=20),
            yaxis=dict(tickprefix='₹', tickformat=',.0f'))
        st.plotly_chart(fig_by, use_container_width=True)

# ════════════════════════════════════════════════════════════════════════════
# TAB 3 — INFRASTRUCTURE
# ════════════════════════════════════════════════════════════════════════════
with tab3:
    infra = bi_f[bi_f['sector']=='Infrastructure'].copy()
    if infra.empty:
        st.info("No Infrastructure trades in current filter range.")
    else:
        st.markdown('<div class="sec-header">🏗️ Infrastructure Sector — Bear Regime Performance</div>', unsafe_allow_html=True)

        i_wr = infra['is_win'].mean()*100
        i_ag = infra['gross_pnl_pct'].mean()
        ik1,ik2,ik3,ik4 = st.columns(4)
        for col,(l,v) in zip([ik1,ik2,ik3,ik4],[
            ("Trades", str(len(infra))),
            ("Win Rate", f"{i_wr:.1f}%"),
            ("Avg Gross", f"{i_ag:+.3f}%"),
            ("Total ₹ P&L", f"₹{infra['pnl_rs_f'].sum():+,.0f}")]):
            with col:
                st.markdown(f"""<div class="stat-box">
                  <div class="stat-val" style="color:#1a6b3c;">{v}</div>
                  <div class="stat-lbl">{l}</div>
                </div>""", unsafe_allow_html=True)

        st.divider()

        # Per-stock
        st.markdown('<div class="sec-header">Per Stock Performance</div>', unsafe_allow_html=True)
        istk = infra.groupby(['symbol','stock_name']).agg(
            trades=('is_win','count'), wins=('is_win','sum'),
            avg_g=('gross_pnl_pct','mean'), total_rs=('pnl_rs_f','sum')
        ).reset_index()
        istk['wr'] = (istk['wins']/istk['trades']*100).round(1)
        istk = istk.sort_values('avg_g', ascending=False)

        fig_i = go.Figure()
        fig_i.add_trace(go.Bar(
            x=istk['symbol'], y=istk['avg_g'],
            marker_color=['#042C53']*len(istk),
            text=[f"{v:+.2f}%" for v in istk['avg_g']], textposition='outside'))
        fig_i.update_layout(height=280, plot_bgcolor='#F5F9FF', paper_bgcolor='#F5F9FF',
            yaxis_title='Avg Gross P&L %', margin=dict(t=10,b=20))
        st.plotly_chart(fig_i, use_container_width=True)

        idisp = istk[['symbol','stock_name','trades','wr','avg_g','total_rs']].copy()
        idisp.columns = ['Symbol','Name','Trades','Win Rate %','Avg Gross %','Total P&L (₹)']
        st.dataframe(
            idisp.style
            .format({'Win Rate %':'{:.1f}','Avg Gross %':'{:+.3f}','Total P&L (₹)':'₹{:+,.0f}'})
            .map(colour_pnl, subset=['Avg Gross %','Total P&L (₹)'])
            .map(style_wr,   subset=['Win Rate %']),
            hide_index=True, use_container_width=True)

        # All infra trades
        st.divider()
        st.markdown('<div class="sec-header">All 16 Infrastructure Trades</div>', unsafe_allow_html=True)
        iall = infra[['monday_date','symbol','gap_pct','entry_price','target_price',
                      'stop_price','stop_width','gross_pnl_pct','net_pnl_pct',
                      'exit_type','is_win','pnl_rs_f']].copy()
        iall.columns = ['Date','Symbol','Gap %','Entry','Target','Stop','Stop W %',
                        'Gross %','Net %','Exit Type','Win','P&L (₹)']
        iall['Win'] = iall['Win'].map({True:'✅ Win', False:'❌ Loss'})
        st.dataframe(
            iall.style
            .format({'Gap %':'{:.2f}%','Entry':'₹{:.2f}','Target':'₹{:.2f}',
                     'Stop':'₹{:.2f}','Stop W %':'{:.2f}%','Gross %':'{:+.3f}%',
                     'Net %':'{:+.3f}%','P&L (₹)':'₹{:+,.0f}'})
            .map(colour_pnl, subset=['Gross %','Net %','P&L (₹)']),
            hide_index=True, use_container_width=True)

# ════════════════════════════════════════════════════════════════════════════
# TAB 4 — TRADE-BY-TRADE
# ════════════════════════════════════════════════════════════════════════════
with tab4:
    st.markdown('<div class="sec-header">📋 Complete 15-Year Trade Log</div>', unsafe_allow_html=True)

    # Summary cards
    t1,t2,t3,t4,t5 = st.columns(5)
    with t1: st.metric("Total Trades",  len(bi_f))
    with t2: st.metric("Wins",          len(wins_f))
    with t3: st.metric("Losses",        len(loss_f))
    with t4: st.metric("Targets Hit",   len(bi_f[bi_f['exit_type']=='target']))
    with t5: st.metric("Stop Hit",      len(bi_f[bi_f['exit_type']=='stop']))

    st.divider()

    # Filters
    fc1, fc2, fc3 = st.columns(3)
    with fc1: sym_f   = st.multiselect("Stock", sorted(bi_f['symbol'].unique()), default=[])
    with fc2: exit_f  = st.multiselect("Exit Type", ['target','stop','eod'], default=['target','stop','eod'])
    with fc3: outcome = st.radio("Outcome", ['All','Wins only','Losses only'], horizontal=True)

    log = bi_f.copy()
    if sym_f:   log = log[log['symbol'].isin(sym_f)]
    if exit_f:  log = log[log['exit_type'].isin(exit_f)]
    if outcome == 'Wins only':   log = log[log['is_win']]
    if outcome == 'Losses only': log = log[~log['is_win']]

    disp_log = log[['monday_date','symbol','sector','gap_pct','entry_price','target_price',
                    'stop_price','stop_width','rr_ratio','gross_pnl_pct','net_pnl_pct',
                    'exit_type','is_win','pnl_rs_f','equity_f']].copy()
    disp_log.columns = ['Date','Symbol','Sector','Gap %','Entry (₹)','Target (₹)',
                        'Stop (₹)','Stop W %','R:R','Gross %','Net %',
                        'Exit','Win','P&L (₹)','Equity (₹)']
    disp_log['Win'] = disp_log['Win'].map({True:'✅','False':'❌',False:'❌'})

    st.caption(f"Showing {len(disp_log)} of {len(bi_f)} trades")
    st.dataframe(
        disp_log.style
        .format({'Gap %':'{:.2f}%','Entry (₹)':'₹{:.2f}','Target (₹)':'₹{:.2f}',
                 'Stop (₹)':'₹{:.2f}','Stop W %':'{:.2f}%','R:R':'{:.2f}',
                 'Gross %':'{:+.3f}%','Net %':'{:+.3f}%',
                 'P&L (₹)':'₹{:+,.0f}','Equity (₹)':'₹{:,.0f}'})
        .map(colour_pnl, subset=['Gross %','Net %','P&L (₹)']),
        hide_index=True, use_container_width=True, height=500)

    st.divider()

    # Best and worst 5
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**🏆 Top 5 Trades (Gross %)**")
        top5 = log.nlargest(5,'gross_pnl_pct')[['monday_date','symbol','gross_pnl_pct','exit_type','pnl_rs_f']]
        top5.columns = ['Date','Symbol','Gross %','Exit','P&L (₹)']
        st.dataframe(top5.style.format({'Gross %':'{:+.3f}%','P&L (₹)':'₹{:+,.0f}'}), hide_index=True)
    with c2:
        st.markdown("**⚠️ Bottom 5 Trades (Gross %)**")
        bot5 = log.nsmallest(5,'gross_pnl_pct')[['monday_date','symbol','gross_pnl_pct','exit_type','pnl_rs_f']]
        bot5.columns = ['Date','Symbol','Gross %','Exit','P&L (₹)']
        st.dataframe(bot5.style.format({'Gross %':'{:+.3f}%','P&L (₹)':'₹{:+,.0f}'}), hide_index=True)

# ════════════════════════════════════════════════════════════════════════════
# TAB 5 — STRATEGY INTELLIGENCE
# ════════════════════════════════════════════════════════════════════════════
with tab5:
    st.markdown('<div class="sec-header">🧭 Strategy Intelligence</div>', unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        # Gap size
        st.markdown("**Gap Size vs Performance**")
        t2 = bi_f.copy()
        bins  = [-10,-2,-1.5,-1.0,-0.5,-0.3,0]
        lbls  = ['>2%','1.5–2%','1–1.5%','0.5–1%','0.3–0.5%','<0.3%']
        t2['gbkt'] = pd.cut(t2['gap_pct'], bins=bins, labels=lbls)
        gbkt = t2.groupby('gbkt', observed=True).agg(
            t=('is_win','count'), wr=('is_win',lambda x: x.mean()*100), ag=('gross_pnl_pct','mean')
        ).reset_index()
        fig_g = px.bar(gbkt, x='gbkt', y='ag', color='ag', text='ag',
            color_continuous_scale=['#B5282A','#F5F9FF','#042C53'], color_continuous_midpoint=0,
            labels={'ag':'Avg P&L %','gbkt':'Gap Size'})
        fig_g.update_traces(texttemplate='%{text:+.2f}%', textposition='outside')
        fig_g.update_layout(height=280, plot_bgcolor='#F5F9FF', paper_bgcolor='#F5F9FF',
            coloraxis_showscale=False, margin=dict(t=10,b=20))
        st.plotly_chart(fig_g, use_container_width=True)

    with c2:
        # Stop width
        st.markdown("**Stop Width vs Performance**")
        t3 = bi_f.copy()
        sbins = [0,0.5,1.0,1.5,2.0,3.0,10]
        slbls = ['<0.5%','0.5–1%','1–1.5%','1.5–2%','2–3%','>3%']
        t3['sbkt'] = pd.cut(t3['stop_width'], bins=sbins, labels=slbls)
        sbkt = t3.groupby('sbkt', observed=True).agg(
            t=('is_win','count'), wr=('is_win',lambda x: x.mean()*100), ag=('gross_pnl_pct','mean')
        ).reset_index()
        fig_s = px.bar(sbkt, x='sbkt', y='wr', color='wr', text='wr',
            color_continuous_scale=['#B5282A','#F5F9FF','#042C53'], color_continuous_midpoint=50,
            labels={'wr':'Win Rate %','sbkt':'Stop Width'})
        fig_s.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
        fig_s.update_layout(height=280, plot_bgcolor='#F5F9FF', paper_bgcolor='#F5F9FF',
            coloraxis_showscale=False, margin=dict(t=10,b=20))
        st.plotly_chart(fig_s, use_container_width=True)

    st.divider()

    # Monthly seasonality
    st.markdown('<div class="sec-header">Monthly Seasonality</div>', unsafe_allow_html=True)
    mon_m = {1:'Jan',2:'Feb',3:'Mar',4:'Apr',5:'May',6:'Jun',7:'Jul',8:'Aug',9:'Sep',10:'Oct',11:'Nov',12:'Dec'}
    mstat = bi_f.groupby('month').agg(t=('is_win','count'), wr=('is_win',lambda x: x.mean()*100), ag=('gross_pnl_pct','mean')).reset_index()
    mstat['mn'] = mstat['month'].map(mon_m)
    fig_m = px.bar(mstat, x='mn', y='ag', color='ag', text='ag',
        color_continuous_scale=['#B5282A','#F5F9FF','#042C53'], color_continuous_midpoint=0,
        labels={'ag':'Avg P&L %','mn':''})
    fig_m.update_traces(texttemplate='%{text:+.2f}%', textposition='outside')
    fig_m.update_layout(height=280, plot_bgcolor='#F5F9FF', paper_bgcolor='#F5F9FF',
        coloraxis_showscale=False, margin=dict(t=10,b=10))
    st.plotly_chart(fig_m, use_container_width=True)

    st.divider()

    # Exit analysis
    st.markdown('<div class="sec-header">Exit Analysis</div>', unsafe_allow_html=True)
    ea = bi_f.groupby('exit_type').agg(t=('is_win','count'),wins=('is_win','sum'),ag=('gross_pnl_pct','mean')).reset_index()
    ea['wr'] = (ea['wins']/ea['t']*100).round(1)
    ea_disp = ea[['exit_type','t','wr','ag']].copy()
    ea_disp.columns = ['Exit Type','Trades','Win Rate %','Avg Gross %']
    st.dataframe(
        ea_disp.style
        .format({'Win Rate %':'{:.1f}','Avg Gross %':'{:+.3f}'})
        .map(colour_pnl, subset=['Avg Gross %'])
        .map(style_wr,   subset=['Win Rate %']),
        hide_index=True, use_container_width=True)

# ════════════════════════════════════════════════════════════════════════════
# TAB 6 — LIVE SCANNER
# ════════════════════════════════════════════════════════════════════════════
with tab6:
    st.markdown('<div class="sec-header">📡 Banking & Infrastructure Live Scanner</div>', unsafe_allow_html=True)

    # Regime status
    try:
        live_r, live_l, live_s200, live_s50 = get_regime()
    except Exception:
        live_r = 'unknown'; live_l = live_s200 = live_s50 = 0

    reg_c = {'bear':'#1a6b3c','sideways':'#9a6b1a','bull':'#B5282A'}.get(live_r,'#666')
    reg_l = {'bear':'🐻 BEAR — Scan recommended','sideways':'➡️ SIDEWAYS — Watch for regime change','bull':'🐂 BULL — Do not scan'}.get(live_r, live_r)
    st.markdown(f"""<div style="background:{'#e6f4ec' if live_r=='bear' else '#fff9f0' if live_r=='sideways' else '#fff5f5'};
        border:2px solid {reg_c};border-radius:10px;padding:12px 18px;margin-bottom:16px;">
      <div style="font-size:16px;font-weight:700;color:{reg_c};">{reg_l}</div>
      <div style="font-size:12px;color:#555;margin-top:3px;">
        Nifty 50: {live_l:,.0f} &nbsp;|&nbsp; 200-DMA: {live_s200:,.0f} &nbsp;|&nbsp;
        Bear threshold: {live_s200*0.95:,.0f}
      </div>
    </div>""", unsafe_allow_html=True)

    # Stock universe for this scanner
    BANK_STOCKS  = ['AXISBANK.NS','BANDHANBNK.NS','BANKBARODA.NS','CANBK.NS','FEDERALBNK.NS',
                    'HDFCBANK.NS','ICICIBANK.NS','IDFCFIRSTB.NS','INDUSINDBK.NS','KOTAKBANK.NS',
                    'MAHABANK.NS','PNB.NS','RBLBANK.NS','SBIN.NS','UJJIVANSFB.NS','UNIONBANK.NS','YESBANK.NS']
    INFRA_STOCKS = ['ADANIPORTS.NS','ENGINERSIN.NS','JSWINFRA.NS','LT.NS']
    ALL_STOCKS   = BANK_STOCKS + INFRA_STOCKS

    st.caption(f"Universe: {len(BANK_STOCKS)} banking stocks + {len(INFRA_STOCKS)} infra stocks = {len(ALL_STOCKS)} total")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("📅 Friday EOD Scan")
        st.caption("Run after 3:15 PM. Finds Fri High < Thu/Wed High.")
        run_fri = st.button("🔍 Run Friday Scan", type="primary" if live_r=='bear' else "secondary", use_container_width=True)
    with col2:
        st.subheader("⚡ Monday 9:20 AM Scan")
        st.caption("Run at 9:20 AM. Checks gap-down on watchlist.")
        run_mon = st.button("⚡ Run Monday Scan", type="primary" if live_r=='bear' else "secondary", use_container_width=True)

    if run_fri or run_mon:
        from backtest_engine import download_batch, compute_rsi, compute_volume_ratio

        with st.spinner(f"Scanning {len(ALL_STOCKS)} stocks…"):
            try:
                scan_end   = date.today().strftime('%Y-%m-%d')
                scan_start = (date.today() - timedelta(days=60)).strftime('%Y-%m-%d')
                all_data   = download_batch(ALL_STOCKS, scan_start, scan_end)

                results = []
                for sym, df in all_data.items():
                    if len(df) < 10: continue
                    df = df.sort_index()
                    if isinstance(df.columns, pd.MultiIndex):
                        for lvl in range(df.columns.nlevels):
                            if 'Close' in df.columns.get_level_values(lvl):
                                df.columns = df.columns.get_level_values(lvl); break
                    if 'Close' not in df.columns: continue
                    try:
                        df['RSI'] = compute_rsi(df['Close'])
                        df['Vol'] = compute_volume_ratio(df['Volume'])
                        fridays   = df[df.index.dayofweek == 4]
                        if len(fridays) == 0: continue
                        last_fri  = fridays.index[-1]
                        fri       = df.loc[last_fri]
                        prev      = df[df.index < last_fri].tail(6)
                        ref = None; ref_type = None
                        for j in range(len(prev)-1,-1,-1):
                            d = prev.index[j]
                            if d.weekday()==3: ref=prev.iloc[j]; ref_type='Thu'; break
                            if d.weekday()==2:
                                if (d+timedelta(days=1)) not in df.index:
                                    ref=prev.iloc[j]; ref_type='Wed'; break
                                break
                        if ref is None or float(fri['High']) >= float(ref['High']): continue
                        sym_c     = sym.replace('.NS','')
                        sector_n  = 'Banking' if sym in BANK_STOCKS else 'Infrastructure'
                        hist      = bi_f[bi_f['symbol']==sym_c]
                        hist_wr   = round(hist['is_win'].mean()*100, 1) if len(hist)>3 else None
                        rsi_v     = float(fri['RSI']) if not pd.isna(fri['RSI']) else None
                        results.append({
                            'Symbol':    sym_c,
                            'Sector':    sector_n,
                            'Ref':       ref_type,
                            'Fri High':  round(float(fri['High']),2),
                            'Fri Low':   round(float(fri['Low']),2),
                            'Fri Close': round(float(fri['Close']),2),
                            'RSI':       round(rsi_v,1) if rsi_v else '—',
                            'Hist WR%':  hist_wr,
                            'Fri Date':  last_fri.date(),
                        })
                    except Exception:
                        pass

                if results:
                    wl = pd.DataFrame(results).sort_values('Hist WR%', ascending=False, na_position='last')
                    st.success(f"✅ {len(wl)} stocks meet Friday setup")

                    if run_mon:
                        sigs = []
                        for _, row in wl.iterrows():
                            sym_full = row['Symbol']+'.NS'
                            if sym_full not in all_data: continue
                            dfd  = all_data[sym_full]
                            mons = dfd[dfd.index.dayofweek==0]
                            if len(mons)==0: continue
                            lm   = mons.index[-1]
                            if lm.date() <= row['Fri Date']: continue
                            mon  = dfd.loc[lm]
                            entry = float(mon['Open'])
                            target= row['Fri Low']; stop=row['Fri High']
                            gap   = (entry - row['Fri Close'])/row['Fri Close']*100
                            if gap>=-0.3 or entry<=target: continue
                            risk  = (stop-entry)/entry*100
                            rwd   = (entry-target)/entry*100
                            rr    = rwd/risk if risk>0 else 0
                            cap_s = st.session_state.get('cap_input', 500000)
                            rp    = st.session_state.get('rp_input', 0.01)
                            shares= max(1, int(cap_s*rp/(entry*risk/100))) if risk>0 else 1
                            sigs.append({
                                'Symbol':   row['Symbol'], 'Sector': row['Sector'],
                                'Gap %':    round(gap,2), 'Entry':  round(entry,2),
                                'Target ↓': round(target,2), 'Stop ↑': round(stop,2),
                                'Risk %':   round(risk,2), 'Reward %': round(rwd,2),
                                'R:R':      round(rr,2), 'Shares': shares,
                                'Hist WR%': row['Hist WR%'],
                            })
                        if sigs:
                            sdf = pd.DataFrame(sigs).sort_values('Hist WR%', ascending=False, na_position='last')
                            st.subheader(f"⚡ {len(sdf)} Trade Signal(s)")
                            st.dataframe(
                                sdf.style.format({
                                    'Gap %':'{:.2f}%','Entry':'₹{:.2f}','Target ↓':'₹{:.2f}',
                                    'Stop ↑':'₹{:.2f}','Risk %':'{:.2f}%','Reward %':'{:.2f}%','R:R':'{:.2f}'
                                }).map(style_wr, subset=['Hist WR%']),
                                hide_index=True, use_container_width=True)
                        else:
                            st.info("No gap-down signals today from the watchlist.")
                    else:
                        st.dataframe(
                            wl.drop(columns=['Fri Date']).style.map(style_wr, subset=['Hist WR%']),
                            hide_index=True, use_container_width=True)
                else:
                    st.info("No Friday setup stocks today.")
            except Exception as e:
                st.error(f"Scanner error: {e}")
                import traceback; st.code(traceback.format_exc())

# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.markdown("""
<div style='text-align:center;color:#5a7a98;font-size:12px;padding:8px 0;'>
  Banking & Infrastructure FM Strategy Platform &nbsp;|&nbsp; 15-Year Backtest 2011–2026 &nbsp;|&nbsp;
  Bear Regime Only &nbsp;|&nbsp; ⚠️ Research use only. Not financial advice. Always use stop losses.
</div>
""", unsafe_allow_html=True)
