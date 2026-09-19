"""Posts a daily market snapshot pulled live from several public APIs -
crypto (CoinGecko), the ruble and precious metals (Bank of Russia, CBR),
US/RU stock indices (Stooq, MOEX ISS), and stock movers worldwide/Russia
(Financial Modeling Prep, MOEX ISS).

Every number comes straight from its API response - nothing here is
generated or paraphrased, so there's nothing to invent or misattribute.
Purely informational, like the rest of the channel: a % move is a fact,
not a recommendation, so this never suggests buying/selling anything.

Each section is independent and fails on its own (logged, not raised) -
one API being down (most likely MOEX or FMP) shouldn't take down the
whole post, it should just be a shorter post that day."""

import os
import urllib.request
from datetime import datetime, timedelta
from xml.etree import ElementTree

import requests

from main import signature_message
from telegram_post import send_message

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

# Optional - world (non-Russian) stock gainers/losers are skipped without
# it. Free tier at financialmodelingprep.com covers this comfortably (one
# request per side, once a day).
FMP_API_KEY = os.environ.get("FMP_API_KEY")

MOVERS_COUNT = 3


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


# ---------------------------------------------------------------- Crypto --

COINGECKO_GLOBAL_URL = "https://api.coingecko.com/api/v3/global"
COINGECKO_CATEGORIES_URL = "https://api.coingecko.com/api/v3/coins/categories"
COINGECKO_MARKETS_URL = "https://api.coingecko.com/api/v3/coins/markets"

# Ranked among the top MARKETS_POOL coins by market cap, so gainers/losers
# are liquid, real coins - not a micro-cap that moved 400% on $200 of volume.
MARKETS_POOL = 100


def fetch_global():
    resp = requests.get(COINGECKO_GLOBAL_URL, timeout=15)
    resp.raise_for_status()
    data = resp.json()["data"]
    return {
        "market_cap_usd": data["total_market_cap"]["usd"],
        "btc_dominance": data["market_cap_percentage"]["btc"],
    }


def fetch_defi_market_cap():
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


def top_movers(items, key, count=MOVERS_COUNT):
    ranked = sorted(items, key=key, reverse=True)
    gainers = ranked[:count]
    losers = ranked[-count:][::-1] if len(ranked) >= count else []
    return gainers, losers


def build_crypto_section():
    lines = []
    try:
        glob = fetch_global()
        markets = fetch_markets()
        btc_cap = glob["market_cap_usd"] * glob["btc_dominance"] / 100
        altcoin_cap = glob["market_cap_usd"] - btc_cap
        defi_cap = fetch_defi_market_cap()

        lines.append("Капитализация рынка: " + format_usd(glob["market_cap_usd"]))
        lines.append("Капитализация альткоинов: " + format_usd(altcoin_cap))
        if defi_cap:
            lines.append("Капитализация #DeFi: " + format_usd(defi_cap))
        lines.append(f"Доминация #Bitcoin: {glob['btc_dominance']:.1f}%")

        btc = next((m for m in markets if m["id"] == "bitcoin"), None)
        eth = next((m for m in markets if m["id"] == "ethereum"), None)
        if btc or eth:
            lines.append("")
            lines.append("💰 <b>Курсы криптовалют</b>")
            if btc:
                lines.append(f"#Bitcoin ~ {format_price(btc['current_price'])}")
            if eth:
                lines.append(f"#Ethereum ~ {format_price(eth['current_price'])}")

        gainers, losers = top_movers(markets, key=lambda m: m["price_change_percentage_24h"])
        if gainers:
            lines.append("")
            lines.append("📈 <b>Лидеры роста крипты за сутки</b>")
            for m in gainers:
                lines.append(f"#{m['symbol'].upper()} {m['price_change_percentage_24h']:+.1f}%")
        if losers:
            lines.append("")
            lines.append("📉 <b>Лидеры падения крипты за сутки</b>")
            for m in losers:
                lines.append(f"#{m['symbol'].upper()} {m['price_change_percentage_24h']:+.1f}%")
    except Exception as e:
        print(f"Crypto section failed: {e}")
        return []
    return lines


# ------------------------------------------------------- Ruble & metals --

CBR_CURRENCY_URL = "https://www.cbr.ru/scripts/XML_daily.asp"
CBR_METALS_URL = "https://www.cbr.ru/scripts/xml_metall.asp"

CURRENCIES = (("USD", "USD"), ("EUR", "EUR"), ("CNY", "CNY"))
METALS = {"1": "Золото", "2": "Серебро", "3": "Платина", "4": "Палладий"}


