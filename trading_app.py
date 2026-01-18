"""
FRIDAY-MONDAY PATTERN TRADING SYSTEM - STREAMLIT WEB APP
Complete visual interface for pattern scanning and trade signal generation
"""

import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import json
import os

# Page configuration
st.set_page_config(
    page_title="Friday-Monday Pattern Trading System",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Nifty 50 stocks dictionary
NIFTY_50_STOCKS = {
    'ADANIPORTS.NS': 'Adani Ports', 'ASIANPAINT.NS': 'Asian Paints', 'AXISBANK.NS': 'Axis Bank',
    'BAJAJ-AUTO.NS': 'Bajaj Auto', 'BAJFINANCE.NS': 'Bajaj Finance', 'BAJAJFINSV.NS': 'Bajaj Finserv',
    'BPCL.NS': 'BPCL', 'BHARTIARTL.NS': 'Bharti Airtel', 'BRITANNIA.NS': 'Britannia',
    'CIPLA.NS': 'Cipla', 'COALINDIA.NS': 'Coal India', 'DIVISLAB.NS': 'Divi\'s Labs',
    'DRREDDY.NS': 'Dr Reddy', 'EICHERMOT.NS': 'Eicher Motors', 'GRASIM.NS': 'Grasim',
    'HCLTECH.NS': 'HCL Tech', 'HDFCBANK.NS': 'HDFC Bank', 'HDFCLIFE.NS': 'HDFC Life',
    'HEROMOTOCO.NS': 'Hero MotoCorp', 'HINDALCO.NS': 'Hindalco', 'HINDUNILVR.NS': 'HUL',
    'ICICIBANK.NS': 'ICICI Bank', 'ITC.NS': 'ITC', 'INDUSINDBK.NS': 'IndusInd Bank',
    'INFY.NS': 'Infosys', 'JSWSTEEL.NS': 'JSW Steel', 'KOTAKBANK.NS': 'Kotak Bank',
    'LT.NS': 'L&T', 'M&M.NS': 'M&M', 'MARUTI.NS': 'Maruti', 'NTPC.NS': 'NTPC',
    'NESTLEIND.NS': 'Nestle', 'ONGC.NS': 'ONGC', 'POWERGRID.NS': 'Power Grid',
    'RELIANCE.NS': 'Reliance', 'SBILIFE.NS': 'SBI Life', 'SHRIRAMFIN.NS': 'Shriram Finance',
    'SBIN.NS': 'SBI', 'SUNPHARMA.NS': 'Sun Pharma', 'TCS.NS': 'TCS',
    'TATACONSUM.NS': 'Tata Consumer', 'TATASTEEL.NS': 'Tata Steel', 'TECHM.NS': 'Tech Mahindra',
    'TITAN.NS': 'Titan', 'ULTRACEMCO.NS': 'UltraTech', 'WIPRO.NS': 'Wipro',
    '^NSEI': 'NIFTY 50', '^NSEBANK': 'BANK NIFTY'
}

# Load historical statistics
@st.cache_data
def load_historical_stats():
    """Load pre-calculated success rates"""
    try:
        stats = pd.read_csv('nifty50_summary_stats.csv')
        return stats
    except:
        return None

# Download stock data
@st.cache_data(ttl=300)  # Cache for 5 minutes
def download_stock_data(symbol, period="1mo"):
    """Download recent stock data"""
    try:
        data = yf.download(symbol, period=period, progress=False)
        if data.empty:
            return None
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
        return data
    except:
        return None

# Calculate technical indicators
def calculate_indicators(data):
    """Calculate RSI and moving averages"""
    if len(data) < 20:
        return data
    
    # RSI
    delta = data['Close'].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = -delta.where(delta < 0, 0).rolling(14).mean()
    rs = gain / loss
    data['RSI'] = 100 - (100 / (1 + rs))
    
    # Moving averages
    data['SMA_20'] = data['Close'].rolling(20).mean()
    data['SMA_50'] = data['Close'].rolling(50).mean()
    
    # Volume ratio
    data['Volume_SMA_20'] = data['Volume'].rolling(20).mean()
    data['Volume_Ratio'] = data['Volume'] / data['Volume_SMA_20']
    
    return data

# Check pattern setup
def check_pattern_setup(data):
    """Check if Friday High < Thursday High"""
    if data is None or len(data) < 2:
        return None
    
    recent = data.tail(5)
    thursday_data = None
    friday_data = None
    
    for i in range(len(recent)-1):
        if recent.index[i].dayofweek == 3:  # Thursday
            thursday_data = recent.iloc[i]
            if i + 1 < len(recent) and recent.index[i+1].dayofweek == 4:  # Friday
                friday_data = recent.iloc[i+1]
                break
    
    if thursday_data is None or friday_data is None:
        return None
    
    if friday_data['High'] < thursday_data['High']:
        return {
            'thursday_high': thursday_data['High'],
            'friday_high': friday_data['High'],
            'friday_low': friday_data['Low'],
            'friday_close': friday_data['Close'],
            'decline_pct': ((friday_data['High'] - thursday_data['High']) / thursday_data['High']) * 100,
            'rsi': data['RSI'].iloc[-1] if 'RSI' in data.columns else None,
            'below_sma20': friday_data['Close'] < data['SMA_20'].iloc[-1] if 'SMA_20' in data.columns else False,
            'volume_ratio': data['Volume_Ratio'].iloc[-1] if 'Volume_Ratio' in data.columns else None
        }
    return None

# Check Monday gap
def check_monday_gap(data):
    """Check Monday's opening gap"""
    if data is None or len(data) < 2:
        return None
    
    recent = data.tail(3)
    friday_close = None
    monday_open = None
    monday_data = None
    
    for i in range(len(recent)):
        if recent.index[i].dayofweek == 4:  # Friday
            friday_close = recent.iloc[i]['Close']
        elif recent.index[i].dayofweek == 0:  # Monday
            monday_open = recent.iloc[i]['Open']
            monday_data = recent.iloc[i]
    
    if friday_close is None or monday_open is None:
        return None
    
    gap_pct = ((monday_open - friday_close) / friday_close) * 100
    
    return {
        'friday_close': friday_close,
        'monday_open': monday_open,
        'monday_low': monday_data['Low'],
        'monday_high': monday_data['High'],
        'gap_pct': gap_pct,
        'has_gap_down': gap_pct < -0.3
    }

# Calculate position size
def calculate_position_size(capital, risk_pct, stop_distance_pct):
    """Calculate shares to trade"""
    risk_amount = capital * (risk_pct / 100)
    position_value = risk_amount / (stop_distance_pct / 100)
    return position_value

# Sidebar
with st.sidebar:
    st.title("⚙️ Settings")
    
    # Capital input
    capital = st.number_input(
        "Trading Capital (₹)",
        min_value=10000,
        max_value=10000000,
        value=100000,
        step=10000,
        help="Total capital available for trading"
    )
    
    st.divider()
    
    # Email settings
    st.subheader("📧 Email Alerts")
    email_enabled = st.checkbox("Enable Email Alerts", value=False)
    
    if email_enabled:
        email_address = st.text_input("Your Email", placeholder="your.email@gmail.com")
        st.info("📝 Configure SMTP settings in config.json for email to work")
    
    st.divider()
    
    # System stats
    st.subheader("📊 System Stats")
    hist_stats = load_historical_stats()
    if hist_stats is not None:
        st.metric("Total Stocks", len(hist_stats))
        st.metric("Avg Gap Success", f"{hist_stats['Gap_Down_Success_Rate'].mean():.1f}%")
        st.metric("Best Stock", hist_stats.nlargest(1, 'Gap_Down_Success_Rate').iloc[0]['Symbol'])

# Main content
st.title("📊 Friday-Monday Pattern Trading System")
st.markdown("**Historical Success Rate:** 88.8% | **Stocks Analyzed:** 48 | **Period:** 5 Years")

# Tabs
tab1, tab2, tab3, tab4 = st.tabs(["📅 Friday Scanner", "📊 Monday Scanner", "📈 Performance", "ℹ️ Help"])

# TAB 1: FRIDAY SCANNER
with tab1:
    st.header("Friday 3:15 PM Scanner")
    st.markdown("Identify stocks where **Friday High < Thursday High**")
    
    col1, col2 = st.columns([3, 1])
    
    with col2:
        if st.button("🔍 Run Friday Scan", type="primary", use_container_width=True):
            st.session_state.friday_scan_running = True
    
    if 'friday_scan_running' in st.session_state and st.session_state.friday_scan_running:
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        watchlist = []
        total_stocks = len(NIFTY_50_STOCKS)
        
        for idx, (symbol, name) in enumerate(NIFTY_50_STOCKS.items()):
            progress = (idx + 1) / total_stocks
            progress_bar.progress(progress)
            status_text.text(f"Scanning {name} ({idx+1}/{total_stocks})...")
            
            data = download_stock_data(symbol)
            if data is not None:
                data = calculate_indicators(data)
                pattern = check_pattern_setup(data)
                
                if pattern:
                    # Get historical stats
                    if hist_stats is not None:
                        stock_stats = hist_stats[hist_stats['Symbol'] == name]
                        gap_success = stock_stats['Gap_Down_Success_Rate'].values[0] if len(stock_stats) > 0 else 0
                    else:
                        gap_success = 0
                    
                    watchlist.append({
                        'Stock': name,
                        'NSE_Code': symbol,
                        'Friday_Low': pattern['friday_low'],
                        'Friday_Close': pattern['friday_close'],
                        'Friday_High': pattern['friday_high'],
                        'Decline_%': pattern['decline_pct'],
                        'RSI': pattern['rsi'],
                        'Below_SMA20': pattern['below_sma20'],
                        'Volume_Ratio': pattern['volume_ratio'],
                        'Gap_Success_%': gap_success
                    })
        
        progress_bar.empty()
        status_text.empty()
        
        if len(watchlist) == 0:
            st.warning("❌ No pattern setups found today")
            st.info("No stocks meet the Friday High < Thursday High condition")
        else:
            st.success(f"✅ Found {len(watchlist)} Pattern Setups!")
            
            # Convert to DataFrame
            watchlist_df = pd.DataFrame(watchlist)
            watchlist_df = watchlist_df.sort_values('Gap_Success_%', ascending=False)
            
            # Save to session state
            st.session_state.friday_watchlist = watchlist_df
            
            # Priority sections
            priority1 = watchlist_df[watchlist_df['Gap_Success_%'] >= 95]
            priority2 = watchlist_df[(watchlist_df['Gap_Success_%'] >= 90) & (watchlist_df['Gap_Success_%'] < 95)]
            priority3 = watchlist_df[(watchlist_df['Gap_Success_%'] >= 80) & (watchlist_df['Gap_Success_%'] < 90)]
            
            if len(priority1) > 0:
                st.subheader("🔥 Priority 1: Highest Confidence (95%+ Success)")
                st.dataframe(
                    priority1[['Stock', 'Friday_Low', 'Friday_Close', 'Decline_%', 'RSI', 'Gap_Success_%']].style.format({
                        'Friday_Low': '₹{:.2f}',
                        'Friday_Close': '₹{:.2f}',
                        'Decline_%': '{:.2f}%',
                        'RSI': '{:.1f}',
                        'Gap_Success_%': '{:.1f}%'
                    }).background_gradient(subset=['Gap_Success_%'], cmap='RdYlGn', vmin=80, vmax=100),
                    use_container_width=True,
                    hide_index=True
                )
            
            if len(priority2) > 0:
                st.subheader("⚡ Priority 2: High Confidence (90-95% Success)")
                st.dataframe(
                    priority2[['Stock', 'Friday_Low', 'Friday_Close', 'Decline_%', 'Gap_Success_%']].style.format({
                        'Friday_Low': '₹{:.2f}',
                        'Friday_Close': '₹{:.2f}',
                        'Decline_%': '{:.2f}%',
                        'Gap_Success_%': '{:.1f}%'
                    }),
                    use_container_width=True,
                    hide_index=True
                )
            
            if len(priority3) > 0:
                st.subheader("📊 Priority 3: Good Confidence (80-90% Success)")
                st.dataframe(
                    priority3[['Stock', 'Friday_Low', 'Friday_Close', 'Gap_Success_%']].style.format({
                        'Friday_Low': '₹{:.2f}',
                        'Friday_Close': '₹{:.2f}',
                        'Gap_Success_%': '{:.1f}%'
                    }),
                    use_container_width=True,
                    hide_index=True
                )
            
            # Full watchlist
            with st.expander("📋 View Complete Watchlist"):
                st.dataframe(
                    watchlist_df.style.format({
                        'Friday_Low': '₹{:.2f}',
                        'Friday_Close': '₹{:.2f}',
                        'Friday_High': '₹{:.2f}',
                        'Decline_%': '{:.2f}%',
                        'RSI': '{:.1f}',
                        'Volume_Ratio': '{:.2f}',
                        'Gap_Success_%': '{:.1f}%'
                    }),
                    use_container_width=True,
                    hide_index=True
                )
            
            # Download button
            csv = watchlist_df.to_csv(index=False)
            st.download_button(
                label="📥 Download Watchlist CSV",
                data=csv,
                file_name=f"friday_watchlist_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                use_container_width=True
            )
            
            # Chart
            fig = px.bar(
                watchlist_df.head(15),
                x='Stock',
                y='Gap_Success_%',
                color='Gap_Success_%',
                color_continuous_scale='RdYlGn',
                title="Top 15 Stocks by Historical Gap Down Success Rate"
            )
            fig.update_layout(yaxis_title="Success Rate (%)", xaxis_title="")
            st.plotly_chart(fig, use_container_width=True)

# TAB 2: MONDAY SCANNER
with tab2:
    st.header("Monday 9:20 AM Gap Scanner")
    st.markdown("Check which watchlist stocks have **gap down >0.3%**")
    
    col1, col2 = st.columns([3, 1])
    
    with col2:
        if st.button("🔍 Run Monday Scan", type="primary", use_container_width=True):
            st.session_state.monday_scan_running = True
    
    if 'monday_scan_running' in st.session_state and st.session_state.monday_scan_running:
        
        # Check if Friday watchlist exists
        if 'friday_watchlist' not in st.session_state:
            st.error("❌ No Friday watchlist found!")
            st.info("Please run Friday Scanner first to generate watchlist")
        else:
            watchlist = st.session_state.friday_watchlist
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            trade_signals = []
            
            for idx, row in watchlist.iterrows():
                progress = (idx + 1) / len(watchlist)
                progress_bar.progress(progress)
                status_text.text(f"Checking {row['Stock']} ({idx+1}/{len(watchlist)})...")
                
                data = download_stock_data(row['NSE_Code'], period="5d")
                gap_info = check_monday_gap(data)
                
                if gap_info and gap_info['has_gap_down']:
                    # Calculate trade specs
                    entry = gap_info['monday_open']
                    target = row['Friday_Low']
                    stop = row['Friday_High']
                    
                    profit_pct = ((target - entry) / entry) * 100
                    risk_pct = ((stop - entry) / entry) * 100
                    
                    position_value = calculate_position_size(capital, 1.0, abs(risk_pct))
                    shares = int(position_value / entry)
                    actual_position = shares * entry
                    
                    profit_if_target = shares * (target - entry)
                    loss_if_stop = shares * (entry - stop)
                    
                    trade_signals.append({
                        'Stock': row['Stock'],
                        'NSE_Code': row['NSE_Code'],
                        'Gap_%': gap_info['gap_pct'],
                        'Historical_Success_%': row['Gap_Success_%'],
                        'Entry': entry,
                        'Target': target,
                        'Stop': stop,
                        'Shares': shares,
                        'Position_Value': actual_position,
                        'Profit_Potential_%': profit_pct,
                        'Risk_%': abs(risk_pct),
                        'Risk_Reward': abs(profit_pct / risk_pct) if risk_pct != 0 else 0,
                        'Profit_if_Target': profit_if_target,
                        'Loss_if_Stop': loss_if_stop,
                        'Capital_Risk_%': (abs(loss_if_stop) / capital) * 100
                    })
            
            progress_bar.empty()
            status_text.empty()
            
            if len(trade_signals) == 0:
                st.warning("❌ No gap down signals today")
                st.info("None of the watchlist stocks gapped down >0.3%")
            else:
                st.success(f"✅ Found {len(trade_signals)} Trade Signals!")
                
                # Convert to DataFrame
                signals_df = pd.DataFrame(trade_signals)
                signals_df = signals_df.sort_values('Historical_Success_%', ascending=False)
                
                # Save to session state
                st.session_state.monday_signals = signals_df
                
                # Display each trade signal
                for idx, trade in signals_df.iterrows():
                    with st.expander(f"📊 {idx+1}. {trade['Stock']} - Gap: {trade['Gap_%']:.2f}% | Success: {trade['Historical_Success_%']:.1f}%", expanded=True):
                        col1, col2, col3 = st.columns(3)
                        
                        with col1:
                            st.metric("Entry Price", f"₹{trade['Entry']:.2f}")
                            st.metric("Shares to Trade", f"{trade['Shares']:,}")
                        
                        with col2:
                            st.metric("Target Price", f"₹{trade['Target']:.2f}", delta=f"{trade['Profit_Potential_%']:.2f}%")
                            st.metric("Position Value", f"₹{trade['Position_Value']:,.0f}")
                        
                        with col3:
                            st.metric("Stop Loss", f"₹{trade['Stop']:.2f}", delta=f"-{trade['Risk_%']:.2f}%")
                            st.metric("Risk:Reward", f"1:{trade['Risk_Reward']:.2f}")
                        
                        st.divider()
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            st.success(f"✅ If Target Hit: **₹{trade['Profit_if_Target']:,.0f}** profit")
                        with col2:
                            st.error(f"❌ If Stop Hit: **₹{trade['Loss_if_Stop']:,.0f}** loss")
                        
                        st.info(f"💰 Capital at Risk: **{trade['Capital_Risk_%']:.2f}%**")
                
                # Quick reference table
                st.subheader("📋 Quick Reference Table")
                st.dataframe(
                    signals_df[['Stock', 'Gap_%', 'Historical_Success_%', 'Entry', 'Target', 'Stop', 'Shares', 'Profit_Potential_%']].style.format({
                        'Gap_%': '{:.2f}%',
                        'Historical_Success_%': '{:.1f}%',
                        'Entry': '₹{:.2f}',
                        'Target': '₹{:.2f}',
                        'Stop': '₹{:.2f}',
                        'Shares': '{:,}',
                        'Profit_Potential_%': '{:.2f}%'
                    }).background_gradient(subset=['Historical_Success_%'], cmap='RdYlGn', vmin=80, vmax=100),
                    use_container_width=True,
                    hide_index=True
                )
                
                # Download button
                csv = signals_df.to_csv(index=False)
                st.download_button(
                    label="📥 Download Trade Signals CSV",
                    data=csv,
                    file_name=f"monday_signals_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )

# TAB 3: PERFORMANCE
with tab3:
    st.header("📈 Historical Performance")
    
    if hist_stats is not None:
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total Stocks", len(hist_stats))
        with col2:
            st.metric("Avg Base Success", f"{hist_stats['Base_Success_Rate'].mean():.1f}%")
        with col3:
            st.metric("Avg Gap Success", f"{hist_stats['Gap_Down_Success_Rate'].mean():.1f}%")
        with col4:
            st.metric("Avg Improvement", f"+{hist_stats['Improvement'].mean():.1f}%")
        
        st.divider()
        
        # Top performers
        st.subheader("🏆 Top 15 Performers")
        top15 = hist_stats.nlargest(15, 'Gap_Down_Success_Rate')
        
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=top15['Symbol'],
            y=top15['Base_Success_Rate'],
            name='Base Pattern',
            marker_color='indianred'
        ))
        fig.add_trace(go.Bar(
            x=top15['Symbol'],
            y=top15['Gap_Down_Success_Rate'],
            name='With Gap Down',
            marker_color='lightseagreen'
        ))
        fig.update_layout(
            barmode='group',
            title="Base vs Enhanced Pattern Success Rate",
            yaxis_title="Success Rate (%)",
            xaxis_title=""
        )
        st.plotly_chart(fig, use_container_width=True)
        
        # Full stats table
        st.subheader("📊 Complete Statistics")
        st.dataframe(
            hist_stats[['Symbol', 'Total_Setups', 'Base_Success_Rate', 'Gap_Down_Setups', 'Gap_Down_Success_Rate', 'Improvement']].style.format({
                'Base_Success_Rate': '{:.1f}%',
                'Gap_Down_Success_Rate': '{:.1f}%',
                'Improvement': '+{:.1f}%'
            }).background_gradient(subset=['Gap_Down_Success_Rate'], cmap='RdYlGn', vmin=70, vmax=100),
            use_container_width=True,
            hide_index=True
        )

