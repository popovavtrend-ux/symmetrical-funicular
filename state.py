import json
import os


def load_state(path):
    """Returns None if this is the very first run (no state file yet).

    Otherwise returns {"seen_ids": set(...), "seeded_feeds": set(...)}.
    Transparently upgrades the old flat-list format (a JSON array of ids,
    with no per-feed seeding tracking).
    """
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return {"seen_ids": set(data), "seeded_feeds": set()}
    return {"seen_ids": set(data["seen_ids"]), "seeded_feeds": set(data["seeded_feeds"])}


def save_state(path, state):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "seen_ids": sorted(state["seen_ids"]),
                "seeded_feeds": sorted(state["seeded_feeds"]),
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
