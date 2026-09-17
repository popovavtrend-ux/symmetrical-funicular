import base64
import json
import os
import random

import requests

PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
PEXELS_SEARCH_URL = "https://api.pexels.com/v1/search"
# Pexels' documented max per_page - pulling the full page instead of a
# token 10 gives the anti-repeat logic in find_stock_image() far more to
# choose from before it's ever forced to reuse a photo.
PEXELS_PER_PAGE = 80

# Optional extra sources - widen the candidate pool further still. Each is
# inactive (silently skipped) unless its key is set; both have a free tier
# (unsplash.com/developers, pixabay.com/api/docs).
UNSPLASH_ACCESS_KEY = os.environ.get("UNSPLASH_ACCESS_KEY")
UNSPLASH_SEARCH_URL = "https://api.unsplash.com/search/photos"
UNSPLASH_PER_PAGE = 30  # Unsplash's documented max per_page

PIXABAY_API_KEY = os.environ.get("PIXABAY_API_KEY")
PIXABAY_SEARCH_URL = "https://pixabay.com/api/"
PIXABAY_PER_PAGE = 80  # Pixabay's documented max per_page

# Last-resort fallback when there's no ANTHROPIC_API_KEY to read the story
# with (see guess_query_from_content below), or the content-based query
# comes back empty/fails/finds no photos. Maps a keyword that might appear
# in a headline (English, or transliterated Russian) to a query term the
# photo APIs actually have good stock photos for.
CRYPTO_KEYWORDS = {
    # Event/topic keywords first, checked before coin names, so a story
    # like "major hack drains DeFi protocol" matches the more specific
    # "hack" rather than stopping at the first coin/tech name it contains.
    "hack": "cybersecurity hacker",
    "hacked": "cybersecurity hacker",
    "exploit": "cybersecurity hacker",
    "взлом": "cybersecurity hacker",
    "regulat": "government regulation",
    "sec ": "government regulation",
    "регулятор": "government regulation",
    "etf": "stock market chart",
    "lawsuit": "court gavel justice",
    "sues": "court gavel justice",
    "суд": "court gavel justice",
    "mining": "bitcoin mining hardware",
    "майнинг": "bitcoin mining hardware",
    "wallet": "digital wallet security",
    "кошел": "digital wallet security",
    "exchange": "stock exchange trading",
    "биржа": "stock exchange trading",
    "stablecoin": "digital currency",
    "bank": "bank building exterior",
    "банк": "bank building exterior",
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


def guess_query_from_content(title, summary):
    """Read the actual story (title + summary, whichever language) and ask
    Claude what it's really about, not just which coin it names - a hack,
    a court ruling, a price crash, a product launch, a partnership, etc.
    Different stories about the same coin then search for different
    things instead of all collapsing onto one generic "bitcoin" query,
    which is the main reason the same handful of photos kept repeating."""
    from anthropic_client import create_message, extract_text, get_client

    try:
        client = get_client()
        prompt = (
            "Read this crypto/finance news story and give 2-4 English "
            "keywords for a stock photo search that captures what it's "
            "actually about - not just the coin or company name, but the "
            "real subject: a hack, a regulatory ruling, a price crash, a "
            "legal case, a product launch, a partnership, a conference, "
            "etc. Prefer concrete, photographable subjects over abstract "
            "crypto terms, e.g. 'court gavel justice' for a lawsuit, 'red "
            "stock chart crash' for a price drop, 'padlock cybersecurity' "
            "for a hack, 'bank building exterior' for a banking story - "
            "only fall back to a coin name or 'cryptocurrency' if nothing "
            "more specific fits. Reply with just the keywords, nothing "
            "else.\n\n"
            f"Title: {title}\n"
            f"Summary: {summary}"
        )
        resp = create_message(client, max_tokens=60, messages=[{"role": "user", "content": prompt}])
        return extract_text(resp).strip() or None
    except Exception as e:
        print(f"Content-based image query failed: {e}")
        return None


def describe_image_for_search(image_url, title):
    """Privately look at the source's own photo (never republished) and ask
    Claude to describe a stock-photo search for it - grounded in the news
    topic, not just the image's literal visual style. Source images are
    often abstract editorial artwork (neon shapes, gradients, icons), and
    describing that literally produces a query that matches nothing about
    the actual story. Used only when guess_query_from_content() above
    isn't available (no summary) or didn't work."""
    from anthropic_client import create_message, extract_text, get_client

    try:
        img_resp = requests.get(image_url, timeout=15)
        img_resp.raise_for_status()
        media_type = img_resp.headers.get("Content-Type", "image/jpeg").split(";")[0]
        image_b64 = base64.b64encode(img_resp.content).decode("ascii")

        client = get_client()
        resp = create_message(
            client,
            max_tokens=200,
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
        return extract_text(resp).strip() or None
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


def _search_pexels(query, per_page=PEXELS_PER_PAGE):
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


def _search_unsplash(query, per_page=UNSPLASH_PER_PAGE):
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


def _search_pixabay(query, per_page=PIXABAY_PER_PAGE):
    if not PIXABAY_API_KEY:
        return []
    try:
        resp = requests.get(
            PIXABAY_SEARCH_URL,
            params={
                "key": PIXABAY_API_KEY,
                "q": query,
                "image_type": "photo",
                "orientation": "horizontal",
                "per_page": per_page,
                "safesearch": "true",
            },
            timeout=15,
        )
        resp.raise_for_status()
        hits = resp.json().get("hits") or []
        return [h["largeImageURL"] for h in hits if h.get("largeImageURL")]
    except Exception as e:
        print(f"Pixabay search failed for {query!r}: {e}")
        return []


def _search_all(query):
    candidates = _search_pexels(query) + _search_unsplash(query) + _search_pixabay(query)
    # The APIs return results ranked by their own relevance score, which is
    # near-identical run to run for a similar query - always taking the
    # first candidate not yet in history means every source converges on
    # the same small ordered sequence of photos. Shuffling means two runs
    # with the same query don't pick images in the same order.
    random.shuffle(candidates)
    return candidates


def find_stock_image(title, summary=None, source_image_url=None, history_path=None):
    """Look up a free-to-use stock photo (Pexels, plus Unsplash/Pixabay if
    configured) visually matching the news topic, instead of hotlinking
    the source's own copyrighted photo. Returns an image URL, or None if
    no API key is configured or nothing matches.

    Query, in order of preference:
    1. guess_query_from_content() - Claude reads the actual story (title +
       summary) and names what it's really about, not just the coin/company
       named in the title.
    2. describe_image_for_search() - Claude looks at the source's own
       illustration, if there is one. Only reached when there's no summary
       to read, or the content-based read above didn't produce anything.
    3. guess_image_query() - static keyword table, used with no
       ANTHROPIC_API_KEY, or if both Claude calls above failed.

    history_path, if given, tracks recently-used photo URLs so a fresh one
    gets picked instead of repeating."""
    if not PEXELS_API_KEY and not UNSPLASH_ACCESS_KEY and not PIXABAY_API_KEY:
        return None

    fallback_query = guess_image_query(title)
    query = None
    if os.environ.get("ANTHROPIC_API_KEY"):
        if summary:
            query = guess_query_from_content(title, summary)
        if not query and source_image_url:
            query = describe_image_for_search(source_image_url, title)
    query = query or fallback_query
    print(f"Stock photo query for {title!r}: {query!r}")

    recent = set(_load_recent_images(history_path))
    candidates = _search_all(query)
    if not candidates and query != fallback_query:
        print(f"No results for {query!r}, retrying with {fallback_query!r}")
        candidates = _search_all(fallback_query)
    if not candidates:
        return None

    result = next((c for c in candidates if c not in recent), candidates[0])

    if history_path:
        _save_recent_images(history_path, [*_load_recent_images(history_path), result])
    return result
