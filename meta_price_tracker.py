"""
META (Facebook) Stock Price Tracker — AI Agent
================================================
Monitors Meta's stock price. When it drops below your target:
  1. Fetches recent META news from NewsAPI
  2. Asks Claude to reason about why the price dropped
  3. Sends you a smart email with analysis, not just a price alert

Requirements:
    pip install -r requirements.txt

Environment variables to set in Railway:
    EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECEIVER
    ANTHROPIC_API_KEY
    NEWS_API_KEY
"""

import yfinance as yf
import time
import os
import smtplib
import requests
import anthropic
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Optional


# ─────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────

TICKER                 = "META"
ALERT_BELOW            = 800.00
CHECK_INTERVAL_SECONDS = 60
LOG_FILE               = "meta_price_log.csv"
ALERT_COOLDOWN_SECONDS = 3600   # 1 hour between emails

# --- Credentials (set these as Railway environment variables) ---
EMAIL_SENDER      = os.environ.get("EMAIL_SENDER",      "you@gmail.com")
EMAIL_PASSWORD    = os.environ.get("EMAIL_PASSWORD",    "xxxx xxxx xxxx xxxx")
EMAIL_RECEIVER    = os.environ.get("EMAIL_RECEIVER",    "you@gmail.com")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
NEWS_API_KEY      = os.environ.get("NEWS_API_KEY",      "")

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

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


def get_news(query: str, num_articles: int = 5) -> list:
    """Fetch recent news headlines for a query using NewsAPI."""
    try:
        url = "https://newsapi.org/v2/everything"
        params = {
            "q": query,
            "sortBy": "publishedAt",
            "pageSize": num_articles,
            "language": "en",
            "apiKey": NEWS_API_KEY,
        }
        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        if data.get("status") != "ok":
            print(f"  [WARN] NewsAPI error: {data.get('message')}")
            return []

        articles = []
        for a in data.get("articles", []):
            articles.append({
                "title":       a.get("title", ""),
                "description": a.get("description", ""),
                "source":      a.get("source", {}).get("name", ""),
                "publishedAt": a.get("publishedAt", ""),
            })
        return articles

    except Exception as e:
        print(f"  [ERROR] Could not fetch news: {e}")
        return []


def analyze_with_claude(price: float, target: float, articles: list) -> str:
    """Ask Claude to reason about the price drop and news."""
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        # Format news for the prompt
        if articles:
            news_text = "\n".join([
                f"- [{a['source']}] {a['title']}: {a['description']}"
                for a in articles
            ])
        else:
            news_text = "No recent news articles found."

        prompt = f"""You are a financial analyst assistant. META's stock price has just dropped below a user's alert threshold.

Price data:
- Current price: ${price:.2f}
- Alert threshold: ${target:.2f}
- Drop below threshold: ${target - price:.2f} ({((target - price) / target * 100):.2f}%)

Recent META news headlines:
{news_text}

Please provide a brief, clear analysis (3-5 sentences) covering:
1. What might be causing this price drop based on the news
2. Whether this looks like a short-term dip or something more significant
3. What the investor should keep an eye on

Be direct and practical. Do not give explicit buy/sell advice."""

        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}]
        )

        return message.content[0].text

    except Exception as e:
        print(f"  [ERROR] Claude analysis failed: {e}")
        return "AI analysis unavailable at this time."


def send_smart_email(price: float, target: float, analysis: str, articles: list):
    """Send a smart email with AI analysis and news."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    subject = f"🔴 META Alert: ${price:.2f} dropped below ${target:.2f} — AI Analysis Inside"

    # Format news links
    news_section = ""
    if articles:
        news_section = "\nRECENT NEWS:\n"
        for a in articles[:3]:
            news_section += f"  • [{a['source']}] {a['title']}\n"

    body = f"""
META Stock Price Alert
══════════════════════════════════════

  Current Price : ${price:.2f}
  Your Target   : below ${target:.2f}
  Below by      : ${target - price:.2f} ({((target - price) / target * 100):.2f}%)
  Time          : {timestamp}

──────────────────────────────────────
AI ANALYSIS
──────────────────────────────────────

{analysis}
{news_section}
──────────────────────────────────────
This is an automated alert from your META Price Tracker Agent.
Next alert in {ALERT_COOLDOWN_SECONDS // 60} minutes if price stays below target.
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

        print(f"  📧 Smart alert email sent to {EMAIL_RECEIVER}")
        return True

    except smtplib.SMTPAuthenticationError:
        print("  [ERROR] Email authentication failed — check your Gmail App Password.")
        return False
    except Exception as e:
        print(f"  [ERROR] Failed to send email: {e}")
        return False


def log_price(price: float):
    """Append price to CSV log file."""
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
    print(f"  META Stock Price Tracker — AI Agent Mode")
    print(f"  Watching  : {TICKER}")
    print(f"  Alert if  : price drops BELOW ${ALERT_BELOW:.2f}")
    print(f"  Interval  : every {CHECK_INTERVAL_SECONDS}s")
    print(f"  Email to  : {EMAIL_RECEIVER}")
    print(f"  Cooldown  : {ALERT_COOLDOWN_SECONDS // 60} min between emails")
    print(f"  AI model  : claude-sonnet-4-6")
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

            if price < ALERT_BELOW:
                now = time.time()
                cooldown_over = (
                    last_alert_time is None or
                    (now - last_alert_time) > ALERT_COOLDOWN_SECONDS
                )
                if cooldown_over:
                    print(f"  ⚠️  Triggered! Fetching news and running AI analysis...")

                    # Step 1: Get news
                    articles = get_news("META Facebook stock")
                    print(f"  📰 Found {len(articles)} news articles")

                    # Step 2: Ask Claude to reason about it
                    print(f"  🤖 Asking Claude for analysis...")
                    analysis = analyze_with_claude(price, ALERT_BELOW, articles)
                    print(f"  ✅ Analysis complete")

                    # Step 3: Send smart email
                    success = send_smart_email(price, ALERT_BELOW, analysis, articles)
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
