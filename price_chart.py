"""Renders a real price chart for a news headline's coin, pulled from
CoinGecko's public market data - so a post about a price move shows the
actual price move, instead of an illustrative stock photo that only looks
like a chart."""

import io
import os
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
# Used two ways: as the ANTHROPIC_API_KEY-less fallback (substring match on
# the title alone), and as the lookup table for the ticker guess_coin_ticker
# below identifies from actually reading the story.
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

# Ticker symbol -> (CoinGecko coin id, ticker symbol), for looking up the
# coin Claude identifies as the story's actual subject (see
# guess_coin_ticker). Much wider than COIN_KEYWORDS above, since a ticker
# is unambiguous where a substring keyword isn't - no risk of e.g. "SOL"
# matching inside an unrelated word the way loose substrings can.
TICKER_TO_COIN = {
    "BTC": ("bitcoin", "BTC"),
    "ETH": ("ethereum", "ETH"),
    "SOL": ("solana", "SOL"),
    "XRP": ("ripple", "XRP"),
    "DOGE": ("dogecoin", "DOGE"),
    "ADA": ("cardano", "ADA"),
    "DOT": ("polkadot", "DOT"),
    "LTC": ("litecoin", "LTC"),
    "ARB": ("arbitrum", "ARB"),
    "OP": ("optimism", "OP"),
    "AVAX": ("avalanche-2", "AVAX"),
    "LINK": ("chainlink", "LINK"),
    "MATIC": ("matic-network", "MATIC"),
    "POL": ("matic-network", "POL"),
    "TON": ("the-open-network", "TON"),
    "SHIB": ("shiba-inu", "SHIB"),
    "SUI": ("sui", "SUI"),
    "APT": ("aptos", "APT"),
    "BNB": ("binancecoin", "BNB"),
    "TRX": ("tron", "TRX"),
    "NEAR": ("near", "NEAR"),
    "ATOM": ("cosmos", "ATOM"),
    "UNI": ("uniswap", "UNI"),
    "ICP": ("internet-computer", "ICP"),
    "FIL": ("filecoin", "FIL"),
    "ETC": ("ethereum-classic", "ETC"),
    "XLM": ("stellar", "XLM"),
    "HBAR": ("hedera-hashgraph", "HBAR"),
    "INJ": ("injective-protocol", "INJ"),
    "PEPE": ("pepe", "PEPE"),
    "SEI": ("sei-network", "SEI"),
    "TIA": ("celestia", "TIA"),
    "AAVE": ("aave", "AAVE"),
    "MKR": ("maker", "MKR"),
    "LDO": ("lido-dao", "LDO"),
    "CRV": ("curve-dao-token", "CRV"),
    "GRT": ("the-graph", "GRT"),
    "ALGO": ("algorand", "ALGO"),
    "VET": ("vechain", "VET"),
    "FTM": ("fantom", "FTM"),
    "THETA": ("theta-token", "THETA"),
    "XMR": ("monero", "XMR"),
    "EOS": ("eos", "EOS"),
    "CHZ": ("chiliz", "CHZ"),
    "SAND": ("the-sandbox", "SAND"),
    "MANA": ("decentraland", "MANA"),
    "AXS": ("axie-infinity", "AXS"),
    "GALA": ("gala", "GALA"),
    "IMX": ("immutable-x", "IMX"),
    "RUNE": ("thorchain", "RUNE"),
    "KAS": ("kaspa", "KAS"),
    "PYTH": ("pyth-network", "PYTH"),
    "JUP": ("jupiter-exchange-solana", "JUP"),
    "ENA": ("ethena", "ENA"),
    "ONDO": ("ondo-finance", "ONDO"),
    "BONK": ("bonk", "BONK"),
    "WIF": ("dogwifcoin", "WIF"),
}


def guess_coin(title):
    """Fallback for when there's no ANTHROPIC_API_KEY (or the content-based
    guess below found nothing usable): substring match on the title alone,
    in a fixed keyword order - keep in mind this can't tell a story's real
    subject from a coin it only mentions in passing."""
    lowered = title.lower()
    for keyword, coin in COIN_KEYWORDS.items():
        if keyword in lowered:
            return coin
    return None


def guess_coin_ticker(title, summary):
    """Read the actual story and ask Claude which single coin it's really
    about, as opposed to guess_coin()'s plain substring match, which picks
    up any coin mentioned anywhere - including in a passing comparison
    ("altcoins rose alongside Bitcoin") that isn't the story's subject at
    all. Returns a (coingecko_id, ticker) pair, or None if the story isn't
    primarily about one specific coin's price, or names one outside
    TICKER_TO_COIN."""
    from anthropic_client import create_message, extract_text, get_client

    try:
        client = get_client()
        prompt = (
            "Read this crypto news story. Is it primarily about one "
            "specific cryptocurrency's price, token, or protocol - as "
            "opposed to crypto/regulation/the market in general, or "
            "mentioning a coin only in passing (e.g. as a market-context "
            "comparison)? If yes, reply with just that coin's ticker "
            "symbol in capitals (e.g. BTC, ETH, ARB). If no single coin "
            "is the actual subject, reply with just NONE.\n\n"
            f"Title: {title}\n"
            f"Summary: {summary}"
        )
        resp = create_message(client, max_tokens=20, messages=[{"role": "user", "content": prompt}])
        ticker = extract_text(resp).strip().upper()
        return TICKER_TO_COIN.get(ticker)
    except Exception as e:
        print(f"Content-based coin identification failed: {e}")
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


def generate_price_chart(title, summary=None, days=7):
    """Returns PNG bytes for the named coin's real price chart, or None if
    no specific coin is actually the story's subject, or the chart couldn't
    be built (network error, bad data, unlisted coin id, etc.) - the caller
    should fall back to a stock photo in that case.

    Prefers reading the story (guess_coin_ticker) over the plain substring
    match (guess_coin) so a story that only mentions a coin in passing -
    e.g. an Arbitrum story that name-drops Bitcoin for market context -
    doesn't get charted as if it were about that other coin."""
    coin = None
    if summary and os.environ.get("ANTHROPIC_API_KEY"):
        coin = guess_coin_ticker(title, summary)
    if not coin:
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
