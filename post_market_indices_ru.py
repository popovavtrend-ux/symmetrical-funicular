"""Daily Russian indices post - IMOEX, RTS, live from MOEX ISS. See
market_data.py."""

import os

from main import signature_message
from market_data import RU_INDICES, arrow, is_trading_day_msk, moex_quote
from telegram_post import send_message

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]


def build_section():
    lines = []
    for index_id, label in RU_INDICES:
        try:
            quote = moex_quote("stock", "index", index_id)
            if quote:
                value, pct = quote["price"], quote["pct"]
                if pct is None:
                    lines.append(f"{label} {value:,.0f}")
                else:
                    suffix = f", закрытие {quote['close_date']}" if quote["close_date"] else ""
                    lines.append(f"{arrow(pct)} {label} {value:,.0f} ({pct:+.1f}%{suffix})")
        except Exception as e:
            print(f"Index {label} (MOEX) failed: {e}")
    return ["📊 <b>Индексы (Россия)</b>"] + lines if lines else []


def build_message():
    lines = build_section()
    if not lines:
        return None
    parts = [signature_message(), "\n".join(lines)]
    parts.append("<i>Данные: MOEX · это не инвестиционная рекомендация</i>")
    return "\n\n".join(parts).strip()


def main():
    if not is_trading_day_msk():
        print("Weekend - MOEX is closed, skipping post.")
        return
    message = build_message()
    if not message:
        print("RU indices section unavailable, skipping post.")
        return
    send_message(BOT_TOKEN, CHAT_ID, message)
    print("Posted RU indices update.")


if __name__ == "__main__":
    main()
