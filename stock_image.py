import base64
import json
import os

import requests

PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
PEXELS_SEARCH_URL = "https://api.pexels.com/v1/search"

# Optional second source - widens the candidate pool so the anti-repeat
# logic below has more to pick from before it's forced to reuse a photo.
# Inactive (silently skipped) unless UNSPLASH_ACCESS_KEY is set; get a free
# one at unsplash.com/developers.
UNSPLASH_ACCESS_KEY = os.environ.get("UNSPLASH_ACCESS_KEY")
UNSPLASH_SEARCH_URL = "https://api.unsplash.com/search/photos"

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


def describe_image_for_search(image_url, title):
    """Privately look at the source's own photo (never republished) and ask
    Claude to describe a stock-photo search for it - grounded in the news
    topic, not just the image's literal visual style. Source images are
    often abstract editorial artwork (neon shapes, gradients, icons), and
    describing that literally produces a query that matches nothing about
    the actual story."""
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
                                f"This image illustrates a crypto/finance news story titled "
                                f"'{title}'. Give 2-4 English keywords for a stock photo search "
                                f"that would find a real (non-illustration) photo relevant to "
                                f"this story - e.g. 'bitcoin coin gold', 'stock market red chart', "
                                f"'bank building exterior', 'blockchain network digital'. If this "
                                f"image is abstract or stylized artwork rather than a literal "
                                f"photo, ignore its abstract style and describe the underlying "
                                f"financial/crypto subject of the story instead. Reply with just "
                                f"the keywords, nothing else."
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


RECENT_IMAGES_LIMIT = 40


def _load_recent_images(history_path):
    if not history_path or not os.path.exists(history_path):
        return []
    try:
        with open(history_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_recent_images(history_path, urls):
    if not history_path:
        return
    os.makedirs(os.path.dirname(history_path) or ".", exist_ok=True)
    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(urls[-RECENT_IMAGES_LIMIT:], f, ensure_ascii=False, indent=2)


def _search_pexels(query, per_page=10):
    if not PEXELS_API_KEY:
        return []
    try:
        resp = requests.get(
            PEXELS_SEARCH_URL,
            params={"query": query, "per_page": per_page, "orientation": "landscape"},
            headers={"Authorization": PEXELS_API_KEY},
            timeout=15,
        )
        resp.raise_for_status()
        photos = resp.json().get("photos") or []
        return [p["src"]["large"] for p in photos]
    except Exception as e:
        print(f"Pexels search failed for {query!r}: {e}")
        return []


def _search_unsplash(query, per_page=10):
    if not UNSPLASH_ACCESS_KEY:
        return []
    try:
        resp = requests.get(
            UNSPLASH_SEARCH_URL,
            params={"query": query, "per_page": per_page, "orientation": "landscape"},
            headers={"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"},
            timeout=15,
        )
        resp.raise_for_status()
        results = resp.json().get("results") or []
        return [r["urls"]["regular"] for r in results if r.get("urls", {}).get("regular")]
    except Exception as e:
        print(f"Unsplash search failed for {query!r}: {e}")
        return []


def find_stock_image(title, source_image_url=None, history_path=None):
    """Look up a free-to-use stock photo (Pexels, plus Unsplash if
    configured) visually matching the news topic, instead of hotlinking
    the source's own copyrighted photo. Returns an image URL, or None if
    no API key is configured or nothing matches.

    A search for a single top result is deterministic - similar-sounding
    queries across unrelated stories (e.g. several different "bitcoin"
    headlines) tend to converge on the same handful of popular stock
    photos. Pooling two sources widens how many distinct photos are even
    available for a given query, and history_path, if given, tracks
    recently-used photo URLs so a fresh one gets picked instead of
    repeating."""
    if not PEXELS_API_KEY and not UNSPLASH_ACCESS_KEY:
        return None

    fallback_query = guess_image_query(title)
    query = fallback_query
    if source_image_url and os.environ.get("ANTHROPIC_API_KEY"):
        vision_query = describe_image_for_search(source_image_url, title)
        if vision_query:
            query = vision_query
    print(f"Stock photo query for {title!r}: {query!r}")

    recent = set(_load_recent_images(history_path))
    candidates = _search_pexels(query) + _search_unsplash(query)
    if not candidates and query != fallback_query:
        print(f"No results for {query!r}, retrying with {fallback_query!r}")
        candidates = _search_pexels(fallback_query) + _search_unsplash(fallback_query)
    if not candidates:
        return None

    result = next((c for c in candidates if c not in recent), candidates[0])

    if history_path:
        _save_recent_images(history_path, [*_load_recent_images(history_path), result])
    return result
