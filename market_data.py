"""Shared data-fetching for all market posts - the 6 daily digest posts
(crypto/currency/indices-world/indices-ru/stocks/metals) and the two
intraday anomaly watchers (crypto, traditional markets) all pull from the
same functions here, so a source or a formatting rule only needs fixing
in one place.

Every number comes straight from its API response - nothing here is
generated or paraphrased, so there's nothing to invent or misattribute.
Purely informational: a % move is a fact, not a recommendation, so this
never suggests buying/selling anything.

Each fetch function raises on failure - callers (digest section builders,
watchers) decide how to degrade: a digest section skips itself and logs,
a watcher just skips that instrument this tick."""

import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone
from xml.etree import ElementTree

import requests

MOVERS_COUNT = 3


def arrow(pct):
    """🟢/🔴 stand in for color, which Telegram's HTML mode can't render."""
    return "🟢" if pct >= 0 else "🔴"


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


def pct_from_prev(last, prev):
    return (last - prev) / prev * 100 if prev else 0


def delta_from_pct(last, pct):
    """Absolute change implied by (last, pct) alone, for sources that give
    a % move but not the raw previous value/absolute delta directly."""
    prev = last / (1 + pct / 100) if (1 + pct / 100) else last
    return last - prev


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
    resp = requests.get(COINGECKO_CATEGORIES_URL, timeout=15)
    resp.raise_for_status()
    for category in resp.json():
        if category.get("id") == "decentralized-finance-defi":
            return category.get("market_cap")
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


def fetch_coin_price(coin_id):
    """Single-coin price + 24h % change, for the crypto watcher - cheaper
    than pulling the top-100 list just to read off one coin."""
    markets = fetch_markets(per_page=250)
    coin = next((m for m in markets if m["id"] == coin_id), None)
    if not coin:
        return None
    return coin["current_price"], coin["price_change_percentage_24h"]


def top_movers(items, key, count=MOVERS_COUNT):
    ranked = sorted(items, key=key, reverse=True)
    gainers = ranked[:count]
    losers = ranked[-count:][::-1] if len(ranked) >= count else []
    return gainers, losers


def build_crypto_section():
    lines = []
    glob = fetch_global()
    markets = fetch_markets()
    btc_cap = glob["market_cap_usd"] * glob["btc_dominance"] / 100
    altcoin_cap = glob["market_cap_usd"] - btc_cap
    try:
        defi_cap = fetch_defi_market_cap()
    except Exception as e:
        print(f"DeFi market cap lookup failed: {e}")
        defi_cap = None

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
        for coin in (btc, eth):
            if coin:
                pct = coin["price_change_percentage_24h"]
                lines.append(f"{arrow(pct)} #{coin['symbol'].upper()} {format_price(coin['current_price'])} ({pct:+.1f}%)")

    gainers, losers = top_movers(markets, key=lambda m: m["price_change_percentage_24h"])
    if gainers:
        lines.append("")
        lines.append("📈 <b>Лидеры роста крипты за сутки</b>")
        for m in gainers:
            lines.append(f"🟢 #{m['symbol'].upper()} {m['price_change_percentage_24h']:+.1f}%")
    if losers:
        lines.append("")
        lines.append("📉 <b>Лидеры падения крипты за сутки</b>")
        for m in losers:
            lines.append(f"🔴 #{m['symbol'].upper()} {m['price_change_percentage_24h']:+.1f}%")
    return lines


# ------------------------------------------------------------- MOEX ISS --
# Shared helpers for every MOEX-sourced instrument: currency, gold/silver,
# indices, stocks. All go through the same {engine}/{market}/.../securities
# JSON shape - one row per instrument, columns given separately.

MOEX_SECURITY_URL = "https://iss.moex.com/iss/engines/{engine}/markets/{market}/{path}/{id}.json"


def _iss_row_dict(table):
    if not table.get("data"):
        return {}
    return dict(zip(table["columns"], table["data"][0]))


