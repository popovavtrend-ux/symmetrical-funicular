import requests

API_BASE = "https://api.telegram.org/bot{token}/{method}"
FILE_BASE = "https://api.telegram.org/file/bot{token}/{file_path}"


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


def download_file_bytes(token, file_id):
    """Fetches a file's bytes via Telegram's two-step file API (getFile for
    the path, then a plain GET on the file host - not a bot method call)."""
    info = _call(token, "getFile", file_id=file_id)
    url = FILE_BASE.format(token=token, file_path=info["file_path"])
    resp = requests.get(url, timeout=60)
    if not resp.ok:
        raise RuntimeError(f"Telegram file download error {resp.status_code}: {resp.text[:200]}")
    return resp.content


def send_document(token, chat_id, filename, file_bytes, caption=None):
    url = API_BASE.format(token=token, method="sendDocument")
    data = {"chat_id": chat_id}
    if caption:
        data["caption"] = caption[:1024]
    resp = requests.post(url, data=data, files={"document": (filename, file_bytes)}, timeout=120)
    if not resp.ok:
        raise RuntimeError(f"Telegram API error {resp.status_code}: {resp.text}")
    result = resp.json()
    if not result.get("ok"):
        raise RuntimeError(f"Telegram API error: {result}")
    return result["result"]
