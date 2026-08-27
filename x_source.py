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
        if parsed.bozo and not parsed.entries:
            continue
        if not parsed.entries:
            continue

        posts = []
        for entry in parsed.entries:
            posts.append(
                {
                    "id": getattr(entry, "id", None) or entry.link,
                    "text": _clean_html(getattr(entry, "summary", "") or entry.title),
                    "url": entry.link.replace(instance, "https://x.com") if instance in entry.link else entry.link,
                    "author": username,
                }
            )
        return posts
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
