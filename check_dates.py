import time

import feedparser

FEED_URLS = [
    "https://protos.com/feed/",
    "https://www.dlnews.com/rss/",
    "https://cryptoslate.com/feed/",
    "https://decrypt.co/feed",
    "https://beincrypto.com/feed/",
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://cointelegraph.com/rss",
    "https://bitcoinmagazine.com/feed",
    "https://thedefiant.io/feed",
]

NOW = time.gmtime()
print(f"Now (UTC): {time.strftime('%Y-%m-%d %H:%M', NOW)}\n")

for url in FEED_URLS:
    parsed = feedparser.parse(url)
    entries = parsed.entries or []
    print(f"=== {url} - {len(entries)} entries ===")
    no_date = 0
    for e in entries:
        pub = e.get("published_parsed") or e.get("updated_parsed")
        if pub:
            age_days = (time.mktime(NOW) - time.mktime(pub)) / 86400
            date_str = time.strftime("%Y-%m-%d %H:%M", pub)
        else:
            no_date += 1
            age_days = None
            date_str = "NO DATE"
        title = (e.get("title") or "")[:70]
        print(f"  {date_str}  (age={age_days if age_days is None else round(age_days,1)}d)  {title!r}")
    print(f"  -> {no_date}/{len(entries)} entries with NO parseable date\n")
