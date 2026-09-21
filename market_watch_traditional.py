"""Intraday anomaly watch for everything that isn't crypto - currency,
gold/silver, world+RU indices, RU stocks. Runs every 2 hours during actual
trading hours only (see market_data.moex_session_open/us_session_open) and
posts an alert immediately, outside the normal digest schedule, whenever
an instrument moves past its category's threshold since the last alert
(or since this watcher first saw it):

- currency (USD/EUR/CNY vs RUB): 1%
- gold/silver: 2%
- indices (US and RU): 1.5%
- individual RU stocks (MOEX TQBR): 5%

World (non-Russian) stocks aren't watched here - the free Financial
Modeling Prep tier only exposes a top-movers list, not a per-ticker quote
endpoint we could track a running reference against, so that stays a
digest-only (post_market_stocks.py) feature.

Each category only runs during its own market's session - checking
US indices while Wall Street is closed, or the ruble while MOEX is shut,
would just compare a frozen closing price against itself and never fire
correctly, along with wasting a request.

Each alert also gets a one-line "why" lookup (move_explainer.py, web
search via Claude) - if nothing credible turns up yet, the alert still
posts on time without it, and the lookup is retried on the next couple of
runs until an explanation appears or we give up on it."""

import os

from main import signature_message
from market_data import (
    CURRENCY_INSTRUMENTS,
    METAL_INSTRUMENTS,
    RU_INDICES,
    US_INDICES,
    arrow,
    fetch_all_moex_stock_prices,
    fetch_currency_rate,
    fetch_metal_rate,
    fetch_moex_index,
    fetch_yahoo_index_change,
    moex_session_open,
    us_session_open,
)
from move_explainer import search_move_explanation
from telegram_post import send_message
from watch_state import add_pending, check_threshold, load_state, retry_pending, save_state

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

STATE_FILE = "data/market_watch_traditional_state.json"
PENDING_FILE = "data/market_watch_traditional_pending.json"

CURRENCY_THRESHOLD_PCT = 1.0
METAL_THRESHOLD_PCT = 2.0
INDEX_THRESHOLD_PCT = 1.5
STOCK_THRESHOLD_PCT = 5.0


def check_currency(state):
    moves = []
    for secid, label in CURRENCY_INSTRUMENTS:
        try:
            result = fetch_currency_rate(secid)
        except Exception as e:
            print(f"Currency {label} failed: {e}")
            continue
        if not result:
            continue
        rate, _, _ = result
        pct = check_threshold(state, f"currency:{secid}", rate, CURRENCY_THRESHOLD_PCT)
        if pct is not None:
            moves.append(
                {
                    "key": f"currency:{secid}",
                    "label": f"{label}/RUB",
                    "pct": pct,
                    "text": f"сейчас {rate:.2f} ₽",
                    "category": "валютная пара",
                }
            )
    return moves


def check_metals(state):
    moves = []
    for secid, label in METAL_INSTRUMENTS:
        try:
            result = fetch_metal_rate(secid)
        except Exception as e:
            print(f"Metal {label} failed: {e}")
            continue
        if not result:
            continue
        rate, _, _ = result
        pct = check_threshold(state, f"metal:{secid}", rate, METAL_THRESHOLD_PCT)
        if pct is not None:
            moves.append(
                {
                    "key": f"metal:{secid}",
                    "label": label,
                    "pct": pct,
                    "text": f"сейчас {rate:,.0f} ₽/г",
                    "category": "драгоценный металл",
                }
            )
    return moves


def check_ru_indices(state):
    moves = []
    for index_id, label in RU_INDICES:
        try:
            result = fetch_moex_index(index_id)
        except Exception as e:
            print(f"Index {label} (MOEX) failed: {e}")
            continue
        if not result:
            continue
        value, _ = result
        pct = check_threshold(state, f"index:{index_id}", value, INDEX_THRESHOLD_PCT)
        if pct is not None:
            moves.append(
                {
                    "key": f"index:{index_id}",
                    "label": label,
                    "pct": pct,
                    "text": f"сейчас {value:,.0f}",
                    "category": "биржевой индекс",
                }
            )
    return moves


def check_us_indices(state):
    moves = []
    for symbol, label in US_INDICES:
        try:
            result = fetch_yahoo_index_change(symbol)
        except Exception as e:
            print(f"Index {label} (Yahoo) failed: {e}")
            continue
        if not result:
            continue
        value, _ = result
        pct = check_threshold(state, f"index:{symbol}", value, INDEX_THRESHOLD_PCT)
        if pct is not None:
            moves.append(
                {
                    "key": f"index:{symbol}",
                    "label": label,
                    "pct": pct,
                    "text": f"сейчас {value:,.0f}",
                    "category": "биржевой индекс США",
                }
            )
    return moves


def check_ru_stocks(state):
    moves = []
    try:
        stocks = fetch_all_moex_stock_prices()
    except Exception as e:
        print(f"RU stock prices failed: {e}")
        return moves
    for secid, info in stocks.items():
        price = info["price"]
        pct = check_threshold(state, f"stock:{secid}", price, STOCK_THRESHOLD_PCT)
        if pct is not None:
            label = f"#{secid} ({info['name']})" if info["name"] != secid else f"#{secid}"
            moves.append(
                {
                    "key": f"stock:{secid}",
                    "label": label,
                    "pct": pct,
                    "text": f"сейчас {price:,.2f} ₽",
                    "category": f"акция {info['name']}" if info["name"] != secid else "акция",
                }
            )
    return moves


def _move_line(move, explanation=None):
    line = f"{arrow(move['pct'])} {move['label']} {move['pct']:+.1f}% с прошлой проверки, {move['text']}"
    return f"{line}\n{explanation}" if explanation else line


def main():
    state = load_state(STATE_FILE)
    pending = load_state(PENDING_FILE)
    moves = []

    if moex_session_open():
        moves += check_currency(state)
        moves += check_metals(state)
        moves += check_ru_indices(state)
        moves += check_ru_stocks(state)
    else:
        print("MOEX session closed, skipping ruble/metals/RU indices/RU stocks.")

    if us_session_open():
        moves += check_us_indices(state)
    else:
        print("US session closed, skipping US indices.")

    save_state(STATE_FILE, state)

    lines = []
    for move in moves:
        explanation = search_move_explanation(move["label"], move["pct"], move["category"])
        if explanation:
            lines.append(_move_line(move, explanation))
        else:
            lines.append(_move_line(move))
            add_pending(pending, move["key"], move["label"], move["pct"], move["category"])

    resolved = retry_pending(pending, search_move_explanation)
    save_state(PENDING_FILE, pending)

    if lines:
        message = "\n\n".join([
            signature_message(),
            "⚡️ <b>Резкое движение</b>",
            "\n\n".join(lines),
            "<i>Данные: MOEX, Yahoo Finance · это не инвестиционная рекомендация</i>",
        ]).strip()
        send_message(BOT_TOKEN, CHAT_ID, message)
        print(f"Posted anomaly alert: {len(lines)} instrument(s).")
    else:
        print("No anomalies this check.")

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
