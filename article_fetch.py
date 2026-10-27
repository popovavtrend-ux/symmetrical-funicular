"""Fetches the source article's own full text instead of relying on the
RSS feed's summary field - many feeds only include the lead paragraph as a
teaser, which starved the rewrite of everything past the opening and
produced posts far thinner than the real story."""

import requests
import trafilatura

# Plain requests' default User-Agent gets blocked by some news sites -
# a normal desktop browser string avoids that without doing anything
# deceptive (it's a real, generic browser ID, not spoofing a specific site).
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    )
}

# Below this, trafilatura likely only found boilerplate (nav, a teaser, a
# paywall notice) rather than the actual article body - not worth
# preferring over the RSS summary we already have.
MIN_ARTICLE_LEN = 200

# Articles can run long; this is plenty for a rewrite and keeps the prompt
# (and its token cost) bounded regardless of how long the source runs.
MAX_ARTICLE_CHARS = 8000


def fetch_article_text(url):
    """Returns the article's own full body text, or None if it couldn't be
    fetched or no real article content could be extracted - callers should
    fall back to the RSS summary in that case, same as any other
    best-effort enrichment in this codebase."""
    try:
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"Failed to fetch article page at {url!r}: {e}")
        return None

    try:
        text = trafilatura.extract(resp.text, include_comments=False, include_tables=False)
    except Exception as e:
        print(f"Failed to extract article text from {url!r}: {e}")
        return None

    if not text or len(text) < MIN_ARTICLE_LEN:
        return None

    return text[:MAX_ARTICLE_CHARS]
