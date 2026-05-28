"""
FRIDAY-MONDAY PATTERN TRADING SYSTEM v2.0
15-Year Honest Backtest | Nifty 250 | Live Scanner | Email Automation
Theme: Light Rose + Gold
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, date, timedelta
import os, json, warnings
warnings.filterwarnings('ignore')

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="FM Trading System",
    page_icon="📉",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Custom CSS (light rose-gold) ──────────────────────────────────────────────
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700&family=Inter:wght@400;500;600&display=swap');
  html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
  h1, h2 { font-family: 'Playfair Display', serif !important; }
  .kpi-box {
    background: linear-gradient(135deg, #fff5f0 0%, #fff8f2 100%);
    border: 1px solid #e8c8b0;
    border-radius: 12px;
    padding: 18px 20px;
    text-align: center;
    margin-bottom: 4px;
  }
  .kpi-label { font-size: 11px; color: #7a5c4e; letter-spacing: 0.06em; text-transform: uppercase; margin-bottom: 6px; }
  .kpi-value { font-size: 28px; font-weight: 700; color: #B5282A; font-family: 'Playfair Display', serif; }
  .kpi-sub   { font-size: 11px; color: #9a7060; margin-top: 4px; }
  .kpi-green { color: #1a6b3c !important; }
  .kpi-red   { color: #B5282A !important; }
  .kpi-gold  { color: #9a6b1a !important; }
  .insight-card {
    background: #fff9f5; border-left: 4px solid #B5282A;
    padding: 12px 16px; border-radius: 0 8px 8px 0; margin-bottom: 10px;
  }
  .insight-title { font-weight: 600; font-size: 13px; color: #B5282A; margin-bottom: 4px; }
  .insight-body  { font-size: 12px; color: #4a3028; line-height: 1.5; }
  .tag {
    display: inline-block; padding: 2px 10px; border-radius: 12px;
    font-size: 11px; font-weight: 600; margin: 2px;
  }
  .tag-green  { background: #e6f4ec; color: #1a6b3c; }
  .tag-red    { background: #fde8e8; color: #B5282A; }
  .tag-amber  { background: #fef5e0; color: #9a6b1a; }
  .tag-blue   { background: #e6eef8; color: #1a4580; }
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
</style>
""", unsafe_allow_html=True)

# ── Constants ─────────────────────────────────────────────────────────────────
COST_PCT = 0.05

# ── Data loading ──────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def load_data():
    try:
        trades  = pd.read_csv('backtest_trades.csv', parse_dates=['friday_date','monday_date'])
        summary = pd.read_csv('backtest_summary.csv')
        # Apply recommended filter: entry > target
        trades['valid'] = trades['entry_price'] > trades['target_price']
        trades['stop_width'] = (trades['stop_price'] - trades['entry_price']) / trades['entry_price'] * 100
        trades['target_depth'] = (trades['entry_price'] - trades['target_price']) / trades['entry_price'] * 100
        trades['rr_ratio']  = trades['target_depth'] / trades['stop_width']
        return trades, summary
    except Exception as e:
        st.error(f"Could not load backtest data: {e}")
        return pd.DataFrame(), pd.DataFrame()

@st.cache_data(ttl=300)
def load_live_data():
    """Load Friday watchlist and Monday signals from Supabase if available."""
    try:
        from supabase import create_client
        url = st.secrets.get("SUPABASE_URL", os.environ.get("SUPABASE_URL",""))
        key = st.secrets.get("SUPABASE_KEY", os.environ.get("SUPABASE_KEY",""))
        if not url or not key:
            return pd.DataFrame(), pd.DataFrame()
        sb = create_client(url, key)
        wl = sb.table('fm_friday_watchlist').select('*').order('scan_date', desc=True).limit(100).execute()
        sg = sb.table('fm_monday_signals').select('*').order('signal_date', desc=True).limit(100).execute()
        wl_df = pd.DataFrame(wl.data) if wl.data else pd.DataFrame()
        sg_df = pd.DataFrame(sg.data) if sg.data else pd.DataFrame()
        return wl_df, sg_df
    except Exception:
        return pd.DataFrame(), pd.DataFrame()

def kpi(label, value, sub="", color="kpi-value"):
    return f"""<div class="kpi-box">
        <div class="kpi-label">{label}</div>
        <div class="{color}">{value}</div>
        <div class="kpi-sub">{sub}</div>
    </div>"""

def insight(title, body):
    return f"""<div class="insight-card">
        <div class="insight-title">{title}</div>
        <div class="insight-body">{body}</div>
    </div>"""