def fetch_cbr_currency_rates():
    """Returns {char_code: rub_per_unit}, e.g. {"USD": 92.34} - official
    Bank of Russia daily rates, the figure Russian media actually cites."""
    resp = requests.get(CBR_CURRENCY_URL, timeout=15)
    resp.raise_for_status()
    root = ElementTree.fromstring(resp.content)
    rates = {}
    for valute in root.findall("Valute"):
        char_code = valute.findtext("CharCode")
        nominal = float(valute.findtext("Nominal").replace(",", "."))
        value = float(valute.findtext("Value").replace(",", "."))
        rates[char_code] = value / nominal
    return rates


def fetch_cbr_metal_prices():
    """Returns {code: rub_per_gram} for the latest available business day
    (Au=1, Ag=2, Pt=3, Pd=4) - CBR only publishes on business days, so a
    single-day lookup can come back empty on a Monday after a holiday
    weekend; request a window and keep the latest record per metal."""
    today = datetime.now()
    date_from = (today - timedelta(days=7)).strftime("%d/%m/%Y")
    date_to = today.strftime("%d/%m/%Y")
    resp = requests.get(
        CBR_METALS_URL, params={"date_req1": date_from, "date_req2": date_to}, timeout=15
    )
    resp.raise_for_status()
    root = ElementTree.fromstring(resp.content)

    latest = {}
    for record in root.findall("Record"):
        code = record.get("Code")
        date = datetime.strptime(record.get("Date"), "%d.%m.%Y")
        price = float(record.findtext("Buy").replace(",", "."))
        if code not in latest or date > latest[code][0]:
            latest[code] = (date, price)
    return {code: price for code, (_, price) in latest.items()}


def build_ruble_section():
    try:
        rates = fetch_cbr_currency_rates()
        lines = ["💵 <b>Курс рубля</b> (ЦБ РФ)"]
        for code, label in CURRENCIES:
            if code in rates:
                lines.append(f"{label} ~ {rates[code]:.2f} ₽")
        return lines if len(lines) > 1 else []
    except Exception as e:
        print(f"Ruble rates section failed: {e}")
        return []


def build_metals_section():
    try:
        prices = fetch_cbr_metal_prices()
        lines = ["🥇 <b>Металлы</b> (ЦБ РФ, за грамм)"]
        for code, label in METALS.items():
            if code in prices:
                lines.append(f"{label} ~ {prices[code]:,.0f} ₽")
        return lines if len(lines) > 1 else []
    except Exception as e:
        print(f"Metals section failed: {e}")
        return []


# ---------------------------------------------------------------- Indices --

STOOQ_DAILY_URL = "https://stooq.com/q/d/l/"
US_INDICES = (("^spx", "S&P 500"), ("^dji", "Dow Jones"), ("^ndq", "Nasdaq"))

MOEX_INDEX_URL = "https://iss.moex.com/iss/engines/stock/markets/index/securities/{id}.json"
RU_INDICES = (("IMOEX", "IMOEX"), ("RTSI", "RTS"))


