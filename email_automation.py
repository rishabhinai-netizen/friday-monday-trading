"""
EMAIL AUTOMATION SYSTEM
Sends automated Friday watchlist and Monday trade signals via email
Can be scheduled with Windows Task Scheduler or Cron
"""

import smtplib
import json
import pandas as pd
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
import yfinance as yf
import os

# Load configuration
def load_config():
    """Load email configuration from config.json"""
    try:
        with open('config.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print("❌ config.json not found!")
        print("Creating sample config file...")
        
        sample_config = {
            "email": {
                "smtp_server": "smtp.gmail.com",
                "smtp_port": 587,
                "sender_email": "your.email@gmail.com",
                "sender_password": "your_app_specific_password",
                "recipient_email": "your.email@gmail.com"
            },
            "trading": {
                "capital": 100000
            }
        }
        
        with open('config.json', 'w') as f:
            json.dump(sample_config, f, indent=4)
        
        print("✅ Sample config.json created. Please edit with your email settings.")
        return sample_config

# Send email with HTML content
def send_email(subject, html_content, attachments=None):
    """Send email with optional attachments"""
    config = load_config()
    email_config = config.get('email', {})
    
    sender_email = email_config.get('sender_email')
    sender_password = email_config.get('sender_password')
    recipient_email = email_config.get('recipient_email')
    smtp_server = email_config.get('smtp_server', 'smtp.gmail.com')
    smtp_port = email_config.get('smtp_port', 587)
    
    if not sender_email or not sender_password:
        print("❌ Email not configured in config.json")
        return False
    
    try:
        # Create message
        message = MIMEMultipart('alternative')
        message['Subject'] = subject
        message['From'] = sender_email
        message['To'] = recipient_email
        
        # Attach HTML content
        html_part = MIMEText(html_content, 'html')
        message.attach(html_part)
        
        # Attach files
        if attachments:
            for filepath in attachments:
                if os.path.exists(filepath):
                    with open(filepath, 'rb') as f:
                        part = MIMEBase('application', 'octet-stream')
                        part.set_payload(f.read())
                    
                    encoders.encode_base64(part)
                    part.add_header(
                        'Content-Disposition',
                        f'attachment; filename= {os.path.basename(filepath)}'
                    )
                    message.attach(part)
        
        # Send email
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(sender_email, sender_password)
        server.send_message(message)
        server.quit()
        
        print(f"✅ Email sent successfully to {recipient_email}")
        return True
    
    except Exception as e:
        print(f"❌ Error sending email: {e}")
        return False

# Nifty 50 stocks
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

# Load stats
def load_historical_stats():
    """Load historical statistics"""
    try:
        return pd.read_csv('nifty50_summary_stats.csv')
    except:
        return None

# Download data
def download_stock_data(symbol, period="1mo"):
    """Download stock data"""
    try:
        data = yf.download(symbol, period=period, progress=False)
        if data.empty:
            return None
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
        return data
    except:
        return None

# Calculate indicators
def calculate_indicators(data):
    """Calculate technical indicators"""
    if len(data) < 20:
        return data
    
    delta = data['Close'].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = -delta.where(delta < 0, 0).rolling(14).mean()
    rs = gain / loss
    data['RSI'] = 100 - (100 / (1 + rs))
    
    data['SMA_20'] = data['Close'].rolling(20).mean()
    data['Volume_SMA_20'] = data['Volume'].rolling(20).mean()
    data['Volume_Ratio'] = data['Volume'] / data['Volume_SMA_20']
    
    return data

# Check pattern
def check_pattern_setup(data):
    """Check Friday pattern"""
    if data is None or len(data) < 2:
        return None
    
    recent = data.tail(5)
    thursday_data = None
    friday_data = None
    
    for i in range(len(recent)-1):
        if recent.index[i].dayofweek == 3:
            thursday_data = recent.iloc[i]
            if i + 1 < len(recent) and recent.index[i+1].dayofweek == 4:
                friday_data = recent.iloc[i+1]
                break
    
    if thursday_data is None or friday_data is None:
        return None
    
    if friday_data['High'] < thursday_data['High']:
        return {
            'friday_low': friday_data['Low'],
            'friday_close': friday_data['Close'],
            'friday_high': friday_data['High'],
            'decline_pct': ((friday_data['High'] - thursday_data['High']) / thursday_data['High']) * 100,
            'rsi': data['RSI'].iloc[-1] if 'RSI' in data.columns else None,
        }
    return None

# Check Monday gap
def check_monday_gap(data):
    """Check Monday gap"""
    if data is None or len(data) < 2:
        return None
    
    recent = data.tail(3)
    friday_close = None
    monday_open = None
    monday_data = None
    
    for i in range(len(recent)):
        if recent.index[i].dayofweek == 4:
            friday_close = recent.iloc[i]['Close']
        elif recent.index[i].dayofweek == 0:
            monday_open = recent.iloc[i]['Open']
            monday_data = recent.iloc[i]
    
    if friday_close is None or monday_open is None:
        return None
    
    gap_pct = ((monday_open - friday_close) / friday_close) * 100
    
    return {
        'friday_close': friday_close,
        'monday_open': monday_open,
        'monday_low': monday_data['Low'],
        'gap_pct': gap_pct,
        'has_gap_down': gap_pct < -0.3
    }

# Friday email automation
def send_friday_alert():
    """Run Friday scanner and send email"""
    print("="*80)
    print("FRIDAY PATTERN SCANNER - EMAIL AUTOMATION")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)
    
    hist_stats = load_historical_stats()
    watchlist = []
    
    print("\nScanning stocks...")
    for symbol, name in NIFTY_50_STOCKS.items():
        print(f"  Checking {name}...", end=" ")
        data = download_stock_data(symbol)
        if data is not None:
            data = calculate_indicators(data)
            pattern = check_pattern_setup(data)
            
            if pattern:
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
                    'Gap_Success_%': gap_success
                })
                print("✓ Pattern found!")
            else:
                print("✗")
        else:
            print("✗ (data error)")
    
    if len(watchlist) == 0:
        print("\n❌ No patterns found today")
        
        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif;">
            <h2 style="color: #e74c3c;">❌ No Pattern Setups Today</h2>
            <p>Date: {datetime.now().strftime('%Y-%m-%d')}</p>
            <p>No stocks met the Friday High &lt; Thursday High condition today.</p>
            <p>Check again next Friday.</p>
        </body>
        </html>
        """
        
        send_email(
            subject=f"Friday Scanner: No Setups - {datetime.now().strftime('%Y-%m-%d')}",
            html_content=html
        )
        return
    
    # Create DataFrame
    watchlist_df = pd.DataFrame(watchlist)
    watchlist_df = watchlist_df.sort_values('Gap_Success_%', ascending=False)
    
    # Save CSV
    csv_filename = f"friday_watchlist_{datetime.now().strftime('%Y%m%d')}.csv"
    watchlist_df.to_csv(csv_filename, index=False)
    
    print(f"\n✅ Found {len(watchlist)} pattern setups!")
    
    # Generate HTML email
    priority1 = watchlist_df[watchlist_df['Gap_Success_%'] >= 95]
    priority2 = watchlist_df[(watchlist_df['Gap_Success_%'] >= 90) & (watchlist_df['Gap_Success_%'] < 95)]
    
    html = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; }}
            h2 {{ color: #2ecc71; }}
            table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
            th {{ background-color: #3498db; color: white; padding: 12px; text-align: left; }}
            td {{ border: 1px solid #ddd; padding: 10px; }}
            tr:nth-child(even) {{ background-color: #f2f2f2; }}
            .priority1 {{ background-color: #d5f4e6; }}
            .priority2 {{ background-color: #fef5e7; }}
        </style>
    </head>
    <body>
        <h2>✅ Friday Pattern Scanner Results</h2>
        <p><strong>Date:</strong> {datetime.now().strftime('%Y-%m-%d %A')}</p>
        <p><strong>Total Setups Found:</strong> {len(watchlist)}</p>
        <hr>
    """
    
    if len(priority1) > 0:
        html += """
        <h3 style="color: #27ae60;">🔥 Priority 1: Highest Confidence (95%+ Success)</h3>
        <table>
            <tr>
                <th>Stock</th>
                <th>Friday Low</th>
                <th>Friday Close</th>
                <th>Decline %</th>
                <th>RSI</th>
                <th>Gap Success %</th>
            </tr>
        """
        for _, row in priority1.iterrows():
            html += f"""
            <tr class="priority1">
                <td><strong>{row['Stock']}</strong></td>
                <td>₹{row['Friday_Low']:.2f}</td>
                <td>₹{row['Friday_Close']:.2f}</td>
                <td>{row['Decline_%']:.2f}%</td>
                <td>{row['RSI']:.1f}</td>
                <td><strong>{row['Gap_Success_%']:.1f}%</strong></td>
            </tr>
            """
        html += "</table>"
    
    if len(priority2) > 0:
        html += """
        <h3 style="color: #f39c12;">⚡ Priority 2: High Confidence (90-95% Success)</h3>
        <table>
            <tr>
                <th>Stock</th>
                <th>Friday Low</th>
                <th>Gap Success %</th>
            </tr>
        """
        for _, row in priority2.iterrows():
            html += f"""
            <tr class="priority2">
                <td>{row['Stock']}</td>
                <td>₹{row['Friday_Low']:.2f}</td>
                <td>{row['Gap_Success_%']:.1f}%</td>
            </tr>
            """
        html += "</table>"
    
    html += """
        <hr>
        <h3>📋 Next Steps:</h3>
        <ol>
            <li>Review the watchlist (attached CSV)</li>
            <li>On Monday 9:15 AM, run Monday scanner</li>
            <li>If gap down &gt;0.3%, execute trades in evening session (5:30-9:30 PM)</li>
        </ol>
        <p style="color: gray; font-size: 12px;">
            Attached: Complete watchlist CSV file<br>
            System: Friday-Monday Pattern Trading System<br>
            Historical Success: 88.8%
        </p>
    </body>
    </html>
    """
    
    # Send email with attachment
    send_email(
        subject=f"🔥 Friday Alert: {len(watchlist)} Pattern Setups Found - {datetime.now().strftime('%Y-%m-%d')}",
        html_content=html,
        attachments=[csv_filename]
    )
    
    print(f"✅ Email sent with {csv_filename}")