def colour_pnl(val):
    c = "#1a6b3c" if val >= 0 else "#B5282A"
    return f"color:{c}; font-weight:600"

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('<h2 style="font-family:Playfair Display,serif; color:#B5282A; font-size:22px;">📉 FM System v2</h2>', unsafe_allow_html=True)
    st.caption("Friday-Monday SHORT Strategy")
    st.divider()

    st.subheader("🔍 Filter Parameters")
    apply_valid_filter = st.checkbox("Entry > Target only (recommended)", value=True,
        help="Only take trades where Monday Open is above Friday Low. Removes degenerate gap-too-large cases.")
    regime_filter = st.multiselect("Market Regime", ['bear','sideways','bull','unknown'],
        default=['bear','sideways','bull'],
        help="Filter backtest by Nifty 50 market regime at time of trade")
    max_stop_width = st.slider("Max Stop Width %", 0.5, 3.0, 3.0, 0.1,
        help="Maximum allowed distance from entry to stop (Friday High). Tighter = better R:R.")
    min_gap = st.slider("Min Gap Down %", 0.3, 2.0, 0.3, 0.1)
    max_gap = st.slider("Max Gap Down %", 0.5, 5.0, 5.0, 0.5)

    st.divider()
    st.subheader("💰 Position Sizing")
    capital = st.number_input("Capital (₹)", 50000, 10000000, 500000, 50000)
    risk_pct = st.slider("Risk per trade %", 0.25, 2.0, 1.0, 0.25)

    st.divider()
    st.caption(f"Data: 2011-04-01 → {date.today().strftime('%d %b %Y')}")
    st.caption("Nifty 250 universe | yfinance data")

# ── Load data ────────────────────────────────────────────────────────────────
all_trades, summary = load_data()

if all_trades.empty:
    st.error("⚠️ Backtest data not found. Run `python backtest_engine.py` first to generate data.")
    st.stop()

# Apply filters
def apply_filters(df):
    flt = df.copy()
    if apply_valid_filter:
        flt = flt[flt['valid']]
    flt = flt[flt['regime'].isin(regime_filter)]
    flt = flt[flt['stop_width'] <= max_stop_width]
    flt = flt[flt['gap_pct'].abs() >= min_gap]
    flt = flt[flt['gap_pct'].abs() <= max_gap]
    return flt

trades = apply_filters(all_trades)

# ── Main content ──────────────────────────────────────────────────────────────
st.markdown('<h1 style="color:#B5282A; margin-bottom:4px;">📉 Friday-Monday Pattern System</h1>', unsafe_allow_html=True)
st.caption(f"15-Year Honest Backtest  •  Nifty 250  •  SHORT Strategy  •  {len(trades):,} filtered trades")

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🏠 Dashboard", "📊 Backtest Deep-Dive", "🧭 Strategy Intelligence",
    "📡 Live Scanner", "📋 Signal History"
])