def fetch_stooq_change(symbol):
    """Returns (last_close, pct_change_vs_prior_close) from Stooq's daily
    history CSV, or None if there isn't enough history in the response.

    Uses urllib directly instead of requests - requests always re-quotes
    the URL through its own normalization (requote_uri), which percent-
    encodes '^' to %5E regardless of whether it came from a params= dict
    or a literal f-string; confirmed live, both 404 the same way against
    Stooq's endpoint. urllib.request sends the URL as given, so the raw
    '^' Stooq actually expects reaches it unchanged."""
    req = urllib.request.Request(f"{STOOQ_DAILY_URL}?s={symbol}&i=d", headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        text = resp.read().decode("utf-8")
    rows = [r for r in text.strip().splitlines() if r and not r.startswith("Date")]
    if len(rows) < 2:
        return None
    prev_close = float(rows[-2].split(",")[4])
    last_close = float(rows[-1].split(",")[4])
    pct = (last_close - prev_close) / prev_close * 100 if prev_close else 0
    return last_close, pct


def _iss_row_dict(table):
    """MOEX ISS returns {"columns": [...], "data": [[...], ...]} - zip the
    first data row up with the column names into a lookup dict."""
    if not table.get("data"):
        return {}
    return dict(zip(table["columns"], table["data"][0]))


def fetch_moex_index(index_id):
    resp = requests.get(MOEX_INDEX_URL.format(id=index_id), timeout=15)
    resp.raise_for_status()
    marketdata = _iss_row_dict(resp.json()["marketdata"])
    last = next((marketdata[k] for k in ("LASTVALUE", "CURRENTVALUE", "LAST") if marketdata.get(k) is not None), None)
    pct = marketdata.get("LASTTOPREVPRICE")
    if last is None:
        return None
    return last, pct


def build_indices_section():
    lines = []
    for symbol, label in US_INDICES:
        try:
            result = fetch_stooq_change(symbol)
            if result:
                value, pct = result
                lines.append(f"{label} ~ {value:,.0f} ({pct:+.1f}%)")
        except Exception as e:
            print(f"Index {label} (Stooq) failed: {e}")

    for index_id, label in RU_INDICES:
        try:
            result = fetch_moex_index(index_id)
            if result:
                value, pct = result
                pct_text = f" ({pct:+.1f}%)" if pct is not None else ""
                lines.append(f"{label} ~ {value:,.0f}{pct_text}")
        except Exception as e:
            print(f"Index {label} (MOEX) failed: {e}")

    return ["📊 <b>Индексы</b>"] + lines if lines else []


# --------------------------------------------------------- Stock movers --

FMP_GAINERS_URL = "https://financialmodelingprep.com/api/v3/stock_market/gainers"
FMP_LOSERS_URL = "https://financialmodelingprep.com/api/v3/stock_market/losers"


def fetch_fmp_movers(url, count=MOVERS_COUNT):
    resp = requests.get(url, params={"apikey": FMP_API_KEY}, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    ranked = sorted(data, key=lambda m: m.get("changesPercentage", 0), reverse=(url == FMP_GAINERS_URL))
    return ranked[:count]


def build_world_stocks_section():
    if not FMP_API_KEY:
        return []
    lines = []
    try:
        gainers = fetch_fmp_movers(FMP_GAINERS_URL)
        if gainers:
            lines.append("📈 <b>Лидеры роста акций (мир)</b>")
            for m in gainers:
                lines.append(f"#{m['symbol']} {m['changesPercentage']:+.1f}%")
    except Exception as e:
        print(f"World stock gainers failed: {e}")
    try:
        losers = fetch_fmp_movers(FMP_LOSERS_URL)
        if losers:
            lines.append("")
            lines.append("📉 <b>Лидеры падения акций (мир)</b>")
            for m in losers:
                lines.append(f"#{m['symbol']} {m['changesPercentage']:+.1f}%")
    except Exception as e:
        print(f"World stock losers failed: {e}")
    return lines


MOEX_SHARES_URL = "https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities.json"


def fetch_moex_stock_movers(count=MOVERS_COUNT):
    resp = requests.get(MOEX_SHARES_URL, params={"iss.meta": "off"}, timeout=15)
    resp.raise_for_status()
    payload = resp.json()

    securities_table = payload["securities"]
    sec_cols = securities_table["columns"]
    secid_idx = sec_cols.index("SECID")
    shortname_idx = sec_cols.index("SHORTNAME") if "SHORTNAME" in sec_cols else secid_idx
    names = {row[secid_idx]: row[shortname_idx] for row in securities_table["data"]}

    market_table = payload["marketdata"]
    m_cols = market_table["columns"]
    m_secid_idx = m_cols.index("SECID")
    pct_idx = m_cols.index("LASTTOPREVPRICE") if "LASTTOPREVPRICE" in m_cols else None
    if pct_idx is None:
        return [], []

    movers = [
        {"secid": row[m_secid_idx], "name": names.get(row[m_secid_idx], row[m_secid_idx]), "pct": row[pct_idx]}
        for row in market_table["data"]
        if row[pct_idx] is not None
    ]
    gainers, losers = top_movers(movers, key=lambda m: m["pct"], count=count)
    return gainers, losers


def build_ru_stocks_section():
    try:
        gainers, losers = fetch_moex_stock_movers()
        lines = []
        if gainers:
            lines.append("📈 <b>Лидеры роста акций (Россия)</b>")
            for m in gainers:
                lines.append(f"#{m['secid']} {m['pct']:+.1f}%")
        if losers:
            lines.append("")
            lines.append("📉 <b>Лидеры падения акций (Россия)</b>")
            for m in losers:
                lines.append(f"#{m['secid']} {m['pct']:+.1f}%")
        return lines
    except Exception as e:
        print(f"Russian stock movers failed: {e}")
        return []


# ------------------------------------------------------------------ Post --


def _add_section(parts, lines):
    if lines:
        parts.append("\n".join(lines))


def build_overview_message():
    parts = [signature_message(), "🌐 <b>Обзор рынка</b>"]

    _add_section(parts, build_crypto_section())
    _add_section(parts, build_ruble_section())
    _add_section(parts, build_metals_section())
    _add_section(parts, build_indices_section())
    _add_section(parts, build_world_stocks_section())
    _add_section(parts, build_ru_stocks_section())

    sources = ["CoinGecko", "ЦБ РФ", "Stooq", "MOEX"]
    if FMP_API_KEY:
        sources.append("Financial Modeling Prep")
    parts.append(f"<i>Данные: {', '.join(sources)} · это не инвестиционная рекомендация</i>")

    return "\n\n".join(parts).strip()


def main():
    message = build_overview_message()
    send_message(BOT_TOKEN, CHAT_ID, message)
    print("Posted market overview.")


if __name__ == "__main__":
    main()
