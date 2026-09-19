"""Daily ruble exchange-rate post - USD/EUR/CNY, live from MOEX (biржевые
котировки, not the once-a-day CBR fix). See market_data.py."""

import os

from main import signature_message
from market_data import GREETING, build_currency_section, is_trading_day_msk
from telegram_post import send_message

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]


def build_message():
    lines = build_currency_section()
    if not lines:
        return None
    parts = [signature_message(), GREETING, "\n".join(lines)]
    parts.append("<i>Данные: MOEX · это не инвестиционная рекомендация</i>")
    return "\n\n".join(parts).strip()


def main():
    if not is_trading_day_msk():
        print("Weekend - MOEX is closed, skipping post.")
        return
    message = build_message()
    if not message:
        print("Currency section unavailable, skipping post.")
        return
    send_message(BOT_TOKEN, CHAT_ID, message)
    print("Posted currency update.")


if __name__ == "__main__":
    main()
