import base64
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


def describe_image_for_search(image_url):
    """Privately look at the source's own photo (never republished) and ask
    Claude to describe its visual subject in a few keywords, so the Pexels
    search below can find something that actually looks similar - not just
    topically related by headline keywords."""
    from anthropic_client import get_client

    try:
        img_resp = requests.get(image_url, timeout=15)
        img_resp.raise_for_status()
        media_type = img_resp.headers.get("Content-Type", "image/jpeg").split(";")[0]
        image_b64 = base64.b64encode(img_resp.content).decode("ascii")

        client = get_client()
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=30,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_b64}},
                        {
                            "type": "text",
                            "text": (
                                "Describe the main visual subject of this image in 2-4 English "
                                "keywords suitable for a stock photo search (e.g. 'bitcoin coin "
                                "gold', 'stock market red chart', 'bank building exterior'). "
                                "Reply with just the keywords, nothing else."
                            ),
                        },
                    ],
                }
            ],
        )
        return resp.content[0].text.strip() or None
    except Exception as e:
        print(f"Image description failed for {image_url!r}: {e}")
        return None


def find_stock_image(title, source_image_url=None):
    """Look up a free-to-use Pexels photo visually matching the news topic,
    instead of hotlinking the source's own copyrighted photo. Returns an
    image URL, or None if no API key is configured or nothing matches."""
    if not PEXELS_API_KEY:
        return None

    query = None
    if source_image_url and os.environ.get("ANTHROPIC_API_KEY"):
        query = describe_image_for_search(source_image_url)
    if not query:
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
