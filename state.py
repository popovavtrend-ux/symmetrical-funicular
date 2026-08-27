import json
import os


def load_seen(path):
    """Returns None if this is the very first run (no state file yet)."""
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return set(json.load(f))


def save_seen(path, seen_ids):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sorted(seen_ids), f, ensure_ascii=False, indent=2)
