"""
FRIDAY-MONDAY PATTERN TRADING SYSTEM v2.0
15-Year Backtest | Nifty 250 | Live Scanner | Email Automation
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, date, timedelta
import os, warnings
warnings.filterwarnings('ignore')

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="FM Trading System",
    page_icon="📉",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700&family=Inter:wght@400;500;600&display=swap');
  html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
  h1, h2 { font-family: 'Playfair Display', serif !important; }
  .kpi-box {
    background: linear-gradient(135deg, #fff5f0 0%, #fff8f2 100%);
    border: 1px solid #e8c8b0; border-radius: 12px;
    padding: 18px 20px; text-align: center; margin-bottom: 4px;
  }
  .kpi-label { font-size: 11px; color: #7a5c4e; letter-spacing: 0.06em; text-transform: uppercase; margin-bottom: 6px; }
  .kpi-value { font-size: 28px; font-weight: 700; color: #B5282A; font-family: 'Playfair Display', serif; }
  .kpi-sub   { font-size: 11px; color: #9a7060; margin-top: 4px; }
  .kpi-green { color: #1a6b3c !important; }
  .kpi-red   { color: #B5282A !important; }
  .kpi-gold  { color: #9a6b1a !important; }
  .stat-card {
    background: #fff9f5; border: 1px solid #ecd8c8;
    border-radius: 10px; padding: 14px 16px; margin-bottom: 8px;
  }
  .stat-title { font-weight: 600; font-size: 13px; color: #4a2010; margin-bottom: 6px; }
  .stat-body  { font-size: 12px; color: #5a4038; line-height: 1.6; }
  .section-header {
    font-family: 'Playfair Display', serif;
    font-size: 20px; color: #2a1008; margin: 8px 0 16px;
    border-bottom: 2px solid #e8c8b0; padding-bottom: 8px;
  }
  div[data-testid="metric-container"] {
    background: #fff9f5; border: 1px solid #e8c0a0;
    border-radius: 10px; padding: 10px 16px;
  }
  .stTabs [data-baseweb="tab-list"] { gap: 4px; }
  .stTabs [data-baseweb="tab"] {
    background: #fff5f0; border-radius: 8px 8px 0 0;
    padding: 8px 18px; font-size: 13px; font-weight: 500;
    color: #7a5c4e !important;
  }
  .stTabs [aria-selected="true"] {
    background: #B5282A !important; color: white !important;
  }
  .regime-badge {
    display: inline-block; padding: 4px 14px; border-radius: 20px;
    font-size: 12px; font-weight: 700; letter-spacing: 0.05em;
  }
  .badge-bear     { background: #e6f4ec; color: #1a6b3c; }
  .badge-sideways { background: #fef5e0; color: #9a6b1a; }
  .badge-bull     { background: #fde8e8; color: #B5282A; }
</style>
""", unsafe_allow_html=True)

COST_PCT = 0.05

# ── Helpers ───────────────────────────────────────────────────────────────────
def kpi(label, value, sub="", color="kpi-value"):
    return f"""<div class="kpi-box">
        <div class="kpi-label">{label}</div>
        <div class="{color}">{value}</div>
        <div class="kpi-sub">{sub}</div>
    </div>"""

def colour_pnl(val):
    if not isinstance(val, (int, float)): return ''
    c = "#1a6b3c" if val >= 0 else "#B5282A"
    return f"color:{c}; font-weight:600"

# ── Data loading ──────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def load_data():
    try:
        trades  = pd.read_csv('backtest_trades.csv', parse_dates=['friday_date','monday_date'])
        summary = pd.read_csv('backtest_summary.csv')
        trades['valid']        = trades['entry_price'] > trades['target_price']
        trades['stop_width']   = (trades['stop_price']  - trades['entry_price']) / trades['entry_price'] * 100
        trades['target_depth'] = (trades['entry_price'] - trades['target_price']) / trades['entry_price'] * 100
        trades['rr_ratio']     = trades['target_depth'] / trades['stop_width']
        return trades, summary
    except Exception as e:
        st.error(f"Could not load backtest data: {e}")
        return pd.DataFrame(), pd.DataFrame()