# ════════════════════════════════════════════════════════════════════════════
# TAB 1 — DASHBOARD
# ════════════════════════════════════════════════════════════════════════════
with tab1:

    # ── Honest verdict ────────────────────────────────────────────────────
    total_raw = len(all_trades)
    wr_raw  = all_trades['is_win'].mean()*100
    raw_avg = all_trades['gross_pnl_pct'].mean()

    total_v = len(all_trades[all_trades['valid']])
    wr_v    = all_trades[all_trades['valid']]['is_win'].mean()*100
    avg_v   = all_trades[all_trades['valid']]['gross_pnl_pct'].mean()

    bear_v  = all_trades[all_trades['valid'] & (all_trades['regime']=='bear')]
    wr_b    = bear_v['is_win'].mean()*100
    avg_b   = bear_v['gross_pnl_pct'].mean()

    c1,c2,c3 = st.columns(3)
    with c1:
        st.markdown(kpi("Raw Strategy WR",f"{wr_raw:.1f}%",f"{total_raw:,} trades • Avg {raw_avg:+.3f}%","kpi-red"), unsafe_allow_html=True)
    with c2:
        st.markdown(kpi("After Entry>Target Filter",f"{wr_v:.1f}%",f"{total_v:,} trades • Avg {avg_v:+.3f}%","kpi-gold"), unsafe_allow_html=True)
    with c3:
        clr = "kpi-green" if avg_b >= 0 else "kpi-red"
        st.markdown(kpi("Bear Regime Only",f"{wr_b:.1f}%",f"{len(bear_v):,} trades • Avg {avg_b:+.3f}%", clr), unsafe_allow_html=True)

    st.divider()

    # KPIs for filtered set
    st.markdown('<div class="section-header">Current Filter Results</div>', unsafe_allow_html=True)

    if len(trades) > 0:
        wr    = trades['is_win'].mean()*100
        wins  = trades[trades['is_win']]
        loss  = trades[~trades['is_win']]
        avg_g = trades['gross_pnl_pct'].mean()
        avg_n = trades['net_pnl_pct'].mean()
        avg_w = wins['gross_pnl_pct'].mean() if len(wins) else 0
        avg_l = loss['gross_pnl_pct'].mean() if len(loss) else 0
        pf    = abs(wins['gross_pnl_pct'].sum()) / abs(loss['gross_pnl_pct'].sum()) if len(loss) and loss['gross_pnl_pct'].sum()!=0 else 0
        n_stocks = trades['symbol'].nunique()
        n_years  = trades['year'].nunique()

        k1,k2,k3,k4,k5,k6 = st.columns(6)
        with k1: st.metric("Trades",f"{len(trades):,}",f"{n_stocks} stocks")
        with k2: st.metric("Win Rate",f"{wr:.1f}%",f"+{wr-50:.1f}% vs random")
        with k3: st.metric("Avg Gross",f"{avg_g:+.3f}%",None)
        with k4: st.metric("Avg Net",f"{avg_n:+.3f}%",f"after {COST_PCT}% costs")
        with k5: st.metric("Profit Factor",f"{pf:.3f}",f"need >1.0 to profit")
        with k6: st.metric("Avg Win|Loss",f"{avg_w:+.2f}% / {avg_l:+.2f}%",None)

        # ── Strategy insights ─────────────────────────────────────────────
        st.divider()
        st.markdown('<div class="section-header">🔬 Strategy Insights</div>', unsafe_allow_html=True)

        ins1, ins2 = st.columns(2)
        with ins1:
            st.markdown(insight("⚠️ Original 88.8% Claim Was Fabricated",
                f"The original app pre-computed 'success rates' on tiny samples (17-41 gap-down setups per stock). "
                f"The actual 15-year WR on Nifty 250 is <b>{wr_raw:.1f}%</b> — not remotely close to 88.8%. "
                f"Coal India's '100% success rate' was based on 17 occurrences, a coin flip over that sample."), unsafe_allow_html=True)
            st.markdown(insight("🔄 The Core Flaw: Entry Below Target",
                f"When Monday gaps down too far (below Friday Low), the 'target' is actually <i>above</i> entry — "
                f"meaning we're expecting a SHORT position to go UP to profit. This affected 49.2% of all raw trades, "
                f"showing as fake 'target hits' with negative P&L. Mandatory fix: Entry > Target."), unsafe_allow_html=True)

        with ins2:
            st.markdown(insight("✅ Real Edge: Bear Regime",
                f"The strategy has a genuine edge in bear markets: WR = <b>{wr_b:.1f}%</b>, "
                f"avg gross = <b>{avg_b:+.3f}%</b>. This makes intuitive sense — short momentum "
                f"continuation is strongest when the broad market is already below its 200-DMA. "
                f"In bull markets (Nifty 50 > 200-DMA), avoid this strategy entirely."), unsafe_allow_html=True)
            st.markdown(insight("📐 R:R Problem Limits Profitability",
                f"Stop = Friday High (wide) vs Target = Friday Low (narrow) creates poor R:R. "
                f"Avg win is only {avg_w:.2f}% but avg loss is {avg_l:.2f}%. "
                f"Tighten entries to max 1.5% stop width, or use Friday High as a hard alert "
                f"level and exit at 0.5× ATR instead."), unsafe_allow_html=True)

        # ── Best regime guidance ──────────────────────────────────────────
        st.divider()
        c1, c2, c3 = st.columns(3)
        for col, reg, icon in zip([c1,c2,c3],['bear','sideways','bull'],['🐻','➡️','🐂']):
            r = all_trades[all_trades['valid'] & (all_trades['regime']==reg)]
            if len(r) > 0:
                wr_r = r['is_win'].mean()*100
                ag_r = r['gross_pnl_pct'].mean()
                clr  = "#1a6b3c" if ag_r >= 0 else "#B5282A"
                verdict = "✅ TRADE" if ag_r >= 0 else ("⚠️ CAUTIOUS" if ag_r > -0.3 else "❌ SKIP")
                with col:
                    st.markdown(f"""<div class="kpi-box">
                        <div class="kpi-label">{icon} {reg.title()} Regime</div>
                        <div style="font-size:22px;font-weight:700;color:{clr};">{verdict}</div>
                        <div class="kpi-sub">WR {wr_r:.1f}% | Avg {ag_r:+.3f}% | {len(r):,} trades</div>
                    </div>""", unsafe_allow_html=True)

    else:
        st.warning("No trades match the current filters. Adjust sidebar parameters.")

