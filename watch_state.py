"""Shared state-file logic for the two intraday anomaly watchers
(market_watch_crypto.py, market_watch_traditional.py) - each instrument's
last-known reference price lives in a small JSON file, keyed by instrument
id, one file per watcher.

The rule is the same for every instrument in every category: the first
time we ever see it, we just remember its price - nothing to compare
against yet, so no alert. After that, every check compares the current
price to the stored reference; crossing the threshold fires an alert AND
resets the reference to the current price, so the next alert (if any) is
measured from here, not from a fixed start-of-day value."""

import json
import os


def load_state(path):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(path, state):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def check_threshold(state, key, current_price, threshold_pct):
    """Returns the % change from the stored reference if it crosses
    threshold_pct (either direction), else None. Mutates state in place -
    seeds a first-seen instrument, and resets the reference on every
    instrument that fires."""
    if not current_price:
        return None
    reference = state.get(key)
    if not reference:
        state[key] = current_price
        return None
    pct = (current_price - reference) / reference * 100
    if abs(pct) >= threshold_pct:
        state[key] = current_price
        return pct
    return None
