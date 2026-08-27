import feedparser


def fetch_entries(feed_url):
    parsed = feedparser.parse(feed_url)
    if parsed.bozo and not parsed.entries:
        raise RuntimeError(f"Failed to parse feed at {feed_url}: {parsed.bozo_exception}")
    return parsed.entries