# ════════════════════════════════════════════════════════════════════════════
# TAB 2 — BACKTEST DEEP-DIVE
# ════════════════════════════════════════════════════════════════════════════
with tab2:
    if len(trades) == 0:
        st.warning("No data for current filters.")
    else:
        st.markdown('<div class="section-header">📅 Year-by-Year Performance</div>', unsafe_allow_html=True)

        ystat = trades.groupby('year').agg(
            trades_=('is_win','count'), wins_=('is_win','sum'),
            gross_=('gross_pnl_pct','mean'), net_=('net_pnl_pct','mean'),
            sum_gross=('gross_pnl_pct','sum')
        ).reset_index()
        ystat['win_rate'] = (ystat['wins_']/ystat['trades_']*100).round(1)
        ystat['gross_'] = ystat['gross_'].round(3)
        ystat['net_']   = ystat['net_'].round(3)

        fig_yr = go.Figure()
        colors = ['#1a6b3c' if g >= 0 else '#B5282A' for g in ystat['gross_']]
        fig_yr.add_trace(go.Bar(x=ystat['year'].astype(str), y=ystat['gross_'],
            marker_color=colors, name='Avg Gross P&L %'))
        fig_yr.add_trace(go.Scatter(x=ystat['year'].astype(str), y=ystat['win_rate'],
            mode='lines+markers', name='Win Rate %', yaxis='y2',
            line=dict(color='#C8860A', width=2), marker=dict(size=6)))
        fig_yr.update_layout(
            height=320, barmode='group',
            yaxis=dict(title='Avg Gross P&L %', zeroline=True, zerolinecolor='#B5282A', zerolinewidth=1.5),
            yaxis2=dict(title='Win Rate %', overlaying='y', side='right', range=[20,80]),
            plot_bgcolor='#FFFAF6', paper_bgcolor='#FFFAF6',
            legend=dict(orientation='h', x=0, y=1.1),
            margin=dict(t=20,b=20)
        )
        st.plotly_chart(fig_yr, use_container_width=True)

        # Yearly table
        disp = ystat[['year','trades_','win_rate','gross_','net_']].copy()
        disp.columns = ['Year','Trades','Win Rate %','Avg Gross %','Avg Net %']
        st.dataframe(
            disp.style
            .format({'Win Rate %':'{:.1f}','Avg Gross %':'{:+.3f}','Avg Net %':'{:+.3f}'})
            .applymap(lambda v: colour_pnl(v) if isinstance(v,float) and abs(v)<5 else '',
                      subset=['Avg Gross %','Avg Net %']),
            hide_index=True, use_container_width=True
        )

        st.divider()
        st.markdown('<div class="section-header">🔍 Exit Type Breakdown</div>', unsafe_allow_html=True)

        et = trades['exit_type'].value_counts().reset_index()
        et.columns = ['exit_type','count']
        et_wins = trades.groupby('exit_type').agg(
            wins=('is_win','sum'), total=('is_win','count'), avg_pnl=('gross_pnl_pct','mean')
        ).reset_index()

        c1, c2 = st.columns([1,2])
        with c1:
            fig_pie = go.Figure(go.Pie(
                labels=et['exit_type'], values=et['count'],
                marker_colors=['#1a6b3c','#B5282A','#C8860A'],
                hole=0.4
            ))
            fig_pie.update_layout(height=250, margin=dict(t=10,b=10),
                paper_bgcolor='#FFFAF6')
            st.plotly_chart(fig_pie, use_container_width=True)
        with c2:
            for _, row in et_wins.iterrows():
                wr = row['wins']/row['total']*100
                st.markdown(f"**{row['exit_type'].upper()}** — {row['total']:,} trades | WR: {wr:.1f}% | Avg: {row['avg_pnl']:+.3f}%")

        st.divider()
        st.markdown('<div class="section-header">📈 Top 25 Stocks by Net P&L</div>', unsafe_allow_html=True)

        stock_stats = trades.groupby(['symbol','stock_name','sector','tier']).agg(
            trades_=('is_win','count'), wr=('is_win',lambda x: x.mean()*100),
            avg_g=('gross_pnl_pct','mean'), total_g=('gross_pnl_pct','sum')
        ).reset_index().query('trades_ >= 15').sort_values('avg_g', ascending=False)

        fig_top = go.Figure()
        top25 = stock_stats.head(25)
        bot25 = stock_stats.tail(25)

        fig_top.add_trace(go.Bar(
            y=top25['symbol'], x=top25['avg_g'],
            orientation='h',
            marker_color=['#1a6b3c' if v>=0 else '#B5282A' for v in top25['avg_g']],
            name='Top 25'
        ))
        fig_top.update_layout(
            height=500, yaxis_title='', xaxis_title='Avg Gross P&L %',
            plot_bgcolor='#FFFAF6', paper_bgcolor='#FFFAF6', margin=dict(t=10,b=10)
        )
        st.plotly_chart(fig_top, use_container_width=True)

        # Full stock table
        with st.expander("📋 Full Stock Performance Table"):
            disp2 = stock_stats[['symbol','stock_name','sector','tier','trades_','wr','avg_g','total_g']].copy()
            disp2.columns = ['Symbol','Name','Sector','Tier','Trades','Win Rate %','Avg Gross %','Total Gross %']
            disp2 = disp2.sort_values('Avg Gross %', ascending=False)
            st.dataframe(
                disp2.style
                .format({'Win Rate %':'{:.1f}','Avg Gross %':'{:+.3f}','Total Gross %':'{:+.1f}'})
                .applymap(lambda v: colour_pnl(v) if isinstance(v,float) and abs(v)<20 else '',
                          subset=['Avg Gross %']),
                hide_index=True, use_container_width=True
            )

