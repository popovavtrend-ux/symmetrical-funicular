import json
import os

CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID_CORP") or os.environ.get("TELEGRAM_CHAT_ID")

CLAUDE_DEFAULT_MODEL = "claude-haiku-4-5-20251001"
DEEPSEEK_DEFAULT_MODEL = "deepseek-chat"

# The team roster lives in a plain JSON file (not code) so adding/renaming
# people later is just editing team.json + adding a bot token secret, no
# code changes.
TEAM_FILE = os.environ.get("CORP_CHAT_TEAM_FILE") or "team.json"

# How many recent chat lines (both human and persona messages) get fed back
# to each persona as context for its reply.
HISTORY_LIMIT = int(os.environ.get("CORP_CHAT_HISTORY_LIMIT") or "40")

# Reply timing: each scheduled reply gets a random delay in this range so
# the chat doesn't feel like an instant bot. A "secondary" commenter (someone
# adding their two cents after the main responder) gets extra delay on top.
MIN_REPLY_DELAY_SEC = int(os.environ.get("CORP_CHAT_MIN_DELAY_SEC") or "60")
MAX_REPLY_DELAY_SEC = int(os.environ.get("CORP_CHAT_MAX_DELAY_SEC") or "1800")
SECONDARY_EXTRA_DELAY_SEC = int(os.environ.get("CORP_CHAT_SECONDARY_EXTRA_DELAY_SEC") or "600")

# Which model decides *who* on the team should answer a given message.
ROUTING_PROVIDER = (os.environ.get("CORP_CHAT_ROUTING_PROVIDER") or "anthropic").strip().lower()
ROUTING_MODEL = os.environ.get("CORP_CHAT_ROUTING_MODEL") or (
    DEEPSEEK_DEFAULT_MODEL if ROUTING_PROVIDER == "deepseek" else CLAUDE_DEFAULT_MODEL
)

# Who a persona defers to (in-character, e.g. "надо уточнить у ...") when
# asked for real confidential company data/records that weren't actually
# provided in the chat - personas must never invent such data themselves.
ACCESS_AUTHORITY = os.environ.get("CORP_CHAT_ACCESS_AUTHORITY") or "генерального директора"


def _load_team_file():
    with open(TEAM_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _persona(entry):
    key = entry["key"]
    provider = (os.environ.get(f"{key.upper()}_PROVIDER") or "anthropic").strip().lower()
    default_model = DEEPSEEK_DEFAULT_MODEL if provider == "deepseek" else CLAUDE_DEFAULT_MODEL
    return {
        "key": key,
        "display_name": os.environ.get(f"{key.upper()}_NAME") or entry["name"],
        "token_env": entry["token_env"],
        "provider": provider,
        "model": os.environ.get(f"{key.upper()}_MODEL") or default_model,
        "role_description": os.environ.get(f"{key.upper()}_ROLE") or entry["role"],
    }


_team_data = _load_team_file()
COMPANY_DESCRIPTION = os.environ.get("CORP_CHAT_COMPANY_DESCRIPTION") or _team_data.get("company_description") or ""
PERSONAS = [_persona(e) for e in _team_data["team"]]


def team_roster_text(personas):
    """personas: only the ones actually wired up (have a bot token) -
    keeps the routing model from picking a colleague who can't reply."""
    return "\n".join(f"- {p['display_name']}: {p['role_description']}" for p in personas) or "(команда пуста)"
