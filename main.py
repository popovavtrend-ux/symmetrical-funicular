import html
import os
import re
import time
from urllib.parse import urlparse

from fetch_feed import fetch_entries
from price_chart import generate_price_chart
from state import load_state, save_state
from stock_image import find_stock_image
from telegram_post import send_message, send_photo, send_photo_bytes
from translate import translate, translate_new

DEFAULT_FEED_URLS = (
    "https://protos.com/feed/,"
    "https://www.dlnews.com/rss/,"
    "https://cryptoslate.com/feed/,"
    "https://decrypt.co/feed,"
    "https://beincrypto.com/feed/"
)

FEED_URLS = [u.strip() for u in (os.environ.get("FEED_URL") or DEFAULT_FEED_URLS).split(",") if u.strip()]
STATE_FILE = os.environ.get("STATE_FILE") or "data/seen_ids.json"
MAX_ITEMS_PER_RUN = int(os.environ.get("MAX_ITEMS_PER_RUN") or "5")
SKIP_TRANSLATION = (os.environ.get("SKIP_TRANSLATION") or "").strip().lower() in ("1", "true", "yes")
# "legacy" = old prompt/rules (the original group pipeline); "new" = the
# full-rewrite, beginner-friendly, no-financial-advice pipeline (the channel).
CONTENT_STYLE = (os.environ.get("CONTENT_STYLE") or "legacy").strip().lower()

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

TAG_RE = re.compile("<[^<]+?>")
WP_APPEARED_FIRST_RE = re.compile(r"\s*The post .+ appeared first on .+?\.\s*$")
IMG_SRC_RE = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)

TELEGRAM_MAX_LEN = 4096
TELEGRAM_PHOTO_CAPTION_MAX_LEN = 1024
SIGNATURE = os.environ.get("SIGNATURE") or "@cryptocompass_news"

# Human-readable publication names for the source line - naming the source
# is what makes rewriting/quoting someone else's news legally a citation
# (e.g. GK RF Art. 1274) rather than an unattributed copy.
SOURCE_NAMES = {
    "protos.com": "Protos",
    "dlnews.com": "DL News",
    "cryptoslate.com": "CryptoSlate",
    "decrypt.co": "Decrypt",
    "beincrypto.com": "BeInCrypto",
    "coindesk.com": "CoinDesk",
    "cointelegraph.com": "Cointelegraph",
    "bitcoinmagazine.com": "Bitcoin Magazine",
    "thedefiant.io": "The Defiant",
    "forklog.com": "Forklog",
    "ru.beincrypto.com": "BeInCrypto",
    "incrypted.com": "Incrypted",
    "cryptocurrency.tech": "Cryptocurrency.Tech",
}


def entry_id(entry):
    return getattr(entry, "id", None) or entry.link


def clean_summary(entry):
    summary = getattr(entry, "summary", "") or ""
    summary = TAG_RE.sub("", summary).strip()
    summary = WP_APPEARED_FIRST_RE.sub("", summary).strip()
    return summary


def extract_source_image_url(entry):
    """Pull the article's own image URL, used only to privately describe it
    for a stock-photo search - it's never sent to Telegram or republished."""
    for thumb in entry.get("media_thumbnail") or []:
        if thumb.get("url"):
            return thumb["url"]

    media_content = entry.get("media_content") or []
    for m in media_content:
        if (m.get("medium") == "image" or (m.get("type") or "").startswith("image")) and m.get("url"):
            return m["url"]
    if media_content and media_content[0].get("url"):
        return media_content[0]["url"]

    for enc in entry.get("enclosures") or []:
        if (enc.get("type") or "").startswith("image") and enc.get("href"):
            return enc["href"]

    raw_html = entry.get("summary") or ""
    content = entry.get("content") or []
    if content:
        raw_html += content[0].get("value") or ""
    match = IMG_SRC_RE.search(raw_html)
    if match:
        return match.group(1)

    return None


def get_source_name(entry):
    host = urlparse(entry.get("_feed_url") or "").netloc
    host = host[4:] if host.startswith("www.") else host
    return SOURCE_NAMES.get(host, host)


