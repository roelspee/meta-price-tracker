"""
META (Facebook) Stock Price Tracker Agent
==========================================
Monitors Meta's stock price and sends you an email alert
when the price drops below your target.

Usage:
    python meta_price_tracker.py

Requirements:
    pip install yfinance

Email Setup (Gmail):
    1. Go to myaccount.google.com/security
    2. Enable 2-Step Verification if not already on
    3. Search "App Passwords" → create one for "Mail"
    4. Paste the 16-character password into EMAIL_PASSWORD below
"""

import yfinance as yf
import time
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Optional


# ─────────────────────────────────────────────
#  CONFIG — edit these before running
# ─────────────────────────────────────────────

TICKER = "META"                     # Stock to track
ALERT_BELOW = 700.00                # 🔔 Send email if price drops BELOW this
CHECK_INTERVAL_SECONDS = 60         # How often to check (seconds)
LOG_FILE = "meta_price_log.csv"     # Set to None to disable logging

# --- Email Settings ---
# These are read from environment variables so your password is never in the code.
# On Railway: set these in your project's "Variables" tab.
# For local testing: you can temporarily paste values directly here instead.
import os as _os
EMAIL_SENDER   = _os.environ.get("EMAIL_SENDER", "you@gmail.com")
EMAIL_PASSWORD = _os.environ.get("EMAIL_PASSWORD", "xxxx xxxx xxxx xxxx")
EMAIL_RECEIVER = _os.environ.get("EMAIL_RECEIVER", "you@gmail.com")
SMTP_HOST      = "smtp.gmail.com"
SMTP_PORT      = 587

# Cooldown: wait this long before sending another alert email
# Prevents inbox spam if price stays below threshold for a long time
ALERT_COOLDOWN_SECONDS = 3600  # 1 hour

# ─────────────────────────────────────────────


def get_price(ticker: str) -> Optional[float]:
    """Fetch the latest stock price."""
    try:
        stock = yf.Ticker(ticker)
        price = stock.fast_info.last_price
        return round(price, 2)
    except Exception as e:
        print(f"  [ERROR] Could not fetch price: {e}")
        return None


def send_email_alert(price: float, target: float):
    """Send an email alert when price drops below target."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    subject = f"🔴 META Alert: ${price:.2f} dropped below ${target:.2f}"

    body = f"""
Hi there,

Your META (Facebook) stock price alert has been triggered.

  Current Price : ${price:.2f}
  Your Target   : below ${target:.2f}
  Below by      : ${target - price:.2f}  ({((target - price) / target * 100):.2f}%)
  Time          : {timestamp}

This is an automated alert from your Meta Price Tracker.
It won't send another alert for {ALERT_COOLDOWN_SECONDS // 60} minutes.
"""

    try:
        msg = MIMEMultipart()
        msg["From"] = EMAIL_SENDER
        msg["To"] = EMAIL_RECEIVER
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())

        print(f"  📧 Alert email sent to {EMAIL_RECEIVER}")
        return True

    except smtplib.SMTPAuthenticationError:
        print("  [ERROR] Email authentication failed.")
        print("  → Use a Gmail App Password, not your regular password.")
        print("  → Guide: myaccount.google.com → Security → App Passwords")
        return False
    except Exception as e:
        print(f"  [ERROR] Failed to send email: {e}")
        return False


def log_price(price: float):
    """Append price + alert flag to CSV log file."""
    if not LOG_FILE:
        return
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    file_exists = os.path.isfile(LOG_FILE)
    with open(LOG_FILE, "a") as f:
        if not file_exists:
            f.write("timestamp,ticker,price,below_target\n")
        below = "YES" if price < ALERT_BELOW else ""
        f.write(f"{timestamp},{TICKER},{price},{below}\n")


def format_change(price: float, prev_price: Optional[float]) -> str:
    if prev_price is None:
        return ""
    change = price - prev_price
    pct = (change / prev_price) * 100
    arrow = "▲" if change >= 0 else "▼"
    return f"  {arrow} ${abs(change):.2f} ({abs(pct):.2f}%)"


def run():
    print("=" * 54)
    print(f"  META Stock Price Tracker — Email Alert Mode")
    print(f"  Watching  : {TICKER}")
    print(f"  Alert if  : price drops BELOW ${ALERT_BELOW:.2f}")
    print(f"  Interval  : every {CHECK_INTERVAL_SECONDS}s")
    print(f"  Email to  : {EMAIL_RECEIVER}")
    print(f"  Cooldown  : {ALERT_COOLDOWN_SECONDS // 60} min between emails")
    if LOG_FILE:
        print(f"  Log file  : {LOG_FILE}")
    print("=" * 54)
    print("  Press Ctrl+C to stop.\n")

    prev_price = None
    last_alert_time = None

    while True:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        price = get_price(TICKER)

        if price is not None:
            change_str = format_change(price, prev_price)
            status = "🔴 BELOW TARGET" if price < ALERT_BELOW else "✅ above target"
            print(f"[{timestamp}]  {TICKER}: ${price:.2f}{change_str}  —  {status}")

            log_price(price)

            # Send alert if below target and cooldown has passed
            if price < ALERT_BELOW:
                now = time.time()
                cooldown_over = (
                    last_alert_time is None or
                    (now - last_alert_time) > ALERT_COOLDOWN_SECONDS
                )
                if cooldown_over:
                    print(f"  ⚠️  ${price:.2f} is below ${ALERT_BELOW:.2f} — sending alert email...")
                    success = send_email_alert(price, ALERT_BELOW)
                    if success:
                        last_alert_time = now
                else:
                    remaining = int(ALERT_COOLDOWN_SECONDS - (now - last_alert_time))
                    print(f"  ⏳ Cooldown active — next email in {remaining // 60}m {remaining % 60}s")

            prev_price = price

        else:
            print(f"[{timestamp}]  Could not retrieve price. Retrying...")

        try:
            time.sleep(CHECK_INTERVAL_SECONDS)
        except KeyboardInterrupt:
            print(f"\nStopped. Goodbye!")
            if LOG_FILE and os.path.isfile(LOG_FILE):
                print(f"Price history saved to: {LOG_FILE}")
            break


if __name__ == "__main__":
    run()
