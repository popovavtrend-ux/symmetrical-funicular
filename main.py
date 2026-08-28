import html
import os
import re
import time

from fetch_feed import fetch_entries
from state import load_seen, save_seen
from telegram_post import send_message
from translate import translate

DEFAULT_FEED_URLS = "https://protos.com/feed/,https://www.dlnews.com/rss/"

FEED_URLS = [u.strip() for u in (os.environ.get("FEED_URL") or DEFAULT_FEED_URLS).split(",") if u.strip()]
STATE_FILE = os.environ.get("STATE_FILE") or "data/seen_ids.json"
MAX_ITEMS_PER_RUN = int(os.environ.get("MAX_ITEMS_PER_RUN") or "5")
# Optional: force a single display name for all sources instead of each
# feed's own <title> (handy for a single-source setup).
SOURCE_NAME_OVERRIDE = os.environ.get("SOURCE_NAME")
SKIP_TRANSLATION = (os.environ.get("SKIP_TRANSLATION") or "").strip().lower() in ("1", "true", "yes")

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

TAG_RE = re.compile("<[^<]+?>")
WP_APPEARED_FIRST_RE = re.compile(r"\s*The post .+ appeared first on .+?\.\s*$")


def entry_id(entry):
    return getattr(entry, "id", None) or entry.link


def clean_summary(entry):
    summary = getattr(entry, "summary", "") or ""
    summary = TAG_RE.sub("", summary).strip()
    summary = WP_APPEARED_FIRST_RE.sub("", summary).strip()
    if len(summary) > 500:
        summary = summary[:497].rsplit(" ", 1)[0] + "..."
    return summary


def build_message(title_ru, summary_ru, link, source_name):
    parts = [f"<b>{html.escape(title_ru)}</b>"]
    if summary_ru:
        parts.append(html.escape(summary_ru))
    parts.append(f'🔗 <a href="{link}">Читать оригинал ({html.escape(source_name)})</a>')
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
        source_name = SOURCE_NAME_OVERRIDE or entry.get("_source_name") or "источник"

        try:
            if SKIP_TRANSLATION:
                title_ru, summary_ru = title, summary
            else:
                title_ru, summary_ru = translate(title, summary)
            message = build_message(title_ru, summary_ru, link, source_name)
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
