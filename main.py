import os
import requests
import gspread
import pandas as pd
import matplotlib.pyplot as plt
from dotenv import load_dotenv
load_dotenv()
from datetime import datetime
from openai import OpenAI
import yfinance as yf
from google.oauth2.service_account import Credentials
import yfinance as yf

# ===== KEYS =====
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
SHEET_ID = os.getenv("SHEET_ID")

client = OpenAI(api_key=OPENAI_API_KEY)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
creds = Credentials.from_service_account_file("google.json", scopes=SCOPES)
gc = gspread.authorize(creds)

sheet = gc.open_by_key(SHEET_ID).worksheet("Portfolio")
history_sheet = gc.open_by_key(SHEET_ID).worksheet("History")

def load_portfolio():
    return sheet.get_all_records()

def get_crypto_prices():
    return {
        "ETH": 2127,
        "SOL": 86
    }

def get_fx():
    return {
        "EURPLN": 4.23,
        "USDPLN": 3.64
    }

def get_stock_prices(tickers):
    prices = {}

    for t in tickers:
        try:
            prices[t] = yf.Ticker(t).history(period="1d")["Close"].iloc[-1]
        except:
            prices[t] = None

    return prices



def calculate(portfolio, fx, crypto_prices, stock_prices):
    total = 0
    breakdown = []

    for a in portfolio:
        t = a["asset_type"]
        name = a["name"]
        amount = float(a["amount"])
        cur = a["currency"]

        value_pln = 0

        if t in ["cash", "bank"]:
            if cur == "PLN":
                value_pln = amount

            elif cur == "EUR":
                value_pln = amount * fx["EURPLN"]

            elif cur == "USD":
                value_pln = amount * fx["USDPLN"]

            else:
                value_pln = 0  # fallback safety

        elif t == "crypto":
            price_usd = crypto_prices.get(name)

            if price_usd is None:
                value_pln = 0
            else:
                value_pln = amount * price_usd * fx["USDPLN"]

        elif t == "stock":
            price_usd = stock_prices.get(name)

            if price_usd is None:
                value_pln = 0
            else:
                value_pln = amount * price_usd * fx["USDPLN"]

        total += value_pln
        breakdown.append(f"{name}: {value_pln:.2f} PLN")

    return total, breakdown

def save_history(total):
    today = datetime.now().strftime("%Y-%m-%d")
    history_sheet.append_row([today, total])

def make_chart():
    data = history_sheet.get_all_records()
    df = pd.DataFrame(data)

    plt.figure()
    plt.plot(df["date"], df["total_pln"])
    plt.xticks(rotation=45)
    plt.tight_layout()

    path = "chart.png"
    plt.savefig(path)
    return path

def risk_alerts(portfolio):
    alerts = []

    crypto = sum(1 for x in portfolio if x["asset_type"] == "crypto")
    stocks = sum(1 for x in portfolio if x["asset_type"] == "stock")

    if crypto > 2:
        alerts.append("⚠️ Высокая доля крипты")

    if stocks > 3:
        alerts.append("⚠️ Слишком много отдельных акций")

    return alerts

def ai_report(total, breakdown, alerts):
    prompt = f"""
Ты финансовый аналитик.

Общий капитал: {total:.2f} PLN

Разбивка:
{breakdown}

Предупреждения системы:
{alerts}

Сделай:
1. Краткое резюме
2. Анализ рисков
3. Что изменилось логически
4. 1–2 спокойных наблюдения

Стиль: кратко, без инвестиционных рекомендаций.
"""

    res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )

    return res.choices[0].message.content

def send(text, chart_path=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    requests.post(url, data={"chat_id": CHAT_ID, "text": text})

    if chart_path:
        with open(chart_path, "rb") as f:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto",
                data={"chat_id": CHAT_ID},
                files={"photo": f}
            )

def main():
    portfolio = load_portfolio()
    fx = get_fx()
    crypto = get_crypto_prices()

    stock_list = [x["name"] for x in portfolio if x["asset_type"] == "stock"]
    stocks = get_stock_prices(stock_list)

    total, breakdown = calculate(portfolio, fx, crypto, stocks)

    alerts = risk_alerts(portfolio)

    report = ai_report(total, breakdown, alerts)

    save_history(total)

    chart = make_chart()

    send(report, chart)

if __name__ == "__main__":
    main()