# ════════════════════════════════════════════════════════════════════════════
# TAB 3 — STRATEGY INTELLIGENCE
# ════════════════════════════════════════════════════════════════════════════
with tab3:
    if len(trades) == 0:
        st.warning("No data for current filters.")
    else:
        # ── Sector heatmap ────────────────────────────────────────────────
        st.markdown('<div class="section-header">🏭 Sector Performance</div>', unsafe_allow_html=True)

        sec = trades.groupby('sector').agg(
            trades_=('is_win','count'), wr=('is_win',lambda x: x.mean()*100), avg_g=('gross_pnl_pct','mean')
        ).reset_index().query('trades_ >= 20').sort_values('avg_g', ascending=False)

        fig_sec = px.bar(sec, x='sector', y='avg_g',
            color='avg_g', color_continuous_scale=['#B5282A','#f5f0eb','#1a6b3c'],
            color_continuous_midpoint=0, text='avg_g',
            labels={'avg_g':'Avg Gross P&L %','sector':'Sector'})
        fig_sec.update_traces(texttemplate='%{text:+.2f}%', textposition='outside')
        fig_sec.update_layout(
            height=350, plot_bgcolor='#FFFAF6', paper_bgcolor='#FFFAF6',
            coloraxis_showscale=False, margin=dict(t=20,b=60),
            xaxis_tickangle=-35
        )
        st.plotly_chart(fig_sec, use_container_width=True)

        # ── Regime × Sector matrix ────────────────────────────────────────
        st.markdown('<div class="section-header">🌡️ Regime × Sector Matrix (Avg Gross P&L)</div>', unsafe_allow_html=True)

        pivot = trades.pivot_table(
            index='sector', columns='regime', values='gross_pnl_pct', aggfunc='mean'
        ).fillna(0)
        pivot = pivot.reindex(columns=[c for c in ['bear','sideways','bull','unknown'] if c in pivot.columns])

        fig_heat = px.imshow(
            pivot, color_continuous_scale='RdYlGn', aspect='auto',
            labels=dict(color='Avg P&L %'), text_auto='.2f',
            zmin=-2, zmax=2
        )
        fig_heat.update_layout(
            height=500, plot_bgcolor='#FFFAF6', paper_bgcolor='#FFFAF6', margin=dict(t=10)
        )
        st.plotly_chart(fig_heat, use_container_width=True)

        st.divider()

        # ── Gap size analysis ─────────────────────────────────────────────
        st.markdown('<div class="section-header">📐 Gap Size Analysis</div>', unsafe_allow_html=True)

        t2 = trades.copy()
        bins   = [-10,-2,-1.5,-1.0,-0.5,-0.3,0]
        labels = ['>2% gap','1.5–2%','1–1.5%','0.5–1%','0.3–0.5%','<filter']
        t2['gap_bucket'] = pd.cut(t2['gap_pct'], bins=bins, labels=labels)
        gbkt = t2.groupby('gap_bucket', observed=True).agg(
            trades_=('is_win','count'), wr=('is_win',lambda x: x.mean()*100),
            avg_g=('gross_pnl_pct','mean'), avg_win=('gross_pnl_pct',lambda x: x[x>0].mean()),
            avg_loss=('gross_pnl_pct',lambda x: x[x<=0].mean())
        ).reset_index()

        c1, c2 = st.columns(2)
        with c1:
            fig_gb = px.bar(gbkt, x='gap_bucket', y='wr',
                color='wr', color_continuous_scale=['#B5282A','#f5f0eb','#1a6b3c'],
                color_continuous_midpoint=50,
                text='wr', labels={'wr':'Win Rate %','gap_bucket':'Gap Size'})
            fig_gb.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
            fig_gb.update_layout(height=300, plot_bgcolor='#FFFAF6', paper_bgcolor='#FFFAF6',
                coloraxis_showscale=False, margin=dict(t=20,b=20), title="Win Rate by Gap Size")
            st.plotly_chart(fig_gb, use_container_width=True)
        with c2:
            fig_gb2 = px.bar(gbkt, x='gap_bucket', y='avg_g',
                color='avg_g', color_continuous_scale=['#B5282A','#f5f0eb','#1a6b3c'],
                color_continuous_midpoint=0,
                text='avg_g', labels={'avg_g':'Avg Gross P&L %','gap_bucket':'Gap Size'})
            fig_gb2.update_traces(texttemplate='%{text:+.3f}%', textposition='outside')
            fig_gb2.update_layout(height=300, plot_bgcolor='#FFFAF6', paper_bgcolor='#FFFAF6',
                coloraxis_showscale=False, margin=dict(t=20,b=20), title="Avg P&L by Gap Size")
            st.plotly_chart(fig_gb2, use_container_width=True)

        st.divider()

        # ── RSI analysis ──────────────────────────────────────────────────
        st.markdown('<div class="section-header">📊 RSI at Friday Close Analysis</div>', unsafe_allow_html=True)

        t3 = trades.dropna(subset=['fri_rsi']).copy()
        rsi_bins   = [0,30,40,50,60,70,80,100]
        rsi_labels = ['<30','30-40','40-50','50-60','60-70','70-80','>80']
        t3['rsi_bucket'] = pd.cut(t3['fri_rsi'], bins=rsi_bins, labels=rsi_labels)
        rbkt = t3.groupby('rsi_bucket', observed=True).agg(
            trades_=('is_win','count'), wr=('is_win',lambda x: x.mean()*100), avg_g=('gross_pnl_pct','mean')
        ).reset_index()

        fig_rsi = px.bar(rbkt, x='rsi_bucket', y='avg_g',
            color='avg_g', color_continuous_scale=['#B5282A','#f5f0eb','#1a6b3c'],
            color_continuous_midpoint=0, text='avg_g',
            labels={'avg_g':'Avg Gross P&L %','rsi_bucket':'RSI Range'})
        fig_rsi.update_traces(texttemplate='%{text:+.3f}%', textposition='outside')
        fig_rsi.update_layout(
            height=300, plot_bgcolor='#FFFAF6', paper_bgcolor='#FFFAF6',
            coloraxis_showscale=False, margin=dict(t=20,b=20)
        )
        st.plotly_chart(fig_rsi, use_container_width=True)
        st.caption("Best RSI range for SHORTs: higher RSI at Friday close (overbought) tends to perform better.")

        # ── Monthly seasonality ───────────────────────────────────────────
        st.divider()
        st.markdown('<div class="section-header">📅 Monthly Seasonality</div>', unsafe_allow_html=True)

        mstat = trades.groupby('month').agg(
            trades_=('is_win','count'), wr=('is_win',lambda x: x.mean()*100), avg_g=('gross_pnl_pct','mean')
        ).reset_index()
        months_name = {1:'Jan',2:'Feb',3:'Mar',4:'Apr',5:'May',6:'Jun',7:'Jul',8:'Aug',9:'Sep',10:'Oct',11:'Nov',12:'Dec'}
        mstat['month_name'] = mstat['month'].map(months_name)

        fig_m = px.bar(mstat, x='month_name', y='avg_g',
            color='avg_g', color_continuous_scale=['#B5282A','#f5f0eb','#1a6b3c'],
            color_continuous_midpoint=0, text='avg_g',
            labels={'avg_g':'Avg Gross P&L %','month_name':''})
        fig_m.update_traces(texttemplate='%{text:+.3f}%', textposition='outside')
        fig_m.update_layout(
            height=280, plot_bgcolor='#FFFAF6', paper_bgcolor='#FFFAF6',
            coloraxis_showscale=False, margin=dict(t=10,b=10)
        )
        st.plotly_chart(fig_m, use_container_width=True)

