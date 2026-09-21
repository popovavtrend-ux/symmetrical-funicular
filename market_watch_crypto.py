"""Intraday anomaly watch for Bitcoin/Ethereum - runs every 2 hours, 24/7
(crypto never closes), and posts an alert immediately, outside the normal
digest schedule, whenever either one moves >=3% since the last alert (or
since this watcher first saw it). Other coins aren't watched here - only
BTC/ETH are liquid and significant enough that a sudden double-digit move
is itself the news; smaller coins swing 3%+ routinely and belong in the
daily digest's top-movers list, not an interrupt.

Each alert also gets a one-line "why" lookup (move_explainer.py, web
search via Claude) - if nothing credible turns up yet, the alert still
posts on time without it, and the lookup is retried on the next couple of
runs until an explanation appears or we give up on it."""

import os

from main import signature_message
from market_data import arrow, fetch_coin_price
from move_explainer import search_move_explanation
from telegram_post import send_message
from watch_state import add_pending, check_threshold, load_state, retry_pending, save_state

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

STATE_FILE = "data/market_watch_crypto_state.json"
PENDING_FILE = "data/market_watch_crypto_pending.json"

WATCHED = (("bitcoin", "Bitcoin"), ("ethereum", "Ethereum"))
THRESHOLD_PCT = 3.0
CATEGORY = "криптовалюта"


def check_all(state):
    moves = []
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
            moves.append({"key": coin_id, "label": f"#{label}", "pct": pct, "price": price})
    return moves


def _move_line(move, explanation=None):
    line = f"{arrow(move['pct'])} {move['label']} {move['pct']:+.1f}% с прошлой проверки, сейчас ~${move['price']:,.0f}"
    return f"{line}\n{explanation}" if explanation else line


def main():
    state = load_state(STATE_FILE)
    pending = load_state(PENDING_FILE)

    moves = check_all(state)
    save_state(STATE_FILE, state)

    lines = []
    for move in moves:
        explanation = search_move_explanation(move["label"], move["pct"], CATEGORY)
        if explanation:
            lines.append(_move_line(move, explanation))
        else:
            lines.append(_move_line(move))
            add_pending(pending, move["key"], move["label"], move["pct"], CATEGORY)

    resolved = retry_pending(pending, search_move_explanation)
    save_state(PENDING_FILE, pending)

    if lines:
        message = "\n\n".join([
            signature_message(),
            "⚡️ <b>Резкое движение</b>",
            "\n\n".join(lines),
            "<i>Данные: CoinGecko · это не инвестиционная рекомендация</i>",
        ]).strip()
        send_message(BOT_TOKEN, CHAT_ID, message)
        print(f"Posted crypto anomaly alert: {len(lines)} instrument(s).")
    else:
        print("No crypto anomalies this check.")

    if resolved:
        follow_up_lines = [f"{entry['label']} {entry['pct']:+.1f}%\n{explanation}" for entry, explanation in resolved]
        message = "\n\n".join([
            signature_message(),
            "🔍 <b>Что случилось: обновление по ранним алертам</b>",
            "\n\n".join(follow_up_lines),
        ]).strip()
        send_message(BOT_TOKEN, CHAT_ID, message)
        print(f"Posted follow-up explanation(s): {len(resolved)}.")


if __name__ == "__main__":
    main()
