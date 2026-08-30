import feedparser

CANDIDATE_FEEDS = [
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://cointelegraph.com/rss",
    "https://bitcoinmagazine.com/feed",
    "https://thedefiant.io/feed",
    "https://forklog.com/feed/",
    "https://ru.beincrypto.com/feed/",
    "https://www.rbc.ru/crypto/rss/",
    "https://ru.cointelegraph.com/rss",
]

for url in CANDIDATE_FEEDS:
    parsed = feedparser.parse(url)
    status = getattr(parsed, "status", None)
    entries = parsed.entries or []
    if parsed.bozo and not entries:
        print(f"[FAIL] {url} - status={status} error={parsed.bozo_exception}")
        continue
    if not entries:
        print(f"[EMPTY] {url} - status={status}, no entries")
        continue
    print(f"[OK] {url} - status={status}, {len(entries)} entries, first title: {entries[0].get('title')!r}")