# ════════════════════════════════════════════════════════════════════════════
# TAB 4 — LIVE SCANNER
# ════════════════════════════════════════════════════════════════════════════
with tab4:
    st.markdown('<div class="section-header">📡 Live Pattern Scanner</div>', unsafe_allow_html=True)

    today = date.today()
    dow   = today.weekday()

    # Market regime indicator
    st.subheader("🌡️ Current Market Regime")
    if st.button("🔄 Check Current Regime", type="primary"):
        with st.spinner("Fetching Nifty 50..."):
            try:
                import yfinance as yf
                nifty = yf.download('^NSEI', period='1y', auto_adjust=True, progress=False)
                if isinstance(nifty.columns, pd.MultiIndex):
                    ohlcv = {'Open','High','Low','Close','Volume'}
                    for lvl in range(nifty.columns.nlevels):
                        if ohlcv.issubset(set(nifty.columns.get_level_values(lvl))):
                            nifty.columns = nifty.columns.get_level_values(lvl)
                            break
                nifty = nifty.dropna()
                close = nifty['Close']
                sma200 = close.rolling(200).mean()
                sma50  = close.rolling(50).mean()
                last   = close.iloc[-1]
                s200   = sma200.iloc[-1]
                s50    = sma50.iloc[-1]
                if last < s200 * 0.95:
                    reg = "🐻 BEAR — Strategy recommended, best edge"
                    clr = "#1a6b3c"
                elif last > s200 * 1.05:
                    reg = "🐂 BULL — Avoid or trade very selectively"
                    clr = "#B5282A"
                else:
                    reg = "➡️ SIDEWAYS — Trade with moderate caution"
                    clr = "#9a6b1a"
                st.markdown(f"<h3 style='color:{clr};'>{reg}</h3>", unsafe_allow_html=True)
                st.caption(f"Nifty 50: {last:.0f} | 200-DMA: {s200:.0f} | 50-DMA: {s50:.0f}")
            except Exception as e:
                st.error(f"Could not fetch: {e}")

    st.divider()

    # Friday Scanner
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("📅 Friday Scanner (EOD)")
        st.caption("Run after 3:15 PM on Fridays. Finds stocks where Fri High < Thu High.")
        run_fri = st.button("🔍 Run Friday Scan Now", use_container_width=True)

    with col2:
        st.subheader("⚡ Monday Scanner (9:20 AM)")
        st.caption("Run at 9:20 AM on Mondays. Checks gap down from Friday watchlist.")
        run_mon = st.button("🔍 Run Monday Scan Now", use_container_width=True)

    if run_fri or run_mon:
        from nifty250_stocks import NIFTY_250_STOCKS
        from backtest_engine import download_batch, build_regime_series, compute_rsi, compute_volume_ratio

        with st.spinner("Downloading data..."):
            try:
                import yfinance as yf

                # Determine scan period
                scan_end = today.strftime('%Y-%m-%d')
                scan_start = (today - timedelta(days=60)).strftime('%Y-%m-%d')

                symbols = list(NIFTY_250_STOCKS.keys())
                # Download in one batch for speed
                batch_data = download_batch(symbols[:60], scan_start, scan_end)
                batch_data2 = download_batch(symbols[60:130], scan_start, scan_end)
                batch_data3 = download_batch(symbols[130:], scan_start, scan_end)
                all_data = {**batch_data, **batch_data2, **batch_data3}
                st.success(f"Downloaded {len(all_data)}/{len(symbols)} stocks.")

                # Get last Friday from data
                nifty_data = yf.download('^NSEI', start=scan_start, auto_adjust=True, progress=False)
                if isinstance(nifty_data.columns, pd.MultiIndex):
                    nifty_data.columns = nifty_data.columns.get_level_values(-1)
                nifty_close = nifty_data['Close']
                sma200_n = nifty_close.rolling(200).mean()
                last_n   = float(nifty_close.iloc[-1])
                last_s200 = float(sma200_n.iloc[-1]) if not np.isnan(sma200_n.iloc[-1]) else last_n
                regime_now = 'bear' if last_n < last_s200*0.95 else ('bull' if last_n > last_s200*1.05 else 'sideways')

                results = []
                for sym, df in all_data.items():
                    if len(df) < 15:
                        continue
                    df = df.sort_index()
                    if isinstance(df.columns, pd.MultiIndex):
                        for lvl in range(df.columns.nlevels):
                            if 'Close' in df.columns.get_level_values(lvl):
                                df.columns = df.columns.get_level_values(lvl)
                                break
                    if 'Close' not in df.columns:
                        continue
                    try:
                        df['RSI'] = compute_rsi(df['Close'])
                        df['VolRatio'] = compute_volume_ratio(df['Volume'])
                        df['SMA20'] = df['Close'].rolling(20).mean()

                        # Find last Friday and Thursday
                        fridays = df[df.index.dayofweek == 4]
                        if len(fridays) == 0:
                            continue
                        last_fri = fridays.index[-1]
                        fri_row  = df.loc[last_fri]

                        # Find ref day
                        prev = df[df.index < last_fri].tail(5)
                        ref  = None
                        ref_type = None
                        for j in range(len(prev)-1, -1, -1):
                            d = prev.index[j]
                            if d.weekday() == 3:
                                ref = prev.iloc[j]; ref_type = 'Thu'; break
                            if d.weekday() == 2:
                                thu = d + timedelta(days=1)
                                if thu not in df.index:
                                    ref = prev.iloc[j]; ref_type = 'Wed'; break
                                break
                        if ref is None:
                            continue

                        if fri_row['High'] >= ref['High']:
                            continue  # Pattern not met

                        info = NIFTY_250_STOCKS.get(sym, {})
                        rsi_val = float(fri_row['RSI']) if not np.isnan(fri_row['RSI']) else None
                        vol_r   = float(fri_row['VolRatio']) if not np.isnan(fri_row['VolRatio']) else None
                        hist = all_trades[all_trades['valid'] & (all_trades['symbol'] == sym.replace('.NS',''))]
                        hist_wr = hist['is_win'].mean()*100 if len(hist) > 5 else None

                        results.append({
                            'Symbol': sym.replace('.NS',''),
                            'Name': info.get('name', sym),
                            'Sector': info.get('sector','?'),
                            'Ref Day': ref_type,
                            'Fri High': round(float(fri_row['High']),2),
                            'Ref High': round(float(ref['High']),2),
                            'Fri Low': round(float(fri_row['Low']),2),
                            'Fri Close': round(float(fri_row['Close']),2),
                            'RSI': round(rsi_val,1) if rsi_val else '-',
                            'Vol Ratio': round(vol_r,2) if vol_r else '-',
                            'Hist WR%': round(hist_wr,1) if hist_wr else '-',
                            'Fri Date': last_fri.date(),
                        })
                    except Exception:
                        pass

                if results:
                    wl_df = pd.DataFrame(results).sort_values('Hist WR%', ascending=False, na_position='last')
                    st.success(f"✅ Found {len(wl_df)} stocks meeting Friday setup")
                    st.caption(f"Current regime: {regime_now.upper()} — {'✅ Trade' if regime_now in ['bear','sideways'] else '⚠️ Caution'}")

                    if run_mon:
                        # Check for gap downs
                        trade_signals = []
                        for _, row in wl_df.iterrows():
                            sym_full = row['Symbol'] + '.NS'
                            if sym_full not in all_data:
                                continue
                            df = all_data[sym_full]
                            # Find last Monday
                            mondays = df[df.index.dayofweek == 0]
                            if len(mondays) == 0:
                                continue
                            last_mon = mondays.index[-1]
                            # Check if last_mon is after last Friday
                            fri_date = row['Fri Date']
                            if last_mon.date() <= fri_date:
                                continue
                            mon = df.loc[last_mon]
                            fri_close = row['Fri Close']
                            gap = (float(mon['Open']) - fri_close) / fri_close * 100
                            if gap >= -0.3:
                                continue
                            entry  = float(mon['Open'])
                            target = row['Fri Low']
                            stop   = row['Fri High']
                            if entry <= target:
                                continue  # Entry below target — skip
                            risk   = (stop - entry) / entry * 100
                            reward = (entry - target) / entry * 100
                            rr     = reward / risk if risk > 0 else 0
                            shares = int((capital * risk_pct/100) / (entry * risk/100))
                            trade_signals.append({
                                'Symbol': row['Symbol'],
                                'Gap %': round(gap,2),
                                'Entry': round(entry,2),
                                'Target': round(target,2),
                                'Stop': round(stop,2),
                                'Risk %': round(risk,2),
                                'Reward %': round(reward,2),
                                'R:R': round(rr,2),
                                'Shares': shares,
                                'Hist WR%': row['Hist WR%'],
                                'Mon Date': last_mon.date(),
                            })

                        if trade_signals:
                            sig_df = pd.DataFrame(trade_signals).sort_values('Hist WR%', ascending=False, na_position='last')
                            st.subheader(f"⚡ {len(sig_df)} Monday Trade Signal(s)")
                            st.dataframe(sig_df.style.format({
                                'Gap %':'{:.2f}%','Entry':'₹{:.2f}','Target':'₹{:.2f}',
                                'Stop':'₹{:.2f}','Risk %':'{:.2f}%','Reward %':'{:.2f}%','R:R':'{:.2f}'
                            }).background_gradient(subset=['Hist WR%'], cmap='RdYlGn', vmin=30, vmax=70),
                            hide_index=True, use_container_width=True)
                        else:
                            st.info("No gap-down signals from the Friday watchlist today.")
                    else:
                        st.dataframe(wl_df.style.background_gradient(subset=['Hist WR%'],
                            cmap='RdYlGn', vmin=30, vmax=70),
                            hide_index=True, use_container_width=True)
                else:
                    st.info("No Friday setup stocks found for the current week.")
            except Exception as e:
                st.error(f"Scanner error: {e}")
                import traceback; st.code(traceback.format_exc())

