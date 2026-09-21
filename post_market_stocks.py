"""Daily stock movers post - top gainers/losers, Russia (MOEX ISS, no key)
and world (Financial Modeling Prep, optional FMP_API_KEY). See
market_data.py."""

import os

from main import signature_message
from market_data import FMP_API_KEY, build_stocks_section, is_trading_day_msk
from telegram_post import send_message

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]


def build_message():
    lines = build_stocks_section()
    if not lines:
        return None
    parts = [signature_message(), "📈 <b>Акции</b>", "\n".join(lines)]
    sources = ["MOEX"]
    if FMP_API_KEY:
        sources.append("Financial Modeling Prep")
    parts.append(f"<i>Данные: {', '.join(sources)} · это не инвестиционная рекомендация</i>")
    return "\n\n".join(parts).strip()


def main():
    if not is_trading_day_msk():
        print("Weekend - markets are closed, skipping post.")
        return
    message = build_message()
    if not message:
        print("Stocks section unavailable, skipping post.")
        return
    send_message(BOT_TOKEN, CHAT_ID, message)
    print("Posted stock movers update.")


if __name__ == "__main__":
    main()
