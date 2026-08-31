import os

CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID_CORP") or os.environ.get("TELEGRAM_CHAT_ID")

CLAUDE_DEFAULT_MODEL = "claude-haiku-4-5-20251001"
DEEPSEEK_DEFAULT_MODEL = "deepseek-chat"

# How many recent chat lines (both human and persona messages) get fed back
# to each persona as context for its reply.
HISTORY_LIMIT = int(os.environ.get("CORP_CHAT_HISTORY_LIMIT") or "40")


def _persona(key, default_name, default_role, token_env):
    provider = (os.environ.get(f"{key.upper()}_PROVIDER") or "anthropic").strip().lower()
    default_model = DEEPSEEK_DEFAULT_MODEL if provider == "deepseek" else CLAUDE_DEFAULT_MODEL
    return {
        "key": key,
        "display_name": os.environ.get(f"{key.upper()}_NAME") or default_name,
        "token_env": token_env,
        "provider": provider,
        "model": os.environ.get(f"{key.upper()}_MODEL") or default_model,
        "role_description": os.environ.get(f"{key.upper()}_ROLE") or default_role,
    }


# Names are placeholders (env-overridable) - the user said they'd pick real
# names later, so nothing here is hardcoded into the prompts/messages.
PERSONAS = [
    _persona(
        "lawyer",
        "Юрист",
        "корпоративный юрист компании: договорное право, корпоративные вопросы, "
        "трудовые споры, претензионная работа",
        "TELEGRAM_BOT_TOKEN_LAWYER",
    ),
    _persona(
        "accountant",
        "Главный бухгалтер",
        "главный бухгалтер компании: налоги, бухгалтерская и налоговая отчётность, "
        "расчёты с сотрудниками и контрагентами, финансовая дисциплина",
        "TELEGRAM_BOT_TOKEN_ACCOUNTANT",
    ),
]
