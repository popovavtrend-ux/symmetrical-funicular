import feedparser


def fetch_entries(feed_urls):
    """feed_urls: a single URL or a list of URLs.

    A feed that fails to fetch/parse is skipped (logged), not fatal - the
    others should still get posted.
    """
    if isinstance(feed_urls, str):
        feed_urls = [feed_urls]

    all_entries = []
    for url in feed_urls:
        try:
            parsed = feedparser.parse(url)
        except Exception as e:
            print(f"Failed to fetch feed at {url}: {e}")
            continue

        if parsed.bozo and not parsed.entries:
            print(f"Failed to parse feed at {url}: {parsed.bozo_exception}")
            continue
        if not parsed.entries:
            print(f"Feed at {url} returned no entries")
            continue

        for entry in parsed.entries:
            entry["_feed_url"] = url
        all_entries.extend(parsed.entries)

    return all_entries
