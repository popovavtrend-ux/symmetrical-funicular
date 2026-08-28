"""Fetches recent posts for X (Twitter) accounts.

Two backends:
- official: X API v2, used when X_BEARER_TOKEN is set. Reliable, but the
  read tier is paid (currently Basic and above).
- nitter: free public Nitter mirrors, tried in order until one responds.
  Nitter instances go down or get blocked often, so this backend is
  best-effort and may simply return nothing for a while.
"""

import os
import re

import feedparser
import requests

TAG_RE = re.compile("<[^<]+?>")
STATUS_ID_RE = re.compile(r"/status/(\d+)")

DEFAULT_NITTER_INSTANCES = [
    "https://nitter.net",
    "https://nitter.poast.org",
    "https://xcancel.com",
]


def _nitter_instances():
    raw = os.environ.get("NITTER_INSTANCES")
    if raw:
        return [i.strip().rstrip("/") for i in raw.split(",") if i.strip()]
    return DEFAULT_NITTER_INSTANCES


def _clean_html(text):
    return TAG_RE.sub("", text or "").strip()


def _fetch_via_nitter(username):
    for instance in _nitter_instances():
        url = f"{instance}/{username}/rss"
        try:
            parsed = feedparser.parse(url)
        except Exception as e:
            print(f"Nitter instance {instance} failed for @{username}: {e}")
            continue
        if not parsed.entries:
            continue

        posts = []
        for entry in parsed.entries:
            link = getattr(entry, "link", "") or ""
            match = STATUS_ID_RE.search(link)
            if not match:
                # Not a real tweet permalink - some mirrors return a single
                # placeholder/error item (e.g. linking back to the feed
                # itself) instead of failing outright. Skip it.
                continue
            status_id = match.group(1)
            posts.append(
                {
                    "id": status_id,
                    "text": _clean_html(getattr(entry, "summary", "") or entry.title),
                    "url": f"https://x.com/{username}/status/{status_id}",
                    "author": username,
                }
            )
        if posts:
            return posts
        # This instance responded but had nothing that looked like a real
        # tweet - try the next mirror instead of reporting a false "no posts".
        print(f"Nitter instance {instance} returned no valid tweets for @{username}, trying next")
    return []


def _fetch_via_official_api(username, bearer_token):
    headers = {"Authorization": f"Bearer {bearer_token}"}

    user_resp = requests.get(
        f"https://api.twitter.com/2/users/by/username/{username}",
        headers=headers,
        timeout=30,
    )
    user_resp.raise_for_status()
    user_id = user_resp.json()["data"]["id"]

    tweets_resp = requests.get(
        f"https://api.twitter.com/2/users/{user_id}/tweets",
        headers=headers,
        params={
            "max_results": 5,
            "exclude": "retweets,replies",
            "tweet.fields": "created_at",
        },
        timeout=30,
    )
    tweets_resp.raise_for_status()
    data = tweets_resp.json().get("data", [])

    posts = []
    for tweet in data:
        posts.append(
            {
                "id": tweet["id"],
                "text": tweet["text"],
                "url": f"https://x.com/{username}/status/{tweet['id']}",
                "author": username,
            }
        )
    return posts


def fetch_recent_posts(username):
    bearer_token = os.environ.get("X_BEARER_TOKEN")
    if bearer_token:
        try:
            return _fetch_via_official_api(username, bearer_token)
        except Exception as e:
            print(f"Official X API failed for @{username}, falling back to Nitter: {e}")
    return _fetch_via_nitter(username)
