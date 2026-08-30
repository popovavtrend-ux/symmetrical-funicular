import html
import os
import re
import time

from fetch_feed import fetch_entries
from state import load_seen, save_seen
from telegram_post import send_message
from translate import translate

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

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

TAG_RE = re.compile("<[^<]+?>")
WP_APPEARED_FIRST_RE = re.compile(r"\s*The post .+ appeared first on .+?\.\s*$")

TELEGRAM_MAX_LEN = 4096


def entry_id(entry):
    return getattr(entry, "id", None) or entry.link


def clean_summary(entry):
    summary = getattr(entry, "summary", "") or ""
    summary = TAG_RE.sub("", summary).strip()
    summary = WP_APPEARED_FIRST_RE.sub("", summary).strip()
    return summary


def build_message(title_ru, summary_ru, link):
    title_html = f"<b>{html.escape(title_ru)}</b>"
    link_html = f'<a href="{link}">Источник</a>'
    summary_html = html.escape(summary_ru) if summary_ru else ""

    # Telegram caps messages at 4096 chars - trim only the summary (not the
    # title or link) if the full article text doesn't fit.
    budget = TELEGRAM_MAX_LEN - len(f"{title_html}\n\n\n\n{link_html}")
    if summary_html and len(summary_html) > budget:
        summary_html = summary_html[: max(0, budget - 3)].rsplit(" ", 1)[0] + "..."

    parts = [title_html]
    if summary_html:
        parts.append(summary_html)
    parts.append(link_html)
    return "\n\n".join(parts)


def sort_key(entry):
    return entry.get("published_parsed") or entry.get("updated_parsed") or time.gmtime(0)


def main():
    entries = fetch_entries(FEED_URLS)
    if not entries:
        print(f"No entries found across FEED_URLS={FEED_URLS}. Are these valid RSS feed URLs?")
        return

    entries.sort(key=sort_key)  # oldest first, interleaved across sources
    seen = load_seen(STATE_FILE)

    if seen is None:
        # First run: seed state without posting, so we don't dump the whole
        # archive into the channel at once.
        seen = {entry_id(e) for e in entries}
        save_seen(STATE_FILE, seen)
        print(f"First run: seeded {len(seen)} existing entries, no messages posted.")
        return

    new_entries = [e for e in entries if entry_id(e) not in seen][:MAX_ITEMS_PER_RUN]

    if not new_entries:
        print("No new entries.")
        return

    for entry in new_entries:
        title = entry.title
        summary = clean_summary(entry)
        link = entry.link

        try:
            # SKIP_TRANSLATION only means "post as-is" when there's no
            # ANTHROPIC_API_KEY to rewrite it into a unique post - once a
            # key is set, even already-Russian sources get rewritten rather
            # than copied verbatim.
            if SKIP_TRANSLATION and not os.environ.get("ANTHROPIC_API_KEY"):
                title_ru, summary_ru = title, summary
            else:
                title_ru, summary_ru = translate(title, summary)
            message = build_message(title_ru, summary_ru, link)
            send_message(BOT_TOKEN, CHAT_ID, message)
        except Exception as e:
            # Don't let one bad entry take down the whole run - the
            # already-posted entries above must still get committed.
            print(f"Failed to post entry {link!r}: {e}")
            continue

        seen.add(entry_id(entry))
        save_seen(STATE_FILE, seen)
        print(f"Posted: {title}")
        time.sleep(3)


if __name__ == "__main__":
    main()
