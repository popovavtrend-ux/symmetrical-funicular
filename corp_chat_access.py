"""File-ownership and access-request/grant bookkeeping for corp_chat.py.

Rule: whoever sends a file into the chat owns it. Anyone else who replies to
that file (or to a pending request about it) is asking for access; the
owner unlocks it for them by replying in that same thread with something
like "да, даю доступ". Everything here is plain dict/list state so it
round-trips through the JSON state file untouched - no file bytes involved,
just file_ids and Telegram user ids.
"""

GRANT_KEYWORDS = ("да", "дава", "разреш", "хорошо", "ладно", "открыт", "предостав", "конечно", "можно", "ок")
MAX_TRACKED_ENTRIES = 300


def register_file_message(file_owners, file_messages, message_id, attachments, owner_id, owner_name):
    if not attachments:
        return
    for a in attachments:
        file_owners.setdefault(a["file_id"], {"owner_id": owner_id, "owner_name": owner_name})
    file_messages[str(message_id)] = attachments
    _trim(file_owners)
    _trim(file_messages)


def resolve_reply_target(reply_to_id, file_messages, access_requests, file_owners):
    """What file(s) - and whose - does this reply refer to?
    Returns (attachments, owner_id), or (None, None) if it's not a reply to
    a tracked file message or access request."""
    if not reply_to_id:
        return None, None
    if reply_to_id in file_messages:
        atts = file_messages[reply_to_id]
        return atts, file_owners.get(atts[0]["file_id"], {}).get("owner_id")
    if reply_to_id in access_requests:
        req = access_requests[reply_to_id]
        return req["attachments"], req["owner_id"]
    return None, None


def has_access(grants, owner_id, requester_id, attachments):
    granted = set(grants.get(f"{owner_id}:{requester_id}", []))
    return all(a["file_id"] in granted for a in attachments)


def register_access_request(access_requests, message_id, attachments, requester_id, owner_id):
    access_requests[str(message_id)] = {"attachments": attachments, "requester_id": requester_id, "owner_id": owner_id}
    _trim(access_requests)


def looks_like_grant(text, reply_is_direct_request):
    """reply_is_direct_request=True means this is a reply straight to
    someone's "can I get access" message - context is unambiguous, so a
    plain "да"/"ок" counts. Replying to the original file message instead is
    more ambiguous (could be about anything), so require it to actually
    mention access."""
    lowered = (text or "").lower()
    if reply_is_direct_request:
        return any(k in lowered for k in GRANT_KEYWORDS)
    return "доступ" in lowered and any(k in lowered for k in GRANT_KEYWORDS)


def grant_access(grants, access_requests, owner_id, attachments, reply_to_id):
    """Unlocks `attachments` for whoever's pending request this reply
    resolves to - a specific requester if replying straight to their
    request, otherwise everyone currently asking for any of these files."""
    file_ids = [a["file_id"] for a in attachments]
    req = access_requests.get(reply_to_id)
    if req and req["owner_id"] == owner_id:
        requester_ids = {req["requester_id"]}
    else:
        requester_ids = {
            r["requester_id"]
            for r in access_requests.values()
            if r["owner_id"] == owner_id and any(a["file_id"] in file_ids for a in r["attachments"])
        }
    for requester_id in requester_ids:
        key = f"{owner_id}:{requester_id}"
        grants[key] = sorted(set(grants.get(key, [])) | set(file_ids))
    return requester_ids


def _trim(d, limit=MAX_TRACKED_ENTRIES):
    if len(d) > limit:
        for key in list(d.keys())[: len(d) - limit]:
            del d[key]
