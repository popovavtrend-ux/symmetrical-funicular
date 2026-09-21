"""Looks up why a specific instrument made the sudden move that just
triggered an alert - used only when market_watch_*.py actually fires,
never on routine checks, so this doesn't touch the LLM budget outside of
real anomalies.

Claude's built-in web-search tool does the actual searching; this just
asks a narrow, current question and extracts a short answer. News about a
move that just started may not be published yet - "found nothing" isn't
final, callers should retry a bit later (see watch_state.pending_*)."""

import os
from datetime import datetime, timedelta, timezone

MSK = timezone(timedelta(hours=3))

NOT_FOUND = "NONE"


def _final_text(response):
    """Concatenates every text block instead of taking just the first one -
    with the web-search tool, Claude's answer can come back as several text
    segments interleaved with citations and search-result blocks."""
    return "".join(getattr(b, "text", "") for b in response.content if getattr(b, "type", None) == "text").strip()


def search_move_explanation(label, pct, category, when=None):
    """Returns a short Russian explanation (with its source named inline)
    or None if nothing credible turned up yet. category is a short hint
    like "криптовалюта" or "акция" so the search query is specific instead
    of just the bare ticker."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None

    from anthropic_client import create_message, get_client

    when = when or datetime.now(MSK)
    direction = "вырос" if pct >= 0 else "упал"
    date_str = when.strftime("%d.%m.%Y")

    client = get_client()
    prompt = (
        f"Сейчас {date_str}. {label} ({category}) только что {direction} "
        f"на {abs(pct):.1f}% за короткий промежуток времени. Найди в "
        "свежих новостях (за последние несколько часов) правдоподобную "
        "причину этого движения. Если находишь такую причину в надёжном "
        "источнике - ответь ОДНИМ коротким предложением на русском, что "
        "произошло и почему, и укажи источник в конце через тире, "
        "например: 'ФРС повысила ставку сильнее ожиданий — Reuters.' "
        f"Если ничего убедительного и достаточно свежего не находишь - "
        f"ответь ровно словом {NOT_FOUND}, без объяснений и рассуждений."
    )
    try:
        response = create_message(
            client,
            max_tokens=400,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as e:
        print(f"Move-explanation search failed for {label}: {e}")
        return None

    text = _final_text(response)
    if not text or NOT_FOUND in text.upper():
        return None
    return text
