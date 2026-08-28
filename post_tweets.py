import html
import json
import os
import time

from compose import compose_post
from telegram_post import send_message
from x_accounts import get_accounts
from x_source import fetch_recent_posts

STATE_FILE = os.environ.get("X_STATE_FILE", "data/seen_tweets.json")
MAX_ITEMS_PER_ACCOUNT = int(os.environ.get("MAX_TWEETS_PER_ACCOUNT_PER_RUN", "3"))

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]


def load_state(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(path, state):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def build_message(post_ru_text, url):
    return f"{html.escape(post_ru_text)}\n\n🔗 <a href=\"{url}\">Оригинал в X</a>"


def process_account(username, state):
    posts = fetch_recent_posts(username)
    if not posts:
        print(f"@{username}: no posts fetched (feed empty or unavailable).")
        return

    posts = list(reversed(posts))  # oldest first
    seen_ids = set(state.get(username, []))

    if username not in state:
        # First run for this account: seed without posting, so we don't
        # dump their recent history into the channel at once.
        state[username] = [p["id"] for p in posts]
        save_state(STATE_FILE, state)
        print(f"@{username}: first run, seeded {len(posts)} posts, nothing posted.")
        return

    new_posts = [p for p in posts if p["id"] not in seen_ids][:MAX_ITEMS_PER_ACCOUNT]
    if not new_posts:
        print(f"@{username}: no new posts.")
        return

    for post in new_posts:
        try:
            post_ru_text = compose_post(username, post["text"], post["url"])
            message = build_message(post_ru_text, post["url"])
            send_message(BOT_TOKEN, CHAT_ID, message)
        except Exception as e:
            # Don't let one bad post take down the whole run - already
            # posted entries above must still get committed.
            print(f"@{username}: failed to post {post['id']}: {e}")
            continue

        seen_ids.add(post["id"])
        state[username] = sorted(seen_ids)
        save_state(STATE_FILE, state)
        print(f"@{username}: posted {post['id']}")
        time.sleep(3)


def main():
    state = load_state(STATE_FILE)
    for username in get_accounts():
        try:
            process_account(username, state)
        except Exception as e:
            # One account's failure shouldn't block the rest.
            print(f"@{username}: unexpected error, skipping: {e}")


if __name__ == "__main__":
    main()