def signature_message():
    return f"<b>{html.escape(SIGNATURE)}</b>"


OPINION_MARKER = "\U0001f4ad "  # 💭 - marks where translate.py's opinion paragraph starts


def build_caption(title_ru, summary_ru, source_name=None, max_len=TELEGRAM_MAX_LEN):
    """Title + body (+ source line) - the caption that renders below the
    photo, or the whole message body when there's no photo. The opinion
    paragraph (after the 💭 marker, if present) is italicized to visually
    set our take apart from the factual context above it."""
    title_html = f"<b>{html.escape(title_ru)}</b>"
    source_html = f"<i>По материалам: {html.escape(source_name)}</i>" if source_name else ""

    plain_summary = summary_ru or ""
    reserved = len(f"{title_html}\n\n") + (len(f"\n\n{source_html}") if source_html else 0)
    budget = max_len - reserved
    if plain_summary and len(plain_summary) > budget:
        plain_summary = plain_summary[: max(0, budget - 3)].rsplit(" ", 1)[0] + "..."

    if OPINION_MARKER in plain_summary:
        context_part, opinion_part = plain_summary.split(OPINION_MARKER, 1)
        context_part = context_part.strip()
        opinion_part = opinion_part.strip()
    else:
        context_part, opinion_part = plain_summary, ""

    parts = [title_html]
    if context_part:
        parts.append(html.escape(context_part))
    if opinion_part:
        parts.append(f"<i>{OPINION_MARKER}{html.escape(opinion_part)}</i>")
    if source_html:
        parts.append(source_html)
    return "\n\n".join(parts)


def build_message(title_ru, summary_ru, source_name=None, max_len=TELEGRAM_MAX_LEN):
    """Signature + title + body (+ source line) in one text message, for
    the no-image case (and as a photo-send fallback) where there's no
    separate photo to put the signature above."""
    header = signature_message()
    caption = build_caption(title_ru, summary_ru, source_name=source_name, max_len=max_len - len(f"{header}\n"))
    return f"{header}\n{caption}"


def sort_key(entry):
    return entry.get("published_parsed") or entry.get("updated_parsed") or time.gmtime(0)


DIGEST_KEYWORDS = ("digest", "roundup", "recap", "week in review")


def is_digest_or_roundup(title):
    """Roundup articles (e.g. Decrypt's "Hodler's Digest") bundle several
    separately-reported, often already-days-old stories under one headline.
    Forcing one through the single-story rewrite produces a post that reads
    like a mash-up of stale news rather than one fresh event."""
    lowered = title.lower()
    if any(kw in lowered for kw in DIGEST_KEYWORDS):
        return True
    return title.count("!") >= 2