@st.cache_data(ttl=300)
def load_live_data():
    try:
        from supabase import create_client
        url = st.secrets.get("SUPABASE_URL", os.environ.get("SUPABASE_URL", ""))
        key = st.secrets.get("SUPABASE_KEY", os.environ.get("SUPABASE_KEY", ""))
        if not url or not key:
            return pd.DataFrame(), pd.DataFrame()
        sb  = create_client(url, key)
        wl  = sb.table('fm_friday_watchlist').select('*').order('scan_date', desc=True).limit(200).execute()
        sg  = sb.table('fm_monday_signals').select('*').order('signal_date', desc=True).limit(200).execute()
        return (pd.DataFrame(wl.data) if wl.data else pd.DataFrame(),
                pd.DataFrame(sg.data) if sg.data else pd.DataFrame())
    except Exception:
        return pd.DataFrame(), pd.DataFrame()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('<div style="font-family:Playfair Display,serif;font-size:22px;font-weight:700;color:#B5282A;">📉 FM System v2</div>', unsafe_allow_html=True)
    st.caption("Friday-Monday SHORT | Nifty 250")
    st.divider()

    st.subheader("🔍 Backtest Filters")
    apply_valid_filter = st.checkbox(
        "Entry > Target only", value=True,
        help="Skip trades where Monday Open fell below Friday Low (no valid SHORT setup).")
    regime_filter = st.multiselect(
        "Market Regime", ['bear','sideways','bull'],
        default=['bear','sideways','bull'])
    max_stop_width = st.slider("Max Stop Width %", 0.5, 3.0, 3.0, 0.1,
        help="Distance from entry to Friday High (stop). Tighter = better R:R.")
    min_gap = st.slider("Min Gap Down %", 0.3, 2.0, 0.3, 0.1)
    max_gap = st.slider("Max Gap Down %", 0.5, 5.0, 5.0, 0.5)

    st.divider()
    st.subheader("💰 Position Sizing")
    capital  = st.number_input("Capital (₹)", 50000, 10000000, 500000, 50000)
    risk_pct = st.slider("Risk per trade %", 0.25, 2.0, 1.0, 0.25)

    st.divider()
    st.caption(f"Universe: Nifty LargeMidCap 250")
    st.caption(f"Period: 2011-04-01 → today")
    st.caption(f"Source: yfinance | Supabase")

# ── Load & filter ─────────────────────────────────────────────────────────────
all_trades, summary = load_data()

if all_trades.empty:
    st.error("⚠️ Backtest data not found. Ensure backtest_trades.csv is in the repo root.")
    st.stop()

def apply_filters(df):
    f = df.copy()
    if apply_valid_filter:
        f = f[f['valid']]
    f = f[f['regime'].isin(regime_filter)]
    f = f[f['stop_width'] <= max_stop_width]
    f = f[f['gap_pct'].abs() >= min_gap]
    f = f[f['gap_pct'].abs() <= max_gap]
    return f

trades = apply_filters(all_trades)

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown('<h1 style="color:#B5282A;margin-bottom:4px;">📉 Friday-Monday Pattern System</h1>', unsafe_allow_html=True)
st.caption(f"SHORT Strategy  •  Nifty 250  •  {len(trades):,} trades match current filters")

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🏠 Dashboard", "📊 Backtest Results", "🧭 Strategy Intelligence",
    "📡 Live Scanner", "📋 Signal History"
])

