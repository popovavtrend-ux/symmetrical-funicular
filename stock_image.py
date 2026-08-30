import os

import requests

PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
PEXELS_SEARCH_URL = "https://api.pexels.com/v1/search"

# Maps a keyword that might appear in a headline (English, or transliterated
# Russian for the RU-language feeds) to the query term Pexels actually has
# good stock photos for.
CRYPTO_KEYWORDS = {
    "bitcoin": "bitcoin",
    "биткоин": "bitcoin",
    "биткойн": "bitcoin",
    "ethereum": "ethereum",
    "эфириум": "ethereum",
    "solana": "solana",
    "солана": "solana",
    "ripple": "ripple",
    "xrp": "ripple",
    "dogecoin": "dogecoin",
    "cardano": "cardano",
    "polkadot": "polkadot",
    "litecoin": "litecoin",
    "binance": "binance",
    "tether": "tether",
    "defi": "defi",
    "nft": "nft",
    "blockchain": "blockchain",
    "блокчейн": "blockchain",
    "crypto": "cryptocurrency",
    "крипто": "cryptocurrency",
}


def guess_image_query(title):
    lowered = title.lower()
    for keyword, query in CRYPTO_KEYWORDS.items():
        if keyword in lowered:
            return query
    return "cryptocurrency"


def find_stock_image(title):
    """Look up a free-to-use Pexels photo matching the news topic, instead
    of hotlinking the source's own copyrighted photo. Returns an image URL,
    or None if no API key is configured or nothing matches."""
    if not PEXELS_API_KEY:
        return None
    query = guess_image_query(title)
    try:
        resp = requests.get(
            PEXELS_SEARCH_URL,
            params={"query": query, "per_page": 1, "orientation": "landscape"},
            headers={"Authorization": PEXELS_API_KEY},
            timeout=15,
        )
        resp.raise_for_status()
        photos = resp.json().get("photos") or []
        if not photos:
            return None
        return photos[0]["src"]["large"]
    except Exception as e:
        print(f"Pexels search failed for {query!r}: {e}")
        return None