def main():
    entries = fetch_entries(FEED_URLS)
    if not entries:
        print(f"No entries found across FEED_URLS={FEED_URLS}. Are these valid RSS feed URLs?")
        return

    digest_count = sum(1 for e in entries if is_digest_or_roundup(e.title))
    if digest_count:
        entries = [e for e in entries if not is_digest_or_roundup(e.title)]
        print(f"Skipped {digest_count} digest/roundup entr{'y' if digest_count == 1 else 'ies'}.")
    if not entries:
        print("No entries left after filtering out digest/roundup articles.")
        return

    state = load_state(STATE_FILE)

    if state is None:
        # First run: seed state without posting, so we don't dump the whole
        # archive into the channel at once.
        seen = {entry_id(e) for e in entries}
        save_state(STATE_FILE, {"seen_ids": seen, "seeded_feeds": set(FEED_URLS)})
        print(f"First run: seeded {len(seen)} existing entries, no messages posted.")
        return

    seen = state["seen_ids"]
    seeded_feeds = state["seeded_feeds"]

    # A feed URL added to FEED_URLS after the first run has never been
    # seeded - without this, all of its current entries would look "new"
    # and get dumped into the channel at once, regardless of how old they
    # actually are. Seed it silently instead, same as the first run.
    new_feed_urls = [u for u in FEED_URLS if u not in seeded_feeds]
    if new_feed_urls:
        newly_seeded = [e for e in entries if e.get("_feed_url") in new_feed_urls]
        seen.update(entry_id(e) for e in newly_seeded)
        seeded_feeds.update(new_feed_urls)
        save_state(STATE_FILE, {"seen_ids": seen, "seeded_feeds": seeded_feeds})
        print(
            f"Seeded {len(newly_seeded)} existing entries from newly added feed(s) "
            f"{new_feed_urls}, no messages posted for them."
        )
        entries = [e for e in entries if e.get("_feed_url") not in new_feed_urls]

    # Newest first - with several active feeds, more can break in one
    # window than MAX_ITEMS_PER_RUN can post. Prioritizing the newest
    # keeps the channel caught up on current events instead of always
    # working through an ever-growing backlog of older stories.
    entries.sort(key=sort_key, reverse=True)
    unseen = [e for e in entries if entry_id(e) not in seen]
    new_entries = unseen[:MAX_ITEMS_PER_RUN]
    stale_backlog = unseen[MAX_ITEMS_PER_RUN:]

    if stale_backlog:
        # Mark the rest as seen without posting them - skip the backlog
        # rather than posting stale news for the next several runs.
        seen.update(entry_id(e) for e in stale_backlog)
        save_state(STATE_FILE, {"seen_ids": seen, "seeded_feeds": seeded_feeds})

    if not new_entries:
        print("No new entries.")
        return

    new_entries.sort(key=sort_key)  # oldest-of-the-batch first, for a readable posting order

    for entry in new_entries:
        title = entry.title
        summary = clean_summary(entry)
        link = entry.link
        source_name = get_source_name(entry)

        try:
            # SKIP_TRANSLATION only means "post as-is" when there's no
            # ANTHROPIC_API_KEY to rewrite it into a unique post - once a
            # key is set, even already-Russian sources get rewritten rather
            # than copied verbatim.
            if SKIP_TRANSLATION and not os.environ.get("ANTHROPIC_API_KEY"):
                title_ru, summary_ru = title, summary
            elif CONTENT_STYLE == "new":
                title_ru, summary_ru = translate_new(title, summary)
            else:
                title_ru, summary_ru = translate(title, summary)

            # Telegram can't render caption text above its own photo, so the
            # signature goes as the caption's first line instead - one
            # message, signature at the top of the text, image above it.
            caption = build_message(
                title_ru, summary_ru, source_name=source_name, max_len=TELEGRAM_PHOTO_CAPTION_MAX_LEN
            )

            # A named coin gets its actual price chart rather than an
            # illustrative stock photo that only looks like one.
            price_chart = generate_price_chart(title)
            if price_chart:
                try:
                    send_photo_bytes(BOT_TOKEN, CHAT_ID, price_chart, "chart.png", caption)
                except Exception as e:
                    print(f"Failed to send price chart, falling back: {e}")
                    price_chart = None

            if not price_chart:
                image_url = find_stock_image(title, source_image_url=extract_source_image_url(entry))
                if image_url:
                    try:
                        send_photo(BOT_TOKEN, CHAT_ID, image_url, caption)
                    except Exception as e:
                        print(f"Failed to send photo ({image_url!r}), falling back to text: {e}")
                        send_message(BOT_TOKEN, CHAT_ID, build_message(title_ru, summary_ru, source_name=source_name))
                else:
                    send_message(BOT_TOKEN, CHAT_ID, build_message(title_ru, summary_ru, source_name=source_name))
        except Exception as e:
            # Don't let one bad entry take down the whole run - the
            # already-posted entries above must still get committed.
            print(f"Failed to post entry {link!r}: {e}")
            continue

        seen.add(entry_id(entry))
        save_state(STATE_FILE, {"seen_ids": seen, "seeded_feeds": seeded_feeds})
        print(f"Posted (source title: {title!r}): {title_ru!r}")
        time.sleep(3)


if __name__ == "__main__":
    main()
