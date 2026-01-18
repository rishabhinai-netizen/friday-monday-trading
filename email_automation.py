"""
EMAIL AUTOMATION SYSTEM - SIMPLIFIED FOR GITHUB ACTIONS
Sends automated Friday watchlist and Monday trade signals via email
"""

import smtplib
import pandas as pd
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
import yfinance as yf
import os
import sys

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

def get_email_config():
    """Get email configuration from environment variables"""
    print("Getting email configuration from environment variables...")
    
    sender_email = os.getenv('SENDER_EMAIL')
    sender_password = os.getenv('SENDER_PASSWORD')
    recipient_email = os.getenv('RECIPIENT_EMAIL')
    smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
    smtp_port = int(os.getenv('SMTP_PORT', '587'))
    
    print(f"SENDER_EMAIL: {'✓ Found' if sender_email else '✗ Missing'}")
    print(f"SENDER_PASSWORD: {'✓ Found' if sender_password else '✗ Missing'}")
    print(f"RECIPIENT_EMAIL: {'✓ Found' if recipient_email else '✗ Missing'}")
    print(f"SMTP_SERVER: {smtp_server}")
    print(f"SMTP_PORT: {smtp_port}")
    
    if not sender_email or not sender_password or not recipient_email:
        print("\n❌ ERROR: Email configuration missing!")
        print("Please check GitHub Secrets:")
        print("  - SENDER_EMAIL")
        print("  - SENDER_PASSWORD")
        print("  - RECIPIENT_EMAIL")
        sys.exit(1)
    
    return {
        'sender_email': sender_email,
        'sender_password': sender_password,
        'recipient_email': recipient_email,
        'smtp_server': smtp_server,
        'smtp_port': smtp_port
    }

def send_email(config, subject, html_content, attachments=None):
    """Send email with optional attachments"""
    print(f"\nSending email to {config['recipient_email']}...")
    
    try:
        # Create message
        message = MIMEMultipart('alternative')
        message['Subject'] = subject
        message['From'] = config['sender_email']
        message['To'] = config['recipient_email']
        
        # Attach HTML content
        html_part = MIMEText(html_content, 'html')
        message.attach(html_part)
        
        # Attach files
        if attachments:
            for filepath in attachments:
                if os.path.exists(filepath):
                    print(f"  Attaching: {filepath}")
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
        print(f"  Connecting to {config['smtp_server']}:{config['smtp_port']}...")
        server = smtplib.SMTP(config['smtp_server'], config['smtp_port'])
        server.starttls()
        print(f"  Logging in as {config['sender_email']}...")
        server.login(config['sender_email'], config['sender_password'])
        print(f"  Sending message...")
        server.send_message(message)
        server.quit()
        
        print(f"✅ Email sent successfully to {config['recipient_email']}")
        return True
    
    except Exception as e:
        print(f"❌ Error sending email: {e}")
        import traceback
        traceback.print_exc()
        return False

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

def friday_scan():
    """Run Friday scanner and send email"""
    print("="*80)
    print("FRIDAY PATTERN SCANNER")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)
    
    config = get_email_config()
    watchlist = []
    
    print("\nScanning stocks...")
    for symbol, name in NIFTY_50_STOCKS.items():
        print(f"  Checking {name}...", end=" ")
        data = download_stock_data(symbol)
        if data is not None:
            data = calculate_indicators(data)
            pattern = check_pattern_setup(data)
            
            if pattern:
                watchlist.append({
                    'Stock': name,
                    'NSE_Code': symbol,
                    'Friday_Low': pattern['friday_low'],
                    'Friday_Close': pattern['friday_close'],
                    'Friday_High': pattern['friday_high'],
                    'Decline_%': pattern['decline_pct'],
                    'RSI': pattern['rsi']
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
        </body>
        </html>
        """
        
        send_email(
            config,
            subject=f"Friday Scanner: No Setups - {datetime.now().strftime('%Y-%m-%d')}",
            html_content=html
        )
        return
    
    # Create DataFrame and save
    watchlist_df = pd.DataFrame(watchlist)
    watchlist_df = watchlist_df.sort_values('RSI', ascending=True)
    
    csv_filename = f"friday_watchlist_{datetime.now().strftime('%Y%m%d')}.csv"
    watchlist_df.to_csv(csv_filename, index=False)
    
    print(f"\n✅ Found {len(watchlist)} pattern setups!")
    
    # Generate HTML email
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
        </style>
    </head>
    <body>
        <h2>✅ Friday Pattern Scanner Results</h2>
        <p><strong>Date:</strong> {datetime.now().strftime('%Y-%m-%d %A')}</p>
        <p><strong>Total Setups Found:</strong> {len(watchlist)}</p>
        <hr>
        <h3>📋 Watchlist</h3>
        <table>
            <tr>
                <th>Stock</th>
                <th>Friday Low</th>
                <th>Friday Close</th>
                <th>Decline %</th>
                <th>RSI</th>
            </tr>
    """
    
    for _, row in watchlist_df.iterrows():
        html += f"""
            <tr>
                <td><strong>{row['Stock']}</strong></td>
                <td>₹{row['Friday_Low']:.2f}</td>
                <td>₹{row['Friday_Close']:.2f}</td>
                <td>{row['Decline_%']:.2f}%</td>
                <td>{row['RSI']:.1f}</td>
            </tr>
        """
    
    html += """
        </table>
        <hr>
        <h3>📋 Next Steps:</h3>
        <ol>
            <li>Review the watchlist (attached CSV)</li>
            <li>On Monday 9:40 AM, check for gap down signals</li>
            <li>If gap down &gt;0.3%, execute trades in evening session</li>
        </ol>
    </body>
    </html>
    """
    
    send_email(
        config,
        subject=f"🔥 Friday Alert: {len(watchlist)} Pattern Setups Found - {datetime.now().strftime('%Y-%m-%d')}",
        html_content=html,
        attachments=[csv_filename]
    )

if __name__ == "__main__":
    print("\n" + "="*80)
    print("EMAIL AUTOMATION - GITHUB ACTIONS")
    print("="*80 + "\n")
    
    if len(sys.argv) < 2:
        print("Usage: python email_automation.py friday")
        sys.exit(1)
    
    mode = sys.argv[1].lower()
    
    if mode == "friday":
        friday_scan()
    else:
        print(f"❌ Invalid mode: {mode}")
        print("Use 'friday'")
        sys.exit(1)