# Monday email automation
def send_monday_alert():
    """Run Monday scanner and send email"""
    print("="*80)
    print("MONDAY GAP SCANNER - EMAIL AUTOMATION")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)
    
    # Load Friday watchlist
    try:
        # Look for most recent Friday watchlist
        import glob
        csv_files = glob.glob("friday_watchlist_*.csv")
        if not csv_files:
            print("❌ No Friday watchlist found!")
            html = """
            <html>
            <body>
                <h2 style="color: #e74c3c;">❌ Error: No Friday Watchlist</h2>
                <p>Please run Friday scanner first to generate watchlist.</p>
            </body>
            </html>
            """
            send_email("Monday Scanner: Error - No Watchlist", html)
            return
        
        latest_watchlist = max(csv_files)
        watchlist_df = pd.read_csv(latest_watchlist)
        print(f"✓ Loaded watchlist: {latest_watchlist}")
        
    except Exception as e:
        print(f"❌ Error loading watchlist: {e}")
        return
    
    # Load config
    config = load_config()
    capital = config.get('trading', {}).get('capital', 100000)
    
    # Check for gap downs
    trade_signals = []
    
    print("\nChecking for gap downs...")
    for _, row in watchlist_df.iterrows():
        print(f"  Checking {row['Stock']}...", end=" ")
        data = download_stock_data(row['NSE_Code'], period="5d")
        gap_info = check_monday_gap(data)
        
        if gap_info and gap_info['has_gap_down']:
            entry = gap_info['monday_open']
            target = row['Friday_Low']
            stop = row['Friday_High']
            
            profit_pct = ((target - entry) / entry) * 100
            risk_pct = abs(((stop - entry) / entry) * 100)
            
            risk_amount = capital * 0.01
            position_value = risk_amount / (risk_pct / 100)
            shares = int(position_value / entry)
            
            profit_if_target = shares * (target - entry)
            loss_if_stop = shares * (entry - stop)
            
            trade_signals.append({
                'Stock': row['Stock'],
                'Gap_%': gap_info['gap_pct'],
                'Success_%': row['Gap_Success_%'],
                'Entry': entry,
                'Target': target,
                'Stop': stop,
                'Shares': shares,
                'Position': shares * entry,
                'Profit': profit_if_target,
                'Loss': loss_if_stop
            })
            print(f"✓ Gap down {gap_info['gap_pct']:.2f}%!")
        else:
            print("✗")
    
    if len(trade_signals) == 0:
        print("\n❌ No gap down signals today")
        
        html = f"""
        <html>
        <body>
            <h2 style="color: #e74c3c;">❌ No Gap Down Signals Today</h2>
            <p>Date: {datetime.now().strftime('%Y-%m-%d')}</p>
            <p>None of the watchlist stocks gapped down &gt;0.3%</p>
            <p>No trades to execute today.</p>
        </body>
        </html>
        """
        
        send_email(
            subject=f"Monday Scanner: No Signals - {datetime.now().strftime('%Y-%m-%d')}",
            html_content=html
        )
        return
    
    # Save signals
    signals_df = pd.DataFrame(trade_signals)
    signals_df = signals_df.sort_values('Success_%', ascending=False)
    csv_filename = f"monday_signals_{datetime.now().strftime('%Y%m%d')}.csv"
    signals_df.to_csv(csv_filename, index=False)
    
    print(f"\n✅ Found {len(trade_signals)} trade signals!")
    
    # Generate HTML email
    html = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; }}
            h2 {{ color: #2ecc71; }}
            table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
            th {{ background-color: #e74c3c; color: white; padding: 12px; text-align: left; }}
            td {{ border: 1px solid #ddd; padding: 10px; }}
            .trade-box {{ background-color: #f8f9fa; border: 2px solid #3498db; padding: 15px; margin: 15px 0; border-radius: 5px; }}
            .profit {{ color: #27ae60; font-weight: bold; }}
            .loss {{ color: #e74c3c; font-weight: bold; }}
        </style>
    </head>
    <body>
        <h2>🎯 Monday Gap Down Signals!</h2>
        <p><strong>Date:</strong> {datetime.now().strftime('%Y-%m-%d %A')}</p>
        <p><strong>Total Trade Signals:</strong> {len(trade_signals)}</p>
        <p><strong>Trading Capital:</strong> ₹{capital:,}</p>
        <hr>
    """
    
    for idx, trade in signals_df.iterrows():
        html += f"""
        <div class="trade-box">
            <h3>📊 Trade {idx+1}: {trade['Stock']} (Success: {trade['Success_%']:.1f}%)</h3>
            <p><strong>Gap:</strong> {trade['Gap_%']:.2f}%</p>
            <table>
                <tr>
                    <th>Entry</th>
                    <th>Target</th>
                    <th>Stop Loss</th>
                    <th>Shares</th>
                </tr>
                <tr>
                    <td>₹{trade['Entry']:.2f}</td>
                    <td>₹{trade['Target']:.2f}</td>
                    <td>₹{trade['Stop']:.2f}</td>
                    <td>{trade['Shares']:,}</td>
                </tr>
            </table>
            <p><strong>Position Value:</strong> ₹{trade['Position']:,.0f}</p>
            <p class="profit">✅ If Target Hit: ₹{trade['Profit']:,.0f} profit</p>
            <p class="loss">❌ If Stop Hit: ₹{abs(trade['Loss']):,.0f} loss</p>
        </div>
        """
    
    html += """
        <hr>
        <h3>⏰ Action Required:</h3>
        <ol>
            <li><strong>TODAY 5:30-9:30 PM:</strong> Execute these trades</li>
            <li>Enter at specified entry prices</li>
            <li><strong>SET STOPS IMMEDIATELY</strong> after entry</li>
            <li>Set targets at Friday low levels</li>
            <li>Use exact position sizes calculated</li>
        </ol>
        <p style="color: gray; font-size: 12px;">
            Attached: Complete trade signals CSV file<br>
            System: Friday-Monday Pattern Trading System<br>
            Risk per trade: 1% of capital
        </p>
    </body>
    </html>
    """
    
    send_email(
        subject=f"🔥 TRADE ALERT: {len(trade_signals)} Signals - Execute Today! - {datetime.now().strftime('%Y-%m-%d')}",
        html_content=html,
        attachments=[csv_filename]
    )
    
    print(f"✅ Email sent with {csv_filename}")

# Main entry point
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python email_automation.py friday   # Run Friday scanner")
        print("  python email_automation.py monday   # Run Monday scanner")
        sys.exit(1)
    
    mode = sys.argv[1].lower()
    
    if mode == "friday":
        send_friday_alert()
    elif mode == "monday":
        send_monday_alert()
    else:
        print(f"❌ Invalid mode: {mode}")
        print("Use 'friday' or 'monday'")