# TAB 4: HELP
with tab4:
    st.header("ℹ️ How to Use This System")
    
    st.markdown("""
    ## 📅 Weekly Workflow
    
    ### Friday 3:15 PM
    1. Click **"Run Friday Scan"** button
    2. System scans all 48 Nifty 50 stocks
    3. Identifies stocks where Friday High < Thursday High
    4. Generates watchlist sorted by historical success rate
    5. Download CSV for reference
    
    ### Monday 9:20 AM
    1. Click **"Run Monday Scan"** button
    2. System checks which watchlist stocks gapped down >0.3%
    3. Generates complete trade specifications for each signal
    4. Shows entry, target, stop loss, position size
    5. Download CSV for your trading platform
    
    ### Monday 5:30-9:30 PM (Your Trading Session)
    1. Execute trades as per system specifications
    2. Enter at Monday open price
    3. Set stop loss at Friday high (MANDATORY)
    4. Set target at Friday low
    5. Use exact position size calculated by system
    
    ---
    
    ## 🎯 Trade Prioritization
    
    **Priority 1 (95%+ Success):** Trade ALL of these
    - Coal India, Divi's Labs, ITC, Bharti Airtel, Reliance, Asian Paints, Titan
    
    **Priority 2 (90-95% Success):** Trade top 3
    - Based on largest gap down and lowest RSI
    
    **Priority 3 (80-90% Success):** Trade only if Priority 1 & 2 are limited
    
    ---
    
    ## 🚨 Critical Rules
    
    1. ✅ **ONLY trade when gap down >0.3%** - System filters automatically
    2. ✅ **ALWAYS set stop at Friday high** - System provides exact level
    3. ✅ **Risk 1% per trade maximum** - System calculates position size
    4. ✅ **Maximum 5 simultaneous trades** - Even if more signals appear
    5. ✅ **Stop hit = Exit immediately** - No averaging down
    
    ---
    
    ## 📊 Expected Results
    
    **Trading top 8 stocks (95%+ success):**
    - Win Rate: 95-100%
    - Monthly Setups: 3-4 trades
    - Average Profit: 0.5-1% per trade
    - Expected Monthly Return: 2-4%
    
    ---
    
    ## 📧 Email Automation
    
    To enable automatic email alerts:
    1. Configure SMTP settings in `config.json`
    2. Set up Windows Task Scheduler or Cron
    3. System will email you Friday watchlist and Monday signals
    4. See setup guide in documentation
    
    ---
    
    ## 🆘 Support
    
    - **Historical Data:** 5 years, 5,331 setups analyzed
    - **Data Source:** Yahoo Finance (yfinance)
    - **Update Frequency:** Real-time (15-min delay for NSE)
    - **System Success Rate:** 88.8% overall
    
    For detailed documentation, see **COMPLETE_USER_GUIDE.md**
    """)

# Footer
st.divider()
st.markdown("""
<div style='text-align: center; color: gray;'>
    <p>Friday-Monday Pattern Trading System | Historical Success: 88.8% | 48 Nifty 50 Stocks | 5 Years Data</p>
    <p>⚠️ Risk Disclaimer: Past performance does not guarantee future results. Always use stop losses.</p>
</div>
""", unsafe_allow_html=True)
