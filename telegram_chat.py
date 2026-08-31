import requests

API_BASE = "https://api.telegram.org/bot{token}/{method}"


def _call(token, method, **params):
    url = API_BASE.format(token=token, method=method)
    resp = requests.post(url, data=params, timeout=30)
    if not resp.ok:
        raise RuntimeError(f"Telegram API error {resp.status_code}: {resp.text}")
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API error: {data}")
    return data["result"]


def get_me(token):
    return _call(token, "getMe")


def get_updates(token, offset=None, timeout=0):
    """Short poll (no long-polling - each run is a one-shot GitHub Actions
    job, not a persistent process)."""
    params = {"timeout": timeout, "allowed_updates": '["message"]'}
    if offset is not None:
        params["offset"] = offset
    return _call(token, "getUpdates", **params)


def send_text(token, chat_id, text):
    # No parse_mode: replies are free-form AI-generated text that may
    # contain characters (e.g. "<", "&") that would break HTML parsing.
    return _call(token, "sendMessage", chat_id=chat_id, text=text, disable_web_page_preview=True)
