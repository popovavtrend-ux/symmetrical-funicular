"""Renders a real price chart for a news headline's coin, pulled from
CoinGecko's public market data - so a post about a price move shows the
actual price move, instead of an illustrative stock photo that only looks
like a chart."""

import io
from datetime import datetime, timezone

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import requests

COINGECKO_MARKET_CHART_URL = "https://api.coingecko.com/api/v3/coins/{id}/market_chart"

# Keyword (English, or transliterated Russian for the RU-language feeds) ->
# (CoinGecko coin id, ticker symbol). Only specific, named coins - a generic
# mention of "crypto"/"blockchain"/"defi"/"nft" has no single price to chart.
COIN_KEYWORDS = {
    "bitcoin": ("bitcoin", "BTC"),
    "биткоин": ("bitcoin", "BTC"),
    "биткойн": ("bitcoin", "BTC"),
    "ethereum": ("ethereum", "ETH"),
    "эфириум": ("ethereum", "ETH"),
    "solana": ("solana", "SOL"),
    "солана": ("solana", "SOL"),
    "ripple": ("ripple", "XRP"),
    "xrp": ("ripple", "XRP"),
    "dogecoin": ("dogecoin", "DOGE"),
    "cardano": ("cardano", "ADA"),
    "polkadot": ("polkadot", "DOT"),
    "litecoin": ("litecoin", "LTC"),
}


def guess_coin(title):
    lowered = title.lower()
    for keyword, coin in COIN_KEYWORDS.items():
        if keyword in lowered:
            return coin
    return None


def fetch_price_series(coin_id, days=7):
    resp = requests.get(
        COINGECKO_MARKET_CHART_URL.format(id=coin_id),
        params={"vs_currency": "usd", "days": days},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("prices") or []  # [[timestamp_ms, price], ...]


def render_price_chart(symbol, prices):
    if not prices:
        return None

    dates = [datetime.fromtimestamp(p[0] / 1000, tz=timezone.utc) for p in prices]
    values = [p[1] for p in prices]
    current = values[-1]
    change_pct = (values[-1] - values[0]) / values[0] * 100 if values[0] else 0
    color = "#16c784" if change_pct >= 0 else "#ea3943"

    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=150)
    ax.plot(dates, values, color=color, linewidth=2)
    ax.fill_between(dates, values, min(values), color=color, alpha=0.08)
    ax.set_title(
        f"{symbol}/USD  ·  ${current:,.2f}  ({change_pct:+.1f}% за 7 дней)",
        fontsize=13,
        fontweight="bold",
        loc="left",
    )
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    ax.grid(True, alpha=0.15)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()


def generate_price_chart(title, days=7):
    """Returns PNG bytes for the named coin's real price chart, or None if
    no specific coin was named in the title, or the chart couldn't be built
    (network error, bad data, unlisted coin id, etc.) - the caller should
    fall back to a stock photo in that case."""
    coin = guess_coin(title)
    if not coin:
        return None
    coin_id, symbol = coin
    try:
        prices = fetch_price_series(coin_id, days=days)
        return render_price_chart(symbol, prices)
    except Exception as e:
        print(f"Price chart failed for {coin_id!r}: {e}")
        return None
