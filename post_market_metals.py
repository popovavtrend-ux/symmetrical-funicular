"""Daily precious metals post - gold/silver live from MOEX, platinum/
palladium on the Bank of Russia's daily fix (no free live-traded source
found for those two). See market_data.py."""

import os

from main import signature_message
from market_data import build_metals_section
from telegram_post import send_message

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]


def build_message():
    lines = build_metals_section()
    if not lines:
        return None
    parts = [signature_message(), "\n".join(lines)]
    parts.append("<i>Данные: MOEX, ЦБ РФ · это не инвестиционная рекомендация</i>")
    return "\n\n".join(parts).strip()


def main():
    message = build_message()
    if not message:
        print("Metals section unavailable, skipping post.")
        return
    send_message(BOT_TOKEN, CHAT_ID, message)
    print("Posted metals update.")


if __name__ == "__main__":
    main()
