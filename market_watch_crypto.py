"""Intraday anomaly watch for Bitcoin/Ethereum - runs every 2 hours, 24/7
(crypto never closes), and posts an alert immediately, outside the normal
digest schedule, whenever either one moves >=3% since the last alert (or
since this watcher first saw it). Other coins aren't watched here - only
BTC/ETH are liquid and significant enough that a sudden double-digit move
is itself the news; smaller coins swing 3%+ routinely and belong in the
daily digest's top-movers list, not an interrupt."""

import os

from main import signature_message
from market_data import arrow, fetch_coin_price
from telegram_post import send_message
from watch_state import check_threshold, load_state, save_state

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

STATE_FILE = "data/market_watch_crypto_state.json"

WATCHED = (("bitcoin", "Bitcoin"), ("ethereum", "Ethereum"))
THRESHOLD_PCT = 3.0


def check_all(state):
    alerts = []
    for coin_id, label in WATCHED:
        try:
            result = fetch_coin_price(coin_id)
        except Exception as e:
            print(f"Price fetch for {label} failed: {e}")
            continue
        if not result:
            continue
        price, _ = result
        pct = check_threshold(state, coin_id, price, THRESHOLD_PCT)
        if pct is not None:
            alerts.append(f"{arrow(pct)} #{label} {pct:+.1f}% с прошлой проверки, сейчас ~${price:,.0f}")
    return alerts


def main():
    state = load_state(STATE_FILE)
    alerts = check_all(state)
    save_state(STATE_FILE, state)

    if not alerts:
        print("No crypto anomalies this check.")
        return

    message = "\n\n".join([
        signature_message(),
        "⚡️ <b>Резкое движение</b>",
        "\n".join(alerts),
        "<i>Данные: CoinGecko · это не инвестиционная рекомендация</i>",
    ]).strip()
    send_message(BOT_TOKEN, CHAT_ID, message)
    print(f"Posted crypto anomaly alert: {len(alerts)} instrument(s).")


if __name__ == "__main__":
    main()
