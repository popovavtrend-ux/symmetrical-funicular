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
correctly, along with wasting a request."""

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
from telegram_post import send_message
from watch_state import check_threshold, load_state, save_state

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

STATE_FILE = "data/market_watch_traditional_state.json"

CURRENCY_THRESHOLD_PCT = 1.0
METAL_THRESHOLD_PCT = 2.0
INDEX_THRESHOLD_PCT = 1.5
STOCK_THRESHOLD_PCT = 5.0


def check_currency(state):
    alerts = []
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
            alerts.append(f"{arrow(pct)} {label}/RUB {pct:+.1f}% с прошлой проверки, сейчас {rate:.2f} ₽")
    return alerts


def check_metals(state):
    alerts = []
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
            alerts.append(f"{arrow(pct)} {label} {pct:+.1f}% с прошлой проверки, сейчас {rate:,.0f} ₽/г")
    return alerts


def check_ru_indices(state):
    alerts = []
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
            alerts.append(f"{arrow(pct)} {label} {pct:+.1f}% с прошлой проверки, сейчас {value:,.0f}")
    return alerts


def check_us_indices(state):
    alerts = []
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
            alerts.append(f"{arrow(pct)} {label} {pct:+.1f}% с прошлой проверки, сейчас {value:,.0f}")
    return alerts


def check_ru_stocks(state):
    alerts = []
    try:
        prices = fetch_all_moex_stock_prices()
    except Exception as e:
        print(f"RU stock prices failed: {e}")
        return alerts
    for secid, price in prices.items():
        pct = check_threshold(state, f"stock:{secid}", price, STOCK_THRESHOLD_PCT)
        if pct is not None:
            alerts.append(f"{arrow(pct)} #{secid} {pct:+.1f}% с прошлой проверки, сейчас {price:,.2f} ₽")
    return alerts


def main():
    state = load_state(STATE_FILE)
    alerts = []

    if moex_session_open():
        alerts += check_currency(state)
        alerts += check_metals(state)
        alerts += check_ru_indices(state)
        alerts += check_ru_stocks(state)
    else:
        print("MOEX session closed, skipping ruble/metals/RU indices/RU stocks.")

    if us_session_open():
        alerts += check_us_indices(state)
    else:
        print("US session closed, skipping US indices.")

    save_state(STATE_FILE, state)

    if not alerts:
        print("No anomalies this check.")
        return

    message = "\n\n".join([
        signature_message(),
        "⚡️ <b>Резкое движение</b>",
        "\n".join(alerts),
        "<i>Данные: MOEX, Yahoo Finance · это не инвестиционная рекомендация</i>",
    ]).strip()
    send_message(BOT_TOKEN, CHAT_ID, message)
    print(f"Posted anomaly alert: {len(alerts)} instrument(s).")


if __name__ == "__main__":
    main()