# ════════════════════════════════════════════════════════════════════════════
# TAB 1 — DASHBOARD
# ════════════════════════════════════════════════════════════════════════════
with tab1:
    if len(trades) == 0:
        st.warning("No trades match current filters. Adjust sidebar parameters.")
    else:
        wr    = trades['is_win'].mean() * 100
        wins  = trades[trades['is_win']]
        loss  = trades[~trades['is_win']]
        avg_g = trades['gross_pnl_pct'].mean()
        avg_n = trades['net_pnl_pct'].mean()
        avg_w = wins['gross_pnl_pct'].mean()  if len(wins)  else 0
        avg_l = loss['gross_pnl_pct'].mean()  if len(loss)  else 0
        pf    = (abs(wins['gross_pnl_pct'].sum()) / abs(loss['gross_pnl_pct'].sum())
                 if len(loss) and loss['gross_pnl_pct'].sum() != 0 else 0)

        # ── Top KPIs ──────────────────────────────────────────────────────
        k1, k2, k3, k4 = st.columns(4)
        with k1:
            clr = "kpi-green" if wr >= 50 else "kpi-red"
            st.markdown(kpi("Win Rate", f"{wr:.1f}%", f"{len(trades):,} trades", clr), unsafe_allow_html=True)
        with k2:
            clr = "kpi-green" if avg_g >= 0 else "kpi-red"
            st.markdown(kpi("Avg Gross P&L", f"{avg_g:+.3f}%", "per trade", clr), unsafe_allow_html=True)
        with k3:
            clr = "kpi-green" if avg_n >= 0 else "kpi-red"
            st.markdown(kpi("Avg Net P&L", f"{avg_n:+.3f}%", f"after {COST_PCT}% costs", clr), unsafe_allow_html=True)
        with k4:
            clr = "kpi-green" if pf >= 1.0 else "kpi-red"
            st.markdown(kpi("Profit Factor", f"{pf:.3f}", "wins÷losses", clr), unsafe_allow_html=True)

        st.divider()

        # ── Win/Loss profile ──────────────────────────────────────────────
        m1, m2, m3, m4, m5, m6 = st.columns(6)
        with m1: st.metric("Winning Trades", f"{len(wins):,}")
        with m2: st.metric("Losing Trades",  f"{len(loss):,}")
        with m3: st.metric("Avg Win",  f"{avg_w:+.3f}%")
        with m4: st.metric("Avg Loss", f"{avg_l:+.3f}%")
        with m5: st.metric("Stocks Covered", f"{trades['symbol'].nunique()}")
        with m6: st.metric("Years", f"{trades['year'].nunique()}")

        st.divider()

        # ── Regime breakdown ──────────────────────────────────────────────
        st.markdown('<div class="section-header">Performance by Market Regime</div>', unsafe_allow_html=True)

        reg_cols = st.columns(3)
        for col, reg, icon in zip(reg_cols, ['bear','sideways','bull'], ['🐻','➡️','🐂']):
            sub = all_trades[all_trades['valid'] & (all_trades['regime'] == reg)]
            if len(sub) == 0:
                continue
            r_wr  = sub['is_win'].mean() * 100
            r_avg = sub['gross_pnl_pct'].mean()
            clr   = "#1a6b3c" if r_avg >= 0 else "#B5282A"
            label = "✅ Positive EV" if r_avg >= 0 else ("⚠️ Marginal" if r_avg > -0.3 else "❌ Negative EV")
            with col:
                st.markdown(f"""<div class="kpi-box">
                    <div class="kpi-label">{icon} {reg.title()} Regime</div>
                    <div style="font-size:20px;font-weight:700;color:{clr};">{label}</div>
                    <div class="kpi-sub">WR {r_wr:.1f}%  •  Avg {r_avg:+.3f}%  •  {len(sub):,} trades</div>
                </div>""", unsafe_allow_html=True)

        st.divider()

        # ── Key observations ──────────────────────────────────────────────
        st.markdown('<div class="section-header">Key Observations</div>', unsafe_allow_html=True)
        o1, o2 = st.columns(2)

        bear_sub = all_trades[all_trades['valid'] & (all_trades['regime']=='bear')]
        bull_sub = all_trades[all_trades['valid'] & (all_trades['regime']=='bull')]
        r_b = bear_sub['gross_pnl_pct'].mean() if len(bear_sub) else 0
        r_u = bull_sub['gross_pnl_pct'].mean() if len(bull_sub) else 0

        top_sec = (all_trades[all_trades['valid'] & (all_trades['regime']=='bear')]
                   .groupby('sector')['gross_pnl_pct'].mean()
                   .nlargest(3).index.tolist())
        top_sec_str = ", ".join(top_sec) if top_sec else "—"

        with o1:
            st.markdown(f"""<div class="stat-card">
                <div class="stat-title">📌 Entry Rule: Monday Open must be above Friday Low</div>
                <div class="stat-body">This filter removes setups where the gap is so large that
                there is no room to run further down. Only trades where Monday Open &gt; Friday Low
                (entry &gt; target) are valid shorts. Remaining {len(all_trades[all_trades['valid']]):,}
                trades from the full {len(all_trades):,} qualify.</div>
            </div>""", unsafe_allow_html=True)

            st.markdown(f"""<div class="stat-card">
                <div class="stat-title">📌 Stop Width Matters</div>
                <div class="stat-body">Average win: <b>{avg_w:+.2f}%</b> vs average loss:
                <b>{avg_l:+.2f}%</b>. A wide Friday High stop can give back multiple wins in one loss.
                Use the Max Stop Width filter on the sidebar to focus on tighter setups.</div>
            </div>""", unsafe_allow_html=True)

        with o2:
            st.markdown(f"""<div class="stat-card">
                <div class="stat-title">📌 Regime is the Primary Edge Driver</div>
                <div class="stat-body">Bear regime average: <b>{r_b:+.3f}%</b> per trade.
                Bull regime average: <b>{r_u:+.3f}%</b> per trade. Nifty 50's position
                relative to its 200-DMA is the single most important filter before entering
                any trade from this system.</div>
            </div>""", unsafe_allow_html=True)

            st.markdown(f"""<div class="stat-card">
                <div class="stat-title">📌 Best Sectors in Bear Regime</div>
                <div class="stat-body">Top-performing sectors (by avg gross P&L) in bear markets:
                <b>{top_sec_str}</b>. Prioritise these stocks when the watchlist is long and
                you need to narrow down which signals to take.</div>
            </div>""", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════════════════
# TAB 2 — BACKTEST RESULTS
# ════════════════════════════════════════════════════════════════════════════
with tab2:
    if len(trades) == 0:
        st.warning("No data for current filters.")
    else:
        # ── Year-by-year ──────────────────────────────────────────────────
        st.markdown('<div class="section-header">Year-by-Year Performance</div>', unsafe_allow_html=True)

        ystat = trades.groupby('year').agg(
            trades_ =('is_win','count'),
            wins_   =('is_win','sum'),
            gross_  =('gross_pnl_pct','mean'),
            net_    =('net_pnl_pct','mean'),
        ).reset_index()
        ystat['win_rate'] = (ystat['wins_'] / ystat['trades_'] * 100).round(1)
        ystat['gross_']   = ystat['gross_'].round(3)
        ystat['net_']     = ystat['net_'].round(3)

        colors = ['#1a6b3c' if g >= 0 else '#B5282A' for g in ystat['gross_']]
        fig_yr = go.Figure()
        fig_yr.add_trace(go.Bar(
            x=ystat['year'].astype(str), y=ystat['gross_'],
            marker_color=colors, name='Avg Gross P&L %'))
        fig_yr.add_trace(go.Scatter(
            x=ystat['year'].astype(str), y=ystat['win_rate'],
            mode='lines+markers', name='Win Rate %', yaxis='y2',
            line=dict(color='#C8860A', width=2), marker=dict(size=6)))
        fig_yr.update_layout(
            height=320,
            yaxis =dict(title='Avg Gross P&L %', zeroline=True, zerolinecolor='#B5282A', zerolinewidth=1.5),
            yaxis2=dict(title='Win Rate %', overlaying='y', side='right', range=[20,80]),
            plot_bgcolor='#FFFAF6', paper_bgcolor='#FFFAF6',
            legend=dict(orientation='h', x=0, y=1.1),
            margin=dict(t=20, b=20)
        )
        st.plotly_chart(fig_yr, use_container_width=True)

        disp = ystat[['year','trades_','win_rate','gross_','net_']].copy()
        disp.columns = ['Year','Trades','Win Rate %','Avg Gross %','Avg Net %']
        st.dataframe(
            disp.style
            .format({'Win Rate %':'{:.1f}', 'Avg Gross %':'{:+.3f}', 'Avg Net %':'{:+.3f}'})
            .map(colour_pnl, subset=['Avg Gross %','Avg Net %']),
            hide_index=True, use_container_width=True
        )

        st.divider()

        # ── Exit type breakdown ───────────────────────────────────────────
        st.markdown('<div class="section-header">Exit Type Breakdown</div>', unsafe_allow_html=True)

        et_wins = trades.groupby('exit_type').agg(
            wins=('is_win','sum'), total=('is_win','count'), avg_pnl=('gross_pnl_pct','mean')
        ).reset_index()
        et = trades['exit_type'].value_counts().reset_index()
        et.columns = ['exit_type','count']

        c1, c2 = st.columns([1,2])
        with c1:
            fig_pie = go.Figure(go.Pie(
                labels=et['exit_type'], values=et['count'],
                marker_colors=['#1a6b3c','#B5282A','#C8860A'], hole=0.4))
            fig_pie.update_layout(height=250, margin=dict(t=10,b=10), paper_bgcolor='#FFFAF6')
            st.plotly_chart(fig_pie, use_container_width=True)
        with c2:
            st.write("")
            for _, row in et_wins.iterrows():
                wr_e = row['wins'] / row['total'] * 100
                c = "🟢" if row['avg_pnl'] >= 0 else "🔴"
                st.markdown(f"{c} **{row['exit_type'].upper()}** — {row['total']:,} trades | "
                            f"WR: {wr_e:.1f}% | Avg P&L: {row['avg_pnl']:+.3f}%")

        st.divider()

        # ── Top stocks ────────────────────────────────────────────────────
        st.markdown('<div class="section-header">Top Stocks by Avg Gross P&L (min 15 trades)</div>', unsafe_allow_html=True)

        stock_stats = (trades
            .groupby(['symbol','stock_name','sector','tier'])
            .agg(trades_=('is_win','count'), wr=('is_win',lambda x: x.mean()*100),
                 avg_g=('gross_pnl_pct','mean'), total_g=('gross_pnl_pct','sum'))
            .reset_index()
            .query('trades_ >= 15')
            .sort_values('avg_g', ascending=False))

        top25 = stock_stats.head(25)
        fig_top = go.Figure()
        fig_top.add_trace(go.Bar(
            y=top25['symbol'], x=top25['avg_g'], orientation='h',
            marker_color=['#1a6b3c' if v >= 0 else '#B5282A' for v in top25['avg_g']]))
        fig_top.update_layout(
            height=500, yaxis_title='', xaxis_title='Avg Gross P&L %',
            plot_bgcolor='#FFFAF6', paper_bgcolor='#FFFAF6', margin=dict(t=10,b=10))
        st.plotly_chart(fig_top, use_container_width=True)

        with st.expander("📋 Full Stock Performance Table"):
            disp2 = stock_stats[['symbol','stock_name','sector','tier','trades_','wr','avg_g','total_g']].copy()
            disp2.columns = ['Symbol','Name','Sector','Tier','Trades','Win Rate %','Avg Gross %','Total Gross %']
            st.dataframe(
                disp2.style
                .format({'Win Rate %':'{:.1f}','Avg Gross %':'{:+.3f}','Total Gross %':'{:+.1f}'})
                .map(colour_pnl, subset=['Avg Gross %']),
                hide_index=True, use_container_width=True
            )

# ════════════════════════════════════════════════════════════════════════════
# TAB 3 — STRATEGY INTELLIGENCE
# ════════════════════════════════════════════════════════════════════════════
with tab3:
    if len(trades) == 0:
        st.warning("No data for current filters.")
    else:
        # ── Sector performance ────────────────────────────────────────────
        st.markdown('<div class="section-header">Sector Performance (Avg Gross P&L)</div>', unsafe_allow_html=True)

        sec = (trades.groupby('sector')
               .agg(trades_=('is_win','count'), wr=('is_win',lambda x: x.mean()*100), avg_g=('gross_pnl_pct','mean'))
               .reset_index().query('trades_ >= 20').sort_values('avg_g', ascending=False))

        fig_sec = px.bar(sec, x='sector', y='avg_g',
            color='avg_g', color_continuous_scale=['#B5282A','#f5f0eb','#1a6b3c'],
            color_continuous_midpoint=0, text='avg_g',
            labels={'avg_g':'Avg Gross P&L %','sector':'Sector'})
        fig_sec.update_traces(texttemplate='%{text:+.2f}%', textposition='outside')
        fig_sec.update_layout(height=360, plot_bgcolor='#FFFAF6', paper_bgcolor='#FFFAF6',
            coloraxis_showscale=False, margin=dict(t=20,b=60), xaxis_tickangle=-35)
        st.plotly_chart(fig_sec, use_container_width=True)

        # ── Regime × Sector heatmap ───────────────────────────────────────
        st.markdown('<div class="section-header">Regime × Sector Matrix</div>', unsafe_allow_html=True)

        pivot = trades.pivot_table(
            index='sector', columns='regime', values='gross_pnl_pct', aggfunc='mean').fillna(0)
        pivot = pivot.reindex(columns=[c for c in ['bear','sideways','bull'] if c in pivot.columns])
        fig_heat = px.imshow(pivot, color_continuous_scale='RdYlGn', aspect='auto',
            labels=dict(color='Avg P&L %'), text_auto='.2f', zmin=-2, zmax=2)
        fig_heat.update_layout(height=500, plot_bgcolor='#FFFAF6',
            paper_bgcolor='#FFFAF6', margin=dict(t=10))
        st.plotly_chart(fig_heat, use_container_width=True)

        st.divider()

        # ── Gap bucket analysis ───────────────────────────────────────────
        st.markdown('<div class="section-header">Gap Size Analysis</div>', unsafe_allow_html=True)

        t2 = trades.copy()
        bins   = [-10, -2, -1.5, -1.0, -0.5, -0.3, 0]
        labels = ['>2%', '1.5–2%', '1–1.5%', '0.5–1%', '0.3–0.5%', '<0.3%']
        t2['gap_bucket'] = pd.cut(t2['gap_pct'], bins=bins, labels=labels)
        gbkt = t2.groupby('gap_bucket', observed=True).agg(
            trades_  =('is_win','count'),
            wr       =('is_win', lambda x: x.mean()*100),
            avg_g    =('gross_pnl_pct','mean'),
        ).reset_index()

        c1, c2 = st.columns(2)
        with c1:
            fig_g1 = px.bar(gbkt, x='gap_bucket', y='wr', color='wr', text='wr',
                color_continuous_scale=['#B5282A','#f5f0eb','#1a6b3c'], color_continuous_midpoint=50,
                labels={'wr':'Win Rate %','gap_bucket':'Gap Size'})
            fig_g1.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
            fig_g1.update_layout(height=300, plot_bgcolor='#FFFAF6', paper_bgcolor='#FFFAF6',
                coloraxis_showscale=False, margin=dict(t=20,b=20), title="Win Rate by Gap Size")
            st.plotly_chart(fig_g1, use_container_width=True)
        with c2:
            fig_g2 = px.bar(gbkt, x='gap_bucket', y='avg_g', color='avg_g', text='avg_g',
                color_continuous_scale=['#B5282A','#f5f0eb','#1a6b3c'], color_continuous_midpoint=0,
                labels={'avg_g':'Avg Gross P&L %','gap_bucket':'Gap Size'})
            fig_g2.update_traces(texttemplate='%{text:+.3f}%', textposition='outside')
            fig_g2.update_layout(height=300, plot_bgcolor='#FFFAF6', paper_bgcolor='#FFFAF6',
                coloraxis_showscale=False, margin=dict(t=20,b=20), title="Avg P&L by Gap Size")
            st.plotly_chart(fig_g2, use_container_width=True)

        st.divider()

        # ── RSI analysis ──────────────────────────────────────────────────
        st.markdown('<div class="section-header">RSI at Friday Close</div>', unsafe_allow_html=True)

        t3 = trades.dropna(subset=['fri_rsi']).copy()
        t3['rsi_bucket'] = pd.cut(t3['fri_rsi'],
            bins=[0,30,40,50,60,70,80,100],
            labels=['<30','30–40','40–50','50–60','60–70','70–80','>80'])
        rbkt = t3.groupby('rsi_bucket', observed=True).agg(
            trades_=('is_win','count'), wr=('is_win',lambda x: x.mean()*100), avg_g=('gross_pnl_pct','mean')
        ).reset_index()
        fig_rsi = px.bar(rbkt, x='rsi_bucket', y='avg_g', color='avg_g', text='avg_g',
            color_continuous_scale=['#B5282A','#f5f0eb','#1a6b3c'], color_continuous_midpoint=0,
            labels={'avg_g':'Avg Gross P&L %','rsi_bucket':'RSI Range'})
        fig_rsi.update_traces(texttemplate='%{text:+.3f}%', textposition='outside')
        fig_rsi.update_layout(height=300, plot_bgcolor='#FFFAF6', paper_bgcolor='#FFFAF6',
            coloraxis_showscale=False, margin=dict(t=20,b=20))
        st.plotly_chart(fig_rsi, use_container_width=True)

        st.divider()

        # ── Monthly seasonality ───────────────────────────────────────────
        st.markdown('<div class="section-header">Monthly Seasonality</div>', unsafe_allow_html=True)
        mstat = trades.groupby('month').agg(
            trades_=('is_win','count'), wr=('is_win',lambda x: x.mean()*100), avg_g=('gross_pnl_pct','mean')
        ).reset_index()
        mstat['month_name'] = mstat['month'].map({
            1:'Jan',2:'Feb',3:'Mar',4:'Apr',5:'May',6:'Jun',
            7:'Jul',8:'Aug',9:'Sep',10:'Oct',11:'Nov',12:'Dec'})
        fig_m = px.bar(mstat, x='month_name', y='avg_g', color='avg_g', text='avg_g',
            color_continuous_scale=['#B5282A','#f5f0eb','#1a6b3c'], color_continuous_midpoint=0,
            labels={'avg_g':'Avg Gross P&L %','month_name':''})
        fig_m.update_traces(texttemplate='%{text:+.3f}%', textposition='outside')
        fig_m.update_layout(height=280, plot_bgcolor='#FFFAF6', paper_bgcolor='#FFFAF6',
            coloraxis_showscale=False, margin=dict(t=10,b=10))
        st.plotly_chart(fig_m, use_container_width=True)

# ════════════════════════════════════════════════════════════════════════════
# TAB 4 — LIVE SCANNER
# ════════════════════════════════════════════════════════════════════════════
with tab4:
    st.markdown('<div class="section-header">Live Pattern Scanner</div>', unsafe_allow_html=True)

    # Regime check
    st.subheader("Market Regime (Live)")
    if st.button("🔄 Check Current Nifty Regime", type="primary"):
        with st.spinner("Fetching Nifty 50…"):
            try:
                import yfinance as yf
                nifty = yf.download('^NSEI', period='1y', auto_adjust=True, progress=False)
                if isinstance(nifty.columns, pd.MultiIndex):
                    for lvl in range(nifty.columns.nlevels):
                        if 'Close' in nifty.columns.get_level_values(lvl):
                            nifty.columns = nifty.columns.get_level_values(lvl); break
                close = nifty['Close'].dropna()
                last  = float(close.iloc[-1])
                s200  = float(close.rolling(200).mean().iloc[-1])
                s50   = float(close.rolling(50).mean().iloc[-1])
                if last < s200 * 0.95:
                    reg, clr = "🐻 BEAR", "#1a6b3c"
                elif last > s200 * 1.05:
                    reg, clr = "🐂 BULL", "#B5282A"
                else:
                    reg, clr = "➡️ SIDEWAYS", "#9a6b1a"
                st.markdown(f"<h3 style='color:{clr};'>{reg}</h3>", unsafe_allow_html=True)
                st.caption(f"Nifty 50: {last:,.0f}  •  200-DMA: {s200:,.0f}  •  50-DMA: {s50:,.0f}")
            except Exception as e:
                st.error(f"Could not fetch: {e}")

    st.divider()

    # Scanner buttons
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Friday EOD Scanner")
        st.caption("Run after 3:15 PM on any Friday. Finds stocks where Fri High < Thu High.")
        run_fri = st.button("🔍 Run Friday Scan", use_container_width=True)
    with col2:
        st.subheader("Monday 9:20 AM Scanner")
        st.caption("Run at 9:20 AM on Mondays. Checks gap-down from Friday watchlist.")
        run_mon = st.button("⚡ Run Monday Scan", use_container_width=True)

    if run_fri or run_mon:
        from nifty250_stocks import NIFTY_250_STOCKS
        from backtest_engine import download_batch, compute_rsi, compute_volume_ratio

        with st.spinner("Downloading data… (this takes ~30s)"):
            try:
                import yfinance as yf

                scan_end   = date.today().strftime('%Y-%m-%d')
                scan_start = (date.today() - timedelta(days=60)).strftime('%Y-%m-%d')
                symbols    = list(NIFTY_250_STOCKS.keys())

                all_data = {}
                for chunk in [symbols[i:i+65] for i in range(0, len(symbols), 65)]:
                    all_data.update(download_batch(chunk, scan_start, scan_end))

                # Regime
                ndata  = yf.download('^NSEI', start=scan_start, auto_adjust=True, progress=False)
                if isinstance(ndata.columns, pd.MultiIndex):
                    for lvl in range(ndata.columns.nlevels):
                        if 'Close' in ndata.columns.get_level_values(lvl):
                            ndata.columns = ndata.columns.get_level_values(lvl); break
                nc     = ndata['Close'].dropna()
                nlast  = float(nc.iloc[-1])
                ns200  = float(nc.rolling(200).mean().iloc[-1])
                regime_now = 'bear' if nlast < ns200*0.95 else ('bull' if nlast > ns200*1.05 else 'sideways')

                results = []
                for sym, df in all_data.items():
                    if len(df) < 15:
                        continue
                    df = df.sort_index()
                    if isinstance(df.columns, pd.MultiIndex):
                        for lvl in range(df.columns.nlevels):
                            if 'Close' in df.columns.get_level_values(lvl):
                                df.columns = df.columns.get_level_values(lvl); break
                    if 'Close' not in df.columns:
                        continue
                    try:
                        df['RSI']      = compute_rsi(df['Close'])
                        df['VolRatio'] = compute_volume_ratio(df['Volume'])
                        df['SMA20']    = df['Close'].rolling(20).mean()

                        fridays   = df[df.index.dayofweek == 4]
                        if len(fridays) == 0:
                            continue
                        last_fri  = fridays.index[-1]
                        fri       = df.loc[last_fri]

                        prev = df[df.index < last_fri].tail(6)
                        ref  = None; ref_type = None
                        for j in range(len(prev)-1, -1, -1):
                            d = prev.index[j]
                            if d.weekday() == 3:
                                ref = prev.iloc[j]; ref_type = 'Thu'; break
                            if d.weekday() == 2:
                                if (d + timedelta(days=1)) not in df.index:
                                    ref = prev.iloc[j]; ref_type = 'Wed'; break
                                break
                        if ref is None or float(fri['High']) >= float(ref['High']):
                            continue

                        info     = NIFTY_250_STOCKS.get(sym, {})
                        sym_clean = sym.replace('.NS','')
                        hist     = all_trades[all_trades['valid'] & (all_trades['symbol'] == sym_clean)]
                        hist_wr  = round(hist['is_win'].mean()*100, 1) if len(hist) > 5 else None

                        rsi_v = float(fri['RSI']) if not pd.isna(fri['RSI']) else None
                        vol_v = float(fri['VolRatio']) if not pd.isna(fri['VolRatio']) else None

                        results.append({
                            'Symbol':    sym_clean,
                            'Name':      info.get('name', sym_clean),
                            'Sector':    info.get('sector','?'),
                            'Ref':       ref_type,
                            'Fri High':  round(float(fri['High']), 2),
                            'Fri Low':   round(float(fri['Low']),  2),
                            'Fri Close': round(float(fri['Close']),2),
                            'RSI':       round(rsi_v, 1) if rsi_v else '—',
                            'Vol Ratio': round(vol_v, 2) if vol_v else '—',
                            'Hist WR%':  hist_wr,
                            'Fri Date':  last_fri.date(),
                        })
                    except Exception:
                        pass

                badge_col = {'bear':'badge-bear','sideways':'badge-sideways','bull':'badge-bull'}
                st.markdown(
                    f'Regime: <span class="regime-badge {badge_col.get(regime_now,"")}">{"🐻 BEAR" if regime_now=="bear" else "🐂 BULL" if regime_now=="bull" else "➡️ SIDEWAYS"}</span>',
                    unsafe_allow_html=True)

                if results:
                    wl_df = pd.DataFrame(results).sort_values('Hist WR%', ascending=False, na_position='last')
                    st.success(f"✅ {len(wl_df)} stocks meet Friday setup condition")

                    if run_mon:
                        sigs = []
                        for _, row in wl_df.iterrows():
                            sym_full = row['Symbol'] + '.NS'
                            if sym_full not in all_data:
                                continue
                            dfd = all_data[sym_full]
                            mons = dfd[dfd.index.dayofweek == 0]
                            if len(mons) == 0:
                                continue
                            last_mon = mons.index[-1]
                            if last_mon.date() <= row['Fri Date']:
                                continue
                            mon     = dfd.loc[last_mon]
                            entry   = float(mon['Open'])
                            target  = row['Fri Low']
                            stop    = row['Fri High']
                            gap     = (entry - row['Fri Close']) / row['Fri Close'] * 100
                            if gap >= -0.3 or entry <= target:
                                continue
                            risk   = (stop - entry) / entry * 100
                            reward = (entry - target) / entry * 100
                            rr     = reward / risk if risk > 0 else 0
                            shares = max(1, int((capital * risk_pct/100) / (entry * risk/100))) if risk > 0 else 0
                            sigs.append({
                                'Symbol':   row['Symbol'],
                                'Gap %':    round(gap, 2),
                                'Entry':    round(entry, 2),
                                'Target ↓': round(target, 2),
                                'Stop ↑':   round(stop, 2),
                                'Risk %':   round(risk, 2),
                                'Reward %': round(reward, 2),
                                'R:R':      round(rr, 2),
                                'Shares':   shares,
                                'Hist WR%': row['Hist WR%'],
                            })

                        if sigs:
                            sig_df = pd.DataFrame(sigs).sort_values('Hist WR%', ascending=False, na_position='last')
                            st.subheader(f"⚡ {len(sig_df)} Monday Trade Signal(s)")
                            st.dataframe(
                                sig_df.style.format({
                                    'Gap %':'{:.2f}%','Entry':'₹{:.2f}','Target ↓':'₹{:.2f}',
                                    'Stop ↑':'₹{:.2f}','Risk %':'{:.2f}%','Reward %':'{:.2f}%','R:R':'{:.2f}'
                                }).background_gradient(subset=['Hist WR%'], cmap='RdYlGn', vmin=30, vmax=70),
                                hide_index=True, use_container_width=True)
                        else:
                            st.info("No gap-down signals from the Friday watchlist for this Monday.")
                    else:
                        st.dataframe(
                            wl_df.drop(columns=['Fri Date']).style
                            .background_gradient(subset=['Hist WR%'], cmap='RdYlGn', vmin=30, vmax=70),
                            hide_index=True, use_container_width=True)
                else:
                    st.info("No stocks meet the Friday setup condition this week.")

            except Exception as e:
                st.error(f"Scanner error: {e}")
                import traceback; st.code(traceback.format_exc())

# ════════════════════════════════════════════════════════════════════════════
# TAB 5 — SIGNAL HISTORY
# ════════════════════════════════════════════════════════════════════════════
with tab5:
    st.markdown('<div class="section-header">Signal History & Performance</div>', unsafe_allow_html=True)
    st.caption("Automated signals captured every Friday (watchlist) and Monday (entry signals + EOD outcomes).")

    wl_hist, sg_hist = load_live_data()

    sub1, sub2 = st.tabs(["📅 Friday Watchlist", "⚡ Monday Signals"])

    with sub1:
        if wl_hist.empty:
            st.info("No Friday watchlist data yet. The system scans every Friday at 3:30 PM IST.")
        else:
            # Show grouped by scan_date
            for scan_dt in sorted(wl_hist['scan_date'].unique(), reverse=True)[:4]:
                grp = wl_hist[wl_hist['scan_date'] == scan_dt]
                with st.expander(f"📅 {scan_dt}  —  {len(grp)} setups found", expanded=(scan_dt == wl_hist['scan_date'].max())):
                    cols_to_show = [c for c in ['symbol','stock_name','sector','ref_day_type',
                                                'fri_high','fri_low','fri_close','fri_rsi',
                                                'hist_win_rate','priority_tier'] if c in grp.columns]
                    st.dataframe(grp[cols_to_show].sort_values('hist_win_rate', ascending=False, na_position='last'),
                                 hide_index=True, use_container_width=True)

    with sub2:
        if sg_hist.empty:
            st.info("No Monday signal data yet. The system generates signals every Monday at 9:20 AM IST.")
        else:
            # Summary metrics
            closed = sg_hist[sg_hist.get('status','') == 'closed'] if 'status' in sg_hist.columns else pd.DataFrame()
            if not closed.empty and 'actual_pnl_pct' in closed.columns:
                wins_live  = closed[closed['actual_pnl_pct'] > 0]
                loss_live  = closed[closed['actual_pnl_pct'] <= 0]
                m1, m2, m3, m4 = st.columns(4)
                with m1: st.metric("Total Signals", len(sg_hist))
                with m2: st.metric("Closed Trades", len(closed))
                with m3: st.metric("Win Rate", f"{len(wins_live)/len(closed)*100:.1f}%" if len(closed) else "—")
                with m4: st.metric("Avg P&L", f"{closed['actual_pnl_pct'].mean():+.3f}%" if len(closed) else "—")
                st.divider()

            cols_to_show = [c for c in ['signal_date','symbol','sector','gap_pct','entry_price',
                                        'target_price','stop_price','rr_ratio','hist_win_rate',
                                        'status','actual_exit_type','actual_pnl_pct'] if c in sg_hist.columns]
            st.dataframe(sg_hist[cols_to_show], hide_index=True, use_container_width=True)

# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.markdown("""
<div style='text-align:center;color:#9a7060;font-size:12px;padding:10px 0;'>
  Friday-Monday Pattern System v2.0 &nbsp;|&nbsp; Nifty 250 &nbsp;|&nbsp;
  ⚠️ For research use only. Not financial advice. Always use stop losses.
</div>
""", unsafe_allow_html=True)