def fetch_moex_security(engine, market, secid, board=None):
    """Returns the marketdata row (as a {column: value} dict) for one MOEX
    instrument - shared by currency pairs, gold/silver, and indices, which
    all live under different engines/markets but the same response shape."""
    path = f"boards/{board}/securities" if board else "securities"
    url = MOEX_SECURITY_URL.format(engine=engine, market=market, path=path, id=secid)
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    return _iss_row_dict(resp.json()["marketdata"])


def _moex_last_and_pct(marketdata):
    last = next(
        (marketdata[k] for k in ("LAST", "LASTVALUE", "CURRENTVALUE") if marketdata.get(k) is not None), None
    )
    pct = marketdata.get("LASTTOPREVPRICE")
    if last is None:
        return None
    return last, pct


# --------------------------------------------------------------- Currency --
# MOEX's currency market (SELT) trades USD/EUR/CNY vs RUB live during its
# session - real-time, unlike the Bank of Russia's once-a-day official fix.
CURRENCY_INSTRUMENTS = (
    ("USD000UTSTOM", "USD"),
    ("EUR_RUB__TOM", "EUR"),
    ("CNYRUB_TOM", "CNY"),
)


def fetch_currency_rate(secid):
    """Returns (rate_rub, pct_change, delta_rub) for one currency pair."""
    marketdata = fetch_moex_security("currency", "selt", secid)
    result = _moex_last_and_pct(marketdata)
    if not result:
        return None
    last, pct = result
    if pct is None:
        return last, None, None
    return last, pct, delta_from_pct(last, pct)


def build_currency_section():
    lines = ["💵 <b>Курс рубля</b> (MOEX)"]
    for secid, label in CURRENCY_INSTRUMENTS:
        try:
            result = fetch_currency_rate(secid)
        except Exception as e:
            print(f"Currency {label} failed: {e}")
            continue
        if not result:
            continue
        rate, pct, delta = result
        if pct is None:
            lines.append(f"{label} {rate:.2f} ₽")
        else:
            lines.append(f"{arrow(pct)} {label} {rate:.2f} ₽ ({delta:+.2f} ₽, {pct:+.1f}%)")
    return lines if len(lines) > 1 else []


# ----------------------------------------------------------------- Metals --
# Gold/silver trade on MOEX (GLDRUB_TOM/SLVRUB_TOM) - live, in rubles per
# gram. Platinum/palladium have no free live-traded source we found, so
# those two stay on the Bank of Russia's once-a-day official fix, with a
# day-over-day change instead of an intraday one (clearly labeled either
# way so the two aren't confused for the same kind of number).
METAL_INSTRUMENTS = (("GLDRUB_TOM", "Золото"), ("SLVRUB_TOM", "Серебро"))

CBR_METALS_URL = "https://www.cbr.ru/scripts/xml_metall.asp"
CBR_METAL_CODES = {"3": "Платина", "4": "Палладий"}


def fetch_metal_rate(secid):
    marketdata = fetch_moex_security("currency", "selt", secid)
    result = _moex_last_and_pct(marketdata)
    if not result:
        return None
    last, pct = result
    if pct is None:
        return last, None, None
    return last, pct, delta_from_pct(last, pct)


def fetch_cbr_metal_history(days=10):
    """Returns {code: [(date, price_rub_per_gram), ...]} sorted oldest to
    newest, for the two metals with no live-traded source (Pt=3, Pd=4).
    A window wider than a couple of days covers weekends/holidays where
    the Bank of Russia doesn't publish a new fix."""
    today = datetime.now()
    date_from = (today - timedelta(days=days)).strftime("%d/%m/%Y")
    date_to = today.strftime("%d/%m/%Y")
    resp = requests.get(CBR_METALS_URL, params={"date_req1": date_from, "date_req2": date_to}, timeout=15)
    resp.raise_for_status()
    root = ElementTree.fromstring(resp.content)

    by_code = {}
    for record in root.findall("Record"):
        code = record.get("Code")
        if code not in CBR_METAL_CODES:
            continue
        date = datetime.strptime(record.get("Date"), "%d.%m.%Y")
        price = float(record.findtext("Buy").replace(",", "."))
        by_code.setdefault(code, []).append((date, price))
    return {code: sorted(points) for code, points in by_code.items()}


