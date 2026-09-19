"""Daily world indices post - S&P 500, Dow Jones, Nasdaq, live from Yahoo
Finance. See market_data.py."""

import os

from main import signature_message
from market_data import GREETING, US_INDICES, arrow, fetch_yahoo_index_change, is_trading_day_msk
from telegram_post import send_message

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]


def build_section():
    lines = []
    for symbol, label in US_INDICES:
        try:
            result = fetch_yahoo_index_change(symbol)
            if result:
                value, pct = result
                lines.append(f"{arrow(pct)} {label} {value:,.0f} ({pct:+.1f}%)")
        except Exception as e:
            print(f"Index {label} (Yahoo) failed: {e}")
    return ["📊 <b>Индексы (мир)</b>"] + lines if lines else []


def build_message():
    lines = build_section()
    if not lines:
        return None
    parts = [signature_message(), GREETING, "\n".join(lines)]
    parts.append("<i>Данные: Yahoo Finance · это не инвестиционная рекомендация</i>")
    return "\n\n".join(parts).strip()


def main():
    if not is_trading_day_msk():
        print("Weekend - US markets are closed, skipping post.")
        return
    message = build_message()
    if not message:
        print("World indices section unavailable, skipping post.")
        return
    send_message(BOT_TOKEN, CHAT_ID, message)
    print("Posted world indices update.")


if __name__ == "__main__":
    main()