# ════════════════════════════════════════════════════════════════════════════
# TAB 5 — SIGNAL HISTORY
# ════════════════════════════════════════════════════════════════════════════
with tab5:
    st.markdown('<div class="section-header">📋 Signal History & Performance</div>', unsafe_allow_html=True)
    watchlist_hist, signals_hist = load_live_data()

    if signals_hist.empty:
        st.info("No signal history in Supabase yet. Signals will appear here after the live system runs on Friday/Monday.")
        st.caption("Live automation: GitHub Actions runs Friday scan at 3:30 PM IST and Monday scan at 9:20 AM IST.")

        # Show what the email will look like
        st.subheader("📧 Email Alert Preview")
        with st.expander("Friday EOD Email Preview"):
            st.markdown("""
**Subject:** 📉 FM System — Friday Watchlist Ready — 3 Setups Found

**From:** fm-trading@yourdomain.com

---
**FRIDAY-MONDAY PATTERN SCANNER**
Scan Date: Friday 24-May-2026 | Regime: SIDEWAYS

| # | Stock | Sector | Fri High | Fri Low | Fri Close | RSI | Hist WR |
|---|-------|--------|----------|---------|-----------|-----|---------|
| 1 | HINDALCO | Metals | 672.30 | 660.10 | 663.50 | 58.2 | 41.2% |
| 2 | BPCL | Oil & Gas | 312.40 | 305.70 | 308.20 | 52.1 | 38.2% |
| 3 | COALINDIA | Metals | 425.80 | 418.30 | 421.70 | 61.4 | 35.8% |

*Set your Monday 9:20 AM alarm. Signal email will arrive within 60 seconds of market open.*
""")
        with st.expander("Monday 9:20 AM Trade Signal Email Preview"):
            st.markdown("""
**Subject:** ⚡ FM TRADE SIGNALS — 9:20 AM — 2 Entries Now

---
**EXECUTE IMMEDIATELY**

**HINDALCO** — Gap down 0.73%
- Entry: ₹658.40 (Mon Open)
- Target: ₹660.10 → already above entry, SKIP ❌

**BPCL** — Gap down 0.52%
- Entry: ₹306.60 (Mon Open)
- Target: ₹305.70 (−0.29%)
- Stop: ₹312.40 (+1.89%)
- R:R: 0.15 — below threshold ⚠️

*Only enter if stop width ≤ 1.5% and entry > target.*
""")
    else:
        st.dataframe(signals_hist, use_container_width=True)

# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.markdown("""
<div style='text-align:center; color:#9a7060; font-size:12px; padding: 10px 0;'>
  Friday-Monday Pattern System v2.0 &nbsp;|&nbsp; 15-Year Backtest · Nifty 250 · 14,057 Trades
  &nbsp;|&nbsp; ⚠️ For informational use only. Not financial advice. Always use stop losses.
</div>
""", unsafe_allow_html=True)