def build_metals_section():
    lines = ["🥇 <b>Металлы</b>"]
    for secid, label in METAL_INSTRUMENTS:
        try:
            result = fetch_metal_rate(secid)
        except Exception as e:
            print(f"Metal {label} (MOEX) failed: {e}")
            continue
        if not result:
            continue
        rate, pct, delta = result
        if pct is None:
            lines.append(f"{label} {rate:,.0f} ₽/г")
        else:
            lines.append(f"{arrow(pct)} {label} {rate:,.0f} ₽/г ({delta:+.0f} ₽, {pct:+.1f}%)")

    try:
        history = fetch_cbr_metal_history()
        for code, label in CBR_METAL_CODES.items():
            points = history.get(code) or []
            if not points:
                continue
            if len(points) == 1:
                lines.append(f"{label} {points[-1][1]:,.0f} ₽/г (ЦБ РФ, дневной фиксинг)")
            else:
                (_, prev), (_, last) = points[-2], points[-1]
                pct = pct_from_prev(last, prev)
                lines.append(f"{arrow(pct)} {label} {last:,.0f} ₽/г ({last - prev:+.0f} ₽, {pct:+.1f}%, ЦБ РФ)")
    except Exception as e:
        print(f"Metals section (CBR) failed: {e}")

    return lines if len(lines) > 1 else []


# ---------------------------------------------------------------- Indices --

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
US_INDICES = (("%5EGSPC", "S&P 500"), ("%5EDJI", "Dow Jones"), ("%5EIXIC", "Nasdaq"))
RU_INDICES = (("IMOEX", "IMOEX"), ("RTSI", "RTS"))


def fetch_yahoo_index_change(symbol):
    """Uses urllib, not requests - requests re-quotes the URL through its
    own normalization regardless of how it's built, percent-encoding '^'
    to %5E; confirmed live against Stooq that this breaks a server expecting
    the raw character. Pre-encoding it ourselves and sending via urllib
    sidesteps the whole problem."""
    url = YAHOO_CHART_URL.format(symbol=symbol)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    meta = data["chart"]["result"][0]["meta"]
    price = meta.get("regularMarketPrice")
    prev_close = meta.get("chartPreviousClose") or meta.get("previousClose")
    if price is None or not prev_close:
        return None
    return price, pct_from_prev(price, prev_close)


def fetch_moex_index(index_id):
    marketdata = fetch_moex_security("stock", "index", index_id)
    return _moex_last_and_pct(marketdata)


def build_indices_section():
    lines = []
    for symbol, label in US_INDICES:
        try:
            result = fetch_yahoo_index_change(symbol)
            if result:
                value, pct = result
                lines.append(f"{arrow(pct)} {label} {value:,.0f} ({pct:+.1f}%)")
        except Exception as e:
            print(f"Index {label} (Yahoo) failed: {e}")

    for index_id, label in RU_INDICES:
        try:
            result = fetch_moex_index(index_id)
            if result:
                value, pct = result
                if pct is None:
                    lines.append(f"{label} {value:,.0f}")
                else:
                    lines.append(f"{arrow(pct)} {label} {value:,.0f} ({pct:+.1f}%)")
        except Exception as e:
            print(f"Index {label} (MOEX) failed: {e}")

    return ["📊 <b>Индексы</b>"] + lines if lines else []


# --------------------------------------------------------- Stock movers --

FMP_API_KEY = os.environ.get("FMP_API_KEY")
FMP_GAINERS_URL = "https://financialmodelingprep.com/api/v3/stock_market/gainers"
FMP_LOSERS_URL = "https://financialmodelingprep.com/api/v3/stock_market/losers"

MOEX_SHARES_URL = "https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities.json"


