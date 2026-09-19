"""Daily crypto market post - market cap, BTC/ETH prices, top gainers/losers.
Pulled live from CoinGecko, no API key needed. See market_data.py for the
actual fetching/formatting logic shared with the other market posts."""

import os

from main import signature_message
from market_data import build_crypto_section
from telegram_post import send_message

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]


def build_message():
    parts = [signature_message(), "💰 <b>Крипторынок</b>"]
    lines = build_crypto_section()
    if not lines:
        return None
    parts.append("\n".join(lines))
    parts.append("<i>Данные: CoinGecko · это не инвестиционная рекомендация</i>")
    return "\n\n".join(parts).strip()


def main():
    message = build_message()
    if not message:
        print("Crypto section unavailable, skipping post.")
        return
    send_message(BOT_TOKEN, CHAT_ID, message)
    print("Posted crypto market update.")


if __name__ == "__main__":
    main()
