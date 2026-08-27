import html
import os
import re
import time

from fetch_feed import fetch_entries
from state import load_seen, save_seen
from telegram_post import send_message
from translate import translate

FEED_URL = os.environ.get("FEED_URL", "https://www.dlnews.com/rss/")
STATE_FILE = os.environ.get("STATE_FILE", "data/seen_ids.json")
MAX_ITEMS_PER_RUN = int(os.environ.get("MAX_ITEMS_PER_RUN", "5"))
SOURCE_NAME = os.environ.get("SOURCE_NAME", "DL News")

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

TAG_RE = re.compile("<[^<]+?>")


def entry_id(entry):
    return getattr(entry, "id", None) or entry.link


def clean_summary(entry):
    summary = getattr(entry, "summary", "") or ""
    summary = TAG_RE.sub("", summary).strip()
    if len(summary) > 500:
        summary = summary[:497].rsplit(" ", 1)[0] + "..."
    return summary


def build_message(title_ru, summary_ru, link):
    parts = [f"<b>{html.escape(title_ru)}</b>"]
    if summary_ru:
        parts.append(html.escape(summary_ru))
    parts.append(f'🔗 <a href="{link}">Читать оригинал ({html.escape(SOURCE_NAME)})</a>')
    return "\n\n".join(parts)


def main():
    entries = fetch_entries(FEED_URL)
    if not entries:
        print("No entries found in feed, nothing to do.")
        return

    entries = list(reversed(entries))  # oldest first
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

        title_ru, summary_ru = translate(title, summary)
        message = build_message(title_ru, summary_ru, link)

        send_message(BOT_TOKEN, CHAT_ID, message)
        seen.add(entry_id(entry))
        save_seen(STATE_FILE, seen)
        print(f"Posted: {title}")
        time.sleep(3)


if __name__ == "__main__":
    main()