def fetch_fmp_movers(url, count=MOVERS_COUNT):
    resp = requests.get(url, params={"apikey": FMP_API_KEY}, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    ranked = sorted(data, key=lambda m: m.get("changesPercentage", 0), reverse=(url == FMP_GAINERS_URL))
    return ranked[:count]


def fetch_all_moex_stock_prices():
    """Returns {secid: last_price} for every liquid RU stock (TQBR board) -
    used by the anomaly watcher, which needs every instrument's current
    price to compare against its own tracked reference, not just the top
    few movers the daily digest shows."""
    resp = requests.get(MOEX_SHARES_URL, params={"iss.meta": "off"}, timeout=15)
    resp.raise_for_status()
    market_table = resp.json()["marketdata"]
    m_cols = market_table["columns"]
    secid_idx = m_cols.index("SECID")
    last_idx = m_cols.index("LAST") if "LAST" in m_cols else None
    if last_idx is None:
        return {}
    return {row[secid_idx]: row[last_idx] for row in market_table["data"] if row[last_idx] is not None}


def fetch_moex_stock_movers(count=MOVERS_COUNT):
    resp = requests.get(MOEX_SHARES_URL, params={"iss.meta": "off"}, timeout=15)
    resp.raise_for_status()
    payload = resp.json()

    securities_table = payload["securities"]
    sec_cols = securities_table["columns"]
    secid_idx = sec_cols.index("SECID")
    names = {row[secid_idx]: row[secid_idx] for row in securities_table["data"]}

    market_table = payload["marketdata"]
    m_cols = market_table["columns"]
    m_secid_idx = m_cols.index("SECID")
    last_idx = m_cols.index("LAST") if "LAST" in m_cols else None
    pct_idx = m_cols.index("LASTTOPREVPRICE") if "LASTTOPREVPRICE" in m_cols else None
    if pct_idx is None:
        return [], []

    movers = [
        {
            "secid": row[m_secid_idx],
            "last": row[last_idx] if last_idx is not None else None,
            "pct": row[pct_idx],
        }
        for row in market_table["data"]
        if row[pct_idx] is not None
    ]
    return top_movers(movers, key=lambda m: m["pct"], count=count)


def build_stocks_section():
    lines = []
    try:
        gainers, losers = fetch_moex_stock_movers()
        if gainers:
            lines.append("📈 <b>Лидеры роста акций (Россия)</b>")
            for m in gainers:
                lines.append(f"🟢 #{m['secid']} {m['pct']:+.1f}%")
        if losers:
            lines.append("")
            lines.append("📉 <b>Лидеры падения акций (Россия)</b>")
            for m in losers:
                lines.append(f"🔴 #{m['secid']} {m['pct']:+.1f}%")
    except Exception as e:
        print(f"Russian stock movers failed: {e}")

    if FMP_API_KEY:
        try:
            gainers = fetch_fmp_movers(FMP_GAINERS_URL)
            if gainers:
                lines.append("")
                lines.append("📈 <b>Лидеры роста акций (мир)</b>")
                for m in gainers:
                    lines.append(f"🟢 #{m['symbol']} {m['changesPercentage']:+.1f}%")
        except Exception as e:
            print(f"World stock gainers failed: {e}")
        try:
            losers = fetch_fmp_movers(FMP_LOSERS_URL)
            if losers:
                lines.append("")
                lines.append("📉 <b>Лидеры падения акций (мир)</b>")
                for m in losers:
                    lines.append(f"🔴 #{m['symbol']} {m['changesPercentage']:+.1f}%")
        except Exception as e:
            print(f"World stock losers failed: {e}")

    return lines


# ------------------------------------------------------------ Trading hours --
# All in MSK (UTC+3, no DST in Russia). US hours are an approximation
# (EDT-based, the figure Russian financial media usually cites) - being
# off by an hour around US daylight-saving transitions doesn't matter at
# a 2-hour check granularity.
MSK = timezone(timedelta(hours=3))

MOEX_SESSION = (10, 19)  # 10:00-19:00 MSK, main equity/currency session
US_SESSION = (16, 23)  # 16:00-23:00 MSK, approx. NYSE/Nasdaq regular hours


def _in_session(now_msk, session):
    start, end = session
    return start <= now_msk.hour < end


def is_weekday(now_msk):
    return now_msk.weekday() < 5  # Monday=0 ... Sunday=6


def moex_session_open(now_msk=None):
    now_msk = now_msk or datetime.now(MSK)
    return is_weekday(now_msk) and _in_session(now_msk, MOEX_SESSION)


def us_session_open(now_msk=None):
    now_msk = now_msk or datetime.now(MSK)
    return is_weekday(now_msk) and _in_session(now_msk, US_SESSION)
