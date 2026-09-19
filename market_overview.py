"""Posts a daily market snapshot (global cap, BTC dominance, top gainers/
losers) pulled live from CoinGecko - pure numbers, not a story, so it has
nothing to attribute and nothing to accidentally invent: the whole post is
built directly from the API response.

Purely informational, like the rest of the channel - a % move is a fact,
not a recommendation, so this never suggests buying/selling anything."""

import os

import requests

from main import signature_message
from telegram_post import send_message

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

COINGECKO_GLOBAL_URL = "https://api.coingecko.com/api/v3/global"
COINGECKO_CATEGORIES_URL = "https://api.coingecko.com/api/v3/coins/categories"
COINGECKO_MARKETS_URL = "https://api.coingecko.com/api/v3/coins/markets"

# Ranked among the top MARKETS_POOL coins by market cap, so gainers/losers
# are liquid, real coins - not a micro-cap that moved 400% on $200 of volume.
MARKETS_POOL = 100
MOVERS_COUNT = 3


def fetch_global():
    resp = requests.get(COINGECKO_GLOBAL_URL, timeout=15)
    resp.raise_for_status()
    data = resp.json()["data"]
    return {
        "market_cap_usd": data["total_market_cap"]["usd"],
        "btc_dominance": data["market_cap_percentage"]["btc"],
    }


def fetch_defi_market_cap():
    """Returns the DeFi sector's total market cap in USD, or None if the
    category lookup fails - this stat is a nice-to-have, not core to the
    post, so a failure here shouldn't take down the whole overview."""
    try:
        resp = requests.get(COINGECKO_CATEGORIES_URL, timeout=15)
        resp.raise_for_status()
        for category in resp.json():
            if category.get("id") == "decentralized-finance-defi":
                return category.get("market_cap")
    except Exception as e:
        print(f"DeFi market cap lookup failed: {e}")
    return None


def fetch_markets(vs_currency="usd", per_page=MARKETS_POOL):
    resp = requests.get(
        COINGECKO_MARKETS_URL,
        params={
            "vs_currency": vs_currency,
            "order": "market_cap_desc",
            "per_page": per_page,
            "page": 1,
            "price_change_percentage": "24h",
        },
        timeout=15,
    )
    resp.raise_for_status()
    return [m for m in resp.json() if m.get("price_change_percentage_24h") is not None]


def top_movers(markets, count=MOVERS_COUNT):
    ranked = sorted(markets, key=lambda m: m["price_change_percentage_24h"], reverse=True)
    gainers = ranked[:count]
    losers = ranked[-count:][::-1] if len(ranked) >= count else []
    return gainers, losers


def format_usd(value):
    if value >= 1_000_000_000_000:
        return f"${value / 1_000_000_000_000:.2f} трлн"
    if value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f} млрд"
    return f"${value:,.0f}"


def format_price(value):
    if value >= 1:
        return f"${value:,.2f}"
    return f"${value:.4f}"


def build_overview_message():
    glob = fetch_global()
    defi_cap = fetch_defi_market_cap()
    markets = fetch_markets()
    gainers, losers = top_movers(markets)

    btc = next((m for m in markets if m["id"] == "bitcoin"), None)
    eth = next((m for m in markets if m["id"] == "ethereum"), None)

    lines = [signature_message(), "🌐 <b>Обзор рынка</b>", ""]
    lines.append(f"Капитализация рынка: {format_usd(glob['market_cap_usd'])}")
    if defi_cap:
        lines.append(f"Капитализация #DeFi: {format_usd(defi_cap)}")
    lines.append(f"Доминация #Bitcoin: {glob['btc_dominance']:.1f}%")
    lines.append("")

    if btc or eth:
        lines.append("💰 <b>Курсы</b>")
        if btc:
            lines.append(f"#Bitcoin ~ {format_price(btc['current_price'])}")
        if eth:
            lines.append(f"#Ethereum ~ {format_price(eth['current_price'])}")
        lines.append("")

    if gainers:
        lines.append("📈 <b>Лидеры роста за сутки</b>")
        for m in gainers:
            lines.append(f"#{m['symbol'].upper()} {m['price_change_percentage_24h']:+.1f}%")
        lines.append("")

    if losers:
        lines.append("📉 <b>Лидеры падения за сутки</b>")
        for m in losers:
            lines.append(f"#{m['symbol'].upper()} {m['price_change_percentage_24h']:+.1f}%")
        lines.append("")

    lines.append("<i>Данные: CoinGecko · это не инвестиционная рекомендация</i>")

    return "\n".join(lines).strip()


def main():
    message = build_overview_message()
    send_message(BOT_TOKEN, CHAT_ID, message)
    print("Posted market overview.")


if __name__ == "__main__":
    main()
